#!/bin/bash
# Sourced by the `if:`-gated PreToolUse Bash hooks. Claude Code's `if:` is
# best-effort: when it cannot tell which commands a Bash input runs (measured:
# `${HOME}`, `$PWD`, `$HTTPS_PROXY`), it runs every such hook regardless of its
# pattern (https://code.claude.com/docs/en/hooks). So each hook re-checks the
# command itself before acting.
#
# command_runs <ERE>: true when the payload's `tool_input.command` runs <ERE> as
# a command, at the start of a line or after `;`, `&`, `|`, `(`, a backtick or
# `$(`, past any `VAR=value` prefixes. Also true when the payload holds no
# readable command (no jq, not JSON, not a Bash call): the gate then acts as it
# did before this check existed, so a parse failure never disarms it.
# Reads the payload from HOOK_INPUT; callers set it once with HOOK_INPUT=$(cat).
command_runs() {
  local cmd
  command -v jq >/dev/null 2>&1 || return 0
  cmd=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || return 0
  [ -n "$cmd" ] || return 0
  printf '%s\n' "$cmd" | grep -qE \
    "(^|[;&|(\`]|\\\$\()[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*($1)([[:space:]]|$)"
}
