"""Tests for AsyncAzureBackend -- covers ASYNC-xxx spec items for Azure.

Requires: azure-storage-file-datalake, azure-identity (test dependencies).
All tests use mocked SDK objects since there is no in-process Azure emulator
for async operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

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
from azure.storage.filedatalake import PathProperties  # noqa: E402
from azure.storage.filedatalake.aio import (  # noqa: E402
    DataLakeDirectoryClient,
    DataLakeFileClient,
    DataLakeServiceClient,
    FileSystemClient,
)

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store._errors import (  # noqa: E402
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderEntry, FolderInfo  # noqa: E402
from remote_store.aio._async_azure import AsyncAzureBackend  # noqa: E402
from remote_store.backends._azure_common import classify_azure_error  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_backend(**kw: Any) -> AsyncAzureBackend:
    """Shorthand for creating an AsyncAzureBackend with sensible test defaults."""
    defaults: dict[str, Any] = {"container": "test", "account_name": "x", "account_key": "fakekey"}
    defaults.update(kw)
    return AsyncAzureBackend(**defaults)


async def _async_iter(items: list[Any]):  # noqa: ANN201 -- async generator
    """Yield items from a list as an async iterator."""
    for item in items:
        yield item


def _mock_blob_props(
    *,
    size: int = 100,
    etag: str = '"0x8D4BCC2E4835CD0"',
    md5: bytes | None = None,
    metadata: dict[str, str] | None = None,
) -> MagicMock:
    """Create a mock BlobProperties-like object."""
    props = MagicMock(spec=BlobProperties)
    props.size = size
    props.content_length = size
    props.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
    props.etag = etag
    cs = MagicMock(spec=ContentSettings)
    cs.content_md5 = md5
    props.content_settings = cs
    props.metadata = metadata or {}
    return props


def _setup_non_hns_backend() -> tuple[AsyncAzureBackend, AsyncMock, AsyncMock]:
    """Create a non-HNS backend with mocked blob and container clients.

    Returns:
        Tuple of (backend, container_client_mock, blob_client_mock).
    """
    backend = _make_backend()
    backend._hns_enabled = False
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
    def test_capabilities_include_all_except_seekable_read(self) -> None:
        caps = _make_backend().capabilities
        assert isinstance(caps, CapabilitySet)
        for cap in Capability:
            if cap is Capability.SEEKABLE_READ:
                assert not caps.supports(cap), "async-azure must not declare SEEKABLE_READ"
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
            AsyncAzureBackend(container=container, account_name="x")

    @pytest.mark.spec("ASYNC-001")
    def test_validation_no_account(self) -> None:
        with pytest.raises(ValueError, match="account_name"):
            AsyncAzureBackend(container="test")

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
    def test_lazy_connection(self) -> None:
        """Construction must not make network calls."""
        backend = _make_backend(container="any-container", account_name="nonexistent")
        assert backend.name == "async-azure"


# =============================================================================
# HNS Detection (ASYNC-004, ASYNC-005)
# =============================================================================


class TestAsyncAzureHNSDetection:
    """HNS detection with mocked async SDK."""

    @pytest.mark.spec("ASYNC-004")
    @pytest.mark.parametrize(
        ("ret", "side_eff", "expected"),
        [
            pytest.param({"is_hns_enabled": True}, None, True, id="hns-enabled"),
            pytest.param({"is_hns_enabled": False}, None, False, id="hns-disabled"),
            pytest.param(None, Exception("network error"), False, id="detection-failure-fallback"),
        ],
    )
    async def test_hns_detection(self, ret: Any, side_eff: Any, expected: bool) -> None:
        backend = _make_backend()
        mock_client = AsyncMock(spec=BlobServiceClient)
        if side_eff is not None:
            mock_client.get_account_information.side_effect = side_eff
        else:
            mock_client.get_account_information.return_value = ret
        backend._blob_service_instance = mock_client
        result = await backend._ensure_hns()
        assert result is expected

    @pytest.mark.spec("ASYNC-005")
    async def test_hns_result_cached(self) -> None:
        backend = _make_backend()
        mock_client = AsyncMock(spec=BlobServiceClient)
        mock_client.get_account_information.return_value = {"is_hns_enabled": True}
        backend._blob_service_instance = mock_client
        first = await backend._ensure_hns()
        second = await backend._ensure_hns()
        assert mock_client.get_account_information.call_count == 1
        assert first is second is True


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
    def test_classify_direct(self, exc_factory: Any, expected_type: type) -> None:
        mapped = classify_azure_error(exc_factory(), "file.txt", "async-azure")
        assert isinstance(mapped, expected_type)

    @pytest.mark.spec("ASYNC-024")
    @pytest.mark.parametrize(
        ("status", "expected_type"),
        [
            pytest.param(404, NotFound, id="http-404"),
            pytest.param(403, PermissionDenied, id="http-403"),
            pytest.param(409, AlreadyExists, id="http-409"),
            pytest.param(500, RemoteStoreError, id="http-500-generic"),
        ],
    )
    def test_classify_http_status(self, status: int, expected_type: type) -> None:
        mapped = classify_azure_error(_http_err("msg", status), "file.txt", "async-azure")
        assert isinstance(mapped, expected_type)

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

    @pytest.mark.spec("ASYNC-008")
    async def test_write_async_iterator(self) -> None:
        """Async iterator content is materialized before upload."""
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        bc.upload_blob = AsyncMock()

        async def gen():  # noqa: ANN202
            yield b"hello "
            yield b"world"

        await backend.write("file.txt", gen())
        assert bc.upload_blob.call_count == 1

    @pytest.mark.spec("ASYNC-008")
    async def test_write_already_exists(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())

        with pytest.raises(AlreadyExists, match="already exists|Already exists"):
            await backend.write("file.txt", b"data")

    @pytest.mark.spec("ASYNC-008")
    async def test_write_overwrite(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        bc.upload_blob = AsyncMock()

        await backend.write("file.txt", b"data", overwrite=True)
        assert bc.upload_blob.call_count == 1

    @pytest.mark.spec("ASYNC-020")
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


# =============================================================================
# List Operations (ASYNC-014, ASYNC-015, ASYNC-029)
# =============================================================================


class TestAsyncAzureListOperations:
    """ASYNC-014/015/029: list_files, list_folders, iter_children."""

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_non_recursive(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        blob_file = MagicMock(spec=BlobProperties)
        blob_file.name = "file.txt"
        blob_file.size = 42
        blob_file.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blob_file.etag = '"abc"'
        blob_file.content_settings = MagicMock(spec=ContentSettings)
        blob_file.content_settings.content_md5 = None
        blob_file.metadata = {}
        blob_file.prefix = None  # not a virtual directory

        cc.walk_blobs.return_value = _async_iter([blob_file])

        files = [f async for f in backend.list_files("")]
        assert len(files) == 1
        assert files[0].name == "file.txt"
        assert isinstance(files[0], FileInfo)

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_recursive(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        blob1 = MagicMock(spec=BlobProperties)
        blob1.name = "file.txt"
        blob1.size = 10
        blob1.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blob1.etag = '"a"'
        blob1.content_settings = MagicMock(spec=ContentSettings)
        blob1.content_settings.content_md5 = None
        blob1.metadata = {}

        blob2 = MagicMock(spec=BlobProperties)
        blob2.name = "sub/deep.txt"
        blob2.size = 20
        blob2.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blob2.etag = '"b"'
        blob2.content_settings = MagicMock(spec=ContentSettings)
        blob2.content_settings.content_md5 = None
        blob2.metadata = {}

        cc.list_blobs.return_value = _async_iter([blob1, blob2])

        files = [f async for f in backend.list_files("", recursive=True)]
        assert len(files) == 2
        names = {f.name for f in files}
        assert names == {"file.txt", "deep.txt"}

    @pytest.mark.spec("ASYNC-015")
    async def test_list_folders(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        folder_item = MagicMock(spec=BlobProperties)
        folder_item.prefix = "test/sub1/"
        folder_item.name = "test/sub1/"

        cc.walk_blobs.return_value = _async_iter([folder_item])

        folders = [f async for f in backend.list_folders("")]
        assert len(folders) == 1
        assert isinstance(folders[0], FolderEntry)
        assert folders[0].name == "sub1"

    @pytest.mark.spec("ASYNC-029")
    async def test_iter_children(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        # A file item
        blob_file = MagicMock(spec=BlobProperties)
        blob_file.name = "file.txt"
        blob_file.size = 42
        blob_file.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blob_file.etag = '"abc"'
        blob_file.content_settings = MagicMock(spec=ContentSettings)
        blob_file.content_settings.content_md5 = None
        blob_file.metadata = {}
        blob_file.prefix = None

        # A folder item (virtual prefix)
        folder_item = MagicMock(spec=BlobProperties)
        folder_item.prefix = "test/sub/"
        folder_item.name = "test/sub/"

        cc.walk_blobs.return_value = _async_iter([blob_file, folder_item])

        children = [c async for c in backend.iter_children("")]
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert len(files) == 1
        assert files[0].name == "file.txt"
        assert len(folders) == 1
        assert folders[0].name == "sub"

    @pytest.mark.spec("ASYNC-014")
    async def test_list_files_empty(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.walk_blobs.return_value = _async_iter([])

        files = [f async for f in backend.list_files("nonexistent")]
        assert files == []


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
        dst_bc.start_copy_from_url = AsyncMock()

        cc.get_blob_client.side_effect = [src_bc, dst_bc]

        await backend.move("src.txt", "dst.txt", overwrite=True)
        assert dst_bc.start_copy_from_url.call_count == 1
        assert src_bc.delete_blob.call_count == 1

    @pytest.mark.spec("ASYNC-019")
    async def test_copy_overwrite(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()

        src_bc = AsyncMock(spec=BlobClient)
        src_bc.get_blob_properties = AsyncMock(return_value=_mock_blob_props())
        src_bc.url = "https://x.blob.core.windows.net/test/src.txt"

        dst_bc = AsyncMock(spec=BlobClient)
        dst_bc.start_copy_from_url = AsyncMock()

        cc.get_blob_client.side_effect = [src_bc, dst_bc]

        await backend.copy("src.txt", "dst.txt", overwrite=True)
        assert dst_bc.start_copy_from_url.call_count == 1


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
        assert isinstance(info, FileInfo)
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

        blob1 = MagicMock(spec=BlobProperties)
        blob1.size = 10
        blob1.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blob2 = MagicMock(spec=BlobProperties)
        blob2.size = 20
        blob2.last_modified = datetime(2024, 6, 1, tzinfo=timezone.utc)

        cc.list_blobs.return_value = _async_iter([blob1, blob2])

        info = await backend.get_folder_info("dir")
        assert isinstance(info, FolderInfo)
        assert info.file_count == 2
        assert info.total_size == 30

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

    @pytest.mark.spec("ASYNC-027")
    def test_resolve(self) -> None:
        backend = _make_backend()
        plan = backend.resolve("file.txt")
        assert plan.kind == "async-azure"
        assert plan.backend == "async-azure"
        assert plan.key == "file.txt"
        assert plan.native_path == "test/file.txt"
        assert "container" in plan.details
        assert plan.details["container"] == "test"

    @pytest.mark.spec("ASYNC-027")
    def test_resolve_has_account_url(self) -> None:
        backend = _make_backend()
        plan = backend.resolve("file.txt")
        assert "account_url" in plan.details


# =============================================================================
# Check Health
# =============================================================================


class TestAsyncAzureCheckHealth:
    """check_health exercises _errors() and container properties."""

    @pytest.mark.spec("ASYNC-024")
    async def test_check_health_non_hns(self) -> None:
        backend, cc, bc = _setup_non_hns_backend()
        cc.get_container_properties = AsyncMock(return_value={"name": "test"})
        await backend.check_health()
        assert cc.get_container_properties.call_count == 1

    @pytest.mark.spec("ASYNC-024")
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
        backend._hns_enabled = True
        backend._blob_service_instance = AsyncMock(spec=BlobServiceClient)
        backend._cc_instance = AsyncMock(spec=ContainerClient)
        backend._datalake_service_instance = AsyncMock(spec=DataLakeServiceClient)
        backend._fs_instance = AsyncMock(spec=FileSystemClient)
        return backend

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

    @pytest.mark.spec("ASYNC-020")
    async def test_write_atomic_hns_uses_temp_and_rename(self) -> None:
        backend = self._make_hns_backend()
        bc = AsyncMock(spec=BlobClient)
        bc.get_blob_properties = AsyncMock(side_effect=ResourceNotFoundError("nope"))
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = AsyncMock(spec=DataLakeFileClient)
        backend._fs_instance.get_file_client.return_value = tmp_fc

        await backend.write_atomic("dir/file.txt", b"content")
        assert tmp_fc.upload_data.call_count == 1
        assert tmp_fc.rename_file.call_count == 1

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_hns_recursive(self) -> None:
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        backend._fs_instance.get_directory_client.return_value = dc

        await backend.delete_folder("my-dir", recursive=True)
        assert dc.delete_directory.call_count == 1

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_hns_non_recursive_empty(self) -> None:
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        backend._fs_instance.get_directory_client.return_value = dc
        backend._fs_instance.get_paths.return_value = _async_iter([])

        await backend.delete_folder("my-dir", recursive=False)
        assert dc.delete_directory.call_count == 1

    @pytest.mark.spec("ASYNC-013")
    async def test_delete_folder_hns_non_recursive_non_empty_raises(self) -> None:
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        backend._fs_instance.get_directory_client.return_value = dc

        child = MagicMock(spec=PathProperties)
        backend._fs_instance.get_paths.return_value = _async_iter([child])

        with pytest.raises(DirectoryNotEmpty, match="not empty|Folder not empty"):
            await backend.delete_folder("my-dir", recursive=False)

    @pytest.mark.spec("ASYNC-005")
    async def test_is_folder_hns_uses_directory_client(self) -> None:
        backend = self._make_hns_backend()
        dc = AsyncMock(spec=DataLakeDirectoryClient)
        backend._fs_instance.get_directory_client.return_value = dc

        assert await backend.is_folder("my-dir") is True
        assert dc.get_directory_properties.call_count == 1


# =============================================================================
# Max Concurrency (ASYNC-033)
# =============================================================================


class TestAsyncAzureMaxConcurrency:
    """max_concurrency kwarg reaches SDK upload/download call sites."""

    @pytest.mark.spec("ASYNC-008")
    async def test_max_concurrency_threaded_to_upload(self) -> None:
        backend = _make_backend(max_concurrency=4)
        backend._hns_enabled = False
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
        backend._hns_enabled = False
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
