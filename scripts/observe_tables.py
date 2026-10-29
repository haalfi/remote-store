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
  index, complete }``, names the enumeration the members come from: each member
  must occur in one of those columns, bar those listed in ``unsourced``, which no
  enumeration in the document holds, and with ``complete = true`` each row of
  that column must be matched by a member and each ID it names, of a family the
  members are IDs of, must be a member. ``basis``, free text, says where a
  domain with no ``source`` comes from.
- ``state``: ``states``, matched in the first column, and ``events``, matched in
  the header. Each state has one row, each event one column, each column an
  event, and no cell is empty.
- ``ids``: ``column`` defines the element IDs its cells hold (an Environment, a
  non-promise register).
- ``register``: a table no domain governs, with its ``reason``.

Every table in the document must be declared, once. Each ``[[ids]]`` gives a
``family`` (``OP-01/D``, ``KEY-``), optionally its ``short`` form (``D``) and
``retired``, the IDs the document names but defines nowhere on purpose (a
spec's unassigned IDs): every other token of a family must name an element
defined by a heading ``<ID>: ...``, a bullet ``- `<ID>`: ...`` or an ``ids``
table, and ``<ID>, row <n>`` must name an existing row of that element's first
table. A short form matches every bare token of its shape, so declare one only
for a letter the document uses for nothing else (not ``O``: axes.md's observers
are O1 to O3). In a cell, ``E1 to E3`` covers E1, E2 and E3; a citation range
checks its two ends only.

A key the kind does not take, a value of the wrong type, an empty string or
array, a non-positive column or index, a value named twice, or a family or short
form two ``[[ids]]`` declare exits 2: read
as findings, a malformed declaration would pass for a defective document, and
ignored, a misspelt key would switch its check off.

Authority: the document governs and the sidecar is a reading of it, written by
``/observe-review`` for a record, never by the session that decides it
(RFC-0028 P3: the review "never edits a decision, an Environment row or an
axis's decided state"). A finding is a gap, an overlap
or a dangling reference in the document unless re-reading shows the
declaration wrong, which is then corrected instead.

Bound: it checks a table against the domain declared for it, never whether
that domain is the right one, so a declaration that copies a table's own rows
finds nothing; ``source`` narrows that only where the members come from
another enumeration, and only a ``complete`` source catches an element the
enumeration gains that no member names. It reads no meaning: two rows that each
match one member but promise conflicting outcomes (``OP-01/O33``'s kind) pass.
A row cited by name (``D34's changed row``) or after a backticked ID goes
unchecked, some ID forms are misread and an ID defined twice is not reported:
BK-507 lists each. A member matches wherever the characters on either side of it are no letter,
digit or underscore: ``j = n`` matches inside ``j = n − 1``, and ``.`` never
matches after a letter; such a member needs a ``match``. Cells are split on ``|``
with ``\\|`` escaped; a table inside a fenced block (``` or ~~~) is skipped. A
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
_FENCE = re.compile(r"^\s*(?P<fence>```|~~~)")
_SEPARATOR = re.compile(r"^\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?$")
_RANGE = re.compile(r"(?<![\w/])(?P<p>[A-Za-z]+-?)(?P<a>\d+) to (?:(?P=p))?(?P<b>\d+)(?!\w)")
_BULLET = re.compile(r"^\s*- `(?P<id>[^`]+)`:")
# Per kind: the keys it requires and the keys it may carry, besides at, kind, index and basis.
_KEYS: dict[str, tuple[set[str], set[str]]] = {
    "case": ({"key", "members"}, {"parts", "source", "unsourced"}),
    "state": ({"states", "events"}, set()),
    "ids": ({"column"}, set()),
    "register": ({"reason"}, set()),
}
_KINDS = tuple(_KEYS)


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
    heading, count, fence, i = "", 0, "", 0
    while i < len(lines):
        line = lines[i]
        opening = _FENCE.match(line)
        if opening and (not fence or opening["fence"] == fence):
            fence = "" if fence else opening["fence"]
            i += 1
            continue
        if fence:
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
        # The width of the first end, so KEY-002 to KEY-004 holds KEY-003, not KEY-3.
        return ", ".join(f"{m['p']}{n:0{len(m['a'])}d}" for n in range(a, b + 1)) if a <= b else m[0]

    return _RANGE.sub(one, cell)


def _several(noun: str, numbers: list[int]) -> str:
    return f"{noun} {', '.join(map(str, numbers[:-1]))} and {numbers[-1]}"


# --- declarations: every shape is checked here, once, before any table is read ---


def _keys(obj: dict[str, Any], where: str, required: set[str], allowed: set[str]) -> None:
    missing = sorted(required - obj.keys())
    if missing:
        raise ValueError(f"{where} needs {', '.join(map(repr, missing))}")
    unknown = sorted(obj.keys() - required - allowed)
    if unknown:
        raise ValueError(f"{where} takes no {', '.join(map(repr, unknown))}")


def _positive(value: Any, where: str, key: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{where}: {key!r} must be a positive integer, not {value!r}")


def _text(value: Any, where: str, key: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: {key!r} must be a non-empty string, not {value!r}")


def _texts(value: Any, where: str, key: str) -> None:
    # A string where a list belongs would be read character by character into false findings.
    if not isinstance(value, list) or not value:
        raise ValueError(f"{where}: {key!r} must be a non-empty array, not {value!r}")
    for v in value:
        _text(v, where, key)
    if len(set(value)) < len(value):
        raise ValueError(f"{where}: {key!r} names a value twice: {value!r}")


def _tables_of(value: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(e, dict) for e in value):
        raise ValueError(f"{key!r} must be an array of tables ([[{key}]])")
    return value


def _validate_case(entry: dict[str, Any], where: str) -> None:
    _positive(entry["key"], where, "key")
    members = entry["members"]
    if not isinstance(members, list) or not members:
        raise ValueError(f"{where}: 'members' must be a non-empty array, not {members!r}")
    names = []
    for m in members:
        if isinstance(m, dict):
            _keys(m, f"{where}: a member", {"name", "match"}, set())
            _text(m["name"], where, "name")
            _text(m["match"], where, "match")
            re.compile(m["match"])
            names.append(m["name"])
        elif isinstance(m, str):
            _text(m, where, "members")
            names.append(m)
        else:
            raise ValueError(f"{where}: a member is a string or {{ name, match }}, not {m!r}")
    if len(set(names)) < len(names):
        raise ValueError(f"{where}: 'members' names a member twice: {names!r}")
    parts = entry.get("parts", {})
    if not isinstance(parts, dict):
        raise ValueError(f"{where}: 'parts' maps member names to arrays, not {parts!r}")
    for name, value in parts.items():
        if name not in names:
            raise ValueError(f"{where}: 'parts' names {name!r}, which is no member")
        _texts(value, where, f"parts.{name}")
    if "source" in entry:
        sources = entry["source"]
        if not isinstance(sources, list) or not sources or not all(isinstance(s, dict) for s in sources):
            raise ValueError(f"{where}: 'source' must be a non-empty array of {{ at, column }}, not {sources!r}")
        for src in sources:
            _keys(src, f"{where}: a source", {"at", "column"}, {"index", "complete"})
            _text(src["at"], where, "source.at")
            _positive(src["column"], where, "source.column")
            if "index" in src:
                _positive(src["index"], where, "source.index")
            if not isinstance(src.get("complete", False), bool):
                raise ValueError(f"{where}: 'source.complete' must be true or false, not {src['complete']!r}")
    if "unsourced" in entry:
        if "source" not in entry:
            raise ValueError(f"{where}: 'unsourced' needs a 'source'")
        _texts(entry["unsourced"], where, "unsourced")
        stray = [u for u in entry["unsourced"] if u not in names]
        if stray:
            raise ValueError(f"{where}: 'unsourced' names {stray!r}, which are no members")


def validate(decl: dict[str, Any]) -> None:
    """Raise ValueError on any declaration the check would misread, so it exits 2, never as findings."""
    _keys(decl, "the declarations", set(), {"table", "ids"})
    for entry in _tables_of(decl.get("table", []), "table"):
        at, kind = entry.get("at"), entry.get("kind")
        if not isinstance(at, str) or not at.strip() or kind not in _KINDS:
            raise ValueError(f"a [[table]] needs a non-empty string 'at' and a kind in {_KINDS}, not {entry!r}")
        where = f"{at!r}"
        required, allowed = _KEYS[kind]
        _keys(entry, f"a {kind} table {where}", required | {"at", "kind"}, allowed | {"index", "basis"})
        if "index" in entry:
            _positive(entry["index"], where, "index")
        if "basis" in entry:
            _text(entry["basis"], where, "basis")
        if kind == "case":
            _validate_case(entry, where)
        elif kind == "state":
            _texts(entry["states"], where, "states")
            _texts(entry["events"], where, "events")
        elif kind == "ids":
            _positive(entry["column"], where, "column")
        else:
            _text(entry["reason"], where, "reason")
    seen: dict[str, str] = {}  # a family or short form -> the family declaring it
    for f in _tables_of(decl.get("ids", []), "ids"):
        where = f"[[ids]] {f.get('family')!r}"
        _keys(f, where, {"family"}, {"short", "retired"})
        _text(f["family"], where, "family")
        if "short" in f:
            _text(f["short"], where, "short")
        if "retired" in f:
            _texts(f["retired"], where, "retired")
            stray = [r for r in f["retired"] if not re.fullmatch(rf"{re.escape(f['family'])}\d+", r)]
            if stray:
                raise ValueError(f"{where}: 'retired' names {stray!r}, which are not of this family")
        # A token two declarations claim would be read as two IDs, one of them undefined.
        for prefix in (f["family"], f.get("short")):
            if prefix is not None and prefix in seen:
                raise ValueError(f"{where}: {prefix!r} is already declared by [[ids]] {seen[prefix]!r}")
            if prefix is not None:
                seen[prefix] = f["family"]


# --- the checks: declarations are valid here ---


@dataclass
class Member:
    name: str
    pattern: re.Pattern[str]


def _members(entry: dict[str, Any]) -> list[Member]:
    return [
        Member(m, _word(re.escape(m))) if isinstance(m, str) else Member(m["name"], _word(m["match"]))
        for m in entry["members"]
    ]


def _cell(cells: list[str], column: int) -> str:
    return cells[column - 1] if column <= len(cells) else ""


def check_case(doc: Document, table: Table, entry: dict[str, Any], families: list[Family]) -> list[str]:
    key = entry["key"]
    members = _members(entry)
    # The ID families the members are elements of: a complete source's tokens of these must each be a member.
    domain = [f for f in families if any(_tokens(m.name, [f]) == [m.name] for m in members)]
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
                    out.append(f"overlap: {m.name!r} part {part!r} is matched by {_several('rows', part_hits)}")
            for n in hits:
                if not any(_word(re.escape(p)).search(keys[n - 1][1]) for p in parts[m.name]):
                    out.append(f"row {n} matches {m.name!r} but none of its parts")
        elif not hits:
            out.append(f"gap: {m.name!r} is matched by no row")
        elif len(hits) > 1:
            out.append(f"overlap: {m.name!r} is matched by {_several('rows', hits)}")
    for n, cell, raw in keys:
        if not any(m.pattern.search(cell) for m in members):
            out.append(f"row {n} ({raw!r}) matches no member")
    columns: list[str] = []
    names = []
    for src in entry.get("source", []):
        index, column = src.get("index", 1), src["column"]
        st = _find(doc, src["at"], index)
        if st is None:
            out.append(f"source: {src['at']!r} table {index} matches no table")
            continue
        if column > len(st.header):
            out.append(f"source: {src['at']!r} table {index} has {len(st.header)} columns, not {column}")
            continue
        name = f"{st.heading.split(':')[0]} column {column}"
        names.append(name)
        cells = [_cell(row, column) for _, row in st.rows]
        columns += [_expand(c) for c in cells]
        if src.get("complete", False):
            for n, c in enumerate(cells, 1):
                expanded = _expand(c)
                if not any(m.pattern.search(expanded) for m in members):
                    out.append(f"source: row {n} of {name} ({c!r}) matches no member")
                    continue
                # A row one member matches can still hold an element none does: E4 in "E1 to E4".
                for token in _tokens(expanded, domain):
                    if not any(m.pattern.search(token) for m in members):
                        out.append(f"source: row {n} of {name} ({c!r}) names {token!r}, which no member matches")
    unsourced = set(entry.get("unsourced", []))
    for m in members:
        if names and m.name not in unsourced and not any(m.pattern.search(c) for c in columns):
            out.append(f"source: {m.name!r} occurs in no cell of {' or '.join(names)}")
    return out


def check_state(table: Table, entry: dict[str, Any]) -> list[str]:
    states = [Member(s, _word(re.escape(s))) for s in entry["states"]]
    events = [Member(e, _word(re.escape(e))) for e in entry["events"]]
    out: list[str] = []
    for s in states:
        hits = [n for n, (_, cells) in enumerate(table.rows, 1) if s.pattern.search(_cell(cells, 1))]
        if not hits:
            out.append(f"state {s.name!r} has no row")
        elif len(hits) > 1:
            out.append(f"state {s.name!r} has {_several('rows', hits)}")
    heads = list(enumerate(table.header[1:], 2))
    for e in events:
        cols = [c for c, h in heads if e.pattern.search(h)]
        if not cols:
            out.append(f"event {e.name!r} has no column")
        elif len(cols) > 1:
            out.append(f"event {e.name!r} has {_several('columns', cols)}")
    for c, h in heads:
        if not any(e.pattern.search(h) for e in events):
            out.append(f"column {c} ({h!r}) matches no event")
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
        family, short = f["family"], f.get("short")
        full = re.compile(rf"(?<![\w/]){re.escape(family)}(?P<n>\d+)(?!\w)")
        abbrev = re.compile(rf"(?<![\w/-]){re.escape(short)}(?P<n>\d+)(?!\w)") if short else None
        found.append(Family(family, short, full, abbrev))
    return found


def _tokens(text: str, families: list[Family]) -> list[str]:
    """The IDs of *families* that *text* names, as written (full or short form)."""
    return [m[0] for f in families for p in (f.full, f.abbrev) if p for m in p.finditer(text)]


def check_citations(
    doc: Document, families: list[Family], id_tables: list[tuple[Table, int]], retired: list[str]
) -> list[str]:
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
                for m in f.full.finditer(_expand(_cell(cells, column))):
                    defined.setdefault(m[0], "")
    out = [f"citation: {r!r} is declared retired but is defined" for r in retired if r in defined]
    for number, line in doc.prose:
        if _HEADING.match(line) or _BULLET.match(line):
            line = re.sub(r"^\s*- `[^`]+`:|^#{1,6}\s+[^:]+:", "", line)
        found: list[tuple[int, str, str]] = []
        for f in families:
            for pattern in (f.full, f.abbrev):
                for m in pattern.finditer(line) if pattern else ():
                    found.append((m.start(), m[0], f.family + m["n"]))
        for _, written, canonical in sorted(found):
            if canonical not in defined and canonical not in retired:
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
    validate(decl)
    ids = decl.get("ids", [])
    families = _families(ids)
    declared: dict[tuple[str, int], int] = {}
    declarations: list[str] = []
    tables: list[str] = []
    id_tables: list[tuple[Table, int]] = []
    resolved: list[tuple[Table, dict[str, Any]]] = []
    for entry in decl.get("table", []):
        at, kind, index = entry["at"], entry["kind"], entry.get("index", 1)
        heads = _anchored(doc, at)
        if len(heads) > 1:
            declarations.append(f"declaration: {at!r} matches {len(heads)} headings")
            continue
        table = _find(doc, at, index)
        if table is None:
            declarations.append(f"declaration: {at!r} table {index} matches no table")
            continue
        declared[(table.heading, table.index)] = declared.get((table.heading, table.index), 0) + 1
        column = entry.get("key", entry.get("column"))
        if column is not None and column > len(table.header):
            declarations.append(f"declaration: {at!r} table {index} has {len(table.header)} columns, not {column}")
            continue
        resolved.append((table, entry))
        if kind == "ids":
            id_tables.append((table, entry["column"]))
    for table in doc.tables:
        times = declared.get((table.heading, table.index), 0)
        if times == 0:
            declarations.append(f"declaration: {table.label} (line {table.line}) is declared by no entry")
        elif times > 1:
            declarations.append(f"declaration: {table.label} (line {table.line}) is declared by {times} entries")
    for table, entry in resolved:
        if entry["kind"] == "case":
            found = check_case(doc, table, entry, families)
        elif entry["kind"] == "state":
            found = check_state(table, entry)
        else:
            found = []
        tables += [f"{table.label}: {f}" for f in found]
    retired = [r for f in ids for r in f.get("retired", [])]
    citations = check_citations(doc, families, id_tables, retired)
    return declarations, tables, citations


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print((__doc__ or "").split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        doc = parse(Path(argv[1]).read_text(encoding="utf-8"))
        decl = tomllib.loads(Path(argv[2]).read_text(encoding="utf-8"))
        groups = check(doc, decl)
    except (OSError, ValueError, re.error) as exc:  # ValueError covers bad TOML and UTF-8; re.error a bad ``match``
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
