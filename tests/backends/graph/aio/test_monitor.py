"""Async copy/move monitor poller (ADR-0023, GR-026).

respx stubs the monitor URL so the real ``poll_monitor`` loop runs against canned
poll responses: pending→succeeded progression, the failed-status error mapping,
``copy_timeout`` expiry with the query-redacted monitor URL in the message,
``Retry-After`` precedence, transient 5xx / transport-error tolerance, and
``asyncio.CancelledError`` propagation. The monitor URL is polled unauthenticated
(live-verified: the pre-signed cross-host endpoint rejects a Graph bearer).
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest
import respx

from remote_store._errors import AlreadyExists, BackendUnavailable, NotFound, PermissionDenied
from remote_store.aio.backends._graph import monitor as graph_monitor
from remote_store.aio.backends._graph.monitor import (
    POLL_COMPLETE_MARKER,
    MonitorResult,
    parse_graph_monitor_response,
    poll_monitor,
)

# A pre-signed monitor URL carrying its own credential in the query (mirrors the
# live shape: a cross-host *.microsoftpersonalcontent.com endpoint).
_MONITOR = "https://my.microsoftpersonalcontent.com/op/01ABC?tempauth=secret-token-value"


@pytest.fixture
def _fast_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse the poll cadence to zero so pending→succeeded runs without waits."""
    monkeypatch.setattr(graph_monitor, "_INITIAL_INTERVAL", 0.0)
    monkeypatch.setattr(graph_monitor, "_MAX_INTERVAL", 0.0)
    monkeypatch.setattr(graph_monitor, "_BACKOFF_FACTOR", 1.0)


