#!/usr/bin/env python3
"""Maintain sdd/backlogid.json and detect ID collisions between the two backlog files.

sdd/backlogid.json records the highest numeric ID per prefix seen in BACKLOG-DONE.md,
so assigning a new ID only requires reading that small JSON plus scanning the much
smaller BACKLOG.md — no full scan of the large BACKLOG-DONE.md needed.

The script always rewrites sdd/backlogid.json before checking for collisions,
so running it is idempotent.

Exit code 0 = clean; 1 = collisions found (same ID appears active and done).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "sdd" / "BACKLOG.md"
BACKLOG_DONE = ROOT / "sdd" / "BACKLOG-DONE.md"
ID_FILE = ROOT / "sdd" / "backlogid.json"

_PREFIXES = ("BK", "BUG", "ID", "AF", "BL")
_HEADER_RE = re.compile(
    r"^- \[(.)\] \*\*(" + "|".join(_PREFIXES) + r")-(\d+[a-z]*) —",
    re.MULTILINE,
)


def _extract_ids(text: str, status_chars: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {p: set() for p in _PREFIXES}
    for m in _HEADER_RE.finditer(text):
        status, prefix, num = m.group(1), m.group(2), m.group(3)
        if status in status_chars:
            result[prefix].add(f"{prefix}-{num}")
    return result


def _max_numeric(ids: set[str]) -> int:
    best = 0
    for item in ids:
        m = re.search(r"\d+", item.split("-", 1)[1])
        if m:
            best = max(best, int(m.group()))
    return best


def main() -> int:
    done_text = BACKLOG_DONE.read_text(encoding="utf-8")
    active_text = BACKLOG.read_text(encoding="utf-8")

    done_ids = _extract_ids(done_text, "x")
    active_ids = _extract_ids(active_text, " ~")

    max_done = {p: _max_numeric(done_ids[p]) for p in _PREFIXES}
    ID_FILE.write_text(json.dumps(max_done, indent=2) + "\n", encoding="utf-8")

    collisions: list[str] = []
    for prefix in _PREFIXES:
        both = active_ids[prefix] & done_ids[prefix]
        collisions.extend(sorted(both))

    max_active = {p: _max_numeric(active_ids[p]) for p in _PREFIXES}
    next_ids = {p: max(max_done[p], max_active[p]) + 1 for p in _PREFIXES}
    next_str = "  ".join(f"{p}={next_ids[p]}" for p in _PREFIXES)
    print(f"Next safe IDs — {next_str}")

    if collisions:
        print(f"\nFound {len(collisions)} collision(s) — same ID active and done:")
        for c in collisions:
            print(f"  {c}")
        print("\nAssign a new ID to the active item (see sdd/backlogid.json for the floor).")
        return 1

    print("No ID collisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
