#!/usr/bin/env python3
"""Maintain sdd/backlogid.json — max ID per prefix in BACKLOG-DONE.md.

Normal mode (no flag):
    Scans BACKLOG-DONE.md, writes sdd/backlogid.json.
    Run after moving items to BACKLOG-DONE.md: hatch run gen-backlogid.

Check mode (--check):
    Read-only. Verifies the JSON is current, then checks BACKLOG.md for
    collisions with done items **and for one ID carried by two open items**,
    checks each open item's attributes (R1) and the file's shape (R2–R4,
    below), and prints next safe IDs per prefix.
    Exit 0 = clean; 1 = stale JSON, collisions, duplicates, or R1–R4 violations.
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
    whether a value is right for the item.

    **R2–R4, shape** (ADR-0040, RFC-0016 D1–D3). A *section* is a ``## ``
    heading other than the rules header; it ends before the separators
    (blank, ``---``, anchor) that precede the next heading.

    * R2: an item is at most 8 content lines (header through its last
      non-separator line, as ``sdd/rfcs/rfc-0016-measure.py`` counts), and at
      most 5 of them between the attribute line and an optional final
      ``Detail:`` line.
    * R3: the preamble is one ``**Promise:**`` paragraph of at most 3
      sentences. So ``Closes when`` fails it. Sentences are split on ``.!?``
      before whitespace and a capital-ish opener. **Bound, both directions:**
      an abbreviation before a capital over-counts (fails loud); a sentence
      opening with a lowercase identifier or a digit (``s3fs``, ``404s``) is
      not counted (fails open). Pinned by ``TestShape``'s stated-bound test.
    * R4: a ``Detail:`` line has the shape
      ``Detail: [dossier](backlog/<id>-<slug>.md)``, resolves from ``sdd/``,
      and the dossier's first ``# `` heading opens with the item's ID.

    **Scope.** R2 and R3 skip a section whose heading line is directly
    followed by ``<!-- backlog: unconverted -->``, ADR-0040's "scoped to
    migrated sections". The marker opts *out*, so a new section is gated from
    birth and conversion is one deleted line; the rules header's migration
    note names converted sections for readers, but the marker is what this
    reads. R4 runs on every section: a dangling link is wrong anywhere.
    **Bounds:** the marker can be added to escape R2/R3, which only review
    sees; R4 checks link and ID, not that index and dossier agree
    (``BACKLOG.md`` § Item authority states that bound); a dossier no item
    links is not detected.

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

Drift-gate::

    kind:       rule
    rule: in each sdd/BACKLOG.md section without the unconverted marker, an item is at most
        eight content lines with a diagnosis of at most five (R2), and the preamble is one
        Promise paragraph of at most three sentences (R3)
    domain:     process

Drift-gate::

    kind:       pair
    compares: each open item's Detail link and ID in sdd/BACKLOG.md ↔ the dossier file under
        sdd/backlog/ and its header ID; the item governs (R4)
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

# R2–R4. Separator lines are not content (RFC-0016 D1); rfc-0016-measure.py
# uses the same delimitation, so the gate and the acceptance figure agree.
_SEP_RE = re.compile(r'^(\s*|---|<a id="[^"]+"></a>)$')
_RULES_ANCHOR = '<a id="how-this-file-works"></a>'
_UNCONVERTED = "<!-- backlog: unconverted -->"
_DETAIL_RE = re.compile(r"^  Detail: \[dossier\]\((backlog/[^)\s]+\.md)\)$")
_DOSSIER_ID_RE = re.compile(r"^# ([A-Z]+-\d+[a-z]*) —")
_ITEM_CAP, _DIAGNOSIS_CAP, _PROMISE_CAP = 8, 5, 3
# A sentence ends at . ! or ? (optionally closed by a backtick, bold or bracket)
# followed by whitespace and a capital-ish opener; "e.g. this" does not split,
# and neither does a lowercase or digit opener (the docstring's fail-open bound).
_SENTENCE_END_RE = re.compile(r"[.!?][`*)\"']*\s+(?=[A-Z`*(\[\"])")


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


def _sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """Each backlog section as ``(title, heading index, end index)``.

    The rules header (the heading under ``_RULES_ANCHOR``) is not a section.
    ``end`` is exclusive and pulled back over separators, so a section's
    trailing ``---`` and the next anchor belong to the next section.
    """
    heads = [i for i, line in enumerate(lines) if line.startswith("## ")]
    out = []
    for k, h in enumerate(heads):
        if h > 0 and lines[h - 1] == _RULES_ANCHOR:
            continue
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        while end > h + 1 and _SEP_RE.match(lines[end - 1]):
            end -= 1
        out.append((lines[h][3:], h, end))
    return out


def _items(lines: list[str], start: int, end: int) -> list[tuple[str, int, int]]:
    """Items in ``lines[start:end]`` as ``(ID, header index, last content index)``."""
    heads = [j for j in range(start, end) if _HEADER_RE.match(lines[j])]
    out = []
    for a, b in zip(heads, [*heads[1:], end][: len(heads)], strict=True):
        last = b - 1
        while last > a and _SEP_RE.match(lines[last]):
            last -= 1
        m = _HEADER_RE.match(lines[a])
        assert m is not None  # heads holds only matching lines
        out.append((f"{m.group(2)}-{m.group(3)}", a, last))
    return out


def _shape_violations(text: str, base: Path) -> tuple[list[str], list[str], list[str]]:
    """R2 item cap, R3 section shape, R4 dossier link, as three lists.

    R2 and R3 skip a section whose heading is directly followed by
    ``_UNCONVERTED``: an opt-out, so a new section is gated from birth
    (ADR-0040 scopes both to migrated sections). R4 runs on every section.
    """
    lines = text.split("\n")
    caps: list[str] = []
    shapes: list[str] = []
    links: list[str] = []
    for title, h, end in _sections(lines):
        items = _items(lines, h + 1, end)
        gated = h + 1 >= len(lines) or lines[h + 1] != _UNCONVERTED
        if gated:
            shapes.extend(_section_shape(title, lines[h + 1 : items[0][1] if items else end]))
        for item, a, last in items:
            detail = _DETAIL_RE.match(lines[last]) is not None
            if gated:
                n = last - a + 1
                diagnosis = n - 2 - detail
                if n > _ITEM_CAP:
                    caps.append(f"line {a + 1}: {item}: {n} content lines (cap {_ITEM_CAP})")
                elif diagnosis > _DIAGNOSIS_CAP:
                    caps.append(f"line {a + 1}: {item}: diagnosis {diagnosis} lines (cap {_DIAGNOSIS_CAP})")
            for j in range(a + 1, last + 1):
                if lines[j].startswith("  Detail:"):
                    links.extend(f"line {j + 1}: {item}: {v}" for v in _dossier_link(item, lines[j], base))
    return caps, shapes, links


def _section_shape(title: str, preamble: list[str]) -> list[str]:
    """R3: heading, optional anchor, one ``**Promise:**`` paragraph of ≤ 3 sentences."""
    paragraphs: list[list[str]] = [[]]
    for line in preamble:
        if not line.strip():
            paragraphs.append([])
        elif not _SEP_RE.match(line):
            paragraphs[-1].append(line)
    paragraphs = [p for p in paragraphs if p]
    found = []
    if len(paragraphs) != 1:
        found.append(f"{title}: preamble has {len(paragraphs)} paragraphs (one Promise paragraph only)")
    if not paragraphs or not paragraphs[0][0].startswith("**Promise:**"):
        found.append(f"{title}: preamble does not open with **Promise:**")
        return found
    sentences = len(_SENTENCE_END_RE.findall(" ".join(paragraphs[0]).strip())) + 1
    if sentences > _PROMISE_CAP:
        found.append(f"{title}: Promise has {sentences} sentences (cap {_PROMISE_CAP})")
    return found


def _dossier_link(item: str, line: str, base: Path) -> list[str]:
    """R4: the link has D2's shape, resolves, and the dossier is named and headed for ``item``."""
    m = _DETAIL_RE.match(line)
    if m is None:
        return ["Detail: line is not `Detail: [dossier](backlog/<id>-<slug>.md)`"]
    rel = m.group(1)
    path = base / rel
    if not path.is_file():
        return [f"Detail: {rel} does not resolve"]
    found = []
    if not path.name.startswith(f"{item.lower()}-"):
        found.append(f"dossier path {rel} is not named {item.lower()}-<slug>.md")
    first = next((x for x in path.read_text(encoding="utf-8").split("\n") if x.startswith("# ")), "")
    head = _DOSSIER_ID_RE.match(first)
    if head is None or head.group(1) != item:
        found.append(f"dossier {rel} is headed {head.group(1) if head else 'with no ID'}")
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
    caps, shapes, links = _shape_violations(active_text, BACKLOG.parent)

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

    for found, rule in (
        (caps, "item(s) over the cap (R2)"),
        (shapes, "section shape violation(s) (R3)"),
        (links, "dossier link violation(s) (R4)"),
    ):
        if found:
            print(f"\nFound {len(found)} {rule} in {BACKLOG.name}, ADR-0040:")
            for v in found:
                print(f"  {v}")

    if duplicates or collisions or attributes or caps or shapes or links:
        return 1

    # Every rule named, so a clean run says which ones passed. The duplicate
    # rule is only reachable after two branches merge, so this line is the
    # first evidence most authors will have that it exists at all.
    print(
        "No ID collisions, no ID on two open items, every open item's attributes in vocabulary, "
        "every migrated section and its items in shape, and every Detail: link resolving to its dossier."
    )
    return 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return _check()
    return _generate()


if __name__ == "__main__":
    raise SystemExit(main())
