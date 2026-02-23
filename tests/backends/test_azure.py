"""Azure backend tests -- covers AZ-xxx spec items.

Requires: azure-storage-file-datalake, azure-identity (test dependencies).
Backend-specific tests run against Azurite when available; construction and
error-mapping tests use mocked SDK objects.
"""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store._errors import (  # noqa: E402
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderInfo  # noqa: E402
from remote_store.backends._azure import AzureBackend  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


def _azurite_reachable() -> bool:
    import socket

    try:
        s = socket.create_connection(("127.0.0.1", 10000), timeout=1)
        s.close()
        return True
    except OSError:
        return False


_AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    "QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
    "TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
)

_needs_azurite = pytest.mark.skipif(
    not _azurite_reachable(),
    reason="Azurite not reachable at 127.0.0.1:10000",
)


@pytest.fixture()
def azure_backend() -> Iterator[Backend]:
    """Create an AzureBackend against Azurite."""
    if not _azurite_reachable():
        pytest.skip("Azurite not reachable")

    from azure.storage.filedatalake import DataLakeServiceClient

    container = f"test-az-{uuid.uuid4().hex[:8]}"
    service = DataLakeServiceClient.from_connection_string(_AZURITE_CONN_STR)
    service.create_file_system(container)

    backend = AzureBackend(container=container, connection_string=_AZURITE_CONN_STR)
    yield backend

    backend.close()
    service.delete_file_system(container)
    service.close()


# region: Construction (AZ-001, AZ-005)
class TestAzureConstruction:
    """AZ-001, AZ-005: construction and validation."""

    @pytest.mark.spec("AZ-001")
    def test_constructor_with_connection_string(self) -> None:
        backend = AzureBackend(container="test", connection_string="DefaultEndpointsProtocol=http;AccountName=x")
        assert backend is not None

    @pytest.mark.spec("AZ-001")
    def test_constructor_with_account_name(self) -> None:
        backend = AzureBackend(container="test", account_name="myaccount")
        assert backend is not None

    @pytest.mark.spec("AZ-001")
    def test_constructor_with_account_url(self) -> None:
        backend = AzureBackend(container="test", account_url="https://myaccount.dfs.core.windows.net")
        assert backend is not None

    @pytest.mark.spec("AZ-002")
    def test_name_is_azure(self) -> None:
        backend = AzureBackend(container="test", account_name="x")
        assert backend.name == "azure"

    @pytest.mark.spec("AZ-003")
    def test_declares_all_capabilities(self) -> None:
        backend = AzureBackend(container="test", account_name="x")
        caps = backend.capabilities
        assert isinstance(caps, CapabilitySet)
        for cap in Capability:
            assert caps.supports(cap), f"Missing capability: {cap.value}"

    @pytest.mark.spec("AZ-004")
    def test_lazy_connection(self) -> None:
        """Construction must not make network calls."""
        backend = AzureBackend(
            container="any-container",
            account_name="nonexistent",
            account_key="fakekey",
        )
        assert backend.name == "azure"

    @pytest.mark.spec("AZ-005")
    def test_empty_container_raises(self) -> None:
        with pytest.raises(ValueError, match="container"):
            AzureBackend(container="", account_name="x")

    @pytest.mark.spec("AZ-005")
    def test_whitespace_container_raises(self) -> None:
        with pytest.raises(ValueError, match="container"):
            AzureBackend(container="   ", account_name="x")

    @pytest.mark.spec("AZ-005")
    def test_no_connection_info_raises(self) -> None:
        with pytest.raises(ValueError, match="account_name"):
            AzureBackend(container="test")


# endregion


