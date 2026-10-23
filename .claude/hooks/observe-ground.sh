#!/bin/bash
# Confine an /observe design session to its ground (RFC-0024 D4, D11).
#
# Usage: observe-ground.sh arm|check|disarm, wired to UserPromptSubmit,
# PreToolUse and SessionEnd in .claude/settings.json. The work is in
# scripts/observe_ground.py; its docstring holds the rules.
#
# `check` runs on every tool call of every session, so it returns at once when
# no session in this checkout is armed (no tmp/observe/*.json). Once one is,
# the guard fails closed: a missing interpreter blocks the call instead of
# letting an armed session read past its ground. `disarm` never blocks.
#
# Paths resolve from this file, as in record-decision.sh. `python` before
# `python3` for the Windows Store stub reason that file gives.

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/scripts/observe_ground.py"
MODE="$1"
PY=$(command -v python || command -v python3)

if [ "$MODE" = "check" ]; then
  compgen -G "$ROOT/tmp/observe/*.json" >/dev/null || exit 0
fi

if [ -z "$PY" ] || [ ! -f "$SCRIPT" ]; then
  [ "$MODE" = "disarm" ] && exit 0
  if [ "$MODE" = "arm" ]; then
    # Unarmed sessions must not break: block only an /observe prompt.
    PAYLOAD=$(cat)
    case "$PAYLOAD" in *'"prompt":"/observe'* | *'"prompt": "/observe'*) ;; *) exit 0 ;; esac
  fi
  echo "Blocked (/observe ground hook): no python or $SCRIPT; the ground cannot be enforced." >&2
  exit 2
fi

"$PY" "$SCRIPT" "$MODE"
STATUS=$?
[ "$MODE" = "disarm" ] && exit 0
exit $STATUS
