# ID-268 — Closing a PR needs a manual agent round trip before it can merge
<!-- doc: repo-only -->

Filed at the maintainer's request after PR #1071 (2026-10-04). The index entry
holds the current diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)). **No alternative is
chosen.** The open decision is which of the shapes below to build, or none.
On 2026-10-05 the maintainer asked for shape 6 (post-merge snapshot) to be
worked out in detail; that is a direction to explore, not a choice.

## Evidence

- **The round trip, as observed on PR #1071.** After review converged and CI was
  green, the maintainer asked whether the PR was merge-ready. It was not: neither
  trace carried the `review:` block. The agent ran
  `hatch run ship-report 1071 --trace-block-only`, pasted it into both traces,
  ran `lint` and `docs-gate`, committed and pushed. CI then re-ran on the new
  head, and only after that could the maintainer merge or set auto-merge.
- **Where the obligation comes from.** [`CLAUDE.md` § Trace authoring](../../CLAUDE.md#trace-authoring)
  requires the block at the close, verbatim from the script, shipped in the
  same PR. `sdd/traces/_schema.yml` does not list `review` among its required
  keys (`required:` at line 26), so no gate enforces it; the rule is the only
  trigger, and a forgotten block merges.
- **Why it cannot be produced earlier.** [RFC-0015 D4](../rfcs/rfc-0015-ship-two-surfaces.md)
  derives every figure about the loop after the loop ends, and the block is
  pasted while the PR is open. The decision itself names the PR number, which
  the block emits as `pr`, as the durable handle; the branch SHAs it lists stop
  resolving at the squash merge.
- **The script can run in a GitHub Actions job, given a deep checkout.**
  `scripts/ship_report.py` reads GitHub through `gh api` (`_gh_one`) and the
  classifier it imports (`sdd/rfcs/rfc-0015-findings.py`), but it also runs git
  against the checkout: `git log <base>..<head>` against `origin/<base>` for the
  review-driven commits, and `git blame` at the reviewed head for each finding's
  origin tag. Its docstring states "Requires `gh` authenticated and the base ref
  fetched". A job therefore needs the PR head, the base branch and full history
  (`fetch-depth: 0` or an explicit unshallow); `actions/checkout` defaults to
  depth 1. Measured in a `git clone --depth 1` of this branch, a shallow
  checkout fails in one of two ways, and neither shows up as `unclassifiable-*`:
  - **Base not fetched:** `git log origin/master..HEAD` exits 128, and the
    script's `_git` helper runs with `check=True`, so the run raises.
  - **Base fetched but shallow:** `git blame` exits 0 and attributes lines past
    the graft to the boundary commit (`^<sha>`). Read from the code, not run:
    `origin()` strips the `^` and passes that commit to its ancestry and
    author-date checks as if it had authored the line, so the tags look
    plausible and are wrong, and the block cannot show the checkout was too
    shallow.
- **The block undercounts rounds posted as conversation comments.** On PR #1071
  both review rounds were posted as PR conversation comments, not as review
  submissions or inline threads. The derived block reported
  `review_rounds: 0`, `findings: 0` and no review-driven commits, although one
  finding was fixed in a commit titled `fix: address PR #1071 review`. Any
  shape below that infers convergence from the block inherits this bound.
- **GitHub offers no pre-merge step that edits the PR.** A merge queue
  (`merge_group`) runs checks on a temporary merge commit and cannot add
  commits to the PR branch, so a block written there never reaches master.
  Stated from GitHub's documented model, not measured in this repo.

### Added 2026-10-05

- **No code consumes a committed `review:` block's figures.** Every `*.py`
  match for a `"review"` / `'review'` key (Grep over the repo) is either
  `tests/scripts/test_ship_report.py`, which tests the writer, or an unrelated
  regex group in `scripts/drift_report.py`. Two guards touch the block without
  reading its figures: `check_traces.py` validates it against `_schema.yml`, and
  `_trace_corpus.py` rejects the duplicate `review:` key a second paste leaves.
  `report-trace-outcomes` does not read it. Not checked: humans or agents that
  read blocks by eye.
- **Branch SHAs still resolve on GitHub after the squash.** `2a174de`, the
  first SHA in `sdd/traces/bk-378-d1-d4.yml`'s `review_driven_commits` (PR
  #1026, squash-merged), resolves through the commits API (`get_commit`, run
  2026-10-05). This narrows, not contradicts, the evidence above and
  `ship_report.py`'s Bounds: the SHAs are not *reachable from master*, but
  GitHub keeps them via the PR's refs. One sample.
