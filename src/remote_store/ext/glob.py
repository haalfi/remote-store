"""Glob — portable pattern matching for file listing.

Delegates to native backend glob when ``Capability.GLOB`` is available,
otherwise falls back to ``Store.list_files()`` + client-side filtering.

For simple name-based filtering, prefer ``Store.list_files(pattern=...)``.
Use ``glob_files`` when you need full recursive glob patterns (``**``,
wildcards in directory segments) and want portable behavior across all
backends.

!!! example

    ```python
    from remote_store.ext.glob import glob_files

    # Works with any backend — uses native glob or list+filter fallback
    for info in glob_files(store, "data/**/*.csv"):
        print(info.path, info.size)
    ```
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store._capabilities import Capability
from remote_store._glob import extract_prefix, needs_recursive, pattern_to_regex

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._models import FileInfo
    from remote_store._store import Store

__all__ = ["glob_files"]


def glob_files(store: Store, pattern: str) -> Iterator[FileInfo]:
    """Match files against a glob pattern.

    When the backend supports ``Capability.GLOB``, delegates to
    ``store.glob()`` for native pattern matching. Otherwise extracts the
    longest non-wildcard prefix, lists files under that prefix, and
    filters client-side.

    Args:
        store: The Store to search.
        pattern: Glob pattern relative to the store root
            (e.g., ``"data/*.csv"``, ``"**/*.txt"``).

    Returns:
        Iterator of matching ``FileInfo`` objects.
    """
    if store.supports(Capability.GLOB):
        yield from store.glob(pattern)
        return

    # Fallback: list + client-side filter
    prefix = extract_prefix(pattern)
    recursive = needs_recursive(pattern)
    compiled = pattern_to_regex(pattern)

    for info in store.list_files(prefix, recursive=recursive):
        if compiled.match(str(info.path)):
            yield info
