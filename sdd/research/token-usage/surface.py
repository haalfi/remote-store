"""Size of the instruction surface every session reads, at fixed dates (KB at the last master commit of each day).

Reads git only; writes ``results/surface.json``. ``--branch`` names the
history to walk (default ``origin/master``).
"""

from __future__ import annotations

import re
import subprocess

import _common as c

DATES = ["2026-05-15", "2026-06-01", "2026-07-01", "2026-08-01", "2026-08-15", "2026-09-01", "2026-10-01", "2026-10-09"]
FILES = [
    "CLAUDE.md",
    "sdd/CLAUDE-REFERENCE.md",
    "CONTRIBUTING.md",
    "sdd/traces/_schema.yml",
    ".claude/skills/ship/SKILL.md",
    ".claude/skills/rvw-pr/SKILL.md",
    ".claude/skills/fix-pr/SKILL.md",
]


def main(argv=None) -> int:
    ap = c.parser(__doc__, data=False)
    ap.add_argument("--branch", default="origin/master")
    args = c.resolve(ap.parse_args(argv))

    def git(*a, inp=None):
        return subprocess.run(
            ["git", "-C", str(args.repo_root), *a],
            input=inp,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout

    rows = {}
    commits = {}
    for d in DATES:
        sha = git("rev-list", "-1", f"--before={d}T23:59:59", args.branch).strip()
        commits[d] = sha[:9]
        sizes = git(
            "cat-file", "--batch-check=%(objectsize)", inp="\n".join(f"{sha}:{f}" for f in FILES) + "\n"
        ).splitlines()
        skills = [
            p
            for p in git("ls-tree", "-r", "--name-only", sha, ".claude/skills").splitlines()
            if p.endswith("/SKILL.md")
        ]
        descr = 0
        for p in skills:
            m = re.search(r"^---\n(.*?)\n---", git("show", f"{sha}:{p}"), re.S)
            dm = re.search(r"^description:\s*(.*?)(?=^\w[\w-]*:|\Z)", m.group(1), re.S | re.M) if m else None
            descr += len(dm.group(1)) if dm else 0
        rows[d] = {
            "kb": {
                f: round(int(s) / 1024, 1) if s.strip().isdigit() else None for f, s in zip(FILES, sizes, strict=False)
            },
            "repo_skills": len(skills),
            "skill_description_bytes": descr,
        }
    c.write_result(
        args.results,
        "surface",
        "surface",
        {"history": args.branch, "commits": " ".join(commits.values())},
        {"dates": rows},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
