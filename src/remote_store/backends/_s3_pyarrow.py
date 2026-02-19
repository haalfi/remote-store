"""Hybrid S3 backend using PyArrow (data path) and s3fs (control path)."""

from __future__ import annotations

import io
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


class S3PyArrowBackend(Backend):
    """Hybrid S3 backend: PyArrow for reads/writes/copies, s3fs for listing/metadata.

    Drop-in alternative to ``S3Backend`` with the same constructor signature.
    Uses PyArrow's C++ S3 filesystem for data-path operations (higher throughput
    for large files) and s3fs for control-path operations (listing, metadata,
    deletion).

    :param bucket: S3 bucket name (required, non-empty).
    :param endpoint_url: Custom endpoint URL (e.g. for MinIO).
    :param key: AWS access key ID.
    :param secret: AWS secret access key.
    :param region_name: AWS region name.
    :param client_options: Additional options passed to s3fs.
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        key: str | None = None,
        secret: str | None = None,
        region_name: str | None = None,
        client_options: dict[str, Any] | None = None,
    ) -> None:
        if not bucket or not bucket.strip():
            raise ValueError("bucket must be a non-empty string")
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._key = key
        self._secret = secret
        self._region_name = region_name
        self._client_options = client_options or {}
        self._pa_fs_instance: Any = None
        self._s3fs_instance: Any = None

    @property
    def name(self) -> str:
        return "s3-pyarrow"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # region: lazy filesystems
    @property
    def _pa_fs(self) -> Any:
        """Lazy PyArrow S3FileSystem."""
        if self._pa_fs_instance is None:
            from pyarrow.fs import S3FileSystem as PyArrowS3  # type: ignore[import-untyped]

            kwargs: dict[str, Any] = {}
            if self._key is not None:
                kwargs["access_key"] = self._key
            if self._secret is not None:
                kwargs["secret_key"] = self._secret
            if self._region_name is not None:
                kwargs["region"] = self._region_name
            if self._endpoint_url is not None:
                endpoint = self._endpoint_url
                # PyArrow uses endpoint_override (host:port) and scheme separately
                if endpoint.startswith("http://"):
                    kwargs["scheme"] = "http"
                    kwargs["endpoint_override"] = endpoint[len("http://") :]
                elif endpoint.startswith("https://"):  # pragma: no cover -- tests use http
                    kwargs["scheme"] = "https"
                    kwargs["endpoint_override"] = endpoint[len("https://") :]
                else:  # pragma: no cover -- tests always have scheme prefix
                    kwargs["endpoint_override"] = endpoint
            kwargs.setdefault("anonymous", False)
            self._pa_fs_instance = PyArrowS3(**kwargs)
        return self._pa_fs_instance

    @property
    def _s3fs(self) -> Any:
        """Lazy s3fs S3FileSystem."""
        if self._s3fs_instance is None:
            import s3fs  # type: ignore[import-untyped]

            opts: dict[str, Any] = dict(self._client_options)
            if self._endpoint_url is not None:
                opts["endpoint_url"] = self._endpoint_url
            if self._key is not None:
                opts["key"] = self._key
            if self._secret is not None:
                opts["secret"] = self._secret
            if self._region_name is not None:
                client_kwargs: dict[str, Any] = opts.setdefault("client_kwargs", {})
                client_kwargs["region_name"] = self._region_name
            opts.setdefault("anon", False)
            self._s3fs_instance = s3fs.S3FileSystem(**opts)
        return self._s3fs_instance

    # endregion

    # region: path helpers
    def _s3_path(self, path: str) -> str:
        """Build bucket/key path for s3fs."""
        if path:
            return f"{self._bucket}/{path}"
        return self._bucket  # pragma: no cover -- tests always provide a path

    def _pa_path(self, path: str) -> str:
        """Build bucket/key path for PyArrow."""
        if path:
            return f"{self._bucket}/{path}"
        return self._bucket  # pragma: no cover -- tests always provide a path

    def to_key(self, native_path: str) -> str:
        prefix = f"{self._bucket}/"
        if native_path.startswith(prefix):
            return native_path[len(prefix) :]
        return native_path

    # endregion

    # region: error mapping
    @contextmanager
    def _s3fs_errors(self, path: str = "") -> Iterator[None]:
        """Map s3fs/botocore exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:
            raise
        except FileNotFoundError:
            raise NotFound(f"Not found: {path}", path=path, backend=self.name) from None
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive; moto raises standard errors
            raise self._classify_error(exc, path) from None

    @contextmanager
    def _pyarrow_errors(self, path: str = "") -> Iterator[None]:
        """Map PyArrow exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:  # pragma: no cover -- passthrough
            raise
        except FileNotFoundError:
            raise NotFound(f"Not found: {path}", path=path, backend=self.name) from None
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        except OSError as exc:  # pragma: no cover -- moto raises FileNotFoundError directly
            msg = str(exc).lower()
            if "404" in msg or "not found" in msg or "no such" in msg or "path does not exist" in msg:
                raise NotFound(f"Not found: {path}", path=path, backend=self.name) from None
            if "403" in msg or "access denied" in msg:
                raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
            if any(kw in msg for kw in ("endpoint", "connect", "timeout", "dns", "name or service")):
                raise BackendUnavailable(str(exc), path=path, backend=self.name) from None
            raise RemoteStoreError(str(exc), path=path, backend=self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive
            raise self._classify_error(exc, path) from None

    def _classify_error(self, exc: Exception, path: str) -> RemoteStoreError:  # pragma: no cover
        """Classify an unknown exception into a remote_store error type."""
        msg = str(exc).lower()
        if "404" in msg or "nosuchkey" in msg or "nosuchbucket" in msg or "not found" in msg:
            return NotFound(f"Not found: {path}", path=path, backend=self.name)
        if "403" in msg or "accessdenied" in msg or "access denied" in msg:
            return PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name)
        if any(kw in msg for kw in ("endpoint", "connect", "timeout", "dns", "name or service")):
            return BackendUnavailable(str(exc), path=path, backend=self.name)
        return RemoteStoreError(str(exc), path=path, backend=self.name)

    # endregion

    # region: helpers
    @staticmethod
    def _read_content(content: WritableContent) -> bytes:
        if isinstance(content, bytes):
            return content
        return content.read()

    def _info_to_fileinfo(self, info: dict[str, Any], path: str) -> FileInfo:
        """Convert an s3fs info dict to a FileInfo."""
        name = path.rsplit("/", 1)[-1] if "/" in path else path
        size = info.get("size", info.get("Size", 0)) or 0
        modified = info.get("LastModified", info.get("last_modified"))
        if isinstance(modified, str):  # pragma: no cover -- moto returns datetime objects
            modified = datetime.fromisoformat(modified)
        if modified is not None and modified.tzinfo is None:  # pragma: no cover -- moto includes tzinfo
            modified = modified.replace(tzinfo=timezone.utc)
        if modified is None:  # pragma: no cover -- moto always provides LastModified
            modified = datetime.now(tz=timezone.utc)
        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=int(size),
            modified_at=modified,
        )

    # endregion

    # region: existence checks (s3fs)
    def exists(self, path: str) -> bool:
        with self._s3fs_errors(path):
            return bool(self._s3fs.exists(self._s3_path(path)))

    def is_file(self, path: str) -> bool:
        with self._s3fs_errors(path):
            try:
                info = self._s3fs.info(self._s3_path(path))
                return bool(info.get("type") == "file")
            except FileNotFoundError:
                return False

    def is_folder(self, path: str) -> bool:
        with self._s3fs_errors(path):
            try:
                info = self._s3fs.info(self._s3_path(path))
                return bool(info.get("type") == "directory")
            except FileNotFoundError:
                return False

    # endregion

    # region: read operations (pyarrow)
    def read(self, path: str) -> BinaryIO:
        with self._pyarrow_errors(path):
            stream = self._pa_fs.open_input_stream(self._pa_path(path))
            data = stream.read()
            return io.BytesIO(data)

    def read_bytes(self, path: str) -> bytes:
        with self._pyarrow_errors(path):
            stream = self._pa_fs.open_input_stream(self._pa_path(path))
            return bytes(stream.read())

    # endregion

    # region: write operations (pyarrow data, s3fs checks)
    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        with self._s3fs_errors(path):
            if not overwrite and self._s3fs.exists(self._s3_path(path)):
                raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        data = self._read_content(content)
        with self._pyarrow_errors(path):
            out = self._pa_fs.open_output_stream(self._pa_path(path))
            out.write(data)
            out.close()

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        # S3 PUT is inherently atomic (S3PA-013)
        self.write(path, content, overwrite=overwrite)

    # endregion

    # region: delete operations (s3fs)
    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        with self._s3fs_errors(path):
            if not self._s3fs.exists(self._s3_path(path)):
                if not missing_ok:
                    raise NotFound(f"File not found: {path}", path=path, backend=self.name)
                return
            self._s3fs.rm(self._s3_path(path))

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._s3fs_errors(path):
            s3_path = self._s3_path(path)
            if not self._s3fs.exists(s3_path):
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
                return
            if recursive:
                self._s3fs.rm(s3_path, recursive=True)
            else:
                # Non-recursive: fail if folder has contents
                contents = self._s3fs.ls(s3_path, detail=True)
                if contents:
                    raise RemoteStoreError(
                        f"Folder not empty: {path}",
                        path=path,
                        backend=self.name,
                    )

    # endregion

    # region: listing operations (s3fs)
    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        try:
            s3_path = self._s3_path(path)
            if not self._s3fs.exists(s3_path):
                return
            if recursive:
                results: dict[str, Any] = self._s3fs.find(s3_path, detail=True)
                for s3_key, info in results.items():
                    if info.get("type") == "file":
                        rel = self.to_key(s3_key)
                        yield self._info_to_fileinfo(info, rel)
            else:
                entries: list[dict[str, Any]] = self._s3fs.ls(s3_path, detail=True)
                for info in entries:
                    if info.get("type") == "file":
                        rel = self.to_key(info["name"])
                        yield self._info_to_fileinfo(info, rel)
        except RemoteStoreError:  # pragma: no cover -- defensive
            raise
        except FileNotFoundError:  # pragma: no cover -- checked via exists()
            return
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive
            raise self._classify_error(exc, path) from None

    def list_folders(self, path: str) -> Iterator[str]:
        try:
            s3_path = self._s3_path(path)
            if not self._s3fs.exists(s3_path):
                return
            entries: list[dict[str, Any]] = self._s3fs.ls(s3_path, detail=True)
            for info in entries:
                if info.get("type") == "directory":
                    folder_name = info["name"].rstrip("/")
                    folder_name = folder_name.rsplit("/", 1)[-1]
                    yield folder_name
        except RemoteStoreError:  # pragma: no cover -- defensive
            raise
        except FileNotFoundError:  # pragma: no cover -- checked via exists()
            return
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive
            raise self._classify_error(exc, path) from None

    # endregion

    # region: metadata (s3fs)
    def get_file_info(self, path: str) -> FileInfo:
        with self._s3fs_errors(path):
            info = self._s3fs.info(self._s3_path(path))
            if info.get("type") != "file":  # pragma: no cover -- s3fs raises FileNotFoundError first
                raise NotFound(f"File not found: {path}", path=path, backend=self.name)
            return self._info_to_fileinfo(info, path)

    def get_folder_info(self, path: str) -> FolderInfo:
        with self._s3fs_errors(path):
            s3_path = self._s3_path(path)
            if not self._s3fs.exists(s3_path):
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
            results: dict[str, Any] = self._s3fs.find(s3_path, detail=True)
            file_count = 0
            total_size = 0
            latest_modified: datetime | None = None
            for _key, info in results.items():
                if info.get("type") == "file":
                    file_count += 1
                    total_size += info.get("size", 0) or 0
                    modified = info.get("LastModified", info.get("last_modified"))
                    if isinstance(modified, str):  # pragma: no cover -- moto returns datetime
                        modified = datetime.fromisoformat(modified)
                    if modified is not None:
                        if modified.tzinfo is None:  # pragma: no cover -- moto includes tzinfo
                            modified = modified.replace(tzinfo=timezone.utc)
                        if latest_modified is None or modified > latest_modified:
                            latest_modified = modified
            if file_count == 0:  # pragma: no cover -- checked via exists() above
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
        # Existence checks via s3fs, copy via pyarrow, delete via s3fs
        with self._s3fs_errors(src):
            if not self._s3fs.exists(self._s3_path(src)):
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if not overwrite and self._s3fs.exists(self._s3_path(dst)):
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
        with self._pyarrow_errors(src):
            self._pa_fs.copy_file(self._pa_path(src), self._pa_path(dst))
        with self._s3fs_errors(src):
            self._s3fs.rm(self._s3_path(src))

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._s3fs_errors(src):
            if not self._s3fs.exists(self._s3_path(src)):
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if not overwrite and self._s3fs.exists(self._s3_path(dst)):
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
        with self._pyarrow_errors(src):
            self._pa_fs.copy_file(self._pa_path(src), self._pa_path(dst))

    # endregion

    # region: lifecycle
    def close(self) -> None:
        if self._s3fs_instance is not None:
            self._s3fs_instance.clear_instance_cache()
            self._s3fs_instance = None
        self._pa_fs_instance = None

    def unwrap(self, type_hint: type[T]) -> T:
        import s3fs
        from pyarrow.fs import S3FileSystem as PyArrowS3

        if type_hint is PyArrowS3:
            return self._pa_fs  # type: ignore[no-any-return]
        if type_hint is s3fs.S3FileSystem:
            return self._s3fs  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend 's3-pyarrow' does not expose native handle of type {type_hint.__name__}. "
            f"Supported: pyarrow.fs.S3FileSystem, s3fs.S3FileSystem.",
            capability="unwrap",
            backend=self.name,
        )

    # endregion
