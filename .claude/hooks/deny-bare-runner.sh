#!/bin/bash
# PreToolUse: block bare test/lint/type runners — use hatch run instead
echo "Blocked: $1" >&2
exit 2
