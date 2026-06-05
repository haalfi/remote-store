"""GraphBackend read-path resilience: range reads, expiry recovery, fallback.

respx stubs ``httpx.AsyncClient`` so the real ``stream_range`` driver and
``GraphBackend._read_bytes`` / ``read`` run against canned Graph responses:
range request shape (GR-015), ``416`` mapping (GR-055), download-URL expiry with
``eTag`` validation (GR-017), and the SharePoint range-to-spool fallback
(GR-015 caveat).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from remote_store._config import RetryPolicy
from remote_store._errors import BackendUnavailable, InvalidPath, NotFound, RemoteStoreError
from remote_store.aio.backends._graph import transfer as graph_transfer
from remote_store.aio.backends._graph.backend import GraphBackend
from remote_store.aio.backends._graph.transfer import RANGE_FALLBACK_FLAG

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_DRIVE = "b!driveid123"
_BASE = "https://graph.microsoft.com/v1.0"
_DL1 = "https://my.sharepoint.example/download/one?tempauth=secret1"
_DL2 = "https://my.sharepoint.example/download/two?tempauth=secret2"


def _make(retry: RetryPolicy | None = None) -> GraphBackend:
    return GraphBackend(_DRIVE, token_provider=lambda: "tok", retry=retry)


def _meta_url(path: str) -> str:
    return _make()._item_url(path)


def _file_item(*, etag: str = '"{ETAG1},1"', url: str = _DL1, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "name": "a.txt",
        "size": 10,
        "lastModifiedDateTime": "2024-01-15T10:30:00Z",
        "eTag": etag,
        "file": {"mimeType": "text/plain"},
        "@microsoft.graph.downloadUrl": url,
    }
    item.update(overrides)
    return item


class TestRangeRequestShape:
    """GR-015: a partial read sends ``Range: bytes=<start>-<end>`` and no auth."""

    @respx.mock
    @pytest.mark.spec("GR-015")
    async def test_range_header_and_no_authorization(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        dl = respx.get(_DL1).mock(return_value=httpx.Response(206, content=b"56789"))
        async with _make() as backend:
            data = await backend._read_bytes("a.txt", 5, 5)
        assert data == b"56789"
        req = dl.calls.last.request
        assert req.headers["range"] == "bytes=5-9"
        assert "authorization" not in {k.lower() for k in req.headers}

    @respx.mock
    @pytest.mark.spec("GR-015")
    async def test_open_ended_range_to_eof(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        dl = respx.get(_DL1).mock(return_value=httpx.Response(206, content=b"3456789"))
        async with _make() as backend:
            data = await backend._read_bytes("a.txt", 3, None)
        assert data == b"3456789"
        assert dl.calls.last.request.headers["range"] == "bytes=3-"

    @respx.mock
    @pytest.mark.spec("GR-015")
    async def test_full_read_sends_no_range_header(self) -> None:
        # GR-015 postcondition: a full read carries no Range header.
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        dl = respx.get(_DL1).mock(return_value=httpx.Response(200, content=b"0123456789"))
        async with _make() as backend:
            data = await backend.read_bytes("a.txt")
        assert data == b"0123456789"
        assert "range" not in {k.lower() for k in dl.calls.last.request.headers}

    @respx.mock
    @pytest.mark.spec("GR-015")
    async def test_read_bytes_on_folder_raises_invalid_path(self) -> None:
        respx.get(_meta_url("a")).mock(return_value=httpx.Response(200, json={"name": "a", "folder": {}}))
        async with _make() as backend:
            with pytest.raises(InvalidPath):
                await backend._read_bytes("a", 0, 4)

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_read_bytes_on_missing_raises_not_found(self) -> None:
        respx.get(_meta_url("gone")).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with _make() as backend:
            with pytest.raises(NotFound):
                await backend._read_bytes("gone", 0, 4)


class TestInvalidRange:
    """GR-055: 416 invalidRange — empty past EOF, error on malformed bounds."""

    @respx.mock
    @pytest.mark.spec("GR-055")
    async def test_start_past_eof_yields_empty(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DL1).mock(return_value=httpx.Response(416, json={"error": {"code": "invalidRange"}}))
        async with _make() as backend:
            assert await backend._read_bytes("a.txt", 100, 10) == b""

    @respx.mock
    @pytest.mark.spec("GR-055")
    async def test_malformed_inverted_range_raises(self) -> None:
        # A negative length inverts the bounds (end < start) — a backend bug that
        # surfaces as RemoteStoreError with the 416 status, not an empty read.
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DL1).mock(return_value=httpx.Response(416, json={"error": {"code": "invalidRange"}}))
        async with _make() as backend:
            with pytest.raises(RemoteStoreError) as exc:
                await backend._read_bytes("a.txt", 5, -3)
        assert "416" in str(exc.value)


class TestDownloadUrlExpiry:
    """GR-017: expiry mid-read → metadata re-fetch + eTag validation."""

    @respx.mock
    @pytest.mark.spec("GR-017")
    async def test_expiry_then_etag_unchanged_resumes(self) -> None:
        # First metadata GET hands out DL1; the read 401s (expired); the re-fetch
        # hands out DL2 with the same eTag, and the resumed read succeeds.
        respx.get(_meta_url("a.txt")).mock(
            side_effect=[
                httpx.Response(200, json=_file_item(url=_DL1)),
                httpx.Response(200, json=_file_item(url=_DL2)),
            ]
        )
        respx.get(_DL1).mock(return_value=httpx.Response(401))
        respx.get(_DL2).mock(return_value=httpx.Response(200, content=b"0123456789"))
        async with _make() as backend:
            assert await backend.read_bytes("a.txt") == b"0123456789"

    @respx.mock
    @pytest.mark.spec("GR-017")
    async def test_expiry_then_etag_changed_raises(self) -> None:
        # The re-fetch shows a different eTag: the file mutated under the read, so
        # rather than splice two versions the backend raises BackendUnavailable.
        respx.get(_meta_url("a.txt")).mock(
            side_effect=[
                httpx.Response(200, json=_file_item(etag='"{ETAG1},1"', url=_DL1)),
                httpx.Response(200, json=_file_item(etag='"{ETAG2},2"', url=_DL2)),
            ]
        )
        respx.get(_DL1).mock(return_value=httpx.Response(403))
        async with _make() as backend:
            with pytest.raises(BackendUnavailable) as exc:
                await backend.read_bytes("a.txt")
        assert "eTag" in str(exc.value)

    @respx.mock
    @pytest.mark.spec("GR-017")
    async def test_persistent_expiry_exhausts_budget(self) -> None:
        # The URL keeps re-expiring; recovery is bounded by RetryPolicy and gives
        # up with BackendUnavailable rather than looping forever.
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item(url=_DL1)))
        respx.get(_DL1).mock(return_value=httpx.Response(401))
        async with _make(RetryPolicy(max_attempts=2)) as backend:
            with pytest.raises(BackendUnavailable) as exc:
                await backend.read_bytes("a.txt")
        assert "expir" in str(exc.value).lower()


class TestSharePointRangeFallback:
    """GR-015 caveat: a drive that ignores Range (200 to a ranged GET) → spool."""

    @respx.mock
    @pytest.mark.spec("GR-015")
    async def test_full_entity_200_falls_back_and_windows(self, caplog: pytest.LogCaptureFixture) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        # A ranged request answered with the WHOLE entity (200, not 206).
        respx.get(_DL1).mock(return_value=httpx.Response(200, content=b"0123456789"))
        with caplog.at_level(logging.WARNING, logger="remote_store.aio.backends._graph"):
            async with _make() as backend:
                data = await backend._read_bytes("a.txt", 5, 4)
                info = await backend.get_file_info("a.txt")
        assert data == b"5678"  # windowed locally from the full entity
        assert RANGE_FALLBACK_FLAG in "\n".join(r.getMessage() for r in caplog.records)
        # The flag rides any FileInfo returned for the same item afterwards.
        assert info.extra[RANGE_FALLBACK_FLAG] is True

    @respx.mock
    @pytest.mark.spec("GR-015")
    async def test_fallback_open_ended_window_to_eof(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DL1).mock(return_value=httpx.Response(200, content=b"0123456789"))
        async with _make() as backend:
            data = await backend._read_bytes("a.txt", 7, None)
        assert data == b"789"  # skip 7, read to EOF

    @respx.mock
    @pytest.mark.spec("GR-017")
    async def test_non_416_4xx_on_range_falls_back_to_spool(self, caplog: pytest.LogCaptureFixture) -> None:
        # A drive that *rejects* a ranged GET with a non-416 4xx (no usable body)
        # is range-incapable: the driver re-issues without a Range header and
        # serves the window from the spooled full entity.
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        route = respx.get(_DL1).mock(
            side_effect=[
                httpx.Response(400, json={"error": {"code": "invalidRequest"}}),
                httpx.Response(200, content=b"0123456789"),
            ]
        )
        with caplog.at_level(logging.WARNING, logger="remote_store.aio.backends._graph"):
            async with _make() as backend:
                data = await backend._read_bytes("a.txt", 5, 4)
        assert data == b"5678"
        assert RANGE_FALLBACK_FLAG in "\n".join(r.getMessage() for r in caplog.records)
        assert route.calls[0].request.headers["range"] == "bytes=5-8"  # rejected ranged GET
        assert "range" not in {k.lower() for k in route.calls[1].request.headers}  # re-issued full GET

    @respx.mock
    @pytest.mark.spec("GR-015")
    async def test_fallback_spools_to_disk_and_windows_in_chunks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Shrink the spool thresholds so a 20-byte body rolls over to disk and the
        # windowing loop reads across multiple iterations (the `owed` decrement
        # path the 1 MiB default never exercises on small test bodies).
        monkeypatch.setattr(graph_transfer, "_SPOOL_MAX_SIZE", 4)
        monkeypatch.setattr(graph_transfer, "_SPOOL_READ_CHUNK", 4)
        body = bytes(range(20))
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DL1).mock(return_value=httpx.Response(200, content=body))
        async with _make() as backend:
            data = await backend._read_bytes("a.txt", 3, 12)
        assert data == body[3:15]  # bounded window, served across 3 four-byte reads

    @respx.mock
    @pytest.mark.spec("GR-015")
    async def test_fallback_open_ended_spools_in_chunks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The open-ended (read-to-EOF) window across multiple spool reads, ending
        # on the empty-read return rather than an `owed` count.
        monkeypatch.setattr(graph_transfer, "_SPOOL_MAX_SIZE", 4)
        monkeypatch.setattr(graph_transfer, "_SPOOL_READ_CHUNK", 4)
        body = bytes(range(14))
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DL1).mock(return_value=httpx.Response(200, content=body))
        async with _make() as backend:
            data = await backend._read_bytes("a.txt", 2, None)
        assert data == body[2:]


class TestMidStreamResume:
    """GR-017: a connection drop after partial delivery resumes from the next byte."""

    @respx.mock
    @pytest.mark.spec("GR-017")
    async def test_drop_mid_body_resumes_via_range(self) -> None:
        # DL1 streams 5 bytes then the connection drops; the re-fetch hands out DL2
        # (same eTag), and the read resumes with Range: bytes=5- for the remainder.
        respx.get(_meta_url("a.txt")).mock(
            side_effect=[
                httpx.Response(200, json=_file_item(url=_DL1)),
                httpx.Response(200, json=_file_item(url=_DL2)),
            ]
        )

        async def _drop_after_5() -> AsyncIterator[bytes]:
            yield b"01234"
            raise httpx.ReadError("connection dropped")

        respx.get(_DL1).mock(return_value=httpx.Response(200, content=_drop_after_5()))
        dl2 = respx.get(_DL2).mock(return_value=httpx.Response(206, content=b"56789"))
        async with _make() as backend:
            assert await backend.read_bytes("a.txt") == b"0123456789"
        assert dl2.calls.last.request.headers["range"] == "bytes=5-"  # resumed from the next unread byte

    @respx.mock
    @pytest.mark.spec("GR-017")
    async def test_drop_then_etag_changed_raises(self) -> None:
        # A drop after partial delivery, then a re-fetch showing a new eTag: the
        # file changed under the read, so resume is refused (no version splicing).
        respx.get(_meta_url("a.txt")).mock(
            side_effect=[
                httpx.Response(200, json=_file_item(etag='"{E1},1"', url=_DL1)),
                httpx.Response(200, json=_file_item(etag='"{E2},2"', url=_DL2)),
            ]
        )

        async def _drop_after_3() -> AsyncIterator[bytes]:
            yield b"012"
            raise httpx.ReadError("connection dropped")

        respx.get(_DL1).mock(return_value=httpx.Response(200, content=_drop_after_3()))
        async with _make() as backend:
            with pytest.raises(BackendUnavailable) as exc:
                await backend.read_bytes("a.txt")
        assert "eTag" in str(exc.value)

    @respx.mock
    @pytest.mark.spec("GR-017")
    async def test_persistent_transport_error_exhausts_budget(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item(url=_DL1)))
        respx.get(_DL1).mock(side_effect=httpx.ConnectError("unreachable"))
        async with _make(RetryPolicy(max_attempts=2)) as backend:
            with pytest.raises(BackendUnavailable) as exc:
                await backend.read_bytes("a.txt")
        assert "transport" in str(exc.value).lower()
