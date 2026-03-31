"""Shared data structures for in-memory backends.

Both ``MemoryBackend`` (sync) and ``AsyncMemoryBackend`` (async) share
the same tree-indexed storage model.  Keeping the dataclasses in a
common module avoids duplication and ensures changes propagate to both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(slots=True)
class FileEntry:
    """Mutable file node in the in-memory tree."""

    data: bytearray
    modified_at: datetime
    content_type: str | None = None


@dataclass(slots=True)
class DirNode:
    """Directory node — children map names to files or subdirectories."""

    children: dict[str, DirNode | FileEntry] = field(default_factory=dict)


class FileSnapshot:
    """Frozen copy of ``FileEntry`` scalars for lock-free iteration.

    Copies size, modified_at, and content_type at snapshot time so that
    concurrent writes to the live ``FileEntry`` cannot produce inconsistent
    ``FileInfo`` objects (e.g. new size with old timestamp).
    """

    __slots__ = ("size", "modified_at", "content_type")

    def __init__(self, entry: FileEntry) -> None:
        self.size = len(entry.data)
        self.modified_at = entry.modified_at
        self.content_type = entry.content_type
