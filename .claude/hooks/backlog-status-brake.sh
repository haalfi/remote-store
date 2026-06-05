#!/bin/bash
# PostToolUse: brake when sdd/BACKLOG.md edit introduces a [~] status.
# Rule: sdd/BACKLOG.md § Completing work — shipping work means [x] plus
# migrate to BACKLOG-DONE.md in the same commit; [~] is for genuinely
# in-flight work spanning multiple PRs or sessions.
#
# Scope: Edit only. Write would false-positive (no old_string to diff
# against, so every preserved [~] looks newly added); MultiEdit is not
# matched (consistent with sibling Edit|Write hooks here).

INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')

# Filter to sdd/BACKLOG.md only — the matcher uses a loose glob (*BACKLOG.md)
# for cross-platform safety (Claude Code may pass absolute paths with either
# slash style, e.g. C:\project\sdd\BACKLOG.md on Windows), so do the precise
# path filter here. Excludes legacy/sam-services-snapshot/.../BACKLOG.md.
case "$FILE" in
  *sdd/BACKLOG.md|*sdd\\BACKLOG.md|sdd/BACKLOG.md|sdd\\BACKLOG.md) ;;
  *) exit 0 ;;
esac

OLD_IDS=$(printf '%s' "$INPUT" | jq -r '.tool_input.old_string // empty' | grep -oE '\[~\] \*\*[A-Z]{2,}-[0-9]+' | sort -u)
NEW_IDS=$(printf '%s' "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // empty' | grep -oE '\[~\] \*\*[A-Z]{2,}-[0-9]+' | sort -u)

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
