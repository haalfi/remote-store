---
name: fix-pr
description: Read review comments from a PR, fix each issue, resolve threads, validate
disable-model-invocation: true
argument-hint: "[PR number]"
---

PR: `$ARGUMENTS` (ask if missing). Repo: `haalfi/remote-store`.

## Step 1: Fetch comments and rebase

Check out the PR's head branch. Run `git fetch origin master`, then rebase onto `origin/master` if behind (`git rebase origin/master`) — parallel PRs may have merged since this branch was created. Use `origin/master`, not local `master`, so the rebase target is current.

For all GitHub API calls in this skill (reading PR data, posting comments, resolving threads):
use `github-pat` first (read+write), fall back to `MCP_DOCKER` for reads only.
When both servers expose the same tool name, always prefer `github-pat`.
See CLAUDE.md § GitHub operations for the full priority chain.

Fetch **all four** comment sources (`owner: "haalfi"`, `repo: "remote-store"`):

| #   | Tool                 | Method               | What it returns                          |
| --- | -------------------- | -------------------- | ---------------------------------------- |
| 1   | `pull_request_read`  | `get_review_comments`| Inline thread comments on specific lines |
| 2   | `pull_request_read`  | `get_comments`       | Review-level comments (pulls API)        |
| 3   | `pull_request_read`  | `get_reviews`        | Review body/summary text                 |
| 4   | `issue_read`         | `get_comments`       | Top-level conversation comments (issues API — GitHub stores these separately) |

If `gh` CLI is authenticated, also fetch thread IDs for resolution in Step 4:

```bash
gh api graphql -f query='
  query($owner:String!, $repo:String!, $number:Int!) {
    repository(owner:$owner, name:$repo) {
      pullRequest(number:$number) {
        reviewThreads(last: 100) {
          nodes {
            id isResolved isOutdated path line
            comments(first: 10) {
              nodes { body author { login } originalLine line path }
            }
          }
        }
      }
    }
  }
' -f owner='haalfi' -f repo='remote-store' -F number=$ARGUMENTS
```

No gh? Skip thread IDs — tell user thread resolution will be manual.

## Step 2: Triage

Build work list from **all four sources** (see table above):

- **Source 1** (inline threads): skip resolved, outdated, and bot comments.
- **Sources 2–4** (reviews, PR comments, issue comments): no resolution state — always scan. Extract actionable items (bugs, spec gaps, test gaps, dead code, etc.).

For each actionable item note: file, line, category (Bug/Spec/Test/Consistency/Ripple/Security), what to change.

**Be critical.** Verify each claim against the code — comments can be wrong or already fixed. Skip bad suggestions with a reason, don't blindly apply them.

## Step 3: Fix

Read each file in full, make the fix, verify against relevant `sdd/` docs (specs, ADRs, audits, design docs) if the change touches a documented area.

## Step 4: Resolve threads

If gh available, batch-resolve fixed threads:

```bash
gh api graphql -f query='
  mutation {
    t0: resolveReviewThread(input:{threadId:"THREAD_ID_0"}) { thread { isResolved } }
    t1: resolveReviewThread(input:{threadId:"THREAD_ID_1"}) { thread { isResolved } }
  }
'
```

Only resolve threads you fixed. No gh? Tell user to resolve manually.

## Step 5: Validate

Run `hatch run lint` and `hatch run test`. Fix failures, re-run until clean.

## Step 6: Commit and push

Stage, commit (`fix: address PR #$ARGUMENTS review`), push. Report: comments fixed/resolved, skipped with reasons.

## Rules

- Do not merge, close, or approve the PR.
- Fix what was asked — don't refactor surrounding code.
