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
check_required_table = _mod.check_required_table
check_attributes_table = _mod.check_attributes_table
check_protocols_table = _mod.check_protocols_table
check_capability_table = _mod.check_capability_table
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

    def test_malformed_ref_flagged_by_parity(self, tmp_path: Path) -> None:
        # A ref the parser cannot read (bad region charset) must not vanish silently.
        snippet = tmp_path / "snip.py"
        snippet.write_text("# --8<-- [start:ok]\n# --8<-- [end:ok]\n", encoding="utf-8")
        guide = '--8<-- "snip.py:ok"\n--8<-- "snip.py:bad.region"\n'
        violations = check_snippet_regions(guide, tmp_path)
        assert any("malformed snippet ref" in v for v in violations)


def _section(start_heading: str, end_heading: str) -> str:
    """One quick-reference section of the current guide, as the known-good fixture."""
    text = _GUIDE.read_text(encoding="utf-8")
    return text[text.index(start_heading) : text.index(end_heading)]


def _required_section() -> str:
    return _section("### Required driver members", "### Declared attributes")


def _attributes_section() -> str:
    return _section("### Declared attributes", "### Optional protocols")


def _protocols_section() -> str:
    return _section("### Optional protocols", "## See also")


def _without_row(section: str, prefix: str) -> str:
    lines = section.splitlines()
    kept = [line for line in lines if not line.startswith(prefix)]
    assert len(kept) == len(lines) - 1, f"fixture no longer has exactly one row starting {prefix!r}"
    return "\n".join(kept)


class TestRequiredTable:
    def test_missing_table_flagged(self) -> None:
        violations = check_required_table("# A guide with no table\n")
        assert len(violations) == 1
        assert "table not found" in violations[0]

    def test_missing_member_flagged(self) -> None:
        violations = check_required_table(_without_row(_required_section(), "| `get(key)`"))
        assert violations == ["required-members table: missing row for 'get'"]

    def test_stale_member_flagged(self) -> None:
        # A row for a method Driver does not declare must be flagged.
        guide = _required_section() + "| `frobnicate(key)` | x | x |\n"
        violations = check_required_table(guide)
        assert violations == ["required-members table: row 'frobnicate' is not a method Driver declares"]

    def test_param_drift_flagged(self) -> None:
        # The drift this gate exists for: a protocol parameter the table never followed.
        real = _required_section()
        drifted = real.replace("`stat(key, follow_links)`", "`stat(key)`")
        assert drifted != real, "guide fixture no longer contains the expected stat row"
        violations = check_required_table(drifted)
        assert len(violations) == 1
        assert "stat" in violations[0]
        assert "follow_links" in violations[0]

    def test_real_guide_table_is_clean(self) -> None:
        assert check_required_table(_required_section()) == []

    def test_subheading_terminates_scan(self) -> None:
        # A #### subheading must end the table scan: the bogus row below it
        # must NOT be absorbed (and therefore not reported as stale).
        guide = _required_section() + "#### aside\n\n| `bogus_member(key)` | x | x |\n"
        assert not any("bogus_member" in v for v in check_required_table(guide))

    def test_escaped_pipe_stays_in_its_cell(self) -> None:
        # `bytes \| BinaryIO` in a later cell must not split the row's first cell.
        guide = _required_section().replace("| `BinaryIO` |", "| `bytes \\| BinaryIO` |")
        assert check_required_table(guide) == []


class TestAttributesTable:
    def test_missing_table_flagged(self) -> None:
        violations = check_attributes_table("# A guide with no table\n")
        assert len(violations) == 1
        assert "table not found" in violations[0]

    def test_missing_attribute_flagged(self) -> None:
        violations = check_attributes_table(_without_row(_attributes_section(), "| `namespace`"))
        assert violations == ["attributes table: missing row for 'namespace'"]

    def test_missing_optional_attribute_flagged(self) -> None:
        violations = check_attributes_table(_without_row(_attributes_section(), "| `stream_catch`"))
        assert violations == ["attributes table: missing row for 'stream_catch'"]

    def test_stale_attribute_flagged(self) -> None:
        guide = _attributes_section() + "| `frobnicate` | x | x |\n"
        violations = check_attributes_table(guide)
        assert violations == ["attributes table: row 'frobnicate' is not a Driver attribute"]

    def test_optional_attribute_dropped_from_driver_docstring_flagged(self, monkeypatch) -> None:
        from remote_store.drivers import Driver

        monkeypatch.setattr(Driver, "__doc__", (Driver.__doc__ or "").replace("``size_probe``", "size_probe"))
        violations = check_attributes_table(_attributes_section())
        assert len(violations) == 1
        assert "'size_probe' is no longer named in the Driver docstring" in violations[0]

    def test_real_guide_table_is_clean(self) -> None:
        assert check_attributes_table(_attributes_section()) == []


