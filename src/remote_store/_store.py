"""Store -- the primary user-facing abstraction."""

from __future__ import annotations

import contextlib
import dataclasses
import fnmatch
import logging
from typing import TYPE_CHECKING, BinaryIO, TypeVar

from remote_store._capabilities import Capability
from remote_store._errors import InvalidPath, NotFound
from remote_store._models import FolderEntry
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

    Args:
        backend: Backend instance (Local, S3, SFTP, Azure, Memory).
        root_path: Prefix prepended to every path.
            ``""`` means the backend root.
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

        Args:
            path: Store-relative file path.

        Returns:
            Readable binary stream positioned at byte 0.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* is empty.
        """
        log.debug("read path=%r", path, extra={"op": "read", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read(self._require_file_path(path))

    def read_bytes(self, path: str) -> bytes:
        """Read the entire file into memory and return ``bytes``.

        Args:
            path: Store-relative file path.

        Returns:
            The file content as ``bytes``.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* is empty.

        Equivalent to ``read(path).read()``.
        """
        log.debug("read_bytes path=%r", path, extra={"op": "read_bytes", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read_bytes(self._require_file_path(path))

    def read_seekable(self, path: str) -> BinaryIO:
        """Return a seekable binary stream for random-access reading.

        Always returns a seekable stream.  On backends that natively
        return seekable streams from ``read()``, this is zero-overhead.
        On other backends (Azure, HTTP), the backend provides an
        optimized seekable implementation (e.g. HTTP Range requests)
        or falls back to spooling into a temporary file.

        Use ``read()`` for sequential streaming.  Use ``read_seekable()``
        when you need ``seek()`` / ``tell()`` -- for example, when
        passing the stream to PyArrow or other analytical readers.

        Args:
            path: Store-relative file path.

        Returns:
            A seekable binary stream positioned at byte 0.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* is empty.
        """
        log.debug(
            "read_seekable path=%r",
            path,
            extra={"op": "read_seekable", "path": path, "backend": self._backend.name},
        )
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._backend.read_seekable(self._require_file_path(path))

    def read_text(self, path: str, *, encoding: str = "utf-8", errors: str = "strict") -> str:
        """Read the entire file and decode it as text.

        Args:
            path: Store-relative file path.
            encoding: Text encoding, any name accepted by ``codecs``.
            errors: Error handler: ``"strict"``, ``"ignore"``,
                ``"replace"``, ``"backslashreplace"``.  See
                ``codecs.register_error`` for custom handlers.

        Returns:
            The file content as ``str``.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* is empty.
            UnicodeDecodeError: If decoding fails with
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

        Args:
            path: Store-relative file path.
            content: ``bytes`` or readable binary stream (``BinaryIO``).
            overwrite: If ``False``, raises ``AlreadyExists`` when
                *path* exists.

        Raises:
            AlreadyExists: If the file exists and *overwrite* is
                ``False``.
            InvalidPath: If *path* is empty.
        """
        _bk = self._backend.name
        log.debug("write path=%r overwrite=%r", path, overwrite, extra={"op": "write", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.WRITE, backend=_bk)
        self._backend.write(self._require_file_path(path), content, overwrite=overwrite)
        log.info("write complete path=%r", path, extra={"op": "write", "path": path, "backend": _bk})

    def write_text(self, path: str, text: str, *, encoding: str = "utf-8", overwrite: bool = False) -> None:
        """Write a string to *path*, encoded with the given encoding.

        Args:
            path: Store-relative file path.
            text: The string to write.
            encoding: Text encoding.
            overwrite: If ``False``, raises ``AlreadyExists`` when
                *path* exists.

        Raises:
            AlreadyExists: If the file exists and *overwrite* is
                ``False``.
            InvalidPath: If *path* is empty.

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

        Args:
            path: Store-relative file path.
            content: ``bytes`` or readable binary stream (``BinaryIO``).
            overwrite: If ``False``, raises ``AlreadyExists`` when
                *path* exists.

        Raises:
            CapabilityNotSupported: If backend lacks ``ATOMIC_WRITE``.
            AlreadyExists: If the file exists and *overwrite* is
                ``False``.
            InvalidPath: If *path* is empty.
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

        Args:
            path: Store-relative file path.
            overwrite: If ``False``, raises ``AlreadyExists`` when
                *path* exists.

        Returns:
            Writable binary stream.

        Raises:
            CapabilityNotSupported: If the backend lacks
                ``ATOMIC_WRITE``.
            AlreadyExists: If *path* exists and *overwrite* is
                ``False``.
            InvalidPath: If *path* is empty.

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

        Args:
            path: Store-relative file path.
            missing_ok: If ``True``, silently succeeds when *path*
                does not exist.

        Raises:
            NotFound: If the file is missing and *missing_ok* is
                ``False``.
            InvalidPath: If *path* is empty.
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

        Args:
            path: Store-relative folder path.  Must not be ``""``
                (root).
            recursive: If ``True``, delete all contents first.
                If ``False``, raises ``DirectoryNotEmpty`` when folder is
                non-empty.
            missing_ok: If ``True``, silently succeeds when *path*
                does not exist.

        Raises:
            NotFound: If the folder is missing and *missing_ok* is
                ``False``.
            DirectoryNotEmpty: If the folder is non-empty and
                *recursive* is ``False``.
            InvalidPath: If *path* is empty (cannot delete the store
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

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        pattern: str | None = None,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        """Yield ``FileInfo`` objects for files under *path*.

        Args:
            path: Store-relative folder path.
            recursive: Descend into subfolders.  Ignored when *max_depth*
                is set.
            pattern: Glob pattern to filter filenames
                (e.g. ``"*.csv"``).  Matched against each file's **name**
                (basename only).  For full path-based patterns, use
                ``ext.glob.glob_files()``.
            max_depth: Maximum folder depth to include.  ``0`` means files
                directly in *path* only; ``1`` adds files in its immediate
                subfolders, and so on.  ``None`` (default) defers to
                *recursive*.  When set, *recursive* is ignored.

        Returns:
            Iterator of ``FileInfo`` with store-relative paths.

        Raises:
            ValueError: If *max_depth* is negative.
        """
        if max_depth is not None and max_depth < 0:
            msg = f"max_depth must be >= 0, got {max_depth}"
            raise ValueError(msg)
        _bk = self._backend.name
        log.debug(
            "list_files path=%r recursive=%r pattern=%r max_depth=%r",
            path,
            recursive,
            pattern,
            max_depth,
            extra={"op": "list_files", "path": path, "backend": _bk},
        )
        self._backend.capabilities.require(Capability.LIST, backend=_bk)

        # Determine recursion mode
        effective_recursive = max_depth > 0 if max_depth is not None else recursive

        # Precompute base depth for filtering
        base_parts = len(RemotePath(path).parts) if path and path != "." else 0

        for info in self._backend.list_files(
            self._full_path(path),
            recursive=effective_recursive,
            max_depth=max_depth,
        ):
            rebased = self._rebase_file_info(info)
            # Depth filter: file parts minus 1 (filename) minus base gives depth
            if max_depth is not None:
                depth = len(rebased.path.parts) - 1 - base_parts
                if depth > max_depth:
                    continue
            if pattern is not None and not fnmatch.fnmatch(rebased.name, pattern):
                continue
            yield rebased

    def list_folders(self, path: str, *, max_depth: int | None = None) -> Iterator[FolderEntry]:
        """Yield subfolders of *path* as ``FolderEntry`` objects.

        Args:
            path: Store-relative folder path.
            max_depth: Maximum folder depth to include.  ``None`` or ``0``
                returns immediate children only (default).  ``1`` adds
                grandchildren, and so on.

        Returns:
            Iterator of ``FolderEntry`` with ``.name`` and ``.path`` (store-relative).

        Raises:
            ValueError: If *max_depth* is negative.
        """
        if max_depth is not None and max_depth < 0:
            msg = f"max_depth must be >= 0, got {max_depth}"
            raise ValueError(msg)
        _bk = self._backend.name
        log.debug(
            "list_folders path=%r max_depth=%r",
            path,
            max_depth,
            extra={"op": "list_folders", "path": path, "backend": _bk},
        )
        self._backend.capabilities.require(Capability.LIST, backend=_bk)

        effective_depth = max_depth if max_depth is not None else 0

        # BFS traversal up to effective_depth levels
        full = self._full_path(path)
        current_level: list[str] = [full]
        for level in range(effective_depth + 1):
            next_level: list[str] = []
            for folder_path in current_level:
                for entry in self._backend.list_folders(folder_path):
                    rebased = self._rebase_folder_entry(entry)
                    yield rebased
                    if level < effective_depth:
                        next_level.append(str(entry.path))
            current_level = next_level

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        """Yield all immediate children (files and folders) of *path* in a single pass.

        Files are yielded as ``FileInfo``, folders as ``FolderEntry``.
        Both have ``.name`` and ``.path`` attributes (satisfying the
        ``PathEntry`` protocol) so callers can iterate uniformly.

        Args:
            path: Store-relative folder path.

        Returns:
            Iterator of ``FileInfo`` (files) and ``FolderEntry`` (folders).
        """
        _bk = self._backend.name
        log.debug("iter_children path=%r", path, extra={"op": "iter_children", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.LIST, backend=_bk)
        for entry in self._backend.iter_children(self._full_path(path)):
            if isinstance(entry, FolderEntry):
                yield self._rebase_folder_entry(entry)
            else:
                yield self._rebase_file_info(entry)

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        """Yield files matching a glob *pattern*, using the backend's native glob implementation.

        Requires ``Capability.GLOB``.

        Args:
            pattern: Glob pattern (e.g. ``"data/**/*.parquet"``).

        Returns:
            Iterator of ``FileInfo`` with store-relative paths.

        Raises:
            CapabilityNotSupported: If the backend lacks ``GLOB``.
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

        Args:
            src: Source file path.
            dst: Destination file path.
            overwrite: If ``False``, raises ``AlreadyExists`` when
                *dst* exists.

        Raises:
            NotFound: If *src* does not exist.
            AlreadyExists: If *dst* exists and *overwrite* is
                ``False``.
            InvalidPath: If *src* or *dst* is empty.
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

        Args:
            src: Source file path.
            dst: Destination file path.
            overwrite: If ``False``, raises ``AlreadyExists`` when
                *dst* exists.

        Raises:
            NotFound: If *src* does not exist.
            AlreadyExists: If *dst* exists and *overwrite* is
                ``False``.
            InvalidPath: If *src* or *dst* is empty.
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

        Args:
            path: Store-relative path.
        """
        log.debug("exists path=%r", path, extra={"op": "exists", "path": path, "backend": self._backend.name})
        return self._backend.exists(self._full_path(path))

    def is_file(self, path: str) -> bool:
        """Return ``True`` if *path* exists and is a file.

        Args:
            path: Store-relative path.
        """
        log.debug("is_file path=%r", path, extra={"op": "is_file", "path": path, "backend": self._backend.name})
        return self._backend.is_file(self._full_path(path))

    def is_folder(self, path: str) -> bool:
        """Return ``True`` if *path* exists and is a folder.

        Args:
            path: Store-relative path.
        """
        log.debug("is_folder path=%r", path, extra={"op": "is_folder", "path": path, "backend": self._backend.name})
        return self._backend.is_folder(self._full_path(path))

    def get_file_info(self, path: str) -> FileInfo:
        """Return a ``FileInfo`` with size, modification time, and content type for a single file.

        Args:
            path: Store-relative file path.

        Returns:
            ``FileInfo``.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* is empty.
        """
        _bk = self._backend.name
        log.debug("get_file_info path=%r", path, extra={"op": "get_file_info", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.METADATA, backend=_bk)
        info = self._backend.get_file_info(self._require_file_path(path))
        return self._rebase_file_info(info)

    def get_folder_info(self, path: str) -> FolderInfo:
        """Return a ``FolderInfo`` with aggregated size and file count for a folder.

        Args:
            path: Store-relative folder path.

        Returns:
            ``FolderInfo``.

        Raises:
            NotFound: If the folder does not exist.
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

        Raises:
            PermissionDenied: If credentials are invalid.
            NotFound: If the bucket, container, or root path does not
                exist.
            BackendUnavailable: If the backend cannot be reached.
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

        Args:
            subpath: Path segment to append to the current root.

        Returns:
            ``Store``.

        Raises:
            InvalidPath: If *subpath* is empty, contains ``..``
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

        Args:
            type_hint: The expected type of the native client
                (e.g. ``pyarrow.fs.FileSystem``).

        Returns:
            The native client.

        Raises:
            CapabilityNotSupported: If the backend cannot provide
                the requested type.

        ```python
        arrow_fs = store.unwrap(pyarrow.fs.FileSystem)
        ```
        """
        return self._backend.unwrap(type_hint)

    def native_path(self, key: str) -> str:
        """Convert a store-relative *key* to the backend's native path representation.

        Inverse of ``to_key()``.

        Args:
            key: Store-relative path.

        Returns:
            Backend-native path (e.g. S3 object key, local filesystem path).
        """
        return self._backend.native_path(self._full_path(key))

    def to_key(self, path: str) -> str:
        """Convert a backend-native *path* to a store-relative key.

        Inverse of ``native_path()``.

        Args:
            path: Backend-native path string.

        Returns:
            Store-relative key.

        Raises:
            InvalidPath: If the path does not belong to this store.
        """
        backend_rel = self._backend.to_key(path)
        return self._strip_root(backend_rel)

    def supports(self, capability: Capability) -> bool:
        """Check whether the backend supports a given ``Capability``.

        Args:
            capability: A ``Capability`` enum member.

        Returns:
            ``True`` if the backend declares this capability.

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

        Returns:
            Store-relative key.

        Raises:
            InvalidPath: If the path does not start with ``root_path``.
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

    def _rebase_folder_entry(self, entry: FolderEntry) -> FolderEntry:
        """Return a copy of *entry* with its path rebased to store-relative."""
        rel = self._strip_root(str(entry.path))
        if rel == str(entry.path):
            return entry
        new_path = RemotePath.from_backend_path(rel)
        return dataclasses.replace(entry, path=new_path)

    # endregion
