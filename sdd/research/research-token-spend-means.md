# Research: A Delivery Costs What It Carries — Ordering Controls for Agent Token Spend

**Date:** 2026-10-10
**Backlog items:** BK-418 (the interventions and their test), with the means it led to under BK-414, BK-419, BK-421, BK-422, BUG-314 and BUG-315; open follow-ups BK-420, BK-423, BK-424.
**Status:** Research complete for one measured comparison; the argument is settled as of the date above, its generality is not. Point-in-time snapshot per [`sdd/000-process.md` § Document types](../000-process.md#document-types). Every figure is derived in the research record [`token-usage/report.md`](token-usage/report.md) and linked from here rather than copied; where the two differ, the record wins. Its folder also holds the scripts, the result files and a page of the figures, [`token-usage/token-spend-analysis.html`](token-usage/token-spend-analysis.html).
**Related:** [`research-code-abundance-goals-and-values.md`](research-code-abundance-goals-and-values.md) argues that the controls that work against understanding debt fix the *order* of operations; this record finds the same for token spend. [`research-appropriate-level-of-detail.md`](research-appropriate-level-of-detail.md) is the source of the detail rule in § 3.

## TL;DR

An agent's delivery costs what it carries forward, not what it does, and what it
carries is set by the order of its operations. The controls that cut it fix an
order rather than add an effort, and a spend target is honest only when it is
judged together with an outcome.

The chain:

1. Every call re-reads the whole context, so a session costs roughly its calls
   times its context, and an item costs more the earlier it enters and the
   longer it stays.
2. A workflow that reviews on the build's context pays for the build again in
   every review round, and the rounds grow dearer as the context grows.
3. The long tail of a review loop is self-made: each fix makes neighbouring
   claims false, and claims nothing checks are checked by the next round.
4. Each of these is prevented by an order and not repaid by an effort: weigh
   related work before planning, review in a fresh context, close a claim by a
   check that can fail, and write only the detail the change owns.
5. Spend is an effort proxy and Goodhart-exposed. As a target it is valid only
   coupled to an outcome check, and the one comparison here shows why: the
   cheaper run was judged by its defects too, and they found what its shorter
   loop had missed.

Link 1 is the arithmetic of prompt caching. Links 2 to 5 are this record's own,
measured on one repository: § 1 and § 2 argue 1 to 3, § 3 argues 4, § 4 tests it
once, and § 5 argues 5 and marks where the argument breaks.

## Context

The repository asked for **sound, standing means that keep token spend and
level of detail appropriate in every piece of work worth doing**, locally and in
cloud sessions. A means is a skill, gate, tool or rule on master that acts on
every delivery, not a one-off saving, and every change is judged by what it does
to a delivery: the tokens it spends, and detail written only where the work owns
it.

The investigation ran in three steps. A first `/ship BUG-280` delivery (run A)
was watched call by call. What it exposed was turned into means on master, each
its own PR. Then the same prompt was delivered again on those means plus one
tested rule (run B), and compared with run A under a decision rule fixed before
the run ([RFC-0020](../rfcs/rfc-0020-ship-token-interventions.md#decision-rule)).

**Sourcing note.** Every figure comes from Claude Code's local transcripts of
this repository, parsed by the scripts beside the record. Units weight tokens by
price (a cache read is a tenth of an input token, output five times), and
dollars use prices fitted to Claude Code's own cost records
([report § 1](token-usage/report.md#1-calibration)). The window is narrow: two
working days for the cost structure, and one run per arm for the comparison.
Cloud sessions are not measured, because their transcripts stay remote.

## 1. A delivery costs what it carries

**Cache reads are 98.7% of the tokens, so the price of a call is the size of the
context it re-reads, and a session costs about its calls times its context.**
Calls at 400k context or more were 23% of calls and 47% of units; across main
sessions, units grew with calls to the power 1.19
([report § 2](token-usage/report.md#2-cost-structure)).

Two consequences carry the rest of this record. **An item's cost is its size
times the calls it stays for**, so the same file read early in a long session
costs many times what it costs late in a short one. And **what is carried is
mostly not what anyone chose to read**: the session prefix, tool results and
hidden thinking are most of the re-read context, the repository's own
instruction files a few percent ([report § 3](token-usage/report.md#3-what-the-re-read-context-is-made-of)).

So the question is not how much work a delivery does, but in what order, and on
what context, it does it.

## 2. Where the carry comes from

**Run A spent 94% of its 59.3 M units after its PR opened, and every one of the
four causes behind that is a matter of order.** A bug fix sized S closed only
after 13 review rounds on two routes
([report § Run A final](token-usage/report.md#run-a-final)).

**The review ran on the build's context.** Run A's main context entered round 1
at 255k tokens and round 7 at 828k; each round paid again for everything the
build had left behind. A compaction reset it to 113k once, and it regrew about
100k per round afterwards: a reset buys a few cheap rounds, not a cheap loop
([report § 7](token-usage/report.md#7-run-a-ship-bug-280-at-the-round-7-checkpoint),
[§ Run A final](token-usage/report.md#run-a-final)).

**The loop made its own work.** Across 41 review loops, 49 to 78% of the
findings from round 4 on were caused by an earlier fix in the same loop, and the
tail was prose. Of 321 prose findings in the 13 longest loops, 94% could be
settled by a command or by listing the cases; 6% needed judgement
([report § 5](token-usage/report.md#5-review-loop-anatomy)). A claim nobody
checks when it is written is checked by the next review round, at that round's
context.

**Orientation came after the plan.** Run A's spec was shared by the backend
redesign. The run never weighed it, hardened a stopgap for seven rounds, and
re-planned only when the maintainer asked; the first route cost 31.5 M units
before the re-plan ([report § 7](token-usage/report.md#7-run-a-ship-bug-280-at-the-round-7-checkpoint)).

**The environment stalled the work.** The local gate was cut off at the tool
limit three times and once left the session idle for 37 minutes, which the
maintainer attributes to other suites running on the machine at the same time
([report § Run A final](token-usage/report.md#run-a-final)).

A fifth cause works on every session rather than in the loop: **the process
files every session and subagent re-reads grew two to four times in five
months**, with nothing pricing the growth
([report § 4](token-usage/report.md#4-five-months-of-traces-and-prs)).

## 3. The controls fix an order

**Each cause has a paydown remedy and a preventive one, and only the preventive
one acts before the cost is incurred.** This is the distinction
[`research-code-abundance-goals-and-values.md` § 2.3](research-code-abundance-goals-and-values.md#23-three-debts-not-one)
draws for understanding debt, and it transfers to cost because cost, too, is
fixed by what is in context when a call is made:

| Cause | Paydown remedy | Preventive control |
| --- | --- | --- |
| Review on the build's context | compact the session when it is already large | **the build writes a handoff and stops; the review loop starts in a fresh session** |
| The loop's own prose findings | another review round per narrowed claim | **write only the detail the change owns; close a prose finding by a check that can fail** |
| Orientation after the plan | re-plan after the loop has hardened the wrong fix | **weigh the open items sharing the work's spec or files, and recommend a scope, before planning** |
| Gate stalls | retry, wait, re-run | **one suite per machine, a deadline on every wait, workers sized to free memory** |
| Unpriced process files | trim them when someone notices | **their total may grow only by a recorded raise** |

Two rows are not orders but gates on the environment; they belong to the
merge-gate cell of the same table, and they are what makes the other rows'
savings visible rather than drowned by stalls.

**The detail rule is an ordering control, not a style rule.** A change that
details only the behaviour it owns removes, at writing time, the claims the
next round would otherwise refute; a claim about anything else is deleted or
pointed at its home, never narrowed, because a narrowed claim is a new claim
([`CONTENT-RULES.md` Rule 8](../CONTENT-RULES.md#change-details-what-it-changes)).
It is what the appropriate-level-of-detail research argues, aimed at the round
it saves.

The appendix maps each control to where it lives on master and the PR that put
it there.

## 4. The test: one delivery, measured twice

**Run B, the same prompt on master with the controls and one tested rule, closed
merge-ready in five rounds at 15.0 M units: a quarter of run A, and 47% below
run A's second route, which had the comparable scope.** The decision rule fixed
before the run was met ([report § Run B](token-usage/report.md#run-b-ship-bug-280-on-the-means)).

| | Run A | Run A, route 2 | Run B |
| --- | ---: | ---: | ---: |
| Units, first call to close | 59.3 M | 28.19 M | 15.0 M |
| Review rounds | 13 | 6 | 5 |
| Main context entering round 1 | 255k | 113k | 104k |
| Findings | — | 49 | 17 |
| Share of findings on prose | — | 61% | 35% |
| Gate cut-offs and idle stalls | 3 and 1 | — | none |

Each control shows in the run:

- **Orient before plan.** Run B read the redesign and its related items first,
  recorded a verdict per cluster, and fixed every branch of the listing methods,
  including the recursive walks run A had deferred. Orient cost 7.4% of the run,
  and no re-plan over scope followed.
- **Fresh context for review.** Every round started on less context than route
  2's, which reached its low start only through a compaction.
- **Detail owned, prose closed by check.** Prose fell from 61% to 35% of the
  findings. The tested rule, rule (c), closed eleven findings by a check the
  fixer ran and quoted, and none of those closes was later found false
  ([report § Rule (c) against the decision rule](token-usage/report.md#rule-c-against-the-decision-rule)).
- **A stable gate.** 16 gate runs, none cut off, no stall.

**What the table cannot show** is which control did how much. They changed
together, run B's scope was wider than route 2's, and run B saw a note about the
experiment during orient. It is one delivery measured twice the same way, not an
effect size per control.

## 5. Where the argument breaks

**The thesis holds on the evidence here, but four findings bound it, and one is
counter-evidence.** Each changes a proposal in § 6.

**A shorter loop found less.** Run B's PR ships two regressions run A's PR had
measured and avoided: a Windows subfolder in the classic delete-pending state,
and a link into a folder the caller cannot enter, on Python 3.14. Run A's
seventh round had found the first; run B's five rounds never raised either. Run
B is still the better fix on every case measured, and the maintainer judged both
regressions not must-fix
([report § The two deliveries compared](token-usage/report.md#the-two-deliveries-compared)).
The point stands regardless: **fewer rounds is a saving only when the
reviewers still reach the platform and edge cases the change touches.** This is
why link 5 of the chain exists. Token spend is on the list of effort proxies
the code-abundance record says to retire
([§ 2.4](research-code-abundance-goals-and-values.md#24-goodhart-applied)), and
as a bare target it would reward exactly this. It survives here only because
the decision rule also failed the run on any must-fix defect the slower run did
not have.

**A control can decay into ritual.** Three of rule (c)'s eleven checks could not
have shown their claim false: a backlog-shape check, run twice, that tests an
item's form and not what it says, and a `git grep` that tests wording. They were
run and quoted, so the rule as written was met. A check that cannot fail is
Goodhart inside the control itself, and the decision rule had no clause against
it.

**The controls cost more than one delivery saves.** Building them took 74.7 M
units, and the whole preparation between the runs 134.0 M: nine runs B, or 1.7
times the saving run B made against run A
([report § What the means cost](token-usage/report.md#what-the-means-cost)).
They repay only across later deliveries, which one comparison cannot show.

**The work did not apply its own thesis.** Measurement, analysis and experiment
setup together cost as much as run A itself. Run A's monitoring and analysis session ran nine hours to a
945k context without a compaction, and no session in the preparation window
compacted at all. Knowing that cost is carried context did not make the
investigating sessions carry less; only a control would have.

## 6. Proposals

**1. Put each control at the step where the decision is made.** Every control
in § 3 sits before the act it protects: orient before the plan, a fresh
session before the review, a check before a claim closes. A control placed after
the act is a paydown, and pays interest in carried context.

**2. Never target spend alone.** Judge a cheaper delivery also by the defects it
ships, compared with the delivery it replaces, as RFC-0020's decision rule did.
Spend without an outcome check rewards the shorter loop that found less.

**3. A check counts only if it can return the claim false.** Adopting rule (c)
needs this clause; a shape check or a wording grep closes nothing. This is the
amendment run B showed missing.

**4. Owe the enumeration when the claim is written.** "Every", "all" and
"never" are where the scope findings come from; principle 9 already makes a
figure name its derivation before it is written, and the same order would
remove the cases the next round would otherwise list
([BK-423](../BACKLOG.md)).

**5. Keep the review on what the review needs.** The untested hypotheses in
[report § 9](token-usage/report.md#9-hypotheses) point the same way: every
subagent pays a prefix of about 53k tokens before it works, and review
subagents re-read the same process files. A smaller, scoped reviewer input is
the next ordering control to test.

**6. Measure the next deliveries the same way, and measure them where they
run.** Two more `/ship` deliveries, one of them drawing prose findings only,
decide whether the saving recurs (RFC-0020 Phase 2). Cloud sessions need their
transcripts copied out to be measured at all.

**7. Hold measuring sessions to the same order.** Delegate sweeps to subagents
whose transcripts end with their task, restart between phases with a written
handoff, and snapshot transcripts early: Claude Code deletes them after about
30 days.

**8. Keep the experiment out of the subject's context, and date phases from
the work, not from incidental records.** A memory note naming the experiment
reached run B during orient; a branch name shared with run A made Claude Code
link run B to run A's PR, and the measurement kit followed that link
([BK-424](../BACKLOG.md)).

## Appendix: remote-store as a worked example

**Seven controls are on master, each its own PR, each acting on every delivery
without anyone remembering to use it.** The authoritative text of each lives
where the table points; it is not restated here.

| Control | Where it lives | PR |
| --- | --- | --- |
| Orient before planning: a verdict per cluster of related open items, a scope recommended before the plan | [`/ship` § Orient](../../.claude/skills/ship/SKILL.md#orient), [`CLAUDE.md` § Backlog](../../CLAUDE.md#backlog) | #1103 |
| Handoff at the PR: the build writes `tmp/ship-handoff-<N>.md` and stops; `/ship resume <N>` reviews in a fresh session | [`/ship`](../../.claude/skills/ship/SKILL.md) | #1103 |
| Detail only what the change owns | [`CONTENT-RULES.md` Rule 8](../CONTENT-RULES.md#change-details-what-it-changes) | #1106, #1109 |
| A stable local gate: one suite per machine, a per-test timeout, a 15-minute deadline on every background wait, workers capped by free memory, a port race fixed | `scripts/run_tests.py`, [`CLAUDE.md` § Parallel tests](../../CLAUDE.md#parallel-tests) | #1105, #1107, #1108 |
| A budget on process files: their total grows only by a recorded raise | `scripts/check_process_budget.py`, `sdd/process-budget.json` | #1110 |
| A lookup tool: one backlog item or reference section by key, instead of a search and a sliced read | [`scripts/sdd_lookup.py`](../../scripts/sdd_lookup.py) | #1099 |
| The Edit/Write lint hook no longer deletes an import before its first use, which forced re-edits | `.claude/hooks/` | #1095 |

Two more act outside the repository, per checkout: the claude.ai skills synced
into every session's listing were turned off, and the auto-memory index was
trimmed; both shrink the prefix every call carries
([report § 8](token-usage/report.md#8-changes-made-so-far)). The measurement kit,
[`token-usage/tokkit.py`](token-usage/tokkit.py) and its siblings, is the
standing means for testing the next control the same way.

**Still open.** Rule (c) passed its test and awaits adoption by an ADR with the
clause in proposal 3 (RFC-0020 Phase 1). BK-423 is proposal 4. BK-424 fixes the
measurement kit's phase dating. BK-420 re-walks the lookup tool against its
baseline around 2026-11-08.

## Sources

The evidence:

- [Research record: where Claude Code sessions on this repo spend their tokens](token-usage/report.md), with its scripts and `results/` beside it
- [RFC-0020: check-closed prose in `/ship`, tested as run B](../rfcs/rfc-0020-ship-token-interventions.md), the decision rule fixed before the run
- Run A: PR #1093; run B: PR #1113; the tested rule: PR #1101 (never merged)

The process it acts on:

- [ADR-0033](../adrs/0033-ship-convergence-driven-review.md) to [ADR-0037](../adrs/0037-whole-file-gate-and-derived-figures.md): the `/ship` review loop the controls sit in
- [`CONTENT-RULES.md`](../CONTENT-RULES.md) and [`research-appropriate-level-of-detail.md`](research-appropriate-level-of-detail.md): the detail rule
- [`research-code-abundance-goals-and-values.md`](research-code-abundance-goals-and-values.md): the preventive-control argument and the Goodhart list this record answers
