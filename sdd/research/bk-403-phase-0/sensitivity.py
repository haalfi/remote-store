"""Post-hoc sensitivity of the H replay to D5's two coarsest FULL rows.

Throwaway research (RFC-0019 Phase 0). NOT an input to the verdict: the
targets and stop criterion were fixed before the run and are judged on the
frozen precision rule set (plan.md). This answers a different question for the
report: how much of the FULL rate comes from treating every ``pyproject.toml``
edit and every ``.github/**`` edit as FULL?

Variant S1, a wrapper around the frozen selector (selector.py is untouched):

- a ``pyproject.toml`` edit whose parsed difference lies only under
  ``tool.hatch.envs.*.scripts``, ``tool.ruff``, ``tool.mypy``,
  ``tool.bumpversion`` or ``project.version`` is removed from the FULL row and
  contributes its layer-4 readers instead;
- a ``.github/**`` edit outside ``ci.yml`` and ``.github/actions/`` likewise.

Usage: python sdd/research/bk-403-phase-0/sensitivity.py 2026-07-04 d306e0223 <universe.json> <out.json>
"""

from __future__ import annotations

import json
import statistics
import sys
import tomllib
from collections import Counter
from pathlib import Path

from metrics import Universe
from p0tree import Tree
from replay_h import population
from selector import Readers, changed_paths, select

SAFE_PREFIXES = ("tool.ruff", "tool.mypy", "tool.bumpversion", "project.version")


def flatten(d: object, prefix: str = "") -> dict[str, object]:
    if isinstance(d, dict):
        out: dict[str, object] = {}
        for k, v in d.items():
            out |= flatten(v, f"{prefix}.{k}" if prefix else k)
        return out
    return {prefix: d}


def pyproject_relaxable(base: Tree, head: Tree) -> bool:
    try:
        a = flatten(tomllib.loads(base.text("pyproject.toml") or ""))
        b = flatten(tomllib.loads(head.text("pyproject.toml") or ""))
    except tomllib.TOMLDecodeError:
        return False
    diff = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}

    def safe(k: str) -> bool:
        parts = k.split(".")
        if k.startswith(SAFE_PREFIXES):
            return True
        return len(parts) >= 5 and parts[:3] == ["tool", "hatch", "envs"] and parts[4] == "scripts"

    return all(safe(k) for k in diff)


def main() -> None:
    since, end, upath, out = sys.argv[1:5]
    U = Universe(Path(upath))
    readers = Readers.load()
    rows = []
    relaxed_paths = Counter()
    for sha, pr in population(since, end):
        base, head = Tree(f"{sha}^"), Tree(sha)
        changes = changed_paths(f"{sha}^", sha)
        keep, removed = [], []
        for s, p in changes:
            if (
                p == "pyproject.toml"
                and pyproject_relaxable(base, head)
                or p.startswith(".github/")
                and p != ".github/workflows/ci.yml"
                and not p.startswith(".github/actions/")
            ):
                removed.append(p)
            else:
                keep.append((s, p))
        res = select(base, head, keep, "precision", readers=readers)
        if res.mode != "FULL":
            for p in removed:
                relaxed_paths[p] += 1
                for r in readers.for_path(p, base):
                    if r.startswith("dir:"):
                        res.add(r[4:], f"{p}: layer 4 reader (S1)")
                    else:
                        res.add(r, f"{p}: layer 4 reader (S1)")
        m = U.metrics(res)
        rows.append({"pr": int(pr), "mode": m["mode"], "wall_share": m["wall_share"], "removed": removed})
    full = sum(1 for r in rows if r["mode"] == "FULL")
    summary = {
        "derivation": f"sensitivity.py {since} {end} {upath}",
        "variant": "S1 (post-hoc, not a verdict input)",
        "n": len(rows),
        "full": full,
        "full_rate": full / len(rows),
        "median_wall_share": statistics.median(r["wall_share"] for r in rows),
        "prs_with_relaxed_paths": sum(1 for r in rows if r["removed"]),
        "relaxed_paths_in_selected_prs": dict(relaxed_paths.most_common()),
        "rows": rows,
    }
    Path(out).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print({k: v for k, v in summary.items() if k != "rows"})


if __name__ == "__main__":
    main()
