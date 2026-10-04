"""Stage-1 test universe and per-test cost for the Phase 0 share metrics.

Throwaway research. One ``pytest --collect-only -q --stage=1`` on the current
tree gives the node ids; ``.test_durations_pass1`` gives seconds per node id.
A node id missing from the durations file gets its file's mean, else the
global median (plan.md § Metric definitions).

Usage: hatch run python sdd/research/bk-403-phase-0/universe.py <out.json>
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    py, out = sys.executable, Path(sys.argv[1])
    r = subprocess.run(
        [py, "-m", "pytest", "--collect-only", "-q", "--stage=1", "-p", "no:benchmark", "-p", "no:randomly"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    ids = [ln.strip() for ln in r.stdout.splitlines() if "::" in ln and not ln.startswith(" ")]
    durations: dict[str, float] = json.loads((ROOT / ".test_durations_pass1").read_text(encoding="utf-8"))
    by_file: dict[str, list[float]] = defaultdict(list)
    for nid, s in durations.items():
        by_file[nid.split("::", 1)[0]].append(s)
    median = statistics.median(durations.values())
    cost: dict[str, float] = {}
    measured = 0
    for nid in ids:
        if nid in durations:
            cost[nid] = durations[nid]
            measured += 1
        else:
            f = nid.split("::", 1)[0]
            cost[nid] = statistics.fmean(by_file[f]) if by_file.get(f) else median
    out.write_text(
        json.dumps(
            {
                "derivation": "pytest --collect-only -q --stage=1 -p no:benchmark; costs from .test_durations_pass1",
                "n": len(ids),
                "measured": measured,
                "median_s": median,
                "total_s": sum(cost.values()),
                "cost": cost,
            }
        ),
        encoding="utf-8",
    )
    print(f"collected {len(ids)}, with a measured duration {measured}, estimated total {sum(cost.values()):.1f} s")


if __name__ == "__main__":
    main()
