"""Run pytest under a resource-bounded xdist worker count (BK-277).

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

import math
import os
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_HEADROOM_FRACTION = 0.75


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


def _has_explicit_n(args: Sequence[str]) -> bool:
    """True if the forwarded args already select a worker count."""
    return any(a == "-n" or a.startswith(("-n", "--numprocesses")) for a in args)


def main() -> int:
    forwarded = sys.argv[1:]
    try:
        workers = compute_workers(os.cpu_count(), os.environ.get("RS_TEST_WORKERS"))
    except ValueError as exc:
        print(f"run_tests: {exc}", file=sys.stderr)
        return 2

    argv = [sys.executable, "-m", "pytest"]
    if not _has_explicit_n(forwarded):
        argv += ["-n", str(workers)]
    argv += forwarded

    # subprocess.run + sys.exit, not os.execvp: the latter is spawn+wait on
    # Windows and raises on launch failure rather than returning a code.
    # subprocess.run is platform-neutral and surfaces exit codes uniformly.
    return subprocess.run(argv, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
