#!/usr/bin/env python3
"""Mechanical spec ↔ Dafny ↔ test traceability gate (ID-206).

`000-process.md` Rule 2 ("no spec without tests") is prose, and the link
from a verified Dafny postcondition to the conformance test that enforces
it was unchecked. This script turns that link into a CI gate.

It builds a coverage matrix across three sources:

  D — spec IDs carrying a verified Dafny postcondition, read from
      ``// @spec <ID>`` tags in ``sdd/formal/*.dfy``.
  T — spec IDs cited by a conformance ``@pytest.mark.spec`` marker under
      ``tests/backends/conformance/``.
  S — spec IDs declared as a section in ``sdd/specs/`` — either a
      ``##``/``###`` heading (``### BE-014: ...``) or the first cell of a
      requirements table row (``| SAW-001 | ... |``). Both forms occur;
      heading level is not consistent across spec files.

Three failure modes (per ID-206):

  F1  a Dafny-backed clause (in D, declared in S) with no conformance
      test (not in T).
  F2  a conformance test citing a spec ID absent from S.
  F3  an ``@spec`` tag citing a spec ID absent from S.

Landing strategy — checked-in baseline
--------------------------------------
Wiring this gate in surfaces every pre-existing spec↔Dafny↔test gap at
once; a hard gate would break the build on day one. ``_BASELINE`` is a
checked-in allow-list of the violations known when the gate landed. The
gate fails on:

  * any violation NOT in the baseline — a regression (a new untested
    verified clause, a new bad marker), and
  * any baseline entry that no longer matches a live violation — a stale
    entry, i.e. the gap was closed.

So the baseline can only shrink, never grow: closing a gap forces its
baseline entry out in the same PR. The violation list printed below is
the worklist for the (T)-backfill items (ID-184 / ID-185 / ID-188 /
BK-195) — exactly the role ID-206 plays as the keystone of the Formal
Verification wave.

CI enforcement. Exit code 0 = ok; 1 = violations found.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A spec-section ID: an uppercase family (optionally hyphenated, e.g.
# ``SQL-BLOB``) followed by a hyphen-number and an optional split-item
# suffix letter (``WR-001a``). Backlog IDs (``ID-134``) match the same
# shape by construction — that is intentional: a test marker citing a
# backlog ID rather than a spec section is an F2 the gate should surface.
_SPEC_ID = r"[A-Z][A-Z0-9]*(?:-[A-Z]+)*-\d+[a-z]?"
_SPEC_ID_RE = re.compile(_SPEC_ID)

# Declaration of a spec section: a Markdown heading at any level, or the
# first cell of a table row (the form spec 022 uses for SAW-001..015).
_HEADING_RE = re.compile(rf"^#+[ \t]+({_SPEC_ID}):")
_TABLE_ROW_RE = re.compile(rf"^\|[ \t]*({_SPEC_ID})[ \t]*\|")

# A structured Dafny traceability tag: ``// @spec BE-014`` (one or more
# IDs, comma- or space-separated) immediately above an ``ensures``.
_SPEC_TAG_RE = re.compile(r"//[ \t]*@spec\b(.*)")

# Violation kinds. Stable strings — they key the baseline below.
KIND_UNTESTED = "dafny-clause-untested"
KIND_TEST_BAD_ID = "conformance-cites-unknown-spec"
KIND_TAG_BAD_ID = "dafny-tag-unknown-spec"

# ---------------------------------------------------------------------------
# Baseline — known violations at gate-landing time (ID-206).
#
# This list MUST shrink and MUST NOT grow. Each entry is a (kind, spec_id)
# pair. Closing a gap makes its entry stale, which fails the gate until
# the entry is removed in the same PR. Adding a new gap fails the gate
# until the gap is fixed — the baseline is not a place to park new debt.
# ---------------------------------------------------------------------------
_BASELINE: frozenset[tuple[str, str]] = frozenset(
    {
        # -- F1: Dafny-backed clauses with no conformance @pytest.mark.spec marker.
        #
        # CAP-004 — RequireCapability's postconditions model the capability
        #   gate. The conformance suite exercises gating but carries no
        #   CAP-004 marker. Surfaced by ID-206; no dedicated owner yet.
        (KIND_UNTESTED, "CAP-004"),
        # DEPTH-001 — DepthCounting.dfy proves the reference depth algorithm
        #   (BK-140 gap 4). The depth conformance tests are filed under
        #   DEPTH-003 + BE-014, not DEPTH-001. Owner: ID-185.
        (KIND_UNTESTED, "DEPTH-001"),
        # WR-008 — WR008FieldMapping pins the head() FileInfo→WriteResult
        #   mapping. No conformance marker cites WR-008. Surfaced by ID-206.
        (KIND_UNTESTED, "WR-008"),
        # WR-010 — the USER_METADATA strict-gate postcondition on Write. The
        #   conformance suite exercises metadata round-trips (WR-012/013) but
        #   carries no WR-010 marker for the pre-I/O gate. Surfaced by ID-206.
        (KIND_UNTESTED, "WR-010"),
        # -- F2: conformance markers citing an ID with no spec section.
        #
        # ID-134 — TestGetFolderInfoAggregates markers cite the backlog ID
        #   ID-134 (aggregate helpers) rather than a spec section. ID-187's
        #   backlog line pairs ID-134 with BE-017; the marker should migrate
        #   to BE-017 when ID-187 lands.
        (KIND_TEST_BAD_ID, "ID-134"),
    }
)


# ---------------------------------------------------------------------------
# Source D — Dafny @spec tags
# ---------------------------------------------------------------------------


def extract_dafny_specs(formal_dir: Path) -> dict[str, list[str]]:
    """Map each spec ID tagged in ``sdd/formal/*.dfy`` to its tag locations.

    A tag is a ``// @spec <ID>[, <ID>...]`` comment. Tags are comments, so
    they never change what Dafny verifies. Every ``.dfy`` file is scanned;
    the refinement (``MemoryBackend.dfy``) carries no tags today but a
    future tag there would be picked up automatically.
    """
    tags: dict[str, list[str]] = {}
    for path in sorted(formal_dir.glob("*.dfy")):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:  # pragma: no cover - defensive
            sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = _SPEC_TAG_RE.search(line)
            if match is None:
                continue
            for spec_id in _SPEC_ID_RE.findall(match.group(1)):
                tags.setdefault(spec_id, []).append(f"{path}:{lineno}")
    return tags


# ---------------------------------------------------------------------------
# Source T — conformance @pytest.mark.spec markers
# ---------------------------------------------------------------------------


def _iter_spec_marker_args(tree: ast.Module) -> list[tuple[int, str]]:
    """Return ``(lineno, id)`` for every ``*.mark.spec("ID")`` call in a tree.

    Walks all ``Call`` nodes (not just decorators) so markers attached via
    ``pytest.param(..., marks=pytest.mark.spec(...))`` are caught too.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match X.mark.spec(...) — Attribute(attr="spec") over Attribute(attr="mark").
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "spec"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "mark"
        ):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.append((node.lineno, arg.value.strip()))
    return found


def extract_conformance_specs(conformance_dir: Path) -> dict[str, list[str]]:
    """Map each spec ID cited by a conformance marker to its citation sites."""
    cited: dict[str, list[str]] = {}
    for path in sorted(conformance_dir.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:  # pragma: no cover - defensive
            sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:  # pragma: no cover - defensive
            sys.stderr.write(f"Skipping {path}: SyntaxError\n")
            continue
        for lineno, spec_id in _iter_spec_marker_args(tree):
            cited.setdefault(spec_id, []).append(f"{path}:{lineno}")
    return cited


# ---------------------------------------------------------------------------
# Source S — spec sections declared in sdd/specs/
# ---------------------------------------------------------------------------


def extract_declared_specs(specs_dir: Path) -> set[str]:
    """Return every spec ID declared as a section in ``sdd/specs/``.

    A section is declared by a Markdown heading (``### BE-014: ...`` — any
    level) or by the first cell of a requirements-table row
    (``| SAW-001 | ... |``). Both forms are in active use; the heading
    level is not consistent across spec files.
    """
    declared: set[str] = set()
    for path in sorted(specs_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:  # pragma: no cover - defensive
            sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
            continue
        for line in text.splitlines():
            for pattern in (_HEADING_RE, _TABLE_ROW_RE):
                match = pattern.match(line)
                if match is not None:
                    declared.add(match.group(1))
    return declared


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------


def compute_violations(
    dafny: dict[str, list[str]],
    conformance: dict[str, list[str]],
    declared: set[str],
) -> list[tuple[str, str]]:
    """Return the sorted list of ``(kind, spec_id)`` violations.

    F1 — a Dafny-backed clause that *is* a declared spec but has no
         conformance marker. (Tags citing a non-spec ID are F3, not F1,
         so the two never double-count the same ID.)
    F2 — a conformance marker citing an ID with no spec section.
    F3 — an ``@spec`` tag citing an ID with no spec section.
    """
    violations: set[tuple[str, str]] = set()
    for spec_id in dafny:
        if spec_id not in declared:
            violations.add((KIND_TAG_BAD_ID, spec_id))
        elif spec_id not in conformance:
            violations.add((KIND_UNTESTED, spec_id))
    for spec_id in conformance:
        if spec_id not in declared:
            violations.add((KIND_TEST_BAD_ID, spec_id))
    return sorted(violations)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_KIND_LABEL = {
    KIND_UNTESTED: "Dafny-backed clause with no conformance test (F1)",
    KIND_TEST_BAD_ID: "conformance marker cites an unknown spec ID (F2)",
    KIND_TAG_BAD_ID: "@spec tag cites an unknown spec ID (F3)",
}


def _print_matrix(
    dafny: dict[str, list[str]],
    conformance: dict[str, list[str]],
    declared: set[str],
) -> None:
    """Print the spec↔Dafny↔test coverage matrix for the Dafny-backed clauses."""
    print("spec <-> Dafny <-> test traceability matrix (ID-206)")
    print(f"  declared spec sections : {len(declared)}")
    print(f"  Dafny-backed clauses   : {len(dafny)}")
    print(f"  conformance-cited IDs  : {len(conformance)}")
    print()
    print("Dafny-backed clauses (D) and their conformance status:")
    for spec_id in sorted(dafny):
        if spec_id not in declared:
            status = "NO SPEC SECTION"
        elif spec_id in conformance:
            status = "tested"
        else:
            status = "UNTESTED"
        print(f"  {spec_id:<12} {status}")
    print()


def _print_violations(
    violations: list[tuple[str, str]],
    dafny: dict[str, list[str]],
    conformance: dict[str, list[str]],
) -> None:
    """Print each violation grouped by kind, with source locations."""
    for kind in (KIND_UNTESTED, KIND_TEST_BAD_ID, KIND_TAG_BAD_ID):
        rows = [v for v in violations if v[0] == kind]
        if not rows:
            continue
        print(f"{_KIND_LABEL[kind]}:")
        for _, spec_id in rows:
            locations = dafny.get(spec_id, []) if kind != KIND_TEST_BAD_ID else conformance.get(spec_id, [])
            shown = ", ".join(locations[:3]) + (" ..." if len(locations) > 3 else "")
            print(f"  {spec_id}: {shown}")
        print()


def main(
    formal_dir: Path | None = None,
    conformance_dir: Path | None = None,
    specs_dir: Path | None = None,
    baseline: frozenset[tuple[str, str]] | None = None,
) -> int:
    formal_dir = formal_dir or ROOT / "sdd" / "formal"
    conformance_dir = conformance_dir or ROOT / "tests" / "backends" / "conformance"
    specs_dir = specs_dir or ROOT / "sdd" / "specs"
    if baseline is None:
        baseline = _BASELINE

    dafny = extract_dafny_specs(formal_dir)
    conformance = extract_conformance_specs(conformance_dir)
    declared = extract_declared_specs(specs_dir)
    violations = compute_violations(dafny, conformance, declared)

    _print_matrix(dafny, conformance, declared)
    _print_violations(violations, dafny, conformance)

    violation_set = set(violations)
    new = sorted(violation_set - baseline)
    stale = sorted(baseline - violation_set)

    if new:
        print(f"FAIL: {len(new)} new traceability violation(s) not in the baseline:")
        for kind, spec_id in new:
            print(f"  [{kind}] {spec_id}")
        print("\nFix the gap, or — only if it is genuinely pre-existing debt —")
        print("add it to _BASELINE in scripts/check_formal_trace.py with a reason.")
    if stale:
        print(f"FAIL: {len(stale)} stale baseline entry/ies (the gap was closed):")
        for kind, spec_id in stale:
            print(f"  [{kind}] {spec_id}")
        print("\nRemove these from _BASELINE in scripts/check_formal_trace.py —")
        print("the baseline must shrink as gaps close, never carry dead weight.")
    if new or stale:
        return 1

    if violations:
        print(f"OK: {len(violations)} known traceability gap(s), all baselined (see _BASELINE).")
    else:
        print("OK: spec <-> Dafny <-> test traceability is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
