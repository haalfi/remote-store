"""Per work item: measured units against the trace and the PR, and the cost after the PR opened.

A work item's sessions are found through the PR it shipped (``_common.WORK``,
``_common.work_groups``). Per item this reports units, estimated dollars, the
share spent in subagents or in sessions other than the one that opened the PR,
the files its trace names against the repo files its transcripts Read, review
rounds and findings from the trace's ``review:`` block, and units per changed
line from the PR.

For sessions whose transcript records when the PR opened (``pr_open``), it
splits the session group's units at that moment, and estimates what running
the post-PR main-session calls on a fresh context would have saved: the
context carried into the PR beyond the session prefix, re-read on every
post-PR call, less a fresh session re-reading 30k or 60k tokens once per
round of about 40 calls.

Reads ``--data`` (extract, ``prs.json``) and ``--repo-root``'s ``sdd/traces``;
writes ``results/work_items.json``.
"""

from __future__ import annotations

import collections

import _common as c
import yaml


def norm(p: str) -> str:
    return p.split("#")[0].strip().replace("\\", "/")


def trace_facts(repo, names):
    files = collections.Counter()
    steps = 0
    rounds = findings = None
    for t in names:
        path = repo / "sdd" / "traces" / t
        if not path.is_file():
            continue
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        for ph in d.get("phases") or []:
            for s in ph.get("steps") or []:
                steps += 1
                if s.get("file"):
                    files[norm(str(s["file"]))] += 1
        r = d.get("review") or {}
        if r:
            rounds = (rounds or 0) + (r.get("review_rounds") or 0)
            findings = (findings or 0) + (r.get("findings") or 0)
        elif d.get("review_rounds"):
            rr = d["review_rounds"]
            rounds = (rounds or 0) + (rr if isinstance(rr, int) else len(rr))
    return files, steps, rounds, findings