# region: HNS Detection (AZ-006)
class TestAzureHNSDetection:
    """AZ-006: HNS detection with mocked SDK."""

    @pytest.mark.spec("AZ-006")
    def test_hns_enabled_detected(self) -> None:
        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        mock_client = MagicMock()
        mock_client.get_account_information.return_value = {"is_hns_enabled": True}
        backend._blob_service_instance = mock_client
        assert backend._hns is True

    @pytest.mark.spec("AZ-006")
    def test_hns_disabled_detected(self) -> None:
        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        mock_client = MagicMock()
        mock_client.get_account_information.return_value = {"is_hns_enabled": False}
        backend._blob_service_instance = mock_client
        assert backend._hns is False

    @pytest.mark.spec("AZ-006")
    def test_hns_detection_failure_falls_back(self) -> None:
        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        mock_client = MagicMock()
        mock_client.get_account_information.side_effect = Exception("network error")
        backend._blob_service_instance = mock_client
        assert backend._hns is False

    @pytest.mark.spec("AZ-006")
    def test_hns_result_cached(self) -> None:
        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        mock_client = MagicMock()
        mock_client.get_account_information.return_value = {"is_hns_enabled": True}
        backend._blob_service_instance = mock_client
        # Access twice
        _ = backend._hns
        _ = backend._hns
        # Should only be called once
        mock_client.get_account_information.assert_called_once()


# endregion


