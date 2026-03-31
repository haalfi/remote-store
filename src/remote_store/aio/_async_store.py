"""AsyncStore -- async counterpart to Store."""

from __future__ import annotations

import dataclasses
import fnmatch
import logging
from typing import TYPE_CHECKING, TypeVar

from remote_store._capabilities import Capability
from remote_store._errors import InvalidPath, NotFound
from remote_store._models import FolderEntry, FolderInfo
from remote_store._path import RemotePath

log = logging.getLogger(__name__)

T = TypeVar("T")

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import datetime
    from types import TracebackType

    from remote_store._backend import Backend
    from remote_store._models import FileInfo
    from remote_store._resolution import ResolutionPlan
    from remote_store.aio._async_backend import AsyncBackend
    from remote_store.aio._types import AsyncWritableContent


class AsyncStore:
    """An async logical remote folder scoped to a root path.

    All path arguments are validated and prefixed with ``root_path``
    before being delegated to the backend.  Supports the async
    context-manager protocol (``async with AsyncStore(...) as s:``)
    which calls ``aclose()`` on exit.

    Args:
        backend: Async or sync backend instance.  Sync backends are
            auto-wrapped via ``SyncBackendAdapter``.
        root_path: Prefix prepended to every path.
            ``""`` means the backend root.
    """

    def __init__(self, backend: AsyncBackend | Backend, root_path: str = "") -> None:
        from remote_store._backend import Backend as _SyncBackend
        from remote_store.aio._async_backend import AsyncBackend as _AsyncBackend
        from remote_store.aio._sync_adapter import SyncBackendAdapter

        if isinstance(backend, _SyncBackend) and not isinstance(backend, _AsyncBackend):
            backend = SyncBackendAdapter(backend)
        self._backend: AsyncBackend = backend
        self._root = str(RemotePath(root_path)) if root_path else ""
        self._owns_backend = True

    # region: reading

    def read(self, path: str) -> AsyncIterator[bytes]:
        """Return an async iterator of byte chunks for *path*.

        The caller is responsible for consuming the iterator.
        Validation (capability check, path check) happens eagerly
        on call, not lazily on first iteration.

        Args:
            path: Store-relative file path.

        Returns:
            Async iterator of byte chunks.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* is empty.
        """
        log.debug("read path=%r", path, extra={"op": "read", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return self._read_chunks(self._require_file_path(path))

    async def _read_chunks(self, resolved: str) -> AsyncIterator[bytes]:
        """Inner generator for :meth:`read` — yields chunks from backend."""
        async for chunk in self._backend.read(resolved):
            yield chunk

    async def read_bytes(self, path: str) -> bytes:
        """Read the entire file into memory and return ``bytes``.

        Args:
            path: Store-relative file path.

        Returns:
            The file content as ``bytes``.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If *path* is empty.

        Equivalent to collecting all chunks from ``read(path)``.
        """
        log.debug("read_bytes path=%r", path, extra={"op": "read_bytes", "path": path, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.READ, backend=self._backend.name)
        return await self._backend.read_bytes(self._require_file_path(path))

    async def read_text(self, path: str, *, encoding: str = "utf-8", errors: str = "strict") -> str:
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

        Equivalent to ``(await read_bytes(path)).decode(encoding, errors)``.
        """
        log.debug(
            "read_text path=%r encoding=%r",
            path,
            encoding,
            extra={"op": "read_text", "path": path, "backend": self._backend.name},
        )
        return (await self.read_bytes(path)).decode(encoding, errors)

    # endregion

    # region: writing

    async def write(self, path: str, content: AsyncWritableContent, *, overwrite: bool = False) -> None:
        """Write binary content to *path*.  Creates parent folders implicitly.

        Args:
            path: Store-relative file path.
            content: ``bytes`` or async iterator of ``bytes``.
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
        await self._backend.write(self._require_file_path(path), content, overwrite=overwrite)
        log.info("write complete path=%r", path, extra={"op": "write", "path": path, "backend": _bk})

    async def write_text(self, path: str, text: str, *, encoding: str = "utf-8", overwrite: bool = False) -> None:
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
        ``await write(path, text.encode(encoding), overwrite=overwrite)``.
        """
        log.debug(
            "write_text path=%r encoding=%r overwrite=%r",
            path,
            encoding,
            overwrite,
            extra={"op": "write_text", "path": path, "backend": self._backend.name},
        )
        await self.write(path, text.encode(encoding), overwrite=overwrite)

    async def write_atomic(self, path: str, content: AsyncWritableContent, *, overwrite: bool = False) -> None:
        """Write binary content to *path* atomically.

        If the write fails or is interrupted, *path* is not left in a
        partial state.

        Args:
            path: Store-relative file path.
            content: ``bytes`` or async iterator of ``bytes``.
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
        await self._backend.write_atomic(self._require_file_path(path), content, overwrite=overwrite)
        log.info("write_atomic complete path=%r", path, extra={"op": "write_atomic", "path": path, "backend": _bk})

    # endregion

    # region: deleting

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
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
        await self._backend.delete(self._require_file_path(path), missing_ok=missing_ok)
        log.info("delete complete path=%r", path, extra={"op": "delete", "path": path, "backend": _bk})

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
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
        await self._backend.delete_folder(self._full_path(path), recursive=recursive, missing_ok=missing_ok)
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
    ) -> AsyncIterator[FileInfo]:
        """Yield ``FileInfo`` objects for files under *path*.

        Validation (capability check, max_depth) happens eagerly
        on call, not lazily on first iteration.

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
            Async iterator of ``FileInfo`` with store-relative paths.

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

        return self._list_files_inner(
            self._full_path(path),
            effective_recursive=effective_recursive,
            pattern=pattern,
            max_depth=max_depth,
            base_parts=base_parts,
        )

    async def _list_files_inner(
        self,
        full_path: str,
        *,
        effective_recursive: bool,
        pattern: str | None,
        max_depth: int | None,
        base_parts: int,
    ) -> AsyncIterator[FileInfo]:
        """Inner generator for :meth:`list_files`."""
        async for info in self._backend.list_files(
            full_path,
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

    def list_folders(self, path: str, *, max_depth: int | None = None) -> AsyncIterator[FolderEntry]:
        """Yield subfolders of *path* as ``FolderEntry`` objects.

        Validation (capability check, max_depth) happens eagerly
        on call, not lazily on first iteration.

        Args:
            path: Store-relative folder path.
            max_depth: Maximum folder depth to include.  ``None`` or ``0``
                returns immediate children only (default).  ``1`` adds
                grandchildren, and so on.

        Returns:
            Async iterator of ``FolderEntry`` with ``.name`` and ``.path`` (store-relative).

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
        return self._list_folders_inner(self._full_path(path), effective_depth=effective_depth)

    async def _list_folders_inner(self, full_path: str, *, effective_depth: int) -> AsyncIterator[FolderEntry]:
        """Inner generator for :meth:`list_folders` — BFS traversal."""
        current_level: list[str] = [full_path]
        for level in range(effective_depth + 1):
            next_level: list[str] = []
            for folder_path in current_level:
                async for entry in self._backend.list_folders(folder_path):
                    rebased = self._rebase_folder_entry(entry)
                    yield rebased
                    if level < effective_depth:
                        next_level.append(str(entry.path))
            current_level = next_level

    def iter_children(self, path: str) -> AsyncIterator[FileInfo | FolderEntry]:
        """Yield all immediate children (files and folders) of *path* in a single pass.

        Files are yielded as ``FileInfo``, folders as ``FolderEntry``.
        Both have ``.name`` and ``.path`` attributes (satisfying the
        ``PathEntry`` protocol) so callers can iterate uniformly.

        Validation (capability check) happens eagerly on call,
        not lazily on first iteration.

        Args:
            path: Store-relative folder path.

        Returns:
            Async iterator of ``FileInfo`` (files) and ``FolderEntry`` (folders).
        """
        _bk = self._backend.name
        log.debug("iter_children path=%r", path, extra={"op": "iter_children", "path": path, "backend": _bk})
        self._backend.capabilities.require(Capability.LIST, backend=_bk)
        return self._iter_children_inner(self._full_path(path))

    async def _iter_children_inner(self, full_path: str) -> AsyncIterator[FileInfo | FolderEntry]:
        """Inner generator for :meth:`iter_children`."""
        async for entry in self._backend.iter_children(full_path):
            if isinstance(entry, FolderEntry):
                yield self._rebase_folder_entry(entry)
            else:
                yield self._rebase_file_info(entry)

    def glob(self, pattern: str) -> AsyncIterator[FileInfo]:
        """Yield files matching a glob *pattern*, using the backend's native glob implementation.

        Requires ``Capability.GLOB``.  Validation (capability check) happens
        eagerly on call, not lazily on first iteration.

        Args:
            pattern: Glob pattern (e.g. ``"data/**/*.parquet"``).

        Returns:
            Async iterator of ``FileInfo`` with store-relative paths.

        Raises:
            CapabilityNotSupported: If the backend lacks ``GLOB``.
        """
        log.debug("glob pattern=%r", pattern, extra={"op": "glob", "path": pattern, "backend": self._backend.name})
        self._backend.capabilities.require(Capability.GLOB, backend=self._backend.name)
        full_pattern = f"{self._root}/{pattern}" if self._root else pattern
        return self._glob_inner(full_pattern)

    async def _glob_inner(self, full_pattern: str) -> AsyncIterator[FileInfo]:
        """Inner generator for :meth:`glob`."""
        async for info in self._backend.glob(full_pattern):
            yield self._rebase_file_info(info)

    # endregion

    # region: file operations

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
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
            if not await self._backend.is_file(src_path):
                raise NotFound(f"Source not found: {src}", path=src, backend=_bk)
            return
        await self._backend.move(src_path, dst_path, overwrite=overwrite)
        log.info("move complete src=%r dst=%r", src, dst, extra={"op": "move", "path": src, "backend": _bk})

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
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
            if not await self._backend.is_file(src_path):
                raise NotFound(f"Source not found: {src}", path=src, backend=_bk)
            return
        await self._backend.copy(src_path, dst_path, overwrite=overwrite)
        log.info("copy complete src=%r dst=%r", src, dst, extra={"op": "copy", "path": src, "backend": _bk})

    # endregion

    # region: metadata

    async def exists(self, path: str) -> bool:
        """Return ``True`` if *path* exists (file or folder).

        Args:
            path: Store-relative path.
        """
        log.debug("exists path=%r", path, extra={"op": "exists", "path": path, "backend": self._backend.name})
        return await self._backend.exists(self._full_path(path))

    async def is_file(self, path: str) -> bool:
        """Return ``True`` if *path* exists and is a file.

        Args:
            path: Store-relative path.
        """
        log.debug("is_file path=%r", path, extra={"op": "is_file", "path": path, "backend": self._backend.name})
        return await self._backend.is_file(self._full_path(path))

    async def is_folder(self, path: str) -> bool:
        """Return ``True`` if *path* exists and is a folder.

        Args:
            path: Store-relative path.
        """
        log.debug("is_folder path=%r", path, extra={"op": "is_folder", "path": path, "backend": self._backend.name})
        return await self._backend.is_folder(self._full_path(path))

    async def get_file_info(self, path: str) -> FileInfo:
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
        info = await self._backend.get_file_info(self._require_file_path(path))
        return self._rebase_file_info(info)

    async def get_folder_info(
        self,
        path: str,
        *,
        max_depth: int | None = None,
    ) -> FolderInfo:
        """Return a ``FolderInfo`` with aggregated size and file count for a folder.

        Args:
            path: Store-relative folder path.
            max_depth: Maximum folder depth to aggregate.  ``0`` means
                files directly in *path* only; ``1`` adds files in its
                immediate subfolders, and so on.  ``None`` (default)
                performs a full recursive traversal via the backend.

        Returns:
            ``FolderInfo``.

        Raises:
            NotFound: If the folder does not exist.
            ValueError: If *max_depth* is negative.
        """
        if max_depth is not None and max_depth < 0:
            msg = f"max_depth must be >= 0, got {max_depth}"
            raise ValueError(msg)
        _bk = self._backend.name
        log.debug(
            "get_folder_info path=%r max_depth=%r",
            path,
            max_depth,
            extra={"op": "get_folder_info", "path": path, "backend": _bk},
        )

        if max_depth is None:
            # Full recursive traversal via backend
            self._backend.capabilities.require(Capability.METADATA, backend=_bk)
            info = await self._backend.get_folder_info(self._full_path(path))
            return self._rebase_folder_info(info)

        # Depth-limited aggregation at the Store level
        self._backend.capabilities.require(Capability.LIST, backend=_bk)
        if not await self._backend.is_folder(self._full_path(path)):
            raise NotFound(
                f"Folder not found: {path}",
                path=path,
                backend=_bk,
            )

        file_count = 0
        total_size = 0
        latest_modified: datetime | None = None
        async for fi in self.list_files(path, max_depth=max_depth):
            file_count += 1
            total_size += fi.size
            if fi.modified_at is not None and (latest_modified is None or fi.modified_at > latest_modified):
                latest_modified = fi.modified_at

        rpath = RemotePath.from_backend_path(path) if path and path != "." else RemotePath.ROOT
        return FolderInfo(
            path=rpath,
            file_count=file_count,
            total_size=total_size,
            modified_at=latest_modified,
        )

    # endregion

    # region: lifecycle

    async def ping(self) -> None:
        """Verify that the backend is reachable.

        Raises:
            PermissionDenied: If credentials are invalid.
            NotFound: If the bucket, container, or root path does not
                exist.
            BackendUnavailable: If the backend cannot be reached.
        """
        _bk = self._backend.name
        log.debug("ping", extra={"op": "ping", "backend": _bk})
        await self._backend.check_health()
        log.info("ping OK", extra={"op": "ping", "backend": _bk})

    async def aclose(self) -> None:
        """Release backend resources.

        Called automatically when used as an async context manager.
        """
        if self._owns_backend:
            await self._backend.aclose()

    def child(self, subpath: str) -> AsyncStore:
        """Return a new ``AsyncStore`` scoped to *subpath* under the current root.

        The child shares the same backend instance.

        Args:
            subpath: Path segment to append to the current root.

        Returns:
            ``AsyncStore``.

        Raises:
            InvalidPath: If *subpath* is empty, contains ``..``
                segments, or includes null bytes.

        ```python
        data = store.child("data/2024")
        async for fi in data.list_files(""):
            ...  # lists files under <root>/data/2024/
        ```
        """
        validated = str(RemotePath(subpath))
        new_root = f"{self._root}/{validated}" if self._root else validated
        child_store = AsyncStore(backend=self._backend, root_path=new_root)
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

    def resolve(self, key: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` describing how *key* maps to storage.

        Delegates to the backend's ``resolve()`` and rebases the key
        so that ``plan.key`` is the store-relative key, not the
        backend-relative path.

        Args:
            key: Store-relative path.  ``""`` resolves the store root.

        Returns:
            A frozen ``ResolutionPlan``.
        """
        full_path = self._full_path(key)
        plan = self._backend.resolve(full_path)
        return dataclasses.replace(plan, key=key)

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
            async for fi in store.glob("**/*.csv"):
                ...
        ```
        """
        return self._backend.capabilities.supports(capability)

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        return f"AsyncStore(backend={self._backend.name!r}, root_path={self._root!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AsyncStore):
            return self._backend is other._backend and self._root == other._root
        return NotImplemented

    def __hash__(self) -> int:
        return hash((id(self._backend), self._root))

    async def __aenter__(self) -> AsyncStore:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

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
