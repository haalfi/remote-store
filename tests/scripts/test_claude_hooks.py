"""Unit tests for .claude/hooks/notify-attention.sh.

Pins the contract points the hook must hold, because a Claude Code hook fails
silently by design: a non-zero exit or a stray stderr line surfaces as a
"hook error" in the transcript rather than as a test failure, so nothing else
in the repo would notice a regression.

1. Always exits 0. A notification backend is never a reason to stall a session.
2. Never writes to stderr, including when ``/dev/tty`` does not exist. The bell
   redirect is brace-wrapped for exactly this: a bare ``>/dev/tty 2>/dev/null``
   still leaks the shell's own "no such device" error, which is the container
   and CI case. See ``_run`` for why this pin needs ``start_new_session``.
3. The bell actually rings when a terminal *is* present. Pinned separately
   under a real pty, because point 2 detaches the terminal in every other test
   and would otherwise let the bell be deleted outright with the suite still
   green — and the hook calls it the primary channel.
4. Falls back to its ``$1`` label whenever the event carries no question
   headers, which covers Notification payloads and unparseable stdin alike.
5. Strips the characters that would break the ``osascript`` string literal —
   quote, backslash, and newline, since an AppleScript string cannot span lines
   — pinned on the ``osascript`` branch itself. Not a general sanitiser: other
   characters pass through, harmlessly, because the message is a single shell
   word that the shell does not re-expand.
6. The wiring in ``.claude/settings.json`` names a hook script that exists, so
   renaming the script cannot leave the hooks silently pointing at nothing.

All three notification backends are exercised through stubs on ``PATH`` rather
than mocks (``sdd/TESTING.md`` Rule 6): the hook resolves them with
``command -v``, so a real executable is the only thing that tests the branch it
actually takes. Which stub is on ``PATH`` selects the arm, so the ``osascript``
and PowerShell arms are reachable here without a macOS or Windows runner.

Deliberately **not** marked ``pytest.mark.os_sensitive``, though it is plainly
OS-specific (bash, ``jq``, symlinks, ``/dev/tty``, POSIX ``PATH``). That marker
means "run on macOS and Windows CI" (``pyproject.toml``). Windows would fail on
the first ``bash``; macOS would add only a real ``osascript``, which point 5
already covers via a stub, so the leg would buy coverage this file already has.
Recorded because the ripple-check "New test file" row asks for the decision, and
an unstated one reads the same as a forgotten one.
"""

from __future__ import annotations

import json
import re
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
_INJECTION_PAYLOAD = r'{"tool_input":{"questions":[{"header":"say \"hi\" \\ now\nnext"}]}}'


def _backend_stub(bin_dir: Path, name: str, log: Path) -> None:
    """Put an executable named *name* on *bin_dir* that records its argv to *log*."""
    stub = bin_dir / name
    stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> {log}\n')
    stub.chmod(0o755)


@pytest.fixture
def stub_bin(tmp_path: Path) -> Path:
    """A PATH entry whose ``notify-send`` records its arguments instead of firing.

    Without this the suite would raise real desktop notifications on any
    machine that has libnotify installed.
    """
    bin_dir = _bare_bin(tmp_path)
    _backend_stub(bin_dir, "notify-send", tmp_path / "notify.log")
    return bin_dir


@pytest.fixture
def osascript_bin(tmp_path: Path) -> Path:
    """A PATH entry with ``osascript`` but no ``notify-send``.

    The hook picks its backend with ``command -v`` in ``notify-send`` →
    ``osascript`` → PowerShell order, so withholding the first is what selects
    the second. That makes the macOS arm reachable on any POSIX runner, which is
    the only way the quote stripping is tested where it actually matters:
    ``osascript`` interpolates the message into a quoted AppleScript literal,
    while ``notify-send`` takes it as a plain argv element where a stray quote
    is harmless.
    """
    bin_dir = _bare_bin(tmp_path)
    _backend_stub(bin_dir, "osascript", tmp_path / "notify.log")
    return bin_dir


@pytest.fixture
def powershell_bin(tmp_path: Path) -> Path:
    """A PATH entry with only ``powershell.exe``, the last arm of the chain.

    Reachable here because selection is by ``command -v``, not by platform, so
    withholding the first two arms picks the third on any runner.
    """
    bin_dir = _bare_bin(tmp_path)
    _backend_stub(bin_dir, "powershell.exe", tmp_path / "notify.log")
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
        pytest.param(_INJECTION_PAYLOAD, "a decision", "say hi  nownext", id="literal-breakers-stripped"),
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


