"""Check an ``/observe`` record's tables, or a spec's, against their declared domains (BK-504).

Usage: ``python scripts/observe_tables.py <document.md> <declarations.toml>``.
RFC-0029 R1's check G3, run by ``/observe-review`` before a reopen and again
before a freeze; the same code checks a spec, because the declarations, not the
document's shape, say where each table is.

The declarations are a TOML sidecar, ``sdd/observe/tables/<entry>.toml`` for a
record. Each ``[[table]]`` names a table by ``at``, a heading's opening words up to
a non-alphanumeric character (``OP-01/D9`` anchors ``### OP-01/D9: ...`` and never
``OP-01/D90``), and ``index``, its 1-based position under that heading (default 1),
and gives its ``kind``:

- ``case``: ``key``, the column whose cells name domain members, and ``members``,
  each a string matched as a whole word or ``{ name, match }`` with a regex. Each
  member is matched by exactly one row (complete, disjoint), and each row by
  some member. ``parts = { <member> = [<part>, ...] }`` lets one member span
  rows, each part in exactly one of them. ``source``, a list of ``{ at, column,
  index }``, names the enumeration the members come from: each member must
  occur in one of those columns, bar those listed in ``unsourced``, which no
  enumeration in the document holds. ``basis``, free text, says where a domain
  with no ``source`` comes from.
- ``state``: ``states``, matched in the first column, and ``events``, matched in
  the header. Each state has one row, each event a column, and no cell is empty.
- ``ids``: ``column`` defines the element IDs its cells hold (an Environment, a
  non-promise register).
- ``register``: a table no domain governs, with its ``reason``.

Every table in the document must be declared. Each ``[[ids]]`` gives a
``family`` (``OP-01/D``, ``KEY-``) and optionally its ``short`` form (``D``):
every token of a family must name an element defined by a heading
``<ID>: ...``, a bullet ``- `<ID>`: ...`` or an ``ids`` table, and ``<ID>, row
<n>`` must name an existing row of that element's first table. In a cell, ``X1
to X3`` covers X1, X2 and X3; a citation range checks its two ends only.

Authority: the document governs and the sidecar is a reading of it, written by
``/observe-review`` for a record, never by the session that decides it
(RFC-0028 P3: the review never edits the record). A finding is a gap, an overlap
or a dangling reference in the document unless re-reading shows the
declaration wrong, which is then corrected instead.

Bound: it checks a table against the domain declared for it, never whether
that domain is the right one, so a declaration that copies a table's own rows
finds nothing; ``source`` narrows that only where the members come from
another enumeration. It reads no meaning: two rows that each match one member
but promise conflicting outcomes (``OP-01/O33``'s kind) pass. Cells are split on
``|`` with ``\\|`` escaped; a table inside a fenced block is skipped. A
declaration written after reading known defects can be shaped to find them,
which its author states with the run (BK-504's trace).

Advisory, run by ``/observe-review`` only, and in no bundle (DRIFT-RULES Rule
5): its findings become open items that only a reopen session decides, so as a
gate it would hold master red from each review until that record's reopen.

Exit 0 with no finding, 1 with findings, 2 on unusable input.

Drift-gate::

    kind:       pair
    compares:   an /observe record's or spec's tables ↔ the domains a sidecar declares
        for them, and its ID citations ↔ the elements it defines
    domain:     process
"""

from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HEADING = re.compile(r"^#{1,6}\s+(?P<text>.*\S)\s*$")
_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}")
_RANGE = re.compile(r"(?<![\w/])(?P<p>[A-Za-z]+-?)(?P<a>\d+) to (?:(?P=p))?(?P<b>\d+)(?!\w)")
_BULLET = re.compile(r"^\s*- `(?P<id>[^`]+)`:")
_KINDS = ("case", "state", "ids", "register")


@dataclass
class Table:
    heading: str
    index: int
    line: int
    header: list[str]
    rows: list[tuple[int, list[str]]] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.heading.split(':')[0]} table {self.index}"


