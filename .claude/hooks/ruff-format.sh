#!/bin/bash
# PostToolUse: auto-format .py files after Edit/Write

FILE=$(jq -r '.tool_input.file_path // empty')
[[ "$FILE" != *.py ]] && exit 0

ruff format "$FILE" 2>/dev/null
# F401 stays unfixable here: an import is often added one edit before the code
# that uses it, and removing it in between leaves a NameError. `hatch run lint`
# runs `ruff check` without --fix, so an import that stays unused still fails it.
ruff check --fix --unfixable F401 "$FILE" 2>/dev/null
exit 0
