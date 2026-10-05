"""Merge the D5 layer-4 reader inventory and check two-method agreement.

Throwaway research (RFC-0019 Phase 0). Inputs: the runtime scans
(``readscan.py``; one directory of per-worker JSON per run, default order and
randomised orders) and the static scan (``staticreads.py``).

Every runtime hit is classified by the frame that made it:

- ``direct``: a frame in ``tests/``, ``scripts/`` or ``examples/`` read it;
- ``src``: library code under ``src/`` read it (e.g. ``_info.py`` listing
  ``ext/``);
- ``render``: ``linecache``/``inspect``/``traceback``/``warnings``/``logging``
  rendering source; order-dependent (research Appendix D);
- ``hypothesis``: Hypothesis harvesting literals from the source of every
  loaded first-party module (``hypothesis/internal/constants_ast.py``). Not
  in the table: it reads whatever happens to be imported, and a constant it
  harvests changes which examples are drawn, not what any test asserts. A
  miss through it is the nondeterministic escape class (D7);
- ``lib``: any other library frame; kept.

Targets kept: tracked files and tracked directories only. Cassettes are left
out, because their explicit layer-1 row owns them with a narrower selection.
A read whose frame is a conftest is attributed to that conftest's scope
(``dir:<d>/``).

Outputs: ``readers.json`` (the table the selector loads) and an agreement
report listing every reader found by only one method.

Usage:
  python sdd/research/bk-403-phase-0/inventory.py <rev> <static.json> <runtime-dir>... \
      --out sdd/research/bk-403-phase-0/readers.json --report <agreement.json>
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from p0tree import Tree

CASSETTE = re.compile(r"^tests/(?:.*/)?cassettes/")
RENDER = ("linecache", "inspect.py", "traceback.py", "warnings.py", "logging/", "tokenize.py")


def classify(via: str) -> str:
    if via.startswith("lib:"):
        lib = via[4:]
        if lib.startswith("hypothesis/"):
            return "hypothesis"
        if any(r in lib for r in RENDER):
            return "render"
        return "lib"
    frame = via.split(":", 1)[0]
    lib = via.split("(lib:", 1)[1].rstrip(")") if "(lib:" in via else ""
    if lib.startswith("hypothesis/"):
        return "hypothesis"
    if frame.startswith("src/"):
        return "render" if any(r in lib for r in RENDER) else "src"
    return "direct"


def load_runtime(dirs: list[str], tree: Tree):
    """reader -> target -> (kind, via, class); plus per-run reader sets."""
    out: dict[str, dict[str, tuple[str, str, str]]] = defaultdict(dict)
    per_run: dict[str, set[str]] = {}
    dropped = Counter()
    for d in dirs:
        run_readers: set[str] = set()
        for f in sorted(Path(d).glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            for test_file, targets in data.items():
                for tgt, (kind, via) in targets.items():
                    if tgt not in tree.files and tgt not in tree.dirs and tgt != ".":
                        dropped["untracked target"] += 1
                        continue
                    if CASSETTE.match(tgt):
                        dropped["cassette (owned by its layer-1 row)"] += 1
                        continue
                    cls = classify(via)
                    if cls == "hypothesis":
                        dropped["hypothesis constant harvesting"] += 1
                        continue
                    reader = test_file
                    vfile = via.split(":", 1)[0]
                    if vfile.endswith("conftest.py"):
                        reader = "dir:" + vfile[: -len("conftest.py")]
                    if tgt == reader:
                        dropped["test file reading itself"] += 1
                        continue
                    prev = out[reader].get(tgt)
                    if prev is None or prev[2] in ("render", "lib"):
                        out[reader][tgt] = (kind, via, cls)
                    run_readers.add(reader)
        per_run[d] = run_readers
    return out, per_run, dropped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rev")
    ap.add_argument("static")
    ap.add_argument("runtime", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args()
    tree = Tree(a.rev)

    static = json.loads(Path(a.static).read_text(encoding="utf-8"))["readers"]
    runtime, per_run, dropped = load_runtime(a.runtime, tree)

    reads: dict[str, set[str]] = defaultdict(set)
    scans: dict[str, set[str]] = defaultdict(set)
    for reader, targets in runtime.items():
        for tgt, (kind, _via, _cls) in targets.items():
            (scans if kind == "scan" else reads)[tgt].add(reader)
    for reader, items in static.items():
        for it in items:
            kind, tgt = it.split(":", 1)
            if CASSETTE.match(tgt):
                continue
            if kind == "scan":
                scans[tgt].add(reader)
            elif kind == "scan-tree":
                scans[tgt].add(reader)
                scans[f"{tgt}/*" if tgt != "." else "*"].add(reader)
            else:
                reads[tgt].add(reader)

    Path(a.out).write_text(
        json.dumps(
            {
                "derivation": f"inventory.py {a.rev} {a.static} " + " ".join(a.runtime),
                "reads": {k: sorted(v) for k, v in sorted(reads.items())},
                "scans": {k: sorted(v) for k, v in sorted(scans.items())},
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    rt = set(runtime)
    st = set(static)
    classes = {r: Counter(c for _, _, c in t.values()) for r, t in runtime.items()}
    report = {
        "rev": a.rev,
        "runtime_readers": len(rt),
        "static_readers": len(st),
        "both": sorted(rt & st),
        "per_run_readers": {d: len(s) for d, s in per_run.items()},
        "order_dependent": sorted(set.union(*per_run.values()) - set.intersection(*per_run.values())),
        "dropped": dict(dropped),
        "runtime_only": {
            r: {
                "classes": dict(classes[r]),
                "n_targets": len(runtime[r]),
                "sample": {t: [k, v] for t, (k, v, _c) in sorted(runtime[r].items())[:8]},
            }
            for r in sorted(rt - st)
        },
        "static_only": {r: static[r][:12] for r in sorted(st - rt)},
        "table": {"reads": len(reads), "scans": len(scans)},
    }
    Path(a.report).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(
        f"runtime readers {len(rt)}, static readers {len(st)}, both {len(rt & st)}, "
        f"runtime-only {len(rt - st)}, static-only {len(st - rt)}; "
        f"order-dependent {len(report['order_dependent'])}; dropped {dict(dropped)}; "
        f"table reads {len(reads)}, scans {len(scans)}"
    )


if __name__ == "__main__":
    main()
