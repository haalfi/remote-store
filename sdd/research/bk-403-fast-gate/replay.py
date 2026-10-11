"""Replay ``scripts/fast_gate.py``'s plan over merged PRs, per PR and per commit.

Usage: python sdd/research/bk-403-fast-gate/replay.py SINCE OUT.jsonl
(SINCE is a merge date, e.g. 2026-08-09; needs ``gh`` and the PR head refs
fetched as ``refs/rs-pr/<n>``, a namespace ``fetch --prune`` leaves alone:
``git fetch origin "+refs/pull/*/head:refs/rs-pr/*"``.)

Per PR: the diff from the first commit's parent to the PR head, Phase 0's
unit. Per commit: each commit against its parent, the unit a gate run on every
commit would see. Gate seconds are modelled from one measured run per member
(``STEP_SECONDS``); a selected test run costs ``TEST_STARTUP`` plus its share of
the rest.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import fast_gate as fg  # noqa: E402

# One run of each `hatch run all` member on the dev box, 2026-10-11, `test-cov-s1` for tests.
STEP_SECONDS = {
    "preflight": 2.6,
    "lint": 8.8,
    "format-check": 0.3,
    "typecheck": 8.6,
    "tests": 157.3,
    "examples": 8.3,
    "notebooks": 0.9,
    "docs-check": 1.0,
    "check-links": 1.1,
    "docs-build": 17.8,
}
TEST_STARTUP = 10.0
FULL_GATE = sum(STEP_SECONDS.values())


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8").stdout


_repo_cache: dict[tuple[str, ...], fg.Repo] = {}


def repo_at(rev: str) -> fg.Repo:
    key = tuple(git("rev-parse", *(f"{rev}:{d}" for d in ("src", "tests", "scripts"))).split())
    if key in _repo_cache:
        return _repo_cache[key]
    listing = git("ls-tree", "-r", "--name-only", rev, "--", "src", "tests", "scripts").splitlines()
    wanted = [p for p in listing if p.endswith((".py", ".toml"))]
    proc = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=ROOT,
        input="".join(f"{rev}:{p}\n" for p in wanted).encode(),
        capture_output=True,
        check=True,
    )
    out, files, i = proc.stdout, {}, 0
    for p in wanted:
        nl = out.index(b"\n", i)
        size = int(out[i:nl].split()[2])
        files[p] = out[nl + 1 : nl + 1 + size].decode("utf-8", "replace")
        i = nl + 1 + size + 1
    _repo_cache.clear()  # one live tree at a time keeps memory flat
    _repo_cache[key] = fg.Repo(files)
    return _repo_cache[key]


def evaluate(base: str, head: str, durations: dict[str, float], total: float) -> dict:
    changes = fg.diff_trees(f"{base}^{{tree}}", f"{head}^{{tree}}")
    if not changes:
        return {"changes": 0, "seconds": 0.0, "tests": "none", "share": 0.0, "steps": []}
    paths = [p for _, p in changes]
    keys = None
    if "pyproject.toml" in paths:
        keys = fg.changed_pyproject_keys(fg.blob_text(base, "pyproject.toml"), fg.blob_text(head, "pyproject.toml"))
    repo = repo_at(head)
    sel = fg.select_tests(repo, changes, keys)
    steps = fg.plan_steps(paths, sel)
    share = 0.0
    if "tests" in steps:
        test_files = fg.suite_files(repo)
        if sel.full:
            share = 1.0
        else:
            chosen, suite = fg.estimate(sel, durations, test_files)
            share = chosen / suite
        if share > fg.CUTOFF:
            share, sel.full_reasons = 1.0, [*sel.full_reasons, "cutoff"]
    secs = sum(v for k, v in STEP_SECONDS.items() if k in steps and k != "tests")
    if "tests" in steps:
        secs += STEP_SECONDS["tests"] if share >= 1.0 else TEST_STARTUP + share * (STEP_SECONDS["tests"] - TEST_STARTUP)
    return {
        "changes": len(changes),
        "seconds": round(secs, 1),
        "tests": "none" if "tests" not in steps else ("FULL" if share >= 1.0 else "selected"),
        "share": round(share, 4),
        "full_reason": sel.full_reasons[0] if sel.full_reasons else None,
        "steps": sorted(steps),
    }


def main() -> None:
    since, out_path = sys.argv[1], Path(sys.argv[2])
    prs = json.loads(
        subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "merged",
                "--limit",
                "400",
                "--search",
                f"merged:>={since}",
                "--json",
                "number,title,mergedAt",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    )
    durations = fg.load_durations(ROOT)
    total = sum(durations.values())
    with out_path.open("w", encoding="utf-8") as fh:
        for pr in sorted(prs, key=lambda p: p["number"]):
            n = pr["number"]
            head = f"refs/rs-pr/{n}"
            try:
                commits = git("rev-list", "--reverse", "--first-parent", head, "^origin/master").split()
            except subprocess.CalledProcessError:
                continue
            if not commits:
                continue
            first_parent = git("rev-parse", f"{commits[0]}^").strip()
            row = {"pr": n, "title": pr["title"], "commits": len(commits)}
            row["pr_level"] = evaluate(first_parent, commits[-1], durations, total)
            row["per_commit"] = []
            prev = first_parent
            for c in commits:
                row["per_commit"].append(evaluate(prev, c, durations, total))
                prev = c
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            print(n, len(commits), row["pr_level"]["tests"], flush=True)


if __name__ == "__main__":
    main()
