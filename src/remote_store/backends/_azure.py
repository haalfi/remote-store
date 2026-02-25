"""Azure Storage backend -- Blob SDK for non-HNS, DataLake SDK for HNS."""

from __future__ import annotations

import contextlib
import io
import logging
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, BinaryIO, TypeVar

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderInfo
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._types import WritableContent

T = TypeVar("T")

_ALL_CAPABILITIES = CapabilitySet(set(Capability))

_log = logging.getLogger(__name__)


class _AzureBinaryIO(io.RawIOBase):
    """Forward-only streaming adapter wrapping StorageStreamDownloader.chunks()."""

    def __init__(self, chunks_iter: Iterator[bytes]) -> None:
        self._iter = chunks_iter
        self._buf = b""

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        wanted = len(b)
        while len(self._buf) < wanted:
            try:
                chunk = next(self._iter)
            except StopIteration:
                break
            self._buf += chunk
        available = self._buf[:wanted]
        self._buf = self._buf[wanted:]
        n = len(available)
        b[:n] = available
        return n

    def close(self) -> None:
        if not self.closed:
            self._iter = iter(())
            self._buf = b""
            super().close()


class AzureBackend(Backend):
    """Azure Storage backend.

    Uses the Blob SDK for non-HNS accounts (plain Blob Storage, Azurite) and
    the DataLake SDK for HNS accounts (ADLS Gen2) to get atomic rename and
    real directory support.

    :param container: Azure Storage container name (required, non-empty).
    :param account_name: Storage account name.
    :param account_url: Full account URL (e.g. ``https://myaccount.dfs.core.windows.net``).
    :param account_key: Storage account key.
    :param sas_token: Shared Access Signature token.
    :param connection_string: Azure Storage connection string.
    :param credential: Any credential object (e.g. ``DefaultAzureCredential()``).
    :param client_options: Additional options passed to service clients.
    """

    def __init__(
        self,
        container: str,
        *,
        account_name: str | None = None,
        account_url: str | None = None,
        account_key: str | None = None,
        sas_token: str | None = None,
        connection_string: str | None = None,
        credential: Any | None = None,
        client_options: dict[str, Any] | None = None,
    ) -> None:
        if not container or not container.strip():
            raise ValueError("container must be a non-empty string")
        if not account_name and not account_url and not connection_string:
            raise ValueError("At least one of account_name, account_url, or connection_string must be provided")
        self._container = container
        self._account_name = account_name
        self._account_url = account_url
        self._account_key = account_key
        self._sas_token = sas_token
        self._connection_string = connection_string
        self._credential = credential
        self._client_options = client_options or {}
        # Lazy instances
        self._blob_service_instance: Any = None
        self._cc_instance: Any = None
        self._datalake_service_instance: Any = None
        self._fs_instance: Any = None
        self._hns_enabled: bool | None = None

    @property
    def name(self) -> str:
        return "azure"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # region: credential helper

    def _resolve_credential(self) -> Any:  # pragma: no cover -- only reached without connection_string
        """Build credential from constructor params."""
        cred = self._credential
        if cred is None and self._account_key is not None:
            cred = self._account_key
        elif cred is None and self._sas_token is not None:
            cred = self._sas_token
        elif cred is None:
            try:
                from azure.identity import DefaultAzureCredential

                cred = DefaultAzureCredential()
            except ImportError:
                raise BackendUnavailable(
                    "No credential provided and azure-identity is not installed. "
                    "Install azure-identity or provide account_key/sas_token/credential.",
                    backend=self.name,
                ) from None
        return cred

    # endregion

    # region: lazy connection -- Blob SDK (always used for non-HNS)

    @property
    def _blob_service(self) -> Any:
        """Lazy BlobServiceClient."""
        if self._blob_service_instance is None:
            from azure.storage.blob import BlobServiceClient

            opts: dict[str, Any] = dict(self._client_options)
            if self._connection_string:
                self._blob_service_instance = BlobServiceClient.from_connection_string(self._connection_string, **opts)
            else:  # pragma: no cover -- only reached without connection_string
                url = self._account_url
                if url is None and self._account_name is not None:
                    url = f"https://{self._account_name}.blob.core.windows.net"
                assert url is not None  # guaranteed by __init__ validation
                cred = self._resolve_credential()
                self._blob_service_instance = BlobServiceClient(account_url=url, credential=cred, **opts)
        return self._blob_service_instance

    @property
    def _cc(self) -> Any:
        """Lazy ContainerClient (Blob SDK)."""
        if self._cc_instance is None:
            self._cc_instance = self._blob_service.get_container_client(self._container)
        return self._cc_instance

    # endregion

    # region: lazy connection -- DataLake SDK (used for HNS only)

    @property
    def _datalake_service(self) -> Any:  # pragma: no cover -- HNS only, requires ADLS Gen2
        """Lazy DataLakeServiceClient (only used for HNS accounts)."""
        if self._datalake_service_instance is None:
            from azure.storage.filedatalake import DataLakeServiceClient

            opts: dict[str, Any] = dict(self._client_options)
            if self._connection_string:
                self._datalake_service_instance = DataLakeServiceClient.from_connection_string(
                    self._connection_string, **opts
                )
            else:
                url = self._account_url
                if url is None and self._account_name is not None:
                    url = f"https://{self._account_name}.dfs.core.windows.net"
                assert url is not None
                cred = self._resolve_credential()
                self._datalake_service_instance = DataLakeServiceClient(account_url=url, credential=cred, **opts)
        return self._datalake_service_instance

    @property
    def _fs(self) -> Any:  # pragma: no cover -- HNS only, requires ADLS Gen2
        """Lazy FileSystemClient (DataLake SDK, HNS only)."""
        if self._fs_instance is None:
            self._fs_instance = self._datalake_service.get_file_system_client(self._container)
        return self._fs_instance

    # endregion

    # region: HNS detection

    @property
    def _hns(self) -> bool:
        """Whether the storage account has Hierarchical Namespace enabled."""
        if self._hns_enabled is None:
            try:
                info = self._blob_service.get_account_information()
                self._hns_enabled = bool(info.get("is_hns_enabled", False))
            except Exception:
                _log.warning(
                    "Failed to detect HNS status, falling back to non-HNS behavior",
                    exc_info=True,
                )
                self._hns_enabled = False
        return self._hns_enabled

    # endregion

    # region: path helpers

    def _azure_path(self, path: str) -> str:
        """Normalize path for Azure (strip leading /, collapse double separators)."""
        return re.sub(r"/+", "/", path).lstrip("/")

    def to_key(self, native_path: str) -> str:
        prefix = f"{self._container}/"
        if native_path.startswith(prefix):
            return native_path[len(prefix) :]
        return native_path

    # endregion

    # region: error mapping

    @contextmanager
    def _errors(self, path: str = "") -> Iterator[None]:
        """Map Azure SDK exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:
            raise
        except Exception as exc:
            raise self._classify(exc, path) from None

    def _classify(self, exc: Exception, path: str) -> RemoteStoreError:
        """Classify an Azure SDK exception into a remote_store error type."""
        from azure.core.exceptions import (
            ClientAuthenticationError,
            HttpResponseError,
            ResourceExistsError,
            ResourceNotFoundError,
            ServiceRequestError,
            ServiceResponseError,
        )

        if isinstance(exc, ResourceNotFoundError):
            return NotFound(f"Not found: {path}", path=path, backend=self.name)
        if isinstance(exc, ResourceExistsError):
            return AlreadyExists(f"Already exists: {path}", path=path, backend=self.name)
        if isinstance(exc, ClientAuthenticationError):
            return PermissionDenied(f"Authentication failed: {path}", path=path, backend=self.name)
        if isinstance(exc, ServiceRequestError | ServiceResponseError):
            return BackendUnavailable(str(exc), path=path, backend=self.name)
        if isinstance(exc, HttpResponseError):
            status = getattr(exc, "status_code", None)
            if status == 404:
                return NotFound(f"Not found: {path}", path=path, backend=self.name)
            if status == 403:
                return PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name)
            if status == 409:
                return AlreadyExists(f"Already exists: {path}", path=path, backend=self.name)
            return RemoteStoreError(str(exc), path=path, backend=self.name)  # pragma: no cover
        return RemoteStoreError(str(exc), path=path, backend=self.name)  # pragma: no cover

    # endregion

    # region: helpers

    def _blob_client(self, path: str) -> Any:
        """Get a BlobClient for the given path."""
        return self._cc.get_blob_client(self._azure_path(path))

    def _props_to_fileinfo(self, props: Any, path: str) -> FileInfo:
        """Convert blob/path properties to FileInfo."""
        name = path.rsplit("/", 1)[-1] if "/" in path else path
        size = getattr(props, "size", None) or getattr(props, "content_length", 0) or 0
        modified = getattr(props, "last_modified", None)
        if modified is not None and modified.tzinfo is None:
            modified = modified.replace(tzinfo=timezone.utc)  # pragma: no cover
        if modified is None:
            modified = datetime.now(tz=timezone.utc)  # pragma: no cover
        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=int(size),
            modified_at=modified,
        )

    # endregion

    # region: existence checks

    def exists(self, path: str) -> bool:
        from azure.core.exceptions import ResourceNotFoundError

        with self._errors(path):
            azure_path = self._azure_path(path)
            if not azure_path:
                return True
            # Check as blob
            bc = self._cc.get_blob_client(azure_path)
            try:
                bc.get_blob_properties()
                return True
            except ResourceNotFoundError:
                pass
            # Check as folder
            if self._hns:  # pragma: no cover -- HNS only
                try:
                    self._fs.get_directory_client(azure_path).get_directory_properties()
                    return True
                except Exception:
                    return False
            else:
                prefix = azure_path.rstrip("/") + "/"
                blobs = self._cc.list_blobs(name_starts_with=prefix, results_per_page=1)
                return any(True for _ in blobs)

    def is_file(self, path: str) -> bool:
        from azure.core.exceptions import ResourceNotFoundError

        with self._errors(path):
            bc = self._blob_client(path)
            try:
                props = bc.get_blob_properties()
                # HNS directories have metadata hdi_isfolder=true
                meta = getattr(props, "metadata", None) or {}
                return not meta.get("hdi_isfolder")
            except ResourceNotFoundError:
                return False

    def is_folder(self, path: str) -> bool:
        with self._errors(path):
            azure_path = self._azure_path(path)
            if not azure_path:
                return True
            if self._hns:  # pragma: no cover -- HNS only
                try:
                    self._fs.get_directory_client(azure_path).get_directory_properties()
                    return True
                except Exception:
                    return False
            else:
                prefix = azure_path.rstrip("/") + "/"
                blobs = self._cc.list_blobs(name_starts_with=prefix, results_per_page=1)
                return any(True for _ in blobs)

    # endregion

    # region: read operations

    def read(self, path: str) -> BinaryIO:
        with self._errors(path):
            bc = self._blob_client(path)
            downloader = bc.download_blob()
            raw = _AzureBinaryIO(downloader.chunks())
            return io.BufferedReader(raw)

    def read_bytes(self, path: str) -> bytes:
        with self._errors(path):
            bc = self._blob_client(path)
            return bytes(bc.download_blob().readall())

    # endregion

    # region: write operations

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        with self._errors(path):
            bc = self._blob_client(path)
            if not overwrite:
                try:
                    bc.get_blob_properties()
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except AlreadyExists:
                    raise
                except ResourceNotFoundError:
                    pass  # Blob doesn't exist, proceed
            bc.upload_blob(content, overwrite=True)

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        if not self._hns:
            # non-HNS: direct upload is atomic (PUT semantics)
            self.write(path, content, overwrite=overwrite)
            return

        # HNS: write to temp file via DFS, then atomic rename
        from azure.core.exceptions import ResourceNotFoundError

        with self._errors(path):  # pragma: no cover -- HNS only
            bc = self._blob_client(path)
            if not overwrite:
                try:
                    bc.get_blob_properties()
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except AlreadyExists:
                    raise
                except ResourceNotFoundError:
                    pass

            azure_path = self._azure_path(path)
            basename = azure_path.rsplit("/", 1)[-1] if "/" in azure_path else azure_path
            parent = azure_path.rsplit("/", 1)[0] if "/" in azure_path else ""
            tmp_name = f".~tmp.{basename}.{uuid.uuid4().hex[:8]}"
            tmp_path = f"{parent}/{tmp_name}" if parent else tmp_name

            tmp_fc = self._fs.get_file_client(tmp_path)
            try:
                tmp_fc.upload_data(content, overwrite=True)
                new_name = f"{self._container}/{azure_path}"
                tmp_fc.rename_file(new_name)
            except Exception:
                with contextlib.suppress(Exception):
                    tmp_fc.delete_file()
                raise

    # endregion

    # region: delete operations

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        with self._errors(path):
            bc = self._blob_client(path)
            try:
                bc.delete_blob()
            except Exception as exc:
                mapped = self._classify(exc, path)
                if isinstance(mapped, NotFound):
                    if not missing_ok:
                        raise mapped from None
                    return
                raise mapped from None  # pragma: no cover

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._errors(path):
            azure_path = self._azure_path(path)

            if self._hns:  # pragma: no cover -- HNS only
                dc = self._fs.get_directory_client(azure_path)
                try:
                    dc.get_directory_properties()
                except Exception as exc:
                    mapped = self._classify(exc, path)
                    if isinstance(mapped, NotFound):
                        if not missing_ok:
                            raise mapped from None
                        return
                    raise mapped from None

                if not recursive:
                    children = list(self._fs.get_paths(path=azure_path, recursive=False, max_results=1))
                    if children:
                        raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend=self.name)
                dc.delete_directory()
            else:
                # non-HNS: virtual folders via blob prefix
                prefix = azure_path.rstrip("/") + "/"
                first = list(self._cc.list_blobs(name_starts_with=prefix, results_per_page=1))
                if first:
                    if not recursive:
                        raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend=self.name)
                    for blob in self._cc.list_blobs(name_starts_with=prefix):
                        self._cc.get_blob_client(blob.name).delete_blob()
                elif not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

    # endregion

    # region: listing operations

    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        with self._errors(path):
            azure_path = self._azure_path(path)
            prefix = (azure_path.rstrip("/") + "/") if azure_path else ""

            if self._hns:  # pragma: no cover -- HNS only
                try:
                    paths = self._fs.get_paths(path=azure_path or "/", recursive=recursive)
                    for p in paths:
                        if not getattr(p, "is_directory", False):
                            yield self._props_to_fileinfo(p, str(p.name))
                except Exception as exc:
                    mapped = self._classify(exc, path)
                    if isinstance(mapped, NotFound):
                        return
                    raise mapped from None
            elif recursive:
                blobs = self._cc.list_blobs(name_starts_with=prefix)
                for blob in blobs:
                    yield self._props_to_fileinfo(blob, blob.name)
            else:
                blobs = self._cc.walk_blobs(name_starts_with=prefix)
                for item in blobs:
                    if not getattr(item, "prefix", None):
                        yield self._props_to_fileinfo(item, item.name)

    def list_folders(self, path: str) -> Iterator[str]:
        with self._errors(path):
            azure_path = self._azure_path(path)
            prefix = (azure_path.rstrip("/") + "/") if azure_path else ""

            if self._hns:  # pragma: no cover -- HNS only
                try:
                    paths = self._fs.get_paths(path=azure_path or "/", recursive=False)
                    for p in paths:
                        if getattr(p, "is_directory", False):
                            folder_name = str(p.name).rstrip("/").rsplit("/", 1)[-1]
                            yield folder_name
                except Exception as exc:
                    mapped = self._classify(exc, path)
                    if isinstance(mapped, NotFound):
                        return
                    raise mapped from None
            else:
                blobs = self._cc.walk_blobs(name_starts_with=prefix)
                for item in blobs:
                    if getattr(item, "prefix", None):
                        folder_name = item.prefix.rstrip("/").rsplit("/", 1)[-1]
                        yield folder_name

    # endregion

    # region: metadata

    def get_file_info(self, path: str) -> FileInfo:
        with self._errors(path):
            bc = self._blob_client(path)
            props = bc.get_blob_properties()
            meta = getattr(props, "metadata", None) or {}
            if meta.get("hdi_isfolder"):  # pragma: no cover -- HNS only
                raise NotFound(f"File not found: {path}", path=path, backend=self.name)
            return self._props_to_fileinfo(props, path)

    def get_folder_info(self, path: str) -> FolderInfo:
        with self._errors(path):
            azure_path = self._azure_path(path)

            if self._hns:  # pragma: no cover -- HNS only
                dc = self._fs.get_directory_client(azure_path)
                dc.get_directory_properties()  # raises if not found

            # Gather stats from files under this prefix
            prefix = (azure_path.rstrip("/") + "/") if azure_path else ""
            file_count = 0
            total_size = 0
            latest_modified: datetime | None = None

            for blob in self._cc.list_blobs(name_starts_with=prefix):
                file_count += 1
                total_size += blob.size or 0
                modified = blob.last_modified
                if modified is not None:
                    if modified.tzinfo is None:  # pragma: no cover
                        modified = modified.replace(tzinfo=timezone.utc)
                    if latest_modified is None or modified > latest_modified:
                        latest_modified = modified

            if file_count == 0 and not self._hns:
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

            return FolderInfo(
                path=RemotePath(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest_modified,
            )

    # endregion

    # region: move and copy

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        with self._errors(src):
            src_bc = self._blob_client(src)
            src_bc.get_blob_properties()  # raises NotFound if missing

            dst_bc = self._blob_client(dst)
            if not overwrite:
                try:
                    dst_bc.get_blob_properties()
                    raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
                except AlreadyExists:
                    raise
                except ResourceNotFoundError:
                    pass

            if self._hns:  # pragma: no cover -- HNS only
                src_fc = self._fs.get_file_client(self._azure_path(src))
                new_name = f"{self._container}/{self._azure_path(dst)}"
                src_fc.rename_file(new_name)
            else:
                # Server-side copy + delete
                dst_bc.start_copy_from_url(src_bc.url)
                src_bc.delete_blob()

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        with self._errors(src):
            src_bc = self._blob_client(src)
            src_bc.get_blob_properties()  # raises NotFound if missing

            dst_bc = self._blob_client(dst)
            if not overwrite:
                try:
                    dst_bc.get_blob_properties()
                    raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
                except AlreadyExists:
                    raise
                except ResourceNotFoundError:
                    pass

            dst_bc.start_copy_from_url(src_bc.url)

    # endregion

    # region: lifecycle

    def close(self) -> None:
        clients = (self._cc_instance, self._blob_service_instance, self._fs_instance, self._datalake_service_instance)
        for client in clients:
            if client is not None:
                with contextlib.suppress(Exception):
                    client.close()
        self._cc_instance = None
        self._blob_service_instance = None
        self._fs_instance = None
        self._datalake_service_instance = None
        self._hns_enabled = None

    def unwrap(self, type_hint: type[T]) -> T:
        from azure.storage.filedatalake import FileSystemClient

        if type_hint is FileSystemClient:
            return self._fs  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend 'azure' does not expose native handle of type {type_hint.__name__}. "
            f"Supported: azure.storage.filedatalake.FileSystemClient.",
            capability="unwrap",
            backend=self.name,
        )

    # endregion
