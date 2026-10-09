---
name: pr
description: Create a pull request for the current branch, after running the repo's validation, trace and branch-freshness gates and filling the PR template. Use when asked to open, raise, or submit a PR for work on a feature branch, in preference to calling the GitHub API directly. Do not use to update, merge, or review an existing PR (that is /fix-pr and /rvw-pr).
argument-hint: "[base branch]"
---

Create a PR from the current branch. Base: `$ARGUMENTS` (default: `master`).
Repo: `haalfi/remote-store`.

Throughout this skill, **`<BASE>`** is `$ARGUMENTS` if provided, else `master`.
Substitute it in every command and reference below.

For all GitHub API calls in this skill, use the configured GitHub MCP server.
Fall back to `gh` CLI for GraphQL-only flows like review-thread resolution.

## Steps

1. **Pre-check:** Verify not on master, the working tree clean apart from the
   decision log (`git status --porcelain -- . ':(exclude)sdd/decisions/'` prints
   nothing), and the branch pushed to remote. Push with `-u` if needed. The log
   is left for Step 4, because this skill's own questions append to it. Then run
   the [branch freshness
   check](../../../sdd/CLAUDE-REFERENCE.md#branch-freshness)
   (`hatch run ref-show branch-freshness`) with `<BASE>`.

2. **Validation gates:** Run the shared [PR validation
   gates](../../../sdd/CLAUDE-REFERENCE.md#pr-validation-gates)
   (`hatch run ref-show pr-validation-gates`) — the mechanical
   gate, the backlog ID-set gate, local-machine reference, and qualitative
   TESTING/CONTENT review. Resolve any stop condition before drafting the PR.

3. **Trace gate:** Extract the backlog IDs this branch's commits claim with
   `python scripts/check_backlog_ids_vs_base.py --print-subject-ids --base origin/<BASE>`,
   which applies that file's `subject_ids()` to each subject of
   `git log origin/<BASE>..HEAD`. **Pass `--base` even when `<BASE>` is `master`**:
   it defaults to `origin/master`, so on any other base an unflagged run reads the
   wrong commit range. **Do not re-spell the
   grammar here.** A `^([A-Z]+-\d+[a-z]?)[:\s]` pattern stood in this step and
   under-enforced silently: it reads only a leading token and requires `:` or
   whitespace straight after the number, so a co-shipped subject like
   `BK-375, BK-373, BK-377: …` matched **nothing** and all three items skipped
   the trace requirement. Three such subjects sit in the forty commits before
   BK-378 (`git log --format=%s origin/master~40..origin/master`, filtered by
   `subject_ids` returning more than one ID). One grammar, one home
   ([`DRIFT-RULES.md` Rule 1](../../../sdd/DRIFT-RULES.md#one-driver)).
   For each unique ID, look up a
   matching trace **case-insensitively** — `find sdd/traces -iname '<id>-*.yml'` —
   because existing trace filenames mix lowercase and uppercase prefixes.
   If any ID has no match, stop and ask the user — [CLAUDE.md § Trace
   authoring (mandatory)](../../../CLAUDE.md#trace-authoring) requires the trace to ship in the same PR as the
   work. Schema: `sdd/traces/_schema.yml`. No ID-prefixed commits? Skip the gate.

4. **Commit the decision-log tail.** Steps 2 and 3 are the last that can ask a
   question; the body is drafted after this commit, so it can rely on a log
   that holds every dialog the PR will carry. Dialogs since the branch's last
   commit, this skill's own included, leave uncommitted lines in
   `sdd/decisions/`
   ([RFC-0018 D2](../../../sdd/rfcs/rfc-0018-decision-capture-at-dialog-time.md)).
   If `git status --porcelain -- sdd/decisions/` prints anything, run
   `git add -- sdd/decisions/`, then
   `git commit -m "<ID>: decision log" -- sdd/decisions/` (bare `decision log`
   when the branch carries no item), then push. The pathspec is what makes the
   commit hold the log alone: without it, `git commit` also takes anything
   already staged. The `git add` comes first because a pathspec commit fails on
   a path git does not yet track.

5. **Gather context:** `git log origin/<BASE>..HEAD --oneline` and `git diff origin/<BASE>...HEAD`
   to understand all changes (not just the latest commit). Use `origin/<BASE>`,
   not local `<BASE>`, so context does not depend on a stale local ref.

6. **Draft PR:** Title (<70 chars) + body. Read `.github/PULL_REQUEST_TEMPLATE.md`
   and fill each section from gathered context: summary bullets from commits,
   check the appropriate Type of change box, link any related issues, fill the
   Checklist. The template is the authoritative body shape.

7. **Create PR** using `create_pull_request`:
   - `owner: "haalfi"`, `repo: "remote-store"`
   - `head:` current branch, `base:` `<BASE>`
   - `title:` and `body:` from step 6

8. **Report** the PR URL.

## Rules

- This skill only creates the PR. Do not merge or approve it.
- Do not push to master.
- **Every figure in the body names the derivation it came from**, run before the
  sentence is written ([`CLAUDE.md` principle 9](../../../CLAUDE.md#principles)).
  Step 6 builds the body from commits, so its counts and claims are exactly the
  ones nobody re-checks: the measured instance behind this rule is a PR body
  asserting a field had moved to 6 when `git show` showed 4 → 5
  ([ADR-0037](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md)).
  Applies to every PR, not only those `/ship` opens — a body drafted here gets
  no other review of its figures.
