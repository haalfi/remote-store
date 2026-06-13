"""GraphBackend write path: small ``PUT /content``, upload sessions, write_atomic.

respx stubs ``httpx.AsyncClient`` so the real ``GraphBackend.write`` /
``write_atomic`` and the ``transfer.upload_session`` driver run against canned
Graph responses: small-file PUT shape + native ``WriteResult`` (GR-018), the
BE-008 ``409`` discrimination (folder / ancestor-file / already-exists),
auto-mkdir (GR-039), the upload-session lifecycle (GR-019..GR-024, GR-038), the
mid-session ``423`` surfacing (GR-045), spool spill (GR-019), and the
``close()`` upload-session-abort half (GR-051).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from remote_store._config import RetryPolicy
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
    ResourceLocked,
)
from remote_store._models import WriteResult
from remote_store.aio.backends._graph import backend as graph_backend
from remote_store.aio.backends._graph import transfer as graph_transfer
from remote_store.aio.backends._graph.backend import GraphBackend
from remote_store.aio.backends._graph.items import parse_graph_datetime
from remote_store.aio.backends._graph.transfer import UPLOAD_SPOOL_MARKER

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_DRIVE = "b!driveid123"
_UPLOAD_URL = "https://up.example.com/session/abc?tempauth=secret"

# Whole-URL regex routes: write composes a conflictBehavior query onto the
# content URL, so an exact-string route would miss; the session/content paths
# are matched by their trailing segment.
_CONTENT_RE = re.compile(r"https://graph\.microsoft\.com/v1\.0/drives/.+:/content(\?.*)?$")
_SESSION_RE = re.compile(r"https://graph\.microsoft\.com/v1\.0/drives/.+:/createUploadSession$")

_FAST = RetryPolicy(max_attempts=3, backoff_base=0.0, backoff_max=0.0, jitter=0.0)


class _CountingProvider:
    """Token provider that counts acquisitions (for the 401-refresh assertions)."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return f"tok{self.calls}"


def _make(retry: RetryPolicy | None = None, *, token_provider: object | None = None) -> GraphBackend:
    return GraphBackend(_DRIVE, token_provider=token_provider or (lambda: "tok"), retry=retry)


def _drive_item(
    *,
    name: str = "a.txt",
    size: int = 4,
    etag: str = '"{E1},1"',
    lmd: str = "2024-01-15T10:30:00Z",
    **extra: object,
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": "01ABCDEF",
        "name": name,
        "size": size,
        "eTag": etag,
        "lastModifiedDateTime": lmd,
        "file": {"mimeType": "text/plain"},
    }
    item.update(extra)
    return item


