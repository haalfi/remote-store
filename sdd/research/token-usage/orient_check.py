"""Prototype of an orient check: which open backlog items share an item's spec IDs, and when a session first saw them.

1. **Related open items.** From ``sdd/BACKLOG.md`` at ``--rev`` (default
   ``HEAD``), every open item whose ``spec:`` attribute line shares a spec ID
   with ``--item``. This is the query an orient step would run before planning.
2. **First mention** (with ``--transcript``). For each related item, and for
   each ``--term``, the first main-session call whose incoming context (tool
   results, prompts, attachments) contains the ID. A mention is not a weighing:
   it shows only when the ID was in front of the session.

Writes ``results/<--name>.json`` (default ``orient_check``).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import _common as c

HEADER = re.compile(r"^- \[[ ~]\] \*\*((?:BK|BUG|ID|BL)-\d+[a-z]?) — (.*)\*\*\s*$")
SPEC = re.compile(r"^\s+spec: (.*?) ·")


def open_items(text: str) -> dict[str, dict]:
    items, cur = {}, None
    for line in text.splitlines():
        m = HEADER.match(line)
        if m:
            cur = m.group(1)
            items[cur] = {"title": m.group(2), "spec": []}
            continue
        s = SPEC.match(line)
        if cur and s and not items[cur]["spec"]:
            items[cur]["spec"] = [x.strip() for x in s.group(1).split(",") if x.strip() not in ("—", "")]
    return items


def first_mentions(transcript: Path, terms: list[str]) -> dict[str, int | None]:
    """Call index (0-based, main session) at which each term first entered the context."""
    found: dict[str, int | None] = dict.fromkeys(terms)
    seen_msg, calls = set(), 0
    pending = ""
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = r.get("message")
        if r.get("type") == "assistant" and isinstance(m, dict) and isinstance(m.get("usage"), dict):
            mid = m.get("id")
            if m.get("model") != "<synthetic>" and mid not in seen_msg:
                seen_msg.add(mid)
                for t in terms:
                    if found[t] is None and re.search(rf"\b{re.escape(t)}\b", pending):
                        found[t] = calls
                pending = ""
                calls += 1
        elif r.get("type") in ("user", "attachment"):
            pending += json.dumps(r.get("message") or r.get("attachment") or "")
    return found


def main(argv=None) -> int:
    ap = c.parser(__doc__, data=False)
    ap.add_argument("--item", required=True, help="backlog ID, e.g. BUG-280")
    ap.add_argument("--rev", default="HEAD", help="commit to read sdd/BACKLOG.md at")
    ap.add_argument("--transcript", type=Path, default=None, help="main-session transcript to scan")
    ap.add_argument("--term", action="append", default=[], help="extra ID to look for (repeatable)")
    ap.add_argument("--name", default="orient_check")
    args = c.resolve(ap.parse_args(argv))
    sha = subprocess.run(
        ["git", "-C", str(args.repo_root), "rev-parse", "--short", args.rev], capture_output=True, text=True, check=True
    ).stdout.strip()
    text = subprocess.run(
        ["git", "-C", str(args.repo_root), "show", f"{sha}:sdd/BACKLOG.md"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    items = open_items(text)
    own = set(items[args.item]["spec"])
    related = {k: sorted(own & set(v["spec"])) for k, v in items.items() if k != args.item and own & set(v["spec"])}
    payload = {
        "item": args.item,
        "spec": sorted(own),
        "open_items": len(items),
        "related": {k: {"shared": v, "title": items[k]["title"]} for k, v in related.items()},
    }
    inputs: dict = {"sdd/BACKLOG.md at commit": sha}
    if args.transcript:
        payload["first_mention_call"] = first_mentions(args.transcript, sorted(related) + args.term)
        inputs["main transcript"] = args.transcript
    c.write_result(args.results, args.name, "orient_check", inputs, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
