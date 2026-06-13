"""GraphBackend read path: metadata, type probes, and simple streaming.

respx stubs ``httpx.AsyncClient`` so the real ``GraphBackend`` /
``graph_send`` / item-mapping code runs against canned Graph responses
(GR-012, GR-013, GR-031, GR-049). The range/expiry/fallback hardening of the
stream (GR-015/017/055) lands with ``transfer.py`` in a later step.
"""

from __future__ import annotations

from datetime import timezone
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from remote_store._errors import BackendUnavailable, InvalidPath, NotFound, PermissionDenied
from remote_store.aio.backends._graph.backend import GraphBackend
from remote_store.aio.backends._graph.items import parse_graph_datetime

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_DRIVE = "b!driveid123"
_BASE = "https://graph.microsoft.com/v1.0"
_DOWNLOAD = "https://my.sharepoint.example/download/presigned?tempauth=secret"


def _make() -> GraphBackend:
    return GraphBackend(_DRIVE, token_provider=lambda: "tok")


async def _collect(stream: AsyncIterator[bytes], sink: list[bytes]) -> None:
    """Drain *stream* into *sink* as bytes arrive.

    Appending per chunk (rather than building a comprehension) keeps any bytes
    yielded *before* an exception, so a caller can assert the sink stayed empty
    to prove the raise preceded the first byte. A comprehension would discard
    the partial list when the iteration raises, hiding a yield-then-raise.
    """
    async for chunk in stream:
        sink.append(chunk)


def _meta_url(path: str) -> str:
    """The item-metadata endpoint the backend GETs for *path*, via the real builder.

    Routing through ``_item_url`` keeps the mocks honest about the drive-root
    special-case (bare ``/root``, not the ``root:`` path-address form).
    """
    return _make()._item_url(path)


def _file_item(name: str = "a.txt", **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "name": name,
        "size": 11,
        "lastModifiedDateTime": "2024-01-15T10:30:00Z",
        "eTag": '"{AB12CD34},2"',
        "file": {"mimeType": "text/plain"},
        "@microsoft.graph.downloadUrl": _DOWNLOAD,
    }
    item.update(overrides)
    return item


def _folder_item(name: str = "a") -> dict[str, object]:
    return {"name": name, "folder": {"childCount": 3}}


class TestItemUrl:
    """GR-031: the drive root item is the bare ``/root``, not ``root:``.

    Regression for a live-only 400: ``root:`` is the path-addressing form and is
    rejected by Graph for a standalone item GET. respx mocks never caught it
    because they mirrored the buggy URL.
    """

    @pytest.mark.spec("GR-031")
    def test_root_uses_bare_item(self) -> None:
        assert _make()._item_url("") == f"{_BASE}/drives/{_DRIVE}/root"

    @pytest.mark.spec("GR-031")
    def test_nested_uses_path_address(self) -> None:
        assert _make()._item_url("a/b.txt") == f"{_BASE}/drives/{_DRIVE}/root:/a/b.txt:"


class TestGetFileInfo:
    """GR-013 field mapping + GR-049 hashes; GR-031 folder/not-found."""

    @respx.mock
    @pytest.mark.spec("GR-013")
    async def test_field_mapping(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        async with _make() as backend:
            info = await backend.get_file_info("a.txt")
        assert info.name == "a.txt"
        assert info.size == 11
        assert info.modified_at.year == 2024
        assert info.modified_at.tzinfo is not None
        # eTag stripped of outer quotes and lowercased.
        assert info.etag == "{ab12cd34},2"
        assert info.content_type == "text/plain"
        # USER_METADATA is not declared, and no canonical digest is selected.
        assert info.metadata is None
        assert info.digest is None

    @respx.mock
    @pytest.mark.spec("GR-049")
    async def test_hashes_ride_extra(self) -> None:
        hashes = {"quickXorHash": "abc=", "sha1Hash": "DEAD", "sha256Hash": "BEEF"}
        item = _file_item()
        item["file"] = {"mimeType": "text/plain", "hashes": hashes}
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=item))
        async with _make() as backend:
            info = await backend.get_file_info("a.txt")
        assert info.extra["graph.file.hashes"] == hashes

    @respx.mock
    @pytest.mark.spec("GR-049")
    async def test_no_hashes_leaves_extra_empty(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        async with _make() as backend:
            info = await backend.get_file_info("a.txt")
        assert "graph.file.hashes" not in info.extra

    @respx.mock
    @pytest.mark.spec("GR-013")
    @pytest.mark.spec("GR-046")  # umbrella: get_file_info on a folder -> InvalidPath
    async def test_folder_raises_invalid_path(self) -> None:
        respx.get(_meta_url("a")).mock(return_value=httpx.Response(200, json=_folder_item()))
        async with _make() as backend:
            with pytest.raises(InvalidPath):
                await backend.get_file_info("a")

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_missing_raises_not_found(self) -> None:
        respx.get(_meta_url("gone.txt")).mock(
            return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}})
        )
        async with _make() as backend:
            with pytest.raises(NotFound):
                await backend.get_file_info("gone.txt")


