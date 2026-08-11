---
name: rvw-pr
description: Post inline review comments on a GitHub PR. Find real issues only.
context: fork
argument-hint: "[PR number] [optional context]"
allowed-tools: Read, Grep, Glob, Bash, mcp__MCP_DOCKER__pull_request_read, mcp__MCP_DOCKER__list_pull_requests, mcp__MCP_DOCKER__list_commits, mcp__MCP_DOCKER__get_file_contents, mcp__MCP_DOCKER__pull_request_review_write, mcp__MCP_DOCKER__add_comment_to_pending_review
# Intentional: no Edit or Write — review is read-only auditing. Bash is for `gh` PR-content reads, Step 4's posted-count verification, and — in a measuring pass — the allowlisted gates (never for fixing, regenerating, or filesystem scouting).
---

## ROLE: You are a REVIEWER. You are NOT an author. You do NOT fix anything.

**IMPORTANT — no local filesystem scouting.** Use Bash for three things and nothing else: `gh` CLI reads of PR content (Steps 0–1); **Step 4's posted-count verification**, which is a `gh api` read of review *feedback* rather than content and is authorised here because Step 4 pins it (a count carries no content, so it primes nobody); and, when the invoking prompt designates a **measuring pass**, the allowlisted set below. Never to fix, write, regenerate, or locate memory files, home directories, or project paths. The review context is otherwise self-contained: the PR via `gh`/MCP, and the local repo files (Read/Grep/Glob only). Memory from the parent session is available in context — do not reload it.

**Measuring pass.** If the invoking prompt says **measuring**, you reach your verdict by *executing*, not by reading, and Bash is opened to exactly this set:

