"""The ``max_depth`` filter and the folder aggregation."""

# DEPTH-003 and BE-017.

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store._models import _known_modified_at

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from remote_store._kernel._model import Entry


def within_depth(prefix: str, key: str, max_depth: int | None) -> bool:
    """Whether *key*, listed under folder *prefix*, is within *max_depth*.

    A file directly in *prefix* is depth 0, so ``max_depth=0`` keeps the
    direct files only. ``None`` keeps everything. The bound is applied only
    to a recursive listing.
    """
    if max_depth is None:
        return True
    rel = key[len(prefix) + 1 :] if prefix else key
    return rel.count("/") <= max_depth


class FolderTally:
    """Accumulates the folder aggregate over a stream of file entries.

    ``modified_at`` is the latest *known* time: the unknown-time sentinel is
    skipped, and ``None`` is the answer when no time is known.
    """

    __slots__ = ("count", "latest", "size")

    def __init__(self) -> None:
        self.count = 0
        self.size = 0
        self.latest: datetime | None = None

    def add(self, entry: Entry) -> None:
        self.count += 1
        self.size += entry.size
        known = _known_modified_at(entry.modified_at)
        if known is not None and (self.latest is None or known > self.latest):
            self.latest = known

    def add_all(self, entries: Iterable[Entry]) -> None:
        for entry in entries:
            self.add(entry)
