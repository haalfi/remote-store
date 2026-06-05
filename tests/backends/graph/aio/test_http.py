"""Graph request primitive and pagination (GR-008/016/028/029/033/035).

respx stubs ``httpx.AsyncClient`` so the real ``graph_send`` / ``iter_pages``
code paths run against canned responses (no network, no live wire).
"""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from remote_store._config import RetryPolicy
from remote_store._errors import BackendUnavailable, NotFound, PermissionDenied, ResourceLocked
from remote_store.aio.backends._graph import http as graph_http
from remote_store.aio.backends._graph.http import acquire_token, graph_send, iter_pages

_ME_DRIVE = "https://graph.microsoft.com/v1.0/me/drive"

# A retry policy with zero waits: the backoff/jitter terms collapse to 0 so the
# loop spins through attempts without real sleeps, keeping the unit tests fast.
_FAST_RETRY = RetryPolicy(max_attempts=3, backoff_base=0.0, backoff_max=0.0, jitter=0.0)


class _CountingProvider:
    """Sync token provider that records how many times it was invoked."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return f"token-{self.calls}"


class TestAcquireToken:
    """GR-008: both sync and async token-provider shapes are supported."""

    @pytest.mark.spec("GR-008")
    async def test_sync_provider(self) -> None:
        assert await acquire_token(lambda: "sync-tok") == "sync-tok"

    @pytest.mark.spec("GR-008")
    async def test_async_provider(self) -> None:
        async def provider() -> str:
            return "async-tok"

        assert await acquire_token(provider) == "async-tok"


class TestGraphSend:
    """The authenticated request primitive (GR-028/029/033/035)."""

    @respx.mock
    @pytest.mark.spec("GR-008")
    async def test_success_attaches_bearer_token(self) -> None:
        route = respx.get(_ME_DRIVE).mock(return_value=httpx.Response(200, json={"id": "d1"}))
        async with httpx.AsyncClient() as client:
            resp = await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "abc")
        assert resp.json() == {"id": "d1"}
        assert route.calls.last.request.headers["Authorization"] == "Bearer abc"

    @respx.mock
    @pytest.mark.spec("GR-029")
    async def test_401_triggers_one_refresh_and_retries(self) -> None:
        provider = _CountingProvider()
        respx.get(_ME_DRIVE).mock(
            side_effect=[
                httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken"}}),
                httpx.Response(200, json={"id": "d1"}),
            ]
        )
        async with httpx.AsyncClient() as client:
            resp = await graph_send(client, "GET", _ME_DRIVE, token_provider=provider)
        assert resp.status_code == 200
        assert provider.calls == 2  # initial + one refresh

    @respx.mock
    @pytest.mark.spec("GR-029")
    async def test_second_401_maps_to_permission_denied(self) -> None:
        respx.get(_ME_DRIVE).mock(
            return_value=httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken"}})
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(PermissionDenied):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t")

    @respx.mock
    @pytest.mark.spec("GR-029")
    async def test_non_refresh_401_maps_without_retry(self) -> None:
        # A 401 with any code other than InvalidAuthenticationToken is a
        # permission failure that a refresh cannot fix: map straight to
        # PermissionDenied, with no second token acquisition (GR-029).
        provider = _CountingProvider()
        route = respx.get(_ME_DRIVE).mock(return_value=httpx.Response(401, json={"error": {"code": "unauthenticated"}}))
        async with httpx.AsyncClient() as client:
            with pytest.raises(PermissionDenied):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=provider)
        assert provider.calls == 1  # no refresh attempt
        assert route.call_count == 1  # request issued exactly once

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_non_401_error_is_mapped(self) -> None:
        respx.get(_ME_DRIVE).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with httpx.AsyncClient() as client:
            with pytest.raises(NotFound):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", path="missing")

    @respx.mock
    @pytest.mark.spec("GR-033")
    async def test_transport_error_is_backend_unavailable(self) -> None:
        respx.get(_ME_DRIVE).mock(side_effect=httpx.ConnectError("no route"))
        async with httpx.AsyncClient() as client:
            with pytest.raises(BackendUnavailable):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t")

    @respx.mock
    @pytest.mark.spec("GR-033")
    async def test_non_json_error_body_classifies_without_code(self) -> None:
        # A 5xx with a plain-text body: error_code() can't parse it, so the
        # mapper falls back to status-only classification (GR-033).
        respx.get(_ME_DRIVE).mock(return_value=httpx.Response(503, text="Service Unavailable"))
        async with httpx.AsyncClient() as client:
            with pytest.raises(BackendUnavailable):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t")

    @respx.mock
    @pytest.mark.spec("GR-029")
    async def test_transport_error_during_refresh_retry(self) -> None:
        respx.get(_ME_DRIVE).mock(
            side_effect=[
                httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken"}}),
                httpx.ConnectError("dropped"),
            ]
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(BackendUnavailable):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=_CountingProvider())

    @respx.mock
    @pytest.mark.spec("GR-035")
    async def test_debug_log_redacts_token(self, caplog: pytest.LogCaptureFixture) -> None:
        respx.get(_ME_DRIVE).mock(return_value=httpx.Response(200, json={"id": "d1"}))
        with caplog.at_level(logging.DEBUG, logger="remote_store.aio.backends._graph"):
            async with httpx.AsyncClient() as client:
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "super-secret")
        joined = "\n".join(r.getMessage() for r in caplog.records)
        assert "super-secret" not in joined
        assert "***" in joined


class TestIterPages:
    """Pagination over ``@odata.nextLink`` (GR-016)."""

    _BASE = "https://graph.microsoft.com/v1.0/sites/s1/drives"
    # Distinct page-2 path: ``nextLink`` is an opaque absolute URL, and a
    # same-path-with-query route would also match the page-1 request (respx
    # does not constrain query by default), looping forever.
    _PAGE2 = "https://graph.microsoft.com/v1.0/sites/s1/drives/_page2"

    @respx.mock
    @pytest.mark.spec("GR-016")
    async def test_follows_next_link_then_terminates(self) -> None:
        respx.get(self._BASE).mock(
            return_value=httpx.Response(200, json={"value": [{"id": "a"}], "@odata.nextLink": self._PAGE2})
        )
        respx.get(self._PAGE2).mock(return_value=httpx.Response(200, json={"value": [{"id": "b"}]}))
        async with httpx.AsyncClient() as client:
            pages = [p async for p in iter_pages(client, self._BASE, token_provider=lambda: "t")]
        assert [d["id"] for page in pages for d in page["value"]] == ["a", "b"]

    @respx.mock
    @pytest.mark.spec("GR-016")
    async def test_empty_value_with_next_link_is_followed(self) -> None:
        respx.get(self._BASE).mock(return_value=httpx.Response(200, json={"value": [], "@odata.nextLink": self._PAGE2}))
        respx.get(self._PAGE2).mock(return_value=httpx.Response(200, json={"value": [{"id": "b"}]}))
        async with httpx.AsyncClient() as client:
            pages = [p async for p in iter_pages(client, self._BASE, token_provider=lambda: "t")]
        assert len(pages) == 2  # the empty first page was not treated as the end

    @respx.mock
    @pytest.mark.spec("GR-016")
    async def test_malformed_next_link_is_backend_unavailable(self) -> None:
        respx.get(self._BASE).mock(return_value=httpx.Response(200, json={"value": [], "@odata.nextLink": "not-a-url"}))
        async with httpx.AsyncClient() as client:
            with pytest.raises(BackendUnavailable):
                async for _ in iter_pages(client, self._BASE, token_provider=lambda: "t"):
                    pass

    @respx.mock
    @pytest.mark.spec("GR-016")
    async def test_cross_host_next_link_is_backend_unavailable(self) -> None:
        # A well-formed but cross-host nextLink must NOT be followed: each page is
        # re-fetched through graph_send with the bearer token attached, so a foreign
        # host would receive the token. The scheme check alone would let this pass.
        respx.get(self._BASE).mock(
            return_value=httpx.Response(200, json={"value": [], "@odata.nextLink": "https://evil.example/p2"})
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(BackendUnavailable):
                async for _ in iter_pages(client, self._BASE, token_provider=lambda: "t"):
                    pass


@pytest.fixture
def record_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the retry loop's ``asyncio.sleep`` with a no-op that records waits.

    Lets the Retry-After precedence tests assert the *computed* backoff without
    waiting wall-clock seconds for it. Patches the symbol the ``http`` module
    actually calls (``http.asyncio.sleep``); monkeypatch restores it.
    """
    delays: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(graph_http.asyncio, "sleep", _fake_sleep)
    return delays


