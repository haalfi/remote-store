"""Tests for the /observe ground hook (RFC-0024 D4, D11; research § 4 S2, S3).

``.claude/hooks/observe-ground.sh`` runs ``scripts/observe_ground.py``. Both are
copied into a temporary repository and run there through bash, with real
payloads on stdin: the wrapper resolves the repository from its own path, so a
copy tests the shipped files against a register and marker this test controls.

What must hold, and why each is pinned: an unarmed session is never blocked,
since the PreToolUse hook runs on every call of every session; an armed one
reads only its allowlist and writes only its record; 0.33 code, tests and
specs 001 to 050 cannot be named into it; and the repository's own register and
wiring point at files that exist.

Not marked ``os_sensitive`` and skipped on Windows, as ``test_claude_hooks.py``
records for its hook: the harness needs bash and symlinks.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests._helpers import hook_bash

ROOT = Path(__file__).resolve().parents[2]
BASH = hook_bash() or "bash"
SESSION = "0b9c2c1e-5f0e-4c4b-9a55-2f1d8c7a6e01"
OTHER = "7d3e8f20-1a2b-4c5d-8e9f-0a1b2c3d4e5f"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the hook harness needs bash and symlinks")

REGISTER = """# Ground register

| Artifact | Flow | Status |
|---|---|---|
| `sdd/specs/051-store-tree.md` | start | active |
| `sdd/formal/old.als` | start | reopened |
| `sdd/observe/catalogue.md` | catalogue | active |
"""

# Two entries, plus a needs row and a not-in-v1 row an entry parser must skip.
CATALOGUE = """# Operation catalogue

| ID | Group | Need |
|---|---|---|
| `N-01` | Data in and out | Read |

| ID | Intent | Target | Result | Offer | Serves |
|---|---|---|---|---|---|
| `OP-01` | Read an item | item | content | v1 | `N-01` |
| `OP-02` | Read an item at offsets | item | reader | v1 | `N-01` |

