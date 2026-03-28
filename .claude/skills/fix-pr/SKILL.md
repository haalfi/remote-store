---
name: fix-pr
description: Read review comments from a PR, fix each issue, resolve threads, validate
disable-model-invocation: true
argument-hint: "[PR number]"
---

PR: `$ARGUMENTS` (ask if missing). Repo: `haalfi/remote-store`.

## Step 1: Fetch comments and rebase

Check out the PR's head branch. Rebase onto master if behind (`git rebase master`) — parallel PRs may have merged since this branch was created.

Use `pull_request_read` (prefer `github-pat`, fall back to `MCP_DOCKER`) with `owner: "haalfi"`, `repo: "remote-store"`, `pullNumber: $ARGUMENTS`.

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

Build work list from unresolved comments. Skip resolved, outdated, and bot comments. For each actionable item note: file, line, category (Bug/Spec/Test/Consistency/Ripple/Security), what to change. List unclear/debatable comments as "Skipped" with reason.

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
