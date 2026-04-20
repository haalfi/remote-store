"""Post-translate class reordering for Dafny's Python output.

Dafny emits ``class MemoryBackend(Backend)`` (and other ``Backend``
subclasses) before ``class Backend`` is defined, which breaks import.
This rewrites ``module_.py`` so classes appear in an importable order
(ADT types, then ``Backend``, then ``default__``, then ``MemoryBackend``,
then ``MemoryBackendMinimal``).

See ``sdd/formal/README.md`` § Class-ordering fix for the authoritative
order specification.

Usage: ``python scripts/_dafny_classorder.py <module_.py>``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_CLASS_RE = re.compile(r"^class\s+(\w+)(?:\b|\()", re.MULTILINE)

_TAIL_ORDER = ("Backend", "default__", "MemoryBackend", "MemoryBackendMinimal")
_SPECIAL = set(_TAIL_ORDER)


def _split_blocks(source: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (preamble, [(class_name, block_text), ...])."""
    matches = list(_CLASS_RE.finditer(source))
    if not matches:
        return source, []
    preamble = source[: matches[0].start()]
    blocks: list[tuple[str, str]] = []
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(source)
        blocks.append((m.group(1), source[m.start() : end]))
    return preamble, blocks


def reorder(source: str) -> str:
    preamble, blocks = _split_blocks(source)
    adt: list[tuple[str, str]] = []
    special: dict[str, tuple[str, str]] = {}
    for name, text in blocks:
        if name in _SPECIAL:
            special[name] = (name, text)
        else:
            adt.append((name, text))
    ordered: list[tuple[str, str]] = list(adt)
    for key in _TAIL_ORDER:
        if key in special:
            ordered.append(special[key])
    return preamble + "".join(text for _, text in ordered)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python scripts/_dafny_classorder.py <module_.py>", file=sys.stderr)
        return 2
    target = Path(argv[1])
    original = target.read_text(encoding="utf-8")
    rewritten = reorder(original)
    if rewritten == original:
        print(f"{target}: already in canonical order")
        return 0
    target.write_text(rewritten, encoding="utf-8")
    print(f"{target}: reordered classes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
