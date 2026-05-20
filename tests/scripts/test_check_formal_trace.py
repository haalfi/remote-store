"""Unit tests for scripts/check_formal_trace.py.

Exercises the ID-206 traceability gate:

D — Dafny ``// @spec`` tag extraction.
T — conformance ``@pytest.mark.spec`` marker extraction (AST).
S — spec-section declaration extraction (headings + requirement tables).
The three failure modes (F1 untested clause, F2 bad test marker, F3 bad
tag) and the shrink-only baseline mechanism in ``main()``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_formal_trace.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_formal_trace", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_formal_trace", module)
    spec.loader.exec_module(module)
    return module


_mod = _load_module()
extract_dafny_specs = _mod.extract_dafny_specs
extract_conformance_specs = _mod.extract_conformance_specs
extract_declared_specs = _mod.extract_declared_specs
compute_violations = _mod.compute_violations
main = _mod.main
KIND_UNTESTED = _mod.KIND_UNTESTED
KIND_TEST_BAD_ID = _mod.KIND_TEST_BAD_ID
KIND_TAG_BAD_ID = _mod.KIND_TAG_BAD_ID


# ---------------------------------------------------------------------------
# Source D — Dafny @spec tags
# ---------------------------------------------------------------------------


class TestExtractDafnySpecs:
    def test_single_tag_above_ensures(self, tmp_path: Path) -> None:
        (tmp_path / "Contract.dfy").write_text(
            "method M()\n  // @spec BE-014\n  ensures true\n",
            encoding="utf-8",
        )
        tags = extract_dafny_specs(tmp_path)
        assert set(tags) == {"BE-014"}
        assert tags["BE-014"][0].endswith("Contract.dfy:2")

    def test_multiple_ids_on_one_tag_line(self, tmp_path: Path) -> None:
        # A postcondition that encodes two clauses may carry both IDs.
        (tmp_path / "C.dfy").write_text("// @spec WR-001a, WR-004\n", encoding="utf-8")
        assert set(extract_dafny_specs(tmp_path)) == {"WR-001a", "WR-004"}

    def test_scans_every_dfy_file(self, tmp_path: Path) -> None:
        (tmp_path / "A.dfy").write_text("// @spec BE-004\n", encoding="utf-8")
        (tmp_path / "B.dfy").write_text("// @spec DEPTH-001\n", encoding="utf-8")
        assert set(extract_dafny_specs(tmp_path)) == {"BE-004", "DEPTH-001"}

    def test_non_tag_comment_ignored(self, tmp_path: Path) -> None:
        # A free-text comment that merely mentions an ID is not a tag.
        (tmp_path / "C.dfy").write_text("// WR-013: user metadata round-trip\n", encoding="utf-8")
        assert extract_dafny_specs(tmp_path) == {}

    def test_atspec_must_be_whole_word(self, tmp_path: Path) -> None:
        # "@specification" must not be read as an "@spec" tag.
        (tmp_path / "C.dfy").write_text("// @specification of BE-099\n", encoding="utf-8")
        assert extract_dafny_specs(tmp_path) == {}

    def test_records_all_locations_for_repeated_id(self, tmp_path: Path) -> None:
        (tmp_path / "C.dfy").write_text("// @spec BE-008\n// @spec BE-008\n", encoding="utf-8")
        assert len(extract_dafny_specs(tmp_path)["BE-008"]) == 2


# ---------------------------------------------------------------------------
# Source T — conformance @pytest.mark.spec markers
# ---------------------------------------------------------------------------


class TestExtractConformanceSpecs:
    def test_decorator_marker_detected(self, tmp_path: Path) -> None:
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\n\n@pytest.mark.spec("BE-014")\ndef test_x():\n    assert True\n',
            encoding="utf-8",
        )
        cited = extract_conformance_specs(tmp_path)
        assert set(cited) == {"BE-014"}
        assert cited["BE-014"][0].endswith("test_a.py:4")

    def test_stacked_markers_detected(self, tmp_path: Path) -> None:
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\n\n@pytest.mark.spec("BE-014")\n@pytest.mark.spec("DEPTH-003")\n'
            "def test_x():\n    assert True\n",
            encoding="utf-8",
        )
        assert set(extract_conformance_specs(tmp_path)) == {"BE-014", "DEPTH-003"}

    def test_marker_inside_pytest_param_marks(self, tmp_path: Path) -> None:
        # Markers attached via marks= on pytest.param must also be caught.
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\nP = pytest.param("x", marks=pytest.mark.spec("SAW-004"))\n',
            encoding="utf-8",
        )
        assert set(extract_conformance_specs(tmp_path)) == {"SAW-004"}

    def test_recurses_into_subdirectories(self, tmp_path: Path) -> None:
        sub = tmp_path / "nested"
        sub.mkdir()
        (sub / "test_a.py").write_text(
            'import pytest\n\n\n@pytest.mark.spec("BE-006")\ndef t(): ...\n', encoding="utf-8"
        )
        assert set(extract_conformance_specs(tmp_path)) == {"BE-006"}

    def test_non_string_marker_arg_ignored(self, tmp_path: Path) -> None:
        # A dynamic marker arg has no literal ID to extract; do not crash.
        (tmp_path / "test_a.py").write_text(
            "import pytest\n\nSID = 'BE-014'\n\n\n@pytest.mark.spec(SID)\ndef t(): ...\n",
            encoding="utf-8",
        )
        assert extract_conformance_specs(tmp_path) == {}

    def test_unrelated_mark_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\n\n@pytest.mark.parametrize("x", [1])\ndef test_x(x):\n    assert x\n',
            encoding="utf-8",
        )
        assert extract_conformance_specs(tmp_path) == {}


# ---------------------------------------------------------------------------
# Source S — declared spec sections
# ---------------------------------------------------------------------------


class TestExtractDeclaredSpecs:
    def test_level_three_heading(self, tmp_path: Path) -> None:
        (tmp_path / "003.md").write_text("### BE-014: list_files()\n", encoding="utf-8")
        assert extract_declared_specs(tmp_path) == {"BE-014"}

    def test_level_two_heading(self, tmp_path: Path) -> None:
        # Heading level is not consistent across spec files (spec 045 uses ##).
        (tmp_path / "045.md").write_text("## WR-013: User Metadata Round-Trip\n", encoding="utf-8")
        assert extract_declared_specs(tmp_path) == {"WR-013"}

    def test_requirements_table_row(self, tmp_path: Path) -> None:
        # Spec 022 declares SAW-001..015 as table rows, not headings.
        (tmp_path / "022.md").write_text(
            "| ID | Requirement | Status |\n|----|----|----|\n| SAW-004 | no partial file | Done |\n",
            encoding="utf-8",
        )
        assert extract_declared_specs(tmp_path) == {"SAW-004"}

    def test_multi_word_family_prefix(self, tmp_path: Path) -> None:
        (tmp_path / "040.md").write_text("### SQL-BLOB-003: capabilities\n", encoding="utf-8")
        assert extract_declared_specs(tmp_path) == {"SQL-BLOB-003"}

    def test_inline_reference_is_not_a_declaration(self, tmp_path: Path) -> None:
        # "See BE-021" in prose must not count as declaring BE-021.
        (tmp_path / "x.md").write_text("Some prose that mentions BE-021 in passing.\n", encoding="utf-8")
        assert extract_declared_specs(tmp_path) == set()

    def test_document_title_is_not_a_spec_id(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text("# Backend Adapter Contract Specification\n", encoding="utf-8")
        assert extract_declared_specs(tmp_path) == set()


# ---------------------------------------------------------------------------
# compute_violations — F1 / F2 / F3
# ---------------------------------------------------------------------------


class TestComputeViolations:
    def test_fully_traced_clause_is_clean(self) -> None:
        violations = compute_violations(
            dafny={"BE-014": ["f:1"]},
            conformance={"BE-014": ["t:1"]},
            declared={"BE-014"},
        )
        assert violations == []

    def test_f1_untested_dafny_clause(self) -> None:
        violations = compute_violations(
            dafny={"BE-014": ["f:1"]},
            conformance={},
            declared={"BE-014"},
        )
        assert violations == [(KIND_UNTESTED, "BE-014")]

    def test_f2_test_cites_unknown_spec(self) -> None:
        violations = compute_violations(
            dafny={},
            conformance={"ZZ-999": ["t:1"]},
            declared={"BE-014"},
        )
        assert violations == [(KIND_TEST_BAD_ID, "ZZ-999")]

    def test_f3_tag_cites_unknown_spec(self) -> None:
        violations = compute_violations(
            dafny={"ZZ-999": ["f:1"]},
            conformance={},
            declared={"BE-014"},
        )
        assert violations == [(KIND_TAG_BAD_ID, "ZZ-999")]

    def test_undeclared_tag_is_f3_only_not_also_f1(self) -> None:
        # A tag citing a non-existent spec is one violation (F3), never
        # also counted as F1 — otherwise closing one would leave the other.
        violations = compute_violations(
            dafny={"ZZ-999": ["f:1"]},
            conformance={},
            declared=set(),
        )
        assert violations == [(KIND_TAG_BAD_ID, "ZZ-999")]

    def test_violations_are_sorted(self) -> None:
        violations = compute_violations(
            dafny={"BE-019": ["f:1"], "BE-004": ["f:2"]},
            conformance={},
            declared={"BE-019", "BE-004"},
        )
        assert violations == [(KIND_UNTESTED, "BE-004"), (KIND_UNTESTED, "BE-019")]


# ---------------------------------------------------------------------------
# main() — baseline mechanics
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path, *, dafny: str, conformance: str, specs: str) -> dict[str, Path]:
    """Build a synthetic formal/conformance/specs tree and return the dirs."""
    formal = tmp_path / "formal"
    conf = tmp_path / "conformance"
    spec = tmp_path / "specs"
    for d in (formal, conf, spec):
        d.mkdir()
    (formal / "Contract.dfy").write_text(dafny, encoding="utf-8")
    (conf / "test_conf.py").write_text(conformance, encoding="utf-8")
    (spec / "003.md").write_text(specs, encoding="utf-8")
    return {"formal_dir": formal, "conformance_dir": conf, "specs_dir": spec}


class TestMain:
    def test_clean_tree_passes(self, tmp_path: Path) -> None:
        dirs = _make_repo(
            tmp_path,
            dafny="// @spec BE-014\nensures true\n",
            conformance='import pytest\n\n\n@pytest.mark.spec("BE-014")\ndef t(): ...\n',
            specs="### BE-014: list_files()\n",
        )
        assert main(**dirs, baseline=frozenset()) == 0

    def test_unbaselined_violation_fails(self, tmp_path: Path) -> None:
        # A Dafny-backed clause with no conformance test and no baseline
        # entry is a regression — the gate must fail.
        dirs = _make_repo(
            tmp_path,
            dafny="// @spec BE-014\nensures true\n",
            conformance="import pytest\n",
            specs="### BE-014: list_files()\n",
        )
        assert main(**dirs, baseline=frozenset()) == 1

    def test_baselined_violation_passes(self, tmp_path: Path) -> None:
        # The same gap, once baselined, passes — that is the landing strategy.
        dirs = _make_repo(
            tmp_path,
            dafny="// @spec BE-014\nensures true\n",
            conformance="import pytest\n",
            specs="### BE-014: list_files()\n",
        )
        baseline = frozenset({(KIND_UNTESTED, "BE-014")})
        assert main(**dirs, baseline=baseline) == 0

    def test_stale_baseline_entry_fails(self, tmp_path: Path) -> None:
        # The clause IS tested, but the baseline still lists it as a gap.
        # A stale entry must fail so the baseline shrinks monotonically.
        dirs = _make_repo(
            tmp_path,
            dafny="// @spec BE-014\nensures true\n",
            conformance='import pytest\n\n\n@pytest.mark.spec("BE-014")\ndef t(): ...\n',
            specs="### BE-014: list_files()\n",
        )
        baseline = frozenset({(KIND_UNTESTED, "BE-014")})
        assert main(**dirs, baseline=baseline) == 1

    def test_repo_invocation_is_green(self) -> None:
        # The real repo must pass against the checked-in _BASELINE — the
        # gate is wired into `hatch run all` and may not fail on master.
        assert main() == 0