| Operation | Disposition |
|---|---|
| Append | Not in v1 |
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for rel in (".claude/hooks/observe-ground.sh", "scripts/observe_ground.py"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    files = {
        "sdd/observe/ground-register.md": REGISTER,
        "sdd/observe/axes.md": "axes",
        ".claude/skills/observe/SKILL.md": "skill",
        "sdd/specs/051-store-tree.md": "tree",
        "sdd/specs/003-backend-adapter-contract.md": "0.33",
        "sdd/formal/old.als": "reopened",
        "sdd/research/prior.md": "named",
        "sdd/observe/catalogue.md": CATALOGUE,
        "sdd/observe/inputs/OP-01.md": "OP-01's notes",
        "sdd/observe/inputs/OP-02.md": "OP-02's notes",
        "src/remote_store/store.py": "code",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


def _run(repo: Path, mode: str, payload: dict[str, object] | str) -> subprocess.CompletedProcess[str]:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [BASH, str(repo / ".claude/hooks/observe-ground.sh"), mode],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _arm(
    repo: Path, prompt: str, session: str = SESSION, transcript: Path | None = None
) -> subprocess.CompletedProcess[str]:
    payload: dict[str, object] = {"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": prompt}
    if transcript is not None:
        payload["transcript_path"] = str(transcript)
    return _run(repo, "arm", payload)


def _call(repo: Path, tool: str, session: str = SESSION, **tool_input: object) -> subprocess.CompletedProcess[str]:
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": session,
        "cwd": str(repo),
        "tool_name": tool,
        "tool_input": tool_input,
    }
    return _run(repo, "check", payload)


# --- arming ------------------------------------------------------------------


def test_observe_prompt_arms_the_session_with_its_record(repo: Path) -> None:
    result = _arm(repo, "/observe OP-01 sdd/research/prior.md")
    assert result.returncode == 0, result.stderr
    state = json.loads((repo / "tmp/observe" / f"{SESSION}.json").read_text(encoding="utf-8"))
    assert state == {
        "entry": "OP-01",
        "record": "sdd/observe/records/OP-01.md",
        "input": "sdd/observe/inputs/OP-01.md",
        "named": ["sdd/research/prior.md"],
    }


def test_other_prompts_leave_the_session_unarmed(repo: Path) -> None:
    result = _arm(repo, "please /observe nothing")
    assert result.returncode == 0
    assert not (repo / "tmp/observe").exists()


@pytest.mark.parametrize(
    ("prompt", "reason"),
    [
        ("/observe", "usage"),
        ("/observe read", "usage"),
        ("/observe op-01", "usage"),
        ("/observe OP-1", "usage"),
        ("/observe N-01", "usage"),
        ("/observe OP-99", "no entry"),
        ("/observe OP-01 src/remote_store/store.py", "never ground"),
        ("/observe OP-01 sdd/specs/003-backend-adapter-contract.md", "never ground"),
        ("/observe OP-01 sdd/missing.md", "not a file"),
        ("/observe OP-01 ../outside.md", "not a file"),
        ("/observe OP-01 sdd/observe/inputs/OP-02.md", "another entry's input"),
        ("/observe OP-01 sdd/formal/old.als", "reopened"),
    ],
)
def test_arm_refuses_bad_operations_and_never_ground_paths(repo: Path, prompt: str, reason: str) -> None:
    result = _arm(repo, prompt)
    assert result.returncode == 2
    assert reason in result.stderr
    assert not (repo / "tmp/observe" / f"{SESSION}.json").exists()


def test_arm_refuses_a_session_that_already_used_a_tool(repo: Path, tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"assistant","message":{"content":[{"type": "tool_use","name":"Read"}]}}\n')
    result = _arm(repo, "/observe OP-01", transcript=transcript)
    assert result.returncode == 2
    assert "fresh session" in result.stderr


def test_arm_accepts_a_transcript_without_tool_use(repo: Path, tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text('{"type":"user","message":{"content":"hi"}}\n')
    assert _arm(repo, "/observe OP-01", transcript=transcript).returncode == 0


# --- unarmed sessions --------------------------------------------------------


def test_unarmed_session_is_never_checked(repo: Path) -> None:
    assert _call(repo, "Bash", command="cat src/remote_store/store.py").returncode == 0
    _arm(repo, "/observe OP-01")
    other = _call(repo, "Read", session=OTHER, file_path=str(repo / "src/remote_store/store.py"))
    assert other.returncode == 0, other.stderr


def test_a_crash_never_blocks_an_unarmed_session(repo: Path) -> None:
    _arm(repo, "/observe OP-01")
    bad = '{"session_id": "' + OTHER + '", "tool_input": ['
    assert _run(repo, "check", bad).returncode == 0
    assert _run(repo, "arm", "{not json").returncode == 0


def test_a_crash_blocks_the_armed_session(repo: Path) -> None:
    _arm(repo, "/observe OP-01")
    bad = '{"session_id": "' + SESSION + '", "tool_input": ['
    result = _run(repo, "check", bad)
    assert result.returncode == 2
    assert "hook failed" in result.stderr


# --- armed sessions ----------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Read", {"file_path": "sdd/specs/051-store-tree.md"}),
        ("Read", {"file_path": "sdd/observe/axes.md"}),
        ("Read", {"file_path": "sdd/observe/ground-register.md"}),
        ("Read", {"file_path": ".claude/skills/observe/SKILL.md"}),
        ("Read", {"file_path": "sdd/research/prior.md"}),
        ("Read", {"file_path": "sdd/observe/catalogue.md"}),
        ("Read", {"file_path": "sdd/observe/inputs/OP-01.md"}),
        ("Grep", {"pattern": "x", "path": "sdd/observe/inputs/OP-01.md"}),
        ("Grep", {"pattern": "TREE", "path": "sdd/specs/051-store-tree.md"}),
        ("Write", {"file_path": "sdd/observe/records/OP-01.md", "content": "x"}),
        ("Edit", {"file_path": "sdd/observe/records/OP-01.md"}),
        ("AskUserQuestion", {"questions": []}),
        ("Skill", {"skill": "observe"}),
        ("WebSearch", {"query": "Hadoop FileSystem specification open"}),
        ("WebFetch", {"url": "https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html"}),
    ],
)
def test_armed_session_may_use_its_allowlist(repo: Path, tool: str, tool_input: dict[str, object]) -> None:
    _arm(repo, "/observe OP-01 sdd/research/prior.md")
    result = _call(repo, tool, **tool_input)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("tool", "tool_input", "reason"),
    [
        ("Read", {"file_path": "src/remote_store/store.py"}, "outside the ground"),
        ("Read", {"file_path": "sdd/formal/old.als"}, "outside the ground"),
        ("Read", {"file_path": "sdd/specs/003-backend-adapter-contract.md"}, "outside the ground"),
        ("Read", {"file_path": "sdd/observe/inputs/OP-02.md"}, "outside the ground"),
        ("Grep", {"pattern": "x", "path": "sdd/observe/inputs"}, "outside the ground"),
        ("Write", {"file_path": "sdd/observe/inputs/OP-01.md"}, "writes only"),
        ("Grep", {"pattern": "x"}, "outside the ground"),
        ("Grep", {"pattern": "x", "path": "sdd"}, "outside the ground"),
        ("Glob", {"pattern": "**/*.md"}, "not available"),
        ("Bash", {"command": "ls"}, "not available"),
        ("Agent", {"prompt": "read src"}, "not available"),
        ("mcp__github__get_file_contents", {"path": "src"}, "not available"),
        ("Skill", {"skill": "ship"}, "not available"),
        ("Write", {"file_path": "sdd/specs/051-store-tree.md"}, "writes only"),
        ("WebFetch", {"url": "https://github.com/haalfi/remote-store/blob/master/src"}, "never ground"),
        ("WebSearch", {"query": "remote_store python read semantics"}, "never ground"),
    ],
)
def test_armed_session_is_denied_outside_its_allowlist(
    repo: Path, tool: str, tool_input: dict[str, object], reason: str
) -> None:
    _arm(repo, "/observe OP-01 sdd/research/prior.md")
    result = _call(repo, tool, **tool_input)
    assert result.returncode == 2
    assert reason in result.stderr


