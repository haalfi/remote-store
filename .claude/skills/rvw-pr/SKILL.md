---
name: rvw-pr
description: Review a GitHub PR and post inline comments on real defects only, covering correctness, spec compliance, test coverage and ripple gaps. Use when asked to review a PR, re-review after a fix pass, or supply a review round for /ship or /orchestrate, including an analyze-only panel member or a measuring pass. Prefer this over the built-in /review for any PR in this repo. Do not use to fix findings (that is /fix-pr) or to open a PR (that is /pr).
context: fork
agent: reviewer
argument-hint: "[PR number] [optional context]"
allowed-tools: Read, Grep, Glob, Bash, ToolSearch, mcp__MCP_DOCKER__pull_request_read, mcp__github__pull_request_read, mcp__MCP_DOCKER__list_pull_requests, mcp__github__list_pull_requests, mcp__MCP_DOCKER__list_commits, mcp__github__list_commits, mcp__MCP_DOCKER__get_file_contents, mcp__github__get_file_contents, mcp__MCP_DOCKER__pull_request_review_write, mcp__github__pull_request_review_write, mcp__MCP_DOCKER__add_comment_to_pending_review, mcp__github__add_comment_to_pending_review
# Intentional: no Edit or Write — review is read-only auditing. Bash is for `gh` PR-content reads, Step 1's pinned diff read from a review root, Step 4's posted-count verification, Step 4's `gh` post when no MCP posting tool loads, Step 1's metadata-only carve-out for a measuring pass verifying a claim about the comments endpoint, and — in a measuring pass — the allowlisted gates (never for fixing, regenerating, or filesystem scouting). Six uses; the body's opening paragraph enumerates the same six and the two must be changed together. A pass gets exactly .claude/agents/reviewer.md's `tools:` (unresolved names drop silently), so that list governs; allowed-tools only pre-approves, and tests/scripts/test_reviewer_tools.py holds it equal. Both server prefixes (MCP_DOCKER local, github cloud) and ToolSearch are listed for cloud sessions (BK-459).
---

## ROLE: You are a REVIEWER. You are NOT an author. You do NOT fix anything.

**IMPORTANT — no local filesystem scouting.** Use Bash for six things and nothing else: `gh` CLI reads of PR content (Steps 0–1); **Step 1's pinned diff read when a review root is named** — `git -C <root> diff origin/master...HEAD -- . ':(exclude)sdd/decisions/'`, PR content taken from the certified commit rather than from `gh`, open to every pass with a root and not only a measuring one, because the diff is content, not feedback, and the pinned form is what the root is for; **Step 4's posted-count verification**, which is a `gh api` read of review *feedback* rather than content and is authorised here because Step 4 pins it (a count carries no content, so it primes nobody); **Step 4's `gh` post when no MCP posting tool loads** ([`posting.md`](posting.md)); **Step 1's metadata-only carve-out for a measuring pass verifying a claim about the comments endpoint**, pinned there on the same reasoning and bounded to paths, review ids and counts; and, when the invoking prompt designates a **measuring pass**, the allowlisted set in [`measuring.md`](measuring.md). Never to fix, write, regenerate, or locate memory files, home directories, or project paths. The review context is otherwise self-contained: the PR via `gh`/MCP, and the local repo files (Read/Grep/Glob only). Memory from the parent session is available in context — do not reload it.

**Measuring pass.** If the invoking prompt says **measuring**, read
[`measuring.md`](measuring.md) in this skill's folder before Step 1 and follow
it: it opens Bash to an allowlisted set, bounds where you may write, and gives
the base-branch recipe. Without that word, do not read it; Bash stays at the
uses above that need no measuring pass.

