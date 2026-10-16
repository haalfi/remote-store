# Research: Two Kernel Deliveries Measured — Long Loops on Large Diffs

**Date:** 2026-10-16
**Backlog items:** BK-389 (PR #1127, with the RFC-0021 detour BK-432, PR #1130) and BK-394 (PR #1144); evidence for BK-431's keep-or-drop decision, closed as keep in the same PR.
**Status:** Measurement complete for the two deliveries. Point-in-time snapshot per [`sdd/000-process.md` § Document types](../000-process.md#document-types). It follows [`research-token-spend-means.md`](research-token-spend-means.md) and [`token-usage/report.md`](token-usage/report.md), which stay as written; where a figure here re-derives one of theirs, both are given.
**Related:** proposal 6 of [`research-token-spend-means.md` § 6](research-token-spend-means.md#6-proposals) asked for this measurement; [ADR-0045](../adrs/0045-close-on-a-check-that-can-fail.md) says a spend figure is judged with the defects shipped.

## TL;DR

Two `/ship` deliveries on the contract kernel cost 98.25 M units (BK-389) and
57.22 M (BK-394), about $227 and $132, and 72 to 92% of it was the review loop.
Neither loop converged: every one of BK-389's 16 rounds and BK-394's 9 posted
findings, and both closed on a maintainer's waiver. A round cost 4.5 to 5.6 M
units, about twice run B's 2.4 M, on larger diffs and a main context that kept
growing; the cost did not scale with the diff's file count or its content (§ 2).

1. **The loop is still where the cost is**, and more content makes a round cost
   more, far less than in proportion: about six times run B's changed lines
   cost about twice its units per round, because a pass re-reads the PR mostly
   from cache (§ 2, § 3). The main session carries every fix.
2. **BK-431's smaller reviewer input held in every pass.** All 82 passes ran as
   `reviewer` and opened at 19.5k to 34.6k tokens, against run B's 42.9k to
   43.9k; the prefix fell from 40.6% to 16 to 32% of a pass's context. It did
   not make passes cheaper, because the PR's own files took the room.
3. **These runs cannot show that run B's saving recurs.** Proposal 6 asked for
   two more `/ship` deliveries, one of them drawing prose findings only, to
   decide that. These two have no A run and both drew code findings, and no
   further delivery is measured.
4. **The largest cut, a three-round cap, trades units for unfixed findings**
   (§ 7): BK-389's rounds 4 onward held 80% of its units and posted 94 of its
   120 findings, an upper bound on what a cap would leave unfixed. What a cap
   would have cost instead is not measured. Reviewing only what changed since
   the last round targets the findings fixes caused, and a fresh session is
   not shown to save.

## Context

The delivery measured was `/ship BK-389`, the RFC-0017 kernel, the next one run
on the means of [`research-token-spend-means.md`](research-token-spend-means.md).
The run did not stay one delivery. After twelve review rounds its maintainer
paused it for a concept change, RFC-0021 (PR #1130, built and reviewed in its
own sessions), then resumed #1127 against it for four more rounds. BK-394, the
Memory backend on the kernel, followed as a second `/ship` with a context prompt
in the main checkout. This record measures all three PRs and keeps them apart.

**Sourcing note.** Every figure comes from the transcript snapshots an observer
session took during the runs, read by
[`token-usage/deliveries.py`](token-usage/deliveries.py) through `tokkit.py`'s
own parser, and from GitHub's review records through `scripts/ship_report.py`.
Citations in square brackets name a field of
[`results/deliveries_bk389_bk394.json`](token-usage/results/deliveries_bk389_bk394.json)
as `[delivery: field]`. Units weight tokens by price, dollars use the fitted
prices of [report § 1](token-usage/report.md#1-calibration). Which session
parts served which PR is a reading of the transcripts, given in § Reproducing.

## 1. What each delivery cost

**BK-389 cost 98.25 M units over six sessions and BK-394 57.22 M over two; the
RFC-0021 detour cost 28.77 M more, which BK-389's own figure leaves out.**
Run B, re-derived with today's kit, cost 15.00 M.

| | BK-389 #1127 | RFC-0021 #1130 | BK-394 #1144 | run B #1113 |
| --- | ---: | ---: | ---: | ---: |
| Units | 98.25 M | 28.77 M | 57.22 M | 15.00 M |
| Est. $ | 226.97 | 66.46 | 132.17 | 34.65 |
| Session parts | 6 | 2 | 2 | 2 |
| Files the PR changes | 91 (37 through round 12) | 56 | 94 | 21 |
| Lines changed, added plus removed | 18,949 (9,110 through round 12) | 7,191 | 8,479 | 1,452 |
| Orient + plan | 1.7% | 0.3% | 5.4% | 7.2% |
| Build (to PR open) | 6.9% | 10.5% | 22.9% | 9.8% |
| Review loop (after PR open) | 91.5% | 89.2% | 71.8% | 83.0% |
| Largest main context | 833k | 699k | 810k | 444k |

From [`units_m`, `usd_estimate`, `sessions`, `changed_files`, `phases_pct`,
`max_main_ctx_k`] per delivery; the lines row is `git diff --shortstat` over
each PR's squash commit on master (`45132599a`, `bc03b75e2`, `b7deb551c`,
`25ac75a3f`, each against its parent). Phases are cut as `tokkit.py report --pr` cuts
them: BK-389 at call 44 (plan approval) and 161 (PR open), BK-394 at 43 and
171, run B at 43 and 93 [`build_cuts`]. Run B's 43 is the current kit's cut;
`report.md` § Run B gives 44 calls and 1.11 M from the kit before BK-424, here
1.08 M. RFC-0021 was concept work led by dialogs, so its cut at the first
answered dialog marks no real plan, and its first two rows mean little.

- **#1127 contains #1130.** RFC-0021 was merged into BK-389's branch as one
  commit and landed with it, which is why #1127 changes 91 files; the two PRs'
  costs do not overlap, since each session part is counted once. Before that
  commit, through its round 12, #1127 changed 37 files and 9,110 lines
  (`git diff --shortstat origin/master...bc03b75e2^1`, the branch head below
  #1130's squash commit; `changed_files` is the PR's list when measured).
- **What #1127's content was.** Of its 18,949 changed lines, 7,906 (42%) are
  under `sdd/`, 6,149 (32%) under `tests/`, 1,876 (10%) the generated sync
  twin under `src/remote_store/_kernel/_sync/`, and 3,018 (16%) everything
  else (`git diff --shortstat 45132599a~1 45132599a -- <path>` per path, the
  rest by difference).
- **Two session parts are not counted in any delivery.** A subagent in
  BK-389's last session opened and fixed PRs #1142 and #1143 (BUG-326,
  BUG-327) for 2.99 M, and the RFC-0021 session's resume on 2026-10-15
  reviewed PR #1131 (BK-435) for 2.41 M in 13 calls after two idle days
  [other].
- **Not split:** BK-389's last session also relayed the BUG-326 work in its
  main context, a few calls left inside BK-389.

## 2. The review loops

**Neither loop converged: no round of either PR posted zero findings, and both
closed on the maintainer's waiver.** BK-389 posted 120 findings over 16 rounds
and BK-394 60 over 9 [`findings_posted`, `rounds`]; a CodeQL submission of 19
refuted findings on #1127 is not counted [`bot_submissions_ignored`].

| | BK-389 | RFC-0021 | BK-394 | run B |
| --- | ---: | ---: | ---: | ---: |
| Rounds | 16 | 13 | 9 | 5 |
| Findings posted | 120 | 76 | 60 | 17 |
| Units in the rounds | 89.06 M | 24.71 M | 40.62 M | 12.14 M |
| of it the main session | 50.90 M | 19.14 M | 19.13 M | 6.95 M |
| Loop units before the first round | 0.81 M | 0.95 M | 0.44 M | 0.31 M |
| Units per round | 5.57 M | 1.90 M | 4.51 M | 2.43 M |
| Units per finding | 0.74 M | 0.33 M | 0.68 M | 0.71 M |
| Main context entering the first and last round | 219k, 733k | 329k, 435k | 91k, 736k | 104k, 360k |

From [`rounds`, `findings_posted`, `review_loop_rounds_units_m`,
`review_loop_before_first_round_units_m`, `units_m_per_round`,
`units_m_per_finding`]; the main-session row sums `rounds[].main_units_m`. The
rounds and the row before them add up to the review-loop phase of § 1 within
0.01 M. A round runs from the main-session call that spawned its passes up to
the call that spawned the next round's, so its cost includes the fix after it; loop cost outside
every such span, a session's calls before its first round and a subagent that
is no round's pass, joins the latest round spawned before it, so a resume
session's opening calls count toward the round they fix.
Run B's figures match `report.md` § Run B; its sixth submission, posted after
the run, is counted outside [`findings_outside_measured_sessions`], as are
two findings on #1130 posted from a session outside the delivery.

- **After round 4, only one of BK-389's rounds posted fewer than six.** By round:
  8, 7, 11, 1, 7, 6, 7, 8, 10, 11, then 7 and 7 before the RFC-0021 pause, and
  11, 10, 3 and 6 after it [`BK-389.rounds[].findings_posted`]. 66 of the 120
  are tagged loop-introduced, caused by an earlier fix in the same loop
  (summed from `hatch run ship-report 1127`'s origin column, the CodeQL round
  left out). The maintainer waived the final round, as the trace records.
- **BK-394 hit the soft ceiling and the divergence check.** Its rounds posted
  3, 2, 13, 8, 13, 12, 5, 3 and 1 [`BK-394.rounds[].findings_posted`]; 21 of
  the 60 are loop-introduced (`hatch run ship-report 1144`). At round 5 the
  session asked how to go on past the soft ceiling of five, and at the closing
  round the divergence check fired on a content guard that round 1 had added
  and four rounds had patched; it was re-scoped, and the last one-docstring fix
  was closed by waiver (the PR's decision log).
- **Session breaks reset the main context; nothing else did.** BK-389's rounds
  ran in four sessions, and each started lower than the last one ended: 638k
  to 378k, 594k to 443k, 559k to 504k [`BK-389.rounds[].main_ctx_k`]. BK-394
  ran all nine rounds in one session, from 91k to 736k. No session compacted
  except one RFC-0021 session, once.
- **A resume cost one to two rounds.** After each of BK-389's three session
  breaks, the new session's calls before its first round cost 3.56 M, 5.26 M
  and 7.06 M, and joined rounds 7, 10 and 12, the last round before each break
  [`BK-389.rounds[].opening_units_m`]. A round before the breaks cost 4.07 M
  without them (below). That cost carries the round's fix, which no figure here
  separates from re-orienting, and the third also holds the last session's
  re-derivation of the kernel against RFC-0021. Round 12 also took a 3.11 M
  subagent that was no review pass [`BK-389.rounds[].other_units_m`].
- **A round costs more on more content, but far less than in proportion.**
  Against run B's 1,452 changed lines and 2.43 M per round: BK-394's 8,479
  lines (5.8 times) cost 4.51 M per round (1.9 times); BK-389's rounds 1 to 12,
  on at most 9,110 lines (6.3 times), cost 4.07 M each (1.7 times) without the
  18.99 M of opening and subagent cost that joined rounds 7, 10 and 12; and its
  rounds 13 to 16, on 18,949 lines (13 times) and with none of that cost,
  cost 5.30 M each (2.2 times). Doubling BK-389's content raised its cost per
  round 1.3 times (summed from `BK-389.rounds[]`'s `units_m`,
  `opening_units_m` and `other_units_m`; the lines as in § 1). With the
  opening cost left in, rounds 1 to 12 cost 5.66 M each. RFC-0021's 7,191
  lines cost less per round than run B's, 1.90 M, because seven of its 13
  rounds ran one narrow pass (below): how a round reads the content counts as
  much as how much there is. Per finding, BK-389 cost about what run B did (0.74 M
  against 0.71 M) and BK-394 a little less (0.68 M), though they drew about
  twice run B's findings per round (7.5 and 6.7 against 3.4).

**RFC-0021's loop was cheap per round because its rounds were narrow.** Seven of
its 13 rounds ran a single pass, three of them narrow checks of one commit, and
its passes cost a median 0.30 M against BK-389's 0.81 M [`RFC-0021.rounds`,
`pass_summary`]. Its main context still reached 699k [`max_main_ctx_k`].

## 3. The review passes

**Every pass ran as the `reviewer` agent on BK-431's smaller input, and a pass
on BK-389 or BK-394 still cost about twice run B's, because the PR filled the
context the prefix gave up.** Per pass, the record kept calls, findings handed back and the
files read whole [`passes`]; this table summarises them.

| | BK-389 | RFC-0021 | BK-394 | run B |
| --- | ---: | ---: | ---: | ---: |
| Passes (as `reviewer`) | 42 (42) | 20 (20) | 20 (20) | 11 (0) |
| First context | 19.6k to 33.3k | 19.7k to 20.5k | 19.5k to 34.6k | 42.9k to 43.9k |
| Calls, median | 39 | 21 | 51.5 | 25 |
| Units per pass, median | 0.81 M | 0.30 M | 0.94 M | 0.43 M |
| Units of all passes | 35.04 M | 5.58 M | 21.49 M | 5.19 M |
| Files read whole, median | 14.5 | 3 | 10 | 3 |
| Context: prefix | 16.2% | 32.1% | 17.2% | 40.6% |
| Context: process files | 7.2% | 13.6% | 7.9% | 13.0% |
| Context: the PR | 51.6% | 21.9% | 44.2% | 19.0% |
| PR tokens carried per pass, median | 2.95 M | 0.35 M | 3.30 M | 0.51 M |
| PR tokens carried by all passes | 127.85 M | 8.00 M | 81.06 M | 6.40 M |

From [`pass_summary`]. Files read whole are the checkout's; a spilled tool
output or a scratch file read back is not counted. The context rows are the
means of `tokkit.py subagents`'s split per pass. PR tokens carried are a pass's
PR share times its context summed over its calls (`deliveries.pr_tokens`):
5.8 and 6.5 times run B's per pass on BK-389 and BK-394, for 1.9 and 2.2 times
its units per pass, because most of them are cache reads, which units weigh at
a tenth of fresh input. The higher first contexts, 26k to 35k, are the
five solo rounds run as a forked `/rvw-pr`, which loads the skill's body
[`passes[].first_ctx`]. Neither PR edits `rvw-pr` [`edits_rvw_pr`], so no pass
read its own instructions as a subject, the confound #1125 met.

By method, from [`by_method`]: a pass counts under the method its description
names first, and its findings are those it handed back. In total these exceed
the posted count (135 against 120 on BK-389, 65 against 60 on BK-394), since a
posted round merges findings that share a file, but not in every round: BK-389's
round 2, a solo measuring pass, and RFC-0021's round 2, also one pass, posted 7
and 5 against 4 handed back [`rounds[]`], so a method's row can also fall short
of what it contributed to the posted count.

| Method | BK-389 passes | its findings | BK-394 passes | its findings |
| --- | ---: | ---: | ---: | ---: |
| Whole-file | 12 | 62 | 4 | 19 |
| Unprimed | 13 | 33 | 4 | 13 |
| Measuring | 15 | 28 | 8 | 19 |
| Other lens (solo, reader, consistency, neglected surface) | 2 | 12 | 4 | 14 |

- **Whole-file passes found the most on BK-389**, about five findings each
  against two for a measuring pass, at a similar median cost (0.82 M against
  0.92 M). On BK-394 the whole-file passes read a median 26 files whole and
  cost a median 1.40 M, the most of any method, for about five findings each.
- **The files each pass read whole are in its row** of
  [`passes[].read_whole`], with its calls, for the call-list comparison #1125
  made by hand between two passes; this record does not repeat it.

## 4. Defects

**No defect has been reported against either merged PR so far, but each
shipped with known open items its own loop filed.** "So far" is master's log
after #1144, which holds only #1145, and `BACKLOG.md`, which names neither PR
outside the items they filed. The comparison ADR-0045
asks for, the defects a cheaper run ships against those of the run it
replaces, has no partner here: neither delivery has an A run.

- **#1144 filed four items at its close** (`git diff b7deb551c~1 b7deb551c --
  sdd/BACKLOG.md`): BUG-328, a `bytearray` write that both Memory drivers
  refuse and that now answers about the target instead of failing raw; BK-442,
  `remote_store.drivers` importing the whole async package, a cost the sync
  path did not have before; BK-441, a driver that omits a required primitive
  inheriting an empty body; and BK-440, the Dafny model's write ranking a gate
  below the order spec 003 states. The first two change behaviour a caller
  can see. The maintainer chose to file rather than fix BK-441 and BK-442
  (the PR's decision log, dialog Finish).
- **#1127 shipped one kernel gap it filed**, BK-439: the kernel's flat `glob`
  skips the store tree's flat rules. The item is due before the first flat
  driver with `GLOB` moves onto the kernel, and none has. Its other new items (`git diff
  45132599a~1 45132599a -- sdd/BACKLOG.md`) are RFC-0021's follow-ups
  (BK-433, BK-434, BK-436, BK-438), a defect found on master (BUG-323) and
  two in the review tooling (BUG-324, BUG-325).
- **One defect in the means under test reached master.** The `reviewer`
  agent's description from #1125 was not valid YAML for a strict parser;
  Claude Code's loader tolerated it, so every pass here ran, and #1145 fixed it
  after both deliveries.

## 5. Active time

**By the gap method in `deliveries.py`, BK-389 was worked for 7 h 02 min over 24.6 hours
of session time, BK-394 for 3 h 54 min, and RFC-0021 for 2 h 37 min.**

| | BK-389 | RFC-0021 | BK-394 | run B |
| --- | ---: | ---: | ---: | ---: |
| Session time | 1,476 min | 1,175 min | 994 min | 116 min |
| Waits on the maintainer | 1,005 min | 1,018 min | 760 min | 17 min |
| Stated idle | 49 min | — | — | — |
| Active | 422 min | 157 min | 234 min | 99 min |

From [`wall_min`, `wait_min`, `stated_idle_min`, `active_min`]. A gap of 60 s
or more in a main transcript counts as a wait when a user prompt or a dialog
answer ends it, and as work when a subagent's hand-back, a task notice or a
tool result does; the method is in `deliveries.py`'s docstring. Session time
counts each part from its first to its last record, so the days between
sessions are not in it, and the overnight waits inside a session are.

- **Stated idle** is the maintainer's: a 48.7-minute `Bash` call in BK-389's
  third session ran while the PC was suspended or waiting on the maintainer.
  The other statement, a suspend on 2026-10-15 from 11:39 to 12:04, falls
  inside a gap the method already counts as a wait.
- **Run B by two methods.** `report.md` § How long the runs took gives 1 h 49
  min active, counting gaps of five minutes or less across main and subagent
  records; this method gives 1 h 39 min. The methods differ, and only this
  one is applied to all four rows.

## 6. What this changes

**BK-431's input is the one control these runs test, and it held; nothing here
re-tests the other controls.**

- **For BK-431.** Every pass opened on the smaller input; the prefix share fell
  by more than half against run B's 40.6% on BK-389 and BK-394 (16.2% and
  17.2%) and by a fifth on RFC-0021 (32.1%) [`pass_summary.prefix_pct_mean`];
  and neither PR edits `rvw-pr`, so the confound #1125 met does not arise. This
  supports keeping it. Whether to close it is the maintainer's call, and so is
  whether spawning every member as `reviewer` partially supersedes
  [ADR-0036](../adrs/0036-reviewers-by-subject-and-method.md)'s first decision,
  which keeps domain personas as a way to staff a scoped lens; this record does
  not close it.
- **The loop's cost on a large PR is its length, not its passes.** The main
  session took 57% of BK-389's round units and 47% of BK-394's (§ 2's table),
  and that session carried every fix forward; only a session break lowered its
  context, and a resume cost one to two rounds. A loop that does not
  converge pays its context again every round.
- **Proposal 6 ends here unmet.** It asked for two more `/ship` deliveries,
  one of them drawing prose findings only, to decide whether the saving
  recurs. These two have no A run to compare with, and both drew code
  findings; BK-394 also started with a context prompt in the main checkout
  rather than in a fresh worktree.

## 7. Where the cost could be cut

**Every cut worth making is in the review loop, and the largest trades units
for findings left unfixed.** The figures below are what the measured rounds
cost, from the result file; what a changed loop would have cost or shipped
instead is not measured, and ADR-0045 counts a cut only if the defects shipped
do not rise. Run B is the warning: its five rounds shipped two regressions run
A's PR had measured and avoided, one of them found in run A's seventh round,
though the maintainer judged neither must-fix
([`research-token-spend-means.md` § 5](research-token-spend-means.md#5-where-the-argument-breaks)).

| Cut | What the measured runs show | Risk | What it would change |
| --- | --- | --- | --- |
| Cap the loop at three rounds, then file or waive the rest | Rounds 4 onward held 78.55 of BK-389's 98.25 M and 29.96 of BK-394's 57.22 M, and posted 94 of 120 and 42 of 60 findings | At most those findings go unfixed: the ones a round-4-or-later fix caused would not exist. Some of the rest are real defects, and how many is not derived here | Partly supersedes ADR-0033's convergence over a round count |
| Review only what changed since the last round, keeping one whole-file pass to exit | 66 of BK-389's 120 findings and 21 of BK-394's 60 were caused by an earlier fix in the loop (§ 2) | A fix that breaks code it did not touch waits for the exit pass | ADR-0037's whole-file exit gate stays, or the risk has no bound |
| Split a large PR, by kind of content too, and settle concept work before the build | Run B's rounds cost 2.43 M on 1,452 changed lines against 4.51 to 5.57 M on 8,479 to 18,949; 74% of #1127's lines were `sdd/` and tests (§ 1); the RFC-0021 detour cost 28.77 M mid-loop | More PRs, each consistent on its own at every commit (principle 3), and a spec PR merged before the code that proves it | Planning has to find the concept change, as orient is meant to |
| Keep generated code out of review passes | 1,876 of #1127's 18,949 changed lines (10%) were the generated sync twin, which `scripts/gen_sync_kernel.py --check` gates against its source (§ 1); 29 of BK-389's 42 passes and 11 of BK-394's 20 read a twin file whole [`passes[].read_whole` under `src/remote_store/_kernel/_sync/`] | A generator defect lands unread unless a pass reviews the generator and its template | The whole-file exit gate (ADR-0037) names the generated files it exempts |
| Choose members by the kind of PR | On BK-389 a whole-file pass handed back about five findings at a 0.82 M median, a measuring pass about two at 0.92 M (§ 3) | On prose and research PRs, measuring passes catch the figure errors that matter | Replaces the fixed panel with a choice per PR |
| Start a fresh session every few rounds | Each of BK-389's three breaks lowered the main context (638k to 378k, 594k to 443k, 559k to 504k), but the resumes' opening calls cost 3.56 M, 5.26 M and 7.06 M, one to two rounds of 4.07 M (§ 2); the third also re-derived the kernel against RFC-0021 | Not shown to save: the resume cost is not separated from the fix it carries | — |

From [`rounds[].units_m`, `rounds[].findings_posted`, `units_m_per_round`,
`by_method`], the cap rows summed over rounds 4 onward. Orient and plan, at 1.7
to 7.2% of a delivery (§ 1), is not worth cutting: orienting badly is how a
detour like RFC-0021 starts. Waiting time costs no units.

## Reproducing

**One script writes the result file, from the snapshots and a map of which
session parts served which PR.** The map is keyed by session ID, so it stays
outside the repo with the snapshots, as `prep_cost.py`'s class map does; the
result's `_provenance` block records its SHA-256 and each part's main
transcript.

```
python sdd/research/token-usage/deliveries.py --repo-root <main checkout> \
    --snapshots <token-kit>/runs --config <token-kit>/deliveries.json \
    --name deliveries_bk389_bk394
```

The parts, as read from the transcripts:

| Delivery | Parts |
| --- | --- |
| BK-389 | the `/ship BK-389` build session; three `/ship resume 1127` sessions; the first 9 calls of a fourth, before it turned to RFC-0021 at 2026-10-12T15:00Z; the session that resumed #1127 against RFC-0021 and closed it, less its BUG-326 subagent |
| RFC-0021 | that fourth session from 15:00Z until its resume on 2026-10-15, and the session that continued it from a handoff prompt |
| BK-394 | the `/ship BK-394` build session and its `/ship resume 1144` |
| run B | as in `report.md` § Run B |

`tokkit.py` gives the same units for each part: `report --session <sid>` for a
whole session, with `--until` for the cut at 15:00Z, and the excluded subagent's
row in `subagents --session <sid>`. The kit's PR link does not match this
split in three places: `report --pr 1127` includes the fourth session whole,
since it began as `/ship resume 1127`, and links neither the RFC-0021
continuation nor #1127's last session, whose first prompt is a handoff. The kit reads Claude Code's
transcript folders, not a snapshot folder, so a re-run of `tokkit.py` on these
snapshots needs them laid out as a projects folder; `deliveries.py` reads the
snapshot folder directly.
