"""Before and after: what four means did to the sessions around their start, from local transcripts.

Every main session of this repository and its worktrees is placed in a period by
its start time, and each means is compared across its own cut:

* **Prefix** (``--skills-off``, ``--memory-trim``): the first call's context, the
  instruction files Claude Code attached to it (user ``CLAUDE.md``, project
  ``CLAUDE.md``, ``MEMORY.md``, read from the ``instructions`` attachment), and the
  rest of the context once those are subtracted at the calibrated tokens per
  character. ``/rvw-pr`` sessions open with nearly the same prompt, so they are
  reported apart as the controlled group.
* **Lookup tool** (``--lookup``): per session, Reads and Greps of the large
  process files (``sdd/BACKLOG.md``, ``sdd/BACKLOG-DONE.md``,
  ``sdd/CLAUDE-REFERENCE.md``) and their result characters, against calls of
  the lookup tool (``backlog-show``, ``backlog-find``, ``ref-show``,
  ``ref-rows``, ``sdd_lookup``).
* **Gate** (``--gate``, ``--gate-workers``): gate runs, cut-offs and idle stalls,
  as ``gates.py`` defines them, over the main sessions and their subagents.

    python means_effects.py --skills-off ISO --memory-trim ISO --lookup ISO --gate ISO --gate-workers ISO

Writes ``results/means_effects.json``: counts, medians and the Claude Code
versions per period, no session IDs. Bounds: a session belongs to the period
its first record falls in, though a setting changed mid-session acts on its
later calls; the version list is reported because a new Claude Code release
changes the system prompt as well.
"""

from __future__ import annotations

import json
import re
import statistics as st
from typing import TYPE_CHECKING

import _common as c
import gates

if TYPE_CHECKING:
    from pathlib import Path

SKIP_DIRS = re.compile(r"-(expectations|gremlins|legacy-sam-services-snapshot)$")
BIG_FILES = re.compile(r"sdd[\\/](BACKLOG\.md|BACKLOG-DONE\.md|CLAUDE-REFERENCE\.md)")
LOOKUP = re.compile(r"backlog-show|backlog-find|ref-show|ref-rows|sdd_lookup")
TOK_PER_CHAR = c.COEF["attachment"]


def records(path: Path):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def instruction_kind(path: str) -> str:
    p = path.replace("\\", "/")
    if p.endswith("/memory/MEMORY.md"):
        return "memory"
    if p.endswith("/.claude/CLAUDE.md") and "/projects/" not in p and p.count("/") <= 4:
        return "user"
    return "project" if p.endswith("CLAUDE.md") else "other"


