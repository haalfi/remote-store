#!/bin/bash
# Block compound commands (&&, ||, ;, heredoc) in Bash tool calls.
# They can't be auto-approved by permission patterns.
# Exit 2 = block the tool call and show the error to Claude.

COMMAND=$(jq -r '.tool_input.command' < /dev/stdin)

# Strip single-quoted and double-quoted strings before checking,
# so that operators inside quotes (e.g. python -c "import os; ...") are ignored.
STRIPPED=$(echo "$COMMAND" | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g')

# Check for compound operators in unquoted portions
if echo "$STRIPPED" | grep -qE '(&&|\|\||;)'; then
  echo "BLOCKED: Compound commands (&&, ||, ;) are not allowed. Split into separate Bash tool calls." >&2
  exit 2
fi

# Check for heredoc syntax
if echo "$STRIPPED" | grep -qE '<<-?\s*'\''?[A-Za-z_]'; then
  echo "BLOCKED: Heredoc substitution (<<EOF) is not allowed. Use the Write tool to create files." >&2
  exit 2
fi

exit 0
