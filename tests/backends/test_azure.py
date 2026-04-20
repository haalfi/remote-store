"""Azure backend tests -- covers AZ-xxx spec items.

Requires: azure-storage-file-datalake, azure-identity (test dependencies).
Backend-specific tests run against Azurite when available; construction and
error-mapping tests use mocked SDK objects.
"""

from __future__ import annotations

import contextlib
import io
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from azure.storage.blob import (  # noqa: E402
    BlobClient,
    BlobProperties,
    BlobServiceClient,
    ContainerClient,
    ContentSettings,
    StorageStreamDownloader,
)
from azure.storage.filedatalake import (  # noqa: E402
    DataLakeDirectoryClient,
    DataLakeFileClient,
    DataLakeServiceClient,
    FileSystemClient,
    PathProperties,
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
from remote_store._models import FileInfo, FolderInfo, WriteResult  # noqa: E402
from remote_store.backends._azure import AzureBackend, _AzureBinaryIO  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


# Tracker so an autouse fixture can close() every backend made in a test —
# without close, AzureBackend.__del__ emits a ResourceWarning at GC time.
_BACKENDS: list[AzureBackend] = []


def _make_backend(**kw: Any) -> AzureBackend:
    """Shorthand for creating an AzureBackend with sensible test defaults."""
    defaults: dict[str, Any] = {"container": "test", "account_name": "x", "account_key": "fakekey"}
    defaults.update(kw)
    backend = AzureBackend(**defaults)
    _BACKENDS.append(backend)
    return backend


@pytest.fixture(autouse=True)
def _close_tracked_backends() -> Iterator[None]:
    yield
    while _BACKENDS:
        backend = _BACKENDS.pop()
        with contextlib.suppress(Exception):
            backend.close()


# -- Shared Azurite helpers (imported from conftest where possible) -----------


def _azurite_reachable() -> bool:
    import socket

    try:
        s = socket.create_connection(("127.0.0.1", 10000), timeout=1)
        s.close()
        return True
    except OSError:
        return False


# Re-use the connection string from conftest
from tests.backends.conftest import _AZURITE_CONN_STR  # noqa: E402


def _needs_azurite(func_or_class):  # type: ignore[no-untyped-def]
    """Apply both requires_docker marker and Azurite-reachability skip."""
    decorated = pytest.mark.requires_docker(func_or_class)
    decorated = pytest.mark.skipif(
        not _azurite_reachable(),
        reason="Azurite not reachable at 127.0.0.1:10000",
    )(decorated)
    return decorated


@pytest.fixture
def azure_backend() -> Iterator[Backend]:
    """Create an AzureBackend against Azurite."""
    if not _azurite_reachable():
        pytest.skip("Azurite not reachable")

    container = f"test-az-{uuid.uuid4().hex[:8]}"
    service = BlobServiceClient.from_connection_string(_AZURITE_CONN_STR)
    try:
        service.create_container(container)
    except Exception:
        service.close()
        raise

    backend = AzureBackend(container=container, connection_string=_AZURITE_CONN_STR)
    yield backend

    backend.close()
    service.delete_container(container)
    service.close()


# =============================================================================
# _AzureBinaryIO unit tests
# =============================================================================


class TestAzureBinaryIO:
    """Unit tests for the streaming adapter."""

    def test_empty_iterator(self) -> None:
        stream = _AzureBinaryIO(iter([]))
        wrapped = io.BufferedReader(stream)
        assert wrapped.read() == b""

    def test_read_exact_chunk(self) -> None:
        stream = _AzureBinaryIO(iter([b"hello"]))
        wrapped = io.BufferedReader(stream)
        assert wrapped.read(5) == b"hello"

    def test_read_less_than_chunk(self) -> None:
        stream = _AzureBinaryIO(iter([b"hello world"]))
        wrapped = io.BufferedReader(stream)
        assert wrapped.read(5) == b"hello"
        assert wrapped.read(6) == b" world"

    def test_read_more_than_chunk(self) -> None:
        stream = _AzureBinaryIO(iter([b"ab", b"cd", b"ef"]))
        wrapped = io.BufferedReader(stream)
        assert wrapped.read(4) == b"abcd"
        assert wrapped.read(2) == b"ef"

    def test_read_all(self) -> None:
        stream = _AzureBinaryIO(iter([b"chunk1", b"chunk2"]))
        wrapped = io.BufferedReader(stream)
        assert wrapped.read() == b"chunk1chunk2"

    def test_readable(self) -> None:
        stream = _AzureBinaryIO(iter([]))
        assert stream.readable() is True

    def test_close_then_read(self) -> None:
        stream = _AzureBinaryIO(iter([b"data"]))
        stream.close()
        assert stream.closed

    def test_close_idempotent(self) -> None:
        stream = _AzureBinaryIO(iter([b"data"]))
        stream.close()
        stream.close()
        assert stream.closed

    def test_exact_boundary_reads(self) -> None:
        """Read exactly at chunk boundaries."""
        stream = _AzureBinaryIO(iter([b"aaa", b"bbb", b"ccc"]))
        wrapped = io.BufferedReader(stream)
        assert wrapped.read(3) == b"aaa"
        assert wrapped.read(3) == b"bbb"
        assert wrapped.read(3) == b"ccc"
        assert wrapped.read(1) == b""


# =============================================================================
# Construction (AZ-001, AZ-005)
# =============================================================================


class TestAzureConstruction:
    """AZ-001, AZ-005: construction and validation."""

    @pytest.mark.spec("AZ-001")
    def test_constructor_with_connection_string(self) -> None:
        backend = _make_backend(account_key=None, connection_string="DefaultEndpointsProtocol=http;AccountName=x")
        assert backend is not None

    @pytest.mark.spec("AZ-001")
    def test_constructor_with_account_name(self) -> None:
        backend = _make_backend(account_key=None, account_name="myaccount")
        assert backend is not None

    @pytest.mark.spec("AZ-001")
    def test_constructor_with_account_url(self) -> None:
        backend = _make_backend(
            account_key=None, account_name=None, account_url="https://myaccount.dfs.core.windows.net"
        )
        assert backend is not None

    @pytest.mark.spec("AZ-002")
    def test_name_is_azure(self) -> None:
        assert _make_backend().name == "azure"

    @pytest.mark.spec("AZ-003")
    def test_declares_all_capabilities(self) -> None:
        caps = _make_backend().capabilities
        assert isinstance(caps, CapabilitySet)
        for cap in Capability:
            if cap is Capability.SEEKABLE_READ:
                assert not caps.supports(cap), "Azure must not declare SEEKABLE_READ"
            elif cap is Capability.ATOMIC_MOVE:
                assert not caps.supports(cap), "Azure must not declare ATOMIC_MOVE (copy-then-delete on non-HNS)"
            else:
                assert caps.supports(cap), f"Missing capability: {cap.value}"

    @pytest.mark.spec("AZ-004")
    def test_lazy_connection(self) -> None:
        """Construction must not make network calls."""
        backend = _make_backend(container="any-container", account_name="nonexistent")
        assert backend.name == "azure"

    @pytest.mark.spec("AZ-005")
    @pytest.mark.parametrize(
        "container",
        [
            pytest.param("", id="empty"),
            pytest.param("   ", id="whitespace"),
        ],
    )
    def test_invalid_container_raises(self, container: str) -> None:
        with pytest.raises(ValueError, match="container"):
            AzureBackend(container=container, account_name="x")

    @pytest.mark.spec("AZ-005")
    def test_no_connection_info_raises(self) -> None:
        with pytest.raises(ValueError, match="account_name"):
            AzureBackend(container="test")

    @pytest.mark.spec("AZ-033")
    def test_max_concurrency_default(self) -> None:
        assert _make_backend()._max_concurrency == 1

    @pytest.mark.spec("AZ-033")
    def test_max_concurrency_custom(self) -> None:
        assert _make_backend(max_concurrency=4)._max_concurrency == 4

    @pytest.mark.spec("AZ-033")
    @pytest.mark.parametrize(
        "val",
        [
            pytest.param(0, id="zero"),
            pytest.param(-1, id="negative"),
        ],
    )
    def test_max_concurrency_invalid_raises(self, val: int) -> None:
        with pytest.raises(ValueError, match="max_concurrency"):
            _make_backend(max_concurrency=val)


# =============================================================================
# Path normalization (AZ-011)
# =============================================================================


class TestAzurePathNormalization:
    """AZ-011: path normalization."""

    @pytest.mark.spec("AZ-011")
    @pytest.mark.parametrize(
        ("inp", "expected"),
        [
            pytest.param("/a/b/c.txt", "a/b/c.txt", id="strips-leading-slash"),
            pytest.param("a//b///c.txt", "a/b/c.txt", id="collapses-double-separators"),
            pytest.param("//a//b/c.txt", "a/b/c.txt", id="combined"),
            pytest.param("", "", id="empty-string"),
        ],
    )
    def test_path_normalization(self, inp: str, expected: str) -> None:
        backend = _make_backend()
        assert backend._azure_path(inp) == expected


# =============================================================================
# HNS Detection (AZ-006)
# =============================================================================


class TestAzureHNSDetection:
    """AZ-006: HNS detection with mocked SDK."""

    @pytest.mark.spec("AZ-006")
    @pytest.mark.parametrize(
        ("ret", "side_eff", "expected"),
        [
            pytest.param({"is_hns_enabled": True}, None, True, id="hns-enabled"),
            pytest.param({"is_hns_enabled": False}, None, False, id="hns-disabled"),
            pytest.param(None, Exception("network error"), False, id="detection-failure-fallback"),
        ],
    )
    def test_hns_detection(self, ret: Any, side_eff: Any, expected: bool) -> None:
        backend = _make_backend()
        mock_client = MagicMock(spec=BlobServiceClient)
        if side_eff is not None:
            mock_client.get_account_information.side_effect = side_eff
        else:
            mock_client.get_account_information.return_value = ret
        backend._blob_service_instance = mock_client
        assert backend._hns is expected

    @pytest.mark.spec("AZ-006")
    def test_hns_result_cached(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock(spec=BlobServiceClient)
        mock_client.get_account_information.return_value = {"is_hns_enabled": True}
        backend._blob_service_instance = mock_client
        first = backend._hns
        second = backend._hns
        mock_client.get_account_information.assert_called_once()
        assert first is second is True


# =============================================================================
# Error mapping (AZ-025 through AZ-028)
# =============================================================================


def _azure_exc(name: str, *args: object) -> Exception:
    """Create an azure.core.exceptions instance by class name."""
    mod = __import__("azure.core.exceptions", fromlist=[name])
    return getattr(mod, name)(*args)


class TestAzureErrorMapping:
    """AZ-025 through AZ-028: structured error classification."""

    @staticmethod
    def _http_err(msg: str, status: int) -> Exception:
        from azure.core.exceptions import HttpResponseError

        exc = HttpResponseError(msg)
        exc.status_code = status
        return exc

    @pytest.mark.spec("AZ-025")
    @pytest.mark.parametrize(
        ("exc_factory", "expected_type"),
        [
            pytest.param(lambda: _azure_exc("ResourceNotFoundError", "not found"), NotFound, id="resource-not-found"),
            pytest.param(lambda: _azure_exc("ResourceExistsError", "exists"), AlreadyExists, id="resource-exists"),
            pytest.param(
                lambda: _azure_exc("ClientAuthenticationError", "auth failed"), PermissionDenied, id="client-auth-error"
            ),
            pytest.param(
                lambda: _azure_exc("ServiceRequestError", "connection refused"),
                BackendUnavailable,
                id="service-request-error",
            ),
            pytest.param(
                lambda: _azure_exc("ServiceResponseError", "bad response"),
                BackendUnavailable,
                id="service-response-error",
            ),
            pytest.param(lambda: RuntimeError("unexpected"), RemoteStoreError, id="unknown-exception"),
        ],
    )
    def test_classify_direct(self, exc_factory: Any, expected_type: type) -> None:
        backend = _make_backend()
        mapped = backend._classify(exc_factory(), "file.txt")
        assert isinstance(mapped, expected_type)

    @pytest.mark.spec("AZ-025")
    @pytest.mark.parametrize(
        ("status", "expected_type"),
        [
            pytest.param(403, PermissionDenied, id="http-403"),
            pytest.param(404, NotFound, id="http-404"),
            pytest.param(409, AlreadyExists, id="http-409"),
            pytest.param(500, RemoteStoreError, id="http-500-generic"),
        ],
    )
    def test_classify_http_status(self, status: int, expected_type: type) -> None:
        backend = _make_backend()
        mapped = backend._classify(self._http_err("msg", status), "file.txt")
        assert isinstance(mapped, expected_type)

    @pytest.mark.spec("AZ-025")
    def test_resource_not_found_has_backend(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        backend = _make_backend()
        mapped = backend._classify(ResourceNotFoundError("not found"), "file.txt")
        assert mapped.backend == "azure"

    @pytest.mark.spec("AZ-025")
    def test_generic_http_excludes_subtypes(self) -> None:
        backend = _make_backend()
        mapped = backend._classify(self._http_err("server error", 500), "file.txt")
        assert not isinstance(mapped, NotFound | AlreadyExists | PermissionDenied)

    @pytest.mark.spec("AZ-025")
    @pytest.mark.spec("SEEK-006")
    def test_classify_unwraps_oserror_cause(self) -> None:
        """_classify unwraps OSError.__cause__ to match Azure exceptions from _AzureRangeReader."""
        from azure.core.exceptions import ResourceNotFoundError

        backend = _make_backend()
        # Simulate what _AzureRangeReader.readinto() does:
        # raise OSError(str(exc)) from exc
        azure_exc = ResourceNotFoundError("blob not found")
        wrapper = OSError(str(azure_exc))
        wrapper.__cause__ = azure_exc
        mapped = backend._classify(wrapper, "file.txt")
        assert isinstance(mapped, NotFound)

    @pytest.mark.spec("AZ-026")
    def test_no_native_exception_leaks(self) -> None:
        """The error context manager converts all exceptions."""
        from azure.core.exceptions import ResourceNotFoundError

        backend = _make_backend()
        with pytest.raises(RemoteStoreError), backend._errors("test"):
            raise ResourceNotFoundError("not found")

    @pytest.mark.spec("AZ-026")
    def test_error_has_backend_attribute(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        backend = _make_backend()
        with pytest.raises(RemoteStoreError) as exc_info, backend._errors("test"):
            raise ResourceNotFoundError("not found")
        assert exc_info.value.backend == "azure"

    @pytest.mark.spec("AZ-028")
    def test_remote_store_errors_pass_through(self) -> None:
        """RemoteStoreError raised inside _errors() passes through unchanged."""
        backend = _make_backend()
        with pytest.raises(NotFound, match="custom"), backend._errors("test"):
            raise NotFound("custom", path="test", backend="azure")


# =============================================================================
# Credential resolution (AZ-032)
# =============================================================================


class TestAzureCredentialResolution:
    """AZ-032: credential resolution paths."""

    _sentinel = object()

    @pytest.mark.spec("AZ-032")
    @pytest.mark.parametrize(
        ("kw", "expected"),
        [
            pytest.param({"account_key": "mykey"}, "mykey", id="account-key"),
            pytest.param({"account_key": None, "sas_token": "mysas"}, "mysas", id="sas-token"),
            pytest.param({"account_key": "key", "sas_token": "sas"}, "key", id="key-precedence-over-sas"),
        ],
    )
    def test_credential_resolution(self, kw: dict[str, Any], expected: str) -> None:
        backend = _make_backend(**kw)
        assert backend._resolve_credential() == expected

    @pytest.mark.spec("AZ-032")
    def test_explicit_credential_used(self) -> None:
        sentinel = object()
        backend = _make_backend(account_key=None, credential=sentinel)
        assert backend._resolve_credential() is sentinel


# =============================================================================
# to_key (AZ-027)
# =============================================================================


class TestAzureToKey:
    """AZ-027: to_key strips container prefix."""

    @pytest.mark.spec("AZ-027")
    @pytest.mark.parametrize(
        ("inp", "expected"),
        [
            pytest.param("my-container/data/file.txt", "data/file.txt", id="strips-container-prefix"),
            pytest.param("data/file.txt", "data/file.txt", id="no-prefix-unchanged"),
            pytest.param("", "", id="empty-string"),
        ],
    )
    def test_to_key(self, inp: str, expected: str) -> None:
        backend = _make_backend(container="my-container")
        assert backend.to_key(inp) == expected


# =============================================================================
# unwrap (AZ-030)
# =============================================================================


class TestAzureUnwrap:
    """AZ-030: unwrap returns FileSystemClient."""

    @pytest.mark.spec("AZ-030")
    def test_unwrap_wrong_type_raises(self) -> None:
        backend = _make_backend()
        with pytest.raises(CapabilityNotSupported):
            backend.unwrap(str)


# =============================================================================
# Lifecycle (AZ-029)
# =============================================================================


class TestAzureLifecycle:
    """AZ-029: close() behavior."""

    @pytest.mark.spec("AZ-029")
    def test_close_without_connection(self) -> None:
        """close() before any connection is safe."""
        backend = _make_backend()
        result = backend.close()
        assert result is None

    @pytest.mark.spec("AZ-029")
    def test_close_idempotent(self) -> None:
        backend = _make_backend()
        backend.close()
        result = backend.close()
        assert result is None

    @pytest.mark.spec("AZ-029")
    def test_close_closes_credential(self) -> None:
        """BUG-156: close() should close cached credential (DefaultAzureCredential)."""
        backend = _make_backend()
        mock_cred = MagicMock(spec=["close"])
        backend._resolved_credential = mock_cred

        backend.close()
        mock_cred.close.assert_called_once()
        assert backend._resolved_credential is None  # internal: no public observable

    @pytest.mark.spec("AZ-029")
    def test_close_credential_without_close_method(self) -> None:
        """BUG-156: close() handles credentials without a close() method."""
        backend = _make_backend()
        backend._resolved_credential = "just-a-key-string"

        backend.close()
        assert backend._resolved_credential is None  # internal: no public observable


# =============================================================================
# delete_folder performance (BUG-157)
# =============================================================================


class TestAzureDeleteFolderPerformance:
    """BUG-157: non-HNS delete_folder should not materialize all blobs for existence check."""

    @pytest.mark.spec("BE-021")
    def test_delete_folder_non_recursive_stops_after_first_blob(self) -> None:
        """Non-recursive delete_folder should stop iterating after finding one blob."""
        backend = _make_backend()
        backend._hns_enabled = False
        cc = MagicMock(spec=ContainerClient)
        backend._cc_instance = cc
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)

        # Create an iterator that tracks how many items were consumed
        consumed: list[Any] = []
        blob1 = MagicMock(spec=BlobProperties)
        blob1.name = "folder/a.txt"
        blob2 = MagicMock(spec=BlobProperties)
        blob2.name = "folder/b.txt"

        def tracking_iter():  # type: ignore[no-untyped-def]
            for b in [blob1, blob2]:
                consumed.append(b)
                yield b

        cc.list_blobs.return_value = tracking_iter()

        with pytest.raises(DirectoryNotEmpty, match="Folder not empty"):
            backend.delete_folder("folder", recursive=False)

        # Should have consumed only 1 blob, not all of them
        assert len(consumed) == 1


# =============================================================================
# read() resource safety (BUG-158)
# =============================================================================


class TestAzureReadResourceSafety:
    """BUG-158: read() should clean up raw stream if wrapping fails."""

    @pytest.mark.spec("BE-021")
    def test_read_closes_raw_stream_on_wrapper_failure(self) -> None:
        """If _ErrorMappingStream fails, the _AzureBinaryIO raw stream should be closed."""
        backend = _make_backend()
        backend._hns_enabled = False
        cc = MagicMock(spec=ContainerClient)
        backend._cc_instance = cc
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)

        bc = MagicMock(spec=BlobClient)
        cc.get_blob_client.return_value = bc

        downloader = MagicMock(spec=StorageStreamDownloader)
        downloader.chunks.return_value = iter([b"data"])
        bc.download_blob.return_value = downloader

        # Track whether _AzureBinaryIO.close() was called
        import remote_store.backends._azure as azure_mod

        original_stream = azure_mod._ErrorMappingStream
        created_raw: list[Any] = []
        original_init = _AzureBinaryIO.__init__

        def tracking_init(self_raw: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self_raw, *args, **kwargs)
            created_raw.append(self_raw)

        try:
            azure_mod._ErrorMappingStream = MagicMock(spec=type, side_effect=RuntimeError("wrapper failed"))
            _AzureBinaryIO.__init__ = tracking_init  # type: ignore[method-assign]
            # _errors() remaps RuntimeError to RemoteStoreError
            with pytest.raises(RemoteStoreError, match="wrapper failed"):
                backend.read("file.txt")
        finally:
            azure_mod._ErrorMappingStream = original_stream
            _AzureBinaryIO.__init__ = original_init  # type: ignore[method-assign]

        # Raw stream should have been created and then closed
        assert len(created_raw) == 1
        assert created_raw[0].closed


# =============================================================================
# HNS code path mock tests
# =============================================================================


class TestAzureHNSPaths:
    """Mock-based tests for HNS code paths that can't be tested with Azurite."""

    def _make_hns_backend(self) -> AzureBackend:
        """Create a backend with HNS enabled and mocked SDK clients."""
        backend = _make_backend()
        backend._hns_enabled = True
        # Mock blob service (still used for some operations)
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)
        backend._cc_instance = MagicMock(spec=ContainerClient)
        # Mock datalake service
        backend._datalake_service_instance = MagicMock(spec=DataLakeServiceClient)
        backend._fs_instance = MagicMock(spec=FileSystemClient)
        return backend

    def test_exists_checks_directory_on_hns(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        backend = self._make_hns_backend()
        # Blob doesn't exist
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("not found")
        backend._cc_instance.get_blob_client.return_value = bc
        # Directory exists
        dc = MagicMock(spec=DataLakeDirectoryClient)
        backend._fs_instance.get_directory_client.return_value = dc
        assert backend.exists("my-dir") is True
        dc.get_directory_properties.assert_called_once()

    def test_exists_returns_false_on_hns_when_missing(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("not found")
        backend._cc_instance.get_blob_client.return_value = bc
        dc = MagicMock(spec=DataLakeDirectoryClient)
        dc.get_directory_properties.side_effect = Exception("not found")
        backend._fs_instance.get_directory_client.return_value = dc
        assert backend.exists("missing") is False

    def test_is_folder_uses_directory_client_on_hns(self) -> None:
        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
        backend._fs_instance.get_directory_client.return_value = dc
        assert backend.is_folder("my-dir") is True
        dc.get_directory_properties.assert_called_once()

    def test_move_uses_rename_on_hns(self) -> None:
        backend = self._make_hns_backend()
        # src blob exists
        src_bc = MagicMock(spec=BlobClient)
        dst_bc = MagicMock(spec=BlobClient)
        from azure.core.exceptions import ResourceNotFoundError

        dst_bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")
        backend._cc_instance.get_blob_client.side_effect = [src_bc, dst_bc]
        # Mock the file client for rename
        fc = MagicMock(spec=DataLakeFileClient)
        backend._fs_instance.get_file_client.return_value = fc
        result = backend.move("src.txt", "dst.txt")
        fc.rename_file.assert_called_once_with("test/dst.txt")
        assert result is None

    def test_write_atomic_uses_temp_and_rename_on_hns(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        backend = self._make_hns_backend()
        backend._max_concurrency = 4
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")
        backend._cc_instance.get_blob_client.return_value = bc
        tmp_fc = MagicMock(spec=DataLakeFileClient)
        tmp_fc.upload_data.return_value = None  # production-accurate: upload_data returns None
        tmp_fc.get_file_properties.return_value = MagicMock(
            spec=["etag", "last_modified"],
            etag=None,
            last_modified=None,
        )
        backend._fs_instance.get_file_client.return_value = tmp_fc
        result = backend.write_atomic("dir/file.txt", b"content")
        tmp_fc.upload_data.assert_called_once_with(b"content", overwrite=True, max_concurrency=4, metadata=None)
        tmp_fc.rename_file.assert_called_once()
        assert isinstance(result, WriteResult)
        assert result.size == len(b"content")

    @pytest.mark.spec("WR-001a")
    def test_write_atomic_hns_populates_etag_from_file_properties(self) -> None:
        """HNS write_atomic must return a rich WriteResult populated from get_file_properties."""
        from azure.core.exceptions import ResourceNotFoundError

        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")
        backend._cc_instance.get_blob_client.return_value = bc
        tmp_fc = MagicMock(spec=DataLakeFileClient)
        tmp_fc.upload_data.return_value = None  # production-accurate: upload_data returns None
        tmp_fc.get_file_properties.return_value = MagicMock(
            spec=["etag", "last_modified"],
            etag='"abc123"',
            last_modified=None,
        )
        backend._fs_instance.get_file_client.return_value = tmp_fc
        result = backend.write_atomic("dir/file.txt", b"data")
        assert result.etag == "abc123"

    def test_write_atomic_hns_swallows_post_rename_read_failure(self) -> None:
        """BUG-173: a post-rename get_file_properties failure must not surface as a write failure.

        After the temp-file rename commits the write, fetching properties to
        populate etag/last_modified can fail (network blip, eventual
        consistency, permissions). Because the commit already happened,
        propagating the error as a write failure would cause the caller to
        retry against a file that already exists -- raising AlreadyExists
        (overwrite=False) or silently double-writing (overwrite=True). The
        fix swallows the post-commit read error, logs a warning, and returns
        a WriteResult with rich fields unset.
        """
        from azure.core.exceptions import ResourceNotFoundError

        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("dst not present yet")
        backend._cc_instance.get_blob_client.return_value = bc

        tmp_fc = MagicMock(spec=DataLakeFileClient)
        tmp_fc.upload_data.return_value = None
        tmp_fc.rename_file.return_value = None  # commit succeeds
        tmp_fc.get_file_properties.side_effect = ResourceNotFoundError("eventual consistency")
        backend._fs_instance.get_file_client.return_value = tmp_fc

        result = backend.write_atomic("dir/file.txt", b"content")

        assert isinstance(result, WriteResult)
        assert result.size == len(b"content")
        assert result.source == "native"
        assert result.etag is None
        assert result.last_modified is None
        tmp_fc.rename_file.assert_called_once()

    def test_delete_folder_uses_directory_client_on_hns(self) -> None:
        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
        backend._fs_instance.get_directory_client.return_value = dc
        backend._fs_instance.get_paths.return_value = []  # empty folder
        result = backend.delete_folder("my-dir", recursive=False)
        dc.delete_directory.assert_called_once()
        assert result is None

    def test_delete_folder_hns_non_recursive_non_empty_raises(self) -> None:
        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
        backend._fs_instance.get_directory_client.return_value = dc
        backend._fs_instance.get_paths.return_value = [MagicMock(spec=PathProperties)]  # has children
        with pytest.raises(DirectoryNotEmpty):
            backend.delete_folder("my-dir", recursive=False)

    def test_list_files_uses_get_paths_on_hns(self) -> None:
        backend = self._make_hns_backend()
        mock_path = MagicMock(spec=PathProperties)
        mock_path.is_directory = False
        mock_path.name = "dir/file.txt"
        mock_path.size = 42
        mock_path.last_modified = None
        backend._fs_instance.get_paths.return_value = [mock_path]
        files = list(backend.list_files("dir"))
        assert len(files) == 1
        assert files[0].name == "file.txt"

    def test_list_folders_uses_get_paths_on_hns(self) -> None:
        backend = self._make_hns_backend()
        mock_path = MagicMock(spec=PathProperties)
        mock_path.is_directory = True
        mock_path.name = "parent/sub"
        backend._fs_instance.get_paths.return_value = [mock_path]
        folders = list(backend.list_folders("parent"))
        assert [f.name for f in folders] == ["sub"]

    def test_get_folder_info_checks_directory_on_hns(self) -> None:
        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
        backend._fs_instance.get_directory_client.return_value = dc
        backend._cc_instance.list_blobs.return_value = []  # empty dir
        info = backend.get_folder_info("my-dir")
        dc.get_directory_properties.assert_called_once()
        assert info.file_count == 0


# =============================================================================
# Max concurrency threading (AZ-033)
# =============================================================================


class TestAzureMaxConcurrency:
    """AZ-033: max_concurrency kwarg reaches all SDK upload/download call sites."""

    def test_max_concurrency_threaded_to_upload(self) -> None:
        """AZ-033: max_concurrency kwarg reaches upload_blob."""
        from azure.core.exceptions import ResourceNotFoundError

        backend = _make_backend(max_concurrency=4)
        backend._hns_enabled = False
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)
        backend._cc_instance = MagicMock(spec=ContainerClient)
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")
        bc.upload_blob.return_value = {}
        backend._cc_instance.get_blob_client.return_value = bc
        result = backend.write("file.txt", b"data")
        bc.upload_blob.assert_called_once_with(b"data", overwrite=True, max_concurrency=4, metadata=None)
        assert isinstance(result, WriteResult)

    def test_max_concurrency_threaded_to_download(self) -> None:
        """AZ-033: max_concurrency kwarg reaches download_blob."""
        backend = _make_backend(max_concurrency=4)
        backend._hns_enabled = False
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)
        backend._cc_instance = MagicMock(spec=ContainerClient)
        bc = MagicMock(spec=BlobClient)
        downloader = MagicMock(spec=StorageStreamDownloader)
        downloader.chunks.return_value = iter([b"data"])
        bc.download_blob.return_value = downloader
        backend._cc_instance.get_blob_client.return_value = bc
        stream = backend.read("file.txt")
        bc.download_blob.assert_called_once_with(max_concurrency=4)
        assert stream is not None
        stream.close()

    def test_max_concurrency_threaded_to_read_bytes(self) -> None:
        """AZ-033: max_concurrency kwarg reaches download_blob in read_bytes."""
        backend = _make_backend(max_concurrency=8)
        backend._hns_enabled = False
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)
        backend._cc_instance = MagicMock(spec=ContainerClient)
        bc = MagicMock(spec=BlobClient)
        downloader = MagicMock(spec=StorageStreamDownloader)
        downloader.readall.return_value = b"data"
        bc.download_blob.return_value = downloader
        backend._cc_instance.get_blob_client.return_value = bc
        result = backend.read_bytes("file.txt")
        bc.download_blob.assert_called_once_with(max_concurrency=8)
        assert result == b"data"

    def test_max_concurrency_threaded_to_open_atomic_hns(self) -> None:
        """AZ-033: max_concurrency kwarg reaches upload_data in open_atomic HNS path."""
        from azure.core.exceptions import ResourceNotFoundError

        backend = _make_backend(max_concurrency=4)
        backend._hns_enabled = True
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)
        backend._cc_instance = MagicMock(spec=ContainerClient)
        backend._datalake_service_instance = MagicMock(spec=DataLakeServiceClient)
        backend._fs_instance = MagicMock(spec=FileSystemClient)
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")
        backend._cc_instance.get_blob_client.return_value = bc
        tmp_fc = MagicMock(spec=DataLakeFileClient)
        backend._fs_instance.get_file_client.return_value = tmp_fc
        with backend.open_atomic("dir/file.txt", overwrite=True) as f:
            f.write(b"content")
        tmp_fc.upload_data.assert_called_once()
        call_kwargs = tmp_fc.upload_data.call_args
        assert call_kwargs[1]["max_concurrency"] == 4
        assert call_kwargs[1]["overwrite"] is True
        tmp_fc.rename_file.assert_called_once()


