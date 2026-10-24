#!/bin/bash
# PreToolUse gate: block commits on master + run lint (skipped for docs-only).
# Also stages the decision log, so it travels with the work it explains
# (RFC-0018 D2), after promoting the session's held records into it.
# Wired without `if:`, whose prefix match misses `git -C <path> commit`
# (BK-486), so it sees every Bash call. It acts once per tree a `git commit`
# in the command runs in (scripts/git_target.py: `cd`, `-C`, git in command
# position only), so a worktree commit is judged on its own branch and index.
# Without python it falls back to command-check.sh and the cwd.
HOOK_INPUT=$(cat)
HERE=$(dirname "$0")
# `python` before `python3`, as in record-decision.sh.
PY=$(command -v python || command -v python3)
if [ -z "$PY" ] || ! TREES=$(printf '%s' "$HOOK_INPUT" | "$PY" "$HERE/../../scripts/git_target.py" commit 2>/dev/null); then
  source "$HERE/command-check.sh"
  command_mentions git commit || exit 0
  TREES=$PWD
fi
[ -n "$TREES" ] || exit 0
RECORDER="$HERE/../../scripts/record_decision.py"

while IFS= read -r TREE; do
  # A tree that is no work tree (an unexpanded `$VAR`, a `$(...)`) is judged as
  # the cwd, as before BK-486: an empty branch must mean detached, not unknown.
  git -C "$TREE" rev-parse --is-inside-work-tree >/dev/null 2>&1 || TREE=$PWD
  BRANCH=$(git -C "$TREE" branch --show-current 2>/dev/null)
  if [ "$BRANCH" = "master" ] || [ "$BRANCH" = "main" ]; then
    echo "Blocked: never commit directly to $BRANCH. Create a feature branch first." >&2
    exit 2
  fi

  # Best-effort: a staging failure must not block the commit.
  TOP=$(git -C "$TREE" rev-parse --show-toplevel 2>/dev/null)
  # On a work branch, first move this session's held base-branch records into
  # its log (BK-486). Detached HEAD has no branch and promotes nothing.
  if [ -n "$TOP" ] && [ -n "$BRANCH" ] && [ -n "$PY" ] && [ -f "$RECORDER" ]; then
    printf '%s' "$HOOK_INPUT" | "$PY" "$RECORDER" --promote "$TOP" >/dev/null 2>&1
  fi
  if [ -n "$TOP" ] && [ -d "$TOP/sdd/decisions" ]; then
    # Held records never stage, even in a checkout whose .gitignore lacks the line.
    git -C "$TOP" add -- sdd/decisions ':(exclude)sdd/decisions/.pending' >/dev/null 2>&1
  fi

  # Skip lint when no code files are staged
  if [ -z "$TOP" ] || ! git -C "$TREE" diff --cached --name-only 2>/dev/null | grep -qE '^(src/|tests/|examples/)'; then
    continue
  fi

  OUTPUT=$(cd "$TOP" && hatch run lint 2>&1 </dev/null)
  if [ $? -ne 0 ]; then
    echo "Blocked: lint failed. Fix before committing:" >&2
    echo "$OUTPUT" >&2
    exit 2
  fi
done <<< "$TREES"
exit 0
