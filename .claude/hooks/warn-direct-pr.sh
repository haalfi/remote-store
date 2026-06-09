#!/bin/bash
# PreToolUse (non-blocking advisory): nudge sessions toward the /pr skill when a
# PR is created directly — a bare `gh pr create` or a create_pull_request MCP
# call (local mcp__MCP_DOCKER__* or cloud mcp__github__*). The /pr skill runs
# the testing/docs/coverage/trace/freshness gates that a direct create skips.
#
# This hook MUST NOT block: the /pr skill itself creates PRs via these same
# tools, and a PreToolUse hook cannot tell the skill apart from a freelancing
# call — so a blocking hook would break the skill's own step 5 in both terminal
# and cloud (see .claude/skills/pr/SKILL.md, and the rejected blocking-hook
# rationale in PR history). It allows the call and surfaces a reminder via
# additionalContext (aimed at the model) and stderr (transcript). If you are
# already running /pr, ignore it.
REASON="Direct PR creation detected. If you are not already running the /pr skill, prefer it: /pr runs the testing, docs, coverage, trace, and freshness gates before opening the PR, instead of working around them. Proceeding with creation."
echo "$REASON" >&2
cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"$REASON","additionalContext":"$REASON"}}
EOF
exit 0
