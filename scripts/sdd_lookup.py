#!/usr/bin/env python3
"""Print one backlog item, done entry, dossier, reference section or ripple row by key (BK-414).

Read-only. Every call parses the files it reads; there is no cache and no
generated copy. Commands, each with a hatch alias:

``show <ID>...`` (``backlog-show``)
    Every ``BACKLOG.md`` / ``BACKLOG-DONE.md`` header carrying the ID,
    verbatim, after a location line. ``--dossier`` appends the item's dossier
    whole, under a banner carrying ``BACKLOG.md`` § Item authority.
``find [<regex>] [--open | --done | --dossiers] [--spec <ID>]... [--max N]`` (``backlog-find``)
    One line per matching item, not per matching line. The regex is
    case-insensitive and matched against the whole entry. ``--spec`` keeps
    open items whose attribute line names that spec ID as a whole token
    (case-insensitive); given several times it keeps an item naming any.
``outline [--done] [--section <text>]`` (``backlog-outline``)
    ``##`` sections with entry counts; with ``--section``, the entries of
    every section whose title contains the text.
``ref-show <anchor | heading> | --list`` (``ref-show``)
    A ``CLAUDE-REFERENCE.md`` section from its heading to the next heading of
    the same or a higher level.
``ref-rows <text>`` (``ref-rows``)
    Every ripple-check trigger whose name contains the text (case-insensitive,
    backticks and ``**`` ignored): its Pre-work row and its Detailed checklist
    rows, verbatim.

A key that matches nothing exits 1 and says what would have matched; it is
never an empty success.

Grammar. Item headers and backlog sections come from ``gen_backlogid.py``
(``_HEADER_RE``, ``_sections``), ripple triggers from
``check_ripple_parity.py`` (``_blocks``, ``_parse_pre_work``,
``_parse_detailed``). Both are gated in ``lint`` and ``docs-gate``, so a file
shape change that breaks the parse fails there first. Two boundaries are this
tool's own:

* An entry starts at ``- [?] **`` and ends before the next line that is
  neither blank nor indented. ``_HEADER_RE`` needs an ID, so it would fold the
  ID-less ``- [x] **— …**`` entries of § Decided against into the entry above.
* A Detailed trigger's rows run from its bold leading cell to the line before
  the next trigger, ``####`` heading or non-table line; ``_parse_detailed``
  returns only the first line.

Bounds (DRIFT-RULES Rule 7):

* ``show`` finds an ID on a header only; a prose mention is reachable by
  ``find``. A released duplicate pair that ``gen_backlogid.py`` tolerates
  prints both headers, each labelled with its section.
* ``--spec`` reads the attribute line, which only open items carry, so it
  never reaches a done entry or a dossier.
* ``ref-show`` reaches anchored sections and, by heading text, unanchored ones.
  A heading inside a fenced code block is not a heading.
* ``ref-rows`` returns table rows, not the paragraphs before a table. It pairs
  the two presentations by name, not by a parent link: ``Trigger`` carries no
  parent, and ``check_ripple_parity.py`` declines an expansion map as something
  that would go stale. A Detailed trigger with no Pre-work twin (a sync/async
  expansion) prints ``[pre-work] none: expansion row``; query its stem to get
  it beside its parent. A short query over-matches (``_GATING dict`` also
  returns ``_BACKEND_GATING dict``) and prints every match.
* Output is verbatim, with no judgement of whether the text is current, and
  reads this working tree only, not other branches.

Not a gate: it compares nothing, so it carries no ``Drift-gate::`` block, and
a wrong answer fails only its own tests (``tests/scripts/test_sdd_lookup.py``,
which also resolves every open ID, anchor and trigger in the live files).
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from check_ripple_parity import Trigger, _blocks, _parse_detailed, _parse_pre_work
from gen_backlogid import _HEADER_RE, _sections

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "sdd" / "BACKLOG.md"
BACKLOG_DONE = ROOT / "sdd" / "BACKLOG-DONE.md"
DOSSIERS = ROOT / "sdd" / "backlog"
REFERENCE = ROOT / "sdd" / "CLAUDE-REFERENCE.md"

# The bold title ends at the first `**` outside a code span: a header can quote `**Breaking**`.
_ENTRY_RE = re.compile(r"^- \[(.)\] \*\*((?:`[^`]*`|[^`*]|\*(?!\*))*)\*\*")
_SPEC_RE = re.compile(r"^  spec: (.+?) · effort: ")
_DOSSIER_LINK_RE = re.compile(r"\((backlog/[^)\s]+\.md)\)")
_HEADING_RE = re.compile(r"^(#{1,6}) +(.+?)\s*$")
_ANCHOR_RE = re.compile(r'^<a id="([^"]+)"></a>$')
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_BANNER = "--- dossier {path} (evidence: dated record; prescription: advisory, re-derive before acting) ---"
_MATCH_WIDTH = 160


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# --------------------------------------------------------------------------- #
# Backlog entries
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Entry:
    path: Path
    status: str  # "open", "in progress" or "done"
    item: str | None  # None for an ID-less § Decided against entry
    title: str
    section: str
    lines: tuple[str, ...]
    line: int  # 1-indexed header line

    def location(self) -> str:
        return f"{self.item or '—'} · {self.status} · {_rel(self.path)}:{self.line}"


def _entries(path: Path) -> list[Entry]:
    """Every entry in one backlog file, in file order, with its ``##`` section."""
    lines = path.read_text(encoding="utf-8").split("\n")
    out: list[Entry] = []
    for section, h, end in _sections(lines):
        for k in range(h + 1, end):
            m = _ENTRY_RE.match(lines[k])
            if m is None:
                continue
            stop = k + 1
            while stop < end and (not lines[stop].strip() or lines[stop][0].isspace()):
                stop += 1
            while stop > k + 1 and not lines[stop - 1].strip():
                stop -= 1
            head = _HEADER_RE.match(lines[k])
            item = f"{head.group(2)}-{head.group(3)}" if head else None
            title = m.group(2)
            if " — " in title:
                title = title.split(" — ", 1)[1]
            if path == BACKLOG_DONE or m.group(1) == "x":
                status = "done"
            else:
                status = "in progress" if m.group(1) == "~" else "open"
            out.append(Entry(path, status, item, title, section, tuple(lines[k:stop]), k + 1))
    return out


