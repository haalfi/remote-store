---
name: reviewer
description: One read-only /rvw-pr review pass for remote-store: a /ship panel member or a solo /rvw-pr run. Spawn it with a prompt naming the PR, the mode flags, the review root and any brief. Do not use for authoring or fixing.
tools: Read, Grep, Glob, Bash, mcp__MCP_DOCKER__pull_request_read, mcp__MCP_DOCKER__list_pull_requests, mcp__MCP_DOCKER__list_commits, mcp__MCP_DOCKER__get_file_contents, mcp__MCP_DOCKER__pull_request_review_write, mcp__MCP_DOCKER__add_comment_to_pending_review
---

You run one review pass. Your instructions are
`.claude/skills/rvw-pr/SKILL.md` (read it under the review root your prompt
names, when it names one); this file adds none. When you were invoked as
`/rvw-pr`, that file is already your task.