# =============================================================================
# Integration tests (require Azurite)
# =============================================================================


@_needs_azurite
class TestAzureIntegration:
    """Integration tests using Azurite emulator."""

    def test_write_and_read_bytes(self, azure_backend: Backend) -> None:
        azure_backend.write("hello.txt", b"hello world")
        assert azure_backend.read_bytes("hello.txt") == b"hello world"

    def test_write_and_read_stream(self, azure_backend: Backend) -> None:
        azure_backend.write("stream.bin", b"\x00\x01\x02\xff")
        stream = azure_backend.read("stream.bin")
        data = stream.read()
        stream.close()
        assert data == b"\x00\x01\x02\xff"

    def test_read_stream_not_bytesio(self, azure_backend: Backend) -> None:
        azure_backend.write("stream_test.bin", b"hello streaming")
        stream = azure_backend.read("stream_test.bin")
        assert not isinstance(stream, io.BytesIO)
        stream.close()

    def test_write_overwrite(self, azure_backend: Backend) -> None:
        azure_backend.write("ow.txt", b"first")
        azure_backend.write("ow.txt", b"second", overwrite=True)
        assert azure_backend.read_bytes("ow.txt") == b"second"

    def test_write_already_exists(self, azure_backend: Backend) -> None:
        azure_backend.write("ae.txt", b"first")
        with pytest.raises(AlreadyExists):
            azure_backend.write("ae.txt", b"second")

    def test_write_from_binaryio(self, azure_backend: Backend) -> None:
        azure_backend.write("bio.txt", io.BytesIO(b"streamed"))
        assert azure_backend.read_bytes("bio.txt") == b"streamed"

    def test_write_nested_path(self, azure_backend: Backend) -> None:
        azure_backend.write("a/b/c/deep.txt", b"deep")
        assert azure_backend.read_bytes("a/b/c/deep.txt") == b"deep"

    def test_exists(self, azure_backend: Backend) -> None:
        assert azure_backend.exists("nope.txt") is False
        azure_backend.write("e.txt", b"x")
        assert azure_backend.exists("e.txt") is True

    def test_is_file(self, azure_backend: Backend) -> None:
        azure_backend.write("f.txt", b"x")
        assert azure_backend.is_file("f.txt") is True
        assert azure_backend.is_file("missing.txt") is False

    def test_is_folder(self, azure_backend: Backend) -> None:
        azure_backend.write("dir/a.txt", b"data")
        assert azure_backend.is_folder("dir") is True
        assert azure_backend.is_folder("nope") is False

    def test_delete_file(self, azure_backend: Backend) -> None:
        azure_backend.write("del.txt", b"x")
        azure_backend.delete("del.txt")
        assert azure_backend.exists("del.txt") is False

    def test_delete_missing_ok(self, azure_backend: Backend) -> None:
        result = azure_backend.delete("nope.txt", missing_ok=True)
        assert result is None

    def test_delete_missing_raises(self, azure_backend: Backend) -> None:
        with pytest.raises(NotFound):
            azure_backend.delete("nope.txt")

    def test_delete_folder_recursive(self, azure_backend: Backend) -> None:
        azure_backend.write("rf/a.txt", b"a")
        azure_backend.write("rf/sub/b.txt", b"b")
        azure_backend.delete_folder("rf", recursive=True)
        assert azure_backend.exists("rf/a.txt") is False
        assert azure_backend.exists("rf/sub/b.txt") is False

    def test_delete_folder_non_recursive_non_empty(self, azure_backend: Backend) -> None:
        azure_backend.write("nonempty/file.txt", b"x")
        with pytest.raises(DirectoryNotEmpty):
            azure_backend.delete_folder("nonempty", recursive=False)

    def test_list_files_non_recursive(self, azure_backend: Backend) -> None:
        azure_backend.write("lst/a.txt", b"a")
        azure_backend.write("lst/b.txt", b"b")
        azure_backend.write("lst/sub/c.txt", b"c")
        files = list(azure_backend.list_files("lst"))
        names = {f.name for f in files}
        assert "a.txt" in names
        assert "b.txt" in names

    def test_list_files_recursive(self, azure_backend: Backend) -> None:
        azure_backend.write("lr/a.txt", b"a")
        azure_backend.write("lr/sub/b.txt", b"b")
        files = list(azure_backend.list_files("lr", recursive=True))
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    def test_list_files_empty(self, azure_backend: Backend) -> None:
        files = list(azure_backend.list_files("empty"))
        assert files == []

    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize(
        ("max_depth", "expected"),
        [
            pytest.param(0, {"a.txt"}, id="depth-0"),
            pytest.param(1, {"a.txt", "b.txt"}, id="depth-1"),
            pytest.param(None, {"a.txt", "b.txt", "c.txt"}, id="unlimited"),
        ],
    )
    def test_list_files_max_depth(self, azure_backend: Backend, max_depth: int | None, expected: set[str]) -> None:
        """BUG-155: list_files respects max_depth parameter."""
        azure_backend.write("md/a.txt", b"a")
        azure_backend.write("md/sub/b.txt", b"b")
        azure_backend.write("md/sub/deep/c.txt", b"c")
        files = list(azure_backend.list_files("md", recursive=True, max_depth=max_depth))
        names = {f.name for f in files}
        assert names == expected

    def test_list_folders(self, azure_backend: Backend) -> None:
        azure_backend.write("lf/sub1/a.txt", b"a")
        azure_backend.write("lf/sub2/b.txt", b"b")
        azure_backend.write("lf/root.txt", b"r")
        folder_names = {f.name for f in azure_backend.list_folders("lf")}
        assert "sub1" in folder_names
        assert "sub2" in folder_names

    def test_get_file_info(self, azure_backend: Backend) -> None:
        azure_backend.write("info.txt", b"hello world")
        fi = azure_backend.get_file_info("info.txt")
        assert isinstance(fi, FileInfo)
        assert fi.name == "info.txt"
        assert fi.size == 11
        assert fi.modified_at is not None

    def test_get_file_info_not_found(self, azure_backend: Backend) -> None:
        with pytest.raises(NotFound):
            azure_backend.get_file_info("missing.txt")

    def test_get_folder_info(self, azure_backend: Backend) -> None:
        azure_backend.write("fi/a.txt", b"aaa")
        azure_backend.write("fi/b.txt", b"bb")
        fi = azure_backend.get_folder_info("fi")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 2
        assert fi.total_size == 5

    def test_get_folder_info_not_found(self, azure_backend: Backend) -> None:
        with pytest.raises(NotFound):
            azure_backend.get_folder_info("nodir")

    def test_move(self, azure_backend: Backend) -> None:
        azure_backend.write("src.txt", b"data")
        azure_backend.move("src.txt", "dst.txt")
        assert azure_backend.exists("src.txt") is False
        assert azure_backend.read_bytes("dst.txt") == b"data"

    @pytest.mark.parametrize(
        "op",
        [
            pytest.param("move", id="move-not-found"),
            pytest.param("copy", id="copy-not-found"),
        ],
    )
    def test_op_not_found(self, azure_backend: Backend, op: str) -> None:
        with pytest.raises(NotFound):
            getattr(azure_backend, op)("missing.txt", "dst.txt")

    @pytest.mark.parametrize(
        "op",
        [
            pytest.param("move", id="move-already-exists"),
            pytest.param("copy", id="copy-already-exists"),
        ],
    )
    def test_op_already_exists(self, azure_backend: Backend, op: str) -> None:
        azure_backend.write("ae1.txt", b"a")
        azure_backend.write("ae2.txt", b"b")
        with pytest.raises(AlreadyExists):
            getattr(azure_backend, op)("ae1.txt", "ae2.txt", overwrite=False)

    def test_move_overwrite(self, azure_backend: Backend) -> None:
        azure_backend.write("mo1.txt", b"a")
        azure_backend.write("mo2.txt", b"b")
        azure_backend.move("mo1.txt", "mo2.txt", overwrite=True)
        assert azure_backend.read_bytes("mo2.txt") == b"a"
        assert azure_backend.exists("mo1.txt") is False

    def test_copy_preserves_source(self, azure_backend: Backend) -> None:
        azure_backend.write("orig.txt", b"data")
        azure_backend.copy("orig.txt", "clone.txt")
        assert azure_backend.read_bytes("orig.txt") == b"data"
        assert azure_backend.read_bytes("clone.txt") == b"data"

    def test_copy_overwrite(self, azure_backend: Backend) -> None:
        azure_backend.write("co1.txt", b"a")
        azure_backend.write("co2.txt", b"b")
        azure_backend.copy("co1.txt", "co2.txt", overwrite=True)
        assert azure_backend.read_bytes("co2.txt") == b"a"

    def test_write_atomic(self, azure_backend: Backend) -> None:
        azure_backend.write_atomic("atomic.txt", b"atomic content")
        assert azure_backend.read_bytes("atomic.txt") == b"atomic content"

    def test_write_atomic_overwrite(self, azure_backend: Backend) -> None:
        azure_backend.write_atomic("at.txt", b"first")
        azure_backend.write_atomic("at.txt", b"second", overwrite=True)
        assert azure_backend.read_bytes("at.txt") == b"second"

    def test_write_atomic_already_exists(self, azure_backend: Backend) -> None:
        azure_backend.write_atomic("at2.txt", b"first")
        with pytest.raises(AlreadyExists):
            azure_backend.write_atomic("at2.txt", b"second", overwrite=False)

    @_needs_azurite
    def test_unwrap_filesystem_client(self, azure_backend: Backend) -> None:

        fs = azure_backend.unwrap(FileSystemClient)
        assert isinstance(fs, FileSystemClient)


