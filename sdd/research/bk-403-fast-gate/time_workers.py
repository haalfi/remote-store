"""Time the Stage-1 suite (no coverage) through the launcher at several worker counts.

Usage: python sdd/research/bk-403-fast-gate/time_workers.py 8 12 14 [--target tests/scripts/]
Runs one after another; prints wall seconds and the pytest summary line per run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    args = sys.argv[1:]
    target: list[str] = []
    if "--target" in args:
        i = args.index("--target")
        target = args[i + 1 :]
        args = args[:i]
    for n in args:
        env = {**os.environ, "RS_TEST_WORKERS": n}
        cmd = [sys.executable, "scripts/run_tests.py", "-p", "no:benchmark", "--stage=1", "-q", *target]
        if n == "0":
            cmd[2:2] = ["-n", "0"]
        t0 = time.monotonic()
        proc = subprocess.run(
            cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        wall = time.monotonic() - t0
        summary = next(
            (ln for ln in reversed(proc.stdout.splitlines()) if " in " in ln and ("passed" in ln or "failed" in ln)),
            "?",
        )
        print(f"workers={n:>3} rc={proc.returncode} wall={wall:6.1f}s  {summary.strip()}", flush=True)


if __name__ == "__main__":
    main()
