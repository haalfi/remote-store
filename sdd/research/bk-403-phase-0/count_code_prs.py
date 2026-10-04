"""Count squash-merged PRs, code PRs (ci.yml CODE_PAT) and src/ PRs in a window.

RFC-0019 Phase 0 population H; throwaway research, not a gate.
Usage: python sdd/research/bk-403-phase-0/count_code_prs.py <since> <end-ref>
"""

import re
import subprocess
import sys

CODE = re.compile(
    r"^(src|tests|examples|scripts)/|^pyproject\.toml$|^\.python-version$|^\.test_durations_pass1$|^docs-src/reference/FEATURES\.md$|^docs-src/_data/graph/|^\.github/workflows/|^\.github/actions/"
)
since, end = sys.argv[1], sys.argv[2]
log = subprocess.run(
    ["git", "log", "--first-parent", end, f"--since={since}", "--format=%H %s"],
    capture_output=True,
    text=True,
    check=True,
).stdout.splitlines()
prs = [line for line in log if re.search(r"\(#\d+\)$", line)]
code = 0
srcn = 0
for line in prs:
    h = line.split()[0]
    files = subprocess.run(["git", "diff", "--name-only", f"{h}^", h], capture_output=True, text=True).stdout.split()
    if any(CODE.search(f) for f in files):
        code += 1
    if any(f.startswith("src/") for f in files):
        srcn += 1
print(f"since {since} to {end}: PRs {len(prs)}, code {code}, touching src/ {srcn}")
