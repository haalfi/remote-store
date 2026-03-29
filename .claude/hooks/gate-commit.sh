#!/bin/bash
# PreToolUse gate: block commits on master + run lint (skipped for docs-only)

BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "main" ]; then
  echo "Blocked: never commit directly to $BRANCH. Create a feature branch first." >&2
  exit 2
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