@dataclass
class Document:
    lines: list[str]
    headings: list[tuple[int, str]]
    tables: list[Table]
    # Lines outside fenced blocks, as (number, text): what citations are read from.
    prose: list[tuple[int, str]]


def _cells(line: str) -> list[str]:
    body = line.strip().replace("\\|", "\0")
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") else body
    return [c.strip().replace("\0", "|") for c in body.split("|")]


def parse(text: str) -> Document:
    lines = text.replace("\r\n", "\n").split("\n")
    headings: list[tuple[int, str]] = []
    tables: list[Table] = []
    prose: list[tuple[int, str]] = []
    heading, count, fenced, i = "", 0, False, 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            fenced = not fenced
            i += 1
            continue
        if fenced:
            i += 1
            continue
        prose.append((i + 1, line))
        head = _HEADING.match(line)
        if head:
            heading, count = head["text"], 0
            headings.append((i + 1, heading))
        elif line.strip().startswith("|") and i + 1 < len(lines) and _SEPARATOR.match(lines[i + 1].strip()):
            count += 1
            table = Table(heading, count, i + 1, _cells(line))
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                table.rows.append((j + 1, _cells(lines[j])))
                prose.append((j + 1, lines[j]))
                j += 1
            tables.append(table)
            prose.append((i + 2, lines[i + 1]))
            i = j
            continue
        i += 1
    return Document(lines, headings, tables, sorted(prose))


def _anchored(doc: Document, at: str) -> list[str]:
    """The headings *at* anchors: its opening words, then no further letter or digit."""
    return [h for _, h in doc.headings if h.startswith(at) and not h[len(at) : len(at) + 1].isalnum()]


def _find(doc: Document, at: str, index: int) -> Table | None:
    heads = _anchored(doc, at)
    if len(heads) != 1:
        return None
    return next((t for t in doc.tables if t.heading == heads[0] and t.index == index), None)


def _word(pattern: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w)(?:{pattern})(?!\w)")


def _expand(cell: str) -> str:
    """A cell with each ``X1 to X3`` written out as ``X1, X2, X3``."""

    def one(m: re.Match[str]) -> str:
        a, b = int(m["a"]), int(m["b"])
        return ", ".join(f"{m['p']}{n}" for n in range(a, b + 1)) if a <= b else m[0]

    return _RANGE.sub(one, cell)


def _rows(rows: list[int]) -> str:
    return f"rows {', '.join(map(str, rows[:-1]))} and {rows[-1]}"


@dataclass
class Member:
    name: str
    pattern: re.Pattern[str]


def _members(entry: dict[str, Any]) -> list[Member]:
    found = []
    for m in _required(entry, "members"):
        if isinstance(m, str):
            found.append(Member(m, _word(re.escape(m))))
        elif isinstance(m, dict) and isinstance(m.get("name"), str) and isinstance(m.get("match"), str):
            found.append(Member(m["name"], _word(m["match"])))
        else:
            raise ValueError(f"{entry.get('at')!r}: a member is a string or {{ name, match }}, not {m!r}")
    return found


def _required(entry: dict[str, Any], key: str) -> Any:
    if key not in entry:
        raise ValueError(f"{entry.get('at')!r}: a {entry.get('kind')} table needs {key!r}")
    return entry[key]


def _cell(cells: list[str], column: int) -> str:
    return cells[column - 1] if 0 < column <= len(cells) else ""


