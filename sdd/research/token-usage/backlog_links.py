"""Test two hypotheses: the backlog files bloat context; links in CLAUDE.md and the authority docs pull reads in.

Every Read result is assigned to one group, first match wins: backlog files
(``sdd/BACKLOG.md``, ``sdd/BACKLOG-DONE.md``, ``sdd/backlog/*``); files linked
from ``CLAUDE.md``; files linked from those or from the authority docs (second
hop); then by area. Link sets are taken from ``--repo-root`` as it is now, so
they are an upper bound for what a session at the time could have followed.

With ``--transcripts``, also counts how the surviving transcripts touched the
two backlog files (Read whole, Read sliced, Grep, other), since the extract
does not keep Read arguments.

Reads ``--data``; writes ``results/backlog_links.json``.
"""

from __future__ import annotations

import collections
import contextlib
import json
import re
from pathlib import Path

import _common as c

AUTHORITY = [
    "sdd/AUTHORING.md",
    "sdd/DOCUMENTATION.md",
    "sdd/CONTENT-RULES.md",
    "sdd/CLAUDE-REFERENCE.md",
    "sdd/000-process.md",
]


def links(repo: Path, path: str) -> set[str]:
    p = repo / path
    if not p.is_file():
        return set()
    out = set()
    for m in re.findall(r"\]\(([^)\s]+)\)", p.read_text(encoding="utf-8", errors="replace")):
        if m.startswith(("http", "#", "mailto")):
            continue
        with contextlib.suppress(ValueError):
            out.add((p.parent / m.split("#")[0]).resolve().relative_to(repo).as_posix())
    return out


def backlog(p: str) -> bool:
    return p in ("sdd/BACKLOG.md", "sdd/BACKLOG-DONE.md") or p.startswith("sdd/backlog/")


def norm(p: str) -> str:
    p = p.replace("\\", "/")
    m = re.search(r"tmp/review/[0-9a-f]+/(.*)", p)
    return m.group(1) if m else p


def touches(dirs: list[Path], files: list[str]) -> dict:
    """How each backlog file was touched in the transcripts still on disk."""
    out = collections.Counter()
    for d in dirs:
        for f in d.rglob("*.jsonl"):
            if str(f.relative_to(d.parent)) not in files:
                continue
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if "BACKLOG" not in line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for b in (r.get("message") or {}).get("content") or []:
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    inp = b.get("input") or {}
                    s = json.dumps(inp)
                    for fn in ("BACKLOG-DONE.md", "BACKLOG.md"):
                        if fn not in s:
                            continue
                        if b["name"] == "Read":
                            mode = "Read slice" if inp.get("offset") or inp.get("limit") else "Read whole"
                        elif b["name"] == "Grep":
                            mode = "Grep " + inp.get("output_mode", "files_with_matches")
                        elif b["name"] in ("Edit", "Write"):
                            mode = "Edit/Write"
                        else:
                            mode = "other"
                        out[f"{fn}: {mode}"] += 1
                        break
    return dict(sorted(out.items()))


def main(argv=None) -> int:
    ap = c.parser(__doc__)
    ap.add_argument("--transcripts", type=Path, action="append", help="transcript folder to scan (repeatable)")
    args = c.resolve(ap.parse_args(argv))
    calls, items, S = c.load_extract(args.data)
    bycall = c.by_file(calls)
    ends = c.segment_ends(bycall)
    model_of = {f: cs[0]["model"] for f, cs in bycall.items()}
    sumctx = sum(x["ctx"] for x in calls)
    l1 = links(args.repo_root, "CLAUDE.md")
    l2 = set().union(*(links(args.repo_root, p) for p in l1 | set(AUTHORITY))) - l1

    def cost(it):
        tok = it["chars"] * c.COEF["tool_result"]
        f = it["file"]
        life = max(0, ends.get((f, it["seg"]), len(bycall[f])) - it["enter"])
        w = 2.0 if not S[f]["is_sub"] else 1.25
        return tok * life, (tok * w + tok * life * 0.1) * c.PRICE[model_of[f]], tok

    groups = collections.defaultdict(lambda: [0, 0.0, 0.0, set()])
    per_file = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    for it in items:
        if it["kind"] != "tool_result:Read" or it["file"] not in bycall or it["detail"].startswith("<"):
            continue
        p = norm(it["detail"])
        if backlog(p):
            g = "backlog files"
        elif p in l1:
            g = "linked from CLAUDE.md"
        elif p in l2:
            g = "linked from the authority docs (second hop)"
        elif p.startswith(".claude/skills"):
            g = ".claude/skills"
        elif p.startswith(("src/", "tests/")):
            g = "src/ + tests/"
        else:
            g = "sdd/ other" if p.startswith("sdd/") else "other repo files"
        car, usd, tok = cost(it)
        r = groups[g]
        r[0] += 1
        r[1] += car
        r[2] += usd
        r[3].add(S[it["file"]]["parent"])
        if backlog(p) or p in l1 or p in l2:
            q = per_file["sdd/backlog/* dossiers" if p.startswith("sdd/backlog/") else p]
            q[0] += 1
            q[1] += car
            q[2] += usd
            q[3] += tok

    payload = {
        "groups": {
            g: {"reads": n, "sessions": len(ss), "context_pct": c.pct(car, sumctx, 2), "usd_estimate": round(usd, 1)}
            for g, (n, car, usd, ss) in sorted(groups.items(), key=lambda kv: -kv[1][1])
        },
        "per_file": {
            p: {
                "reads": n,
                "tokens_per_read": round(tok / n),
                "context_pct": c.pct(car, sumctx, 2),
                "usd_estimate": round(usd, 1),
            }
            for p, (n, car, usd, tok) in sorted(per_file.items(), key=lambda kv: -kv[1][1])[:8]
        },
        "backlog_touches_in_surviving_transcripts": touches(args.transcripts, list(S)) if args.transcripts else None,
    }
    inputs = c.extract_inputs(args.data) | {"CLAUDE.md": args.repo_root / "CLAUDE.md"}
    c.write_result(args.results, "backlog_links", "backlog_links", inputs, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
