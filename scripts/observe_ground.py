"""Confine an ``/observe`` design session to its ground (RFC-0024 D4, D11).

Run by ``.claude/hooks/observe-ground.sh`` with one mode argument, the hook
payload on stdin. The method is research-spec-first-reset.md § 4: S2 (a fresh
session and a hook that denies reads outside an allowlist) and S3 (the
allowlist is the ground register plus files the maintainer names at the start).

* ``arm`` (``UserPromptSubmit``): a prompt ``/observe <entry> [path ...]`` arms
  the session by writing ``tmp/observe/<session_id>.json``. ``<entry>`` is an
  ID of the operation catalogue (``OP-01``), the unit of a session (RFC-0026).
  Refused, with the prompt blocked, when the session already used a tool (it is
  not fresh), when the catalogue is not an ``active`` register row, when
  ``<entry>`` is no row of the catalogue, or when a named path is missing, is
  0.33 code, tests or a spec 001 to 050 (never ground, RFC-0024 § R1), is
  another entry's input file, or is a ``reopened`` register row.
  The prompt ``/observe release`` instead releases an armed or locked session
  (below); in a session with no marker it is refused.
* ``rearm`` (``SessionStart``): a resumed or compacted session that ``arm``
  armed is armed again, from the last ``/observe`` prompt before its first tool
  use, so it never resumes unarmed, whatever became of its marker, unless the
  marker is a release or that last prompt was ``/observe release``. When those
  arguments no longer arm (the catalogue reopened, an entry or named path gone),
  or the hook fails on a transcript naming ``/observe`` or one it cannot read, the session is locked
  instead: every call but the neutral ones is refused until ``/clear`` or a release.
* ``check`` (``PreToolUse``): in an armed session, a call passes only if it
  stays inside the allowlist; a released session may do anything but write its
  record; every other session passes untouched, the wrapper's fail-closed
  branch included.
* ``disarm`` (``SessionEnd``): when the session is cleared (``reason: clear``),
  turns its marker into a release; a session that ends any other way may resume
  armed.

A release (``{"released": "clear" | "release", "record": ...}``) marks a session
that is no longer a design session, so a resume never re-arms it (BK-498: a
worker restart after ``/clear`` resumed the cleared session, not the new one).
It frees the session, so it can commit its decision logs, and keeps its record
closed to Write, Edit, MultiEdit, NotebookEdit and a Bash command naming the record: a
session that may have read off the ground never writes the record (S1, S4).
A locked or unreadable marker names no record, so its release closes every file
under ``sdd/observe/records/``. That Bash check matches the path as text, so it
also refuses reading or staging the record by name, and a command that writes
the record without spelling it passes. A finished record is committed after
``/clear``, by a session with no marker. Only the maintainer can release, by a prompt.

What the hook cannot do: tell why the harness resumed a cleared session; join
a dialog split across two session ids, whose halves the recorder files under
each; or release a session resumed in a new container, where no marker
survives, so ``rearm`` arms it again and ``/observe release`` is still the way
out.

The skill re-runs its canary before every axis as well, so an unarmed session
stops even where these events do not reach.

The allowlist is the method files, the ``active`` rows of the ground register,
the entry's input file (``sdd/observe/inputs/<entry>.md``, never another
entry's; RFC-0027), the named paths and the entry's record, the only file the
session may write. Reads go through Read, or Grep on one allowed file. Glob, Bash, Agent and
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
CATALOGUE = "sdd/observe/catalogue.md"
RECORDS = "sdd/observe/records/"
RECORD = RECORDS + "{entry}.md"
INPUTS = "sdd/observe/inputs/"
INPUT = INPUTS + "{entry}.md"

_PROMPT = re.compile(r"\s*/observe(?:\s+(?P<args>.*))?\s*$", re.DOTALL)
# How a transcript, and possibly UserPromptSubmit, records a typed slash command.
_TAGGED = re.compile(r"<command-name>/?observe</command-name>.*?<command-args>(?P<args>.*?)</command-args>", re.DOTALL)
_ENTRY = re.compile(r"OP-\d{2}")
# A catalogue entry row: | `OP-NN` | intent | ...
_ENTRY_ROW = re.compile(r"^\|\s*`(OP-\d{2})`\s*\|")
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
# A register row: `path` | flow | status |
_ROW = re.compile(r"^\|\s*`(?P<path>[^`]+)`\s*\|[^|]*\|\s*(?P<status>active|reopened)\s*\|\s*$")
_NEVER_GROUND = re.compile(r"^(src/|tests/|sdd/specs/0(?:0[1-9]|[1-4]\d|50)-)")
_OWN_SURFACE = re.compile(r"remote[-_ ]?store", re.IGNORECASE)
_TOOL_USE = re.compile(r'"type"\s*:\s*"tool_use"')
# Tools that read no file and write none.
_NEUTRAL = frozenset({"AskUserQuestion", "ToolSearch", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"})


_RELEASE = ["release"]
_WAY_OUT = "Not a design session? The maintainer types /observe release."
# Write tools refused on a released session's record, with the key naming the file.
_WRITERS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}


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


def ground(root: Path, status: str = "active") -> list[str]:
    """Repo-relative paths of the register's rows of ``status`` (``active`` or ``reopened``)."""
    try:
        text = (root / REGISTER).read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused(f"ground register unreadable: {exc}") from exc
    return [m["path"] for m in map(_ROW.match, text.splitlines()) if m and m["status"] == status]


