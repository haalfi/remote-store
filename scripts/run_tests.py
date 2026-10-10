"""Run pytest under a resource-bounded xdist worker count (BK-277), one suite at a time (BK-419).

``pytest -n auto`` spawns one worker per logical CPU. On a high-core
workstation that saturates the machine — and with several agent/dev sessions
running suites at once it has pegged and crashed the box. This launcher caps
the worker count to leave headroom, so the suite still profits from available
cores without taking all of them.

Worker count (``compute_workers``):

* ``RS_TEST_WORKERS`` env var wins when set:
  - ``auto`` -> one worker per logical CPU (the old ``-n auto`` behaviour),
  - a positive integer -> exactly that many.
* Otherwise: ``max(1, floor(cpu * 0.75) - 1)`` — roughly three-quarters of the
  cores, minus one, never below 1. (8 cores -> 5, 16 -> 11, 32 -> 23; a 1-2
  core machine -> 1.)

Suite lock (``acquire_suite_lock``): one launcher run at a time per machine,
across sessions, worktrees and clones. Two suites at once have stalled each
other near the end of the run, so a second run waits for the first, printing
who holds the lock, and gives up with exit code ``EXIT_LOCK_TIMEOUT`` after
``RS_TEST_LOCK_WAIT`` seconds (default 300; ``0`` refuses at once). The lock is
an OS file lock on ``RS_TEST_LOCK_FILE`` (default under the user's home), so
the OS drops it when the holder exits by any path, a crash or a kill included,
and a dead holder never blocks a later run. A run started from inside a locked
suite (``RS_TEST_LOCK_HELD`` set) skips the lock instead of waiting on its own
parent. Bounds: the lock belongs to one launcher call. If the launcher is killed
while its pytest children survive, the lock is free while they still run. A hatch
script with two launcher calls (``test``, ``test-cov*``) takes it twice, so
another session's suite can run between its passes (never during one), and the
script can wait twice.

Per-test timeout: ``--timeout=300`` (pytest-timeout) is added unless the
forwarded args set ``--timeout``; ``RS_TEST_TIMEOUT=<seconds>`` changes it and
``0`` leaves it off. A hung test then fails by name instead of the run hanging.
CI calls pytest inline, so neither the lock nor the timeout applies there.

Everything after the script name is forwarded verbatim to pytest, so the
``hatch`` scripts pass their own flags (``-p no:benchmark``, ``--cov=...``).
If the forwarded args already set ``-n`` / ``--numprocesses`` the launcher does
not add its own, so an explicit override on the command line still wins.

Usage::

    python scripts/run_tests.py -p no:benchmark
    RS_TEST_WORKERS=4 python scripts/run_tests.py -p no:benchmark   # override
    python scripts/run_tests.py -n 0 tests/aio                      # caller's -n wins
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from collections.abc import Sequence

_HEADROOM_FRACTION = 0.75
_DEFAULT_TIMEOUT = 300
# Under both session bounds with room for a run: a foreground tool call ends at
# 600 s, a background wait at 15 min (CLAUDE.md § Parallel tests).
_DEFAULT_LOCK_WAIT = 300.0
# EX_TEMPFAIL: distinct from pytest's own 0-5, and "try again later" is what it means.
EXIT_LOCK_TIMEOUT = 75
_HELD_ENV = "RS_TEST_LOCK_HELD"


def compute_workers(cpu_count: int | None, override: str | None) -> int:
    """Return the xdist worker count for this machine.

    Args:
        cpu_count: Logical CPU count (``os.cpu_count()``); ``None`` is treated
            as a single core.
        override: Raw ``RS_TEST_WORKERS`` value (``None`` when unset). ``"auto"``
            (case-insensitive) means one worker per CPU; a positive integer
            string means exactly that many.

    Raises:
        ValueError: If *override* is set but is neither ``"auto"`` nor a
            positive integer.
    """
    cpus = cpu_count or 1
    if override is not None and override.strip():
        token = override.strip()
        if token.lower() == "auto":
            return max(1, cpus)
        try:
            n = int(token)
        except ValueError:
            raise ValueError(f"RS_TEST_WORKERS must be 'auto' or a positive integer, got {override!r}") from None
        if n < 1:
            raise ValueError(f"RS_TEST_WORKERS must be >= 1, got {override!r}")
        return n
    return max(1, math.floor(cpus * _HEADROOM_FRACTION) - 1)


def _env_seconds(name: str, default: float) -> float:
    """Read a non-negative number of seconds from env var *name*.

    Raises:
        ValueError: If the variable is set but is not a non-negative number.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        raise ValueError(f"{name} must be a number of seconds, got {raw!r}") from None
    if value < 0 or not math.isfinite(value):
        raise ValueError(f"{name} must be >= 0, got {raw!r}")
    return value


def _has_explicit_n(args: Sequence[str]) -> bool:
    """True if the forwarded args already select a worker count.

    ``startswith("-n")`` covers both the separate-token form (``-n 4``) and the
    glued form (``-n4`` / ``-n0``); ``--numprocesses`` covers the long option in
    either ``--numprocesses 4`` or ``--numprocesses=4`` shape.
    """
    return any(a.startswith(("-n", "--numprocesses")) for a in args)