async def _agen(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


# ===========================================================================
# Small-file write (GR-018) + native WriteResult (WR-004)
# ===========================================================================


class TestSmallWrite:
    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_put_content_shape_and_conflict_behavior_fail(self) -> None:
        route = respx.put(_CONTENT_RE).mock(return_value=httpx.Response(201, json=_drive_item(size=5)))
        async with _make() as backend:
            await backend.write("a.txt", b"hello")
        req = route.calls.last.request
        assert req.method == "PUT"
        assert req.url.path == f"/v1.0/drives/{_DRIVE}/root:/a.txt:/content"
        assert req.url.params["@microsoft.graph.conflictBehavior"] == "fail"
        assert req.content == b"hello"

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_overwrite_maps_to_conflict_behavior_replace(self) -> None:
        route = respx.put(_CONTENT_RE).mock(return_value=httpx.Response(200, json=_drive_item(size=5)))
        async with _make() as backend:
            await backend.write("a.txt", b"hello", overwrite=True)
        assert route.calls.last.request.url.params["@microsoft.graph.conflictBehavior"] == "replace"

    @respx.mock
    @pytest.mark.spec("WR-004")
    async def test_native_write_result_fields(self) -> None:
        lmd = "2024-03-04T09:08:07Z"
        respx.put(_CONTENT_RE).mock(
            return_value=httpx.Response(201, json=_drive_item(size=4, etag='"{ETAG},7"', lmd=lmd))
        )
        async with _make() as backend:
            result = await backend.write("a.txt", b"data")
        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.size == 4
        assert str(result.path) == "a.txt"
        assert result.etag == "{etag},7"  # _clean_etag: outer quotes stripped, lowercased
        assert result.last_modified == parse_graph_datetime(lmd)
        assert result.digest is None  # GR-049: no canonical hash selected
        assert result.version_id is None
        assert result.metadata is None

    @respx.mock
    @pytest.mark.spec("WR-004")
    async def test_version_id_from_sharepoint_publication(self) -> None:
        respx.put(_CONTENT_RE).mock(
            return_value=httpx.Response(201, json=_drive_item(publication={"versionId": "3.0", "level": "published"}))
        )
        async with _make() as backend:
            result = await backend.write("a.txt", b"data")
        assert result.version_id == "3.0"

    @respx.mock
    @pytest.mark.spec("GR-039")
    async def test_auto_mkdir_nested_path_encodes_segments(self) -> None:
        route = respx.put(_CONTENT_RE).mock(return_value=httpx.Response(201, json=_drive_item(name="c.txt")))
        async with _make() as backend:
            await backend.write("a/b dir/c.txt", b"x")
        # Graph creates intermediate folders implicitly; the backend issues no
        # mkdir, just the path-addressed content PUT with each segment encoded
        # on the wire (the space survives as %20 in the raw path).
        assert b"/root:/a/b%20dir/c.txt:/content" in route.calls.last.request.url.raw_path

    @respx.mock
    @pytest.mark.spec("ASYNC-021")
    async def test_async_iterator_content_is_materialised(self) -> None:
        route = respx.put(_CONTENT_RE).mock(return_value=httpx.Response(201, json=_drive_item(size=9)))
        async with _make() as backend:
            await backend.write("a.txt", _agen(b"012", b"345", b"678"))
        assert route.calls.last.request.content == b"012345678"


# ===========================================================================
# BE-008 / GR-018: 409 discrimination
# ===========================================================================


class TestConflictDiscrimination:
    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_existing_file_no_overwrite_raises_already_exists(self) -> None:
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}}))
        async with _make() as backend:
            with pytest.raises(AlreadyExists, match="a.txt"):
                await backend.write("a.txt", b"x")

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_folder_at_target_raises_invalid_path(self) -> None:
        respx.put(_CONTENT_RE).mock(
            return_value=httpx.Response(
                409,
                json={"error": {"code": "nameAlreadyExists", "details": [{"name": "a.txt", "folder": {}}]}},
            )
        )
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="folder"):
                await backend.write("a.txt", b"x")

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_file_ancestor_raises_invalid_path_even_with_overwrite(self) -> None:
        # ID-209: a slash-aligned ancestor that is a regular file -> InvalidPath
        # regardless of overwrite.
        respx.put(_CONTENT_RE).mock(
            return_value=httpx.Response(
                409,
                json={"error": {"code": "nameAlreadyExists", "details": [{"name": "parent", "file": {}}]}},
            )
        )
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="ancestor"):
                await backend.write("parent/child.txt", b"x", overwrite=True)

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_non_json_409_body_falls_back_to_already_exists(self) -> None:
        # A 409 with an unparseable body carries no facets to discriminate, so it
        # degrades to the plain AlreadyExists default.
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(409, text="<html>conflict</html>"))
        async with _make() as backend:
            with pytest.raises(AlreadyExists):
                await backend.write("a.txt", b"x")

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_top_level_folder_facet_body_raises_invalid_path(self) -> None:
        # conflictBehavior=fail may echo the existing target item at the body top
        # level rather than under error.details.
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(409, json={"name": "a.txt", "folder": {}}))
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="folder"):
                await backend.write("a.txt", b"x")