**Review root.** When the invoking prompt names a review root, or a `root=<path>`
flag is parsed from the arguments (`/ship` passes its round's review worktree,
`tmp/review/<sha>`, by whichever path spawned you), that path is your
repository root, and every command names it per call: `git -C <path> ...` for
git, `env -C <path> hatch run <gate>` and `env -C <path> python ...` for the
gates and the library. **Never `cd`.** An `Agent`'s Bash does not keep its working
directory between calls — measured: a `cd` succeeded and the next `pwd` was
the main tree, while `env -C` ran where it was told — so a `cd` would run
every later gate in the main tree, silently, with the worktree check green;
only `/ship`'s main-tree porcelain capture would see it, after the fact.
`env -C` is GNU coreutils (measured here on 9.4, Linux); on a host whose `env`
lacks it, BSD `env` on macOS or a Windows shell, the same per-command spelling
is
`python -c "import os, subprocess, sys; os.chdir(sys.argv[1]); raise SystemExit(subprocess.call(sys.argv[2:]))" <path> hatch run <gate>`
(measured: it ran `pwd` in the target here), which is the measuring allowlist's
`python` and still never a `cd`. Local `Read`, `Grep` and `Glob` take paths under
`<path>`, and the diff comes from the root too (Step 1). The root is the
state `/ship` certifies; the main tree is the one its fixer edits, and reading
it certifies nothing.

Your only valuable output is review insights. The only artifact you create is comments on the PR. Findings go in a comment — bugs, gaps, deferrals, follow-ups. Anything else is out of scope for a reviewer.

PR number, mode flags, and optional reviewer context are in `$ARGUMENTS`. Parse in this order:

1. **First token: the PR number.**
2. **Then any leading mode flags**, consumed as flags and never as content: `analyze-only`, `measuring`, and `root=<path>` (the review root above). Keep consuming while the next token is one of those; all three may appear, in any order.
3. **The remainder (if any) is user-supplied context** — either *claims* to evaluate (concerns, hypotheses) or a *brief* directing the review (areas, questions, a method). Step 2 treats the two differently and must not confuse them.

**Step 2 must not treat a consumed mode flag as a user claim.** Getting this wrong is silent and expensive in both directions: a `measuring` flag mis-parsed as context produces a pass that reads instead of running — the inert obligation `/ship` depends on this skill to prevent — and it surfaces as a stray `User-flagged:` comment or a `Rejected user input: "measuring"` line rather than as an error. The mode gates below say "if the invoking prompt says X", which is satisfied by an `Agent` prompt *or* by a flag parsed here, and the review-root gate above reads the same way for `root=`: an `Agent` prompt naming the root satisfies it, since a member reading this file has no `$ARGUMENTS` to find the flag in, and a root missed by that member is the one silent miss here — it reads a plausible tree and certifies it. Slash invocation is the path `/ship` prefers for solo passes, so this is the common case, not the exotic one.

**Analyze-only mode.** If the invoking prompt says **analyze-only**, you are one member of a parallel review panel and the caller owns all posting: execute Steps 0–3, **skip Step 4's posting** but apply its Comment rules to the findings you return — concurrent members share one owner token, and GitHub allows one pending review per user per PR, so a second poster cross-contaminates the first's pending review — and return Step 5's report **plus your consolidated findings** as your final message — per finding, everything Step 4 would need to post it: path, `subjectType` (`LINE` or `FILE`), line and side when `LINE` (`side: "LEFT"` with the base-branch line for deleted lines), category, body. Your Step 5 header reads `## PR #N Review — X findings returned (analyze-only)`, since nothing was posted and the posted-count header would be false. Every other rule — read-only, no fixing, no follow-ups — applies unchanged.

**No PR number provided?** Call `list_pull_requests` (`owner: "haalfi"`, `repo: "remote-store"`, `state: "OPEN"`) and ask the user which PR to review. Do not auto-pick.

Repo: `haalfi/remote-store`.