def check_case(doc: Document, table: Table, entry: dict[str, Any]) -> list[str]:
    key = int(_required(entry, "key"))
    members = _members(entry)
    parts: dict[str, list[str]] = entry.get("parts", {})
    keys = [(n, _expand(_cell(cells, key)), _cell(cells, key)) for n, (_, cells) in enumerate(table.rows, 1)]
    out: list[str] = []
    for m in members:
        hits = [n for n, cell, _ in keys if m.pattern.search(cell)]
        if m.name in parts:
            for part in parts[m.name]:
                part_hits = [n for n in hits if _word(re.escape(part)).search(keys[n - 1][1])]
                if not part_hits:
                    out.append(f"gap: {m.name!r} part {part!r} is matched by no row")
                elif len(part_hits) > 1:
                    out.append(f"overlap: {m.name!r} part {part!r} is matched by {_rows(part_hits)}")
            for n in hits:
                if not any(_word(re.escape(p)).search(keys[n - 1][1]) for p in parts[m.name]):
                    out.append(f"row {n} matches {m.name!r} but none of its parts")
        elif not hits:
            out.append(f"gap: {m.name!r} is matched by no row")
        elif len(hits) > 1:
            out.append(f"overlap: {m.name!r} is matched by {_rows(hits)}")
    for n, cell, raw in keys:
        if not any(m.pattern.search(cell) for m in members):
            out.append(f"row {n} ({raw!r}) matches no member")
    sources = entry.get("source", [])
    if sources:
        columns: list[str] = []
        names = []
        for src in sources:
            st = _find(doc, src["at"], int(src.get("index", 1)))
            if st is None:
                out.append(f"source: {src['at']!r} table {src.get('index', 1)} matches no table")
                continue
            names.append(f"{st.heading.split(':')[0]} column {src['column']}")
            columns += [_expand(_cell(cells, int(src["column"]))) for _, cells in st.rows]
        unsourced = set(entry.get("unsourced", []))
        for m in members:
            if names and m.name not in unsourced and not any(m.pattern.search(c) for c in columns):
                out.append(f"source: {m.name!r} occurs in no cell of {' or '.join(names)}")
    return out


def check_state(table: Table, entry: dict[str, Any]) -> list[str]:
    states = [Member(s, _word(re.escape(s))) for s in _required(entry, "states")]
    events = [Member(e, _word(re.escape(e))) for e in _required(entry, "events")]
    out: list[str] = []
    for s in states:
        hits = [n for n, (_, cells) in enumerate(table.rows, 1) if s.pattern.search(_cell(cells, 1))]
        if not hits:
            out.append(f"state {s.name!r} has no row")
        elif len(hits) > 1:
            out.append(f"state {s.name!r} has {_rows(hits)}")
    for e in events:
        if not any(e.pattern.search(h) for h in table.header[1:]):
            out.append(f"event {e.name!r} has no column")
    for n, (_, cells) in enumerate(table.rows, 1):
        if not any(s.pattern.search(_cell(cells, 1)) for s in states):
            out.append(f"row {n} ({_cell(cells, 1)!r}) matches no state")
        for col in range(2, len(table.header) + 1):
            if not _cell(cells, col):
                out.append(f"row {n} ({_cell(cells, 1)!r}) has an empty cell in column {col}")
    return out


@dataclass
class Family:
    family: str
    short: str | None
    full: re.Pattern[str]
    abbrev: re.Pattern[str] | None


def _families(spec: list[dict[str, Any]]) -> list[Family]:
    found = []
    for f in spec:
        family, short = f.get("family"), f.get("short")
        if not isinstance(family, str) or (short is not None and not isinstance(short, str)):
            raise ValueError(f"[[ids]] needs a string 'family' and an optional string 'short', not {f!r}")
        full = re.compile(rf"(?<![\w/]){re.escape(family)}(?P<n>\d+)(?!\w)")
        abbrev = re.compile(rf"(?<![\w/-]){re.escape(short)}(?P<n>\d+)(?!\w)") if short else None
        found.append(Family(family, short, full, abbrev))
    return found


