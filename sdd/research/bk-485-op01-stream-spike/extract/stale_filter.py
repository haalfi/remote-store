"""Count closed decisions (Open items: none) that a later open item names.

Usage: stale_filter.py RECORD.md
"""

import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
head, _, items = text.partition("\n## Open items\n")
closed = []
for m in re.finditer(r"^### (OP-01/D(\d+)):.*?^- \*\*Open items:\*\* ([^\n]+)$", head, re.M | re.S):
    if m.group(3).strip().rstrip(".") == "none":
        closed.append(int(m.group(2)))
# each open item is a "- `OP-01/On`:" bullet; collect the decisions it names
named: dict[int, set[str]] = {}
for m in re.finditer(r"^- `(OP-01/O\d+)`:(.*?)(?=^- `OP-01/O|\Z)", items, re.M | re.S):
    for d in re.findall(r"\bD(\d+)\b", m.group(2)):
        named.setdefault(int(d), set()).add(m.group(1).removeprefix("OP-01/"))
hit = {d: sorted(named[d], key=lambda o: int(o[1:])) for d in closed if d in named}
print(f"closed decisions: {len(closed)}; mentioned anywhere in a later open item: {len(hit)} (upper bound)")
# strict: decisions an item is *about* -- "a reopen of / a note on / a gap in OP-01/Dn and Dm"
# up to " against", the first "(" or the first ". "
about: dict[int, set[str]] = {}
for m in re.finditer(
    r"^- `(OP-01/O\d+)`: (?:an? |three )?(?:reopen|note|gaps?)[^\n]*?(?:of|on|in) (.*?)(?: against|\(|\. )",
    items,
    re.M | re.S,
):
    for d in re.findall(r"\bD(\d+)\b", m.group(2)):
        about.setdefault(int(d), set()).add(m.group(1).removeprefix("OP-01/"))
strict = {d: sorted(about[d], key=lambda o: int(o[1:])) for d in closed if d in about}
print(f"closed decisions an open item reopens, notes or finds a gap in: {len(strict)}")
for d, os_ in strict.items():
    print(f"  D{d}: {', '.join(os_)}")