def main(argv=None) -> int:
    args = c.resolve(c.parser(__doc__).parse_args(argv))
    calls, items, S = c.load_extract(args.data)
    prs = {p["number"]: p for p in c.load_prs(args.data)}
    bycall = c.by_file(calls)
    groups = c.work_groups(S, list(prs.values()))
    itemsby = collections.defaultdict(list)
    for it in items:
        itemsby[it["file"]].append(it)
    ends = c.segment_ends(bycall)
    U = sum(x["units"] for x in calls)

    rows = {}
    for name, w in c.WORK.items():
        parents = groups[name]
        files = [f for f in bycall if S[f]["parent"] in parents]
        cs = [x for f in files for x in bycall[f]]
        units = sum(x["units"] for x in cs)
        usd = sum(x["units"] * c.PRICE[x["model"]] for x in cs)
        # the session that opened the PR; the others are review and fix sessions
        openers = {S[f]["parent"] for f in files if not S[f]["is_sub"] and set(w["prs"]) & set(S[f]["prs"] or [])}
        openers = openers or parents
        review = sum(
            x["units"]
            for x in cs
            if x["is_sub"] or x["skill"] in ("rvw-pr", "fix-pr") or S[x["file"]]["parent"] not in openers
        )
        readtok = collections.Counter()
        for f in files:
            for it in itemsby[f]:
                if it["kind"] == "tool_result:Read" and not it["detail"].startswith("<"):
                    readtok[norm(it["detail"])] += it["chars"] * c.COEF["tool_result"]
        tfiles, steps, rounds, findings = trace_facts(args.repo_root, w["traces"])
        lines = sum(prs[n]["add"] + prs[n]["del"] for n in w["prs"])
        rows[name] = {
            "kind": w["kind"],
            "prs": w["prs"],
            "session_groups": len(parents & {S[f]["parent"] for f in files}),
            "transcripts": len(files),
            "calls": len(cs),
            "units_m": round(units / 1e6, 1),
            "usd_estimate": round(usd),
            "subagent_or_review_units_pct": c.pct(review, units, 0),
            "trace_steps": steps,
            "trace_files": len(tfiles),
            "repo_files_read": len(readtok),
            "overlap": len(set(tfiles) & set(readtok)),
            "read_tokens_not_in_trace_pct": c.pct(
                sum(v for k, v in readtok.items() if k not in tfiles), sum(readtok.values()), 0
            ),
            "review_rounds": rounds,
            "findings": findings,
            "units_per_finding_m": round(units / findings / 1e6, 2) if findings else None,
            "changed_lines": lines,
            "units_per_changed_line_k": round(units / lines / 1e3, 1),
        }

    # cost after the PR opened, for sessions that recorded the moment
    after = []
    for f, s in S.items():
        if s["is_sub"] or not s.get("pr_open") or f not in bycall:
            continue
        item = next((n for n, w in c.WORK.items() if any(str(p) in s["pr_open"] for p in w["prs"])), None)
        if item is None:
            continue
        pr = next(str(p) for p in c.WORK[item]["prs"] if str(p) in s["pr_open"])
        t_open = s["pr_open"][pr]
        grp = [x for g in bycall if S[g]["parent"] == s["parent"] for x in bycall[g]]
        main_cs = bycall[f]
        pre = [x for x in grp if x["ts"] < t_open]
        post = [x for x in grp if x["ts"] >= t_open]
        m_pre = [x for x in main_cs if x["ts"] < t_open]
        m_post = [x for x in main_cs if x["ts"] >= t_open]
        gu = sum(x["units"] for x in grp)
        carry = m_post[0]["ctx"] - main_cs[0]["ctx"] if m_post else 0
        gross = carry * 0.1 * len(m_post)
        rounds = max(1, len(m_post) // 40)
        fresh = {
            f"reread_{k // 1000}k": c.pct(gross - rounds * (k * 1.25 + k * 0.1 * 40), gu, 0) for k in (30_000, 60_000)
        }
        after.append(
            {
                "item": item,
                "pr": int(pr),
                "group_units_after_pr_open_pct": c.pct(sum(x["units"] for x in post), gu, 0),
                "group_calls_before_after": [len(pre), len(post)],
                "main_context_at_pr_open": m_post[0]["ctx"] if m_post else None,
                "main_units_per_call_before_after": [
                    round(sum(x["units"] for x in m_pre) / max(1, len(m_pre))),
                    round(sum(x["units"] for x in m_post) / max(1, len(m_post))),
                ],
                "fresh_context_ceiling": {"gross_pct": c.pct(gross, gu, 0), "net_pct": fresh, "rounds_assumed": rounds},
            }
        )

    # trace exposure (whole-file size per reading trace) against what reads cost here
    paid = collections.Counter()
    nreads = collections.Counter()
    for it in items:
        if it["kind"] == "tool_result:Read" and it["file"] in bycall:
            tok = it["chars"] * c.COEF["tool_result"]
            life = ends.get((it["file"], it["seg"]), len(bycall[it["file"]])) - it["enter"]
            paid[norm(it["detail"])] += tok * life * 0.1 + tok * 1.5
            nreads[norm(it["detail"])] += 1
    exposure_files = ["sdd/BACKLOG-DONE.md", "sdd/BACKLOG.md", "sdd/CLAUDE-REFERENCE.md", "sdd/traces/_schema.yml",
                      ".claude/skills/ship/SKILL.md", ".claude/skills/rvw-pr/SKILL.md"]  # fmt: skip
    paid_rows = {p: {"reads": nreads[p], "units_pct": c.pct(paid[p], U, 2)} for p in exposure_files}

    payload = {"items": rows, "after_pr_open": sorted(after, key=lambda r: r["item"]), "paid_by_file": paid_rows}
    inputs = c.extract_inputs(args.data) | {"prs.json": args.data / "prs.json"}
    c.write_result(args.results, "work_items", "workitems", inputs, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
