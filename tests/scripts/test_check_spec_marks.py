"""Unit tests for scripts/check_spec_marks.py.

Exercises the BK-251 spec-mark gate:

S — spec-section declaration extraction (headings + requirement tables),
    with per-ID locations so duplicate declarations are detectable.
T — ``@pytest.mark.spec`` marker extraction (AST) across the whole
    ``tests/`` tree, not just conformance.

The three failure modes and the shrink-only baseline / allowlist
mechanism in ``main()``:

  drift  — a shipped (declared, non-allowlisted) spec ID with no mark.
  stale  — a ``spec`` marker citing an ID no spec declares.
  dup    — a spec ID declared more than once in the spec tree.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_spec_marks.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_spec_marks", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_spec_marks", module)
    spec.loader.exec_module(module)
    return module


_mod = _load_module()
extract_declared_specs = _mod.extract_declared_specs
extract_test_specs = _mod.extract_test_specs
is_allowlisted = _mod.is_allowlisted
compute_violations = _mod.compute_violations
main = _mod.main
KIND_DRIFT = _mod.KIND_DRIFT
KIND_STALE = _mod.KIND_STALE
KIND_DUPLICATE = _mod.KIND_DUPLICATE


# ---------------------------------------------------------------------------
# Source S — declared spec sections (with locations for duplicate detection)
# ---------------------------------------------------------------------------


class TestExtractDeclaredSpecs:
    def test_heading_declaration(self, tmp_path: Path) -> None:
        (tmp_path / "003.md").write_text("### BE-014: list_files()\n", encoding="utf-8")
        declared = extract_declared_specs(tmp_path)
        assert set(declared) == {"BE-014"}
        assert declared["BE-014"][0].endswith("003.md:1")

    def test_level_two_heading(self, tmp_path: Path) -> None:
        # Heading level is not consistent across spec files (spec 045 uses ##).
        (tmp_path / "045.md").write_text("## WR-013: User Metadata Round-Trip\n", encoding="utf-8")
        assert set(extract_declared_specs(tmp_path)) == {"WR-013"}

    def test_heading_with_parenthetical_before_colon(self, tmp_path: Path) -> None:
        (tmp_path / "046.md").write_text("## EW-001 (was WR-014): write_with_hash Returns Digest\n", encoding="utf-8")
        assert set(extract_declared_specs(tmp_path)) == {"EW-001"}

    def test_requirement_table_row(self, tmp_path: Path) -> None:
        (tmp_path / "022.md").write_text(
            "| ID | Requirement | Status |\n|----|----|----|\n| SAW-004 | no partial file | Done |\n",
            encoding="utf-8",
        )
        assert set(extract_declared_specs(tmp_path)) == {"SAW-004"}

    def test_multi_word_family_prefix(self, tmp_path: Path) -> None:
        (tmp_path / "040.md").write_text("### SQL-BLOB-003: capabilities\n", encoding="utf-8")
        assert set(extract_declared_specs(tmp_path)) == {"SQL-BLOB-003"}

    def test_table_row_outside_requirement_table_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text("| Spec | Status |\n|----|----|\n| BE-099 | planned |\n", encoding="utf-8")
        assert extract_declared_specs(tmp_path) == {}

    def test_inline_reference_is_not_a_declaration(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text("Some prose that mentions BE-021 in passing.\n", encoding="utf-8")
        assert extract_declared_specs(tmp_path) == {}

    def test_duplicate_id_records_both_locations(self, tmp_path: Path) -> None:
        # The STORE-015 collision shape: two headings, one ID.
        (tmp_path / "001.md").write_text("### STORE-015: native_path()\n\n### STORE-015: glob()\n", encoding="utf-8")
        declared = extract_declared_specs(tmp_path)
        assert len(declared["STORE-015"]) == 2


# ---------------------------------------------------------------------------
# Source T — @pytest.mark.spec markers across the whole tests/ tree
# ---------------------------------------------------------------------------


class TestExtractTestSpecs:
    def test_decorator_marker_detected(self, tmp_path: Path) -> None:
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\n\n@pytest.mark.spec("BE-014")\ndef test_x():\n    assert True\n',
            encoding="utf-8",
        )
        cited = extract_test_specs(tmp_path)
        assert set(cited) == {"BE-014"}
        assert cited["BE-014"][0].endswith("test_a.py:4")

    def test_marker_inside_pytest_param_marks(self, tmp_path: Path) -> None:
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\nP = pytest.param("x", marks=pytest.mark.spec("SAW-004"))\n',
            encoding="utf-8",
        )
        assert set(extract_test_specs(tmp_path)) == {"SAW-004"}

    def test_recurses_into_subdirectories(self, tmp_path: Path) -> None:
        sub = tmp_path / "nested"
        sub.mkdir()
        (sub / "test_a.py").write_text(
            'import pytest\n\n\n@pytest.mark.spec("BE-006")\ndef t(): ...\n', encoding="utf-8"
        )
        assert set(extract_test_specs(tmp_path)) == {"BE-006"}

    def test_bare_marker_expression_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "test_a.py").write_text('import pytest\n\npytest.mark.spec("WR-010")\n', encoding="utf-8")
        assert extract_test_specs(tmp_path) == {}

    def test_pytestmark_assignment_detected(self, tmp_path: Path) -> None:
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\npytestmark = [pytest.mark.spec("SIO-001")]\n', encoding="utf-8"
        )
        assert set(extract_test_specs(tmp_path)) == {"SIO-001"}

    def test_comma_joined_id_string_splits(self, tmp_path: Path) -> None:
        # test_examples.py writes some marks as one comma-joined string,
        # e.g. spec("DAG-002,DAG-003,DAG-005"). Each embedded ID counts.
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\n\n@pytest.mark.spec("DAG-002,DAG-003,DAG-005")\ndef t(): ...\n',
            encoding="utf-8",
        )
        assert set(extract_test_specs(tmp_path)) == {"DAG-002", "DAG-003", "DAG-005"}


# ---------------------------------------------------------------------------
# Allowlist — type-(d) IDs and implementation-pending backends
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_design_principle_id_allowlisted(self) -> None:
        # SIO-006 is a design principle (type d) — never mark-able.
        assert is_allowlisted("SIO-006") is True

    def test_pending_graph_backend_prefix_allowlisted(self) -> None:
        # The whole GR-* family is owned by ID-127, backend not yet built.
        assert is_allowlisted("GR-001") is True
        assert is_allowlisted("GR-057") is True

    def test_resource_locked_pending_id_allowlisted(self) -> None:
        # ERR-013 / ResourceLocked ships with the Graph backend.
        assert is_allowlisted("ERR-013") is True

    def test_ordinary_shipped_id_not_allowlisted(self) -> None:
        assert is_allowlisted("BE-014") is False


# ---------------------------------------------------------------------------
# compute_violations — drift / stale / duplicate
# ---------------------------------------------------------------------------


class TestComputeViolations:
    def test_marked_shipped_id_is_clean(self) -> None:
        violations = compute_violations(
            declared={"BE-014": ["s:1"]},
            marks={"BE-014": ["t:1"]},
        )
        assert violations == []

    def test_drift_unmarked_shipped_id(self) -> None:
        violations = compute_violations(
            declared={"BE-014": ["s:1"]},
            marks={},
        )
        assert violations == [(KIND_DRIFT, "BE-014")]

    def test_allowlisted_id_is_not_drift(self) -> None:
        # A declared but allowlisted (type-d) ID with no mark is not drift.
        violations = compute_violations(
            declared={"SIO-006": ["s:1"]},
            marks={},
        )
        assert violations == []

    def test_stale_mark_cites_unknown_spec(self) -> None:
        # The stale HTTP-001 shape: a mark citing an ID no spec declares.
        violations = compute_violations(
            declared={"BE-014": ["s:1"]},
            marks={"BE-014": ["t:1"], "HTTP-001": ["t:2"]},
        )
        assert violations == [(KIND_STALE, "HTTP-001")]

    def test_duplicate_declaration(self) -> None:
        # The STORE-015 collision: declared twice.
        violations = compute_violations(
            declared={"STORE-015": ["s:1", "s:2"]},
            marks={"STORE-015": ["t:1"]},
        )
        assert violations == [(KIND_DUPLICATE, "STORE-015")]

    def test_backlog_id_mark_is_not_stale(self) -> None:
        # `@pytest.mark.spec("BK-123")` is a sanctioned backlog-provenance
        # marker, not a stale spec reference — the gate does not govern it.
        violations = compute_violations(
            declared={"BE-014": ["s:1"]},
            marks={"BE-014": ["t:1"], "BK-123": ["t:2"], "BUG-137": ["t:3"], "ID-050": ["t:4"]},
        )
        assert violations == []

    def test_gate_code_mark_is_not_stale(self) -> None:
        # Docs-framework gate codes (G-01..G-07, spec 047) are a separate
        # traceability namespace cited alongside DOCFRAME-NNN sections.
        violations = compute_violations(
            declared={"BE-014": ["s:1"]},
            marks={"BE-014": ["t:1"], "G-01": ["t:2"]},
        )
        assert violations == []

    def test_violations_are_sorted(self) -> None:
        violations = compute_violations(
            declared={"BE-019": ["s:1"], "BE-004": ["s:2"]},
            marks={},
        )
        assert violations == [(KIND_DRIFT, "BE-004"), (KIND_DRIFT, "BE-019")]


# ---------------------------------------------------------------------------
# main() — baseline mechanics
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path, *, specs: str, tests: str) -> dict[str, Path]:
    spec = tmp_path / "specs"
    test = tmp_path / "tests"
    for d in (spec, test):
        d.mkdir()
    (spec / "003.md").write_text(specs, encoding="utf-8")
    (test / "test_conf.py").write_text(tests, encoding="utf-8")
    return {"specs_dir": spec, "tests_dir": test}


class TestMain:
    def test_clean_tree_passes(self, tmp_path: Path) -> None:
        dirs = _make_repo(
            tmp_path,
            specs="### BE-014: list_files()\n",
            tests='import pytest\n\n\n@pytest.mark.spec("BE-014")\ndef t(): ...\n',
        )
        assert main(**dirs, baseline=frozenset()) == 0

    def test_unbaselined_drift_fails(self, tmp_path: Path) -> None:
        dirs = _make_repo(
            tmp_path,
            specs="### BE-014: list_files()\n",
            tests="import pytest\n",
        )
        assert main(**dirs, baseline=frozenset()) == 1

    def test_baselined_drift_passes(self, tmp_path: Path) -> None:
        dirs = _make_repo(
            tmp_path,
            specs="### BE-014: list_files()\n",
            tests="import pytest\n",
        )
        baseline = frozenset({(KIND_DRIFT, "BE-014")})
        assert main(**dirs, baseline=baseline) == 0

    def test_stale_baseline_entry_fails(self, tmp_path: Path) -> None:
        # The ID IS marked now, but the baseline still lists it as a gap.
        dirs = _make_repo(
            tmp_path,
            specs="### BE-014: list_files()\n",
            tests='import pytest\n\n\n@pytest.mark.spec("BE-014")\ndef t(): ...\n',
        )
        baseline = frozenset({(KIND_DRIFT, "BE-014")})
        assert main(**dirs, baseline=baseline) == 1

    def test_stale_mark_is_not_baselineable_silently(self, tmp_path: Path) -> None:
        # A stale-mark violation outside the baseline fails the gate.
        dirs = _make_repo(
            tmp_path,
            specs="### BE-014: list_files()\n",
            tests='import pytest\n\n\n@pytest.mark.spec("HTTP-001")\ndef t(): ...\n',
        )
        # BE-014 drift is baselined; the stale HTTP-001 is not — still fails.
        baseline = frozenset({(KIND_DRIFT, "BE-014")})
        assert main(**dirs, baseline=baseline) == 1

    def test_repo_invocation_is_green(self) -> None:
        # The real repo must pass against the checked-in _BASELINE — the
        # gate is wired into the lint job and may not fail on master.
        assert main() == 0
