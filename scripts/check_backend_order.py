"""Check that every backend enumeration lists backends in the canonical order.

``CONTRIBUTING.md`` (§ Adding a New Backend) pins one order for every
place the backends are enumerated::

    local (Local, Memory)
      -> cloud (S3, S3-PyArrow, Azure, Graph)
        -> SFTP / SSH
          -> special-purpose (HTTP, SQLBlob, SQLQuery)

The convention was previously guarded by a hand-run ``git grep``. That
failed twice in review, for two independent reasons, and both are why
this script exists:

* **Sentinel leak.** The grep keyed on ``SQLQuery``. Any enumeration
  that abbreviates -- ``docs-src/context7.json`` wrote plain ``SQL`` --
  is invisible to the command that is supposed to guarantee it cannot
  hide.
* **Pathspec leak.** The grep scanned ``README.md docs-src/``. Two
  full-membership enumerations live outside that path (repo-root
  ``context7.json``, ``packaging/conda-forge/recipe.yaml``).

A grep is a heuristic with a blast radius the reader cannot see. This
gate reads the enumerations instead.

What is checked
===============

**Order, not membership.** Membership is intent-dependent and cannot be
mechanised without false positives:

* ``docs-src/reference/api/backends/index.md`` deliberately splits the
  sync table from the native-async table, so neither lists all ten.
* The README's *How it compares* row deliberately abridges (no
  S3-PyArrow; ``SQL`` collapses the two SQL backends).

Requiring "all ten, always" would flag both. So this gate proves the one
thing that IS mechanically decidable -- that the backends an enumeration
*does* name appear in canonical order -- and leaves "is this list
complete?" to review. An enumeration may name any subset; it may not
name them out of order.

What counts as an enumeration
=============================

Two shapes, both requiring ``_MIN_BACKENDS`` distinct backends before
the gate engages (below that a line is prose, not a list):

* **Inline** -- one line naming several backends. Covers prose lists,
  Markdown table *header* rows (i.e. column-wise tables), JSON strings
  in ``context7.json``, and the recipe's ``about.description``.
* **Table rows** -- the leading cell of each row in one Markdown table,
  read top to bottom. Covers row-wise tables. Consecutive repeats of a
  backend collapse to one entry, so ``Azure (HNS)`` / ``Azure
  (non-HNS)`` and SFTP's three strategy rows do not read as disorder.

Exit codes
==========

* ``0`` -- every enumeration is in canonical order.
* ``1`` -- one or more enumerations are out of order (printed to stderr
  with ``file:line`` and the offending sequence).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

# --------------------------------------------------------------------------- #
# The canonical order
# --------------------------------------------------------------------------- #

# Ordered: the taxonomy CONTRIBUTING pins. Index = rank.
#
# Aliases are the surface spellings a backend actually appears under.
# They are matched case-sensitively: lowercase "local files" and "http"
# are prose, not enumeration entries, and matching them would turn every
# sentence into a candidate list. Longest alias wins, so "S3-PyArrow"
# cannot be shredded into "S3" + junk.
_BACKENDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Local", ("LocalBackend", "Local")),
    ("Memory", ("MemoryBackend", "Memory")),
    # S3-PyArrow before S3 matters only for readability here; the
    # longest-alias-wins rule in _ALIAS_RE is what actually disambiguates.
    ("S3", ("S3Backend", "S3")),
    (
        "S3-PyArrow",
        ("S3PyArrowBackend", "S3-PyArrow", "S3PyArrow", "S3 (PyArrow)"),
    ),
    ("Azure", ("AzureBackend", "Azure")),
    ("Graph", ("GraphBackend", "Microsoft Graph", "OneDrive", "Graph")),
    ("SFTP", ("SFTPBackend", "SFTP")),
    ("HTTP", ("ReadOnlyHttpBackend", "ReadOnlyHTTP", "ReadOnlyHttp", "HTTP", "Http")),
    # Bare ``SQL`` is the abbreviation that hid docs-src/context7.json from the
    # grep this gate replaces, so it must resolve to something. It maps to
    # SQLBlob: the two SQL backends are adjacent and last in the canonical
    # order, so for an *order* check either rank answers identically, and a
    # list that abbreviates can no longer slip past. The longer "SQL Blob" /
    # "SQL Query" aliases win where a document spells them out, and the
    # symmetric token boundary keeps both "SQLAlchemy" and "PostgreSQL" from
    # matching at all.
    ("SQLBlob", ("SQLBlobBackend", "SQLBlob", "SQL Blob", "SQL")),
    ("SQLQuery", ("SQLQueryBackend", "SQLQuery", "SQL Query")),
)

_RANK: dict[str, int] = {name: i for i, (name, _) in enumerate(_BACKENDS)}

# alias -> canonical name
_ALIAS_TO_NAME: dict[str, str] = {alias: name for name, aliases in _BACKENDS for alias in aliases}

# Longest alias first so "S3-PyArrow" wins over "S3" and "SQLQueryBackend"
# over "SQLQuery".
#
# The alternation MUST be wrapped in a group: `a|b|c(?!...)` binds the
# lookahead to `c` alone, which let "SQL" match inside "SQLAlchemy" and
# "S3" inside "S3FS".
#
# The boundary is symmetric on purpose. A trailing guard alone stops an
# alias from matching as a *prefix* ("SQLAlchemy") but not as a *suffix*:
# "PostgreSQL", "MySQL" and "NoSQL" all end in a bare "SQL", and every one
# of them named the SQLBlob backend until the leading guard went in. That
# was live in the scanned tree -- concurrency.md's "(PostgreSQL, MySQL)
# SQLBlob and SQLQuery are thread-safe" read as three SQLBlobs -- and it
# passed only because the repeats collapsed and the segment stayed under
# _MIN_BACKENDS. An RDBMS name next to a six-backend list would have
# invented a violation, or hidden one.
_TOKEN_CHARS = r"[A-Za-z0-9_-]"
_ALIAS_RE = re.compile(
    f"(?<!{_TOKEN_CHARS})(?:"
    + "|".join(re.escape(alias) for alias in sorted(_ALIAS_TO_NAME, key=len, reverse=True))
    + f")(?!{_TOKEN_CHARS})"
)

# A segment naming fewer than this many distinct backends is prose (or a
# two-backend comparison), not an enumeration. Six is comfortably above
# the largest incidental co-mention in the docs and comfortably below
# the smallest real enumeration.
_MIN_BACKENDS = 6

# One line can hold several *independent* enumerations, and running them
# together invents disorder that is not there. Three real cases:
#
# * A Markdown comparison row -- each cell is a different product's
#   backend list; ours is only one of them.
# * ``Built-in backends: <sync list>. Native async: <async list>.`` --
#   two lists, each ordered, in one string.
# * ``pick among <list>; Graph (OneDrive) is async-only.`` -- a trailing
#   re-mention of a backend already named.
#
# So a line is cut into segments at cell walls (``|``), clause ends
# (``;``), and sentence ends (a period followed by space), and each
# segment is judged on its own.
_SEGMENT_RE = re.compile(r"\||;|(?<=\.)\s")

# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Every surface that can carry a backend enumeration. The pathspec leak
# this gate exists to close is precisely a scope list that stops at
# docs-src/, so packaging/ and the repo-root metadata are in.
#
# Two surfaces are deliberately absent rather than excluded, and the
# distinction matters if you ever widen this list:
#
# * ``FEATURES.md`` is generated between BEGIN_GENERATED markers and sorts
#   alphabetically by contract. Scanning it would fail the gate against a
#   file no human may hand-edit.
# * ``sdd/research/`` holds point-in-time snapshots that must not be
#   retro-edited to match today's taxonomy.
#
# Neither is reachable from the roots below, so neither needs an exclusion
# today. Adding ``sdd`` to _SCANNED_TREES would change that.
_SCANNED_FILES: tuple[str, ...] = (
    "README.md",
    "CONTRIBUTING.md",
    "context7.json",
    "packaging/conda-forge/recipe.yaml",
)
_SCANNED_TREES: tuple[tuple[str, str], ...] = (
    ("docs-src", "*.md"),
    ("docs-src", "*.json"),
)

# Pruned from inside the scanned trees: docs-src/_data/ holds generated
# graph artefacts, not authored prose.
_EXCLUDED_PARTS: frozenset[str] = frozenset({"_data"})


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    found: tuple[str, ...]
    snippet: str

    def reason(self) -> str:
        canonical = sorted(set(self.found), key=lambda n: _RANK[n])
        return f"found [{', '.join(self.found)}] -- expected [{', '.join(canonical)}]"


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


def backends_in(text: str) -> list[str]:
    """Return the canonical backend names named in *text*, in order.

    Consecutive repeats collapse: a row-wise table with ``Azure (HNS)``
    and ``Azure (non-HNS)`` names Azure once, not twice.
    """
    out: list[str] = []
    for m in _ALIAS_RE.finditer(text):
        name = _ALIAS_TO_NAME[m.group(0)]
        if not out or out[-1] != name:
            out.append(name)
    return out


def is_ordered(names: Iterable[str]) -> bool:
    """True when *names* is non-decreasing in canonical rank."""
    ranks = [_RANK[n] for n in names]
    return all(a <= b for a, b in zip(ranks, ranks[1:], strict=False))


def _distinct(names: Iterable[str]) -> int:
    return len(set(names))


# --------------------------------------------------------------------------- #
# Scanners
# --------------------------------------------------------------------------- #


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _column_sequence(row: str) -> list[str]:
    """The backends a table row names *across* its cells, left to right.

    This is how a column-wise table (``| Capability | Local | Memory | …``)
    is read. Only cells naming exactly one backend count as columns: a cell
    holding a whole list is a list, not a column heading, which is what
    keeps the README's comparison row -- where each cell is a *different
    product's* backends -- from reading as one scrambled enumeration.
    """
    out: list[str] = []
    for cell in _cells(row):
        names = backends_in(cell)
        if len(names) != 1:
            continue
        if not out or out[-1] != names[0]:
            out.append(names[0])
    return out


def _scan_inline(lines: list[str], path: Path) -> list[Violation]:
    """Flag any segment naming >= _MIN_BACKENDS backends out of order.

    A table row is judged twice, because it carries two independent
    enumerations: the sequence of its cells (column-wise tables) and the
    contents of each cell (a list that happens to live in a table).
    """
    out: list[Violation] = []
    for idx, line in enumerate(lines):
        is_row = line.lstrip().startswith("|")

        if is_row:
            column_seq = _column_sequence(line)
            if _distinct(column_seq) >= _MIN_BACKENDS and not is_ordered(column_seq):
                out.append(
                    Violation(
                        path=path,
                        line=idx + 1,
                        found=tuple(column_seq),
                        snippet=line.strip()[:120],
                    )
                )
            segments = [seg for cell in _cells(line) for seg in _SEGMENT_RE.split(cell)]
        else:
            segments = _SEGMENT_RE.split(line)

        for segment in segments:
            found = backends_in(segment)
            if _distinct(found) < _MIN_BACKENDS or is_ordered(found):
                continue
            out.append(
                Violation(
                    path=path,
                    line=idx + 1,
                    found=tuple(found),
                    snippet=segment.strip()[:120],
                )
            )
    return out


def _iter_tables(lines: list[str]) -> Iterator[tuple[int, list[str]]]:
    """Yield (start_line, rows) for each Markdown table's data rows.

    A table is a run of ``|``-leading lines. The header and the
    ``|---|`` separator are dropped; the header is already covered by
    the inline scanner (that is how column-wise tables are checked).
    """
    run: list[str] = []
    start = 0
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("|"):
            if not run:
                start = idx + 1
            run.append(line)
            continue
        if run:
            yield start, run
            run = []
    if run:
        yield start, run


def _leading_cell(row: str) -> str:
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    return cells[0] if cells else ""


def _scan_tables(lines: list[str], path: Path) -> list[Violation]:
    """Flag row-wise tables whose leading cells name backends out of order."""
    out: list[Violation] = []
    for start, rows in _iter_tables(lines):
        # Drop the |---| separator row and anything before it (the header).
        body = rows
        for i, row in enumerate(rows):
            if set(row.strip().strip("|")) <= set("-: |"):
                body = rows[i + 1 :]
                break
        found: list[str] = []
        for row in body:
            names = backends_in(_leading_cell(row))
            if len(names) != 1:
                # A leading cell that names no backend (or several) is
                # not a per-backend row; this is not a row-wise table.
                continue
            if not found or found[-1] != names[0]:
                found.append(names[0])
        if _distinct(found) < _MIN_BACKENDS or is_ordered(found):
            continue
        out.append(
            Violation(
                path=path,
                line=start,
                found=tuple(found),
                snippet="(table rows)",
            )
        )
    return out


def scan_file(path: Path) -> list[Violation]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lines = text.splitlines()
    return _scan_inline(lines, path) + _scan_tables(lines, path)


# --------------------------------------------------------------------------- #
# File enumeration
# --------------------------------------------------------------------------- #


def iter_scanned_files(repo_root: Path = _REPO_ROOT) -> Iterator[Path]:
    for rel in _SCANNED_FILES:
        p = repo_root / rel
        if p.is_file():
            yield p
    for tree, pattern in _SCANNED_TREES:
        root = repo_root / tree
        if not root.is_dir():
            continue
        for p in sorted(root.rglob(pattern)):
            if _EXCLUDED_PARTS & set(p.relative_to(root).parts):
                continue
            yield p


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

_REMEDIATION = (
    "See CONTRIBUTING.md (Adding a New Backend, 'Backend order'). Insert the "
    "backend into its group; do not append it. Order: Local, Memory, S3, "
    "S3-PyArrow, Azure, Graph, SFTP, HTTP, SQLBlob, SQLQuery."
)


def collect_violations(repo_root: Path = _REPO_ROOT) -> list[Violation]:
    out: list[Violation] = []
    for path in iter_scanned_files(repo_root):
        out.extend(scan_file(path))
    out.sort(key=lambda v: (str(v.path), v.line))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_REPO_ROOT,
        help="Repository root (default: the checkout this script lives in).",
    )
    args = parser.parse_args(argv)

    violations = collect_violations(args.repo_root)
    if not violations:
        print("check_backend_order: every backend enumeration is in canonical order.")
        return 0

    for v in violations:
        try:
            rel = v.path.relative_to(args.repo_root)
        except ValueError:
            rel = v.path
        print(f"{rel}:{v.line}: {v.reason()}", file=sys.stderr)
        print(f"    {v.snippet}", file=sys.stderr)
    print(
        f"\ncheck_backend_order: {len(violations)} enumeration(s) out of order.",
        file=sys.stderr,
    )
    print(_REMEDIATION, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
