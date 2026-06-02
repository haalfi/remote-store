#!/usr/bin/env python3
"""Maintain sdd/backlogid.json — max ID per prefix in BACKLOG-DONE.md.

Normal mode (no flag):
    Scans BACKLOG-DONE.md, writes sdd/backlogid.json.
    Run after moving items to BACKLOG-DONE.md: hatch run gen-backlogid.

Check mode (--check):
    Read-only. Verifies the JSON is current, then checks BACKLOG.md for
    collisions with done items and prints next safe IDs per prefix.
    Exit 0 = clean; 1 = stale JSON or collisions found.
    Suitable for use as a lint gate.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "sdd" / "BACKLOG.md"
BACKLOG_DONE = ROOT / "sdd" / "BACKLOG-DONE.md"
ID_FILE = ROOT / "sdd" / "backlogid.json"

_PREFIXES = ("BK", "BUG", "ID", "AF", "BL")
_HEADER_RE = re.compile(
    r"^- \[(.)\] \*\*(" + "|".join(_PREFIXES) + r")-(\d+[a-z]*)(?:\s+\([^)]+\))? —",
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


def _generate() -> int:
    done_ids = _extract_ids(BACKLOG_DONE.read_text(encoding="utf-8"), "x")
    max_done = {p: _max_numeric(done_ids[p]) for p in _PREFIXES}
    # newline="\n": force LF; text-mode write on Windows emits CRLF and churns the eol=lf JSON.
    ID_FILE.write_text(json.dumps(max_done, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Updated {ID_FILE.relative_to(ROOT)}")
    return 0


def _check() -> int:
    done_text = BACKLOG_DONE.read_text(encoding="utf-8")
    active_text = BACKLOG.read_text(encoding="utf-8")

    done_ids = _extract_ids(done_text, "x")
    active_ids = _extract_ids(active_text, " ~")

    actual_max = {p: _max_numeric(done_ids[p]) for p in _PREFIXES}

    try:
        stored = json.loads(ID_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: {ID_FILE.relative_to(ROOT)} not found. Run: hatch run gen-backlogid")
        return 1

    stale = [p for p in _PREFIXES if stored.get(p) != actual_max[p]]
    if stale:
        for p in stale:
            print(f"STALE: {p}: stored={stored.get(p)}, actual={actual_max[p]}")
        print("Run: hatch run gen-backlogid")
        return 1

    collisions = sorted(item for p in _PREFIXES for item in active_ids[p] & done_ids[p])

    max_active = {p: _max_numeric(active_ids[p]) for p in _PREFIXES}
    next_ids = {p: max(actual_max[p], max_active[p]) + 1 for p in _PREFIXES}
    next_str = "  ".join(f"{p}={next_ids[p]}" for p in _PREFIXES)
    print(f"Next safe IDs: {next_str}")

    if collisions:
        print(f"\nFound {len(collisions)} collision(s) — same ID active and done:")
        for c in collisions:
            print(f"  {c}")
        print("\nAssign a new ID to the active item (floor: sdd/backlogid.json).")
        return 1

    print("No ID collisions.")
    return 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return _check()
    return _generate()


if __name__ == "__main__":
    raise SystemExit(main())
