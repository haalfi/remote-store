# BK-419 — A local gate run has no per-test timeout and no wait deadline, so a stalled suite stalls the session
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and advisory
prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence, 2026-10-09

Run A's figures come from
[`gates.py`](../research/token-usage/gates.py) over that run's transcript, result
[`results/run_a_final_gates.json`](../research/token-usage/results/run_a_final_gates.json):
33 gate tool calls, 31 of them foreground `hatch run all`, median 194 s, 3 at or
over 590 s, one idle stall of 37 min.

The incidents below were read from the Claude Code transcripts on this machine on
2026-10-09, by matching each stalled gate's start time against every other
session's gate tool calls (`gates.py` run over all of this repo's project
folders). Transcripts are deleted after 30 days, so this table is the record:

| When (UTC) | Session | What happened | Another full suite running? |
| --- | --- | --- | --- |
| 2026-10-04 15:54 | BK-397 `/ship` | `hatch run test-cov-s1` returned after 2,364 s | Weak: the same session had started two background gates at 15:39; whether they still ran is not recorded |
| 2026-10-09 09:53 | BUG-280 run A | `hatch run all` cut off at 600 s, then hung about 45 min near 97% of the test step | Yes: a BK-397 worktree session started a background gate at 09:51 |
| 2026-10-09 12:22 | BUG-280 run A | cut off at 600 s | Yes: another session ran `hatch run test-cov-s1` from 12:21 |
| 2026-10-09 13:07 | BUG-280 run A | cut off at 600 s | No: the same session's previous gate (13:02, 176 s) had ended; no other gate call in the transcripts |

The 09:53 stall shows the second failure mode: the tool moved the gate to the
background, the session ended its turn to wait, and with no deadline it stayed
idle until the user asked after 37 min.

## What a fix has to cover

- **A stalled worker.** At 09:53 the xdist workers sat idle at 97% with almost no
  CPU time; with no per-test timeout the run never ends.
- **An unbounded wait.** A backgrounded gate notifies only when it exits, so a
  session waiting on it has no clock of its own.
- **Overlap.** Two of three run-A cut-offs coincide with another session's full
  suite, and two scan batches at once "hung at 97%" in BK-403 Phase 0
  ([trace](../traces/bk-403-rfc-0019-phase-0.yml), the `run_scans.sh` step).
  Nothing serialises full suites across sessions.

Reproducing the overlap deliberately (two `hatch run all` at once with
`RS_TEST_WORKERS=8`) is the first step, and it also says whether a lock alone
would have prevented the 13:07 case, which it would not.
