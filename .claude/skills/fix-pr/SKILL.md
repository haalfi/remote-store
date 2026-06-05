---
name: fix-pr
description: Read review comments from a PR, fix each issue, resolve threads, validate
disable-model-invocation: true
argument-hint: "[PR number]"
---

PR: `$ARGUMENTS`. Repo: `haalfi/remote-store`.

**No PR number provided?** Run `git branch --show-current`, then call `list_pull_requests` with `owner: "haalfi"`, `repo: "remote-store"`, `state: "OPEN"`, `head: "haalfi:<branch>"`. If exactly one PR matches, confirm with the user. If zero or multiple match, or the user declines, fall through to listing all open PRs and ask which to fix.

## Step 0: Verify PR is open

If `$ARGUMENTS` is empty, the no-args fallback above must have resolved a
PR number first; use that resolved value below. Do not call the API with
an empty `pullNumber`.

Read the PR state via `gh pr view <resolved PR number> --repo haalfi/remote-store --json state,title` (fall back to `pull_request_read` with `method: "get"`, `owner: "haalfi"`, `repo: "remote-store"` when `gh` is unavailable). If `state` is `CLOSED` or the PR is merged, stop and ask the user — do not fix stale or typo'd PR numbers.

## Step 1: Prepare branch and fetch comments

Check out the PR's head branch.

**Freshness check:** Run `git fetch origin master`, then
`git rev-list --count origin/master ^HEAD`. If the count is non-zero, the
branch is behind `origin/master`. Stop and ask the user whether to rebase.
If approved: `git rebase origin/master` then immediately
`git push --force-with-lease origin <current-branch>`, so Step 6's push is a
plain fast-forward. Do not rebase silently — `--force-with-lease` is
destructive to anyone tracking the branch.

Read PR **content** (diff, files, body) via `gh` CLI when available; read review
**feedback with resolution state** (the four comment sources below) via the
GitHub MCP server — content-only `gh` reads miss `isResolved`/`isOutdated`. Post
comments and resolve threads via MCP, falling back to `gh api graphql` for the
thread-resolve gap. This split is identical in the main session and any forked
PR skill — see [`sdd/CLAUDE-REFERENCE.md` § GitHub PR I/O split](../../../sdd/CLAUDE-REFERENCE.md#github-pr-io-split).

**Fetch comments after any rebase, not before.** Line numbers and the
`isOutdated` flag are computed against the PR's current HEAD; comments
fetched before a force-push triage against stale metadata.

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

For each actionable item note: file, line, category (Bug/Spec/Test/Consistency/Ripple/Perf/Security), what to change.

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

Run `hatch run lint`. Fix failures, re-run until clean.

**Coverage gate:** Check `git diff origin/master...HEAD --name-only` for files under `src/`, `tests/`, or `examples/`.
- If any match: run `hatch run test-cov-strict` (enforces 95%; needs Azurite running locally — see [CLAUDE.md § Coverage gate](../../../CLAUDE.md#coverage-gate)). If it fails, stop and report which files are below threshold.
- If none match (docs/config-only): run `hatch run test`.

5a. **Testing gate:** Do the changed tests follow the rules in `sdd/TESTING.md`?
    Report violations before commit.

5b. **Docs gate:** Does changed documentation follow the rules in `sdd/CONTENT-RULES.md`?
    Report violations before commit.

5d. **Local-machine reference gate:** Grep all files changed on this branch
    (`git diff origin/master...HEAD --name-only`) for private local-machine
    references that are unreachable from the repo:

    - `See memory ` or `` captured as `<slug>.md` `` — Claude Code memory slugs
    - `[A-Z]:\\[A-Za-z]` — Windows drive paths (skip `\n`/`\r`/`\t` escape sequences in string literals)
    - `~/\.claude` or `\.claude/projects` — private config paths

    Cover all tracked file types: `.md`, `.py`, `.sh`, `.yml`, `.dfy`, `.tla`.
    If any match, fix before committing — replace each with the principle or
    content it refers to, inline.

5c. **Trace update:** Find the trace already on this branch via
    `git diff origin/master...HEAD --name-only` — any `sdd/traces/*.yml`
    that appears is the target. The /pr trace gate guarantees it exists
    before the PR is opened. Update it with the review-driven fields:

    - `discovery_followups` — new backlog items the review surfaced.
    - `surprising_ripples` — paths the ripple-check table did not anticipate
      that the review caught.
    - `co_shipped_items` — unrelated items the review confirmed this PR also closes.

    No trace in the diff? The PR touches no backlog item; skip and note it
    in the Step 6 report. If the review surfaces a distinct new backlog
    item that warrants its own work, that follows the /pr flow in a
    separate PR — do not create a new trace here.

## Step 6: Commit and push

Stage, commit (`fix: address PR #$ARGUMENTS review`), push. Report: comments fixed/resolved, skipped with reasons.

## Rules

- Do not merge, close, or approve the PR.
- Fix what was asked — don't refactor surrounding code.
