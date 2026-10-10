# Research: Means that keep token spend and detail appropriate

**Date:** 2026-10-10
**Backlog items:** BK-418 (the interventions and their test), with the means it led to under BK-414, BK-419, BK-421, BK-422, BUG-314 and BUG-315; open follow-ups BK-420, BK-423, BK-424.
**Status:** Advisory research, point-in-time snapshot per [`sdd/000-process.md` § Document types](../000-process.md#document-types). It summarises one investigation and the changes it led to. Every figure here is derived in the research record [`token-usage/report.md`](token-usage/report.md), which this document links rather than copies; where the two differ, the record wins. The record's folder also holds the scripts, the result files and a page of the same figures, [`token-usage/token-spend-analysis.html`](token-usage/token-spend-analysis.html).

## Goal

**Sound, standing means that keep token spend and level of detail appropriate
in every piece of work worth doing, locally and in cloud sessions.** A means is
a skill, gate, tool or rule on master that acts on every delivery, not a
one-off saving. Every change is judged by what it does to a delivery: the
tokens it spends, and detail written only where the work owns it.

## Answer

**Most of a delivery's tokens are the model re-reading its own context after
the PR opens, and the long tail of a review loop repairs prose the loop's own
fixes broke. Seven means now on master act on those causes; the same delivery
re-run on them cost a quarter as much.** The delivery was `/ship BUG-280`: run A
before the means, 59.3 M price-weighted units, and run B after them, 15.0 M in
five review rounds ([report § Run A final](token-usage/report.md#run-a-final),
[§ Run B](token-usage/report.md#run-b-ship-bug-280-on-the-means)). Building the
means cost more than the saving of one delivery, and which means did how much
one run cannot say; both are below.

## Where the tokens go

**A call costs about its context, so a session costs about its calls times its
context, and the review loop is where both peak.** Cache reads are almost all
tokens; a main session's context grows with every tool result and every turn
of hidden thinking, and every review round pays again for everything the build
left behind ([report § 2, § 3](token-usage/report.md#2-cost-structure)).

- **After the PR opens.** Run A spent 94% of its units in the review loop and
  its subagents. Its main context entered round 1 at 255k tokens and round 7 at
  828k ([report § 7](token-usage/report.md#7-run-a-ship-bug-280-at-the-round-7-checkpoint)).
- **The prose tail.** From round 4 on, 49 to 78% of a long loop's findings
  were caused by an earlier fix in the same loop, and nearly all prose findings
  are settled by a command or by listing the cases
  ([report § 5](token-usage/report.md#5-review-loop-anatomy)).
- **Thin orientation.** Run A never weighed the backend redesign that shares
  its spec, hardened a stopgap for seven rounds, then re-planned
  ([report § 7](token-usage/report.md#7-run-a-ship-bug-280-at-the-round-7-checkpoint)).
- **An unreliable local gate.** Run A's gate was cut off at the tool limit three
  times and left the session idle once for 37 minutes
  ([report § Run A final](token-usage/report.md#run-a-final)).
- **Process files grow unpriced.** What every session and every subagent
  re-reads grew two to four times in five months
  ([report § 4](token-usage/report.md#4-five-months-of-traces-and-prs)).

## The means on master

**Each means answers one of those causes and acts on every delivery without
anyone remembering to use it.** The PR is the change; the authoritative text
of each rule is where it lives, linked here, not restated.

| Means | Cause it acts on | Where it lives | PR |
| --- | --- | --- | --- |
| Orient before planning: a verdict per cluster of related open items, and a scope recommended before the plan | thin orientation | [`/ship` § Orient](../../.claude/skills/ship/SKILL.md#orient), [`CLAUDE.md` § Backlog](../../CLAUDE.md#backlog) | #1103 |
| Handoff at the PR: the build session writes a handoff and stops; a fresh session runs the review loop | context carried into every round | [`/ship`](../../.claude/skills/ship/SKILL.md)'s handoff and `/ship resume <PR>` | #1103 |
| Claim discipline: a change details only the behaviour it owns; any other claim is deleted or pointed away, never narrowed | the prose tail | [`CONTENT-RULES.md` Rule 8](../CONTENT-RULES.md#change-details-what-it-changes) | #1106, #1109 |
| A stable local gate: one suite per machine, a per-test timeout, a 15-minute deadline on every background wait, workers capped by free memory, the moto port race fixed | gate cut-offs and stalls | `scripts/run_tests.py`, [`CLAUDE.md` § Parallel tests](../../CLAUDE.md#parallel-tests) | #1105, #1107, #1108 |
| A budget on process files: their total bytes may grow only by a recorded raise | process files growing unpriced | `scripts/check_process_budget.py`, `sdd/process-budget.json` | #1110 |
| A lookup tool: one backlog item or reference section by key, instead of a search and a sliced read | repeated reads of large process files | [`scripts/sdd_lookup.py`](../../scripts/sdd_lookup.py) (`hatch run backlog-show`, `backlog-find`, `ref-show`, `ref-rows`) | #1099 |
| The Edit/Write lint hook no longer deletes an import before its first use | forced re-edits | `.claude/hooks/` | #1095 |

Two more apply outside the repo, per checkout: turning off the claude.ai skills
synced into every session's listing, and a trimmed auto-memory index. Both cut
the prefix every call carries ([report § 8](token-usage/report.md#8-changes-made-so-far)).
The measurement kit itself, `token-usage/tokkit.py` and its siblings, is the
standing means for testing the next change the same way (#1098, #1102, #1104).

## What the means did to one delivery

**Run B, the same `/ship BUG-280` on master with the means and one tested rule,
closed in five rounds at 15.0 M units against run A's 59.3 M and its
comparable second route's 28.19 M.** Every round started on less context, the
loop drew 17 findings instead of 49, and the gate had no cut-off and no stall
([report § Run B](token-usage/report.md#run-b-ship-bug-280-on-the-means)).

| | Run A | Run A, route 2 | Run B |
| --- | ---: | ---: | ---: |
| Units, first call to close | 59.3 M | 28.19 M | 15.0 M |
| Review rounds | 13 | 6 | 5 |
| Main context entering round 1 | 255k | 113k | 104k |
| Findings | — | 49 | 17 |
| Share of findings on prose | — | 61% | 35% |

- **Orient changed the plan.** Run B read the redesign and its related items
  before planning and fixed every branch of the listing methods, including the
  recursive walks run A had deferred. Orient cost 7.4% of the run.
- **The handoff held context down.** Run A reached a low context only through a
  compaction, and regrew about 100k tokens per round after it.
- **The tested rule held but proved less than hoped.** Rule (c), closing a
  prose finding by a check the fixer runs and quotes instead of by another
  review round, fired eleven times and none of its closes was later found
  false. But only one round closed on such prose alone, and three of the
  eleven checks could not have shown their claim false. It passed RFC-0020's
  decision rule; adopting it is the RFC's next phase
  ([report § Rule (c) against the decision rule](token-usage/report.md#rule-c-against-the-decision-rule)).
- **A shorter loop found less.** Run B's PR ships two narrow regressions run A's
  PR had measured and avoided, and is still the better fix on every case
  measured ([report § The two deliveries compared](token-usage/report.md#the-two-deliveries-compared)).

**What one run cannot show.** The means and the tested rule changed together,
so the saving is theirs jointly. Run B's scope was wider than route 2's, and run
B saw a note about the experiment during orient. Read the table as one delivery
measured twice the same way, not as an effect size per means.

## What the means cost

**Building the means took 74.7 M units, and the whole preparation between the
two runs 134.0 M: nine runs B, or 1.7 times the saving run B made against run
A.** Measurement and experiment setup took the rest, as much as run A itself
([report § What the means cost](token-usage/report.md#what-the-means-cost)).
The means repay only across later deliveries, which is what the open items
below measure.

## Learnings for anyone working on this repo

**The figures are from one repo and two runs; the habits they argue for are
not.** Each points at its evidence in the record's
[§ Learnings](token-usage/report.md#learnings).

- **Price every call by its context.** A long session gets dearer per call, not
  only longer. Start the review of a PR in a fresh session from a written
  handoff, rather than on the context the build left behind.
- **Orient before you plan.** List the open items that share the work's spec or
  files and say how each relates. It is cheap, and it is the step that
  prevents a whole loop spent on a fix a pending redesign will reshape.
- **Write only the detail your change owns.** A claim about anything else is a
  target for the next review round and a source of the next round's findings.
- **Close prose by a check that can fail.** A command, a count or the
  enumerated cases settles a claim; a check of shape or wording does not.
- **Keep what the loop files to its defect.** Items filed during a review loop
  drew findings in the next round in both runs.
- **Fewer rounds is a saving only if the reviewers still reach the platform and
  edge cases the change touches.**
- **Measure a change before it becomes process, and fix the decision rule
  before the run.** Observe the scope a run picks rather than setting it, keep
  notes about the experiment out of the run's context, date phases from the
  PR and the plan rather than from incidental records, and snapshot
  transcripts early: they are deleted after about 30 days, and cloud sessions
  leave none locally.
- **Measuring costs too.** A monitoring or analysis session grows with what it
  watches; delegate sweeps to subagents and compact or restart between phases.

## What is still open

**The saving is shown once; whether it holds for every delivery worth doing is
what the next measured deliveries decide.**

- **Adopt rule (c) or not.** RFC-0020's Phase 1 is an ADR amending the clauses
  it waives, with the clause run B showed missing: a check counts only if it
  can return the claim false. Phase 2 measures the next two `/ship` deliveries,
  one of them drawing prose findings only.
- **BK-423:** owe the enumeration for "every", "all" and "never" at writing
  time, as principle 9 already does for figures.
- **BK-424:** date a run's phases from the PR and the plan, not from records
  that can point at the wrong event.
- **BK-420:** re-walk the lookup tool against its baseline, around 2026-11-08.
- **Cloud sessions** are not measured: their transcripts stay remote.
- **Untested hypotheses** in [report § 9](token-usage/report.md#9-hypotheses):
  a smaller input for each review subagent, the cache TTL, and hidden thinking
  by effort level.
