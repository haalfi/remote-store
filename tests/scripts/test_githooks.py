"""The agent gates in ``.githooks/`` act in the repository git runs them in (BK-486).

They replaced Claude PreToolUse hooks that guessed the target repository from
the command line and missed ``git -C <path> commit``. Each test here drives a
real ``git commit`` or ``git push`` against a scratch repository whose
``core.hooksPath`` points at this checkout's ``.githooks/``, so git itself
decides where the hook runs; nothing hands the hook a payload.

Bounds: Claude Code's environment is simulated by setting ``CLAUDECODE`` and
``CLAUDE_CODE_SESSION_ID`` (a cloud session measured both, the latter equal to
the hook payload's ``session_id``). No test stages code, so lint and typecheck
never run here. The wiring tests read ``settings.json``; when Claude Code fires
a hook is not exercised.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests._helpers import hook_bash

ROOT = Path(__file__).resolve().parents[2]
GITHOOKS = ROOT / ".githooks"
HOOKS = ROOT / ".claude" / "hooks"
SESSION = "8f551ca6-684d-5d72-b7c0-d6da1ce729ee"


def _env(*, agent: bool) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE"))}
    if agent:
        env.update(CLAUDECODE="1", CLAUDE_CODE_SESSION_ID=SESSION)
    return env


def _git(*args: str, cwd: Path, agent: bool = True) -> subprocess.CompletedProcess[str]:
    ident = ["-c", "user.name=t", "-c", "user.email=t@t"]
    return subprocess.run(
        ["git", *ident, *args], cwd=cwd, env=_env(agent=agent), capture_output=True, text=True, check=False
    )


def _ok(*args: str, cwd: Path) -> str:
    result = _git(*args, cwd=cwd, agent=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(path: Path, branch: str) -> Path:
    _ok("init", "-q", "-b", branch, str(path), cwd=path.parent)
    _ok("commit", "-q", "--allow-empty", "-m", "init", cwd=path)
    _ok("config", "core.hooksPath", str(GITHOOKS), cwd=path)
    return path


@pytest.fixture
def on_master(tmp_path: Path) -> Path:
    return _repo(tmp_path / "repo", "master")


@pytest.fixture
def on_feature(tmp_path: Path) -> Path:
    return _repo(tmp_path / "repo", "feature")


# --- pre-commit: the master block ---------------------------------------------


def test_agent_commit_on_master_is_blocked(on_master: Path) -> None:
    result = _git("commit", "--allow-empty", "-m", "x", cwd=on_master)

    assert result.returncode != 0
    assert "Blocked: never commit directly to master" in result.stderr


def test_agent_commit_with_git_C_from_elsewhere_is_blocked(on_master: Path) -> None:
    """The form the PreToolUse ``if:`` filter never fired on."""
    result = _git("-C", str(on_master), "commit", "--allow-empty", "-m", "x", cwd=on_master.parent)

    assert result.returncode != 0
    assert "Blocked: never commit directly to master" in result.stderr


def test_agent_commit_with_git_dir_is_blocked(on_master: Path) -> None:
    result = _git(
        f"--git-dir={on_master / '.git'}",
        f"--work-tree={on_master}",
        "commit",
        "--allow-empty",
        "-m",
        "x",
        cwd=on_master.parent,
    )

    assert result.returncode != 0
    assert "Blocked: never commit directly to master" in result.stderr


def test_worktrees_are_judged_on_their_own_branch(on_feature: Path) -> None:
    """Main tree on ``feature``, a linked worktree (a ``.git`` file) on ``master``."""
    tree = on_feature.parent / "on-master"
    _ok("worktree", "add", "-q", "-b", "master", str(tree), cwd=on_feature)
    assert (tree / ".git").is_file()

    into_worktree = _git("-C", str(tree), "commit", "--allow-empty", "-m", "x", cwd=on_feature)
    into_main = _git("-C", str(on_feature), "commit", "--allow-empty", "-m", "x", cwd=tree)

    assert into_worktree.returncode != 0
    assert "Blocked: never commit directly to master" in into_worktree.stderr
    assert into_main.returncode == 0, into_main.stderr


def test_human_commit_on_master_passes(on_master: Path) -> None:
    """Without ``CLAUDECODE`` the gates stay out of a person's way."""
    result = _git("commit", "--allow-empty", "-m", "x", cwd=on_master, agent=False)

    assert result.returncode == 0, result.stderr


def test_a_failing_local_hook_still_blocks(on_feature: Path) -> None:
    """``core.hooksPath`` hides ``.git/hooks``; pre-commit chains to it."""
    local = on_feature / ".git" / "hooks" / "pre-commit"
    local.write_text("#!/bin/sh\necho local-hook-ran >&2\nexit 1\n", encoding="utf-8")
    local.chmod(0o755)

    result = _git("commit", "--allow-empty", "-m", "x", cwd=on_feature, agent=False)

    assert result.returncode != 0
    assert "local-hook-ran" in result.stderr


# --- pre-commit: the decision log (RFC-0018 D2) --------------------------------


def _hold(repo: Path, text: str = '{"event": "asked"}\n') -> Path:
    held = repo / "sdd" / "decisions" / ".pending" / f"{SESSION}.jsonl"
    held.parent.mkdir(parents=True)
    held.write_text(text, encoding="utf-8")
    return held


