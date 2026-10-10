# BK-384 — RFC-0015 is built but unmeasured: three deliveries decide whether it graduates
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

The open half of **BK-378**, which shipped D1 and D4 and is recorded in
`BACKLOG-DONE.md`. Every decision RFC-0015 proposes is now in force in the
skills — D2, D3's worktree half and D5's posting half since #1020, D1 and D4
with BK-378 — so the RFC has, for the first time, a state its acceptance
criterion can be read against. Nothing has read it yet.
**What is owed** is the criterion as § Impact wrote it: three deliveries run
under the rules, pooled, then `rfc-0015-findings.py` over them. Graduate if
(1) the loop-introduced share of must-fix findings from round 3 on is below
50%, (2) the derived trace block draws a finding in at most one round across
the three, and (3) the retraction trigger fires at most once. **One delivery is
one draw and is not the criterion.** With every decision shipped, any of the
three failing sends the RFC back to Draft with the measured figures attached,
not to the ADR with a softened threshold — the branch BK-379's miss was
explicitly *not* on, and this one is.
**Clause 2 is askable for the first time.** It had no referent until
`ship_report.py` generated the block it names; it is read from the per-file
count the script emits about the trace, against the hand-written block's
measured rate of eleven stalenesses across four traces.
**Three things stay held until the measurement, not because they are
undecided.** D3's cap lift — panel composition must not move finding counts
between BK-379's pilot share (RFC-0015 § Pilot result, re-based by BUG-295)
and this sample. D5's stop-rule wiring — its dry run fired
zero times under all three readings, so the constants ship unchanged and there
is no firing to tune them against. D6's deferred half — the whole-file brief
excluding the trace's `review:` key, and a measuring member re-running
`ship-report`.
**Three measured observations BK-378's review surfaced, for whoever takes
this.** First, **the repo's own tooling is unmeasured by the coverage gate**:
`pyproject.toml` scopes coverage to `--cov=remote_store`, and `ci.yml`'s
`tooling-tests` job states it runs without coverage, so no gap in any
`scripts/` gate can reach the 95% floor — those guards' whole value is that
job's pass/fail. Left alone deliberately: extending the scope would put every
existing script under a floor none was written against. Second, **D6's
deferred half has a permission problem**, recorded in the RFC under D6: a
measuring member cannot run `ship-report`, because it is not on `/rvw-pr`'s
by-name allowlist and it reads comment bodies, which that skill's carve-out
excludes. Independent re-derivation needs a mode that reads no feedback.
Third, **the figures D4 does not cover still went stale inside BK-378's own
loop**: the guard count and the scanned-surface count are about the work rather
than about the review, so `ship-report` does not emit them, and both were wrong
at the closing gate because a fix pass moved them after they were last derived.
D4 bounds the review block alone; the rest of a trace and a register entry stays
hand-derived, and re-deriving at the close is a convention nothing enforces.
Whether that gap is worth a gate is this item's to decide — it is the same
failure shape the RFC measured, one surface over.
**The two block-handling defects BK-378's review recorded are shipped** under
[`BK-383`](../BACKLOG-DONE.md), with the duplicate-ID gate ID-257 hands over:
D4 now states that a squash merge retires every SHA in
`review_driven_commits`, so the list is orphaned on arrival whoever wrote it,
and the block carries `pr` as the handle that survives; and `check_traces.py`
refuses the duplicate `review:` key that a second paste leaves behind. What
stays here is the measurement they were blocking, not the mechanism.
**When pooling BK-378's PR, use 5 rounds and 54 findings, not the block's 4
and 41.** Round 5 was the closing exit gates, run analyze-only; its 13
must-fix findings were relayed to the author and fixed without being posted,
so no comment endpoint carries them and `ship-report` cannot see them —
`sdd/traces/bk-378-d1-d4.yml` states this in a note above the block. Pooled at
4/41 that PR contributes a denominator understated by 13 of 54, which is 24%.
Treat the 13 as loop-introduced-detectable-only-at-the-close.
**The sample is the next three deliveries**, whichever they are. `BK-380`
(Python 3.10's security-fix end, dated 2026-10-04) is next in line and could be
the first of them.
**Exit criteria:** RFC-0015 accepted or rejected with its open questions
answered — 1, 3, 4 and 6 remain; 5 was answered by BK-378; 2 is BK-353's line
of work and the RFC already declares it out of scope — and, if accepted,
an ADR amending **ADR-0033/0034/0035/0037**, 0035 because D3 widens the
one-seat trade in its "Every panel carries one measuring member" Decision
bullet, the floor unchanged.

## Correction, 2026-09-28

The sampling rule is stale. Before this conversion's own block was added,
`rg -n '^  pr: 10(2[7-9]|[3-9][0-9])' sdd/traces/` found derived review
blocks for #1027, #1028, #1029, #1032, #1033, #1034, #1036, #1037 and #1038,
all merged after BK-378's #1026, and this body names no rule for which count. Seven of the nine are BK-365 deliveries, and only #1032, the
§ 1 pilot, reached round 3: its block's `by_round` lists four rounds, round 4
carrying a loop-introduced finding, while the other six list at most two
(counted by loading each `sdd/traces/bk-365-*.yml` block). Read rounds from
`by_round`, not `review_rounds`, which the schema defines as review-driven
commits. One instrument limit is missing: #1027's trace says to pool it as
"6 rounds and 89 findings"
(`sdd/traces/bk-383-duplicate-id-gate-and-d4-durability.yml:186`), because some
rounds were posted where `ship-report` does not read. Found by the ADR-0040 § 6
conversion.

## D2 restricted, 2026-10-10

Under BK-418 (trace `sdd/traces/bk-418-claims.yml`), D2's shape (4), narrowing
a claim to what was measured, applies only to behaviour the PR changes. A
claim about behaviour the PR leaves alone, and that the change does not rely
on, takes shape (2)
([`CONTENT-RULES.md` Rule 4](../CONTENT-RULES.md#change-details-what-it-changes)).
D2's five shapes are unchanged in number and text. A delivery sampled here
that merged after this ran D2 in the restricted form, and its shape histogram
should say so.
