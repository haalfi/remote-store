"""Append an ``AskUserQuestion`` hook event to the session's decision log.

Run by ``.claude/hooks/record-decision.sh`` on ``PreToolUse`` and
``PostToolUse`` with matcher ``AskUserQuestion``; reads the hook payload on
stdin and appends one JSON line to ``sdd/decisions/<session_id>.jsonl`` under
this checkout's root. The design, and why each field is kept, is RFC-0018 D1
and D2.

One line per event::

    {"event": "asked" | "answered", "ts": "<UTC ISO-8601>Z",
     "session_id": ..., "tool_use_id": ...,
     "branch": <name, or null when detached>, "head": <sha or null>,
     "remote_session_id": ...,          # only when CLAUDE_CODE_REMOTE_SESSION_ID is set
     "tool_input": {...},               # verbatim
     "tool_response": {...}}            # verbatim, answered only

Payloads are stored as received and never interpreted: outcomes are derived by
readers (RFC-0018 D3). An event other than the two registered ones is kept
under its raw ``hook_event_name`` with the whole payload, so a future
registration loses nothing; readers skip kinds they do not know.

Never blocks the dialog it records. Every error is caught, noted in one stderr
line, and the process exits 0; the wrapper covers the case where this file
cannot even start. Stdlib only, because the hook runs outside any hatch env.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

_KINDS = {"PreToolUse": "asked", "PostToolUse": "answered"}
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
_GIT_TIMEOUT_S = 5


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = result.stdout.strip()
    return out if result.returncode == 0 and out else None


def record(payload: Mapping[str, Any], root: Path, env: Mapping[str, str]) -> Path | None:
    """Append *payload* as one line under *root*; return the log path, or None if skipped."""
    if payload.get("tool_name") != "AskUserQuestion":
        return None
    hook_event = str(payload.get("hook_event_name"))
    kind = _KINDS.get(hook_event, hook_event)

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not _SAFE_ID.fullmatch(session_id):
        session_id = "unknown-session"

    line: dict[str, Any] = {
        "event": kind,
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "session_id": payload.get("session_id"),
        "tool_use_id": payload.get("tool_use_id"),
        # `branch --show-current` prints nothing on a detached HEAD, which _git maps to None.
        "branch": _git(root, "branch", "--show-current"),
        "head": _git(root, "rev-parse", "HEAD"),
    }
    remote = env.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    if remote:
        line["remote_session_id"] = remote
    if hook_event in _KINDS:
        line["tool_input"] = payload.get("tool_input")
        if "tool_response" in payload:
            line["tool_response"] = payload["tool_response"]
    else:
        line["payload"] = dict(payload)

    log = root / "sdd" / "decisions" / f"{session_id}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    return log


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
        record(payload, Path(__file__).resolve().parents[1], os.environ)
    except Exception as exc:  # noqa: BLE001 -- a recorder must never block the dialog
        print(f"record_decision: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
