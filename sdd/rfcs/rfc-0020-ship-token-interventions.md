# RFC-0020: Four `/ship` interventions against post-PR token cost, tested as run B

## Status

Draft. **Nothing below is built. This RFC seeks approval for Phase 0 only: build
a `/ship` variant carrying four interventions, run it once on BUG-280 as run
B, and compare it with run A per phase and per round.** `/ship` itself and
ADR-0033 to ADR-0037 stay unchanged unless Phase 0 passes the decision rule
below. Tracked as **BK-418**. The evidence is the research record
[`sdd/research/token-usage/report.md`](../research/token-usage/report.md),
cited below as *the report*.

[2026-10-10, the maintainer's plan after run A, BK-418's `bk-418-orient`
trace: two parts now ship on master ahead of run B. P2 landed as written. P3
is replaced by `/ship` § Orient, in which the session reads the related work
and judges it rather than asking the user per cluster. So these clauses no
longer hold, and **do not set up run B from them**: the sentences above saying
nothing is built and `/ship` stays unchanged; § Start conditions' "master plus
one commit, the variant" and "Master's `/ship` is unchanged throughout"; the
Decision rule's P3 row, which scores the per-cluster dialog § Orient replaced;
the **Confounds** paragraph, which names BK-414's lookup tool landing before
run B but not P2 and § Orient; and the
Roadmap's "nothing that changes `/ship` itself lands before Phase 1", with its
Phase 0 row's "master's `/ship` stays unchanged". Under the
plan, run B starts from master with P2 and § Orient merged, plus one variant
commit holding only the prose-closing rule that overrides ADR clauses.
Rewriting this RFC to the plan is open under BK-418.]

## Summary

**A `/ship` delivery spends most of its tokens after the PR opens, because
every review round re-reads the context the build left behind, and the long
tail of rounds repairs prose the loop's own fixes made false.** Four changes
target that cost: a prose-tail stop, a fresh context at PR open, an orient
check for related open work, and a gate that cannot hang a session. One
delivery under a variant carrying all four, against one run without them on
the same item, decides which go on to amend the ADRs.

## Motivation

**The cost is set by calls times context, the review loop is where both are
largest, and nothing in `/ship` today acts on either.** The report has the
figures and their derivations. This section names only the four it acts on.

- **Post-PR share.** Run A (`/ship BUG-280`) spent 94.1% of its 59.3 M units in
  the post-PR main session and its subagents. BK-397's `/ship` run spent 82%
  after its PR opened (report § Answer, § Run A final).
- **Context entering each round.** Run A's main context grew from 255k at round
  1 to 828k at round 7. After a compaction it stood at 113k, then regrew by
  about 102k per round over the next five (report § 7, § Run A final).
- **The prose tail.** From round 4, 49 to 78% of findings were caused by an
  earlier fix in the same loop. Of 41 PRs with a review block, 17 drew prose and
  trace findings only, including loops of 10 to 13 rounds. Of 321 prose findings
  in the 13 longest loops, 94% are settled by a command or by listing the cases
  (report § 5).
- **Related open work.** BUG-280 shares spec BE-021 with seven open items, two of
  them the redesign that later narrowed run A's fix. The ID BK-389 first appeared
  in run A's context at call 2, and BK-394 at call 414. That records when an ID
  was in front of the session, not whether the plan weighed it (report § 7).
