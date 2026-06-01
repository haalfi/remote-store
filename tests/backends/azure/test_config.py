"""Azure backend tests -- covers AZ-xxx spec items.

Requires: azure-storage-file-datalake, azure-identity (test dependencies).
Backend-specific tests run against Azurite when available; construction and
error-mapping tests use mocked SDK objects.
"""

from __future__ import annotations

import contextlib
import io
import logging
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
    DirectoryProperties,
    FileSystemClient,
    PathProperties,
)

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
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
from remote_store._models import FileInfo, WriteResult  # noqa: E402
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


# -- Shared Azurite helpers (imported from conftest) -------------------------
from tests.conftest import _azurite_reachable  # noqa: E402


def _needs_azurite(func_or_class):  # type: ignore[no-untyped-def]
    """Apply both requires_docker marker and Azurite-reachability skip."""
    decorated = pytest.mark.requires_docker(func_or_class)
    decorated = pytest.mark.skipif(
        not _azurite_reachable(),
        reason="Azurite not reachable at 127.0.0.1:10000",
    )(decorated)
    return decorated


@pytest.fixture
def azure_backend(azurite_server: str | None) -> Iterator[Backend]:
    """Create an AzureBackend against Azurite."""
    if azurite_server is None:
        pytest.skip("Azurite not reachable")

    container = f"test-az-{uuid.uuid4().hex[:8]}"
    service = BlobServiceClient.from_connection_string(azurite_server)
    try:
        service.create_container(container)
    except Exception:
        service.close()
        raise

    backend = AzureBackend(container=container, connection_string=azurite_server)
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
    @pytest.mark.spec("AZ-016")
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


class TestAzureReadForwardOnly:
    """SEEK-007: AzureBackend.read() returns the chunked forward-only stream,
    not the seekable range reader (which is reserved for read_seekable())."""

    @pytest.mark.spec("SEEK-007")
    def test_read_returns_non_seekable_stream(self) -> None:
        backend = _make_backend()
        backend._hns_enabled = False
        cc = MagicMock(spec=ContainerClient)
        backend._cc_instance = cc
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)
        bc = MagicMock(spec=BlobClient)
        cc.get_blob_client.return_value = bc
        downloader = MagicMock(spec=StorageStreamDownloader)
        downloader.chunks.return_value = iter([b"hello"])
        bc.download_blob.return_value = downloader

        stream = backend.read("file.txt")
        try:
            assert stream.seekable() is False  # forward-only: read() is unchanged
            assert stream.read() == b"hello"
        finally:
            stream.close()


