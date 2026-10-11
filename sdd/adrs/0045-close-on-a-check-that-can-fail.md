# ADR-0045: A Close Rests on a Check That Can Fail, and Spend Is Judged With Defects

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0033, ADR-0044 |

Amends [ADR-0033](0033-ship-convergence-driven-review.md)'s *factual disputes
are settled by measurement* clause, which gains a condition on what counts as
one, and [ADR-0044](0044-ship-subject-list-review-contract.md)'s row-coverage
clause, which gains the same condition. Neither loses anything.
[ADR-0037](0037-whole-file-gate-and-derived-figures.md)'s derivation clause is
untouched: it asks where a figure came from, this record asks whether a check
offered as a close could have come out the other way.
[ADR-0034](0034-ship-panel-rounds-and-unprimed-exit.md),
[ADR-0035](0035-vary-method-not-model.md) and
[ADR-0036](0036-reviewers-by-subject-and-method.md) are untouched: nothing here
changes who reviews or when the loop may stop.

## Context

BK-430, from the token-spend research
([proposals 2 and 3](../research/research-token-spend-means.md#6-proposals)).
Run B of `/ship BUG-280` closed ten prose findings on a check the fixer ran and
quoted. Four of those checks could not have shown their claim false: a `git
grep` for wording, twice, and a backlog-shape check run on what two items say
rather than on their form
([report § Rule (c) against the decision rule](../research/token-usage/report.md#rule-c-against-the-decision-rule)).
The rule under test was met as written; the check had become ritual.

Run B also cost a quarter of run A's units and shipped two regressions run A's
PR had avoided
([report § The two deliveries compared](../research/token-usage/report.md#the-two-deliveries-compared)).
RFC-0020's decision rule caught that only because it failed the run on a
must-fix defect the slower run did not have, a clause written for that one
experiment. Nothing on master weighs a cheaper loop by what it ships.

## Decision

- **A close that rests on a check counts only if the check could have returned
  the claim false.** This binds every close by evidence in a review loop: fix
  shape (3), a refute's evidence, and a subject-list row marked covered. The
  reply names the result that would have refuted the claim; a check that tests
  wording or shape is evidence about wording or shape, never about content. A
  test added in a fix pass already owes this through its mutation check; this
  clause gives every other check the same obligation. *Reverse if* the clause
  adds rounds across a meaningful sample of deliveries without changing what
  ships.

- **A change to the review loop justified by spend also compares the defects
  its deliveries shipped.** Fewer units or rounds justify a change to `/ship`
  only beside the defects those deliveries shipped against the deliveries they
  replace; spend alone never does, since the shorter loop that found less is
  exactly what it rewards. *Reverse if* defect counts per delivery prove too
  sparse to compare, at which point the cheaper honest answer is to stop
  claiming a saving.

Where each clause sits in the triage table, the fix-pass obligations and the
row coverage is operational contract and lives in
`.claude/skills/ship/SKILL.md` and `.claude/skills/fix-pr/SKILL.md`.

## Consequences

- **Positive:** a close is evidence a reader can disagree with, not a ritual a
  reviewer can only re-run; the four run B closes would each have had to name
  another check or stay open.
- **Positive:** the next measured deliveries are compared on units, rounds and
  defects together, as the research's proposal 6 asks.
- **Negative:** a fixer must think about the failing result before running the
  check, which costs a sentence per reply and may turn a quick grep into a probe.
- **Negative:** whether a check *could* have failed is a judgement, and a
  reviewer can still accept one that could not. The clause makes the judgement
  visible in the reply; it does not make it mechanical.
- **Negative:** this changes how findings close inside BK-384's graduation
  sample for RFC-0015, to be recorded there.
- **Neutral:** `/orchestrate` applies `/fix-pr`'s Step 3 and so inherits the
  first clause; it has no stop rule and no spend comparison for the second.
