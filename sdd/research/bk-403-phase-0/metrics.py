"""Selection -> Phase 0 metrics (selected share, wall-clock share, jobs).

Throwaway research. Expands a ``Result``'s targets over the Stage-1 universe
(``universe.py``) at node-id granularity, applying fixture allowlists to
conformance node ids by their parametrize id.
"""

from __future__ import annotations

import json
import statistics
import tomllib
from collections import defaultdict
from typing import TYPE_CHECKING

from p0tree import ROOT
from selector import CODE_JOBS, CONFORMANCE, Result, covers

if TYPE_CHECKING:
    from pathlib import Path

_FIXTURE_IDS = set(
    tomllib.loads((ROOT / "tests/backends/fixtures/fixtures.toml").read_text(encoding="utf-8"))["fixture"]
)


class Universe:
    def __init__(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self.cost: dict[str, float] = data["cost"]
        self.total_n = len(self.cost)
        self.total_s = sum(self.cost.values())
        self.by_file: dict[str, list[str]] = defaultdict(list)
        for nid in self.cost:
            self.by_file[nid.split("::", 1)[0]].append(nid)
        self.fixture_of: dict[str, str | None] = {}
        for nid in self.cost:
            fid = None
            if "[" in nid and nid.startswith(CONFORMANCE):
                for tok in nid[nid.index("[") + 1 : -1].split("-"):
                    if tok in _FIXTURE_IDS:
                        fid = tok
                        break
            self.fixture_of[nid] = fid
        sizes = [len(v) for v in self.by_file.values()]
        self.median_file_n = statistics.median(sizes)
        self.median_file_s = statistics.median(sum(self.cost[n] for n in v) for v in self.by_file.values())

    def expand(self, res: Result) -> tuple[set[str], int, float]:
        """Selected node ids, plus imputed (count, seconds) for target files absent today."""
        if res.mode == "FULL":
            return set(self.cost), 0, 0.0
        sel: set[str] = set()
        imp_n, imp_s = 0, 0.0
        for k, allow in res.targets.items():
            if k.endswith("/"):
                files = [f for f in self.by_file if f.startswith(k)]
            else:
                files = [k] if k in self.by_file else []
                if not files and k.startswith("tests/") and k.rsplit("/", 1)[-1].startswith("test_"):
                    imp_n += int(self.median_file_n)
                    imp_s += self.median_file_s
            for f in files:
                for nid in self.by_file[f]:
                    if allow is None or not f.startswith(CONFORMANCE):
                        sel.add(nid)
                    else:
                        fid = self.fixture_of[nid]
                        if fid is None or fid in allow:
                            sel.add(nid)
        return sel, imp_n, imp_s

    def metrics(self, res: Result) -> dict:
        sel, imp_n, imp_s = self.expand(res)
        n = min(len(sel) + imp_n, self.total_n)
        s = min(sum(self.cost[x] for x in sel) + imp_s, self.total_s)
        jobs = [j for j in CODE_JOBS if j in res.jobs]
        return {
            "mode": res.mode,
            "full_reasons": res.full_reasons,
            "selected_n": n,
            "selected_share": n / self.total_n,
            "wall_s": s,
            "wall_share": s / self.total_s,
            "jobs": jobs,
            "n_jobs": len(jobs),
            "imputed_files": imp_n > 0,
        }


def contains(res: Result, nodeid_prefix: str, universe: Universe | None = None) -> bool:
    """Whether the selection holds the test named by ``file::name`` (prefix match on the name)."""
    if res.mode == "FULL":
        return True
    f = nodeid_prefix.split("::", 1)[0]
    for k, allow in res.targets.items():
        if not covers(k, f):
            continue
        if allow is None or not f.startswith(CONFORMANCE):
            return True
        tail = nodeid_prefix.split("::")[-1]
        if any(fid in tail for fid in allow):
            return True
    return False
