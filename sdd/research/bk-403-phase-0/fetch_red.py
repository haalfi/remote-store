"""Fetch population R: past red ``ci.yml`` pull_request runs, their failing
jobs and failing test ids. Throwaway research (RFC-0019 Phase 0).

Uses the ``gh`` CLI only (``gh run list``, ``gh run view --json jobs``,
``gh run view --log-failed``). A run whose log has expired is kept with
``log: "unavailable"``, so the report can say how many were usable.

Usage: python sdd/research/bk-403-phase-0/fetch_red.py <limit> <out.json>
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

FAILED = re.compile(r"(?:^|\s)(FAILED|ERROR) (tests/[^\s]+?\.py(?:::[^\s]+)?)(?:\s|$)")


def gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout


def main() -> None:
    limit, out = sys.argv[1], sys.argv[2]
    runs = json.loads(
        gh(
            "run", "list", "--workflow", "ci.yml", "--status", "failure", "--limit", limit,
            "--json", "databaseId,event,headBranch,headSha,createdAt,displayTitle,attempt",
        )
    )  # fmt: skip
    runs = [r for r in runs if r["event"] == "pull_request"]
    rows = []
    for r in runs:
        rid = str(r["databaseId"])
        row = dict(r)
        try:
            jobs = json.loads(gh("run", "view", rid, "--json", "jobs"))["jobs"]
            row["failed_jobs"] = sorted({j["name"] for j in jobs if j["conclusion"] == "failure"})
            row["cancelled_jobs"] = sorted({j["name"] for j in jobs if j["conclusion"] == "cancelled"})
        except RuntimeError as e:
            row["failed_jobs"] = None
            row["error"] = str(e)
        try:
            log = gh("run", "view", rid, "--log-failed")
            tests: dict[str, set[str]] = {}
            for line in log.splitlines():
                job = line.split("\t", 1)[0]
                for m in FAILED.finditer(line):
                    tests.setdefault(job, set()).add(m.group(2))
            row["failed_tests"] = {k: sorted(v) for k, v in tests.items()}
            row["log"] = "ok" if log.strip() else "empty"
        except RuntimeError as e:
            row["failed_tests"] = {}
            row["log"] = "unavailable"
            row["log_error"] = str(e)
        rows.append(row)
        print(rid, row.get("failed_jobs"), row["log"], sum(len(v) for v in row["failed_tests"].values()), flush=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)
    print(f"runs {len(rows)}, logs ok {sum(1 for r in rows if r['log'] == 'ok')}")


if __name__ == "__main__":
    main()
