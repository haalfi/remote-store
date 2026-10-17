"""Enumerate GLOB/TREE spec IDs and the test files that mark them (spec marker or mention)."""

import pathlib
import re

root = pathlib.Path(".")
spec_ids = {}
for f, pre in [("sdd/specs/018-glob.md", "GLOB"), ("sdd/specs/051-store-tree.md", "TREE")]:
    for m in re.finditer(rf"^##+ ({pre}-\d{{3}})", (root / f).read_text(), re.M):
        spec_ids[m.group(1)] = []
for t in sorted(root.glob("tests/**/*.py")):
    txt = t.read_text(errors="replace")
    for sid in spec_ids:
        if re.search(rf"spec\(\s*\"{sid}\"", txt):
            spec_ids[sid].append(str(t))
for sid, files in spec_ids.items():
    print(sid, files or "NO spec marker")