def check_citations(doc: Document, families: list[Family], id_tables: list[tuple[Table, int]]) -> list[str]:
    defined: dict[str, str] = {}  # ID -> the heading whose section defines it, or "" for a bullet or a table cell
    for _, heading in doc.headings:
        for f in families:
            m = re.match(rf"{re.escape(f.family)}\d+(?=:|\s|$)", heading)
            if m:
                defined[m[0]] = heading
    for _, line in doc.prose:
        bullet = _BULLET.match(line)
        if bullet:
            defined.setdefault(bullet["id"], "")
    for table, column in id_tables:
        for _, cells in table.rows:
            for f in families:
                for m in f.full.finditer(_cell(cells, column)):
                    defined.setdefault(m[0], "")
    out: list[str] = []
    for number, line in doc.prose:
        if _HEADING.match(line) or _BULLET.match(line):
            line = re.sub(r"^\s*- `[^`]+`:|^#{1,6}\s+[^:]+:", "", line)
        found: list[tuple[int, str, str]] = []
        for f in families:
            for pattern in (f.full, f.abbrev):
                for m in pattern.finditer(line) if pattern else ():
                    found.append((m.start(), m[0], f.family + m["n"]))
        for _, written, canonical in sorted(found):
            if canonical not in defined:
                out.append(f"citation: {written!r} (line {number}) names no defined element")
        for f in families:
            names = re.escape(f.family) + (f"|{re.escape(f.short)}" if f.short else "")
            for m in re.finditer(rf"(?<![\w/-])(?:{names})(?P<n>\d+), row (?P<row>\d+)\b", line):
                canonical = f.family + m["n"]
                heading = defined.get(canonical)
                if not heading:
                    continue
                first = next((t for t in doc.tables if t.heading == heading), None)
                size = len(first.rows) if first else 0
                if int(m["row"]) > size:
                    out.append(f"citation: {m[0]!r} (line {number}): {canonical}'s first table has {size} rows")
    return out


def check(doc: Document, decl: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Findings as (declarations, tables, citations)."""
    entries = decl.get("table", [])
    if not isinstance(entries, list):
        raise ValueError("'table' must be an array of tables ([[table]])")
    declared: set[tuple[str, int]] = set()
    declarations: list[str] = []
    tables: list[str] = []
    id_tables: list[tuple[Table, int]] = []
    resolved: list[tuple[Table, dict[str, Any]]] = []
    for entry in entries:
        at, kind, index = entry.get("at"), entry.get("kind"), int(entry.get("index", 1))
        if not isinstance(at, str) or kind not in _KINDS:
            raise ValueError(f"a [[table]] needs a string 'at' and a kind in {_KINDS}, not {entry!r}")
        heads = _anchored(doc, at)
        if len(heads) > 1:
            declarations.append(f"declaration: {at!r} matches {len(heads)} headings")
            continue
        table = _find(doc, at, index)
        if table is None:
            declarations.append(f"declaration: {at!r} table {index} matches no table")
            continue
        declared.add((table.heading, table.index))
        resolved.append((table, entry))
        if kind == "ids":
            id_tables.append((table, int(_required(entry, "column"))))
        elif kind == "register":
            _required(entry, "reason")
    for table in doc.tables:
        if (table.heading, table.index) not in declared:
            declarations.append(f"declaration: {table.label} (line {table.line}) is declared by no entry")
    for table, entry in resolved:
        if entry["kind"] == "case":
            found = check_case(doc, table, entry)
        elif entry["kind"] == "state":
            found = check_state(table, entry)
        else:
            found = []
        tables += [f"{table.label}: {f}" for f in found]
    citations = check_citations(doc, _families(decl.get("ids", [])), id_tables)
    return declarations, tables, citations


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print((__doc__ or "").split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        doc = parse(Path(argv[1]).read_text(encoding="utf-8"))
        decl = tomllib.loads(Path(argv[2]).read_text(encoding="utf-8"))
        groups = check(doc, decl)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"observe_tables: {exc}", file=sys.stderr)
        return 2
    print(f"# Tables of {argv[1]} against {argv[2]}")
    for title, found in zip(("Declarations", "Tables", "Citations"), groups, strict=True):
        print(f"\n## {title}\n")
        print("\n".join(f"- {f}" for f in found) or "none")
    total = sum(len(g) for g in groups)
    print(f"\n{total} findings")
    return 1 if total else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.exit(main(sys.argv))
