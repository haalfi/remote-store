# ID-267 — Trace-outcome report revisit at the next release
<!-- doc: repo-only -->

The index entry in [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead)
holds the current diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Fourth revisit ticket for the release-anchored trigger ID-238 shipped;
successor to [ID-259](id-259-trace-outcome-revisit.md), which fired at v0.33.0.
Per [`CONTRIBUTING.md` § Release](../../CONTRIBUTING.md#release) Phase 0, each
release reads `hatch run report-trace-outcomes` and closes the open revisit
ticket. This item is the pin that makes the ticket findable; the checklist
describes the behaviour without naming it, since `check_no_tracker_refs` bars
tracker IDs from that published file.

**Record at the revisit:** the corpus totals (the baseline the following
release differences against, since the report keeps no history); the
references selected (top-ranked row, plus any row with `rate` ≥ 1.5× the top
row's at `reads` ≥ 20, computed from the top row's ratio and not its rounded
percentage); and per selected reference one of **act** (file work against it),
**defer** (leave it, say why), or **accept** (the tags are exposure, not a
defect). The threshold is fitted: re-check it against the full ranking rather
than inherit it.

**Difference the interval before dispositioning.** The ranking is cumulative,
so a reference can be re-selected on tags an earlier revisit already
dispositioned; ID-259 found four of its seven selections carried no new tag.
Re-run the baseline rather than copying the table below, by running the
release-base commit's own script over its own traces in a worktree, and check
it reproduces these totals before differencing against it.

**Baseline**, measured at `39059422c` (the v0.33.0 release base): 356 traces,
358 negative tags (296 `misleading`, 62 `unclear`), `sdd/BACKLOG.md`
top-ranked at 35 over 358 reads, so the bar was 1.5 × 35/358 = 14.66%. Selected
then, as tags over reads: `CONTRIBUTING.md` 14/59,
`src/remote_store/backends/_local.py` 7/30,
`sdd/specs/029-async-store-backend-api.md` 5/28, and
`docs-src/reference/migration.md`, `sdd/formal/README.md` and
`tests/backends/fixtures/_cassettes.py` at 3/20 each. ID-259's close note
carries the interval and how each was dispositioned.

**The one standing test:** `CONTRIBUTING.md` was deferred twice on § Release's
recurrence. It becomes **act** if § Release still gains tags once ID-254 and
ID-255 have closed.

**On Windows**, run the report with `PYTHONIOENCODING=utf-8` until BUG-305
closes; the default cp1252 console raises `UnicodeEncodeError` before printing.

**Exit criteria:** decision logged here, then the successor ticket opened and
its ID named in this item's close note.
