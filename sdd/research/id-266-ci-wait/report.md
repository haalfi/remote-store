# Research: does anyone wait on in-progress CI runs?
<!-- doc: repo-only -->

**Date:** 2026-10-11
**Backlog items:** ID-266
**Status:** Answered for 2026-07-11 to 2026-10-11; ID-266 stays open.
Point-in-time snapshot per
[`sdd/000-process.md` § Document types](../../000-process.md#document-types).

## Question

ID-266 would replace the full CI gate on in-progress PR pushes with a fast
lane, keeping the full run on the merge head. How much time could that save,
compared with the time spent waiting on CI at merge, which it leaves alone?

## Answer

**At most 8.7 h of the waiting that PR timestamps show in the last 93 days,
against 7.5 h of merge waiting that the fast lane leaves in place.** Waits the
timestamps cannot show are not bounded (§ Bounds). The bound counts each waited-on run at its full
duration, so the fast lane's own run time and the escapes it moves to the close
both come off it.

| Measure, 2026-07-11 to 2026-10-11 | Value |
| --- | --- |
| `ci.yml` PR runs (completed, cancelled) | 1,318 (1,190, 128) |
| Code-sized run duration (p50, p90) | 4.9 min, 7.6 min |
| Completed runs followed by another push (red) | 987 (35) |
| Followed by a push: first-bin excess, bound | 36, 4.0 h |
| Followed by any PR activity: first-bin excess, bound | 96, 8.7 h |
| Merges within 5 min of the final run's end (of 214) | 99 |
| Merge waiting (median, total) | 4.5 min, 7.5 h |

Derivation: `fetch.py tmp/ci-wait 2026-07-11`, then
`measure.py tmp/ci-wait 2026-07-11 2026-10-11T12:40:00Z`, both beside this
report. A run is code-sized when it took at least 2.5 min; shorter completed
runs are docs-only fan-outs.

**How waiting is detected.** For each completed run, the gap from its end to
the branch's next event, in 3-min bins. Without waiting, the bins decay
smoothly; a session that waited for the run acts right after it ends, so only
the first bin's excess over the next two bins' mean counts as waiting. Two
next events are measured:
- **The next push:** bins 119, 92, 75, 62, 75, excess 36. This misses a
  `/ship` round, which reads CI and replies to threads, then reviews again
  before it pushes (`.claude/skills/ship/SKILL.md` § Close each round).
- **The first push, comment, review reply or review**, on PRs merged in the
  window, up to the merge: bins 170, 85, 64, 39, 38, excess 96. 539 of the
  1,233 runs had activity before they ended, so they fall outside the bins.

Each excess event saves at most its run's duration. The bound sums the
durations of the longest first-bin runs, as many as the excess, so no choice of
which runs waited can exceed it.

**What a fast lane would cost.** 35 of the 987 in-progress runs were red.
`hatch run fast` selects tests since BK-403, so the per-push full run is what
catches its misses during the loop; a CI fast lane moves them to the close,
where RFC-0019 § Roadmap prices an escape at a fix pass, its re-review and
another full run.

**Bounds.** Waiting is inferred from timestamps, not observed. Reading CI
leaves no timestamp, so two waits are not counted: one that ends in nothing on
the PR, and one that follows activity during the run, such as a reply posted
before the run ends and then a wait before the next push. Runs are matched to merges and activity by branch name.
Earlier history is not used: the code-sized median was 2.8 min in 2026-03 and
8.0 min in 2026-07 (`measure.py tmp/ci-wait 2026-03-01 2026-04-01T00:00:00Z`
and `… 2026-07-01 2026-08-01T00:00:00Z`), so only the recent window describes
the repo today.

## Re-running

`fetch.py <dir> <since>` fetches PR activity for PRs merged since `<since>`;
`measure.py <dir> <since> <until>` reports the window.
