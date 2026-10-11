"""Unit tests for the time cuts the token kit's scripts take (``sdd/research/token-usage/``).

Transcripts write milliseconds (``14:07:00.500Z``); a cut is usually given to
the second (``14:07:00Z``) or without an offset. Compared as strings, the first
sorts before the second, so a call half a second after a cut fell inside it.
Each test puts one record half a second after its cut. Transcripts are
synthetic ``tmp_path`` JSONL.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

_KIT = Path(__file__).resolve().parents[2] / "sdd" / "research" / "token-usage"
sys.path.insert(0, str(_KIT))

import _common  # noqa: E402
import gates  # noqa: E402
import prep_cost  # noqa: E402
import route_baseline  # noqa: E402
import tokkit  # noqa: E402

SID = "00000000-0000-0000-0000-0000000000c1"
CUT = "2026-10-10T14:07:00Z"
AFTER = "2026-10-10T14:07:00.500Z"  # half a second after CUT


def _call(n: int, ts: str) -> dict:
    usage = {"input_tokens": 1, "cache_read_input_tokens": 100, "output_tokens": 1}
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {"id": f"m{n}", "model": "claude-opus-5-5", "usage": usage, "content": []},
    }


def _write(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return path


class TestWhen:
    @pytest.mark.parametrize("cut", [CUT, "2026-10-10T14:07:00", "2026-10-10T16:07:00+02:00"])
    def test_every_spelling_of_a_cut_is_the_same_time_and_precedes_the_call(self, cut):
        assert _common.when(cut) == _common.when(CUT) < _common.when(AFTER)

    def test_a_cut_is_written_back_in_the_transcripts_form(self):
        assert _common.iso(_common.when("2026-10-10T16:07:00+02:00")) == CUT


class TestGates:
    def _transcript(self, tmp_path: Path) -> Path:
        use = {"type": "tool_use", "id": "g1", "name": "Bash", "input": {"command": "hatch run all"}}
        result = {"type": "tool_result", "tool_use_id": "g1", "content": "ok"}
        return _write(
            tmp_path / "t.jsonl",
            [
                {"type": "assistant", "timestamp": "2026-10-10T14:00:00.000Z", "message": {"content": [use]}},
                {"type": "user", "timestamp": AFTER, "message": {"content": [result]}},
            ],
        )

    @pytest.mark.parametrize(("until", "runs"), [(CUT, 0), ("2026-10-10T14:07:00", 0), ("2026-10-10T14:07:01Z", 1)])
    def test_a_gate_run_ending_after_the_cut_is_left_out(self, tmp_path, until, runs):
        t = self._transcript(tmp_path)
        argv = ["--repo-root", str(tmp_path), "--results", str(tmp_path), "--transcripts", str(t), "--until", until]
        gates.main(argv)
        assert json.loads((tmp_path / "gates.json").read_text(encoding="utf-8"))["gate_runs"] == runs


class TestPrepCost:
    def test_a_session_starting_after_the_cut_is_left_out_and_the_window_is_written_as_z(self, tmp_path, monkeypatch):
        transcripts, data = tmp_path / "transcripts", tmp_path / "data"
        _write(transcripts / f"{SID}.jsonl", [_call(0, AFTER)])
        data.mkdir()
        (data / "prep_classes.json").write_text(json.dumps({SID: {"class": "a"}}), encoding="utf-8")
        monkeypatch.setattr(_common, "default_transcripts", lambda repo: [transcripts])
        argv = ["--repo-root", str(tmp_path), "--data", str(data), "--results", str(tmp_path)]
        prep_cost.main([*argv, "--since", "2026-10-10T14:00:00", "--until", "2026-10-10T14:07:00"])
        out = json.loads((tmp_path / "prep_cost.json").read_text(encoding="utf-8"))
        assert out["sessions"] == 0
        assert out["window"] == {"since": "2026-10-10T14:00:00Z", "until": CUT}


class TestRouteBaseline:
    def test_the_first_call_after_the_checkpoint_is_the_one_half_a_second_later(self, tmp_path):
        tokkit.ARGS = argparse.Namespace(repo_root=tmp_path)
        snap = tmp_path / SID
        _write(snap / f"{SID}.jsonl", [_call(0, "2026-10-10T14:06:00.000Z"), _call(1, AFTER)])
        out = route_baseline.split(snap, 0, _common.when(CUT))["checkpoint"]
        assert (out["until"], out["first_main_call_after"]) == (CUT, 1)


class TestTokkitFind:
    def test_a_session_starting_half_a_second_after_since_is_listed(self, tmp_path, monkeypatch, capsys):
        transcripts = tmp_path / "transcripts"
        _write(transcripts / f"{SID}.jsonl", [_call(0, AFTER)])
        monkeypatch.setattr(tokkit.cm, "default_transcripts", lambda repo: [transcripts])
        tokkit.main(["--repo-root", str(tmp_path), "find", "--since", CUT])
        assert SID in capsys.readouterr().out


@pytest.mark.parametrize(
    "run",
    [
        lambda p: gates.main(["--results", str(p), "--transcripts", str(p), "--until", "yesterday"]),
        lambda p: route_baseline.main(["--snapshot", str(p), "--route-start-call", "0", "--checkpoint", "yesterday"]),
        lambda p: tokkit.main(["--repo-root", str(p), "find", "--since", "yesterday"]),
        lambda p: prep_cost.main(["--data", str(p), "--since", "yesterday", "--until", CUT]),
    ],
    ids=["gates", "route_baseline", "tokkit-find", "prep_cost"],
)
def test_a_cut_that_is_not_a_timestamp_is_a_usage_error(tmp_path, capsys, run):
    with pytest.raises(SystemExit) as exc:
        run(tmp_path)
    assert exc.value.code == 2
    assert "yesterday" in capsys.readouterr().err
