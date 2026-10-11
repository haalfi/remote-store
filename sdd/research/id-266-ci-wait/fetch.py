"""Fetch every ``ci.yml`` pull_request run and every merged PR as JSON.

Throwaway research (ID-266). Needs an authenticated ``gh``.

Usage: python sdd/research/id-266-ci-wait/fetch.py tmp/ci-wait
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = "haalfi/remote-store"


def gh_json(args: list[str]):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def main() -> None:
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    # The runs endpoint caps each query at 1000 results, so walk back in time
    # with created=<oldest until a window comes back short.
    runs: list = []
    seen: set = set()
    upper = None
    while True:
        path = f"repos/{REPO}/actions/workflows/ci.yml/runs?event=pull_request&per_page=100"
        if upper:
            path += f"&created=%3C{upper}"
        pages = gh_json(["api", "--paginate", "--slurp", path])
        batch = [r for page in pages for r in page["workflow_runs"] if r["id"] not in seen]
        if not batch:
            break
        runs.extend(batch)
        seen.update(r["id"] for r in batch)
        if len(batch) < 1000:
            break
        upper = min(r["created_at"] for r in batch)
    keep = [
        {
            "id": r["id"],
            "branch": r["head_branch"],
            "created": r["created_at"],
            "started": r.get("run_started_at"),
            "updated": r["updated_at"],
            "conclusion": r["conclusion"],
        }
        for r in runs
    ]
    (outdir / "runs.json").write_text(json.dumps(keep, indent=1), encoding="utf-8")
    prs = gh_json(
        ["pr", "list", "-R", REPO, "--state", "merged", "--limit", "5000", "--json", "number,headRefName,mergedAt"]
    )
    (outdir / "prs.json").write_text(json.dumps(prs, indent=1), encoding="utf-8")
    print(f"runs={len(keep)} merged_prs={len(prs)}")


if __name__ == "__main__":
    main()
