"""Azure Storage backend -- Blob SDK for non-HNS, DataLake SDK for HNS."""

from __future__ import annotations

import contextlib
import io
import logging
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, TypeVar, cast

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RetryPolicy, Secret, _reveal
from remote_store._errors import (
    AlreadyExists,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
from remote_store._path import RemotePath
from remote_store._stream import _ErrorMappingStream
from remote_store.backends._azure_common import (
    _build_azure_write_result,
    build_azure_retry,
    classify_azure_error,
    props_to_fileinfo,
    resolve_credential,
    validate_azure_params,
)
from remote_store.backends._azure_common import (
    azure_path as _azure_path_fn,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from remote_store._resolution import ResolutionPlan
    from remote_store._types import WritableContent

T = TypeVar("T")

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.SEEKABLE_READ, Capability.ATOMIC_MOVE})

log = logging.getLogger(__name__)

# Staged-block upload granularity — intentionally separate from _COPY_BUFSIZE.
# _COPY_BUFSIZE (256 KiB) controls Python-level pipe chunking for Local/SFTP/S3.
# _AZURE_BLOCK_SIZE controls HTTP PUT request size for the Azure staged-block
# protocol; the Azure SDK reads the source stream in this-sized chunks.
# 1 MiB: SDK peak ≈ 2 × 1 MiB = 2 MiB, within the 4.55 MiB lazy threshold
# (65% × 7 MiB min file).  Yields ~4× fewer staged-block HTTP requests vs
# the previous 256 KiB value.  Users can override via client_options.
_AZURE_BLOCK_SIZE = 1 * 1024 * 1024  # 1 MiB


class _ByteCountingIO:
    """Wraps a BinaryIO and counts bytes consumed — used to populate WriteResult.size."""

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream
        self.count: int = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._stream.read(size)
        self.count += len(chunk)
        return chunk


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


class _AzureRangeReader(io.RawIOBase):
    """Seekable reader using Azure Blob SDK range requests.

    Each ``readinto()`` issues a single HTTP Range request via
    ``download_blob(offset=, length=)``.  No data is downloaded until
    ``read()`` is called, making this ideal for PyArrow's
    ``PythonFile.read_at(nbytes, offset)`` which seeks then reads small
    byte ranges for Parquet column pruning.
    """

    def __init__(self, blob_client: Any, file_size: int, max_concurrency: int = 1) -> None:
        self._bc = blob_client
        self._size = file_size
        self._pos = 0
        self._max_concurrency = max_concurrency

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:  # SEEK_SET
            self._pos = offset
        elif whence == 1:  # SEEK_CUR
            self._pos += offset
        elif whence == 2:  # SEEK_END
            self._pos = self._size + offset
        self._pos = max(0, min(self._pos, self._size))
        return self._pos

    def tell(self) -> int:
        return self._pos

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        remaining = self._size - self._pos
        if remaining <= 0:
            return 0
        length = min(len(b), remaining)
        try:
            data = self._bc.download_blob(
                offset=self._pos,
                length=length,
                max_concurrency=self._max_concurrency,
            ).readall()
        except OSError:
            raise
        except Exception as exc:
            # Azure SDK raises AzureError subclasses (HttpResponseError,
            # ResourceNotFoundError, etc.) which are not OSError.
            # Re-raise as OSError so _ErrorMappingStream can catch and
            # classify them via the backend's _classify() method.
            raise OSError(str(exc)) from exc
        n = len(data)
        b[:n] = data
        self._pos += n
        return n

    def close(self) -> None:
        if not self.closed:
            self._bc = None
            super().close()