class TestTypeProbes:
    """GR-031: exists / is_file / is_folder suppress 404 to False."""

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_exists_true_false(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_meta_url("gone")).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with _make() as backend:
            assert await backend.exists("a.txt") is True
            assert await backend.exists("gone") is False

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_is_file(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_meta_url("a")).mock(return_value=httpx.Response(200, json=_folder_item()))
        respx.get(_meta_url("gone")).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with _make() as backend:
            assert await backend.is_file("a.txt") is True
            assert await backend.is_file("a") is False
            assert await backend.is_file("gone") is False

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_is_folder(self) -> None:
        respx.get(_meta_url("a")).mock(return_value=httpx.Response(200, json=_folder_item()))
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_meta_url("gone")).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with _make() as backend:
            assert await backend.is_folder("a") is True
            assert await backend.is_folder("a.txt") is False
            assert await backend.is_folder("gone") is False

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_root_is_folder(self) -> None:
        # The drive root carries the folder facet (root + folder facets).
        respx.get(_meta_url("")).mock(return_value=httpx.Response(200, json={"folder": {}, "root": {}}))
        async with _make() as backend:
            assert await backend.is_folder("") is True

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_probes_suppress_resource_not_found(self) -> None:
        # A 404 resourceNotFound must not escape the probes as BackendUnavailable:
        # any 404 reports missing (BE-004/BE-005). Error-raising operations keep
        # the drive-identity escalation.
        respx.get(_meta_url("gone")).mock(
            return_value=httpx.Response(404, json={"error": {"code": "resourceNotFound"}})
        )
        async with _make() as backend:
            assert await backend.exists("gone") is False
            assert await backend.is_file("gone") is False
            assert await backend.is_folder("gone") is False

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_get_file_info_keeps_resource_not_found_escalation(self) -> None:
        # The probe suppression is probe-only: an error-raising metadata read
        # still maps the drive-identity 404 to BackendUnavailable.
        respx.get(_meta_url("gone.txt")).mock(
            return_value=httpx.Response(404, json={"error": {"code": "resourceNotFound"}})
        )
        async with _make() as backend:
            with pytest.raises(BackendUnavailable):
                await backend.get_file_info("gone.txt")


class TestRead:
    """GR-012: stream from the pre-signed download URL; BE-021 folder check."""

    @respx.mock
    @pytest.mark.spec("GR-012")
    async def test_streams_content(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DOWNLOAD).mock(return_value=httpx.Response(200, content=b"hello world"))
        async with _make() as backend:
            chunks = [c async for c in backend.read("a.txt")]
        assert b"".join(chunks) == b"hello world"

    @respx.mock
    @pytest.mark.spec("GR-015")
    async def test_download_request_has_no_authorization(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        dl = respx.get(_DOWNLOAD).mock(return_value=httpx.Response(200, content=b"x"))
        async with _make() as backend:
            _ = [c async for c in backend.read("a.txt")]
        # The download URL is pre-signed; no bearer token is attached.
        assert "authorization" not in {k.lower() for k in dl.calls.last.request.headers}

    @respx.mock
    @pytest.mark.spec("GR-012")
    async def test_read_bytes_joins(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DOWNLOAD).mock(return_value=httpx.Response(200, content=b"hello world"))
        async with _make() as backend:
            assert await backend.read_bytes("a.txt") == b"hello world"

    @respx.mock
    @pytest.mark.spec("GR-012")
    async def test_folder_raises_before_yield(self) -> None:
        # read() is an async generator: _get_item + the folder check defer to the
        # first __anext__, then the stream loop runs. Collecting into a list and
        # asserting it stayed empty pins the GR-012 ordering contract — the folder
        # check fires before any byte. A bare `async for ...: pass` would also pass
        # on a yield-then-raise, so it could not catch a future reorder that moved
        # the directory check after the stream (audit-016 L7).
        respx.get(_meta_url("a")).mock(return_value=httpx.Response(200, json=_folder_item()))
        chunks: list[bytes] = []
        async with _make() as backend:
            with pytest.raises(InvalidPath):
                await _collect(backend.read("a"), chunks)
        assert chunks == []

    @respx.mock
    @pytest.mark.spec("GR-012")  # ordering: existence check precedes any byte
    @pytest.mark.spec("GR-031")  # mapping: itemNotFound -> NotFound
    async def test_missing_raises_not_found(self) -> None:
        # Same GR-012 ordering pin for the not-found path: _get_item raises before
        # the stream loop, so no byte is yielded and the download URL is never
        # reached (its route is left unmocked).
        respx.get(_meta_url("gone.txt")).mock(
            return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}})
        )
        chunks: list[bytes] = []
        async with _make() as backend:
            with pytest.raises(NotFound):
                await _collect(backend.read("gone.txt"), chunks)
        assert chunks == []

    @respx.mock
    @pytest.mark.spec("GR-012")
    async def test_missing_download_url_raises(self) -> None:
        item = _file_item()
        del item["@microsoft.graph.downloadUrl"]
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=item))
        async with _make() as backend:
            with pytest.raises(BackendUnavailable):
                async for _ in backend.read("a.txt"):
                    pass

    @respx.mock
    @pytest.mark.spec("GR-012")
    async def test_presigned_host_error_raises(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DOWNLOAD).mock(return_value=httpx.Response(500))
        async with _make() as backend:
            with pytest.raises(BackendUnavailable):
                async for _ in backend.read("a.txt"):
                    pass

    @respx.mock
    @pytest.mark.spec("GR-033")
    async def test_download_transport_error_raises(self) -> None:
        # A transport failure on the pre-signed host (the stream goes direct, not
        # via graph_send) is mapped to BackendUnavailable per GR-033.
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DOWNLOAD).mock(side_effect=httpx.ConnectError("boom"))
        async with _make() as backend:
            with pytest.raises(BackendUnavailable):
                async for _ in backend.read("a.txt"):
                    pass


