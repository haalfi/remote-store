"""``scripts/git_target.py``: which trees a Bash command's ``git <subcommand>`` runs in (BK-486).

The commit and push gates act once per tree this returns, so a miss skips the
gate and a false match promotes held decision records or blocks an unrelated
command. Pure string tests; the gates themselves run in
``test_hook_command_check.py``. Paths are POSIX-shaped, so the module is
skipped on Windows, where ``os.path`` joins them with backslashes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "git_target.py"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX path shapes")


@pytest.fixture(scope="module")
def git_target() -> Any:
    scripts = str(SCRIPT.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import git_target

    return git_target


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param("git commit -m x", ["/cwd"], id="bare"),
        pytest.param("git -C /abs/repo commit", ["/abs/repo"], id="absolute-C"),
        pytest.param("git -C a -C b commit", ["/cwd/a/b"], id="C-composes"),
        pytest.param('git -C "$PWD" commit -m x', ["/cwd"], id="PWD-is-the-cwd"),
        pytest.param("git --work-tree=/w commit", ["/cwd"], id="work-tree-keeps-the-repo"),
        pytest.param("git --git-dir=/r/.git commit", ["gitdir:/r/.git"], id="git-dir-picks-the-repo"),
        pytest.param("git -C /a --git-dir .git commit", ["gitdir:/a/.git"], id="git-dir-relative-to-C"),
        pytest.param("GIT_DIR=/r/.git git commit", ["gitdir:/r/.git"], id="GIT_DIR-assignment"),
        pytest.param("cd -- /wt && git commit", ["/wt"], id="cd-end-of-options"),
        pytest.param("cd -P -- /wt && git commit", ["/wt"], id="cd-option-then-end-of-options"),
        pytest.param("GIT_DIR=/r/.git ls; git commit", ["/cwd"], id="GIT_DIR-ends-at-separator"),
        pytest.param("time -p git commit", ["/cwd"], id="time-with-option"),
        pytest.param("cd -P /wt && git commit", ["/wt"], id="cd-with-option"),
        pytest.param("git -c a=b -C /r commit", ["/r"], id="valued-option-before-C"),
        pytest.param("cd /wt && git commit", ["/wt"], id="after-cd"),
        pytest.param("cd sub; git -C .. commit", ["/cwd"], id="cd-then-relative-C"),
        pytest.param('if true; then git commit -m "$X"; fi', ["/cwd"], id="after-keyword"),
        pytest.param("FOO=1 timeout 60 git commit", ["/cwd"], id="after-assignment-and-wrapper"),
        pytest.param("x=$(git commit -m y)", ["/cwd"], id="in-substitution"),
        pytest.param("ls\ngit commit", ["/cwd"], id="second-line"),
        pytest.param("git commit -m a && git -C /o commit -m b", ["/cwd", "/o"], id="two-invocations"),
        pytest.param("git commit -m 'unbalanced", ["/cwd"], id="unsplittable-falls-back-to-cwd"),
        pytest.param("nice -n 10 git commit", ["/cwd"], id="wrapper-valued-option"),
        pytest.param("timeout -s KILL 60 git commit", ["/cwd"], id="timeout-signal-and-duration"),
        pytest.param("sudo -u someone git commit", ["/cwd"], id="sudo-user"),
        pytest.param("env -u FOO BAR=1 git commit", ["/cwd"], id="env-unset-then-assignment"),
        pytest.param("env -C /other git commit", ["/other"], id="env-chdir-followed"),
        pytest.param("env --chdir=/other git -C sub commit", ["/other/sub"], id="env-chdir-then-C"),
        pytest.param("/usr/bin/git commit", ["/cwd"], id="absolute-git-path"),
        pytest.param("env -C /other ls; git commit", ["/cwd"], id="wrapper-chdir-ends-at-separator"),
    ],
)
def test_finds_each_invocation_and_its_tree(git_target: Any, command: str, expected: list[str]) -> None:
    assert git_target.targets(command, "commit", "/cwd") == expected


@pytest.mark.parametrize(
    "command",
    [
        pytest.param('gh pr create --body "run git -C p commit"', id="quoted-text"),
        pytest.param('git commit -m "then git push"', id="in-another-commits-message"),
        pytest.param("git log --grep commit", id="argument-of-another-subcommand"),
        pytest.param("git cat-file commit HEAD", id="object-type-argument"),
        pytest.param("git commit-tree x", id="longer-subcommand"),
        pytest.param("echo git commit", id="argument-of-another-command"),
    ],
)
def test_ignores_a_mention_that_runs_no_such_subcommand(git_target: Any, command: str) -> None:
    subcommand = "push" if "push" in command else "commit"
    assert git_target.targets(command, subcommand, "/cwd") == []


def _main(stdin: str, cwd: Path) -> list[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "commit"], input=stdin, capture_output=True, text=True, cwd=cwd, check=True
    )
    return result.stdout.splitlines()


def test_main_prints_one_tree_per_line(tmp_path: Path) -> None:
    payload = json.dumps({"tool_input": {"command": "git commit -m a; git -C sub commit -m b"}})

    assert _main(payload, tmp_path) == [str(tmp_path.resolve()), str(tmp_path.resolve() / "sub")]


@pytest.mark.parametrize("stdin", [pytest.param("not json", id="not-json"), pytest.param("{}", id="no-command")])
def test_main_prints_the_cwd_for_an_unreadable_payload(tmp_path: Path, stdin: str) -> None:
    """Fails closed, as ``command_mentions`` does: the gate still acts on the cwd."""
    assert _main(stdin, tmp_path) == [str(tmp_path.resolve())]
