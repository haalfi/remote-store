"""Extract one row per API call and one row per context item from Claude Code transcripts.

Writes ``calls.jsonl``, ``items.jsonl`` and ``sessions.json`` into ``--data``.
These hold prompts, local paths and session IDs: they stay out of the repo,
and every other script reads them from there.

    python extract.py [--transcripts DIR ...] [--since 2026-08-14] [--exclude-session SID ...]

``--transcripts`` defaults to the folders ``_common.default_transcripts``
computes for ``--repo-root``. A call is one assistant record with ``usage``,
deduplicated by message id. An item is anything that enters the context
before a call (tool result, attachment, prompt, the model's own tool inputs
and text), recorded with its character count and the call it entered at.
Only transcripts whose first record falls on or after ``--since`` count.
"""

from __future__ import annotations

import contextlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import _common as c

CLEAR = re.compile(r"<command-name>/?clear<|<local-command-")
SKILL_BODY = re.compile(r"Base directory for this skill: .*?[\\/]skills[\\/]([\w\-:]+)")


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def chars(x) -> int:
    if x is None:
        return 0
    if isinstance(x, str):
        return len(x)
    if isinstance(x, list):
        n = 0
        for b in x:
            if isinstance(b, dict):
                n += 6000 if b.get("type") == "image" else chars(b.get("text", b.get("content", "")))
            elif isinstance(b, str):
                n += len(b)
        return n
    if isinstance(x, dict):
        return len(json.dumps(x))
    return 0


class Paths:
    """Normalise a file path to repo-relative, or to a placeholder outside the repo."""

    def __init__(self, repo: Path):
        name = re.escape(repo.name)
        self.repo_re = re.compile(rf"^.*?{name}(?:[\\/]\.claude[\\/]worktrees[\\/][^\\/]+)?[\\/]", re.I)

    def __call__(self, p) -> str:
        p = str(p)
        parts = re.split(r"[\\/]", p)
        if ".claude" in parts and "projects" in parts:
            return "<transcript>"
        if re.search(r"Temp[\\/]claude", p):
            return "<scratch/tasks>"
        m = self.repo_re.match(p)
        if m:
            return p[m.end() :].replace("\\", "/")
        return "<outside>/" + p.replace("\\", "/")[-60:]


def bash_cat(cmd) -> str:
    s = re.sub(r"^(\w+=\S+\s+)+", "", " ".join(str(cmd).split()))
    m = re.match(r"hatch run (?:python )?(?:-m )?([\w\-./]+)", s)
    if m:
        return "hatch run " + m.group(1)
    for pre in ("gh pr", "gh api", "gh issue", "gh run", "git diff", "git log", "git show", "git status", "git grep",
                "git commit", "git push", "git fetch", "git"):  # fmt: skip
        if s.startswith(pre):
            return pre
    if s.startswith(("python -m pytest", "pytest", "python scripts/run_tests")):
        return "pytest"
    if s.startswith("python"):
        return "python"
    return s.split(" ")[0][:20] if s else "?"


def tool_label(name: str, inp, norm) -> tuple[str, str]:
    inp = inp if isinstance(inp, dict) else {}
    if name == "Read":
        return "Read", norm(inp.get("file_path", "?"))
    if name in ("Bash", "PowerShell"):
        return name, bash_cat(inp.get("command", ""))
    if name in ("Grep", "Glob"):
        return name, str(inp.get("pattern", ""))[:60]
    if name in ("Edit", "Write"):
        return name, norm(inp.get("file_path", "?"))
    if name == "Skill":
        return "Skill", str(inp.get("skill", "?"))
    if name in ("Agent", "Task"):
        return "Agent", str(inp.get("subagent_type", "general-purpose"))
    if name.startswith("mcp__"):
        parts = name.split("__")
        return "mcp:" + parts[1], parts[-1]
    return name, ""


def transcript_files(dirs: list[Path], exclude: set[str]):
    for d in dirs:
        for f in sorted(d.rglob("*.jsonl")):
            if f.stem in exclude or exclude & set(f.parts):
                continue
            yield d, f


