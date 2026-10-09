"""What every call re-reads: the calibrated composition of context, summed over all calls.

An item's **carried** tokens are its calibrated size times the calls it stays
in context: from the call it entered at to the end of its transcript segment
(a compaction ends a segment). The **prefix** is each transcript's first-call
context, paid on every call of that transcript. Hidden thinking is each call's
output tokens minus its calibrated visible output, carried from the next call
on. What none of these explain is reported as unexplained.

Reads ``--data``, writes ``results/composition.json``.
"""

from __future__ import annotations

import collections
import statistics as st

import _common as c

# MEMORY.md before the 2026-10-09 trim: 13,620 bytes / 2.43 chars per token. The
# file lives outside the repo, so its size is a recorded input, not read here.
MEMORY_TOKENS_BEFORE_TRIM = 5605


def main(argv=None) -> int:
    ap = c.parser(__doc__)
    ap.add_argument("--memory-tokens", type=int, default=MEMORY_TOKENS_BEFORE_TRIM, help="MEMORY.md size in tokens")
    args = c.resolve(ap.parse_args(argv))
    calls, items, S = c.load_extract(args.data)
    bycall = c.by_file(calls)
    ends = c.segment_ends(bycall)
    n = {f: len(cs) for f, cs in bycall.items()}
    U = sum(x["units"] for x in calls)

    carried = collections.Counter()
    detail = collections.Counter()
    vis_by_enter = collections.Counter()
    for it in items:
        f = it["file"]
        if f not in n:
            continue
        if it["kind"].startswith("assistant"):
            vis_by_enter[(f, it["enter"])] += it["chars"]
        if it["enter"] == 0:
            continue  # part of the prefix
        tok = it["chars"] * c.COEF[c.group(it["kind"])]
        life = max(0, ends.get((f, it["seg"]), n[f]) - it["enter"])
        carried[it["kind"]] += tok * life
        detail[(it["kind"], it["detail"])] += tok * life
    hidden_carried = 0.0
    hidden_out = 0.0
    for f, cs in bycall.items():
        for a, b in zip(cs, cs[1:], strict=False):
            hidden = max(0, a["out"] - vis_by_enter[(f, b["idx"])] * c.COEF["assistant"])
            hidden_out += hidden
            hidden_carried += c.COEF["hidden"] * hidden * (ends.get((f, a["seg"]), n[f]) - b["idx"])
    prefix = sum(cs[0]["ctx"] * len(cs) for cs in bycall.values())
    sumctx = sum(x["ctx"] for x in calls)

    roll = collections.Counter()
    for k, v in carried.items():
        if k.startswith("tool_result:"):
            t = k[12:]
            roll["tool result: " + (t if t in ("Read", "Bash", "Grep", "TaskOutput") else "other")] += v
        elif k.startswith("assistant_tool_use:"):
            roll["tool inputs the model wrote"] += v
        elif k in ("assistant_text", "assistant_thinking"):
            roll["visible model text"] += v
        elif k == "attachment":
            roll["harness attachments"] += v
        else:
            roll["prompts, skill bodies, other"] += v
    roll["hidden thinking"] = hidden_carried
    roll["session prefix"] = prefix
    roll["unexplained"] = sumctx - prefix - sum(carried.values()) - hidden_carried
    attachments = collections.Counter({d: v for (k, d), v in detail.items() if k == "attachment"})
    att_count = collections.Counter(it["detail"] for it in items if it["kind"] == "attachment" and it["enter"] > 0)

    # prefix composition: items that entered before call 0, mean per transcript
    prefix_parts = {}
    for kind, label in ((False, "main"), (True, "subagent")):
        sel = [f for f in bycall if S[f]["is_sub"] == kind]
        comp = collections.Counter()
        for it in items:
            if it["file"] in sel and it["enter"] == 0:
                comp[it["detail"] if it["kind"] == "attachment" else it["kind"]] += (
                    it["chars"] * c.COEF[c.group(it["kind"])]
                )
        mean_prefix = st.mean(bycall[f][0]["ctx"] for f in sel)
        prefix_parts[label] = {
            "n": len(sel),
            "mean_prefix_tokens": round(mean_prefix),
            "min_prefix_tokens": min(bycall[f][0]["ctx"] for f in sel),
            "max_prefix_tokens": max(bycall[f][0]["ctx"] for f in sel),
            "instructions": round(comp["instructions"] / len(sel)),
            "skill_listing": round(comp["skill_listing"] / len(sel)),
            "system_prompt_and_tools_rest": round(mean_prefix - sum(comp.values()) / len(sel)),
        }

    # output: visible (calibrated) versus hidden
    out_tokens = sum(x["out"] for x in calls)
    vis = collections.Counter()
    for it in items:
        if it["kind"].startswith("assistant"):
            vis[it["kind"].split(":")[-1] if ":" in it["kind"] else it["kind"]] += it["chars"] * c.COEF["assistant"]

    # tool volume, errors, re-reads
    volume = collections.Counter()
    volume_tok = collections.Counter()
    errors = collections.Counter()
    reads = collections.Counter()
    read_tok = collections.Counter()
    sub_readers = collections.defaultdict(set)
    for it in items:
        k = it["kind"]
        if k.startswith("tool_result:"):
            volume[k[12:]] += 1
            volume_tok[k[12:]] += it["chars"] * c.COEF["tool_result"]
            if it.get("err"):
                errors[k[12:]] += 1
        if k == "tool_result:Read":
            reads[(it["file"], it["detail"])] += 1
            read_tok[(it["file"], it["detail"])] += it["chars"]
            if S[it["file"]]["is_sub"]:
                sub_readers[it["detail"]].add(it["file"])
    reread = sum(read_tok[k] * (reads[k] - 1) / reads[k] for k in reads if reads[k] > 1)

    # auto-loaded instruction files, as if in every call (one cache write at start, a read per later call)
    claude_tokens = round((args.repo_root / "CLAUDE.md").stat().st_size * c.COEF["attachment"])

    def always(tok, mains_only):
        return sum(
            tok * (2.0 if not S[f]["is_sub"] else 1.25) + tok * 0.1 * len(cs)
            for f, cs in bycall.items()
            if not (mains_only and S[f]["is_sub"])
        )

    payload = {
        "sum_context_tokens": sumctx,
        "shares_pct": {k: c.pct(v, sumctx) for k, v in roll.most_common()},
        "top_items_pct": [
            {"kind": k, "detail": d, "pct": round(100 * v / sumctx, 2)} for (k, d), v in detail.most_common(25)
        ],
        "attachments_after_start": {
            k: {"injections": att_count[k], "pct": round(100 * v / sumctx, 2)} for k, v in attachments.most_common(6)
        },
        "prefix": prefix_parts,
        "output": {
            "tokens": out_tokens,
            "units_pct": c.pct(c.W["out"] * out_tokens, U),
            "hidden_pct_of_output": c.pct(hidden_out, out_tokens, 0),
            "visible_tokens_by_kind": {k: round(v) for k, v in vis.most_common(6)},
        },
        "tool_volume": {
            k: {"results": volume[k], "mean_tokens": round(volume_tok[k] / volume[k])} for k, _ in volume.most_common(5)
        },
        "tool_errors": {"total": sum(errors.values()), "by_tool": dict(errors.most_common(3))},
        "read_tokens_reread_pct": c.pct(reread, sum(read_tok.values()), 0),
        "files_read_by_most_subagents": [
            {"file": p, "subagents": len(fs)} for p, fs in sorted(sub_readers.items(), key=lambda kv: -len(kv[1]))[:8]
        ],
        "instruction_files": {
            "claude_md_tokens": claude_tokens,
            "claude_md_units_pct_if_every_call": c.pct(always(claude_tokens, False), U, 2),
            "memory_md_tokens": args.memory_tokens,
            "memory_md_units_pct_main_sessions": c.pct(always(args.memory_tokens, True), U, 2),
        },
    }
    inputs = c.extract_inputs(args.data) | {"CLAUDE.md": args.repo_root / "CLAUDE.md"}
    c.write_result(args.results, "composition", "composition", inputs, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
