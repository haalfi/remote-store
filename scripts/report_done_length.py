"""Median words per ``BACKLOG-DONE.md`` entry, per section, split by dossier.

ADR-0041 keeps a completed entry for an item with a dossier short: what
shipped and where, plus the link. The rule is review-enforced with no length
cap, so whether new entries follow it shows only in the numbers. This script
prints them: for each ``## `` section of ``sdd/BACKLOG-DONE.md``, the entry
count and median words, over all entries and split into entries for an item
with a dossier and entries without one. An item has a dossier when a file
named ``<id>-*.md`` sits in the ``backlog/`` directory beside the register, or
when its entry links one; *Unlinked* counts dossier entries that omit the link,
which the rule requires.

An entry runs from its ``- [x] **ID`` header line to the next header or any
``#`` heading; words are ``str.split()`` tokens. That is the derivation the
figures in ADR-0041's Context were measured with, so the release reading
compares like with like.

Run with::

    hatch run report-done-length
    python scripts/report_done_length.py [path/to/BACKLOG-DONE.md]

Why this is a report, not a gate
================================
The exit code never depends on what is found.
[`sdd/DRIFT-RULES.md` Rule 5](../sdd/DRIFT-RULES.md#mandatory-path) requires
an advisory check to say why it does not gate:

* **ADR-0041 decided against a length rule.** It follows the research's
  advice to add none beside CONTENT-RULES Rule 7; a word threshold here
  would be that rule by the back door.
* **A median is a population figure, not a per-entry verdict.** One long
  entry can be right (a close that records a decision), so no single entry
  fails. Whether the population moved is read once per release by a person.

What this report does NOT catch
===============================
State the bound, per [Rule 7](../sdd/DRIFT-RULES.md#miss-rate):

* **Length, not shape.** A short entry that omits where the work shipped, or
  a long one that restates its dossier, reads the same as a compliant entry
  of the same length. Shape stays review's job.
* **Dossiers are known by filename, links by text.** A dossier deleted or
  renamed off the ``<id>-`` prefix is not seen, so its unlinked entry falls
  into the without half. A link is ``](backlog/<id>-`` for the entry's own
  ID anywhere in the entry; a link written another way (``../backlog/``, an
  absolute URL) is not seen, so its entry reads as Unlinked.
* **No miss rate is estimated.** Nothing is flagged, so there is no recall
  to measure; the figure is only as good as the counting rule above.

Drift-gate::

    kind:       report
    surfaces:   median words per BACKLOG-DONE.md entry per section, split by whether the item
        has a dossier, and dossier entries that omit the link
    domain:     process
"""

from __future__ import annotations

import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parents[1] / "sdd" / "BACKLOG-DONE.md"
# An ID, or the dash an entry that never had one carries (Decided against).
_HEADER = re.compile(r"- \[x\] \*\*([A-Z]+-\d+|—)")
_LINK = "](backlog/"
_DOSSIER_FILE = re.compile(r"([a-z]+-\d+)-.*\.md")


@dataclass(frozen=True)
class Entry:
    words: int
    has_dossier: bool
    linked: bool


@dataclass(frozen=True)
class Row:
    section: str
    n: int
    median: float
    n_dossier: int
    median_dossier: float | None
    n_unlinked: int
    n_plain: int
    median_plain: float | None


def dossier_ids(directory: Path) -> frozenset[str]:
    """IDs with a ``<id>-*.md`` dossier in *directory*; empty if it is absent."""
    if not directory.is_dir():
        return frozenset()
    return frozenset(m.group(1).upper() for f in directory.iterdir() if (m := _DOSSIER_FILE.fullmatch(f.name)))


def parse(text: str, dossiers: frozenset[str] = frozenset()) -> dict[str, list[Entry]]:
    """Map each ``## `` section, in file order, to its entries.

    *dossiers* holds the IDs with a dossier file (see :func:`dossier_ids`).

    A heading that repeats gets its own key, suffixed ``(2)``, ``(3)``, ...
    """
    sections: dict[str, list[Entry]] = {}
    section: str | None = None
    current: list[str] | None = None
    item_id = ""

    def close() -> None:
        if current is not None and section is not None:
            body = "\n".join(current)
            # Only a link to the item's own dossier counts; citing a neighbour's does not.
            linked = item_id != "—" and f"{_LINK}{item_id.lower()}-" in body
            sections[section].append(Entry(len(body.split()), linked or item_id in dossiers, linked))

    for line in text.split("\n"):
        if line.startswith("#"):
            close()
            current = None
            if line.startswith("## "):
                name = line[3:].strip()
                section, k = name, 1
                while section in sections:
                    k += 1
                    section = f"{name} ({k})"
                sections[section] = []
        elif m := _HEADER.match(line):
            close()
            item_id = m.group(1)
            current = [line] if section is not None else None
        elif current is not None:
            current.append(line)
    close()
    return sections


def _median(values: list[int]) -> float | None:
    return float(statistics.median(values)) if values else None


def summarize(sections: dict[str, list[Entry]]) -> list[Row]:
    """One row per section that holds at least one entry."""
    rows = []
    for name, entries in sections.items():
        if not entries:
            continue
        with_dossier = [e.words for e in entries if e.has_dossier]
        plain = [e.words for e in entries if not e.has_dossier]
        rows.append(
            Row(
                section=name,
                n=len(entries),
                median=float(statistics.median(e.words for e in entries)),
                n_dossier=len(with_dossier),
                median_dossier=_median(with_dossier),
                n_unlinked=sum(1 for e in entries if e.has_dossier and not e.linked),
                n_plain=len(plain),
                median_plain=_median(plain),
            )
        )
    return rows


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:g}"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else _DEFAULT
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"report-done-length: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    print(f"Words per entry in {path.name} (header to next header or heading, str.split()).\n")
    print("| Section | Entries | Median | With dossier | Median | Unlinked | Without | Median |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in summarize(parse(text, dossier_ids(path.parent / "backlog"))):
        print(
            f"| {r.section} | {r.n} | {_fmt(r.median)} | {r.n_dossier} | {_fmt(r.median_dossier)}"
            f" | {r.n_unlinked} | {r.n_plain} | {_fmt(r.median_plain)} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
