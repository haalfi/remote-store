"""Check pilot.toml against OP-01's record and the freeze-1 rules, and print its views.

Usage (repo root):
    hatch run python sdd/research/bk-511-op01-behaviour-classification/check_pilot.py \
        sdd/observe/records/OP-01.md

1. Vocabulary: every facet value is in its vocabulary.
2. Coverage: every pilot decision is cited by a clause's decided_by or listed in
   record_text. The pilot set is the stream slice, every transitive amender of
   it, and CITED_NOT_AMENDING: decisions that decide the slice's behaviour
   without an Amends line reaching it.
3. Rules: every rule id of the spike's freeze-1 stream_rules.toml maps to a clause.
4. Views: counts per facet and path x local.
Exit 1 on a vocabulary, coverage or rule failure.
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
# Decide the slice without an Amends line reaching it: the cancelled close
# (D49 amends D19; D94, D118, D138 build on D50) and the failure phases (D96 amends D35 etc.).
CITED_NOT_AMENDING = [49, 94, 96, 118, 138]
VOCAB = {
    "path": {
        "success",
        "end",
        "caller-error",
        "storage-failure",
        "cancellation",
        "release",
        "non-promise",
        "lifetime-end",
    },
    "form": {"stream", "whole"},
    "api": {"sync", "async", "both"},
    "state": {"Open", "Exhausted", "Failed", "Closed", "not-Closed", "any", "open-call"},
    "kind": {"structure", "function", "single call", "lifetime", "environment", "liveness"},
    "status": {"decided", "partly", "implied", "open"},
}
TRIGGER = re.compile(r"^(O1|O2|O3|Runtime|GC|E([1-9]|1[0-9]))$")
SCOPE = re.compile(r"^(portable|variation:.+|backend:.+)$")
LOCAL = re.compile(r"^(pass|untested|not-offered|C[1-8])$")


def main(record: Path) -> int:
    ds = parse(record.read_text(encoding="utf-8"))
    by = collections.defaultdict(set)
    for d, v in ds.items():
        for t in v["amends"]:
            by[t].add(d)
    pilot, todo = set(SLICE), list(SLICE)
    while todo:
        for a in by.get(todo.pop(), ()):
            if a not in pilot:
                pilot.add(a)
                todo.append(a)
    pilot |= set(CITED_NOT_AMENDING)

    spec = tomllib.loads((HERE / "pilot.toml").read_text(encoding="utf-8"))
    clauses, text_only = spec["clause"], {int(r["decision"][1:]) for r in spec["record_text"]}
    problems = []
    for c in clauses:
        for facet, allowed in VOCAB.items():
            if c[facet] not in allowed:
                problems.append(f"{c['id']}: {facet} = {c[facet]!r}")
        if not TRIGGER.match(c["trigger"]):
            problems.append(f"{c['id']}: trigger = {c['trigger']!r}")
        if not SCOPE.match(c["scope"]):
            problems.append(f"{c['id']}: scope = {c['scope']!r}")
        if not LOCAL.match(c["local"]):
            problems.append(f"{c['id']}: local = {c['local']!r}")
        for d in c["decided_by"]:
            if int(d[1:]) not in ds:
                problems.append(f"{c['id']}: {d} is no decision")
    cited = {int(d[1:]) for c in clauses for d in c["decided_by"]}
    uncovered = sorted(pilot - cited - text_only)
    problems += [f"pilot decision D{d} is in no clause and not in record_text" for d in uncovered]
    rule_ids = {r["id"] for r in tomllib.loads(RULES.read_text(encoding="utf-8"))["rule"]}
    mapped = {r for c in clauses for r in c.get("rule", [])}
    problems += [f"rule {r} maps to no clause" for r in sorted(rule_ids - mapped)]
    problems += [f"clause names unknown rule {r}" for r in sorted(mapped - rule_ids)]

    print(f"pilot decisions: {len(pilot)}; clauses: {len(clauses)}; record-text only: {len(text_only)}")
    outside = sorted(cited - pilot)
    print("cited outside the pilot set:", ", ".join(f"D{d}" for d in outside) or "-")
    for facet in ("path", "trigger", "state", "api", "scope", "kind", "status", "local", "axis"):
        print(f"{facet}: {dict(collections.Counter(c[facet] for c in clauses).most_common())}")
    print("path x local:")
    tab = collections.defaultdict(collections.Counter)
    for c in clauses:
        tab[c["path"]]["gap" if c["local"].startswith("C") else c["local"]] += 1
    for p, cnt in tab.items():
        print(f"  {p:<16} {dict(cnt)}")
    print(
        "open or partly decided:",
        ", ".join(f"{c['id']} ({c.get('gap', '-')})" for c in clauses if c["status"] != "decided"),
    )
    print("Local gaps:", ", ".join(f"{c['id']}:{c['local']}" for c in clauses if c["local"].startswith("C")))
    print("Result:", "OK" if not problems else "FAIL")
    for p in problems:
        print("  ", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
