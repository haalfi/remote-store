"""Unit tests for scripts/check_custom_backend_guide.py (BK-320)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_custom_backend_guide.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_custom_backend_guide", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_custom_backend_guide", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()
check_snippet_regions = _mod.check_snippet_regions
check_abstract_table = _mod.check_abstract_table
check_optional_overrides_table = _mod.check_optional_overrides_table
check_conformance_files = _mod.check_conformance_files
check_registration_toml = _mod.check_registration_toml
main = _mod.main

_GUIDE = Path(__file__).resolve().parents[2] / "docs-src" / "guides" / "custom-backend-guide.md"


class TestSnippetRegions:
    def test_resolves_real_region(self, tmp_path: Path) -> None:
        snippet = tmp_path / "snip.py"
        snippet.write_text("# --8<-- [start:demo]\nx = 1\n# --8<-- [end:demo]\n", encoding="utf-8")
        guide = '```python\n--8<-- "snip.py:demo"\n```\n'
        assert check_snippet_regions(guide, tmp_path) == []

    def test_missing_region_flagged(self, tmp_path: Path) -> None:
        snippet = tmp_path / "snip.py"
        snippet.write_text("# --8<-- [start:other]\n# --8<-- [end:other]\n", encoding="utf-8")
        guide = '--8<-- "snip.py:demo"\n'
        violations = check_snippet_regions(guide, tmp_path)
        assert len(violations) == 2
        assert "[start:demo]" in violations[0]
        assert "[end:demo]" in violations[1]

    def test_missing_file_flagged(self, tmp_path: Path) -> None:
        violations = check_snippet_regions('--8<-- "gone.py:demo"\n', tmp_path)
        assert violations == ["snippet file not found: gone.py (region demo)"]

    def test_zero_includes_flagged(self, tmp_path: Path) -> None:
        # A guide that lost every include must fail, not report clean.
        violations = check_snippet_regions("# guide with no includes\n", tmp_path)
        assert len(violations) == 1
        assert "no --8<-- snippet includes" in violations[0]

    def test_whole_file_include_checked(self, tmp_path: Path) -> None:
        # pymdownx also supports region-less whole-file includes.
        (tmp_path / "whole.py").write_text("x = 1\n", encoding="utf-8")
        assert check_snippet_regions('--8<-- "whole.py"\n', tmp_path) == []
        violations = check_snippet_regions('--8<-- "gone_whole.py"\n', tmp_path)
        assert violations == ["snippet file not found: gone_whole.py"]


class TestAbstractTable:
    def test_missing_table_flagged(self) -> None:
        violations = check_abstract_table("# A guide with no table\n")
        assert len(violations) == 1
        assert "table not found" in violations[0]

    def test_missing_member_flagged(self) -> None:
        guide = "### Abstract methods (must implement)\n\n| Member |\n|---|\n| `exists(path)` |\n"
        violations = check_abstract_table(guide)
        assert any("missing row for 'read'" in v for v in violations)

    def test_stale_member_flagged(self) -> None:
        # A row for a method the ABC does not declare abstract must be flagged.
        real_table = _real_guide_table()
        guide = real_table + "| `frobnicate(path)` | x | x |\n"
        violations = check_abstract_table(guide)
        assert violations == ["abstract-methods table: row 'frobnicate' is not an abstract member of Backend"]

    def test_param_drift_flagged(self) -> None:
        # Simulate the BUG-235 drift: drop max_depth from the list_files row.
        real_table = _real_guide_table()
        drifted = real_table.replace("`list_files(path, recursive, max_depth)`", "`list_files(path, recursive)`")
        assert drifted != real_table, "guide fixture no longer contains the expected list_files row"
        violations = check_abstract_table(drifted)
        assert len(violations) == 1
        assert "list_files" in violations[0]
        assert "max_depth" in violations[0]

    def test_real_guide_table_is_clean(self) -> None:
        assert check_abstract_table(_real_guide_table()) == []

    def test_subheading_terminates_scan(self) -> None:
        # A #### subheading must end the table scan: the bogus row below it
        # must NOT be absorbed (and therefore not reported as stale).
        guide = _real_guide_table() + "#### aside\n\n| `bogus_member(path)` | x | x |\n"
        assert not any("bogus_member" in v for v in check_abstract_table(guide))


def _real_guide_table() -> str:
    """The current guide's abstract-methods section, as the known-good fixture."""
    text = _GUIDE.read_text(encoding="utf-8")
    start = text.index("### Abstract methods")
    end = text.index("### Optional overrides")
    return text[start:end]


def _real_overrides_table() -> str:
    """The current guide's optional-overrides section, as the known-good fixture."""
    text = _GUIDE.read_text(encoding="utf-8")
    start = text.index("### Optional overrides")
    end = text.index("## See also")
    return text[start:end]


