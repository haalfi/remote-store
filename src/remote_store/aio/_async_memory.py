"""In-memory async backend -- tree-indexed, zero I/O, asyncio.Lock."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypeVar

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import AlreadyExists, DirectoryNotEmpty, InvalidPath, NotFound
from remote_store._models import FileInfo, FolderEntry, FolderInfo
from remote_store._path import RemotePath
from remote_store.aio._async_backend import AsyncBackend
from remote_store.backends._memory import _DirNode, _FileEntry, _FileSnapshot

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from remote_store.aio._types import AsyncWritableContent

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.GLOB})

log = logging.getLogger(__name__)
T = TypeVar("T")


class AsyncMemoryBackend(AsyncBackend):
    """In-memory async backend using a tree-indexed data structure.

    Zero dependencies, no filesystem access, no network.  Designed as a
    drop-in async backend for unit testing, interactive exploration, and
    documentation examples.

    All 8 capabilities are supported.  The full conformance suite passes
    with zero skips.
    """

    def __init__(self) -> None:
        self._root = _DirNode()
        self._file_count = 0
        self._folder_count = 0
        self._lock = asyncio.Lock()

    # region: properties

    @property
    def name(self) -> str:
        return "async-memory"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # endregion

    # region: public methods

    async def exists(self, path: str) -> bool:
        """Check if a file or folder exists.

        Args:
            path: Backend-relative key, or ``""`` for the root.

        Returns:
            ``True`` if a file or folder exists at *path*.
        """
        segments = _split_path(path)
        async with self._lock:
            if not segments:
                return True  # root always exists
            return self._traverse(segments) is not None

    async def is_file(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing file.

        Args:
            path: Backend-relative key.

        Returns:
            ``True`` if *path* exists and is a file.
        """
        segments = _split_path(path)
        async with self._lock:
            if not segments:
                return False
            return isinstance(self._traverse(segments), _FileEntry)

    async def is_folder(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing folder.

        Args:
            path: Backend-relative key, or ``""`` for the root.

        Returns:
            ``True`` if *path* exists and is a folder.
        """
        segments = _split_path(path)
        async with self._lock:
            if not segments:
                return True  # root is a folder
            return isinstance(self._traverse(segments), _DirNode)

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Open a file for reading and return an async iterator of byte chunks.

        Args:
            path: Backend-relative key.

        Returns:
            An async iterator yielding a single byte chunk (the full content).

        Raises:
            NotFound: If the file does not exist.
        """
        segments = _split_path(path)
        async with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _FileEntry):
                raise NotFound(f"File not found: {path}", path=path, backend="async-memory")
            snapshot = bytes(node.data)
        yield snapshot

    async def read_bytes(self, path: str) -> bytes:
        """Read the full content of a file as bytes.

        Args:
            path: Backend-relative key.

        Returns:
            The file content.

        Raises:
            NotFound: If the file does not exist.
        """
        segments = _split_path(path)
        async with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _FileEntry):
                raise NotFound(f"File not found: {path}", path=path, backend="async-memory")
            return bytes(node.data)

    async def write(self, path: str, content: AsyncWritableContent, *, overwrite: bool = False) -> None:
        """Write content to a file.

        Args:
            path: Backend-relative key.
            content: Data to write (bytes or async iterator of bytes).
            overwrite: If ``False``, raise if file already exists.

        Raises:
            AlreadyExists: If the file exists and ``overwrite`` is ``False``.
            InvalidPath: If the path is empty or conflicts with a directory.
        """
        segments = _split_path(path)
        if not segments:
            raise InvalidPath("Path must not be empty for file operations", path=path, backend="async-memory")

        # Materialize content outside the lock.
        if isinstance(content, bytes):
            raw = bytearray(content)
        else:
            chunks: list[bytes] = []
            async for chunk in content:
                chunks.append(chunk)
            raw = bytearray(b"".join(chunks))

        async with self._lock:
            parent = self._ensure_parents(segments)
            leaf = segments[-1]
            existing = parent.children.get(leaf)

            if isinstance(existing, _DirNode):
                raise InvalidPath(
                    f"Cannot write -- '{leaf}' exists as a directory",
                    path=path,
                    backend="async-memory",
                )
            if isinstance(existing, _FileEntry):
                if not overwrite:
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend="async-memory")
                existing.data[:] = raw
                existing.modified_at = datetime.now(timezone.utc)
            else:
                parent.children[leaf] = _FileEntry(
                    data=raw,
                    modified_at=datetime.now(timezone.utc),
                )
                self._file_count += 1

    async def write_atomic(self, path: str, content: AsyncWritableContent, *, overwrite: bool = False) -> None:
        """Write content atomically (same as write for in-memory backend).

        Args:
            path: Backend-relative key.
            content: Data to write.
            overwrite: If ``False``, raise if file already exists.

        Raises:
            AlreadyExists: If the file exists and ``overwrite`` is ``False``.
        """
        await self.write(path, content, overwrite=overwrite)

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        Args:
            path: Backend-relative key.
            missing_ok: If ``True``, do not raise when the file is absent.

        Raises:
            NotFound: If the file is missing and ``missing_ok`` is ``False``.
            InvalidPath: If the path is empty.
        """
        segments = _split_path(path)
        if not segments:
            raise InvalidPath("Path must not be empty for file operations", path=path, backend="async-memory")

        async with self._lock:
            parent = self._traverse(segments[:-1])
            if parent is None or not isinstance(parent, _DirNode):
                if not missing_ok:
                    raise NotFound(f"File not found: {path}", path=path, backend="async-memory")
                return
            leaf = segments[-1]
            existing = parent.children.get(leaf)
            if not isinstance(existing, _FileEntry):
                if not missing_ok:
                    raise NotFound(f"File not found: {path}", path=path, backend="async-memory")
                return
            del parent.children[leaf]
            self._file_count -= 1

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder.

        Args:
            path: Backend-relative key.
            recursive: If ``True``, delete all contents first.
            missing_ok: If ``True``, do not raise when absent.

        Raises:
            NotFound: If the folder is missing and ``missing_ok`` is ``False``.
            DirectoryNotEmpty: If non-empty and ``recursive`` is ``False``.
            InvalidPath: If the path is empty.
        """
        segments = _split_path(path)
        if not segments:
            raise InvalidPath("Path must not be empty for folder delete", path=path, backend="async-memory")

        async with self._lock:
            parent = self._traverse(segments[:-1])
            if parent is None or not isinstance(parent, _DirNode):
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend="async-memory")
                return

            leaf = segments[-1]
            node = parent.children.get(leaf)
            if node is None or not isinstance(node, _DirNode):
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend="async-memory")
                return

            if not recursive:
                if node.children:
                    raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend="async-memory")
                del parent.children[leaf]
                self._folder_count -= 1
            else:
                files, folders = _count_subtree(node)
                del parent.children[leaf]
                self._file_count -= files
                self._folder_count -= folders + 1  # +1 for the node itself

    async def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> AsyncIterator[FileInfo]:
        """List files under ``path``.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.
            recursive: If ``True``, include files in all subdirectories.
            max_depth: Optional maximum folder depth to traverse.

        Returns:
            An async iterator of ``FileInfo`` objects.
        """
        segments = _split_path(path)
        async with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _DirNode):
                return
            prefix = "/".join(segments) if segments else ""
            if recursive:
                snapshot = _snapshot_subtree(node)
            else:
                children_snap = {
                    name: _FileSnapshot(child) for name, child in node.children.items() if isinstance(child, _FileEntry)
                }
        if recursive:
            for info in _collect_files_from_snapshot(snapshot, prefix, max_depth=max_depth):
                yield info
        else:
            for name, child in children_snap.items():
                child_path = f"{prefix}/{name}" if prefix else name
                yield FileInfo(
                    path=RemotePath(child_path),
                    name=name,
                    size=child.size,
                    modified_at=child.modified_at,
                    content_type=child.content_type,
                )

    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        """List immediate subfolders under ``path``.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            An async iterator of ``FolderEntry`` objects.
        """
        segments = _split_path(path)
        async with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _DirNode):
                return
            prefix = "/".join(segments) if segments else ""
            children_snapshot = dict(node.children)
        for name, child in children_snapshot.items():
            if isinstance(child, _DirNode):
                yield FolderEntry(
                    path=RemotePath(f"{prefix}/{name}" if prefix else name),
                    name=name,
                )

    async def iter_children(self, path: str) -> AsyncIterator[FileInfo | FolderEntry]:
        """Yield both files and folders under ``path`` in a single pass.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            An async iterator of ``FileInfo`` (files) and ``FolderEntry`` (folders).
        """
        segments = _split_path(path)
        async with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _DirNode):
                return
            prefix = "/".join(segments) if segments else ""
            children_snapshot = {
                name: _FileSnapshot(child) if isinstance(child, _FileEntry) else child
                for name, child in node.children.items()
            }
        for name, child in children_snapshot.items():
            if isinstance(child, _FileSnapshot):
                child_path = f"{prefix}/{name}" if prefix else name
                yield FileInfo(
                    path=RemotePath(child_path),
                    name=name,
                    size=child.size,
                    modified_at=child.modified_at,
                    content_type=child.content_type,
                )
            elif isinstance(child, _DirNode):
                child_path = f"{prefix}/{name}" if prefix else name
                yield FolderEntry(path=RemotePath(child_path), name=name)

    async def get_file_info(self, path: str) -> FileInfo:
        """Get metadata for a file.

        Args:
            path: Backend-relative key.

        Returns:
            A ``FileInfo`` with size, modification time, etc.

        Raises:
            NotFound: If the file does not exist.
        """
        segments = _split_path(path)
        if not segments:
            raise NotFound("File not found: (empty path)", path=path, backend="async-memory")
        async with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _FileEntry):
                raise NotFound(f"File not found: {path}", path=path, backend="async-memory")
            return FileInfo(
                path=RemotePath(path),
                name=segments[-1],
                size=len(node.data),
                modified_at=node.modified_at,
                content_type=node.content_type,
            )

    async def get_folder_info(self, path: str) -> FolderInfo:
        """Get metadata for a folder.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            A ``FolderInfo`` with file count, total size, etc.

        Raises:
            NotFound: If the folder does not exist.
        """
        segments = _split_path(path)
        async with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _DirNode):
                raise NotFound(f"Folder not found: {path}", path=path, backend="async-memory")
            file_count = 0
            total_size = 0
            latest: datetime | None = None
            stack: list[_DirNode] = [node]
            while stack:
                current = stack.pop()
                for child in current.children.values():
                    if isinstance(child, _FileEntry):
                        file_count += 1
                        total_size += len(child.data)
                        if latest is None or child.modified_at > latest:
                            latest = child.modified_at
                    elif isinstance(child, _DirNode):
                        stack.append(child)
            return FolderInfo(
                path=RemotePath.from_backend_path(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest,
            )

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move or rename a file.

        Args:
            src: Backend-relative source key.
            dst: Backend-relative destination key.
            overwrite: If ``True``, replace any existing file at *dst*.

        Raises:
            NotFound: If ``src`` does not exist.
            AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
            InvalidPath: If source or destination path is empty.
        """
        src_segments = _split_path(src)
        dst_segments = _split_path(dst)
        if not src_segments:
            raise InvalidPath("Source path must not be empty", path=src, backend="async-memory")
        if not dst_segments:
            raise InvalidPath("Destination path must not be empty", path=dst, backend="async-memory")

        if src_segments == dst_segments:
            # Verify source exists, then no-op.
            async with self._lock:
                parent = self._traverse(src_segments[:-1])
                leaf = parent.children.get(src_segments[-1]) if isinstance(parent, _DirNode) else None
                if not isinstance(leaf, _FileEntry):
                    raise NotFound(f"Source not found: {src}", path=src, backend="async-memory")
            return

        async with self._lock:
            # Find source
            src_parent = self._traverse(src_segments[:-1])
            if not isinstance(src_parent, _DirNode):
                raise NotFound(f"Source not found: {src}", path=src, backend="async-memory")
            src_leaf = src_segments[-1]
            entry = src_parent.children.get(src_leaf)
            if not isinstance(entry, _FileEntry):
                raise NotFound(f"Source not found: {src}", path=src, backend="async-memory")

            # Prepare destination
            dst_parent = self._ensure_parents(dst_segments)
            dst_leaf = dst_segments[-1]
            dst_existing = dst_parent.children.get(dst_leaf)

            if isinstance(dst_existing, _DirNode):
                raise InvalidPath(
                    f"Cannot move -- destination '{dst}' exists as a directory",
                    path=dst,
                    backend="async-memory",
                )
            if isinstance(dst_existing, _FileEntry) and not overwrite:
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend="async-memory")

            # If overwriting, the net file count doesn't change
            if isinstance(dst_existing, _FileEntry):
                self._file_count -= 1

            # Detach from source, attach to destination
            del src_parent.children[src_leaf]
            dst_parent.children[dst_leaf] = entry

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        Args:
            src: Backend-relative source key.
            dst: Backend-relative destination key.
            overwrite: If ``True``, replace any existing file at *dst*.

        Raises:
            NotFound: If ``src`` does not exist.
            AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
            InvalidPath: If source or destination path is empty.
        """
        src_segments = _split_path(src)
        dst_segments = _split_path(dst)
        if not src_segments:
            raise InvalidPath("Source path must not be empty", path=src, backend="async-memory")
        if not dst_segments:
            raise InvalidPath("Destination path must not be empty", path=dst, backend="async-memory")

        async with self._lock:
            # Find source
            src_node = self._traverse(src_segments)
            if not isinstance(src_node, _FileEntry):
                raise NotFound(f"Source not found: {src}", path=src, backend="async-memory")

            # Prepare destination
            dst_parent = self._ensure_parents(dst_segments)
            dst_leaf = dst_segments[-1]
            dst_existing = dst_parent.children.get(dst_leaf)

            if isinstance(dst_existing, _DirNode):
                raise InvalidPath(
                    f"Cannot copy -- destination '{dst}' exists as a directory",
                    path=dst,
                    backend="async-memory",
                )
            if isinstance(dst_existing, _FileEntry) and not overwrite:
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend="async-memory")

            new_entry = _FileEntry(
                data=bytearray(src_node.data),
                modified_at=datetime.now(timezone.utc),
                content_type=src_node.content_type,
            )

            if not isinstance(dst_existing, _FileEntry):
                self._file_count += 1

            dst_parent.children[dst_leaf] = new_entry

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        return f"AsyncMemoryBackend(files={self._file_count}, folders={self._folder_count})"

    # endregion

    # region: private helpers

    def _traverse(self, segments: list[str]) -> _DirNode | _FileEntry | None:
        """Walk the tree following *segments*. Returns None if any segment is missing."""
        node: _DirNode | _FileEntry = self._root
        for seg in segments:
            if not isinstance(node, _DirNode):
                return None
            child = node.children.get(seg)
            if child is None:
                return None
            node = child
        return node

    def _ensure_parents(self, segments: list[str]) -> _DirNode:
        """Create intermediate directories as needed, return the parent node."""
        node = self._root
        for seg in segments[:-1]:
            child = node.children.get(seg)
            if child is None:
                child = _DirNode()
                node.children[seg] = child
                self._folder_count += 1
            elif isinstance(child, _FileEntry):
                raise InvalidPath(
                    f"Cannot create directory -- '{seg}' exists as a file",
                    path="/".join(segments),
                    backend="async-memory",
                )
            node = child
        return node

    # endregion


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions, no instance state)
# ---------------------------------------------------------------------------


