#!/bin/bash
# Confine an /observe design session to its ground (RFC-0024 D4, D11).
#
# Usage: observe-ground.sh arm|rearm|check|disarm, wired to UserPromptSubmit,
# SessionStart, PreToolUse and SessionEnd in .claude/settings.json. The work is
# in scripts/observe_ground.py; its docstring holds the rules.
#
# `check` runs on every tool call of every session, so it returns at once unless
# this session's own marker (tmp/observe/<session_id>.json, armed, locked or
# released) exists. Only then
# does it need python, and it fails closed: a missing interpreter or script
# blocks the armed session's call instead of letting it read past its ground.
# Other sessions are never blocked; nor is `disarm`, nor `arm` or `rearm` for a
# session that is not an /observe one.
#
# Builtins only before python runs, so the fail-closed branch holds with
# nothing on PATH but bash. `python` before `python3` for the Windows Store stub
# reason record-decision.sh gives.

HOOK_DIR="${BASH_SOURCE[0]%/*}"
ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
SCRIPT="$ROOT/scripts/observe_ground.py"
MODE="$1"
IFS= read -r -d '' PAYLOAD
SID=""
if [[ $PAYLOAD =~ \"session_id\"[[:space:]]*:[[:space:]]*\"([A-Za-z0-9_-]+)\" ]]; then
  SID="${BASH_REMATCH[1]}"
fi

if [ "$MODE" = "check" ] && { [ -z "$SID" ] || [ ! -f "$ROOT/tmp/observe/$SID.json" ]; }; then
  exit 0
fi

PY=$(command -v python || command -v python3)
if [ -z "$PY" ] || [ ! -f "$SCRIPT" ]; then
  case "$MODE" in
    check) ;;
    arm) [[ $PAYLOAD =~ \"prompt\"[[:space:]]*:[[:space:]]*\"[[:space:]]*/observe ]] || exit 0 ;;
    *) exit 0 ;;
  esac
  echo "Blocked (/observe ground hook): no python or $SCRIPT; the ground cannot be enforced." >&2
  exit 2
fi

printf '%s' "$PAYLOAD" | "$PY" "$SCRIPT" "$MODE"
STATUS=$?
[ "$MODE" = "disarm" ] && exit 0
exit $STATUS
