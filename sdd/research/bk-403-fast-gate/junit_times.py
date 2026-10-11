"""Aggregate a JUnit XML run: slowest tests, and seconds per top-level test area and per file.

Usage: python sdd/research/bk-403-fast-gate/junit_times.py tmp/fastgate-junit.xml [--json OUT]
``--json`` writes ``{test file: summed seconds}`` for the gate's estimator.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def file_of(case: ET.Element) -> str:
    cls = case.get("classname", "")
    parts = cls.split(".")
    # classname is dotted module[.Class]; find the longest prefix that is a file
    for i in range(len(parts), 0, -1):
        p = "/".join(parts[:i]) + ".py"
        if Path(p).exists():
            return p
    return cls


def main() -> None:
    root = ET.parse(sys.argv[1]).getroot()
    cases = list(root.iter("testcase"))
    per_file: Counter[str] = Counter()
    per_area: Counter[str] = Counter()
    slow = []
    for c in cases:
        t = float(c.get("time", 0) or 0)
        f = file_of(c)
        per_file[f] += t
        area = "/".join(f.split("/")[:2]) + "/"
        per_area[area] += t
        slow.append((t, f"{f}::{c.get('name')}"))
    total = sum(per_file.values())
    print(f"{len(cases)} cases, {total:.1f} s summed")
    print("slowest tests:")
    for t, n in sorted(slow, reverse=True)[:15]:
        print(f"  {t:6.1f}  {n}")
    print("per area:")
    for a, t in per_area.most_common(12):
        print(f"  {t:6.1f}  {a}")
    print("slowest files:")
    for f, t in per_file.most_common(12):
        print(f"  {t:6.1f}  {f}")
    if "--json" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--json") + 1])
        out.write_text(json.dumps({k: round(v, 3) for k, v in sorted(per_file.items())}, indent=0), encoding="utf-8")


if __name__ == "__main__":
    main()