class TestAzureNonHnsFolderMarkers:
    """AZ-010: on a non-HNS account, write() creates only the blob -- no folder
    marker blobs for the intermediate path segments (same as S3-008)."""

    @pytest.mark.spec("AZ-010")
    def test_non_hns_write_creates_no_folder_markers(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        backend = _make_backend()
        backend._hns_enabled = False
        cc = MagicMock(spec=ContainerClient)
        backend._cc_instance = cc
        backend._blob_service_instance = MagicMock(spec=BlobServiceClient)
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")  # target does not exist
        cc.get_blob_client.return_value = bc

        backend.write("a/b/c.txt", b"data")

        # Exactly one upload: the leaf blob. No marker blobs are PUT for "a/"/"a/b/".
        bc.upload_blob.assert_called_once()
        # And no blob client was ever requested for a folder-marker (trailing-slash) key.
        for call in cc.get_blob_client.call_args_list:
            key = call.args[0] if call.args else call.kwargs.get("blob")
            assert not str(key).endswith("/")


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

    @pytest.mark.spec("AZ-012")
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

    @pytest.mark.spec("AZ-008")
    def test_is_folder_uses_directory_client_on_hns(self) -> None:
        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
        dir_props = MagicMock(spec=DirectoryProperties)
        dir_props.metadata = {"hdi_isfolder": "true"}
        dc.get_directory_properties.return_value = dir_props
        backend._fs_instance.get_directory_client.return_value = dc
        assert backend.is_folder("my-dir") is True
        dc.get_directory_properties.assert_called_once()

    @pytest.mark.spec("BE-005")
    @pytest.mark.spec("AZ-013")
    @pytest.mark.spec("AZ-036")
    def test_is_folder_returns_false_for_file_path_on_hns(self) -> None:
        """BUG-203: is_folder must return False when the path is a file, not a directory.

        On HNS, get_directory_properties() succeeds for file paths too (returns
        status 200).  Without the hdi_isfolder probe, is_folder wrongly returns
        True for regular files.
        """
        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
        file_props = MagicMock(spec=DirectoryProperties)
        file_props.metadata = {}  # regular file: no hdi_isfolder
        dc.get_directory_properties.return_value = file_props
        backend._fs_instance.get_directory_client.return_value = dc
        assert backend.is_folder("a.txt") is False

    @pytest.mark.spec("BE-005")
    @pytest.mark.spec("AZ-013")
    @pytest.mark.spec("AZ-036")
    def test_is_file_returns_false_for_hns_directory_blob(self) -> None:
        """BUG-203 (symmetric): is_file must return False for an HNS directory path.

        The blob HEAD response for an HNS directory includes x-ms-meta-hdi_isfolder=true.
        The hdi_isfolder probe in is_file must filter these out.
        """
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        dir_blob_props = MagicMock(spec=BlobProperties)
        dir_blob_props.metadata = {"hdi_isfolder": "true"}
        bc.get_blob_properties.return_value = dir_blob_props
        backend._cc_instance.get_blob_client.return_value = bc
        assert backend.is_file("a-dir") is False

    @pytest.mark.spec("AZ-017")
    def test_move_uses_rename_on_hns(self) -> None:
        backend = self._make_hns_backend()
        # src blob exists
        src_bc = MagicMock(spec=BlobClient)
        src_bc.get_blob_properties.return_value = MagicMock(spec=BlobProperties, metadata={})
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

    @pytest.mark.spec("BE-018")
    @pytest.mark.parametrize("op", ["move", "copy"])
    def test_source_is_directory_raises_invalid_path(self, op: str) -> None:
        """BUG-200: move/copy with an HNS directory src must raise InvalidPath."""
        backend = self._make_hns_backend()
        src_bc = MagicMock(spec=BlobClient)
        src_bc.get_blob_properties.return_value = _make_hns_blob_props()
        backend._cc_instance.get_blob_client.return_value = src_bc

        with pytest.raises(InvalidPath, match="src_dir"):
            getattr(backend, op)("src_dir", "dst.txt")

    @pytest.mark.spec("BE-019")
    @pytest.mark.parametrize("op", ["move", "copy"])
    def test_destination_is_directory_raises_invalid_path(self, op: str) -> None:
        """BUG-200: move/copy with an HNS directory dst must raise InvalidPath."""

        backend = self._make_hns_backend()
        src_bc = MagicMock(spec=BlobClient)
        src_bc.get_blob_properties.return_value = MagicMock(spec=BlobProperties, metadata={})
        dst_bc = MagicMock(spec=BlobClient)
        dst_bc.get_blob_properties.return_value = _make_hns_blob_props()
        backend._cc_instance.get_blob_client.side_effect = [src_bc, dst_bc]

        with pytest.raises(InvalidPath, match="dst_dir"):
            getattr(backend, op)("src.txt", "dst_dir")

    @pytest.mark.spec("BE-018", "BE-019")
    @pytest.mark.parametrize("op", ["move", "copy"])
    @pytest.mark.parametrize("overwrite", [True, False], ids=["overwrite", "no-overwrite"])
    def test_self_op_is_noop(self, op: str, overwrite: bool) -> None:
        """BUG-201 (sync): move(p, p) / copy(p, p) is a no-op for files."""
        backend = _make_backend()
        backend._hns_enabled = False
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.return_value = MagicMock(spec=BlobProperties, metadata={})
        backend._cc_instance = MagicMock(spec=["get_blob_client"])
        backend._cc_instance.get_blob_client.return_value = bc

        getattr(backend, op)("file.txt", "file.txt", overwrite=overwrite)

        # Only one blob client lookup (for the existence probe); no copy or delete.
        assert backend._cc_instance.get_blob_client.call_count == 1
        bc.start_copy_from_url.assert_not_called()
        bc.delete_blob.assert_not_called()

    @pytest.mark.spec("BE-018", "BE-019", "BE-021")
    @pytest.mark.parametrize("op", ["move", "copy"])
    def test_self_op_on_hns_directory_raises_invalid_path(self, op: str) -> None:
        """BUG-201 + #1: self-op short-circuit must still raise InvalidPath on HNS directory."""
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.return_value = _make_hns_blob_props()
        backend._cc_instance.get_blob_client.return_value = bc

        with pytest.raises(InvalidPath, match="some_dir"):
            getattr(backend, op)("some_dir", "some_dir")

    @pytest.mark.spec("BE-018", "BE-019")
    @pytest.mark.parametrize("op", ["move", "copy"])
    def test_self_op_missing_raises_not_found(self, op: str) -> None:
        """move(p, p) / copy(p, p) where p does not exist raises NotFound (not AlreadyExists)."""
        from azure.core.exceptions import ResourceNotFoundError

        backend = _make_backend()
        backend._hns_enabled = False
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")
        backend._cc_instance = MagicMock(spec=["get_blob_client"])
        backend._cc_instance.get_blob_client.return_value = bc

        with pytest.raises(NotFound, match="not found|Not found"):
            getattr(backend, op)("missing.txt", "missing.txt")

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
        tmp_fc.upload_data.assert_called_once_with(
            b"content", length=len(b"content"), overwrite=True, max_concurrency=4, metadata=None
        )
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

    @pytest.mark.spec("WR-001a")
    def test_write_atomic_hns_swallows_post_rename_read_failure(self, caplog: pytest.LogCaptureFixture) -> None:
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

        dst_fc = MagicMock(spec=DataLakeFileClient)
        dst_fc.get_file_properties.side_effect = ResourceNotFoundError("eventual consistency")

        # Production calls get_file_client twice: first for tmp_path, then for the
        # destination after rename. Distinct mocks prevent a future regression
        # where post-rename reads hit the wrong client from slipping past.
        backend._fs_instance.get_file_client.side_effect = [tmp_fc, dst_fc]

        with caplog.at_level(logging.WARNING, logger="remote_store.backends._azure"):
            result = backend.write_atomic("dir/file.txt", b"content")

        assert isinstance(result, WriteResult)
        assert result.size == len(b"content")
        assert result.source == "native"
        assert result.etag is None
        assert result.last_modified is None
        tmp_fc.rename_file.assert_called_once()
        dst_fc.get_file_properties.assert_called_once()
        assert any("post-rename get_file_properties failed" in record.message for record in caplog.records), (
            "expected warning log on swallowed post-commit read failure"
        )

    @pytest.mark.spec("WR-001a")
    @pytest.mark.spec("BE-010")
    def test_write_atomic_hns_streaming_uses_dfs_append_protocol(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BUG-202: streaming write_atomic drives the DFS append protocol directly.

        ``flush_data`` requires ``position=<total bytes>``; ``upload_data`` with
        an unseekable wrapper leaves ``position=None`` on real HNS
        (``MissingRequiredQueryParameter``).  Fix: ``create_file`` →
        per-chunk ``append_data(offset, length)`` → ``flush_data(position)``;
        memory is bounded to ``_AZURE_BLOCK_SIZE`` (mirrors the async sibling
        from BUG-194).

        Monkeypatches ``_AZURE_BLOCK_SIZE`` to 50 so the 150-byte payload is
        split into three chunks — exercises offset advancement across
        iterations, not just the trivial single-chunk path. (Default 1 MiB
        would consume the whole payload in one ``content.read()`` call.)
        """
        from azure.core.exceptions import ResourceNotFoundError

        from remote_store.backends import _azure as _azure_mod

        monkeypatch.setattr(_azure_mod, "_AZURE_BLOCK_SIZE", 50)
        payload = b"hello-streaming" * 10  # 150 bytes → 3 chunks of 50 bytes
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")
        backend._cc_instance.get_blob_client.return_value = bc
        tmp_fc = MagicMock(spec=DataLakeFileClient)
        tmp_fc.get_file_properties.return_value = MagicMock(
            spec=["etag", "last_modified"],
            etag=None,
            last_modified=None,
        )
        backend._fs_instance.get_file_client.return_value = tmp_fc

        result = backend.write_atomic("dir/stream.bin", io.BytesIO(payload))

        # upload_data must NOT be called for streaming input (would re-introduce
        # the MissingRequiredQueryParameter regression).
        tmp_fc.upload_data.assert_not_called()

        tmp_fc.create_file.assert_called_once()

        # Reconstruct the body from the append_data calls and verify the full
        # payload survives the chunked transfer — guards against a future
        # refactor that drops bytes or reorders the append protocol while the
        # length= / flush_data positions still look right.
        appended = b""
        running_offset = 0
        for call in tmp_fc.append_data.call_args_list:
            chunk = call.args[0] if call.args else call.kwargs.get("data")
            offset = call.kwargs.get("offset")
            length = call.kwargs.get("length")
            assert offset == running_offset, f"append_data offset drift: {offset} != {running_offset}"
            assert length == len(chunk), f"append_data length mismatch: {length} != {len(chunk)}"
            appended += chunk
            running_offset += length
        assert appended == payload, "append_data chunks do not reconstruct the original payload"

        # flush_data must close with position=<total bytes>.
        flush_call = tmp_fc.flush_data.call_args
        assert flush_call is not None, "flush_data was not called"
        flush_position = flush_call.args[0] if flush_call.args else flush_call.kwargs.get("position")
        assert flush_position == len(payload), f"flush_data position {flush_position} != payload size {len(payload)}"

        assert isinstance(result, WriteResult)
        assert result.size == len(payload)

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

    @pytest.mark.spec("BE-013")
    def test_delete_folder_hns_raises_invalid_path_on_file(self) -> None:
        """BUG-198: delete_folder on a file path must raise InvalidPath, not DirectoryNotEmpty."""
        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
        # Simulate ADLS Gen2 behaviour: get_directory_properties succeeds for
        # file paths but returns no hdi_isfolder metadata (resource_type=file).
        dc.get_directory_properties.return_value = MagicMock(spec=["metadata"], metadata={})
        backend._fs_instance.get_directory_client.return_value = dc
        with pytest.raises(InvalidPath, match="file-path.txt"):
            backend.delete_folder("file-path.txt")
        dc.delete_directory.assert_not_called()

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_hns_raises_invalid_path_on_file(self) -> None:
        """BUG-198: get_folder_info on a file path must raise InvalidPath."""
        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
        # Simulate ADLS Gen2 behaviour: get_directory_properties succeeds for
        # file paths but returns no hdi_isfolder metadata (resource_type=file).
        dc.get_directory_properties.return_value = MagicMock(spec=["metadata"], metadata={})
        backend._fs_instance.get_directory_client.return_value = dc
        with pytest.raises(InvalidPath, match="file-path.txt"):
            backend.get_folder_info("file-path.txt")
        backend._fs_instance.get_paths.assert_not_called()

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
        backend._fs_instance.get_paths.return_value = []  # empty dir
        info = backend.get_folder_info("my-dir")
        dc.get_directory_properties.assert_called_once()
        backend._fs_instance.get_paths.assert_called_once()
        assert info.file_count == 0

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_filters_hns_directory_markers(self) -> None:
        """BUG-199: file_count must exclude hdi_isfolder=true entries returned by get_paths."""
        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
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
        backend._fs_instance.get_paths.return_value = [file_a, dir_marker, file_b]
        info = backend.get_folder_info("mix")
        assert info.file_count == 2, "directory marker must not be counted as a file"
        assert info.total_size == 5

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_raises_not_found_on_hns_missing_directory(self) -> None:
        """BE-017: !PathExists → NotFound. get_directory_properties raises ResourceNotFoundError."""
        from azure.core.exceptions import ResourceNotFoundError

        backend = self._make_hns_backend()
        dc = MagicMock(spec=DataLakeDirectoryClient)
        dc.get_directory_properties.side_effect = ResourceNotFoundError("not found")
        backend._fs_instance.get_directory_client.return_value = dc
        with pytest.raises(NotFound, match=r"^Not found: missing\b"):
            backend.get_folder_info("missing")

    @pytest.mark.spec("BE-016", "BE-021")
    def test_get_file_info_raises_invalid_path_on_hns_directory(self) -> None:
        """BUG-195: get_file_info must raise InvalidPath when hdi_isfolder=true (BE-016)."""
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        props = MagicMock(spec=BlobProperties)
        props.metadata = {"hdi_isfolder": "true"}
        bc.get_blob_properties.return_value = props
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="exists as a directory"):
            backend.get_file_info("mydir")

    @pytest.mark.spec("BE-016")
    def test_get_file_info_raises_not_found_on_missing_path(self) -> None:
        """BE-016: !PathExists → NotFound (non-HNS path still works)."""
        from azure.core.exceptions import ResourceNotFoundError

        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("not found")
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(NotFound):
            backend.get_file_info("missing.txt")

    # BUG-197: read, read_bytes, read_seekable, delete must raise InvalidPath for HNS dirs

    @pytest.mark.spec("BE-021", "BE-007")
    def test_read_bytes_on_hns_directory_raises_invalid_path(self) -> None:
        """BUG-197: read_bytes on an HNS directory path must raise InvalidPath.

        The download_blob() call succeeds (directory marker is a 0-byte blob);
        the fix inspects downloader.properties.metadata post-download.
        """
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        # Explicit spec list: do NOT use StorageStreamDownloader (its spec hides
        # .properties on some SDK versions, masking the fix's metadata probe).
        downloader = MagicMock(spec=["readall", "properties"])
        downloader.readall.return_value = b""
        downloader.properties.metadata = {"hdi_isfolder": "true"}
        bc.download_blob.return_value = downloader
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="is a directory"):
            backend.read_bytes("mydir")

    @pytest.mark.spec("BE-021", "BE-007")
    def test_read_bytes_on_hns_file_returns_bytes(self) -> None:
        """read_bytes on a normal HNS file must return its content unchanged."""
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        downloader = MagicMock(spec=["readall", "properties"])
        downloader.readall.return_value = b"hello"
        downloader.properties.metadata = {}
        bc.download_blob.return_value = downloader
        backend._cc_instance.get_blob_client.return_value = bc
        assert backend.read_bytes("file.txt") == b"hello"

    @pytest.mark.spec("BE-021", "BE-006")
    def test_read_on_hns_directory_raises_invalid_path(self) -> None:
        """BUG-197: read on an HNS directory path must raise InvalidPath.

        The pre-check calls get_blob_properties() (HEAD) before download_blob();
        when hdi_isfolder is set, InvalidPath is raised before any download.
        """
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        dir_props = MagicMock(spec=["metadata"])
        dir_props.metadata = {"hdi_isfolder": "true"}
        bc.get_blob_properties.return_value = dir_props
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="is a directory"):
            backend.read("mydir")

    @pytest.mark.spec("BE-021", "BE-006")
    def test_read_on_hns_file_does_not_raise(self) -> None:
        """read on a normal HNS file must not raise InvalidPath."""
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        file_props = MagicMock(spec=["metadata"])
        file_props.metadata = {}
        bc.get_blob_properties.return_value = file_props
        downloader = MagicMock(spec=StorageStreamDownloader)
        downloader.chunks.return_value = iter([b"data"])
        bc.download_blob.return_value = downloader
        backend._cc_instance.get_blob_client.return_value = bc
        stream = backend.read("file.txt")
        assert stream is not None
        stream.close()

    @pytest.mark.spec("BE-021", "BE-006")
    def test_read_seekable_on_hns_directory_raises_invalid_path(self) -> None:
        """BUG-197: read_seekable on an HNS directory path must raise InvalidPath.

        read_seekable always calls get_blob_properties() for the file size;
        the fix checks hdi_isfolder from the same response.
        """
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        dir_props = MagicMock(spec=["metadata", "size"])
        dir_props.metadata = {"hdi_isfolder": "true"}
        dir_props.size = 0
        bc.get_blob_properties.return_value = dir_props
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="is a directory"):
            backend.read_seekable("mydir")

    @pytest.mark.spec("BE-021", "BE-006")
    def test_read_seekable_on_hns_file_does_not_raise(self) -> None:
        """read_seekable on a normal HNS file must not raise InvalidPath."""
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        file_props = MagicMock(spec=["metadata", "size"])
        file_props.metadata = {}
        file_props.size = 5
        bc.get_blob_properties.return_value = file_props
        backend._cc_instance.get_blob_client.return_value = bc
        stream = backend.read_seekable("file.txt")
        assert stream is not None
        stream.close()

    @pytest.mark.spec("BE-021", "BE-012")
    def test_delete_on_hns_directory_raises_invalid_path(self) -> None:
        """BUG-197: delete on an HNS directory path must raise InvalidPath.

        The pre-check calls get_blob_properties() (HEAD) before delete_blob();
        when hdi_isfolder is set, InvalidPath is raised without any delete call.
        """
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        dir_props = MagicMock(spec=["metadata"])
        dir_props.metadata = {"hdi_isfolder": "true"}
        bc.get_blob_properties.return_value = dir_props
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="is a directory"):
            backend.delete("mydir")
        bc.delete_blob.assert_not_called()

    @pytest.mark.spec("BE-021", "BE-012")
    def test_delete_on_hns_file_does_not_raise(self) -> None:
        """delete on a normal HNS file must not raise InvalidPath."""
        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        file_props = MagicMock(spec=["metadata"])
        file_props.metadata = {}
        bc.get_blob_properties.return_value = file_props
        bc.delete_blob.return_value = None
        backend._cc_instance.get_blob_client.return_value = bc
        backend.delete("file.txt")
        assert bc.delete_blob.call_count == 1

    @pytest.mark.spec("BE-021", "BE-012")
    def test_delete_missing_with_missing_ok_true_does_not_raise_on_hns(self) -> None:
        """BUG-197 regression: the hdi_isfolder HEAD probe must not break missing_ok=True.

        Pre-fix the probe re-raised ``ResourceNotFoundError`` before
        ``delete_blob()`` ever ran, so ``missing_ok=True`` had no opportunity
        to swallow the error.  Surfaced by Stage 3 recording against real
        ADLS Gen2 (``test_delete_missing[missing_ok_passes-file-azure_live]``).
        """
        from azure.core.exceptions import ResourceNotFoundError

        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        bc.get_blob_properties.side_effect = ResourceNotFoundError("nope")
        bc.delete_blob.side_effect = ResourceNotFoundError("nope")
        backend._cc_instance.get_blob_client.return_value = bc
        backend.delete("missing.txt", missing_ok=True)
        # delete_blob() must have been attempted (probe must not short-circuit
        # on missing-file errors).
        assert bc.delete_blob.call_count == 1

    @pytest.mark.spec("BE-021", "BE-012")
    def test_delete_directory_is_not_empty_409_maps_to_invalid_path(self) -> None:
        """BUG-197 data-loss guard: HNS non-empty directory yields 409 DirectoryIsNotEmpty.

        The pre-check usually short-circuits on ``hdi_isfolder``. When the
        probe fails for any reason (network, permissions, mocked) and
        ``delete_blob()`` then surfaces ``DirectoryIsNotEmpty``, the fallback
        in delete() must raise ``InvalidPath`` — not let ``AlreadyExists`` or
        a generic mapping silently swallow the data-loss signal.
        """
        from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

        backend = self._make_hns_backend()
        bc = MagicMock(spec=BlobClient)
        # Probe fails (so we exercise the fallback path, not the pre-check).
        bc.get_blob_properties.side_effect = ResourceNotFoundError("probe failed")
        # delete_blob raises DirectoryIsNotEmpty — the 409 we care about.
        exc = HttpResponseError("conflict")
        exc.error_code = "DirectoryIsNotEmpty"
        bc.delete_blob.side_effect = exc
        backend._cc_instance.get_blob_client.return_value = bc
        with pytest.raises(InvalidPath, match="is a directory"):
            backend.delete("mydir")

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_root_hns_call_shape(self) -> None:
        """BUG-213: get_folder_info('') on HNS skips the dir-probe (root is
        always a folder) and calls get_paths('/') — the 'or /' fallback is
        the root-path accommodation.

        Real ADLS Gen2 rejects ``get_directory_client("")`` with "Please
        specify a file system name and file path", so the impl must
        short-circuit the probe for ``azure_path == ""``.  Pins the intended
        call shape so any future change to root-path handling surfaces as a
        regression independent of live SDK semantics.
        """
        backend = self._make_hns_backend()
        backend._fs_instance.get_paths.return_value = []  # root is empty for this test

        info = backend.get_folder_info("")

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
    """Azure-specific integration tests using Azurite emulator.
    Generic create/read/update/delete/list/move/copy operations are covered by the
    parameterized conformance suite (BE-004 through BE-019)."""

    def test_read_stream_not_bytesio(self, azure_backend: Backend) -> None:
        """read() returns a lazy streaming object, not a materialised BytesIO."""
        azure_backend.write("stream_test.bin", b"hello streaming")
        stream = azure_backend.read("stream_test.bin")
        assert not isinstance(stream, io.BytesIO)
        stream.close()

    @pytest.mark.spec("BE-021")
    @pytest.mark.spec("DEPTH-003")
    @pytest.mark.parametrize(
        ("max_depth", "expected"),
        [
            pytest.param(0, {"a.txt"}, id="depth-0"),
            pytest.param(1, {"a.txt", "b.txt"}, id="depth-1"),
            pytest.param(None, {"a.txt", "b.txt", "c.txt"}, id="unlimited"),
        ],
    )
    def test_list_files_max_depth(self, azure_backend: Backend, max_depth: int | None, expected: set[str]) -> None:
        """BUG-155: list_files respects max_depth (DEPTH-003; Azure filters client-side, no native pruning)."""
        azure_backend.write("md/a.txt", b"a")
        azure_backend.write("md/sub/b.txt", b"b")
        azure_backend.write("md/sub/deep/c.txt", b"c")
        files = list(azure_backend.list_files("md", recursive=True, max_depth=max_depth))
        names = {f.name for f in files}
        assert names == expected

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
    @pytest.mark.spec("AZ-019")
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
    @pytest.mark.spec("AZ-019")
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


# =============================================================================
# HNS directory path guard — write / write_atomic / open_atomic (BE-008, BE-010, BE-021)
# =============================================================================


def _make_hns_blob_props(metadata: dict[str, str] | None = None) -> MagicMock:
    """Create a mock BlobProperties representing an HNS directory blob."""
    props = MagicMock(spec=BlobProperties)
    props.size = 0
    props.content_length = 0
    props.last_modified = None
    props.etag = None
    cs = MagicMock(spec=ContentSettings)
    cs.content_md5 = None
    props.content_settings = cs
    props.metadata = metadata if metadata is not None else {"hdi_isfolder": "true"}
    return props


def _setup_hns_write_backend() -> tuple[AzureBackend, MagicMock, MagicMock]:
    """Return (backend, container_client, blob_client) with HNS enabled."""
    backend = _make_backend()
    backend._hns_enabled = True
    cc = MagicMock(spec=ContainerClient)
    backend._cc_instance = cc
    bc = MagicMock(spec=BlobClient)
    cc.get_blob_client.return_value = bc
    backend._blob_service_instance = MagicMock(spec=BlobServiceClient)
    fs = MagicMock(spec=FileSystemClient)
    backend._fs_instance = fs
    return backend, cc, bc


class TestAzureWriteOnHnsDirectory:
    """BE-021: write/write_atomic/open_atomic on an HNS directory path must raise InvalidPath."""

    @pytest.mark.spec("BE-021")
    @pytest.mark.spec("BE-008")
    @pytest.mark.parametrize("overwrite", [False, True])
    def test_write_raises_invalid_path_on_hns_dir(self, overwrite: bool) -> None:
        backend, _cc, bc = _setup_hns_write_backend()
        bc.get_blob_properties.return_value = _make_hns_blob_props()
        with pytest.raises(InvalidPath, match="exists as a directory"):
            backend.write("mydir", b"data", overwrite=overwrite)

    @pytest.mark.spec("BE-021")
    @pytest.mark.spec("BE-010")
    @pytest.mark.parametrize("overwrite", [False, True])
    def test_write_atomic_raises_invalid_path_on_hns_dir(self, overwrite: bool) -> None:
        backend, _cc, bc = _setup_hns_write_backend()
        bc.get_blob_properties.return_value = _make_hns_blob_props()
        with pytest.raises(InvalidPath, match="exists as a directory"):
            backend.write_atomic("mydir", b"data", overwrite=overwrite)

    @pytest.mark.spec("BE-008")
    def test_write_regular_file_not_affected(self) -> None:
        """A normal (non-dir) blob at the path should still raise AlreadyExists."""
        backend, _cc, bc = _setup_hns_write_backend()
        bc.get_blob_properties.return_value = _make_hns_blob_props(metadata={})
        with pytest.raises(AlreadyExists, match="already exists|Already exists"):
            backend.write("file.txt", b"data")

    @pytest.mark.spec("BE-008")
    def test_write_path_not_found_proceeds(self) -> None:
        """When the blob doesn't exist (ResourceNotFoundError), write should not raise."""
        from azure.core.exceptions import ResourceNotFoundError

        backend, _cc, bc = _setup_hns_write_backend()
        bc.get_blob_properties.side_effect = ResourceNotFoundError("not found")
        bc.upload_blob.return_value = {"etag": '"abc"', "last_modified": None, "version_id": None, "content_md5": None}
        result = backend.write("new.txt", b"data")
        assert result is not None

    @pytest.mark.spec("BE-010")
    def test_write_atomic_path_not_found_proceeds(self) -> None:
        """When the blob doesn't exist, write_atomic should not raise — proceed to temp+rename."""
        from azure.core.exceptions import ResourceNotFoundError

        backend, _cc, bc = _setup_hns_write_backend()
        bc.get_blob_properties.side_effect = ResourceNotFoundError("not found")
        tmp_fc = MagicMock(spec=DataLakeFileClient)
        tmp_fc.upload_data.return_value = None
        dst_fc = MagicMock(spec=DataLakeFileClient)
        dst_fc.get_file_properties.return_value = MagicMock(
            spec=["etag", "last_modified"], etag=None, last_modified=None
        )
        backend._fs_instance.get_file_client.side_effect = [tmp_fc, dst_fc]
        result = backend.write_atomic("new.txt", b"data")
        assert result is not None
        tmp_fc.upload_data.assert_called_once()
        tmp_fc.rename_file.assert_called_once_with("test/new.txt")

    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize("overwrite", [False, True])
    def test_open_atomic_raises_invalid_path_on_hns_dir(self, overwrite: bool) -> None:
        backend, _cc, bc = _setup_hns_write_backend()
        bc.get_blob_properties.return_value = _make_hns_blob_props()
        with (
            pytest.raises(InvalidPath, match="exists as a directory"),
            backend.open_atomic("mydir", overwrite=overwrite),
        ):
            pass

    @pytest.mark.spec("BE-021")
    def test_open_atomic_regular_file_not_affected(self) -> None:
        """A normal (non-dir) blob at the path should still raise AlreadyExists."""
        backend, _cc, bc = _setup_hns_write_backend()
        bc.get_blob_properties.return_value = _make_hns_blob_props(metadata={})
        with pytest.raises(AlreadyExists, match="already exists|Already exists"), backend.open_atomic("file.txt"):
            pass

    @pytest.mark.spec("BE-021")
    def test_open_atomic_path_not_found_proceeds(self) -> None:
        """When the blob doesn't exist, open_atomic should not raise — proceed to temp+rename."""
        from azure.core.exceptions import ResourceNotFoundError

        backend, _cc, bc = _setup_hns_write_backend()
        bc.get_blob_properties.side_effect = ResourceNotFoundError("not found")
        tmp_fc = MagicMock(spec=DataLakeFileClient)
        tmp_fc.upload_data.return_value = None
        backend._fs_instance.get_file_client.return_value = tmp_fc
        with backend.open_atomic("new.txt") as f:
            f.write(b"data")
        assert tmp_fc.upload_data.call_count == 1
        tmp_fc.rename_file.assert_called_once_with("test/new.txt")


# =============================================================================
# RetryPolicy acceptance and azure-SDK retry mapping (RET-012)
# Migrated from tests/test_config.py (BK-216 / BK-191).
# =============================================================================


_RETRY_CONN_STR = "DefaultEndpointsProtocol=http;AccountName=a;"


@pytest.mark.spec("RET-012")
def test_azure_accepts_retry() -> None:
    from remote_store._config import RetryPolicy

    rp = RetryPolicy(max_attempts=7)
    assert AzureBackend(container="c", connection_string=_RETRY_CONN_STR, retry=rp)._retry is rp


@pytest.mark.spec("RET-012")
@pytest.mark.parametrize(
    ("rp_kwargs", "expected_backoff", "expected_jitter"),
    [
        pytest.param({"max_attempts": 5, "backoff_base": 2.0, "jitter": 3.0}, 2, 3, id="integer_values"),
        pytest.param({"max_attempts": 3, "backoff_base": 0.5, "jitter": 0.7}, 1, 1, id="fractional_rounds_up"),
    ],
)
def test_azure_build_retry_mapping(rp_kwargs: dict[str, Any], expected_backoff: int, expected_jitter: int) -> None:
    from remote_store._config import RetryPolicy

    rp = RetryPolicy(**rp_kwargs)
    azure_retry = AzureBackend(container="c", connection_string=_RETRY_CONN_STR, retry=rp)._build_azure_retry()
    assert azure_retry.total_retries == rp_kwargs["max_attempts"] - 1
    assert azure_retry.initial_backoff == expected_backoff
    assert azure_retry.random_jitter_range == expected_jitter


@pytest.mark.spec("RET-012")
def test_azure_build_retry_none() -> None:
    assert AzureBackend(container="c", connection_string=_RETRY_CONN_STR)._build_azure_retry() is None


# region: Credential masking (AF-008, SEC-004) — migrated from tests/test_coverage_gaps.py (BK-222 / BK-191 slice 6/6)


class TestAzureCredentialMasking:
    """AF-008: AzureBackend repr masks sensitive fields and accepts Secret wrappers."""

    def test_masks_set_secrets(self) -> None:
        backend = AzureBackend(
            container="c",
            account_name="acct",
            account_key="mykey",
            sas_token="mysas",
            connection_string="conn=str",
            credential="cred_obj",
        )
        _BACKENDS.append(backend)
        r = repr(backend)
        for raw in ("mykey", "mysas", "conn=str", "cred_obj"):
            assert raw not in r
        for masked in ("account_key='***'", "sas_token='***'", "connection_string='***'", "credential='***'"):
            assert masked in r
        for visible in ("container='c'", "account_name='acct'"):
            assert visible in r

    def test_shows_none_for_unset_secrets(self) -> None:
        backend = AzureBackend(container="c", account_url="https://x.blob.core.windows.net")
        _BACKENDS.append(backend)
        r = repr(backend)
        for expected in ("account_key=None", "sas_token=None", "connection_string=None", "credential=None"):
            assert expected in r

    @pytest.mark.spec("SEC-004")
    def test_accepts_secret_wrapper(self) -> None:
        from remote_store._config import Secret

        backend = AzureBackend(
            container="c",
            account_name="acct",
            account_key=Secret("mykey"),
            sas_token=Secret("tok"),
            connection_string=Secret("conn=str"),
        )
        _BACKENDS.append(backend)
        assert backend._account_key == "mykey"  # internal: no public observable (repr shows '***' for raw strings too)
        assert backend._sas_token == "tok"  # internal: no public observable
        assert backend._connection_string == "conn=str"  # internal: no public observable


# endregion
