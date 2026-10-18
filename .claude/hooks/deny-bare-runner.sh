#!/bin/bash
# PreToolUse: block bare test/lint/type runners — use hatch run instead.
# $1 is "<runner> → <hint>"; the runner is re-checked against the command,
# because `if:` also fires on commands it cannot parse (command-check.sh).
HOOK_INPUT=$(cat)
source "$(dirname "$0")/command-check.sh"
command_mentions "${1%% →*}" || exit 0
echo "Blocked: $1" >&2
exit 2