class TestLiveWriteErrorFidelity:
    """GR-046: the live status shapes (501 / 404) the respx 409-facet tests above
    do NOT reproduce — verified against a real drive in GR-DONE, locked here."""

    @respx.mock
    @pytest.mark.spec("GR-046")
    async def test_501_on_folder_target_raises_invalid_path(self) -> None:
        # Live Graph rejects PUT /content to a folder with 501 notSupported (not a
        # 409+folder-facet); the backend maps it to InvalidPath directly.
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(501, json={"error": {"code": "notSupported"}}))
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="folder"):
                await backend.write("somedir", b"x")

    @respx.mock
    @pytest.mark.spec("GR-046")
    async def test_404_under_file_ancestor_raises_invalid_path(self) -> None:
        # Live Graph answers a write under a file ancestor with 404 (not 409); the
        # backend confirms the ancestor is a file via a metadata GET, then re-raises
        # InvalidPath naming it.
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        respx.get(url__regex=r".*/root:/parent\.txt:$").mock(
            return_value=httpx.Response(200, json={"name": "parent.txt", "file": {}})
        )
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="parent.txt"):
                await backend.write("parent.txt/child.txt", b"x")

    @respx.mock
    @pytest.mark.spec("GR-046")
    async def test_404_without_file_ancestor_falls_back_to_not_found(self) -> None:
        # A write 404 whose ancestor is NOT a regular file (the ancestor GET 404s)
        # has no InvalidPath cause, so it falls back to the mapped NotFound.
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        respx.get(url__regex=r".*/root:/parent\.txt:$").mock(
            return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}})
        )
        async with _make() as backend:
            with pytest.raises(NotFound):
                await backend.write("parent.txt/child.txt", b"x")

    @respx.mock
    @pytest.mark.spec("GR-031")
    async def test_drive_scope_404_keeps_backend_unavailable_mapping(self) -> None:
        # A write 404 with no file ancestor routes back through classify_graph_error:
        # a drive-scope resourceNotFound keeps its BackendUnavailable mapping (GR-031)
        # rather than flattening to NotFound (PR #769 review).
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(404, json={"error": {"code": "resourceNotFound"}}))
        async with _make() as backend:
            with pytest.raises(BackendUnavailable):
                await backend.write("a.txt", b"x")


# ===========================================================================
# Metadata gate + path validity + write_atomic
# ===========================================================================


class TestWriteGuards:
    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_non_empty_metadata_rejected_at_backend(self) -> None:
        # Defense-in-depth: the authoritative gate is the Store layer, but a
        # direct-backend call with non-empty metadata still raises.
        async with _make() as backend:
            with pytest.raises(CapabilityNotSupported, match="USER_METADATA"):
                await backend.write("a.txt", b"x", metadata={"author": "alice"})

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_empty_metadata_is_a_no_op(self) -> None:
        route = respx.put(_CONTENT_RE).mock(return_value=httpx.Response(201, json=_drive_item()))
        async with _make() as backend:
            await backend.write("a.txt", b"x", metadata={})
            await backend.write("a.txt", b"x", metadata=None)
        assert route.call_count == 2

    @pytest.mark.spec("GR-018")
    async def test_write_to_drive_root_raises_invalid_path(self) -> None:
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="root"):
                await backend.write("", b"x")
            with pytest.raises(InvalidPath, match="root"):
                await backend.write("/", b"x")

    @respx.mock
    @pytest.mark.spec("GR-040")
    async def test_write_atomic_delegates_to_write(self) -> None:
        route = respx.put(_CONTENT_RE).mock(return_value=httpx.Response(201, json=_drive_item(size=4)))
        async with _make() as backend:
            result = await backend.write_atomic("a.txt", b"data")
        assert result.source == "native"
        assert route.calls.last.request.url.params["@microsoft.graph.conflictBehavior"] == "fail"

    @respx.mock
    @pytest.mark.spec("GR-030")
    async def test_write_maps_403_to_permission_denied(self) -> None:
        # Per-method guard (audit-016 L7): the centralised 403->PermissionDenied
        # mapping reaches the write data-plane method unchanged. 403 is not in the
        # small-PUT return_on set, so graph_send raises it directly.
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(403, json={"error": {"code": "accessDenied"}}))
        async with _make() as backend:
            with pytest.raises(PermissionDenied):
                await backend.write("a.txt", b"data")

    @respx.mock
    @pytest.mark.spec("GR-040")
    async def test_write_atomic_propagates_write_failure(self) -> None:
        # write_atomic inherits write's exceptions verbatim. Pin the failure path
        # directly rather than only transitively (audit-016 L7): an existing file
        # with the default overwrite=False 409s and surfaces AlreadyExists, naming
        # the path, straight through write_atomic.
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}}))
        async with _make() as backend:
            with pytest.raises(AlreadyExists, match="a.txt"):
                await backend.write_atomic("a.txt", b"data")


# ===========================================================================
# Upload session (GR-019..GR-024, GR-038)
# ===========================================================================


