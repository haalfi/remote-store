#!/usr/bin/env python3
"""Maintain sdd/backlogid.json — max ID per prefix in BACKLOG-DONE.md.

Normal mode (no flag):
    Scans BACKLOG-DONE.md, writes sdd/backlogid.json.
    Run after moving items to BACKLOG-DONE.md: hatch run gen-backlogid.

Check mode (--check):
    Read-only. Verifies the JSON is current, then checks BACKLOG.md for
    collisions with done items **and for one ID carried by two open items**,
    checks each open item's attributes (R1, below), and prints next safe IDs
    per prefix.
    Exit 0 = clean; 1 = stale JSON, collisions, duplicates, or R1 violations.
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

    **Bound: the open side only.** `BACKLOG-DONE.md` collapses the same way, and
    the path is reachable — two branches mint one ID and each *closes* its item
    before merging, so neither is ever open and nothing here sees it. It is
    deliberately not checked, because the register already carries four such
    pairs from before the ID discipline (`BK-001`, `BUG-001`, `BUG-144`, and
    `BK-167b`, whose second header is the sanctioned `(partial)` split shape).
    Renumbering items inside released sections would falsify the release
    record, and a gate that needs an exemption list on its first run is
    fighting its own subject. `BK-385` carries the decision with those four as
    its evidence.

    **R1, attribute vocabulary** ([ADR-0040](../sdd/adrs/0040-backlog-as-index.md)).
    Every open item's header is followed directly by its
    ``spec: … · effort: … · audience: …`` line; ``effort`` is one of S/M/L and
    each ``audience`` value is in ``sdd/traces/_schema.yml``'s enum, read from
    the schema so the two vocabularies cannot drift. A missing line fails too,
    or an item could evade the rule by omitting it. It checks vocabulary, not
    whether a value is right for the item. R2–R4 (item cap, section shape,
    dossier link) are ADR-0040's too and not built here yet.

Drift-gate::

    kind:       pair
    compares: the max ID per prefix in sdd/BACKLOG-DONE.md ↔ sdd/backlogid.json, and the open IDs in
        sdd/BACKLOG.md against both
    domain:     process

Drift-gate::

    kind:       rule
    rule: no ID appears on two open item headers in sdd/BACKLOG.md — the done
        register is out of scope, for the reason the module docstring gives
    domain:     process

Drift-gate::

    kind:       pair
    compares: each open item's audience values in sdd/BACKLOG.md ↔ the audience
        enum in sdd/traces/_schema.yml, which governs (R1; effort against S/M/L)
    domain:     process
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from _trace_corpus import load_trace

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "sdd" / "BACKLOG.md"
BACKLOG_DONE = ROOT / "sdd" / "BACKLOG-DONE.md"
ID_FILE = ROOT / "sdd" / "backlogid.json"

TRACE_SCHEMA = ROOT / "sdd" / "traces" / "_schema.yml"

_PREFIXES = ("BK", "BUG", "ID", "AF", "BL")
_HEADER_RE = re.compile(
    r"^- \[(.)\] \*\*(" + "|".join(_PREFIXES) + r")-(\d+[a-z]*)(?:\s+\([^)]+\))? —",
    re.MULTILINE,
)
_ATTR_RE = re.compile(r"^  spec: .+ · effort: (.+?) · audience: (.+)$")
_EFFORTS = ("S", "M", "L")


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


def _audience_enum() -> set[str]:
    """The trace schema's audience enum: one vocabulary for traces and items."""
    schema = load_trace(TRACE_SCHEMA.read_text(encoding="utf-8"))
    return set(schema["properties"]["audience"]["items"]["enum"])


def _attribute_violations(text: str, audiences: set[str]) -> list[str]:
    """R1: each open item's next line is its attribute line, with legal values.

    Open items only (``[ ]``/``[~]``); ``BACKLOG-DONE.md`` entries carry no
    attribute line. A missing line is a violation, else it would bypass the rule.
    """
    lines = text.split("\n")
    found: list[str] = []
    for i, line in enumerate(lines):
        m = _HEADER_RE.match(line)
        if not m or m.group(1) not in " ~":
            continue
        item = f"{m.group(2)}-{m.group(3)}"
        where = f"line {i + 2}: {item}"
        attr = _ATTR_RE.match(lines[i + 1]) if i + 1 < len(lines) else None
        if attr is None:
            found.append(f"{where}: no attribute line (`  spec: … · effort: … · audience: …`)")
            continue
        effort, audience = attr.group(1), attr.group(2)
        if effort not in _EFFORTS:
            found.append(f"{where}: effort {effort!r} not in {'/'.join(_EFFORTS)}")
        found.extend(
            f"{where}: audience {a!r} not in {TRACE_SCHEMA.name}'s enum"
            for a in (x.strip() for x in audience.split(","))
            if a not in audiences
        )
    return found


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
    attributes = _attribute_violations(active_text, _audience_enum())

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

    if attributes:
        print(f"\nFound {len(attributes)} attribute violation(s) in {BACKLOG.name} (R1, ADR-0040):")
        for v in attributes:
            print(f"  {v}")

    if duplicates or collisions or attributes:
        return 1

    # Every rule named, so a clean run says which ones passed. The duplicate
    # rule is only reachable after two branches merge, so this line is the
    # first evidence most authors will have that it exists at all.
    print("No ID collisions, no ID on two open items, and every open item's attributes in vocabulary.")
    return 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return _check()
    return _generate()


if __name__ == "__main__":
    raise SystemExit(main())