def test_agent_commit_promotes_and_commits_the_held_records(on_feature: Path) -> None:
    held = _hold(on_feature)

    result = _git("commit", "--allow-empty", "-m", "x", cwd=on_feature)

    assert result.returncode == 0, result.stderr
    assert not held.exists()
    log = f"sdd/decisions/{SESSION}.jsonl"
    assert _ok("show", "--name-only", "--format=", "HEAD", cwd=on_feature) == log
    events = [json.loads(line)["event"] for line in (on_feature / log).read_text(encoding="utf-8").splitlines()]
    assert events == ["asked", "promoted"]


def test_pathspec_commit_leaves_the_log_for_the_next_commit(on_feature: Path) -> None:
    """A pathspec commit runs hooks on a temporary index; staging there would
    commit the log while leaving the real index behind HEAD."""
    _hold(on_feature)
    (on_feature / "a.txt").write_text("a\n", encoding="utf-8")
    _ok("add", "a.txt", cwd=on_feature)
    (on_feature / "a.txt").write_text("b\n", encoding="utf-8")

    result = _git("commit", "-m", "x", "--", "a.txt", cwd=on_feature)

    assert result.returncode == 0, result.stderr
    assert _ok("show", "--name-only", "--format=", "HEAD", cwd=on_feature) == "a.txt"
    assert _ok("status", "--porcelain", "--untracked-files=all", cwd=on_feature) == "?? sdd/decisions/" + (
        f"{SESSION}.jsonl"
    )


# --- pre-push ------------------------------------------------------------------


@pytest.fixture
def with_remote(on_feature: Path) -> Path:
    remote = on_feature.parent / "remote.git"
    _ok("init", "-q", "--bare", str(remote), cwd=on_feature.parent)
    _ok("remote", "add", "origin", str(remote), cwd=on_feature)
    return on_feature


@pytest.mark.parametrize(
    "refspec",
    [pytest.param("HEAD:master", id="head-to-master"), pytest.param("HEAD:refs/heads/main", id="head-to-main")],
)
def test_agent_push_to_master_is_blocked_whatever_the_local_branch(with_remote: Path, refspec: str) -> None:
    result = _git("push", "-q", "origin", refspec, cwd=with_remote)

    assert result.returncode != 0
    assert "Blocked: never push directly to" in result.stderr


def test_agent_push_of_a_work_branch_passes(with_remote: Path) -> None:
    result = _git("push", "-q", "origin", "feature", cwd=with_remote)

    assert result.returncode == 0, result.stderr


def test_human_push_to_master_passes(with_remote: Path) -> None:
    result = _git("push", "-q", "origin", "HEAD:master", cwd=with_remote, agent=False)

    assert result.returncode == 0, result.stderr


# --- the Claude Code side: installer, --no-verify, wiring -----------------------


def _bash(script: Path, *, cwd: Path, stdin: str = "") -> subprocess.CompletedProcess[str]:
    bash = hook_bash()
    if bash is None:
        pytest.fail("no usable bash (Git Bash on Windows); a skip would read as a pass")
    return subprocess.run(
        [bash, script.as_posix()], cwd=cwd, input=stdin, env=_env(agent=False), capture_output=True, text=True
    )


def test_installer_points_git_at_the_checkouts_githooks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _ok("init", "-q", str(repo), cwd=tmp_path)
    (repo / ".githooks").mkdir()

    result = _bash(HOOKS / "install-githooks.sh", cwd=repo)

    assert result.returncode == 0
    assert Path(_ok("config", "--get", "core.hooksPath", cwd=repo)) == (repo / ".githooks").resolve()


def test_installer_leaves_another_tools_hooks_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _ok("init", "-q", str(repo), cwd=tmp_path)
    (repo / ".githooks").mkdir()
    _ok("config", "core.hooksPath", ".husky", cwd=repo)

    result = _bash(HOOKS / "install-githooks.sh", cwd=repo)

    assert result.returncode == 0
    assert _ok("config", "--get", "core.hooksPath", cwd=repo) == ".husky"


def _payload(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("git commit --no-verify -m x", id="commit"),
        pytest.param("git -C /r push --no-verify origin x", id="push-with-C"),
        pytest.param("cd x && git commit -m 'y' --no-verify", id="after-a-quoted-message"),
    ],
)
def test_no_verify_is_denied(command: str, tmp_path: Path) -> None:
    result = _bash(HOOKS / "deny-no-verify.sh", cwd=tmp_path, stdin=_payload(command))

    assert result.returncode == 2
    assert "Blocked: --no-verify" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("git commit -m 'drop --no-verify from the docs'", id="in-single-quotes"),
        pytest.param('git commit -m "mention --no-verify"', id="in-double-quotes"),
        pytest.param("git log --oneline", id="unrelated"),
    ],
)
def test_no_verify_in_quoted_text_passes(command: str, tmp_path: Path) -> None:
    result = _bash(HOOKS / "deny-no-verify.sh", cwd=tmp_path, stdin=_payload(command))

    assert result.returncode == 0
    assert result.stderr == ""


def _handlers(event: str) -> list[dict[str, str]]:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return [handler for entry in settings["hooks"][event] for handler in entry["hooks"]]


def test_settings_wire_the_installer_and_the_deny_not_the_old_gates() -> None:
    session_start = [h["command"] for h in _handlers("SessionStart")]
    pre_tool = _handlers("PreToolUse")

    assert any("install-githooks.sh" in command for command in session_start)
    (deny,) = [h for h in pre_tool if "deny-no-verify.sh" in h["command"]]
    assert "if" not in deny, "an if: prefix match would miss `git -C <path> commit --no-verify`"
    assert not [h for h in pre_tool if "gate-commit" in h["command"] or "gate-push" in h["command"]]