def test_the_skill_canary_is_refused_only_when_armed(repo: Path) -> None:
    canary = "tmp/observe/canary-not-ground"
    assert _call(repo, "Read", file_path=canary).returncode == 0
    _arm(repo, "/observe OP-01")
    result = _call(repo, "Read", file_path=canary)
    assert result.returncode == 2
    assert "outside the ground" in result.stderr
    # The refusal names every readable non-ground file, since Glob is denied.
    for rel in (
        ".claude/skills/observe/SKILL.md",
        "sdd/observe/axes.md",
        "sdd/observe/records/OP-01.md",
        "sdd/observe/inputs/OP-01.md",
    ):
        assert rel in result.stderr


def test_arm_refuses_when_the_catalogue_is_unreadable(repo: Path) -> None:
    (repo / "sdd/observe/catalogue.md").unlink()
    result = _arm(repo, "/observe OP-01")
    assert result.returncode == 2
    assert "catalogue unreadable" in result.stderr


def test_arm_refuses_while_the_catalogue_is_reopened(repo: Path) -> None:
    register = repo / "sdd/observe/ground-register.md"
    text = register.read_text(encoding="utf-8")
    register.write_text(text.replace("| catalogue | active |", "| catalogue | reopened |"), encoding="utf-8")
    result = _arm(repo, "/observe OP-01")
    assert result.returncode == 2
    assert "not active ground" in result.stderr
    assert not (repo / "tmp/observe" / f"{SESSION}.json").exists()


def test_a_symlink_into_code_is_denied(repo: Path) -> None:
    link = repo / "sdd/specs/051-store-tree.md"
    link.unlink()
    link.symlink_to(repo / "src/remote_store/store.py")
    _arm(repo, "/observe OP-01")
    assert _call(repo, "Read", file_path=str(link)).returncode == 2


