"""Local gate runs and idle stalls in one or more transcripts: how long each gate took and how it ended.

A **gate run** is a Bash or PowerShell call whose command contains
``hatch run all``, ``hatch run test`` or ``hatch run test-cov*``; its wall
time runs from the call to its result. It ended *background* if it was
started with ``run_in_background`` or moved there, *cut off* if the result
reports a timeout, *failed* on an error result, else *passed*.

An **idle stall** is an assistant turn that ends while saying it waits for a
background command, followed by more than 15 minutes with no user record.

    python gates.py --transcripts DIR_OR_FILE [...]

Writes ``results/<--name>.json`` (default ``gates``). Inputs are transcripts,
so the result names only counts and durations.
"""

from __future__ import annotations

import json
import re
import statistics as st
from datetime import datetime
from pathlib import Path

import _common as c

GATE = re.compile(r"hatch run (all|test-cov[\w-]*|test)\b")
WAITING = re.compile(r"background|waiting|gate is still running|CI (is )?(still )?running|monitor", re.I)


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


UNTIL: str | None = None


def records(path: Path):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if UNTIL and (r.get("timestamp") or "") > UNTIL:
            return
        yield r


def gate_runs(path: Path):
    uses, out = {}, []
    for r in records(path):
        m = r.get("message")
        if not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        for b in m["content"]:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") in ("Bash", "PowerShell"):
                inp = b.get("input") or {}
                g = GATE.search(" ".join(str(inp.get("command", "")).split()))
                if g:
                    uses[b["id"]] = (r["timestamp"], g.group(0), bool(inp.get("run_in_background")))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                t0, cmd, bg = uses.pop(b["tool_use_id"])
                txt = str(b.get("content"))
                if bg or "running in background" in txt.lower():
                    how = "background"
                elif re.search(r"timed out|moved to the background|exceeded", txt, re.I):
                    how = "cut off"
                elif b.get("is_error") or re.search(r"\bfailed\b|Error|exit code [1-9]", txt):
                    how = "failed"
                else:
                    how = "passed"
                out.append(
                    {"command": cmd, "outcome": how, "wall_s": round((ts(r["timestamp"]) - ts(t0)).total_seconds())}
                )
    return out


def stalls(path: Path):
    recs = [r for r in records(path) if r.get("timestamp")]
    out = []
    for i, r in enumerate(recs):
        m = r.get("message") or {}
        if r.get("type") != "assistant" or m.get("stop_reason") != "end_turn":
            continue
        nxt = next((x for x in recs[i + 1 :] if x.get("type") in ("user", "queue-operation")), None)
        if not nxt:
            continue
        gap = (ts(nxt["timestamp"]) - ts(r["timestamp"])).total_seconds() / 60
        c_ = m.get("content")
        text = (
            " ".join(b.get("text", "") for b in c_ if isinstance(b, dict) and b.get("type") == "text")
            if isinstance(c_, list)
            else ""
        )
        if gap > 15 and WAITING.search(text):
            out.append(round(gap))
    return out


def main(argv=None) -> int:
    ap = c.parser(__doc__, data=False)
    ap.add_argument(
        "--transcripts", type=Path, action="append", required=True, help="transcript file or folder (repeatable)"
    )
    ap.add_argument("--name", default="gates", help="result file name")
    ap.add_argument("--until", default=None, help="ISO timestamp: ignore records after it")
    args = c.resolve(ap.parse_args(argv))
    global UNTIL
    UNTIL = args.until
    files = [f for p in args.transcripts for f in ([p] if p.is_file() else sorted(p.rglob("*.jsonl")))]
    runs = [x for f in files for x in gate_runs(f)]
    idle = [x for f in files if "subagents" not in f.parts for x in stalls(f)]
    fg = [x for x in runs if x["command"] == "hatch run all" and x["outcome"] != "background"]
    payload = {
        "transcripts": len(files),
        "gate_runs": len(runs),
        "by_outcome": {
            k: sum(1 for x in runs if x["outcome"] == k) for k in ("passed", "failed", "cut off", "background")
        },
        "foreground_all": {
            "n": len(fg),
            "median_s": st.median(x["wall_s"] for x in fg) if fg else None,
            "at_or_over_590s": sum(1 for x in fg if x["wall_s"] >= 590),
        },
        "idle_stalls_min": sorted(idle, reverse=True),
    }
    c.write_result(args.results, args.name, "gates", {f"transcript {i}": f for i, f in enumerate(files)}, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
