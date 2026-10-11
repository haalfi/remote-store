# Research: does anyone wait on in-progress CI runs?
<!-- doc: repo-only -->

**Date:** 2026-10-11
**Backlog items:** ID-266
**Status:** Answered for 2026-07-11 to 2026-10-11: **parked, re-measure on
2027-01-11** (§ Revisit). Point-in-time snapshot per
[`sdd/000-process.md` § Document types](../../000-process.md#document-types).

## Question

ID-266 would replace the full CI gate on in-progress PR pushes with a fast
lane, keeping the full run on the merge head. How much time could that save,
compared with the time spent waiting on CI at merge, which it leaves alone?

## Answer

**At most 2.9 h in the last 93 days, against 7.5 h of merge waiting that the
fast lane leaves in place.** In-progress waiting barely shows above chance.

| Measure, 2026-07-11 to 2026-10-11 | Value |
| --- | --- |
| `ci.yml` PR runs (completed, cancelled) | 1,318 (1,190, 128) |
| Code-sized run duration (p50, p90) | 4.9 min, 7.6 min |
| Completed runs followed by another push (red) | 987 (35) |
| First-bin excess of next pushes (below) | 36 |
| Upper bound on fast-lane saving (excess × p50) | 2.9 h |
| Merges within 5 min of the final run's end (of 214) | 99 |
| Merge waiting (median, total) | 4.5 min, 7.5 h |

Derivation: `fetch.py tmp/ci-wait`, then
`measure.py tmp/ci-wait 2026-07-11 2026-10-11T12:40:00Z`, both beside this
report. A run is code-sized when it took at least 2.5 min; shorter completed
runs are docs-only fan-outs.

**How waiting is detected.** For each completed run followed by another push
on the branch, the gap from the run's end to that push, in 3-min bins: 119,
92, 75, 62, 75, then falling to 26 by 27–30 min. A push made after waiting for
CI lands in the first bin. Without waiting, the bins decay smoothly, so only
the first bin's excess over the next two bins' mean, 36 pushes, counts as
waiting. Each of those could have been saved at most one code-sized run.

**What a fast lane would cost.** 35 of the 987 in-progress runs were red.
`hatch run fast` selects tests since BK-403, so the per-push full run is what
catches its misses during the loop; a CI fast lane moves them to the close,
where RFC-0019 § Roadmap prices an escape at a fix pass, its re-review and
another full run.

**Bounds.** Waiting is inferred from timestamps, not observed. Runs are
matched to merges by branch name. Earlier history is not used: run time went
from 2.8 min (median, 2026-03) to 8.0 min (2026-07) and back, so only the
recent window describes the repo today.

## Revisit

Re-run both scripts with the window `2026-10-11` to `2027-01-11`. Reopen the
fast lane if the upper bound on its saving reaches the merge waiting in the
same window, or the code-sized median passes 10 min. Otherwise decide against
ID-266.
