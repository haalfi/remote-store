# ID-268 — Closing a PR needs a manual agent round trip before it can merge
<!-- doc: repo-only -->

Filed at the maintainer's request after PR #1071 (2026-10-04). The index entry
holds the current diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)). **No alternative is
chosen.** The open decision is which of the shapes below to build, or none.

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
- **The script needs no local state beyond the repo.** `scripts/ship_report.py`
  reads GitHub through `gh api` only (line 206), so it can run in a GitHub
  Actions job.
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

## Interactions

- **[RFC-0019](../rfcs/rfc-0019-two-speed-test-gate.md) D1 (ID-266).** A
  `merge-candidate` label starts the full CI lane, and **any push clears the
  mark**. A close step that pushes the block after `merge-candidate` is set
  clears it and restarts the wait. Whichever shape is chosen has to order the
  close commit before the mark, or be the thing that sets it.
- **CI on a bot push.** A commit pushed with the default `GITHUB_TOKEN` does not
  trigger `ci.yml`, so required checks would never report on the new head. A
  GitHub App or fine-grained token is needed for any shape that commits from a
  workflow. BK-400 records the same constraint for a bot-opened PR.
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
   Costs a token and the RFC-0019 ordering above.
2. **Fold the close into RFC-0019's `merge-candidate`.** The one signal that
   says "this head is final" also writes the block, before the full lane runs.
   Removes a second label, but couples this item to ID-266's phases and needs
   D1's push-clears-the-mark rule to exempt or precede the close commit.
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

## What would decide

- Whether RFC-0015's graduation (BK-384) keeps the committed block; if not,
  shape 3 dominates.
- Whether ID-266's `merge-candidate` lands; if it does, shapes 1 and 2 are the
  same question asked of one trigger.
- Whether convergence must stay a human judgement. The undercount above says
  the block alone cannot make it today.
