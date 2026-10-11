"""Unit tests for the token kit's phase dating (``sdd/research/token-usage/tokkit.py``).

Transcripts are synthetic ``tmp_path`` JSONL in the shape Claude Code writes.
The kit's real input, a ``/ship`` run's transcript, holds prompts and local
paths and stays outside the repo; these tests rebuild the shapes that misled
run B's phase split: a ``pr-link`` record for another PR written before the
real one opened, a probe script written before the plan was approved, a plan
rejected before one was approved, and commits run as ``git -C <dir>``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

_KIT = Path(__file__).resolve().parents[2] / "sdd" / "research" / "token-usage"
sys.path.insert(0, str(_KIT))

import tokkit  # noqa: E402

SID = "00000000-0000-0000-0000-000000000001"


def _ts(minute: int) -> str:
    return f"2026-10-10T14:{minute:02d}:00.000Z"


def _call(n: int, minute: int, *blocks) -> dict:
    usage = {"input_tokens": 1, "cache_read_input_tokens": 1000, "output_tokens": 10}
    return {
        "type": "assistant",
        "timestamp": _ts(minute),
        "message": {"id": f"m{n}", "model": "claude-opus-5-5", "usage": usage, "content": list(blocks)},
    }


def _use(tid: str, name: str, **inp) -> dict:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def _result(tid: str, minute: int, text: str, *, error: bool = False) -> dict:
    block: dict[str, object] = {"type": "tool_result", "tool_use_id": tid, "content": text}
    if error:
        block["is_error"] = True
    return {"type": "user", "timestamp": _ts(minute), "message": {"role": "user", "content": [block]}}


APPROVED = "User has approved your plan. You can now start coding."
REJECTED = "The user doesn't want to proceed with this tool use. The tool use was rejected."
ANSWERED = 'Your questions have been answered: "Scope?"="Narrow". You can now continue.'


def _run_b_shaped() -> list[dict]:
    """Calls 0-8. Plan approved before call 4; the PR is created at minute 11, before call 7."""
    return [
        {"type": "user", "timestamp": _ts(0), "message": {"role": "user", "content": "/ship BK-1"}},
        _call(0, 0, _use("q1", "AskUserQuestion", questions=[])),
        _result("q1", 1, ANSWERED),
        # A probe script written during orient: the old split ended orient here.
        _call(1, 2, _use("w1", "Write", file_path="tmp/probe.py", content="x")),
        _result("w1", 2, "ok"),
        _call(2, 3, _use("p1", "ExitPlanMode", plan="v1")),
        _result("p1", 4, REJECTED, error=True),
        _call(3, 5, _use("p2", "ExitPlanMode", plan="v2")),
        _result("p2", 6, APPROVED),
        _call(4, 7, _use("e1", "Edit", file_path="src/x.py")),
        _result("e1", 7, "ok"),
        _call(5, 8, _use("b1", "Bash", command="git -C wt commit -m 'BK-1: x'")),
        _result("b1", 8, "ok"),
        # Claude Code links the session to another PR whose branch name the worktree reused.
        {"type": "pr-link", "prNumber": 6, "timestamp": _ts(9)},
        _call(6, 10, _use("b2", "Bash", command="gh pr create --title x")),
        _result("b2", 11, "https://github.com/o/r/pull/7"),
        {"type": "pr-link", "prNumber": 7, "timestamp": _ts(11)},
        _call(7, 12, _use("b3", "PowerShell", command="git -C wt push")),
        _result("b3", 12, "ok"),
        _call(8, 13, _use("a1", "Agent", description="review round 1")),
    ]


def _write(dirpath: Path, records: list[dict]) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / f"{SID}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return path


@pytest.fixture
def kit(tmp_path, monkeypatch):
    """A transcript folder and snapshot folder; the kit reads only these."""
    transcripts = tmp_path / "transcripts"
    monkeypatch.setattr(tokkit.cm, "default_transcripts", lambda repo: [transcripts])
    tokkit.ARGS = argparse.Namespace(repo_root=tmp_path)
    return transcripts, tmp_path / "snap"


def _report(tmp_path, snap, *extra) -> dict:
    out = tmp_path / "out" / "summary.json"
    argv = ["--repo-root", str(tmp_path), "--snapshots", str(snap), "report", "--session", SID]
    tokkit.main([*argv, "--json", str(out), *extra])
    return json.loads(out.read_text(encoding="utf-8"))


def _cache_pr(snap: Path, number: int, created: str) -> None:
    (snap / SID).mkdir(parents=True, exist_ok=True)
    (snap / SID / f"pr-{number}.json").write_text(
        json.dumps({"number": number, "createdAt": created}), encoding="utf-8"
    )


class TestBashCategory:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("git commit -m x", "git commit"),
            ("git -C tmp/pr-push push -u origin a:b", "git push"),
            ('git -C "K:/a b/wt" commit -m x', "git commit"),
            ("git -c user.name=x -C wt commit -m x", "git commit"),
            ("git --no-pager -C wt log -1", "git log"),
            ("git --git-dir=.git --work-tree=. diff", "git diff"),
            ("GIT_EDITOR=true git -C wt commit", "git commit"),
            # Stripping -C must not leave its directory to be read as the subcommand.
            ("git -C tmp/pr-push cherry-pick 460ff5cea", "git"),
            # Before the word boundary this started with "git commit" and counted as a commit.
            ("git commit-tree abc", "git"),
            ("gh pr create --title x", "gh pr"),
        ],
    )
    def test_git_global_options_do_not_hide_the_subcommand(self, command, expected):
        assert tokkit.bash_cat(command) == expected


class TestEvents:
    def test_commit_and_push_via_git_dash_c_are_events_in_bash_and_powershell(self, kit):
        transcripts, _ = kit
        _, _, events = tokkit.parse_file(_write(transcripts, _run_b_shaped()))
        assert [(e["kind"], e["idx"]) for e in events if e["kind"].startswith("git")] == [
            ("git commit", 6),
            ("git push", 8),
        ]

    def test_only_an_approved_plan_and_an_answered_question_are_events(self, kit):
        transcripts, _ = kit
        _, _, events = tokkit.parse_file(_write(transcripts, _run_b_shaped()))
        marks = [(e["kind"], e["idx"]) for e in events if e["kind"] in ("plan-approved", "question-answered")]
        assert marks == [("question-answered", 1), ("plan-approved", 4)]

    def test_pr_link_is_reported_as_a_link_not_as_the_pr_opening(self, kit):
        transcripts, _ = kit
        _, _, events = tokkit.parse_file(_write(transcripts, _run_b_shaped()))
        assert [(e["kind"], e["detail"]) for e in events if e["kind"].startswith("pr")] == [
            ("pr-link", "PR #6"),
            ("pr-link", "PR #7"),
        ]


class TestPhases:
    def test_phases_cut_at_plan_approval_and_pr_creation_not_at_records(self, kit, tmp_path):
        transcripts, snap = kit
        _write(transcripts, _run_b_shaped())
        _cache_pr(snap, 7, "2026-10-10T14:11:00Z")
        s = _report(tmp_path, snap, "--pr", "7")
        assert (s["plan_end_call"], s["pr_open_call"], s["pr"]) == (4, 7, 7)
        assert {k: v["calls"] for k, v in s["phases"].items() if k != "subagents"} == {
            "orient + plan (to plan approval)": 4,
            "build (plan approval to PR open)": 3,
            "review loop (after PR open)": 2,
        }

    def test_a_pr_opened_after_the_session_leaves_no_review_phase(self, kit, tmp_path):
        transcripts, snap = kit
        _write(transcripts, _run_b_shaped())
        _cache_pr(snap, 7, "2026-10-10T15:00:00Z")
        s = _report(tmp_path, snap, "--pr", "7")
        assert s["pr_open_call"] is None
        assert "review loop (after PR open)" not in s["phases"]

    def test_without_an_approved_plan_the_first_answered_question_ends_orient(self, kit, tmp_path):
        transcripts, snap = kit
        records = [r for r in _run_b_shaped() if r.get("timestamp") not in (_ts(3), _ts(4), _ts(5), _ts(6))]
        _write(transcripts, records)
        _cache_pr(snap, 7, "2026-10-10T14:11:00Z")
        s = _report(tmp_path, snap, "--pr", "7")
        assert s["plan_end_call"] == 1

    @pytest.mark.parametrize(
        ("dropped", "plan_end", "phases"),
        [
            # No approval before PR open at all: one unsplit phase, not a cut in the review loop.
            (
                (_ts(1), _ts(6)),
                None,
                {"orient, plan and build (no plan approval found)": 7, "review loop (after PR open)": 2},
            ),
            # A question answered before PR open and a plan approved only after it: the question.
            (
                (_ts(6),),
                1,
                {
                    "orient + plan (to plan approval)": 1,
                    "build (plan approval to PR open)": 6,
                    "review loop (after PR open)": 2,
                },
            ),
        ],
        ids=["only-after-pr", "question-before-plan-after"],
    )
    def test_an_approval_after_pr_open_does_not_end_orient(self, kit, tmp_path, dropped, plan_end, phases):
        transcripts, snap = kit
        records = [r for r in _run_b_shaped() if r.get("timestamp") not in dropped]
        # The plan is approved only during the review loop, after call 8.
        _write(transcripts, [*records, _result("p2", 14, APPROVED)])
        _cache_pr(snap, 7, "2026-10-10T14:11:00Z")
        s = _report(tmp_path, snap, "--pr", "7")
        assert s["plan_end_call"] == plan_end
        assert {k: v["calls"] for k, v in s["phases"].items() if k != "subagents"} == phases

    def test_without_pr_there_is_no_review_phase_and_the_report_says_why(self, kit, tmp_path):
        transcripts, snap = kit
        _write(transcripts, _run_b_shaped())
        s = _report(tmp_path, snap)
        assert s["pr_open_call"] is None
        assert s["pr"] is None
        assert {k: v["calls"] for k, v in s["phases"].items() if k != "subagents"} == {
            "orient + plan (to plan approval)": 4,
            "build (plan approval to PR open)": 5,
        }
        assert "pass --pr" in (snap / SID / "report.md").read_text(encoding="utf-8")

    def test_without_any_approval_the_pre_pr_calls_are_one_unsplit_phase(self, kit, tmp_path):
        transcripts, snap = kit
        records = [r for r in _run_b_shaped() if r.get("timestamp") not in (_ts(1), _ts(4), _ts(6))]
        _write(transcripts, records)
        _cache_pr(snap, 7, "2026-10-10T14:11:00Z")
        s = _report(tmp_path, snap, "--pr", "7")
        assert s["plan_end_call"] is None
        assert {k: v["calls"] for k, v in s["phases"].items() if k != "subagents"} == {
            "orient, plan and build (no plan approval found)": 7,
            "review loop (after PR open)": 2,
        }


class TestUntil:
    def test_a_call_within_the_cut_second_but_after_it_is_left_out(self, kit, tmp_path):
        # As strings, "14:07:00.500Z" <= "14:07:00Z" holds: run B's hand cut at plan
        # approval kept the first build call this way.
        transcripts, snap = kit
        records = _run_b_shaped()
        records[9]["timestamp"] = "2026-10-10T14:07:00.500Z"  # call 4, the first after approval
        _write(transcripts, records)
        s = _report(tmp_path, snap, "--until", "2026-10-10T14:07:00Z")
        assert s["main_calls"] == 4

    def test_a_cut_without_an_offset_is_read_as_utc(self, kit, tmp_path):
        # Transcript timestamps end in Z; a naive cut must not fail to compare with them.
        transcripts, snap = kit
        _write(transcripts, _run_b_shaped())
        assert _report(tmp_path, snap, "--until", "2026-10-10T14:07:00")["main_calls"] == 5

    def test_a_cut_that_is_not_a_timestamp_is_a_usage_error(self, kit, tmp_path, capsys):
        transcripts, snap = kit
        _write(transcripts, _run_b_shaped())
        with pytest.raises(SystemExit) as exc:
            _report(tmp_path, snap, "--until", "yesterday")
        assert exc.value.code == 2
        assert "--until" in capsys.readouterr().err


class TestRelatedSessions:
    """A review session of the PR, opened after the main one, joins the report only through --pr."""

    def _with_review(self, transcripts: Path, prompt: str) -> None:
        _write(transcripts, _run_b_shaped())
        review = [
            {"type": "user", "timestamp": _ts(20), "message": {"role": "user", "content": prompt}},
            _call(100, 21),
            _call(101, 22),
        ]
        (transcripts / "00000000-0000-0000-0000-000000000002.jsonl").write_text(
            "\n".join(json.dumps(r) for r in review), encoding="utf-8"
        )

    def test_the_review_of_the_given_pr_is_counted(self, kit, tmp_path):
        transcripts, snap = kit
        self._with_review(transcripts, "/rvw-pr 7")
        _cache_pr(snap, 7, "2026-10-10T14:11:00Z")
        s = _report(tmp_path, snap, "--pr", "7")
        assert (s["transcripts"], s["calls"]) == (2, 9 + 2)

    @pytest.mark.parametrize("extra", [[], ["--pr", "6"]], ids=["no-pr", "pr-link-of-reused-branch"])
    def test_a_review_of_another_pr_or_without_pr_is_left_out(self, kit, tmp_path, extra):
        # PR 6 is the one the pr-link record named for the reused branch name.
        transcripts, snap = kit
        self._with_review(transcripts, "/rvw-pr 7")
        _cache_pr(snap, 6, "2026-10-10T13:00:00Z")
        s = _report(tmp_path, snap, *extra)
        assert (s["transcripts"], s["calls"]) == (1, 9)


class TestPrCreation:
    def test_created_at_is_fetched_once_with_gh_and_cached_in_the_snapshot(self, kit, tmp_path, monkeypatch):
        transcripts, snap = kit
        _write(transcripts, _run_b_shaped())
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return argparse.Namespace(stdout=json.dumps({"number": 7, "createdAt": "2026-10-10T14:11:00Z"}))

        monkeypatch.setattr(tokkit.subprocess, "run", fake_run)
        assert _report(tmp_path, snap, "--pr", "7")["pr_open_call"] == 7
        assert _report(tmp_path, snap, "--pr", "7")["pr_open_call"] == 7
        assert len(calls) == 1
        assert calls[0][:4] == ["gh", "pr", "view", "7"]
        assert json.loads((snap / SID / "pr-7.json").read_text(encoding="utf-8"))["createdAt"] == (
            "2026-10-10T14:11:00Z"
        )