def test_osascript_literal_survives_quote_injection(osascript_bin: Path) -> None:
    """Contract point 5, pinned on the branch that actually builds a quoted literal.

    Asserts the whole argument rather than that the stripped text appears: a
    leaked ``"`` would still leave the text present while splitting the literal
    into a different AppleScript statement, which a substring check would pass.
    """
    result = _run(_INJECTION_PAYLOAD, "a decision", osascript_bin)

    assert result.returncode == 0
    assert result.stderr == ""
    delivered = (osascript_bin.parent / "notify.log").read_text().strip()
    assert delivered == '-e display notification "Waiting on you: say hi  nownext" with title "Claude Code"'


def test_powershell_arm_is_reached_when_it_is_the_only_backend(powershell_bin: Path) -> None:
    """The last arm of the chain fires, so no backend is dead in the suite.

    It beeps rather than showing the message, so there is nothing to assert about
    ``$MSG`` here — the contract is only that the arm is selected and invoked.
    """
    result = _run(_ASK_PAYLOAD, "a decision", powershell_bin)

    assert result.returncode == 0
    assert result.stderr == ""
    delivered = (powershell_bin.parent / "notify.log").read_text().strip()
    assert delivered == "-Command [System.Console]::Beep(880, 300)"


def test_settings_hook_commands_point_at_files_that_exist() -> None:
    """Contract point 6: the wiring names a script that is really there.

    The tests above run the hook by path, so they all keep passing if
    ``settings.json`` is left pointing at a renamed or deleted script — the
    wiring is the one part of the mechanism nothing else here touches. A hook
    with a bad path fails silently at runtime, which is the whole reason this
    module exists.

    Deliberately checks paths only, not matchers: a matcher's validity is a fact
    about Claude Code, not about this repo, so asserting it here would pin our
    guess rather than the product's behaviour.
    """
    settings = json.loads((_HOOK.parents[1] / "settings.json").read_text(encoding="utf-8"))
    commands = [
        handler["command"]
        for event in settings["hooks"].values()
        for entry in event
        for handler in entry["hooks"]
        if handler.get("type") == "command"
    ]
    referenced = {
        Path(match.group(1))
        for command in commands
        if (match := re.search(r'"\$CLAUDE_PROJECT_DIR"/(\S+\.sh)', command))
    }

    assert referenced, "expected settings.json to reference at least one hook script"
    project_dir = _HOOK.parents[2]
    missing = sorted(str(p) for p in referenced if not (project_dir / p).is_file())
    assert not missing, f"settings.json references hook scripts that do not exist: {missing}"


def test_bell_rings_when_a_terminal_is_present(tmp_path: Path) -> None:
    """Contract point 3: the hook's primary channel actually fires.

    Every other test detaches the controlling terminal to pin point 2, which
    leaves the bell unexercised — delete the ``/dev/tty`` line outright and they
    all still pass. This is the paired case, so the guard is asserted from both
    sides: bell present with a terminal, no stderr without one.

    ``pty.fork`` rather than ``openpty``: the child needs the pty as its
    *controlling* terminal for ``/dev/tty`` to resolve, which takes a new
    session plus TIOCSCTTY, not merely an inherited fd. Imported inside the
    function because ``pty`` is POSIX-only, and a module-level import would
    break collection on the Windows leg of ``test-cross-platform``.
    """
    import os
    import pty

    bin_dir = _bare_bin(tmp_path)
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(_ASK_PAYLOAD)

    pid, master_fd = pty.fork()
    if pid == 0:  # pragma: no cover - child is replaced by execve
        # Everything here must exit the child rather than raise. An escaping
        # exception would unwind into pytest's own machinery *in the forked
        # child*, which then reports and tears down a second time — turning a
        # missing file into unreadable double output.
        try:
            fd = os.open(str(payload_file), os.O_RDONLY)
            os.dup2(fd, 0)
            os.execve("/bin/bash", ["bash", str(_HOOK), "a decision"], {"PATH": str(bin_dir)})
        except BaseException:  # noqa: BLE001 -- in a forked child, nothing may escape
            os._exit(127)
        os._exit(127)

    chunks = []
    while True:
        try:
            data = os.read(master_fd, 1024)
        except OSError:  # EIO on Linux once the child closes the slave side
            break
        if not data:
            break
        chunks.append(data)
    os.close(master_fd)
    _, status = os.waitpid(pid, 0)

    assert os.waitstatus_to_exitcode(status) == 0
    assert b"\a" in b"".join(chunks)