def _split_path(path: str) -> list[str]:
    """Split and validate a path, returning a list of segments.

    Raises:
        InvalidPath: For absolute paths, ``..`` segments, or null bytes.
    """
    if "\0" in path:
        raise InvalidPath("Path contains null byte", path=path, backend="async-memory")
    if path.startswith("/"):
        raise InvalidPath("Absolute paths are not allowed", path=path, backend="async-memory")

    segments: list[str] = []
    for seg in path.split("/"):
        if seg == "" or seg == ".":
            continue
        if seg == "..":
            raise InvalidPath("Path contains '..' segment", path=path, backend="async-memory")
        segments.append(seg)
    return segments


def _count_subtree(node: _DirNode) -> tuple[int, int]:
    """Count files and sub-folders in a subtree (excludes the node itself)."""
    files = 0
    folders = 0
    stack: list[_DirNode] = [node]
    while stack:
        current = stack.pop()
        for child in current.children.values():
            if isinstance(child, _FileEntry):
                files += 1
            else:
                folders += 1
                stack.append(child)
    return files, folders


def _snapshot_subtree(node: _DirNode) -> dict[str, _FileSnapshot | dict[str, Any]]:
    """Deep-copy the tree structure under *node* for lock-free iteration.

    Returns a nested dict where file leaves are ``_FileSnapshot`` objects
    (frozen scalar copies, not live references) and directories are plain
    dicts mirroring the ``children`` structure.  Uses an iterative approach
    to avoid recursion-limit concerns on deep trees.
    """
    root: dict[str, Any] = {}
    # Stack of (source _DirNode children, target snapshot dict)
    stack: list[tuple[dict[str, _DirNode | _FileEntry], dict[str, Any]]] = [
        (node.children, root),
    ]
    while stack:
        src_children, dst = stack.pop()
        for name, child in src_children.items():
            if isinstance(child, _FileEntry):
                dst[name] = _FileSnapshot(child)
            elif isinstance(child, _DirNode):
                sub: dict[str, Any] = {}
                dst[name] = sub
                stack.append((child.children, sub))
    return root


def _collect_files_from_snapshot(
    snapshot: dict[str, Any],
    prefix: str,
    *,
    max_depth: int | None = None,
) -> list[FileInfo]:
    """Collect FileInfo objects from a snapshot dict (outside lock).

    Uses iterative DFS for consistency with ``_count_subtree`` and
    ``get_folder_info``, avoiding recursion-limit concerns on deep trees.
    """
    results: list[FileInfo] = []
    stack: list[tuple[dict[str, Any], str, int]] = [(snapshot, prefix, 0)]
    while stack:
        current, cur_prefix, depth = stack.pop()
        for name, child in current.items():
            child_path = f"{cur_prefix}/{name}" if cur_prefix else name
            if isinstance(child, _FileSnapshot):
                results.append(
                    FileInfo(
                        path=RemotePath(child_path),
                        name=name,
                        size=child.size,
                        modified_at=child.modified_at,
                        content_type=child.content_type,
                    )
                )
            elif isinstance(child, dict):
                if max_depth is not None and depth >= max_depth:
                    continue
                stack.append((child, child_path, depth + 1))
    return results
