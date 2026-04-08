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

# Attempt typecheck; skip if hatch is unavailable (environmental issue, not code quality)
OUTPUT=$(hatch run typecheck 2>&1)
EXIT_CODE=$?
if [ $EXIT_CODE -eq 127 ] || echo "$OUTPUT" | grep -q "No module named\|not found"; then
  echo "Warning: typecheck unavailable (hatch/dependencies), proceeding anyway" >&2
  exit 0
fi
if [ $EXIT_CODE -ne 0 ]; then
  echo "Blocked: typecheck failed. Fix before pushing:" >&2
  echo "$OUTPUT" >&2
  exit 2
fi
