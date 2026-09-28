# ID-259 — Trace-outcome report revisit at the next release
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Third revisit ticket for the release-anchored trigger ID-238 shipped;
successor to [ID-258](../BACKLOG-DONE.md), which fired at v0.32.0. Per
[`CONTRIBUTING.md` § Release](../../CONTRIBUTING.md#release) Phase 0, each release
reads `hatch run report-trace-outcomes` and closes the open revisit ticket.
This item is the pin that makes the ticket findable.
**The pin lives here, not in the checklist.** `CONTRIBUTING.md` is a published
surface, so [CONTENT-RULES Rules 1 and 5](../CONTENT-RULES.md#rules) bar a tracker
ID from it (`check_no_tracker_refs` enforces this, and caught the first attempt).
The checklist therefore describes the behaviour and points here; this file is
the single place that says *which* ticket is open — the same split
`sdd/formal/README.md` uses to pin ID-150. **Separate from ID-150 for that
reason**: two published documents pin two different tickets, with different
triggers and different exit sets, and each mints its own successor. One merged
ticket would falsely close one trigger with the other.
**Record at the revisit:** the corpus totals (the baseline the following
release differences against — the report keeps no history); the references
selected (top-ranked row, plus any row with `rate` ≥ 1.5× the top row's at
`reads` ≥ 20 — a fitted threshold, re-check it rather than inherit it); and per
selected reference one of **act** (file work against it), **defer** (leave it,
say why), or **accept** (the tags are exposure, not a defect).
**Baseline to difference against**, measured at `1d43c1b` (the v0.32.0
release base): 310 traces, 306 negative tags (263 `misleading`, 43 `unclear`),
`sdd/BACKLOG.md` top-ranked at 30 over 302 reads (9.9% as the report displays
it; compute the bar from 30/302, not from the rounded figure — ID-258 did the
latter and review caught it). The previous two
baselines were 302 traces / 284 tags at `6cd170c` and 270 / 207 at `4076ed7`,
with the same top row at 9.8% and 9.3%; ID-258's close note carries both
differences and how each selected reference was dispositioned.
**Read the interval, not only the cumulative table.** ID-258 selected the same
five references as ID-249, and three of them had gained no tag at all in
between — an absolute-count ranking over a cumulative corpus re-selects on
standing totals, so a reference can be selected twice on the strength of
evidence already dispositioned. Difference the per-reference counts against the
baseline above before dispositioning, and say which selections are new
evidence and which are carry-over.
**Exit criteria:** decision logged here, then the successor ticket opened and
its ID named in this item's close note.

## Correction, 2026-09-28

"Two published documents pin two different tickets" is false: both pins sit in
repo-only files, `sdd/formal/README.md` (ID-150) and `sdd/BACKLOG.md` (this
item), while the published `CONTRIBUTING.md` pins none. The trigger has not
fired: `git ls-remote --tags origin` shows no `v0.33.0`, and `pyproject.toml`
reads `0.32.0`. For the difference at release, `hatch run report-trace-outcomes`
today reports 335 traces and 331 negative tags (280 `misleading`, 51
`unclear`), `sdd/BACKLOG.md` top at 33 over 342 reads. Found by the ADR-0040 § 6 conversion.