- **Environment.** Three of run A's local gate runs were cut off at the tool
  limit, and one background wait left it idle for 37 minutes (report § 7). Two of
  the three cut-offs overlapped another session's suite, per
  [BK-419's dossier](../backlog/bk-419-local-gate-unbounded-wait.md).

## Proposal

**Each intervention states its mechanism, the clause it would change if
Phase 0 keeps it, and the largest share of spend the report attributes to the
cost it targets.** Amendment targets follow each record's own `Amends` chain.
A clause that a later record has already amended is amended at its home, in
the record that introduced it, consistent with the amendments it carries.

### P1. Prose-tail stop

**Once code and tests have converged, prose findings are closed by the check
that settles them, not by another review round.**

- **Mechanism.** The tail starts at the first round with no code or test finding
  after a verified code fix pass. From then on:
  - every prose finding's fix names its check (a command, a grep, a count, or the
    enumerated cases), and the fixer runs it before committing;
  - no new finding-round opens for prose alone;
  - the loop closes on one pass that carries the existing exit gates (unprimed,
    whole-file, measuring where it applies) over the final state;
  - a prose must-fix finding from that closing pass is fixed, its check is run
    and recorded in the reply, and the loop ends there without another gated
    pass.

  A prose finding with no check, which the report puts at 6% (judgment), and
  every code or test finding, reopen the loop as today.
- **Would amend.** Five clauses, each at its home, all for check-closed prose
  findings in the tail only:
  - [ADR-0033](../adrs/0033-ship-convergence-driven-review.md)'s *Terminate the
    review loop on convergence*: a round whose only must-fix findings are
    check-closed tail prose counts as converged;
  - ADR-0033's *The loop may not end on an unreviewed fix pass*: the fix after
    the closing pass is verified by its recorded check, not by a review;
  - [ADR-0034](../adrs/0034-ship-panel-rounds-and-unprimed-exit.md)'s *The loop
    cannot end until an unprimed reviewer has seen the final state*;
  - [ADR-0037](../adrs/0037-whole-file-gate-and-derived-figures.md)'s whole-file
    gate: both gates are met by the closing pass and stay met after a
    check-closed prose fix;
  - [ADR-0035](../adrs/0035-vary-method-not-model.md)'s *A premise about
    existing behaviour is executed, not read, before it ships*: the measuring
    gate met by the closing pass stays met, and a prose fix narrowing a
    behavioural claim is measured by its own recorded check.

  ADR-0036 is unchanged.
- **Ceiling.** Small on PRs that change code: of 24 PRs with a code or test
  finding, the median had no round with findings after the last one, and 4 had
  two or more. Large on PRs without code findings: 17 of the 41 drew prose and
  trace findings only, in loops of up to 13 rounds (report § 5). Run B is a code
  PR, so it tests the small case only (Open Question 4).

### P2. Fresh context at PR open

**The review loop is driven by a session that starts at the PR, not by the
one that built it.**

- **Mechanism.** When `/pr` returns, the build session writes a handoff:
  - the PR number and branch;
  - the plan and the Step 1 subject list with its executed / read / not reached
    marks;
  - the trace path and open decisions.

  It then ends. A fresh top-level session, started by the maintainer, reads the
  handoff, the PR and the files it touches, and runs Step 4 and Step 5. It is the
  main loop from then on: it fixes, owns the sibling sweep, and holds the
  convergence judgement. Reviewers are unchanged.