# region: Glob (GLOB-020)
class TestAzureGlob:
    """GLOB-020: AzureBackend native glob via prefix-optimized listing."""

    def _populate(self, backend: Backend) -> None:
        backend.write("report.csv", b"r1")
        backend.write("report.txt", b"r2")
        backend.write("data/sales.csv", b"d1")
        backend.write("data/sub/deep.csv", b"d2")
        backend.write("logs/app.log", b"l1")
        backend.write("logs/archive/old.log", b"l2")
        backend.write("file1.txt", b"f1")
        backend.write("file2.txt", b"f2")

    @_needs_azurite
    @pytest.mark.spec("GLOB-020")
    def test_glob_star_csv(self, azure_backend: Backend) -> None:
        self._populate(azure_backend)
        results = sorted(str(f.path) for f in azure_backend.glob("*.csv"))
        assert results == ["report.csv"]

    @_needs_azurite
    @pytest.mark.spec("GLOB-020")
    def test_glob_recursive(self, azure_backend: Backend) -> None:
        self._populate(azure_backend)
        results = sorted(str(f.path) for f in azure_backend.glob("**/*.log"))
        assert results == ["logs/app.log", "logs/archive/old.log"]

    @_needs_azurite
    @pytest.mark.spec("GLOB-020")
    def test_glob_subdirectory(self, azure_backend: Backend) -> None:
        self._populate(azure_backend)
        results = sorted(str(f.path) for f in azure_backend.glob("data/*.csv"))
        assert results == ["data/sales.csv"]

    @_needs_azurite
    @pytest.mark.spec("GLOB-020")
    def test_glob_no_matches(self, azure_backend: Backend) -> None:
        self._populate(azure_backend)
        results = list(azure_backend.glob("*.xyz"))
        assert results == []

    @_needs_azurite
    @pytest.mark.spec("GLOB-020")
    def test_glob_files_only(self, azure_backend: Backend) -> None:
        self._populate(azure_backend)
        for info in azure_backend.glob("**/*"):
            assert isinstance(info, FileInfo)

    @_needs_azurite
    @pytest.mark.spec("GLOB-020")
    def test_glob_question_mark(self, azure_backend: Backend) -> None:
        self._populate(azure_backend)
        results = sorted(str(f.path) for f in azure_backend.glob("file?.txt"))
        assert results == ["file1.txt", "file2.txt"]


