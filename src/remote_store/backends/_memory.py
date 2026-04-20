"""In-memory backend — tree-indexed, zero dependencies, no I/O."""

from __future__ import annotations

import contextlib
import io
import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, BinaryIO

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import AlreadyExists, DirectoryNotEmpty, InvalidPath, NotFound
from remote_store._models import FileInfo, FolderEntry, FolderInfo, WriteResult
from remote_store._path import RemotePath
from remote_store.backends._memory_tree import DirNode as _DirNode
from remote_store.backends._memory_tree import FileEntry as _FileEntry
from remote_store.backends._memory_tree import FileSnapshot as _FileSnapshot

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from remote_store._types import WritableContent

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.GLOB, Capability.LAZY_READ})

log = logging.getLogger(__name__)


class MemoryBackend(Backend):
    """In-memory backend using a tree-indexed data structure.

    Zero dependencies, no filesystem access, no network.  Designed as a
    drop-in backend for unit testing, interactive exploration, and
    documentation examples.

    All capabilities except ``GLOB`` are supported.  The full conformance
    suite passes with zero skips.
    """

    def __init__(self) -> None:
        self._root = _DirNode()
        self._file_count = 0
        self._folder_count = 0
        self._lock = threading.Lock()

    # region: properties

    @property
    def name(self) -> str:
        return "memory"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # endregion

    # region: public methods

    def exists(self, path: str) -> bool:
        segments = self._split_path(path)
        with self._lock:
            if not segments:
                return True  # root always exists
            return self._traverse(segments) is not None

    def is_file(self, path: str) -> bool:
        segments = self._split_path(path)
        with self._lock:
            if not segments:
                return False
            return isinstance(self._traverse(segments), _FileEntry)

    def is_folder(self, path: str) -> bool:
        segments = self._split_path(path)
        with self._lock:
            if not segments:
                return True  # root is a folder
            return isinstance(self._traverse(segments), _DirNode)

    def read(self, path: str) -> BinaryIO:
        segments = self._split_path(path)
        with self._lock:
            node = self._traverse(segments)
            if isinstance(node, _DirNode):
                raise InvalidPath(f"Not a file: {path}", path=path, backend="memory")
            if not isinstance(node, _FileEntry):
                raise NotFound(f"File not found: {path}", path=path, backend="memory")
            result = io.BytesIO(node.data)
        return result

    def read_bytes(self, path: str) -> bytes:
        segments = self._split_path(path)
        with self._lock:
            node = self._traverse(segments)
            if isinstance(node, _DirNode):
                raise InvalidPath(f"Not a file: {path}", path=path, backend="memory")
            if not isinstance(node, _FileEntry):
                raise NotFound(f"File not found: {path}", path=path, backend="memory")
            return bytes(node.data)

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        segments = self._split_path(path)
        if not segments:
            raise InvalidPath("Path must not be empty for file operations", path=path, backend="memory")

        # Build bytearray without a second copy: for streams, accumulate
        # chunks directly into the target bytearray instead of reading all
        # bytes first and then copying into a new bytearray.
        if isinstance(content, bytes):
            raw = bytearray(content)
        else:
            raw = bytearray()
            while True:
                chunk = content.read(65536)
                if not chunk:
                    break
                raw.extend(chunk)

        stored_meta = dict(metadata) if metadata else None
        with self._lock:
            # Capture ``now`` under the lock so that ``modified_at`` values
            # reflect lock-acquisition order: a late-acquiring writer must
            # not stamp an earlier timestamp than an earlier-acquiring writer
            # on the same key.
            now = datetime.now(timezone.utc)
            parent = self._ensure_parents(segments)
            leaf = segments[-1]
            existing = parent.children.get(leaf)

            if isinstance(existing, _DirNode):
                raise InvalidPath(
                    f"Cannot write — '{leaf}' exists as a directory",
                    path=path,
                    backend="memory",
                )
            if isinstance(existing, _FileEntry):
                if not overwrite:
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend="memory")
                existing.data[:] = raw
                existing.modified_at = now
                existing.metadata = stored_meta
            else:
                parent.children[leaf] = _FileEntry(
                    data=raw,
                    modified_at=now,
                    metadata=stored_meta,
                )
                self._file_count += 1
        return WriteResult(
            path=RemotePath(path),
            size=len(raw),
            source="native",
            last_modified=now,
            metadata=metadata,
        )

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        return self.write(path, content, overwrite=overwrite, metadata=metadata)

    @contextlib.contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        segments = self._split_path(path)
        if not segments:
            raise InvalidPath("Path must not be empty for file operations", path=path, backend="memory")
        if not overwrite:
            with self._lock:
                if isinstance(self._traverse(segments), _FileEntry):
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend="memory")
        buf = io.BytesIO()
        yield buf
        buf.seek(0)
        self.write(path, buf.getvalue(), overwrite=overwrite)

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        segments = self._split_path(path)
        if not segments:
            raise InvalidPath("Path must not be empty for file operations", path=path, backend="memory")

        with self._lock:
            parent = self._traverse(segments[:-1])
            if parent is None or not isinstance(parent, _DirNode):
                if not missing_ok:
                    raise NotFound(f"File not found: {path}", path=path, backend="memory")
                return
            leaf = segments[-1]
            existing = parent.children.get(leaf)
            if isinstance(existing, _DirNode):
                raise InvalidPath(f"Not a file: {path}", path=path, backend="memory")
            if not isinstance(existing, _FileEntry):
                if not missing_ok:
                    raise NotFound(f"File not found: {path}", path=path, backend="memory")
                return
            del parent.children[leaf]
            self._file_count -= 1

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        segments = self._split_path(path)
        if not segments:
            raise InvalidPath("Path must not be empty for folder delete", path=path, backend="memory")

        with self._lock:
            parent = self._traverse(segments[:-1])
            if parent is None or not isinstance(parent, _DirNode):
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend="memory")
                return

            leaf = segments[-1]
            node = parent.children.get(leaf)
            if isinstance(node, _FileEntry):
                raise InvalidPath(f"Not a folder: {path}", path=path, backend="memory")
            if node is None or not isinstance(node, _DirNode):
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend="memory")
                return

            if not recursive:
                if node.children:
                    raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend="memory")
                del parent.children[leaf]
                self._folder_count -= 1
            else:
                files, folders = self._count_subtree(node)
                del parent.children[leaf]
                self._file_count -= files
                self._folder_count -= folders + 1  # +1 for the node itself

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        segments = self._split_path(path)
        with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _DirNode):
                return
            prefix = "/".join(segments) if segments else ""
            if recursive:
                snapshot = self._snapshot_subtree(node)
            else:
                children_snap = {
                    name: _FileSnapshot(child) for name, child in node.children.items() if isinstance(child, _FileEntry)
                }
        if recursive:
            yield from self._collect_files_from_snapshot(snapshot, prefix, max_depth=max_depth)
        else:
            for name, child in children_snap.items():
                child_path = f"{prefix}/{name}" if prefix else name
                yield FileInfo(
                    path=RemotePath(child_path),
                    name=name,
                    size=child.size,
                    modified_at=child.modified_at,
                    content_type=child.content_type,
                    metadata=child.metadata,
                )

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        segments = self._split_path(path)
        with self._lock:
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

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        segments = self._split_path(path)
        with self._lock:
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
                    metadata=child.metadata,
                )
            elif isinstance(child, _DirNode):
                child_path = f"{prefix}/{name}" if prefix else name
                yield FolderEntry(path=RemotePath(child_path), name=name)

    def get_file_info(self, path: str) -> FileInfo:
        segments = self._split_path(path)
        if not segments:
            raise NotFound("File not found: (empty path)", path=path, backend="memory")
        with self._lock:
            node = self._traverse(segments)
            if isinstance(node, _DirNode):
                raise InvalidPath(f"Not a file: {path}", path=path, backend="memory")
            if not isinstance(node, _FileEntry):
                raise NotFound(f"File not found: {path}", path=path, backend="memory")
            return FileInfo(
                path=RemotePath(path),
                name=segments[-1],
                size=len(node.data),
                modified_at=node.modified_at,
                content_type=node.content_type,
                metadata=node.metadata,
            )

    def get_folder_info(self, path: str) -> FolderInfo:
        segments = self._split_path(path)
        with self._lock:
            node = self._traverse(segments)
            if isinstance(node, _FileEntry):
                raise InvalidPath(f"Not a folder: {path}", path=path, backend="memory")
            if not isinstance(node, _DirNode):
                raise NotFound(f"Folder not found: {path}", path=path, backend="memory")
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

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        src_segments = self._split_path(src)
        dst_segments = self._split_path(dst)
        if not src_segments:
            raise InvalidPath("Source path must not be empty", path=src, backend="memory")
        if not dst_segments:
            raise InvalidPath("Destination path must not be empty", path=dst, backend="memory")

        if src_segments == dst_segments:
            # Verify source exists and is a file, then no-op.
            with self._lock:
                parent = self._traverse(src_segments[:-1])
                leaf = parent.children.get(src_segments[-1]) if isinstance(parent, _DirNode) else None
                if isinstance(leaf, _DirNode):
                    raise InvalidPath(f"Source is a directory: {src}", path=src, backend="memory")
                if not isinstance(leaf, _FileEntry):
                    raise NotFound(f"Source not found: {src}", path=src, backend="memory")
            return

        with self._lock:
            # Find source
            src_parent = self._traverse(src_segments[:-1])
            if not isinstance(src_parent, _DirNode):
                raise NotFound(f"Source not found: {src}", path=src, backend="memory")
            src_leaf = src_segments[-1]
            entry = src_parent.children.get(src_leaf)
            if isinstance(entry, _DirNode):
                raise InvalidPath(f"Source is a directory: {src}", path=src, backend="memory")
            if not isinstance(entry, _FileEntry):
                raise NotFound(f"Source not found: {src}", path=src, backend="memory")

            # Prepare destination
            dst_parent = self._ensure_parents(dst_segments)
            dst_leaf = dst_segments[-1]
            dst_existing = dst_parent.children.get(dst_leaf)

            if isinstance(dst_existing, _DirNode):
                raise InvalidPath(
                    f"Cannot move — destination '{dst}' exists as a directory",
                    path=dst,
                    backend="memory",
                )
            if isinstance(dst_existing, _FileEntry) and not overwrite:
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend="memory")

            # If overwriting, the net file count doesn't change
            if isinstance(dst_existing, _FileEntry):
                self._file_count -= 1

            # Detach from source, attach to destination
            del src_parent.children[src_leaf]
            dst_parent.children[dst_leaf] = entry

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        src_segments = self._split_path(src)
        dst_segments = self._split_path(dst)
        if not src_segments:
            raise InvalidPath("Source path must not be empty", path=src, backend="memory")
        if not dst_segments:
            raise InvalidPath("Destination path must not be empty", path=dst, backend="memory")

        with self._lock:
            # Find source
            src_node = self._traverse(src_segments)
            if isinstance(src_node, _DirNode):
                raise InvalidPath(f"Source is a directory: {src}", path=src, backend="memory")
            if not isinstance(src_node, _FileEntry):
                raise NotFound(f"Source not found: {src}", path=src, backend="memory")

            # Self-copy is a no-op
            if src_segments == dst_segments:
                return

            # Prepare destination
            dst_parent = self._ensure_parents(dst_segments)
            dst_leaf = dst_segments[-1]
            dst_existing = dst_parent.children.get(dst_leaf)

            if isinstance(dst_existing, _DirNode):
                raise InvalidPath(
                    f"Cannot copy — destination '{dst}' exists as a directory",
                    path=dst,
                    backend="memory",
                )
            if isinstance(dst_existing, _FileEntry) and not overwrite:
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend="memory")

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
        return f"MemoryBackend(files={self._file_count}, folders={self._folder_count})"

    # endregion

    # region: private helpers

    @staticmethod
    def _split_path(path: str) -> list[str]:
        """Split and validate a path, returning a list of segments.

        Raises:
            InvalidPath: For absolute paths, ``..`` segments, or null bytes.
        """
        if "\0" in path:
            raise InvalidPath("Path contains null byte", path=path, backend="memory")
        if path.startswith("/"):
            raise InvalidPath("Absolute paths are not allowed", path=path, backend="memory")

        segments: list[str] = []
        for seg in path.split("/"):
            if seg == "" or seg == ".":
                continue
            if seg == "..":
                raise InvalidPath("Path contains '..' segment", path=path, backend="memory")
            segments.append(seg)
        return segments

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
                    f"Cannot create directory — '{seg}' exists as a file",
                    path="/".join(segments),
                    backend="memory",
                )
            node = child
        return node

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def _collect_files_from_snapshot(
        snapshot: dict[str, Any],
        prefix: str,
        *,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        """Yield FileInfo objects from a snapshot dict (outside lock).

        Uses iterative DFS for consistency with ``_count_subtree`` and
        ``get_folder_info``, avoiding recursion-limit concerns on deep trees.
        """
        stack: list[tuple[dict[str, Any], str, int]] = [(snapshot, prefix, 0)]
        while stack:
            current, cur_prefix, depth = stack.pop()
            for name, child in current.items():
                child_path = f"{cur_prefix}/{name}" if cur_prefix else name
                if isinstance(child, _FileSnapshot):
                    yield FileInfo(
                        path=RemotePath(child_path),
                        name=name,
                        size=child.size,
                        modified_at=child.modified_at,
                        content_type=child.content_type,
                        metadata=child.metadata,
                    )
                elif isinstance(child, dict):
                    if max_depth is not None and depth >= max_depth:
                        continue
                    stack.append((child, child_path, depth + 1))

    # endregion
