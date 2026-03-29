#!/bin/bash
# PreToolUse gate: block pushes to master + run typecheck (skipped for docs-only)

BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "main" ]; then
  echo "Blocked: never push directly to master/main." >&2
  exit 2
fi

# Skip typecheck when no code files changed vs base
if ! git diff origin/master...HEAD --name-only 2>/dev/null | grep -qE '^(src/|tests/|examples/)'; then
  exit 0
fi

OUTPUT=$(hatch run typecheck 2>&1)
if [ $? -ne 0 ]; then
  echo "Blocked: typecheck failed. Fix before pushing:" >&2
  echo "$OUTPUT" >&2
  exit 2
fi
