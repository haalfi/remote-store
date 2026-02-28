"""In-memory backend — tree-indexed, zero dependencies, no I/O."""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, BinaryIO, cast

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import AlreadyExists, DirectoryNotEmpty, InvalidPath, NotFound
from remote_store._models import FileInfo, FolderInfo
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._types import WritableContent

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.GLOB})


# ---------------------------------------------------------------------------
# Internal data structures (MEM-DS-002, MEM-DS-003, MEM-DS-004)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _FileEntry:
    data: bytearray
    modified_at: datetime
    content_type: str | None = None


@dataclass(slots=True)
class _DirNode:
    children: dict[str, _DirNode | _FileEntry] = field(default_factory=dict)


class MemoryBackend(Backend):
    """In-memory backend using a tree-indexed data structure.

    Zero dependencies, no filesystem access, no network.  Designed as a
    drop-in backend for unit testing, interactive exploration, and
    documentation examples.

    All 8 capabilities are supported.  The full conformance suite passes
    with zero skips.
    """

    def __init__(self) -> None:
        self._root = _DirNode()
        self._file_count = 0
        self._folder_count = 0
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"MemoryBackend(files={self._file_count}, folders={self._folder_count})"

    @property
    def name(self) -> str:
        return "memory"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # ------------------------------------------------------------------
    # Path helpers (MEM-DS-005)
    # ------------------------------------------------------------------

    @staticmethod
    def _split_path(path: str) -> list[str]:
        """Split and validate a path, returning a list of segments.

        :raises InvalidPath: For absolute paths, ``..`` segments, or null bytes.
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

    # ------------------------------------------------------------------
    # Existence checks (BE-004, BE-005)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Read operations (MEM-010, MEM-011)
    # ------------------------------------------------------------------

    def read(self, path: str) -> BinaryIO:
        segments = self._split_path(path)
        with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _FileEntry):
                raise NotFound(f"File not found: {path}", path=path, backend="memory")
            snapshot = bytes(node.data)
        return io.BufferedReader(cast("io.RawIOBase", io.BytesIO(snapshot)))

    def read_bytes(self, path: str) -> bytes:
        segments = self._split_path(path)
        with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _FileEntry):
                raise NotFound(f"File not found: {path}", path=path, backend="memory")
            return bytes(node.data)

    # ------------------------------------------------------------------
    # Write operations (MEM-012, MEM-013)
    # ------------------------------------------------------------------

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        segments = self._split_path(path)
        if not segments:
            raise InvalidPath("Path must not be empty for file operations", path=path, backend="memory")

        raw = content if isinstance(content, bytes) else content.read()

        with self._lock:
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
                existing.modified_at = datetime.now(timezone.utc)
            else:
                parent.children[leaf] = _FileEntry(
                    data=bytearray(raw),
                    modified_at=datetime.now(timezone.utc),
                )
                self._file_count += 1

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        self.write(path, content, overwrite=overwrite)

    # ------------------------------------------------------------------
    # Delete operations (BE-012, MEM-014)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Listing (BE-014, BE-015)
    # ------------------------------------------------------------------

    def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
        segments = self._split_path(path)
        with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _DirNode):
                return
            prefix = "/".join(segments) if segments else ""
            results = self._collect_files(node, prefix, recursive=recursive)
        yield from results

    @staticmethod
    def _collect_files(
        node: _DirNode,
        prefix: str,
        *,
        recursive: bool,
    ) -> list[FileInfo]:
        """Collect FileInfo objects from a directory node (under lock).

        Uses iterative DFS for consistency with ``_count_subtree`` and
        ``get_folder_info``, avoiding recursion-limit concerns on deep trees.
        """
        results: list[FileInfo] = []
        stack: list[tuple[_DirNode, str]] = [(node, prefix)]
        while stack:
            current, cur_prefix = stack.pop()
            for name, child in current.children.items():
                child_path = f"{cur_prefix}/{name}" if cur_prefix else name
                if isinstance(child, _FileEntry):
                    results.append(
                        FileInfo(
                            path=RemotePath(child_path),
                            name=name,
                            size=len(child.data),
                            modified_at=child.modified_at,
                            content_type=child.content_type,
                        )
                    )
                elif recursive and isinstance(child, _DirNode):
                    stack.append((child, child_path))
        return results

    def list_folders(self, path: str) -> Iterator[str]:
        segments = self._split_path(path)
        with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _DirNode):
                return
            results = [name for name, child in node.children.items() if isinstance(child, _DirNode)]
        yield from results

    # ------------------------------------------------------------------
    # Metadata (BE-016, BE-017, MEM-015)
    # ------------------------------------------------------------------

    def get_file_info(self, path: str) -> FileInfo:
        segments = self._split_path(path)
        if not segments:
            raise NotFound("File not found: (empty path)", path=path, backend="memory")
        with self._lock:
            node = self._traverse(segments)
            if not isinstance(node, _FileEntry):
                raise NotFound(f"File not found: {path}", path=path, backend="memory")
            return FileInfo(
                path=RemotePath(path),
                name=segments[-1],
                size=len(node.data),
                modified_at=node.modified_at,
                content_type=node.content_type,
            )

    def get_folder_info(self, path: str) -> FolderInfo:
        segments = self._split_path(path)
        with self._lock:
            node = self._traverse(segments)
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
                path=RemotePath(path) if path else RemotePath("."),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest,
            )

    # ------------------------------------------------------------------
    # Move and copy (MEM-016, MEM-016b)
    # ------------------------------------------------------------------

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        src_segments = self._split_path(src)
        dst_segments = self._split_path(dst)
        if not src_segments:
            raise InvalidPath("Source path must not be empty", path=src, backend="memory")
        if not dst_segments:
            raise InvalidPath("Destination path must not be empty", path=dst, backend="memory")

        # Short-circuit: moving a file to itself is a no-op
        if src_segments == dst_segments:
            return

        with self._lock:
            # Find source
            src_parent = self._traverse(src_segments[:-1])
            if not isinstance(src_parent, _DirNode):
                raise NotFound(f"Source not found: {src}", path=src, backend="memory")
            src_leaf = src_segments[-1]
            entry = src_parent.children.get(src_leaf)
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
            if not isinstance(src_node, _FileEntry):
                raise NotFound(f"Source not found: {src}", path=src, backend="memory")

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
