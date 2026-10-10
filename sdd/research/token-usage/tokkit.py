"""Token kit: snapshot, live-watch and analyse one Claude Code session on this repo.

    python tokkit.py find   [--since ISO]            # list candidate sessions
    python tokkit.py live   --session SID [--every N] # one line per event while it runs
    python tokkit.py report --session SID [--md OUT]  # snapshot + full analysis

The session may live in any of the transcript folders
``_common.default_transcripts`` finds for ``--repo-root`` (a ``/ship``
worktree gets its own). ``report`` first copies the main transcript, its
subagents and tool-results into ``--snapshots/<sid>/`` (default
``<repo-root>/tmp/token-kit/runs``, gitignored), because Claude Code deletes
transcripts after ``cleanupPeriodDays`` (30 by default). Snapshots and the
report hold prompts and paths: they stay out of the repo.

Token sizes use ``_common.COEF`` (calibrate.py), dollars ``_common.PRICE``,
units ``_common.W``. The report's phases split the main session at its first
Edit or Write and at its first ``pr-link`` record, and lists review rounds by
the subagents each round spawned.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import statistics as st
import sys
import time
from pathlib import Path

import _common as cm

KIT = Path(__file__).resolve().parent
W, COEF, PRICE = cm.W, cm.COEF, cm.PRICE
ARGS: argparse.Namespace


# ----------------------------------------------------------------- discovery
def project_dirs():
    return cm.default_transcripts(ARGS.repo_root)


def first_ts(path: Path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("timestamp"):
                return r["timestamp"]
    return None


def first_prompt(path: Path) -> str:
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            m = r.get("message")
            if r.get("type") == "user" and isinstance(m, dict) and not r.get("isMeta"):
                c = m.get("content")
                # Skip /clear and local-command wrappers: the real request follows them.
                if isinstance(c, str) and not re.search(r"<command-name>/?clear<|<local-command-", c):
                    return " ".join(c.split())[:120]
    return ""


def locate(sid: str) -> Path:
    for d in project_dirs():
        p = d / f"{sid}.jsonl"
        if p.exists():
            return p
    raise SystemExit(f"no transcript for session {sid}")


def cmd_find(args):
    rows = []
    for d in project_dirs():
        for p in d.glob("*.jsonl"):
            t = first_ts(p)
            if t and (not args.since or t >= args.since):
                rows.append((t, p.stem, d.name, p.stat().st_size, first_prompt(p)))
    for t, sid, d, size, prompt in sorted(rows):
        print(f"{t[:19]}  {sid}  {size / 1e6:6.2f} MB  {d:44}  {prompt}")


# ----------------------------------------------------------------- parsing
def transcript_files(main: Path):
    files = [main]
    sub = main.parent / main.stem / "subagents"
    if sub.is_dir():
        files += sorted(sub.glob("*.jsonl"))
    return files


def bash_cat(cmd: str) -> str:
    c = re.sub(r"^(\w+=\S+\s+)+", "", " ".join(str(cmd).split()))
    m = re.match(r"hatch run (?:python )?(?:-m )?([\w\-./]+)", c)
    if m:
        return "hatch run " + m.group(1)
    for pre in ("gh pr", "gh api", "gh run", "git diff", "git log", "git show", "git commit", "git push", "git"):
        if c.startswith(pre):
            return pre
    if "pytest" in c[:40]:
        return "pytest"
    return c.split(" ")[0][:24] if c else "?"


def norm_path(p: str) -> str:
    p = str(p).replace("\\", "/")
    if "/.claude/" in p and "/projects/" in p:
        return "<tool-results>" if "tool-results" in p else "<transcript>"
    if re.search(r"Temp/claude", p):
        return "<scratch>"
    m = re.search(rf"{re.escape(ARGS.repo_root.name)}(?:/\.claude/worktrees/[^/]+)?/(.*)$", p)
    p = m.group(1) if m else "<outside>/" + p[-50:]
    m = re.match(r"tmp/review/[0-9a-f]+/(.*)", p)
    return ("<review-snapshot>/" + m.group(1)) if m else p


def tool_label(name: str, inp) -> tuple[str, str]:
    inp = inp if isinstance(inp, dict) else {}
    if name == "Read":
        return "Read", norm_path(inp.get("file_path", "?"))
    if name in ("Bash", "PowerShell"):
        return name, bash_cat(inp.get("command", ""))
    if name in ("Edit", "Write"):
        return name, norm_path(inp.get("file_path", "?"))
    if name in ("Grep", "Glob"):
        return name, str(inp.get("pattern", ""))[:50]
    if name == "Skill":
        return "Skill", str(inp.get("skill", "?"))
    if name in ("Agent", "Task"):
        return "Agent", str(inp.get("description", inp.get("subagent_type", "")))[:50]
    if name.startswith("mcp__"):
        return "mcp", name.split("__")[-1]
    return name, ""


def chars(c) -> int:
    if isinstance(c, str):
        return len(c)
    if isinstance(c, list):
        return sum(
            6000
            if isinstance(b, dict) and b.get("type") == "image"
            else chars(b.get("text", b.get("content", "")))
            if isinstance(b, dict)
            else 0
            for b in c
        )
    return 0


def parse_file(path: Path):
    """Return (calls, items, events) for one transcript."""
    calls, items, events = [], [], []
    seen, tools, pending = set(), {}, []
    seg = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        t, ts = r.get("type"), r.get("timestamp")
        if t == "pr-link" and not any(
            e["kind"] == "pr-open" and e["detail"] == f"PR #{r.get('prNumber')}" for e in events
        ):
            events.append(
                {
                    "ts": r.get("timestamp") or (calls[-1]["ts"] if calls else None),
                    "kind": "pr-open",
                    "detail": f"PR #{r.get('prNumber')}",
                    "idx": len(calls),
                }
            )
        if t == "system" and r.get("subtype") == "compact_boundary":
            seg += 1
            events.append({"ts": ts, "kind": "compaction", "detail": "", "idx": len(calls)})
        if t == "attachment":
            a = r.get("attachment") or {}
            n = sum(chars(x.get("content")) for x in r.get("rendered") or [] if isinstance(x, dict))
            if n:
                pending.append(("attachment", a.get("type", "?"), n * COEF["attachment"]))
            continue
        m = r.get("message")
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if t == "user":
            if isinstance(content, str):
                k = "user_meta" if r.get("isMeta") else "user_prompt"
                sk = re.search(r"Base directory for this skill: .*?[\\/]skills[\\/]([\w\-:]+)", content)
                pending.append((k, ("skill-body:" + sk.group(1)) if sk else "", len(content) * COEF["user"]))
            elif isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_result":
                        cat, det = tools.get(b.get("tool_use_id"), ("?", ""))
                        txt = b.get("content")
                        n = chars(txt)
                        spilled = "persisted-output" in (txt if isinstance(txt, str) else json.dumps(txt))
                        pending.append(
                            (f"result:{cat}", det + (" [spilled]" if spilled else ""), n * COEF["tool_result"])
                        )
                    elif b.get("type") == "text":
                        pending.append(
                            (
                                "user_prompt" if not r.get("isMeta") else "user_meta",
                                "",
                                len(b.get("text", "")) * COEF["user"],
                            )
                        )
            continue
        if t != "assistant":
            continue
        usage, mid = m.get("usage"), m.get("id")
        if (
            isinstance(usage, dict)
            and m.get("model") != "<synthetic>"
            and (not isinstance(mid, str) or mid not in seen)
        ):
            if isinstance(mid, str):
                seen.add(mid)
            cc = usage.get("cache_creation") or {}
            w5 = cc.get("ephemeral_5m_input_tokens", 0) if cc else usage.get("cache_creation_input_tokens", 0)
            w1h = cc.get("ephemeral_1h_input_tokens", 0) if cc else 0
            row = {
                "idx": len(calls),
                "ts": ts,
                "seg": seg,
                "model": m.get("model"),
                "skill": r.get("attributionSkill"),
                "input": usage.get("input_tokens", 0),
                "read": usage.get("cache_read_input_tokens", 0),
                "w5": w5,
                "w1h": w1h,
                "out": usage.get("output_tokens", 0),
                "emits": [],
            }
            row["ctx"] = row["input"] + row["read"] + w5 + w1h
            row["units"] = sum(W[k] * row[k] for k in ("input", "read", "w5", "w1h", "out"))
            for kind, det, tok in pending:
                items.append({"enter": row["idx"], "seg": seg, "kind": kind, "detail": det, "tok": tok})
            pending = []
            calls.append(row)
        if isinstance(content, list) and calls:
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    cat, det = tool_label(b.get("name", "?"), b.get("input"))
                    tools[b.get("id")] = (cat, det)
                    calls[-1]["emits"].append(f"{cat} {det}".strip())
                    pending.append((f"tool_input:{cat}", det, len(json.dumps(b.get("input"))) * COEF["assistant"]))
                    if cat == "Agent":
                        events.append({"ts": ts, "kind": "agent-spawn", "detail": det, "idx": len(calls)})
                    if cat == "Bash" and det in ("git commit", "git push"):
                        events.append({"ts": ts, "kind": det, "detail": "", "idx": len(calls)})
                    if cat == "Skill":
                        events.append({"ts": ts, "kind": "skill", "detail": det, "idx": len(calls)})
                elif b.get("type") == "text":
                    pending.append(("assistant_text", "", len(b.get("text", "")) * COEF["assistant"]))
    return calls, items, events


def visible_out(items, idx):
    return sum(
        i["tok"]
        for i in items
        if i["enter"] == idx and (i["kind"].startswith("tool_input") or i["kind"] == "assistant_text")
    )


# ----------------------------------------------------------------- live
def cmd_live(args):
    main = locate(args.session)
    seen_files, shown_calls, shown_events = {}, collections.Counter(), set()
    print(f"watching {main}", flush=True)
    while True:
        for f in transcript_files(main):
            calls, items, events = parse_file(f)
            tag = "main" if f == main else f.stem[-6:]
            if f not in seen_files and f != main:
                meta = f.with_name(f.stem + ".meta.json")
                desc = json.loads(meta.read_text()).get("description", "") if meta.exists() else ""
                print(f"[{tag}] subagent started: {desc}", flush=True)
            seen_files[f] = True
            for e in events:
                key = (str(f), e["kind"], e["idx"], e["detail"])
                if key not in shown_events:
                    shown_events.add(key)
                    print(f"[{tag}] {e['kind']:12} call {e['idx']:4}  {e['detail']}", flush=True)
            n = len(calls)
            if n and n // args.every > shown_calls[str(f)] // args.every:
                u = sum(c["units"] for c in calls)
                usd = sum(c["units"] * PRICE.get(c["model"], 2.31e-6) for c in calls)
                print(
                    f"[{tag}] {n:4} calls  ctx {calls[-1]['ctx'] / 1e3:6.0f}k  units {u / 1e6:6.2f}M  ~${usd:6.2f}",
                    flush=True,
                )
            shown_calls[str(f)] = n
        time.sleep(args.poll)


# ----------------------------------------------------------------- report
def snapshot(main: Path) -> Path:
    dest = ARGS.snapshots / main.stem
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(main, dest / main.name)
    side = main.parent / main.stem
    if side.is_dir():
        shutil.copytree(side, dest / main.stem, dirs_exist_ok=True)
    return dest


def carried(calls, items):
    """Calibrated re-read tokens per item: tokens x calls it stays in context (until compaction)."""
    segend = collections.defaultdict(int)
    for c in calls:
        segend[c["seg"]] = max(segend[c["seg"]], c["idx"] + 1)
    out = collections.Counter()
    det = collections.Counter()
    for it in items:
        if it["enter"] == 0:
            continue
        life = max(0, segend[it["seg"]] - it["enter"])
        out[it["kind"]] += it["tok"] * life
        det[(it["kind"], it["detail"])] += it["tok"] * life
    for a, b in zip(calls, calls[1:], strict=False):
        hidden = max(0, a["out"] - visible_out(items, b["idx"]))
        out["thinking (hidden)"] += COEF["hidden"] * hidden * max(0, segend[a["seg"]] - b["idx"])
    return out, det


def cmd_report(args):
    main = locate(args.session)
    dest = snapshot(main)
    lines = []
    p = lines.append
    files = transcript_files(main)

    def load(f):
        calls, items, events = parse_file(f)
        if args.until:
            calls = [x for x in calls if (x["ts"] or "") <= args.until]
            items = [i for i in items if i["enter"] < len(calls)]
            events = [e for e in events if e["idx"] < len(calls)]
        return calls, items, events

    parsed = {f: load(f) for f in files}
    mc, mi, me = parsed[main]
    # Review/fix rounds a /ship loop runs as their own sessions (e.g. a forked /rvw-pr <PR>),
    # and the fresh session /ship § Resume at the PR runs the loop in (/ship resume <PR>).
    prs = {e["detail"].split("#")[1] for e in me if e["kind"] == "pr-open"}
    start = first_ts(main) or ""
    related = []
    for d in project_dirs():
        for cand in d.glob("*.jsonl"):
            if cand == main or (first_ts(cand) or "") < start:
                continue
            fp = first_prompt(cand)
            if any(re.search(rf"/(rvw-pr|fix-pr|ship\b.*\bresume)\b.*\b{pr}\b", fp) for pr in prs):
                related.append(cand)
                snapshot(cand)
                for rf in transcript_files(cand):
                    files.append(rf)
                    parsed[rf] = load(rf)
    if related:
        p(f"Related sessions included: {', '.join(r.stem[:8] + ' (' + first_prompt(r)[:30] + ')' for r in related)}\n")
    allcalls = [c for f in files for c in parsed[f][0]]
    U = sum(c["units"] for c in allcalls)
    usd = sum(c["units"] * PRICE.get(c["model"], 2.31e-6) for c in allcalls)
    p(f"# Token report: session {main.stem}\n")
    p(f"Snapshot: `{dest}`. First prompt: `{first_prompt(main)}`\n")
    tot = collections.Counter()
    for c in allcalls:
        for k in ("input", "read", "w5", "w1h", "out"):
            tot[k] += c[k]
    p("## Totals\n")
    p("| Transcripts | Calls | Tokens | Units | Est. $ |\n| ---: | ---: | ---: | ---: | ---: |")
    p(
        f"| {len(files)} (1 main, {len(files) - 1} subagents) | {len(allcalls)} | "
        f"{sum(tot.values()):,} | {U:,.0f} | {usd:.2f} |\n"
    )
    p("| Class | Tokens | Share of units |\n| --- | ---: | ---: |")
    for k, name in (
        ("read", "cache read"),
        ("w1h", "cache write 1h"),
        ("w5", "cache write 5m"),
        ("out", "output"),
        ("input", "input"),
    ):
        p(f"| {name} | {tot[k]:,} | {W[k] * tot[k] / U * 100:.1f}% |")
    # phases of the main session
    pr = next((e for e in me if e["kind"] == "pr-open"), None)
    first_edit = next((c["idx"] for c in mc if any(x.startswith(("Edit", "Write")) for x in c["emits"])), None)

    def phase_of(c):
        if pr and c["idx"] >= pr["idx"]:
            return "3 review loop (after PR open)"
        if first_edit is not None and c["idx"] >= first_edit:
            return "2 build (first edit to PR open)"
        return "1 orient + plan (before first edit)"

    p("\n## Main session by phase\n")
    p("| Phase | Calls | Units | Share of all units | Mean ctx |\n| --- | ---: | ---: | ---: | ---: |")
    ph = collections.defaultdict(list)
    for c in mc:
        ph[phase_of(c)].append(c)
    for k in sorted(ph):
        cs = ph[k]
        p(
            f"| {k} | {len(cs)} | {sum(c['units'] for c in cs):,.0f} | "
            f"{sum(c['units'] for c in cs) / U * 100:.1f}% | {st.mean(c['ctx'] for c in cs) / 1e3:.0f}k |"
        )
    subu = U - sum(c["units"] for c in mc)
    p(f"| subagents (all) | {len(allcalls) - len(mc)} | {subu:,.0f} | {subu / U * 100:.1f}% | |")
    # subagents
    p("\n## Subagents\n")
    p("| Description | Calls | Prefix | Final ctx | Units | Share |\n| --- | ---: | ---: | ---: | ---: | ---: |")
    for f in files[1:]:
        cs = parsed[f][0]
        if not cs:
            continue
        meta = f.with_name(f.stem + ".meta.json")
        desc = json.loads(meta.read_text()).get("description", f.stem) if meta.exists() else f.stem
        u = sum(c["units"] for c in cs)
        p(f"| {desc} | {len(cs)} | {cs[0]['ctx']:,} | {cs[-1]['ctx']:,} | {u:,.0f} | {u / U * 100:.1f}% |")
    # composition (all transcripts)
    p("\n## What the re-read context is made of (all transcripts)\n")
    comp = collections.Counter()
    dets = collections.Counter()
    sumctx = sum(c["ctx"] for c in allcalls)
    prefix = 0
    for f in files:
        cs, its, _ = parsed[f]
        if not cs:
            continue
        prefix += cs[0]["ctx"] * len(cs)
        o, d = carried(cs, its)
        comp.update(o)
        dets.update(d)
    roll = collections.Counter({"session prefix": prefix})
    for k, v in comp.items():
        roll[
            k.split(":")[0]
            + (":" + k.split(":")[1] if k.startswith("result:") and k.split(":")[1] in ("Read", "Bash", "Grep") else "")
        ] += v
    roll["unexplained"] = sumctx - prefix - sum(comp.values())
    p("| Component | Share |\n| --- | ---: |")
    for k, v in roll.most_common():
        p(f"| {k} | {v / sumctx * 100:.1f}% |")
    p("\n### Top 25 items by carried tokens\n")
    p("| Share | Kind | Detail |\n| ---: | --- | --- |")
    for (k, d), v in dets.most_common(25):
        p(f"| {v / sumctx * 100:.2f}% | {k} | `{d}` |")
    # what the model was doing: units by the tool each call emitted
    p("\n## Units by what the call emitted (main session)\n")
    act = collections.Counter()
    for c in mc:
        e = c["emits"][0].split(" ")[0] if c["emits"] else "text/final"
        act[e] += c["units"]
    mu = sum(act.values())
    p("| Emitted | Units | Share of main |\n| --- | ---: | ---: |")
    for k, v in act.most_common(12):
        p(f"| {k} | {v:,.0f} | {v / mu * 100:.1f}% |")
    # re-reads and spills
    reads = collections.Counter()
    rtok = collections.Counter()
    for f in files:
        for it in parsed[f][1]:
            if it["kind"] == "result:Read":
                reads[(f.stem, it["detail"])] += 1
                rtok[(f.stem, it["detail"])] += it["tok"]
    dup = sum(rtok[k] * (reads[k] - 1) / reads[k] for k in reads if reads[k] > 1)
    p(f"\nRe-reads of a file already read in the same transcript: {dup:,.0f} of {sum(rtok.values()):,.0f} Read tokens.")
    spills = [it for f in files for it in parsed[f][1] if it["detail"].endswith("[spilled]")]
    p(f"Spilled (oversized) tool outputs: {len(spills)}: " + ", ".join(sorted({s["detail"] for s in spills})))
    p("\n## Events (main session)\n")
    for e in me:
        p(f"- call {e['idx']}: {e['kind']} {e['detail']}")
    text = "\n".join(lines)
    out = Path(args.md) if args.md else dest / "report.md"
    out.write_text(text, encoding="utf-8")
    (dest / "calls.json").write_text(json.dumps({str(f.name): parsed[f][0] for f in files}), encoding="utf-8")
    if not args.json:
        print(text)
    print(f"written: {out}")
    if args.json:
        summary = {
            "transcripts": sum(1 for f in files if parsed[f][0]),
            "calls": len(allcalls),
            "main_calls": len(mc),
            "units_m": round(U / 1e6, 2),
            "usd_estimate": round(usd, 2),
            "units_pct_by_class": {k: round(W[k] * tot[k] / U * 100, 1) for k in W},
            "first_edit_call": first_edit,
            "pr_open_call": pr["idx"] if pr else None,
            "compaction_calls": [e["idx"] for e in me if e["kind"] == "compaction"],
            "phases": {
                k.split(" ", 1)[1]: {
                    "calls": len(cs),
                    "units_pct": round(sum(x["units"] for x in cs) / U * 100, 1),
                    "mean_ctx_k": round(st.mean(x["ctx"] for x in cs) / 1e3),
                }
                for k, cs in sorted(ph.items())
            }
            | {"subagents": {"calls": len(allcalls) - len(mc), "units_pct": round(subu / U * 100, 1)}},
            "context_shares_pct": {k: round(v / sumctx * 100, 1) for k, v in roll.most_common()},
            "top_items_pct": [
                {"kind": k, "detail": d, "pct": round(v / sumctx * 100, 2)}
                for (k, d), v in dets.most_common(10)
                if not d.startswith("<outside>")
            ],
            "read_tokens_reread_pct": round(dup / max(1, sum(rtok.values())) * 100, 1),
            "spilled_outputs": len(spills),
            "rounds": rounds_of(mc, me, files, parsed),
        }
        cm.write_result(Path(args.json).parent, Path(args.json).stem, "tokkit", {"main transcript": main}, summary)


def rounds_of(mc, me, files, parsed):
    """Review rounds as the main-session calls that spawned subagents, with what each round cost.

    A round runs from one spawning call to the next; its cost is the main-session
    units in that span plus the units of the subagents it spawned (matched by the
    Agent description recorded in each subagent's ``.meta.json``)."""
    spawns = collections.defaultdict(list)
    forked = []  # a forked /rvw-pr runs as one subagent whose description starts with "/rvw-pr"
    for e in me:
        if e["kind"] == "agent-spawn":
            spawns[e["idx"]].append(e["detail"])
        elif e["kind"] == "skill" and e["detail"].endswith("rvw-pr"):
            spawns[e["idx"]].append("/rvw-pr")
            forked.append(e["idx"])
    starts = sorted(spawns)
    sub_units = collections.Counter()
    subs = [f for f in files[1:] if parsed[f][0]]
    rvw = []
    for f in subs:
        meta = f.with_name(f.stem + ".meta.json")
        desc = (json.loads(meta.read_text()).get("description", "") if meta.exists() else "")[:50]
        if desc.startswith("/rvw-pr"):
            rvw.append((parsed[f][0][0]["ts"] or "", f))
            continue
        # A round re-run after a rebase repeats its descriptions: take the latest matching
        # spawn whose spawning call (an event's idx is the call after it) precedes this
        # subagent's first call.
        first = parsed[f][0][0]["ts"] or ""
        at = max((i for i in starts if desc in spawns[i] and (mc[i - 1]["ts"] or "") <= first), default=None)
        if at is not None:
            sub_units[at] += sum(x["units"] for x in parsed[f][0])
    for at, (_, f) in zip(forked, sorted(rvw, key=lambda t: t[0]), strict=False):
        sub_units[at] += sum(x["units"] for x in parsed[f][0])
    out = []
    for n, i in enumerate(starts):
        j = starts[n + 1] if n + 1 < len(starts) else len(mc)
        out.append(
            {
                "spawn_call": i,
                "members": len(spawns[i]),
                "main_ctx_k": round(mc[i - 1]["ctx"] / 1e3),
                "main_units_m": round(sum(x["units"] for x in mc[i:j]) / 1e6, 2),
                "subagent_units_m": round(sub_units[i] / 1e6, 2),
            }
        )
    return out


def main(argv=None):
    global ARGS
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "token kit")
    ap.add_argument("--repo-root", type=Path, default=cm.DEFAULT_REPO, help="checkout whose transcripts to read")
    ap.add_argument(
        "--snapshots", type=Path, default=None, help="snapshot folder (default <repo-root>/tmp/token-kit/runs)"
    )
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("find")
    f.add_argument("--since", default=None)
    lv = sp.add_parser("live")
    lv.add_argument("--session", required=True)
    lv.add_argument("--every", type=int, default=25)
    lv.add_argument("--poll", type=float, default=20)
    rp = sp.add_parser("report")
    rp.add_argument("--session", required=True)
    rp.add_argument("--md", default=None)
    rp.add_argument("--json", default=None, help="also write an aggregated, ID-free summary to this .json path")
    rp.add_argument("--until", default=None, help="ISO timestamp: ignore calls after it, in every transcript")
    args = ap.parse_args(argv)
    args.repo_root = args.repo_root.resolve()
    args.snapshots = args.snapshots or args.repo_root / "tmp" / "token-kit" / "runs"
    ARGS = args
    {"find": cmd_find, "live": cmd_live, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