class TestProtocolsTable:
    def test_missing_table_flagged(self) -> None:
        violations = check_protocols_table("# A guide with no table\n")
        assert len(violations) == 1
        assert "table not found" in violations[0]

    def test_missing_protocol_flagged(self) -> None:
        violations = check_protocols_table(_without_row(_protocols_section(), "| [`SupportsGlob`]"))
        assert violations == ["protocols table: missing row for 'SupportsGlob'"]

    def test_stale_protocol_flagged(self) -> None:
        guide = _protocols_section() + "| `SupportsTeleport` | `teleport(key)` | x |\n"
        violations = check_protocols_table(guide)
        assert violations == [
            "protocols table: row 'SupportsTeleport' is not a Supports* protocol in remote_store.drivers"
        ]

    def test_param_drift_flagged(self) -> None:
        real = _protocols_section()
        drifted = real.replace("`get_range(key, offset, length)`", "`get_range(key, offset)`")
        assert drifted != real, "guide fixture no longer contains the expected get_range row"
        violations = check_protocols_table(drifted)
        assert len(violations) == 1
        assert "SupportsRangeRead.get_range" in violations[0]
        assert "length" in violations[0]

    def test_wrong_member_flagged(self) -> None:
        real = _protocols_section()
        drifted = real.replace("`copy(src, dst, overwrite)`", "`duplicate(src, dst, overwrite)`")
        assert drifted != real, "guide fixture no longer contains the expected copy row"
        violations = check_protocols_table(drifted)
        assert violations == ["protocols table: 'SupportsCopy' row names 'duplicate', not one of its methods ['copy']"]

    def test_real_guide_table_is_clean(self) -> None:
        assert check_protocols_table(_protocols_section()) == []


def _capability_section() -> str:
    return _section("## Step 2: Declare capabilities", "The other capabilities need only")


class TestCapabilityTable:
    def test_real_guide_table_is_clean(self) -> None:
        assert check_capability_table(_capability_section()) == []

    def test_missing_table_flagged(self) -> None:
        violations = check_capability_table("# no table\n")
        assert violations == ["capability table not found (header '| Capability | Backed by |' missing?)"]

    def test_a_backer_construction_refuses_is_flagged(self) -> None:
        # The guide must not teach a declaration the kernel refuses at construction.
        real = _capability_section()
        drifted = real.replace("| `GLOB` | `SupportsGlob` |", "| `GLOB` | nothing, the kernel globs |")
        assert drifted != real, "guide fixture no longer contains the expected GLOB row"
        assert check_capability_table(drifted) == [
            "capability table: 'GLOB' names [], but construction accepts ['SupportsGlob']"
        ]

    def test_a_missing_backer_is_flagged(self) -> None:
        real = _capability_section()
        drifted = real.replace("`SupportsAtomicMove`, `SupportsRename` or `SupportsCopy`", "`SupportsCopy`")
        assert drifted != real, "guide fixture no longer contains the expected MOVE row"
        violations = check_capability_table(drifted)
        assert violations == [
            "capability table: 'MOVE' names ['SupportsCopy'], "
            "but construction accepts ['SupportsAtomicMove', 'SupportsCopy', 'SupportsRename']"
        ]

    def test_a_dropped_rename_qualifier_is_flagged(self) -> None:
        # A rename that does not replace backs MOVE but not ATOMIC_MOVE.
        real = _capability_section()
        drifted = real.replace(
            "`SupportsAtomicMove`, or `SupportsRename` with `rename_replaces = True` |",
            "`SupportsAtomicMove` or `SupportsRename` |",
        )
        assert drifted != real, "guide fixture no longer contains the expected ATOMIC_MOVE row"
        assert check_capability_table(drifted) == [
            "capability table: 'ATOMIC_MOVE' row omits 'rename_replaces = True', "
            "which construction needs for SupportsRename"
        ]

    def test_a_wrong_put_is_atomic_setting_is_flagged(self) -> None:
        real = _capability_section()
        drifted = real.replace("| `put_is_atomic = True`,", "| `put_is_atomic = False`,")
        assert drifted != real, "guide fixture no longer contains the expected ATOMIC_WRITE row"
        assert check_capability_table(drifted) == [
            "capability table: 'ATOMIC_WRITE' row omits 'put_is_atomic = True', "
            "which construction needs for put_is_atomic"
        ]

    def test_a_missing_capability_row_is_flagged(self) -> None:
        violations = check_capability_table(_without_row(_capability_section(), "| `COPY`"))
        assert violations == ["capability table: missing row for 'COPY'"]

    def test_an_ungated_capability_row_is_flagged(self) -> None:
        guide = _capability_section().replace(
            "| `GLOB` | `SupportsGlob` |", "| `GLOB` | `SupportsGlob` |\n| `READ` | `SupportsRangeRead` |"
        )
        violations = check_capability_table(guide)
        assert violations == ["capability table: row 'READ' is not a capability construction gates"]