def main(argv=None) -> int:
    ap = c.parser(__doc__, results=False)
    ap.add_argument("--transcripts", type=Path, action="append", help="transcript folder (repeatable)")
    ap.add_argument("--since", default="2026-08-14", help="first-record date cut-off, ISO (default 2026-08-14)")
    ap.add_argument("--exclude-session", action="append", default=[], help="session ID to skip (repeatable)")
    args = c.resolve(ap.parse_args(argv))
    dirs = args.transcripts or c.default_transcripts(args.repo_root)
    if not dirs:
        ap.error("no transcript folder found; pass --transcripts")
    cutoff = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
    norm = Paths(args.repo_root)
    args.data.mkdir(parents=True, exist_ok=True)
    seen_msg: set = set()
    sessions: dict = {}
    with (
        (args.data / "calls.jsonl").open("w", encoding="utf-8") as calls_out,
        (args.data / "items.jsonl").open("w", encoding="utf-8") as items_out,
    ):
        for d, f in transcript_files(dirs, set(args.exclude_session)):
            rel = str(f.relative_to(d.parent))
            is_sub = "subagents" in f.parts
            meta: dict = {}
            if is_sub:
                mf = f.with_name(f.stem + ".meta.json")
                if mf.exists():
                    meta = json.loads(mf.read_text(encoding="utf-8"))
                meta["forked_skill"] = f.with_name(f.stem + ".forked-skill.json").exists()
            recs = []
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                with contextlib.suppress(json.JSONDecodeError):
                    recs.append(json.loads(line))
            first = next((ts(r["timestamp"]) for r in recs if r.get("timestamp")), None)
            if first is None or first < cutoff:
                continue
            rel_parts = f.relative_to(d).parts
            S = sessions.setdefault(
                rel,
                {
                    "file": rel,
                    "project": d.name,
                    "parent": rel_parts[0] if is_sub else f.stem,
                    "is_sub": is_sub,
                    "meta": meta,
                    "first_ts": first.isoformat(),
                    "titles": [],
                    "prs": [],
                    "branches": [],
                    "skills": [],
                    "slash": [],
                    "first_prompt": None,
                    "cost": None,
                    "compactions": 0,
                    "user_prompts": 0,
                    "models": [],
                    "dup_records": 0,
                },
            )
            parse(recs, rel, is_sub, S, seen_msg, norm, calls_out, items_out)
    (args.data / "sessions.json").write_text(json.dumps(sessions, indent=1, default=str), encoding="utf-8")
    print(len(sessions), "transcripts in window, written to", args.data)
    return 0