# endregion


# region: ETag and Digest (AZ-034)
class TestAzureETagAndDigest:
    """AZ-034: ETag and Content-MD5 digest population in FileInfo."""

    @pytest.mark.spec("AZ-034")
    @_needs_azurite
    def test_get_file_info_has_etag(self, azure_backend: Backend) -> None:
        azure_backend.write("etag_test.txt", b"hello")
        fi = azure_backend.get_file_info("etag_test.txt")
        assert fi.etag is not None
        assert isinstance(fi.etag, str)
        assert '"' not in fi.etag
        assert fi.etag == fi.etag.lower()

    @pytest.mark.spec("AZ-034")
    @_needs_azurite
    def test_list_files_has_etag(self, azure_backend: Backend) -> None:
        azure_backend.write("etag_list.txt", b"hello")
        files = list(azure_backend.list_files(""))
        matches = [f for f in files if f.name == "etag_list.txt"]
        assert len(matches) == 1
        assert matches[0].etag is not None
        assert '"' not in matches[0].etag

    @pytest.mark.spec("AZ-034")
    def test_digest_from_content_md5(self) -> None:
        """Blob properties with Content-MD5 bytes yield ContentDigest('md5', hex)."""
        import hashlib
        from datetime import datetime, timezone

        from remote_store._models import ContentDigest

        content = b"hello world"
        md5_hex = hashlib.md5(content).hexdigest()
        md5_bytes = bytes.fromhex(md5_hex)

        mock_settings = MagicMock(spec=ContentSettings)
        mock_settings.content_md5 = md5_bytes
        mock_props = MagicMock(spec=BlobProperties)
        mock_props.etag = '"abc123"'
        mock_props.content_settings = mock_settings
        mock_props.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_props.size = len(content)
        mock_props.content_length = len(content)

        backend = _make_backend(container="c", account_name="fake", account_key=None)
        fi = backend._props_to_fileinfo(mock_props, "test.txt")

        assert isinstance(fi.digest, ContentDigest)
        assert fi.digest.algorithm == "md5"
        assert fi.digest.value == md5_hex

    @pytest.mark.spec("AZ-034")
    def test_digest_none_when_no_content_md5(self) -> None:
        """Blob properties without Content-MD5 yield digest=None."""
        from datetime import datetime, timezone

        mock_settings = MagicMock(spec=ContentSettings)
        mock_settings.content_md5 = None
        mock_props = MagicMock(spec=BlobProperties)
        mock_props.etag = '"abc123"'
        mock_props.content_settings = mock_settings
        mock_props.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_props.size = 0
        mock_props.content_length = 0

        backend = _make_backend(container="c", account_name="fake", account_key=None)
        fi = backend._props_to_fileinfo(mock_props, "test.txt")

        assert fi.digest is None

    @pytest.mark.spec("AZ-034")
    def test_digest_none_when_content_settings_absent(self) -> None:
        """Blob properties where content_settings is None yield digest=None."""
        from datetime import datetime, timezone

        mock_props = MagicMock(spec=BlobProperties)
        mock_props.etag = '"abc123"'
        mock_props.content_settings = None
        mock_props.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_props.size = 0
        mock_props.content_length = 0

        backend = _make_backend(container="c", account_name="fake", account_key=None)
        fi = backend._props_to_fileinfo(mock_props, "test.txt")

        assert fi.digest is None

    @pytest.mark.spec("AZ-034")
    def test_etag_stripped_and_lowercased(self) -> None:
        """Raw Azure ETag (double-quoted) is stripped and lowercased in FileInfo.etag."""
        from datetime import datetime, timezone

        mock_settings = MagicMock(spec=ContentSettings)
        mock_settings.content_md5 = None
        mock_props = MagicMock(spec=BlobProperties)
        mock_props.etag = '"0X8D4BCC2E4835CD0"'
        mock_props.content_settings = mock_settings
        mock_props.last_modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_props.size = 0
        mock_props.content_length = 0

        backend = _make_backend(container="c", account_name="fake", account_key=None)
        fi = backend._props_to_fileinfo(mock_props, "test.txt")

        assert fi.etag == "0x8d4bcc2e4835cd0"


