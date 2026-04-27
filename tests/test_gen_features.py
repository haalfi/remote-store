"""Tests for scripts/gen_features.py (ID-163)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gen_features_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    import gen_features

    return gen_features


@pytest.fixture(scope="module")
def graph(gen_features_module):
    return gen_features_module._load_graph()


@pytest.fixture(scope="module")
def pyproject(gen_features_module):
    return gen_features_module._load_pyproject()


class TestRegistryOrder:
    def test_parses_at_least_one_entry(self, gen_features_module):
        order = gen_features_module._parse_registry_order()
        assert len(order) >= 1

    def test_local_and_memory_present(self, gen_features_module):
        types = [t for t, _ in gen_features_module._parse_registry_order()]
        assert "local" in types
        assert "memory" in types

    def test_returns_tuples(self, gen_features_module):
        for type_str, cls_name in gen_features_module._parse_registry_order():
            assert isinstance(type_str, str)
            assert isinstance(cls_name, str)
            assert type_str
            assert cls_name


class TestBaselineCaps:
    def test_excludes_flag_caps(self, gen_features_module, graph):
        baseline = gen_features_module._baseline_caps(graph)
        assert "USER_METADATA" not in baseline
        assert "WRITE_RESULT_NATIVE" not in baseline

    def test_includes_gate_caps(self, gen_features_module, graph):
        baseline = gen_features_module._baseline_caps(graph)
        for cap in ("READ", "WRITE", "DELETE", "LIST", "GLOB", "MOVE", "COPY"):
            assert cap in baseline

    def test_is_sorted_alphabetically(self, gen_features_module, graph):
        baseline = gen_features_module._baseline_caps(graph)
        assert baseline == sorted(baseline)


class TestFormatCaps:
    def test_all_when_nothing_missing(self, gen_features_module):
        baseline = ["A", "B", "C"]
        assert gen_features_module._format_caps(frozenset({"A", "B", "C"}), baseline) == "All"

    def test_all_except_when_majority_present(self, gen_features_module):
        baseline = ["A", "B", "C", "D", "E", "F", "G", "H"]
        declared = frozenset({"A", "B", "C", "D", "E", "F"})  # 6 of 8 present
        result = gen_features_module._format_caps(declared, baseline)
        assert result.startswith("All except")
        assert "`G`" in result
        assert "`H`" in result

    def test_explicit_list_when_minority_present(self, gen_features_module):
        baseline = ["A", "B", "C", "D", "E", "F", "G", "H"]
        declared = frozenset({"A", "B", "C"})  # 3 of 8 — minority
        result = gen_features_module._format_caps(declared, baseline)
        assert "All" not in result
        assert "`A`" in result

    def test_preserves_baseline_order_in_except_clause(self, gen_features_module):
        # Need majority present to trigger "All except" path.
        baseline = ["ATOMIC_MOVE", "COPY", "DELETE", "GLOB"]
        declared = frozenset({"COPY", "DELETE", "GLOB"})  # missing ATOMIC_MOVE (3 present > 1 missing)
        result = gen_features_module._format_caps(declared, baseline)
        # ATOMIC_MOVE appears first in baseline, so it should be listed first in "except".
        assert result == "All except `ATOMIC_MOVE`"


class TestBackendsMainTable:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        lines = table.splitlines()
        assert lines[0] == "| Type | Class | Extra | Capabilities |"
        assert lines[1] == "|---|---|---|---|"

    def test_all_registered_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        for type_str, _ in gen_features_module._parse_registry_order():
            assert f"| `{type_str}` |" in table, f"Backend {type_str!r} missing"

    def test_local_renders_as_all(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        local_row = next(row for row in table.splitlines() if row.startswith("| `local`"))
        assert local_row.endswith("| All |")

    def test_http_extra_has_stdlib_note(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        http_row = next(row for row in table.splitlines() if row.startswith("| `http`"))
        assert "stdlib" in http_row

    def test_http_caps_explicit_list(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        http_row = next(row for row in table.splitlines() if row.startswith("| `http`"))
        assert "All" not in http_row.split("|")[-2]

    def test_s3_missing_only_atomic_move(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        s3_row = next(row for row in table.splitlines() if row.startswith("| `s3` |"))
        assert "ATOMIC_MOVE" in s3_row
        assert s3_row.endswith("All except `ATOMIC_MOVE` |")


class TestBackendsFlagsTable:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        lines = table.splitlines()
        assert "WRITE_RESULT_NATIVE" in lines[0]
        assert "USER_METADATA" in lines[0]
        assert lines[1] == "|---|---|---|"

    def test_all_registered_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        for type_str, _ in gen_features_module._parse_registry_order():
            assert f"| `{type_str}` |" in table

    def test_local_has_write_result_no_user_metadata(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        local_row = next(row for row in table.splitlines() if row.startswith("| `local`"))
        cols = [c.strip() for c in local_row.split("|")[1:-1]]
        assert cols[1] == "Yes"
        assert cols[2] == "—"

    def test_sql_blob_uses_notes(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        sql_row = next(row for row in table.splitlines() if row.startswith("| `sql-blob`"))
        assert "requires" in sql_row
        assert "modified_at" in sql_row
        assert "user_metadata" in sql_row

    def test_azure_has_both_flags(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        azure_row = next(row for row in table.splitlines() if row.startswith("| `azure`"))
        cols = [c.strip() for c in azure_row.split("|")[1:-1]]
        assert cols[1] == "Yes"
        assert cols[2] == "Yes"


class TestInstallExtras:
    def test_starts_and_ends_with_fence(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        lines = block.splitlines()
        assert lines[0] == "```"
        assert lines[-1] == "```"

    def test_excludes_dev_tooling(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        for excluded in ("dev", "bench", "docs"):
            assert f"remote-store[{excluded}]" not in block

    def test_includes_backend_extras(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        for extra in ("s3", "azure", "sftp", "sql", "sql-query"):
            assert f"remote-store[{extra}]" in block

    def test_includes_extension_extras(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        for extra in ("arrow", "otel", "yaml", "pydantic", "dagster"):
            assert f"remote-store[{extra}]" in block

    def test_has_comments(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        assert "# S3 via s3fs" in block
        assert "# Azure ADLS Gen2" in block

    def test_columns_aligned(self, gen_features_module, pyproject):
        """All comment markers (#) must start at the same column."""
        block = gen_features_module.project_install_extras(pyproject)
        comment_cols = [line.index("#") for line in block.splitlines() if "#" in line and not line.startswith("```")]
        if comment_cols:
            assert len(set(comment_cols)) == 1, "Comment columns are not aligned"


class TestRegionReplacement:
    def test_replaces_known_region(self, gen_features_module):
        text = "before\n<!-- BEGIN_GENERATED:foo -->\nold content\n<!-- END_GENERATED:foo -->\nafter"
        result = gen_features_module._replace_regions(text, {"foo": "new content"})
        assert "old content" not in result
        assert "new content" in result
        assert "before" in result
        assert "after" in result

    def test_leaves_unknown_region_untouched(self, gen_features_module):
        text = "<!-- BEGIN_GENERATED:bar -->\nstuff\n<!-- END_GENERATED:bar -->"
        result = gen_features_module._replace_regions(text, {"other": "x"})
        assert "stuff" in result

    def test_replaces_multiple_regions(self, gen_features_module):
        text = (
            "<!-- BEGIN_GENERATED:a -->\nA old\n<!-- END_GENERATED:a -->\n"
            "middle\n"
            "<!-- BEGIN_GENERATED:b -->\nB old\n<!-- END_GENERATED:b -->"
        )
        result = gen_features_module._replace_regions(text, {"a": "A new", "b": "B new"})
        assert "A new" in result
        assert "B new" in result
        assert "old" not in result


class TestFeaturesFileIntegrity:
    def test_features_md_has_all_regions(self):
        text = (ROOT / "FEATURES.md").read_text(encoding="utf-8")
        for region in ("backends_main", "backends_flags", "install_extras"):
            assert f"<!-- BEGIN_GENERATED:{region} -->" in text
            assert f"<!-- END_GENERATED:{region} -->" in text

    def test_features_md_is_up_to_date(self, gen_features_module, graph, pyproject):
        """Generated regions in FEATURES.md must match current projection output."""
        text = (ROOT / "FEATURES.md").read_text(encoding="utf-8")
        text_lf = text.replace("\r\n", "\n")
        projections = gen_features_module.project_all(graph, pyproject)
        updated = gen_features_module._replace_regions(text_lf, projections)
        assert text_lf == updated, "FEATURES.md generated regions are out of date. Run: hatch run gen-features"
