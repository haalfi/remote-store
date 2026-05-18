#!/bin/bash
# PostToolUse: brake when sdd/BACKLOG.md edit introduces a [~] status.
# Rule: sdd/BACKLOG.md § Completing work — shipping work means [x] plus
# migrate to BACKLOG-DONE.md in the same commit; [~] is for genuinely
# in-flight work spanning multiple PRs or sessions.

INPUT=$(cat)
OLD_IDS=$(echo "$INPUT" | jq -r '.tool_input.old_string // empty' | grep -oE '\[~\] \*\*(BK|BUG|ID|AF|BL)-[0-9]+' | sort -u)
NEW_IDS=$(echo "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // empty' | grep -oE '\[~\] \*\*(BK|BUG|ID|AF|BL)-[0-9]+' | sort -u)

ADDED=$(comm -23 <(echo "$NEW_IDS") <(echo "$OLD_IDS"))
[ -z "$ADDED" ] && exit 0

cat >&2 <<EOF
STOP AND RECONSIDER: this edit sets the following backlog item(s) to [~] (in progress):
$ADDED

Rule (sdd/BACKLOG.md § Completing work): if this PR ships the whole fix, the
correct state is [x] plus migrate to BACKLOG-DONE.md in the same commit.
[~] is only for work genuinely in-flight across multiple PRs or sessions.
Confirm which case this is before continuing.
EOF

exit 2