def test_clear_ends_the_restriction(repo: Path) -> None:
    _arm(repo, "/observe OP-01")
    assert _run(repo, "disarm", {"session_id": SESSION, "reason": "clear"}).returncode == 0
    state = json.loads((repo / "tmp/observe" / f"{SESSION}.json").read_text(encoding="utf-8"))
    assert state == {"released": "clear", "record": "sdd/observe/records/OP-01.md"}
    assert _call(repo, "Bash", command="ls").returncode == 0
    assert _run(repo, "disarm", {"session_id": SESSION, "reason": "clear"}).returncode == 0


def test_clear_without_a_marker_leaves_none(repo: Path) -> None:
    assert _run(repo, "disarm", {"session_id": SESSION, "reason": "clear"}).returncode == 0
    assert not (repo / "tmp/observe").exists()


def test_clear_releases_an_unreadable_marker(repo: Path) -> None:
    marker = repo / "tmp/observe" / f"{SESSION}.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{not json", encoding="utf-8")
    assert _call(repo, "Bash", command="ls").returncode == 2
    assert _run(repo, "disarm", {"session_id": SESSION, "reason": "clear"}).returncode == 0
    assert _call(repo, "Bash", command="ls").returncode == 0
    assert _call(repo, "Write", file_path="sdd/observe/records/OP-01.md", content="x").returncode == 2


# BK-498: a worker restart after /clear resumed the cleared session, most likely re-armed by rearm.
def test_a_cleared_session_is_not_rearmed_on_resume(repo: Path, tmp_path: Path) -> None:
    _arm(repo, "/observe OP-01 sdd/research/prior.md")
    _run(repo, "disarm", {"session_id": SESSION, "reason": "clear"})
    transcript = tmp_path / "resumed.jsonl"
    transcript.write_text(_TYPED + _TOOL_USE, encoding="utf-8")
    payload = {"session_id": SESSION, "source": "resume", "transcript_path": str(transcript)}
    assert _run(repo, "rearm", payload).returncode == 0
    assert _call(repo, "Bash", command="git commit -m x").returncode == 0
    assert _call(repo, "Read", file_path="src/remote_store/store.py").returncode == 0
    refused = _call(repo, "Write", file_path="sdd/observe/records/OP-01.md", content="x")
    assert refused.returncode == 2
    assert "released" in refused.stderr


def _lock(repo: Path, tmp_path: Path) -> None:
    transcript = tmp_path / "locked.jsonl"
    transcript.write_text(_SLUG, encoding="utf-8")
    _run(repo, "rearm", {"session_id": SESSION, "source": "resume", "transcript_path": str(transcript)})


@pytest.mark.parametrize("state", ["armed", "locked"])
def test_release_frees_a_session_but_locks_its_record(repo: Path, tmp_path: Path, state: str) -> None:
    if state == "armed":
        _arm(repo, "/observe OP-01")
    else:
        _lock(repo, tmp_path)
    assert _call(repo, "Bash", command="ls").returncode == 2
    released = _arm(repo, "/observe release")
    assert released.returncode == 0, released.stderr
    assert "released" in released.stdout
    assert _call(repo, "Bash", command="git add sdd/decisions && git commit -m x").returncode == 0
    assert _call(repo, "Read", file_path="src/remote_store/store.py").returncode == 0
    assert _call(repo, "ReadNotifications").returncode == 0
    record = "sdd/observe/records/OP-01.md"
    for tool, tool_input in (
        ("Write", {"file_path": record, "content": "x"}),
        ("Edit", {"file_path": str(repo / record)}),
        ("MultiEdit", {"file_path": record}),
        ("NotebookEdit", {"notebook_path": record}),
        ("Bash", {"command": f"echo x >> {record}"}),
    ):
        result = _call(repo, tool, **tool_input)
        assert result.returncode == 2, tool
        assert "fresh /observe session" in result.stderr
    # The session left the ground, so no record is open to it, its own or another entry's.
    assert _call(repo, "Write", file_path="sdd/observe/records/OP-02.md", content="x").returncode == 2
    assert _call(repo, "Write", file_path="sdd/observe/notes.md", content="x").returncode == 0
    # A later restart keeps it released, and a second release changes nothing.
    transcript = tmp_path / "resumed.jsonl"
    transcript.write_text(_TYPED, encoding="utf-8")
    assert _run(repo, "rearm", {"session_id": SESSION, "transcript_path": str(transcript)}).returncode == 0
    assert _arm(repo, "/observe release").returncode == 0
    assert _call(repo, "Bash", command="ls").returncode == 0


