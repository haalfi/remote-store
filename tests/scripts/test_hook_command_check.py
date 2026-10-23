"""The ``if:``-gated PreToolUse hooks act only on the command they gate (BK-459).

Claude Code runs an ``if:``-gated hook whenever it cannot tell which commands a
Bash input runs, regardless of the pattern (https://code.claude.com/docs/en/hooks).
Measured in a session: ``ls -d "${HOME}"`` was blocked by the ``echo`` deny hook and
drew the ``gh pr create`` advisory. Each hook therefore re-checks
``tool_input.command`` through ``.claude/hooks/command-check.sh``; these tests pin
that re-check on every hook that sources it, in both directions, plus its
fail-closed fallback.

Bounds: the hooks are run directly with a hand-built payload, so what Claude Code
actually sends and when it fires the hook are not exercised here; the payload shape
is the one the hooks reference documents. The hooks run for real, with the bash
``tests._helpers.hook_bash`` picks and the ``jq`` and ``git`` it sees; a missing
one fails rather than skips, because a skipped test reads as a pass. Not
``os_sensitive``: what is pinned is a regex over the command, which does not vary
by OS, and ``tooling-tests`` runs this module on every ``.claude/hooks/`` change.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests._helpers import hook_bash

_HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"
_ECHO_HINT = "echo → output text directly or use Write tool"


def _payload(command: str, tool: str = "Bash") -> str:
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}})


def _run(hook: str, stdin: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    bash = hook_bash()
    if bash is None:
        pytest.fail("no usable bash (Git Bash on Windows); a skip would read as a pass")
    # Ask the chosen bash, not this process: the tools must be on *its* PATH.
    missing = [
        tool
        for tool in ("jq", "git")
        if subprocess.run([bash, "-c", f"command -v {tool}"], capture_output=True, check=False).returncode != 0
    ]
    if missing:
        pytest.fail(f"{bash} cannot see {', '.join(missing)}; the hooks need them, and a skip would read as a pass")
    return subprocess.run(
        [bash, (_HOOKS / hook).as_posix(), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
        timeout=60,
    )


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("echo hi", id="bare"),
        pytest.param("echo ${HOME}", id="bare-with-expansion"),
        pytest.param("cd x && echo hi", id="after-and"),
        pytest.param("ls; echo hi", id="after-semicolon"),
        pytest.param("ls | echo hi", id="after-pipe"),
        pytest.param("FOO=1 BAR=2 echo hi", id="after-assignments"),
        pytest.param("x=$(echo hi)", id="in-substitution"),
        pytest.param("x=`echo hi`", id="in-backticks"),
        pytest.param("ls\necho hi", id="second-line"),
        pytest.param("echo", id="no-arguments"),
        pytest.param('if [ -n "$X" ]; then echo hi; fi', id="after-keyword"),
        pytest.param('timeout 60 echo "$X"', id="after-wrapper"),
        # A mention the re-check cannot tell from a run keeps the gate acting.
        pytest.param("git grep -n echo", id="mention-as-argument"),
        pytest.param("ls ./echo", id="mention-in-path"),
    ],
)
def test_deny_hook_blocks_a_command_that_mentions_its_runner(command: str) -> None:
    result = _run("deny-bare-runner.sh", _payload(command), _ECHO_HINT)

    assert result.returncode == 2
    assert result.stderr.strip() == f"Blocked: {_ECHO_HINT}"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param('ls -d "${HOME}"', id="unparseable-expansion"),
        pytest.param('ls -d "$PWD"', id="pwd-expansion"),
        pytest.param("echoes hi", id="runner-as-prefix"),
        pytest.param("printf 'my-echo'", id="runner-inside-a-word"),
    ],
)
def test_deny_hook_allows_a_command_that_does_not(command: str) -> None:
    result = _run("deny-bare-runner.sh", _payload(command), _ECHO_HINT)

    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize(
    "stdin",
    [
        pytest.param("", id="empty"),
        pytest.param("not json", id="not-json"),
        pytest.param(json.dumps({"tool_name": "Bash", "tool_input": {}}), id="no-command"),
    ],
)
def test_deny_hook_blocks_when_the_payload_is_unreadable(stdin: str) -> None:
    """A payload the re-check cannot read leaves the gate as it was: it blocks."""
    result = _run("deny-bare-runner.sh", stdin, _ECHO_HINT)

    assert result.returncode == 2


def test_pr_advisory_stays_silent_for_another_command() -> None:
    result = _run("warn-direct-pr.sh", _payload('ls -d "${HOME}"'))

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(
    "stdin",
    [
        pytest.param(_payload("gh pr create --fill"), id="bash-gh-pr-create"),
        pytest.param(_payload("git push && gh  pr create --fill"), id="bash-after-and"),
        pytest.param(
            json.dumps({"tool_name": "mcp__github__create_pull_request", "tool_input": {"title": "t"}}),
            id="mcp-create-pull-request",
        ),
    ],
)
def test_pr_advisory_fires_for_pr_creation(stdin: str) -> None:
    result = _run("warn-direct-pr.sh", stdin)

    assert result.returncode == 0
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "allow"
    assert decision["additionalContext"].startswith("Direct PR creation detected.")


@pytest.fixture
def repo_on_master(tmp_path: Path) -> Path:
    """A git repo on ``master``, where both gates block the command they gate."""
    subprocess.run(["git", "init", "-q", "-b", "master", str(tmp_path)], check=True)
    return tmp_path


@pytest.mark.parametrize(
    ("hook", "command"),
    [
        pytest.param("gate-commit.sh", "git commit -m x", id="commit"),
        pytest.param("gate-push.sh", "git push -u origin x", id="push"),
        pytest.param("gate-commit.sh", 'git -C "$PWD" commit -m x', id="commit-after-git-option"),
        pytest.param("gate-commit.sh", "git -C /abs/repo commit -m x", id="commit-after-git-C-path"),
        pytest.param("gate-push.sh", "git -c push.default=current push", id="push-after-git-option"),
        pytest.param("gate-push.sh", "git -C /abs/repo push -u origin x", id="push-after-git-C-path"),
        pytest.param("gate-commit.sh", 'if true; then git commit -m "$X"; fi', id="commit-after-keyword"),
    ],
)
def test_gate_blocks_its_command_on_master(hook: str, command: str, repo_on_master: Path) -> None:
    result = _run(hook, _payload(command), cwd=repo_on_master)

    assert result.returncode == 2
    assert "Blocked: never" in result.stderr


@pytest.mark.parametrize("hook", ["gate-commit.sh", "gate-push.sh"])
def test_gate_ignores_another_command_on_master(hook: str, repo_on_master: Path) -> None:
    """The misfire this pins blocked every unparseable command on master and,
    on a branch, staged ``sdd/decisions`` and ran lint or typecheck for it."""
    result = _run(hook, _payload('ls -d "${HOME}"'), cwd=repo_on_master)

    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize("hook", ["gate-commit.sh", "gate-push.sh"])
def test_gate_is_wired_without_an_if_filter(hook: str) -> None:
    """The gates filter themselves (above), so ``settings.json`` must not pre-filter them.

    Measured (BK-486 follow-up): ``if: "Bash(git commit*)"`` is a prefix match, so
    ``git -C <path> commit``, the form cloud sessions use, never ran the gate. The
    commit skipped the master block and lint, and held decision records stayed
    in ``sdd/decisions/.pending/`` unpromoted.
    """
    settings = json.loads((_HOOKS.parent / "settings.json").read_text(encoding="utf-8"))
    handlers = [
        handler
        for entry in settings["hooks"]["PreToolUse"]
        if entry.get("matcher") == "Bash"
        for handler in entry["hooks"]
        if hook in handler.get("command", "")
    ]

    assert len(handlers) == 1, f"expected one Bash PreToolUse handler for {hook}, found {len(handlers)}"
    assert "if" not in handlers[0], f"{hook} is pre-filtered by if: {handlers[0]['if']!r}"
