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
    assert not (repo / "tmp/observe" / f"{SESSION}.json").exists()
    assert _call(repo, "Bash", command="ls").returncode == 0
    assert _run(repo, "disarm", {"session_id": SESSION, "reason": "clear"}).returncode == 0


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


def test_a_resumed_ordinary_session_stays_unarmed(repo: Path, tmp_path: Path) -> None:
    transcript = tmp_path / "plain.jsonl"
    transcript.write_text('{"type":"user","message":{"content":"fix the bug"}}\n' + _TYPED, encoding="utf-8")
    payload = {"session_id": OTHER, "source": "resume", "transcript_path": str(transcript)}
    assert _run(repo, "rearm", payload).returncode == 0
    assert not (repo / "tmp/observe").exists()


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