def entries(root: Path) -> list[str]:
    """The catalogue's entry IDs, in row order."""
    try:
        text = (root / CATALOGUE).read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused(f"catalogue unreadable: {exc}") from exc
    return [m[1] for m in map(_ENTRY_ROW.match, text.splitlines()) if m]


def _observe_args(text: str) -> list[str] | None:
    """The arguments of an ``/observe`` prompt, typed or in slash-command tag form; None otherwise."""
    tagged = _TAGGED.search(text)
    if tagged:
        return tagged["args"].split()
    m = _PROMPT.match(text)
    return (m["args"] or "").split() if m else None


def _armed_args(transcript: Path) -> list[str] | None:
    """The arguments of the last ``/observe`` prompt before the transcript's first tool use.

    These are the prompts ``arm`` accepts, a later one replacing an earlier one, so
    this is what the session was armed with; None if it never was.
    """
    args = None
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        if _TOOL_USE.search(line):
            break
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "user" or entry.get("isMeta"):
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
        if isinstance(content, str):
            prompt = _observe_args(content)
            # arm never arms on a release, so it ends any arming before it.
            args = None if prompt == _RELEASE else prompt or args
    return args


def _state(root: Path, session_id: str) -> dict[str, Any] | None:
    """The session's marker, or None when it has none."""
    marker = _marker(root, session_id)
    return json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None


def _release(root: Path, session_id: str, how: str) -> bool:
    """Turn the session's marker into a release; False when it has none."""
    try:
        state = _state(root, session_id)
    except ValueError:  # an unreadable marker is released without its record
        state = {}
    if state is None:
        return False
    if "released" not in state:
        state = {"released": how, "record": state.get("record")}
        _marker(root, session_id).write_text(json.dumps(state), encoding="utf-8", newline="\n")
    return True


def arm(payload: dict[str, Any], root: Path) -> str | None:
    """Write the marker for an ``/observe`` prompt, or release one; return its record, or None."""
    args = _observe_args(payload.get("prompt") or "")
    if args is None:
        return None
    if args == _RELEASE:
        if not _release(root, payload.get("session_id") or "", "release"):
            raise Refused("no /observe session to release in this session")
        print(
            "/observe ground hook: this session is released. It is no design session: commit every uncommitted "
            "sdd/decisions/ log on the work branch, then stop. No record is written or staged here: a record is "
            "written by a fresh /observe session and committed after /clear."
        )
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
    """Re-arm a resumed or compacted session that ``arm`` armed; return its record, or None.

    Its marker may be gone (cleared, or a resume under a new session_id) while its
    transcript still holds the design dialogue, so a resume never runs unarmed.
    """
    transcript = payload.get("transcript_path")
    if not transcript or not Path(transcript).is_file():
        return None
    with contextlib.suppress(Refused, OSError, ValueError):
        if "released" in (_state(root, payload.get("session_id") or "") or {}):
            return None
    try:
        args = _armed_args(Path(transcript))
        return None if args is None else _write_marker(payload, root, args)
    except Exception as exc:
        # SessionStart cannot block: a resume that cannot re-arm, refused or crashed, is locked.
        # A crash locks a transcript naming /observe, or one it cannot read: an ordinary readable one stays free.
        if not isinstance(exc, Refused):
            with contextlib.suppress(OSError):
                if "/observe" not in Path(transcript).read_text(encoding="utf-8", errors="replace"):
                    return None
        reason = str(exc) if isinstance(exc, Refused) else f"hook failed: {type(exc).__name__}"
        marker = _marker(root, payload.get("session_id") or "")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"locked": reason}), encoding="utf-8", newline="\n")
        raise Refused(f"session locked: {reason}") from exc