def parse(recs, rel, is_sub, S, seen_msg, norm, calls_out, items_out) -> None:
    call_idx = segment = 0
    prev = None
    tool_names: dict = {}
    pending: list = []
    seen_uuid: set = set()
    last_ts = None

    def prompt(text: str) -> None:
        S["user_prompts"] += 1
        if S["first_prompt"] is None and not CLEAR.search(text):
            S["first_prompt"] = text[:300]

    for r in recs:
        t, u = r.get("type"), r.get("uuid")
        if u:
            if u in seen_uuid:
                S["dup_records"] += 1
                continue
            seen_uuid.add(u)
        if t == "custom-title":
            S["titles"].append(r.get("customTitle"))
        elif t == "ai-title":
            S["titles"].append(r.get("aiTitle"))
        elif t == "pr-link" and r.get("prNumber") not in S["prs"]:
            S["prs"].append(r.get("prNumber"))
            S.setdefault("pr_open", {})[str(r.get("prNumber"))] = r.get("timestamp")
        elif t == "cost-state":
            S["cost"] = {k: r.get(k) for k in ("totalCostUSD", "totalLinesAdded", "totalLinesRemoved", "modelUsage")}
        elif t == "system" and r.get("subtype") == "compact_boundary":
            S["compactions"] += 1
            segment += 1
        elif t == "system" and r.get("subtype") == "local_command":
            m = re.search(r"<command-name>(.*?)</command-name>", r.get("content", ""))
            if m:
                S["slash"].append(m.group(1))
        br = r.get("gitBranch")
        if br and br not in S["branches"]:
            S["branches"].append(br)
        if r.get("timestamp"):
            last_ts = r["timestamp"]
        msg = r.get("message")
        if t == "attachment":
            a = r.get("attachment") or {}
            rendered = r.get("rendered")
            n = (
                sum(chars(x.get("content")) for x in rendered if isinstance(x, dict))
                if isinstance(rendered, list)
                else 0
            )
            if n:
                pending.append(("attachment", a.get("type", "?"), n, None))
            continue
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if t == "user":
            if isinstance(content, str):
                kind = "user_meta" if r.get("isMeta") else "user_prompt"
                detail = ""
                if kind == "user_prompt":
                    prompt(content)
                    m = re.search(r"<command-name>/?(.*?)</command-name>", content)
                    if m:
                        S["slash"].append(m.group(1))
                else:
                    m = SKILL_BODY.search(content)
                    detail = ("skill-body:" + m.group(1)) if m else content[:40].replace("\n", " ")
                if r.get("isCompactSummary"):
                    kind, detail = "compact_summary", ""
                pending.append((kind, detail, len(content), None))
            elif isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_result":
                        cat, det = tool_names.get(b.get("tool_use_id"), ("?", ""))
                        pending.append(("tool_result:" + cat, det, chars(b.get("content")), b.get("is_error")))
                    elif b.get("type") == "text":
                        txt = b.get("text", "")
                        m = SKILL_BODY.search(txt)
                        if m:
                            pending.append(("user_meta", "skill-body:" + m.group(1), len(txt), None))
                        elif r.get("isMeta"):
                            pending.append(("user_meta", txt[:40].replace("\n", " "), len(txt), None))
                        else:
                            prompt(txt)
                            pending.append(("user_prompt", "", len(txt), None))
                    elif b.get("type") == "image":
                        pending.append(("user_prompt", "image", 6000, None))
            continue
        if t != "assistant":
            continue
        usage, mid = msg.get("usage"), msg.get("id")
        if isinstance(usage, dict) and mid not in seen_msg:
            seen_msg.add(mid)
            cc = usage.get("cache_creation") or {}
            w5 = cc.get("ephemeral_5m_input_tokens", 0) if cc else usage.get("cache_creation_input_tokens", 0)
            w1h = cc.get("ephemeral_1h_input_tokens", 0) if cc else 0
            rd = usage.get("cache_read_input_tokens", 0)
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            ctx = inp + rd + w5 + w1h
            tnow = ts(r.get("timestamp", ""))
            gap = (tnow - prev["t"]).total_seconds() if prev and tnow and prev["t"] else None
            row = {
                "file": rel,
                "idx": call_idx,
                "seg": segment,
                "ts": r.get("timestamp"),
                "model": msg.get("model"),
                "branch": r.get("gitBranch"),
                "skill": r.get("attributionSkill"),
                "input": inp,
                "read": rd,
                "w5": w5,
                "w1h": w1h,
                "out": out,
                "ctx": ctx,
                "units": c.W["input"] * inp + c.W["read"] * rd + c.W["w5"] * w5 + c.W["w1h"] * w1h + c.W["out"] * out,
                "gap": gap,
                "miss": bool(prev and rd < 0.5 * prev["ctx"] and prev["ctx"] > 10000),
                "prev_ctx": prev["ctx"] if prev else 0,
                "prev_model": prev["model"] if prev else None,
                "stop": msg.get("stop_reason"),
                "is_sub": is_sub,
            }
            calls_out.write(json.dumps(row) + "\n")
            for kind, det, n, err in pending:
                rec = {
                    "file": rel,
                    "enter": call_idx,
                    "seg": segment,
                    "kind": kind,
                    "detail": det,
                    "chars": n,
                    "err": err,
                }
                items_out.write(json.dumps(rec) + "\n")
            pending = []
            if msg.get("model") and msg.get("model") not in S["models"]:
                S["models"].append(msg.get("model"))
            prev = {"ctx": ctx, "t": tnow, "model": msg.get("model")}
            call_idx += 1
        if isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "tool_use":
                    cat, det = tool_label(b.get("name", "?"), b.get("input"), norm)
                    tool_names[b.get("id")] = (cat, det)
                    if cat == "Skill":
                        S["skills"].append(det)
                    pending.append(("assistant_tool_use:" + cat, det, len(json.dumps(b.get("input"))), None))
                elif bt == "text":
                    pending.append(("assistant_text", "", len(b.get("text", "")), None))
                elif bt == "thinking":
                    pending.append(("assistant_thinking", "", len(b.get("thinking", "")), None))
    S["calls"] = call_idx
    S["last_ts"] = last_ts
    S["segments"] = segment + 1


if __name__ == "__main__":
    raise SystemExit(main())
