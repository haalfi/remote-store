"""Shared base class for S3 backends that use s3fs for control-path operations."""

from __future__ import annotations

import abc
import os
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from remote_store._backend import Backend
from remote_store._errors import (
    NotFound,
    RemoteStoreError,
    _classify_by_message,
    _not_found,
    _permission_denied,
)
from remote_store._models import FileInfo, FolderEntry, FolderInfo
from remote_store._path import RemotePath
from remote_store.backends._fileinfo import _clean_etag, _name_from_path, _normalize_modified

if TYPE_CHECKING:
    from collections.abc import Iterator


def _normalize_endpoint_url(url: str | None) -> str | None:
    """Normalize endpoint URL: bare ``host:port`` becomes ``https://host:port``.

    URLs with an existing ``http://`` or ``https://`` scheme are returned
    unchanged (after stripping whitespace).  Bare hostnames or ``host:port``
    strings are prefixed with ``https://``.
    """
    if url is None:
        return None
    url = url.strip()
    if not url:
        return None
    # Case-insensitive scheme check per RFC 3986 § 3.1
    lower = url[:8].lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return url
    return f"https://{url}"


_S3_CA_ENV_VARS: tuple[str, ...] = ("AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE")


def _resolve_tls_ca_bundle(
    explicit: str | None,
    env_vars: tuple[str, ...],
) -> str | None:
    """Resolve CA bundle: explicit param > env vars (in order) > None."""
    if explicit is not None:
        return explicit
    for var in env_vars:
        val = os.environ.get(var)
        if val:
            return val
    return None


def _validate_tls_ca_bundle(resolved: str | None) -> None:
    """Validate that the resolved CA bundle path is an existing file."""
    if resolved is not None and not Path(resolved).is_file():
        raise ValueError(f"tls_ca_bundle path does not exist or is not a file: {resolved}")


class _S3Base(Backend):
    """Internal base for S3 backends that share an s3fs control path.

    Subclasses must implement the ``_s3fs`` abstract property plus all
    remaining ``Backend`` abstract methods (read, write, etc.).
    """

    # Set by subclass __init__
    _bucket: str

    # region: abstract property

    @property
    @abc.abstractmethod
    def _s3fs(self) -> Any:
        """Return the s3fs ``S3FileSystem`` instance."""
        ...

    # endregion

    # region: path helpers

    def _s3_path(self, path: str) -> str:
        """Build ``bucket/key`` path for s3fs."""
        if path:
            return f"{self._bucket}/{path}"
        return self._bucket

    def to_key(self, native_path: str) -> str:
        prefix = f"{self._bucket}/"
        if native_path.startswith(prefix):
            return native_path[len(prefix) :]
        return native_path

    # endregion

    # region: shared listing methods

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        try:
            s3_path = self._s3_path(path)
            if recursive:
                queue: deque[str] = deque([s3_path])
                while queue:
                    current = queue.popleft()
                    try:
                        dir_entries: list[dict[str, Any]] = self._s3fs.ls(current, detail=True)
                    except FileNotFoundError:
                        continue  # directory deleted mid-traversal
                    for info in dir_entries:
                        if info.get("type") == "file":
                            rel = self.to_key(info["name"])
                            yield self._info_to_fileinfo(info, rel)
                        elif info.get("type") == "directory":
                            queue.append(info["name"])
            else:
                entries: list[dict[str, Any]] = self._s3fs.ls(s3_path, detail=True)
                for info in entries:
                    if info.get("type") == "file":
                        rel = self.to_key(info["name"])
                        yield self._info_to_fileinfo(info, rel)
        except RemoteStoreError:  # pragma: no cover -- defensive
            raise
        except FileNotFoundError:  # pragma: no cover -- s3fs returns empty for missing prefixes
            return
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise _permission_denied(path, self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive
            raise self._classify_error(exc, path) from None

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        try:
            s3_path = self._s3_path(path)
            entries: list[dict[str, Any]] = self._s3fs.ls(s3_path, detail=True)
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
            raise _permission_denied(path, self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive
            raise self._classify_error(exc, path) from None

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        try:
            s3_path = self._s3_path(path)
            entries: list[dict[str, Any]] = self._s3fs.ls(s3_path, detail=True)
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
            raise _permission_denied(path, self.name) from None
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

    # endregion

    # region: shared metadata methods

    def get_folder_info(self, path: str) -> FolderInfo:
        # S3 folders are virtual (prefix-based).  An empty folder is simply a
        # prefix with no objects, so exists() already returns False for truly
        # non-existent prefixes.
        with self._s3fs_errors(path):
            s3_path = self._s3_path(path)
            if not self._s3fs.exists(s3_path):
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
            file_count = 0
            total_size = 0
            latest_modified: datetime | None = None
            queue: deque[str] = deque([s3_path])
            while queue:
                current = queue.popleft()
                try:
                    entries: list[dict[str, Any]] = self._s3fs.ls(current, detail=True)
                except FileNotFoundError:
                    continue  # directory deleted mid-traversal
                for info in entries:
                    if info.get("type") == "directory":
                        queue.append(info["name"])
                    elif info.get("type") == "file":
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
            return FolderInfo(
                path=RemotePath.from_backend_path(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest_modified,
            )

    # endregion

    # region: shared error handling

    @contextmanager
    def _s3fs_errors(self, path: str = "") -> Iterator[None]:
        """Map s3fs/botocore exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:
            raise
        except FileNotFoundError:
            raise _not_found(path, self.name) from None
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise _permission_denied(path, self.name) from None
        except Exception as exc:
            raise self._classify_error(exc, path) from None

    def _classify_error(self, exc: Exception, path: str) -> RemoteStoreError:
        """Classify an unknown exception into a remote_store error type.

        Uses the shared heuristic fallback.  Subclasses may override to
        check SDK-specific exception types first.
        """
        return _classify_by_message(exc, path, self.name)

    # endregion

    # region: shared FileInfo construction

    def _info_to_fileinfo(self, info: dict[str, Any], path: str) -> FileInfo:
        """Convert an s3fs info dict to a ``FileInfo``.

        ETag extraction is delegated to ``_extract_etag()`` so subclasses
        can suppress or customise it.
        """
        name = _name_from_path(path)
        size = info.get("size", info.get("Size", 0)) or 0
        modified = _normalize_modified(info.get("LastModified", info.get("last_modified")))
        etag = self._extract_etag(info)
        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=int(size),
            modified_at=modified,
            etag=etag,
        )

    def _extract_etag(self, info: dict[str, Any]) -> str | None:
        """Extract and clean the ETag from an s3fs info dict.

        The base class defaults to extracting ETag because that is the
        common case (``S3Backend`` and any future s3fs-based backend).
        ``S3PyArrowBackend`` overrides to return ``None`` because its
        read path does not use s3fs metadata.
        """
        raw = info.get("ETag") or info.get("etag")
        return _clean_etag(raw)

    # endregion
