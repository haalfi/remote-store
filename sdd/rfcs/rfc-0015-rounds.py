#!/usr/bin/env python3
"""Derivation for RFC-0015 Table 1: ``review_rounds`` before and after a commit.

Population: traces added since ``<since>``, from
``git log --diff-filter=A --format= --name-only <since>..HEAD -- sdd/traces``
(underscore-prefixed files are schema, not traces). Value: the integer after
``^review_rounds:`` in each file; a trailing comment is ignored. The rest of
``sdd/traces/[!_]*.yml`` forms the "before" population. Prints sorted values
with trace names, then median and mean, for both.

Usage::

    python sdd/rfcs/rfc-0015-rounds.py 24d9464
"""

from __future__ import annotations

import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RX = re.compile(r"^review_rounds:\s*(\d+)", re.M)


def main(since: str) -> None:
    out = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "log",
            "--diff-filter=A",
            "--format=",
            "--name-only",
            f"{since}..HEAD",
            "--",
            "sdd/traces",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    added = {p for p in out if p.endswith(".yml") and not Path(p).name.startswith("_")}
    everything = {str(p.relative_to(ROOT)) for p in (ROOT / "sdd/traces").glob("[!_]*.yml")}
    for label, paths in ((f"since {since}", added), (f"before {since}", everything - added)):
        vals = []
        for p in sorted(paths):
            m = RX.search((ROOT / p).read_text())
            if m:
                vals.append((int(m.group(1)), Path(p).stem))
        vals.sort()
        nums = [v for v, _ in vals]
        print(f"{label}: n={len(nums)} median={statistics.median(nums)} mean={statistics.mean(nums):.2f}")
        print("  " + ", ".join(f"{n}:{name}" for n, name in vals))


if __name__ == "__main__":
    main(sys.argv[1])
