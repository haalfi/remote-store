"""Replay population H (historical PR diffs) through both rule sets.

Throwaway research (RFC-0019 Phase 0). For every squash-merged PR commit on the
first parent of <end> since <since> whose diff matches ``CODE_PAT``, select
with the pilot and precision variants (and the precision variant read
literally, D5 as written), and write one JSON line per PR and variant.

Usage:
  python sdd/research/bk-403-phase-0/replay_h.py 2026-07-04 d306e0223 <universe.json> <out.jsonl>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from metrics import Universe
from p0tree import Tree, git
from selector import CODE_PAT, Readers, changed_paths, select


def population(since: str, end: str) -> list[tuple[str, str]]:
    out = []
    for line in git("log", "--first-parent", end, f"--since={since}", "--format=%H %s").splitlines():
        m = re.search(r"\(#(\d+)\)$", line)
        if not m:
            continue
        sha = line.split()[0]
        files = git("diff", "--name-only", f"{sha}^", sha).split()
        if any(CODE_PAT.search(f) for f in files):
            out.append((sha, m.group(1)))
    return out


def main() -> None:
    since, end, upath, opath = sys.argv[1:5]
    U = Universe(Path(upath))
    readers = Readers.load()
    pop = population(since, end)
    with open(opath, "w", encoding="utf-8") as fh:
        for sha, pr in pop:
            base, head = Tree(f"{sha}^"), Tree(sha)
            changes = changed_paths(f"{sha}^", sha)
            for variant, literal in (("pilot", False), ("precision", False), ("precision-literal", True)):
                v = "precision" if variant.startswith("precision") else "pilot"
                res = select(base, head, changes, v, readers=readers, literal=literal)
                rec = {"pr": int(pr), "sha": sha[:10], "variant": variant, **U.metrics(res)}
                rec["n_changed"] = len(changes)
                rec["src_touched"] = any(p.startswith("src/") for _, p in changes)
                fh.write(json.dumps(rec) + "\n")
            print(pr, flush=True)
    print(f"replayed {len(pop)} PRs")


if __name__ == "__main__":
    main()
