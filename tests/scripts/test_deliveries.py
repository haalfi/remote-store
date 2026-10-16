"""Unit tests for ``sdd/research/token-usage/deliveries.py``'s judgements on a transcript.

Each figure in the research record rests on one of these: which gap is a wait,
which subagent is a review pass, how many findings a pass handed back, and which
calls a session part keeps. Transcripts are synthetic ``tmp_path`` JSONL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_KIT = Path(__file__).resolve().parents[2] / "sdd" / "research" / "token-usage"
sys.path.insert(0, str(_KIT))

import deliveries  # noqa: E402


def _write(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return path


def _assistant(ts: str, content: list | None = None) -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {"content": content or []}}


def _user(ts: str, content) -> dict:
    return {"type": "user", "timestamp": ts, "message": {"content": content}}


def _call(mid: str, ts: str, tokens: int, content: list | None = None) -> dict:
    """An assistant record carrying usage: ``tokens`` fresh input tokens weigh one unit each."""
    msg = {"id": mid, "model": "claude-opus-4-6", "usage": {"input_tokens": tokens}, "content": content or []}
    return {"type": "assistant", "timestamp": ts, "message": msg}


class TestActive:
    def test_a_gap_ended_by_a_prompt_or_a_dialog_answer_is_a_wait(self, tmp_path):
        ask = {"type": "tool_use", "id": "q1", "name": "AskUserQuestion", "input": {}}
        answer = {"type": "tool_result", "tool_use_id": "q1", "content": "answered"}
        t = _write(
            tmp_path / "m.jsonl",
            [
                _assistant("2026-10-10T10:00:00Z", [ask]),
                _user("2026-10-10T10:10:00Z", [answer]),  # 10 min dialog wait
                _assistant("2026-10-10T10:10:30Z"),
                _user("2026-10-10T10:30:30Z", "next prompt"),  # 20 min prompt wait
            ],
        )
        wall, wait = deliveries.active(t, {})
        assert (wall, wait) == (1830.0, 1800.0)

    def test_a_gap_ended_by_a_notification_or_a_tool_result_is_work(self, tmp_path):
        bash = {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "hatch run fast"}}
        result = {"type": "tool_result", "tool_use_id": "b1", "content": "ok"}
        t = _write(
            tmp_path / "m.jsonl",
            [
                _assistant("2026-10-10T10:00:00Z", [bash]),
                _user("2026-10-10T10:05:00Z", [result]),
                _assistant("2026-10-10T10:05:10Z"),
                _user("2026-10-10T10:15:10Z", "<task-notification> a pass finished"),
            ],
        )
        wall, wait = deliveries.active(t, {})
        assert (wall, wait) == (910.0, 0.0)

    def test_a_gap_under_a_minute_is_work_whatever_ends_it(self, tmp_path):
        t = _write(tmp_path / "m.jsonl", [_assistant("2026-10-10T10:00:00Z"), _user("2026-10-10T10:00:59Z", "go")])
        assert deliveries.active(t, {}) == (59.0, 0.0)

    def test_only_records_inside_the_part_count(self, tmp_path):
        t = _write(
            tmp_path / "m.jsonl",
            [
                _assistant("2026-10-10T10:00:00Z"),
                _assistant("2026-10-10T10:00:30Z"),
                _assistant("2026-10-10T11:00:00Z"),
            ],
        )
        assert deliveries.active(t, {"until": "2026-10-10T10:59:00Z"}) == (30.0, 0.0)


class TestHandback:
    def test_the_count_line_of_the_last_handback_is_summed(self, tmp_path):
        early = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": "Bug: 9 | Spec: 9"}}
        last = {
            "type": "tool_use",
            "name": "SubagentHandback",
            "input": {"message": "## Review\nBug: 1 | Spec: 2 (Possible) | Test: 0 | Consistency: 1"},
        }
        t = _write(
            tmp_path / "a.jsonl",
            [_assistant("2026-10-10T10:00:00Z", [early]), _assistant("2026-10-10T10:01:00Z", [last])],
        )
        assert deliveries.handback(t) == 4

    def test_a_forked_pass_without_a_handback_is_read_from_its_last_text(self, tmp_path):
        text = {"type": "text", "text": "## PR #1 Review\n**Bug**: 2 | Spec: 1 | Ripple: 0"}
        t = _write(tmp_path / "a.jsonl", [_assistant("2026-10-10T10:00:00Z", [text])])
        assert deliveries.handback(t) == 3

    def test_a_pass_with_no_count_line_has_no_figure(self, tmp_path):
        text = {"type": "text", "text": "Now tear down the worktrees."}
        t = _write(tmp_path / "a.jsonl", [_assistant("2026-10-10T10:00:00Z", [text])])
        assert deliveries.handback(t) is None


class TestSelection:
    @pytest.mark.parametrize(
        ("sub", "expected"),
        [
            ({"type": "reviewer", "description": "Closing round: unprimed member"}, True),
            ({"type": "general-purpose", "description": "Round 4 whole-file panel member"}, True),
            ({"type": "general-purpose", "description": "/rvw-pr 1127 root=tmp/review/x"}, True),
            ({"type": "testing-expert", "description": "Write A.10 generated kernel suites"}, False),
            ({"type": "general-purpose", "description": "Open PR for BUG-326 branch"}, False),
        ],
    )
    def test_a_review_pass_is_a_reviewer_or_a_subagent_described_as_one(self, sub, expected):
        assert deliveries.is_pass(sub) is expected

    def test_a_part_keeps_its_window_and_its_agent_filter(self):
        part = {"since": "2026-10-12T15:00:00Z", "until": "2026-10-15T06:00:00Z", "exclude_agents": ["a4614"]}
        assert deliveries.within("2026-10-12T15:00:00.000Z", part)
        assert not deliveries.within("2026-10-12T14:59:59.999Z", part)
        assert not deliveries.within("2026-10-15T06:00:00Z", part)
        assert not deliveries.keep_agent("agent-a4614f4bcebad8abf", part)
        assert deliveries.keep_agent("agent-ad87b172", part)
        assert deliveries.keep_agent("agent-a4614f4bcebad8abf", {"agents": ["a4614"]})

    def test_a_pass_counts_under_the_method_its_description_names_first(self):
        passes = [
            {"description": d, "calls": 10, "units": 1e6, "read_whole": [], "findings_handed_back": 1}
            for d in ("Final measuring + whole-file member", "Whole-file then unprimed member", "Reader member")
        ]
        out = deliveries.by_method(passes)
        assert {k: v["passes"] for k, v in out.items()} == {"measuring": 1, "whole-file": 1, "other": 1}

    def test_a_read_whole_is_a_repo_file_not_a_spilled_output_or_a_scratch_file(self, tmp_path, monkeypatch):
        def read(i, path, **extra):
            return {"type": "tool_use", "id": f"r{i}", "name": "Read", "input": {"file_path": path, **extra}}

        monkeypatch.setattr(
            deliveries.tokkit,
            "ARGS",
            deliveries.argparse.Namespace(repo_root=Path("K:/Code/remote-store")),
            raising=False,
        )
        t = _write(
            tmp_path / "a.jsonl",
            [
                _assistant(
                    "2026-10-10T10:00:00Z",
                    [
                        read(1, "K:/Code/remote-store/tmp/review/abc123/src/a.py"),
                        read(2, "K:/Code/remote-store/sdd/b.md"),
                        read(3, "K:/Code/remote-store/sdd/c.md", offset=10, limit=20),
                        read(4, "C:/Users/x/.claude/projects/p/s/tool-results/t1.txt"),
                        read(5, "C:/Users/x/.claude/projects/p/s/tool-results/t2.txt"),
                        read(6, "F:/Temp/claude/p/s/scratchpad/n.md"),
                    ],
                )
            ],
        )
        assert deliveries.read_whole(t) == ["<review-snapshot>/src/a.py", "sdd/b.md"]


class TestRounds:
    @staticmethod
    def _pass(desc, ts):
        return {"type": "reviewer", "description": desc, "first_ts": ts}

    def test_a_pass_joins_the_latest_spawn_of_its_description_before_it(self):
        mc = [{"ts": f"2026-10-10T10:0{n}:00Z"} for n in range(6)]
        # The same description is spawned at call 1 and at call 4 (events sit one past the call).
        spawns = [(2, "Closing review"), (5, "Closing review"), (3, "Other member")]
        early = self._pass("Closing review", "2026-10-10T10:02:30Z")
        late = self._pass("Closing review", "2026-10-10T10:04:30Z")
        orphan = self._pass("Unspawned member", "2026-10-10T10:04:30Z")
        builder = {"type": "testing-expert", "description": "Write suites", "first_ts": "2026-10-10T10:02:30Z"}
        rounds = deliveries.group_rounds([early, late, orphan, builder], spawns, mc)
        assert dict(rounds) == {2: [early], 5: [late], None: [orphan]}

    def test_a_round_spans_main_calls_from_its_spawn_to_the_next(self):
        assert deliveries.round_spans({5: [], 2: [], None: []}, 9) == [(2, 5), (5, 9)]

    def test_a_submission_goes_to_the_round_spawned_before_it_unless_that_round_had_ended(self):
        def epoch(ts):
            return deliveries.when(ts).timestamp()

        rounds = [
            {"spawn_ts": "2026-10-10T10:00:00Z", "end_ts": "2026-10-10T11:00:00Z"},
            {"spawn_ts": "2026-10-10T11:00:00Z", "end_ts": "2026-10-10T12:00:00Z"},
        ]
        subs = [
            (epoch("2026-10-10T09:59:00Z"), 1),  # before any round
            (epoch("2026-10-10T10:30:00Z"), 2),
            (epoch("2026-10-10T11:30:00Z"), 4),
            (epoch("2026-10-10T12:00:01Z"), 8),  # after the last round's span
        ]
        posted, outside = deliveries.assign_submissions(subs, rounds)
        assert (dict(posted), outside) == ({0: 2, 1: 4}, 9)

    def test_an_unsubmitted_or_bot_review_is_not_a_submission(self):
        findings = {1: ["f"] * 2, 2: ["f"] * 3, 3: ["f"] * 5}  # 3 is still pending
        sr = SimpleNamespace(
            rounds_with_findings=lambda pr: (findings, {1: 100, 2: 200}, {}, [3]),
            fnd=SimpleNamespace(_gh=lambda path: [{"id": 2, "user": {"type": "Bot"}}, {"id": 1, "user": {}}]),
        )
        assert deliveries.submissions(sr, 1) == ([(100, 2)], 1)

    def test_loop_cost_outside_every_span_joins_the_round_before_it(self):
        rounds = [{"spawn_ts": "2026-10-10T10:00:00Z"}, {"spawn_ts": "2026-10-10T12:00:00Z"}]
        loose = [
            {"ts": "2026-10-10T09:00:00Z", "units": 1, "usd": 0.5, "main": True},  # before any round
            {"ts": "2026-10-10T10:00:00Z", "units": 2, "usd": 0.5, "main": True},  # the spawning call
            {"ts": "2026-10-10T11:00:00Z", "units": 4, "usd": 0.5, "main": False},  # a fixer subagent
            {"ts": "2026-10-11T08:00:00Z", "units": 8, "usd": 0.5, "main": True},  # a resume session's opening
        ]
        per_round, before = deliveries.assign_loose(loose, rounds)
        assert dict(per_round) == {
            0: {"main_units": 2, "other_units": 4, "usd": 1.0},
            1: {"main_units": 8, "other_units": 0, "usd": 0.5},
        }
        assert before == {"main_units": 1, "other_units": 0, "usd": 0.5}


class TestMeasurePart:
    def test_every_loop_unit_lands_in_a_round_or_in_the_loose_cost(self, tmp_path, monkeypatch):
        """A resume part: a call before the first spawn, the spawning call, a pass, a fixer, two fix calls."""
        monkeypatch.setattr(
            deliveries.tokkit,
            "ARGS",
            deliveries.argparse.Namespace(repo_root=Path("K:/Code/remote-store")),
            raising=False,
        )
        sid = "s1"
        sub = tmp_path / sid / sid / "subagents"
        sub.mkdir(parents=True)
        spawn = {"type": "tool_use", "id": "a1", "name": "Agent", "input": {"description": "Round member"}}
        _write(
            tmp_path / sid / f"{sid}.jsonl",
            [
                _call("m0", "2026-10-10T10:00:00Z", 1),
                _call("m1", "2026-10-10T10:01:00Z", 10, [spawn]),
                _call("m2", "2026-10-10T10:05:00Z", 100),
                _call("m3", "2026-10-10T10:06:00Z", 1000),
            ],
        )
        for name, kind, desc, ts, tokens in (
            ("agent-p1", "reviewer", "Round member", "2026-10-10T10:02:00Z", 10_000),
            ("agent-f1", "general-purpose", "Fix the findings", "2026-10-10T10:05:30Z", 100_000),
        ):
            _write(sub / f"{name}.jsonl", [_call(f"{name}-0", ts, tokens)])
            (sub / f"{name}.meta.json").write_text(json.dumps({"agentType": kind, "description": desc}))

        out = deliveries.measure_part(tmp_path, {"session": sid}, set(), "9999-01-01T00:00:00Z")

        assert out["phases"] == {"review loop": 111_111}
        [r] = out["rounds"]
        assert (r["main_units"], [p["units"] for p in r["passes"]]) == (1100, [10_000])
        assert sorted((x["units"], x["main"]) for x in out["loose"]) == [(1, True), (10, True), (100_000, False)]
        in_rounds = r["main_units"] + sum(p["units"] for p in r["passes"])
        assert in_rounds + sum(x["units"] for x in out["loose"]) == out["phases"]["review loop"]
