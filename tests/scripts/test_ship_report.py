"""Unit tests for scripts/ship_report.py.

RFC-0015 D4 makes this script the only producer of the `/ship` Step 5 report and
the trace's ``review:`` block. Two things therefore have to hold, and they are
what this suite is mostly about.

**The classification must be the classifier's.** ``TestReuse`` pins that the
module's ``origin``, ``triage`` and round ordering are
``sdd/rfcs/rfc-0015-findings.py``'s function objects, not same-named local
copies. Two implementations of "which round is this finding in" would eventually
disagree, and RFC-0015's acceptance criterion is measured with one of them — so
a name-only equality here would be exactly the weak assertion that lets the
divergence in.

**The CI verdict must not read `skipped` as failure or `pending` as green.**
``TestCiVerdict`` runs the reducer over the shape actually measured on this
repo: 39 runs on one commit, 15 of them ``skipped``, several names repeated.
That shape is the reason the reducer exists, so it is the fixture.

Offline by construction: every ``gh`` reach is monkeypatched. The one thing
these tests cannot cover is whether the REST endpoints still answer in the shape
assumed — ``_gh_wrapped`` exists because ``commits/<sha>/check-runs`` wraps its
array in an object while the comment endpoints do not, and only a live call can
say that is still true.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ship_report.py"
_CLASSIFIER = Path(__file__).resolve().parents[2] / "sdd" / "rfcs" / "rfc-0015-findings.py"


def _load():
    spec = importlib.util.spec_from_file_location("ship_report", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("ship_report", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _run(name: str, conclusion: str | None, status: str = "completed", completed_at: str = "2026-09-01T00:00:00Z"):
    return {"name": name, "conclusion": conclusion, "status": status, "completed_at": completed_at}


@pytest.fixture
def data() -> dict:
    """One collected report, shaped as ``collect`` returns it."""
    return {
        "pr": 1025,
        "title": "BK-378: Build D1 and D4",
        "head": "abcdef1234567890",
        "base_ref": "origin/master",
        "state": "open",
        "submissions": 2,
        "findings": 3,
        "unsubmitted_reviews": 0,
        "by_round": [
            {
                "round": 1,
                "findings": 2,
                "origin": {"original": 2},
                "triage": {"must-fix": 2},
                "duration_hours": 1.5,
            },
            {
                "round": 2,
                "findings": 1,
                "origin": {"loop-introduced": 1},
                "triage": {"refuted": 1},
                "duration_hours": 0.25,
            },
        ],
        "rows": [
            {
                "round": 1,
                "path": "scripts/a.py",
                "line": 12,
                "origin": "original",
                "triage": "must-fix",
                "artifact": "code",
                "record": False,
            },
            {
                "round": 1,
                "path": "scripts/a.py",
                "line": None,
                "origin": "unclassifiable-file",
                "triage": "must-fix",
                "artifact": "code",
                "record": False,
            },
            {
                "round": 2,
                "path": "sdd/BACKLOG.md",
                "line": 3,
                "origin": "loop-introduced",
                "triage": "refuted",
                "artifact": "prose",
                "record": True,
            },
        ],
        "per_file": {"scripts/a.py": 2, "sdd/BACKLOG.md": 1},
        "changed_files": ["scripts/a.py", "sdd/BACKLOG.md", "tests/scripts/test_a.py"],
        "untouched_files": ["tests/scripts/test_a.py"],
        "review_driven_commits": [
            ("0123456789abcdef", 1, "BK-378: fix round 1"),
        ],
        "ci": {
            "verdict": "GREEN",
            "counts": {"skipped": 3, "success": 5},
            "failed": [],
            "pending": [],
            "total_runs": 9,
            "distinct_names": 8,
        },
    }


class TestReuse:
    """CLAUDE.md principle 4: the classifier is imported, never reimplemented."""

    def test_origin_and_triage_are_the_classifiers_objects(self) -> None:
        spec = importlib.util.spec_from_file_location("rfc0015_findings_probe", _CLASSIFIER)
        assert spec is not None
        assert spec.loader is not None
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)  # type: ignore[union-attr]

        # Same source file, so the code objects must match byte for byte. A
        # local copy would differ even if it were a perfect transcription today.
        for name in ("origin", "triage", "artifact_class", "is_record"):
            assert getattr(_mod.fnd, name).__code__.co_code == getattr(reference, name).__code__.co_code

    def test_the_module_defines_no_classifier_of_its_own(self) -> None:
        source = _SCRIPT.read_text(encoding="utf-8")
        for name in ("def origin(", "def triage(", "def artifact_class(", "def is_record("):
            assert name not in source, f"{name} is the classifier's; import it"

    def test_loading_a_missing_classifier_is_loud(self, tmp_path: Path) -> None:
        """No silent fallback: a quiet reimplementation is the defect this prevents."""
        with pytest.raises((RuntimeError, FileNotFoundError)):
            _mod._load_classifier(tmp_path / "not-here.py")


class TestCiVerdict:
    """The shape measured on this repo, not an idealised one."""

    def test_skipped_runs_do_not_make_the_head_red(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runs = [_run(f"skipped-{i}", "skipped") for i in range(15)] + [_run(f"ok-{i}", "success") for i in range(5)]
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        verdict = _mod.ci_verdict("deadbeef")
        assert verdict["verdict"] == "GREEN"
        assert verdict["counts"] == {"skipped": 15, "success": 5}
        assert verdict["failed"] == []

    @pytest.mark.parametrize("conclusion", ["failure", "timed_out", "cancelled", "action_required"])
    def test_a_bad_conclusion_is_red_and_named(self, monkeypatch: pytest.MonkeyPatch, conclusion: str) -> None:
        runs = [_run("ok", "success"), _run("lint", conclusion)]
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        verdict = _mod.ci_verdict("deadbeef")
        assert verdict["verdict"] == "RED"
        assert verdict["failed"] == ["lint"]

    def test_a_running_matrix_is_pending_not_green(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """/ship's own rule. Reporting this as green is how a loop closes on unread CI."""
        runs = [_run("ok", "success"), _run("test", None, status="in_progress", completed_at="")]
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        verdict = _mod.ci_verdict("deadbeef")
        assert verdict["verdict"] == "PENDING"
        assert verdict["pending"] == ["test"]

    def test_a_failure_outranks_a_pending(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runs = [_run("lint", "failure"), _run("test", None, status="queued", completed_at="")]
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        assert _mod.ci_verdict("deadbeef")["verdict"] == "RED"

    def test_a_rerun_name_reduces_to_the_latest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Names repeat on a re-run; counting both would double-report an old failure."""
        runs = [
            _run("test", "failure", completed_at="2026-09-01T00:00:00Z"),
            _run("test", "success", completed_at="2026-09-02T00:00:00Z"),
        ]
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        verdict = _mod.ci_verdict("deadbeef")
        assert verdict["verdict"] == "GREEN"
        assert verdict["distinct_names"] == 1
        assert verdict["total_runs"] == 2

    def test_no_checks_is_its_own_verdict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Distinct from green: nothing ran, so nothing passed."""
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: [])
        assert _mod.ci_verdict("deadbeef")["verdict"] == "NO CHECKS"