- **The script runs post-merge with one caveat, read from the code.**
  `collect()` takes `head` from the PR's `head.sha`, which stays the last
  branch head after the merge, and `ensure_commit()` fetches it by SHA. The
  range is `origin/<base>..head`. Under a squash merge that range is still the
  branch's commits. Under a merge commit (`allow_merge_commit` is enabled per
  the Bounds) head becomes an ancestor of master, the range is empty, and
  `review_rounds` reads 0 with no error. A post-merge run needs the base pinned
  to the merge commit's first parent.
- **The trace→PR link is derivable from git.** The squash commit that adds a
  trace carries `(#NNNN)` in its subject in 941 of the 976 merge-free commits
  `ship_report.py`'s Bounds counted, so `git log --diff-filter=A -- <trace>`
  usually names the PR without any field in the trace. The 35 exceptions mean
  this is a fallback, not a guarantee.

## Interactions

- **[RFC-0019](../rfcs/rfc-0019-two-speed-test-gate.md) D1 (ID-266).**
  *(RFC-0019's Phase 0 stopped its selector on 2026-10-04, so the lane is not
  built yet; this interaction binds once ID-266 builds a `merge-candidate`
  lane.)* A
  `merge-candidate` label starts the full CI lane, and **any push clears the
  mark**. A close step that pushes the block after `merge-candidate` is set
  clears it and restarts the wait. Whichever shape is chosen has to order the
  close commit before the mark, or be the thing that sets it.
- **CI on a bot push or label.** A commit pushed with the default `GITHUB_TOKEN` does not
  trigger `ci.yml`, so required checks would never report on the new head. A
  GitHub App or fine-grained token is needed for any shape that commits from a
  workflow. BK-400 records the same constraint for a bot-opened PR. The same
  holds for the label: RFC-0019 D3 states that events caused by `GITHUB_TOKEN`
  start no workflow, and the full lane starts on the `merge-candidate`
  `labeled` event. A close workflow that adds `merge-candidate` with its default
  token leaves the head with no full run and no `merge-gate`, so merge stays
  blocked with nothing reporting why. Shape 2, and any shape that "is the thing
  that sets" the mark, needs the App or fine-grained token for the label too,
  even if it commits nothing.
- **Signed commits.** Master requires signed commits. A commit made through the
  GraphQL `createCommitOnBranch` mutation is signed by GitHub; this is to be
  verified against the ruleset before relying on it.

## Alternatives (advisory, none chosen)

1. **Label-triggered close workflow.** The maintainer adds a label when review
   has converged; a workflow runs `ship-report`, appends the block to every
   `sdd/traces/*.yml` the PR adds, commits through `createCommitOnBranch`, and
   runs `gh pr merge --auto --squash`. The repo already enables auto-merge from
   a workflow after a human approval
   (`.github/workflows/dependabot-auto-merge.yml`). Keeps RFC-0015 D4 intact.
   Costs a token, a full-history checkout for `ship-report` (Evidence above), and
   the RFC-0019 ordering above.
2. **Fold the close into RFC-0019's `merge-candidate`.** The one signal that
   says "this head is final" also writes the block, before the full lane runs.
   Removes a second label, but couples this item to ID-266's phases and needs
   D1's push-clears-the-mark rule to exempt or precede the close commit. Costs
   the same token and checkout as shape 1: a workflow that sets the label with
   `GITHUB_TOKEN` starts no full lane.
3. **Stop committing the block.** The trace keeps `pr: <N>` and the figures are
   derived on demand from it. Removes the close step entirely. Reverses D4's
   "its output is the trace's review block, verbatim", so it needs RFC-0015
   (Draft, tracked as BK-384) amended, and any aggregator that reads committed
   blocks would have to call GitHub instead.
4. **Agent-side only.** `/fix-pr`, on a pass that finds nothing to fix, or a
   dedicated close skill, writes and pushes the block in the same turn, so the
   maintainer's "is it ready?" is answered by a pushed head rather than a second
   request. No CI or token change, but the round trip and the CI re-run remain.
5. **Write the block after the merge.** Listed for completeness: it breaks
   `CLAUDE.md`'s same-PR rule and principle 3 (the repo describes reality at
   every commit), and needs its own PR because master accepts no direct push.