def test_release_without_an_observe_session_is_refused(repo: Path) -> None:
    result = _arm(repo, "/observe release")
    assert result.returncode == 2
    assert "no /observe session to release" in result.stderr
    assert not (repo / "tmp/observe").exists()


def test_refusals_name_the_way_out(repo: Path, tmp_path: Path) -> None:
    _arm(repo, "/observe OP-01")
    for tool, tool_input in (
        ("Bash", {"command": "ls"}),
        ("Read", {"file_path": "src/remote_store/store.py"}),
        ("Write", {"file_path": "notes.md", "content": "x"}),
        ("Edit", {"file_path": "notes.md"}),
        ("WebSearch", {"query": "remote-store docs"}),
    ):
        result = _call(repo, tool, **tool_input)
        assert result.returncode == 2, tool
        assert "/observe release" in result.stderr, tool
    transcript = tmp_path / "locked.jsonl"
    transcript.write_text(_SLUG, encoding="utf-8")
    notice = _run(repo, "rearm", {"session_id": SESSION, "source": "resume", "transcript_path": str(transcript)})
    assert notice.returncode == 2
    assert "/observe release" in notice.stderr
    assert "/observe release" in _call(repo, "Bash", command="ls").stderr
    (repo / "tmp/observe" / f"{SESSION}.json").write_text("{not json", encoding="utf-8")
    assert "/observe release" in _call(repo, "Bash", command="ls").stderr


@pytest.mark.parametrize("reason", ["prompt_input_exit", "logout", "other", None])
def test_any_other_session_end_keeps_the_marker_for_a_resume(repo: Path, reason: str | None) -> None:
    _arm(repo, "/observe OP-01")
    assert _run(repo, "disarm", {"session_id": SESSION, "reason": reason}).returncode == 0
    assert _call(repo, "Bash", command="ls").returncode == 2


# --- resume ------------------------------------------------------------------

_TYPED = '{"type":"user","message":{"role":"user","content":"/observe OP-01 sdd/research/prior.md"}}\n'
_TAGGED = (
    '{"type":"user","message":{"role":"user","content":"<command-message>observe</command-message>\\n'
    '<command-name>/observe</command-name>\\n<command-args>OP-01 sdd/research/prior.md</command-args>"}}\n'
)
_META = '{"type":"user","isMeta":true,"message":{"role":"user","content":[{"type":"text","text":"skill body"}]}}\n'


@pytest.mark.parametrize("first", [_TYPED, _TAGGED])
def test_a_resumed_observe_session_is_armed_again(repo: Path, tmp_path: Path, first: str) -> None:
    transcript = tmp_path / "resumed.jsonl"
    tool_use = '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read"}]}}\n'
    transcript.write_text(first + _META + tool_use, encoding="utf-8")
    payload = {"session_id": OTHER, "source": "resume", "transcript_path": str(transcript)}
    assert _run(repo, "rearm", payload).returncode == 0
    state = json.loads((repo / "tmp/observe" / f"{OTHER}.json").read_text(encoding="utf-8"))
    assert state["named"] == ["sdd/research/prior.md"]
    assert _call(repo, "Bash", session=OTHER, command="ls").returncode == 2


_SLUG = '{"type":"user","message":{"role":"user","content":"/observe read"}}\n'


