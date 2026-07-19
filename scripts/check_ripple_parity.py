"""Gate: the ripple-check's two presentations stay in trigger-parity.

`sdd/CLAUDE-REFERENCE.md` presents the ripple-check twice:

* the **Pre-work index** -- one line per trigger, read before starting; and
* the **Detailed checklist** -- the same triggers with their full ripple set,
  read at verify-end and during PR review.

The header note over the two tables promises they "cover the same triggers in
the same lifecycle order". They never quite did by hand: the Detailed checklist
*expands* two triggers into sync + async pairs (`_GATING dict` →
`_GATING dict` + `_GATING dict (async)`; `_BACKEND_GATING dict` →
`_BACKEND_GATING dict` + `_ASYNC_BACKEND_GATING`), which is intentional, but it
had also silently *dropped* one (`Local-machine reference in any committed
file`), which was a defect a reader of either table alone could not see. The
enforcement comment beside the tables always said "if drift recurs, promote a
check script into BACKLOG" -- this is that script (ID-234).

The invariant
=============

The **Pre-work index is the canonical spine.** Every Pre-work trigger must
appear in the Detailed checklist under the **same lifecycle section** and in the
**same relative order**. The Detailed checklist MAY carry extra *expansion*
rows that have no Pre-work equivalent (the sync/async splits), but:

* it may not *omit* a Pre-work trigger,
* it may not *reorder* the shared triggers, and
* an expansion row may not float free -- within a section it must follow at
  least one shared (Pre-work) trigger, so a genuinely new trigger added only to
  the Detailed checklist (and forgotten in the Pre-work index) is still caught.

This is trigger-parity, not row-parity: the Detailed checklist's higher row
count is by design, so a checksum on row counts (which never held) is the wrong
tool. Matching trigger *names* under their section is what actually drifts.

Parsing
=======

Both presentations are Markdown tables grouped under ``#### <Section>``
headers, bracketed by the ``pre-work-index`` and ``detailed-checklist`` HTML
anchors. A trigger is the **leading cell** of a data row:

* In the Pre-work index every trigger is a single, un-bolded row.
* In the Detailed checklist trigger names are **bold**; a long name wraps across
  consecutive bold leading cells (``**New authoritative**`` /
  ``**process doc in `sdd/`**``), and a trigger's ripple set continues in
  following rows whose leading cell is empty or a non-bold ``(qualifier)``. So a
  Detailed trigger begins at a bold leading cell that does *not* immediately
  follow another bold leading cell, and its name is the concatenation of the
  consecutive bold cells.

Exit codes
==========

* ``0`` -- every Pre-work trigger is present in the Detailed checklist, same
  section, same order.
* ``1`` -- a trigger was omitted, reordered, or an expansion is unanchored;
  one line per violation to stderr, plus remediation.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REFERENCE = _REPO_ROOT / "sdd" / "CLAUDE-REFERENCE.md"

# The ripple-check lives between these anchors. The Detailed checklist runs from
# its anchor to the first top-level break (`---` or a `## ` heading) after it.
_PRE_WORK_ANCHOR = '<a id="pre-work-index"></a>'
_DETAILED_ANCHOR = '<a id="detailed-checklist"></a>'

_SECTION_RE = re.compile(r"^#### +(.+?)\s*$")
_TOP_BREAK_RE = re.compile(r"^(-{3,}\s*|## +.+)$")


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Trigger:
    section: str
    name: str
    line: int  # 1-indexed line in CLAUDE-REFERENCE.md

    @property
    def key(self) -> tuple[str, str]:
        return (self.section, self.name)


@dataclass(frozen=True)
class Violation:
    line: int
    message: str


# --------------------------------------------------------------------------- #
# Table helpers
# --------------------------------------------------------------------------- #


def _leading_cell(row: str) -> str:
    """First cell of a Markdown table row, stripped of the outer pipes."""
    return row.strip().strip("|").split("|", 1)[0].strip()


def _is_table_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def _is_separator(cell: str) -> bool:
    return bool(cell) and set(cell) <= set("-: ")


def _norm(cell: str) -> str:
    """Trigger name, comparable across the two presentations.

    Strip the bold markers the Detailed checklist wraps names in, drop
    surrounding whitespace, and collapse internal runs of whitespace so a
    name that wrapped across cells reads identically to its one-line form.
    """
    return re.sub(r"\s+", " ", cell.replace("**", "").strip())


def _is_bold(cell: str) -> bool:
    return "**" in cell


# --------------------------------------------------------------------------- #
# Block extraction
# --------------------------------------------------------------------------- #


def _blocks(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (pre_work_lines, detailed_lines) as (lineno, line) pairs.

    ``lineno`` is 1-indexed into the whole file so violations point at the
    real line. The Pre-work block runs from its anchor to the Detailed
    anchor; the Detailed block from its anchor to the next top-level break.
    """
    lines = text.splitlines()
    pre_start = det_start = None
    for i, line in enumerate(lines):
        if _PRE_WORK_ANCHOR in line:
            pre_start = i
        elif _DETAILED_ANCHOR in line:
            det_start = i
            break

    if pre_start is None or det_start is None:
        return [], []

    pre = [(i + 1, lines[i]) for i in range(pre_start, det_start)]

    det_end = len(lines)
    for i in range(det_start + 1, len(lines)):
        if _TOP_BREAK_RE.match(lines[i]):
            det_end = i
            break
    det = [(i + 1, lines[i]) for i in range(det_start, det_end)]
    return pre, det