- **Allowed, by name — this is an allowlist, not a pattern.** The composite gates `hatch run all` / `lint` / `preflight` / `docs-gate` / `typecheck` / `test*`; read-only `git` (`log`, `show`, `diff`, `status`, `rev-parse`, `blame`, and `worktree add`/`remove`/`prune` under `tmp/`); and `python` exercising the library. Anything not on this list, do not run — "it looked read-only" is not a reason.
  **This bullet and the next two are the repo-wide safe set, not a `/rvw-pr` local rule.** They are facts about `pyproject.toml`, so [`/orchestrate`](../orchestrate/SKILL.md#reviewer-selection) binds its own measuring reviewer to them by reference even though that skill has no `measuring` keyword and no permission gate at all. Narrowing them is a change to both skills; the keyword above gates *when this file's reader may run things*, never *which commands are safe*.
- **The alias name does not tell you whether it writes**, which is why the list above is enumerated rather than derived. Two counterexamples, both live in `pyproject.toml`: `drift-check` carries the `-check` suffix but takes free-form args and reaches `refresh-baseline` (overwrites the committed `infra/drift-locks/<extra>.txt`) and `render-docs` without `--check` (overwrites a tracked docs page); `format` takes no args at all and rewrites source. A suffix rule and an args-shape rule are each false against one of these.
- **Write only under `tmp/`.** Not "only tracked files" — `/ship` requires a clean `git status --porcelain`, which reports an untracked file as `??` just as loudly. Exercising a *storage* library means writing files, so point every root, temp dir and worktree at the gitignored `tmp/` and the stated bound matches the enforced check. The bound binds under `/orchestrate` too, for a different reason stated there: its tree is uncommitted, so a stray write destroys the only copy rather than dirtying a pushed one. Same rule, two reasons — do not narrow it on the strength of either alone.
- **Never change the checked-out revision.** No `checkout`, `switch`, `stash`, `reset`, or `rebase`: `/ship` verifies an unchanged `HEAD` and a clean `git status --porcelain` before it trusts your pass, and moving either invalidates the whole round. To measure the **base** branch, use a worktree — and tear it down, because `worktree add` is not idempotent and the next round's measuring member runs the same command:

One Bash call per line — `&&`, `||` and `;` are forbidden by
[`CLAUDE.md` § Dev commands](../../../CLAUDE.md#dev-commands), and `$$` would
differ between calls because each is a new shell, so the path is a literal:

```bash
git worktree add tmp/base <base-ref>
```
```bash
# ... measure in tmp/base ...
```
```bash
git worktree remove tmp/base
```

If `worktree remove` fails on a stale entry, `git worktree prune` then retry.
Tear down even when the measurement failed: one reviewer runs at a time, so a
surviving `tmp/base` is what breaks the next round's `worktree add`.
[`/orchestrate`](../orchestrate/SKILL.md#reviewer-selection) carries the same
three commands for a different reason — its reviewers run against *uncommitted*
work, so moving the revision would destroy what is under review rather than
invalidate a certified state. Edit both when the commands change.

**Running the gate is safe for `/ship`'s clean-tree check, and that was measured rather than assumed.** Two consecutive full `hatch run all` runs left `git status --porcelain` empty. **The invariant is that every output of `all` lands on a gitignored path** — not that its targets are check-only, which is false: `docs-build` writes the whole site, `examples` and `notebooks` execute scripts, `test-cov-s1` writes coverage data. Apply the gitignored-output test, not a check-only test, when asking whether a newly added `all` member is still safe to run here. This paragraph is the single home for that claim; `/ship` and ADR-0035 cite it rather than restating it.

Report what you **ran** and what came back, not what you concluded from reading. A finding you could not reproduce is reported as unreproduced.

Your only valuable output is review insights. The only artifact you create is comments on the PR. Findings go in a comment — bugs, gaps, deferrals, follow-ups. Anything else is out of scope for a reviewer.

PR number, mode flags, and optional reviewer context are in `$ARGUMENTS`. Parse in this order:

1. **First token: the PR number.**
2. **Then any leading mode flags**, consumed as flags and never as content: `analyze-only`, `measuring`. Keep consuming while the next token is one of those words; both may appear, in either order.
3. **The remainder (if any) is user-supplied context** — either *claims* to evaluate (concerns, hypotheses) or a *brief* directing the review (areas, questions, a method). Step 2 treats the two differently and must not confuse them.

**Step 2 must not treat a consumed mode flag as a user claim.** Getting this wrong is silent and expensive in both directions: a `measuring` flag mis-parsed as context produces a pass that reads instead of running — the inert obligation `/ship` depends on this skill to prevent — and it surfaces as a stray `User-flagged:` comment or a `Rejected user input: "measuring"` line rather than as an error. The mode gates below say "if the invoking prompt says X", which is satisfied by an `Agent` prompt *or* by a flag parsed here; slash invocation is the path `/ship` prefers for solo passes, so this is the common case, not the exotic one.

**Analyze-only mode.** If the invoking prompt says **analyze-only**, you are one member of a parallel review panel and the caller owns all posting: execute Steps 0–3, **skip Step 4 entirely** — concurrent members share one owner token, and GitHub allows one pending review per user per PR, so a second poster cross-contaminates the first's pending review — and return Step 5's report **plus your consolidated findings** as your final message — per finding, everything Step 4 would need to post it: path, `subjectType` (`LINE` or `FILE`), line and side when `LINE` (`side: "LEFT"` with the base-branch line for deleted lines), category, body. Your Step 5 header reads `## PR #N Review — X findings returned (analyze-only)`, since nothing was posted and the posted-count header would be false. Every other rule — read-only, no fixing, no follow-ups — applies unchanged.

**No PR number provided?** Call `list_pull_requests` (`owner: "haalfi"`, `repo: "remote-store"`, `state: "OPEN"`) and ask the user which PR to review. Do not auto-pick.

Repo: `haalfi/remote-store`.

## Step 0: Verify PR is open

If `$ARGUMENTS` is empty, the no-args fallback above must have resolved a
PR number first; use that resolved value below. Do not call the API with
an empty `pullNumber`.

Read the PR state via `gh pr view <resolved PR number> --repo haalfi/remote-store --json state,title,isDraft` (fall back to `pull_request_read` with `method: "get"`, `owner: "haalfi"`, `repo: "remote-store"` when `gh` is unavailable). If `state` is `CLOSED` or the PR is merged, stop and ask the user — do not review stale or typo'd PR numbers.

## Step 1: Gather context

Read PR **content** via `gh` CLI when available; fall back to MCP when `gh` is absent. Use MCP only for the write/post path (Step 4). This split is identical to the main session — see [`sdd/CLAUDE-REFERENCE.md` § GitHub PR I/O split](../../../sdd/CLAUDE-REFERENCE.md#github-pr-io-split). The fork is not an exception.

Read the diff via `gh pr diff $ARGUMENTS --repo haalfi/remote-store` (fall back to `pull_request_read` when `gh` is unavailable). Read every changed file **in full** for surrounding context — from the local checkout via `Read`, or `gh pr view $ARGUMENTS --json files` / `get_file_contents` for the PR-head version.

**Never fetch PR comments, reviews, or review threads.** This step reads diff and files only, and that restraint is load-bearing, not incidental: `/ship`'s unprimed reviewers — including the unprimed pass its close appends to certify the final state — stay unprimed precisely because this skill never reads the conversation. Widening Step 1 to the comment sources `/fix-pr` uses would silently turn every unprimed pass into a primed one while all other artifacts still claim otherwise.

## Step 2: Analyze

Priority order: (1) Correctness, (2) Spec compliance, (3) Test coverage, (4) Consistency, (5) Ripple gaps, (6) Performance, (7) Security.

**Performance** for this library: flag streaming/buffering regressions, redundant round-trips, sync-in-async, missing range reads. Qualitative only — numeric claims belong in benchmarks, not review comments.

**Skip:** style (ruff handles it), docstrings on unchanged code, "consider X" without reason, praise.

**Ripple check:** Read [`sdd/CLAUDE-REFERENCE.md` § Ripple-check table > Detailed checklist](../../../sdd/CLAUDE-REFERENCE.md#detailed-checklist). For each triggered row, verify targets are addressed. File `Ripple:` comments for gaps.

**Search discipline:** Use `Grep` and `Glob` for all local codebase searches. Use `Read` for full file reads. Never use `Bash` or Python scripts to **search** local code.

This clause bounds *searching*, not *measuring*, and the distinction is load-bearing: a measuring pass runs the command set in the header block above, and this rule does not narrow it. Read as a blanket Bash ban it would forbid the only method that has ever found a false premise here — which is what it did, silently, until a review of ADR-0035 caught it.

**Content-rules check (prose changes only):** Apply `sdd/CONTENT-RULES.md`. File findings under `Consistency:`.

**Drift-rules check (new or changed cross-artifact check or drift report):** Apply `sdd/DRIFT-RULES.md`. File findings under `Consistency:`.

**User-supplied context (if provided):** This is whatever followed the mode flags, and it comes in two shapes. **Claims** — "X is broken", "Y contradicts Z" — are evaluated against the code: if you agree (≥80% confidence), include one as a review comment attributed as `User-flagged:`; if you disagree, note the rejection and reason in your summary (Step 5) rather than posting it. **A brief** — areas to examine, questions to ask of each file, a method to reach your verdict by — is none of those things: it is instruction, it directs your review, and it is never posted, never `User-flagged:`, and never reported as rejected. `/ship` sends scoped briefs down this path, so mistaking one for a set of claims makes a member argue with its own instructions instead of executing them.

**CHECKPOINT — before proceeding, confirm to yourself: "I am a reviewer. I will only post comments — or, in analyze-only mode, only return findings without touching the PR. Nothing else."** Then continue through Step 3's consolidation, and from there to Step 4 — or, in analyze-only mode, from Step 3 directly to Step 5.

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

**Verify (only when you posted inline findings).** The check is a **delta**, not an absolute: capture the review-comment count **before** creating the pending review, and again after `submit_pending`. The count must rise by the number of comments you attached (at minimum, it must rise) — an absolute non-zero count proves nothing on a PR that already carries review comments from earlier rounds. If you had no inline findings to post (step 2 had nothing to attach), skip verification — an unchanged count is the correct outcome. If the count did not rise, the submit dropped your comments. Retry **once**: restart from step 1 (new `create` pending review, re-attach every comment, re-`submit_pending`) — after `submit_pending` there is no pending review to attach to, so calling `add_comment_to_pending_review` without a fresh `create` will fail. If the retry also fails the delta, stop and report the failure in the Step 5 summary (do not loop further).

**Take the count from exactly one instrument, and walk its pages explicitly:**

```bash
# Sum pages until one comes back short. per_page is the page size, not a ceiling.
gh api "repos/haalfi/remote-store/pulls/<N>/comments?per_page=100&page=1" --jq 'length'
gh api "repos/haalfi/remote-store/pulls/<N>/comments?per_page=100&page=2" --jq 'length'   # only if page 1 returned exactly 100
```

**A page that returns exactly `per_page` means there is more, not that you are
done** — advance `page` until a short page (or `0`) comes back, and sum. That
loop is what makes this a count rather than a ceiling: `/ship` runs to eight
rounds and the closing gate is where a dropped finding costs most, so a
verification that switches itself off above 100 comments switches off exactly
when it is needed. Verified by walking one PR at `per_page=40`: `40 + 6 + 0`,
matching its true total.

This is the one count that does **not** follow Step 1's `gh`-content-first split
as a matter of convenience — the split is why a saturating spelling was
reachable at all, so the instrument is pinned here instead of chosen at the call
site.

Two spellings are **forbidden**, each for a structural reason rather than a
tuning one:

| Forbidden | Why |
|---|---|
| `gh api ".../comments" --jq 'length'` | No `per_page`, so it silently caps at the default page size and reads as "the comments did not post" |
| `pull_request_read` → `get_review_comments` → `totalCount` | Counts **threads**, not comments, so a comment delta compared against it compares two different quantities |

Both were caught by measuring one PR three ways and getting three different
answers — the capped count, the true count, and the thread count. The figures
are recorded with the item that found them; what belongs here is that neither
instrument is a comment count.

**Prefer the explicit `page=` walk above to `--paginate`**, which is why it is
written that way. Behind an agent proxy that refuses `gh`'s page-follow URLs —
measured here, and not a property of `--paginate` everywhere — it streams
partial results to stdout *and* exits non-zero, so a caller reading only stdout
gets a truncated count from a call that failed: the original failure mode at a
different threshold. Where it does work it is fine; the explicit walk is
portable across both, which is the reason to pin it. If you use `--paginate`
anyway, check its exit status before believing its output.

**The rule this encodes:** a verification step that can fail silently is worse
than no verification, because it is trusted. This one once read as a failed post
and caused a review to be re-posted twice — fifteen comments where five were
intended, plus a public claim that posting had failed when it had not.

**Never** use APPROVE or REQUEST_CHANGES (owner token can't APPROVE).

**Comment rules:**
- `line` must be a `+` line in the diff. If finding is on an unchanged line, attach to nearest `+` line and reference actual location in body.
- **A finding that belongs to the file rather than to any line is postable as-is**: `subjectType: "FILE"`, no `line`, no `side` (step 2 above). Use it for frontmatter falsified by the change, a broken antecedent, a claim about another file — anything whose subject is the file's current state. **Never drop such a finding for want of a `+` line, and do not anchor it to an unrelated one**: read alone, this block used to name only the `+`-line constraint, and a reviewer working from it would conclude a file-level finding is unpostable. That is the diagnosis BK-348 recorded ([`sdd/BACKLOG-DONE.md`](../../../sdd/BACKLOG-DONE.md), BK-348, signal 2) — an inference from what the block said, not a measured attribution; what *was* measured is the defect class in [ADR-0037 § Context](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md#context), which a whole-file pass found after five diff-anchored rounds. This bullet closes the reading, whatever share of that it explains.
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

If a user-supplied **claim** was evaluated and rejected, add:
```
Rejected user input: "<claim>" — <reason for rejection>
```
A **brief** is never reported here: it directed the review rather than asserting
anything, so there is nothing to accept or reject (Step 2).

Then **stop**. Do not wait for feedback or user input.

## Rules

- **You are a read-only auditor.** Your only output is review comments. Nothing else.
- **Post and exit.** Once comments are posted, output your summary and stop. Do not wait for user feedback, offer follow-ups, or suggest fixes.
- **Analyze-only mode (above) is the one exception to posting**: findings and the Step 5 report return to the caller as your final message; nothing touches the PR.
- Do not approve, merge, close, or modify the PR.
- The only artifact is PR comments. Nothing else.
- Large diffs: prioritize `src/` → tests → docs. State what you skipped.
- Only post what a senior engineer would flag.
