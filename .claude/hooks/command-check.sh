#!/bin/bash
# Sourced by the `if:`-gated PreToolUse Bash hooks. Claude Code's `if:` is
# best-effort: when it cannot tell which commands a Bash input runs (measured:
# `${HOME}`, `$PWD`, `$HTTPS_PROXY`), it runs every such hook regardless of its
# pattern (https://code.claude.com/docs/en/hooks). So each hook re-checks the
# command itself before acting.
#
# command_mentions WORD...: true unless the payload's `tool_input.command`
# provably cannot run WORDs, which is when they do not all appear in it as
# whole words, in order (`git commit` matches `git -C "$PWD" commit`). The
# check only clears commands that never name the target; a mention it cannot
# tell from a run (an argument, a path, `then`/`timeout`/`git -c` before it)
# keeps the gate acting as it did before this check existed (BK-459 review).
# Also true when the payload holds no readable command (no jq, not JSON).
# Reads the payload from HOOK_INPUT; callers set it once with HOOK_INPUT=$(cat).
command_mentions() {
  local cmd re word sep='[^[:alnum:]_.-]'
  command -v jq >/dev/null 2>&1 || return 0
  cmd=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || return 0
  [ -n "$cmd" ] || return 0
  re="(^|$sep)$1"
  shift
  for word in "$@"; do re="$re($sep.*)?$sep$word"; done
  printf '%s' "$cmd" | tr '\n' ' ' | grep -qE "$re($sep|\$)"
}
