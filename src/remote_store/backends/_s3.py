"""S3-compatible object storage backend using s3fs."""

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


class S3Backend(Backend):
    """S3-compatible object storage backend using s3fs.

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
        self._fs_instance: Any = None

    @property
    def name(self) -> str:
        return "s3"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # region: lazy filesystem

    @property
    def _fs(self) -> Any:
        if self._fs_instance is None:
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
            self._fs_instance = s3fs.S3FileSystem(**opts)
        return self._fs_instance

    # endregion

    # region: path helpers

    def _s3_path(self, path: str) -> str:
        if path:
            return f"{self._bucket}/{path}"
        return self._bucket

    def _rel_path(self, s3_path: str) -> str:
        prefix = f"{self._bucket}/"
        if s3_path.startswith(prefix):
            return s3_path[len(prefix) :]
        return s3_path

    # endregion

    # region: error mapping

    @contextmanager
    def _errors(self, path: str = "") -> Iterator[None]:
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
        if isinstance(modified, str):
            modified = datetime.fromisoformat(modified)
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
            return bool(self._fs.exists(self._s3_path(path)))

    def is_file(self, path: str) -> bool:
        with self._errors(path):
            try:
                info = self._fs.info(self._s3_path(path))
                return bool(info.get("type") == "file")
            except FileNotFoundError:
                return False

    def is_folder(self, path: str) -> bool:
        with self._errors(path):
            try:
                info = self._fs.info(self._s3_path(path))
                return bool(info.get("type") == "directory")
            except FileNotFoundError:
                return False

    # endregion

    # region: read operations

    def read(self, path: str) -> BinaryIO:
        with self._errors(path):
            data = self._fs.cat_file(self._s3_path(path))
            return io.BytesIO(data)

    def read_bytes(self, path: str) -> bytes:
        with self._errors(path):
            return bytes(self._fs.cat_file(self._s3_path(path)))

    # endregion

    # region: write operations

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        with self._errors(path):
            if not overwrite and self._fs.exists(self._s3_path(path)):
                raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
            data = self._read_content(content)
            self._fs.pipe_file(self._s3_path(path), data)

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        # S3 PUT is inherently atomic (S3-010)
        self.write(path, content, overwrite=overwrite)

    # endregion

    # region: delete operations

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        with self._errors(path):
            if not self._fs.exists(self._s3_path(path)):
                if not missing_ok:
                    raise NotFound(f"File not found: {path}", path=path, backend=self.name)
                return
            self._fs.rm(self._s3_path(path))

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._errors(path):
            s3_path = self._s3_path(path)
            if not self._fs.exists(s3_path):
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
                return
            if recursive:
                self._fs.rm(s3_path, recursive=True)
            else:
                # Non-recursive: fail if folder has contents
                contents = self._fs.ls(s3_path, detail=True)
                if contents:
                    raise RemoteStoreError(
                        f"Folder not empty: {path}",
                        path=path,
                        backend=self.name,
                    )

    # endregion

    # region: listing operations

    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        try:
            s3_path = self._s3_path(path)
            if not self._fs.exists(s3_path):
                return
            if recursive:
                results: dict[str, Any] = self._fs.find(s3_path, detail=True)
                for s3_key, info in results.items():
                    if info.get("type") == "file":
                        rel = self._rel_path(s3_key)
                        yield self._info_to_fileinfo(info, rel)
            else:
                entries: list[dict[str, Any]] = self._fs.ls(s3_path, detail=True)
                for info in entries:
                    if info.get("type") == "file":
                        rel = self._rel_path(info["name"])
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
            if not self._fs.exists(s3_path):
                return
            entries: list[dict[str, Any]] = self._fs.ls(s3_path, detail=True)
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

    # region: metadata

    def get_file_info(self, path: str) -> FileInfo:
        with self._errors(path):
            info = self._fs.info(self._s3_path(path))
            if info.get("type") != "file":
                raise NotFound(f"File not found: {path}", path=path, backend=self.name)
            return self._info_to_fileinfo(info, path)

    def get_folder_info(self, path: str) -> FolderInfo:
        with self._errors(path):
            s3_path = self._s3_path(path)
            if not self._fs.exists(s3_path):
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
            results: dict[str, Any] = self._fs.find(s3_path, detail=True)
            file_count = 0
            total_size = 0
            latest_modified: datetime | None = None
            for _key, info in results.items():
                if info.get("type") == "file":
                    file_count += 1
                    total_size += info.get("size", 0) or 0
                    modified = info.get("LastModified", info.get("last_modified"))
                    if isinstance(modified, str):
                        modified = datetime.fromisoformat(modified)
                    if modified is not None:
                        if modified.tzinfo is None:
                            modified = modified.replace(tzinfo=timezone.utc)
                        if latest_modified is None or modified > latest_modified:
                            latest_modified = modified
            if file_count == 0:
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
            if not self._fs.exists(self._s3_path(src)):
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if not overwrite and self._fs.exists(self._s3_path(dst)):
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
            self._fs.copy(self._s3_path(src), self._s3_path(dst))
            self._fs.rm(self._s3_path(src))

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._errors(src):
            if not self._fs.exists(self._s3_path(src)):
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if not overwrite and self._fs.exists(self._s3_path(dst)):
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
            self._fs.copy(self._s3_path(src), self._s3_path(dst))

    # endregion

    # region: lifecycle

    def close(self) -> None:
        if self._fs_instance is not None:
            self._fs_instance.clear_instance_cache()
            self._fs_instance = None

    def unwrap(self, type_hint: type[T]) -> T:
        import s3fs

        if type_hint is s3fs.S3FileSystem:
            return self._fs  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend 's3' does not expose native handle of type {type_hint.__name__}. "
            f"Override unwrap() in your backend to provide native access.",
            capability="unwrap",
            backend=self.name,
        )

    # endregion
