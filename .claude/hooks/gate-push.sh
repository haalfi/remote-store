#!/bin/bash
# PreToolUse gate: block pushes to master + run typecheck

BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "main" ]; then
  echo "Blocked: never push directly to master/main." >&2
  exit 2
fi

OUTPUT=$(hatch run typecheck 2>&1)
if [ $? -ne 0 ]; then
  echo "Blocked: typecheck failed. Fix before pushing:" >&2
  echo "$OUTPUT" >&2
  exit 2
fi
