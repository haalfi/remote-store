# BK-332 — Schedule the custom-backend rehearsal
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 3](../BACKLOG.md#users-succeed-unaided) by the ADR-0040 § 3
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Effort splits: S to define the rehearsal, M per run.
"Build a backend against the guide, from scratch, without help" runs today
only as a side effect of guide PRs. Its output is a list of places the guide,
the contract, or the conformance suite failed the builder — BK-324 and BK-325
are one run's findings (PR #932), which is the argument for scheduling it
rather than running it by accident.
**Cadence:** once per minor release, or after any change to the `Backend` ABC
or the conformance suite, whichever comes first — the two events that can
invalidate the guide, per [`DRIFT-RULES.md` Rule 9](../DRIFT-RULES.md#period).
**Evidence level, stated because the ranking flatters it:** n = 1. The claim
that rehearsal has the best findings-per-unit-noise rests on that single run.

## Re-measured, 2026-09-27

Still n = 1. `rg -n -i rehearsal sdd/traces sdd/BACKLOG-DONE.md` finds no
recorded run; its one hit is the ADR-0040 § 3 conversion's own trace, which
names the rehearsal's placement. The PR #932 run's record is
`sdd/traces/bk-320-custom-backend-guide-refresh.yml`, and BK-324, one of its
two findings, is done in `BACKLOG-DONE.md`. Found by the ADR-0040 § 3
conversion.