class TestPermissionDeniedPerMethod:
    """GR-030: a ``403 accessDenied`` surfaces as ``PermissionDenied`` through the
    read-path data-plane methods, not just centrally at ``graph_send``.

    The 403→PermissionDenied mapping lives once in ``classify_graph_error``
    (asserted in ``test_http_mapping.py`` / ``test_http.py``). These pin that the
    centralised mapping actually reaches the public methods unchanged — the
    per-method guard audit-016 L7 found missing on the data plane.
    """

    @respx.mock
    @pytest.mark.spec("GR-030")
    async def test_get_file_info_maps_403(self) -> None:
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(403, json={"error": {"code": "accessDenied"}}))
        async with _make() as backend:
            with pytest.raises(PermissionDenied):
                await backend.get_file_info("a.txt")

    @respx.mock
    @pytest.mark.spec("GR-030")
    async def test_read_maps_403(self) -> None:
        # The metadata GET 403s before the stream starts. Mock the pre-signed
        # download route and assert it saw zero calls, so "no download attempted"
        # is an explicit assertion rather than an emergent property of strict-mock
        # routing — a later catch-all/pass-through router would otherwise drop the
        # guarantee silently (PR #799 review).
        respx.get(_meta_url("a.txt")).mock(return_value=httpx.Response(403, json={"error": {"code": "accessDenied"}}))
        dl = respx.get(_DOWNLOAD).mock(return_value=httpx.Response(200, content=b"x"))
        async with _make() as backend:
            with pytest.raises(PermissionDenied):
                async for _ in backend.read("a.txt"):
                    pass
        assert dl.called is False


class TestParseGraphDatetime:
    """RFC 3339 parsing with the trailing-Z normalisation for the 3.10 floor."""

    @pytest.mark.spec("GR-013")
    def test_trailing_z(self) -> None:
        dt = parse_graph_datetime("2024-01-15T10:30:00Z")
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timezone.utc.utcoffset(None)
        assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2024, 1, 15, 10, 30)

    @pytest.mark.spec("GR-013")
    def test_explicit_offset(self) -> None:
        dt = parse_graph_datetime("2024-01-15T10:30:00+02:00")
        assert dt.tzinfo is not None

    @pytest.mark.spec("GR-013")
    def test_naive_timestamp_assumed_utc(self) -> None:
        # A timestamp with neither Z nor an explicit offset is treated as UTC.
        dt = parse_graph_datetime("2024-01-15T10:30:00")
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timezone.utc.utcoffset(None)

    @pytest.mark.spec("GR-013")
    @pytest.mark.parametrize("bad", ["", None, "not-a-date", 12345])
    def test_fallback_is_tz_aware(self, bad: object) -> None:
        dt = parse_graph_datetime(bad)
        assert dt.tzinfo is not None
