#!/bin/bash
# SessionStart: point git at the agent gates in .githooks/ (BK-486). Git then
# runs them in whichever repository a commit or push lands in, which a Claude
# PreToolUse hook could only guess from the command line.
#
# core.hooksPath lives in the config every linked worktree shares, so it names
# the main worktree's .githooks/ (beside the common git dir), never a linked
# worktree's: one that is later removed would leave git running no hooks at
# all. An existing core.hooksPath of another tool is left alone, and so is a
# main worktree without .githooks/. Always exits 0: a session must start.
COMMON=$(git rev-parse --git-common-dir 2>/dev/null) || exit 0
MAIN=$(cd "$COMMON/.." 2>/dev/null && pwd) || exit 0
[ -d "$MAIN/.githooks" ] || exit 0
CURRENT=$(git config --get core.hooksPath)
if [ -z "$CURRENT" ] || [ "${CURRENT%/.githooks}" != "$CURRENT" ]; then
  git config core.hooksPath "$MAIN/.githooks"
fi
exit 0
