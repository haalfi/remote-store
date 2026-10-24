#!/bin/bash
# PreToolUse: deny `--no-verify` on a Bash command that runs git. It skips the
# git hooks in .githooks/, which hold the master block, lint, typecheck and the
# decision-log promotion (BK-486). Quoted spans are stripped first, so a commit
# message that names the flag passes, and a command without a bare `git` word
# (`dafny translate --no-verify`) is not git's flag. Bounds: `git commit -n` and `-c core.hooksPath=...`
# also skip the hooks and are not caught; this guards a slip, not an attacker.
# Without jq the command cannot be read, and the hook allows it.
command -v jq >/dev/null 2>&1 || exit 0
CMD=$(jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
UNQUOTED=$(printf '%s' "$CMD" | tr '\n' ' ' | sed -E "s/'[^']*'//g; s/\"([^\"\\\\]|\\\\.)*\"//g")
if printf '%s' "$UNQUOTED" | grep -qE '(^|[^[:alnum:]_./-])git([[:space:]]|$)' &&
  printf '%s' "$UNQUOTED" | grep -qE '(^|[[:space:]])--no-verify([[:space:]=]|$)'; then
  echo "Blocked: --no-verify skips the git hooks in .githooks/ (master block, lint, decision log). Fix what the hook reports instead." >&2
  exit 2
fi
exit 0
