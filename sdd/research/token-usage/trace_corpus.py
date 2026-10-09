"""Five months of traces: what each one read, how large it was then, and how long its review loop ran.

No transcripts needed. For every ``sdd/traces/*.yml`` the creation commit is
found (``git log --diff-filter=A``) and every step's file is sized *at that
commit* (``git cat-file --batch-check``), so a trace from May is measured
against May's files. Sizes bound what was read from above: most steps read one
section.

Writes ``corpus.json`` (one row per trace; repo data only) into ``--data``
for ``pr_model.py`` and ``ship_era.py``, and ``results/trace_corpus.json``.
"""

from __future__ import annotations

import collections
import json
import re
import statistics as st
import subprocess

import _common as c
import yaml

PROCESS = re.compile(
    r"^(CLAUDE\.md|CONTRIBUTING\.md|sdd/(CLAUDE-REFERENCE|BACKLOG|BACKLOG-DONE|000-process|TESTING|DESIGN|"
    r"AUTHORING|DOCUMENTATION|CONTENT-RULES|DRIFT-RULES|GATE-INVENTORY)\.md|sdd/traces/_schema\.yml|"
    r"\.claude/(skills|agents|hooks)/|sdd/adrs/|sdd/rfcs/rfc-0015|sdd/backlog/)"
)


def kind(p: str) -> str:
    if PROCESS.match(p):
        return "process"
    if p.startswith(("src/", "tests/", "examples/")):
        return "code"
    if p.startswith(("sdd/specs/", "sdd/formal/")):
        return "spec"
    if p.startswith(("docs-src/", "README", "FEATURES", "CHANGELOG")):
        return "docs"
    if p.startswith("sdd/traces/"):
        return "traces"
    if p.startswith(("scripts/", ".github/", "pyproject")):
        return "tooling"
    return "other-sdd" if p.startswith("sdd/") else "other"


def main(argv=None) -> int:
    args = c.resolve(c.parser(__doc__).parse_args(argv))
    repo = args.repo_root

    def git(*a, inp=None):
        return subprocess.run(
            ["git", "-C", str(repo), *a], input=inp, capture_output=True, text=True, encoding="utf-8", errors="replace"
        ).stdout

    created = {}
    sha = date = None
    for line in git("log", "--diff-filter=A", "--name-only", "--format=@%H %aI", "--", "sdd/traces/").splitlines():
        if line.startswith("@"):
            sha, date = line[1:].split(" ")
        elif line.strip().endswith(".yml"):
            created[line.strip()] = (sha, date)  # log is newest first, so the oldest add wins

    rows, queries = [], []
    for f in sorted((repo / "sdd" / "traces").glob("*.yml")):
        rel = f"sdd/traces/{f.name}"
        if f.name.startswith("_") or rel not in created:
            continue
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(d, dict):
            continue
        sha, date = created[rel]
        steps = []
        for ph in d.get("phases") or []:
            for s in (ph.get("steps") or []) if isinstance(ph, dict) else []:
                if isinstance(s, dict) and s.get("file"):
                    p = str(s["file"]).split("#")[0].strip()
                    steps.append({"file": p, "outcome": s.get("outcome")})
                    queries.append(f"{sha}:{p}")
        rv = d.get("review") or {}
        rows.append(
            {
                "trace": f.name,
                "id": d.get("id"),
                "sha": sha,
                "date": date[:10],
                "month": date[:7],
                "steps": steps,
                "rounds": rv.get("review_rounds", d.get("review_rounds")),
                "findings": rv.get("findings"),
                "disc": len(d.get("discovery_followups") or []),
            }
        )
    res = git("cat-file", "--batch-check=%(objectsize)", inp="\n".join(queries) + "\n").splitlines()
    sizes = {q: int(r) if r.strip().isdigit() else 0 for q, r in zip(queries, res, strict=False)}
    for row in rows:
        for s in row["steps"]:
            s["bytes"] = sizes.get(f"{row['sha']}:{s['file']}", 0)
            s["kind"] = kind(s["file"])
    args.data.mkdir(parents=True, exist_ok=True)
    (args.data / "corpus.json").write_text(json.dumps(rows), encoding="utf-8")

    def distinct(r, k=None):
        return {s["file"]: s["bytes"] for s in r["steps"] if k is None or s["kind"] == k}

    by_m = collections.defaultdict(list)
    for r in rows:
        by_m[r["month"]].append(r)
    monthly = {}
    for m in sorted(by_m):
        rs = by_m[m]
        kb = [sum(distinct(r).values()) / 1024 for r in rs]
        pkb = [sum(distinct(r, "process").values()) / 1024 for r in rs]
        rr = [r["rounds"] for r in rs if isinstance(r["rounds"], int)]
        monthly[m] = {
            "traces": len(rs),
            "kb_read_mean": round(st.mean(kb)),
            "process_share_of_bytes_pct": c.pct(sum(pkb), sum(kb), 0),
            "review_rounds_median": st.median(rr) if rr else None,
        }
    top = collections.Counter()
    for r in rows:
        for f in {s["file"] for s in r["steps"] if s["kind"] == "process"}:
            top[f] += 1
    reach = {}
    for f, _ in top.most_common(6):
        reach[f] = {
            m: c.pct(sum(1 for r in rs if any(s["file"] == f for s in r["steps"])), len(rs), 0)
            for m, rs in sorted(by_m.items())
        }
    rr_all = [r["rounds"] for r in rows if isinstance(r["rounds"], int)]
    head = git("rev-parse", "--short", "HEAD").strip()
    payload = {
        "traces": len(rows),
        "first": min(r["date"] for r in rows),
        "last": max(r["date"] for r in rows),
        "monthly": monthly,
        "process_file_reach_pct_by_month": reach,
        "review_rounds_all": {"n": len(rr_all), "median": st.median(rr_all), "max": max(rr_all)},
        "traces_with_review_block": sum(1 for r in rows if r["findings"] is not None),
    }
    c.write_result(args.results, "trace_corpus", "trace_corpus", {"sdd/traces at commit": head}, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
