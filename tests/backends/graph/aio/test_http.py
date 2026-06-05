"""Graph request primitive and pagination (GR-008/016/028/029/033/035).

respx stubs ``httpx.AsyncClient`` so the real ``graph_send`` / ``iter_pages``
code paths run against canned responses (no network, no live wire).
"""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from remote_store._errors import BackendUnavailable, NotFound, PermissionDenied
from remote_store.aio.backends._graph.http import acquire_token, graph_send, iter_pages

_ME_DRIVE = "https://graph.microsoft.com/v1.0/me/drive"


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
