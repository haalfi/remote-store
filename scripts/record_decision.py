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
under its raw ``hook_event_name`` with the payload less its local paths
(``cwd``, ``transcript_path``, ``scratchpad_dir``), so a future registration
loses nothing it may publish; readers skip kinds they do not know.

Never blocks the dialog it records. Every error inside ``main()`` is caught,
noted in one stderr line, and the process exits 0; the wrapper covers the case
where this file cannot even start. Stdlib only, and no construct newer than the
oldest host ``python`` it may meet, because the hook runs outside any hatch env
and the repo's ``requires-python`` does not bind that interpreter.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

_KINDS = {"PreToolUse": "asked", "PostToolUse": "answered"}
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
# Absolute local paths every payload carries. The log is committed to a public
# repository, so the raw-name fallback drops them, as the test fixtures do.
_LOCAL_PATH_KEYS = frozenset({"cwd", "transcript_path", "scratchpad_dir"})
_GIT_CMD = ["git"]
# One deadline for both git calls, at most half the hook's 10 s timeout in
# settings.json: a hook killed at its timeout loses the event, while a git call
# that runs out of budget only nulls its field.
_GIT_BUDGET_S = 4.0


def _git(root: Path, deadline: float, *args: str) -> str | None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    try:
        result = subprocess.run(
            [*_GIT_CMD, "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=remaining,
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

    deadline = time.monotonic() + _GIT_BUDGET_S
    line: dict[str, Any] = {
        "event": kind,
        # timezone.utc, not datetime.UTC: the host interpreter may predate 3.11.
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),  # noqa: UP017
        "session_id": payload.get("session_id"),
        "tool_use_id": payload.get("tool_use_id"),
        # `branch --show-current` prints nothing on a detached HEAD, which _git maps to None.
        "branch": _git(root, deadline, "branch", "--show-current"),
        "head": _git(root, deadline, "rev-parse", "HEAD"),
    }
    remote = env.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    if remote:
        line["remote_session_id"] = remote
    if hook_event in _KINDS:
        line["tool_input"] = payload.get("tool_input")
        if "tool_response" in payload:
            line["tool_response"] = payload["tool_response"]
    else:
        line["payload"] = {k: v for k, v in payload.items() if k not in _LOCAL_PATH_KEYS}

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
