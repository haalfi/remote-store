"""Tests for the decision recorder and its hook wrapper (RFC-0018 D1, D2).

``scripts/record_decision.py`` appends one JSON line per ``AskUserQuestion``
hook event to ``sdd/decisions/<session_id>.jsonl``; the wrapper
``.claude/hooks/record-decision.sh`` runs it and always exits 0, because exit 2
from a ``PreToolUse`` hook blocks the dialog it is recording.

**The payloads are reconstructed, not recorded.** Step 0's probe dumps were
deleted after the probe (RFC-0018 § Step 0 observations). Each fixture below is
rebuilt from the fragments that section quotes verbatim, under the top-level key
set it lists as common to every payload. What the recorder must not lose is
exactly those quoted parts, so that is what each test asserts.

Every test drives a real git repository in ``tmp_path`` rather than a mocked
``git`` (``sdd/TESTING.md`` Rule 6): branch and HEAD are read with ``git -C``,
and a stub could not tell a detached HEAD from a missing repo.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
WRAPPER = ROOT / ".claude" / "hooks" / "record-decision.sh"
GATE_COMMIT = ROOT / ".claude" / "hooks" / "gate-commit.sh"

# Resolved through PATH, not left to the OS: on Windows, CreateProcess searches
# System32 before PATH and a bare "bash" runs WSL's launcher instead of the Git
# Bash that Claude Code runs hooks with.
BASH = shutil.which("bash") or "bash"

SESSION = "8f551ca6-684d-5d72-b7c0-d6da1ce729ee"  # step 0's session_id, observation 4


@pytest.fixture(scope="module")
def recorder() -> Any:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import record_decision

    return record_decision


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo on work branch ``feature`` with one commit."""
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", "-b", "feature")
    (path / "f").write_text("x")
    _git(path, "add", "f")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _payload(event: str, tool_use_id: str, tool_input: dict[str, Any], tool_response: Any = None) -> dict[str, Any]:
    """A hook payload with step 0's common top-level keys."""
    payload: dict[str, Any] = {
        "session_id": SESSION,
        "transcript_path": f"/root/.claude/projects/x/{SESSION}.jsonl",
        "cwd": "/home/user/remote-store",
        "scratchpad_dir": "/tmp/scratch",
        "prompt_id": "p1",
        "permission_mode": "auto",
        "effort": "medium",
        "hook_event_name": event,
        "tool_name": "AskUserQuestion",
        "tool_input": tool_input,
        "tool_use_id": tool_use_id,
    }
    if event == "PostToolUse":
        payload["tool_response"] = tool_response
        payload["duration_ms"] = 1
    return payload


def _question(text: str, labels: list[str], multi: bool = False) -> dict[str, Any]:
    return {
        "question": text,
        "header": "Probe",
        "multiSelect": multi,
        "options": [{"label": label, "description": f"about {label}"} for label in labels],
    }