# region: Error mapping (AZ-025 through AZ-028)
class TestAzureErrorMapping:
    """AZ-025 through AZ-028: structured error classification."""

    @pytest.mark.spec("AZ-025")
    def test_resource_not_found_maps_to_not_found(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        mapped = backend._classify(ResourceNotFoundError("not found"), "file.txt")
        assert isinstance(mapped, NotFound)
        assert mapped.backend == "azure"

    @pytest.mark.spec("AZ-025")
    def test_resource_exists_maps_to_already_exists(self) -> None:
        from azure.core.exceptions import ResourceExistsError

        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        mapped = backend._classify(ResourceExistsError("exists"), "file.txt")
        assert isinstance(mapped, AlreadyExists)

    @pytest.mark.spec("AZ-025")
    def test_http_403_maps_to_permission_denied(self) -> None:
        from azure.core.exceptions import HttpResponseError

        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        exc = HttpResponseError("forbidden")
        exc.status_code = 403
        mapped = backend._classify(exc, "file.txt")
        assert isinstance(mapped, PermissionDenied)

    @pytest.mark.spec("AZ-025")
    def test_http_404_maps_to_not_found(self) -> None:
        from azure.core.exceptions import HttpResponseError

        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        exc = HttpResponseError("not found")
        exc.status_code = 404
        mapped = backend._classify(exc, "file.txt")
        assert isinstance(mapped, NotFound)

    @pytest.mark.spec("AZ-025")
    def test_http_409_maps_to_already_exists(self) -> None:
        from azure.core.exceptions import HttpResponseError

        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        exc = HttpResponseError("conflict")
        exc.status_code = 409
        mapped = backend._classify(exc, "file.txt")
        assert isinstance(mapped, AlreadyExists)

    @pytest.mark.spec("AZ-025")
    def test_client_auth_error_maps_to_permission_denied(self) -> None:
        from azure.core.exceptions import ClientAuthenticationError

        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        mapped = backend._classify(ClientAuthenticationError("auth failed"), "file.txt")
        assert isinstance(mapped, PermissionDenied)

    @pytest.mark.spec("AZ-025")
    def test_service_request_error_maps_to_unavailable(self) -> None:
        from azure.core.exceptions import ServiceRequestError

        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        mapped = backend._classify(ServiceRequestError("connection refused"), "")
        assert isinstance(mapped, BackendUnavailable)

    @pytest.mark.spec("AZ-026")
    def test_no_native_exception_leaks(self) -> None:
        """The error context manager converts all exceptions."""
        from azure.core.exceptions import ResourceNotFoundError

        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        with pytest.raises(RemoteStoreError), backend._errors("test"):
            raise ResourceNotFoundError("not found")

    @pytest.mark.spec("AZ-026")
    def test_error_has_backend_attribute(self) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        with pytest.raises(RemoteStoreError) as exc_info, backend._errors("test"):
            raise ResourceNotFoundError("not found")
        assert exc_info.value.backend == "azure"

    @pytest.mark.spec("AZ-028")
    def test_remote_store_errors_pass_through(self) -> None:
        """RemoteStoreError raised inside _errors() passes through unchanged."""
        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        with pytest.raises(NotFound, match="custom"), backend._errors("test"):
            raise NotFound("custom", path="test", backend="azure")


# endregion


# region: to_key (AZ-027)
class TestAzureToKey:
    """AZ-027: to_key strips container prefix."""

    @pytest.mark.spec("AZ-027")
    def test_strips_container_prefix(self) -> None:
        backend = AzureBackend(container="my-container", account_name="x")
        assert backend.to_key("my-container/data/file.txt") == "data/file.txt"

    @pytest.mark.spec("AZ-027")
    def test_no_prefix_unchanged(self) -> None:
        backend = AzureBackend(container="my-container", account_name="x")
        assert backend.to_key("data/file.txt") == "data/file.txt"

    @pytest.mark.spec("AZ-027")
    def test_empty_string(self) -> None:
        backend = AzureBackend(container="my-container", account_name="x")
        assert backend.to_key("") == ""


# endregion


# region: unwrap (AZ-030)
class TestAzureUnwrap:
    """AZ-030: unwrap returns FileSystemClient."""

    @pytest.mark.spec("AZ-030")
    def test_unwrap_wrong_type_raises(self) -> None:
        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        with pytest.raises(CapabilityNotSupported):
            backend.unwrap(str)


# endregion


# region: Lifecycle (AZ-029)
class TestAzureLifecycle:
    """AZ-029: close() behavior."""

    @pytest.mark.spec("AZ-029")
    def test_close_without_connection(self) -> None:
        """close() before any connection is safe."""
        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        backend.close()

    @pytest.mark.spec("AZ-029")
    def test_close_idempotent(self) -> None:
        backend = AzureBackend(container="test", account_name="x", account_key="fakekey")
        backend.close()
        backend.close()


# endregion


# region: Integration tests (require Azurite)
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
        azure_backend.delete("nope.txt", missing_ok=True)

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
        with pytest.raises(RemoteStoreError):
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

    def test_list_folders(self, azure_backend: Backend) -> None:
        azure_backend.write("lf/sub1/a.txt", b"a")
        azure_backend.write("lf/sub2/b.txt", b"b")
        azure_backend.write("lf/root.txt", b"r")
        folders = set(azure_backend.list_folders("lf"))
        assert "sub1" in folders
        assert "sub2" in folders

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

    def test_move_not_found(self, azure_backend: Backend) -> None:
        with pytest.raises(NotFound):
            azure_backend.move("missing.txt", "dst.txt")

    def test_move_already_exists(self, azure_backend: Backend) -> None:
        azure_backend.write("m1.txt", b"a")
        azure_backend.write("m2.txt", b"b")
        with pytest.raises(AlreadyExists):
            azure_backend.move("m1.txt", "m2.txt", overwrite=False)

    def test_move_overwrite(self, azure_backend: Backend) -> None:
        azure_backend.write("mo1.txt", b"a")
        azure_backend.write("mo2.txt", b"b")
        azure_backend.move("mo1.txt", "mo2.txt", overwrite=True)
        assert azure_backend.read_bytes("mo2.txt") == b"a"
        assert azure_backend.exists("mo1.txt") is False

    def test_copy(self, azure_backend: Backend) -> None:
        azure_backend.write("orig.txt", b"data")
        azure_backend.copy("orig.txt", "clone.txt")
        assert azure_backend.read_bytes("orig.txt") == b"data"
        assert azure_backend.read_bytes("clone.txt") == b"data"

    def test_copy_not_found(self, azure_backend: Backend) -> None:
        with pytest.raises(NotFound):
            azure_backend.copy("missing.txt", "dst.txt")

    def test_copy_already_exists(self, azure_backend: Backend) -> None:
        azure_backend.write("c1.txt", b"a")
        azure_backend.write("c2.txt", b"b")
        with pytest.raises(AlreadyExists):
            azure_backend.copy("c1.txt", "c2.txt", overwrite=False)

    def test_copy_overwrite(self, azure_backend: Backend) -> None:
        azure_backend.write("co1.txt", b"a")
        azure_backend.write("co2.txt", b"b")
        azure_backend.copy("co1.txt", "co2.txt", overwrite=True)
        assert azure_backend.read_bytes("co2.txt") == b"a"
        assert azure_backend.read_bytes("co1.txt") == b"a"

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
        from azure.storage.filedatalake import FileSystemClient

        fs = azure_backend.unwrap(FileSystemClient)
        assert isinstance(fs, FileSystemClient)


# endregion
