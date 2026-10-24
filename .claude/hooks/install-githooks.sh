#!/bin/bash
# SessionStart: point git at the agent gates in .githooks/ (BK-486). Git then
# runs them in whichever repository a commit or push lands in, which a Claude
# PreToolUse hook could only guess from the command line.
#
# The path is absolute, so a linked worktree on a branch without .githooks/
# still uses these. An existing core.hooksPath of another tool is left alone,
# and so is a checkout without .githooks/. Always exits 0: a session must start.
TOP=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -d "$TOP/.githooks" ] || exit 0
CURRENT=$(git config --get core.hooksPath)
if [ -z "$CURRENT" ] || [ "${CURRENT%/.githooks}" != "$CURRENT" ]; then
  git config core.hooksPath "$TOP/.githooks"
fi
exit 0