def session(main: Path) -> dict | None:
    start = version = first_prompt = None
    first_ctx = None
    instr: dict[str, int] = {}
    big_reads = big_chars = lookups = 0
    pending: set[str] = set()
    for r in records(main):
        start = start or r.get("timestamp")
        version = version or r.get("version")
        m = r.get("message")
        a = r.get("attachment")
        if r.get("type") == "attachment" and isinstance(a, dict) and a.get("type") == "instructions" and not instr:
            for f in a.get("files") or []:
                k = instruction_kind(str(f.get("path", "")))
                instr[k] = instr.get(k, 0) + len(str(f.get("content", "")))
        if r.get("type") == "user" and isinstance(m, dict) and not r.get("isMeta") and first_prompt is None:
            content = m.get("content")
            if isinstance(content, str) and "<local-command" not in content and "/clear" not in content[:60]:
                first_prompt = content
        if not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        if r.get("type") == "assistant":
            u = m.get("usage")
            if first_ctx is None and isinstance(u, dict) and m.get("model") != "<synthetic>":
                first_ctx = (
                    u.get("input_tokens", 0)
                    + u.get("cache_read_input_tokens", 0)
                    + u.get("cache_creation_input_tokens", 0)
                )
            for b in m["content"]:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                inp = b.get("input") or {}
                if b.get("name") in ("Read", "Grep") and BIG_FILES.search(
                    str(inp.get("file_path") or inp.get("path") or "")
                ):
                    big_reads += 1
                    pending.add(b["id"])
                elif b.get("name") in ("Bash", "PowerShell") and LOOKUP.search(str(inp.get("command", ""))):
                    lookups += 1
        else:
            for b in m["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    big_chars += len(str(b.get("content")))
    if first_ctx is None:
        return None
    subs = sorted((main.parent / main.stem / "subagents").glob("*.jsonl"))
    runs = [x for f in [main, *subs] for x in gates.gate_runs(f)]
    instr_tok = sum(instr.values()) * TOK_PER_CHAR
    return {
        "start": start,
        "version": version,
        "review": bool(first_prompt and re.match(r"\s*/rvw-pr\b", first_prompt)),
        "first_ctx": first_ctx,
        "instr_chars": instr,
        "rest_ctx": first_ctx - instr_tok,
        "big_reads": big_reads,
        "big_chars": big_chars,
        "lookups": lookups,
        "gate_runs": runs,
        "stalls": gates.stalls(main),
    }


def med(xs):
    xs = list(xs)
    return round(st.median(xs)) if xs else None


def prefix_stats(rows: list[dict]) -> dict:
    return {
        "sessions": len(rows),
        "versions": sorted({r["version"] for r in rows if r["version"]}),
        "first_ctx_median": med(r["first_ctx"] for r in rows),
        "memory_chars_median": med(r["instr_chars"].get("memory", 0) for r in rows),
        "project_claude_md_chars_median": med(r["instr_chars"].get("project", 0) for r in rows),
        "rest_ctx_median": med(r["rest_ctx"] for r in rows),
    }


def main(argv=None) -> int:
    ap = c.parser(__doc__, data=False)
    for flag in ("--skills-off", "--memory-trim", "--lookup", "--gate", "--gate-workers"):
        ap.add_argument(flag, required=True, help="ISO timestamp of the change")
    args = c.resolve(ap.parse_args(argv))
    mains = [
        p for d in c.default_transcripts(args.repo_root) if not SKIP_DIRS.search(d.name) for p in d.glob("*.jsonl")
    ]
    rows = [s for s in (session(p) for p in mains) if s]

    def between(lo, hi):
        return [r for r in rows if (lo is None or r["start"] >= lo) and (hi is None or r["start"] < hi)]

    periods = {
        "before skills off": (None, args.skills_off),
        "skills off, memory untrimmed": (args.skills_off, args.memory_trim),
        "skills off, memory trimmed": (args.memory_trim, None),
    }
    prefix = {
        name: {
            "all": prefix_stats(between(lo, hi)),
            "rvw-pr": prefix_stats([r for r in between(lo, hi) if r["review"]]),
        }
        for name, (lo, hi) in periods.items()
    }

    def lookup_stats(rs):
        work = [r for r in rs if not r["review"]]
        return {
            "sessions": len(work),
            "sessions_reading_big_files": sum(1 for r in work if r["big_reads"]),
            "big_file_reads": sum(r["big_reads"] for r in work),
            "big_file_result_chars": sum(r["big_chars"] for r in work),
            "lookup_calls": sum(r["lookups"] for r in work),
        }

    def gate_stats(rs):
        runs = [x for r in rs for x in r["gate_runs"]]
        fg = [x for x in runs if x["command"] == "hatch run all" and x["outcome"] == "passed"]
        return {
            "sessions": len(rs),
            "gate_runs": len(runs),
            "by_outcome": {
                k: sum(1 for x in runs if x["outcome"] == k) for k in ("passed", "failed", "cut off", "background")
            },
            "passing_hatch_run_all_median_s": med(x["wall_s"] for x in fg),
            "idle_stalls_min": sorted((m for r in rs for m in r["stalls"]), reverse=True),
        }

    payload = {
        "cuts": {
            "skills_off": args.skills_off,
            "memory_trim": args.memory_trim,
            "lookup": args.lookup,
            "gate": args.gate,
            "gate_workers": args.gate_workers,
        },
        "tokens_per_char": TOK_PER_CHAR,
        "prefix": prefix,
        "lookup": {
            "before": lookup_stats(between(None, args.lookup)),
            "after": lookup_stats(between(args.lookup, None)),
        },
        "gate": {
            "before": gate_stats(between(None, args.gate)),
            "lock_and_timeout_only": gate_stats(between(args.gate, args.gate_workers)),
            "after": gate_stats(between(args.gate_workers, None)),
        },
    }
    c.write_result(
        args.results,
        "means_effects",
        "means_effects",
        {f"transcript {i}": p for i, p in enumerate(sorted(mains))},
        payload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