def _dialog(
    qtext: str, labels: list[str], answer: str, *, multi: bool = False, prefill: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The Pre and Post payloads of one answered dialog, as step 0 saw them.

    Post carries the answer in both ``tool_input.answers`` and
    ``tool_response.answers``, and ``tool_response.questions`` repeats the
    questions (case a).
    """
    questions = [_question(qtext, labels, multi)]
    pre_input: dict[str, Any] = {"questions": questions}
    if prefill is not None:
        pre_input["answers"] = {qtext: prefill}
    answers = {qtext: answer}
    tid = f"toolu_{zlib.crc32(qtext.encode()):010d}"
    pre = _payload("PreToolUse", tid, pre_input)
    post = _payload(
        "PostToolUse", tid, {"questions": questions, "answers": answers}, {"questions": questions, "answers": answers}
    )
    return pre, post


Q_A = "Dialog a (single-select, recommended): which?"
Q_B = "Dialog b (single-select, Other): which?"
Q_C = "Dialog c (multiSelect): which?"
Q_E = "Dialog e (prefill probe): which?"
Q_A2 = "Extra probe (turn interrupt): which?"
SENTINEL = "[User dismissed — do not proceed, wait for next instruction]"

# Cases a, b, c, e and a' of RFC-0018 § Step 0 observations, answer strings verbatim.
ANSWERED = {
    "a-followed": _dialog(Q_A, ["Alpha (Recommended)", "Bravo"], "Alpha (Recommended)"),
    "b-other": _dialog(Q_B, ["Delta (Recommended)", "Echo"], "Other manual echo"),
    "c-multiselect": _dialog(
        Q_C,
        ["Golf (Recommended)", "Hotel (Recommended)", "India"],
        "Golf (Recommended), India, Some more not mentioned yet",
        multi=True,
    ),
    "e-prefill-overridden": _dialog(Q_E, ["Lima (Recommended)", "Mike"], "Mike", prefill="Lima (Recommended)"),
    "a-prime-sentinel": _dialog(Q_A2, ["Yes (Recommended)", "No"], SENTINEL),
}


def _lines(repo: Path) -> list[dict[str, Any]]:
    log = repo / "sdd" / "decisions" / f"{SESSION}.jsonl"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("case", list(ANSWERED), ids=list(ANSWERED))
def test_answered_dialog_appends_asked_then_answered(case: str, recorder: Any, repo: Path) -> None:
    pre, post = ANSWERED[case]
    head = _git(repo, "rev-parse", "HEAD")

    recorder.record(pre, repo, {})
    recorder.record(post, repo, {})

    asked, answered = _lines(repo)
    common = {"session_id": SESSION, "tool_use_id": pre["tool_use_id"], "branch": "feature", "head": head}
    assert {k: asked[k] for k in common} == common
    assert {k: answered[k] for k in common} == common
    assert asked["event"] == "asked"
    assert answered["event"] == "answered"
    # Verbatim: the recorder keeps what it received and interprets nothing (D1).
    assert asked["tool_input"] == pre["tool_input"]
    assert "tool_response" not in asked
    assert answered["tool_input"] == post["tool_input"]
    assert answered["tool_response"] == post["tool_response"]
    assert asked["ts"].endswith("Z")
    assert "remote_session_id" not in asked


LIVE = Path(__file__).parent / "fixtures" / "record_decision"


def test_live_payload_pair_is_kept_verbatim(recorder: Any, repo: Path) -> None:
    """The one pair captured raw, from BK-397's own end-to-end dialog (2026-10-04).

    Only ``cwd``, ``transcript_path`` and ``scratchpad_dir`` were replaced, as
    local paths. It carries what the reconstructions above cannot: keys step 0
    did not list (``annotations`` in both ``tool_input`` and ``tool_response``,
    ``effort`` as an object), which is the payload drift D1's verbatim rule
    exists to survive.
    """
    pre = json.loads((LIVE / "live-pre.json").read_text(encoding="utf-8"))
    post = json.loads((LIVE / "live-post.json").read_text(encoding="utf-8"))
    recorder.record(pre, repo, {})
    recorder.record(post, repo, {})

    log = repo / "sdd" / "decisions" / f"{pre['session_id']}.jsonl"
    asked, answered = (json.loads(x) for x in log.read_text(encoding="utf-8").splitlines())
    assert (asked["event"], answered["event"]) == ("asked", "answered")
    assert asked["tool_use_id"] == answered["tool_use_id"] == pre["tool_use_id"] == post["tool_use_id"]
    assert asked["tool_input"] == pre["tool_input"]
    assert answered["tool_input"] == post["tool_input"]
    assert answered["tool_response"] == post["tool_response"]
    assert answered["tool_response"]["annotations"] == {}


def test_prefill_survives_in_the_asked_line(recorder: Any, repo: Path) -> None:
    """Case e: the agent's prefill is only visible in Pre, so it must be kept there.

    D3 reads ``prefilled`` from the ``asked`` event's ``tool_input``; Post's copy
    already holds the user's override.
    """
    pre, post = ANSWERED["e-prefill-overridden"]
    recorder.record(pre, repo, {})
    recorder.record(post, repo, {})

    asked, answered = _lines(repo)
    assert asked["tool_input"]["answers"] == {Q_E: "Lima (Recommended)"}
    assert answered["tool_response"]["answers"] == {Q_E: "Mike"}


def test_denied_dialog_leaves_a_lone_asked_line(recorder: Any, repo: Path) -> None:
    """Case d: a denial fires only ``PreToolUse``, so the log ends on ``asked``."""
    pre, _ = _dialog("Dialog d (single-select, denied): which?", ["Foxtrot (Recommended)", "Golf"], "unused")
    recorder.record(pre, repo, {})

    (only,) = _lines(repo)
    assert only["event"] == "asked"


def test_appends_never_rewrites(recorder: Any, repo: Path) -> None:
    pre_a, post_a = ANSWERED["a-followed"]
    pre_b, post_b = ANSWERED["b-other"]
    for payload in (pre_a, post_a, pre_b, post_b):
        recorder.record(payload, repo, {})

    lines = _lines(repo)
    assert [(line["event"], line["tool_use_id"]) for line in lines] == [
        ("asked", pre_a["tool_use_id"]),
        ("answered", pre_a["tool_use_id"]),
        ("asked", pre_b["tool_use_id"]),
        ("answered", pre_b["tool_use_id"]),
    ]


def test_detached_head_records_null_branch(recorder: Any, repo: Path) -> None:
    """D4.0 binds a detached-HEAD event to the next work branch, so it must say it had none."""
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "--detach")
    recorder.record(ANSWERED["a-followed"][0], repo, {})

    (line,) = _lines(repo)
    assert line["branch"] is None
    assert line["head"] == head


def test_remote_session_id_recorded_when_set(recorder: Any, repo: Path) -> None:
    """Observation 4: D4.0's trailer fallback matches this variable, not ``session_id``."""
    env = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_01FPZRdRyQ4sj5AD4DZF1zg3"}
    recorder.record(ANSWERED["a-followed"][0], repo, env)

    (line,) = _lines(repo)
    assert line["remote_session_id"] == "cse_01FPZRdRyQ4sj5AD4DZF1zg3"


def test_outside_a_git_repo_records_null_git_fields(recorder: Any, tmp_path: Path) -> None:
    recorder.record(ANSWERED["a-followed"][0], tmp_path, {})

    (line,) = [
        json.loads(x)
        for x in (tmp_path / "sdd" / "decisions" / f"{SESSION}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert line["branch"] is None
    assert line["head"] is None


def test_other_tools_are_ignored(recorder: Any, repo: Path) -> None:
    payload = dict(ANSWERED["a-followed"][0], tool_name="Bash", tool_input={"command": "ls"})
    assert recorder.record(payload, repo, {}) is None
    assert not (repo / "sdd" / "decisions").exists()


def test_unregistered_event_kept_under_its_raw_name(recorder: Any, repo: Path) -> None:
    """``PostToolUseFailure`` is not registered (RFC-0018 Open Questions), but if a
    future registration delivers it, the payload is kept rather than dropped."""
    payload = dict(ANSWERED["a-followed"][0], hook_event_name="PostToolUseFailure", error="boom")
    recorder.record(payload, repo, {})

    (line,) = _lines(repo)
    assert line["event"] == "PostToolUseFailure"
    assert line["payload"]["error"] == "boom"


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", None], ids=["dotdot", "slash", "empty", "missing"])
def test_unsafe_session_id_cannot_escape_the_log_dir(bad: Any, recorder: Any, repo: Path) -> None:
    payload = dict(ANSWERED["a-followed"][0], session_id=bad)
    path = recorder.record(payload, repo, {})

    assert path == repo / "sdd" / "decisions" / "unknown-session.jsonl"
    assert path.is_file()


def test_utf8_answer_round_trips(recorder: Any, repo: Path) -> None:
    """The sentinel carries an em dash; Windows' default encoding would mangle it."""
    recorder.record(ANSWERED["a-prime-sentinel"][1], repo, {})

    (line,) = _lines(repo)
    assert line["tool_response"]["answers"][Q_A2] == SENTINEL


# --- main(): the process boundary --------------------------------------------


def _run_recorder(script: Path, stdin: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([sys.executable, str(script)], input=stdin, capture_output=True, check=False)


def _repo_layout(repo: Path, *, recorder_body: str | None) -> Path:
    """Copy the wrapper into *repo* and, unless None, a recorder beside it.

    The wrapper finds the recorder relative to itself, so this is the layout the
    hook sees in a real checkout.
    """
    hooks = repo / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    shutil.copy(WRAPPER, hooks / WRAPPER.name)
    if recorder_body is not None:
        (repo / "scripts").mkdir()
        (repo / "scripts" / "record_decision.py").write_text(recorder_body, encoding="utf-8")
    return hooks / WRAPPER.name


def test_main_on_garbage_stdin_exits_zero_without_stdout(repo: Path) -> None:
    """A recorder error is noted on stderr and never blocks (D1 fail-open)."""
    _repo_layout(repo, recorder_body=(SCRIPTS / "record_decision.py").read_text(encoding="utf-8"))
    result = _run_recorder(repo / "scripts" / "record_decision.py", b"not json")

    assert result.returncode == 0
    assert result.stdout == b""
    assert b"record_decision" in result.stderr


def test_main_appends_under_its_own_repo_root(repo: Path) -> None:
    _repo_layout(repo, recorder_body=(SCRIPTS / "record_decision.py").read_text(encoding="utf-8"))
    pre, _ = ANSWERED["a-followed"]
    result = _run_recorder(repo / "scripts" / "record_decision.py", json.dumps(pre).encode("utf-8"))

    assert result.returncode == 0
    assert result.stdout == b""
    assert [line["event"] for line in _lines(repo)] == ["asked"]


# --- the wrapper ---------------------------------------------------------------


def _run_wrapper(wrapper: Path, stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, wrapper.as_posix()], input=stdin, capture_output=True, text=True, encoding="utf-8", check=False
    )


def test_wrapper_exits_zero_when_recorder_is_missing(repo: Path) -> None:
    """D1: a missing ``.py`` makes CPython exit 2, which would block the dialog."""
    wrapper = _repo_layout(repo, recorder_body=None)
    result = _run_wrapper(wrapper, json.dumps(ANSWERED["a-followed"][0]))

    assert result.returncode == 0
    assert result.stdout == ""


def test_wrapper_exits_zero_when_recorder_exits_two(repo: Path) -> None:
    """The exit code that blocks a ``PreToolUse`` hook is swallowed, not propagated."""
    wrapper = _repo_layout(repo, recorder_body="import sys\nprint('noise')\nsys.exit(2)\n")
    result = _run_wrapper(wrapper, json.dumps(ANSWERED["a-followed"][0]))

    assert result.returncode == 0
    assert result.stdout == ""


def test_wrapper_runs_the_recorder(repo: Path) -> None:
    wrapper = _repo_layout(repo, recorder_body=(SCRIPTS / "record_decision.py").read_text(encoding="utf-8"))
    pre, post = ANSWERED["c-multiselect"]
    for payload in (pre, post):
        result = _run_wrapper(wrapper, json.dumps(payload))
        assert result.returncode == 0
        assert result.stdout == ""

    assert [line["event"] for line in _lines(repo)] == ["asked", "answered"]


# --- gate-commit.sh staging (D2) ---------------------------------------------


def _run_gate_commit(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, GATE_COMMIT.as_posix()], cwd=repo, input="{}", capture_output=True, text=True, check=False
    )


def test_gate_commit_stages_the_decision_log(repo: Path) -> None:
    log = repo / "sdd" / "decisions" / f"{SESSION}.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text('{"event":"asked"}\n', encoding="utf-8")

    result = _run_gate_commit(repo)

    assert result.returncode == 0
    assert _git(repo, "diff", "--cached", "--name-only") == f"sdd/decisions/{SESSION}.jsonl"


def test_gate_commit_without_a_decision_log_is_silent(repo: Path) -> None:
    result = _run_gate_commit(repo)

    assert result.returncode == 0
    assert result.stderr == ""
    assert _git(repo, "diff", "--cached", "--name-only") == ""