def _all_entries(*, open_: bool = True, done: bool = True) -> list[Entry]:
    return [*(_entries(BACKLOG) if open_ else []), *(_entries(BACKLOG_DONE) if done else [])]


def _dossiers_of(entry: Entry) -> list[Path]:
    """The dossiers an entry links, plus any named for its ID (``BACKLOG.md`` § Dossiers)."""
    found: list[Path] = []
    for line in entry.lines:
        found.extend(BACKLOG.parent / rel for rel in _DOSSIER_LINK_RE.findall(line))
    if entry.item:
        found.extend(sorted(DOSSIERS.glob(f"{entry.item.lower()}-*.md")))
    unique: list[Path] = []
    for p in found:
        if p.is_file() and p.resolve() not in {u.resolve() for u in unique}:
            unique.append(p)
    return unique


def _clip(line: str) -> str:
    line = line.strip()
    return line if len(line) <= _MATCH_WIDTH else line[: _MATCH_WIDTH - 1] + "…"


def cmd_show(ids: list[str], dossier: bool) -> int:
    entries = _all_entries()
    missing: list[str] = []
    blocks: list[str] = []
    for raw in ids:
        item = raw.upper()
        hits = [e for e in entries if e.item == item]
        if not hits:
            missing.append(raw)
            continue
        shown: list[Path] = []
        for e in hits:
            blocks.append(f"{e.location()} · § {e.section}\n" + "\n".join(e.lines))
            if not dossier:
                continue
            for p in _dossiers_of(e):
                if p in shown:
                    continue
                shown.append(p)
                blocks.append(_BANNER.format(path=_rel(p)) + "\n" + p.read_text(encoding="utf-8").rstrip("\n"))
            if not shown:
                blocks.append(f"--- dossier: none for {item} ---")
    if blocks:
        print("\n\n".join(blocks))
    if missing:
        print(
            f"No header in {_rel(BACKLOG)} or {_rel(BACKLOG_DONE)} carries {', '.join(missing)}. "
            "A prose mention is reachable by `backlog-find`; `backlog-outline --section <text>` lists IDs.",
            file=sys.stderr,
        )
        return 1
    return 0


def _spec_ids(entry: Entry) -> set[str]:
    m = _SPEC_RE.match(entry.lines[1]) if len(entry.lines) > 1 else None
    return {s.strip().upper() for s in m.group(1).split(",")} if m else set()


