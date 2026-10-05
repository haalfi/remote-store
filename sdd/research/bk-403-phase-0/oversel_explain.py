"""Explain coverage-minimal tests the selector did not select (D7 cross-check).

Throwaway research. For each SELECTED H diff with a gap, list per changed
``src/`` file the lines and enclosing function that the unselected tests
executed, so each gap can be classified (missing rule vs finalizer/GC
attribution, which coverage charges to whatever test is running).

Usage: python sdd/research/bk-403-phase-0/oversel_explain.py <contexts.json> <oversel.json> <h.jsonl> <out.json>
"""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

from metrics import Universe
from p0tree import Tree
from selector import Readers, changed_paths, select


def enclosing(tree: ast.Module, line: int) -> str:
    best = "<module>"
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= line <= (node.end_lineno or 0):
            best = node.name
    return best


def main() -> None:
    cov = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    gaps = {
        r["pr"] for r in json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["rows"] if r["minimal_not_selected"]
    }
    U = Universe(Path("tmp/universe.json"))
    readers = Readers.load()
    files = {
        k.replace("\\", "/")[k.replace("\\", "/").index("src/") :]: v
        for k, v in cov["files"].items()
        if "src/" in k.replace("\\", "/")
    }
    out = {}
    for line in Path(sys.argv[3]).read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec["variant"] != "precision" or rec["pr"] not in gaps:
            continue
        sha = rec["sha"]
        changes = changed_paths(f"{sha}^", sha)
        res = select(Tree(f"{sha}^"), Tree(sha), changes, "precision", readers=readers)
        sel, _, _ = U.expand(res)
        per_file = {}
        for _, p in changes:
            if not p.startswith("src/") or p not in files:
                continue
            src_tree = ast.parse((Path(p)).read_text(encoding="utf-8")) if Path(p).exists() else None
            funcs: dict[str, set[str]] = defaultdict(set)
            for ln, ctxs in files[p]["contexts"].items():
                for c in ctxs:
                    nid = c.split("|", 1)[0]
                    if c and nid in U.cost and nid not in sel:
                        fn = enclosing(src_tree, int(ln)) if src_tree else "?"
                        funcs[fn].add(nid)
            if funcs:
                per_file[p] = {fn: {"tests": len(t), "sample": sorted(t)[:3]} for fn, t in funcs.items()}
        out[rec["pr"]] = per_file
    Path(sys.argv[4]).write_text(json.dumps(out, indent=1), encoding="utf-8")
    for pr, pf in out.items():
        print(pr, {p: {fn: v["tests"] for fn, v in d.items()} for p, d in pf.items()})


if __name__ == "__main__":
    main()
