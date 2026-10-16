"""Measure whole deliveries from tokkit snapshots: units, phases, review rounds and passes, active time.

A delivery is one PR and the parts of sessions that served it. Which parts is a
judgement made by reading the transcripts, and it is keyed by session ID, so it
comes from a ``--config`` file kept outside the repo, like ``prep_cost.py``'s
class map:

    {"deliveries": {"BK-389": {"pr": 1127, "parts": [
        {"session": "<sid>", "build": true},
        {"session": "<sid>", "until": "2026-10-12T15:00:00Z"},
        {"session": "<sid>", "exclude_agents": ["<agent id prefix>"]}],
      "idle": [["<ISO>", "<ISO>"]]}},
     "other": {"<label>": [{"session": "<sid>", "agents": ["<agent id prefix>"]}]}}

    python deliveries.py --repo-root <main checkout> --snapshots <tokkit snapshot folder> --config <map.json>

``--repo-root`` must be a checkout named as the transcripts' paths name it
(``remote-store``), because ``tokkit.norm_path`` matches that name.

A part keeps the main-session calls in ``[since, until)`` and the subagents whose
first call falls there, less ``exclude_agents``, or only ``agents``; ``"main":
false`` drops the main-session calls, leaving subagents alone. Every figure
reuses ``tokkit.py``'s parser, so a part's units are those ``tokkit.py report``
prints for the same session and ``--until``.

- **Phases.** The ``build`` part is cut as ``tokkit.py report --pr`` cuts it: at
  plan approval and at the PR's ``createdAt``; a subagent goes to the phase its
  first call falls in. Every other part is review loop.
- **Rounds.** A review pass is what ``is_pass`` says; passes spawned by one
  main-session call form a round. A round costs its passes plus the
  main-session calls from the one that spawned it up to the one that spawned
  the next round, or to the part's end, so it includes the fix that follows it. Review-loop cost outside every span
  (a part's calls before its first round, a subagent that is no round's pass)
  joins the latest round spawned before it, across parts, so a resume session's
  opening calls count toward the round they fix; what precedes the first
  round is reported on its own. Each human-submitted GitHub
  review carrying findings (``ship_report.rounds_with_findings``) is assigned
  to the latest round spawned before it was submitted, and counted outside the
  measured sessions when that round's span had already ended; a bot's is not
  counted.
- **Passes.** Calls, first and final context, units, the context split
  ``tokkit.py subagents`` prints, the checkout's files read whole (a ``Read``
  with no offset or limit), and the findings it handed back: the sum of the
  ``Bug: n | Spec: n | ...`` line in its last ``SubagentHandback``, else in its
  last text. A posted round can merge duplicates or add findings no pass
  handed back, so per round the two counts differ in either direction.
  ``by_method`` groups passes by the method their description names first.
- **Active time.** A gap method, on the main transcript's user and
  assistant records: a gap of 60 s or more ended by a user prompt, or by the
  answer to ``AskUserQuestion`` or ``ExitPlanMode``, is a wait; one ended by a
  ``<task-notification>``, a subagent's hand-back or a tool result is work.
  Active is wall time less the waits and less the delivery's ``idle`` spans
  (time the maintainer stated idle, such as a suspended PC inside a tool call).

Writes ``results/<--name>.json``, which holds no session or agent ID.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import re
import statistics as st
import sys
from pathlib import Path

import _common as cm
import tokkit

when = cm.when


def _ship_report(repo: Path):
    spec = importlib.util.spec_from_file_location("ship_report", repo / "scripts" / "ship_report.py")
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("cannot load scripts/ship_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def records(path: Path):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def within(ts, part) -> bool:
    if not ts:
        return True
    t = when(ts)
    return (not part.get("since") or t >= when(part["since"])) and (not part.get("until") or t < when(part["until"]))


def keep_agent(stem: str, part) -> bool:
    aid = stem.removeprefix("agent-")
    if part.get("agents") is not None:
        return any(aid.startswith(a) for a in part["agents"])
    return not any(aid.startswith(a) for a in part.get("exclude_agents", []))


def is_pass(sub) -> bool:
    """A review pass: a ``reviewer`` agent, a forked ``/rvw-pr``, or, before BK-431 gave
    passes their own agent, a subagent its spawner described as a review, pass or member."""
    d = sub["description"]
    return sub["type"] == "reviewer" or d.startswith("/rvw-pr") or bool(re.search(r"(?i)\b(review|pass|member)\b", d))


def handback(path: Path):
    """The findings a pass handed back, summed from its count line, or None when it has none."""
    msg, last = None, ""
    for r in records(path):
        m = r.get("message")
        if r.get("type") != "assistant" or not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        for b in m["content"]:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") == "SubagentHandback":
                msg = (b.get("input") or {}).get("message", "")
            elif b.get("type") == "text" and b.get("text", "").strip():
                last = b["text"]
    text = msg if msg is not None else last
    line = next((ln for ln in text.splitlines() if re.match(r"\s*\**Bug\**:\s*\d+", ln)), None)
    return None if line is None else sum(int(n) for n in re.findall(r":\s*(\d+)", line))


def read_whole(path: Path) -> list[str]:
    """The files a pass read whole: each ``Read`` target with no offset or limit, once.

    A target ``tokkit.norm_path`` folded to a placeholder (a spilled tool output, a
    transcript, a scratch file) is not a file of the checkout, so it is left out; a
    review snapshot's files are the PR's and stay."""
    return sorted(
        {
            t["target"]
            for t in tokkit.tool_calls(path)
            if t["tool"] == "Read"
            and not t["target"].endswith("]")
            and (not t["target"].startswith("<") or t["target"].startswith("<review-snapshot>/"))
        }
    )


def is_wait(r, tools) -> bool:
    m = r.get("message")
    if r.get("type") != "user" or not isinstance(m, dict) or r.get("isMeta"):
        return False
    c = m.get("content")
    blocks = [{"type": "text", "text": c}] if isinstance(c, str) else c if isinstance(c, list) else []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_result":
            if tools.get(b.get("tool_use_id")) in ("AskUserQuestion", "ExitPlanMode"):
                return True
        elif b.get("type") == "text":
            t = b.get("text", "")
            return not ("<task-notification>" in t or "Another Claude session sent a message" in t)
    return False


def active(main: Path, part) -> tuple[float, float]:
    """(wall, wait) seconds of one part's main transcript by the gap method."""
    tools, prev, wall, wait = {}, None, 0.0, 0.0
    for r in records(main):
        if r.get("type") not in ("user", "assistant") or not r.get("timestamp") or not within(r["timestamp"], part):
            continue
        m = r.get("message")
        content = m.get("content") if isinstance(m, dict) else None
        for b in content if isinstance(content, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                tools[b.get("id")] = b.get("name")
        t = when(r["timestamp"])
        if prev is not None and t > prev:
            g = (t - prev).total_seconds()
            wall += g
            if g >= 60 and is_wait(r, tools):
                wait += g
        prev = t
    return wall, wait


def usd(calls) -> float:
    return sum(c["units"] * cm.PRICE.get(c["model"], 2.31e-6) for c in calls)


def context_split(calls, items, changed) -> dict:
    """The context classes ``tokkit.py subagents`` prints for one subagent, in percent."""
    sumctx = sum(c["ctx"] for c in calls)
    out, det = tokkit.carried(calls, items)
    split = collections.Counter({"prefix": calls[0]["ctx"] * len(calls)})
    for (kind, d), v in det.items():
        split[tokkit.sub_class(kind, d, changed)] += v
    split["other"] += out["thinking (hidden)"]
    split["unexplained"] = sumctx - sum(split.values())
    return {k: round(split[k] / sumctx * 100, 1) for k in tokkit.SUB_CLASSES}


def group_rounds(subs, spawns, mc) -> dict:
    """Review passes keyed by the spawn event that started them, ``None`` when none did.

    ``spawns`` holds ``(idx, detail)`` events, where ``idx`` is one past the spawning call
    in ``mc``. A pass belongs to the latest spawn with its description (cut to 50
    characters, as ``tokkit`` cuts it; a forked ``/rvw-pr`` matches the skill call) whose
    call came no later than the pass's first call."""
    rounds = collections.defaultdict(list)
    for s in subs:
        if not is_pass(s):
            continue
        key = "/rvw-pr" if s["description"].startswith("/rvw-pr") else s["description"][:50]
        at = max(
            (i for i, d in spawns if d == key and (mc[i - 1]["ts"] or "") <= s["first_ts"]),
            default=None,
        )
        rounds[at].append(s)
    return rounds


def round_spans(rounds, hi) -> list[tuple[int, int]]:
    """Each round's main-session calls ``[a, b)``: from its spawning call to the next round's, the last to ``hi``.

    A spawn event's index is one past its call, so a round keyed ``i`` starts at call ``i - 1``."""
    starts = sorted(i for i in rounds if i is not None)
    return [(i - 1, starts[n + 1] - 1 if n + 1 < len(starts) else hi) for n, i in enumerate(starts)]


def fold_rounds(rounds, extra, posted) -> tuple[list[dict], float]:
    """Each round's row, with the loose cost ``assign_loose`` gave it folded in, and the loop's units.

    ``opening_units_m`` is the main-session part of that cost: calls a later session made
    before its first round, which carry the fix of the round before the break."""
    zero = {"main_units": 0, "other_units": 0, "usd": 0.0}
    out, loop_units = [], 0
    for k, r in enumerate(rounds):
        x = extra.get(k, zero)
        pu = sum(s["units"] for s in r["passes"])
        mu = r["main_units"] + x["main_units"]
        loop_units += mu + pu + x["other_units"]
        out.append(
            {
                "round": k + 1,
                "passes": len(r["passes"]),
                "main_ctx_k": r["main_ctx_k"],
                "main_units_m": m2(mu),
                "opening_units_m": m2(x["main_units"]),
                "pass_units_m": m2(pu),
                "other_units_m": m2(x["other_units"]),
                "units_m": m2(mu + pu + x["other_units"]),
                "usd": round(r["main_usd"] + sum(s["usd"] for s in r["passes"]) + x["usd"], 2),
                "findings_posted": posted[k],
                "findings_handed_back": sum(s["findings_handed_back"] or 0 for s in r["passes"]),
            }
        )
    return out, loop_units


def assign_submissions(subs, rounds) -> tuple[collections.Counter, int]:
    """Posted findings per round index, and those outside the measured sessions.

    A submission ``(epoch seconds, findings)`` goes to the latest round spawned before it;
    it is outside when no round was, or when that round's span had ended."""
    posted, outside = collections.Counter(), 0
    for ts, n in subs:
        at = max((k for k, r in enumerate(rounds) if when(r["spawn_ts"]).timestamp() <= ts), default=None)
        if at is None or ts > when(rounds[at]["end_ts"]).timestamp():
            outside += n
        else:
            posted[at] += n
    return posted, outside


def assign_loose(loose, rounds) -> tuple[dict, dict]:
    """Loop cost outside every round span, per round index, and what precedes the first round.

    Each item ``{"ts", "units", "usd", "main"}`` goes to the latest round spawned no later
    than it: a resume session's opening calls fix the round the last session ran, and a
    fixer subagent works on the round it follows. Returns ``(per_round, before)``, each
    summing ``main_units``, ``other_units`` and ``usd``."""
    zero = {"main_units": 0, "other_units": 0, "usd": 0.0}
    per_round: dict[int, dict] = collections.defaultdict(lambda: dict(zero))
    before = dict(zero)
    for x in loose:
        at = max((k for k, r in enumerate(rounds) if when(r["spawn_ts"]) <= when(x["ts"])), default=None)
        into = before if at is None else per_round[at]
        into["main_units" if x["main"] else "other_units"] += x["units"]
        into["usd"] += x["usd"]
    return per_round, before


def measure_part(snap: Path, part, changed, created) -> dict:
    sid = part["session"]
    main = snap / sid / f"{sid}.jsonl"
    mc, _, me = tokkit.parse_file(main)
    keep = [c for c in mc if within(c["ts"], part)] if part.get("main", True) else []
    lo, hi = (keep[0]["idx"], keep[-1]["idx"] + 1) if keep else (0, 0)
    subs = []
    for f in tokkit.transcript_files(main)[1:]:
        calls, items, _ = tokkit.parse_file(f)
        if not calls or not within(calls[0]["ts"], part) or not keep_agent(f.stem, part):
            continue
        meta = f.with_name(f.stem + ".meta.json")
        meta = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
        whole = read_whole(f)
        subs.append(
            {
                "type": meta.get("agentType", "?"),
                "description": meta.get("description", ""),
                "first_ts": calls[0]["ts"],
                "calls": len(calls),
                "first_ctx": calls[0]["ctx"],
                "final_ctx": calls[-1]["ctx"],
                "units": sum(c["units"] for c in calls),
                "usd": usd(calls),
                "context_pct": context_split(calls, items, changed),
                "findings_handed_back": handback(f),
                "read_whole": whole,
            }
        )
    # Phases, as tokkit.py report cuts them (build part only; every other part is review loop).
    build = bool(part.get("build"))
    pr_idx = plan_idx = plan_ts = None
    if build:
        pr_idx = next((c["idx"] for c in mc if c["ts"] and when(c["ts"]) >= when(created)), None)
        events = sorted(
            [*me, {"ts": created, "kind": "pr-open", "detail": "", "idx": pr_idx}],
            key=lambda e: (e["idx"] is None, e["idx"] or 0),
        )
        plan_idx, _ = tokkit.plan_end(events, pr_idx)
        plan_ts = mc[plan_idx]["ts"] if plan_idx is not None and plan_idx < len(mc) else None

    def phase(idx=None, ts=None):
        if not build:
            return "review loop"
        if (idx is not None and pr_idx is not None and idx >= pr_idx) or (ts and when(ts) >= when(created)):
            return "review loop"
        if (idx is not None and plan_idx is not None and idx >= plan_idx) or (
            ts and plan_ts and when(ts) >= when(plan_ts)
        ):
            return "build"
        return "orient + plan"

    phases = collections.Counter()
    for c in keep:
        phases[phase(idx=c["idx"])] += c["units"]
    for s in subs:
        phases[phase(ts=s["first_ts"])] += s["units"]
    phase_calls = {"plan_approval_call": plan_idx, "pr_open_call": pr_idx} if build else {}
    # Review rounds: passes grouped by the main-session call that spawned them.
    spawns = [(e["idx"], e["detail"]) for e in me if e["kind"] == "agent-spawn" and lo < e["idx"] <= hi]
    spawns += [
        (e["idx"], "/rvw-pr")
        for e in me
        if e["kind"] == "skill" and e["detail"].endswith("rvw-pr") and lo < e["idx"] <= hi
    ]
    rounds = group_rounds(subs, spawns, mc)
    spans = round_spans(rounds, hi)
    # Loop cost no round span holds: main calls before the part's first round, and
    # subagents that are not a round's pass. main() gives each to the round before it.
    in_span = {k for i, j in spans for k in range(i, j)}
    in_round = {id(s) for i, ps in rounds.items() if i is not None for s in ps}
    loose = [
        {"ts": c["ts"], "units": c["units"], "usd": usd([c]), "main": True}
        for c in keep
        if c["idx"] not in in_span and phase(idx=c["idx"]) == "review loop"
    ] + [
        {"ts": s["first_ts"], "units": s["units"], "usd": s["usd"], "main": False}
        for s in subs
        if id(s) not in in_round and phase(ts=s["first_ts"]) == "review loop"
    ]
    out_rounds = []
    for a, b in spans:
        main_span = mc[a:b]
        out_rounds.append(
            {
                "spawn_ts": mc[a]["ts"],
                "end_ts": mc[b - 1]["ts"],
                "main_ctx_k": round(mc[a]["ctx"] / 1e3),
                "main_units": sum(c["units"] for c in main_span),
                "main_usd": usd(main_span),
                "passes": rounds[a + 1],
            }
        )
    return {
        "calls": len(keep) + sum(s["calls"] for s in subs),
        "units": sum(c["units"] for c in keep) + sum(s["units"] for s in subs),
        "usd": usd(keep) + sum(s["usd"] for s in subs),
        "phases": phases,
        "phase_calls": phase_calls,
        "rounds": out_rounds,
        "loose": loose,
        "unassigned_passes": len(rounds.get(None, [])),
        "max_main_ctx_k": round(max((c["ctx"] for c in keep), default=0) / 1e3),
        "time": active(main, part),
    }


def submissions(sr, pr: int):
    """Human-submitted reviews carrying findings, oldest first: (submitted_at, findings).

    A review not yet submitted has no time to place it by, so it is left out; so is a bot's,
    whose count is returned beside the list."""
    rounds, review_ts, _, unsubmitted = sr.rounds_with_findings(pr)
    bots = {rv["id"] for rv in sr.fnd._gh(f"pulls/{pr}/reviews") if (rv.get("user") or {}).get("type") == "Bot"}
    return [(review_ts[rid], len(fs)) for rid, fs in rounds.items() if rid not in bots and rid not in unsubmitted], len(
        [rid for rid in rounds if rid in bots]
    )


def by_method(passes) -> dict:
    """Passes grouped by the method their spawner named first in the description: unprimed,
    whole-file or measuring; any other lens (a solo round, a reader or consistency member) is other."""
    groups = collections.defaultdict(list)
    for s in passes:
        d = s["description"].lower()
        named = [(d.find(w), w) for w in ("unprimed", "whole-file", "measuring") if w in d]
        groups[min(named)[1] if named else "other"].append(s)
    return {
        k: {
            "passes": len(ps),
            "calls_median": st.median(s["calls"] for s in ps),
            "units_m_median": m2(st.median(s["units"] for s in ps)),
            "read_whole_median": st.median(len(s["read_whole"]) for s in ps),
            "findings_handed_back": sum(s["findings_handed_back"] or 0 for s in ps),
        }
        for k, ps in sorted(groups.items())
    }


def m2(x) -> float:
    return round(x / 1e6, 2)


def main(argv=None) -> int:
    ap = cm.parser(__doc__, data=False)
    ap.add_argument("--snapshots", type=Path, required=True, help="tokkit snapshot folder: <sid>/<sid>.jsonl")
    ap.add_argument("--config", type=Path, required=True, help="the delivery map (keyed by session ID)")
    ap.add_argument("--name", default="deliveries", help="result file name")
    args = cm.resolve(ap.parse_args(argv))
    tokkit.ARGS = argparse.Namespace(repo_root=args.repo_root)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sr = _ship_report(args.repo_root)
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    payload: dict = {"deliveries": {}, "other": {}}
    for label, d in cfg["deliveries"].items():
        pr = d["pr"]
        meta = sr.pr_meta(pr)
        changed = set(sr.changed_files(pr))
        parts = [measure_part(args.snapshots, p, changed, meta["created_at"]) for p in d["parts"]]
        units = sum(p["units"] for p in parts)
        phases = collections.Counter()
        for p in parts:
            phases.update(p["phases"])
        wall = sum(p["time"][0] for p in parts)
        wait = sum(p["time"][1] for p in parts)
        idle = sum((when(b) - when(a)).total_seconds() for a, b in d.get("idle", []))
        rounds = sorted((r for p in parts for r in p["rounds"]), key=lambda r: when(r["spawn_ts"]))
        subs, bot_subs = submissions(sr, pr)
        posted, outside = assign_submissions(subs, rounds)
        extra, before = assign_loose([x for p in parts for x in p["loose"]], rounds)
        passes = [s for r in rounds for s in r["passes"]]
        out_rounds, loop_units = fold_rounds(rounds, extra, posted)
        found = sum(posted.values())
        payload["deliveries"][label] = {
            "pr": pr,
            "pr_created": meta["created_at"],
            "edits_rvw_pr": any(f.startswith(".claude/skills/rvw-pr/") for f in changed),
            "changed_files": len(changed),
            "sessions": len(d["parts"]),
            "calls": sum(p["calls"] for p in parts),
            "units_m": m2(units),
            "usd_estimate": round(sum(p["usd"] for p in parts), 2),
            "phases_units_m": {k: m2(v) for k, v in phases.items()},
            "phases_pct": {k: round(v / units * 100, 1) for k, v in phases.items()},
            "build_cuts": [p["phase_calls"] for p in parts if p["phase_calls"]],
            "max_main_ctx_k": max(p["max_main_ctx_k"] for p in parts),
            "wall_min": round(wall / 60),
            "wait_min": round(wait / 60),
            "stated_idle_min": round(idle / 60),
            "active_min": round((wall - wait - idle) / 60),
            "rounds": out_rounds,
            "review_loop_rounds_units_m": m2(loop_units),
            "review_loop_before_first_round_units_m": m2(before["main_units"] + before["other_units"]),
            "findings_posted": found,
            "findings_outside_measured_sessions": outside,
            "bot_submissions_ignored": bot_subs,
            "units_m_per_round": round(loop_units / 1e6 / max(1, len(rounds)), 2),
            "units_m_per_finding": round(loop_units / 1e6 / max(1, found), 2),
            "passes": [
                {
                    "round": next(k + 1 for k, r in enumerate(rounds) if s in r["passes"]),
                    "description": s["description"],
                    "type": s["type"],
                    "calls": s["calls"],
                    "first_ctx": s["first_ctx"],
                    "final_ctx": s["final_ctx"],
                    "units_m": m2(s["units"]),
                    "findings_handed_back": s["findings_handed_back"],
                    "read_whole": s["read_whole"],
                    "context_pct": s["context_pct"],
                }
                for s in passes
            ],
            "pass_summary": {
                "passes": len(passes),
                "as_reviewer": sum(1 for s in passes if s["type"] == "reviewer"),
                "first_ctx_k_range": [
                    round(min(s["first_ctx"] for s in passes) / 1e3, 1),
                    round(max(s["first_ctx"] for s in passes) / 1e3, 1),
                ]
                if passes
                else None,
                "calls_median": st.median(s["calls"] for s in passes) if passes else None,
                "units_m_median": m2(st.median(s["units"] for s in passes)) if passes else None,
                "units_m_total": m2(sum(s["units"] for s in passes)),
                "read_whole_median": st.median(len(s["read_whole"]) for s in passes) if passes else None,
                "prefix_pct_mean": round(st.mean(s["context_pct"]["prefix"] for s in passes), 1) if passes else None,
                "process_pct_mean": round(st.mean(s["context_pct"]["process"] for s in passes), 1) if passes else None,
                "pr_pct_mean": round(st.mean(s["context_pct"]["pr"] for s in passes), 1) if passes else None,
            },
            "by_method": by_method(passes),
            "unassigned_passes": sum(p["unassigned_passes"] for p in parts),
        }
        print(f"{label}: {m2(units)} M units, {len(rounds)} rounds, {found} findings posted")
    for label, ps in cfg.get("other", {}).items():
        parts = [measure_part(args.snapshots, p, set(), "9999-01-01T00:00:00Z") for p in ps]
        payload["other"][label] = {
            "units_m": m2(sum(p["units"] for p in parts)),
            "usd_estimate": round(sum(p["usd"] for p in parts), 2),
        }
    inputs: dict[str, Path | str] = {"config": args.config}
    for label, d in cfg["deliveries"].items():
        for i, p in enumerate(d["parts"]):
            inputs[f"{label} part {i} main transcript"] = args.snapshots / p["session"] / f"{p['session']}.jsonl"
    cm.write_result(args.results, args.name, "deliveries", inputs, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
