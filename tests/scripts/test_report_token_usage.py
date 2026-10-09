"""Unit tests for the token usage report.

Transcripts are synthetic ``tmp_path`` JSONL in the shape Claude Code
writes: one record per content block, records of one API response sharing
``message.id`` and its ``usage``. Traces are synthetic too. No test reads
real transcripts, which live outside the repo, or the real ``sdd/traces``,
whose counts grow with every PR.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.os_sensitive

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "report_token_usage.py"


def _load():
    spec = importlib.util.spec_from_file_location("report_token_usage", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("report_token_usage", mod)
    spec.loader.exec_module(mod)
    return mod


rtu = _load()


def _usage(inp=0, write=0, read=0, out=0, ttl="1h"):
    return {
        "input_tokens": inp,
        "cache_creation_input_tokens": write,
        "cache_read_input_tokens": read,
        "output_tokens": out,
        "cache_creation": {f"ephemeral_{ttl}_input_tokens": write},
    }


def _assistant(msg_id, usage, *blocks):
    return json.dumps(
        {"type": "assistant", "message": {"id": msg_id, "role": "assistant", "usage": usage, "content": list(blocks)}}
    )


def _result(tool_id, text):
    return json.dumps(
        {
            "type": "user",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]},
        }
    )


def _read(tool_id, path):
    return {"type": "tool_use", "id": tool_id, "name": "Read", "input": {"file_path": path}}


def _session():
    """Three API calls; a 400-char Read result enters after call 1, so two calls carry it."""
    u1 = _usage(inp=10, write=1000, read=0, out=50)
    return [
        _assistant("m1", u1, {"type": "text", "text": "x"}),
        # Second record of the same response: its usage must not count twice.
        _assistant("m1", u1, _read("t1", "sdd/BACKLOG.md")),
        _result("t1", "a" * 400),
        _assistant("m2", _usage(inp=1, write=100, read=1000, out=20)),
        _assistant("m3", _usage(inp=1, write=0, read=1100, out=30)),
    ]


class TestParse:
    def test_usage_counts_each_response_once(self):
        s = rtu.parse(_session(), "s")
        assert s.calls == 3
        assert dict(s.tokens) == {"input": 12, "read": 2100, "output": 100, "write_5m": 0, "write_1h": 1100}

    def test_prefix_is_first_call_context(self):
        assert rtu.parse(_session(), "s").prefix == 1010

    def test_units_apply_price_weights(self):
        s = rtu.parse(_session(), "s")
        assert s.units == pytest.approx(12 * 1 + 1100 * 2 + 2100 * 0.1 + 100 * 5)

    def test_result_attributed_to_target_with_carried_cost(self):
        s = rtu.parse(_session(), "s")
        # 400 chars // 4 = 100 tokens, re-read by calls 2 and 3.
        assert s.results == {"Read sdd/BACKLOG.md": [100, 200]}

    def test_result_after_last_call_carries_nothing(self):
        lines = [_assistant("m1", _usage(inp=1), _read("t1", "f")), _result("t1", "b" * 40)]
        assert rtu.parse(lines, "s").results == {"Read f": [10, 0]}

    def test_legacy_usage_without_ttl_split_counts_as_5m_write(self):
        usage = {"input_tokens": 0, "cache_creation_input_tokens": 80, "output_tokens": 0}
        s = rtu.parse([_assistant("m1", usage)], "s")
        assert s.tokens["write_5m"] == 80
        assert s.tokens["write_1h"] == 0

    def test_list_content_and_unknown_tool_id(self):
        line = json.dumps(
            {
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "nope", "content": [{"type": "text", "text": "c" * 8}]}
                    ]
                }
            }
        )
        assert rtu.parse([line], "s").results == {"?": [2, 0]}

    def test_responses_without_id_each_count(self):
        # The id dedupes records of one response; with no id there is nothing to
        # dedupe on, so a second id-less response must not be dropped as a repeat.
        lines = [json.dumps({"message": {"usage": _usage(inp=5)}}), json.dumps({"message": {"usage": _usage(inp=7)}})]
        s = rtu.parse(lines, "s")
        assert s.calls == 2
        assert s.tokens["input"] == 12

    def test_bad_lines_are_counted_not_fatal(self):
        s = rtu.parse(["{not json", *_session()], "s")
        assert s.bad_lines == 1
        assert s.calls == 3

    @pytest.mark.parametrize(
        ("inp", "expected"),
        [
            ({"command": "git  status\n-s"}, "Bash git status -s"),
            ({"description": "only"}, "Bash"),
            ("not a dict", "Bash"),
        ],
    )
    def test_target_naming(self, inp, expected):
        assert rtu._target("Bash", inp) == expected


def _trace(steps):
    return yaml.safe_dump({"id": "BK-1", "phases": [{"id": "p", "steps": steps}]})


class TestTraceReads:
    @pytest.fixture
    def repo(self, tmp_path):
        (tmp_path / "sdd" / "traces").mkdir(parents=True)
        (tmp_path / "big.md").write_text("x" * 400, encoding="utf-8")
        (tmp_path / "small.md").write_text("x" * 40, encoding="utf-8")
        return tmp_path

    def _write(self, repo, name, text):
        (repo / "sdd" / "traces" / name).write_text(text, encoding="utf-8")

    def test_aggregates_per_file_across_traces(self, repo):
        self._write(
            repo,
            "a.yml",
            _trace(
                [
                    {"file": "big.md", "read_type": "gate"},
                    # Same file again with an anchor: one more step, same trace.
                    {"file": "big.md#section", "read_type": "reference"},
                    {"file": "small.md", "read_type": "verify"},
                ]
            ),
        )
        self._write(repo, "b.yml", _trace([{"file": "big.md", "read_type": "gate"}]))
        rows, read, bad = rtu.trace_reads(repo / "sdd" / "traces", repo)
        by = {r.path: r for r in rows}
        assert (read, bad) == (2, 0)
        assert (len(by["big.md"].traces), by["big.md"].steps, by["big.md"].gates) == (2, 3, 2)
        assert by["big.md"].size == 100
        assert by["big.md"].exposure == 200
        assert (len(by["small.md"].traces), by["small.md"].exposure) == (1, 10)

    def test_missing_file_and_directory_have_no_size(self, repo):
        self._write(repo, "a.yml", _trace([{"file": "gone.md"}, {"file": "sdd/traces"}]))
        rows, _, _ = rtu.trace_reads(repo / "sdd" / "traces", repo)
        assert {r.path: r.size for r in rows} == {"gone.md": 0, "sdd/traces": 0}

    def test_schema_skipped_and_bad_yaml_counted(self, repo):
        self._write(repo, "_schema.yml", _trace([{"file": "big.md"}]))
        self._write(repo, "bad.yml", "phases: [unclosed")
        self._write(repo, "empty.yml", "")
        rows, read, bad = rtu.trace_reads(repo / "sdd" / "traces", repo)
        assert rows == []
        assert (read, bad) == (1, 1)

    @pytest.mark.parametrize("kind", ["undecodable", "directory"])
    def test_unreadable_trace_is_skipped_not_fatal(self, repo, kind):
        # Same cases test_check_traces pins for the gate: neither is a YAMLError.
        traces = repo / "sdd" / "traces"
        if kind == "undecodable":
            (traces / "bad.yml").write_bytes(b'id: BK-1\ntitle: "\xff\xfe"\n')
        else:
            (traces / "adir.yml").mkdir()
        self._write(repo, "ok.yml", _trace([{"file": "big.md"}]))
        rows, read, bad = rtu.trace_reads(traces, repo)
        assert (read, bad) == (1, 1)
        assert [r.path for r in rows] == ["big.md"]

    @pytest.mark.parametrize(
        "text",
        [
            "phases: [orient]\n",  # a phase that is a scalar
            "phases: {orient: {steps: []}}\n",  # phases as a mapping
            "phases:\n  - steps: big.md\n",  # steps as a scalar
            "- phases: []\n",  # top level a list
        ],
    )
    def test_yaml_valid_but_wrong_shape_is_skipped_not_fatal(self, repo, text):
        self._write(repo, "shape.yml", text)
        self._write(repo, "ok.yml", _trace([{"file": "big.md"}]))
        rows, read, bad = rtu.trace_reads(repo / "sdd" / "traces", repo)
        assert (read, bad) == (1, 1)
        assert [r.path for r in rows] == ["big.md"]

    def test_duplicate_key_trace_is_rejected_by_shared_loader(self, repo):
        # Plain yaml.safe_load would keep the last `phases` and count this trace.
        self._write(repo, "dup.yml", "phases: []\nphases: []\n")
        _, read, bad = rtu.trace_reads(repo / "sdd" / "traces", repo)
        assert (read, bad) == (0, 1)

    def test_main_prints_ranked_trace_section(self, repo, capsys):
        self._write(repo, "a.yml", _trace([{"file": "small.md"}, {"file": "big.md", "read_type": "gate"}]))
        empty = repo / "no-transcripts"
        empty.mkdir()
        assert rtu.main([str(empty), "--traces-dir", str(repo / "sdd" / "traces"), "--repo-root", str(repo)]) == 0
        out = capsys.readouterr().out
        assert "across 1 trace(s)" in out
        assert out.index("`big.md`") < out.index("`small.md`")
        assert "| 100 | 1 | 100 | 1 | 1 | 100 | `big.md` |" in out

    def test_repo_root_is_explicit_not_derived_from_traces_dir(self, repo, tmp_path, capsys):
        # A corpus outside <repo>/sdd/traces still sizes against --repo-root.
        snap = tmp_path / "snap" / "a" / "traces"
        snap.mkdir(parents=True)
        (snap / "a.yml").write_text(_trace([{"file": "big.md"}]), encoding="utf-8")
        empty = repo / "no-transcripts"
        empty.mkdir()
        assert rtu.main([str(empty), "--traces-dir", str(snap), "--repo-root", str(repo)]) == 0
        assert "| 100 | 1 | 100 | 1 | 0 | 100 | `big.md` |" in capsys.readouterr().out


@pytest.fixture
def no_traces(tmp_path):
    d = tmp_path / "traces-empty"
    d.mkdir()
    return ["--traces-dir", str(d), "--repo-root", str(tmp_path)]


class TestMain:
    def test_directory_is_scanned_recursively(self, tmp_path, capsys, no_traces):
        (tmp_path / "sess").mkdir()
        (tmp_path / "main.jsonl").write_text("\n".join(_session()), encoding="utf-8")
        (tmp_path / "sess" / "agent.jsonl").write_text("\n".join(_session()), encoding="utf-8")
        assert rtu.main([str(tmp_path), *no_traces]) == 0
        out = capsys.readouterr().out
        assert "2 transcript(s)" in out
        assert "| main.jsonl | 3 | 1,010 |" in out
        assert f"| {Path('sess') / 'agent.jsonl'} | 3 |" in out
        # Aggregated over both transcripts.
        assert "| 400 | 200 | `Read sdd/BACKLOG.md` |" in out

    def test_top_limits_result_rows(self, tmp_path, capsys, no_traces):
        lines = [
            _assistant("m1", _usage(inp=1), _read("t1", "a"), _read("t2", "b")),
            _result("t1", "x" * 40),
            _result("t2", "y" * 80),
            _assistant("m2", _usage(inp=1)),
        ]
        f = tmp_path / "s.jsonl"
        f.write_text("\n".join(lines), encoding="utf-8")
        assert rtu.main([str(f), "--top", "1", *no_traces]) == 0
        out = capsys.readouterr().out
        assert "`Read b`" in out
        assert "`Read a`" not in out

    def test_bad_lines_reported(self, tmp_path, capsys, no_traces):
        f = tmp_path / "s.jsonl"
        f.write_text("garbage\n" + "\n".join(_session()), encoding="utf-8")
        rtu.main([str(f), *no_traces])
        assert "1 line(s) were not JSON" in capsys.readouterr().out

    @pytest.mark.parametrize(
        ("extra", "message"),
        [
            (["absent-transcripts"], "no transcripts at"),
            (["--top"], "expected one argument"),
            (["--top", "abc"], "invalid int value"),
            (["--top", "-1"], "--top must be >= 0"),
            (["--bogus"], "unrecognized arguments"),
            (["--traces-dir", "absent-dir"], "--traces-dir does not exist"),
            (["--repo-root", "absent-root"], "--repo-root does not exist"),
        ],
    )
    def test_usage_errors_exit_2(self, tmp_path, capsys, monkeypatch, no_traces, extra, message):
        monkeypatch.chdir(tmp_path)  # relative "absent-*" paths resolve under tmp_path
        # Later flags override the fixture's, so each case isolates one error.
        with pytest.raises(SystemExit) as exc:
            rtu.main([*no_traces, *extra])
        assert exc.value.code == 2
        assert message in capsys.readouterr().err

    def test_help_exits_0(self, capsys):
        with pytest.raises(SystemExit) as exc:
            rtu.main(["--help"])
        assert exc.value.code == 0
        assert "--repo-root" in capsys.readouterr().out

    def test_help_without_docstring_exits_0(self, capsys, monkeypatch):
        # `python -OO` strips docstrings; the parser description must not need one.
        monkeypatch.setattr(rtu, "__doc__", None)
        with pytest.raises(SystemExit) as exc:
            rtu.main(["--help"])
        assert exc.value.code == 0
        assert "--repo-root" in capsys.readouterr().out

    def test_absent_default_dir_skips_transcripts(self, tmp_path, capsys, monkeypatch, no_traces):
        monkeypatch.setattr(rtu, "default_dir", lambda: tmp_path / "absent")
        assert rtu.main(no_traces) == 0
        out = capsys.readouterr().out
        assert "transcript section skipped" in out
        assert "across 0 trace(s)" in out

    def test_default_dir_matches_claude_code_slug(self):
        assert rtu.default_dir(Path("/home/user/remote-store")).name == "-home-user-remote-store"