# endregion


# =============================================================================
# Resolution (RES-053)
# =============================================================================


class TestAzureResolve:
    """RES-053: AzureBackend.resolve() returns kind='azure' with container and account_url."""

    @pytest.mark.spec("RES-053")
    def test_kind_is_azure(self) -> None:
        backend = _make_backend()
        plan = backend.resolve("file.txt")
        assert plan.kind == "azure"

    @pytest.mark.spec("RES-053")
    def test_details_has_container(self) -> None:
        backend = _make_backend()
        plan = backend.resolve("file.txt")
        assert "container" in plan.details

    @pytest.mark.spec("RES-053")
    def test_details_has_account_url(self) -> None:
        backend = _make_backend()
        plan = backend.resolve("file.txt")
        assert "account_url" in plan.details


# =============================================================================
# __del__ cleanup contract (BK-143)
# =============================================================================


class TestAzureDelCleanup:
    """BK-143 (Error): AzureBackend.__del__ emits ResourceWarning and closes clients."""

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
    def test_del_closes_each_client_attr(self, attr: str, spec_cls: type) -> None:
        """__del__ emits ResourceWarning and closes whichever client attr is open."""
        backend = _make_backend()
        mock = MagicMock(spec=spec_cls)
        setattr(backend, attr, mock)  # internal: no public observable
        with pytest.warns(ResourceWarning, match="Unclosed AzureBackend"):
            backend.__del__()
        mock.close.assert_called_once()

    @pytest.mark.spec("BK-143")
    def test_del_continues_closing_after_exception(self) -> None:
        """__del__ closes remaining clients even if one raises on .close()."""
        backend = _make_backend()
        mock_cc = MagicMock(spec=ContainerClient)
        mock_cc.close.side_effect = RuntimeError("network error")
        mock_bs = MagicMock(spec=BlobServiceClient)
        backend._cc_instance = mock_cc  # internal: no public observable
        backend._blob_service_instance = mock_bs  # internal: no public observable
        with pytest.warns(ResourceWarning, match="Unclosed AzureBackend"):
            backend.__del__()
        mock_bs.close.assert_called_once()

    @pytest.mark.spec("BK-143")
    def test_del_is_safe_when_no_clients(self) -> None:
        """__del__ does not raise or warn when no clients have been opened."""
        backend = _make_backend()
        result = backend.__del__()
        assert result is None


