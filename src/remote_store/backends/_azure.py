"""Azure Storage backend using azure-storage-file-datalake directly."""

from __future__ import annotations

import contextlib
import io
import logging
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
        # Accumulate enough data from the iterator
        while len(self._buf) < wanted:
            try:
                chunk = next(self._iter)
            except StopIteration:
                break
            self._buf += chunk
        # Return what we have
        available = self._buf[:wanted]
        self._buf = self._buf[wanted:]
        n = len(available)
        b[:n] = available
        return n

    def close(self) -> None:
        if not self.closed:
            self._iter = iter(())  # release reference
            self._buf = b""
            super().close()


class AzureBackend(Backend):
    """Azure Storage backend using ``azure-storage-file-datalake``.

    Targets ADLS Gen2 (Hierarchical Namespace) as the primary use case while
    remaining fully functional against plain Blob Storage accounts without HNS.

    :param container: Azure Storage container name (required, non-empty).
    :param account_name: Storage account name.
    :param account_url: Full account URL (e.g. ``https://myaccount.dfs.core.windows.net``).
    :param account_key: Storage account key.
    :param sas_token: Shared Access Signature token.
    :param connection_string: Azure Storage connection string.
    :param credential: Any credential object (e.g. ``DefaultAzureCredential()``).
    :param client_options: Additional options passed to ``DataLakeServiceClient``.
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
        self._service_client: Any = None
        self._fs_client: Any = None
        self._hns_enabled: bool | None = None

    @property
    def name(self) -> str:
        return "azure"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # region: lazy connection

    @property
    def _client(self) -> Any:
        """Lazy DataLakeServiceClient."""
        if self._service_client is None:
            from azure.storage.filedatalake import DataLakeServiceClient

            opts: dict[str, Any] = dict(self._client_options)

            if self._connection_string:
                self._service_client = DataLakeServiceClient.from_connection_string(self._connection_string, **opts)
            else:
                # Build credential
                cred = self._credential
                if cred is None and self._account_key is not None:
                    cred = self._account_key
                elif cred is None and self._sas_token is not None:
                    cred = self._sas_token
                elif cred is None:
                    # Attempt DefaultAzureCredential
                    try:
                        from azure.identity import DefaultAzureCredential

                        cred = DefaultAzureCredential()
                    except ImportError:
                        raise BackendUnavailable(
                            "No credential provided and azure-identity is not installed. "
                            "Install azure-identity or provide account_key/sas_token/credential.",
                            backend=self.name,
                        ) from None

                url = self._account_url
                if url is None and self._account_name is not None:
                    url = f"https://{self._account_name}.dfs.core.windows.net"

                assert url is not None  # guaranteed by __init__ validation
                self._service_client = DataLakeServiceClient(account_url=url, credential=cred, **opts)
        return self._service_client

    @property
    def _fs(self) -> Any:
        """Lazy FileSystemClient for the configured container."""
        if self._fs_client is None:
            self._fs_client = self._client.get_file_system_client(self._container)
        return self._fs_client

    @property
    def _hns(self) -> bool:
        """Whether the storage account has Hierarchical Namespace enabled."""
        if self._hns_enabled is None:
            try:
                info = self._client.get_account_information()
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
        """Normalize path for Azure (strip leading /)."""
        return path.lstrip("/")

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
            return RemoteStoreError(str(exc), path=path, backend=self.name)
        return RemoteStoreError(str(exc), path=path, backend=self.name)

    # endregion

    # region: helpers

    def _get_file_client(self, path: str) -> Any:
        """Get a DataLakeFileClient for the given path."""
        return self._fs.get_file_client(self._azure_path(path))

    def _get_directory_client(self, path: str) -> Any:
        """Get a DataLakeDirectoryClient for the given path."""
        return self._fs.get_directory_client(self._azure_path(path))

    def _props_to_fileinfo(self, props: Any, path: str) -> FileInfo:
        """Convert path properties to FileInfo."""
        name = path.rsplit("/", 1)[-1] if "/" in path else path
        size = getattr(props, "size", None) or getattr(props, "content_length", 0) or 0
        modified = getattr(props, "last_modified", None)
        if modified is not None and modified.tzinfo is None:
            modified = modified.replace(tzinfo=timezone.utc)
        if modified is None:
            modified = datetime.now(tz=timezone.utc)
        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=int(size),
            modified_at=modified,
        )

    # endregion

    # region: existence checks

    def exists(self, path: str) -> bool:
        with self._errors(path):
            azure_path = self._azure_path(path)
            if not azure_path:
                # Root always "exists"
                return True
            try:
                self._fs.get_file_client(azure_path).get_file_properties()
                return True
            except Exception:
                pass
            # Check as directory
            if self._hns:
                try:
                    self._fs.get_directory_client(azure_path).get_directory_properties()
                    return True
                except Exception:
                    return False
            else:
                # non-HNS: check if any blobs exist with this prefix
                paths = self._fs.get_paths(path=azure_path, recursive=False, max_results=1)
                return any(True for _ in paths)

    def is_file(self, path: str) -> bool:
        with self._errors(path):
            try:
                props = self._get_file_client(path).get_file_properties()
                is_dir = getattr(props.get("metadata", {}), "get", lambda *_: None)("hdi_isfolder")
                if is_dir:
                    return False
                # HNS: check is_directory attribute
                resource_type = getattr(props, "metadata", {}).get("hdi_isfolder", None)
                if resource_type:
                    return False
                return not getattr(props, "is_directory", False)
            except Exception:
                return False

    def is_folder(self, path: str) -> bool:
        with self._errors(path):
            azure_path = self._azure_path(path)
            if not azure_path:
                return True
            if self._hns:
                try:
                    props = self._fs.get_directory_client(azure_path).get_directory_properties()
                    return bool(getattr(props, "is_directory", True))
                except Exception:
                    return False
            else:
                # non-HNS: folder exists if any blobs have this prefix
                prefix = azure_path.rstrip("/") + "/"
                paths = self._fs.get_paths(path=prefix, recursive=False, max_results=1)
                return any(True for _ in paths)

    # endregion

    # region: read operations

    def read(self, path: str) -> BinaryIO:
        with self._errors(path):
            fc = self._get_file_client(path)
            downloader = fc.download_file()
            raw = _AzureBinaryIO(downloader.chunks())
            return io.BufferedReader(raw)

    def read_bytes(self, path: str) -> bytes:
        with self._errors(path):
            fc = self._get_file_client(path)
            downloader = fc.download_file()
            return bytes(downloader.readall())

    # endregion

    # region: write operations

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        with self._errors(path):
            fc = self._get_file_client(path)
            if not overwrite:
                try:
                    fc.get_file_properties()
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except AlreadyExists:
                    raise
                except Exception:
                    pass  # File doesn't exist, proceed
            if isinstance(content, bytes):
                fc.upload_data(content, overwrite=True)
            else:
                fc.upload_data(content, overwrite=True)

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        if not self._hns:
            # non-HNS: direct upload is atomic (PUT semantics)
            self.write(path, content, overwrite=overwrite)
            return

        with self._errors(path):
            fc = self._get_file_client(path)
            if not overwrite:
                try:
                    fc.get_file_properties()
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except AlreadyExists:
                    raise
                except Exception:
                    pass

            # Write to temp file, then atomic rename
            azure_path = self._azure_path(path)
            name = azure_path.rsplit("/", 1)[-1] if "/" in azure_path else azure_path
            parent = azure_path.rsplit("/", 1)[0] if "/" in azure_path else ""
            tmp_name = f".~tmp.{name}.{uuid.uuid4().hex[:8]}"
            tmp_path = f"{parent}/{tmp_name}" if parent else tmp_name

            tmp_fc = self._fs.get_file_client(tmp_path)
            try:
                if isinstance(content, bytes):
                    tmp_fc.upload_data(content, overwrite=True)
                else:
                    tmp_fc.upload_data(content, overwrite=True)

                # Atomic rename
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
            fc = self._get_file_client(path)
            try:
                fc.delete_file()
            except Exception as exc:
                mapped = self._classify(exc, path)
                if isinstance(mapped, NotFound):
                    if not missing_ok:
                        raise mapped from None
                    return
                raise mapped from None

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._errors(path):
            azure_path = self._azure_path(path)

            if self._hns:
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
                    # Check if directory is empty
                    children = list(self._fs.get_paths(path=azure_path, recursive=False, max_results=1))
                    if children:
                        raise RemoteStoreError(f"Folder not empty: {path}", path=path, backend=self.name)
                dc.delete_directory()
            else:
                # non-HNS: list and delete all blobs with this prefix
                prefix = azure_path.rstrip("/") + "/"
                found = False
                paths = list(self._fs.get_paths(path=prefix, recursive=True))
                if paths:
                    found = True
                    if not recursive:
                        raise RemoteStoreError(f"Folder not empty: {path}", path=path, backend=self.name)
                    for p in paths:
                        self._fs.get_file_client(p.name).delete_file()
                else:
                    # Check direct path as well (edge case: "folder" blob)
                    try:
                        self._fs.get_file_client(azure_path).get_file_properties()
                        found = True
                    except Exception:
                        pass

                if not found and not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

    # endregion

    # region: listing operations

    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        with self._errors(path):
            azure_path = self._azure_path(path)
            try:
                paths = self._fs.get_paths(path=azure_path or "/", recursive=recursive)
                for p in paths:
                    if not getattr(p, "is_directory", False):
                        rel = str(p.name)
                        yield self._props_to_fileinfo(p, rel)
            except Exception as exc:
                mapped = self._classify(exc, path)
                if isinstance(mapped, NotFound):
                    return
                raise mapped from None

    def list_folders(self, path: str) -> Iterator[str]:
        with self._errors(path):
            azure_path = self._azure_path(path)
            try:
                paths = self._fs.get_paths(path=azure_path or "/", recursive=False)
                for p in paths:
                    if getattr(p, "is_directory", False):
                        folder_path = str(p.name)
                        folder_name = folder_path.rstrip("/").rsplit("/", 1)[-1]
                        yield folder_name
            except Exception as exc:
                mapped = self._classify(exc, path)
                if isinstance(mapped, NotFound):
                    return
                raise mapped from None

    # endregion

    # region: metadata

    def get_file_info(self, path: str) -> FileInfo:
        with self._errors(path):
            fc = self._get_file_client(path)
            props = fc.get_file_properties()
            if getattr(props, "is_directory", False):
                raise NotFound(f"File not found: {path}", path=path, backend=self.name)
            return self._props_to_fileinfo(props, path)

    def get_folder_info(self, path: str) -> FolderInfo:
        with self._errors(path):
            azure_path = self._azure_path(path)

            if self._hns:
                dc = self._fs.get_directory_client(azure_path)
                dc.get_directory_properties()  # raises if not found

            # Gather stats from files under this path
            paths = list(self._fs.get_paths(path=azure_path or "/", recursive=True))
            file_count = 0
            total_size = 0
            latest_modified: datetime | None = None
            for p in paths:
                if not getattr(p, "is_directory", False):
                    file_count += 1
                    total_size += getattr(p, "content_length", 0) or 0
                    modified = getattr(p, "last_modified", None)
                    if modified is not None:
                        if modified.tzinfo is None:
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
        with self._errors(src):
            src_fc = self._get_file_client(src)
            # Check source exists
            src_fc.get_file_properties()

            dst_fc = self._get_file_client(dst)
            if not overwrite:
                try:
                    dst_fc.get_file_properties()
                    raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
                except AlreadyExists:
                    raise
                except Exception:
                    pass

            if self._hns:
                # Atomic rename
                new_name = f"{self._container}/{self._azure_path(dst)}"
                src_fc.rename_file(new_name)
            else:
                # Copy + delete
                dst_fc.upload_data(src_fc.download_file().readall(), overwrite=True)
                src_fc.delete_file()

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._errors(src):
            src_fc = self._get_file_client(src)
            # Check source exists
            src_fc.get_file_properties()

            dst_fc = self._get_file_client(dst)
            if not overwrite:
                try:
                    dst_fc.get_file_properties()
                    raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
                except AlreadyExists:
                    raise
                except Exception:
                    pass

            # Server-side copy via start_copy
            dst_fc.upload_data(src_fc.download_file().readall(), overwrite=True)

    # endregion

    # region: lifecycle

    def close(self) -> None:
        if self._fs_client is not None:
            with contextlib.suppress(Exception):
                self._fs_client.close()
            self._fs_client = None
        if self._service_client is not None:
            with contextlib.suppress(Exception):
                self._service_client.close()
            self._service_client = None
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