@pytest.fixture
def record_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace ``asyncio.sleep`` in the poller with a no-op that records its delay.

    Lets the interval / Retry-After tests assert the *computed* wait without
    actually sleeping. The poll loop must still terminate (succeed) so the
    recorder is not driven forever.
    """
    delays: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(graph_monitor.asyncio, "sleep", _fake_sleep)
    return delays


async def _poll(**kwargs: object) -> None:
    async with httpx.AsyncClient() as client:
        await poll_monitor(_MONITOR, client, **kwargs)  # type: ignore[arg-type]


# ===========================================================================
# parse_graph_monitor_response (pure)
# ===========================================================================


class TestParseMonitorResponse:
    @pytest.mark.spec("GR-026")
    def test_completed_status_is_succeeded(self) -> None:
        r = httpx.Response(200, json={"status": "completed", "percentageComplete": 100.0})
        assert parse_graph_monitor_response(r) == MonitorResult("succeeded")

    @pytest.mark.spec("GR-026")
    def test_in_progress_status_is_pending(self) -> None:
        r = httpx.Response(202, json={"status": "inProgress", "percentageComplete": 40.0})
        assert parse_graph_monitor_response(r) == MonitorResult("pending")

    @pytest.mark.spec("GR-026")
    def test_failed_status_carries_error_envelope(self) -> None:
        r = httpx.Response(200, json={"status": "failed", "error": {"code": "nameAlreadyExists", "message": "x"}})
        result = parse_graph_monitor_response(r)
        assert result.state == "failed"
        assert result.error == {"code": "nameAlreadyExists", "message": "x"}

    @pytest.mark.spec("GR-026")
    def test_redirect_is_succeeded(self) -> None:
        # A completion 3xx (Graph redirecting to the new item) is terminal success.
        r = httpx.Response(303, headers={"Location": "https://example/new"})
        assert parse_graph_monitor_response(r) == MonitorResult("succeeded")

    @pytest.mark.spec("GR-026")
    def test_body_without_status_is_unclassified_pending(self) -> None:
        assert parse_graph_monitor_response(httpx.Response(200, json={"foo": 1})).classified is False
        assert parse_graph_monitor_response(httpx.Response(200, text="<not-json>")).classified is False
        assert parse_graph_monitor_response(httpx.Response(200, json={"status": 5})).classified is False


# ===========================================================================
# poll_monitor — happy path
# ===========================================================================


@pytest.mark.usefixtures("_fast_poll")
class TestPollSuccess:
    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_single_poll_completed_returns_and_logs_marker(self, caplog: pytest.LogCaptureFixture) -> None:
        respx.get(_MONITOR).mock(return_value=httpx.Response(200, json={"status": "completed"}))
        with caplog.at_level(logging.DEBUG, logger="remote_store.aio.backends._graph"):
            await _poll(path="dst.txt")
        assert POLL_COMPLETE_MARKER in "\n".join(r.getMessage() for r in caplog.records)

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_pending_then_succeeded(self) -> None:
        route = respx.get(_MONITOR).mock(
            side_effect=[
                httpx.Response(202, json={"status": "inProgress"}),
                httpx.Response(202, json={"status": "notStarted"}),
                httpx.Response(200, json={"status": "completed"}),
            ]
        )
        await _poll(path="dst.txt")
        assert route.call_count == 3

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_marker_omits_the_presigned_url(self, caplog: pytest.LogCaptureFixture) -> None:
        # GR-035: the success DEBUG record must not carry the monitor URL's token.
        respx.get(_MONITOR).mock(return_value=httpx.Response(200, json={"status": "completed"}))
        with caplog.at_level(logging.DEBUG, logger="remote_store.aio.backends._graph"):
            await _poll(path="dst.txt")
        assert "secret-token-value" not in "\n".join(r.getMessage() for r in caplog.records)


# ===========================================================================
# poll_monitor — failed-status mapping (GR-026 -> standard error table)
# ===========================================================================


@pytest.mark.usefixtures("_fast_poll")
class TestPollFailure:
    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_failed_name_already_exists_maps_to_already_exists(self) -> None:
        respx.get(_MONITOR).mock(
            return_value=httpx.Response(200, json={"status": "failed", "error": {"code": "nameAlreadyExists"}})
        )
        with pytest.raises(AlreadyExists):
            await _poll(path="dst.txt")

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_failed_item_not_found_maps_to_not_found(self) -> None:
        respx.get(_MONITOR).mock(
            return_value=httpx.Response(200, json={"status": "failed", "error": {"code": "itemNotFound"}})
        )
        with pytest.raises(NotFound):
            await _poll(path="dst.txt")

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_failed_unknown_code_maps_to_backend_unavailable(self) -> None:
        respx.get(_MONITOR).mock(
            return_value=httpx.Response(200, json={"status": "failed", "error": {"code": "weirdNewCode"}})
        )
        with pytest.raises(BackendUnavailable, match="weirdNewCode"):
            await _poll(path="dst.txt")

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_failed_without_error_envelope_maps_to_backend_unavailable(self) -> None:
        respx.get(_MONITOR).mock(return_value=httpx.Response(200, json={"status": "failed"}))
        with pytest.raises(BackendUnavailable):
            await _poll(path="dst.txt")


# ===========================================================================
# poll_monitor — transient tolerance
# ===========================================================================


@pytest.mark.usefixtures("_fast_poll")
class TestPollTransient:
    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_5xx_during_poll_is_treated_as_pending(self) -> None:
        route = respx.get(_MONITOR).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(500),
                httpx.Response(200, json={"status": "completed"}),
            ]
        )
        await _poll(path="dst.txt")
        assert route.call_count == 3

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_transport_error_during_poll_is_treated_as_pending(self) -> None:
        route = respx.get(_MONITOR).mock(
            side_effect=[
                httpx.ConnectError("boom"),
                httpx.Response(200, json={"status": "completed"}),
            ]
        )
        await _poll(path="dst.txt")
        assert route.call_count == 2


# ===========================================================================
# poll_monitor — terminal HTTP 4xx on the poll request (BUG-218, GR-026)
# ===========================================================================


@pytest.mark.usefixtures("_fast_poll")
class TestPollHttpError:
    """A non-throttle 4xx on the poll *request* is terminal, not pending.

    A permission revoked mid-operation (403) or an expired / deleted monitor
    URL (404) must surface as a typed error rather than loop until
    ``copy_timeout`` — which defaults to ``None`` (unbounded), so treating
    these as pending would hang ``copy()``/``move()`` forever (BUG-218). A
    ``429`` is throttling, not failure, and must stay pending like a ``5xx``.
    """

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_404_during_poll_raises_not_found(self) -> None:
        route = respx.get(_MONITOR).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        with pytest.raises(NotFound):
            await _poll(path="dst.txt")
        assert route.call_count == 1  # raised on the first 4xx; no re-poll

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_403_during_poll_raises_permission_denied(self) -> None:
        respx.get(_MONITOR).mock(return_value=httpx.Response(403, json={"error": {"code": "accessDenied"}}))
        with pytest.raises(PermissionDenied):
            await _poll(path="dst.txt")

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_429_during_poll_stays_pending(self) -> None:
        # Throttling is transient, not terminal: keep polling like a 5xx.
        route = respx.get(_MONITOR).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json={"status": "completed"}),
            ]
        )
        await _poll(path="dst.txt")
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_408_during_poll_stays_pending(self) -> None:
        # 408 Request Timeout is transient (retryable by convention), not a
        # terminal failure: keep polling like a 5xx rather than raising.
        route = respx.get(_MONITOR).mock(
            side_effect=[
                httpx.Response(408),
                httpx.Response(200, json={"status": "completed"}),
            ]
        )
        await _poll(path="dst.txt")
        assert route.call_count == 2


# ===========================================================================
# poll_monitor — timeout expiry (GR-026 closed-set last_status)
# ===========================================================================


@pytest.mark.usefixtures("_fast_poll")
class TestPollTimeout:
    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_timeout_expiry_message_carries_count_and_pending_status(self) -> None:
        respx.get(_MONITOR).mock(return_value=httpx.Response(202, json={"status": "inProgress"}))
        with pytest.raises(BackendUnavailable) as exc:
            await _poll(path="dst.txt", timeout=0.05)
        msg = str(exc.value)
        assert "poll(s)" in msg
        assert "last_status=pending" in msg

    @respx.mock
    @pytest.mark.spec("GR-035")
    async def test_timeout_message_redacts_the_presigned_query(self) -> None:
        # GR-026 embeds the monitor URL for diagnosis; GR-035 bars the token. The
        # message carries scheme/host/path but never the ?tempauth=... query.
        respx.get(_MONITOR).mock(return_value=httpx.Response(202, json={"status": "inProgress"}))
        with pytest.raises(BackendUnavailable) as exc:
            await _poll(path="dst.txt", timeout=0.05)
        msg = str(exc.value)
        assert "my.microsoftpersonalcontent.com/op/01ABC" in msg
        assert "secret-token-value" not in msg
        assert "tempauth" not in msg

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_timeout_last_status_parse_error_on_unreadable_body(self) -> None:
        respx.get(_MONITOR).mock(return_value=httpx.Response(200, json={"no": "status"}))
        with pytest.raises(BackendUnavailable, match="last_status=parse-error"):
            await _poll(path="dst.txt", timeout=0.05)

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_timeout_last_status_5xx_when_server_errors(self) -> None:
        respx.get(_MONITOR).mock(return_value=httpx.Response(503))
        with pytest.raises(BackendUnavailable, match="last_status=5xx"):
            await _poll(path="dst.txt", timeout=0.05)

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_unbounded_timeout_none_polls_until_terminal(self) -> None:
        route = respx.get(_MONITOR).mock(
            side_effect=[
                httpx.Response(202, json={"status": "inProgress"}),
                httpx.Response(200, json={"status": "completed"}),
            ]
        )
        await _poll(path="dst.txt", timeout=None)
        assert route.call_count == 2


# ===========================================================================
# poll_monitor — interval / Retry-After cadence
# ===========================================================================


class TestPollCadence:
    @respx.mock
    @pytest.mark.spec("GR-048")
    async def test_retry_after_overrides_computed_interval_when_larger(
        self, monkeypatch: pytest.MonkeyPatch, record_sleep: list[float]
    ) -> None:
        monkeypatch.setattr(graph_monitor, "_INITIAL_INTERVAL", 1.0)
        monkeypatch.setattr(graph_monitor, "_MAX_INTERVAL", 30.0)
        respx.get(_MONITOR).mock(
            side_effect=[
                httpx.Response(202, json={"status": "inProgress"}, headers={"Retry-After": "7"}),
                httpx.Response(200, json={"status": "completed"}),
            ]
        )
        await _poll(path="dst.txt")
        # Computed interval is 1 s; Retry-After 7 s is larger, so it wins.
        assert record_sleep == [7.0]

    @respx.mock
    @pytest.mark.spec("GR-048")
    async def test_retry_after_ignored_when_smaller_than_interval(
        self, monkeypatch: pytest.MonkeyPatch, record_sleep: list[float]
    ) -> None:
        monkeypatch.setattr(graph_monitor, "_INITIAL_INTERVAL", 10.0)
        monkeypatch.setattr(graph_monitor, "_MAX_INTERVAL", 30.0)
        respx.get(_MONITOR).mock(
            side_effect=[
                httpx.Response(202, json={"status": "inProgress"}, headers={"Retry-After": "2"}),
                httpx.Response(200, json={"status": "completed"}),
            ]
        )
        await _poll(path="dst.txt")
        assert record_sleep == [10.0]

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_interval_grows_by_backoff_factor_up_to_ceiling(
        self, monkeypatch: pytest.MonkeyPatch, record_sleep: list[float]
    ) -> None:
        monkeypatch.setattr(graph_monitor, "_INITIAL_INTERVAL", 1.0)
        monkeypatch.setattr(graph_monitor, "_MAX_INTERVAL", 4.0)
        monkeypatch.setattr(graph_monitor, "_BACKOFF_FACTOR", 2.0)
        respx.get(_MONITOR).mock(
            side_effect=[
                httpx.Response(202, json={"status": "inProgress"}),
                httpx.Response(202, json={"status": "inProgress"}),
                httpx.Response(202, json={"status": "inProgress"}),
                httpx.Response(200, json={"status": "completed"}),
            ]
        )
        await _poll(path="dst.txt")
        # 1 -> 2 -> 4 (clamped at the 4 s ceiling).
        assert record_sleep == [1.0, 2.0, 4.0]


# ===========================================================================
# poll_monitor — cancellation
# ===========================================================================


@pytest.mark.usefixtures("_fast_poll")
class TestPollCancellation:
    @respx.mock
    @pytest.mark.spec("GR-051")
    async def test_cancellation_propagates(self) -> None:
        # A never-terminal monitor; cancelling the task must raise CancelledError
        # out of the poller (the server-side op is left running, per GR-026).
        respx.get(_MONITOR).mock(return_value=httpx.Response(202, json={"status": "inProgress"}))
        async with httpx.AsyncClient() as client:
            task = asyncio.ensure_future(poll_monitor(_MONITOR, client, path="dst.txt"))
            await asyncio.sleep(0)  # let the poller reach its first await
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
