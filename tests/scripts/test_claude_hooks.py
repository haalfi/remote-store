"""Unit tests for .claude/hooks/notify-attention.sh.

Pins the four contract points the hook must hold, because a Claude Code hook
fails silently by design: a non-zero exit or a stray stderr line surfaces as a
"hook error" in the transcript rather than as a test failure, so nothing else
in the repo would notice a regression.

1. Always exits 0. A notification backend is never a reason to stall a session.
2. Never writes to stderr, including when ``/dev/tty`` does not exist. The bell
   redirect is brace-wrapped for exactly this: a bare ``>/dev/tty 2>/dev/null``
   still leaks the shell's own "no such device" error, which is the container
   and CI case. See ``_run`` for why this pin needs ``start_new_session``.
3. Falls back to its ``$1`` label whenever the event carries no question
   headers, which covers Notification payloads and unparseable stdin alike.
4. Strips ``"`` and ``\\`` from headers before they reach the ``osascript``
   string literal.

The notification backend is exercised through a stub on ``PATH`` rather than a
mock (``sdd/TESTING.md`` Rule 6): the hook resolves it with ``command -v``, so
a real executable is the only thing that tests the branch it actually takes.

Deliberately **not** marked ``pytest.mark.os_sensitive``, though it is plainly
OS-specific (bash, ``jq``, symlinks, ``/dev/tty``, POSIX ``PATH``). That marker
means "run on macOS and Windows CI" (``pyproject.toml``), and the subject is a
bash hook that only ever executes on the developer's own machine under a
POSIX shell; the Windows leg would fail on the first ``bash``. Recorded here
because the ripple-check "New test file" row asks for the decision, and an
unstated one reads the same as a forgotten one.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

# Everything the hook shells out to, plus bash itself. A PATH holding only
# these is how the "no notification backend" case is built: it cannot simply be
# an empty PATH, because then bash is unreachable and the test measures nothing.
_REQUIRED_BINARIES = ("bash", "cat", "jq", "tr")

_HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "notify-attention.sh"

_ASK_PAYLOAD = (
    '{"hook_event_name":"PreToolUse","tool_name":"AskUserQuestion",'
    '"tool_input":{"questions":[{"header":"Scope"},{"header":"Strength"}]}}'
)
_IDLE_PAYLOAD = '{"hook_event_name":"Notification","notification_type":"idle_prompt"}'
_INJECTION_PAYLOAD = r'{"tool_input":{"questions":[{"header":"say \"hi\" \\ now"}]}}'


@pytest.fixture
def stub_bin(tmp_path: Path) -> Path:
    """A PATH entry whose ``notify-send`` records its arguments instead of firing.

    Without this the suite would raise real desktop notifications on any
    machine that has libnotify installed.
    """
    bin_dir = _bare_bin(tmp_path)
    log = tmp_path / "notify.log"
    stub = bin_dir / "notify-send"
    stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> {log}\n')
    stub.chmod(0o755)
    return bin_dir


def _bare_bin(tmp_path: Path) -> Path:
    """A PATH entry holding only the hook's dependencies, no notification backend."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in _REQUIRED_BINARIES:
        found = shutil.which(name)
        assert found is not None, f"{name} is required to exercise the hook"
        (bin_dir / name).symlink_to(found)
    return bin_dir


def _run(payload: str, label: str, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    # start_new_session detaches the controlling terminal (setsid), which is what
    # makes contract point 2 a real assertion rather than an environment quirk.
    # A child normally inherits the parent's tty, so run from an interactive
    # shell the bell write *succeeds*, no stderr appears, and the assertion holds
    # whether or not the brace guard exists — green on a developer machine, red
    # only in tty-less CI. That is the vacuous green sdd/TESTING.md warns about.
    # Detaching makes /dev/tty absent everywhere, so the guard is pinned on every
    # machine; it also stops the suite ringing the developer's terminal bell.
    env = {"PATH": str(bin_dir)}
    return subprocess.run(
        ["bash", str(_HOOK), label],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        start_new_session=True,
    )


@pytest.mark.parametrize(
    ("payload", "label", "expected"),
    [
        pytest.param(_ASK_PAYLOAD, "a decision", "Scope, Strength", id="headers-used"),
        pytest.param(_IDLE_PAYLOAD, "your next prompt", "your next prompt", id="no-questions-field"),
        pytest.param("not json at all", "a decision", "a decision", id="unparseable-stdin"),
        pytest.param("", "a decision", "a decision", id="empty-stdin"),
        pytest.param(_INJECTION_PAYLOAD, "a decision", "say hi  now", id="quotes-stripped"),
    ],
)
def test_notification_message(payload: str, label: str, expected: str, stub_bin: Path) -> None:
    """The composed message uses question headers, else the fallback label."""
    result = _run(payload, label, stub_bin)

    assert result.returncode == 0
    assert result.stderr == ""
    delivered = (stub_bin.parent / "notify.log").read_text()
    assert delivered.strip() == f"Claude Code Waiting on you: {expected}"


def test_survives_missing_notification_backend(tmp_path: Path) -> None:
    """No backend and no controlling terminal is a normal container run, not an error.

    Pins the brace-wrapped ``/dev/tty`` redirect: an unguarded one leaks a shell
    error here even though the command's own stderr is redirected.
    """
    result = _run(_ASK_PAYLOAD, "a decision", _bare_bin(tmp_path))

    assert result.returncode == 0
    assert result.stderr == ""
