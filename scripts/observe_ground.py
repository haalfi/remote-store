"""Confine an ``/observe`` design session to its ground (RFC-0024 D4, D11).

Run by ``.claude/hooks/observe-ground.sh`` with one mode argument, the hook
payload on stdin. The method is research-spec-first-reset.md § 4: S2 (a fresh
session and a hook that denies reads outside an allowlist) and S3 (the
allowlist is the ground register plus files the maintainer names at the start).

* ``arm`` (``UserPromptSubmit``): a prompt ``/observe <op> [path ...]`` arms
  the session by writing ``tmp/observe/<session_id>.json``. Refused, with the
  prompt blocked, when the session already used a tool (it is not fresh), when
  ``<op>`` is not a slug, or when a named path is missing or is 0.33 code, tests
  or a spec 001 to 050 (never ground, RFC-0024 § R1).
* ``rearm`` (``SessionStart``): a resumed or compacted session whose
  transcript opens with ``/observe`` is armed again, so it never resumes
  unarmed, whatever became of its marker.
* ``check`` (``PreToolUse``): in an armed session, a call passes only if it
  stays inside the allowlist; every other session passes untouched, the
  wrapper's fail-closed branch included.
* ``disarm`` (``SessionEnd``): removes the marker only when the session is
  cleared (``reason: clear``); a session that ends any other way may resume.

The skill re-runs its canary before every axis as well, so an unarmed session
stops even where these events do not reach.

The allowlist is the method files, the ``active`` rows of the ground register,
the named paths and the operation's record, the only file the session may
write. Reads go through Read, or Grep on one allowed file. Glob, Bash, Agent and
every tool not listed below are denied: a path inside a shell command cannot be
checked. WebSearch and WebFetch pass unless they name remote-store, whose code
and docs are 0.33 (the maintainer's choice for prior art on the web).

Exit codes follow Claude Code's hook contract: 0 allows, 2 blocks with the
stderr line shown to the model (``check``) or the user (``arm``). Stdlib only,
for the same reason as ``record_decision.py``: the hook runs outside any hatch
env.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REGISTER = "sdd/observe/ground-register.md"
MARKER_DIR = "tmp/observe"
# Read by every session; none of them is ground.
METHOD_FILES = (
    ".claude/skills/observe/SKILL.md",
    "sdd/observe/axes.md",
    REGISTER,
)
RECORD = "sdd/observe/records/{op}.md"

_PROMPT = re.compile(r"\s*/observe(?:\s+(?P<args>.*))?\s*$", re.DOTALL)
# How a transcript, and possibly UserPromptSubmit, records a typed slash command.
_TAGGED = re.compile(r"<command-name>/?observe</command-name>.*?<command-args>(?P<args>.*?)</command-args>", re.DOTALL)
_OP = re.compile(r"[a-z][a-z0-9_]*")
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
# A register row: `path` | flow | status |
_ROW = re.compile(r"^\|\s*`(?P<path>[^`]+)`\s*\|[^|]*\|\s*(?P<status>active|reopened)\s*\|\s*$")
_NEVER_GROUND = re.compile(r"^(src/|tests/|sdd/specs/0(?:0[1-9]|[1-4]\d|50)-)")
_OWN_SURFACE = re.compile(r"remote[-_ ]?store", re.IGNORECASE)
_TOOL_USE = re.compile(r'"type"\s*:\s*"tool_use"')
# Tools that read no file and write none.
_NEUTRAL = frozenset({"AskUserQuestion", "ToolSearch", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"})


class Refused(Exception):
    """The call or prompt is blocked; the message says why."""


def _marker(root: Path, session_id: str) -> Path:
    if not _SAFE_ID.fullmatch(session_id):
        raise Refused(f"unusable session_id {session_id!r}")
    return root / MARKER_DIR / f"{session_id}.json"


def _real(root: Path, path: str, cwd: str | None = None) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd or root) / p
    return os.path.realpath(p)


def ground(root: Path) -> list[str]:
    """Repo-relative paths of the register's ``active`` rows."""
    try:
        text = (root / REGISTER).read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused(f"ground register unreadable: {exc}") from exc
    return [m["path"] for m in map(_ROW.match, text.splitlines()) if m and m["status"] == "active"]


def _observe_args(text: str) -> list[str] | None:
    """The arguments of an ``/observe`` prompt, typed or in slash-command tag form; None otherwise."""
    tagged = _TAGGED.search(text)
    if tagged:
        return tagged["args"].split()
    m = _PROMPT.match(text)
    return (m["args"] or "").split() if m else None


def _first_prompt(transcript: Path) -> str | None:
    """The text of the transcript's first user message that is not harness metadata."""
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "user" or entry.get("isMeta"):
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
        if isinstance(content, str) and content.strip():
            return content
    return None


def arm(payload: dict[str, Any], root: Path) -> str | None:
    """Write the marker for an ``/observe`` prompt; return its record, or None."""
    args = _observe_args(payload.get("prompt") or "")
    if args is None:
        return None
    transcript = payload.get("transcript_path")
    if (
        transcript
        and Path(transcript).is_file()
        and _TOOL_USE.search(Path(transcript).read_text(encoding="utf-8", errors="replace"))
    ):
        raise Refused("/observe needs a fresh session (S2): this one already used a tool. Run /clear first.")
    return _write_marker(payload, root, args)


