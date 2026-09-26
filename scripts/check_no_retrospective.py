#!/usr/bin/env python3
"""BK-378: no retrospective sits on the deliverable surface (RFC-0015 D1).

A *retrospective* is text whose subject is an earlier version of the artifact it
sits in: ``Retrospective:``, *until round N*, *an earlier revision of this
sentence*, *corrected in round N*. RFC-0015 D1's rule is that a durable artifact
carries the current claim and its derivation, never the history of getting there
— the history lives in the PR, and what the repo keeps of it is derived from the
PR once, after the loop ends, by ``scripts/ship_report.py``.

**The unit is the file and the boundary is what the text is about, not where it
sits.** Text whose subject is the repository or the work is content, however
historical: a register entry recording that a collision happened twice in this
repo is about the repo, not about a previous draft of the entry, and stays. That
distinction is what the phrase set below encodes, and it is what lets this check
run over whole files without a paragraph parser.

The surface
-----------
``SURFACE`` below. It is the operational spelling of D1's "code, tests, specs,
docs, ``CHANGELOG.md``, the migration guide, and ``sdd/BACKLOG*.md`` in full" —
the migration guide is ``docs-src/reference/migration.md`` and needs no row of
its own. ``examples/`` is included because it is a surface users read.
``sdd/backlog/*.md`` is included because ADR-0040 moves item bodies there
verbatim: without it, "``sdd/BACKLOG*.md`` in full" would shrink by every body
the migration moves. Those files pass here because the text passed in
``BACKLOG.md``.

**What is off the surface, stated as the complement rather than a sample**,
because a partial exclusion list reads as a complete one. Everything not matched
by ``SURFACE`` is unscanned; the trees that a reader would expect to be scanned,
and their reasons, are:

* ``sdd/traces/`` is *the record*, which is where D1 sends the round-by-round
  account. At the time of writing it carried 143 matching lines across 44 files
  (the phrase set below over ``sdd/traces/*.yml``), every one of them correctly
  placed.
* ``sdd/rfcs/``, ``sdd/research/`` and ``sdd/audits/`` are records too, and
  RFC-0015 in particular *defines* the phrase set, so including it would fail
  this check on the document that specifies it.
* ``sdd/adrs/`` is unscanned, and this is the exclusion most worth arguing:
  an accepted ADR is never edited either way
  ([`000-process.md` Rule 4](../sdd/000-process.md#rules)), so a hit there could
  not be acted on without superseding the record. It carried no hits when this
  was built.
* **The top-level ``sdd/*.md`` authority docs** — ``DRIFT-RULES.md``,
  ``CONTENT-RULES.md``, ``AUTHORING.md``, ``TESTING.md`` and their siblings —
  are unscanned, and nothing about D1 argues they should be. They are the
  deliverable in every sense; they are out only because § References' glob named
  ``sdd/specs/*.md`` and ``sdd/BACKLOG*.md`` and stopped there, and widening the
  surface would re-base the figure the RFC states. A retrospective in one of
  them is a reviewer's to catch, like any other the phrase set does not reach.
* **The repo-root dual-classified pages** — ``README.md``, ``FEATURES.md``,
  ``CONTRIBUTING.md`` — likewise, for the same reason. Note that
  ``check_no_tracker_refs.py`` answers a neighbouring "surface users read"
  question and *does* include them, so the two gates draw that line differently
  and on purpose: its subject is what reaches users, this one's is what D1's
  glob names.
* ``scripts/`` and ``.claude/`` are not on the surface D1 names.

Self-exemption
--------------
``_EXEMPT`` holds two paths, and only one of them is forced.

**The guard is forced.** ``tests/scripts/test_check_no_retrospective.py``
matches ``tests/**/*.py`` and so sits *inside* the surface, and it cannot test a
phrase matcher without spelling the phrases. That is the same shape
``gen_gate_inventory.py`` handles for its own ``Drift-gate::`` header, and for
the same reason: a checker that reads its own definition of what to catch
reports itself.

**This file's own entry is forward cover, not forced**, and saying otherwise
invites the reader to conclude ``scripts/`` is scanned, which § What is off the
surface denies. ``SURFACE`` has no ``scripts/`` glob, so ``iter_surface_files``
never enumerates this file and the entry changes nothing today. It is kept
against a future widening rather than deleted, because a surface that gained
``scripts/`` would otherwise fail on the file defining the phrases.

Bounds (DRIFT-RULES Rule 7)
---------------------------
* **It matches phrases, not a diary written in other words, and the residue is
  not small.** A retrospective that avoids the phrase set is a reviewer's to
  catch, and both halves of that were demonstrated while this gate was built:
  the first run reported 14 lines, a hand read of the same files found more the
  set cannot reach, and a later review round found more again in a file the
  first two passes had already edited. The misses share a stem the set requires
  the wrong suffix for — ``an earlier revision of this`` does not match *an
  earlier revision attributed*, and nothing matches *this clause used to carry*.
  **No count of the residue is given here**, deliberately: every count written
  during this gate's construction was an under-derivation within one round, and
  a total a reader cannot check is worth less than the rule. Measure it by
  widening the pattern and reading the hits; the shapes are pinned by
  ``TestStatedBound`` in the guard.
* **It is line-oriented**, so a phrase split across a line break is missed. The
  phrase set was authored against this repo's wrapped prose, where the tested
  phrases are short enough to survive wrapping, but nothing enforces that.
* **It is case-sensitive**, verbatim as RFC-0015 § References spells it:
  ``Retrospective`` and ``Round \\d`` are capitalised, ``annotated after`` is
  listed in both cases because both occur. A lower-case ``retrospective:`` mid
  sentence is not matched.
* **It cannot tell a retrospective from a quotation of one.** A file quoting the
  phrase set to explain it is a hit; that is why the two files that must quote it
  are exempt, and why ``sdd/rfcs/`` is off the surface.

Run with::

    hatch run check-no-retrospective
    hatch run lint                  # bundled
    hatch run docs-gate             # bundled; the surface spans sdd/ and
                                    # docs-src/, which a CODE_PAT-gated `lint`
                                    # skips
    python scripts/check_no_retrospective.py

Exit codes: ``0`` clean, ``1`` one or more hits, each printed as
``<path>:<line>: <text>`` (DRIFT-RULES Rule 2 — name the element, do not merely
fail).

Drift-gate::

    kind:       rule
    rule: no file on the deliverable surface — code, tests, examples, specs, docs, CHANGELOG.md,
        sdd/BACKLOG*.md and its dossiers under sdd/backlog/ — carries a retrospective, meaning text
        whose subject is an earlier version of the artifact it sits in, as RFC-0015's phrase set spells it
    domain:     process
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The deliverable surface, per RFC-0015 D1 and the glob its § References pins.
# `examples/` is the one addition: it is a surface users read, and D1's "code"
# reaches it. Order is the order hits are reported in.
SURFACE: tuple[str, ...] = (
    "CHANGELOG.md",
    "sdd/specs/*.md",
    "sdd/BACKLOG*.md",
    "sdd/backlog/*.md",
    "src/**/*.py",
    "tests/**/*.py",
    "examples/**/*.py",
    "examples/**/*.md",
    "examples/**/*.ipynb",
    "docs-src/**/*.md",
)

# Verbatim from RFC-0015 § References. Do not "tidy" it: the RFC states the
# figures it derives with this exact alternation, so a change here silently
# re-bases every count that cites it. Case-sensitive, as written there.
PHRASES = (
    r"Retrospective|Annotated after|annotated after|until round \d|"
    r"an earlier revision of this|this (line|sentence|figure|step) (said|read|was)|"
    r"corrected in round|Round \d (caught|found|corrected)"
)

_RX = re.compile(PHRASES)

# The guard is forced; this file's own entry is forward cover and is inert
# while SURFACE has no scripts/ glob. See the module docstring, which says which
# is which. Repo-relative, POSIX spelling.
_EXEMPT = frozenset(
    {
        "scripts/check_no_retrospective.py",
        "tests/scripts/test_check_no_retrospective.py",
    }
)


class Hit:
    """One matching line, located well enough to open (Rule 2)."""

    __slots__ = ("path", "line", "text")

    def __init__(self, path: str, line: int, text: str) -> None:
        self.path, self.line, self.text = path, line, text

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.text}"


def iter_surface_files(root: Path = ROOT, surface: tuple[str, ...] = SURFACE) -> list[Path]:
    """Every file on the deliverable surface, de-duplicated, in glob order.

    ``sdd/BACKLOG*.md`` and ``CHANGELOG.md`` can only match once each, but a
    future overlapping pair of globs would otherwise report a file twice.
    """
    seen: dict[Path, None] = {}
    for pattern in surface:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                seen.setdefault(path, None)
    return list(seen)


def scan(root: Path = ROOT, surface: tuple[str, ...] = SURFACE, exempt: frozenset[str] = _EXEMPT) -> list[Hit]:
    """Return every retrospective hit on the surface, in file then line order."""
    hits: list[Hit] = []
    for path in iter_surface_files(root, surface):
        rel = path.relative_to(root).as_posix()
        if rel in exempt:
            continue
        for number, text in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if _RX.search(text):
                hits.append(Hit(rel, number, text.strip()))
    return hits


def scanned_count(root: Path = ROOT, surface: tuple[str, ...] = SURFACE, exempt: frozenset[str] = _EXEMPT) -> int:
    """How many files ``scan`` actually reads — enumerated minus exempt.

    Separate from ``len(iter_surface_files())``, which counts the exempt files
    too: a gate reporting a figure larger than what it looked at is the defect
    this PR's own principle 9 is about.
    """
    return sum(1 for path in iter_surface_files(root, surface) if path.relative_to(root).as_posix() not in exempt)


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.root or root

    hits = scan(root=root)
    if not hits:
        print(f"No retrospectives on the deliverable surface ({scanned_count(root)} files scanned).")
        return 0

    files = len({hit.path for hit in hits})
    print(f"Found {len(hits)} retrospective line(s) in {files} file(s):", file=sys.stderr)
    for hit in hits:
        print(f"  {hit.format()}", file=sys.stderr)
    print(
        "\nRFC-0015 D1: a durable artifact carries the current claim and its derivation, "
        "never the history of getting there. Keep the claim, delete the clause whose "
        "subject is an earlier version of the text.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
