"""S3-compatible object storage backend using s3fs."""

from __future__ import annotations

import base64
import io
import logging
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, BinaryIO, TypeVar, cast

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RetryPolicy, Secret, _reveal
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import ContentDigest, FileInfo, FolderEntry, FolderInfo
from remote_store._path import RemotePath
from remote_store._stream import _ErrorMappingStream

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._types import WritableContent

T = TypeVar("T")

_ALL_CAPABILITIES = CapabilitySet(set(Capability))

log = logging.getLogger(__name__)


class S3Backend(Backend):
    """S3-compatible object storage backend using s3fs.

    Args:
        bucket: S3 bucket name (required, non-empty).
        endpoint_url: Custom endpoint URL (e.g. for MinIO).
        key: AWS access key ID.
        secret: AWS secret access key.
        region_name: AWS region name.
        client_options: Additional options passed to s3fs.
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        key: str | Secret | None = None,
        secret: str | Secret | None = None,
        region_name: str | None = None,
        client_options: dict[str, Any] | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        if not bucket or not bucket.strip():
            raise ValueError("bucket must be a non-empty string")
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._key = _reveal(key)
        self._secret = _reveal(secret)
        self._region_name = region_name
        self._client_options = client_options or {}
        self._retry = retry
        self._fs_instance: Any = None

    # region: properties

    @property
    def name(self) -> str:
        return "s3"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # endregion

    # region: public methods

    def check_health(self) -> None:
        with self._errors():
            self._fs.s3.head_bucket(Bucket=self._bucket)

    def to_key(self, native_path: str) -> str:
        prefix = f"{self._bucket}/"
        if native_path.startswith(prefix):
            return native_path[len(prefix) :]
        return native_path

    def native_path(self, path: str) -> str:
        if path:
            return f"{self._bucket}/{path}"
        return self._bucket

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

    def read(self, path: str) -> BinaryIO:
        with self._errors(path):
            f: BinaryIO = self._fs.open(self._s3_path(path), "rb")
            raw = _ErrorMappingStream(f, self._classify_error, path)
            return io.BufferedReader(cast("io.RawIOBase", raw))

    def read_bytes(self, path: str) -> bytes:
        with self._errors(path):
            return bytes(self._fs.cat_file(self._s3_path(path)))

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        with self._errors(path):
            if not overwrite and self._fs.exists(self._s3_path(path)):
                raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
            if isinstance(content, bytes):
                self._fs.pipe_file(self._s3_path(path), content)
            else:
                with self._fs.open(self._s3_path(path), "wb") as f:
                    shutil.copyfileobj(content, f)

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        # S3 PUT is inherently atomic (S3-010)
        self.write(path, content, overwrite=overwrite)

    @contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        # S3 PUT is inherently atomic -- buffer then upload (SAW-010)
        with self._errors(path):
            if not overwrite and self._fs.exists(self._s3_path(path)):
                raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        buf: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(  # noqa: SIM115
            max_size=8 * 1024 * 1024,
        )
        try:
            yield cast("BinaryIO", buf)
            buf.seek(0)
            self.write(path, cast("BinaryIO", buf), overwrite=overwrite)
        finally:
            buf.close()

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
                    raise DirectoryNotEmpty(
                        f"Folder not empty: {path}",
                        path=path,
                        backend=self.name,
                    )

    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        try:
            s3_path = self._s3_path(path)
            if recursive:
                results: dict[str, Any] = self._fs.find(s3_path, detail=True)
                for s3_key, info in results.items():
                    if info.get("type") == "file":
                        rel = self.to_key(s3_key)
                        yield self._info_to_fileinfo(info, rel)
            else:
                entries: list[dict[str, Any]] = self._fs.ls(s3_path, detail=True)
                for info in entries:
                    if info.get("type") == "file":
                        rel = self.to_key(info["name"])
                        yield self._info_to_fileinfo(info, rel)
        except RemoteStoreError:  # pragma: no cover -- defensive
            raise
        except FileNotFoundError:  # pragma: no cover -- s3fs returns empty for missing prefixes
            return
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive
            raise self._classify_error(exc, path) from None

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        try:
            s3_path = self._s3_path(path)
            entries: list[dict[str, Any]] = self._fs.ls(s3_path, detail=True)
            for info in entries:
                if info.get("type") == "directory":
                    rel = self.to_key(info["name"].rstrip("/"))
                    folder_name = rel.rsplit("/", 1)[-1]
                    yield FolderEntry(path=RemotePath(rel), name=folder_name)
        except RemoteStoreError:  # pragma: no cover -- defensive
            raise
        except FileNotFoundError:  # pragma: no cover -- s3fs returns empty for missing prefixes
            return
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive
            raise self._classify_error(exc, path) from None

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        try:
            s3_path = self._s3_path(path)
            entries: list[dict[str, Any]] = self._fs.ls(s3_path, detail=True)
            for info in entries:
                if info.get("type") == "file":
                    rel = self.to_key(info["name"])
                    yield self._info_to_fileinfo(info, rel)
                elif info.get("type") == "directory":
                    rel = self.to_key(info["name"].rstrip("/"))
                    folder_name = rel.rsplit("/", 1)[-1]
                    yield FolderEntry(path=RemotePath(rel), name=folder_name)
        except RemoteStoreError:  # pragma: no cover -- defensive
            raise
        except FileNotFoundError:  # pragma: no cover -- s3fs returns empty for missing prefixes
            return
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive
            raise self._classify_error(exc, path) from None

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
            raw = self._fs.call_s3(
                "head_object",
                Bucket=self._bucket,
                Key=path,
                ChecksumMode="ENABLED",
            )
            return self._head_to_fileinfo(raw, path)

    def get_folder_info(self, path: str) -> FolderInfo:
        # S3 folders are virtual (prefix-based), like Azure non-HNS.  An empty
        # folder is simply a prefix with no objects, so exists() already
        # returns False for truly non-existent prefixes.  Unlike Azure non-HNS
        # we don't raise NotFound for file_count==0 after the exists() check,
        # because s3fs.exists() verifies the prefix is valid.
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
            return FolderInfo(
                path=RemotePath.from_backend_path(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest_modified,
            )

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

    def close(self) -> None:
        if self._fs_instance is not None:
            self._fs_instance = None

    def unwrap(self, type_hint: type[T]) -> T:
        import s3fs  # type: ignore[import-untyped]

        if type_hint is s3fs.S3FileSystem:
            return self._fs  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend 's3' does not expose native handle of type {type_hint.__name__}. "
            f"Override unwrap() in your backend to provide native access.",
            capability="unwrap",
            backend=self.name,
        )

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        return (
            f"S3Backend(bucket={self._bucket!r}, "
            f"endpoint_url={self._endpoint_url!r}, "
            f"key={'***' if self._key is not None else None!r}, "
            f"secret={'***' if self._secret is not None else None!r}, "
            f"region_name={self._region_name!r})"
        )

    # endregion

    # region: private helpers

    @property
    def _fs(self) -> Any:
        if self._fs_instance is None:
            import s3fs

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
            if self._retry is not None:
                import botocore.config  # type: ignore[import-untyped]

                rp = self._retry
                if rp.backoff_base != 1.0 or rp.backoff_max != 60.0 or rp.jitter != 1.0 or rp.timeout is not None:
                    log.debug(
                        "S3 retry: backoff_base, backoff_max, jitter, timeout are not "
                        "mappable to botocore; only max_attempts is used",
                    )
                client_kwargs = opts.setdefault("client_kwargs", {})
                existing_config = client_kwargs.get("config")
                retry_config = botocore.config.Config(
                    retries={"max_attempts": rp.max_attempts, "mode": "standard"},
                )
                if existing_config is not None:
                    client_kwargs["config"] = existing_config.merge(retry_config)
                else:
                    client_kwargs["config"] = retry_config
            opts.setdefault("anon", False)
            self._fs_instance = s3fs.S3FileSystem(**opts)
        return self._fs_instance

    def _s3_path(self, path: str) -> str:
        if path:
            return f"{self._bucket}/{path}"
        return self._bucket

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
        except Exception as exc:
            raise self._classify_error(exc, path) from None

    def _classify_error(self, exc: Exception, path: str) -> RemoteStoreError:
        """Classify an unknown exception into a remote_store error type."""
        msg = str(exc).lower()
        if "404" in msg or "nosuchkey" in msg or "nosuchbucket" in msg or "not found" in msg:
            return NotFound(f"Not found: {path}", path=path, backend=self.name)
        if "403" in msg or "accessdenied" in msg or "access denied" in msg:
            return PermissionDenied(f"Permission denied: {path}", path=path, backend=self.name)
        if any(kw in msg for kw in ("endpoint", "connect", "timeout", "dns", "name or service")):
            return BackendUnavailable(str(exc), path=path, backend=self.name)
        return RemoteStoreError(str(exc), path=path, backend=self.name)

    def _info_to_fileinfo(self, info: dict[str, Any], path: str, *, digest: ContentDigest | None = None) -> FileInfo:
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
        # ETag: S3 returns it double-quoted (e.g. '"abc123"'); strip and lowercase.
        raw_etag = info.get("ETag") or info.get("etag")
        etag = raw_etag.strip('"').lower() if isinstance(raw_etag, str) else None
        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=int(size),
            modified_at=modified,
            etag=etag,
            digest=digest,
        )

    # S3-024: algorithm name → HeadObject response key for checksums
    _CHECKSUM_ALGO_TO_RESPONSE_KEY: dict[str, str] = {
        "sha256": "ChecksumSHA256",
        "sha1": "ChecksumSHA1",
        "crc32": "ChecksumCRC32",
        "crc32c": "ChecksumCRC32C",
    }

    def _head_to_fileinfo(self, raw: dict[str, Any], path: str) -> FileInfo:
        """Convert a raw boto3 HeadObject response to a FileInfo.

        Expects a response obtained with ``ChecksumMode="ENABLED"`` so that
        checksum fields (``ChecksumSHA256``, etc.) are included when present.
        """
        name = path.rsplit("/", 1)[-1] if "/" in path else path
        size = raw.get("ContentLength", 0) or 0
        modified = raw.get("LastModified")
        if isinstance(modified, str):
            modified = datetime.fromisoformat(modified)
        if modified is not None and modified.tzinfo is None:
            modified = modified.replace(tzinfo=timezone.utc)
        if modified is None:
            modified = datetime.now(tz=timezone.utc)
        raw_etag = raw.get("ETag")
        etag = raw_etag.strip('"').lower() if isinstance(raw_etag, str) else None
        digest = self._digest_from_head_response(raw)
        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=int(size),
            modified_at=modified,
            etag=etag,
            digest=digest,
        )

    def _digest_from_head_response(self, raw: dict[str, Any]) -> ContentDigest | None:
        """Extract a ContentDigest from a HeadObject response with ChecksumMode=ENABLED.

        Iterates the known checksum response keys and returns the first one found.
        Returns None when no checksum key is present in the response.

        Note: Amazon S3 automatically computes and stores CRC32 checksums for objects
        created since late 2022, so ``ContentDigest`` may be returned even for objects
        uploaded without an explicit checksum algorithm.
        """
        for algo_lower, response_key in self._CHECKSUM_ALGO_TO_RESPONSE_KEY.items():
            b64_value = raw.get(response_key)
            if not b64_value:
                continue
            try:
                return ContentDigest(algo_lower, base64.b64decode(b64_value).hex())
            except Exception:
                continue
        return None

    # endregion
