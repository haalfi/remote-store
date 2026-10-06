"""BUG-215: run_mutate guarantees a report for a zero-candidate scope.

pytest-gremlins writes no JSON report when a scope's target files contain
zero mutation candidates — the plugin returns from ``pytest_terminal_summary``
before the report write. ``mutation_report.py record`` then reads the absent
report on an otherwise-green leg as a silent reporting break (counts ``None``
-> harness failure), turning the weekly mutation run red forever for a scope
that simply has nothing to mutate (e.g. ``ext-glob``: no operators, no
literals, only a value-less ``return``).

``run_mutate.py`` closes the gap by synthesising the canonical all-zero report
the plugin would have written for an empty score — but only when the scope is
positively confirmed to have zero candidates (via pytest-gremlins' own
transformer), so a genuine reporting break (gremlins exist, no report) still
fails the leg.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_mutate.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_mutate", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("run_mutate", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


class TestEnsureReportForEmptyScope:
    def test_synthesises_empty_report_on_green_zero_candidate_scope(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "_scope_has_no_mutation_candidates", lambda scope: True)
        report = tmp_path / "gremlins.json"
        _mod._ensure_report_for_empty_scope(SimpleNamespace(targets=["x.py"]), returncode=0, report_path=report)
        data = json.loads(report.read_text())
        assert data["summary"]["zapped"] == 0
        assert data["summary"]["survived"] == 0
        assert data["summary"]["timeout"] == 0
        assert data["summary"]["error"] == 0

    def test_synthesised_report_classifies_as_ok(self, tmp_path, monkeypatch):
        # Cross-check the contract with the consumer: the synthesised report
        # must make mutation_report.py classify the scope as clean, not as a
        # survivor or a harness failure.
        monkeypatch.setattr(_mod, "_scope_has_no_mutation_candidates", lambda scope: True)
        report = tmp_path / "gremlins.json"
        _mod._ensure_report_for_empty_scope(SimpleNamespace(targets=["x.py"]), returncode=0, report_path=report)

        spec = importlib.util.spec_from_file_location(
            "mutation_report", Path(__file__).resolve().parents[2] / "scripts" / "mutation_report.py"
        )
        assert spec is not None
        assert spec.loader is not None
        mr = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("mutation_report", mr)
        spec.loader.exec_module(mr)
        counts = mr._load_counts(report)
        classified = mr.classify_scopes(["s"], {"s": {"scope": "s", "job_status": "success", "counts": counts}})
        assert classified["s"]["status"] == "ok"

    def test_does_not_write_when_leg_is_red(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "_scope_has_no_mutation_candidates", lambda scope: True)
        report = tmp_path / "gremlins.json"
        _mod._ensure_report_for_empty_scope(SimpleNamespace(targets=["x.py"]), returncode=1, report_path=report)
        assert not report.exists()

    def test_does_not_overwrite_an_existing_report(self, tmp_path, monkeypatch):
        # A real run wrote a report (gremlins existed); never clobber it.
        monkeypatch.setattr(_mod, "_scope_has_no_mutation_candidates", lambda scope: True)
        report = tmp_path / "gremlins.json"
        report.write_text('{"summary": {"zapped": 5, "survived": 1}}')
        _mod._ensure_report_for_empty_scope(SimpleNamespace(targets=["x.py"]), returncode=0, report_path=report)
        assert json.loads(report.read_text())["summary"]["zapped"] == 5

    def test_does_not_write_when_scope_has_candidates(self, tmp_path, monkeypatch):
        # The genuine reporting-break case: gremlins exist but no report was
        # written. Leave the file absent so record() fails the leg as before.
        monkeypatch.setattr(_mod, "_scope_has_no_mutation_candidates", lambda scope: False)
        report = tmp_path / "gremlins.json"
        _mod._ensure_report_for_empty_scope(SimpleNamespace(targets=["x.py"]), returncode=0, report_path=report)
        assert not report.exists()


class TestPytestArgPassthrough:
    """BUG-303: gremlins flags reach pytest on argv, not via PYTEST_ADDOPTS.

    Before pytest-gremlins 1.11.0 a ``--gremlin-*`` flag in ``PYTEST_ADDOPTS``
    broke the plugin's coverage pre-scan, so every gremlin fell back to the
    full test set (fixed upstream in #568). ``run_mutate.py`` forwards trailing
    arguments onto the pytest command line, which works on every version.
    """

    def _run_main(self, monkeypatch, argv: list[str]) -> list[str]:
        seen: list[list[str]] = []

        def fake_run(cmd, check):
            seen.append(cmd)
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(_mod.subprocess, "run", fake_run)
        monkeypatch.setattr(_mod, "_ensure_report_for_empty_scope", lambda scope, rc: None)
        monkeypatch.setattr(sys, "argv", ["run_mutate.py", *argv])
        assert _mod.main() == 0
        assert len(seen) == 1
        return seen[0]

    def test_trailing_args_are_appended_to_pytest_argv(self, monkeypatch):
        scope = next(iter(_mod.SCOPES))
        cmd = self._run_main(monkeypatch, [scope, "--gremlin-report=html,json", "--gremlin-workers=4"])
        assert cmd[:3] == [sys.executable, "-m", "pytest"]
        assert cmd[-2:] == ["--gremlin-report=html,json", "--gremlin-workers=4"]
        assert "--gremlins" in cmd

    def test_no_trailing_args_leaves_argv_unchanged(self, monkeypatch):
        scope = next(iter(_mod.SCOPES))
        cmd = self._run_main(monkeypatch, [scope])
        assert cmd == [sys.executable, *_mod._build_pytest_argv(scope)]

    def test_prefix_of_own_option_is_forwarded_not_abbreviated(self, monkeypatch):
        # `--co` is pytest's collect-only and a prefix of `--container-needs`;
        # argparse's default abbreviation matching would swallow it.
        scope = next(iter(_mod.SCOPES))
        cmd = self._run_main(monkeypatch, [scope, "--co"])
        assert cmd[-1] == "--co"


class TestWorkflowKeepsGremlinsFlagsOffAddopts:
    """BUG-303: the defect lived in mutation.yml, so pin the workflow itself.

    Before pytest-gremlins 1.11.0, a ``--gremlin*`` token in the mutate step's
    ``PYTEST_ADDOPTS`` silently turned coverage-guided selection off. The
    report flags stay on the ``run_mutate.py`` command line regardless.
    """

    _WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "mutation.yml"

    def _mutate_step(self) -> dict:
        yaml = pytest.importorskip("yaml")
        steps = yaml.safe_load(self._WORKFLOW.read_text(encoding="utf-8"))["jobs"]["mutate"]["steps"]
        matches = [s for s in steps if "run_mutate.py" in s.get("run", "")]
        assert len(matches) == 1, "expected exactly one step invoking run_mutate.py"
        return matches[0]

    def test_pytest_addopts_carries_no_gremlins_flag(self):
        addopts = self._mutate_step().get("env", {}).get("PYTEST_ADDOPTS", "")
        assert "gremlin" not in addopts

    def test_report_flags_are_on_the_command_line(self):
        run = self._mutate_step()["run"]
        assert "--gremlin-report=" in run
        assert "--gremlins-html-dir=" in run

    def test_plugin_warnings_are_shown_not_fatal(self):
        # The project's filterwarnings escalates warnings to errors; without
        # this filter the plugin's "no data" UserWarning failed a leg (run 45).
        assert "-W default::UserWarning:pytest_gremlins.plugin" in self._mutate_step()["run"]

    def test_sftp_scopes_get_one_worker(self):
        step = self._mutate_step()
        workers = step["env"]["WORKERS"]
        assert "sftp-scopes" in workers
        assert "'1'" in workers
        assert '--gremlin-workers="$WORKERS"' in step["run"]


class TestScopeCandidateDiscovery:
    """Asks pytest-gremlins' own transformer, so it matches what the plugin
    counts and goes red if the plugin moves the internals
    ``_scope_has_no_mutation_candidates`` imports. Runs in CI via the
    ``tooling-tests`` job, which installs pytest-gremlins alongside ``.[dev]``
    for exactly this reason (ci.yml). Skips only where the plugin is genuinely
    absent: bare introspection runners, and any environment installed without
    ``.[mutate]``."""

    def test_glob_has_no_mutation_candidates(self):
        pytest.importorskip("pytest_gremlins")
        scope = SimpleNamespace(targets=["src/remote_store/ext/glob.py"])
        assert _mod._scope_has_no_mutation_candidates(scope) is True

    def test_yaml_has_mutation_candidates(self):
        pytest.importorskip("pytest_gremlins")
        scope = SimpleNamespace(targets=["src/remote_store/ext/yaml.py"])
        assert _mod._scope_has_no_mutation_candidates(scope) is False
