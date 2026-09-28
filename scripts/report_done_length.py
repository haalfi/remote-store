"""Median words per ``BACKLOG-DONE.md`` entry, per section, split by dossier link.

ADR-0041 keeps a completed entry for an item with a dossier short: what
shipped and where, plus the link. The rule is review-enforced with no length
cap, so whether new entries follow it shows only in the numbers. This script
prints them: for each ``## `` section of ``sdd/BACKLOG-DONE.md``, the entry
count and median words, over all entries and split into entries that link a
dossier under ``sdd/backlog/`` and entries that do not.

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
* **A dossier link is detected textually** as ``](backlog/`` anywhere in the
  entry, so a link to some other item's dossier marks the entry as linked.
* **No miss rate is estimated.** Nothing is flagged, so there is no recall
  to measure; the figure is only as good as the counting rule above.

Drift-gate::

    kind:       report
    surfaces:   median words per BACKLOG-DONE.md entry per section, split by whether the entry
        links a dossier
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
_HEADER = re.compile(r"- \[x\] \*\*(?:[A-Z]+-\d+|—)")
_DOSSIER = "](backlog/"


@dataclass(frozen=True)
class Entry:
    words: int
    has_dossier: bool


@dataclass(frozen=True)
class Row:
    section: str
    n: int
    median: float
    n_dossier: int
    median_dossier: float | None
    n_plain: int
    median_plain: float | None


def parse(text: str) -> dict[str, list[Entry]]:
    """Map each ``## `` section, in file order, to its entries.

    A heading that repeats gets its own key, suffixed ``(2)``, ``(3)``, ...
    """
    sections: dict[str, list[Entry]] = {}
    section: str | None = None
    current: list[str] | None = None

    def close() -> None:
        if current is not None and section is not None:
            body = "\n".join(current)
            sections[section].append(Entry(len(body.split()), _DOSSIER in body))

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
        elif _HEADER.match(line):
            close()
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
        linked = [e.words for e in entries if e.has_dossier]
        plain = [e.words for e in entries if not e.has_dossier]
        rows.append(
            Row(
                section=name,
                n=len(entries),
                median=float(statistics.median(e.words for e in entries)),
                n_dossier=len(linked),
                median_dossier=_median(linked),
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
    print("| Section | Entries | Median | With dossier | Median | Without | Median |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in summarize(parse(text)):
        print(
            f"| {r.section} | {r.n} | {_fmt(r.median)} | {r.n_dossier} | {_fmt(r.median_dossier)}"
            f" | {r.n_plain} | {_fmt(r.median_plain)} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
