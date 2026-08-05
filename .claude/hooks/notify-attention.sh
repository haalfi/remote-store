#!/bin/bash
# Alert the user that Claude Code is waiting on them.
#
# Wired to two events (see .claude/settings.json):
#   PreToolUse(AskUserQuestion) — fires exactly when a blocking dialog opens.
#   Notification(idle_prompt)   — backstop for a turn that ended without one.
#
# $1 is the fallback label used when the event carries no question headers.
# Never blocks: every path exits 0. A missing notification backend is not a
# reason to stall the session, so all backends are best-effort and silent.

INPUT=$(cat)
LABEL="${1:-input needed}"

# PreToolUse(AskUserQuestion) carries the question headers; Notification does
# not, and jq yields "null"/empty there. Either way fall back to $1.
HEADERS=$(printf '%s' "$INPUT" | jq -r '[.tool_input.questions[]?.header] | join(", ")' 2>/dev/null)
case "$HEADERS" in
  ""|null) HEADERS="$LABEL" ;;
esac

# Strip characters that would break the osascript string literal below.
HEADERS=$(printf '%s' "$HEADERS" | tr -d '"\\')
MSG="Waiting on you: $HEADERS"

# Set CLAUDE_NOTIFY_DEBUG=1 to see the composed message instead of guessing
# which backend fired. Used by tmp/test-notify-hook.sh.
if [ -n "$CLAUDE_NOTIFY_DEBUG" ]; then
  printf 'notify: %s\n' "$MSG"
fi

# Terminal bell first. It needs no daemon, survives SSH, and is the only
# channel that works when Claude Code runs in a container or headless shell.
# Braces so the redirect covers the shell's own "no such device" error too:
# a bare `printf ... >/dev/tty 2>/dev/null` still leaks it into the transcript
# when there is no controlling terminal, which is the container/CI case.
{ printf '\a' >/dev/tty; } 2>/dev/null

# Desktop notification, first available backend wins.
if command -v notify-send >/dev/null 2>&1; then
  notify-send "Claude Code" "$MSG" >/dev/null 2>&1
elif command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"$MSG\" with title \"Claude Code\"" >/dev/null 2>&1
elif command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -Command "[System.Console]::Beep(880, 300)" >/dev/null 2>&1
fi

exit 0