def _has_explicit_timeout(args: Sequence[str]) -> bool:
    """True if the forwarded args already set pytest-timeout's ``--timeout``."""
    return any(a == "--timeout" or a.startswith("--timeout=") for a in args)


def suite_lock_path() -> Path:
    """Return the machine-wide lock file: ``RS_TEST_LOCK_FILE``, else one under the home directory.

    Not under the checkout, because every worktree and clone must resolve the
    same file; not under the temp directory, because ``TMP`` can differ
    between sessions.
    """
    override = os.environ.get("RS_TEST_LOCK_FILE")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "remote-store" / "test-suite.lock"


def _try_lock(fd: int) -> bool:
    """Take an exclusive, non-blocking OS lock on *fd*; False if another process holds it."""
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


class SuiteLock:
    """A held suite lock. The OS releases it when the process exits; ``release`` frees it early."""

    def __init__(self, fd: int, info_path: Path) -> None:
        self._fd: int | None = fd
        self._info_path = info_path

    def release(self) -> None:
        if self._fd is None:
            return
        with contextlib.suppress(OSError):
            self._info_path.unlink(missing_ok=True)
        # Closing the descriptor drops the OS lock on every platform.
        os.close(self._fd)
        self._fd = None


def _describe_holder(info_path: Path) -> str:
    """Best-effort description of the current holder, from the info file it wrote."""
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        return f"pid {info['pid']} in {info['cwd']}, started {info['started']}"
    except (OSError, ValueError, KeyError, TypeError):
        return "an unknown process"


def acquire_suite_lock(
    path: Path,
    wait_seconds: float,
    *,
    poll: float = 1.0,
    report_every: float = 30.0,
    out: TextIO | None = None,
) -> SuiteLock | None:
    """Take the suite lock at *path*, waiting up to *wait_seconds*; None if it stayed busy.

    Prints who holds the lock when it first has to wait, then a progress line
    every *report_every* seconds, to *out* (default stderr).
    """
    stream = out if out is not None else sys.stderr
    path.parent.mkdir(parents=True, exist_ok=True)
    info_path = path.with_name(path.name + ".info")
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    start = time.monotonic()
    next_report = start
    try:
        while not _try_lock(fd):
            now = time.monotonic()
            waited = now - start
            if waited >= wait_seconds:
                print(
                    f"run_tests: gave up after {waited:.0f}s; the suite lock {path} is held by "
                    f"{_describe_holder(info_path)}. Raise RS_TEST_LOCK_WAIT to wait longer.",
                    file=stream,
                    flush=True,
                )
                os.close(fd)
                return None
            if now >= next_report:
                print(
                    f"run_tests: waiting for the suite lock ({waited:.0f}s of {wait_seconds:.0f}s); "
                    f"held by {_describe_holder(info_path)}",
                    file=stream,
                    flush=True,
                )
                next_report = now + report_every
            time.sleep(min(poll, max(0.0, wait_seconds - waited)))
    except BaseException:
        os.close(fd)
        raise
    info = {"pid": os.getpid(), "cwd": os.getcwd(), "started": dt.datetime.now().isoformat(timespec="seconds")}
    # The description is a courtesy to waiters; the lock is what counts.
    with contextlib.suppress(OSError):
        info_path.write_text(json.dumps(info), encoding="utf-8")
    return SuiteLock(fd, info_path)


def main() -> int:
    forwarded = sys.argv[1:]
    try:
        workers = compute_workers(os.cpu_count(), os.environ.get("RS_TEST_WORKERS"))
        timeout = _env_seconds("RS_TEST_TIMEOUT", _DEFAULT_TIMEOUT)
        lock_wait = _env_seconds("RS_TEST_LOCK_WAIT", _DEFAULT_LOCK_WAIT)
    except ValueError as exc:
        print(f"run_tests: {exc}", file=sys.stderr)
        return 2

    argv = [sys.executable, "-m", "pytest"]
    if not _has_explicit_n(forwarded):
        argv += ["-n", str(workers)]
    if timeout > 0 and not _has_explicit_timeout(forwarded):
        argv.append(f"--timeout={timeout:g}")
    argv += forwarded

    lock = None
    if not os.environ.get(_HELD_ENV):
        lock = acquire_suite_lock(suite_lock_path(), lock_wait)
        if lock is None:
            return EXIT_LOCK_TIMEOUT
    env = {**os.environ, _HELD_ENV: os.environ.get(_HELD_ENV) or str(os.getpid())}
    try:
        # subprocess.run + sys.exit, not os.execvp: the latter is spawn+wait on
        # Windows and raises on launch failure rather than returning a code.
        # subprocess.run is platform-neutral and surfaces exit codes uniformly.
        return subprocess.run(argv, check=False, env=env).returncode
    finally:
        if lock is not None:
            lock.release()


if __name__ == "__main__":
    sys.exit(main())
