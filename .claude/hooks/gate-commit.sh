#!/bin/bash
# PreToolUse gate: block commits on master + run lint (skipped for docs-only).
# Also stages the decision log, so it travels with the work it explains
# (RFC-0018 D2).

BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "main" ]; then
  echo "Blocked: never commit directly to $BRANCH. Create a feature branch first." >&2
  exit 2
fi

# Best-effort: a staging failure must not block the commit.
TOP=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -n "$TOP" ] && [ -d "$TOP/sdd/decisions" ]; then
  git -C "$TOP" add -- sdd/decisions >/dev/null 2>&1
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
