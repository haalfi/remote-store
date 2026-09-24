#!/usr/bin/env python3
"""Maintain sdd/backlogid.json — max ID per prefix in BACKLOG-DONE.md.

Normal mode (no flag):
    Scans BACKLOG-DONE.md, writes sdd/backlogid.json.
    Run after moving items to BACKLOG-DONE.md: hatch run gen-backlogid.

Check mode (--check):
    Read-only. Verifies the JSON is current, then checks BACKLOG.md for
    collisions with done items **and for one ID carried by two open items**,
    and prints next safe IDs per prefix.
    Exit 0 = clean; 1 = stale JSON, collisions, or duplicates found.
    Wired into `hatch run lint` and `hatch run docs-gate` — the latter because
    `lint` is CODE_PAT-gated and so skipped for an `sdd/`-only change, which is
    exactly the change that bumps this file.

    The duplicate half exists because the open-versus-done comparison could not
    see its own file: `_extract_ids` returns sets, so two headers sharing an ID
    collapsed to one before anything compared them. Measured — `BK-382` reached
    master on two distinct open items (from `8e35697` and `e5fb4a8`) and this
    check printed "No ID collisions." ID-257 predicted the minting collision and
    records that its open-versus-open half had no gate; this is that gate. It
    catches the collision **after** both branches merge and does not prevent it:
    preventing it needs a mint-time view of unmerged branches, which stays
    ID-257's open question.

Drift-gate::

    kind:       pair
    compares: the max ID per prefix in sdd/BACKLOG-DONE.md ↔ sdd/backlogid.json, and the open IDs in
        sdd/BACKLOG.md against both
    domain:     process

Drift-gate::

    kind:       rule
    rule: every open item header in sdd/BACKLOG.md carries an ID no other open
        item carries
    domain:     process
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
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


def _duplicate_ids(text: str, status_chars: str) -> dict[str, int]:
    """IDs whose header appears more than once in one file, with their count.

    Separate from ``_extract_ids`` rather than a widening of it. That function
    returns ``dict[str, set[str]]`` and ``check_backlog_ids_vs_base.py`` imports
    it for set arithmetic against the base — a guard test pins the import to
    this module — so changing its return type to carry multiplicity would
    rewrite a second gate to fix this one. Two functions over one
    ``_HEADER_RE`` keeps the grammar single-homed, which is the property that
    mattered.

    Keyed on the whole ``PREFIX-NNN[a-z]*`` token, so ``BK-139a`` and
    ``BK-139b`` are two items rather than one item twice. Keying on the numeric
    part would fail every split item, which is the shape this check must not
    touch.
    """
    counts: Counter[str] = Counter()
    for m in _HEADER_RE.finditer(text):
        status, prefix, num = m.group(1), m.group(2), m.group(3)
        if status in status_chars:
            counts[f"{prefix}-{num}"] += 1
    return {item: n for item, n in counts.items() if n > 1}


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
    duplicates = _duplicate_ids(active_text, " ~")

    max_active = {p: _max_numeric(active_ids[p]) for p in _PREFIXES}
    next_ids = {p: max(actual_max[p], max_active[p]) + 1 for p in _PREFIXES}
    next_str = "  ".join(f"{p}={next_ids[p]}" for p in _PREFIXES)
    print(f"Next safe IDs: {next_str}")

    # Both failures are reported before returning, rather than the first one
    # short-circuiting: an author who fixes a duplicate only to be told about a
    # collision on the next run pays two cycles for one read of the file.
    if duplicates:
        print(f"\nFound {len(duplicates)} duplicate ID(s) — one ID on two open items in {BACKLOG.name}:")
        for item, count in sorted(duplicates.items()):
            print(f"  {item} ({count} headers)")
        print(
            "\nTwo branches minted the same ID before either merged (ID-257). Renumber the "
            "later-merged item to the next safe ID above, and sweep every reference to it."
        )

    if collisions:
        print(f"\nFound {len(collisions)} collision(s) — same ID active and done:")
        for c in collisions:
            print(f"  {c}")
        print("\nAssign a new ID to the active item (floor: sdd/backlogid.json).")

    if duplicates or collisions:
        return 1

    print("No ID collisions.")
    return 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return _check()
    return _generate()


if __name__ == "__main__":
    raise SystemExit(main())