class TestGraphSendRetry:
    """RetryPolicy folded into ``graph_send`` (GR-047 / GR-048, RET-015)."""

    @respx.mock
    @pytest.mark.spec("GR-047")
    async def test_retryable_5xx_retries_then_succeeds(self) -> None:
        route = respx.get(_ME_DRIVE).mock(
            side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"id": "d1"})]
        )
        async with httpx.AsyncClient() as client:
            resp = await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=_FAST_RETRY)
        assert resp.status_code == 200
        assert route.call_count == 3  # two transient failures, then success

    @respx.mock
    @pytest.mark.spec("GR-047")
    async def test_retry_exhausted_raises_last_mapped_error(self) -> None:
        route = respx.get(_ME_DRIVE).mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient() as client:
            with pytest.raises(BackendUnavailable):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=_FAST_RETRY)
        assert route.call_count == 3  # max_attempts, all exhausted

    @respx.mock
    @pytest.mark.spec("GR-047")
    async def test_429_is_retried(self) -> None:
        route = respx.get(_ME_DRIVE).mock(
            side_effect=[
                httpx.Response(429, json={"error": {"code": "activityLimitReached"}}),
                httpx.Response(200, json={"id": "d1"}),
            ]
        )
        async with httpx.AsyncClient() as client:
            resp = await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=_FAST_RETRY)
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.spec("GR-047")
    async def test_transport_error_is_retried(self) -> None:
        route = respx.get(_ME_DRIVE).mock(
            side_effect=[httpx.ConnectError("reset"), httpx.Response(200, json={"id": "d1"})]
        )
        async with httpx.AsyncClient() as client:
            resp = await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=_FAST_RETRY)
        assert resp.status_code == 200
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.spec("GR-048")
    async def test_retry_after_delta_seconds_is_the_delay_floor(self, record_sleeps: list[float]) -> None:
        # Retry-After: 7 (delta-seconds). The zero-backoff policy computes 0, so
        # the header value is what governs the wait.
        respx.get(_ME_DRIVE).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "7"}, json={"error": {"code": "activityLimitReached"}}),
                httpx.Response(200, json={"id": "d1"}),
            ]
        )
        async with httpx.AsyncClient() as client:
            await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=_FAST_RETRY)
        assert record_sleeps == [7.0]

    @respx.mock
    @pytest.mark.spec("GR-048")
    async def test_retry_after_http_date_is_parsed(self, record_sleeps: list[float]) -> None:
        # Retry-After as an HTTP-date far in the future: parsing must yield a
        # large positive delta (proving the date branch ran), dominating the
        # zero backoff. The patched sleep records but does not wait.
        respx.get(_ME_DRIVE).mock(
            side_effect=[
                httpx.Response(
                    503, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}, json={"error": {"code": "x"}}
                ),
                httpx.Response(200, json={"id": "d1"}),
            ]
        )
        async with httpx.AsyncClient() as client:
            await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=_FAST_RETRY)
        assert len(record_sleeps) == 1
        assert record_sleeps[0] > 1_000_000  # seconds until 2099 — the date was parsed, not ignored

    @respx.mock
    @pytest.mark.spec("GR-047")
    async def test_timeout_budget_stops_the_loop_early(self, record_sleeps: list[float]) -> None:
        # A large backoff against a tiny wall-clock budget: the loop must give up
        # before a second request rather than wait out the backoff.
        route = respx.get(_ME_DRIVE).mock(return_value=httpx.Response(503))
        policy = RetryPolicy(max_attempts=5, backoff_base=10.0, backoff_max=60.0, jitter=0.0, timeout=0.05)
        async with httpx.AsyncClient() as client:
            with pytest.raises(BackendUnavailable):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=policy)
        assert route.call_count == 1  # budget spent before the backoff could elapse
        assert record_sleeps == []  # never slept — the timeout check short-circuited

    @respx.mock
    @pytest.mark.spec("GR-048")
    async def test_large_retry_after_against_small_budget_short_circuits(self, record_sleeps: list[float]) -> None:
        # The realistic throttle case: the server says "wait 60s" via Retry-After
        # while the retry budget is 0.5s. The budget guard runs on the
        # Retry-After-raised delay, so the loop gives up rather than sleeping past
        # the budget — the Retry-After/timeout interaction the two are tested for
        # only in isolation otherwise.
        route = respx.get(_ME_DRIVE).mock(
            return_value=httpx.Response(
                429, headers={"Retry-After": "60"}, json={"error": {"code": "activityLimitReached"}}
            )
        )
        policy = RetryPolicy(max_attempts=5, backoff_base=0.0, backoff_max=0.0, jitter=0.0, timeout=0.5)
        async with httpx.AsyncClient() as client:
            with pytest.raises(BackendUnavailable):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=policy)
        assert route.call_count == 1  # gave up before a second attempt
        assert record_sleeps == []  # the 60s Retry-After never slept — budget short-circuited

    @respx.mock
    @pytest.mark.spec("GR-045")
    async def test_terminal_resource_locked_is_not_retried(self) -> None:
        route = respx.get(_ME_DRIVE).mock(return_value=httpx.Response(423, json={"error": {"code": "resourceLocked"}}))
        async with httpx.AsyncClient() as client:
            with pytest.raises(ResourceLocked):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=_FAST_RETRY)
        assert route.call_count == 1  # terminal: raised on the first attempt

    @respx.mock
    @pytest.mark.spec("GR-054")
    async def test_terminal_507_is_not_retried(self) -> None:
        route = respx.get(_ME_DRIVE).mock(return_value=httpx.Response(507, json={"error": {"code": "x"}}))
        async with httpx.AsyncClient() as client:
            with pytest.raises(BackendUnavailable):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", retry=_FAST_RETRY)
        assert route.call_count == 1  # 507 does not clear on short-term retry

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_terminal_404_is_not_retried(self) -> None:
        route = respx.get(_ME_DRIVE).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with httpx.AsyncClient() as client:
            with pytest.raises(NotFound):
                await graph_send(client, "GET", _ME_DRIVE, token_provider=lambda: "t", path="x", retry=_FAST_RETRY)
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.spec("GR-029")
    async def test_auth_refresh_then_retryable_5xx_then_success(self) -> None:
        # The one-shot 401 refresh and the retry loop compose: a 401 refreshes
        # in-attempt, a following 503 drives a loop retry, then 200.
        provider = _CountingProvider()
        route = respx.get(_ME_DRIVE).mock(
            side_effect=[
                httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken"}}),
                httpx.Response(503),
                httpx.Response(200, json={"id": "d1"}),
            ]
        )
        async with httpx.AsyncClient() as client:
            resp = await graph_send(client, "GET", _ME_DRIVE, token_provider=provider, retry=_FAST_RETRY)
        assert resp.status_code == 200
        assert route.call_count == 3
        # attempt 0 acquires (1) then refreshes on the 401 (2); the loop's second
        # attempt re-acquires fresh (3) — every _send_attempt fetches a token.
        assert provider.calls == 3

    @pytest.mark.spec("GR-048")
    def test_parse_retry_after_handles_garbage(self) -> None:
        # Unparseable header → None, so the caller falls back to computed backoff.
        assert graph_http._parse_retry_after(None) is None
        assert graph_http._parse_retry_after("") is None
        assert graph_http._parse_retry_after("not-a-date") is None
        assert graph_http._parse_retry_after("12") == 12.0

    @pytest.mark.spec("GR-048")
    def test_parse_retry_after_naive_http_date_assumed_utc(self) -> None:
        # An HTTP-date without a timezone token parses to a naive datetime;
        # it is assumed UTC rather than rejected. Far-future → large positive.
        assert graph_http._parse_retry_after("Wed, 21 Oct 2099 07:28:00") > 1_000_000
