#!/usr/bin/env python3
"""Derive every sdd/BACKLOG.md figure RFC-0016 quotes.

Usage: python sdd/rfcs/rfc-0016-measure.py [--at <rev>]

Reads the file at <rev> (default: the working tree) and prints:
- character split by region (rules header, section preambles, item bodies);
- per-section item count, preamble words, and item-body line median/max;
- how many item bodies exceed the proposed inline cap.

Regions: the rules header is everything before the second `## ` heading;
a section preamble runs from its `## ` heading to its first item header;
an item body is every line from its header to the next item or heading.
"""

from __future__ import annotations

import re
import subprocess
import sys
from statistics import median

ITEM_RE = re.compile(r"^- \[.\] \*\*[A-Z]+-\d+")
BODY_CAP = 8  # proposed inline cap (header + attribute line + diagnosis)


def _load(rev: str | None) -> list[str]:
    if rev:
        out = subprocess.run(
            ["git", "show", f"{rev}:sdd/BACKLOG.md"], check=True, capture_output=True, text=True
        ).stdout
    else:
        with open("sdd/BACKLOG.md", encoding="utf-8") as fh:
            out = fh.read()
    return out.split("\n")


def main() -> int:
    rev = sys.argv[sys.argv.index("--at") + 1] if "--at" in sys.argv else None
    lines = _load(rev)
    heads = [i for i, line in enumerate(lines) if line.startswith("## ")]
    total = len("\n".join(lines))
    rules = len("\n".join(lines[: heads[1]]))
    pre_chars = item_chars = 0
    all_bodies: list[int] = []
    rows = []
    for k, h in enumerate(heads[1:], 1):
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        starts = [j for j in range(h, end) if ITEM_RE.match(lines[j])]
        first = starts[0] if starts else end
        pre_chars += len("\n".join(lines[h:first]))
        item_chars += len("\n".join(lines[first:end]))
        bodies = [b - a for a, b in zip(starts, [*starts[1:], end][: len(starts)], strict=True)]
        all_bodies += bodies
        rows.append((lines[h][3:40], len(starts), len(" ".join(lines[h:first]).split()), bodies))

    print(f"lines {len(lines)}  chars {total}  (~{total // 4} tokens at 4 chars/token)")
    for name, n in (("rules header", rules), ("section preambles", pre_chars), ("item bodies", item_chars)):
        print(f"  {name:<18} {n:>7} chars  {round(n / total * 100):>3}%")
    print("\nsection                                items  preamble-words  body-lines median/max")
    for name, n, words, bodies in rows:
        stat = f"{median(bodies):.0f}/{max(bodies)}" if bodies else "—"
        print(f"  {name:<37} {n:>5}  {words:>14}  {stat:>10}")
    over = sum(1 for b in all_bodies if b > BODY_CAP)
    print(f"\nitems {len(all_bodies)}; bodies over {BODY_CAP} lines: {over}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
