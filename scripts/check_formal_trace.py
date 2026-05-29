#!/usr/bin/env python3
"""Mechanical spec ↔ Dafny ↔ test traceability check (ID-206).

`000-process.md` Rule 2 ("no spec without tests") is prose. This script
makes the spec ↔ Dafny ↔ test wiring mechanically checkable by building
a coverage matrix across three sources:

  D — spec IDs carrying a verified Dafny postcondition, read from
      ``// @spec <ID>`` tags in ``sdd/formal/*.dfy``.
  T — spec IDs cited by a conformance ``@pytest.mark.spec`` marker under
      ``tests/backends/conformance/``. A ``*.mark.spec(...)`` call counts
      only in a position pytest actually treats as a marker — a decorator
      on a test function/class, a ``pytest.param(marks=...)`` entry, or a
      ``pytestmark`` assignment. A bare ``pytest.mark.spec(...)``
      expression that decorates nothing is dead code and is ignored.
  S — spec IDs declared as a section in ``sdd/specs/`` — either a
      ``##``/``###`` heading (``### BE-014: ...``) or a row of a
      requirement table (a table whose first column header is ``ID`` —
      the form spec 022 uses for SAW-001..015). Heading level and
      declaration form are not consistent across spec files.

Three failure modes (per ID-206):

  F1  a Dafny-tagged spec ID (in D, declared in S) that no conformance
      marker cites (not in T).
  F2  a conformance marker citing a spec ID absent from S.
  F3  an ``@spec`` tag citing a spec ID absent from S.

Scope — what this check does and does not prove
-----------------------------------------------
The check certifies *traceability* at spec-ID granularity. It is not a
proof of test depth, and should be read with these limits in mind:

  * **ID granularity, not clause granularity.** D, T and S key on spec
    ID. Several distinct ``ensures`` may share one ID (e.g. the many
    postconditions tagged ``BE-014``); one marker citing that ID clears
    F1 for all of them. The check proves every Dafny-cited spec ID is
    cited by at least one conformance marker — not that each individual
    postcondition has its own test.
  * **Citation, not assertion.** T records that a marker naming an ID
    sits on a test; it does not verify the test asserts that clause, or
    that the test is even enabled (a marker on a skipped test still
    counts), or that the cited ID is the *right* one.
  * **D is author-curated.** D is the set of postconditions an author
    chose to tag. Keeping every contract postcondition tagged is a
    review obligation — in the same spirit as the manually-mirrored
    ``MemoryBackend`` / ``MemoryBackendMinimal`` parity already
    documented in ``sdd/formal/README.md``; an untagged ``ensures`` is
    invisible to this check.

Closing these gaps fully would need per-clause sub-IDs and assertion-
level analysis, deliberately out of ID-206's scope. What the check buys
is a mechanical worklist and a regression tripwire on the *citation*
layer, which the spec ↔ Dafny ↔ test chain had none of before.

Landing strategy — checked-in baseline
--------------------------------------
Wiring this check in surfaces every pre-existing spec↔Dafny↔test gap at
once; a hard gate would break the build on day one. ``_BASELINE`` is a
checked-in allow-list of the violations known when the check landed. Two
things are mechanically enforced:

  * a violation NOT in the baseline fails the check — a regression, and
  * a baseline entry that no longer matches a live violation fails the
    check — a stale entry, i.e. the gap was closed.

The second rule makes the baseline self-prune: closing a gap forces its
entry out in the same change. Baseline *growth* is NOT blocked
mechanically — a new violation can be parked by editing ``_BASELINE``.
That edit is visible in review and is the point where a human must
refuse new debt; the check cannot make that judgement. The printed
violation list is the worklist for the (T)-backfill items (ID-184 /
ID-185 / ID-188).

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

# Declaration of a spec section: a Markdown heading at any level, or a
# row of a requirement table — a table whose first column header is
# ``ID`` (the form spec 022 uses for SAW-001..015). A table-shaped line
# outside such a table does not declare a spec.
#
# In a heading the ID may carry a parenthetical before the colon, as in
# ``## EW-001 (was WR-014): ...`` (spec 046's renamed sections); the
# optional ``(...)`` group keeps those declarations in S.
_HEADING_RE = re.compile(rf"^#+[ \t]+({_SPEC_ID})(?: \([^)]*\))?:")
_TABLE_ROW_RE = re.compile(rf"^\|[ \t]*({_SPEC_ID})[ \t]*\|")
_ID_TABLE_HEADER_RE = re.compile(r"^\|[ \t]*ID[ \t]*\|", re.IGNORECASE)

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
        # WR-008 — WR008FieldMapping (BackendContract.dfy) pins the pure
        #   FileInfo→WriteResult field map. WR-008 is Store.head(), a
        #   Store-layer composition over get_file_info (spec 045 § WR-008),
        #   not a backend operation the conformance suite drives; head()
        #   field-mapping coverage lives in
        #   tests/test_store.py::TestStoreHead. The conformance dir this gate
        #   scans has no head() test by design, so this F1 is structural,
        #   not a backfill gap.
        (KIND_UNTESTED, "WR-008"),
        # WR-010 — the USER_METADATA strict gate. Per spec 045 § WR-010 and
        #   ADR-0026 the gate is enforced once at the Store layer
        #   (_store.py / _async_store.py via capabilities.require) BEFORE
        #   delegating; a non-declaring backend never receives a non-empty
        #   metadata mapping, so backends deliberately do not re-check it and
        #   a backend-conformance assertion would be architecturally wrong.
        #   Store-layer coverage lives in
        #   tests/test_store.py::TestMetadataGate. Structural F1, not a
        #   backfill gap.
        (KIND_UNTESTED, "WR-010"),
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


def _is_spec_call(node: ast.AST) -> bool:
    """True if ``node`` is a ``*.mark.spec(...)`` call (e.g. ``pytest.mark.spec``)."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "spec"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "mark"
    )


