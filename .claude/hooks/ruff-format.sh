#!/bin/bash
# PostToolUse: auto-format .py files after Edit/Write

FILE=$(jq -r '.tool_input.file_path // empty')
[[ "$FILE" != *.py ]] && exit 0

ruff format "$FILE" 2>/dev/null
ruff check --fix "$FILE" 2>/dev/null
exit 0
