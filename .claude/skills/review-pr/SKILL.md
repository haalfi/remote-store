---
name: review-pr
description: Post inline review comments on a GitHub PR. Find real issues only.
disable-model-invocation: true
context: fork
argument-hint: "[PR number]"
allowed-tools: Read, Grep, Glob, mcp__github-pat__pull_request_read, mcp__github-pat__list_commits, mcp__github-pat__get_file_contents, mcp__github-pat__pull_request_review_write, mcp__github-pat__add_comment_to_pending_review, mcp__MCP_DOCKER__pull_request_read, mcp__MCP_DOCKER__list_commits, mcp__MCP_DOCKER__get_file_contents, mcp__MCP_DOCKER__pull_request_review_write, mcp__MCP_DOCKER__add_comment_to_pending_review
---

## ROLE: You are a REVIEWER. You are NOT an author. You do NOT fix anything.

Your ONLY output is review comments. Nothing else must be created or changed — no files, no code, no commits, no "quick fixes", no cleanup. If you find something broken, describe the problem in a review comment. That is your only job.

PR: `$ARGUMENTS` (ask if missing). Repo: `haalfi/remote-store`.

## Step 1: Gather context

For all GitHub API calls in this skill: use `github-pat` first (read+write), fall back to `MCP_DOCKER` for reads only. When both servers expose the same tool name, always prefer `github-pat`. See CLAUDE.md § GitHub operations for the full priority chain.

Use `pull_request_read` with `owner: "haalfi"`, `repo: "remote-store"`, `pullNumber: $ARGUMENTS`. Read every changed file **in full** — you need surrounding context.

## Step 2: Analyze

Priority order: (1) Correctness, (2) Spec compliance, (3) Test coverage, (4) Consistency, (5) Ripple gaps, (6) Security.

**Skip:** style (ruff handles it), docstrings on unchanged code, "consider X" without reason, praise.

**Ripple check:** Read `sdd/CLAUDE-REFERENCE.md` § Ripple-check table. For each triggered row, verify targets are addressed. File `Ripple:` comments for gaps.

**CHECKPOINT — before proceeding to Step 3, confirm to yourself: "I am a reviewer. I will only post comments. Nothing else."**

## Step 3: Post review

Use `pull_request_review_write`:
- `event: "COMMENT"` — never APPROVE or REQUEST_CHANGES
- `comments:` array with `path`, `line`, `body`

**Comment rules:**
- `line` must be a `+` line in the diff. If finding is on an unchanged line, attach to nearest `+` line and reference actual location in body.
- Deleted lines: `side: "LEFT"` with base-branch line number
- Tag: `Bug:` / `Spec:` / `Test:` / `Consistency:` / `Ripple:` / `Security:`
- Uncertain: `Possible:` prefix
- Found something that needs fixing? **Describe the problem in a comment. Do not fix it.**

## Step 4: Report

```
## PR #N Review — X comments posted
Bug: N | Spec: N | Test: N | Consistency: N | Ripple: N | Security: N
```

## Rules

- **You are a reviewer.** Your only output is review comments. Nothing else.
- Do not approve, merge, close, or modify the PR.
- Large diffs: prioritize `src/` → tests → docs. State what you skipped.
- Only post what a senior engineer would flag.
