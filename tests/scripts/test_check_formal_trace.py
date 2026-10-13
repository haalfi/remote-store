"""Unit tests for scripts/check_formal_trace.py.

Exercises the ID-206 traceability gate:

D — Dafny ``// @spec`` tag extraction.
T — conformance ``@pytest.mark.spec`` marker extraction (AST).
S — spec-section declaration extraction (headings + requirement tables).
R — Alloy and Lean ``-- @spec`` tags and ``-- @restates`` declarations.
The three failure modes (F1 untested clause, F2 bad test marker, F3 bad
tag), the three restatement kinds (R1 bad tag, R2 untagged section, R3
unknown restated spec) and the shrink-only baseline mechanism in
``main()``.
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
extract_declared_by_file = _mod.extract_declared_by_file
extract_restatements = _mod.extract_restatements
compute_violations = _mod.compute_violations
compute_restatement_violations = _mod.compute_restatement_violations
main = _mod.main
KIND_UNTESTED = _mod.KIND_UNTESTED
KIND_TEST_BAD_ID = _mod.KIND_TEST_BAD_ID
KIND_TAG_BAD_ID = _mod.KIND_TAG_BAD_ID
KIND_RESTATEMENT_BAD_ID = _mod.KIND_RESTATEMENT_BAD_ID
KIND_RESTATEMENT_UNTAGGED = _mod.KIND_RESTATEMENT_UNTAGGED
KIND_RESTATES_UNKNOWN = _mod.KIND_RESTATES_UNKNOWN


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

    def test_bare_marker_expression_ignored(self, tmp_path: Path) -> None:
        # A *.mark.spec(...) call that decorates nothing is dead code. If it
        # counted, one dead line would silence an F1 with no test added.
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\n_ = pytest.mark.spec("CAP-004")\npytest.mark.spec("WR-010")\n',
            encoding="utf-8",
        )
        assert extract_conformance_specs(tmp_path) == {}

    def test_class_decorator_marker_detected(self, tmp_path: Path) -> None:
        # A spec marker decorating a test class applies to its methods.
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\n\n@pytest.mark.spec("BE-017")\nclass TestX:\n'
            "    def test_y(self):\n        assert True\n",
            encoding="utf-8",
        )
        assert set(extract_conformance_specs(tmp_path)) == {"BE-017"}

    def test_pytestmark_assignment_detected(self, tmp_path: Path) -> None:
        # `pytestmark = ...` is a real pytest marker-application site.
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\npytestmark = [pytest.mark.spec("SIO-001")]\n',
            encoding="utf-8",
        )
        assert set(extract_conformance_specs(tmp_path)) == {"SIO-001"}

    def test_marker_on_skipped_test_still_counts(self, tmp_path: Path) -> None:
        # Documents a deliberate scope limit (docstring § Scope): the check
        # verifies citation, not enablement — a marker on a skipped test
        # still counts toward T.
        (tmp_path / "test_a.py").write_text(
            'import pytest\n\n\n@pytest.mark.spec("BE-008")\n@pytest.mark.skip\ndef test_x():\n    assert True\n',
            encoding="utf-8",
        )
        assert set(extract_conformance_specs(tmp_path)) == {"BE-008"}


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

    def test_heading_with_parenthetical_before_colon(self, tmp_path: Path) -> None:
        # Spec 046 declares its renamed sections as `## EW-001 (was WR-014): ...`
        # — a parenthetical sits between the ID and the colon.
        (tmp_path / "046.md").write_text(
            "## EW-001 (was WR-014): write_with_hash Returns Digest\n",
            encoding="utf-8",
        )
        assert extract_declared_specs(tmp_path) == {"EW-001"}

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

    def test_table_row_outside_requirement_table_ignored(self, tmp_path: Path) -> None:
        # A table whose first column header is not `ID` (a summary /
        # cross-reference table) declares nothing — otherwise one stray
        # row could legitimise a bogus F2/F3 citation.
        (tmp_path / "x.md").write_text(
            "| Spec | Status |\n|----|----|\n| BE-099 | planned |\n",
            encoding="utf-8",
        )
        assert extract_declared_specs(tmp_path) == set()

    def test_requirement_table_header_is_case_insensitive(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text(
            "| id | Requirement |\n|----|----|\n| SAW-007 | empty path |\n",
            encoding="utf-8",
        )
        assert extract_declared_specs(tmp_path) == {"SAW-007"}

    def test_inline_reference_is_not_a_declaration(self, tmp_path: Path) -> None:
        # "See BE-021" in prose must not count as declaring BE-021.
        (tmp_path / "x.md").write_text("Some prose that mentions BE-021 in passing.\n", encoding="utf-8")
        assert extract_declared_specs(tmp_path) == set()

    def test_document_title_is_not_a_spec_id(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text("# Backend Adapter Contract Specification\n", encoding="utf-8")
        assert extract_declared_specs(tmp_path) == set()

    def test_declared_by_file_keeps_each_spec_apart(self, tmp_path: Path) -> None:
        # A restatement's claim space is the sections of the one spec it
        # restates, so the per-file split must not leak IDs across files.
        (tmp_path / "051-store-tree.md").write_text("## TREE-001: Partition\n", encoding="utf-8")
        (tmp_path / "003.md").write_text("### BE-014: list_files()\n", encoding="utf-8")
        assert extract_declared_by_file(tmp_path) == {
            "051-store-tree.md": {"TREE-001"},
            "003.md": {"BE-014"},
        }


# ---------------------------------------------------------------------------
# Source R — Alloy and Lean restatements
# ---------------------------------------------------------------------------


def _formal_tree(tmp_path: Path, *, als: str | None = None, lean: str | None = None) -> Path:
    formal = tmp_path / "formal"
    (formal / "alloy").mkdir(parents=True)
    (formal / "lean").mkdir(parents=True)
    if als is not None:
        (formal / "alloy" / "M.als").write_text(als, encoding="utf-8")
    if lean is not None:
        (formal / "lean" / "M.lean").write_text(lean, encoding="utf-8")
    return formal


class TestExtractRestatements:
    def test_alloy_tag_and_restates_declaration(self, tmp_path: Path) -> None:
        formal = _formal_tree(
            tmp_path,
            als="-- @restates sdd/specs/051-store-tree.md\nmodule M\n-- @spec TREE-002\npred AX2 { }\n",
        )
        r = extract_restatements(formal)
        assert set(r) == {"alloy/M.als"}
        assert set(r["alloy/M.als"].restates) == {"051-store-tree.md"}
        assert r["alloy/M.als"].tags["TREE-002"][0].endswith("M.als:3")

    def test_lean_tag_indented_inside_a_structure(self, tmp_path: Path) -> None:
        # Lean's Axioms structure carries one field per clause, so the tag
        # sits indented above a field's docstring.
        formal = _formal_tree(
            tmp_path,
            lean="structure Axioms where\n  -- @spec TREE-001\n  /-- AX-1 -/\n  ax1 : True\n",
        )
        assert set(extract_restatements(formal)["lean/M.lean"].tags) == {"TREE-001"}

    def test_multiple_ids_on_one_tag_line(self, tmp_path: Path) -> None:
        formal = _formal_tree(tmp_path, als="-- @spec TREE-010, TREE-011\n")
        assert set(extract_restatements(formal)["alloy/M.als"].tags) == {"TREE-010", "TREE-011"}

    def test_prose_mention_is_not_a_tag(self, tmp_path: Path) -> None:
        # The files' headers name TREE-001 to TREE-012 in prose; only a
        # `-- @spec` line is a tag.
        formal = _formal_tree(tmp_path, lean="/-! Source of truth: spec 051 (TREE-001 to TREE-012). -/\n")
        assert extract_restatements(formal)["lean/M.lean"].tags == {}

    def test_tag_quoted_inside_a_block_comment_is_not_a_tag(self, tmp_path: Path) -> None:
        # Both files' headers quote the tag syntax in a block comment. A quote
        # naming a real ID must not count as tagging that section (#1135 review).
        formal = _formal_tree(
            tmp_path,
            als="/*\n * e.g. `-- @spec TREE-009` on KeyDef\n */\n",
            lean="/-! e.g. `-- @spec TREE-009` on Key\n`-- @restates sdd/specs/051-store-tree.md` -/\n",
        )
        r = extract_restatements(formal)
        assert r["alloy/M.als"].tags == {}
        assert r["lean/M.lean"].tags == {}
        assert r["lean/M.lean"].restates == {}

    def test_lean_docstring_opener_is_not_a_line_comment(self, tmp_path: Path) -> None:
        # `/--` opens a Lean docstring; its `--` must not read as a tag line.
        formal = _formal_tree(tmp_path, lean="/-- @spec TREE-003 -/\ntheorem t : True := trivial\n")
        assert extract_restatements(formal)["lean/M.lean"].tags == {}

    def test_atspec_must_be_whole_word(self, tmp_path: Path) -> None:
        formal = _formal_tree(tmp_path, als="-- @specification of TREE-004\n")
        assert extract_restatements(formal)["alloy/M.als"].tags == {}

    def test_dafny_and_other_files_are_not_restatements(self, tmp_path: Path) -> None:
        # Top-level .dfy files are source D, and lake metadata beside the
        # Lean sources is not a restatement.
        formal = _formal_tree(tmp_path)
        (formal / "Contract.dfy").write_text("// @spec BE-014\n", encoding="utf-8")
        (formal / "lean" / "lakefile.toml").write_text("# -- @spec TREE-001\n", encoding="utf-8")
        assert extract_restatements(formal) == {}

    def test_restatement_tags_do_not_enter_source_d(self, tmp_path: Path) -> None:
        # F1 keys on D. A TREE-* tag in D would demand a conformance marker
        # that BK-436 has not written yet.
        formal = _formal_tree(tmp_path, als="-- @spec TREE-001\n", lean="-- @spec TREE-002\n")
        assert extract_dafny_specs(formal) == {}


class TestComputeRestatementViolations:
    _DECLARED_BY_FILE = {"051-store-tree.md": {"TREE-001", "TREE-002"}, "003.md": {"BE-014"}}
    _DECLARED = {"TREE-001", "TREE-002", "BE-014"}

    def _violations(self, tmp_path: Path, als: str) -> list[tuple[str, str]]:
        restatements = extract_restatements(_formal_tree(tmp_path, als=als))
        return compute_restatement_violations(restatements, self._DECLARED_BY_FILE, self._DECLARED)

    def test_complete_restatement_is_clean(self, tmp_path: Path) -> None:
        als = "-- @restates sdd/specs/051-store-tree.md\n-- @spec TREE-001\n-- @spec TREE-002\n"
        assert self._violations(tmp_path, als) == []

    def test_r1_tag_cites_unknown_spec(self, tmp_path: Path) -> None:
        assert self._violations(tmp_path, "-- @spec TREE-099\n") == [
            (KIND_RESTATEMENT_BAD_ID, "alloy/M.als TREE-099"),
        ]

    def test_r2_restated_section_without_tag(self, tmp_path: Path) -> None:
        # The case BK-437 names: a section with no counterpart in a
        # restatement of its spec. Localized to the file and the ID.
        als = "-- @restates sdd/specs/051-store-tree.md\n-- @spec TREE-001\n"
        assert self._violations(tmp_path, als) == [
            (KIND_RESTATEMENT_UNTAGGED, "alloy/M.als TREE-002"),
        ]

    def test_r3_restates_an_unknown_spec(self, tmp_path: Path) -> None:
        # Otherwise a renamed spec file would switch completeness off silently.
        als = "-- @restates sdd/specs/099-gone.md\n-- @spec TREE-001\n"
        assert self._violations(tmp_path, als) == [
            (KIND_RESTATES_UNKNOWN, "alloy/M.als 099-gone.md"),
        ]

    def test_tag_outside_the_restated_spec_is_allowed(self, tmp_path: Path) -> None:
        # Only an undeclared ID is an error; citing a declared section of
        # another spec is a cross-reference.
        als = "-- @restates sdd/specs/051-store-tree.md\n-- @spec TREE-001, TREE-002\n-- @spec BE-014\n"
        assert self._violations(tmp_path, als) == []

    def test_no_restates_means_no_completeness_demand(self, tmp_path: Path) -> None:
        assert self._violations(tmp_path, "-- @spec TREE-001\n") == []


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

    def test_untagged_restated_section_fails(self, tmp_path: Path) -> None:
        dirs = _make_repo(
            tmp_path,
            dafny="",
            conformance="import pytest\n",
            specs="## TREE-001: Partition\n## TREE-002: Root\n",
        )
        (dirs["formal_dir"] / "alloy").mkdir()
        (dirs["formal_dir"] / "alloy" / "M.als").write_text(
            "-- @restates sdd/specs/003.md\n-- @spec TREE-001\n", encoding="utf-8"
        )
        assert main(**dirs, baseline=frozenset()) == 1

    def test_complete_restatement_passes(self, tmp_path: Path) -> None:
        dirs = _make_repo(
            tmp_path,
            dafny="",
            conformance="import pytest\n",
            specs="## TREE-001: Partition\n## TREE-002: Root\n",
        )
        (dirs["formal_dir"] / "lean").mkdir()
        (dirs["formal_dir"] / "lean" / "M.lean").write_text(
            "-- @restates sdd/specs/003.md\n-- @spec TREE-001\n-- @spec TREE-002\n", encoding="utf-8"
        )
        assert main(**dirs, baseline=frozenset()) == 0

    def test_repo_invocation_is_green(self) -> None:
        # The real repo must pass against the checked-in _BASELINE — the
        # gate is wired into `hatch run all` and may not fail on master.
        assert main() == 0

    def test_repo_restatements_cover_spec_051(self) -> None:
        # Without this, the repo test above would also pass if both files
        # dropped their @restates line: no declaration, no completeness check.
        root = _SCRIPT.parents[1]
        restatements = extract_restatements(root / "sdd" / "formal")
        tree = extract_declared_by_file(root / "sdd" / "specs")["051-store-tree.md"]
        assert len(tree) == 12
        for label in ("alloy/StoreAxioms.als", "lean/StoreAxioms.lean"):
            assert set(restatements[label].restates) == {"051-store-tree.md"}
            assert tree <= set(restatements[label].tags)
