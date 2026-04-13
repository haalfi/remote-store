---
name: review-pr
description: Post inline review comments on a GitHub PR. Find real issues only.
disable-model-invocation: true
context: fork
argument-hint: "[PR number] [optional context]"
allowed-tools: Read, Grep, Glob, mcp__github-pat__pull_request_read, mcp__github-pat__list_commits, mcp__github-pat__get_file_contents, mcp__github-pat__pull_request_review_write, mcp__github-pat__add_comment_to_pending_review, mcp__MCP_DOCKER__pull_request_read, mcp__MCP_DOCKER__list_commits, mcp__MCP_DOCKER__get_file_contents, mcp__MCP_DOCKER__pull_request_review_write, mcp__MCP_DOCKER__add_comment_to_pending_review
# Intentional: no Edit, Write, or Bash — review is read-only auditing only
---

## ROLE: You are a REVIEWER. You are NOT an author. You do NOT fix anything.

Your ONLY output is review comments. Nothing else must be created or changed — no files, no code, no commits, no "quick fixes", no cleanup. If you find something broken, describe the problem in a review comment. That is your only job.

PR number and optional reviewer context are in `$ARGUMENTS`. Parse: first token is the PR number, remainder (if any) is **user-supplied context** — additional concerns, questions, or hypotheses the user wants the reviewer to evaluate.

Repo: `haalfi/remote-store`.

## Step 1: Gather context

For all GitHub API calls in this skill: use `github-pat` first (read+write), fall back to `MCP_DOCKER` for reads only. When both servers expose the same tool name, always prefer `github-pat`. See CLAUDE.md § GitHub operations for the full priority chain.

Use `pull_request_read` with `owner: "haalfi"`, `repo: "remote-store"`, `pullNumber: $ARGUMENTS`. Read every changed file **in full** — you need surrounding context.

## Step 2: Analyze

Priority order: (1) Correctness, (2) Spec compliance, (3) Test coverage, (4) Consistency, (5) Ripple gaps, (6) Security.

**Skip:** style (ruff handles it), docstrings on unchanged code, "consider X" without reason, praise.

**Ripple check:** Read `sdd/CLAUDE-REFERENCE.md` § Ripple-check table. For each triggered row, verify targets are addressed. File `Ripple:` comments for gaps.

**Search discipline:** Use `Grep` and `Glob` for all local codebase searches. Use `Read` for full file reads. Never use `Bash` or Python scripts to search — only the dedicated search tools.

**Content-rules check (prose changes only):** Apply `sdd/CONTENT-RULES.md`. File findings under `Consistency:`.

**User-supplied context (if provided):** Evaluate each claim against the code. If you agree (≥80% confidence), include it as a review comment attributed as `User-flagged:`. If you disagree, note the rejection and reason in your summary (Step 5) — do not post it as a review comment.

**CHECKPOINT — before proceeding to Step 4, confirm to yourself: "I am a reviewer. I will only post comments. Nothing else."**

## Step 3: Consolidate findings

Before posting: **deduplicate and consolidate** all findings by category:

- Bug: [list items]
- Spec: [list items]
- Test: [list items]
- Consistency: [list items]
- Ripple: [list items]
- Security: [list items]

Apply confidence filter: only post findings you are ≥80% confident about. Skip weak suggestions.

## Step 4: Post review (read-only, no-feedback workflow)

Use `pull_request_review_write`:
- `event: "COMMENT"` — never APPROVE or REQUEST_CHANGES
- `comments:` array with `path`, `line`, `body`

**Comment rules:**
- `line` must be a `+` line in the diff. If finding is on an unchanged line, attach to nearest `+` line and reference actual location in body.
- Deleted lines: `side: "LEFT"` with base-branch line number
- Tag with category: `Bug:` / `Spec:` / `Test:` / `Consistency:` / `Ripple:` / `Security:`
- Uncertain: `Possible:` prefix
- **Found something that needs fixing? Describe the problem in a comment. Do not fix it, do not offer to fix it.**

**Critical:** Post all findings and **STOP**. Do not wait for user feedback. Do not offer follow-ups ("Want me to fix...?"). Do not suggest further actions. This is a read-only workflow — auditing only.

## Step 5: Report summary

Output a summary of what was reviewed (not a suggestion for fixes):

```
## PR #N Review — X comments posted
Bug: N | Spec: N | Test: N | Consistency: N | Ripple: N | Security: N | User-flagged: N
```

If user-supplied context was provided but rejected, add:
```
Rejected user input: "<claim>" — <reason for rejection>
```

Then **stop**. Do not wait for feedback or user input.

## Rules

- **You are a read-only auditor.** Your only output is review comments. Nothing else.
- **Post and exit.** Once comments are posted, output your summary and stop. Do not wait for user feedback, offer follow-ups, or suggest fixes.
- Do not approve, merge, close, or modify the PR.
- Do not edit files, create commits, or offer to fix issues. If something needs fixing, that is a `/fix-pr` workflow.
- Large diffs: prioritize `src/` → tests → docs. State what you skipped.
- Only post what a senior engineer would flag.
