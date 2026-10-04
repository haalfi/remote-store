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

## Decision at v0.33.0, 2026-10-04

Fired at the v0.33.0 release, Phase 0, as the third revisit of the trigger
ID-238 shipped. Successor: **ID-267**.

**Corpus at `39059422c`** (the v0.33.0 release base,
`hatch run report-trace-outcomes`): 356 traces, 5576 steps, 2962 carrying an
explicit `outcome` (53.1%), 358 negative tags (296 `misleading`, 62
`unclear`) across 168 traces and 158 references. Against the baseline above
(310 traces, 306 tags) that is +46 traces and +52 tags (+33 `misleading`, +19
`unclear`). The window is the 60 PRs merged since v0.32.0, counted from
`gh api repos/haalfi/remote-store/releases/generate-notes` with
`previous_tag_name=v0.32.0`. The baseline was re-run, not copied: that commit's
own script over that commit's own traces, in a worktree at `1d43c1b`, returned
310 traces and 306 tags, so the per-reference counts below difference like
against like.

**On Windows the report needs `PYTHONIOENCODING=utf-8`**: under the default
cp1252 console it raises `UnicodeEncodeError` on `→` before printing (BUG-305).

**Selection, by ID-238's rule.** Top row `sdd/BACKLOG.md` at 35 over 358 reads,
so the bar is 1.5 × 35/358 = **14.66%**, from the ratio. Six rows clear it at
`reads` ≥ 20, up from four: `CONTRIBUTING.md` (14/59, 23.7%),
`src/remote_store/backends/_local.py` (7/30, 23.3%),
`sdd/specs/029-async-store-backend-api.md` (5/28, 17.9%), and three at exactly
3/20 (15.0%), clearing by 0.34pp: `docs-src/reference/migration.md`,
`sdd/formal/README.md` and `tests/backends/fixtures/_cassettes.py`. Derived by
filtering every row of the full ranking (`--top 400`, 155 rows) on both
conditions. The threshold is kept: the two new rows enter at the `reads` floor,
and only one of them carries a new tag.

**The interval**, per reference, base → now:

| Reference | Tags | Reads | New tags |
|---|---|---|---|
| `sdd/BACKLOG.md` | 30 → 35 | 302 → 358 | 5 |
| `CONTRIBUTING.md` | 11 → 14 | 48 → 59 | 3 |
| `src/remote_store/backends/_local.py` | 7 → 7 | 23 → 30 | 0 |
| `sdd/specs/029-async-store-backend-api.md` | 5 → 5 | 27 → 28 | 0 |
| `docs-src/reference/migration.md` | 3 → 3 | 18 → 20 | 0 |
| `sdd/formal/README.md` | 2 → 3 | 15 → 20 | 1 |
| `tests/backends/fixtures/_cassettes.py` | 3 → 3 | 20 → 20 | 0 |

Four of the seven carry no new evidence. `migration.md` is selected for the
first time only because its reads reached the floor of 20, with its tags
unchanged. The new tags were found by differencing each reference's tag lines
between the two reports.

**Dispositions.**

- `sdd/BACKLOG.md`: **accept**. The 5 new tags (BK-365, BK-369, BK-377,
  BUG-281, ID-263) are each on an item's prescription or figure that failed
  when re-derived, the class [§ Item authority](../BACKLOG.md#how-this-file-works)
  already marks advisory. Its interval rate is 5/56 (8.9%), below its
  cumulative 9.8%.
- `CONTRIBUTING.md`: **defer**, with ID-258's test unchanged: the disposition
  becomes **act** if § Release still gains tags once ID-254 and ID-255 close,
  and both are still open. Two of the three new tags are on § Release: BK-371
  (`misleading`, Rules 8 and 9 were unwired from the bump table and checklist)
  and BK-375 (`unclear`, stale line coordinates in its own item). The third,
  BK-391, is on § Development Setup. All three were corrected in the PR that
  raised them.
- `sdd/formal/README.md`: **accept**. One new tag, ID-263's, on the open
  decision its own PR closed.
- `src/remote_store/backends/_local.py`, `sdd/specs/029-async-store-backend-api.md`,
  `tests/backends/fixtures/_cassettes.py`: **accept**, carry-over, unchanged
  since ID-258 accepted them.
- `docs-src/reference/migration.md`: **accept**, carry-over: three tags already
  in the corpus at the baseline, selected now on reads alone.

Trace: `sdd/traces/id-259-trace-outcome-revisit.yml`.