@pytest.mark.parametrize(("first", "reopen"), [(_TYPED, True), (_SLUG, False)])
def test_a_resume_that_cannot_rearm_is_locked_not_unarmed(repo: Path, tmp_path: Path, first: str, reopen: bool) -> None:
    if reopen:
        register = repo / "sdd/observe/ground-register.md"
        text = register.read_text(encoding="utf-8")
        register.write_text(text.replace("| catalogue | active |", "| catalogue | reopened |"), encoding="utf-8")
    transcript = tmp_path / "resumed.jsonl"
    transcript.write_text(first, encoding="utf-8")
    payload = {"session_id": OTHER, "source": "resume", "transcript_path": str(transcript)}
    assert _run(repo, "rearm", payload).returncode == 2
    for tool, tool_input in (
        ("Bash", {"command": "cat src/remote_store/store.py"}),
        ("Read", {"file_path": "sdd/observe/axes.md"}),
        ("Write", {"file_path": "sdd/observe/records/OP-01.md"}),
    ):
        result = _call(repo, tool, session=OTHER, **tool_input)
        assert result.returncode == 2
        assert "cannot be re-armed" in result.stderr


def test_a_marker_from_the_slug_hook_is_locked(repo: Path) -> None:
    marker = repo / "tmp/observe" / f"{SESSION}.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"operation": "read", "record": "sdd/observe/records/read.md", "named": []}))
    for tool in ("Read", "Write"):
        result = _call(repo, tool, file_path="sdd/observe/records/read.md")
        assert result.returncode == 2
        assert "cannot be re-armed" in result.stderr


_TOOL_USE = '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read"}]}}\n'


def test_a_resumed_ordinary_session_stays_unarmed(repo: Path, tmp_path: Path) -> None:
    # A tool ran before the /observe prompt, so arm refused it: nothing to re-arm.
    transcript = tmp_path / "plain.jsonl"
    plain = '{"type":"user","message":{"content":"fix the bug"}}\n'
    transcript.write_text(plain + _TOOL_USE + _TYPED, encoding="utf-8")
    payload = {"session_id": OTHER, "source": "resume", "transcript_path": str(transcript)}
    assert _run(repo, "rearm", payload).returncode == 0
    assert not (repo / "tmp/observe").exists()


@pytest.mark.parametrize(
    ("lines", "entry"),
    [
        # Chat before /observe, no tool yet: arm accepted it, so rearm must too.
        (['{"type":"user","message":{"content":"hello"}}\n', _TYPED], "OP-01"),
        # A second /observe before any tool replaced the first: rearm takes the last.
        ([_TYPED, '{"type":"user","message":{"content":"/observe OP-02"}}\n'], "OP-02"),
    ],
)
def test_rearm_takes_the_last_observe_prompt_before_any_tool(
    repo: Path, tmp_path: Path, lines: list[str], entry: str
) -> None:
    transcript = tmp_path / "resumed.jsonl"
    transcript.write_text("".join(lines) + _TOOL_USE + '{"type":"user","message":{"content":"/observe OP-01"}}\n')
    payload = {"session_id": OTHER, "source": "compact", "transcript_path": str(transcript)}
    assert _run(repo, "rearm", payload).returncode == 0
    state = json.loads((repo / "tmp/observe" / f"{OTHER}.json").read_text(encoding="utf-8"))
    assert state["entry"] == entry


_RELEASE_PROMPT = '{"type":"user","message":{"content":"/observe release"}}\n'
# A tool result or the model's own text quoting the prompt is no release by the maintainer.
_QUOTED = (
    '{"type":"user","message":{"content":[{"type":"tool_result","content":"/observe release"}]}}\n'
    '{"type":"assistant","message":{"content":[{"type":"text","text":"/observe release"}]}}\n'
)


