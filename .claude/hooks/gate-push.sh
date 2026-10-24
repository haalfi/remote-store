#!/bin/bash
# PreToolUse gate: block pushes to master + run typecheck (skipped for docs-only)
# Wired without `if:`, whose prefix match misses `git -C <path> push` (BK-486),
# so it sees every Bash call. It acts once per tree a `git push` in the command
# runs in (scripts/git_target.py: `cd`, `-C`, git in command position only), so
# a worktree push is judged on its own branch. Without python it falls back to
# command-check.sh and the cwd.
HOOK_INPUT=$(cat)
HERE=$(dirname "$0")
PY=$(command -v python || command -v python3)
if [ -z "$PY" ] || ! TREES=$(printf '%s' "$HOOK_INPUT" | "$PY" "$HERE/../../scripts/git_target.py" push 2>/dev/null); then
  source "$HERE/command-check.sh"
  command_mentions git push || exit 0
  TREES=$PWD
fi
[ -n "$TREES" ] || exit 0

while IFS= read -r TREE; do
  BRANCH=$(git -C "$TREE" branch --show-current 2>/dev/null)
  if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "main" ]; then
    echo "Blocked: never push directly to master/main." >&2
    exit 2
  fi

  # Skip typecheck when no code files changed vs base
  if ! git -C "$TREE" diff origin/master...HEAD --name-only 2>/dev/null | grep -qE '^(src/|tests/|examples/)'; then
    continue
  fi

  TOP=$(git -C "$TREE" rev-parse --show-toplevel 2>/dev/null)
  [ -n "$TOP" ] || continue
  OUTPUT=$(cd "$TOP" && hatch run typecheck 2>&1 </dev/null)
  if [ $? -ne 0 ]; then
    echo "Blocked: typecheck failed. Fix before pushing:" >&2
    echo "$OUTPUT" >&2
    exit 2
  fi
done <<< "$TREES"
exit 0