def _is_pytestmark_name(node: ast.AST) -> bool:
    """True if ``node`` is the ``pytestmark`` name (a module/class marker list)."""
    return isinstance(node, ast.Name) and node.id == "pytestmark"


def _marker_anchors(node: ast.AST) -> list[ast.expr]:
    """Return the expressions where ``node`` may legitimately apply markers.

    The four positions pytest treats as marker applications: a decorator
    on a function/class, a ``marks=`` value, and a ``pytestmark``
    assignment (plain or annotated). Anything else is not a marker site.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return list(node.decorator_list)
    if isinstance(node, ast.Call):
        return [kw.value for kw in node.keywords if kw.arg == "marks"]
    if isinstance(node, ast.Assign) and any(_is_pytestmark_name(t) for t in node.targets):
        return [node.value]
    if isinstance(node, ast.AnnAssign) and node.value is not None and _is_pytestmark_name(node.target):
        return [node.value]
    return []


def _iter_spec_marker_args(tree: ast.Module) -> list[tuple[int, str]]:
    """Return ``(lineno, id)`` for every *applied* conformance ``spec`` marker.

    A ``*.mark.spec("ID")`` call counts only when it sits in a position
    pytest actually treats as a marker (see ``_marker_anchors``). A bare
    ``pytest.mark.spec(...)`` expression that decorates nothing is dead
    code and is ignored — otherwise a single dead line could silence an
    F1 without adding any test.
    """
    # First pass: collect spec calls that are anchored to a real marker
    # position. ``id()`` keys de-duplicate a call reached via two anchors
    # (e.g. a parametrize decorator that itself contains pytest.param).
    anchored: set[int] = set()
    for node in ast.walk(tree):
        for anchor in _marker_anchors(node):
            for sub in ast.walk(anchor):
                if _is_spec_call(sub):
                    anchored.add(id(sub))

    # Second pass: emit the string args of every anchored spec call.
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_spec_call(node) and id(node) in anchored:
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

    A section is declared by either:

      * a Markdown heading at any level (``### BE-014: ...``), or
      * a row of a *requirement table* — a Markdown table whose first
        column header is ``ID`` (the form spec 022 uses for
        SAW-001..015).

    A table-shaped line outside a requirement table (a summary,
    cross-reference or changelog table) does not declare a spec, so a
    stray ``| BE-099 | ... |`` row cannot legitimise a bogus citation.
    """
    declared: set[str] = set()
    for path in sorted(specs_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:  # pragma: no cover - defensive
            sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
            continue
        in_requirement_table = False
        for line in text.splitlines():
            heading = _HEADING_RE.match(line)
            if heading is not None:
                declared.add(heading.group(1))
                in_requirement_table = False
                continue
            if not line.startswith("|"):
                # Any non-table line ends the current table.
                in_requirement_table = False
                continue
            if _ID_TABLE_HEADER_RE.match(line):
                in_requirement_table = True
                continue
            if in_requirement_table:
                row = _TABLE_ROW_RE.match(line)
                if row is not None:
                    declared.add(row.group(1))
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
    KIND_UNTESTED: "Dafny-tagged spec ID with no conformance marker (F1)",
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
