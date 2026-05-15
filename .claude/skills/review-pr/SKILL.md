---
name: review-pr
description: Post inline review comments on a GitHub PR. Find real issues only.
disable-model-invocation: true
context: fork
argument-hint: "[PR number] [optional context]"
allowed-tools: Read, Grep, Glob, mcp__MCP_DOCKER__pull_request_read, mcp__MCP_DOCKER__list_pull_requests, mcp__MCP_DOCKER__list_commits, mcp__MCP_DOCKER__get_file_contents, mcp__MCP_DOCKER__pull_request_review_write, mcp__MCP_DOCKER__add_comment_to_pending_review
# Intentional: no Edit, Write, or Bash — review is read-only auditing only
---

## ROLE: You are a REVIEWER. You are NOT an author. You do NOT fix anything.

**IMPORTANT — no local filesystem scouting.** Do NOT use Bash. Do NOT attempt to read or locate memory files, home directories, or project paths. The review context is fully self-contained: GitHub API for the PR, and the local repo files (Read/Grep/Glob only). Memory from the parent session is available in context — do not reload it.

Your only valuable output is review insights. The only artifact you create is comments on the PR. Findings go in a comment — bugs, gaps, deferrals, follow-ups. Anything else is out of scope for a reviewer.

PR number and optional reviewer context are in `$ARGUMENTS`. Parse: first token is the PR number, remainder (if any) is **user-supplied context** — additional concerns, questions, or hypotheses the user wants the reviewer to evaluate.

**No PR number provided?** Call `list_pull_requests` (`owner: "haalfi"`, `repo: "remote-store"`, `state: "OPEN"`) and ask the user which PR to review. Do not auto-pick.

Repo: `haalfi/remote-store`.

## Step 0: Verify PR is open

If `$ARGUMENTS` is empty, the no-args fallback above must have resolved a
PR number first; use that resolved value below. Do not call the API with
an empty `pullNumber`.

Call `pull_request_read` with `method: "get"`, `owner: "haalfi"`, `repo: "remote-store"`, `pullNumber: <resolved PR number>`. If `state` is `CLOSED` or the PR is merged, stop and ask the user — do not review stale or typo'd PR numbers.

## Step 1: Gather context

For all GitHub API calls in this skill, use the GitHub MCP server tools listed in `allowed-tools`.

Use `pull_request_read` with `owner: "haalfi"`, `repo: "remote-store"`, `pullNumber: $ARGUMENTS`. Read every changed file **in full** — you need surrounding context.

## Step 2: Analyze

Priority order: (1) Correctness, (2) Spec compliance, (3) Test coverage, (4) Consistency, (5) Ripple gaps, (6) Performance, (7) Security.

**Performance** for this library: flag streaming/buffering regressions, redundant round-trips, sync-in-async, missing range reads. Qualitative only — numeric claims belong in benchmarks, not review comments.

**Skip:** style (ruff handles it), docstrings on unchanged code, "consider X" without reason, praise.

**Ripple check:** Read `sdd/CLAUDE-REFERENCE.md` § Ripple-check table > Detailed checklist. For each triggered row, verify targets are addressed. File `Ripple:` comments for gaps.

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
- Perf: [list items]
- Security: [list items]

Apply confidence filter: only post findings you are ≥80% confident about. Skip weak suggestions.

## Step 4: Post review (read-only, no-feedback workflow)

**Use the pending-review flow — three steps, in order.** The GitHub MCP server silently drops inline comments if you pass them as a `comments:` array on a single `submit`/`create` call. Always:

1. **Create a pending review.** `pull_request_review_write` with `method: "create"` and **no `event` parameter** — omitting `event` is what makes the review pending (the `event` enum is only `APPROVE` / `REQUEST_CHANGES` / `COMMENT`; passing any value here submits immediately). No review ID bookkeeping is needed — subsequent calls attach to the requester's latest pending review automatically.
2. **Attach each inline comment** with `add_comment_to_pending_review`, one call per finding. Required params: `path`, `body`, `subjectType: "LINE"` (or `"FILE"` for file-level). Optional: `line`, `side`, `startLine`, `startSide` for multi-line. Do not batch into a single review creation.
3. **Submit the review.** `pull_request_review_write` with `method: "submit_pending"`, `event: "COMMENT"`, and the summary body.

**Verify (only when you posted inline findings).** If you had no inline findings to post (step 2 had nothing to attach), skip verification — `totalCount: 0` is the correct outcome. Otherwise call `pull_request_read` with `method: "get_review_comments"`: if `totalCount` is 0, the submit dropped them. Retry **once**: restart from step 1 (new `create` pending review, re-attach every comment, re-`submit_pending`) — after `submit_pending` there is no pending review to attach to, so calling `add_comment_to_pending_review` without a fresh `create` will fail. If the retry also returns 0, stop and report the failure in the Step 5 summary (do not loop further).

**Never** use APPROVE or REQUEST_CHANGES (owner token can't APPROVE).

**Comment rules:**
- `line` must be a `+` line in the diff. If finding is on an unchanged line, attach to nearest `+` line and reference actual location in body.
- Deleted lines: `side: "LEFT"` with base-branch line number
- Tag with category: `Bug:` / `Spec:` / `Test:` / `Consistency:` / `Ripple:` / `Perf:` / `Security:`
- Uncertain: `Possible:` prefix
- **Found something that needs fixing? Describe the problem in a comment. Do not fix it, do not offer to fix it.**

**Critical:** Post all findings and **STOP**. Do not wait for user feedback. Do not offer follow-ups ("Want me to fix...?"). Do not suggest further actions. This is a read-only workflow — auditing only.

## Step 5: Report summary

Output a summary of what was reviewed (not a suggestion for fixes):

```
## PR #N Review — X comments posted
Subject: <one-line description of what the PR does, in your own words>
Bug: N | Spec: N | Test: N | Consistency: N | Ripple: N | Perf: N | Security: N | User-flagged: N
```

The `Subject:` line is a sanity check — if it doesn't match the PR's actual intent, you reviewed the wrong thing.

If user-supplied context was provided but rejected, add:
```
Rejected user input: "<claim>" — <reason for rejection>
```

Then **stop**. Do not wait for feedback or user input.

## Rules

- **You are a read-only auditor.** Your only output is review comments. Nothing else.
- **Post and exit.** Once comments are posted, output your summary and stop. Do not wait for user feedback, offer follow-ups, or suggest fixes.
- Do not approve, merge, close, or modify the PR.
- The only artifact is PR comments. Nothing else.
- Large diffs: prioritize `src/` → tests → docs. State what you skipped.
- Only post what a senior engineer would flag.