def rearm(payload: dict[str, Any], root: Path) -> str | None:
    """Re-arm a resumed or compacted session whose first prompt was ``/observe``; return its record, or None.

    Its marker may be gone (cleared, or a resume under a new session_id) while its
    transcript still holds the design dialogue, so a resume never runs unarmed.
    """
    transcript = payload.get("transcript_path")
    if not transcript or not Path(transcript).is_file():
        return None
    first = _first_prompt(Path(transcript))
    args = _observe_args(first) if first else None
    return None if args is None else _write_marker(payload, root, args)


def _write_marker(payload: dict[str, Any], root: Path, args: list[str]) -> str:
    if not args or not _OP.fullmatch(args[0]):
        raise Refused("usage: /observe <operation> [path ...], operation as a lower-case slug")
    named = []
    for path in args[1:]:
        rel = Path(_real(root, path)).relative_to(os.path.realpath(root)).as_posix() if _inside(root, path) else None
        if rel is None or not Path(root, rel).is_file():
            raise Refused(f"{path}: not a file in this repository")
        if _NEVER_GROUND.match(rel):
            raise Refused(f"{rel}: 0.33 code, tests and specs 001 to 050 are never ground (RFC-0024 § R1)")
        named.append(rel)
    doc = RECORD.format(op=args[0])
    marker = _marker(root, payload.get("session_id") or "")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"operation": args[0], "record": doc, "named": named}), encoding="utf-8", newline="\n"
    )
    return doc


def _inside(root: Path, path: str) -> bool:
    real, base = _real(root, path), os.path.realpath(root)
    return real == base or real.startswith(base + os.sep)


def check(payload: dict[str, Any], root: Path) -> None:
    """Raise Refused when an armed session's call leaves its allowlist."""
    sid = payload.get("session_id") or ""
    if not _SAFE_ID.fullmatch(sid) or not _marker(root, sid).is_file():
        return
    marker = _marker(root, sid)
    state = json.loads(marker.read_text(encoding="utf-8"))
    tool = payload.get("tool_name") or ""
    args = payload.get("tool_input") or {}
    cwd = payload.get("cwd")
    if tool in _NEUTRAL:
        return
    if tool == "Skill" and args.get("skill") == "observe":
        return
    if tool in ("WebSearch", "WebFetch"):
        target = args.get("query") or args.get("url") or ""
        if _OWN_SURFACE.search(target):
            raise Refused(f"{tool}: remote-store's own code and docs are 0.33, never ground (S1)")
        return
    doc = _real(root, state["record"])
    if tool in ("Write", "Edit"):
        if _real(root, args.get("file_path") or "", cwd) != doc:
            raise Refused(f"{tool}: this session writes only {state['record']} (S4)")
        return
    if tool in ("Read", "Grep"):
        target = args.get("file_path") if tool == "Read" else args.get("path")
        allowed = {_real(root, p) for p in (*METHOD_FILES, *ground(root), *state["named"])} | {doc}
        real = _real(root, target or "", cwd)
        # A symlinked entry is judged by what it points at.
        rel = os.path.relpath(real, os.path.realpath(root)).replace(os.sep, "/")
        if not target or real not in allowed or _NEVER_GROUND.match(rel) or rel.startswith("../"):
            raise Refused(
                f"{tool}: {target or '(no path)'} is outside the ground. Allowed: the files {REGISTER} "
                f"lists as active, the method files {', '.join(METHOD_FILES)}, the record "
                f"{state['record']} and the paths named at /observe (S3)."
            )
        return
    raise Refused(f"{tool}: not available in an /observe session (S2). Read allowed files with Read.")


def disarm(payload: dict[str, Any], root: Path) -> None:
    """Drop the marker only when the session is cleared: any other end may be resumed."""
    if payload.get("reason") != "clear":
        return
    with contextlib.suppress(Refused):
        _marker(root, payload.get("session_id") or "").unlink(missing_ok=True)


def _concerns_observe(mode: str, raw: str, root: Path) -> bool:
    """Whether a crash on *raw* may block: only an /observe prompt or an armed session's call."""
    if mode == "arm":
        return "/observe" in raw
    if mode == "check":
        sid = re.search(r'"session_id"\s*:\s*"([A-Za-z0-9_-]+)"', raw)
        return sid is not None and (root / MARKER_DIR / f"{sid[1]}.json").is_file()
    return False


def main(argv: list[str], root: Path = ROOT) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
        if mode == "arm":
            arm(payload, root)
        elif mode == "rearm":
            rearm(payload, root)
        elif mode == "check":
            check(payload, root)
        elif mode == "disarm":
            disarm(payload, root)
        else:
            raise Refused(f"unknown mode {mode!r}")
    except Refused as exc:
        print(f"Blocked (/observe ground hook): {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 -- fail closed for an armed session only
        if not _concerns_observe(mode, raw, root):
            return 0
        print(f"Blocked (/observe ground hook failed): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