6. **Post-merge snapshot on the PR.** The merge is the convergence signal, so
   nothing has to infer it. A workflow on `pull_request_target: closed` with
   `merged == true` checks out master at full depth, runs `ship-report`, and
   posts the block as a PR comment. The trace carries no `review:` block.
   - *Removes:* the close commit, its CI re-run, the token and signed-commit
     questions (commenting needs only `pull-requests: write` on the default
     token), and the RFC-0019 ordering, since no push happens before the merge.
   - *Gains:* the figures are frozen at merge time, which shape 3 lacks; the
     squash SHA is final, so the block can emit it (D4 withheld it because it
     was ephemeral); the "count excludes the commit that carries it" offset in
     `ship_report.py`'s Bounds disappears.
   - *`pull_request_target` is safe here* because the workflow and script come
     from master and the PR head is only read by `git log` / `git blame`, never
     executed. It also covers fork PRs, where `pull_request` gets a read-only token.
   - *Costs:* amend RFC-0015 D4 ("its output is the trace's review block") and
     `CLAUDE.md` § Trace authoring; the `/ship` skill's close step and
     `_schema.yml`'s `review` key go or become optional. The record moves out
     of git into a comment that anyone with write access can edit or delete,
     and leaves with the repo if it ever leaves GitHub. `ship_report.py`
     needs a post-merge base (Evidence, 2026-10-05) and a way to find the PR
     number (trace field or the squash subject). A `workflow_dispatch` input
     for a PR number covers backfill and a failed run.
   - *Final round count, including conversation rounds (folded in
     2026-10-05).* A purpose of the snapshot is the PR's final review-round
     figures: rounds as submissions (`by_round`) and `review_rounds`, which
     counts review-driven *commits* (`ship_report.py` Bounds). Post-merge,
     both are final. What counts as review feedback is already defined:
     [`/fix-pr` Step 1](../../.claude/skills/fix-pr/SKILL.md) fetches four
     sources and its triage scans all of them, plain conversation comments
     (source 4, `issues/<N>/comments`) included. `ship_report.py` reads inline
     comments grouped by review and uses reviews (source 3) only for
     `submitted_at` (`rounds_with_findings()`), so it misses source 4 entirely
     (the PR #1071 undercount above) and a review whose findings sit only in
     its body. The post-merge run counts rounds over the same four sources;
     reading them after the merge primes no reviewer, since the loop is over.
     Open: `/fix-pr` filters by judgement ("actionable items"), a script needs
     a mechanical rule for which source-4 comments are not rounds (the PR
     author's replies, CI and status bots, the agent's own status comments).
7. **`git notes` on the squash commit.** As 6, but the block goes to
   `refs/notes/review` instead of a comment. Keeps the record in git. Notes
   are not fetched by default, few readers know them, and whether the
   ruleset covers a notes ref is not checked.
8. **Batched backfill PR.** At merge the trace holds a `review: pending`
   marker (honest under principle 3, like `[~]`); a scheduled bot opens one PR
   filling every pending block. Keeps blocks in the tree; needs the App token
   (as BK-400) and adds a recurring PR.
9. **Shape 4 plus a cheap re-run.** The agent pushes the block in the same
   turn; CI path-filters a commit that only touches traces' `review:` keys down
   to the fast jobs; a gate checks the block is present. Changes no RFC; the
   round trip remains but costs seconds instead of a full run.

**Set aside.** A merge queue (see Evidence) and a required check that the
committed block *equals* a fresh run. GitHub review data keeps changing after
the close (late comments, edited reviews), so an equality check flaps; only a
presence check is stable, and shape 9 includes it.

## What would decide

- Whether RFC-0015's graduation (BK-384) keeps the committed block; if not,
  shape 6 dominates shape 3 (same amendment, frozen figures). No code consumes
  the block's figures today (Evidence, 2026-10-05), so dropping it breaks no
  reader; the two guards that validate its shape lose their subject.
- Whether a record outside the tree (a PR comment) is acceptable as the
  durable home; if not, shapes 7 and 8 keep post-merge timing in git.
- Whether ID-266's `merge-candidate` lands; if it does, shapes 1 and 2 are the
  same question asked of one trigger.
- Whether convergence must stay a human judgement. The undercount above says
  the block alone cannot make it today.