def cmd_find(pattern: re.Pattern[str] | None, scope: str | None, specs: list[str], limit: int) -> int:
    rows: list[str] = []
    if scope in (None, "open", "done"):
        for e in _all_entries(open_=scope in (None, "open") or bool(specs), done=scope in (None, "done") and not specs):
            if specs and not _spec_ids(e) & {s.upper() for s in specs}:
                continue
            if pattern is None:
                at = 1  # --spec alone: show the attribute line that matched
            else:
                at = next((i for i, line in enumerate(e.lines) if pattern.search(line)), -1)
                if at < 0:
                    continue
            row = f"{e.location()} · {e.title}"
            if at > 0:
                row += f" ⟶ {_clip(e.lines[at])}"
            rows.append(row)
    if scope in (None, "dossiers") and not specs and pattern is not None:
        for p in sorted(DOSSIERS.glob("*.md")):
            text = p.read_text(encoding="utf-8").split("\n")
            at = next((i for i, line in enumerate(text) if pattern.search(line)), -1)
            if at < 0:
                continue
            h1 = next((x[2:] for x in text if x.startswith("# ")), p.name)
            rows.append(f"{_rel(p)}:{at + 1} · {h1} ⟶ {_clip(text[at])}")
    if not rows:
        terms = [f"/{pattern.pattern}/"] if pattern else []
        terms += [f"spec {', '.join(specs)}"] if specs else []
        what = " and ".join(terms)
        print(f"No {scope or 'item, entry or dossier'} matches {what}.", file=sys.stderr)
        return 1
    print("\n".join(rows[:limit]))
    if len(rows) > limit:
        print(f"… {len(rows) - limit} more; narrow the pattern or raise --max.")
    return 0


def cmd_outline(done: bool, section: str | None) -> int:
    path = BACKLOG_DONE if done else BACKLOG
    lines = path.read_text(encoding="utf-8").split("\n")
    entries = _entries(path)
    sections = _sections(lines)
    if section is None:
        for title, h, _end in sections:
            n = sum(1 for e in entries if h < e.line - 1 < _end)
            print(f"{_rel(path)}:{h + 1} ## {title} · {n} entries")
        return 0
    wanted = [(t, h, end) for t, h, end in sections if section.casefold() in t.casefold()]
    if not wanted:
        print(f"No section of {_rel(path)} contains {section!r}. Sections:", file=sys.stderr)
        for title, _h, _end in sections:
            print(f"  {title}", file=sys.stderr)
        return 1
    for title, h, end in wanted:
        print(f"{_rel(path)}:{h + 1} ## {title}")
        for e in entries:
            if h < e.line - 1 < end:
                print(f"  {e.location()} · {e.title}")
    return 0


# --------------------------------------------------------------------------- #
# CLAUDE-REFERENCE.md sections
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    anchor: str | None
    start: int  # 0-indexed heading line
    end: int  # exclusive, trailing separators trimmed


def _headings(lines: list[str]) -> list[Heading]:
    raw: list[tuple[int, str, str | None, int]] = []
    fenced = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        m = None if fenced else _HEADING_RE.match(line)
        if m:
            prev = _ANCHOR_RE.match(lines[i - 1].strip()) if i else None
            raw.append((len(m.group(1)), m.group(2), prev.group(1) if prev else None, i))
    out: list[Heading] = []
    for n, (level, text, anchor, start) in enumerate(raw):
        end = next((s for lv, _t, _a, s in raw[n + 1 :] if lv <= level), len(lines))
        while end > start + 1 and (
            not lines[end - 1].strip() or lines[end - 1].strip() == "---" or _ANCHOR_RE.match(lines[end - 1].strip())
        ):
            end -= 1
        out.append(Heading(level, text, anchor, start, end))
    return out


def cmd_ref_show(key: str | None, list_: bool) -> int:
    lines = REFERENCE.read_text(encoding="utf-8").split("\n")
    heads = _headings(lines)
    if list_ or key is None:
        for h in heads:
            anchor = f" #{h.anchor}" if h.anchor else ""
            print(f"{_rel(REFERENCE)}:{h.start + 1} {'#' * h.level} {h.text}{anchor} · {h.end - h.start} lines")
        return 0
    k = key.lstrip("#").strip()
    hits = [h for h in heads if h.anchor == k] or [h for h in heads if h.text.casefold() == k.casefold()]
    if not hits:
        partial = [h for h in heads if k.casefold() in h.text.casefold()]
        if len(partial) == 1:
            hits = partial
        else:
            reason = f"{len(partial)} headings contain" if partial else "No anchor or heading matches"
            print(f"{reason} {key!r} in {_rel(REFERENCE)}. Candidates:", file=sys.stderr)
            for h in partial or heads:
                anchor = f" #{h.anchor}" if h.anchor else ""
                print(f"  {'#' * h.level} {h.text}{anchor}", file=sys.stderr)
            return 1
    print(
        "\n\n".join(
            f"{_rel(REFERENCE)}:{h.start + 1}-{h.end} · {h.text}\n" + "\n".join(lines[h.start : h.end]) for h in hits
        )
    )
    return 0