class TestOptionalOverridesTable:
    def test_missing_table_flagged(self) -> None:
        violations = check_optional_overrides_table("# A guide with no table\n")
        assert len(violations) == 1
        assert "table not found" in violations[0]

    def test_missing_member_flagged(self) -> None:
        # Simulate the BK-320 drift this check exists for: drop the resolve() row.
        real_table = _real_overrides_table()
        lines = [line for line in real_table.splitlines() if not line.startswith("| `resolve(")]
        assert len(lines) < len(real_table.splitlines()), "overrides fixture no longer contains a resolve() row"
        violations = check_optional_overrides_table("\n".join(lines))
        assert violations == ["optional-overrides table: missing row for 'resolve'"]

    def test_stale_member_flagged(self) -> None:
        guide = _real_overrides_table() + "| `frobnicate(path)` | x |\n"
        violations = check_optional_overrides_table(guide)
        assert violations == ["optional-overrides table: row 'frobnicate' is not a public non-abstract Backend method"]

    def test_param_drift_flagged(self) -> None:
        drifted = _real_overrides_table().replace("`unwrap(type_hint)`", "`unwrap(hint)`")
        violations = check_optional_overrides_table(drifted)
        assert len(violations) == 1
        assert "unwrap" in violations[0]
        assert "type_hint" in violations[0]

    def test_real_guide_table_is_clean(self) -> None:
        assert check_optional_overrides_table(_real_overrides_table()) == []


class TestConformanceFiles:
    def test_existing_file_ok(self) -> None:
        root = Path(__file__).resolve().parents[2]
        assert check_conformance_files("see tests/backends/conformance/test_io.py", root) == []

    def test_nonexistent_file_flagged(self) -> None:
        root = Path(__file__).resolve().parents[2]
        violations = check_conformance_files("see tests/backends/conformance/test_gone.py", root)
        assert violations == ["guide names nonexistent conformance file: test_gone.py"]

    def test_zero_references_flagged(self) -> None:
        root = Path(__file__).resolve().parents[2]
        violations = check_conformance_files("guide with no conformance refs", root)
        assert len(violations) == 1
        assert "names no tests/backends/conformance/" in violations[0]


class TestRegistrationToml:
    _ROOT = Path(__file__).resolve().parents[2]

    def test_real_guide_toml_is_valid(self) -> None:
        text = _GUIDE.read_text(encoding="utf-8")
        assert check_registration_toml(text, self._ROOT) == []

    def test_invalid_enum_value_flagged(self) -> None:
        guide = '```toml\n[backend.x]\ntransport = "carrier-pigeon"\nconcurrency = "thread_safe"\n```\n'
        violations = check_registration_toml(guide, self._ROOT)
        assert len(violations) == 1
        assert "carrier-pigeon" in violations[0]

    def test_missing_concurrency_flagged(self) -> None:
        guide = '```toml\n[backend.x]\ntransport = "http"\n```\n'
        violations = check_registration_toml(guide, self._ROOT)
        assert len(violations) == 1
        assert "concurrency" in violations[0]

    def test_fixture_fields_validated(self) -> None:
        guide = '```toml\n[fixture.x]\nstage = 9\nkind = "imaginary"\ncontainer = "redis"\n```\n'
        violations = check_registration_toml(guide, self._ROOT)
        assert len(violations) == 3

    def test_unparseable_fence_flagged(self) -> None:
        guide = "```toml\nthis is [not toml\n```\n"
        violations = check_registration_toml(guide, self._ROOT)
        assert len(violations) == 1
        assert "does not parse" in violations[0]


class TestMain:
    def test_real_guide_passes(self, capsys) -> None:
        assert main() == 0
        assert "in sync" in capsys.readouterr().out

    def test_missing_guide_returns_one(self, tmp_path: Path, capsys) -> None:
        assert main([str(tmp_path / "gone.md")]) == 1
        assert "guide not found" in capsys.readouterr().err

    def test_drifted_guide_returns_one(self, tmp_path: Path, capsys) -> None:
        drifted = _GUIDE.read_text(encoding="utf-8").replace(
            "`list_files(path, recursive, max_depth)`", "`list_files(path, recursive)`"
        )
        target = tmp_path / "guide.md"
        target.write_text(drifted, encoding="utf-8")
        assert main([str(target)]) == 1
        assert "list_files" in capsys.readouterr().err

    # One drift case per remaining check, so silently unwiring any check
    # from main() fails a test (each drift is invisible to the others).

    def test_optional_table_drift_fails_main(self, tmp_path: Path, capsys) -> None:
        text = _GUIDE.read_text(encoding="utf-8")
        drifted = "\n".join(line for line in text.splitlines() if not line.startswith("| `resolve("))
        assert drifted != text, "guide fixture no longer contains the resolve() row"
        target = tmp_path / "guide.md"
        target.write_text(drifted, encoding="utf-8")
        assert main([str(target)]) == 1
        assert "resolve" in capsys.readouterr().err

    def test_conformance_file_drift_fails_main(self, tmp_path: Path, capsys) -> None:
        drifted = _GUIDE.read_text(encoding="utf-8").replace(
            "tests/backends/conformance/test_io.py", "tests/backends/conformance/test_vanished.py"
        )
        target = tmp_path / "guide.md"
        target.write_text(drifted, encoding="utf-8")
        assert main([str(target)]) == 1
        assert "test_vanished.py" in capsys.readouterr().err

    def test_snippet_include_drift_fails_main(self, tmp_path: Path, capsys) -> None:
        drifted = _GUIDE.read_text(encoding="utf-8").replace("--8<--", "(include removed)")
        target = tmp_path / "guide.md"
        target.write_text(drifted, encoding="utf-8")
        assert main([str(target)]) == 1
        assert "snippet includes" in capsys.readouterr().err

    def test_registration_toml_drift_fails_main(self, tmp_path: Path, capsys) -> None:
        drifted = _GUIDE.read_text(encoding="utf-8").replace('concurrency       = "thread_safe"', "")
        target = tmp_path / "guide.md"
        target.write_text(drifted, encoding="utf-8")
        assert main([str(target)]) == 1
        assert "concurrency" in capsys.readouterr().err
