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

- **What reads a committed `review:` block.** The `*.py` files naming
  `review_rounds` or indexing a `review` key are three (Grep over the repo):
  - `sdd/rfcs/rfc-0015-rounds.py`, the derivation of RFC-0015 Table 1. Its
    `RX` anchor admits the two-space indent so it reads `review_rounds`
    *inside* the block, and its docstring names the "after" population
    emptying as the failure that widening prevents.
  - `scripts/ship_report.py`, the writer; `trace_block()` keeps the field at
    that indent so the rounds script still reads it.
  - `tests/scripts/test_ship_report.py`,
    `test_the_legacy_corpus_reads_identically_under_the_anchor`, which reads
    every committed block and asserts the anchor agrees with it.

  Two guards check its shape: `check_traces.py` validates it against
  `_schema.yml`, and `_trace_corpus.py` rejects the duplicate `review:` key a
  second paste leaves. Any shape that stops committing the block takes every
  later trace out of Table 1's "after" population.
- **Correction to "Why it cannot be produced earlier":** "the branch SHAs it
  lists stop resolving at the squash merge" is false for one measured case.
  `2a174de`, the first SHA in `sdd/traces/bk-378-d1-d4.yml`'s
  `review_driven_commits` (PR #1026, squash-merged), resolves through the
  commits API (`get_commit`, run 2026-10-05). One sample. What holds is the
  weaker claim, held only by `ship_report.py`'s Bounds (lines 118-121): the
  SHAs are not *reachable from master*. The refuted "stop resolving" claim
  also sits in four places outside this dossier (Grep, 2026-10-05):
  - RFC-0015 D4, `rfc-0015-ship-two-surfaces.md:596` ("It does not buy SHAs
    that resolve") and :613 ("During the loop the branch SHAs resolve");
  - `sdd/traces/_schema.yml:234-236` ("the SHAs stop resolving at the merge");
  - `_schema.yml:312-313`, `pr` as "the only field here that still resolves
    once the PR is merged";
  - `scripts/ship_report.py:447-448`, the same sentence in `trace_block()`.

  They stay as written until whoever acts on ID-268 corrects them, with a
  second sample first. Shape 6's *Gains* does not rest on this claim: the
  squash SHA D4 withheld is `merge_commit_sha` on an *open* PR, GitHub's
  ephemeral test merge, which is a different commit.
- **The script runs post-merge with one caveat, read from the code.**
  `collect()` takes `head` from the PR's `head.sha`, which stays the last
  branch head after the merge, and `ensure_commit()` fetches it by SHA. The
  range is `origin/<base>..head`. Under a squash merge that range is still the
  branch's commits. Under a merge commit (`allow_merge_commit` is enabled per
  the Bounds) head becomes an ancestor of master, the range is empty, and
  `review_rounds` reads 0 with no error. A post-merge run needs the base pinned
  to the merge commit's first parent.
- **The trace→PR link is derivable from git.** Of the 285 commits on master
  that add a trace, all 285 end their subject with `(#NNNN)`
  (`git log --diff-filter=A --format=%s origin/master -- 'sdd/traces/[!_]*.yml'`
  in a full clone, matched against `\(#\d+\)$`, run 2026-10-05). It is a
  convention, not a guarantee: nothing enforces the subject.

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
   - *Costs, shared with shape 3 (and 7):* every RFC-0015 clause that assumes
     the block sits in the trace is amended. Found in
     `sdd/rfcs/rfc-0015-ship-two-surfaces.md`:
     - **D4**, "its output is the trace's review block".
     - **D1's mechanism**: the block pasted under one `review:` key, the
       boundary `check_traces.py` / `_trace_corpus.py` guard.
     - **D6's deferred half**: the whole-file brief excludes the trace's
       `review:` key.
     - **The acceptance criterion's clause 2**, BK-384's graduation test: "the
       derived trace block draws a finding in at most one round". Without the
       block the clause has no referent.
     - **Table 1's derivation**, `rfc-0015-rounds.py`, which loses every later
       trace from its "after" population (Evidence, 2026-10-05).

     Outside the RFC: `CLAUDE.md` § Trace authoring and the `/ship` close step.
     `pr` exists only inside the `review:` block and the schema's top level is
     `additionalProperties: false` (`_schema.yml:27`), so the trace keeps no
     PR number unless a top-level field is added; the squash subject is the
     alternative (Evidence, 2026-10-05). The record moves out of git into a
     comment that anyone with write access can edit or delete, and leaves with
     the repo if it ever leaves GitHub. `ship_report.py` needs a post-merge
     base (Evidence, 2026-10-05). A `workflow_dispatch` input for a PR number
     covers backfill and a failed run.
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
     `/fix-pr` filters sources 2–4 by judgement ("actionable items"), so the
     script needs to know which comments that judgement counted. **Proposed
     (maintainer, 2026-10-05): `/fix-pr` records it while fixing.** Inline
     findings already leave a record: their replies carry the prefix
     `fnd.triage()` parses ("Fixed in", "Filed as", "Refuted"). Review bodies
     and conversation comments (sources 3 and 4) get no defined reply. Each
     pass would post one conversation comment carrying a machine-readable tag
     per such comment it treated as review feedback: its id, a findings count,
     and, when the count is above zero, a verdict in `triage()`'s vocabulary
     (`must-fix` / `filed` / `refuted` / `unknown`). Zero is carried by the
     count alone; the vocabulary is not extended.
     - *Clean rounds are tagged by their author, not by a fix pass.* A clean
       round gets no fix pass (`/ship`: "a clean round needs no successor",
       `ship/SKILL.md:625-626`), and `/ship`'s closing unprimed pass is one by
       construction. So `/rvw-pr` Step 4 puts the round marker, with findings
       count 0, in its own body-only review. A fix pass only tags feedback
       that `/rvw-pr` did not post: human reviews, other bots, conversation
       comments.
     - *Counting:* a source-3/4 comment is a round iff a tag or a `/rvw-pr`
       round marker names it. A review that already has inline findings is
       one `by_round` entry and is not tagged, so no round counts twice.
     - *Exclusion rule, still needed:* the tag comments and shape 6's own
       snapshot comment carry a skip marker, distinct from `/rvw-pr`'s round
       marker, and both `/fix-pr`'s triage and the script skip comments
       carrying it. Login cannot separate the rest: `/rvw-pr` posts with the
       owner token, so reviewer and author share one.
     - *Residual:* feedback that neither `/rvw-pr` posted nor a fix pass
       tagged stays untagged. The script reports untagged, unmarked
       source-3/4 comments as an `untagged` count. That count is an upper bound on missed feedback, not a count of
       it, because author replies and status comments land there too.

     Costs amendments to `/fix-pr`, to `/ship`'s "Close each round" (it runs
     `/fix-pr`'s mechanics inline rather than invoking it, `ship/SKILL.md:531-536`)
     and to `/rvw-pr` Step 4, plus a tag and marker format all three and the
     script parse.
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

- Whether RFC-0015 is amended to drop the committed block. BK-384's
  graduation test (acceptance clause 2) presupposes the block, so graduating
  as written keeps it; dropping it amends that clause, D1, D4, D6 and Table
  1's derivation (shape 6, *Costs*). If that amendment is taken, shape 6
  dominates shape 3 (same amendment, frozen figures).
- Whether a record outside the tree (a PR comment) is acceptable as the
  durable home; if not, shapes 7 and 8 keep post-merge timing in git.
- Whether ID-266's `merge-candidate` lands; if it does, shapes 1 and 2 are the
  same question asked of one trigger.
- Whether convergence must stay a human judgement. The undercount above says
  the block alone cannot make it today.
