#!/bin/bash
# Block compound commands (&&, ||, ;) in Bash tool calls.
# They can't be auto-approved by permission patterns.
# Exit 2 = block the tool call and show the error to Claude.

COMMAND=$(jq -r '.tool_input.command' < /dev/stdin)

if echo "$COMMAND" | grep -qE '(&&|\|\||;)'; then
  echo "BLOCKED: Compound commands (&&, ||, ;) are not allowed. Split into separate Bash tool calls." >&2
  exit 2
fi

exit 0
