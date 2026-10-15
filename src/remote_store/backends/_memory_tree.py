"""The in-memory tree both Memory drivers share.

``MemoryTree`` is the wire the two Memory drivers hold: a tree of ``DirNode``
and ``FileEntry`` nodes with the driver primitives over it, each on a key the
contract kernel has already validated and normalised. It takes no lock; each
driver calls it under its own (a ``threading.Lock`` or an ``asyncio.Lock``), so
every primitive is one locked step. Refusals are raised
already typed, without ``backend``, which the kernel's choke point fills from
the driver's ``name``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from remote_store._errors import AlreadyExists, DirectoryNotEmpty, InvalidPath, NotFound
from remote_store._kernel._model import Entry, Page, PutResult

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(slots=True)
class FileEntry:
    """Mutable file node in the in-memory tree."""

    data: bytearray
    modified_at: datetime
    content_type: str | None = None
    metadata: dict[str, str] | None = None


@dataclass(slots=True)
class DirNode:
    """Directory node — children map names to files or subdirectories."""

    children: dict[str, DirNode | FileEntry] = field(default_factory=dict)


def _split(key: str) -> list[str]:
    """A canonical key's segments; the root ``""`` has none."""
    return key.split("/") if key else []


def _join(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name


def _file_entry(key: str, node: FileEntry) -> Entry:
    return Entry(
        key=key,
        kind="file",
        size=len(node.data),
        modified_at=node.modified_at,
        content_type=node.content_type,
        metadata=node.metadata,
    )


class MemoryTree:
    """The tree and its counters; every method is one step a driver locks."""

    __slots__ = ("file_count", "folder_count", "root")

    def __init__(self) -> None:
        self.root = DirNode()
        self.file_count = 0
        self.folder_count = 0

    # region: lookup

    def traverse(self, key: str) -> DirNode | FileEntry | None:
        """The node at *key*, or ``None`` when absent or under a file. O(d)."""
        node: DirNode | FileEntry = self.root
        for seg in _split(key):
            if not isinstance(node, DirNode):
                return None
            child = node.children.get(seg)
            if child is None:
                return None
            node = child
        return node

    def _parent_and_leaf(self, key: str) -> tuple[DirNode | None, str]:
        parent_key, _, leaf = key.rpartition("/")
        parent = self.traverse(parent_key)
        return (parent if isinstance(parent, DirNode) else None), leaf

    def _ensure_parents(self, key: str) -> DirNode:
        """Create the missing folders above *key*; a file among them is ``InvalidPath``."""
        node = self.root
        for seg in _split(key)[:-1]:
            child = node.children.get(seg)
            if child is None:
                child = DirNode()
                node.children[seg] = child
                self.folder_count += 1
            elif isinstance(child, FileEntry):
                raise InvalidPath(f"Cannot create directory, '{seg}' exists as a file", path=key)
            node = child
        return node

    def stat(self, key: str) -> Entry | None:
        node = self.traverse(key)
        if node is None:
            return None
        if isinstance(node, FileEntry):
            return _file_entry(key, node)
        return Entry(key=key, kind="folder")

    def file(self, key: str) -> FileEntry:
        """The file at *key*; a folder is ``InvalidPath``, anything else ``NotFound``."""
        node = self.traverse(key)
        if isinstance(node, DirNode):
            raise InvalidPath(f"Not a file: {key}", path=key)
        if node is None:
            raise NotFound(f"File not found: {key}", path=key)
        return node

    # endregion

    # region: writes

    def put(self, key: str, data: bytearray, *, overwrite: bool, metadata: Mapping[str, str] | None) -> PutResult:
        """Store *data* at *key*, creating its parent folders (``parents == "implicit"``)."""
        # ``now`` under the caller's lock, so modified_at follows lock-acquisition order.
        now = datetime.now(UTC)
        parent = self._ensure_parents(key)
        leaf = key.rpartition("/")[2]
        existing = parent.children.get(leaf)
        stored = dict(metadata) if metadata else None
        if isinstance(existing, DirNode):
            raise InvalidPath(f"Cannot write, '{leaf}' exists as a directory", path=key)
        if isinstance(existing, FileEntry):
            if not overwrite:
                raise AlreadyExists(f"File already exists: {key}", path=key)
            existing.data[:] = data
            existing.modified_at = now
            existing.metadata = stored
        else:
            parent.children[leaf] = FileEntry(data=data, modified_at=now, metadata=stored)
            self.file_count += 1
        return PutResult(size=len(data), source="native", last_modified=now, metadata=metadata)

    def check_target(self, key: str, *, overwrite: bool) -> None:
        """Refuse what ``put`` would refuse at *key*, changing nothing: a write handle opens on it."""
        node: DirNode | FileEntry = self.root
        segs = _split(key)
        for seg in segs[:-1]:
            child = node.children.get(seg) if isinstance(node, DirNode) else None
            if child is None:
                return
            if isinstance(child, FileEntry):
                raise InvalidPath(f"Cannot create directory, '{seg}' exists as a file", path=key)
            node = child
        existing = node.children.get(segs[-1]) if isinstance(node, DirNode) else None
        if isinstance(existing, DirNode):
            raise InvalidPath(f"Cannot write, '{segs[-1]}' exists as a directory", path=key)
        if existing is not None and not overwrite:
            raise AlreadyExists(f"File already exists: {key}", path=key)

    def delete(self, key: str) -> None:
        parent, leaf = self._parent_and_leaf(key)
        existing = parent.children.get(leaf) if parent is not None else None
        if isinstance(existing, DirNode):
            raise InvalidPath(f"Not a file: {key}", path=key)
        if existing is None or parent is None:
            raise NotFound(f"File not found: {key}", path=key)
        del parent.children[leaf]
        self.file_count -= 1

    def _source(self, src: str) -> tuple[DirNode, str, FileEntry]:
        parent, leaf = self._parent_and_leaf(src)
        entry = parent.children.get(leaf) if parent is not None else None
        if isinstance(entry, DirNode):
            raise InvalidPath(f"Source is a directory: {src}", path=src)
        if entry is None or parent is None:
            raise NotFound(f"Source not found: {src}", path=src)
        return parent, leaf, entry

    def _destination(self, dst: str, *, overwrite: bool) -> tuple[DirNode, str, FileEntry | None]:
        parent = self._ensure_parents(dst)
        leaf = dst.rpartition("/")[2]
        existing = parent.children.get(leaf)
        if isinstance(existing, DirNode):
            raise InvalidPath(f"Destination '{dst}' exists as a directory", path=dst)
        if existing is not None and not overwrite:
            raise AlreadyExists(f"Destination already exists: {dst}", path=dst)
        return parent, leaf, existing

    def move(self, src: str, dst: str, *, overwrite: bool) -> None:
        """Re-link the file node: detach and attach in one step, the payload never copied."""
        src_parent, src_leaf, entry = self._source(src)
        dst_parent, dst_leaf, existing = self._destination(dst, overwrite=overwrite)
        if existing is not None:
            self.file_count -= 1
        del src_parent.children[src_leaf]
        dst_parent.children[dst_leaf] = entry

    def copy(self, src: str, dst: str, *, overwrite: bool) -> None:
        """Copy into an independent byte buffer."""
        _, _, entry = self._source(src)
        dst_parent, dst_leaf, existing = self._destination(dst, overwrite=overwrite)
        if existing is None:
            self.file_count += 1
        dst_parent.children[dst_leaf] = FileEntry(
            data=bytearray(entry.data),
            modified_at=datetime.now(UTC),
            content_type=entry.content_type,
            metadata=entry.metadata,
        )

    # endregion

    # region: folders

    def _folder(self, key: str) -> tuple[DirNode, str, DirNode]:
        parent, leaf = self._parent_and_leaf(key)
        node = parent.children.get(leaf) if parent is not None else None
        if isinstance(node, FileEntry):
            raise InvalidPath(f"Not a folder: {key}", path=key)
        if node is None or parent is None:
            raise NotFound(f"Folder not found: {key}", path=key)
        return parent, leaf, node

    def remove_folder(self, key: str) -> None:
        """Remove the empty folder at *key*; checks and detach in one step."""
        parent, leaf, node = self._folder(key)
        if node.children:
            raise DirectoryNotEmpty(f"Folder not empty: {key}", path=key)
        del parent.children[leaf]
        self.folder_count -= 1

    def delete_tree(self, key: str) -> None:
        """Detach the folder at *key* and its subtree in one step, keeping the counters."""
        parent, leaf, node = self._folder(key)
        files, folders = 0, 0
        stack = [node]
        while stack:
            for child in stack.pop().children.values():
                if isinstance(child, FileEntry):
                    files += 1
                else:
                    folders += 1
                    stack.append(child)
        del parent.children[leaf]
        self.file_count -= files
        self.folder_count -= folders + 1

    def folder_stats(self, key: str) -> tuple[int, int, datetime | None]:
        """File count, total size and latest time under *key*, in one walk.

        A key that is no folder holds nothing here; the kernel's probe after an
        empty aggregate types it.
        """
        node = self.traverse(key)
        count, size, latest = 0, 0, None
        if not isinstance(node, DirNode):
            return count, size, latest
        stack = [node]
        while stack:
            for child in stack.pop().children.values():
                if isinstance(child, FileEntry):
                    count += 1
                    size += len(child.data)
                    if latest is None or child.modified_at > latest:
                        latest = child.modified_at
                else:
                    stack.append(child)
        return count, size, latest

    def list_page(self, prefix: str, *, delimiter: str | None) -> Page:
        """Everything under *prefix* in one page, collected in one step.

        A *prefix* that is a file, lies under one or is absent lists nothing.
        ``delimiter=None`` is every file of the subtree; ``"/"`` the immediate
        files and subfolders.
        """
        node = self.traverse(prefix)
        if not isinstance(node, DirNode):
            return Page()
        if delimiter is not None:
            files: list[Entry] = []
            folders: list[str] = []
            for name, child in node.children.items():
                if isinstance(child, FileEntry):
                    files.append(_file_entry(_join(prefix, name), child))
                else:
                    folders.append(_join(prefix, name))
            return Page(entries=tuple(files), prefixes=tuple(folders))
        out: list[Entry] = []
        stack: list[tuple[str, DirNode]] = [(prefix, node)]
        while stack:
            base, current = stack.pop()
            for name, child in current.children.items():
                key = _join(base, name)
                if isinstance(child, FileEntry):
                    out.append(_file_entry(key, child))
                else:
                    stack.append((key, child))
        return Page(entries=tuple(out))

    # endregion
