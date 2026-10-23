#!/bin/bash
# PreToolUse gate: block commits on master + run lint (skipped for docs-only).
# Also stages the decision log, so it travels with the work it explains
# (RFC-0018 D2), after promoting the session's held records into it.
# Wired without `if:`, whose prefix match misses `git -C <path> commit`, so it
# runs on every Bash call and filters itself (command-check.sh).
HOOK_INPUT=$(cat)
source "$(dirname "$0")/command-check.sh"
command_mentions git commit || exit 0

BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "main" ]; then
  echo "Blocked: never commit directly to $BRANCH. Create a feature branch first." >&2
  exit 2
fi

# Best-effort: a staging failure must not block the commit.
TOP=$(git rev-parse --show-toplevel 2>/dev/null)
# On a work branch, first move this session's held base-branch records into its
# log (BK-486). Detached HEAD has no branch and promotes nothing. The recorder
# is found relative to this file, as in record-decision.sh, and `python` comes
# before `python3` for the same reason.
RECORDER="$(dirname "$0")/../../scripts/record_decision.py"
PY=$(command -v python || command -v python3)
if [ -n "$TOP" ] && [ -n "$BRANCH" ] && [ -n "$PY" ] && [ -f "$RECORDER" ]; then
  printf '%s' "$HOOK_INPUT" | "$PY" "$RECORDER" --promote "$TOP" >/dev/null 2>&1
fi
if [ -n "$TOP" ] && [ -d "$TOP/sdd/decisions" ]; then
  # Held records never stage, even in a checkout whose .gitignore lacks the line.
  git -C "$TOP" add -- sdd/decisions ':(exclude)sdd/decisions/.pending' >/dev/null 2>&1
fi

# Skip lint when no code files are staged
if ! git diff --cached --name-only | grep -qE '^(src/|tests/|examples/)'; then
  exit 0
fi

OUTPUT=$(hatch run lint 2>&1)
if [ $? -ne 0 ]; then
  echo "Blocked: lint failed. Fix before committing:" >&2
  echo "$OUTPUT" >&2
  exit 2
fi
