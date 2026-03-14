"""Store -- the primary user-facing abstraction."""

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
    before being delegated to the backend.  Supports the context-manager
    protocol (``with Store(...) as s:``) which calls ``close()`` on exit.

    :param backend: Backend instance (Local, S3, SFTP, Azure, Memory).
    :param root_path: Prefix prepended to every path.
        ``""`` means the backend root.

    ``Store`` is immutable after construction and can be shared across
    threads.  Backend thread safety depends on the backend implementation.

    .. note::
       The root path does not need to exist before constructing the store.
       :meth:`write` creates intermediate folders implicitly on all backends,
       so files written under a new ``root_path`` will work without any
       explicit folder-creation step.
    """

    def __init__(self, backend: Backend, root_path: str = "") -> None:
        self._backend = backend
        self._root = str(RemotePath(root_path)) if root_path else ""
        self._owns_backend = True

    # region: reading

    def read(self, path: str) -> BinaryIO:
        """Return a readable binary stream positioned at the start of *path*.

        The caller is responsible for closing the stream (or using a
        ``with`` block).

        :param path: Store-relative file path.
        :returns: Readable binary stream positioned at byte 0.
        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If *path* is empty.
        """
        log.debug("read path=%r", path, extra={"op": "read", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read(self._require_file_path(path))

    def read_bytes(self, path: str) -> bytes:
        """Read the entire file into memory and return ``bytes``.

        :param path: Store-relative file path.
        :returns: The file content as ``bytes``.
        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If *path* is empty.

        Equivalent to ``read(path).read()``.
        """
        log.debug("read_bytes path=%r", path, extra={"op": "read_bytes", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read_bytes(self._require_file_path(path))

    def read_text(self, path: str, *, encoding: str = "utf-8", errors: str = "strict") -> str:
        """Read the entire file and decode it as text.

        :param path: Store-relative file path.
        :param encoding: Text encoding, any name accepted by ``codecs``.
        :param errors: Error handler: ``"strict"``, ``"ignore"``,
            ``"replace"``, ``"backslashreplace"``.  See
            ``codecs.register_error`` for custom handlers.
        :returns: The file content as ``str``.
        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If *path* is empty.
        :raises UnicodeDecodeError: If decoding fails with
            ``errors="strict"``.

        Equivalent to ``read_bytes(path).decode(encoding, errors)``.
        """
        log.debug(
            "read_text path=%r encoding=%r",
            path,
            encoding,
            extra={"op": "read_text", "path": path, "backend": self._backend.name},
        )
        return self.read_bytes(path).decode(encoding, errors)

    # endregion

    # region: writing

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write binary content to *path*.  Creates parent folders implicitly.

        :param path: Store-relative file path.
        :param content: ``bytes`` or readable binary stream (``BinaryIO``).
        :param overwrite: If ``False``, raises ``AlreadyExists`` when
            *path* exists.
        :raises AlreadyExists: If the file exists and *overwrite* is
            ``False``.
        :raises InvalidPath: If *path* is empty.
        """
        _bk = self._backend.name
        log.debug("write path=%r overwrite=%r", path, overwrite, extra={"op": "write", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.WRITE, backend=_bk)
        self._backend.write(self._require_file_path(path), content, overwrite=overwrite)
        log.info("write complete path=%r", path, extra={"op": "write", "path": path, "backend": _bk})

    def write_text(self, path: str, text: str, *, encoding: str = "utf-8", overwrite: bool = False) -> None:
        """Write a string to *path*, encoded with the given encoding.

        :param path: Store-relative file path.
        :param text: The string to write.
        :param encoding: Text encoding.
        :param overwrite: If ``False``, raises ``AlreadyExists`` when
            *path* exists.
        :raises AlreadyExists: If the file exists and *overwrite* is
            ``False``.
        :raises InvalidPath: If *path* is empty.

        Equivalent to
        ``write(path, text.encode(encoding), overwrite=overwrite)``.
        """
        log.debug(
            "write_text path=%r encoding=%r overwrite=%r",
            path,
            encoding,
            overwrite,
            extra={"op": "write_text", "path": path, "backend": self._backend.name},
        )
        self.write(path, text.encode(encoding), overwrite=overwrite)

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        """Write binary content to *path* atomically.

        If the write fails or is interrupted, *path* is not left in a
        partial state.

        :param path: Store-relative file path.
        :param content: ``bytes`` or readable binary stream (``BinaryIO``).
        :param overwrite: If ``False``, raises ``AlreadyExists`` when
            *path* exists.
        :raises CapabilityNotSupported: If backend lacks ``ATOMIC_WRITE``.
        :raises AlreadyExists: If the file exists and *overwrite* is
            ``False``.
        :raises InvalidPath: If *path* is empty.
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
        """Context manager that yields a writable binary stream.

        The file is committed atomically on successful exit; on exception
        the partial write is discarded.

        :param path: Store-relative file path.
        :param overwrite: If ``False``, raises ``AlreadyExists`` when
            *path* exists.
        :returns: Writable binary stream.
        :raises CapabilityNotSupported: If the backend lacks
            ``ATOMIC_WRITE``.
        :raises AlreadyExists: If *path* exists and *overwrite* is
            ``False``.
        :raises InvalidPath: If *path* is empty.

        ```python
        with store.open_atomic("data/output.bin", overwrite=True) as f:
            f.write(b"chunk 1")
            f.write(b"chunk 2")
        # file is now visible at data/output.bin
        ```
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

    # endregion

    # region: deleting

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a single file.

        :param path: Store-relative file path.
        :param missing_ok: If ``True``, silently succeeds when *path*
            does not exist.
        :raises NotFound: If the file is missing and *missing_ok* is
            ``False``.
        :raises InvalidPath: If *path* is empty.
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

        :param path: Store-relative folder path.  Must not be ``""``
            (root).
        :param recursive: If ``True``, delete all contents first.
            If ``False``, raises ``DirectoryNotEmpty`` when folder is
            non-empty.
        :param missing_ok: If ``True``, silently succeeds when *path*
            does not exist.
        :raises NotFound: If the folder is missing and *missing_ok* is
            ``False``.
        :raises DirectoryNotEmpty: If the folder is non-empty and
            *recursive* is ``False``.
        :raises InvalidPath: If *path* is empty (cannot delete the store
            root).
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

    # endregion

    # region: listing and iteration

    def list_files(self, path: str, *, recursive: bool = False, pattern: str | None = None) -> Iterator[FileInfo]:
        """Yield ``FileInfo`` objects for files under *path*.

        :param path: Store-relative folder path.
        :param recursive: Descend into subfolders.
        :param pattern: Glob pattern to filter filenames
            (e.g. ``"*.csv"``).  Matched against each file's **name**
            (basename only).  For full path-based patterns, use
            ``ext.glob.glob_files()``.
        :returns: Iterator of ``FileInfo`` with store-relative paths.
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

    def list_folders(self, path: str) -> Iterator[str]:
        """Yield immediate subfolder names of *path*.

        :param path: Store-relative folder path.
        :returns: Iterator of subfolder name strings.
        """
        _bk = self._backend.name
        log.debug("list_folders path=%r", path, extra={"op": "list_folders", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.LIST, backend=_bk)
        return self._backend.list_folders(self._full_path(path))

    def iter_children(self, path: str) -> Iterator[FileInfo | str]:
        """Yield all immediate children (files and folders) of *path* in a single pass.

        Files are yielded as ``FileInfo`` (with store-relative paths),
        folders as bare ``str`` names.

        :param path: Store-relative folder path.
        :returns: Iterator of ``FileInfo`` (files) and ``str``
            (folder names).
        """
        _bk = self._backend.name
        log.debug("iter_children path=%r", path, extra={"op": "iter_children", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.LIST, backend=_bk)
        for entry in self._backend.iter_children(self._full_path(path)):
            if isinstance(entry, str):
                yield entry
            else:
                yield self._rebase_file_info(entry)

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        """Yield files matching a glob *pattern*, using the backend's native glob implementation.

        Requires ``Capability.GLOB``.

        :param pattern: Glob pattern (e.g. ``"data/**/*.parquet"``).
        :returns: Iterator of ``FileInfo`` with store-relative paths.
        :raises CapabilityNotSupported: If the backend lacks ``GLOB``.
        """
        log.debug("glob pattern=%r", pattern, extra={"op": "glob", "path": pattern, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.GLOB, backend=self._backend.name)
        full_pattern = f"{self._root}/{pattern}" if self._root else pattern
        for info in self._backend.glob(full_pattern):
            yield self._rebase_file_info(info)

    # endregion

    # region: file operations

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move (rename) a file from *src* to *dst*.

        File-only -- to move a folder, iterate its contents.

        :param src: Source file path.
        :param dst: Destination file path.
        :param overwrite: If ``False``, raises ``AlreadyExists`` when
            *dst* exists.
        :raises NotFound: If *src* does not exist.
        :raises AlreadyExists: If *dst* exists and *overwrite* is
            ``False``.
        :raises InvalidPath: If *src* or *dst* is empty.
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
        """Copy a file from *src* to *dst*.

        File-only -- to copy a folder, iterate its contents.

        :param src: Source file path.
        :param dst: Destination file path.
        :param overwrite: If ``False``, raises ``AlreadyExists`` when
            *dst* exists.
        :raises NotFound: If *src* does not exist.
        :raises AlreadyExists: If *dst* exists and *overwrite* is
            ``False``.
        :raises InvalidPath: If *src* or *dst* is empty.
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

    # region: metadata

    def exists(self, path: str) -> bool:
        """Return ``True`` if *path* exists (file or folder).

        :param path: Store-relative path.
        """
        log.debug("exists path=%r", path, extra={"op": "exists", "path": path, "backend": self._backend.name})
        return self._backend.exists(self._full_path(path))

    def is_file(self, path: str) -> bool:
        """Return ``True`` if *path* exists and is a file.

        :param path: Store-relative path.
        """
        log.debug("is_file path=%r", path, extra={"op": "is_file", "path": path, "backend": self._backend.name})
        return self._backend.is_file(self._full_path(path))

    def is_folder(self, path: str) -> bool:
        """Return ``True`` if *path* exists and is a folder.

        :param path: Store-relative path.
        """
        log.debug("is_folder path=%r", path, extra={"op": "is_folder", "path": path, "backend": self._backend.name})
        return self._backend.is_folder(self._full_path(path))

    def get_file_info(self, path: str) -> FileInfo:
        """Return a ``FileInfo`` with size, modification time, and content type for a single file.

        :param path: Store-relative file path.
        :returns: ``FileInfo``.
        :raises NotFound: If the file does not exist.
        :raises InvalidPath: If *path* is empty.
        """
        _bk = self._backend.name
        log.debug("get_file_info path=%r", path, extra={"op": "get_file_info", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.METADATA, backend=_bk)
        info = self._backend.get_file_info(self._require_file_path(path))
        return self._rebase_file_info(info)

    def get_folder_info(self, path: str) -> FolderInfo:
        """Return a ``FolderInfo`` with aggregated size and file count for a folder.

        :param path: Store-relative folder path.
        :returns: ``FolderInfo``.
        :raises NotFound: If the folder does not exist.
        """
        _bk = self._backend.name
        log.debug("get_folder_info path=%r", path, extra={"op": "get_folder_info", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.METADATA, backend=_bk)
        info = self._backend.get_folder_info(self._full_path(path))
        return self._rebase_folder_info(info)

    # endregion

    # region: lifecycle

    def ping(self) -> None:
        """Verify that the backend is reachable.

        :raises PermissionDenied: If credentials are invalid.
        :raises NotFound: If the bucket, container, or root path does not
            exist.
        :raises BackendUnavailable: If the backend cannot be reached.
        """
        _bk = self._backend.name
        log.debug("ping", extra={"op": "ping", "backend": _bk})
        self._backend.check_health()
        log.info("ping OK", extra={"op": "ping", "backend": _bk})

    def close(self) -> None:
        """Release backend resources.

        Called automatically when used as a context manager.
        """
        if self._owns_backend:
            self._backend.close()

    def child(self, subpath: str) -> Store:
        """Return a new ``Store`` scoped to *subpath* under the current root.

        The child shares the same backend instance.

        :param subpath: Path segment to append to the current root.
        :returns: ``Store``.
        :raises InvalidPath: If *subpath* is empty, contains ``..``
            segments, or includes null bytes.

        ```python
        data = store.child("data/2024")
        data.list_files("")  # lists files under <root>/data/2024/
        ```
        """
        validated = str(RemotePath(subpath))
        new_root = f"{self._root}/{validated}" if self._root else validated
        child_store = Store(backend=self._backend, root_path=new_root)
        child_store._owns_backend = False
        return child_store

    # endregion

    # region: interop (backend-specific)

    def unwrap(self, type_hint: type[T]) -> T:
        """Return the backend's native client object, cast to *type_hint*.

        :param type_hint: The expected type of the native client
            (e.g. ``pyarrow.fs.FileSystem``).
        :returns: The native client.
        :raises CapabilityNotSupported: If the backend cannot provide
            the requested type.

        ```python
        arrow_fs = store.unwrap(pyarrow.fs.FileSystem)
        ```
        """
        return self._backend.unwrap(type_hint)

    def native_path(self, key: str) -> str:
        """Convert a store-relative *key* to the backend's native path representation.

        Inverse of ``to_key()``.

        :param key: Store-relative path.
        :returns: Backend-native path (e.g. S3 object key, local
            filesystem path).
        """
        return self._backend.native_path(self._full_path(key))

    def to_key(self, path: str) -> str:
        """Convert a backend-native *path* to a store-relative key.

        Inverse of ``native_path()``.

        :param path: Backend-native path string.
        :returns: Store-relative key.
        :raises InvalidPath: If the path does not belong to this store.
        """
        backend_rel = self._backend.to_key(path)
        return self._strip_root(backend_rel)

    def supports(self, capability: Capability) -> bool:
        """Check whether the backend supports a given ``Capability``.

        :param capability: A ``Capability`` enum member.
        :returns: ``True`` if the backend declares this capability.

        ```python
        if store.supports(Capability.GLOB):
            results = store.glob("**/*.csv")
        ```
        """
        return self._backend.capabilities.supports(capability)

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