# --------------------------------------------------------------------------- #
# Trigger extraction
# --------------------------------------------------------------------------- #


def _parse_pre_work(block: list[tuple[int, str]]) -> list[Trigger]:
    """One trigger per data row; the leading cell is the trigger name."""
    triggers: list[Trigger] = []
    section = ""
    for lineno, line in block:
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1)
            continue
        if not _is_table_row(line):
            continue
        cell = _leading_cell(line)
        if not cell or _is_separator(cell) or _norm(cell) == "Trigger":
            continue
        triggers.append(Trigger(section, _norm(cell), lineno))
    return triggers


def _parse_detailed(block: list[tuple[int, str]]) -> list[Trigger]:
    """Each **bold** leading cell is one trigger; other rows continue it.

    A trigger's full name lives in a single bold leading cell -- a long
    qualifier wraps into *non-bold* continuation cells, never across a second
    bold cell. That keeps the rule unambiguous: two consecutive bold cells are
    two triggers (``**Spec section**`` then ``**Capability**``), never one name
    split in two. If a name is ever re-wrapped across two bold cells, both halves
    read as triggers absent from the Pre-work index, so this gate fails and
    points the editor back at the single-cell form.
    """
    triggers: list[Trigger] = []
    section = ""
    for lineno, line in block:
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1)
            continue
        if not _is_table_row(line):
            continue
        cell = _leading_cell(line)
        if _is_separator(cell) or _norm(cell) == "Trigger":
            continue
        if _is_bold(cell):
            triggers.append(Trigger(section, _norm(cell), lineno))
    return triggers


# --------------------------------------------------------------------------- #
# The invariant
# --------------------------------------------------------------------------- #


def check(pre: list[Trigger], det: list[Trigger]) -> list[Violation]:
    violations: list[Violation] = []

    if not pre:
        violations.append(Violation(1, "Pre-work index: no triggers parsed (table structure changed?)"))
    if not det:
        violations.append(Violation(1, "Detailed checklist: no triggers parsed (table structure changed?)"))
    if not pre or not det:
        return violations

    det_keys = [t.key for t in det]
    det_key_set = set(det_keys)

    # 1. Presence: every Pre-work trigger must exist in the Detailed checklist,
    #    under the same section.
    absent = [t for t in pre if t.key not in det_key_set]
    for t in absent:
        violations.append(
            Violation(
                t.line,
                f"Pre-work trigger {t.name!r} (section {t.section!r}) is missing from the Detailed checklist",
            )
        )

    # 2. Order: the Pre-work triggers present in the Detailed checklist must
    #    appear there in the same relative order (greedy subsequence match).
    if not absent:
        i = 0
        for key in det_keys:
            if i < len(pre) and key == pre[i].key:
                i += 1
        if i < len(pre):
            t = pre[i]
            violations.append(
                Violation(
                    t.line,
                    f"Pre-work trigger {t.name!r} (section {t.section!r}) is out of order in the Detailed checklist",
                )
            )

    # 3. Anchored expansions: an extra Detailed trigger (no Pre-work twin) must
    #    follow a shared trigger within its section, so a new trigger added only
    #    to the Detailed checklist cannot masquerade as an expansion.
    pre_key_set = {t.key for t in pre}
    seen_shared_in_section: set[str] = set()
    for t in det:
        if t.key in pre_key_set:
            seen_shared_in_section.add(t.section)
        elif t.section not in seen_shared_in_section:
            violations.append(
                Violation(
                    t.line,
                    f"Detailed trigger {t.name!r} (section {t.section!r}) has no "
                    f"Pre-work trigger before it: add it to the Pre-work index, or "
                    f"place the expansion after its parent trigger",
                )
            )

    violations.sort(key=lambda v: v.line)
    return violations


def collect_violations(reference: Path = _REFERENCE) -> list[Violation]:
    try:
        text = reference.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - only if the file vanishes
        return [Violation(1, f"cannot read {reference}: {exc}")]
    pre_block, det_block = _blocks(text)
    return check(_parse_pre_work(pre_block), _parse_detailed(det_block))


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

_REMEDIATION = (
    "See sdd/CLAUDE-REFERENCE.md (Ripple-check table, header note). Every "
    "Pre-work index trigger must appear in the Detailed checklist under the same "
    "section, in the same order. The Detailed checklist may add expansion rows "
    "(e.g. the sync/async gating splits), but must not drop or re-order a trigger."
)


def iter_reference(repo_root: Path) -> Iterator[Path]:
    yield repo_root / "sdd" / "CLAUDE-REFERENCE.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_REPO_ROOT,
        help="Repository root (default: the checkout this script lives in).",
    )
    args = parser.parse_args(argv)

    reference = args.repo_root / "sdd" / "CLAUDE-REFERENCE.md"
    violations = collect_violations(reference)
    if not violations:
        print("check_ripple_parity: the two ripple-check presentations are in trigger-parity.")
        return 0

    for v in violations:
        print(f"sdd/CLAUDE-REFERENCE.md:{v.line}: {v.message}", file=sys.stderr)
    print(
        f"\ncheck_ripple_parity: {len(violations)} ripple-check parity violation(s).",
        file=sys.stderr,
    )
    print(_REMEDIATION, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