class TestDuplicateRows:
    def test_a_wrong_duplicate_before_the_right_row_is_flagged(self) -> None:
        # dict() keeps the last row, so without this a wrong first row would pass.
        guide = _required_section().replace("| `put(", "| `put(key)` | x | x |\n| `put(", 1)
        assert "required-members table: duplicate row for 'put'" in check_required_table(guide)

    def test_duplicate_protocol_and_attribute_rows_are_flagged(self) -> None:
        protocols = _protocols_section()
        row = next(line for line in protocols.splitlines() if line.startswith("| [`SupportsGlob`]"))
        assert "protocols table: duplicate row for 'SupportsGlob'" in check_protocols_table(protocols + row + "\n")
        attributes = _attributes_section()
        arow = next(line for line in attributes.splitlines() if line.startswith("| `namespace`"))
        assert "attributes table: duplicate row for 'namespace'" in check_attributes_table(attributes + arow + "\n")


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
        guide = (
            '```toml\n[backend.x]\ntransport = "http"\nconcurrency = "thread_safe"\n```\n'
            '```toml\n[fixture.x]\nbackend = "x"\nstage = 9\nkind = "real-local"\n```\n'
        )
        violations = check_registration_toml(guide, self._ROOT)
        assert len(violations) == 1
        assert "stage" in violations[0]

    def test_unknown_backend_family_flagged(self) -> None:
        guide = '```toml\n[fixture.x]\nbackend = "no-such-family"\nstage = 1\nkind = "real-local"\n```\n'
        violations = check_registration_toml(guide, self._ROOT)
        assert len(violations) == 1
        assert "not declared in backends.toml" in violations[0]

    def test_loader_type_checks_apply(self) -> None:
        # Routed through the loader's own parser, so its type checks fire too.
        guide = '```toml\n[backend.x]\ntransport = "http"\nconcurrency = "thread_safe"\nsources = "oops"\n```\n'
        violations = check_registration_toml(guide, self._ROOT)
        assert len(violations) == 1
        assert "list of strings" in violations[0]

    def test_zero_fences_flagged(self) -> None:
        violations = check_registration_toml("no fences here", self._ROOT)
        assert len(violations) == 1
        assert "no ```toml fences" in violations[0]

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
        drifted = _GUIDE.read_text(encoding="utf-8").replace("`stat(key, follow_links)`", "`stat(key)`")
        target = tmp_path / "guide.md"
        target.write_text(drifted, encoding="utf-8")
        assert main([str(target)]) == 1
        assert "follow_links" in capsys.readouterr().err

    # One drift case per remaining check, so silently unwiring any check
    # from main() fails a test (each drift is invisible to the others).

    def test_attributes_table_drift_fails_main(self, tmp_path: Path, capsys) -> None:
        text = _GUIDE.read_text(encoding="utf-8")
        drifted = "\n".join(line for line in text.splitlines() if not line.startswith("| `put_is_atomic`"))
        assert drifted != text, "guide fixture no longer contains the put_is_atomic row"
        target = tmp_path / "guide.md"
        target.write_text(drifted, encoding="utf-8")
        assert main([str(target)]) == 1
        assert "put_is_atomic" in capsys.readouterr().err

    def test_protocols_table_drift_fails_main(self, tmp_path: Path, capsys) -> None:
        text = _GUIDE.read_text(encoding="utf-8")
        drifted = "\n".join(line for line in text.splitlines() if not line.startswith("| [`SupportsFolderStats`]"))
        assert drifted != text, "guide fixture no longer contains the SupportsFolderStats row"
        target = tmp_path / "guide.md"
        target.write_text(drifted, encoding="utf-8")
        assert main([str(target)]) == 1
        assert "SupportsFolderStats" in capsys.readouterr().err

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
