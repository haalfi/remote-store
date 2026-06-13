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


class TestScopeCandidateDiscovery:
    """Asks pytest-gremlins' own transformer, so it matches what the plugin
    counts. Skips when the plugin is absent (bare introspection runners and
    the <3.11 matrix do not install it)."""

    def test_glob_has_no_mutation_candidates(self):
        pytest.importorskip("pytest_gremlins")
        scope = SimpleNamespace(targets=["src/remote_store/ext/glob.py"])
        assert _mod._scope_has_no_mutation_candidates(scope) is True

    def test_yaml_has_mutation_candidates(self):
        pytest.importorskip("pytest_gremlins")
        scope = SimpleNamespace(targets=["src/remote_store/ext/yaml.py"])
        assert _mod._scope_has_no_mutation_candidates(scope) is False
