"""Gather D7 escape-log evidence for each candidate miss in the R replay.

Throwaway research (RFC-0019 Phase 0). For every run with a job or test miss,
collect: the changed paths the selector saw, the precision jobs, the failing
job's failed steps (``gh run view --json jobs``, which survives log expiry),
and every other ``ci.yml`` run on the same head SHA with its conclusion (an
unchanged rerun that passed is the evidence D7 requires for
"nondeterministic").

Usage: python sdd/research/bk-403-phase-0/r_evidence.py <r_replay.jsonl> <red_runs.json> <end> <out.json>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from p0tree import Tree, git
from selector import Readers, changed_paths, select


def gh_json(*args: str):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def main() -> None:
    rows = [json.loads(x) for x in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
    red = {r["databaseId"]: r for r in json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))}
    end = sys.argv[3]
    readers = Readers.load()
    out = []
    for r in rows:
        if not any(r[v]["job_misses"] or r[v]["test_misses"] for v in ("pilot", "precision")):
            continue
        full_sha = red[r["run"]]["headSha"]
        mb = git("merge-base", full_sha, end).strip()
        changes = changed_paths(mb, full_sha)
        res = select(Tree(mb), Tree(full_sha), changes, "precision", readers=readers)
        jobs = gh_json("run", "view", str(r["run"]), "--json", "jobs") or {"jobs": []}
        failed_steps = {
            j["name"]: [s["name"] for s in j.get("steps", []) if s.get("conclusion") == "failure"]
            for j in jobs["jobs"]
            if j["conclusion"] == "failure"
        }
        same_sha = gh_json(
            "run", "list", "--workflow", "ci.yml", "--commit", full_sha, "--limit", "20",
            "--json", "databaseId,conclusion,attempt,event,createdAt",
        )  # fmt: skip
        out.append(
            {
                "run": r["run"],
                "sha": r["sha"],
                "title": r["title"],
                "changed": [p for _, p in changes],
                "precision_mode": res.mode,
                "precision_jobs": sorted(res.jobs),
                "pilot": r["pilot"],
                "precision": r["precision"],
                "failed_steps": failed_steps,
                "runs_on_same_sha": same_sha,
                "attempt": red[r["run"]].get("attempt"),
            }
        )
        print(r["run"], len(changes), res.mode, failed_steps, same_sha, flush=True)
    Path(sys.argv[4]).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
