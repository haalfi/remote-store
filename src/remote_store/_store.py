"""Store — the primary user-facing abstraction."""

from __future__ import annotations

import contextlib
import dataclasses
import fnmatch
import logging
from typing import TYPE_CHECKING, BinaryIO, TypeVar

from remote_store._capabilities import Capability
from remote_store._errors import InvalidPath, NotFound
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

    # region: public methods

    def close(self) -> None:
        """Close the underlying backend, releasing any held resources.

        Child stores created via ``child()`` do **not** close the shared
        backend — only the owning store does.
        """
        if self._owns_backend:
            self._backend.close()

    def child(self, subpath: str) -> Store:
        """Return a new Store scoped to a subfolder of this store.

        The child shares this store's backend (no new connection) and
        composes the root path: ``{self._root}/{subpath}``.

        :param subpath: Non-empty relative path validated via ``RemotePath``.
        :returns: A child Store whose ``close()`` does **not** close the
            shared backend.
        :raises InvalidPath: If *subpath* is empty, contains ``..``, or
            contains null bytes.

        Example::

            child = store.child("2026/03")
            child.write("report.csv", data)  # writes to "2026/03/report.csv"
        """
        validated = str(RemotePath(subpath))
        new_root = f"{self._root}/{validated}" if self._root else validated
        child_store = Store(backend=self._backend, root_path=new_root)
        child_store._owns_backend = False
        return child_store

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

        Delegates to ``Backend.unwrap()``.

        :param type_hint: The expected type (e.g., ``pyarrow.fs.FileSystem``).
        :returns: The native handle cast to *type_hint*.
        :raises CapabilityNotSupported: If the backend cannot provide the requested type.
        """
        return self._backend.unwrap(type_hint)

    def native_path(self, key: str) -> str:
        """Convert a store-relative key to the backend-native path.

        Composes store root-path prefixing with ``Backend.native_path()``.
        The result is usable with the native handle returned by ``unwrap()``.

        :param key: Store-relative key (e.g., ``"file.parquet"``).
        :returns: Backend-native path (e.g., ``"my-bucket/root/file.parquet"``).
        """
        return self._backend.native_path(self._full_path(key))

    def supports(self, capability: Capability) -> bool:
        """Check whether the backend supports a capability.

        :param capability: The capability to check.
        :returns: ``True`` if the backend declares this capability.
        """
        return self._backend.capabilities.supports(capability)

    def exists(self, path: str) -> bool:
        """Check if a file or folder exists.

        :param path: Store-relative key, or ``""`` for the store root.
        :returns: ``True`` if a file or folder exists at *path*.

        Example::

            if store.exists("data/report.csv"):
                stream = store.read("data/report.csv")
        """
        log.debug("exists path=%r", path, extra={"op": "exists", "path": path, "backend": self._backend.name})
        return self._backend.exists(self._full_path(path))

    def is_file(self, path: str) -> bool:
        """Check if path is an existing file.

        :param path: Store-relative key.
        :returns: ``True`` if *path* exists and is a file.
        """
        log.debug("is_file path=%r", path, extra={"op": "is_file", "path": path, "backend": self._backend.name})
        return self._backend.is_file(self._full_path(path))

    def is_folder(self, path: str) -> bool:
        """Check if path is an existing folder.

        :param path: Store-relative key, or ``""`` for the store root.
        :returns: ``True`` if *path* exists and is a folder.
        """
        log.debug("is_folder path=%r", path, extra={"op": "is_folder", "path": path, "backend": self._backend.name})
        return self._backend.is_folder(self._full_path(path))

    def read(self, path: str) -> BinaryIO:
        """Open a file for reading.

        The caller is responsible for closing the returned stream.

        :param path: Store-relative key.
        :returns: A readable binary stream. Must be closed by the caller.
        :raises NotFound: If the file does not exist.

        Example::

            with store.read("data/report.csv") as f:
                content = f.read()
        """
        log.debug("read path=%r", path, extra={"op": "read", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read(self._require_file_path(path))

    def read_bytes(self, path: str) -> bytes:
        """Read full file content as bytes.

        :param path: Store-relative key.
        :returns: The file content as a ``bytes`` object.
        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If ``path`` is empty.

        Example::

            data = store.read_bytes("config.json")
        """
        log.debug("read_bytes path=%r", path, extra={"op": "read_bytes", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read_bytes(self._require_file_path(path))

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content to a file.

        :param path: Store-relative key.
        :param content: Data to write (``bytes``, ``str``, or readable binary stream).
        :param overwrite: If ``True``, replace any existing file.
        :raises AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``path`` is empty.

        Example::

            store.write("greeting.txt", b"hello world")
            store.write("greeting.txt", b"updated", overwrite=True)
        """
        _bk = self._backend.name
        log.debug("write path=%r overwrite=%r", path, overwrite, extra={"op": "write", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.WRITE, backend=_bk)
        self._backend.write(self._require_file_path(path), content, overwrite=overwrite)
        log.info("write complete path=%r", path, extra={"op": "write", "path": path, "backend": _bk})

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write content atomically.

        Content is staged in a temporary location and promoted in one step.
        Readers never see a partial file.

        :param path: Store-relative key.
        :param content: Data to write (``bytes``, ``str``, or readable binary stream).
        :param overwrite: If ``True``, replace any existing file.
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

    @contextlib.contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        """Open a file for streaming atomic writing.

        Yields a writable file object. Content written to it is staged in a
        backend-specific temporary location. On successful context exit the
        file is atomically promoted to *path*. On exception the temporary
        artifact is removed and *path* is never modified.

        :param path: Store-relative key for the target file.
        :param overwrite: If ``False``, raise if the file already exists.
        :returns: A writable binary stream (via ``yield``).
        :raises AlreadyExists: If *path* exists and *overwrite* is ``False``.
        :raises CapabilityNotSupported: If the backend lacks ``ATOMIC_WRITE``.
        :raises InvalidPath: If *path* is empty.

        Example::

            with store.open_atomic("output.csv", overwrite=True) as f:
                f.write(b"col1,col2\\n")
                f.write(b"a,1\\n")
        """
        _bk = self._backend.name
        log.debug(
            "open_atomic path=%r overwrite=%r",
            path,
            overwrite,
            extra={"op": "open_atomic", "path": path, "backend": _bk},
        )
        self._backend.capabilities.require(Capability.ATOMIC_WRITE, backend=_bk)
        with self._backend.open_atomic(self._require_file_path(path), overwrite=overwrite) as f:
            yield f
        log.info(
            "open_atomic complete path=%r",
            path,
            extra={"op": "open_atomic", "path": path, "backend": _bk},
        )

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        :param path: Store-relative key.
        :param missing_ok: If ``True``, do not raise when the file is absent.
        :raises NotFound: If the file is missing and ``missing_ok`` is ``False``.
        :raises InvalidPath: If ``path`` is empty.

        Example::

            store.delete("old-report.csv")
            store.delete("maybe-gone.csv", missing_ok=True)
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

        :param path: Store-relative key (must not be empty).
        :param recursive: If ``True``, delete all contents first.
        :param missing_ok: If ``True``, do not raise when the folder is absent.
        :raises NotFound: If the folder is missing and ``missing_ok`` is ``False``.
        :raises InvalidPath: If ``path`` is empty (cannot delete the store root).
        :raises DirectoryNotEmpty: If the folder is non-empty and ``recursive``
            is ``False``.
        """
        _bk = self._backend.name
        log.debug(
            "delete_folder path=%r recursive=%r",
            path,
            recursive,
            extra={"op": "delete_folder", "path": path, "backend": _bk},
        )
        if not path or path == ".":
            raise InvalidPath("Cannot delete the store root", path=path)
        self._backend.capabilities.require(Capability.DELETE, backend=_bk)
        self._backend.delete_folder(self._full_path(path), recursive=recursive, missing_ok=missing_ok)
        log.info("delete_folder complete path=%r", path, extra={"op": "delete_folder", "path": path, "backend": _bk})

    def list_files(self, path: str, *, recursive: bool = False, pattern: str | None = None) -> Iterator[FileInfo]:
        """List files under path, optionally filtering by name pattern.

        Returned ``FileInfo.path`` values are store-relative keys (``root_path``
        is stripped), so they can be fed directly back into other Store methods.

        :param path: Store-relative folder key, or ``""`` for the store root.
        :param recursive: Include files in all subdirectories.
        :param pattern: Optional ``fnmatch`` pattern matched against each file's
            **name** (basename only, e.g., ``"*.csv"``, ``"report.*"``).
            Path-based patterns like ``"subdir/*.csv"`` will not match — use
            ``ext.glob.glob_files()`` for full path-based pattern matching.
            Filtering is applied at the Store level so it works with every
            backend.
        :returns: An iterator of ``FileInfo`` objects with store-relative
            paths.

        Example::

            for info in store.list_files("data", recursive=True, pattern="*.csv"):
                print(info.name, info.size)
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

        Like ``unwrap()``, this gives direct access to a backend-specific
        capability.  For portable pattern matching that works on every
        backend, use ``list_files(pattern=...)`` for simple name filters
        or ``ext.glob.glob_files()`` for full recursive glob patterns.

        Returned ``FileInfo.path`` values are store-relative keys
        (``root_path`` is stripped), like ``list_files``.

        :param pattern: Glob pattern relative to the store root
            (e.g., ``"data/*.csv"``, ``"**/*.txt"``).
        :returns: An iterator of ``FileInfo`` objects with store-relative
            paths.
        :raises CapabilityNotSupported: If the backend lacks ``GLOB``.
        """
        log.debug("glob pattern=%r", pattern, extra={"op": "glob", "path": pattern, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.GLOB, backend=self._backend.name)
        full_pattern = f"{self._root}/{pattern}" if self._root else pattern
        for info in self._backend.glob(full_pattern):
            yield self._rebase_file_info(info)

    def list_folders(self, path: str) -> Iterator[str]:
        """List immediate subfolder names.

        :param path: Store-relative folder key, or ``""`` for the store root.
        :returns: An iterator of subfolder name strings (not full paths).
        """
        _bk = self._backend.name
        log.debug("list_folders path=%r", path, extra={"op": "list_folders", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.LIST, backend=_bk)
        return self._backend.list_folders(self._full_path(path))

    def get_file_info(self, path: str) -> FileInfo:
        """Get file metadata.

        :param path: Store-relative key.
        :returns: A ``FileInfo`` with size, modification time, and other
            backend-provided metadata.
        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If ``path`` is empty.

        Example::

            info = store.get_file_info("report.csv")
            print(info.size, info.modified_at)
        """
        _bk = self._backend.name
        log.debug("get_file_info path=%r", path, extra={"op": "get_file_info", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.METADATA, backend=_bk)
        info = self._backend.get_file_info(self._require_file_path(path))
        return self._rebase_file_info(info)

    def get_folder_info(self, path: str) -> FolderInfo:
        """Get folder metadata.

        :param path: Store-relative folder key, or ``""`` for the store root.
        :returns: A ``FolderInfo`` with file count, total size, and other
            backend-provided metadata.
        :raises NotFound: If the folder does not exist.
        """
        _bk = self._backend.name
        log.debug("get_folder_info path=%r", path, extra={"op": "get_folder_info", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.METADATA, backend=_bk)
        info = self._backend.get_folder_info(self._full_path(path))
        return self._rebase_folder_info(info)

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move or rename a file.

        If *src* and *dst* resolve to the same path, the method verifies that
        the source exists and returns without error.

        :param src: Source store-relative key.
        :param dst: Destination store-relative key.
        :param overwrite: If ``True``, replace any existing file at *dst*.
        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``src`` or ``dst`` is empty.

        Example::

            store.move("draft.txt", "final.txt")
        """
        _bk = self._backend.name
        log.debug(
            "move src=%r dst=%r overwrite=%r", src, dst, overwrite, extra={"op": "move", "path": src, "backend": _bk}
        )
        self._backend.capabilities.require(Capability.MOVE, backend=_bk)
        src_path = self._require_file_path(src)
        dst_path = self._require_file_path(dst)
        if src_path == dst_path:
            if not self._backend.is_file(src_path):
                raise NotFound(f"Source not found: {src}", path=src, backend=_bk)
            return
        self._backend.move(src_path, dst_path, overwrite=overwrite)
        log.info("move complete src=%r dst=%r", src, dst, extra={"op": "move", "path": src, "backend": _bk})

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        If *src* and *dst* resolve to the same path, the method verifies that
        the source exists and returns without error.

        :param src: Source store-relative key.
        :param dst: Destination store-relative key.
        :param overwrite: If ``True``, replace any existing file at *dst*.
        :raises NotFound: If ``src`` does not exist.
        :raises AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        :raises InvalidPath: If ``src`` or ``dst`` is empty.
        """
        _bk = self._backend.name
        log.debug(
            "copy src=%r dst=%r overwrite=%r", src, dst, overwrite, extra={"op": "copy", "path": src, "backend": _bk}
        )
        self._backend.capabilities.require(Capability.COPY, backend=_bk)
        src_path = self._require_file_path(src)
        dst_path = self._require_file_path(dst)
        if src_path == dst_path:
            if not self._backend.is_file(src_path):
                raise NotFound(f"Source not found: {src}", path=src, backend=_bk)
            return
        self._backend.copy(src_path, dst_path, overwrite=overwrite)
        log.info("copy complete src=%r dst=%r", src, dst, extra={"op": "copy", "path": src, "backend": _bk})

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        return f"Store(backend={self._backend.name!r}, root_path={self._root!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Store):
            return self._backend is other._backend and self._root == other._root
        return NotImplemented

    def __hash__(self) -> int:
        return hash((id(self._backend), self._root))

    def __enter__(self) -> Store:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # endregion

    # region: private helpers

    def _full_path(self, path: str) -> str:
        """Resolve a path that may be empty (store root) or a relative subpath.

        Accepts ``""`` and ``"."`` as root aliases so that
        ``str(RemotePath.ROOT)`` round-trips through Store methods.
        """
        if not path or path == ".":
            if self._root:
                return self._root
            return ""
        validated = RemotePath(path)
        if self._root:
            return f"{self._root}/{validated}"
        return str(validated)

    def _require_file_path(self, path: str) -> str:
        """Resolve a path that must be non-empty (file-targeted operations)."""
        if not path or path == ".":
            raise InvalidPath("Path must not be empty or root for file operations", path=path)
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
        new_path = RemotePath.from_backend_path(rel)
        return dataclasses.replace(info, path=new_path)

    # endregion
