#!/usr/bin/env python3
"""Gate: a generated sdd index table renders what its kind declares.

``docs-src/_path_rules.yml`` declares each SDD kind's index shape with two
optional flags: ``status:`` adds a constant status column, ``dated:`` adds a
"Date (as of)" column filled from each document's ``**Date:**`` header. Both
flags reach the published table through code that cannot see whether the
inputs are there, so both fail silently:

R1 -- **Every document of a dated kind carries a parseable header date.**
     A research doc with no ``**Date:**`` header renders ``—`` and sorts to
     the bottom of a table whose own preamble says "listed newest first".
     `mkdocs build --strict` is content with the em dash, and the pytest
     control that reads the live tree
     (``tests/scripts/test_render_sdd_indexes.py``) cannot run on the diff
     that breaks this: ``ci.yml``'s ``CODE_PAT`` has no ``^sdd/``, so a PR
     adding only ``sdd/research/research-foo.md`` gets ``code=false`` and
     skips every test job. That is the BK-333 wiring trap, and the reason
     this script is wired into ``docs-gate`` as well as ``lint`` -- the same
     reason ``check-ripple-parity``, ``check-traces``,
     ``check-changelog-unreleased`` and ``gen-gate-inventory-check`` are.

R2 -- **Each kind's ``_index.tmpl`` header declares as many columns as
     ``render._index_row`` emits cells**, i.e. ``2 + bool(status) +
     bool(dated)``. Python-Markdown's tables extension drops a surplus row
     cell without a word, so flipping ``dated: true`` on a kind whose
     template still has a two-column header publishes the table with no date
     column at all, green gates throughout.

Both rules enumerate from ``_path_rules.yml`` via ``scan.SDD_KINDS`` (Rule 3:
derived, not maintained beside), and every failure names the offending file
(Rule 2). Authority is the declaration: ``_path_rules.yml`` says what the kind
is, and the documents and template must supply it.

Bounds -- what this does not catch
==================================

* **Header cells are counted, not matched.** R2 compares arity only, so a
  three-column header whose third column is labelled anything at all
  satisfies it. A header that says ``Status`` over the date column passes.
* **R1 checks presence and shape, never correctness.** A parseable
  ``**Date:** 2019-01-01`` on a document written yesterday is a fact this
  gate has no way to dispute.
* **Only kinds declared in ``_path_rules.yml`` are seen.** A kind rendered
  by some other path, or a template with no ``{{ ..._rows }}`` placeholder,
  is outside the enumeration.
* **R1 enumerates via ``_scan_kind``, which does not consult per-file
  ``<!-- doc: -->`` markers.** A ``repo-only`` document matching a dated
  kind's glob is still required to carry a header date, because the index
  and nav claim it regardless of its marker -- the BK-362 gap. That is the
  existing behaviour of the enumeration, not a rule this gate adds.
* **The separator row is not checked.** A header/separator arity mismatch is
  a Markdown defect this gate leaves to the build.

Drift-gate::

    kind:       rule
    rule:       every generated sdd index table has the columns its kind declares,
                  and every document of a dated kind carries a header date
    domain:     explanation <-> realization
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from docs.scan import SDD_KINDS, scan_all_sdd  # noqa: E402

DOCS_SRC = ROOT / "docs-src"


def _expected_columns(kind) -> int:  # noqa: ANN001 — SddKind, imported at runtime only
    """Cell count ``render._index_row`` emits: first + link, plus each flag."""
    return 2 + bool(kind.status) + bool(kind.dated)


def _header_columns(tmpl: Path) -> int | None:
    """Column count of the template's table header, or None if it has no table."""
    for line in tmpl.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            return len(stripped.strip("|").split("|"))
    return None


def check(repo_root: Path | None = None) -> list[str]:
    """Return one message per violation; empty when both rules hold.

    *repo_root* is resolved at call time, not bound as a default, so a test
    can point the gate at a seeded tree.
    """
    repo_root = ROOT if repo_root is None else repo_root
    errors: list[str] = []
    entries_by_kind = scan_all_sdd(repo_root)

    for kind in SDD_KINDS:
        # R1: every document of a dated kind has a parseable header date.
        if kind.dated:
            for entry in entries_by_kind.get(kind.slug, []):
                if entry.date is None:
                    rel = entry.source.relative_to(repo_root)
                    errors.append(
                        f"R1 {rel}: no parseable '**Date:** YYYY-MM-DD' in the header ({kind.slug} is a dated kind)"
                    )

        # R2: the template header declares as many columns as a row emits.
        tmpl = repo_root / "docs-src" / "explanation" / "design" / kind.slug / "_index.tmpl"
        if not tmpl.is_file():
            errors.append(f"R2 {tmpl.relative_to(repo_root)}: missing index template for kind {kind.slug!r}")
            continue
        found = _header_columns(tmpl)
        expected = _expected_columns(kind)
        if found is None:
            errors.append(f"R2 {tmpl.relative_to(repo_root)}: no table header row found")
        elif found != expected:
            flags = ", ".join(f for f, on in (("status", kind.status), ("dated", kind.dated)) if on) or "none"
            errors.append(
                f"R2 {tmpl.relative_to(repo_root)}: header has {found} column(s), "
                f"rows emit {expected} (flags: {flags}) — the surplus cell is dropped silently"
            )

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("sdd index check failed:")
        for e in errors:
            print(f"  {e}")
        return 1
    dated = [k.slug for k in SDD_KINDS if k.dated]
    print(
        f"check_sdd_index: {len(SDD_KINDS)} kind(s) match their index template; "
        f"dated kind(s) fully dated: {dated or 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
