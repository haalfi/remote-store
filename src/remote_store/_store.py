"""Store — the primary user-facing abstraction."""

from __future__ import annotations

import dataclasses
import fnmatch
import logging
from typing import TYPE_CHECKING, BinaryIO, TypeVar

from remote_store._capabilities import Capability
from remote_store._errors import InvalidPath
from remote_store._path import RemotePath

log = logging.getLogger(__name__)

T = TypeVar("T")

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import TracebackType

    from remote_store._backend import Backend
    from remote_store._models import FileInfo, FolderInfo
    from remote_store._types import WritableContent


class Store:
    """A logical remote folder scoped to a root path.

    All path arguments are validated and prefixed with ``root_path``
    before being delegated to the backend.

    :param backend: The backend to delegate I/O to.
    :param root_path: Path prefix for all operations (may be empty).
    """

    def __init__(self, backend: Backend, root_path: str = "") -> None:
        self._backend = backend
        self._root = str(RemotePath(root_path)) if root_path else ""
        self._owns_backend = True

    def __repr__(self) -> str:
        return f"Store(backend={self._backend.name!r}, root_path={self._root!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Store):
            return self._backend is other._backend and self._root == other._root
        return NotImplemented

    def __hash__(self) -> int:
        return hash((id(self._backend), self._root))

    def close(self) -> None:
        """Close the underlying backend, releasing any held resources.

        Child stores created via :meth:`child` do **not** close the shared
        backend — only the owning store does.
        """
        if self._owns_backend:
            self._backend.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def child(self, subpath: str) -> Store:
        """Return a new Store scoped to a subfolder of this store.

        The child shares this store's backend (no new connection) and
        composes the root path: ``{self._root}/{subpath}``.

        :param subpath: Non-empty relative path validated via ``RemotePath``.
        :returns: A child Store whose ``close()`` does **not** close the
            shared backend.
        :raises InvalidPath: If *subpath* is empty, contains ``..``, or
            contains null bytes.
        """
        validated = str(RemotePath(subpath))
        new_root = f"{self._root}/{validated}" if self._root else validated
        child_store = Store(backend=self._backend, root_path=new_root)
        child_store._owns_backend = False
        return child_store

    def _full_path(self, path: str) -> str:
        """Resolve a path that may be empty (store root) or a relative subpath."""
        if not path:
            if self._root:
                return self._root
            return ""
        validated = RemotePath(path)
        if self._root:
            return f"{self._root}/{validated}"
        return str(validated)

    def _require_file_path(self, path: str) -> str:
        """Resolve a path that must be non-empty (file-targeted operations)."""
        if not path:
            raise InvalidPath("Path must not be empty for file operations", path=path)
        return self._full_path(path)

    def _strip_root(self, backend_rel: str) -> str:
        """Strip ``root_path`` prefix from a backend-relative path.

        :returns: Store-relative key.
        :raises InvalidPath: If the path does not start with ``root_path``.
        """
        if not self._root:
            return backend_rel
        if backend_rel == self._root:
            return ""
        prefix = self._root + "/"
        if backend_rel.startswith(prefix):
            return backend_rel[len(prefix) :]
        raise InvalidPath(
            f"Path {backend_rel!r} is not under store root {self._root!r}",
            path=backend_rel,
        )

    def _rebase_file_info(self, info: FileInfo) -> FileInfo:
        """Return a copy of *info* with its path rebased to store-relative."""
        rel = self._strip_root(str(info.path))
        if rel == str(info.path):
            return info
        return dataclasses.replace(info, path=RemotePath(rel))

    def _rebase_folder_info(self, info: FolderInfo) -> FolderInfo:
        """Return a copy of *info* with its path rebased to store-relative."""
        rel = self._strip_root(str(info.path))
        if rel == str(info.path):
            return info
        return dataclasses.replace(info, path=RemotePath(rel))

    def to_key(self, path: str) -> str:
        """Convert an absolute or backend-native path to a store-relative key.

        Composes ``backend.to_key()`` (strips the backend's native root) with
        store-root stripping (removes ``root_path`` prefix).

        :param path: Absolute, backend-native, or backend-relative path.
        :returns: Key relative to this store's ``root_path``.
        :raises InvalidPath: If the path does not belong to this store.
        """
        backend_rel = self._backend.to_key(path)
        return self._strip_root(backend_rel)

    def unwrap(self, type_hint: type[T]) -> T:
        """Return the backend's native handle if it matches the requested type.

        Delegates to :meth:`Backend.unwrap`.

        :param type_hint: The expected type (e.g., ``pyarrow.fs.FileSystem``).
        :raises CapabilityNotSupported: If the backend cannot provide the requested type.
        """
        return self._backend.unwrap(type_hint)

    def supports(self, capability: Capability) -> bool:
        """Check whether the backend supports a capability."""
        return self._backend.capabilities.supports(capability)

    def exists(self, path: str) -> bool:
        """Check if a file or folder exists."""
        log.debug("exists path=%r", path, extra={"op": "exists", "path": path, "backend": self._backend.name})
        return self._backend.exists(self._full_path(path))

    def is_file(self, path: str) -> bool:
        """Check if path is an existing file."""
        log.debug("is_file path=%r", path, extra={"op": "is_file", "path": path, "backend": self._backend.name})
        return self._backend.is_file(self._full_path(path))

    def is_folder(self, path: str) -> bool:
        """Check if path is an existing folder."""
        log.debug("is_folder path=%r", path, extra={"op": "is_folder", "path": path, "backend": self._backend.name})
        return self._backend.is_folder(self._full_path(path))

    def read(self, path: str) -> BinaryIO:
        """Open a file for reading.

        :raises NotFound: If the file does not exist.
        """
        log.debug("read path=%r", path, extra={"op": "read", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read(self._require_file_path(path))

    def read_bytes(self, path: str) -> bytes:
        """Read full file content as bytes.

        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If ``path`` is empty.
        """
        log.debug("read_bytes path=%r", path, extra={"op": "read_bytes", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read_bytes(self._require_file_path(path))

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content to a file.

        :raises AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``path`` is empty.
        """
        _bk = self._backend.name
        log.debug("write path=%r overwrite=%r", path, overwrite, extra={"op": "write", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.WRITE, backend=_bk)
        self._backend.write(self._require_file_path(path), content, overwrite=overwrite)
        log.info("write complete path=%r", path, extra={"op": "write", "path": path, "backend": _bk})

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content atomically.

        :raises CapabilityNotSupported: If backend lacks ``ATOMIC_WRITE``.
        :raises AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``path`` is empty.
        """
        _bk = self._backend.name
        log.debug(
            "write_atomic path=%r overwrite=%r",
            path,
            overwrite,
            extra={"op": "write_atomic", "path": path, "backend": _bk},
        )
        self._backend.capabilities.require(Capability.ATOMIC_WRITE, backend=_bk)
        self._backend.write_atomic(self._require_file_path(path), content, overwrite=overwrite)
        log.info("write_atomic complete path=%r", path, extra={"op": "write_atomic", "path": path, "backend": _bk})

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        :raises NotFound: If the file is missing and ``missing_ok`` is ``False``.
        :raises InvalidPath: If ``path`` is empty.
        """
        _bk = self._backend.name
        log.debug(
            "delete path=%r missing_ok=%r", path, missing_ok, extra={"op": "delete", "path": path, "backend": _bk}
        )
        self._backend.capabilities.require(Capability.DELETE, backend=_bk)
        self._backend.delete(self._require_file_path(path), missing_ok=missing_ok)
        log.info("delete complete path=%r", path, extra={"op": "delete", "path": path, "backend": _bk})

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder.

        :raises NotFound: If the folder is missing and ``missing_ok`` is ``False``.
        :raises InvalidPath: If ``path`` is empty (cannot delete the store root).
        """
        _bk = self._backend.name
        log.debug(
            "delete_folder path=%r recursive=%r",
            path,
            recursive,
            extra={"op": "delete_folder", "path": path, "backend": _bk},
        )
        if not path:
            raise InvalidPath("Cannot delete the store root", path=path)
        self._backend.capabilities.require(Capability.DELETE, backend=_bk)
        self._backend.delete_folder(self._full_path(path), recursive=recursive, missing_ok=missing_ok)
        log.info("delete_folder complete path=%r", path, extra={"op": "delete_folder", "path": path, "backend": _bk})

    def list_files(self, path: str, *, recursive: bool = False, pattern: str | None = None) -> Iterator[FileInfo]:
        """List files under path, optionally filtering by name pattern.

        Returned ``FileInfo.path`` values are store-relative keys (``root_path``
        is stripped), so they can be fed directly back into other Store methods.

        :param recursive: Include files in all subdirectories.
        :param pattern: Optional ``fnmatch`` pattern matched against each file's
            **name** (basename only, e.g., ``"*.csv"``, ``"report.*"``).
            Path-based patterns like ``"subdir/*.csv"`` will not match — use
            ``ext.glob.glob_files()`` for full path-based pattern matching.
            Filtering is applied at the Store level so it works with every
            backend.
        """
        _bk = self._backend.name
        log.debug(
            "list_files path=%r recursive=%r pattern=%r",
            path,
            recursive,
            pattern,
            extra={"op": "list_files", "path": path, "backend": _bk},
        )
        self._backend.capabilities.require(Capability.LIST, backend=_bk)
        for info in self._backend.list_files(self._full_path(path), recursive=recursive):
            rebased = self._rebase_file_info(info)
            if pattern is not None and not fnmatch.fnmatch(rebased.name, pattern):
                continue
            yield rebased

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        """Match files against a glob pattern using native backend support.

        Like :meth:`unwrap`, this gives direct access to a backend-specific
        capability.  For portable pattern matching that works on every
        backend, use ``list_files(pattern=...)`` for simple name filters
        or ``ext.glob.glob_files()`` for full recursive glob patterns.

        Returned ``FileInfo.path`` values are store-relative keys
        (``root_path`` is stripped), like ``list_files``.

        :param pattern: Glob pattern relative to the store root
            (e.g., ``"data/*.csv"``, ``"**/*.txt"``).
        :raises CapabilityNotSupported: If the backend lacks ``GLOB``.
        """
        log.debug("glob pattern=%r", pattern, extra={"op": "glob", "path": pattern, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.GLOB, backend=self._backend.name)
        full_pattern = f"{self._root}/{pattern}" if self._root else pattern
        for info in self._backend.glob(full_pattern):
            yield self._rebase_file_info(info)

    def list_folders(self, path: str) -> Iterator[str]:
        """List immediate subfolder names."""
        _bk = self._backend.name
        log.debug("list_folders path=%r", path, extra={"op": "list_folders", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.LIST, backend=_bk)
        return self._backend.list_folders(self._full_path(path))

    def get_file_info(self, path: str) -> FileInfo:
        """Get file metadata.

        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If ``path`` is empty.
        """
        _bk = self._backend.name
        log.debug("get_file_info path=%r", path, extra={"op": "get_file_info", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.METADATA, backend=_bk)
        info = self._backend.get_file_info(self._require_file_path(path))
        return self._rebase_file_info(info)

    def get_folder_info(self, path: str) -> FolderInfo:
        """Get folder metadata.

        :raises NotFound: If the folder does not exist.
        """
        _bk = self._backend.name
        log.debug("get_folder_info path=%r", path, extra={"op": "get_folder_info", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.METADATA, backend=_bk)
        info = self._backend.get_folder_info(self._full_path(path))
        return self._rebase_folder_info(info)

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move/rename a file.

        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``src`` or ``dst`` is empty.
        """
        _bk = self._backend.name
        log.debug(
            "move src=%r dst=%r overwrite=%r", src, dst, overwrite, extra={"op": "move", "path": src, "backend": _bk}
        )
        self._backend.capabilities.require(Capability.MOVE, backend=_bk)
        self._backend.move(self._require_file_path(src), self._require_file_path(dst), overwrite=overwrite)
        log.info("move complete src=%r dst=%r", src, dst, extra={"op": "move", "path": src, "backend": _bk})

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``src`` or ``dst`` is empty.
        """
        _bk = self._backend.name
        log.debug(
            "copy src=%r dst=%r overwrite=%r", src, dst, overwrite, extra={"op": "copy", "path": src, "backend": _bk}
        )
        self._backend.capabilities.require(Capability.COPY, backend=_bk)
        self._backend.copy(self._require_file_path(src), self._require_file_path(dst), overwrite=overwrite)
        log.info("copy complete src=%r dst=%r", src, dst, extra={"op": "copy", "path": src, "backend": _bk})
