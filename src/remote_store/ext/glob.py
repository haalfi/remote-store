"""Glob — portable pattern matching for file listing.

Delegates to native backend glob when ``Capability.GLOB`` is available,
otherwise falls back to ``Store.list_files()`` + client-side filtering.

For simple name-based filtering, prefer ``Store.list_files(pattern=...)``.
Use ``glob_files`` when you need full recursive glob patterns (``**``,
wildcards in directory segments) and want portable behavior across all
backends.

Usage::

    from remote_store.ext.glob import glob_files

    # Works with any backend — uses native glob or list+filter fallback
    for info in glob_files(store, "data/**/*.csv"):
        print(info.path, info.size)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from remote_store._capabilities import Capability

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

    :param store: The Store to search.
    :param pattern: Glob pattern relative to the store root
        (e.g., ``"data/*.csv"``, ``"**/*.txt"``).
    :returns: Iterator of matching ``FileInfo`` objects.
    """
    if store.supports(Capability.GLOB):
        yield from store.glob(pattern)
        return

    # Fallback: list + client-side filter
    prefix = _extract_prefix(pattern)
    recursive = _needs_recursive(pattern)
    compiled = _pattern_to_regex(pattern)

    for info in store.list_files(prefix, recursive=recursive):
        if compiled.match(str(info.path)):
            yield info


def _extract_prefix(pattern: str) -> str:
    """Extract the longest non-wildcard directory prefix.

    >>> _extract_prefix("data/2024/*.csv")
    'data/2024'
    >>> _extract_prefix("**/*.csv")
    ''
    >>> _extract_prefix("*.txt")
    ''
    """
    parts = pattern.split("/")
    prefix_parts: list[str] = []
    for part in parts:
        if any(c in part for c in ("*", "?", "[")):
            break
        prefix_parts.append(part)
    # If all parts are literal, the last one is the filename — use parent
    if len(prefix_parts) == len(parts):
        prefix_parts = prefix_parts[:-1]
    return "/".join(prefix_parts)


def _needs_recursive(pattern: str) -> bool:
    """Determine whether the pattern requires recursive listing.

    Returns ``True`` if the pattern contains ``**`` or if any non-final
    path segment contains wildcards.
    """
    if "**" in pattern:
        return True
    parts = pattern.split("/")
    return any(any(c in part for c in ("*", "?", "[")) for part in parts[:-1])


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a glob pattern to a compiled regex.

    Supports:
    - ``*``    → ``[^/]*`` (any chars except separator)
    - ``**/``  → ``(?:.+/)?`` (zero or more path segments)
    - ``**``   (at end) → ``.*`` (match everything)
    - ``?``    → ``[^/]`` (single non-separator char)
    - ``[…]``  → character class (passed through)
    - ``[!…]`` → negated character class (``[!abc]`` → ``[^abc]``)

    ``**`` must be a complete path segment (``**/``, ``/**``, or the
    entire pattern). Patterns like ``**error`` are not supported and
    raise ``ValueError``.
    """
    parts: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*" and i + 1 < n and pattern[i + 1] == "*":
            i += 2
            if i < n and pattern[i] == "/":
                i += 1  # consume trailing slash
                parts.append("(?:.+/)?")
            elif i >= n:
                # ** at end of pattern
                parts.append(".*")
            else:
                msg = (
                    f"'**' must be a complete path segment, "
                    f"got '**{pattern[i]}' in pattern {pattern!r}"
                )
                raise ValueError(msg)
        elif c == "*":
            parts.append("[^/]*")
            i += 1
        elif c == "?":
            parts.append("[^/]")
            i += 1
        elif c == "[":
            # Character class — find the closing bracket
            j = i + 1
            if j < n and pattern[j] == "!":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1  # literal ] at start of class
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:
                # No closing bracket — treat [ as literal
                parts.append(re.escape(c))
                i += 1
            else:
                # Extract class content and convert
                content = pattern[i + 1 : j]
                if content.startswith("!"):
                    parts.append(f"[^{content[1:]}]")
                else:
                    parts.append(f"[{content}]")
                i = j + 1
        else:
            parts.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(parts) + "$")
