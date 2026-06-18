"""Tests for AsyncAzureBackend -- covers ASYNC-xxx spec items for Azure.

Requires: azure-storage-file-datalake, azure-identity (test dependencies).
All tests use mocked SDK objects since there is no in-process Azure emulator
for async operations.
"""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from azure.core.exceptions import (  # noqa: E402
    ClientAuthenticationError,
    HttpResponseError,
    ResourceExistsError,
    ResourceNotFoundError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.storage.blob import (  # noqa: E402
    BlobProperties,
    ContentSettings,
    StorageStreamDownloader,
)
from azure.storage.blob.aio import BlobClient, BlobServiceClient, ContainerClient  # noqa: E402
from azure.storage.filedatalake import DirectoryProperties, PathProperties  # noqa: E402
from azure.storage.filedatalake.aio import (  # noqa: E402
    DataLakeDirectoryClient,
    DataLakeFileClient,
    DataLakeServiceClient,
    FileSystemClient,
)

from remote_store._capabilities import Capability  # noqa: E402
from remote_store._errors import (  # noqa: E402
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderEntry, WriteResult  # noqa: E402
from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: E402
from remote_store.backends import AzureUtils  # noqa: E402
from remote_store.backends._azure_common import (  # noqa: E402
    build_azure_retry,
    classify_azure_error,
    props_to_fileinfo,
    resolve_credential,
    validate_azure_params,
)
from tests.backends.azure._materialization_guard import (  # noqa: E402
    assert_streamed_not_materialized,
    async_chunks,
    collect_async_upload,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Tracker so an autouse async fixture can aclose() every backend made in a test —
# without aclose, AsyncAzureBackend.__del__ emits a ResourceWarning at GC time.
_BACKENDS: list[AsyncAzureBackend] = []


def _make_backend(**kw: Any) -> AsyncAzureBackend:
    """Shorthand for creating an AsyncAzureBackend with sensible test defaults.

    Defaults to ``hns=False``; pass ``hns=True`` (or set ``backend._hns``
    afterwards) for HNS-path tests.
    """
    defaults: dict[str, Any] = {"container": "test", "hns": False, "account_name": "x", "account_key": "fakekey"}
    defaults.update(kw)
    backend = AsyncAzureBackend(**defaults)
    _BACKENDS.append(backend)
    return backend


@pytest.fixture(autouse=True)
async def _aclose_tracked_backends() -> AsyncIterator[None]:
    yield
    while _BACKENDS:
        backend = _BACKENDS.pop()
        with contextlib.suppress(Exception):
            await backend.aclose()


async def _async_iter(items: list[Any]):  # noqa: ANN201 -- async generator
    """Yield items from a list as an async iterator."""
    for item in items:
        yield item


def _mock_blob_props(
    *,
    name: str | None = None,
    size: int = 100,
    etag: str = '"0x8D4BCC2E4835CD0"',
    md5: bytes | None = None,
    metadata: dict[str, str] | None = None,
    prefix: str | None = None,
) -> MagicMock:
    """Create a mock BlobProperties-like object."""
    props = MagicMock(spec=BlobProperties)
    if name is not None:
        props.name = name
    props.size = size
    props.content_length = size
    props.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
    props.etag = etag
    cs = MagicMock(spec=ContentSettings)
    cs.content_md5 = md5
    props.content_settings = cs
    props.metadata = metadata or {}
    props.prefix = prefix
    return props


def _setup_non_hns_backend() -> tuple[AsyncAzureBackend, AsyncMock, AsyncMock]:
    """Create a non-HNS backend with mocked blob and container clients.

    Returns:
        Tuple of (backend, container_client_mock, blob_client_mock).
    """
    backend = _make_backend()
    backend._hns = False
    cc = AsyncMock(spec=ContainerClient)
    backend._cc_instance = cc
    bc = AsyncMock(spec=BlobClient)
    cc.get_blob_client.return_value = bc
    backend._blob_service_instance = AsyncMock(spec=BlobServiceClient)
    return backend, cc, bc


# =============================================================================
# Construction (ASYNC-001, ASYNC-002, ASYNC-003)
# =============================================================================


class TestAsyncAzureConstruction:
    """ASYNC-001/002/003: construction, name, capabilities, validation."""

    @pytest.mark.spec("ASYNC-002")
    def test_name(self) -> None:
        backend = _make_backend()
        assert backend.name == "async-azure"

    @pytest.mark.spec("ASYNC-003")
    @pytest.mark.spec("ASYNC-076")
    def test_capabilities_include_all_except_seekable_read(self) -> None:
        caps = _make_backend().capabilities
        # Behavioral: verify capabilities answer supports() correctly (not just type)
        for cap in Capability:
            if cap is Capability.SEEKABLE_READ:
                assert not caps.supports(cap), "async-azure must not declare SEEKABLE_READ"
            elif cap is Capability.ATOMIC_MOVE:
                assert not caps.supports(cap), "async-azure must not declare ATOMIC_MOVE (copy-then-delete)"
            else:
                assert caps.supports(cap), f"Missing capability: {cap.value}"

    @pytest.mark.spec("ASYNC-001")
    @pytest.mark.parametrize(
        "container",
        [
            pytest.param("", id="empty"),
            pytest.param("   ", id="whitespace"),
        ],
    )
    def test_validation_empty_container(self, container: str) -> None:
        with pytest.raises(ValueError, match="container"):
            AsyncAzureBackend(container=container, hns=False, account_name="x")

    @pytest.mark.spec("ASYNC-001")
    def test_validation_no_account(self) -> None:
        with pytest.raises(ValueError, match="account_name"):
            AsyncAzureBackend(container="test", hns=False)

    @pytest.mark.spec("AZ-006")
    def test_validation_hns_required(self) -> None:
        """Omitting ``hns`` is a construction error -- no silent default (AZ-006)."""
        with pytest.raises(ValueError, match="hns must be declared explicitly"):
            AsyncAzureBackend(container="test", account_name="x", account_key="fakekey")

    @pytest.mark.spec("AZ-006")
    @pytest.mark.parametrize(
        "bad",
        [
            pytest.param("false", id="str-false"),
            pytest.param("true", id="str-true"),
            pytest.param("no", id="str-no"),
            pytest.param(0, id="int-zero"),
            pytest.param(1, id="int-one"),
        ],
    )
    def test_validation_hns_non_bool_raises(self, bad: object) -> None:
        """A non-bool ``hns`` (e.g. config string "false") is rejected, not coerced (AZ-006)."""
        with pytest.raises(ValueError, match="hns must be declared explicitly"):
            AsyncAzureBackend(container="test", hns=bad, account_name="x", account_key="fakekey")

    @pytest.mark.spec("ASYNC-001")
    @pytest.mark.parametrize(
        "val",
        [
            pytest.param(0, id="zero"),
            pytest.param(-1, id="negative"),
        ],
    )
    def test_validation_bad_concurrency(self, val: int) -> None:
        with pytest.raises(ValueError, match="max_concurrency"):
            _make_backend(max_concurrency=val)

    @pytest.mark.spec("ASYNC-001")
    def test_constructor_with_connection_string(self) -> None:
        backend = _make_backend(
            account_key=None,
            connection_string="DefaultEndpointsProtocol=http;AccountName=x",
        )
        assert backend.name == "async-azure"

    @pytest.mark.spec("ASYNC-001")
    def test_constructor_with_account_url(self) -> None:
        backend = _make_backend(
            account_key=None,
            account_name=None,
            account_url="https://myaccount.dfs.core.windows.net",
        )
        assert backend.name == "async-azure"

    @pytest.mark.spec("ASYNC-001")
    @pytest.mark.spec("ASYNC-071")
    def test_lazy_connection(self) -> None:
        """Construction must not make network calls."""
        backend = _make_backend(container="any-container", account_name="nonexistent")
        assert backend.name == "async-azure"


# =============================================================================
# HNS discovery -- AzureUtils.adetect_hns (AZ-006)
# =============================================================================


class TestAsyncAzureUtilsDetectHns:
    """AZ-006: explicit, fail-loud async HNS discovery via ``AzureUtils.adetect_hns``."""

    @pytest.mark.spec("AZ-006")
    @pytest.mark.parametrize("flag", [True, False])
    async def test_adetect_hns_returns_account_flag(self, flag: bool) -> None:
        svc = AsyncMock(spec=BlobServiceClient)
        svc.get_account_information.return_value = {"is_hns_enabled": flag}
        with patch("remote_store.backends._azure.build_blob_service", return_value=svc) as mk:
            result = await AzureUtils.adetect_hns(connection_string="fake-conn")
        assert result is flag
        mk.assert_called_once()
        svc.get_account_information.assert_awaited_once()
        svc.close.assert_awaited_once()  # throwaway client is always closed

    @pytest.mark.spec("AZ-006")
    async def test_adetect_hns_absent_key_is_false(self) -> None:
        svc = AsyncMock(spec=BlobServiceClient)
        svc.get_account_information.return_value = {}  # key absent
        with patch("remote_store.backends._azure.build_blob_service", return_value=svc):
            assert await AzureUtils.adetect_hns(connection_string="fake-conn") is False

    @pytest.mark.spec("AZ-006")
    async def test_adetect_hns_raises_on_probe_error(self) -> None:
        """Fail-loud: a probe error is mapped to a remote_store error and raised.

        The resolved async credential is awaited-closed on the error path too
        (the common failure case) -- a probe failure must not leak the
        auto-created ``DefaultAzureCredential``'s aiohttp session.
        """
        svc = AsyncMock(spec=BlobServiceClient)
        svc.get_account_information.side_effect = ClientAuthenticationError("denied")
        cred = MagicMock(spec=["close"])
        cred.close = AsyncMock()
        with (
            patch("remote_store.backends._azure.build_blob_service", return_value=svc),
            pytest.raises(PermissionDenied),
        ):
            await AzureUtils.adetect_hns(account_url="https://x.blob.core.windows.net", credential=cred)
        svc.close.assert_awaited_once()  # client is closed even on the error path
        cred.close.assert_awaited_once()  # credential is closed even on the error path

    @pytest.mark.spec("AZ-006")
    async def test_adetect_hns_closes_resolved_credential(self) -> None:
        """The async credential is awaited-closed too -- an unclosed aiohttp session leaks connectors."""
        svc = AsyncMock(spec=BlobServiceClient)
        svc.get_account_information.return_value = {"is_hns_enabled": True}
        cred = MagicMock(spec=["close"])  # async DefaultAzureCredential exposes an awaitable close()
        cred.close = AsyncMock()
        with patch("remote_store.backends._azure.build_blob_service", return_value=svc):
            result = await AzureUtils.adetect_hns(account_url="https://x.blob.core.windows.net", credential=cred)
        assert result is True
        svc.close.assert_awaited_once()
        cred.close.assert_awaited_once()

    @pytest.mark.spec("AZ-006")
    async def test_adetect_hns_string_credential_has_no_close(self) -> None:
        """A string credential (account_key/SAS) has no ``close`` -- the close path skips it cleanly."""
        svc = AsyncMock(spec=BlobServiceClient)
        svc.get_account_information.return_value = {"is_hns_enabled": False}
        with patch("remote_store.backends._azure.build_blob_service", return_value=svc):
            # account_key resolves to a plain str credential -- must not raise on close.
            result = await AzureUtils.adetect_hns(account_url="https://x.blob.core.windows.net", account_key="k")
        assert result is False
        svc.close.assert_awaited_once()

    @pytest.mark.spec("AZ-006")
    async def test_adetect_hns_closes_credential_on_build_error(self) -> None:
        """A build-time error (no account locator) still awaited-closes the resolved credential.

        ``build_blob_service`` raises before the probe runs; the async credential
        ``_resolve_detect_credential`` produced must not leak its aiohttp session --
        it is resolved and closed inside the same ``try``/``finally``.
        """
        cred = MagicMock(spec=["close"])
        cred.close = AsyncMock()
        with pytest.raises(ValueError, match="account_name, account_url, or connection_string"):
            await AzureUtils.adetect_hns(credential=cred)
        cred.close.assert_awaited_once()


# =============================================================================
# Error Mapping (ASYNC-024)
# =============================================================================


def _http_err(msg: str, status: int) -> HttpResponseError:
    """Create an HttpResponseError with a status_code."""
    exc = HttpResponseError(msg)
    exc.status_code = status
    return exc


class TestAsyncAzureErrorMapping:
    """ASYNC-024: structured error classification."""

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.parametrize(
        ("exc_factory", "expected_type"),
        [
            pytest.param(
                lambda: ResourceNotFoundError("not found"),
                NotFound,
                id="resource-not-found",
            ),
            pytest.param(
                lambda: ResourceExistsError("exists"),
                AlreadyExists,
                id="resource-exists",
            ),
            pytest.param(
                lambda: ClientAuthenticationError("auth failed"),
                PermissionDenied,
                id="client-auth-error",
            ),
            pytest.param(
                lambda: ServiceRequestError("connection refused"),
                BackendUnavailable,
                id="service-request-error",
            ),
            pytest.param(
                lambda: ServiceResponseError("bad response"),
                BackendUnavailable,
                id="service-response-error",
            ),
            pytest.param(
                lambda: RuntimeError("unexpected"),
                RemoteStoreError,
                id="unknown-exception",
            ),
        ],
    )
    @pytest.mark.spec("ASYNC-079")
    def test_classify_direct(self, exc_factory: Any, expected_type: type) -> None:
        mapped = classify_azure_error(exc_factory(), "file.txt", "async-azure")
        assert isinstance(mapped, expected_type)
        assert mapped.path == "file.txt"

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.parametrize(
        ("status", "expected_type"),
        [
            pytest.param(404, NotFound, id="http-404"),
            pytest.param(401, PermissionDenied, id="http-401"),
            pytest.param(403, PermissionDenied, id="http-403"),
            pytest.param(409, AlreadyExists, id="http-409"),
            pytest.param(429, BackendUnavailable, id="http-429-throttle"),
            pytest.param(500, BackendUnavailable, id="http-500"),
            pytest.param(502, BackendUnavailable, id="http-502"),
            pytest.param(503, BackendUnavailable, id="http-503"),
            pytest.param(504, BackendUnavailable, id="http-504"),
            # 412 (precondition) has no dedicated error type and is unreachable
            # via the public API; it stays the generic base error (BUG-222).
            pytest.param(412, RemoteStoreError, id="http-412-generic"),
        ],
    )
    def test_classify_http_status(self, status: int, expected_type: type) -> None:
        mapped = classify_azure_error(_http_err("msg", status), "file.txt", "async-azure")
        assert isinstance(mapped, expected_type)
        assert mapped.path == "file.txt"

    @pytest.mark.spec("ASYNC-024")
    def test_error_has_backend_attribute(self) -> None:
        mapped = classify_azure_error(ResourceNotFoundError("not found"), "file.txt", "async-azure")
        assert mapped.backend == "async-azure"

    @pytest.mark.spec("ASYNC-024")
    async def test_remote_store_errors_pass_through(self) -> None:
        """RemoteStoreError raised inside _errors() passes through unchanged."""
        backend = _make_backend()
        with pytest.raises(NotFound, match="custom"):
            async with backend._errors("test"):
                raise NotFound("custom", path="test", backend="async-azure")

    @pytest.mark.spec("ASYNC-024")
    async def test_native_exceptions_mapped(self) -> None:
        """Native exceptions are mapped through _errors() context manager."""
        backend = _make_backend()
        with pytest.raises(NotFound):
            async with backend._errors("test"):
                raise ResourceNotFoundError("not found")


# =============================================================================
# Read / Write (ASYNC-006, ASYNC-007, ASYNC-008, ASYNC-020, ASYNC-021)
# =============================================================================


class TestAsyncAzureReadWrite:
    """ASYNC-006/007/008/020/021: read and write operations."""

    @pytest.mark.spec("ASYNC-006")
    async def test_read_streams_chunks(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        downloader = MagicMock(spec=StorageStreamDownloader)
        downloader.chunks.return_value = _async_iter([b"chunk1", b"chunk2"])
        bc.download_blob = AsyncMock(return_value=downloader)

        chunks = [chunk async for chunk in backend.read("file.txt")]
        assert b"".join(chunks) == b"chunk1chunk2"
        assert len(chunks) == 2

    @pytest.mark.spec("ASYNC-007")
    async def test_read_bytes(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        downloader = AsyncMock(spec=StorageStreamDownloader)
        downloader.readall = AsyncMock(return_value=b"hello world")
        bc.download_blob = AsyncMock(return_value=downloader)

        data = await backend.read_bytes("file.txt")
        assert data == b"hello world"

    @pytest.mark.spec("ASYNC-007")
    async def test_read_bytes_not_found(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.download_blob = AsyncMock(side_effect=ResourceNotFoundError("blob not found"))

        with pytest.raises(NotFound, match="not found|Not found"):
            await backend.read_bytes("missing.txt")

    @pytest.mark.spec("ASYNC-006")
    async def test_read_stream_not_found(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.download_blob = AsyncMock(side_effect=ResourceNotFoundError("blob not found"))

        with pytest.raises(NotFound, match="not found|Not found"):
            async for _ in backend.read("missing.txt"):
                pass

    @pytest.mark.spec("ASYNC-008")
    async def test_write_bytes(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        bc.upload_blob = AsyncMock()

        await backend.write("file.txt", b"data")
        assert bc.upload_blob.call_count == 1
        call_args = bc.upload_blob.call_args
        assert call_args[0][0] == b"data"

    @pytest.mark.spec("ASYNC-008", "ASYNC-021")
    async def test_write_async_iterator_streams(self) -> None:
        """Async iterator content is passed through to upload_blob without
        being materialized first (BUG-165).

        The Azure SDK's ``upload_blob`` accepts ``AsyncIterable[bytes]`` and
        streams it in bounded memory; materializing in the backend would
        break the streaming promise (SIO-003 / ASYNC-021) for large payloads.
        """
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))

        captured: list[bytes] = []

        async def _fake_upload(data, **_kwargs):  # noqa: ANN001, ANN202
            # Emulate the SDK: consume the async iterator to EOF.
            async for chunk in data:
                captured.append(chunk)

        bc.upload_blob = AsyncMock(side_effect=_fake_upload)

        async def gen():  # noqa: ANN202
            yield b"hello "
            yield b"world"

        agen = gen()
        await backend.write("file.txt", agen)
        assert bc.upload_blob.call_count == 1
        # Chunks forwarded without buffering — full payload arrives in order.
        assert captured == [b"hello ", b"world"]

    @pytest.mark.spec("ASYNC-008")
    async def test_write_already_exists(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        with pytest.raises(AlreadyExists, match="already exists|Already exists"):
            await backend.write("file.txt", b"data")

    @pytest.mark.spec("ASYNC-008")
    async def test_write_overwrite(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        bc.upload_blob = AsyncMock()

        await backend.write("file.txt", b"data", overwrite=True)
        assert bc.upload_blob.call_count == 1

    @pytest.mark.spec("ASYNC-074")
    async def test_non_hns_streams_async_iterator_to_upload(self) -> None:
        """ASYNC-074 / BUG-165: a non-HNS write passes the AsyncIterator straight
        to upload_blob (streamed in bounded memory, not collected into bytes
        first). upload_blob receives an async iterable, and its chunks reconstruct
        the full payload."""
        from azure.core.exceptions import ResourceNotFoundError

        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        bc.upload_blob = AsyncMock()

        async def payload():  # type: ignore[no-untyped-def]
            yield b"hello "
            yield b"world"

        await backend.write("file.txt", payload())

        bc.upload_blob.assert_awaited_once()
        forwarded = bc.upload_blob.await_args.args[0]
        assert hasattr(forwarded, "__aiter__")  # streamed, not a materialized bytes blob
        collected = b"".join([chunk async for chunk in forwarded])
        assert collected == b"hello world"

    @pytest.mark.spec("ASYNC-020")
    @pytest.mark.spec("ASYNC-072")
    async def test_write_atomic_non_hns(self) -> None:
        """Non-HNS write_atomic delegates to write (PUT is atomic)."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        bc.upload_blob = AsyncMock()

        await backend.write_atomic("file.txt", b"atomic")
        assert bc.upload_blob.call_count == 1

    @pytest.mark.spec("ASYNC-021")
    async def test_write_creates_intermediate_dirs(self) -> None:
        """Azure blobs don't need mkdir -- write to deep path works."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        bc.upload_blob = AsyncMock()

        await backend.write("a/b/c.txt", b"deep")
        assert bc.upload_blob.call_count == 1

    @pytest.mark.spec("WR-010")
    async def test_write_passes_metadata_to_sdk(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        bc.upload_blob = AsyncMock(return_value={})

        await backend.write("file.txt", b"data", metadata={"k": "v"})

        call_kwargs = bc.upload_blob.call_args[1]
        assert call_kwargs.get("metadata") == {"k": "v"}

    @pytest.mark.spec("WR-001", "WR-004")
    async def test_write_returns_write_result_with_native_fields(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))

        mock_response = {
            "etag": '"0x8D4BCC2E4835CD0"',
            "last_modified": datetime(2024, 1, 1, tzinfo=timezone.utc),
        }
        bc.upload_blob = AsyncMock(return_value=mock_response)

        result = await backend.write("file.txt", b"hello")

        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.etag == "0x8d4bcc2e4835cd0"
        assert result.last_modified == datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert result.size == 5

    @pytest.mark.spec("WR-010")
    async def test_write_atomic_passes_metadata_to_sdk(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        bc.upload_blob = AsyncMock(return_value={})

        await backend.write_atomic("file.txt", b"data", metadata={"k": "v"})

        call_kwargs = bc.upload_blob.call_args[1]
        assert call_kwargs.get("metadata") == {"k": "v"}


# ---------------------------------------------------------------------------
# Materialization guard (BK-240; SIO-003, ASYNC-021)
# ---------------------------------------------------------------------------


class TestAsyncAzureNoMaterialization:
    """BK-240: the write path must not collapse an AsyncIterator to one chunk.

    ``test_non_hns_streams_async_iterator_to_upload`` already rejects a plain
    join-to-bytes (the forwarded arg loses ``__aiter__``). This closes the
    subtler variant a future refactor is most likely to reach for: join the
    chunks, then re-emit the result as a *single-chunk* async generator. That
    wrapper still has ``__aiter__`` and still reconstructs the payload, so the
    older guard passes while bounded memory is already broken. The chunk-count
    discriminator catches it because the join collapses 3 chunks into 1.
    """

    @pytest.mark.spec("ASYNC-021", "SIO-003")
    async def test_non_hns_preserves_chunk_boundaries(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))

        observed: list[bytes] = []

        async def _upload(data, **_kwargs):  # noqa: ANN001, ANN202
            observed.extend(await collect_async_upload(data))
            return {}

        bc.upload_blob = AsyncMock(side_effect=_upload)

        await backend.write("file.txt", async_chunks())

        bc.upload_blob.assert_awaited_once()
        # The SDK must observe the supplied chunk sequence unchanged; a collapse
        # to one chunk would mean the backend materialized before forwarding.
        assert len(observed) > 1, "upload_blob observed a collapsed (materialized) payload"
        assert_streamed_not_materialized(observed)


# =============================================================================
# List Operations (ASYNC-014, ASYNC-015, ASYNC-029)
# =============================================================================


class TestAsyncAzureListOperations:
    """ASYNC-014/015/029: list_files, list_folders, iter_children."""

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_non_recursive(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        blob_file = _mock_blob_props(name="file.txt", size=42, etag='"abc"')

        cc.walk_blobs.return_value = _async_iter([blob_file])

        files = [f async for f in backend.list_files("")]
        assert len(files) == 1
        assert files[0].name == "file.txt"
        assert files[0].size == 42

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_recursive(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        blob1 = _mock_blob_props(name="file.txt", size=10, etag='"a"')
        blob2 = _mock_blob_props(name="sub/deep.txt", size=20, etag='"b"')

        cc.list_blobs.return_value = _async_iter([blob1, blob2])

        files = [f async for f in backend.list_files("", recursive=True)]
        assert len(files) == 2
        names = {f.name for f in files}
        assert names == {"file.txt", "deep.txt"}

    @pytest.mark.spec("ASYNC-015")
    async def test_list_folders(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        folder_item = _mock_blob_props(name="test/sub1/", prefix="test/sub1/")

        cc.walk_blobs.return_value = _async_iter([folder_item])

        folders = [f async for f in backend.list_folders("")]
        assert len(folders) == 1
        assert folders[0].name == "sub1"
        assert str(folders[0].path) == "sub1"

    @pytest.mark.spec("ASYNC-029")
    async def test_iter_children(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        blob_file = _mock_blob_props(name="file.txt", size=42, etag='"abc"')
        folder_item = _mock_blob_props(name="test/sub/", prefix="test/sub/")

        cc.walk_blobs.return_value = _async_iter([blob_file, folder_item])

        children = [c async for c in backend.iter_children("")]
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert len(files) == 1
        assert files[0].name == "file.txt"
        assert len(folders) == 1
        assert folders[0].name == "sub"

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_max_depth_zero(self) -> None:
        """BUG-155: list_files(max_depth=0) should return only immediate files."""
        backend, cc, bc = _setup_non_hns_backend()
        blob_root = _mock_blob_props(name="data/a.txt", size=10, etag='"a"')
        blob_sub = _mock_blob_props(name="data/sub/b.txt", size=20, etag='"b"')
        blob_deep = _mock_blob_props(name="data/sub/deep/c.txt", size=30, etag='"c"')

        cc.list_blobs.return_value = _async_iter([blob_root, blob_sub, blob_deep])

        files = [f async for f in backend.list_files("data", recursive=True, max_depth=0)]
        names = {f.name for f in files}
        assert names == {"a.txt"}

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_max_depth_one(self) -> None:
        """BUG-155: list_files(max_depth=1) should return files up to depth 1."""
        backend, cc, bc = _setup_non_hns_backend()
        blob_root = _mock_blob_props(name="data/a.txt", size=10, etag='"a"')
        blob_sub = _mock_blob_props(name="data/sub/b.txt", size=20, etag='"b"')
        blob_deep = _mock_blob_props(name="data/sub/deep/c.txt", size=30, etag='"c"')

        cc.list_blobs.return_value = _async_iter([blob_root, blob_sub, blob_deep])

        files = [f async for f in backend.list_files("data", recursive=True, max_depth=1)]
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_empty(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.walk_blobs.return_value = _async_iter([])

        files = [f async for f in backend.list_files("nonexistent")]
        assert files == []

    @pytest.mark.spec("ASYNC-024")
    async def test_list_files_error_mapped(self) -> None:
        """Native Azure exceptions during listing are mapped to RemoteStoreError."""
        backend, cc, bc = _setup_non_hns_backend()
        cc.list_blobs.return_value = _async_iter([])
        cc.walk_blobs.side_effect = ServiceRequestError("connection lost")

        with pytest.raises(BackendUnavailable, match="connection lost"):
            async for _ in backend.list_files("data"):
                pass


# =============================================================================
# Delete Operations (ASYNC-012, ASYNC-013)
# =============================================================================


class TestAsyncAzureDeleteOperations:
    """ASYNC-012/013: delete file and folder operations."""

    @pytest.mark.spec("ASYNC-012")
    async def test_delete(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.delete_blob = AsyncMock()

        await backend.delete("file.txt")
        assert bc.delete_blob.call_count == 1

    @pytest.mark.spec("ASYNC-012")
    async def test_delete_missing_ok(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.delete_blob = AsyncMock(side_effect=ResourceNotFoundError("not found"))

        result = await backend.delete("missing.txt", missing_ok=True)
        assert result is None

    @pytest.mark.spec("ASYNC-012")
    async def test_delete_not_found(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.delete_blob = AsyncMock(side_effect=ResourceNotFoundError("not found"))

        with pytest.raises(NotFound, match="not found|Not found"):
            await backend.delete("missing.txt")

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_recursive(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        blob1 = MagicMock(spec=BlobProperties)
        blob1.name = "dir/a.txt"
        blob2 = MagicMock(spec=BlobProperties)
        blob2.name = "dir/sub/b.txt"

        # First call: check if folder has content (returns first item)
        cc.list_blobs.side_effect = [
            _async_iter([blob1]),  # first check: has content
            _async_iter([blob1, blob2]),  # second: enumerate all for deletion
        ]
        inner_bc = AsyncMock(spec=BlobClient)
        inner_bc.delete_blob = AsyncMock()
        cc.get_blob_client.return_value = inner_bc

        await backend.delete_folder("dir", recursive=True)
        assert inner_bc.delete_blob.call_count == 2

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_not_empty(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        blob = MagicMock(spec=BlobProperties)
        blob.name = "dir/file.txt"
        cc.list_blobs.return_value = _async_iter([blob])

        with pytest.raises(DirectoryNotEmpty, match="not empty|Folder not empty"):
            await backend.delete_folder("dir", recursive=False)

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_not_found(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.list_blobs.return_value = _async_iter([])

        with pytest.raises(NotFound, match="not found|Folder not found"):
            await backend.delete_folder("dir")

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_missing_ok(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.list_blobs.return_value = _async_iter([])

        result = await backend.delete_folder("dir", missing_ok=True)
        assert result is None


# =============================================================================
# Move and Copy (ASYNC-018, ASYNC-019)
# =============================================================================


class TestAsyncAzureMoveAndCopy:
    """ASYNC-018/019: move and copy operations."""

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.spec("ASYNC-073")
    async def test_move_non_hns(self) -> None:
        """Non-HNS move: copy_from_url + delete."""
        backend, cc, bc = _setup_non_hns_backend()

        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        src_bc.url = "https://x.blob.core.windows.net/test/src.txt"
        src_bc.delete_blob = AsyncMock()

        dst_bc = AsyncMock(spec=BlobClient)
        dst_bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        dst_bc.start_copy_from_url = AsyncMock()

        cc.get_blob_client.side_effect = [src_bc, dst_bc]

        await backend.move("src.txt", "dst.txt")
        assert dst_bc.start_copy_from_url.call_count == 1
        assert dst_bc.start_copy_from_url.call_args[0][0] == src_bc.url
        assert src_bc.delete_blob.call_count == 1

    @pytest.mark.spec("ASYNC-019")
    async def test_copy(self) -> None:
        """Copy: copy_from_url only, source retained."""
        backend, cc, bc = _setup_non_hns_backend()

        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        src_bc.url = "https://x.blob.core.windows.net/test/src.txt"

        dst_bc = AsyncMock(spec=BlobClient)
        dst_bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        dst_bc.start_copy_from_url = AsyncMock()

        cc.get_blob_client.side_effect = [src_bc, dst_bc]

        await backend.copy("src.txt", "dst.txt")
        assert dst_bc.start_copy_from_url.call_count == 1
        assert dst_bc.start_copy_from_url.call_args[0][0] == src_bc.url

    @pytest.mark.spec("ASYNC-018")
    async def test_move_not_found(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        cc.get_blob_client.return_value = src_bc

        with pytest.raises(NotFound, match="not found|Not found"):
            await backend.move("missing.txt", "dst.txt")

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_not_found(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        cc.get_blob_client.return_value = src_bc

        with pytest.raises(NotFound, match="not found|Not found"):
            await backend.copy("missing.txt", "dst.txt")

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_already_exists(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        dst_bc = AsyncMock(spec=BlobClient)
        dst_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        cc.get_blob_client.side_effect = [src_bc, dst_bc]

        with pytest.raises(AlreadyExists, match="already exists|Already exists"):
            await backend.copy("src.txt", "dst.txt")

    @pytest.mark.spec("ASYNC-018")
    async def test_move_already_exists(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        dst_bc = AsyncMock(spec=BlobClient)
        dst_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        cc.get_blob_client.side_effect = [src_bc, dst_bc]

        with pytest.raises(AlreadyExists, match="already exists|Already exists"):
            await backend.move("src.txt", "dst.txt")

    @pytest.mark.spec("ASYNC-018")
    async def test_move_overwrite(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        src_bc.url = "https://x.blob.core.windows.net/test/src.txt"
        src_bc.delete_blob = AsyncMock()

        dst_bc = AsyncMock(spec=BlobClient)
        # Non-HNS overwrite=True takes the start_copy_from_url + delete path
        # without any dst probe — BUG-200's hdi_isfolder probe lives in the
        # HNS branch only. ``get_blob_properties`` is intentionally not set up;
        # it is never awaited on this code path. ``start_copy_from_url`` is
        # the only dst-side SDK call.
        dst_bc.start_copy_from_url = AsyncMock()

        cc.get_blob_client.side_effect = [src_bc, dst_bc]

        await backend.move("src.txt", "dst.txt", overwrite=True)
        assert dst_bc.start_copy_from_url.call_count == 1
        assert src_bc.delete_blob.call_count == 1
        dst_bc.get_blob_properties.assert_not_called()

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_overwrite(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        src_bc.url = "https://x.blob.core.windows.net/test/src.txt"

        dst_bc = AsyncMock(spec=BlobClient)
        # Non-HNS overwrite=True copies via ``start_copy_from_url`` without
        # any dst probe; BUG-200's hdi_isfolder probe is HNS-only.
        # ``get_blob_properties`` is intentionally not set up — never awaited.
        dst_bc.start_copy_from_url = AsyncMock()

        cc.get_blob_client.side_effect = [src_bc, dst_bc]

        await backend.copy("src.txt", "dst.txt", overwrite=True)
        assert dst_bc.start_copy_from_url.call_count == 1
        dst_bc.get_blob_properties.assert_not_called()

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.parametrize("overwrite", [True, False], ids=["overwrite", "no-overwrite"])
    async def test_move_self_op_is_noop(self, overwrite: bool) -> None:
        """BE-018 / ASYNC-018: move(p, p) is a no-op — no copy or delete fired."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        await backend.move("file.txt", "file.txt", overwrite=overwrite)

        # Only one blob client lookup (for the existence probe); no copy or delete.
        assert cc.get_blob_client.call_count == 1
        bc.start_copy_from_url.assert_not_called()
        bc.delete_blob.assert_not_called()

    @pytest.mark.spec("ASYNC-018")
    async def test_move_self_op_missing_raises_not_found(self) -> None:
        """move(p, p) where p does not exist raises NotFound (not AlreadyExists)."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))

        with pytest.raises(NotFound, match="not found|Not found"):
            await backend.move("missing.txt", "missing.txt")

    @pytest.mark.spec("ASYNC-019")
    @pytest.mark.parametrize("overwrite", [True, False], ids=["overwrite", "no-overwrite"])
    async def test_copy_self_op_is_noop(self, overwrite: bool) -> None:
        """BE-019 / ASYNC-019: copy(p, p) is a no-op — no copy fired."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        await backend.copy("file.txt", "file.txt", overwrite=overwrite)

        # Only one blob client lookup (for the existence probe); no copy.
        assert cc.get_blob_client.call_count == 1
        bc.start_copy_from_url.assert_not_called()

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_self_op_missing_raises_not_found(self) -> None:
        """copy(p, p) where p does not exist raises NotFound (not AlreadyExists)."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))

        with pytest.raises(NotFound, match="not found|Not found"):
            await backend.copy("missing.txt", "missing.txt")

    @pytest.mark.spec("AZ-017")
    @pytest.mark.parametrize("overwrite", [True, False], ids=["overwrite", "no-overwrite"])
    async def test_move_self_op_normalised_no_data_loss(self, overwrite: bool) -> None:
        """BK-301 / L1: non-canonical paths naming the same blob (``a//b`` vs
        ``a/b``) are recognised as a self-move after normalisation — no
        copy-to-self + delete-source data loss, and no AlreadyExists when
        overwrite is False (BE-018 self-move is a no-op)."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        await backend.move("a//b", "a/b", overwrite=overwrite)

        assert cc.get_blob_client.call_count == 1  # single existence probe; no copy/delete
        bc.start_copy_from_url.assert_not_called()
        bc.delete_blob.assert_not_called()

    @pytest.mark.spec("AZ-018")
    @pytest.mark.parametrize("overwrite", [True, False], ids=["overwrite", "no-overwrite"])
    async def test_copy_self_op_normalised_is_noop(self, overwrite: bool) -> None:
        """BK-301 / L1: ``copy('a//b', 'a/b')`` is a self-op after normalisation
        (BE-019 no-op regardless of overwrite)."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        await backend.copy("a//b", "a/b", overwrite=overwrite)

        assert cc.get_blob_client.call_count == 1  # single existence probe; no copy
        bc.start_copy_from_url.assert_not_called()


class TestAsyncAzureGlobErrorParity:
    """BK-301 / L2: a glob pattern-compile error (re.error) propagates as-is
    rather than being re-wrapped as a backend error — aligning the async twin
    with the sync one (the async glob previously wrapped the whole body)."""

    @pytest.mark.spec("AZ-019")
    async def test_glob_propagates_pattern_compile_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import remote_store._glob as glob_mod

        backend, cc, bc = _setup_non_hns_backend()

        def _boom(_pattern: str) -> Any:
            raise re.error("bad pattern")

        monkeypatch.setattr(glob_mod, "pattern_to_regex", _boom)

        with pytest.raises(re.error):
            async for _info in backend.glob("data/*.csv"):
                pass


# =============================================================================
# Metadata (ASYNC-016, ASYNC-017)
# =============================================================================


class TestAsyncAzureMetadata:
    """ASYNC-016/017: get_file_info, get_folder_info, exists, is_file, is_folder."""

    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props(size=42))

        info = await backend.get_file_info("file.txt")
        assert info.name == "file.txt"
        assert info.size == 42
        assert info.modified_at is not None

    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info_not_found(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))

        with pytest.raises(NotFound, match="not found|Not found"):
            await backend.get_file_info("missing.txt")

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        blob1 = _mock_blob_props(size=10)
        blob2 = _mock_blob_props(size=20)
        blob2.last_modified = datetime(2024, 6, 1, tzinfo=timezone.utc)

        cc.list_blobs.return_value = _async_iter([blob1, blob2])

        info = await backend.get_folder_info("dir")
        assert info.file_count == 2
        assert info.total_size == 30
        assert info.modified_at == datetime(2024, 6, 1, tzinfo=timezone.utc)

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_not_found(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.list_blobs.return_value = _async_iter([])

        with pytest.raises(NotFound, match="not found|Folder not found"):
            await backend.get_folder_info("empty")

    @pytest.mark.spec("ASYNC-004")
    async def test_exists_file(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        assert await backend.exists("file.txt") is True

    @pytest.mark.spec("ASYNC-004")
    async def test_exists_missing(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        cc.list_blobs.return_value = _async_iter([])

        assert await backend.exists("ghost.txt") is False

    @pytest.mark.spec("ASYNC-004")
    async def test_exists_root(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        assert await backend.exists("") is True

    @pytest.mark.spec("ASYNC-004")
    async def test_exists_folder_via_prefix(self) -> None:
        """Non-HNS: folder existence checked via blob prefix listing."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        blob = MagicMock(spec=BlobProperties)
        blob.name = "dir/file.txt"
        cc.list_blobs.return_value = _async_iter([blob])

        assert await backend.exists("dir") is True

    @pytest.mark.spec("ASYNC-005")
    async def test_is_file(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        assert await backend.is_file("file.txt") is True

    @pytest.mark.spec("ASYNC-005")
    async def test_is_file_missing(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))

        assert await backend.is_file("missing.txt") is False

    @pytest.mark.spec("ASYNC-005")
    async def test_is_file_hns_directory_marker(self) -> None:
        """Blobs with hdi_isfolder metadata are directories, not files."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(
            return_value=_mock_blob_props(metadata={"hdi_isfolder": "true"}),
        )
        assert await backend.is_file("dir") is False

    @pytest.mark.spec("ASYNC-005")
    async def test_is_folder(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        blob = MagicMock(spec=BlobProperties)
        blob.name = "dir/file.txt"
        cc.list_blobs.return_value = _async_iter([blob])

        assert await backend.is_folder("dir") is True

    @pytest.mark.spec("ASYNC-005")
    async def test_is_folder_empty_root(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        assert await backend.is_folder("") is True


# =============================================================================
# Close / Lifecycle (ASYNC-022)
# =============================================================================


class TestAsyncAzureClose:
    """ASYNC-022: aclose releases all clients."""

    @pytest.mark.spec("ASYNC-022")
    async def test_aclose_closes_all_clients(self) -> None:
        backend = _make_backend()
        mock_cc = AsyncMock(spec=ContainerClient)
        mock_bs = AsyncMock(spec=BlobServiceClient)
        mock_ds = AsyncMock(spec=DataLakeServiceClient)
        mock_fs = AsyncMock(spec=FileSystemClient)

        backend._cc_instance = mock_cc
        backend._blob_service_instance = mock_bs
        backend._datalake_service_instance = mock_ds
        backend._fs_instance = mock_fs

        await backend.aclose()

        assert mock_cc.close.call_count == 1
        assert mock_bs.close.call_count == 1
        assert mock_ds.close.call_count == 1
        assert mock_fs.close.call_count == 1

    @pytest.mark.spec("ASYNC-022")
    async def test_aclose_suppresses_errors(self) -> None:
        backend = _make_backend()
        mock_cc = AsyncMock(spec=ContainerClient)
        mock_cc.close.side_effect = Exception("close error")
        backend._cc_instance = mock_cc
        backend._blob_service_instance = AsyncMock(spec=BlobServiceClient)

        # Should not raise
        result = await backend.aclose()
        assert result is None

    @pytest.mark.spec("ASYNC-022")
    async def test_aclose_without_connection(self) -> None:
        """aclose() before any connection is safe."""
        backend = _make_backend()
        result = await backend.aclose()
        assert result is None

    @pytest.mark.spec("ASYNC-022")
    async def test_aclose_idempotent(self) -> None:
        backend = _make_backend()
        await backend.aclose()
        result = await backend.aclose()
        assert result is None


# =============================================================================
# Context Manager (ASYNC-023)
# =============================================================================


class TestAsyncAzureContextManager:
    """ASYNC-023: async context manager protocol."""

    @pytest.mark.spec("ASYNC-023")
    async def test_async_with_protocol(self) -> None:
        backend = _make_backend()
        async with backend as b:
            assert b is backend
            assert b.name == "async-azure"

    @pytest.mark.spec("ASYNC-023")
    async def test_exit_calls_aclose(self) -> None:
        backend = _make_backend()
        mock_cc = AsyncMock(spec=ContainerClient)
        backend._cc_instance = mock_cc
        backend._blob_service_instance = AsyncMock(spec=BlobServiceClient)

        async with backend:
            pass

        assert mock_cc.close.call_count == 1


# =============================================================================
# Path and Resolve (ASYNC-025, ASYNC-026, ASYNC-027)
# =============================================================================


class TestAsyncAzurePathAndResolve:
    """ASYNC-025/026/027: to_key, native_path, resolve."""

    @pytest.mark.spec("ASYNC-025")
    @pytest.mark.parametrize(
        ("inp", "expected"),
        [
            pytest.param("test/data/file.txt", "data/file.txt", id="strips-container-prefix"),
            pytest.param("data/file.txt", "data/file.txt", id="no-prefix-unchanged"),
            pytest.param("", "", id="empty-string"),
        ],
    )
    def test_to_key(self, inp: str, expected: str) -> None:
        backend = _make_backend(container="test")
        assert backend.to_key(inp) == expected

    @pytest.mark.spec("ASYNC-026")
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            pytest.param("file.txt", "test/file.txt", id="simple-file"),
            pytest.param("a/b/c.txt", "test/a/b/c.txt", id="nested-path"),
            pytest.param("", "test", id="root"),
        ],
    )
    def test_native_path(self, path: str, expected: str) -> None:
        backend = _make_backend(container="test")
        assert backend.native_path(path) == expected

    @pytest.mark.spec("ASYNC-027", "ASYNC-058")
    def test_resolve(self) -> None:
        backend = _make_backend()
        plan = backend.resolve("file.txt")
        assert plan.kind == "async-azure"
        assert plan.backend == "async-azure"
        assert plan.key == "file.txt"
        assert plan.native_path == "test/file.txt"
        assert "container" in plan.details
        assert plan.details["container"] == "test"

    @pytest.mark.spec("ASYNC-027", "ASYNC-058")
    def test_resolve_has_account_url(self) -> None:
        backend = _make_backend()
        plan = backend.resolve("file.txt")
        assert "account_url" in plan.details


# =============================================================================
# Check Health
# =============================================================================


class TestAsyncAzureCheckHealth:
    """check_health exercises _errors() and container properties."""

    @pytest.mark.spec("ASYNC-024", "ASYNC-075")
    async def test_check_health_non_hns(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.get_container_properties = AsyncMock(return_value={"name": "test"})
        await backend.check_health()
        assert cc.get_container_properties.call_count == 1

    @pytest.mark.spec("ASYNC-024", "ASYNC-075")
    async def test_check_health_error_mapped(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.get_container_properties = AsyncMock(
            side_effect=ClientAuthenticationError("bad creds"),
        )
        with pytest.raises(PermissionDenied, match="Authentication failed"):
            await backend.check_health()


# =============================================================================
# Glob
# =============================================================================


class TestAsyncAzureGlob:
    """ASYNC-028: glob delegates to list_files + regex matching."""

    @pytest.mark.spec("ASYNC-028")
    async def test_glob_matches_pattern(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        blob1 = MagicMock(spec=BlobProperties)
        blob1.name = "data/report.csv"
        blob1.size = 100
        blob1.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blob1.etag = None
        blob1.content_settings = MagicMock(spec=ContentSettings)
        blob1.content_settings.content_md5 = None

        blob2 = MagicMock(spec=BlobProperties)
        blob2.name = "data/image.png"
        blob2.size = 200
        blob2.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blob2.etag = None
        blob2.content_settings = MagicMock(spec=ContentSettings)
        blob2.content_settings.content_md5 = None

        cc.walk_blobs.return_value = _async_iter([blob1, blob2])
        results = [info async for info in backend.glob("data/*.csv")]
        assert len(results) == 1
        assert results[0].name == "report.csv"

    @pytest.mark.spec("ASYNC-028")
    async def test_glob_no_matches(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.walk_blobs.return_value = _async_iter([])
        results = [info async for info in backend.glob("missing/*.txt")]
        assert results == []


# =============================================================================
# Unwrap
# =============================================================================


class TestAsyncAzureUnwrap:
    """ASYNC-025: unwrap exposes native async FileSystemClient."""

    @pytest.mark.spec("ASYNC-025")
    def test_unwrap_unsupported_type(self) -> None:
        backend = _make_backend()
        with pytest.raises(CapabilityNotSupported, match="does not expose"):
            backend.unwrap(str)

    @pytest.mark.spec("ASYNC-025")
    def test_unwrap_filesystem_client(self) -> None:
        from azure.storage.filedatalake.aio import FileSystemClient as AsyncFSClient

        backend = _make_backend()
        mock_fs = MagicMock(spec=FileSystemClient)
        backend._fs_instance = mock_fs
        backend._datalake_service_instance = AsyncMock(spec=DataLakeServiceClient)
        result = backend.unwrap(AsyncFSClient)
        assert result is mock_fs


# =============================================================================
# HNS Code Paths (mock-based)
# =============================================================================


class TestAsyncAzureHNSPaths:
    """Mock-based tests for HNS code paths."""

    def _make_hns_backend(self) -> AsyncAzureBackend:
        """Create a backend with HNS enabled and mocked async SDK clients."""
        backend = _make_backend()
        backend._hns = True
        backend._blob_service_instance = AsyncMock(spec=BlobServiceClient)
        backend._cc_instance = AsyncMock(spec=ContainerClient)
        backend._datalake_service_instance = AsyncMock(spec=DataLakeServiceClient)
        backend._fs_instance = AsyncMock(spec=FileSystemClient)
        return backend

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_uses_get_paths_on_hns(self) -> None:
        """BUG-199: HNS branch uses DFS get_paths, not Blob list_blobs."""
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        dc.get_directory_properties.return_value = MagicMock(
            spec=DirectoryProperties, metadata={"hdi_isfolder": "true"}
        )
        backend._fs_instance.get_directory_client.return_value = dc
        backend._fs_instance.get_paths.return_value = _async_iter([])
        info = await backend.get_folder_info("my-dir")
        dc.get_directory_properties.assert_called_once()
        backend._fs_instance.get_paths.assert_called_once()
        assert info.file_count == 0

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_filters_hns_directory_markers(self) -> None:
        """BUG-199: file_count excludes hdi_isfolder=true entries returned by get_paths."""
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        dc.get_directory_properties.return_value = MagicMock(
            spec=DirectoryProperties, metadata={"hdi_isfolder": "true"}
        )
        backend._fs_instance.get_directory_client.return_value = dc
        file_a = MagicMock(spec=PathProperties)
        file_a.is_directory = False
        file_a.content_length = 3
        file_a.last_modified = None
        dir_marker = MagicMock(spec=PathProperties)
        dir_marker.is_directory = True
        dir_marker.content_length = 0
        dir_marker.last_modified = None
        file_b = MagicMock(spec=PathProperties)
        file_b.is_directory = False
        file_b.content_length = 2
        file_b.last_modified = None
        backend._fs_instance.get_paths.return_value = _async_iter([file_a, dir_marker, file_b])
        info = await backend.get_folder_info("mix")
        assert info.file_count == 2, "directory marker must not be counted as a file"
        assert info.total_size == 5

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_raises_not_found_on_hns_missing_directory(self) -> None:
        """ASYNC-017: !PathExists → NotFound. get_directory_properties raises ResourceNotFoundError."""
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        dc.get_directory_properties.side_effect = ResourceNotFoundError("not found")
        backend._fs_instance.get_directory_client.return_value = dc
        with pytest.raises(NotFound, match=r"^Not found: missing\b"):
            await backend.get_folder_info("missing")

    @pytest.mark.spec("ASYNC-016", "BE-021")
    async def test_get_file_info_raises_invalid_path_on_hns_directory(self) -> None:
        """BUG-195: get_file_info must raise InvalidPath when hdi_isfolder=true (ASYNC-016)."""
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        props = MagicMock(spec=BlobProperties)
        props.metadata = {"hdi_isfolder": "true"}
        bc.get_blob_properties = AsyncMock(return_value=props)
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await backend.get_file_info("mydir")

    @pytest.mark.spec("ASYNC-005")
    async def test_is_folder_returns_false_for_file_path_on_hns(self) -> None:
        """BUG-203 (async parity): is_folder must return False when the path is a file.

        On HNS, ``get_directory_properties()`` succeeds for file paths too
        (returns status 200).  Without the ``hdi_isfolder`` probe, async
        ``is_folder`` wrongly returns True for regular files — same defect
        shape as the sync sibling closed by BUG-203.
        """
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        file_props = MagicMock(spec=DirectoryProperties)
        file_props.metadata = {}  # regular file: no hdi_isfolder
        dc.get_directory_properties = AsyncMock(return_value=file_props)
        backend._fs_instance.get_directory_client.return_value = dc
        assert await backend.is_folder("a.txt") is False

    @pytest.mark.spec("ASYNC-016")
    async def test_get_file_info_raises_not_found_on_missing_path(self) -> None:
        """ASYNC-016: !PathExists → NotFound (non-HNS path still works)."""
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("not found"))
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(NotFound):
            await backend.get_file_info("missing.txt")

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_root_hns_call_shape(self) -> None:
        """BUG-213: get_folder_info('') on HNS skips the dir-probe (root is
        always a folder) and calls get_paths('/') — the 'or /' fallback is
        the root-path accommodation.

        Real ADLS Gen2 rejects ``get_directory_client("")`` with "Please
        specify a file system name and file path", so the impl must
        short-circuit the probe for ``ap == ""``.  Pins the intended call
        shape so any future change to root-path handling surfaces as a
        regression independent of live SDK semantics.
        """
        backend = self._make_hns_backend()
        backend._fs_instance.get_paths.return_value = _async_iter([])

        info = await backend.get_folder_info("")

        # Root path must SKIP get_directory_client (would 400 on real ADLS).
        backend._fs_instance.get_directory_client.assert_not_called()
        # get_paths must use the '/' fallback (azure_path or '/') for the root case.
        call_kwargs = backend._fs_instance.get_paths.call_args
        assert call_kwargs is not None
        # Explicit if/elif: a falsy-but-present path="" would silently fall through
        # `kwargs.get("path") or args[0]`, masking the very regression this test pins.
        if "path" in call_kwargs.kwargs:
            path_arg = call_kwargs.kwargs["path"]
        elif call_kwargs.args:
            path_arg = call_kwargs.args[0]
        else:
            path_arg = None
        assert path_arg == "/", f"get_paths must be called with '/' at the root (azure_path or '/'); got {path_arg!r}"
        assert info.file_count == 0
        assert info.total_size == 0

    @pytest.mark.spec("ASYNC-018")
    async def test_move_uses_rename_on_hns(self) -> None:
        backend = self._make_hns_backend()
        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        dst_bc = AsyncMock(spec=BlobClient)
        dst_bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))

        backend._cc_instance.get_blob_client.side_effect = [src_bc, dst_bc]

        fc = AsyncMock(spec=DataLakeFileClient)
        backend._fs_instance.get_file_client.return_value = fc

        await backend.move("src.txt", "dst.txt")
        assert fc.rename_file.call_count == 1
        assert fc.rename_file.call_args[0][0] == "test/dst.txt"

    @pytest.mark.spec("ASYNC-004")
    @pytest.mark.spec("ASYNC-070")
    async def test_declared_non_hns_move_uses_copy_delete(self) -> None:
        """A backend declared ``hns=False`` takes the copy+delete move path (AZ-006/AZ-017).

        Dual-mode architecture (ASYNC-070): the declared flag, not a probe,
        selects the Blob vs DataLake code path.
        """
        backend = _make_backend(hns=False)
        svc = AsyncMock(spec=BlobServiceClient)
        backend._blob_service_instance = svc
        backend._cc_instance = AsyncMock(spec=ContainerClient)
        backend._fs_instance = AsyncMock(spec=FileSystemClient)
        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        dst_bc = AsyncMock(spec=BlobClient)
        dst_bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.side_effect = [src_bc, dst_bc]

        await backend.move("src.txt", "dst.txt")

        # No HNS probe is ever issued; the declared flag drives the path.
        svc.get_account_information.assert_not_called()
        assert dst_bc.start_copy_from_url.call_count == 1
        assert dst_bc.start_copy_from_url.call_args[0][0] == src_bc.url
        assert src_bc.delete_blob.call_count == 1
        backend._fs_instance.get_file_client.assert_not_called()  # no HNS rename branch

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.parametrize("op", ["move", "copy"])
    async def test_source_is_directory_raises_invalid_path(self, op: str) -> None:
        """BUG-200: move/copy with an HNS directory src must raise InvalidPath."""
        backend = self._make_hns_backend()
        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props(metadata={"hdi_isfolder": "true"}))
        backend._cc_instance.get_blob_client.return_value = src_bc

        with pytest.raises(InvalidPath, match="src_dir"):
            await getattr(backend, op)("src_dir", "dst.txt")

    @pytest.mark.spec("ASYNC-018")
    @pytest.mark.parametrize("op", ["move", "copy"])
    async def test_destination_is_directory_raises_invalid_path(self, op: str) -> None:
        """BUG-200: move/copy with an HNS directory dst must raise InvalidPath."""
        backend = self._make_hns_backend()
        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        dst_bc = AsyncMock(spec=BlobClient)
        dst_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props(metadata={"hdi_isfolder": "true"}))
        backend._cc_instance.get_blob_client.side_effect = [src_bc, dst_bc]

        with pytest.raises(InvalidPath, match="dst_dir"):
            await getattr(backend, op)("src.txt", "dst_dir")

    @pytest.mark.spec("ASYNC-020")
    async def test_write_atomic_hns_uses_temp_and_rename(self) -> None:
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc.get_file_properties = AsyncMock(return_value={})
        tmp_fc.rename_file.return_value = final_fc
        backend._fs_instance.get_file_client.return_value = tmp_fc

        await backend.write_atomic("dir/file.txt", b"content")
        assert tmp_fc.upload_data.call_count == 1
        assert tmp_fc.rename_file.call_count == 1

    @pytest.mark.spec("ASYNC-010", "ASYNC-021")
    async def test_write_atomic_hns_streams_async_chunks(self) -> None:
        """HNS write_atomic streams AsyncIterator payloads via create_file + append_data + flush_data.

        upload_data passes length=None for async generators, so the SDK omits the
        required ``?position=`` query parameter on real ADLS Gen2, returning
        MissingRequiredQueryParameter (BUG-194).  The fix: drive the DFS append
        protocol directly — one append_data call per chunk with the cumulative offset,
        then flush_data with the final byte count.  Memory is bounded to one chunk at
        a time (SIO-003, ASYNC-021); upload_data is NOT called for AsyncIterator input.
        """
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        backend._fs_instance.get_file_client.return_value = tmp_fc

        final_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc.get_file_properties = AsyncMock(return_value={})
        tmp_fc.rename_file.return_value = final_fc

        async def chunk_gen():  # noqa: ANN202
            yield b"hello "
            yield b"world"

        agen = chunk_gen()
        await backend.write_atomic("dir/file.txt", agen)

        # AsyncIterator path: create_file → append_data per chunk → flush_data.
        # Pin the metadata kwarg explicitly: a future refactor that drops the
        # metadata= argument from create_file would still pass assert_awaited_once().
        tmp_fc.create_file.assert_awaited_once_with(metadata=None)
        assert tmp_fc.append_data.await_count == 2
        tmp_fc.append_data.assert_any_await(b"hello ", offset=0, length=6)
        tmp_fc.append_data.assert_any_await(b"world", offset=6, length=5)
        tmp_fc.flush_data.assert_awaited_once_with(11)
        assert tmp_fc.rename_file.call_count == 1
        # upload_data must NOT be called for AsyncIterator input (BUG-194 regression guard).
        tmp_fc.upload_data.assert_not_awaited()

    @pytest.mark.spec("ASYNC-010", "WR-012")
    async def test_write_atomic_hns_async_iterator_metadata_reaches_create_file(self) -> None:
        """AsyncIterator + metadata routes the kwarg to create_file, not upload_data.

        BUG-194's AsyncIterator branch drives the DFS protocol directly: metadata is
        passed to ``create_file`` (which sets it on the temp file before the chunks
        are appended), not to ``upload_data`` (which is not awaited on this path).
        A future refactor that drops the metadata kwarg from ``create_file`` would
        silently lose user metadata on streaming HNS writes.
        """
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        backend._fs_instance.get_file_client.return_value = tmp_fc

        final_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc.get_file_properties = AsyncMock(return_value={})
        tmp_fc.rename_file.return_value = final_fc

        async def chunk_gen():  # noqa: ANN202
            yield b"hello "
            yield b"world"

        result = await backend.write_atomic("dir/file.txt", chunk_gen(), metadata={"k": "v"})

        # WR-012: metadata must reach create_file on the AsyncIterator path.
        tmp_fc.create_file.assert_awaited_once_with(metadata={"k": "v"})
        # upload_data must NOT be called for AsyncIterator input.
        tmp_fc.upload_data.assert_not_awaited()
        # WR-012: WriteResult.metadata still echoes the caller's mapping.
        assert result.metadata == {"k": "v"}

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic_hns_cleans_up_on_failure(self) -> None:
        """HNS write_atomic deletes temp file when rename fails."""
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        tmp_fc.rename_file = AsyncMock(side_effect=RuntimeError("rename failed"))
        backend._fs_instance.get_file_client.return_value = tmp_fc

        with pytest.raises(RemoteStoreError):
            await backend.write_atomic("dir/file.txt", b"content")
        assert tmp_fc.delete_file.call_count == 1

    @pytest.mark.spec("WR-004")
    async def test_write_atomic_hns_returns_native_fields(self) -> None:
        """HNS write_atomic populates etag, last_modified, size, source from get_file_properties.

        version_id and digest are None on HNS: ADLS Gen2 PathProperties does not
        surface content_md5 or version_id via get_file_properties().
        """
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc = AsyncMock(spec=DataLakeFileClient)
        # BUG-196: the fix uses getattr(props, "etag"/"last_modified") so the mock
        # must be an object with those attributes, not a plain dict.
        props = MagicMock(
            spec=["etag", "last_modified"],
            etag='"abc123"',
            last_modified=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        final_fc.get_file_properties = AsyncMock(return_value=props)
        tmp_fc.rename_file.return_value = final_fc
        backend._fs_instance.get_file_client.return_value = tmp_fc

        tmp_fc.upload_data = AsyncMock(return_value=None)

        result = await backend.write_atomic("file.txt", b"content")

        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.etag == "abc123"
        assert result.last_modified == datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert result.size == 7
        assert result.version_id is None
        assert result.digest is None

    @pytest.mark.spec("WR-004", "WR-001a")
    async def test_write_atomic_hns_get_file_properties_success_populates_etag(self) -> None:
        """BUG-196 success branch: get_file_properties returns props → etag/last_modified populated.

        Verifies the try branch of the BUG-196 try/except mirrors the sync BUG-173
        pattern: props attributes are extracted via getattr and forwarded to
        _build_azure_write_result.
        """
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc = AsyncMock(spec=DataLakeFileClient)
        props = MagicMock(
            spec=["etag", "last_modified"],
            etag='"deadbeef"',
            last_modified=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        final_fc.get_file_properties = AsyncMock(return_value=props)
        tmp_fc.rename_file.return_value = final_fc
        backend._fs_instance.get_file_client.return_value = tmp_fc
        tmp_fc.upload_data = AsyncMock(return_value=None)

        result = await backend.write_atomic("hns/file.txt", b"hello")

        assert result.source == "native"
        assert result.etag == "deadbeef"  # quote-stripped by _build_azure_write_result
        assert result.last_modified == datetime(2025, 6, 1, tzinfo=timezone.utc)
        assert result.size == 5

    @pytest.mark.spec("WR-004", "WR-001a")
    async def test_write_atomic_hns_get_file_properties_failure_returns_etag_none(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """BUG-196 fallback branch: get_file_properties raises → etag=None, write does not fail.

        The rename already committed the write. A transient post-rename read failure
        must not surface as a write failure (retrying would raise AlreadyExists on
        overwrite=False or silently double-write). Mirrors the sync BUG-173 pattern.
        WR-001a lists etag as Optional; etag=None is the documented fallback value.
        """
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc.get_file_properties = AsyncMock(side_effect=RuntimeError("network blip"))
        tmp_fc.rename_file.return_value = final_fc
        backend._fs_instance.get_file_client.return_value = tmp_fc
        tmp_fc.upload_data = AsyncMock(return_value=None)

        with caplog.at_level(logging.WARNING):
            result = await backend.write_atomic("hns/file.txt", b"hello")

        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.etag is None
        assert result.last_modified is None
        assert result.size == 5
        assert any("post-rename get_file_properties failed" in r.message for r in caplog.records), (
            "expected warning log on swallowed post-commit read failure"
        )

    @pytest.mark.spec("WR-010", "WR-012")
    async def test_write_atomic_hns_metadata_preserved(self) -> None:
        """HNS write_atomic forwards the metadata kwarg to upload_data on the temp file.

        WriteResult.metadata echoes the caller's mapping by construction (WR-012).
        Post-rename metadata preservation on the live file is an ADLS Gen2 rename
        semantics concern; live coverage of that property lives in
        ``tests/backends/conformance/test_atomic.py::TestWriteResultConformance::test_metadata_round_trips_via_get_file_info``
        (parametrised over ``write`` and ``write_atomic``, run against
        ``azure_live`` / ``azure_live_async``).
        """
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc.get_file_properties = AsyncMock(return_value={})
        tmp_fc.rename_file.return_value = final_fc
        backend._fs_instance.get_file_client.return_value = tmp_fc

        tmp_fc.upload_data = AsyncMock(return_value=None)

        result = await backend.write_atomic("dir/file.txt", b"data", metadata={"k": "v"})

        upload_kwargs = tmp_fc.upload_data.call_args[1]
        assert upload_kwargs.get("metadata") == {"k": "v"}
        assert result.metadata == {"k": "v"}

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic_hns_overwrite_true_does_not_raise_already_exists(self) -> None:
        """overwrite=True: HNS dir check still runs but AlreadyExists is not raised for a regular file."""
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc.get_file_properties = AsyncMock(return_value={})
        tmp_fc.rename_file.return_value = final_fc
        backend._fs_instance.get_file_client.return_value = tmp_fc

        await backend.write_atomic("dir/file.txt", b"data", overwrite=True)

        bc.get_blob_properties.assert_awaited_once()
        assert tmp_fc.upload_data.call_count == 1

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic_hns_overwrite_false_file_exists_raises(self) -> None:
        """overwrite=False raises AlreadyExists when the target file already exists."""
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        backend._cc_instance.get_blob_client.return_value = bc

        with pytest.raises(AlreadyExists):
            await backend.write_atomic("dir/file.txt", b"data", overwrite=False)

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_hns_recursive(self) -> None:
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        dc.get_directory_properties.return_value = MagicMock(
            spec=DirectoryProperties, metadata={"hdi_isfolder": "true"}
        )
        backend._fs_instance.get_directory_client.return_value = dc

        await backend.delete_folder("my-dir", recursive=True)
        assert dc.delete_directory.call_count == 1

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_hns_non_recursive_empty(self) -> None:
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        dc.get_directory_properties.return_value = MagicMock(
            spec=DirectoryProperties, metadata={"hdi_isfolder": "true"}
        )
        backend._fs_instance.get_directory_client.return_value = dc
        backend._fs_instance.get_paths.return_value = _async_iter([])

        await backend.delete_folder("my-dir", recursive=False)
        assert dc.delete_directory.call_count == 1

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_hns_non_recursive_non_empty_raises(self) -> None:
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        dc.get_directory_properties.return_value = MagicMock(
            spec=DirectoryProperties, metadata={"hdi_isfolder": "true"}
        )
        backend._fs_instance.get_directory_client.return_value = dc

        child = MagicMock(spec=PathProperties)
        backend._fs_instance.get_paths.return_value = _async_iter([child])

        with pytest.raises(DirectoryNotEmpty, match="not empty|Folder not empty"):
            await backend.delete_folder("my-dir", recursive=False)

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_hns_raises_invalid_path_on_file(self) -> None:
        """BUG-198: delete_folder on a file path must raise InvalidPath, not DirectoryNotEmpty."""
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        # Simulate ADLS Gen2 behaviour: get_directory_properties succeeds for
        # file paths but returns no hdi_isfolder metadata (resource_type=file).
        dc.get_directory_properties.return_value = MagicMock(spec=DirectoryProperties, metadata={})
        backend._fs_instance.get_directory_client.return_value = dc
        with pytest.raises(InvalidPath, match="file-path.txt"):
            await backend.delete_folder("file-path.txt")
        dc.delete_directory.assert_not_called()

    @pytest.mark.spec("ASYNC-017")
    async def test_get_folder_info_hns_raises_invalid_path_on_file(self) -> None:
        """BUG-198: get_folder_info on a file path must raise InvalidPath."""
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        # Simulate ADLS Gen2 behaviour: get_directory_properties succeeds for
        # file paths but returns no hdi_isfolder metadata (resource_type=file).
        dc.get_directory_properties.return_value = MagicMock(spec=DirectoryProperties, metadata={})
        backend._fs_instance.get_directory_client.return_value = dc
        with pytest.raises(InvalidPath, match="file-path.txt"):
            await backend.get_folder_info("file-path.txt")
        backend._fs_instance.get_paths.assert_not_called()

    @pytest.mark.spec("ASYNC-005")
    async def test_is_folder_hns_uses_directory_client(self) -> None:
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        # BUG-203: is_folder must read hdi_isfolder from get_directory_properties().
        # A real HNS directory marker has the metadata set; without an explicit
        # props return value, AsyncMock auto-attrs swallow the metadata read.
        dir_props = MagicMock(spec=DirectoryProperties)
        dir_props.metadata = {"hdi_isfolder": "true"}
        dc.get_directory_properties = AsyncMock(return_value=dir_props)
        backend._fs_instance.get_directory_client.return_value = dc

        assert await backend.is_folder("my-dir") is True
        assert dc.get_directory_properties.call_count == 1

    # BUG-197: read, read_bytes, delete must raise InvalidPath for HNS dirs (async)

    @pytest.mark.spec("BE-021", "ASYNC-007")
    async def test_read_bytes_on_hns_directory_raises_invalid_path(self) -> None:
        """BUG-197: async read_bytes on an HNS directory path must raise InvalidPath.

        The download_blob() call succeeds (directory marker is a 0-byte blob);
        the fix inspects downloader.properties.metadata post-download.
        """
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        downloader = AsyncMock(spec=StorageStreamDownloader)
        downloader.readall = AsyncMock(return_value=b"")
        props = MagicMock(spec=["metadata"])
        props.metadata = {"hdi_isfolder": "true"}
        downloader.properties = props
        bc.download_blob = AsyncMock(return_value=downloader)
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="is a directory"):
            await backend.read_bytes("mydir")

    @pytest.mark.spec("BE-021", "ASYNC-007")
    async def test_read_bytes_on_hns_file_returns_bytes(self) -> None:
        """Async read_bytes on a normal HNS file must return its content unchanged."""
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        downloader = AsyncMock(spec=StorageStreamDownloader)
        downloader.readall = AsyncMock(return_value=b"hello")
        props = MagicMock(spec=["metadata"])
        props.metadata = {}
        downloader.properties = props
        bc.download_blob = AsyncMock(return_value=downloader)
        backend._cc_instance.get_blob_client.return_value = bc
        assert await backend.read_bytes("file.txt") == b"hello"

    @pytest.mark.spec("BE-021", "ASYNC-006")
    async def test_read_on_hns_directory_raises_invalid_path(self) -> None:
        """BUG-197: async read (streaming) on an HNS directory must raise InvalidPath.

        download_blob() is awaited; then downloader.properties.metadata is checked
        before yielding any chunks. The downloader is closed before raising so
        the underlying HTTP response is not leaked back to the pool.
        """
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        downloader = AsyncMock(spec=["properties", "chunks", "close"])
        props = MagicMock(spec=["metadata"])
        props.metadata = {"hdi_isfolder": "true"}
        downloader.properties = props
        bc.download_blob = AsyncMock(return_value=downloader)
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="is a directory"):
            async for _ in backend.read("mydir"):
                pass  # pragma: no cover
        # downloader.close() must be called before the InvalidPath raise
        # so the HTTP response is returned to the pool — otherwise the
        # connection leaks (review-flagged BUG-197 follow-up). The impl
        # awaits the result only if isawaitable (works for sync and async
        # SDK signatures), so assert_called_once covers both shapes.
        downloader.close.assert_called_once()

    @pytest.mark.spec("BE-021", "ASYNC-006")
    async def test_read_on_hns_file_yields_chunks(self) -> None:
        """Async read on a normal HNS file must yield its chunks."""
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        downloader = AsyncMock(spec=StorageStreamDownloader)
        props = MagicMock(spec=["metadata"])
        props.metadata = {}
        downloader.properties = props

        async def _chunks():  # noqa: ANN202
            yield b"data"

        downloader.chunks = _chunks
        bc.download_blob = AsyncMock(return_value=downloader)
        backend._cc_instance.get_blob_client.return_value = bc
        chunks = [c async for c in backend.read("file.txt")]
        assert chunks == [b"data"]

    @pytest.mark.spec("BE-021", "ASYNC-012")
    async def test_delete_on_hns_directory_raises_invalid_path(self) -> None:
        """BUG-197: async delete on an HNS directory path must raise InvalidPath.

        The pre-check calls get_blob_properties() before delete_blob();
        when hdi_isfolder is set, InvalidPath is raised without any delete call.
        """
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        dir_props = MagicMock(spec=["metadata"])
        dir_props.metadata = {"hdi_isfolder": "true"}
        bc.get_blob_properties = AsyncMock(return_value=dir_props)
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="is a directory"):
            await backend.delete("mydir")
        bc.delete_blob.assert_not_awaited()

    @pytest.mark.spec("BE-021", "ASYNC-012")
    async def test_delete_on_hns_file_does_not_raise(self) -> None:
        """Async delete on a normal HNS file must not raise InvalidPath."""
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        file_props = MagicMock(spec=["metadata"])
        file_props.metadata = {}
        bc.get_blob_properties = AsyncMock(return_value=file_props)
        bc.delete_blob = AsyncMock(return_value=None)
        backend._cc_instance.get_blob_client.return_value = bc
        await backend.delete("file.txt")
        assert bc.delete_blob.await_count == 1

    @pytest.mark.spec("BE-021", "ASYNC-012")
    async def test_delete_missing_with_missing_ok_true_does_not_raise_on_hns(self) -> None:
        """BUG-197 regression: the async hdi_isfolder HEAD probe must not break missing_ok=True.

        Pre-fix the probe re-raised ``ResourceNotFoundError`` before
        ``delete_blob()`` ever ran, so ``missing_ok=True`` had no opportunity
        to swallow the error.
        """
        from azure.core.exceptions import ResourceNotFoundError

        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        bc.delete_blob = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc
        await backend.delete("missing.txt", missing_ok=True)
        # delete_blob() must have been awaited (probe must not short-circuit
        # on missing-file errors).
        assert bc.delete_blob.await_count == 1

    @pytest.mark.spec("BE-021", "ASYNC-012")
    async def test_delete_directory_is_not_empty_409_maps_to_invalid_path(self) -> None:
        """BUG-197 data-loss guard (async): HNS non-empty directory yields 409 DirectoryIsNotEmpty.

        Async sibling of the sync DirectoryIsNotEmpty fallback test.  When
        the probe fails for any reason and ``delete_blob()`` then surfaces
        ``DirectoryIsNotEmpty``, the fallback must raise ``InvalidPath`` —
        not let ``AlreadyExists`` or a generic mapping silently swallow the
        data-loss signal.
        """
        from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("probe failed"))
        exc = HttpResponseError("conflict")
        exc.error_code = "DirectoryIsNotEmpty"
        bc.delete_blob = AsyncMock(side_effect=exc)
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="is a directory"):
            await backend.delete("mydir")


# =============================================================================
# Max Concurrency (ASYNC-033)
# =============================================================================


class TestAsyncAzureMaxConcurrency:
    """max_concurrency kwarg reaches SDK upload/download call sites."""

    @pytest.mark.spec("ASYNC-008")
    async def test_max_concurrency_threaded_to_upload(self) -> None:
        backend = _make_backend(max_concurrency=4)
        backend._hns = False
        backend._blob_service_instance = AsyncMock(spec=BlobServiceClient)
        cc = AsyncMock(spec=ContainerClient)
        backend._cc_instance = cc
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        bc.upload_blob = AsyncMock()
        cc.get_blob_client.return_value = bc

        await backend.write("file.txt", b"data")
        assert bc.upload_blob.call_count == 1
        assert bc.upload_blob.call_args[1]["max_concurrency"] == 4

    @pytest.mark.spec("ASYNC-007")
    async def test_max_concurrency_threaded_to_download(self) -> None:
        backend = _make_backend(max_concurrency=8)
        backend._hns = False
        backend._blob_service_instance = AsyncMock(spec=BlobServiceClient)
        cc = AsyncMock(spec=ContainerClient)
        backend._cc_instance = cc
        bc = AsyncMock(spec=BlobClient)
        downloader = AsyncMock(spec=StorageStreamDownloader)
        downloader.readall = AsyncMock(return_value=b"data")
        bc.download_blob = AsyncMock(return_value=downloader)
        cc.get_blob_client.return_value = bc

        await backend.read_bytes("file.txt")
        assert bc.download_blob.call_count == 1
        assert bc.download_blob.call_args[1]["max_concurrency"] == 8


# =============================================================================
# Repr (ASYNC-001)
# =============================================================================


class TestAsyncAzureRepr:
    """Repr should not leak credentials."""

    @pytest.mark.spec("ASYNC-001")
    def test_repr_masks_credentials(self) -> None:
        backend = _make_backend()
        r = repr(backend)
        assert "AsyncAzureBackend" in r
        assert "fakekey" not in r
        assert "***" in r

    @pytest.mark.spec("ASYNC-001")
    def test_repr_shows_container(self) -> None:
        backend = _make_backend(container="my-bucket")
        r = repr(backend)
        assert "my-bucket" in r


# =============================================================================
# _azure_common: props_to_fileinfo (ASYNC-016)
# =============================================================================


class TestPropsToFileinfo:
    """Behavioral tests for the shared props_to_fileinfo helper."""

    @pytest.mark.spec("ASYNC-016")
    def test_extracts_name_from_nested_path(self) -> None:
        props = _mock_blob_props(size=50, etag='"0xABC"')
        info = props_to_fileinfo(props, "folder/sub/data.csv")
        assert info.name == "data.csv"
        assert info.size == 50
        assert str(info.path) == "folder/sub/data.csv"

    @pytest.mark.spec("ASYNC-016")
    def test_flat_path_name(self) -> None:
        props = _mock_blob_props(size=10)
        info = props_to_fileinfo(props, "readme.md")
        assert info.name == "readme.md"

    @pytest.mark.spec("ASYNC-016")
    def test_etag_stripped_and_lowered(self) -> None:
        props = _mock_blob_props(etag='"0x8D4BCC2E4835CD0"')
        info = props_to_fileinfo(props, "file.txt")
        assert info.etag == "0x8d4bcc2e4835cd0"

    @pytest.mark.spec("ASYNC-016")
    def test_md5_digest_extracted(self) -> None:
        md5_bytes = b"\xd4\x1d\x8c\xd9\x8f\x00\xb2\x04\xe9\x80\x09\x98\xec\xf8\x42\x7e"
        props = _mock_blob_props(md5=md5_bytes)
        info = props_to_fileinfo(props, "file.txt")
        assert info.digest is not None
        assert info.digest.algorithm == "md5"
        assert info.digest.value == md5_bytes.hex()

    @pytest.mark.spec("ASYNC-016")
    def test_no_md5_returns_no_digest(self) -> None:
        props = _mock_blob_props()
        info = props_to_fileinfo(props, "file.txt")
        assert info.digest is None

    @pytest.mark.spec("ASYNC-016")
    def test_empty_md5_returns_no_digest(self) -> None:
        props = _mock_blob_props(md5=b"")
        info = props_to_fileinfo(props, "file.txt")
        assert info.digest is None

    @pytest.mark.spec("ASYNC-016")
    def test_no_etag_returns_none(self) -> None:
        props = _mock_blob_props()
        props.etag = None
        info = props_to_fileinfo(props, "file.txt")
        assert info.etag is None

    @pytest.mark.spec("ASYNC-016")
    def test_content_length_fallback(self) -> None:
        """Uses content_length when size is missing."""
        props = _mock_blob_props(size=0)
        props.size = None
        props.content_length = 77
        info = props_to_fileinfo(props, "file.txt")
        assert info.size == 77


# =============================================================================
# _azure_common: classify_azure_error — OSError unwrap (ASYNC-024)
# =============================================================================


class TestClassifyAzureErrorOSErrorUnwrap:
    """classify_azure_error unwraps OSError wrapping an AzureError."""

    @pytest.mark.spec("ASYNC-024")
    def test_oserror_wrapping_resource_not_found(self) -> None:
        inner = ResourceNotFoundError("blob not found")
        wrapper = OSError("read failed")
        wrapper.__cause__ = inner
        mapped = classify_azure_error(wrapper, "data.bin", "async-azure")
        assert mapped.path == "data.bin"
        assert mapped.backend == "async-azure"
        assert "Not found" in str(mapped)

    @pytest.mark.spec("ASYNC-024")
    def test_oserror_wrapping_service_request_error(self) -> None:
        inner = ServiceRequestError("connection timeout")
        wrapper = OSError("stream read failed")
        wrapper.__cause__ = inner
        mapped = classify_azure_error(wrapper, "data.bin", "async-azure")
        assert isinstance(mapped, BackendUnavailable)
        assert mapped.path == "data.bin"


# =============================================================================
# _azure_common: resolve_credential (ASYNC-001)
# =============================================================================


class TestResolveCredential:
    """resolve_credential returns the correct credential type."""

    @pytest.mark.spec("ASYNC-001")
    def test_explicit_credential_returned(self) -> None:
        sentinel = object()
        result = resolve_credential(sentinel, None, None, is_async=False, backend_name="test")
        assert result is sentinel

    @pytest.mark.spec("ASYNC-001")
    def test_account_key_used(self) -> None:
        result = resolve_credential(None, "my-key", None, is_async=False, backend_name="test")
        assert result == "my-key"

    @pytest.mark.spec("ASYNC-001")
    def test_sas_token_used(self) -> None:
        result = resolve_credential(None, None, "my-sas", is_async=False, backend_name="test")
        assert result == "my-sas"

    @pytest.mark.spec("ASYNC-001")
    def test_account_key_preferred_over_sas(self) -> None:
        result = resolve_credential(None, "my-key", "my-sas", is_async=False, backend_name="test")
        assert result == "my-key"

    @pytest.mark.spec("ASYNC-001")
    def test_default_credential_sync(self) -> None:
        """Falls back to DefaultAzureCredential for sync path."""
        result = resolve_credential(None, None, None, is_async=False, backend_name="test")
        from azure.identity import DefaultAzureCredential

        assert isinstance(result, DefaultAzureCredential)

    @pytest.mark.spec("ASYNC-001")
    def test_default_credential_async(self) -> None:
        """Falls back to DefaultAzureCredential for async path."""
        result = resolve_credential(None, None, None, is_async=True, backend_name="test")
        from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

        assert isinstance(result, AsyncDefaultAzureCredential)

    @pytest.mark.spec("ASYNC-001")
    def test_missing_identity_raises_backend_unavailable(self) -> None:
        """BackendUnavailable when azure-identity missing and no credential given."""
        import sys
        from unittest import mock

        with (
            mock.patch.dict(sys.modules, {"azure.identity": None, "azure.identity.aio": None}),
            pytest.raises(BackendUnavailable, match="azure-identity"),
        ):
            resolve_credential(None, None, None, is_async=False, backend_name="test")


# =============================================================================
# _azure_common: build_azure_retry (ASYNC-001)
# =============================================================================


class TestBuildAzureRetry:
    """build_azure_retry maps RetryPolicy to ExponentialRetry."""

    @pytest.mark.spec("ASYNC-001")
    def test_none_returns_none(self) -> None:
        assert build_azure_retry(None) is None

    @pytest.mark.spec("ASYNC-001")
    def test_default_retry_policy(self) -> None:
        from remote_store._config import RetryPolicy

        retry = build_azure_retry(RetryPolicy())
        assert retry is not None
        assert retry.total_retries == 2  # max_attempts(3) - 1

    @pytest.mark.spec("ASYNC-001")
    def test_custom_retry_policy(self) -> None:
        from remote_store._config import RetryPolicy

        rp = RetryPolicy(max_attempts=5, backoff_base=2.0, jitter=0.5)
        retry = build_azure_retry(rp)
        assert retry is not None
        assert retry.total_retries == 4  # 5 - 1
        assert retry.initial_backoff == 2
        assert retry.random_jitter_range == 0

    @pytest.mark.spec("ASYNC-001")
    def test_unmappable_fields_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """backoff_max != 60 or timeout != None triggers a debug log."""

        from remote_store._config import RetryPolicy

        rp = RetryPolicy(backoff_max=30.0, timeout=120.0)
        with caplog.at_level(logging.DEBUG, logger="remote_store.backends._azure_common"):
            retry = build_azure_retry(rp)
        assert retry is not None
        assert "not mappable" in caplog.text


# =============================================================================
# _azure_common: validate_azure_params (ASYNC-001)
# =============================================================================


class TestValidateAzureParams:
    """validate_azure_params raises ValueError on invalid input."""

    @pytest.mark.spec("ASYNC-001")
    def test_account_url_accepted(self) -> None:
        result = validate_azure_params(
            container="c",
            account_name=None,
            account_url="https://x.blob.core.windows.net",
            connection_string=None,
            max_concurrency=1,
            hns=False,
        )
        assert result is None

    @pytest.mark.spec("ASYNC-001")
    def test_connection_string_accepted(self) -> None:
        result = validate_azure_params(
            container="c",
            account_name=None,
            account_url=None,
            connection_string="DefaultEndpointsProtocol=http;AccountName=x",
            max_concurrency=1,
            hns=False,
        )
        assert result is None

    @pytest.mark.spec("ASYNC-001")
    def test_no_auth_raises(self) -> None:
        with pytest.raises(ValueError, match="account_name"):
            validate_azure_params(
                container="c",
                account_name=None,
                account_url=None,
                connection_string=None,
                max_concurrency=1,
                hns=False,
            )

    @pytest.mark.spec("ASYNC-004")
    def test_hns_none_raises(self) -> None:
        with pytest.raises(ValueError, match="hns must be declared explicitly"):
            validate_azure_params(
                container="c",
                account_name=None,
                account_url=None,
                connection_string="DefaultEndpointsProtocol=http;AccountName=x",
                max_concurrency=1,
                hns=None,
            )


# =============================================================================
# AsyncAzureBackend: error mapping in list/glob operations (ASYNC-024)
# =============================================================================


class TestAsyncAzureErrorPropagation:
    """RemoteStoreError re-raised untouched in list/glob/iter_children."""

    @pytest.mark.spec("ASYNC-024")
    async def test_list_folders_error_mapped(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.walk_blobs.side_effect = ServiceRequestError("timeout")

        with pytest.raises(BackendUnavailable, match="timeout"):
            async for _ in backend.list_folders("data"):
                pass

    @pytest.mark.spec("ASYNC-024")
    async def test_iter_children_error_mapped(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.walk_blobs.side_effect = ResourceNotFoundError("not here")

        with pytest.raises(NotFound):
            async for _ in backend.iter_children("missing"):
                pass

    @pytest.mark.spec("ASYNC-024")
    async def test_list_files_remote_store_error_passthrough(self) -> None:
        """RemoteStoreError raised during list_files passes through unchanged."""
        backend, cc, bc = _setup_non_hns_backend()
        cc.walk_blobs.side_effect = NotFound("custom not found", path="x", backend="async-azure")

        with pytest.raises(NotFound, match="custom not found"):
            async for _ in backend.list_files("data"):
                pass

    @pytest.mark.spec("ASYNC-024")
    async def test_list_folders_remote_store_error_passthrough(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.walk_blobs.side_effect = PermissionDenied("denied", path="x", backend="async-azure")

        with pytest.raises(PermissionDenied, match="denied"):
            async for _ in backend.list_folders("data"):
                pass

    @pytest.mark.spec("ASYNC-024")
    async def test_iter_children_remote_store_error_passthrough(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.walk_blobs.side_effect = AlreadyExists("exists", path="x", backend="async-azure")

        with pytest.raises(AlreadyExists, match="exists"):
            async for _ in backend.iter_children("data"):
                pass


# =============================================================================
# AsyncAzureBackend: read_file error mapping (ASYNC-024)
# =============================================================================


class TestAsyncAzureReadErrors:
    """Error mapping in read_file and read_bytes."""

    @pytest.mark.spec("ASYNC-024")
    async def test_read_file_remote_store_error_passthrough(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.download_blob = AsyncMock(
            side_effect=NotFound("custom", path="x.txt", backend="async-azure"),
        )

        with pytest.raises(NotFound, match="custom"):
            async for _ in backend.read("x.txt"):
                pass

    @pytest.mark.spec("ASYNC-024")
    async def test_read_file_native_error_mapped(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.download_blob = AsyncMock(side_effect=ResourceNotFoundError("nope"))

        with pytest.raises(NotFound):
            async for _ in backend.read("missing.txt"):
                pass


# =============================================================================
# AsyncAzureBackend: write_atomic with async iterator (ASYNC-007)
# =============================================================================


class TestAsyncAzureWriteAtomicIterator:
    """write_atomic passes async iterator content through (BUG-165)."""

    @pytest.mark.spec("ASYNC-007", "ASYNC-021")
    async def test_write_atomic_streams_async_chunks(self) -> None:
        """write_atomic forwards the async iterator to upload_blob without
        materializing (non-HNS path). See BUG-165."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        captured: list[bytes] = []

        async def _fake_upload(data, **_kwargs):  # noqa: ANN001, ANN202
            async for chunk in data:
                captured.append(chunk)

        bc.upload_blob = AsyncMock(side_effect=_fake_upload)

        async def chunk_gen():
            yield b"hello "
            yield b"world"

        agen = chunk_gen()
        await backend.write_atomic("file.txt", agen, overwrite=True)
        bc.upload_blob.assert_awaited_once()
        assert captured == [b"hello ", b"world"]


# =============================================================================
# AsyncAzureBackend: close credential (ASYNC-001)
# =============================================================================


class TestAsyncAzureCloseCredential:
    """aclose() cleans up credential resources."""

    @pytest.mark.spec("ASYNC-001")
    @pytest.mark.spec("ASYNC-078")
    async def test_close_closes_credential(self) -> None:
        backend = _make_backend()
        mock_cred = MagicMock(spec=["close"])
        mock_cred.close = AsyncMock()
        backend._resolved_credential = mock_cred

        await backend.aclose()
        mock_cred.close.assert_awaited_once()
        assert backend._resolved_credential is None  # internal: no public observable

    @pytest.mark.spec("ASYNC-001")
    async def test_close_without_credential(self) -> None:
        """aclose() when no credential was resolved does not raise."""
        backend = _make_backend()
        await backend.aclose()
        assert backend._resolved_credential is None  # internal: no public observable


# =============================================================================
# __del__ cleanup contract (BK-143)
# =============================================================================


class TestAsyncAzureDelCleanup:
    """BK-143 (Error): AsyncAzureBackend.__del__ emits ResourceWarning."""

    @pytest.mark.spec("BK-143")
    @pytest.mark.parametrize(
        ("attr", "spec_cls"),
        [
            ("_cc_instance", ContainerClient),
            ("_blob_service_instance", BlobServiceClient),
            ("_fs_instance", FileSystemClient),
            ("_datalake_service_instance", DataLakeServiceClient),
        ],
    )
    def test_del_emits_resource_warning_for_each_client(self, attr: str, spec_cls: type) -> None:
        """__del__ emits ResourceWarning whichever client attr is open."""
        backend = _make_backend()
        setattr(backend, attr, MagicMock(spec=spec_cls))  # internal: no public observable
        with pytest.warns(ResourceWarning, match="Unclosed AsyncAzureBackend"):
            backend.__del__()

    @pytest.mark.spec("BK-143")
    def test_del_is_safe_when_no_clients(self) -> None:
        """__del__ does not raise or warn when no clients have been opened."""
        backend = _make_backend()
        assert backend.__del__() is None


# =============================================================================
# HNS directory path guard — write / write_atomic (ASYNC-008, ASYNC-010, ASYNC-024)
# =============================================================================


def _setup_hns_write_backend_async() -> tuple[AsyncAzureBackend, AsyncMock, AsyncMock]:
    """Return (backend, container_client, blob_client) with HNS enabled."""
    backend = _make_backend()
    backend._hns = True
    cc = AsyncMock(spec=ContainerClient)
    backend._cc_instance = cc
    bc = AsyncMock(spec=BlobClient)
    cc.get_blob_client.return_value = bc
    backend._blob_service_instance = AsyncMock(spec=BlobServiceClient)
    fs = AsyncMock(spec=FileSystemClient)
    backend._fs_instance = fs
    return backend, cc, bc


class TestAsyncAzureWriteOnHnsDirectory:
    """ASYNC-024: write/write_atomic on an HNS directory path must raise InvalidPath."""

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.spec("ASYNC-008")
    @pytest.mark.parametrize("overwrite", [False, True])
    async def test_write_raises_invalid_path_on_hns_dir(self, overwrite: bool) -> None:
        backend, _cc, bc = _setup_hns_write_backend_async()
        bc.get_blob_properties.return_value = _mock_blob_props(metadata={"hdi_isfolder": "true"})
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await backend.write("mydir", b"data", overwrite=overwrite)

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.spec("ASYNC-010")
    @pytest.mark.parametrize("overwrite", [False, True])
    async def test_write_atomic_raises_invalid_path_on_hns_dir(self, overwrite: bool) -> None:
        backend, _cc, bc = _setup_hns_write_backend_async()
        bc.get_blob_properties.return_value = _mock_blob_props(metadata={"hdi_isfolder": "true"})
        with pytest.raises(InvalidPath, match="exists as a directory"):
            await backend.write_atomic("mydir", b"data", overwrite=overwrite)

    @pytest.mark.spec("ASYNC-008")
    async def test_write_regular_file_not_affected(self) -> None:
        """A normal (non-dir) blob at the path should still raise AlreadyExists."""
        backend, _cc, bc = _setup_hns_write_backend_async()
        bc.get_blob_properties.return_value = _mock_blob_props(metadata={})
        with pytest.raises(AlreadyExists, match="already exists|Already exists"):
            await backend.write("file.txt", b"data")

    @pytest.mark.spec("ASYNC-008")
    async def test_write_path_not_found_proceeds(self) -> None:
        """When the blob doesn't exist (ResourceNotFoundError), write should not raise."""
        backend, _cc, bc = _setup_hns_write_backend_async()
        bc.get_blob_properties.side_effect = ResourceNotFoundError("not found")
        bc.upload_blob.return_value = {"etag": '"abc"', "last_modified": None, "version_id": None, "content_md5": None}
        result = await backend.write("new.txt", b"data")
        assert result is not None

    @pytest.mark.spec("ASYNC-010")
    async def test_write_atomic_path_not_found_proceeds(self) -> None:
        """When the blob doesn't exist, write_atomic should not raise — proceed to temp+rename."""
        backend, _cc, bc = _setup_hns_write_backend_async()
        bc.get_blob_properties.side_effect = ResourceNotFoundError("not found")
        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        tmp_fc.upload_data.return_value = None
        final_fc = AsyncMock(spec=DataLakeFileClient)
        final_fc.get_file_properties = AsyncMock(return_value={})
        tmp_fc.rename_file.return_value = final_fc
        backend._fs_instance.get_file_client.return_value = tmp_fc
        result = await backend.write_atomic("new.txt", b"data")
        assert result is not None
        tmp_fc.upload_data.assert_awaited_once()
        tmp_fc.rename_file.assert_awaited_once_with("test/new.txt")