class TestReviewDrivenCommits:
    """The trace's review_rounds value, on the origin tag's own boundary."""

    @staticmethod
    def _log(monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> None:
        class _Result:
            stdout = "\n".join(lines) + "\n"

        monkeypatch.setattr(_mod.fnd, "_git", lambda *a, **k: _Result())

    def test_only_commits_after_the_first_review_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._log(
            monkeypatch,
            ["ccc\x00300\x00fix: round 2", "bbb\x00200\x00fix: round 1", "aaa\x00100\x00BK-378: implement"],
        )
        out = _mod.review_driven_commits("origin/master", "HEAD", 150)
        assert [sha for sha, _at, _s in out] == ["bbb", "ccc"]

    def test_the_result_is_oldest_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """git log is newest-first; a reader follows the loop forwards."""
        self._log(monkeypatch, ["ccc\x00300\x00third", "bbb\x00200\x00second"])
        assert [s for _sha, _at, s in _mod.review_driven_commits("origin/master", "HEAD", 100)] == [
            "second",
            "third",
        ]

    def test_no_review_yet_means_no_review_driven_commits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._log(monkeypatch, ["aaa\x00100\x00BK-378: implement"])
        assert _mod.review_driven_commits("origin/master", "HEAD", None) == []

    def test_a_subject_containing_nulls_is_not_truncated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """split(sep, 2) keeps a subject with a stray separator intact."""
        self._log(monkeypatch, ["aaa\x00300\x00fix: a\x00b subject"])
        (_sha, _at, subject) = _mod.review_driven_commits("origin/master", "HEAD", 100)[0]
        assert subject == "fix: a\x00b subject"

    def test_a_commit_exactly_at_the_boundary_is_not_review_driven(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Strictly later, matching origin()'s `authored < first_review_ts` split."""
        self._log(monkeypatch, ["aaa\x00200\x00at the boundary"])
        assert _mod.review_driven_commits("origin/master", "HEAD", 200) == []


class TestTraceBlock:
    """The block is pasted verbatim, so its shape is the contract."""

    def test_review_rounds_stays_findable_by_the_rounds_script(self, data: dict) -> None:
        """rfc-0015-rounds.py reads the field with a line-start anchor.

        It is amended in this change to tolerate leading whitespace; this test
        pins the other half — that the field is at a plain two-space indent and
        not nested deeper, where no reasonable anchor would find it.
        """
        block = _mod.trace_block(data)
        assert "\n  review_rounds: 1\n" in block

    def test_review_rounds_is_the_commit_count(self, data: dict) -> None:
        data["review_driven_commits"] = [("a" * 40, 1, "one"), ("b" * 40, 2, "two")]
        assert "\n  review_rounds: 2\n" in _mod.trace_block(data)

    def test_the_block_is_valid_yaml_and_round_trips(self, data: dict) -> None:
        import yaml

        parsed = yaml.safe_load(_mod.trace_block(data))
        assert set(parsed) == {"review"}
        review = parsed["review"]
        assert review["review_rounds"] == 1
        assert review["submissions"] == 2
        assert review["findings"] == 3
        assert review["by_round"][0]["origin"] == {"original": 2}
        assert review["by_file"] == [
            {"path": "scripts/a.py", "findings": 2},
            {"path": "sdd/BACKLOG.md", "findings": 1},
        ]
        assert review["untouched_files"] == ["tests/scripts/test_a.py"]
        assert review["ci"]["verdict"] == "GREEN"

    def test_empty_collections_stay_valid_yaml(self, data: dict) -> None:
        import yaml

        data["untouched_files"] = []
        data["review_driven_commits"] = []
        review = yaml.safe_load(_mod.trace_block(data))["review"]
        assert review["untouched_files"] == []
        assert review["review_driven_commits"] == []
        assert review["review_rounds"] == 0

    def test_a_subject_with_a_quote_survives_yaml(self, data: dict) -> None:
        import yaml

        data["review_driven_commits"] = [("a" * 40, 1, "fix: don't break it")]
        review = yaml.safe_load(_mod.trace_block(data))["review"]
        assert review["review_driven_commits"][0]["subject"] == "fix: don't break it"

    def test_an_all_digit_short_sha_stays_a_string(self, data: dict) -> None:
        """Regression: `3153683` unquoted parses back as an *integer*.

        Caught by `check_traces.py` the first time this block was validated
        against the schema — which is the schema/script pair working as the
        drift gate the `review:` description claims it is. A subject or path
        can hit the same class, so all four scalars go through `_q`.
        """
        import yaml

        data["review_driven_commits"] = [("3153683abcdef", 1, "fix: a round")]
        review = yaml.safe_load(_mod.trace_block(data))["review"]
        assert review["review_driven_commits"][0]["sha"] == "3153683"
        assert isinstance(review["review_driven_commits"][0]["sha"], str)

    def test_a_subject_with_a_backslash_round_trips(self, data: dict) -> None:
        """`%r` would have failed this: YAML single quotes do not process escapes."""
        import yaml

        data["review_driven_commits"] = [("a" * 40, 1, r"fix: match a\b in the regex")]
        review = yaml.safe_load(_mod.trace_block(data))["review"]
        assert review["review_driven_commits"][0]["subject"] == r"fix: match a\b in the regex"

    def test_a_path_with_a_colon_round_trips(self, data: dict) -> None:
        import yaml

        data["per_file"] = {"docs-src/guides/a: b.md": 1}
        review = yaml.safe_load(_mod.trace_block(data))["review"]
        assert review["by_file"][0]["path"] == "docs-src/guides/a: b.md"

    def test_the_block_validates_against_the_trace_schema(self, data: dict) -> None:
        """The pair is a drift gate, not a convention — so pin it from this side too.

        `_schema.yml`'s `review:` object is `additionalProperties: false`, so a
        field added to the emitter without a schema property fails here as well
        as in `check_traces.py`.
        """
        import yaml
        from jsonschema.validators import validator_for

        schema_path = Path(__file__).resolve().parents[2] / "sdd" / "traces" / "_schema.yml"
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        review_schema = schema["properties"]["review"]
        validator = validator_for(schema)(review_schema)
        errors = sorted(validator.iter_errors(yaml.safe_load(_mod.trace_block(data))["review"]), key=str)
        assert errors == [], "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)

    def test_the_block_names_its_derivation(self, data: dict) -> None:
        """CLAUDE.md principle 9: the figures say what produced them."""
        block = _mod.trace_block(data)
        assert "hatch run ship-report 1025" in block
        assert "Do not hand-edit" in block


class TestStep5Report:
    def test_it_carries_every_section_step_5_requires(self, data: dict) -> None:
        report = _mod.step5_report(data)
        for heading in (
            "## Rounds and findings",
            "## Per-file distribution",
            "## Origin tag per finding",
            "## Review-driven commits",
            "## CI on the head",
            "## Trace `review:` block",
        ):
            assert heading in report

    def test_untouched_files_are_named_not_counted(self, data: dict) -> None:
        """The brief needs the names; an adjective is what the recipe replaced."""
        report = _mod.step5_report(data)
        assert "`tests/scripts/test_a.py`" in report
        assert "1 of 3 changed files" in report

    def test_a_file_level_finding_renders_without_a_line(self, data: dict) -> None:
        report = _mod.step5_report(data)
        assert "| 1 | `scripts/a.py` | — | unclassifiable-file | must-fix |" in report

    def test_failed_and_pending_checks_are_named(self, data: dict) -> None:
        data["ci"] = {
            "verdict": "RED",
            "counts": {"failure": 1, "pending": 1, "success": 1},
            "failed": ["test (3.10)"],
            "pending": ["docs"],
            "total_runs": 3,
            "distinct_names": 3,
        }
        report = _mod.step5_report(data)
        assert "- FAILED: `test (3.10)`" in report
        assert "- PENDING: `docs`" in report

    def test_unsubmitted_reviews_are_reported_not_hidden(self, data: dict) -> None:
        data["unsubmitted_reviews"] = 2
        assert "2 review(s) had no `submitted_at`" in _mod.step5_report(data)

    def test_the_report_embeds_the_trace_block(self, data: dict) -> None:
        assert _mod.trace_block(data).rstrip("\n") in _mod.step5_report(data)


class TestPaging:
    """The wrapped-array reader, which exists because one endpoint differs."""

    def test_it_walks_until_a_short_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pages = {1: {"check_runs": [{"n": i} for i in range(100)]}, 2: {"check_runs": [{"n": 100}]}}
        calls: list[str] = []

        def fake(path: str):
            calls.append(path)
            return pages[int(path.rsplit("page=", 1)[1])]

        monkeypatch.setattr(_mod, "_gh_one", fake)
        rows = _mod._gh_wrapped("commits/x/check-runs", "check_runs")
        assert len(rows) == 101
        assert len(calls) == 2

    def test_a_full_first_page_is_never_assumed_complete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A page of exactly per_page rows means there is another — the cursor bug."""
        pages = {1: {"check_runs": [{"n": i} for i in range(100)]}, 2: {"check_runs": []}}
        monkeypatch.setattr(_mod, "_gh_one", lambda path: pages[int(path.rsplit("page=", 1)[1])])
        assert len(_mod._gh_wrapped("commits/x/check-runs", "check_runs")) == 100

    def test_a_missing_key_yields_nothing_rather_than_raising(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_mod, "_gh_one", lambda path: {"total_count": 0})
        assert _mod._gh_wrapped("commits/x/check-runs", "check_runs") == []