- **Would amend.** No ADR clause. ADR-0036's *The main loop fixes and owns the
  sweep* sets the main loop against a domain-scoped delegate, and the fresh
  session is still the main loop in that sense. The change lands in
  `.claude/skills/ship/SKILL.md` (Step 3's end and a handoff step). A spawned
  agent as driver would instead delegate the orchestrator, which `/ship` § Roles
  forbids ("Never delegated"), so Phase 0 does not use one.
- **Ceiling.** 23 to 28% of the session group, net of the fresh session's own
  reads, on BK-397, the one `/ship` run the report computes it for (report
  § 9, row 1). That is an upper bound, and it decays. After run A's compaction
  the context regrew by about 102k per round, so a single reset at PR open buys
  only the first rounds. Open Question 1 asks whether to reset per round.

### P3. Orient check for related open work

**Before planning, `/ship` lists the open items that share the item's spec
IDs or the files it will touch, and asks how they relate.**

- **Mechanism.** In Step 1 (Frame), run the query the report's
  `orient_check.py` prototypes: open items in `sdd/BACKLOG.md` whose `spec:`
  attribute shares an ID with the item. Add the items whose dossiers name a file
  the plan touches. If the list is not empty, one `AskUserQuestion` dialog per
  related cluster comes before plan mode: proceed, narrow, or wait. The
  dialog's options and the user's answer are logged under `sdd/decisions/`.
- **Would amend.** No ADR clause. The step sequence is the skill's operational
  contract (ADR-0033 § Decision, last paragraph), so this lands in
  `.claude/skills/ship/SKILL.md` Step 1 alone.
- **Why a dialog, not a listing.** Five of the seven items' IDs were in run A's
  context by call 14 (report § 7). An ID in context does not show that the plan
  weighed the item. A dialog records an answer per item, so whether the plan
  changed is observable.
- **Noise.** For BUG-280 the query returns seven items, two of them the redesign
  (report § 7). Phase 0 records the count and how many of them changed the plan.
- **Ceiling.** A whole review loop, on items a pending redesign reshapes. Run A's
  first route, 31.5 M of its 59.3 M units, was spent before the narrowing
  (report § 7, § Run A final).

### P4. Gate robustness

**A local gate run can neither collide with another session's suite nor
leave a session waiting without a deadline.**

- **Mechanism.** Three parts:
  - only one full suite runs on the machine at a time, across sessions and
    worktrees: a lock taken by `scripts/run_tests.py` and released at exit, with a
    second run waiting or refusing rather than starting;
  - a per-test timeout, so a hung test fails by name instead of the tool call
    timing out;
  - a deadline on every background wait, after which the session reports and
    stops waiting.

  The tooling half is BK-419, which this RFC does not duplicate. In
  Phase 0 the collision half is a start condition rather than an intervention
  (§ Experiment), so only the deadline is under test.
- **Would amend.** No ADR clause. It changes `CLAUDE.md` § Parallel tests and
  `scripts/run_tests.py`, under BK-419.
- **Ceiling.** Wall time and re-run gates rather than a token share. Idle time
  costs no tokens, but each re-run gate does, and the report does not price
  them.

### Not in run B: a smaller reviewer input

The report's hypotheses 3 and 4 point at what every reviewer re-reads: its
skill file (2.72% of run A's re-read context at round 7), spilled tool outputs
read back, and the shared process files. A diet for that input
was considered and left out of run B by the maintainer, so that run B tests the
four interventions above and no other intervention; the one other change it runs
under is a confound, stated below. It stays a candidate for a later RFC.

## Experiment

**Run B is one `/ship BUG-280` delivery under the variant, started under the
same conditions as run A and compared with it round by round, not only in
totals.** With n = 1 per arm, the comparison can reject an intervention that
does nothing or does harm, but cannot estimate a rate. The decision rule below
is written for that.

### Start conditions

From the agreed run plan:
- a fresh session whose first prompt is exactly `/ship BUG-280`;
- started from `master` plus one commit, the variant, which edits
  `.claude/skills/ship/SKILL.md` on its own unmerged branch, in a fresh
  worktree without run A's branch. The master base commit and the variant
  commit are both recorded. Master's `/ship` is unchanged throughout;
- no other test suite running on the machine during the run;
- the same model as run A;
- watched with `tokkit.py live` and reported with `tokkit.py report --json`.

Run A's PR #1093 stays a draft until the comparison is done. The better of
the two PRs is then merged and the other closed.

### Metrics

Run B's values come from the same scripts as run A's. Run A's are in the
report's `results/` where the last column names a file. The others do not exist
yet, and Phase 0 derives them for both runs.

| Level | Metric | Source | Run A |
| --- | --- | --- | --- |
| Run | Units, estimated dollars, share after PR open | `tokkit.py report --json` | `run_a_final.json` |
| Phase | Calls, units share, mean context: orient, build, review main, subagents | same, `phases` | `run_a_final.json`; first route `run_a_round7.json` |
| Round | Main context at the round's start, main units, subagent units, members | same, `rounds` | same two files |
| Round | Findings by target (code/test, prose, trace) and the loop-introduced share | the PR's review comments, via `rounds.py` with a per-PR mode | not yet derived |
| Tail | Finding-rounds after the last code or test finding; prose fixes closed by a named check | same, plus the fix commits | not yet derived |
| Orient | Related items listed, dialogs asked, whether the plan changed | Step 1 output, `sdd/decisions/` | `run_a_orient_check.json` (listing only) |
| Gate | Gate runs, cut-offs, idle stalls | `gates.py` | `run_a_final_gates.json` |
| Outcome | Must-fix findings found after the close by the maintainer's review | the PR | PR #1093 |

### Decision rule

**Fixed before run B starts. An intervention goes on to an ADR amendment
(Phase 1) only if its own metric moved and the outcome did not get worse.**

| Intervention | Keeps if | Fails if |
| --- | --- | --- |
| P1 prose-tail stop | Run B has fewer finding-rounds after its last code or test finding than run A's first route | The maintainer's post-close review finds a false claim of a kind the tail closed by check |
| P2 fresh context | Main context at the start of each of run B's first three rounds is at most half of run A's at the same round (run A: 255k, 304k, 355k) | Run B's post-PR units are not lower than run A's first-route post-PR units (28.0 M: 88.9% of 31.5 M, review loop and subagents, report § 7), or the handoff lost a subject that run A covered |
| P3 orient check | The recorded dialog changes run B's plan for at least one listed item before plan mode | The plan is unchanged by the dialog, or the check runs after planning |
| P4 gate deadline | Every background wait ends by completion or by its deadline | Any idle stall over the deadline |

**Run B as a whole fails** if its PR ships a must-fix defect that run A's PR
did not have. It also fails if its total units are not lower than run A's
first route (31.5 M), the fairer baseline, since run A's second route is the
narrowing P3 targets. A failing run B keeps the variant out of `/ship`, and
the RFC records why.

**Confounds, stated in advance.** Master moves between the runs, and this RFC,
the report and the variant each add to the context of later sessions. Run B's
author knows BUG-280 only through what master holds. Any of run A's narrowing
that is not on master is invisible to it, and that is intended. Run B also runs
with no other suite on the machine, a start condition run A did not have: two of
run A's three cut-offs overlapped another session's suite (BK-419's dossier),
and each cut-off cost a re-run gate. That favours run B in the run-level and P2
comparisons for a reason none of P1 to P3 controls. Run B also runs with BK-414's
lookup tool, which lands before it by the maintainer's decision: `/ship` Step 1
reads the item and the Pre-work index through it, and a `CLAUDE.md` rule sends
every session's single-key lookups to it. That can move the Phase row's orient
calls and units share, and how the Orient row's related items are listed, for a
reason none of P1 to P3 controls. Its lookups appear as Bash calls to
`hatch run backlog-*` and `ref-*`, not as Reads of the files they print from, so
the comparison counts them together with Read and Grep calls on `BACKLOG*.md` and
`CLAUDE-REFERENCE.md` in both runs; otherwise run B's lookups read as a drop in
reads.

## Roadmap

**Three phases, each with its exit fixed before it starts. Phase 0 can stop
the whole effort, and nothing that changes `/ship` itself lands before Phase
1.**

| Phase | Goal | Deliverables | Exit |
| --- | --- | --- | --- |
| **0. Test** | Decide from one delivery which interventions to keep | The `/ship` variant (an unmerged branch editing `.claude/skills/ship/SKILL.md`; master's `/ship` stays unchanged); `rounds.py` able to take one PR without a trace block; run B; the comparison written into the report's run B section | The decision rule above, applied per intervention |
| **1. Amend** | Write what Phase 0 kept into process | If P1 is kept, one ADR amending the five clauses named under it; `/ship` edits for every kept intervention; the variant branch closed | The ADR, if any, accepted and `/ship` carrying the kept interventions |
| **2. Confirm** | Check the gain holds on a delivery that is not BUG-280 | The next two `/ship` deliveries measured with the same metrics | Post-PR share and tail rounds no worse than run B's on both; otherwise reopen |

## Alternatives Considered

**Every rejected option either changes many things at once with no way to
tell which helped, or targets a cost the report puts at a few percent.**

- **Amend the ADRs now, on the report alone.** Rejected: the report describes two
  days and one run. The ADR chain was built one measured delivery at a time
  (ADR-0033 to ADR-0037), and amending it from correlations would break that.
- **One run per intervention.** Four BUG-280 runs at run A's cost is about 237 M
  units (4 × 59.3 M) for n = 1 each, and the interventions interact: P2's saving depends on how
  many rounds P1 leaves. Rejected for Phase 0. Phase 2 can separate them if the
  bundle passes.
- **A hard round cap instead of P1.** Rejected for the reason ADR-0033 gives: a
  cap ships defects the rounds after it would find. P1 relaxes convergence only
  for prose findings in the tail that a recorded check closes. Code findings and
  unchecked prose still reopen the loop.
- **Trimming the always-loaded files first.** Done where it was cheap (report §
  8). What is left is a few percent per file (report § 3), against a post-PR share
  of 82 to 94%.

## Impact

**No public API, runtime behaviour or user documentation changes. The impact
is on one skill, an ADR amendment only if P1 is kept, and the local gate.**

- **Public API / backwards compatibility:** none.
- **Process:** Phase 0 adds an unmerged variant branch of `/ship`. If P1 is kept,
  Phase 1 amends ADR-0033 (convergence and fix-pass clauses), ADR-0034 (unprimed
  exit gate), ADR-0035 (measuring clause) and ADR-0037 (whole-file gate) for
  check-closed tail prose. P2, P3 and P4 change the skill and the gate tooling
  only. ADR-0036 is not amended.
- **Tooling:** `rounds.py` gains a per-PR mode. Gate robustness lands under
  BK-419.
- **Ripples to carry when built:** `/ship` § Stop rule and § Roles (the
  orchestrator stays the main loop, now the post-PR session); `/fix-pr`'s
  sibling-sweep clause and reply rules, which carry P1's recorded check;
  `CLAUDE.md` § Parallel tests.

## Open Questions

1. **Reset per round instead of once.** Run A's compaction shows the context
   regrowing within one loop. A fresh fixer per round would hold context flat, at
   the cost of a handoff per round. Phase 0 runs the once-per-PR form. Phase 2
   decides whether to try per round.
2. **A driver the maintainer need not start.** Phase 0 uses a fresh top-level
   session, which the maintainer starts. A spawned agent would avoid that step
   but delegates the orchestrator, which `/ship` § Roles forbids, and its results
   return into the build session's context. If P2 is kept, Phase 1 decides
   whether that trade is worth amending § Roles for.
3. **File overlap in P3.** Spec IDs come from the attribute line. Touched files
   come from dossiers, which name files in prose. Phase 0 counts how often the file
   half adds an item the spec half missed.
4. **Where the prose tail starts on a PR with no code.** P1's trigger, the first
   round with no code finding after a verified code fix, never fires on a PR
   without code findings. Seventeen of 41 PRs are like that, with loops of up to
   13 rounds (report § 5). Starting the tail after round 1 there would end most
   of them early. Run B cannot test it,
   because BUG-280 is a code PR. A docs-only delivery is needed before Phase 1
   writes P1 for that case.

## References

- [Research record](../research/token-usage/report.md): every figure cited
  above, with its derivation.
- ADRs: [0033](../adrs/0033-ship-convergence-driven-review.md),
  [0034](../adrs/0034-ship-panel-rounds-and-unprimed-exit.md),
  [0035](../adrs/0035-vary-method-not-model.md),
  [0036](../adrs/0036-reviewers-by-subject-and-method.md),
  [0037](../adrs/0037-whole-file-gate-and-derived-figures.md).
- [RFC-0019](rfc-0019-two-speed-test-gate.md): the Phase 0 pattern this RFC
  follows.
- Backlog: BK-418 (this RFC),
  [BK-419](../backlog/bk-419-local-gate-unbounded-wait.md) (gate robustness),
  BK-366 (bug share).
