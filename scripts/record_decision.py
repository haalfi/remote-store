"""Append an ``AskUserQuestion`` hook event to the session's decision log.

Run by ``.claude/hooks/record-decision.sh`` on ``PreToolUse`` and
``PostToolUse`` with matcher ``AskUserQuestion``; reads the hook payload on
stdin and appends one JSON line to ``sdd/decisions/<session_id>.jsonl`` under
this checkout's root. The design, and why each field is kept, is RFC-0018 D1
and D2.

One line per event::

    {"event": "asked" | "answered", "ts": "<UTC ISO-8601>Z",
     "session_id": ..., "tool_use_id": ...,
     "branch": <name, or null when detached or unread>, "head": <sha or null>,
     "remote_session_id": ...,          # only when CLAUDE_CODE_REMOTE_SESSION_ID is set
     "tool_input": {...},               # verbatim
     "tool_response": {...}}            # verbatim, answered only

Two kinds of dialog stay out of the committed log (RFC-0018 D1 to D3, as BK-486
amends them). One tagged ``metadata.source: "housekeeping"`` is not recorded:
the tag reaches ``PreToolUse`` only, so its ``tool_use_id`` is kept in
``sdd/decisions/.pending/<session_id>.skip`` to drop the ``answered`` event too.
One asked on the base branch or a detached HEAD is held in the gitignored
``sdd/decisions/.pending/<session_id>.jsonl`` (one whose branch git could not
read is logged, since it may be a work branch, and so is one during a rebase,
whose detached HEAD is the branch being rebased) and moved into the log, in order,
only by ``promote()``, which ``gate-commit.sh`` runs with ``--promote`` before
that same session commits on a work branch. One
``{"event": "promoted", "ts", "session_id", "branch", "head"}`` line follows
them, naming the work branch, which binds them there under D4.0, read in the
log's line order: the moved lines land after any the session logged since. A dialog never
promotes: the branch it reads is the project directory's, which another session
may have switched. So a question held after a session's cleanup reaches a
commit only if that session later commits on a work branch, untagged.

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
# The pair gate-commit.sh refuses to commit on; an event there, or on a detached
# HEAD, is held until the session commits on a work branch.
_BASE_BRANCHES = frozenset({"master", "main"})
_HOUSEKEEPING = "housekeeping"
# One deadline for both git calls, at most half the hook's 10 s timeout in
# settings.json: a hook killed at its timeout loses the event, while a git call
# that runs out of budget only nulls its field.
_GIT_BUDGET_S = 4.0


def _git(root: Path, deadline: float, *args: str) -> str | None:
    """*args*' stripped output, possibly empty; None when git failed or ran out of budget."""
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
    return result.stdout.strip() if result.returncode == 0 else None


def _rebasing(root: Path, deadline: float) -> bool:
    """True while a rebase runs, which detaches HEAD from the branch it rewrites."""
    paths = _git(root, deadline, "rev-parse", "--git-path", "rebase-merge", "--git-path", "rebase-apply")
    return bool(paths) and any((root / p).is_dir() for p in paths.splitlines())


def _safe_session(payload: Mapping[str, Any]) -> str:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not _SAFE_ID.fullmatch(session_id):
        return "unknown-session"
    return session_id


def _pending(root: Path) -> Path:
    return root / "sdd" / "decisions" / ".pending"


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _skipped(payload: Mapping[str, Any], root: Path, session_id: str) -> bool:
    """True for either event of a dialog tagged housekeeping, remembering the tag from Pre."""
    skip = _pending(root) / f"{session_id}.skip"
    tool_use_id = str(payload.get("tool_use_id"))
    tool_input = payload.get("tool_input")
    metadata = tool_input.get("metadata") if isinstance(tool_input, dict) else None
    source = metadata.get("source") if isinstance(metadata, dict) else None
    if payload.get("hook_event_name") == "PreToolUse" and source == _HOUSEKEEPING:
        _append(skip, tool_use_id + "\n")
        return True
    return skip.is_file() and tool_use_id in skip.read_text(encoding="utf-8").splitlines()


def _now() -> str:
    # timezone.utc, not datetime.UTC: the host interpreter may predate 3.11.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")  # noqa: UP017


def promote(root: Path, session_id: str) -> int:
    """Move *session_id*'s held lines into its log under *root*, in order; return how many.

    Run by ``gate-commit.sh`` before that session commits on a work branch. A
    ``promoted`` line follows the moved lines, naming the branch and HEAD they
    moved on. It is the session's event on that work branch, so RFC-0018 D4.0
    binds them there although the commit recorded no dialog.
    """
    held = _pending(root) / f"{session_id}.jsonl"
    if not held.is_file():
        return 0
    deadline = time.monotonic() + _GIT_BUDGET_S
    branch = _git(root, deadline, "branch", "--show-current") or None
    head = _git(root, deadline, "rev-parse", "HEAD") or None
    text = held.read_text(encoding="utf-8")
    marker = {"event": "promoted", "ts": _now(), "session_id": session_id, "branch": branch, "head": head}
    _append(root / "sdd" / "decisions" / f"{session_id}.jsonl", text + json.dumps(marker) + "\n")
    held.unlink()
    return len(text.splitlines())


def record(payload: Mapping[str, Any], root: Path, env: Mapping[str, str]) -> Path | None:
    """Append *payload* as one line under *root*; return the path written, or None if skipped."""
    if payload.get("tool_name") != "AskUserQuestion":
        return None
    hook_event = str(payload.get("hook_event_name"))
    kind = _KINDS.get(hook_event, hook_event)

    session_id = _safe_session(payload)
    if _skipped(payload, root, session_id):
        return None

    deadline = time.monotonic() + _GIT_BUDGET_S
    # `branch --show-current` prints nothing on a detached HEAD; None means git failed.
    branch = _git(root, deadline, "branch", "--show-current")
    line: dict[str, Any] = {
        "event": kind,
        "ts": _now(),
        "session_id": payload.get("session_id"),
        "tool_use_id": payload.get("tool_use_id"),
        "branch": branch or None,
        "head": _git(root, deadline, "rev-parse", "HEAD") or None,
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

    # Held lines are not promoted here: the branch is the project directory's,
    # which another session may have switched, so only this session's own
    # commit (gate-commit.sh --promote) moves them. A branch git could not read
    # may be a work branch, so that event is logged with a null branch, as before;
    # so is one during a rebase, whose `rebase --continue` no hook promotes on.
    detached = branch == "" and not _rebasing(root, deadline)
    if detached or branch in _BASE_BRANCHES:
        target = _pending(root) / f"{session_id}.jsonl"
    else:
        target = root / "sdd" / "decisions" / f"{session_id}.jsonl"
    _append(target, json.dumps(line, ensure_ascii=False) + "\n")
    return target


def main(argv: list[str] | None = None) -> int:
    """Record the hook payload on stdin; with ``--promote ROOT``, promote its session under ROOT."""
    args = sys.argv[1:] if argv is None else argv
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
        if args[:1] == ["--promote"]:
            promote(Path(args[1]), _safe_session(payload))
        else:
            record(payload, Path(__file__).resolve().parents[1], os.environ)
    except Exception as exc:  # noqa: BLE001 -- a recorder must never block the dialog or the commit
        print(f"record_decision: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