def _trigger_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("`", "").replace("**", "")).strip().casefold()


def _detailed_extent(lines: list[str], det: list[Trigger], t: Trigger) -> int:
    """Last 1-indexed line of a Detailed trigger's rows."""
    later = [d.line for d in det if d.line > t.line]
    limit = later[0] - 1 if later else len(lines)
    last = t.line
    while last < limit and lines[last].lstrip().startswith("|"):
        last += 1
    return last


def cmd_ref_rows(text: str) -> int:
    content = REFERENCE.read_text(encoding="utf-8")
    lines = content.splitlines()
    pre_block, det_block = _blocks(content)
    pre, det = _parse_pre_work(pre_block), _parse_detailed(det_block)
    if not pre or not det:
        print(f"No ripple-check tables parsed from {_rel(REFERENCE)}.", file=sys.stderr)
        return 1
    q = _trigger_key(text)
    pre_by_key = {t.key: t for t in pre}
    det_keys = {t.key for t in det}
    where = _rel(REFERENCE)
    groups: list[str] = []
    for d in (t for t in det if q in _trigger_key(t.name)):
        twin = pre_by_key.get(d.key)
        head = f"[pre-work] {where}:{twin.line}\n{lines[twin.line - 1]}" if twin else "[pre-work] none: expansion row"
        last = _detailed_extent(lines, det, d)
        span = f"{d.line}-{last}" if last > d.line else f"{d.line}"
        groups.append(f"{head}\n[detailed] {where}:{span}\n" + "\n".join(lines[d.line - 1 : last]))
    for p in (t for t in pre if q in _trigger_key(t.name) and t.key not in det_keys):
        groups.append(f"[pre-work] {where}:{p.line}\n{lines[p.line - 1]}\n[detailed] none")
    if not groups:
        print(f"No ripple-check trigger name contains {text!r}. Triggers:", file=sys.stderr)
        seen: set[str] = set()
        for t in sorted([*pre, *det], key=lambda t: t.line):
            if t.name not in seen:
                seen.add(t.name)
                print(f"  {t.section} · {t.name}", file=sys.stderr)
        return 1
    print("\n\n".join(groups))
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="print every header carrying the ID(s), verbatim")
    show.add_argument("ids", nargs="+", metavar="ID")
    show.add_argument("--dossier", action="store_true", help="append the item's dossier whole")

    find = sub.add_parser("find", help="one line per item matching a regex and/or spec ID")
    find.add_argument("pattern", nargs="?", help="case-insensitive regex, matched against each entry")
    scope = find.add_mutually_exclusive_group()
    scope.add_argument("--open", dest="scope", action="store_const", const="open")
    scope.add_argument("--done", dest="scope", action="store_const", const="done")
    scope.add_argument("--dossiers", dest="scope", action="store_const", const="dossiers")
    find.add_argument(
        "--spec", action="append", default=[], metavar="ID", help="open items whose attribute line names this spec ID"
    )
    find.add_argument("--max", type=int, default=20, dest="limit")

    outline = sub.add_parser("outline", help="## sections with entry counts")
    outline.add_argument("--done", action="store_true", help="outline BACKLOG-DONE.md instead")
    outline.add_argument("--section", help="list the entries of sections whose title contains this text")

    ref_show = sub.add_parser("ref-show", help="print a CLAUDE-REFERENCE.md section by anchor or heading")
    ref_show.add_argument("key", nargs="?")
    ref_show.add_argument("--list", action="store_true", dest="list_", help="list every heading and anchor")

    ref_rows = sub.add_parser("ref-rows", help="print a ripple-check trigger's Pre-work and Detailed rows")
    ref_rows.add_argument("text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    # Output quotes the files verbatim, em dashes and arrows included, which a
    # Windows cp1252 stdout cannot encode (BUG-305).
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    if args.command == "show":
        return cmd_show(args.ids, args.dossier)
    if args.command == "find":
        if args.pattern is None and not args.spec:
            parser.error("find needs a pattern, --spec, or both")
        if args.spec and args.scope in ("done", "dossiers"):
            parser.error("--spec reads the attribute line, which only open items carry")
        try:
            pattern = re.compile(args.pattern, re.IGNORECASE) if args.pattern is not None else None
        except re.error as exc:
            parser.error(f"invalid regex: {exc}")
        return cmd_find(pattern, args.scope, args.spec, args.limit)
    if args.command == "outline":
        return cmd_outline(args.done, args.section)
    if args.command == "ref-show":
        return cmd_ref_show(args.key, args.list_)
    return cmd_ref_rows(args.text)


if __name__ == "__main__":
    raise SystemExit(main())
