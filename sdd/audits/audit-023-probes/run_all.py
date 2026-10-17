"""Run every audit-023 probe and record its output next to it as ``<probe>.out``.

Run from the repo root: ``hatch run python sdd/audits/audit-023-probes/run_all.py``.
A probe that exits non-zero is reported and its output still recorded. The
recorded outputs are the ones audit-023 quotes; a later run that differs means
the code moved, not that the audit is wrong.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SKIP = {"run_all.py"}


def main() -> int:
    failed = []
    probes = sorted(p for p in HERE.rglob("*.py") if p.name not in SKIP)
    for probe in probes:
        proc = subprocess.run(  # noqa: S603
            [sys.executable, str(probe)], capture_output=True, text=True, timeout=600, check=False
        )
        probe.with_suffix(".out").write_text(proc.stdout + proc.stderr)
        status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
        if proc.returncode:
            failed.append(probe)
        print(f"{status:8} {probe.relative_to(HERE)}")
    print(f"{len(probes)} probes, {len(failed)} non-zero")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
