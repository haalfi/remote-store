"""Unit tests for scripts/mutation_report.py (BK-273 rolling-issue reconciler).

The script gives mutation.yml its durable-TODO surface: every ``mutate-<scope>``
leg records a per-scope outcome JSON (``record``), and the summary job
classifies them and reconciles a single rolling ``[mutation]`` GitHub issue
(``reconcile``). The model under test, decided per audit-018 C-DECISION / A3:

* harness/implementation failure (the run broke) -> issue opened/updated;
  the mutate leg is already red.
* surviving mutants -> advisory only; they never trigger the issue.
* all clear on a full run -> comment-and-close; a partial (single-scope)
  dispatch never closes the issue.

Tests run hermetically: ``gh`` calls are captured by replacing the module's
``_gh`` helper, never executed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mutation_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("mutation_report", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("mutation_report", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _gremlins_json(tmp_path: Path, survived: int = 0, zapped: int = 10, timeout: int = 0, error: int = 0) -> Path:
    path = tmp_path / "gremlins.json"
    total = survived + zapped + timeout + error
    path.write_text(
        json.dumps(
            {
                "summary": {
                    "total": total,
                    "zapped": zapped,
                    "survived": survived,
                    "timeout": timeout,
                    "error": error,
                    "pardoned": 0,
                    "percentage": 100.0 * zapped / total if total else 0.0,
                },
                "files": {},
                "results": [],
            }
        )
    )
    return path


def _write_outcome(dir_: Path, scope: str, job_status: str, counts: dict | None) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{scope}.json").write_text(json.dumps({"scope": scope, "job_status": job_status, "counts": counts}))


class _GhRecorder:
    """Capture gh invocations; serve canned ``issue list`` responses."""

    def __init__(self, open_issue: int | None = None):
        self.calls: list[tuple[str, ...]] = []
        self._open_issue = open_issue

    def __call__(self, *args: str, input_: str | None = None):
        self.calls.append(args)

        class Result:
            stdout = ""

        result = Result()
        if args[:2] == ("issue", "list"):
            issues = []
            if self._open_issue is not None:
                issues = [{"number": self._open_issue, "title": _TITLE}]
            result.stdout = json.dumps(issues)
        if input_ is not None:
            self.calls[-1] = (*args, f"<<{input_}>>")
        return result

    def verbs(self) -> list[str]:
        return [c[1] for c in self.calls if c[0] == "issue"]


_TITLE = "[mutation] Weekly mutation run health"


# --------------------------------------------------------------------------- #
# record
# --------------------------------------------------------------------------- #


class TestRecord:
    def test_green_leg_records_counts_from_gremlins_report(self, tmp_path):
        report = _gremlins_json(tmp_path, survived=2, zapped=8)
        out = tmp_path / "outcome" / "core-store.json"
        rc = _mod.main(
            ["record", "core-store", "--job-status", "success", "--gremlins-json", str(report), "--out", str(out)]
        )
        assert rc == 0
        data = json.loads(out.read_text())
        assert data["scope"] == "core-store"
        assert data["job_status"] == "success"
        assert data["counts"]["survived"] == 2
        assert data["counts"]["zapped"] == 8

    def test_missing_gremlins_report_records_null_counts(self, tmp_path):
        out = tmp_path / "outcome" / "core-store.json"
        rc = _mod.main(
            [
                "record",
                "core-store",
                "--job-status",
                "failure",
                "--gremlins-json",
                str(tmp_path / "absent.json"),
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        data = json.loads(out.read_text())
        assert data["job_status"] == "failure"
        assert data["counts"] is None

    def test_corrupt_gremlins_report_on_green_job_fails_the_leg(self, tmp_path):
        # A truncated/garbage report on an otherwise-green leg still writes
        # the outcome (counts: null -> harness failure downstream) but exits
        # non-zero, so the leg goes red and the "harness failure -> issue AND
        # red run" invariant holds.
        report = tmp_path / "gremlins.json"
        report.write_text("{not json")
        out = tmp_path / "outcome" / "core-store.json"
        rc = _mod.main(
            ["record", "core-store", "--job-status", "success", "--gremlins-json", str(report), "--out", str(out)]
        )
        assert rc == 1
        assert json.loads(out.read_text())["counts"] is None

    def test_missing_gremlins_report_on_green_job_fails_the_leg(self, tmp_path):
        # Same invariant for the silent case: pytest exited 0 but no report
        # exists (e.g. the plugin moved its output path). The leg must fail
        # loudly rather than letting the issue fire on a green run.
        out = tmp_path / "outcome" / "core-store.json"
        rc = _mod.main(
            [
                "record",
                "core-store",
                "--job-status",
                "success",
                "--gremlins-json",
                str(tmp_path / "absent.json"),
                "--out",
                str(out),
            ]
        )
        assert rc == 1
        data = json.loads(out.read_text())
        assert data["job_status"] == "success"
        assert data["counts"] is None


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #


class TestClassify:
    def test_red_job_is_harness_failure(self):
        scopes = _mod.classify_scopes(["a"], {"a": {"scope": "a", "job_status": "failure", "counts": None}})
        assert scopes["a"]["status"] == "harness_failure"
        assert "failure" in scopes["a"]["reason"]

    def test_cancelled_job_is_harness_failure(self):
        scopes = _mod.classify_scopes(["a"], {"a": {"scope": "a", "job_status": "cancelled", "counts": None}})
        assert scopes["a"]["status"] == "harness_failure"

    def test_green_job_without_report_is_harness_failure(self):
        # pytest-gremlins exits 0 on survivors, so a green leg that wrote no
        # JSON report means the reporting half of the harness broke silently.
        scopes = _mod.classify_scopes(["a"], {"a": {"scope": "a", "job_status": "success", "counts": None}})
        assert scopes["a"]["status"] == "harness_failure"
        assert "report" in scopes["a"]["reason"]

    def test_missing_outcome_for_expected_scope_is_harness_failure(self):
        scopes = _mod.classify_scopes(
            ["a", "b"], {"a": {"scope": "a", "job_status": "success", "counts": {"survived": 0}}}
        )
        assert scopes["b"]["status"] == "harness_failure"
        assert "outcome" in scopes["b"]["reason"]

    def test_survivors_on_green_job_are_advisory(self):
        scopes = _mod.classify_scopes(
            ["a"], {"a": {"scope": "a", "job_status": "success", "counts": {"survived": 3, "zapped": 7}}}
        )
        assert scopes["a"]["status"] == "survivors"

    def test_green_job_full_kill_is_ok(self):
        scopes = _mod.classify_scopes(
            ["a"], {"a": {"scope": "a", "job_status": "success", "counts": {"survived": 0, "zapped": 10}}}
        )
        assert scopes["a"]["status"] == "ok"


# --------------------------------------------------------------------------- #
# body rendering
# --------------------------------------------------------------------------- #


class TestRenderBody:
    def test_harness_failures_listed_with_reason(self):
        scopes = _mod.classify_scopes(["a"], {"a": {"scope": "a", "job_status": "failure", "counts": None}})
        body = _mod.render_body(scopes, run_url="https://example.test/run/1", full_run=True)
        assert "Harness / implementation failures" in body
        assert "`a`" in body
        assert "https://example.test/run/1" in body

    def test_survivors_section_is_marked_advisory_and_not_a_trigger(self):
        scopes = _mod.classify_scopes(
            ["a", "b"],
            {
                "a": {"scope": "a", "job_status": "failure", "counts": None},
                "b": {"scope": "b", "job_status": "success", "counts": {"survived": 2, "zapped": 8}},
            },
        )
        body = _mod.render_body(scopes, run_url="u", full_run=True)
        assert "advisory" in body
        assert "never open" in body  # the body states survivors do not trigger the issue
        assert "`b`" in body

    def test_clear_scopes_listed(self):
        scopes = _mod.classify_scopes(
            ["a", "b"],
            {
                "a": {"scope": "a", "job_status": "failure", "counts": None},
                "b": {"scope": "b", "job_status": "success", "counts": {"survived": 0}},
            },
        )
        body = _mod.render_body(scopes, run_url="u", full_run=True)
        assert "Clear" in body
        assert "`b`" in body

    def test_partial_run_is_flagged_in_body(self):
        scopes = _mod.classify_scopes(["a"], {"a": {"scope": "a", "job_status": "failure", "counts": None}})
        body = _mod.render_body(scopes, run_url="u", full_run=False)
        assert "partial" in body.lower()


# --------------------------------------------------------------------------- #
# reconcile
# --------------------------------------------------------------------------- #


def _reconcile(tmp_path, monkeypatch, *, gh: _GhRecorder, scopes_json: str, full_run: str = "true") -> int:
    monkeypatch.setattr(_mod, "_gh", gh)
    return _mod.main(
        [
            "reconcile",
            str(tmp_path / "outcomes"),
            "--repo",
            "haalfi/remote-store",
            "--run-url",
            "https://example.test/run/1",
            "--title",
            _TITLE,
            "--scopes",
            scopes_json,
            "--full-run",
            full_run,
        ]
    )


class TestReconcile:
    def test_harness_failure_creates_issue_when_none_open(self, tmp_path, monkeypatch):
        _write_outcome(tmp_path / "outcomes", "a", "failure", None)
        gh = _GhRecorder(open_issue=None)
        assert _reconcile(tmp_path, monkeypatch, gh=gh, scopes_json='["a"]') == 0
        assert "create" in gh.verbs()

    def test_harness_failure_updates_existing_issue(self, tmp_path, monkeypatch):
        _write_outcome(tmp_path / "outcomes", "a", "failure", None)
        gh = _GhRecorder(open_issue=42)
        assert _reconcile(tmp_path, monkeypatch, gh=gh, scopes_json='["a"]') == 0
        assert "edit" in gh.verbs()
        assert "create" not in gh.verbs()

    def test_survivors_alone_do_not_open_an_issue(self, tmp_path, monkeypatch):
        _write_outcome(tmp_path / "outcomes", "a", "success", {"survived": 3, "zapped": 7})
        gh = _GhRecorder(open_issue=None)
        assert _reconcile(tmp_path, monkeypatch, gh=gh, scopes_json='["a"]') == 0
        assert "create" not in gh.verbs()
        assert "edit" not in gh.verbs()

    def test_all_clear_full_run_closes_open_issue_with_comment(self, tmp_path, monkeypatch):
        _write_outcome(tmp_path / "outcomes", "a", "success", {"survived": 0, "zapped": 10})
        gh = _GhRecorder(open_issue=42)
        assert _reconcile(tmp_path, monkeypatch, gh=gh, scopes_json='["a"]') == 0
        assert "comment" in gh.verbs()
        assert "close" in gh.verbs()

    def test_all_clear_partial_run_never_closes(self, tmp_path, monkeypatch):
        # A single-scope dispatch cannot vouch for the other scopes — the
        # deliberate divergence from drift_report's regenerate-everything model.
        _write_outcome(tmp_path / "outcomes", "a", "success", {"survived": 0, "zapped": 10})
        gh = _GhRecorder(open_issue=42)
        assert _reconcile(tmp_path, monkeypatch, gh=gh, scopes_json='["a"]', full_run="false") == 0
        assert "close" not in gh.verbs()
        assert "comment" not in gh.verbs()

    def test_all_clear_no_open_issue_is_noop(self, tmp_path, monkeypatch):
        _write_outcome(tmp_path / "outcomes", "a", "success", {"survived": 0, "zapped": 10})
        gh = _GhRecorder(open_issue=None)
        assert _reconcile(tmp_path, monkeypatch, gh=gh, scopes_json='["a"]') == 0
        assert gh.verbs() == ["list"]

    def test_setup_failure_no_scopes_no_outcomes_opens_issue(self, tmp_path, monkeypatch):
        # The 05-09 class: setup died, so there is no scope list and no
        # outcome artifacts at all. The run still broke — issue required.
        (tmp_path / "outcomes").mkdir()
        gh = _GhRecorder(open_issue=None)
        assert _reconcile(tmp_path, monkeypatch, gh=gh, scopes_json="") == 0
        assert "create" in gh.verbs()

    def test_step_summary_table_appended_when_env_set(self, tmp_path, monkeypatch):
        _write_outcome(tmp_path / "outcomes", "a", "success", {"survived": 2, "zapped": 8, "timeout": 0, "error": 0})
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        gh = _GhRecorder(open_issue=None)
        assert _reconcile(tmp_path, monkeypatch, gh=gh, scopes_json='["a"]') == 0
        text = summary.read_text()
        assert "| Scope |" in text
        assert "`a`" in text
        assert "2" in text  # survived count is in the table, not just job.status