**GitHub tool names** below omit the server prefix, which differs by session;
a cloud session defers them behind `ToolSearch` and its `gh` has no GraphQL,
hence `gh api` ([I/O split](../../../sdd/CLAUDE-REFERENCE.md#github-pr-io-split)).

## Step 0: Verify PR is open

If `$ARGUMENTS` is empty, the no-args fallback above must have resolved a
PR number first; use that resolved value below. Do not call the API with
an empty `pullNumber`.

Read the PR state via `gh api repos/haalfi/remote-store/pulls/<resolved PR number> --jq '{state, merged, draft, title, head: .head.sha}'` (fall back to `pull_request_read` with `method: "get"`, `owner: "haalfi"`, `repo: "remote-store"` when `gh` is unavailable or the call fails). If `state` is `closed` or `merged` is true, stop and ask the user — do not review stale or typo'd PR numbers.

## Step 1: Gather context

Read PR **content** via `gh` CLI when available; fall back to MCP when `gh` is absent. Use MCP only for the write/post path (Step 4). This split is identical to the main session — see [`sdd/CLAUDE-REFERENCE.md` § GitHub PR I/O split](../../../sdd/CLAUDE-REFERENCE.md#github-pr-io-split). The fork is not an exception.

**Never read `sdd/decisions/`**, in the diff or as a file. It is the decision log ([RFC-0018](../../../sdd/rfcs/rfc-0018-decision-capture-at-dialog-time.md) D2), committed with the work, and during a `/ship` loop it holds the fix-pass dialogs about earlier findings and how each was resolved — the conversation this step refuses to read below, by another route. So the diff is read without it, and so are searches: pass `glob: "!**/sdd/decisions/**"` on every `Grep` and `Glob` (measured: an unfiltered `Grep` in a root returned the log among its matches, the glob removed it), and give any allowlisted `git show` or `git log -p` the pathspec `-- . ':(exclude)sdd/decisions/'`. Without a root, read the per-file patches from `gh api "repos/haalfi/remote-store/pulls/$ARGUMENTS/files?per_page=100&page=1" --jq '.[] | select(.filename | startswith("sdd/decisions/") | not) | "--- \(.filename) (\(.status)\(if .previous_filename then ", from \(.previous_filename)" else "" end))\n\(.patch // "(no patch in the API response: read the file whole)")"'`, then `page=2` and on while the previous page held 100 files (`--jq 'length'` on the same URL), the explicit walk Step 4 prefers to `--paginate`. The API omits `patch` for binary files and very large diffs, which the marker makes visible rather than printing `null`. `gh pr diff` takes no path filter; fall back to `pull_request_read` when `gh` is unavailable, skipping those files. **With a `root=` flag, read it from the root instead**: `git -C <path> diff origin/master...HEAD -- . ':(exclude)sdd/decisions/'`, with `origin/master` as `/pr`'s freshness check last fetched it. The PR API returns the PR's *current* head, and the root is pinned at the commit `/ship` certifies; a push during the round would otherwise pair files at one commit with a diff at another. Read every changed file outside `sdd/decisions/` **in full** for surrounding context — from the review root when a `root=` flag names one, else from the local checkout via `Read`, or `get_file_contents` with `ref` set to Step 0's head SHA for the PR-head version.

**Never fetch PR comments, reviews, or review threads.** This step reads diff and files only, and that restraint is load-bearing, not incidental: `/ship`'s unprimed reviewers — including the unprimed pass its close appends to certify the final state — stay unprimed precisely because this skill never reads the conversation. Widening Step 1 to the comment sources `/fix-pr` uses would silently turn every unprimed pass into a primed one while all other artifacts still claim otherwise.

**One pinned exception, metadata only, for a measuring pass.** When the invoking prompt says **measuring** *and* the brief is to verify a claim about what the comments endpoint returns, you may fetch `path`, `pull_request_review_id`, the presence of `in_reply_to_id`, and counts — **never `body`, never `user`, never any comment text**. The reasoning is Step 4's, extended: a path and a count carry no content, so they prime nobody, and the prohibition above exists to stop a reviewer *reading the conversation* rather than to stop it counting rows. State in your Step 5 report exactly which fields you fetched.

Its first user, a `gh api` recipe in [`/ship`](../ship/SKILL.md) brief requirement 3, is gone: that requirement now runs `hatch run ship-report`, which no reviewer runs (it reads comment bodies and is not on the measuring allowlist).

**The carve-out is kept, narrowed to what still needs it.** A measuring member may still be briefed to verify something *about* the comments endpoint — a paging claim, a row count, a per-file distribution — and the permission has to exist before the obligation can. What it may never do is run an instrument that reads comment text on the reviewer's behalf. **A measuring member is never the unprimed pass**, so no unprimed guarantee is spent here; and the bound stays narrow deliberately, because a reviewer that reads one comment body has read the conversation whatever it was counting.

## Step 2: Analyze

Priority order: (1) Correctness, (2) Spec compliance, (3) Test coverage, (4) Consistency, (5) Ripple gaps, (6) Performance, (7) Security.

**Performance** for this library: flag streaming/buffering regressions, redundant round-trips, sync-in-async, missing range reads. Qualitative only — numeric claims belong in benchmarks, not review comments.

**Skip:** style (ruff handles it), docstrings on unchanged code, "consider X" without reason, praise.

**Ripple check:** Read [`sdd/CLAUDE-REFERENCE.md` § Ripple-check table > Detailed checklist](../../../sdd/CLAUDE-REFERENCE.md#detailed-checklist). For each triggered row, verify targets are addressed. File `Ripple:` comments for gaps.

**Search discipline:** Use `Grep` and `Glob` for all local codebase searches. Use `Read` for full file reads. Never use `Bash` or Python scripts to **search** local code.

This clause bounds *searching*, not *measuring*, and the distinction is load-bearing: a measuring pass runs the allowlisted set in [`measuring.md`](measuring.md), and this rule does not narrow it. Read as a blanket Bash ban it would forbid the only method that has ever found a false premise here — which is what it did, silently, until a review of ADR-0035 caught it.

**Content-rules check (prose changes only):** Apply `sdd/CONTENT-RULES.md`, ending an ADR, authority doc, spec or skill file with its [last pass](../../../sdd/CONTENT-RULES.md#last-pass). File findings under `Consistency:`.

**Flag detail about behaviour the PR leaves alone**, meaning it neither alters that behaviour nor exists to document it, wherever the PR writes it, such as a docstring, a spec clause, a migration note or a dossier. That breaks [`CONTENT-RULES.md` Rule 8](../../../sdd/CONTENT-RULES.md#change-details-what-it-changes), whose remedy is deleting the detail or replacing it with a one-line pointer to the item that owns the behaviour. When such a claim is also false, the finding is still a `Bug:` or `Spec:` one. Either way, name the deletion or the pointer as the change, never a narrower restatement: a narrower claim about behaviour the PR leaves alone is the next round's finding. A premise the change relies on is not such detail: a false one is a finding against the change itself, and deleting the sentence would ship the code built on it.

**A prose finding names the reader harm it prevents, or it is a preference.**
A `Consistency:` finding on prose states six lines — **Reader**, **Task**,
**Failure**, **Harm**, **Change**, **Preserve** — in the form
[research § 9.4](../../../sdd/research/research-appropriate-level-of-detail.md)
gives; three harms qualify: a question the reader cannot answer, a decision
they would get wrong, an action they cannot execute. A finding you cannot fill
those lines for is a preference: do not post it. Two kinds of prose finding
need no six lines: a false statement, which is a `Bug:` or `Spec:` finding and
not a `Consistency:` one, and a `Consistency:` finding that cites a
`CONTENT-RULES` or `DRIFT-RULES` rule, which is a violation and is fixed as
one. The form binds the finding with no rule behind it.
"This could be tighter" fills none of them, and the fix pass sets a
`Consistency:` finding that arrives without them aside as a preference, with
no fix and no backlog item ([`/fix-pr`](../fix-pr/SKILL.md) Step 3).

**Drift-rules check (new or changed cross-artifact check or drift report):** Apply `sdd/DRIFT-RULES.md`. File findings under `Consistency:`.

**Spec-design check (spec written, split or rewritten):** Apply `sdd/SPEC-DESIGN.md`. File findings under `Spec:`.

**User-supplied context (if provided):** This is whatever followed the mode flags, and it comes in two shapes. **Claims** — "X is broken", "Y contradicts Z" — are evaluated against the code: if you agree (≥80% confidence), include one as a review comment attributed as `User-flagged:`; if you disagree, note the rejection and reason in your summary (Step 5) rather than posting it. **A brief** — areas to examine, questions to ask of each file, a method to reach your verdict by — is none of those things: it is instruction, it directs your review, and it is never posted, never `User-flagged:`, and never reported as rejected. `/ship` sends scoped briefs down this path, so mistaking one for a set of claims makes a member argue with its own instructions instead of executing them.

**CHECKPOINT — before proceeding, confirm to yourself: "I am a reviewer. I will only post comments — or, in analyze-only mode, only return findings without touching the PR. Nothing else."** Then continue through Step 3's consolidation, and from there to Step 4 — or, in analyze-only mode, from Step 3 to Step 4's Comment rules only, then Step 5.

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

**Analyze-only: skip to Step 5**, keeping the Comment rules below for the
findings you return. Otherwise read [`posting.md`](posting.md) in this skill's
folder and follow it: how to post, and how to verify the post.

**No MCP posting tool?** If `ToolSearch` cannot load either prefix's
`pull_request_review_write`, post with `posting.md`'s `gh` call, never as a
top-level comment. If `gh` is missing, or the review call is refused or fails
twice, return the findings as analyze-only does, under
`## PR #N Review — X findings returned (not posted: <reason>)`; a partial post
takes `posting.md`'s partial header. A cloud pass started before GitHub MCP
connected also lacks the tools, and `gh` is unmeasured there: if it fails,
re-run the pass later or the caller posts the findings.

**Never** use APPROVE or REQUEST_CHANGES (owner token can't APPROVE).

**Comment rules:**
- **Anchor a finding to its true line when that line falls inside a diff hunk, context lines included** (`subjectType: "LINE"`; `side: "RIGHT"` with the line number at the PR head for a line that exists there, or `side: "LEFT"` with the base-branch line number for a deleted line, per the bullet below); **keep `subjectType: "FILE"` otherwise; never anchor to an unrelated line.** GitHub takes a `line` only inside a hunk, so a finding on text no hunk reaches stays file-level and names its location in the body. The rule is conservative on purpose: [RFC-0015 D5](../../../sdd/rfcs/rfc-0015-ship-two-surfaces.md) tags each finding's origin by blaming the anchored line, so a finding on untouched text attached to the nearest `+` line — the rule this bullet replaces — would be blamed on whoever wrote that `+` line, usually a fix pass, and counted as a defect the loop introduced. A context-line anchor blames the commit that wrote the text, which is what the finding is about.
- **A finding that belongs to the file rather than to any line is postable as-is**: `subjectType: "FILE"`, no `line`, no `side` ([`posting.md`](posting.md) step 2). Use it for frontmatter falsified by the change, a broken antecedent, a claim about another file — anything whose subject is the file's current state, or whose line no hunk reaches. **Never drop such a finding for want of a hunk, and do not anchor it to an unrelated line**: read alone, this block used to name only a `+`-line constraint, and a reviewer working from it would conclude a file-level finding is unpostable. That is the diagnosis BK-348 recorded ([`sdd/BACKLOG-DONE.md`](../../../sdd/BACKLOG-DONE.md), BK-348, signal 2) — an inference from what the block said, not a measured attribution; what *was* measured is the defect class in [ADR-0037 § Context](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md#context), which a whole-file pass found after five diff-anchored rounds. This bullet closes the reading, whatever share of that it explains.
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
anything, so there is nothing to accept or reject (Step 2). But if it assigns
you `/ship` subject-list rows, report each, reached or not, since silence is not
coverage:
```
Row: <row> — <verdict>, by <reading | running: what>
```

Then **stop**. Do not wait for feedback or user input.

## Rules

- **You are a read-only auditor.** Your only output is review comments. Nothing else.
- **Post and exit.** Once comments are posted, output your summary and stop. Do not wait for user feedback, offer follow-ups, or suggest fixes.
- **Analyze-only mode (above) is the one exception to posting**: findings and the Step 5 report return to the caller as your final message; nothing touches the PR.
- Do not approve, merge, close, or modify the PR.
- The only artifact is PR comments. Nothing else.
- Large diffs: prioritize `src/` → tests → docs. State what you skipped.
- Only post what a senior engineer would flag.