@pytest.mark.parametrize(
    ("lines", "armed"),
    [
        # The order of a real session: its canary Read runs before the maintainer can release.
        ([_TYPED, _TOOL_USE, _RELEASE_PROMPT], False),
        ([_TYPED, _RELEASE_PROMPT, _TOOL_USE], False),
        ([_TYPED, _TOOL_USE, _QUOTED], True),
    ],
    ids=["release-after-tool", "release-before-tool", "quoted-release"],
)
def test_a_released_transcript_leaves_a_resume_unarmed(
    repo: Path, tmp_path: Path, lines: list[str], armed: bool
) -> None:
    # A resume in a new container or under a new id has no marker; the transcript's release still ends the arming.
    transcript = tmp_path / "resumed.jsonl"
    transcript.write_text("".join(lines), encoding="utf-8")
    payload = {"session_id": OTHER, "source": "resume", "transcript_path": str(transcript)}
    result = _run(repo, "rearm", payload)
    assert result.returncode == 0, result.stderr
    assert (repo / "tmp/observe" / f"{OTHER}.json").exists() is armed


def test_a_rearm_whose_transcript_cannot_be_read_is_locked(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sys.path.insert(0, str(repo / "scripts"))
    import observe_ground

    transcript = tmp_path / "unreadable.jsonl"
    transcript.write_text(_TYPED, encoding="utf-8")
    real_read = Path.read_text

    def unreadable(self: Path, *args: object, **kwargs: object) -> str:
        if self == transcript:
            raise PermissionError(13, "Permission denied")
        return real_read(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", unreadable)
    payload = {"session_id": OTHER, "source": "resume", "transcript_path": str(transcript)}
    with pytest.raises(observe_ground.Refused, match="session locked"):
        observe_ground.rearm(payload, repo)
    monkeypatch.undo()
    result = _call(repo, "Bash", session=OTHER, command="ls")
    assert result.returncode == 2
    assert "cannot be re-armed" in result.stderr


def test_an_ordinary_resume_with_an_odd_transcript_stays_unarmed(repo: Path, tmp_path: Path) -> None:
    transcript = tmp_path / "plain.jsonl"
    transcript.write_text('{"type":"user","message":"oops"}\n{"type":"user","message":{"content":"hi"}}\n')
    payload = {"session_id": OTHER, "source": "resume", "transcript_path": str(transcript)}
    assert _run(repo, "rearm", payload).returncode == 0
    assert not (repo / "tmp/observe").exists()


@pytest.mark.parametrize("where", ["register", "transcript"])
def test_a_rearm_that_crashes_is_locked_not_unarmed(repo: Path, tmp_path: Path, where: str) -> None:
    transcript = tmp_path / "resumed.jsonl"
    if where == "register":
        register = repo / "sdd/observe/ground-register.md"
        register.write_bytes(register.read_bytes() + b"\xff\xfe")
        transcript.write_text(_TYPED, encoding="utf-8")
    else:  # a line _armed_args cannot parse, ahead of the /observe prompt
        transcript.write_text('{"type":"user","message":"oops"}\n' + _TYPED, encoding="utf-8")
    payload = {"session_id": OTHER, "source": "resume", "transcript_path": str(transcript)}
    assert _run(repo, "rearm", payload).returncode == 2
    result = _call(repo, "Bash", session=OTHER, command="ls")
    assert result.returncode == 2
    assert "cannot be re-armed" in result.stderr


def test_arm_reads_the_slash_command_tag_form(repo: Path) -> None:
    prompt = "<command-name>/observe</command-name>\n<command-args>OP-02</command-args>"
    assert _arm(repo, prompt).returncode == 0
    state = json.loads((repo / "tmp/observe" / f"{SESSION}.json").read_text(encoding="utf-8"))
    assert state["entry"] == "OP-02"


# --- the wrapper without python or script --------------------------------------


def _bash_only_path(tmp_path: Path) -> str:
    bin_dir = tmp_path / "bin-bash-only"
    bin_dir.mkdir()
    (bin_dir / "bash").symlink_to(shutil.which("bash") or BASH)
    return str(bin_dir)


def _run_bare(repo: Path, path_env: str, mode: str, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    bash = Path(path_env.split(":")[0]) / "bash"
    return subprocess.run(
        [str(bash), str(repo / ".claude/hooks/observe-ground.sh"), mode],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": path_env},
    )


@pytest.mark.parametrize("missing", ["python", "script"])
def test_wrapper_fails_closed_only_for_the_armed_session(repo: Path, tmp_path: Path, missing: str) -> None:
    _arm(repo, "/observe OP-01")
    path_env = _bash_only_path(tmp_path)
    if missing == "script":
        (repo / "scripts/observe_ground.py").unlink()
        path_env = f"{path_env}:{Path(sys.executable).parent}"
    armed = {"session_id": SESSION, "tool_name": "Read", "tool_input": {}}
    blocked = _run_bare(repo, path_env, "check", armed)
    assert blocked.returncode == 2
    assert "cannot be enforced" in blocked.stderr
    other = {"session_id": OTHER, "tool_name": "Bash", "tool_input": {}}
    assert _run_bare(repo, path_env, "check", other).returncode == 0
    assert _run_bare(repo, path_env, "arm", {"session_id": OTHER, "prompt": "/observe OP-01"}).returncode == 2
    assert _run_bare(repo, path_env, "arm", {"session_id": SESSION, "prompt": "/observe release"}).returncode == 2
    assert _run_bare(repo, path_env, "arm", {"session_id": OTHER, "prompt": "hello"}).returncode == 0
    assert _run_bare(repo, path_env, "rearm", {"session_id": OTHER}).returncode == 0
    assert _run_bare(repo, path_env, "disarm", {"session_id": SESSION, "reason": "clear"}).returncode == 0


# --- the repository's own files ------------------------------------------------


def test_repository_register_admits_only_existing_ground_files() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import observe_ground

    paths = observe_ground.ground(ROOT)
    assert "sdd/specs/051-store-tree.md" in paths
    for rel in paths:
        assert (ROOT / rel).is_file(), rel
        assert not observe_ground._NEVER_GROUND.match(rel), rel
    for rel in observe_ground.METHOD_FILES:
        assert (ROOT / rel).is_file(), rel


def test_repository_has_one_input_per_entry_and_none_is_ground() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import observe_ground

    entries = observe_ground.entries(ROOT)
    assert len(entries) == len(set(entries)) > 0
    inputs = sorted(p.stem for p in (ROOT / "sdd/observe/inputs").glob("*.md"))
    assert inputs == sorted(entries)
    ground = set(observe_ground.ground(ROOT))
    assert not any(rel.startswith("sdd/observe/inputs/") for rel in ground)


def test_ci_runs_this_module_when_any_file_it_reads_changes() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import observe_ground

    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    hooks_pat = re.compile(re.search(r"HOOKS_PAT='([^']+)'", ci)[1])  # type: ignore[index]
    read = [*observe_ground.ground(ROOT), *observe_ground.METHOD_FILES, observe_ground.CATALOGUE]
    read += [p.relative_to(ROOT).as_posix() for p in (ROOT / "sdd/observe/inputs").glob("*.md")]
    assert [rel for rel in read if not hooks_pat.search(rel)] == []
    assert not hooks_pat.search("sdd/observe/records/OP-01.md")


def test_settings_wire_all_four_modes() -> None:
    settings = (ROOT / ".claude/settings.json").read_text(encoding="utf-8")
    hooks = json.loads(settings)["hooks"]
    wired = {
        event: [h["command"] for entry in hooks[event] for h in entry["hooks"] if "observe-ground.sh" in h["command"]]
        for event in ("UserPromptSubmit", "SessionStart", "PreToolUse", "SessionEnd")
    }
    assert [re.findall(r" (arm|rearm|check|disarm)$", c) for e in wired.values() for c in e] == [
        ["arm"],
        ["rearm"],
        ["check"],
        ["disarm"],
    ]
    assert (ROOT / ".claude/hooks/observe-ground.sh").is_file()
