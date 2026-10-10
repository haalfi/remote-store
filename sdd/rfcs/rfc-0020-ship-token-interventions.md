# RFC-0020: Check-closed prose in `/ship`, tested as run B

## Status

Draft. **This RFC seeks approval for Phase 0 only: run `/ship BUG-280` once
more, as run B, on master plus one variant commit holding rule (c), and
compare it with run A's second route.** Rule (c) is the only intervention under
test. Everything else run A's research led to is on master before run B and is
environment, listed under [Confounds](#confounds). `/ship` and ADR-0033 to
ADR-0037 stay unchanged unless run B passes the decision rule below. Tracked as
**BK-418**. The evidence is the research record
[`sdd/research/token-usage/report.md`](../research/token-usage/report.md),
cited below as *the report*.

**Phase 0 ran on 2026-10-10** as PR #1113, on master `eff7953bb` plus the
variant `fba0850a6`. **It does not establish rule (c):** the first keeps
clause is not met, because the one round that closed on check-closed prose
alone was followed by a round that re-read its fix, owed for a code fix
(the maintainer's reading of the clause's text). Rule (c) stays out of
`/ship`, and #1101 closes, per the Roadmap. The report's § Run B scores every
clause. The maintainer judged the two regressions #1113 has and #1093 avoids
not must-fix; they are open follow-ups on #1113.

## Summary

**A `/ship` delivery spends most of its tokens after the PR opens, and the
long tail of its review rounds repairs prose that the loop's own fixes made
false.** Rule (c) closes each prose finding by the check that settles it
instead of by another review round. One delivery of BUG-280 under a variant
carrying rule (c), on a master that already carries the other changes, is
compared with run A's second route when run B picks that route's scope. If rule (c) holds,
one ADR amends the five clauses it waives; otherwise the variant closes.

## Motivation

**The review loop is where the cost is, and from round 4 most of what it
finds is prose its own fixes broke.** The report has the figures and their
derivations; this section names only those rule (c) acts on.

- **Post-PR share.** Run A (`/ship BUG-280`, PR #1093) spent 94.1% of its
  59.3 M units in the post-PR main session and its subagents (report § Run A
  final).
- **The prose tail.** From round 4, 49 to 78% of findings were caused by an
  earlier fix in the same loop. Of 41 PRs with a review block, 17 drew prose
  and trace findings only, including loops of 10 to 13 rounds. Of 321 prose
  findings in the 13 longest loops, 94% are settled by a command or by listing
  the cases (report § 5).
- **Run A's second route**, the scope PR #1093 shipped: six rounds and 49 findings,
  of which the fix-commit classifier labels 30 prose and a hand reading 37
  (report § Run B baseline).

What else run A exposed (thin orientation, context growth across rounds, an
unreliable local gate, unpriced process files) is addressed on master, not
here.

## Proposal

**Rule (c): in every round, a prose finding is closed by the check that
settles it, not by another review round.** It lives on the variant branch
`bk-418-ship-variant` ([#1101](https://github.com/haalfi/remote-store/pull/1101),
a draft that is never merged) as one commit to
`.claude/skills/ship/SKILL.md`.

- **Prose finding.** One whose fix changes no executable line: docs, specs,
  skills, comments, CHANGELOG, the trace. Every other finding is a code or test
  finding, and rule (c) does not touch it. This is the fix-commit classifier's
  definition (report § Run B baseline), so run B is scored by the rule it ran.
- **Mechanism.**
  - The fixer names the check, runs it before committing, and quotes it with
    what it returned in the reply: a command, a grep, a count, or the
    enumerated cases.
  - A round whose only must-fix findings are check-closed prose counts as
    converged, and the fix pass after it is verified by its recorded checks,
    not by a review round.
  - The exit gates already met (unprimed, whole-file, measuring) stay met
    across a check-closed prose fix. A prose fix narrowing a behavioural claim
    is measured by its own check.
  - The Step 5 report lists each check-closed prose finding with its check and
    what it returned.
- **Not covered.** A prose finding no check can settle, which the report puts at
  6% (judgement), and every code or test finding go through the loop as before.
- **Clauses it waives**, for check-closed prose only, each at its home, as the
  variant commit names them:
  - [ADR-0033](../adrs/0033-ship-convergence-driven-review.md)'s *Terminate the
    review loop on convergence*: a round whose only must-fix findings are
    check-closed prose counts as converged;
  - ADR-0033's *The loop may not end on an unreviewed fix pass*: that fix pass
    is verified by its recorded checks;
  - [ADR-0034](../adrs/0034-ship-panel-rounds-and-unprimed-exit.md)'s *The loop
    cannot end until an unprimed reviewer has seen the final state*;
  - [ADR-0037](../adrs/0037-whole-file-gate-and-derived-figures.md)'s
    whole-file gate: a met gate stays met across a check-closed prose fix;
  - [ADR-0035](../adrs/0035-vary-method-not-model.md)'s *A premise about
    existing behaviour is executed, not read, before it ships*: a met gate stays
    met, and a prose fix narrowing a behavioural claim is measured by its own
    check.

  ADR-0036 is unchanged.
- **Process budget.** Rule (c) grows `ship/SKILL.md`, so under
  [BK-422](../traces/bk-422-process-budget.yml) the variant commit records a
  raise with `python scripts/check_process_budget.py --raise --item BK-418` and
  commits `sdd/process-budget.json` beside the skill: 295,438 to 297,425 bytes at
  the variant's current head (its `raises` entry). The budget file is
  bookkeeping, not behaviour.

### Not in run B

**Two candidates that act on the same cost stay out, so that rule (c) is the
only change run B scores.**

- **BK-423**, a quantifier rule at authoring time, is held until run B is
  scored, because it acts on the findings rule (c) targets.
- **A smaller reviewer input** (the report's hypotheses 3 and 4: what every
  reviewer re-reads) was left out by the maintainer and stays a candidate for a
  later RFC.

## Experiment

**Run B is one `/ship BUG-280` delivery from master plus the variant commit,
compared with run A's second route round by round, not only in totals.** With
n = 1 per arm, the comparison can reject a rule that does nothing or does harm,
but cannot estimate a rate; the decision rule is written for that.

### Start conditions

**Run B starts as run A did, from a recorded base, with nothing steering it
toward run A's outcome.**

- Master after this RFC's rewrite merges, plus the variant commit rebased onto
  it, which touches `.claude/skills/ship/SKILL.md` and `sdd/process-budget.json`
  only. Both SHAs are recorded in #1101's body and in the report's run B
  section.
- A fresh worktree at the variant SHA, without run A's branch.
- A fresh session whose first prompt is exactly `/ship BUG-280`. At the
  handoff line, `/clear`, then `/ship resume <N>`.
- No other test suite running on the machine during the run.
- The same model as run A.
- Watched with `tokkit.py live` and reported with `tokkit.py report --json`,
  counting the resumed session with the build session.

Run A's PR #1093 stays a draft until the comparison is done. The better of the
two PRs is then merged and the other closed.

### Metrics

Run B's values come from the same scripts as run A's route 2, whose results are
in the report's `results/`.

| Level | Metric | Source | Run A, route 2 |
| --- | --- | --- | --- |
| Run | Units from the first call to the close; loop units from the first round | `tokkit.py report --json`, `route_baseline.py` | `run_a_route2.json`: 28.19 M, 22.62 M |
| Round | Members, main context at the round's start, main and subagent units | same, `rounds` | `run_a_route2.json` |
| Round | Findings, prose and code by the fix-commit classifier | `pr_rounds.py --pr <N>` | `pr_1093_rounds.json`, route 2 |
| Rule (c) | Rounds closed on check-closed prose alone; check-closed prose fixes and the check each quotes | the PR's replies, the Step 5 report | — |
| Gate | Gate runs, cut-offs, idle stalls | `gates.py` | `run_a_final_gates.json`, whole run |
| Outcome | Must-fix findings the maintainer's review finds after the close | the PR | PR #1093 |

By the classifier, every one of route 2's six rounds had at least one code
finding (3, 1, 4, 4, 5 and 1, from `pr_1093_rounds.json` `rounds`, route 2), so
under rule (c) none of them would have converged on prose alone. The classifier
errs toward code on #1093 (report § Run B baseline), and run B goes through the
same rule.

### Decision rule

**Fixed before run B starts. Rule (c) goes on to an ADR amendment (Phase 1)
only if it fired, the loop was shorter, and no prose fix it closed without
review proved false.** The baseline is route 2, not route 1: route 1 ran a
plan the re-plan at `cdcaa35c6` discarded, and route 2 shipped the scope
PR #1093 holds, `LocalBackend`'s listing methods only (report § Run B
baseline). Route 2 still started with route 1's context, 113k at its first
round (`run_a_route2.json` `route.rounds`).

**Scope is observed, not set.** BUG-280's entry leaves the scope open (the
three methods, or the listing-generator pattern across backends), and run B's
prompt stays exactly `/ship BUG-280`, so its § Orient dialog picks the scope.
The round and unit checks below compare against route 2 only when that dialog
picks `LocalBackend`'s listing methods. On any other scope they are void:
run B is scored on the remaining checks, and the report records the scope it
took.

| Keeps if all hold | Fails if any holds |
| --- | --- |
| At least one round closes on check-closed prose alone, with no review round opened to verify it | Rule (c) never fires |
| Run B closes in fewer than route 2's six rounds | A prose fix closed by check proves false, in a later round or in the maintainer's post-close review |
| Every check-closed prose fix quotes its check and what it returned | A check-closed fix's reply names no check, or a check that was not run |

**Run B as a whole fails** if its PR ships a must-fix defect that run A's PR
did not have, or if its units from the first call to the close are not lower
than route 2's 28.19 M. A failing run B keeps rule (c) out of `/ship`, and the
report records why.

<a id="confounds"></a>
### Confounds

**Master moves between the runs, and every change that could move run B's
figures is on it before run B starts.** These are environment, not
interventions, and none is scored. Derived with
`git log 31ebe6be7..origin/master` over `CLAUDE.md`, `.claude/`,
`sdd/CONTENT-RULES.md`, `sdd/CLAUDE-REFERENCE.md`, `sdd/traces/_schema.yml`,
`scripts/`, `infra/` and `pyproject.toml`, where `31ebe6be7` is run A's fork
point:

- #1099, BK-414's lookup tool: [dossier](../backlog/bk-414-sdd-lookup.md);
- #1103, `/ship` § Orient and the handoff at the PR with `/ship resume`:
  [trace](../traces/bk-418-orient.yml);
- #1105, suite lock, per-test timeout, background-wait deadline:
  [BK-419](../backlog/bk-419-local-gate-unbounded-wait.md);
- #1106, claim discipline (a) and (b):
  [`CONTENT-RULES.md` Rule 8](../CONTENT-RULES.md#change-details-what-it-changes);
- #1107, the moto fixture port race: [trace](../traces/bug-315-moto-port-race.yml);
- #1108, workers capped by free memory:
  [trace](../traces/bk-421-memory-aware-workers.yml);
- #1109, `CONTENT-RULES.md` restructured, one-sentence lead per rule;
- #1110, the process-file budget: [trace](../traces/bk-422-process-budget.yml).

Rule 8 (#1106) and the handoff (#1103) both aim at fewer and cheaper rounds, so
a shorter loop alone does not show that rule (c) caused it; that is why the
decision rule also requires rule (c) to fire. Run B's author knows BUG-280 only
through what master holds, and that is intended. This RFC, the report and the
variant also add to later sessions' context.

## Roadmap

**Three phases, each with its exit fixed before it starts. Phase 0 can stop
the whole effort.**

| Phase | Goal | Deliverables | Exit |
| --- | --- | --- | --- |
| **0. Test** | Decide from one delivery whether rule (c) holds | The variant ([#1101](https://github.com/haalfi/remote-store/pull/1101)) rebased onto master; run B; the comparison in the report's run B section | The decision rule above |
| **1. Amend** | Put rule (c) into process, if kept | One ADR amending the five clauses under [Proposal](#proposal); `/ship` carrying rule (c); #1101 closed. If not kept: #1101 closes and the report records why | The ADR accepted and `/ship` carrying rule (c), or #1101 closed |
| **2. Confirm** | Check the gain on deliveries that are not BUG-280 | The next two `/ship` deliveries, measured with the same metrics | Rounds and units no worse than run B's on both; otherwise reopen |

BK-423 is decided after run B is scored, whichever way Phase 0 goes.

## Alternatives Considered

**Every rejected option either ends the loop on prose no check has settled,
or changes the ADRs before one delivery has tested the change.**

- **Amend the ADRs now, on the report alone.** Rejected: the ADR chain was built
  one measured delivery at a time (ADR-0033 to ADR-0037), and amending it from
  correlations would break that.
- **Rule (c) in the tail only**, from the first round with no code finding after
  a verified code fix, as this RFC first proposed. Rejected for run B: that
  trigger never fires on a PR without code findings, which is 17 of the 41 PRs
  with a review block (report § 5).
- **A hard round cap.** Rejected for the reason ADR-0033 gives: a cap ships
  defects the rounds after it would find. Rule (c) ends rounds only for prose a
  recorded check closes.

## Impact

**No public API, runtime behaviour or user documentation changes. The impact
is on one skill and, if rule (c) is kept, one ADR.**

- **Public API / backwards compatibility:** none.
- **Process:** Phase 0 adds an unmerged variant branch of `/ship`. If rule (c)
  is kept, Phase 1 amends ADR-0033 (convergence and fix-pass clauses),
  ADR-0034 (unprimed exit gate), ADR-0035 (measuring clause) and ADR-0037
  (whole-file gate) for check-closed prose. ADR-0036 is not amended.
- **Ripples to carry when built:** `/ship` § Stop rule, § Rules and Step 5;
  `/fix-pr`'s reply rules, which carry the recorded check; the process budget's
  raise.

## Open Questions

**One question run B cannot answer, because BUG-280 is a code PR.**

1. **A delivery without code findings.** Run B is a code PR, so it cannot show
   what rule (c) does on the 17 of 41 PRs that drew prose and trace findings
   only (report § 5). Phase 2 should include such a delivery before rule (c) is
   taken as settled for them.

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
- Backlog: BK-418 (this RFC), BK-423 (held until run B is scored).
