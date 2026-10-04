"""Replay population R (past red CI runs) through both rule sets.

Throwaway research (RFC-0019 Phase 0). For every run in ``fetch_red.py``'s
output: fetch its head commit if missing, select on the diff from the merge
base with <end> to the head, then check every failing job and failing test:

- a failing job the fast lane would not run is a **job miss** (its failures
  were invisible to the fast lane);
- a failing test in a run job that the selection does not hold is a
  **test miss**;
- jobs outside ``code`` (``docs``, ``verify-*``) and the ``gate`` aggregator
  are not the selector's and are counted apart.

Misses are candidates; each is classified by hand per D7 § Escape log with the
evidence that class requires.

Usage: python sdd/research/bk-403-phase-0/replay_r.py <red_runs.json> <end> <out.jsonl>
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from metrics import contains
from p0tree import ROOT, Tree, git
from selector import CODE_JOBS, Readers, changed_paths, select

NOT_SELECTOR = {"docs", "verify-formal", "verify-tla", "gate", "setup"}
# Historical job names that ci.yml has since renamed (found by tallying every
# failing job id in R; an unmapped name would otherwise count as not-selector).
JOB_ALIASES = {"pyarrow24-check": "pyarrow-major-check"}


def job_id(name: str) -> str:
    jid = re.split(r"[ (]", name, maxsplit=1)[0]
    return JOB_ALIASES.get(jid, jid)


def have(sha: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=ROOT, capture_output=True).returncode == 0


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as fh_in:
        runs = json.load(fh_in)
    end, out = sys.argv[2], sys.argv[3]
    readers = Readers.load()
    stats = {"runs": len(runs), "usable": 0, "no_log": 0, "no_commit": 0, "no_jobs": 0}
    with open(out, "w", encoding="utf-8") as fh:
        for r in runs:
            if not r.get("failed_jobs"):
                stats["no_jobs"] = stats.get("no_jobs", 0) + 1
                continue
            if r.get("log") != "ok":
                stats["no_log"] += 1  # job-level check only; failing test ids unknown
            sha = r["headSha"]
            if not have(sha):
                subprocess.run(["git", "fetch", "-q", "origin", sha], cwd=ROOT, capture_output=True)
            if not have(sha):
                stats["no_commit"] += 1
                continue
            stats["usable"] += 1
            mb = git("merge-base", sha, end).strip()
            changes = changed_paths(mb, sha)
            base, head = Tree(mb), Tree(sha)
            rec = {"run": r["databaseId"], "sha": sha[:10], "branch": r["headBranch"], "title": r["displayTitle"],
                   "created": r["createdAt"], "failed_jobs": r["failed_jobs"], "n_changed": len(changes),
                   "log": r.get("log")}  # fmt: skip
            for v in ("pilot", "precision"):
                res = select(base, head, changes, v, readers=readers)
                job_misses, test_misses, other = [], [], []
                tests_by_job = r.get("failed_tests", {})
                for jname in r["failed_jobs"]:
                    jid = job_id(jname)
                    if jid in NOT_SELECTOR or jid not in CODE_JOBS:
                        other.append(jname)
                        continue
                    if res.mode == "FULL":
                        continue
                    if jid not in res.jobs:
                        job_misses.append({"job": jname, "tests": sorted(tests_by_job.get(jname, []))})
                        continue
                    for t in tests_by_job.get(jname, []):
                        if not contains(res, t):
                            test_misses.append({"job": jname, "test": t})
                rec[v] = {
                    "mode": res.mode,
                    "full_reasons": res.full_reasons[:3],
                    "job_misses": job_misses,
                    "test_misses": test_misses,
                    "not_selector_jobs": other,
                }
            fh.write(json.dumps(rec) + "\n")
            print(r["databaseId"], rec["pilot"]["mode"], rec["precision"]["mode"],
                  len(rec["precision"]["job_misses"]), len(rec["precision"]["test_misses"]), flush=True)  # fmt: skip
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
