"""List the decisions whose Amends line names a slice decision, and who amends each.

Usage (repo root):
    hatch run python sdd/research/bk-485-op01-stream-spike/freeze-1/amends.py sdd/observe/records/OP-01.md
Slice: D2, D6, D7, D15 to D18, D20, D36. Direct amendments only; chains are not followed.
"""

import re
import sys
from pathlib import Path

SLICE = {2, 6, 7, 15, 16, 17, 18, 20, 36}
text = Path(sys.argv[1]).read_text(encoding="utf-8")
head, _, _ = text.partition("\n## Axis status\n")
secs = re.split(r"^(?=### OP-01/D\d+:)", head, flags=re.M)
amended_by: dict[int, list[str]] = {}
for s in secs:
    m = re.match(r"### OP-01/D(\d+): (.*)", s)
    if not m:
        continue
    d, title = int(m.group(1)), m.group(2).strip()
    am = re.search(r"^- \*\*Amends:\*\*\s*(.*(?:\n  .*)*)", s, re.M)
    if am:
        targets = " ".join(am.group(1).split())
        for t in re.findall(r"\bD(\d+)\b", targets.split(".")[0]):
            amended_by.setdefault(int(t), []).append(f"D{d}")
        if any(int(t) in SLICE for t in re.findall(r"\bD(\d+)\b", targets)):
            print(f"D{d}: {title}\n   Amends: {targets[:300]}")
print()
for d in sorted(SLICE):
    print(f"D{d} amended by: {', '.join(amended_by.get(d, [])) or '-'}")