# =============================================================================
# _blob_service opts (AZ-022, AZ-031)
# =============================================================================


class TestBlobServiceOpts:
    """AZ-022, AZ-031: _blob_service passes correct block-size opts to BlobServiceClient."""

    _CONN_STR = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KXkJ4MIK7JUCA==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"

    @pytest.mark.spec("AZ-035")
    def test_blob_service_default_block_size(self) -> None:
        """_blob_service passes max_block_size=1 MiB and max_single_put_size=1 MiB by default."""
        backend = _make_backend(container="test", account_key=None, connection_string=self._CONN_STR)

        captured_kwargs: dict[str, Any] = {}

        def fake_from_conn_str(conn_str: str, **kwargs: Any) -> MagicMock:
            captured_kwargs.update(kwargs)
            return MagicMock(spec=BlobServiceClient)

        with patch(
            "azure.storage.blob.BlobServiceClient.from_connection_string",
            side_effect=fake_from_conn_str,
        ):
            _ = backend._blob_service

        assert captured_kwargs["max_block_size"] == 1 * 1024 * 1024
        assert captured_kwargs["max_single_put_size"] == 1 * 1024 * 1024

    @pytest.mark.spec("AZ-031")
    def test_blob_service_client_options_override_wins(self) -> None:
        """User-supplied client_options values take precedence over library defaults."""
        custom_block = 512 * 1024
        backend = _make_backend(
            container="test",
            account_key=None,
            connection_string=self._CONN_STR,
            client_options={"max_block_size": custom_block},
        )

        captured_kwargs: dict[str, Any] = {}

        def fake_from_conn_str(conn_str: str, **kwargs: Any) -> MagicMock:
            captured_kwargs.update(kwargs)
            return MagicMock(spec=BlobServiceClient)

        with patch(
            "azure.storage.blob.BlobServiceClient.from_connection_string",
            side_effect=fake_from_conn_str,
        ):
            _ = backend._blob_service

        # User override wins; max_single_put_size falls back to the library default.
        assert captured_kwargs["max_block_size"] == custom_block
        assert captured_kwargs["max_single_put_size"] == 1 * 1024 * 1024