class AzureBackend(Backend):
    """Azure Storage backend.

    Uses the Blob SDK for non-HNS accounts (plain Blob Storage, Azurite) and
    the DataLake SDK for HNS accounts (ADLS Gen2) to get atomic rename and
    real directory support.

    ``move()`` on non-HNS accounts is implemented as a server-side copy
    followed by a blob delete.  This is non-atomic: a failure between the
    two steps may leave both source and destination present.  HNS accounts
    use ``rename_file`` which is atomic, but since the backend cannot
    guarantee HNS at construction time, ``ATOMIC_MOVE`` is not declared.

    Args:
        container: Azure Storage container name (required, non-empty).
        account_name: Storage account name.
        account_url: Full account URL (e.g. ``https://myaccount.dfs.core.windows.net``).
        account_key: Storage account key.
        sas_token: Shared Access Signature token.
        connection_string: Azure Storage connection string.
        credential: Any credential object (e.g. ``DefaultAzureCredential()``).
        client_options: Additional options passed to service clients.
            The library sets ``max_single_put_size``, ``max_block_size``,
            and ``min_large_block_upload_threshold`` defaults for streaming
            memory discipline; user-supplied values take precedence.
        max_concurrency: Maximum number of parallel connections for
            uploads and downloads (default ``1`` -- sequential).
    """

    CAPABILITIES: ClassVar[CapabilitySet] = _ALL_CAPABILITIES

    def __init__(
        self,
        container: str,
        *,
        account_name: str | None = None,
        account_url: str | None = None,
        account_key: str | Secret | None = None,
        sas_token: str | Secret | None = None,
        connection_string: str | Secret | None = None,
        credential: Any | None = None,
        client_options: dict[str, Any] | None = None,
        retry: RetryPolicy | None = None,
        max_concurrency: int = 1,
    ) -> None:
        validate_azure_params(container, account_name, account_url, connection_string, max_concurrency)
        self._container = container
        self._account_name = account_name
        self._account_url = account_url
        self._account_key = _reveal(account_key)
        self._sas_token = _reveal(sas_token)
        self._connection_string = _reveal(connection_string)
        self._credential = credential
        self._client_options = client_options or {}
        self._retry = retry
        self._max_concurrency = max_concurrency
        # Lazy instances
        self._blob_service_instance: Any = None
        self._cc_instance: Any = None
        self._datalake_service_instance: Any = None
        self._fs_instance: Any = None
        self._hns_enabled: bool | None = None
        self._resolved_credential: Any = None

    # region: properties

    @property
    def name(self) -> str:
        return "azure"

    @property
    def capabilities(self) -> CapabilitySet:
        return self.CAPABILITIES

    # endregion

    # region: public methods

    def check_health(self) -> None:
        with self._errors():
            if self._hns:
                self._fs.get_file_system_properties()
            else:
                self._cc.get_container_properties()

    def to_key(self, native_path: str) -> str:
        prefix = f"{self._container}/"
        if native_path.startswith(prefix):
            return native_path[len(prefix) :]
        return native_path

    def native_path(self, path: str) -> str:
        if path:
            return f"{self._container}/{path}"
        return self._container

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` with Azure-specific details.

        Args:
            path: Backend-relative key.

        Returns:
            Plan with ``kind="azure"`` and ``details`` containing
            ``container`` and ``account_url``.
        """
        from remote_store._resolution import ResolutionPlan as _RP
        from remote_store._resolution import _strip_userinfo

        return _RP(
            kind="azure",
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={
                "container": self._container,
                "account_url": _strip_userinfo(self._account_url),
            },
        )

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
                except Exception:  # noqa: BLE001
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
                except Exception:  # noqa: BLE001
                    return False
            else:
                prefix = azure_path.rstrip("/") + "/"
                blobs = self._cc.list_blobs(name_starts_with=prefix, results_per_page=1)
                return any(True for _ in blobs)

    def read(self, path: str) -> BinaryIO:
        with self._errors(path):
            bc = self._blob_client(path)
            if self._hns:  # pragma: no cover -- HNS only
                from azure.core.exceptions import ResourceNotFoundError

                try:
                    props = bc.get_blob_properties()
                    blob_meta = getattr(props, "metadata", None) or {}
                    if blob_meta.get("hdi_isfolder"):
                        raise InvalidPath(f"Cannot read — '{path}' is a directory", path=path, backend=self.name)
                except (InvalidPath, ResourceNotFoundError):
                    raise
                except Exception:  # noqa: BLE001
                    pass  # Let the download attempt reveal the real error
            downloader = bc.download_blob(max_concurrency=self._max_concurrency)
            raw = _AzureBinaryIO(downloader.chunks())
            try:
                ems = _ErrorMappingStream(raw, self._classify, path)
                return io.BufferedReader(cast(io.RawIOBase, ems))  # noqa: TC006
            except BaseException:
                with contextlib.suppress(Exception):
                    raw.close()
                raise

    def read_seekable(self, path: str) -> BinaryIO:
        with self._errors(path):
            bc = self._blob_client(path)
            props = bc.get_blob_properties()
            blob_meta = getattr(props, "metadata", None) or {}
            if blob_meta.get("hdi_isfolder"):  # pragma: no cover -- HNS only
                raise InvalidPath(f"Cannot read — '{path}' is a directory", path=path, backend=self.name)
            file_size = props.size
            raw = _AzureRangeReader(bc, file_size, self._max_concurrency)
            # No BufferedReader: PyArrow's PythonFile handles unbuffered
            # RawIOBase directly, and BufferedReader's seek-invalidates-buffer
            # behavior would turn each PythonFile.read_at() into a new HTTP
            # request even for adjacent reads. Matches S3PyArrowBackend pattern.
            return cast(BinaryIO, _ErrorMappingStream(raw, self._classify, path))  # noqa: TC006

    def read_bytes(self, path: str) -> bytes:
        with self._errors(path):
            bc = self._blob_client(path)
            downloader = bc.download_blob(max_concurrency=self._max_concurrency)
            data = bytes(downloader.readall())
            if self._hns:  # pragma: no cover -- HNS only
                # BE-021: file-API operations on an HNS directory path must
                # raise InvalidPath. download_blob() succeeds (directory marker
                # is a 0-byte blob), so inspect response metadata post-download.
                props = getattr(downloader, "properties", None)
                blob_meta = getattr(props, "metadata", None) or {}
                if blob_meta.get("hdi_isfolder"):
                    raise InvalidPath(f"Cannot read — '{path}' is a directory", path=path, backend=self.name)
            return data

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        from azure.core.exceptions import ResourceNotFoundError

        with self._errors(path):
            bc = self._blob_client(path)
            if self._hns:
                try:
                    props = bc.get_blob_properties()
                    blob_meta = getattr(props, "metadata", None) or {}
                    if blob_meta.get("hdi_isfolder"):
                        raise InvalidPath(
                            f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name
                        )
                    if not overwrite:
                        raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except (InvalidPath, AlreadyExists):
                    raise
                except ResourceNotFoundError:
                    pass  # Blob doesn't exist, proceed
            elif not overwrite:
                try:
                    bc.get_blob_properties()
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except AlreadyExists:
                    raise
                except ResourceNotFoundError:
                    pass  # Blob doesn't exist, proceed
            sdk_metadata = metadata or None
            if isinstance(content, bytes):
                size = len(content)
                resp = bc.upload_blob(
                    content, overwrite=True, max_concurrency=self._max_concurrency, metadata=sdk_metadata
                )
            else:
                counter = _ByteCountingIO(content)
                resp = bc.upload_blob(
                    counter, overwrite=True, max_concurrency=self._max_concurrency, metadata=sdk_metadata
                )
                size = counter.count
            return _build_azure_write_result(path, size, resp, metadata)

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        if not self._hns:
            # non-HNS: direct upload is atomic (PUT semantics)
            return self.write(path, content, overwrite=overwrite, metadata=metadata)

        # HNS: write to temp file via DFS, then atomic rename
        from azure.core.exceptions import ResourceNotFoundError

        with self._errors(path):
            bc = self._blob_client(path)
            try:
                props = bc.get_blob_properties()
                blob_meta = getattr(props, "metadata", None) or {}
                if blob_meta.get("hdi_isfolder"):
                    raise InvalidPath(f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name)
                if not overwrite:
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
            except (InvalidPath, AlreadyExists):
                raise
            except ResourceNotFoundError:
                pass  # Blob doesn't exist yet; proceed to temp upload + atomic rename

            azure_path = self._azure_path(path)
            basename = azure_path.rsplit("/", 1)[-1] if "/" in azure_path else azure_path
            parent = azure_path.rsplit("/", 1)[0] if "/" in azure_path else ""
            tmp_name = f".~tmp.{basename}.{uuid.uuid4().hex[:8]}"
            tmp_path = f"{parent}/{tmp_name}" if parent else tmp_name

            sdk_metadata = metadata or None
            size: int
            upload_target: Any
            if isinstance(content, bytes):
                size = len(content)
                upload_target = content
            else:
                _counter = _ByteCountingIO(content)
                upload_target = _counter
                size = 0  # set after upload

            tmp_fc = self._fs.get_file_client(tmp_path)
            try:
                tmp_fc.upload_data(
                    upload_target, overwrite=True, max_concurrency=self._max_concurrency, metadata=sdk_metadata
                )
                new_name = f"{self._container}/{azure_path}"
                tmp_fc.rename_file(new_name)
            except Exception:
                with contextlib.suppress(Exception):
                    tmp_fc.delete_file()
                raise

            if not isinstance(content, bytes):
                size = _counter.count
            # BUG-173: the rename above has already committed the write.  A
            # post-commit read failure (network blip, eventual consistency,
            # permissions) must not surface as a write failure -- retrying
            # would raise AlreadyExists (overwrite=False) or silently
            # double-write.  Fall back to a WriteResult without rich fields.
            dst_fc = self._fs.get_file_client(azure_path)
            props_dict: dict[str, Any] = {}
            try:
                props = dst_fc.get_file_properties()
                props_dict = {
                    "etag": getattr(props, "etag", None),
                    "last_modified": getattr(props, "last_modified", None),
                }
            except Exception as exc:  # noqa: BLE001 -- post-commit read fallback
                log.warning(
                    "HNS write_atomic committed to %s but post-rename get_file_properties failed: %s",
                    path,
                    exc,
                )
            return _build_azure_write_result(path, size, props_dict, metadata)

    @contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        if not self._hns:
            # non-HNS: buffer then PUT (atomic by nature) -- SAW-011
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
                        pass
            buf: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(  # noqa: SIM115
                max_size=8 * 1024 * 1024,
            )
            try:
                yield cast(BinaryIO, buf)  # noqa: TC006
                buf.seek(0)
                self.write(path, cast(BinaryIO, buf), overwrite=overwrite)  # noqa: TC006
            finally:
                buf.close()
        else:
            # HNS: write to temp file via DFS, then atomic rename -- SAW-011
            from azure.core.exceptions import ResourceNotFoundError

            with self._errors(path):
                bc = self._blob_client(path)
                try:
                    props = bc.get_blob_properties()
                    blob_meta = getattr(props, "metadata", None) or {}
                    if blob_meta.get("hdi_isfolder"):
                        raise InvalidPath(
                            f"Cannot write — '{path}' exists as a directory",
                            path=path,
                            backend=self.name,
                        )
                    if not overwrite:
                        raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except (InvalidPath, AlreadyExists):
                    raise
                except ResourceNotFoundError:
                    pass  # Blob doesn't exist yet; proceed to temp upload + atomic rename

                azure_path = self._azure_path(path)
                basename = azure_path.rsplit("/", 1)[-1] if "/" in azure_path else azure_path
                parent = azure_path.rsplit("/", 1)[0] if "/" in azure_path else ""
                tmp_name = f".~tmp.{basename}.{uuid.uuid4().hex[:8]}"
                tmp_path = f"{parent}/{tmp_name}" if parent else tmp_name

            # Yield outside _errors() so user exceptions aren't remapped
            buf_hns: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(  # noqa: SIM115
                max_size=8 * 1024 * 1024,
            )
            try:
                yield cast(BinaryIO, buf_hns)  # noqa: TC006
                buf_hns.seek(0)
                with self._errors(path):
                    tmp_fc = self._fs.get_file_client(tmp_path)
                    try:
                        tmp_fc.upload_data(buf_hns, overwrite=True, max_concurrency=self._max_concurrency)
                        new_name = f"{self._container}/{azure_path}"
                        tmp_fc.rename_file(new_name)
                    except Exception:
                        with contextlib.suppress(Exception):
                            tmp_fc.delete_file()
                        raise
            finally:
                buf_hns.close()

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        with self._errors(path):
            bc = self._blob_client(path)
            if self._hns:  # pragma: no cover -- HNS only
                from azure.core.exceptions import ResourceNotFoundError

                try:
                    props = bc.get_blob_properties()
                    blob_meta = getattr(props, "metadata", None) or {}
                    if blob_meta.get("hdi_isfolder"):
                        raise InvalidPath(f"Cannot delete — '{path}' is a directory", path=path, backend=self.name)
                except (InvalidPath, ResourceNotFoundError):
                    raise
                except Exception:  # noqa: BLE001
                    pass  # Let the delete_blob() call reveal the real error
            try:
                bc.delete_blob()
            except Exception as exc:  # noqa: BLE001
                mapped = self._classify(exc, path)
                if isinstance(mapped, NotFound):
                    if not missing_ok:
                        raise mapped from None
                    return
                # BE-021: HNS non-empty directory yields DirectoryIsNotEmpty (409).
                # The file-API delete() must raise InvalidPath, not AlreadyExists.
                from azure.core.exceptions import HttpResponseError

                if isinstance(exc, HttpResponseError) and getattr(exc, "error_code", None) == "DirectoryIsNotEmpty":
                    raise InvalidPath(
                        f"Cannot delete — '{path}' is a directory", path=path, backend=self.name
                    ) from None
                raise mapped from None  # pragma: no cover

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._errors(path):
            azure_path = self._azure_path(path)

            if self._hns:  # pragma: no cover -- HNS only
                dc = self._fs.get_directory_client(azure_path)
                try:
                    dc.get_directory_properties()
                except Exception as exc:  # noqa: BLE001
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
                has_children = False
                for _ in self._cc.list_blobs(name_starts_with=prefix, results_per_page=1):
                    has_children = True
                    break
                if has_children:
                    if not recursive:
                        raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend=self.name)
                    for blob in self._cc.list_blobs(name_starts_with=prefix):
                        self._cc.get_blob_client(blob.name).delete_blob()
                elif not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        with self._errors(path):
            azure_path = self._azure_path(path)
            prefix = (azure_path.rstrip("/") + "/") if azure_path else ""

            if self._hns:  # pragma: no cover -- HNS only
                try:
                    paths = self._fs.get_paths(path=azure_path or "/", recursive=recursive)
                    for p in paths:
                        if not getattr(p, "is_directory", False):
                            if recursive and max_depth is not None:
                                rel = str(p.name)[len(prefix) :]
                                depth = rel.count("/")
                                if depth > max_depth:
                                    continue
                            yield self._props_to_fileinfo(p, str(p.name))
                except Exception as exc:  # noqa: BLE001
                    mapped = self._classify(exc, path)
                    if isinstance(mapped, NotFound):
                        return
                    raise mapped from None
            elif recursive:
                blobs = self._cc.list_blobs(name_starts_with=prefix)
                for blob in blobs:
                    if max_depth is not None:
                        rel = blob.name[len(prefix) :]
                        depth = rel.count("/")
                        if depth > max_depth:
                            continue
                    yield self._props_to_fileinfo(blob, blob.name)
            else:
                blobs = self._cc.walk_blobs(name_starts_with=prefix)
                for item in blobs:
                    if not getattr(item, "prefix", None):
                        yield self._props_to_fileinfo(item, item.name)

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        with self._errors(path):
            azure_path = self._azure_path(path)
            prefix = (azure_path.rstrip("/") + "/") if azure_path else ""

            if self._hns:  # pragma: no cover -- HNS only
                try:
                    paths = self._fs.get_paths(path=azure_path or "/", recursive=False)
                    for p in paths:
                        if getattr(p, "is_directory", False):
                            rel = str(p.name).rstrip("/")
                            folder_name = rel.rsplit("/", 1)[-1]
                            yield FolderEntry(path=RemotePath(rel), name=folder_name)
                except Exception as exc:  # noqa: BLE001
                    mapped = self._classify(exc, path)
                    if isinstance(mapped, NotFound):
                        return
                    raise mapped from None
            else:
                blobs = self._cc.walk_blobs(name_starts_with=prefix)
                for item in blobs:
                    if getattr(item, "prefix", None):
                        rel = self.to_key(item.prefix.rstrip("/"))
                        folder_name = rel.rsplit("/", 1)[-1]
                        yield FolderEntry(path=RemotePath(rel), name=folder_name)

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        with self._errors(path):
            azure_path = self._azure_path(path)
            prefix = (azure_path.rstrip("/") + "/") if azure_path else ""

            if self._hns:  # pragma: no cover -- HNS only
                try:
                    paths = self._fs.get_paths(path=azure_path or "/", recursive=False)
                    for p in paths:
                        if getattr(p, "is_directory", False):
                            rel = str(p.name).rstrip("/")
                            folder_name = rel.rsplit("/", 1)[-1]
                            yield FolderEntry(path=RemotePath(rel), name=folder_name)
                        else:
                            yield self._props_to_fileinfo(p, str(p.name))
                except Exception as exc:  # noqa: BLE001
                    mapped = self._classify(exc, path)
                    if isinstance(mapped, NotFound):
                        return
                    raise mapped from None
            else:
                blobs = self._cc.walk_blobs(name_starts_with=prefix)
                for item in blobs:
                    if getattr(item, "prefix", None):
                        rel = self.to_key(item.prefix.rstrip("/"))
                        folder_name = rel.rsplit("/", 1)[-1]
                        yield FolderEntry(path=RemotePath(rel), name=folder_name)
                    else:
                        yield self._props_to_fileinfo(item, item.name)

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        from remote_store._glob import extract_prefix, needs_recursive, pattern_to_regex

        prefix = extract_prefix(pattern)
        recursive = needs_recursive(pattern)
        compiled = pattern_to_regex(pattern)
        for info in self.list_files(prefix, recursive=recursive):
            if compiled.match(str(info.path)):
                yield info

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
            file_count = 0
            total_size = 0
            latest_modified: datetime | None = None

            if self._hns:  # pragma: no cover -- HNS only
                # DFS get_paths exposes is_directory inline; list_blobs would
                # silently count hdi_isfolder marker blobs as files (BUG-199).
                dc = self._fs.get_directory_client(azure_path)
                dc.get_directory_properties()  # raises if not found
                for p in self._fs.get_paths(path=azure_path or "/", recursive=True):
                    if getattr(p, "is_directory", False):
                        continue
                    file_count += 1
                    # Mirror props_to_fileinfo (_azure_common.py:127) attribute order so
                    # FolderInfo.total_size and FileInfo.size agree for the same path.
                    size = getattr(p, "size", None) or getattr(p, "content_length", 0) or 0
                    total_size += int(size)
                    modified = getattr(p, "last_modified", None)
                    if modified is not None:
                        if modified.tzinfo is None:
                            modified = modified.replace(tzinfo=timezone.utc)
                        if latest_modified is None or modified > latest_modified:
                            latest_modified = modified
            else:
                prefix = (azure_path.rstrip("/") + "/") if azure_path else ""
                for blob in self._cc.list_blobs(name_starts_with=prefix):
                    file_count += 1
                    total_size += blob.size or 0
                    modified = blob.last_modified
                    if modified is not None:
                        if modified.tzinfo is None:  # pragma: no cover
                            modified = modified.replace(tzinfo=timezone.utc)
                        if latest_modified is None or modified > latest_modified:
                            latest_modified = modified
                if file_count == 0:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

            return FolderInfo(
                path=RemotePath.from_backend_path(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest_modified,
            )

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
        # Close credential (e.g. DefaultAzureCredential holds transport sessions).
        if self._resolved_credential is not None:
            close = getattr(self._resolved_credential, "close", None)
            if close is not None:
                with contextlib.suppress(Exception):
                    close()
            self._resolved_credential = None

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

    # region: dunder methods

    def __del__(self) -> None:
        # Guard against interpreter shutdown: module globals may be None.
        try:
            has_clients = any(
                (
                    getattr(self, "_cc_instance", None),
                    getattr(self, "_blob_service_instance", None),
                    getattr(self, "_fs_instance", None),
                    getattr(self, "_datalake_service_instance", None),
                )
            )
            if not has_clients:
                return
        except Exception:  # noqa: BLE001
            return
        try:  # noqa: SIM105 — cannot use contextlib.suppress during shutdown
            self._del_cleanup()
        except Exception:  # noqa: BLE001
            pass

    def _del_cleanup(self) -> None:
        """Warn and inline-close clients; called by __del__ without contextlib."""
        try:
            import warnings

            warnings.warn(
                f"Unclosed {type(self).__name__}. Call .close() or use a context manager.",
                ResourceWarning,
                stacklevel=2,
            )
        except Exception:  # noqa: BLE001
            pass
        # Inline cleanup — cannot rely on contextlib.suppress during shutdown.
        for attr in ("_cc_instance", "_blob_service_instance", "_fs_instance", "_datalake_service_instance"):
            try:
                client = getattr(self, attr, None)
                if client is not None:
                    client.close()
            except Exception:  # noqa: BLE001
                pass
            try:  # noqa: SIM105 — cannot use contextlib during shutdown
                setattr(self, attr, None)
            except Exception:  # noqa: BLE001
                pass

    def __repr__(self) -> str:
        return (
            f"AzureBackend(container={self._container!r}, "
            f"account_name={self._account_name!r}, "
            f"account_key={'***' if self._account_key is not None else None!r}, "
            f"sas_token={'***' if self._sas_token is not None else None!r}, "
            f"connection_string={'***' if self._connection_string is not None else None!r}, "
            f"credential={'***' if self._credential is not None else None!r})"
        )

    # endregion

    # region: private helpers

    def _resolve_credential(self) -> Any:  # pragma: no cover -- only reached without connection_string
        """Return cached credential, creating it on first call."""
        if self._resolved_credential is None:
            self._resolved_credential = resolve_credential(
                self._credential,
                self._account_key,
                self._sas_token,
                is_async=False,
                backend_name=self.name,
            )
        return self._resolved_credential

    def _build_azure_retry(self) -> Any | None:
        """Build an Azure ExponentialRetry from the retry policy, or None."""
        return build_azure_retry(self._retry)

    @property
    def _blob_service(self) -> Any:
        """Lazy BlobServiceClient."""
        if self._blob_service_instance is None:
            from azure.storage.blob import BlobServiceClient

            opts: dict[str, Any] = dict(self._client_options)
            # BUG-161: force staged-block upload for large streams.
            _blk = _AZURE_BLOCK_SIZE
            opts.setdefault("max_single_put_size", _blk)
            opts.setdefault("max_block_size", _blk)
            opts.setdefault("min_large_block_upload_threshold", 1)  # 1 byte = always stage
            azure_retry = self._build_azure_retry()
            if azure_retry is not None and "retry_policy" not in opts:
                opts["retry_policy"] = azure_retry
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

    @property
    def _datalake_service(self) -> Any:  # pragma: no cover -- HNS only, requires ADLS Gen2
        """Lazy DataLakeServiceClient (only used for HNS accounts)."""
        if self._datalake_service_instance is None:
            from azure.storage.filedatalake import DataLakeServiceClient

            opts: dict[str, Any] = dict(self._client_options)
            _blk = _AZURE_BLOCK_SIZE
            opts.setdefault("max_single_put_size", _blk)
            opts.setdefault("max_block_size", _blk)
            opts.setdefault("min_large_block_upload_threshold", 1)  # 1 byte = always stage
            azure_retry = self._build_azure_retry()
            if azure_retry is not None and "retry_policy" not in opts:
                opts["retry_policy"] = azure_retry
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

    @property
    def _hns(self) -> bool:
        """Whether the storage account has Hierarchical Namespace enabled."""
        if self._hns_enabled is None:
            try:
                info = self._blob_service.get_account_information()
                self._hns_enabled = bool(info.get("is_hns_enabled", False))
            except Exception:  # noqa: BLE001
                log.warning(
                    "Failed to detect HNS status, falling back to non-HNS behavior",
                    exc_info=True,
                )
                self._hns_enabled = False
        return self._hns_enabled

    def _azure_path(self, path: str) -> str:
        """Normalize path for Azure (strip leading /, collapse double separators)."""
        return _azure_path_fn(path)

    @contextmanager
    def _errors(self, path: str = "") -> Iterator[None]:
        """Map Azure SDK exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._classify(exc, path) from None

    def _classify(self, exc: Exception, path: str) -> RemoteStoreError:
        """Classify an Azure SDK exception into a remote_store error type.

        When called via ``_ErrorMappingStream`` on an ``_AzureRangeReader``,
        the exception may be an ``OSError`` wrapping the original Azure SDK
        exception (via ``__cause__``).  Unwrap before matching.
        """
        return classify_azure_error(exc, path, self.name)

    def _blob_client(self, path: str) -> Any:
        """Get a BlobClient for the given path."""
        return self._cc.get_blob_client(self._azure_path(path))

    def _props_to_fileinfo(self, props: Any, path: str) -> FileInfo:
        """Convert blob/path properties to FileInfo."""
        return props_to_fileinfo(props, path)

    # endregion
