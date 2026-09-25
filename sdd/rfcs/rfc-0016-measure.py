#!/usr/bin/env python3
"""Derive every sdd/BACKLOG.md figure RFC-0016 quotes.

Usage: python sdd/rfcs/rfc-0016-measure.py [--at <rev>] [--item <ID> ...]

Reads the file at <rev> (default: the working tree) and prints:
- character split by region (rules header, section preambles, item bodies);
- per-section item count, preamble words, and item line median/max;
- how many items exceed the proposed inline cap;
- attribute values R1 would reject (effort outside S/M/L, audience outside
  sdd/traces/_schema.yml's enum at the same rev);
- with --item, the measured length of each named item.

Regions. Separator lines (blank, `---`, `<a id=...>`) that sit between the
last content of one region and the next `## ` heading belong to the section
that follows, not to the item or header before them. The rules header is
everything before the Release Blockers section so adjusted; a section preamble
runs from its adjusted start to its first item header. An item's length is its
content lines, header through last non-separator line, so the blank line
between items and a section's trailing `---`/anchor are not counted.
"""

from __future__ import annotations

import re
import subprocess
import sys
from statistics import median

ITEM_RE = re.compile(r"^- \[.\] \*\*([A-Z]+-\d+[a-z]?)")
SEP_RE = re.compile(r"^(\s*|---|<a id=\"[^\"]+\"></a>)$")
ATTR_RE = re.compile(r"^  spec: .* · effort: (.*?) · audience: (.*)$")
BODY_CAP = 8  # content lines: header, attribute line, diagnosis <= 5, optional Detail:
EFFORTS = {"S", "M", "L"}


def _read(rev: str | None, path: str) -> str:
    if rev:
        return subprocess.run(["git", "show", f"{rev}:{path}"], check=True, capture_output=True, text=True).stdout
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _audience_enum(rev: str | None) -> set[str]:
    schema = _read(rev, "sdd/traces/_schema.yml")
    block = schema.split("\n  audience:", 1)[1].split("description:", 1)[0]
    return set(re.findall(r"^\s+- ([a-z_.]+)$", block, re.M))


def _args(flag: str) -> list[str]:
    out, grab = [], False
    for a in sys.argv[1:]:
        if a.startswith("--"):
            grab = a == flag
        elif grab:
            out.append(a)
    return out


def main() -> int:
    rev = (_args("--at") or [None])[0]
    lines = _read(rev, "sdd/BACKLOG.md").split("\n")
    heads = [i for i, line in enumerate(lines) if line.startswith("## ")]
    # Pull each heading's start back over the separators that precede it.
    starts_adj = []
    for h in heads:
        s = h
        while s > 0 and SEP_RE.match(lines[s - 1]):
            s -= 1
        starts_adj.append(s)
    total = len("\n".join(lines))
    rules = len("\n".join(lines[: starts_adj[1]]))
    pre_chars = item_chars = 0
    # A list, not a dict keyed by ID: two open items can share an ID (e5fb4a8
    # carries BK-382 and BUG-291 twice), and keying would drop one of each.
    lengths: list[tuple[str, int]] = []
    rows = []
    for k in range(1, len(heads)):
        start, end = starts_adj[k], (starts_adj[k + 1] if k + 1 < len(heads) else len(lines))
        items = [j for j in range(start, end) if ITEM_RE.match(lines[j])]
        first = items[0] if items else end
        pre_chars += len("\n".join(lines[start:first]))
        item_chars += len("\n".join(lines[first:end]))
        sec = []
        for a, b in zip(items, [*items[1:], end][: len(items)], strict=True):
            last = b - 1
            while last > a and SEP_RE.match(lines[last]):
                last -= 1
            n = last - a + 1
            lengths.append((ITEM_RE.match(lines[a]).group(1), n))
            sec.append(n)
        rows.append((lines[heads[k]][3:40], len(items), len(" ".join(lines[start:first]).split()), sec))

    print(f"lines {len(lines)}  chars {total}  (~{total // 4} tokens at 4 chars/token)")
    for name, n in (("rules header", rules), ("section preambles", pre_chars), ("item bodies", item_chars)):
        print(f"  {name:<18} {n:>7} chars  {round(n / total * 100):>3}%")
    print("\nsection                                items  preamble-words  item-lines median/max")
    for name, n, words, sec in rows:
        stat = f"{median(sec):.0f}/{max(sec)}" if sec else "—"
        print(f"  {name:<37} {n:>5}  {words:>14}  {stat:>10}")
    over = sum(1 for _, n in lengths if n > BODY_CAP)
    print(f"\nitems {len(lengths)}; items over {BODY_CAP} content lines: {over}")

    enum = _audience_enum(rev)
    print("\nattribute values R1 would reject:")
    for i, line in enumerate(lines, 1):
        m = ATTR_RE.match(line)
        if not m:
            continue
        effort, audience = m.group(1), m.group(2)
        bad_aud = [a for a in (x.strip() for x in audience.split(",")) if a not in enum]
        if effort not in EFFORTS or bad_aud:
            print(f"  line {i}: effort={effort!r} audience-outside-enum={bad_aud}")
    for item in _args("--item"):
        found = [n for i, n in lengths if i == item]
        print(f"\n{item}: {found or 'not found'} content lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