def _write_marker(payload: dict[str, Any], root: Path, args: list[str]) -> str:
    if not args or not _ENTRY.fullmatch(args[0]):
        raise Refused("usage: /observe <entry> [path ...], entry as a catalogue ID such as OP-01")
    entry = args[0]
    if CATALOGUE not in ground(root):
        raise Refused(f"{CATALOGUE} is not active ground in {REGISTER}: no entry can be designed until it is")
    if entry not in entries(root):
        raise Refused(f"{entry}: no entry of that ID in {CATALOGUE}")
    own_input = INPUT.format(entry=entry)
    reopened = set(ground(root, "reopened"))
    named = []
    for path in args[1:]:
        rel = Path(_real(root, path)).relative_to(os.path.realpath(root)).as_posix() if _inside(root, path) else None
        if rel is None or not Path(root, rel).is_file():
            raise Refused(f"{path}: not a file in this repository")
        if _NEVER_GROUND.match(rel):
            raise Refused(f"{rel}: 0.33 code, tests and specs 001 to 050 are never ground (RFC-0024 § R1)")
        if rel.startswith(INPUTS) and rel != own_input:
            raise Refused(f"{rel}: another entry's input is never admitted to {entry}'s session (RFC-0027 P1)")
        if rel in reopened:
            raise Refused(f"{rel}: reopened in {REGISTER}; it is off the allowlist until its flow re-admits it")
        named.append(rel)
    doc = RECORD.format(entry=entry)
    state = {"entry": entry, "record": doc, "input": INPUT.format(entry=entry), "named": named}
    marker = _marker(root, payload.get("session_id") or "")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(state), encoding="utf-8", newline="\n")
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
    if "released" in state:
        _check_released(state, tool, args, root, cwd)
        return
    if tool in _NEUTRAL:
        return
    if "entry" not in state:  # locked by rearm, or written by the hook's operation-slug version
        reason = state.get("locked") or "its marker predates catalogue entries"
        raise Refused(
            f"{tool}: this /observe session cannot be re-armed ({reason}). /clear, then start afresh. {_WAY_OUT}"
        )
    if tool == "Skill" and args.get("skill") == "observe":
        return
    if tool in ("WebSearch", "WebFetch"):
        target = args.get("query") or args.get("url") or ""
        if _OWN_SURFACE.search(target):
            raise Refused(
                f"{tool}: remote-store's own code and docs describe version 0.33, never ground (S1). {_WAY_OUT}"
            )
        return
    doc = _real(root, state["record"])
    if tool in ("Write", "Edit"):
        if _real(root, args.get("file_path") or "", cwd) != doc:
            raise Refused(f"{tool}: this session writes only {state['record']} (S4). {_WAY_OUT}")
        return
    if tool in ("Read", "Grep"):
        target = args.get("file_path") if tool == "Read" else args.get("path")
        own = (*METHOD_FILES, *ground(root), state["input"], *state["named"])
        allowed = {_real(root, p) for p in own} | {doc}
        real = _real(root, target or "", cwd)
        # A symlinked allowlist file is judged by what it points at.
        rel = os.path.relpath(real, os.path.realpath(root)).replace(os.sep, "/")
        if not target or real not in allowed or _NEVER_GROUND.match(rel) or rel.startswith("../"):
            raise Refused(
                f"{tool}: {target or '(no path)'} is outside the ground. Allowed: the files {REGISTER} "
                f"lists as active, the method files {', '.join(METHOD_FILES)}, the entry's input "
                f"{state['input']}, the record {state['record']} and the paths named at /observe (S3). "
                f"{_WAY_OUT}"
            )
        return
    raise Refused(f"{tool}: not available in an /observe session (S2). Read allowed files with Read. {_WAY_OUT}")


def _check_released(state: dict[str, Any], tool: str, args: dict[str, Any], root: Path, cwd: str | None) -> None:
    """Raise Refused when a released session's call writes its record, or any record when it names none."""
    # A locked or unreadable marker names no record, so every record is closed to it.
    record = state.get("record") or RECORDS
    if tool in _WRITERS:
        target = _real(root, args.get(_WRITERS[tool]) or "", cwd)
        guarded = _real(root, record)
        writes = target == guarded or (record == RECORDS and target.startswith(guarded + os.sep))
    else:
        writes = tool == "Bash" and record.rstrip("/") in str(args.get("command") or "")
    if writes:
        raise Refused(
            f"{tool}: this session is released; {record} is written only by a fresh /observe session and "
            "committed after /clear, never named here (S4)"
        )


def disarm(payload: dict[str, Any], root: Path) -> None:
    """Release the session's marker when it is cleared: any other end may be resumed armed."""
    if payload.get("reason") != "clear":
        return
    with contextlib.suppress(Refused, OSError, ValueError):
        _release(root, payload.get("session_id") or "", "clear")


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
        hint = f" {_WAY_OUT}" if mode == "check" else ""
        print(f"Blocked (/observe ground hook failed): {type(exc).__name__}: {exc}.{hint}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
