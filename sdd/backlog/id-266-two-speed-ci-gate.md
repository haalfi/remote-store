# ID-266 — Every in-progress PR push runs the full pre-merge CI gate
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
runs a selected lane on every supported interpreter (Stage 1 on the
non-primary legs; the primary leg's tier is the open decision below), and a
non-draft PR runs today's full `ci.yml` gate.
`ci-full.yml` stays the post-merge backstop.

**Four prerequisites, all from § M1.** The ADR cannot be accepted until each
has an answer:

1. **Conversion must run the full lane.** `ci.yml`'s `pull_request` trigger
   has no `types:`, so marking a draft ready with no new push starts no run.
   A `types:` key replaces GitHub's defaults rather than extending them, so
   the key must restate them: `types: [opened, synchronize, reopened,
   ready_for_review]`. The lane split must also hold for `reopened`, which
   can fire on a draft.
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

**Dependency:** BK-403 (a map must exist, and its portability finding
answers prerequisite 3's last question).

**Prerequisite 3, answered for `pytest-testmon` (2026-10-03):** one map does
not serve every interpreter. testmon discards a map on any change of Python
patch version or package minor version, and CI installs unpinned
([`research-bk-403-testmon-poc.md`](../research/research-bk-403-testmon-poc.md),
Appendix C). The PoC's answer to the item as a whole is "not now"; it is
revisited on BK-403's condition (local rounds still a measured bottleneck
after BUG-301 and BK-401).

**In this item's scope:** prerequisite 4's `/pr` and `/ship` skill changes.
No other item delivers them. The `/ship` edit shares
`.claude/skills/ship/SKILL.md` with BK-404, whose open decision includes
whether `/ship` runs the selected target before round pushes; sequence the
two edits together.

**Open decision for the ADR:** the primary leg's tier in the draft lane.
Stage 2 keeps ADR-0043's per-PR live-backend guarantee; Stage 1 is cheaper but
leaves a round touching `_s3.py` or `_sftp.py` on moto or in-process SFTP until
the close (§ M1).
