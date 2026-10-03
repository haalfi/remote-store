# BK-400 — The shard durations go stale between manual refreshes, so the primary shards balance on partial data
<!-- doc: repo-only -->

Filed from [audit-022](../audits/audit-022-gate-speed-strategies.md), proposal
P5. The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence (by reference)

- **Coverage of the timing file:** audit-022 § M2, its timed, collected and
  overlap figures and the derivation of each, with its caveat (collected
  locally without the Stage-2 services).
- **Why the file is committed:** § M2. It is in `CODE_PAT`, so a refresh re-runs
  the gate, and every run's shard split can be reproduced from its commit.
- **The duty today:** ADR-0043 § Consequences ("Unchanged duties") and
  [`CI-OPERATIONS.md`](../CI-OPERATIONS.md) § `ci-full.yml`, the
  Durations-refresh duty.

## Prescription (advisory)

`ci-full.yml` already runs the full suite on every master push. Have it
regenerate `.test_durations_pass1` there and open a refresh PR when the result
drifts past a threshold. The file stays committed and `CODE_PAT`-gated. The
alternative, shards fetching durations from the last `ci-full.yml` run, is
rejected in § M2 on cost and reproducibility.

**Open decisions:**

- **The drift threshold**, and which measure it applies to (unknown-test share,
  stale entries, or the shard imbalance itself).
- **The token that opens the PR.** Every workflow here uses only
  `GITHUB_TOKEN` (`rg -n 'secrets\.' .github/workflows`, 2026-10-03), and a PR
  opened with `GITHUB_TOKEN` does not trigger `pull_request` workflows. So the
  refresh PR would not run `ci.yml`, and the audit's "which `CODE_PAT` then
  gates like any other" would not hold. It needs a PAT or GitHub App token,
  or a maintainer push to the PR branch before merge. Found while filing; the
  audit does not name it.
- **Where the duty is recorded:** ADR-0043 is Accepted and is not edited.
  `CI-OPERATIONS.md`'s runbook changes from a manual duty to the automated PR's
  review.