# =============================================================================
# WriteResult (WR-001, WR-001a, WR-007, WR-009, WR-010, WR-012)
# =============================================================================


class TestAzureWriteResult:
    """Unit tests (mock-based) for WriteResult from AzureBackend.write() and write_atomic()."""

    def _make_non_hns(self) -> tuple[AzureBackend, MagicMock]:
        backend = _make_backend()
        backend._hns_enabled = False
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)
        backend._cc_instance = MagicMock(spec=ContainerClient)
        bc = MagicMock(spec=BlobClient)
        from azure.core.exceptions import ResourceNotFoundError

        bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")
        backend._cc_instance.get_blob_client.return_value = bc
        return backend, bc

    @pytest.mark.spec("WR-001a")
    def test_write_etag_stripped_and_lowercased(self) -> None:
        backend, bc = self._make_non_hns()
        bc.upload_blob.return_value = {"etag": '"0xABCDEF"', "last_modified": None}
        result = backend.write("f.txt", b"x")
        assert result.etag == "0xabcdef"

    @pytest.mark.spec("WR-001a")
    def test_write_etag_none_when_missing(self) -> None:
        backend, bc = self._make_non_hns()
        bc.upload_blob.return_value = {}
        result = backend.write("f.txt", b"x")
        assert result.etag is None

    @pytest.mark.spec("WR-001a")
    def test_write_version_id_populated(self) -> None:
        backend, bc = self._make_non_hns()
        bc.upload_blob.return_value = {"version_id": "v1"}
        result = backend.write("f.txt", b"x")
        assert result.version_id == "v1"

    @pytest.mark.spec("WR-007")
    def test_write_digest_none_on_default_path(self) -> None:
        backend, bc = self._make_non_hns()
        bc.upload_blob.return_value = {}
        result = backend.write("f.txt", b"x")
        assert result.digest is None

    @pytest.mark.spec("WR-012")
    def test_write_metadata_passed_to_sdk(self) -> None:
        backend, bc = self._make_non_hns()
        bc.upload_blob.return_value = {}
        backend.write("f.txt", b"x", metadata={"k": "v"})
        call_kwargs = bc.upload_blob.call_args[1]
        assert call_kwargs["metadata"] == {"k": "v"}

    @pytest.mark.spec("WR-012")
    def test_write_metadata_none_passes_none_to_sdk(self) -> None:
        backend, bc = self._make_non_hns()
        bc.upload_blob.return_value = {}
        backend.write("f.txt", b"x")
        call_kwargs = bc.upload_blob.call_args[1]
        assert call_kwargs["metadata"] is None

    @pytest.mark.spec("WR-001")
    def test_write_atomic_non_hns_returns_write_result(self) -> None:
        backend, bc = self._make_non_hns()
        bc.upload_blob.return_value = {}
        result = backend.write_atomic("f.txt", b"data")
        assert isinstance(result, WriteResult)
        assert result.size == 4

    @pytest.mark.spec("WR-009")
    def test_capabilities_include_write_result_native(self) -> None:
        from remote_store._capabilities import Capability

        assert _make_backend().capabilities.supports(Capability.WRITE_RESULT_NATIVE)

    @pytest.mark.spec("WR-010")
    def test_capabilities_include_user_metadata(self) -> None:
        from remote_store._capabilities import Capability

        assert _make_backend().capabilities.supports(Capability.USER_METADATA)


@_needs_azurite
class TestAzureWriteResultIntegration:
    """Azurite-based integration tests for Azure-wire WriteResult behaviour."""

    @pytest.mark.spec("WR-001a")
    def test_write_etag_non_empty(self, azure_backend: Backend) -> None:
        result = azure_backend.write("et.txt", b"data")
        assert isinstance(result.etag, str)
        assert len(result.etag) > 0

    @pytest.mark.spec("WR-001a")
    def test_write_last_modified_populated(self, azure_backend: Backend) -> None:
        result = azure_backend.write("lm.txt", b"data")
        assert result.last_modified is not None

    @pytest.mark.spec("WR-013")
    def test_write_metadata_round_trips_via_file_info(self, azure_backend: Backend) -> None:
        azure_backend.write("rt.txt", b"data", metadata={"env": "prod"})
        fi = azure_backend.get_file_info("rt.txt")
        assert fi.metadata is not None
        assert fi.metadata.get("env") == "prod"
