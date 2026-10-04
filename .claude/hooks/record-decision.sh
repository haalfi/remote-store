#!/bin/bash
# Record an AskUserQuestion hook event in sdd/decisions/ (RFC-0018 D1).
#
# Wired to PreToolUse and PostToolUse with matcher AskUserQuestion (see
# .claude/settings.json). The work is in scripts/record_decision.py; this
# wrapper exists so the hook can never block the dialog it records: a missing
# or broken recorder makes CPython exit 2, and exit 2 from a PreToolUse hook
# blocks the tool. So every path below exits 0.
#
# The recorder is found relative to this file. settings.json runs this file as
# "$CLAUDE_PROJECT_DIR"/.claude/hooks/record-decision.sh, so in a session that
# is the project directory, and the log lands there (RFC-0018 D2 states the
# bound when work is committed in another checkout). Resolving from $0 rather
# than reading the variable is what lets the tests run this file from a copy.
#
# `python` before `python3`: on Windows `python3` can resolve to the Microsoft
# Store stub, which prints an install hint and exits non-zero.

RECORDER="$(dirname "$0")/../../scripts/record_decision.py"
PY=$(command -v python || command -v python3)

if [ -n "$PY" ] && [ -f "$RECORDER" ]; then
  "$PY" "$RECORDER" >/dev/null
fi

exit 0
