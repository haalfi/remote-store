#!/bin/bash
# Record an AskUserQuestion hook event in sdd/decisions/ (RFC-0018 D1).
#
# Wired to PreToolUse and PostToolUse with matcher AskUserQuestion (see
# .claude/settings.json). The work is in scripts/record_decision.py; this
# wrapper exists so the hook can never block the dialog it records: a missing
# or broken recorder makes CPython exit 2, and exit 2 from a PreToolUse hook
# blocks the tool. So every path below exits 0.
#
# The recorder is found relative to this file, not via $CLAUDE_PROJECT_DIR, so
# the log lands in the checkout this hook belongs to.
#
# `python` before `python3`: on Windows `python3` can resolve to the Microsoft
# Store stub, which prints an install hint and exits non-zero.

RECORDER="$(dirname "$0")/../../scripts/record_decision.py"
PY=$(command -v python || command -v python3)

if [ -n "$PY" ] && [ -f "$RECORDER" ]; then
  "$PY" "$RECORDER" >/dev/null
fi

exit 0
