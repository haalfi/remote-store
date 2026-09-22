"""Unit tests for scripts/ship_report.py.

RFC-0015 D4 makes this script the only producer of the `/ship` Step 5 report and
the trace's ``review:`` block. Two things therefore have to hold, and they are
what this suite is mostly about.

**The classification must be the classifier's.** Two implementations of "which
round is this finding in" would eventually disagree, and RFC-0015's acceptance
criterion is measured with one of them. ``TestReuse`` pins the *path* and that
this module defines no classifier of its own; the reuse itself is pinned
**behaviourally** by ``TestCollect``, which stubs ``fnd.origin`` and asserts the
tag flows through while ``fnd.triage`` runs unstubbed. A code-object comparison
against a probe loaded from the same file proved nothing, and that is what stood
here.

**The CI verdict must not read `skipped` as failure or `pending` as green.**
``test_the_measured_shape_reduces_correctly`` assembles the shape actually
measured on this repo — 39 runs on one commit, 15 ``skipped``, four names
repeated — because that shape is the reason the reducer exists. Stated because
it is easy to describe a fixture and not build one: the surrounding tests use
small focused fixtures, and none of them has repeated names *and* the skipped
bulk together.

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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "ship_report.py"
_CLASSIFIER = _REPO_ROOT / "sdd" / "rfcs" / "rfc-0015-findings.py"
_ROUNDS = _REPO_ROOT / "sdd" / "rfcs" / "rfc-0015-rounds.py"
_SCHEMA = _REPO_ROOT / "sdd" / "traces" / "_schema.yml"


def _schema_gaps(node: dict, path: str) -> list[str]:
    """Every object below `node` that leaves a property optional, or is not closed.

    Module-level rather than nested in its test so a synthetic schema can reach
    the not-closed branch: the real schema closes every object, so that branch
    is unreachable from it and a mutation deleting it survived.

    The recursion runs for **every** object with `properties`, not only closed
    ones. Descending only into closed objects left the same hole one layer down
    — an object added without `additionalProperties: false` would be neither
    reported nor entered, and its whole subtree invisible.
    """
    gaps: list[str] = []
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            if node.get("additionalProperties") is not False:
                gaps.append(f"{path}: not closed (no additionalProperties: false)")
            missing = set(props) - set(node.get("required") or [])
            if missing:
                gaps.append(f"{path}: optional {sorted(missing)}")
            for name, child in props.items():
                gaps += _schema_gaps(child, f"{path}.{name}")
        items = node.get("items")
        if isinstance(items, dict):
            gaps += _schema_gaps(items, f"{path}[]")
    return gaps


def _load_rounds():
    """Import `rfc-0015-rounds.py`, whose filename is not a Python identifier.

    The same `spec_from_file_location` route `ship_report` uses for the
    classifier. Without it the anchor that reads this emitter's output is
    pinned by nothing executable anywhere in the repo.
    """
    spec = importlib.util.spec_from_file_location("rfc0015_rounds", _ROUNDS)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _load():
    spec = importlib.util.spec_from_file_location("ship_report", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("ship_report", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _run(
    name: str,
    conclusion: str | None,
    status: str = "completed",
    completed_at: str | None = "2026-09-01T00:00:00Z",
    started_at: str = "2026-09-01T00:00:00Z",
):
    """One check-run row, in the shape the endpoint actually returns.

    `started_at` is not decoration. GitHub sends `completed_at: null` with a
    populated `started_at` while a run is `queued` or `in_progress`, and
    `ci_verdict` reduces on `completed_at or started_at`. A helper that could
    only emit `completed_at=""` made a running re-run sort *oldest* and lose the
    latest-per-name reduction, when in reality it sorts newest and wins — so the
    case the reducer exists for was not merely untested but unreachable.
    """
    return {
        "name": name,
        "conclusion": conclusion,
        "status": status,
        "completed_at": completed_at,
        "started_at": started_at,
    }


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

    def test_the_classifier_is_loaded_from_the_rfcs_own_file(self) -> None:
        """Pins the path, which is the only thing a path check can pin.

        An earlier form compared `_mod.fnd`'s code objects against a probe
        loaded from the same path and called that proof of reuse — true by
        construction, and it never looked at `_mod.origin`, which is what a
        local copy would have been. The reuse is pinned *behaviourally* by
        `TestCollect`, which stubs `fnd.origin` and asserts the tag flows
        through while `fnd.triage` runs unstubbed.
        """
        assert _mod._CLASSIFIER == _CLASSIFIER
        assert _mod._CLASSIFIER.is_file()
        for name in ("origin", "triage", "artifact_class", "is_record", "_gh", "_ts", "_git", "ensure_commit"):
            assert hasattr(_mod.fnd, name), f"{name} is not resolvable on the imported classifier"

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
        runs = [_run("ok", "success"), _run("test", None, status="in_progress", completed_at=None)]
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        verdict = _mod.ci_verdict("deadbeef")
        assert verdict["verdict"] == "PENDING"
        assert verdict["pending"] == ["test"]

    def test_a_failure_outranks_a_pending(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runs = [_run("lint", "failure"), _run("test", None, status="queued", completed_at=None)]
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        assert _mod.ci_verdict("deadbeef")["verdict"] == "RED"

    def test_a_failed_check_now_re_running_is_pending_not_red(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The case the reducer exists for, and the one the old helper could not express.

        A name that completed `failure`, then started again: the running row has
        `completed_at: null` and a later `started_at`, so it is the latest and
        the head is PENDING. Reading the stale failure instead would send the
        loop into a fix pass for a check that is already re-running.
        """
        runs = [
            _run("test", "failure", completed_at="2026-09-01T00:00:00Z", started_at="2026-09-01T00:00:00Z"),
            _run("test", None, status="in_progress", completed_at=None, started_at="2026-09-02T00:00:00Z"),
        ]
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        verdict = _mod.ci_verdict("deadbeef")
        assert verdict["verdict"] == "PENDING"
        assert verdict["pending"] == ["test"]
        assert verdict["failed"] == []

    @pytest.mark.parametrize("newest_first", [False, True], ids=["oldest-first", "newest-first"])
    def test_a_rerun_name_reduces_to_the_latest(self, monkeypatch: pytest.MonkeyPatch, newest_first: bool) -> None:
        """Names repeat on a re-run; counting both would double-report an old failure.

        Parametrised over both row orders deliberately. With the fixture only
        oldest-first, an implementation that dropped the timestamp comparison
        entirely (`latest[name] = run`, unconditionally) passed — and the
        endpoint actually returns results `started_at` **descending**, so the
        one ordering the old fixture used was the one that never occurs.
        """
        runs = [
            _run("test", "failure", completed_at="2026-09-01T00:00:00Z", started_at="2026-09-01T00:00:00Z"),
            _run("test", "success", completed_at="2026-09-02T00:00:00Z", started_at="2026-09-02T00:00:00Z"),
        ]
        if newest_first:
            runs.reverse()
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        verdict = _mod.ci_verdict("deadbeef")
        assert verdict["verdict"] == "GREEN"
        assert verdict["failed"] == []
        assert verdict["distinct_names"] == 1
        assert verdict["total_runs"] == 2

    def test_no_checks_is_its_own_verdict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Distinct from green: nothing ran, so nothing passed."""
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: [])
        assert _mod.ci_verdict("deadbeef")["verdict"] == "NO CHECKS"

    def test_the_measured_shape_reduces_correctly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The shape the reducer exists for, assembled rather than described.

        Measured on this repo: 39 runs on one commit, 15 `skipped`, several
        names repeated. The module docstring cited that shape as the reason for
        the reducer and said "so it is the fixture" while no such fixture
        existed — the nearest had 20 distinct names and no repetition.
        """
        runs = [_run(f"skipped-{i}", "skipped") for i in range(15)]
        runs += [_run(f"ok-{i}", "success") for i in range(20)]
        # Four names repeated, each an older row plus a newer one.
        for i in range(4):
            runs.append(
                _run(f"ok-{i}", "failure", completed_at="2026-08-01T00:00:00Z", started_at="2026-08-01T00:00:00Z")
            )
        assert len(runs) == 39
        monkeypatch.setattr(_mod, "_gh_wrapped", lambda *a, **k: runs)
        verdict = _mod.ci_verdict("deadbeef")
        assert verdict["total_runs"] == 39
        assert verdict["distinct_names"] == 35
        assert verdict["verdict"] == "GREEN", "the stale failures must lose the reduction"
        assert verdict["counts"] == {"skipped": 15, "success": 20}


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

    def test_a_commit_at_the_boundary_is_review_driven(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The tie belongs to the loop, on both sides of the pair.

        `origin()` splits on `authored < first_review_ts`, which selects
        **original** — so at equality it returns `loop-introduced`. A `>` here
        excluded the same commit from `review_rounds`, making the two disagree
        at exactly the tie the docstrings said could not happen. This assertion
        is the pair's only guard, and an earlier form of it pinned the wrong
        side while its docstring claimed to rule the divergence out.
        """
        self._log(monkeypatch, ["aaa\x00200\x00at the boundary"])
        assert [s for _sha, _at, s in _mod.review_driven_commits("origin/master", "HEAD", 200)] == ["at the boundary"]

    def test_the_boundary_agrees_with_the_classifiers_split(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Calls the real `fnd.origin`, so the pair genuinely cannot drift apart.

        An earlier form re-spelled the classifier's expression
        (`not (authored < first_review_ts)`) and called that "the pair". It was
        not: sabotaging `fnd.origin` to return a constant left this test green
        while the two diverged at every timestamp. The only coupling that holds
        is invoking the function.

        `origin()` blames a line at a commit, so its `_git` is stubbed to answer
        the two calls it makes for a non-pre-existing line: `blame` naming a
        commit, then `merge-base --is-ancestor` failing, then `show` giving the
        author date.
        """
        first_review_ts = 200

        def classify(authored: int) -> str:
            def fake_git(*args: str, **kwargs):
                class _R:
                    returncode = 0
                    stdout = ""

                result = _R()
                if args[0] == "blame":
                    result.stdout = "cafebabe 1) a line\n"
                elif args[0] == "merge-base":
                    result.returncode = 1  # not reachable from master -> not pre-existing
                elif args[0] == "show":
                    result.stdout = f"{authored}\n"
                return result

            monkeypatch.setattr(_mod.fnd, "_git", fake_git)
            monkeypatch.setattr(_mod.fnd, "ensure_commit", lambda sha: None)
            row = {
                "subject_type": "line",
                "side": "RIGHT",
                "original_line": 1,
                "original_commit_id": "c" * 40,
                "path": "a.py",
            }
            return _mod.fnd.origin(row, first_review_ts)

        for authored in (199, 200, 201):
            origin_verdict = classify(authored)
            self._log(monkeypatch, [f"aaa\x00{authored}\x00subject"])
            counted = bool(_mod.review_driven_commits("origin/master", "HEAD", first_review_ts))
            assert counted is (origin_verdict == "loop-introduced"), (
                f"authored={authored}: origin() says {origin_verdict!r}, review_driven_commits "
                f"{'counted' if counted else 'skipped'} it"
            )


class TestTraceBlock:
    """The block is pasted verbatim, so its shape is the contract."""

    def test_review_rounds_stays_findable_by_the_rounds_script(self, data: dict) -> None:
        """Exercises the **real** anchor, not a transcription of it.

        `rfc-0015-rounds.py` derives RFC-0015 Table 1's before/after populations
        from this field. Asserting the emitter's literal spelling pinned only
        one half of a two-file coupling: reverting the anchor would silently
        empty the entire "after" side and leave the suite green, which is the
        shape DRIFT-RULES Rule 8 is about. Importing it covers both halves with
        one assertion.
        """
        rounds = _load_rounds()
        match = rounds.RX.search(_mod.trace_block(data))
        assert match is not None, "the rounds script cannot find review_rounds in the emitted block"
        assert int(match.group(1)) == 1

    def test_the_anchor_ignores_prose_inside_a_folded_scalar(self, data: dict) -> None:
        """The defect a free `[ \\t]*` indent introduced, and the reason it is bounded.

        `sdd/traces/bk-338-review-roster.yml:421` carries
        `review_rounds: 4 and a per-round review phase…` as prose at a ten-space
        indent. A BK-378-onward trace has no top-level field, so under a free
        indent that prose line would be the first match and the script would
        report it — a silent wrong integer feeding a median, in place of the
        loud exclusion the widening was meant to prevent.
        """
        rounds = _load_rounds()
        prose = "          review_rounds: 4 and a per-round review phase, and a scan\n"
        assert rounds.RX.search(prose) is None
        # Both real spellings still read: the emitter's two-space indent, and
        # the legacy corpus's top-level field.
        assert rounds.RX.search("  review_rounds: 9\n").group(1) == "9"
        assert rounds.RX.search("review_rounds: 4\n").group(1) == "4"

    def test_the_legacy_corpus_reads_identically_under_the_anchor(self) -> None:
        """The amendment must not disturb any existing reading.

        Asserted over whatever the corpus holds rather than against a pinned
        total, so it cannot go stale on the next trace. (Measured while writing:
        324 traces, 261 carrying the field.)
        """
        import re as _re

        rounds = _load_rounds()
        legacy = _re.compile(r"^review_rounds:\s*(\d+)", _re.M)
        traces = sorted((_REPO_ROOT / "sdd" / "traces").glob("[!_]*.yml"))
        assert traces, "no traces found; the corpus glob is wrong"
        for path in traces:
            text = path.read_text(encoding="utf-8")
            old, new = legacy.search(text), rounds.RX.search(text)
            assert (old is None) == (new is None), f"{path.name}: the anchors disagree on presence"
            if old is not None:
                assert old.group(1) == new.group(1), f"{path.name}: the anchors disagree on value"

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
        """Every sequence key, not just the two that happened to have a guard.

        An earlier form of this test covered `untouched_files` and
        `review_driven_commits` — which were exactly the two the emitter
        guarded — so it could not see that `by_round` and `by_file` serialised
        as YAML *null*. A test written from the implementation tests the
        implementation.
        """
        import yaml

        data["by_round"] = []
        data["per_file"] = {}
        data["untouched_files"] = []
        data["review_driven_commits"] = []
        review = yaml.safe_load(_mod.trace_block(data))["review"]
        for key in ("by_round", "by_file", "untouched_files", "review_driven_commits"):
            assert review[key] == [], f"{key} is {review[key]!r}, not an empty list"
        assert review["review_rounds"] == 0

    def test_an_all_empty_block_still_validates(self, data: dict) -> None:
        """The ordinary shape of a PR whose review posted no inline findings."""
        import yaml
        from jsonschema.validators import validator_for

        data["by_round"] = []
        data["per_file"] = {}
        data["untouched_files"] = []
        data["review_driven_commits"] = []
        schema_path = Path(__file__).resolve().parents[2] / "sdd" / "traces" / "_schema.yml"
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        validator = validator_for(schema)(schema["properties"]["review"])
        errors = sorted(validator.iter_errors(yaml.safe_load(_mod.trace_block(data))["review"]), key=str)
        assert errors == [], "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)

    def test_the_schema_requires_every_field_the_emitter_writes(self) -> None:
        """Closes the drift gate's other direction, at **every** depth.

        `additionalProperties: false` catches a field added without a property.
        Nothing caught one removed, because five of nine top-level fields were
        optional. Asserting only the top level left the same hole one layer
        down — `ci` had no `required:` at all, so `ci: {}` validated and an
        emitter that stopped writing the verdict passed; `by_round` items
        required two of their five. Both survived a mutation run against the
        top-level-only form of this test, which is why it walks now.
        """
        import yaml

        schema_path = Path(__file__).resolve().parents[2] / "sdd" / "traces" / "_schema.yml"
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        assert _schema_gaps(schema["properties"]["review"], "review") == []

    def test_the_walk_reports_an_object_that_is_not_closed(self) -> None:
        """The walk's own guard, over a synthetic schema.

        The real schema closes every object, so this branch is unreachable from
        it — and a mutation deleting the branch survived a run against the live
        schema alone. Without this, the next `ci`-shaped key added without
        `additionalProperties: false` would be neither reported nor descended
        into, and its whole subtree would be invisible.
        """
        open_object = {"properties": {"a": {"type": "string"}}, "required": ["a"]}
        assert _schema_gaps(open_object, "x") == ["x: not closed (no additionalProperties: false)"]

    def test_the_walk_descends_into_an_open_objects_subtree(self) -> None:
        """Reporting is not enough — the subtree beneath an open object must still be read."""
        nested = {
            "properties": {
                "inner": {"properties": {"b": {"type": "string"}}, "additionalProperties": False},
            },
            "required": ["inner"],
        }
        gaps = _schema_gaps(nested, "x")
        assert "x: not closed (no additionalProperties: false)" in gaps
        assert "x.inner: optional ['b']" in gaps

    @pytest.mark.parametrize(
        "dropped",
        [
            "derivation",
            "review_rounds",
            "submissions",
            "findings",
            "by_round",
            "by_file",
            "untouched_files",
            "review_driven_commits",
            "ci",
        ],
    )
    def test_dropping_any_emitted_field_fails_the_schema(self, data: dict, dropped: str) -> None:
        import yaml
        from jsonschema.validators import validator_for

        schema_path = Path(__file__).resolve().parents[2] / "sdd" / "traces" / "_schema.yml"
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        validator = validator_for(schema)(schema["properties"]["review"])
        block = yaml.safe_load(_mod.trace_block(data))["review"]
        del block[dropped]
        assert list(validator.iter_errors(block)), f"dropping {dropped} validated"

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

    def test_a_null_duration_is_yaml_null_not_the_string_None(self, data: dict) -> None:
        """Regression: a bare `None` reads back as the *string* "None".

        The schema declares `duration_hours: [number, "null"]`, so the nullable
        branch could never validate — and it is reachable: a review with no
        `submitted_at` leaves the duration unset, which the module docstring says
        is reported rather than hidden. The earlier tests all used real numbers,
        so nothing exercised it.
        """
        import yaml

        data["by_round"][0]["duration_hours"] = None
        review = yaml.safe_load(_mod.trace_block(data))["review"]
        assert review["by_round"][0]["duration_hours"] is None

    def test_a_null_duration_still_validates_against_the_schema(self, data: dict) -> None:
        import yaml
        from jsonschema.validators import validator_for

        data["by_round"][0]["duration_hours"] = None
        schema_path = Path(__file__).resolve().parents[2] / "sdd" / "traces" / "_schema.yml"
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        validator = validator_for(schema)(schema["properties"]["review"])
        errors = sorted(validator.iter_errors(yaml.safe_load(_mod.trace_block(data))["review"]), key=str)
        assert errors == [], "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)

    @pytest.mark.parametrize("verdict", ["GREEN", "RED", "PENDING", "NO CHECKS"])
    def test_every_verdict_round_trips_as_a_string(self, data: dict, verdict: str) -> None:
        """`NO CHECKS` is the interesting case — a plain scalar with a space, and
        near enough to YAML 1.1's `NO` → False coercion to pin rather than reason about.
        """
        import yaml

        data["ci"] = dict(data["ci"], verdict=verdict)
        review = yaml.safe_load(_mod.trace_block(data))["review"]
        assert review["ci"]["verdict"] == verdict
        assert isinstance(review["ci"]["verdict"], str)

    def test_the_origin_and_triage_mappings_round_trip_unquoted(self, data: dict) -> None:
        """The other unquoted scalars, which a sweep claiming `verdict` was the only one missed.

        Both keys and values of the flow mappings are interpolated straight from
        the classifier's vocabulary. Nothing breaks today — the vocabulary is
        fixed and YAML-safe — so this pins the enumeration rather than a bug,
        which is what the earlier claim should have done.
        """
        import yaml

        data["by_round"][0]["origin"] = {
            "original": 2,
            "loop-introduced": 1,
            "pre-existing": 1,
            "unclassifiable-file": 1,
            _mod.UNCLASSIFIABLE_NO_BOUNDARY: 1,
        }
        data["by_round"][0]["triage"] = {"must-fix": 3, "filed": 1, "refuted": 1, "unknown": 1}
        entry = yaml.safe_load(_mod.trace_block(data))["review"]["by_round"][0]
        assert entry["origin"]["loop-introduced"] == 1
        assert entry["origin"][_mod.UNCLASSIFIABLE_NO_BOUNDARY] == 1
        assert entry["triage"]["must-fix"] == 3
        assert all(isinstance(k, str) for k in entry["origin"])
        assert all(isinstance(k, str) for k in entry["triage"])

    def test_the_block_names_a_derivation_that_reproduces_it(self, data: dict) -> None:
        """Principle 9, and the flag is the whole of it.

        The schema declares `derivation` "re-runnable as written", and the bare
        command prints the Markdown report rather than this block — so a
        `derivation` without `--trace-block-only` names a command that produces
        the wrong artifact, in the one field whose only job is to name the right
        one.
        """
        import yaml

        block = _mod.trace_block(data)
        assert "Do not hand-edit" in block
        assert yaml.safe_load(block)["review"]["derivation"] == "hatch run ship-report 1025 --trace-block-only"

    def test_both_homes_state_the_paste_commit_offset(self) -> None:
        """The one hand-transcription failure D4 does *not* remove, stated twice.

        `review_driven_commits` reads `<base>..<head>` before the commit that
        pastes the block exists, so re-running `derivation` afterwards returns
        one more. The schema described that as a failure D4 removes until the
        closing gate read the two files against each other. It is a bound, so
        DRIFT-RULES Rule 7 puts it in the script; it is also what a trace reader
        needs, so it is in the schema — and a fix that drops either half leaves
        the other claiming a precision the pair does not have.
        """
        import yaml

        script = _SCRIPT.read_text(encoding="utf-8")
        assert "The count excludes the commit that carries it." in script

        schema = yaml.safe_load(_SCHEMA.read_text(encoding="utf-8"))
        review = schema["properties"]["review"]["properties"]
        assert "Excludes the commit that pastes this" in review["review_rounds"]["description"]
        assert "returns `review_rounds + 1`" in review["derivation"]["description"]


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


class TestRoundsWithFindings:
    """The grouping the whole report rests on, stubbed the way TestPaging stubs."""

    @staticmethod
    def _stub(monkeypatch: pytest.MonkeyPatch, comments: list[dict], reviews: list[dict]) -> None:
        def fake(path: str):
            if path.endswith("/comments"):
                return comments
            if path.endswith("/reviews"):
                return reviews
            raise AssertionError(f"unexpected endpoint {path}")

        monkeypatch.setattr(_mod.fnd, "_gh", fake)

    @staticmethod
    def _comment(cid: int, review_id: int, path: str, reply_to: int | None = None, body: str = ""):
        return {
            "id": cid,
            "pull_request_review_id": review_id,
            "path": path,
            "in_reply_to_id": reply_to,
            "created_at": f"2026-09-0{cid}T00:00:00Z",
            "body": body,
            "original_line": 1,
            "original_commit_id": "a" * 40,
        }

    def test_replies_are_not_counted_as_findings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The measured regression the docstring names: the endpoint returns both.

        An unfiltered tally reports the surface as more examined than it is, and
        the inflation is loop-dependent — one row on one PR, a doubling on
        another — so it cannot be corrected by a ratio afterwards.
        """
        comments = [
            self._comment(1, 10, "a.py"),
            self._comment(2, 10, "a.py", reply_to=1, body="Must-fix. Fixed in abc."),
            self._comment(3, 10, "b.py"),
        ]
        self._stub(monkeypatch, comments, [{"id": 10, "submitted_at": "2026-09-01T10:00:00Z"}])
        rounds, _ts, first_reply, _unsub = _mod.rounds_with_findings(1)
        assert [len(group) for group in rounds.values()] == [2]
        assert first_reply == {1: "Must-fix. Fixed in abc."}

    def test_rounds_are_ordered_by_submission_time_not_row_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Round index is submission order by construction, as the classifier defines it."""
        comments = [self._comment(1, 20, "late.py"), self._comment(2, 10, "early.py")]
        reviews = [
            {"id": 20, "submitted_at": "2026-09-02T00:00:00Z"},
            {"id": 10, "submitted_at": "2026-09-01T00:00:00Z"},
        ]
        self._stub(monkeypatch, comments, reviews)
        rounds, _ts, _fr, _unsub = _mod.rounds_with_findings(1)
        assert [group[0]["path"] for group in rounds.values()] == ["early.py", "late.py"]

    def test_a_review_without_submitted_at_sorts_last_and_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        comments = [self._comment(1, 99, "no-stamp.py"), self._comment(2, 10, "stamped.py")]
        reviews = [{"id": 10, "submitted_at": "2026-09-01T00:00:00Z"}, {"id": 99}]
        self._stub(monkeypatch, comments, reviews)
        rounds, _ts, _fr, unsubmitted = _mod.rounds_with_findings(1)
        assert unsubmitted == [99]
        assert [group[0]["path"] for group in rounds.values()] == ["stamped.py", "no-stamp.py"]

    def test_only_the_first_reply_in_a_thread_is_the_verdict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`/rvw-pr` never answers comments, so the first reply is the fix pass speaking."""
        comments = [
            self._comment(1, 10, "a.py"),
            self._comment(3, 10, "a.py", reply_to=1, body="second"),
            self._comment(2, 10, "a.py", reply_to=1, body="first"),
        ]
        self._stub(monkeypatch, comments, [{"id": 10, "submitted_at": "2026-09-01T00:00:00Z"}])
        _rounds, _ts, first_reply, _unsub = _mod.rounds_with_findings(1)
        assert first_reply[1] == "first"


class TestCollect:
    """The whole assembly, with every network reach stubbed."""

    @pytest.fixture
    def stubbed(self, monkeypatch: pytest.MonkeyPatch):
        meta = {
            "title": "BK-378: a title",
            "state": "open",
            "merged_at": None,
            "created_at": "2026-09-01T00:00:00Z",
            "head": {"sha": "b" * 40},
            "base": {"ref": "master"},
        }
        comments = [
            {
                "id": 1,
                "pull_request_review_id": 10,
                "path": "scripts/a.py",
                "in_reply_to_id": None,
                "created_at": "2026-09-01T09:00:00Z",
                "original_line": 4,
                "original_commit_id": "c" * 40,
                "body": "",
            },
            {
                "id": 2,
                "pull_request_review_id": 10,
                "path": "scripts/a.py",
                "in_reply_to_id": 1,
                "created_at": "2026-09-01T11:00:00Z",
                "body": "Must-fix. Fixed in abc.",
            },
        ]
        monkeypatch.setattr(_mod, "pr_meta", lambda pr: meta)
        monkeypatch.setattr(_mod, "changed_files", lambda pr: ["scripts/a.py", "tests/scripts/test_a.py"])
        monkeypatch.setattr(
            _mod,
            "ci_verdict",
            lambda sha: {
                "verdict": "GREEN",
                "counts": {},
                "failed": [],
                "pending": [],
                "total_runs": 0,
                "distinct_names": 0,
            },
        )
        monkeypatch.setattr(_mod, "review_driven_commits", lambda base, head, ts: [("d" * 40, 1, "fix: a round")])
        monkeypatch.setattr(_mod.fnd, "ensure_commit", lambda sha: None)
        monkeypatch.setattr(_mod.fnd, "origin", lambda row, ts: "loop-introduced")
        monkeypatch.setattr(
            _mod.fnd,
            "_gh",
            lambda path: (
                comments if path.endswith("/comments") else [{"id": 10, "submitted_at": "2026-09-01T10:00:00Z"}]
            ),
        )
        return meta

    def test_it_assembles_the_figures_the_report_states(self, stubbed) -> None:
        data = _mod.collect(1026)
        assert data["submissions"] == 1
        assert data["findings"] == 1
        assert data["per_file"] == {"scripts/a.py": 1}
        assert data["base_ref"] == "origin/master"
        assert data["by_round"][0]["triage"] == {"must-fix": 1}
        assert data["by_round"][0]["origin"] == {"loop-introduced": 1}

    def test_untouched_is_the_changed_list_minus_the_finding_paths(self, stubbed) -> None:
        data = _mod.collect(1026)
        assert data["untouched_files"] == ["tests/scripts/test_a.py"]

    def test_the_first_pass_duration_runs_from_the_prs_creation(self, stubbed) -> None:
        """Created 00:00, submitted 10:00 — the first pass has no predecessor to measure from."""
        assert _mod.collect(1026)["by_round"][0]["duration_hours"] == 10.0

    def test_a_merged_pr_reports_merged_rather_than_its_state(self, stubbed, monkeypatch) -> None:
        stubbed["merged_at"] = "2026-09-03T00:00:00Z"
        assert _mod.collect(1026)["state"] == "merged"

    def test_collect_output_renders_and_validates(self, stubbed) -> None:
        """End to end: the assembled data survives both emitters and the schema."""
        import yaml
        from jsonschema.validators import validator_for

        data = _mod.collect(1026)
        schema_path = Path(__file__).resolve().parents[2] / "sdd" / "traces" / "_schema.yml"
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        validator = validator_for(schema)(schema["properties"]["review"])
        errors = sorted(validator.iter_errors(yaml.safe_load(_mod.trace_block(data))["review"]), key=str)
        assert errors == [], "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        assert "## Per-file distribution" in _mod.step5_report(data)


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


class TestChangedFiles:
    """The minuend, whose truncation the module docstring calls invisible."""

    def test_it_reads_the_filename_key_and_uses_every_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = [{"filename": f"f{i}.py", "status": "modified"} for i in range(150)]
        monkeypatch.setattr(_mod.fnd, "_gh", lambda path: rows)
        assert _mod.changed_files(1) == [f"f{i}.py" for i in range(150)]

    def test_it_pages_through_the_shared_reader(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Delegates to the classifier's paged walk rather than fetching page one.

        A truncated changed-file list drops a file out of *both* the touched and
        untouched sets, which is invisible — unlike a truncated finding list,
        which merely over-reports neglect.
        """
        seen: list[str] = []

        def fake(path: str):
            seen.append(path)
            return [{"filename": "a.py"}]

        monkeypatch.setattr(_mod.fnd, "_gh", fake)
        _mod.changed_files(1026)
        assert seen == ["pulls/1026/files"]


class TestMain:
    """The entry point, offline — it needs no network double, only a stubbed `collect`."""

    @pytest.fixture
    def collected(self, monkeypatch: pytest.MonkeyPatch, data: dict):
        monkeypatch.setattr(_mod, "collect", lambda pr: data)
        return data

    def test_the_default_prints_the_step_5_report(self, collected, capsys: pytest.CaptureFixture[str]) -> None:
        assert _mod.main(["1025"]) == 0
        out = capsys.readouterr().out
        assert "## Per-file distribution" in out
        assert out.startswith("# /ship report")

    def test_trace_block_only_prints_the_block_and_nothing_else(
        self, collected, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert _mod.main(["1025", "--trace-block-only"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("review:")
        assert "## Per-file distribution" not in out

    def test_out_writes_the_file_and_creates_its_parent(
        self, collected, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "nested" / "dir" / "ship-report-1025.md"
        assert _mod.main(["1025", "--out", str(target)]) == 0
        assert target.read_text(encoding="utf-8").startswith("# /ship report")
        assert f"Written to {target}" in capsys.readouterr().err

    def test_out_honours_trace_block_only(self, collected, tmp_path: Path) -> None:
        target = tmp_path / "block.yml"
        assert _mod.main(["1025", "--trace-block-only", "--out", str(target)]) == 0
        assert target.read_text(encoding="utf-8").startswith("review:")


class TestNoBoundary:
    """The fifth cause: no review in the sample carries a `submitted_at`."""

    def test_findings_are_tagged_under_their_own_cause(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Not `unclassifiable-noline`, which means a null `original_line`.

        Borrowing that name made the block claim a blame failure that never
        happened, for every finding in the PR.
        """
        meta = {
            "title": "t",
            "state": "open",
            "merged_at": None,
            "created_at": "2026-09-01T00:00:00Z",
            "head": {"sha": "b" * 40},
            "base": {"ref": "master"},
        }
        comments = [
            {
                "id": 1,
                "pull_request_review_id": 10,
                "path": "scripts/a.py",
                "in_reply_to_id": None,
                "created_at": "2026-09-01T09:00:00Z",
                "original_line": 4,
                "original_commit_id": "c" * 40,
                "body": "",
            }
        ]
        monkeypatch.setattr(_mod, "pr_meta", lambda pr: meta)
        monkeypatch.setattr(_mod, "changed_files", lambda pr: ["scripts/a.py"])
        monkeypatch.setattr(
            _mod,
            "ci_verdict",
            lambda sha: {
                "verdict": "GREEN",
                "counts": {},
                "failed": [],
                "pending": [],
                "total_runs": 0,
                "distinct_names": 0,
            },
        )
        monkeypatch.setattr(_mod.fnd, "ensure_commit", lambda sha: None)
        # No review carries `submitted_at`, so there is no boundary at all.
        monkeypatch.setattr(_mod.fnd, "_gh", lambda path: comments if path.endswith("/comments") else [{"id": 10}])
        data = _mod.collect(1)
        assert data["unsubmitted_reviews"] == 1
        assert data["by_round"][0]["origin"] == {_mod.UNCLASSIFIABLE_NO_BOUNDARY: 1}
        assert data["review_driven_commits"] == []

    def test_the_tag_is_not_one_of_the_classifiers_four(self) -> None:
        assert _mod.UNCLASSIFIABLE_NO_BOUNDARY not in _mod.fnd.UNCLASSIFIABLE