@pytest.fixture
def _small_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the upload-session path for tiny bodies by shrinking the boundary."""
    monkeypatch.setattr(graph_backend, "_SMALL_FILE_MAX_SIZE", 4)


def _session_backend() -> GraphBackend:
    backend = _make(_FAST)
    backend._upload_chunk_size = 4  # 4-byte chunks so tiny bodies span multiple PUTs
    return backend


@pytest.mark.usefixtures("_small_threshold")
class TestUploadSession:
    @respx.mock
    @pytest.mark.spec("GR-019")
    @pytest.mark.spec("GR-021")
    async def test_create_session_then_aligned_chunks_then_final_item(self) -> None:
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        chunks = respx.put(_UPLOAD_URL).mock(
            side_effect=[
                httpx.Response(202, json={"nextExpectedRanges": ["4-"]}),
                httpx.Response(202, json={"nextExpectedRanges": ["8-"]}),
                httpx.Response(201, json=_drive_item(size=10)),
            ]
        )
        async with _session_backend() as backend:
            result = await backend.write("big.bin", b"0123456789")
        assert result.source == "native"
        assert result.size == 10
        ranges = [c.request.headers["content-range"] for c in chunks.calls]
        assert ranges == ["bytes 0-3/10", "bytes 4-7/10", "bytes 8-9/10"]
        assert chunks.calls[0].request.content == b"0123"

    @respx.mock
    @pytest.mark.spec("GR-019")
    async def test_create_session_uses_conflict_behavior(self) -> None:
        session = respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(201, json=_drive_item(size=6)))
        async with _session_backend() as backend:
            backend._upload_chunk_size = 320 * 1024  # single chunk
            await backend.write("big.bin", b"abcdef", overwrite=True)
        import json as _json

        body = _json.loads(session.calls.last.request.content)
        assert body["item"]["@microsoft.graph.conflictBehavior"] == "replace"

    @respx.mock
    @pytest.mark.spec("GR-023")
    async def test_resume_follows_server_next_expected_ranges(self) -> None:
        # The server acknowledges only 2 of the first 4 bytes; the client resumes
        # from the server's offset (2), not its own cursor (4).
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        chunks = respx.put(_UPLOAD_URL).mock(
            side_effect=[
                httpx.Response(202, json={"nextExpectedRanges": ["2-"]}),
                httpx.Response(201, json=_drive_item(size=6)),
            ]
        )
        async with _session_backend() as backend:
            await backend.write("big.bin", b"abcdef")
        assert chunks.calls[1].request.headers["content-range"] == "bytes 2-5/6"

    @respx.mock
    @pytest.mark.spec("GR-022")
    async def test_transient_5xx_retries_same_chunk_without_session_restart(self) -> None:
        session = respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        chunks = respx.put(_UPLOAD_URL).mock(
            side_effect=[
                httpx.Response(202, json={"nextExpectedRanges": ["4-"]}),
                httpx.Response(503),
                httpx.Response(201, json=_drive_item(size=8)),
            ]
        )
        async with _session_backend() as backend:
            await backend.write("big.bin", b"01234567")
        assert session.call_count == 1  # the session is NOT recreated on retry
        assert chunks.call_count == 3
        # The retried chunk re-sends the same Content-Range (bytes 4-7).
        assert chunks.calls[1].request.headers["content-range"] == "bytes 4-7/8"
        assert chunks.calls[2].request.headers["content-range"] == "bytes 4-7/8"

    @respx.mock
    @pytest.mark.spec("GR-038")
    async def test_chunk_puts_are_unauthenticated_against_presigned_session(self) -> None:
        # GR-038: the session URL is pre-authorised. Live-verified: chunk PUTs to
        # the (cross-host) uploadUrl must carry NO Authorization header — sending
        # the graph bearer both leaks the token and is rejected. The token
        # provider is invoked only for the authenticated createUploadSession.
        provider = _CountingProvider()
        session = respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        chunk = respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(201, json=_drive_item(size=5)))
        backend = _make(_FAST, token_provider=provider)
        backend._upload_chunk_size = 320 * 1024  # single chunk; body > small threshold -> session
        async with backend:
            await backend.write("big.bin", b"01234")
        assert session.call_count == 1  # the pre-authorised session URL is not recreated
        assert "authorization" not in {k.lower() for k in chunk.calls.last.request.headers}
        assert provider.calls == 1  # only createUploadSession authenticates

    @respx.mock
    @pytest.mark.spec("GR-023")
    async def test_missing_next_expected_ranges_is_backend_unavailable(self) -> None:
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(202, json={}))
        respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        async with _session_backend() as backend:
            with pytest.raises(BackendUnavailable, match="nextExpectedRanges"):
                await backend.write("big.bin", b"01234567")

    @respx.mock
    @pytest.mark.spec("GR-023")
    async def test_malformed_next_expected_ranges_is_backend_unavailable(self) -> None:
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(202, json={"nextExpectedRanges": ["not-a-range"]}))
        respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        async with _session_backend() as backend:
            with pytest.raises(BackendUnavailable, match="nextExpectedRanges"):
                await backend.write("big.bin", b"01234567")

    @respx.mock
    @pytest.mark.spec("GR-023")
    async def test_non_advancing_next_expected_ranges_is_backend_unavailable(self) -> None:
        # Liveness guard: a 202 whose resume offset does not advance past the chunk
        # just sent (here the server keeps re-requesting byte 0) means no progress.
        # Without the guard the loop would re-PUT the same chunk forever; it must
        # fail fast instead. The 4-byte chunk at offset 0 gets back "0-" -> 0 <= 0.
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(202, json={"nextExpectedRanges": ["0-"]}))
        respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        async with _session_backend() as backend:
            with pytest.raises(BackendUnavailable, match="no progress"):
                await backend.write("big.bin", b"01234567")

    @respx.mock
    @pytest.mark.spec("GR-019")
    async def test_missing_upload_url_is_backend_unavailable(self) -> None:
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"expirationDateTime": "soon"}))
        async with _session_backend() as backend:
            with pytest.raises(BackendUnavailable, match="uploadUrl"):
                await backend.write("big.bin", b"01234567")

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_create_session_409_discriminates_conflict(self) -> None:
        # The BE-008 discrimination applies at session creation too (GR-018 note).
        respx.post(_SESSION_RE).mock(
            return_value=httpx.Response(
                409, json={"error": {"code": "nameAlreadyExists", "details": [{"name": "big.bin", "folder": {}}]}}
            )
        )
        async with _session_backend() as backend:
            with pytest.raises(InvalidPath, match="folder"):
                await backend.write("big.bin", b"01234567")

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_final_chunk_409_already_exists_discriminates(self) -> None:
        # A commit conflict on the final chunk (conflictBehavior=fail, existing
        # file) discriminates to AlreadyExists rather than the invalidRange path.
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}}))
        respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        async with _session_backend() as backend:
            with pytest.raises(AlreadyExists):
                await backend.write("big.bin", b"01234567")

    @respx.mock
    @pytest.mark.spec("GR-019")
    async def test_session_without_final_item_is_backend_unavailable(self) -> None:
        # A 202 whose nextExpectedRanges advances the cursor to EOF without a
        # final 200/201 is a Graph contract violation.
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(202, json={"nextExpectedRanges": ["8-"]}))
        respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        async with _session_backend() as backend:
            with pytest.raises(BackendUnavailable, match="without a final driveItem"):
                await backend.write("big.bin", b"01234567")


# ===========================================================================
# Abort + 423 + 507 (GR-024, GR-045, GR-054)
# ===========================================================================


@pytest.mark.usefixtures("_small_threshold")
class TestUploadSessionFailures:
    @respx.mock
    @pytest.mark.spec("GR-045")
    async def test_423_mid_session_surfaces_resource_locked_without_abort(self) -> None:
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(
            side_effect=[
                httpx.Response(202, json={"nextExpectedRanges": ["4-"]}),
                httpx.Response(423, json={"error": {"code": "resourceLocked"}}),
            ]
        )
        delete = respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        async with _session_backend() as backend:
            with pytest.raises(ResourceLocked) as exc:
                await backend.write("big.bin", b"01234567")
        # GR-045 / GR-035: the credentialed session URL is NEVER surfaced verbatim
        # — its query (the credential, GR-038) is stripped so a logged exception
        # cannot leak it. The redacted host+path still identifies the session and
        # the last nextExpectedRanges ride the message for diagnosis. The session
        # is left ALIVE (no abort) — resume requires re-deriving the URL.
        msg = str(exc.value)
        assert "tempauth" not in msg
        assert "secret" not in msg
        assert _UPLOAD_URL not in msg
        assert "up.example.com/session/abc" in msg  # redacted host+path retained
        assert "4-" in msg
        assert delete.call_count == 0

    @respx.mock
    @pytest.mark.spec("GR-045")
    @pytest.mark.spec("GR-035")  # credential masking: no token in str(exc)/repr(exc)
    async def test_423_message_redacts_the_presigned_session_query(self) -> None:
        # The pre-signed uploadUrl carries its own credential in the query (GR-038);
        # it must never reach str(exc) / repr(exc), mirroring the monitor redaction
        # (test_monitor.py::test_timeout_message_redacts_the_presigned_query).
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(423, json={"error": {"code": "resourceLocked"}}))
        respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        async with _session_backend() as backend:
            with pytest.raises(ResourceLocked) as exc:
                await backend.write("big.bin", b"01234567")
        for rendered in (str(exc.value), repr(exc.value)):
            assert "tempauth" not in rendered
            assert "secret" not in rendered

    @respx.mock
    @pytest.mark.spec("GR-024")
    @pytest.mark.spec("GR-046")  # umbrella: write malformed Content-Range (409 invalidRange) -> RemoteStoreError
    async def test_invalid_range_chunk_aborts_session(self) -> None:
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(409, json={"error": {"code": "invalidRange"}}))
        delete = respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        async with _session_backend() as backend:
            with pytest.raises(RemoteStoreError, match="invalidRange"):
                await backend.write("big.bin", b"01234567")
        assert delete.called  # GR-024 best-effort abort

    @respx.mock
    @pytest.mark.spec("GR-054")
    async def test_quota_limit_mid_session_is_backend_unavailable_and_aborts(self) -> None:
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(507, json={"error": {"code": "quotaLimitReached"}}))
        delete = respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        async with _session_backend() as backend:
            with pytest.raises(BackendUnavailable, match="507|storage|quota"):
                await backend.write("big.bin", b"01234567")
        assert delete.called

    @respx.mock
    @pytest.mark.spec("GR-024")
    async def test_abort_swallows_delete_failure(self) -> None:
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(409, json={"error": {"code": "invalidRange"}}))
        respx.delete(_UPLOAD_URL).mock(side_effect=httpx.ConnectError("unreachable"))
        async with _session_backend() as backend:
            # The original RemoteStoreError propagates; the failed abort is swallowed.
            with pytest.raises(RemoteStoreError, match="invalidRange"):
                await backend.write("big.bin", b"01234567")


# ===========================================================================
# Spool spill (GR-019)
# ===========================================================================


class TestSpoolSpill:
    @respx.mock
    @pytest.mark.spec("GR-019")
    async def test_unknown_length_iterator_spill_emits_debug_marker(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(graph_transfer, "_UPLOAD_SPOOL_MAX_SIZE", 4)
        monkeypatch.setattr(graph_backend, "_SMALL_FILE_MAX_SIZE", 4)
        respx.post(_SESSION_RE).mock(return_value=httpx.Response(200, json={"uploadUrl": _UPLOAD_URL}))
        respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(201, json=_drive_item(size=10)))
        with caplog.at_level(logging.DEBUG, logger="remote_store.aio.backends._graph"):
            async with _make(_FAST) as backend:
                backend._upload_chunk_size = 320 * 1024  # single chunk
                await backend.write("big.bin", _agen(b"01234", b"56789"))
        assert UPLOAD_SPOOL_MARKER in "\n".join(r.getMessage() for r in caplog.records)

    @respx.mock
    @pytest.mark.spec("GR-019")
    async def test_small_iterator_does_not_spill(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # An iterator that stays within the in-memory threshold replays from
        # memory: no spill, no marker, and the small PUT carries the joined body.
        route = respx.put(_CONTENT_RE).mock(return_value=httpx.Response(201, json=_drive_item(size=6)))
        with caplog.at_level(logging.DEBUG, logger="remote_store.aio.backends._graph"):
            async with _make() as backend:
                await backend.write("a.txt", _agen(b"abc", b"def"))
        assert route.calls.last.request.content == b"abcdef"
        assert UPLOAD_SPOOL_MARKER not in "\n".join(r.getMessage() for r in caplog.records)


# ===========================================================================
# close() upload-session-abort half (GR-051)
# ===========================================================================


class TestCloseAbortsSessions:
    @respx.mock
    @pytest.mark.spec("GR-051")
    async def test_close_aborts_in_flight_session(self) -> None:
        delete = respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        backend = _make()
        backend._active_upload_sessions.add(_UPLOAD_URL)
        await backend.aclose()
        assert delete.called
        assert backend._active_upload_sessions == set()

    @respx.mock
    @pytest.mark.spec("GR-051")
    async def test_close_swallows_session_abort_failure(self) -> None:
        respx.delete(_UPLOAD_URL).mock(side_effect=httpx.ConnectError("unreachable"))
        backend = _make()
        backend._active_upload_sessions.add(_UPLOAD_URL)
        # close() must never raise on cleanup, even when the abort DELETE fails.
        await backend.aclose()
        assert backend._active_upload_sessions == set()
