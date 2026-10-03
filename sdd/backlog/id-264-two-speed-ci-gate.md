# ID-264 — Every in-progress PR push runs the full pre-merge CI gate
<!-- doc: repo-only -->

Filed from [audit-022](../audits/audit-022-gate-speed-strategies.md), proposal
P3. The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence (by reference)

- **The cost:** audit-022 § M1, the PR #1054 and PR #1058 run counts and
  durations.
- **The proposed shape:** § M1's draft / non-draft / post-merge lanes. The
  PR's draft state is the single selector.

## Prescription (advisory)

A new ADR amending
[ADR-0043](../adrs/0043-tiered-ci-gate-derived-interpreter-set.md): a draft PR
runs a selected lane on every supported interpreter (Stage 2 on the primary,
Stage 1 elsewhere), and a non-draft PR runs today's full `ci.yml` gate.
`ci-full.yml` stays the post-merge backstop.

**Four prerequisites, all from § M1.** The ADR cannot be accepted until each
has an answer:

1. **Conversion must run the full lane.** `ci.yml`'s `pull_request` trigger
   has no `types:`, so marking a draft ready with no new push starts no run.
   Add `ready_for_review`.
2. **Protection must require a check only the full lane produces.** If the
   draft lane also reports `gate`, a selected run satisfies branch protection
   and the merge invariant (one full green run on the final head) breaks.
3. **The draft lane needs a map in CI** (§ M1, "the hardest part"): who
   produces it (the last full lane, or `ci-full.yml` on master), how it reaches
   the PR run with a fail-open fallback when missing or stale, and whether one
   map serves every interpreter. A declared table needs none of this.
4. **`/pr` and `/ship` must use the draft state.** `/pr` opens PRs non-draft
   today, so `/ship` never sees a draft. `/pr` must open as draft and `/ship`
   mark ready at its close. The draft lane keeps every interpreter because
   `/ship`'s § Close each round records an interpreter-specific red that only
   the full matrix showed.

**Dependencies:** BK-398 (a map must exist, and its portability finding
answers prerequisite 3's last question); the `/pr` and `/ship` skill changes
of prerequisite 4.

**Open decision for the ADR:** the primary leg's tier in the draft lane.
Stage 2 keeps ADR-0043's per-PR live-backend guarantee; Stage 1 is cheaper but
leaves a round touching `_s3.py` or `_sftp.py` on moto or in-process SFTP until
the close (§ M1).
