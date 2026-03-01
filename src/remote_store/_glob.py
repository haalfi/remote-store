"""Shared glob helpers — prefix extraction, recursive detection, pattern-to-regex.

Used by ``ext.glob`` (Tier 3 fallback) and by cloud backends that implement
native ``Backend.glob()`` (Tier 2).  These are pure functions with no
backend or Store dependencies.
"""

from __future__ import annotations

import re


def extract_prefix(pattern: str) -> str:
    """Extract the longest non-wildcard directory prefix.

    >>> extract_prefix("data/2024/*.csv")
    'data/2024'
    >>> extract_prefix("**/*.csv")
    ''
    >>> extract_prefix("*.txt")
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


def needs_recursive(pattern: str) -> bool:
    """Determine whether the pattern requires recursive listing.

    Returns ``True`` if the pattern contains ``**`` or if any non-final
    path segment contains wildcards.
    """
    if "**" in pattern:
        return True
    parts = pattern.split("/")
    return any(any(c in part for c in ("*", "?", "[")) for part in parts[:-1])


def pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a glob pattern to a compiled regex.

    Supports:
    - ``*``    -> ``[^/]*`` (any chars except separator)
    - ``**/``  -> ``(?:.+/)?`` (zero or more path segments)
    - ``**``   (at end) -> ``.*`` (match everything)
    - ``?``    -> ``[^/]`` (single non-separator char)
    - ``[...]``  -> character class (passed through)
    - ``[!...]`` -> negated character class (``[!abc]`` -> ``[^abc]``)

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
                msg = f"'**' must be a complete path segment, got '**{pattern[i]}' in pattern {pattern!r}"
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
