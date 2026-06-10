"""Unit tests for scripts/check_ci_inventory.py (BK-275 inventory gate).

The gate enforces that every workflow on a family trigger
(``on.schedule`` / ``on.pull_request_review``) is named in the
CI-operations handbook. Tests run against hermetic tmp_path fixtures, not
the live repo, so they stay stable as workflows are added.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_ci_inventory.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_ci_inventory", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_ci_inventory", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _write_workflow(directory: Path, name: str, on_block: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(f"name: {name}\non:\n{on_block}\njobs:\n  noop:\n    runs-on: ubuntu-latest\n")


# --------------------------------------------------------------------------- #
# Family detection
# --------------------------------------------------------------------------- #


class TestFamilyDetection:
    def test_schedule_is_family(self, tmp_path):
        _write_workflow(tmp_path, "sweep.yml", '  schedule:\n    - cron: "0 5 * * 6"')
        assert _mod.family_workflows(tmp_path) == ["sweep.yml"]

    def test_pull_request_review_is_family(self, tmp_path):
        _write_workflow(tmp_path, "automerge.yml", "  pull_request_review:\n    types: [submitted]")
        assert _mod.family_workflows(tmp_path) == ["automerge.yml"]

    def test_push_and_pull_request_are_not_family(self, tmp_path):
        _write_workflow(tmp_path, "ci.yml", "  push:\n    branches: [master]\n  pull_request:")
        assert _mod.family_workflows(tmp_path) == []

    def test_yaml_extension_is_also_judged(self, tmp_path):
        # GitHub Actions honours both .yml and .yaml; a scheduled guard
        # committed as .yaml must not slip past the gate.
        _write_workflow(tmp_path, "sweep.yaml", '  schedule:\n    - cron: "0 5 * * 6"')
        assert _mod.family_workflows(tmp_path) == ["sweep.yaml"]

    def test_yaml_on_boolean_key_gotcha(self, tmp_path):
        # PyYAML parses the bare ``on:`` mapping key as the bool True, not "on".
        # The detector must still find the schedule trigger underneath.
        _write_workflow(tmp_path, "sweep.yml", '  schedule:\n    - cron: "0 6 * * 1"')
        on = _mod._on_node(tmp_path / "sweep.yml")
        assert "schedule" in _mod._triggers(on)


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


class TestCheck:
    def test_documented_family_workflow_passes(self, tmp_path):
        wf = tmp_path / "workflows"
        _write_workflow(wf, "drift-guard.yml", '  schedule:\n    - cron: "0 7 * * 1"')
        handbook = tmp_path / "CI-OPERATIONS.md"
        handbook.write_text("| `drift-guard.yml` | Mon 07:00 UTC | rolling Issue | yes | /drift |\n")

        assert _mod.check(wf, handbook) == []

    def test_undocumented_family_workflow_fails(self, tmp_path):
        wf = tmp_path / "workflows"
        _write_workflow(wf, "mutation.yml", '  schedule:\n    - cron: "0 5 * * 6"')
        handbook = tmp_path / "CI-OPERATIONS.md"
        handbook.write_text("| `drift-guard.yml` | Mon 07:00 UTC | rolling Issue | yes |\n")

        errors = _mod.check(wf, handbook)
        assert len(errors) == 1
        assert "mutation.yml" in errors[0]
        assert "schedule" in errors[0]

    def test_exception_workflow_named_anywhere_passes(self, tmp_path):
        # A family workflow documented only as an exception (no rolling issue)
        # still satisfies the presence gate.
        wf = tmp_path / "workflows"
        _write_workflow(wf, "codeql.yml", '  push:\n  schedule:\n    - cron: "0 6 * * 1"')
        handbook = tmp_path / "CI-OPERATIONS.md"
        handbook.write_text("### Exceptions\n\n- `codeql.yml` reports to the Security tab.\n")

        assert _mod.check(wf, handbook) == []

    def test_non_family_workflow_need_not_be_documented(self, tmp_path):
        wf = tmp_path / "workflows"
        _write_workflow(wf, "ci.yml", "  push:\n  pull_request:")
        handbook = tmp_path / "CI-OPERATIONS.md"
        handbook.write_text("(no rows)\n")

        assert _mod.check(wf, handbook) == []

    def test_missing_handbook_fails(self, tmp_path):
        wf = tmp_path / "workflows"
        _write_workflow(wf, "sweep.yml", '  schedule:\n    - cron: "0 5 * * 6"')
        errors = _mod.check(wf, tmp_path / "absent.md")
        assert len(errors) == 1
        assert "not found" in errors[0]


# --------------------------------------------------------------------------- #
# The live repo must pass its own gate
# --------------------------------------------------------------------------- #


def test_repo_inventory_is_honest():
    assert _mod.check(_mod.WORKFLOWS_DIR, _mod.HANDBOOK) == []
