---
name: fix-pr
description: Read review comments from a PR, fix each issue, resolve threads, validate
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

**Freshness check:** Run the shared [branch freshness
check](../../../sdd/CLAUDE-REFERENCE.md#branch-freshness) with `<BASE>` =
`master`, so Step 6's push is a plain fast-forward.

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
| 1   | `pull_request_read`  | `get_review_comments`| Inline review **threads** (not comments) on specific lines — pass `perPage: 100` |
| 2   | `pull_request_read`  | `get_comments`       | Review-level comments (pulls API)        |
| 3   | `pull_request_read`  | `get_reviews`        | Review body/summary text                 |
| 4   | `issue_read`         | `get_comments`       | Top-level conversation comments (issues API — GitHub stores these separately) |

**Every one of these paginates, and a truncated work list is indistinguishable
from a short one.** Pass `perPage: 100`; if a source returns exactly 100, or
source 1 reports `hasNextPage`, fetch the next page (`after` the returned
`endCursor` for source 1, `page` for the rest) until it does not. A comment you
never fetched looks exactly like a comment that does not exist, and this list is
the input to every fix below — the same silent-ceiling shape `/rvw-pr` Step 4
pins its own instrument against.

Source 1 returns **threads**, each carrying its own comments; do not treat its
`totalCount` as a comment count.

If `gh` CLI is authenticated, also fetch thread IDs for resolution in Step 4:

```bash
gh api graphql -f query='
  query($owner:String!, $repo:String!, $number:Int!) {
    repository(owner:$owner, name:$repo) {
      pullRequest(number:$number) {
        reviewThreads(last: 100) {   # saturating: if this returns 100, page it
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

`reviewThreads(last: 100)` is a ceiling, not a total: if it returns exactly 100,
page it with `before`/`after` rather than assuming that is all of them. MCP
`resolve_review_thread` covers the same gap where `gh api graphql` is
unavailable.

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

Run the shared [PR validation
gates](../../../sdd/CLAUDE-REFERENCE.md#pr-validation-gates) — the mechanical gate,
local-machine reference, and qualitative TESTING/CONTENT review — with `<BASE>` =
`master`. Report violations and resolve any stop condition before committing.

**Trace update.** Find the trace already on this branch via
`git diff origin/master...HEAD --name-only` — any `sdd/traces/*.yml`
that appears is the target. The /pr trace gate guarantees it exists
before the PR is opened. Update it with the review-driven fields:

- `discovery_followups` — new backlog items the review surfaced.
- `surprising_ripples` — paths the ripple-check table did not anticipate
  that the review caught.
- `co_shipped_items` — unrelated items the review confirmed this PR also closes.

No trace in the diff? The PR touches no backlog item; skip and note it
in the Step 6 report. If the review surfaces a distinct new backlog item
that warrants its own work, that follows the /pr flow in a separate PR —
do not create a new trace here.

## Step 6: Commit and push

Stage, commit (`fix: address PR #$ARGUMENTS review`), push. Report: comments
fixed/resolved, skipped with reasons, per finding the class swept and per fix
the sibling descriptions swept — each with what it caught, because a sweep
that found nothing reads exactly like one that never ran — the enumeration
behind any fix to a quantified claim, and any changed surface the gate never
executed.

## Rules

- Do not merge, close, or approve the PR.
- Fix what was asked — don't refactor surrounding code.
- Fix the finding's class, not only the lines it names: a review names the
  instances it happened to see. Siblings share a failure mode, not a spelling,
  so for a rule spanning backends the question is which backends the tests
  execute against, not which lines match a grep.
- **A claim about an action names what you ran, and you run it before you write
  the sentence.** "I swept both sites", "I measured it", "I checked every
  backend" — in a reply, a commit message, or the Step 6 report — carries the
  command, path list, or enumeration behind it. This is
  [`CLAUDE.md` principle 9](../../../CLAUDE.md#principles) applied to the half
  of its class its *mechanism* cannot reach. The principle names action-claims
  explicitly; what it cannot supply for them is a derivation, because a number
  can show its working and an action has only the check you did or did not run.
  So the enforcement for that half lands here, where replies are authored.
  Replies are durable, are re-read by Step 1's own comment fetch on every later
  round, and are reviewed by **nobody** — no reviewer fetches them, by design,
  because that is what keeps `/ship`'s unprimed passes unprimed. That bound is
  why the check is yours: a false "I swept X" in a reply survives to the end of
  the loop and beyond
  ([ADR-0037 § Context](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md#context)).
- **A fix to a quantified claim is scoped to the quantifier, not to the
  finding.** When the artifact under repair says "every X", "all but Y", or
  "each of these", the fix covers that extent and the reply states the
  enumeration — how many there are, and that you counted rather than assumed.
  Closing a finding to exactly its own wording leaves the rest of the class
  open and reads, to every later reviewer, as though it were closed. A
  divergence list claiming "every operation except the two deletes" needs an
  item scoped to every operation except the two deletes, not to whichever
  subset a reviewer happened to measure — that gap was caught, closed to its
  own wording, and caught again three rounds later in the same sentence.
- Sweep your own fixes the same way: a fix changes a thing, and every other
  description of that thing — docstring, comment, spec table, guide — is now
  suspect. The class sweep above fires on a review finding; nothing but this
  rule points a sweep at the defects a fix itself creates, and that is where
  they land
  ([ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md)).
  Same discipline: coverage, not a grep — the same claim appears in different
  words.
- **A copy is not correct because it matches the source. It is correct when it
  is true where it sits.** The sweep above finds the copies; this rule checks
  them. A clause true of some backends becomes false the moment it is written
  as a flat guarantee on a backend-agnostic facade, and a qualifier that was
  redundant in the spec is load-bearing in a docstring the whole API reads.
  Ask of each copy what its own readers will take it to promise, not whether
  it agrees with the original. Filling an omission with a statement that is
  wrong at its new altitude is a smaller defect than the omission and a more
  misleading one, because it reads as authoritative.
