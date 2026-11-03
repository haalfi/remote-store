"""Check the behaviour clauses against OP-01's record and the freeze-1 rules, and print views.

Usage (repo root):
    hatch run python sdd/research/bk-511-op01-behaviour-classification/check.py \
        sdd/observe/records/OP-01.md [--pilot]

Clause files: pilot.toml, plus whole/*.toml unless --pilot. Facets: whole/SCHEMA.md.
1. Vocabulary: every facet value is in its vocabulary; clause ids are unique.
2. Coverage: every decision in scope is cited by a clause's decided_by or listed in
   record_text. Scope is the whole record, or with --pilot the stream slice, its
   transitive amenders and CITED_NOT_AMENDING (decisions that decide the slice
   without an Amends line reaching it).
3. Rules: every rule id of the spike's freeze-1 stream_rules.toml maps to a clause.
4. Views: counts per facet, path x form, the not-decided clauses, Local's gaps.
Exit 1 on a vocabulary, id, coverage or rule failure.
"""

from __future__ import annotations

import collections
import re
import sys
import tomllib
from pathlib import Path

from effective import parse

HERE = Path(__file__).resolve().parent
RULES = HERE.parents[0] / "bk-485-op01-stream-spike" / "freeze-1" / "stream_rules.toml"
SLICE = [2, 6, 7, 15, 16, 17, 18, 20, 36]
# The cancelled close (D49 amends D19; D94, D118, D138 build on D50) and the failure phases (D96).
CITED_NOT_AMENDING = [49, 94, 96, 118, 138]
VOCAB = {
    "path": {
        "success",
        "end",
        "absent",
        "caller-error",
        "storage-failure",
        "cancellation",
        "release",
        "concurrent",
        "non-promise",
        "lifetime-end",
        "configuration",
    },
    "form": {"stream", "whole", "text", "both", "all", "handle"},
    "api": {"sync", "async", "both"},
    "state": {"Open", "Exhausted", "Failed", "Closed", "not-Closed", "any", "open-call", "none"},
    "kind": {"structure", "function", "single call", "lifetime", "environment", "liveness"},
    "status": {"decided", "partly", "implied", "open"},
}
TRIGGER = re.compile(r"^(O1|O2|O3|Runtime|GC|E([1-9]|1[0-9]))$")
SCOPE = re.compile(r"^(portable|variation:.+|backend:.+)$")
LOCAL = re.compile(r"^(pass|untested|not-offered|C[1-8])$")
VIEWS = ("path", "form", "api", "state", "scope", "kind", "status", "local", "axis")


def pilot_scope(ds: dict) -> set[int]:
    by = collections.defaultdict(set)
    for d, v in ds.items():
        for t in v["amends"]:
            by[t].add(d)
    scope, todo = set(SLICE), list(SLICE)
    while todo:
        for a in by.get(todo.pop(), ()):
            if a not in scope:
                scope.add(a)
                todo.append(a)
    return scope | set(CITED_NOT_AMENDING)


def check_clause(c: dict, ds: dict) -> list[str]:
    bad = [f"{c['id']}: {f} = {c[f]!r}" for f, allowed in VOCAB.items() if c[f] not in allowed]
    trig = c["trigger"]
    if not isinstance(trig, list) or not trig or not all(TRIGGER.match(t) for t in trig):
        bad.append(f"{c['id']}: trigger = {trig!r}")
    if not SCOPE.match(c["scope"]):
        bad.append(f"{c['id']}: scope = {c['scope']!r}")
    if not LOCAL.match(c["local"]):
        bad.append(f"{c['id']}: local = {c['local']!r}")
    bad += [f"{c['id']}: {d} is no decision" for d in c["decided_by"] if int(d[1:]) not in ds]
    return bad


def main(record: Path, pilot_only: bool) -> int:
    ds = parse(record.read_text(encoding="utf-8"))
    files = [HERE / "pilot.toml"] + ([] if pilot_only else sorted((HERE / "whole").glob("*.toml")))
    clauses, text_only = [], {}
    for f in files:
        spec = tomllib.loads(f.read_text(encoding="utf-8"))
        clauses += spec.get("clause", [])
        text_only |= {int(r["decision"][1:]): f.name for r in spec.get("record_text", [])}

    problems = [p for c in clauses for p in check_clause(c, ds)]
    ids = collections.Counter(c["id"] for c in clauses)
    problems += [f"clause id {i} is used {n} times" for i, n in ids.items() if n > 1]
    scope = pilot_scope(ds) if pilot_only else set(ds)
    cited = {int(d[1:]) for c in clauses for d in c["decided_by"]}
    problems += [f"D{d} is in no clause and not in record_text" for d in sorted(scope - cited - set(text_only))]
    rule_ids = {r["id"] for r in tomllib.loads(RULES.read_text(encoding="utf-8"))["rule"]}
    mapped = {r for c in clauses for r in c.get("rule", [])}
    problems += [f"rule {r} maps to no clause" for r in sorted(rule_ids - mapped)]
    problems += [f"clause names unknown rule {r}" for r in sorted(mapped - rule_ids)]

    print(f"files: {', '.join(f.name for f in files)}")
    print(f"decisions in scope: {len(scope)}; clauses: {len(clauses)}; record-text only: {len(text_only)}")
    if pilot_only:
        print("cited outside the pilot set:", ", ".join(f"D{d}" for d in sorted(cited - scope)) or "-")
    for facet in VIEWS:
        print(f"{facet}: {dict(collections.Counter(c[facet] for c in clauses).most_common())}")
    world = collections.Counter(
        "World" if any(t.startswith("E") for t in c["trigger"]) else "caller/runtime" for c in clauses
    )
    print(f"trigger: {dict(world)}")
    rows = collections.Counter(t for c in clauses for t in c["trigger"] if t.startswith("E"))
    print("Environment rows cited:", dict(sorted(rows.items(), key=lambda kv: int(kv[0][1:]))))
    print("path x form:")
    tab = collections.defaultdict(collections.Counter)
    for c in clauses:
        tab[c["path"]][c["form"]] += 1
    for p, cnt in sorted(tab.items()):
        print(f"  {p:<16} {dict(cnt)}")
    print(
        "not decided:",
        ", ".join(f"{c['id']} ({c['status']}, {c.get('gap', '-')})" for c in clauses if c["status"] != "decided"),
    )
    print("Local gaps:", ", ".join(f"{c['id']}:{c['local']}" for c in clauses if c["local"].startswith("C")))
    print("Result:", "OK" if not problems else "FAIL")
    for p in problems:
        print("  ", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), "--pilot" in sys.argv[2:]))
