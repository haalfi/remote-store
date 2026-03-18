#!/bin/bash
# Block compound commands (&&, ||, ;, heredoc) in Bash tool calls.
# They can't be auto-approved by permission patterns.
# Exit 2 = block the tool call and show the error to Claude.

COMMAND=$(jq -r '.tool_input.command' < /dev/stdin)

# Collapse to a single line so multi-line quoted strings are handled,
# then strip single-quoted and double-quoted strings before checking.
# Limitation: backslash-escaped quotes inside strings (e.g. "hello\"world")
# are not handled — the sed patterns treat \" as a quote boundary, which can
# cause false positives. This is safe (Claude restructures the command) but
# may confuse debugging if a legitimate command is unexpectedly blocked.
STRIPPED=$(echo "$COMMAND" | tr '\n' ' ' | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g')

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
