# ADR-0044: The Subject List Is the Review's Contract

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0033 |

Amends [ADR-0033](0033-ship-convergence-driven-review.md)'s *terminate the
review loop on convergence* clause, which a further stop clause joins. Unlike
[ADR-0037](0037-whole-file-gate-and-derived-figures.md)'s gate, this clause is
not discharged by an appended pass, so
[ADR-0034](0034-ship-panel-rounds-and-unprimed-exit.md)'s exit-gate shape is
not instantiated and that record is untouched; so are
[ADR-0035](0035-vary-method-not-model.md) and
[ADR-0036](0036-reviewers-by-subject-and-method.md): nothing here changes how
a reviewer is selected or what method it uses, only what the loop must have
covered before it closes.

## Context

BK-425, from the token-spend research. Two deliveries of `/ship BUG-280` were
compared case by case
([report § The two deliveries compared](../research/token-usage/report.md#the-two-deliveries-compared)).
Run B (#1113) was the better fix in a third of the lines and reached it in five
review rounds, but it shipped two regressions run A (#1093) had avoided: a link
into a folder the caller cannot enter makes the whole listing raise, and a
subfolder in the classic delete-pending state on Windows raises
`PermissionDenied`. Run A's round 7 had measured the second state.

Run B's handoff already had the right shape: the `/ship` subject list marked
executed, read only or not reached, and a list of the author's doubts. Two
things were missing. No row named a Windows deletion state or a link into a
locked folder, because the list named subjects and not the platforms and edge
cases each touched. And nothing obliged a round to take up a row marked not
reached: the stop rule's five clauses at the time (a round with no must-fix
finding, a reviewed fix pass, an unprimed reviewer, whole-file reading,
measured claims) named nothing on the list. A shorter loop is a
saving only while its reviewers still reach what the change touches
([research proposal 9](../research/research-token-spend-means.md#6-proposals)).

## Decision

- **The Step 1 subject list is the review's contract, and the loop cannot end
  until every row is covered or the user waived it.** Each row names a subject,
  the platforms and edge cases it touches, its known risk, and its executed,
  read only or not reached mark; it travels in the handoff to the session that
  runs the loop. Scoped briefs carry the uncovered rows, each assigned to a
  member. A row is covered when a pass reports its verdict on it and the method;
  a row whose risk is behaviour is covered only by running it. Uncovered rows
  that alone block the stop go to the user in one dialog, and only the user
  waives one: the session that wants to stop is not the one to decide what it
  may leave unreviewed. *Reverse if* covering rows adds rounds across a
  meaningful sample of deliveries without changing what ships.
  *Amended by [ADR-0045](0045-close-on-a-check-that-can-fail.md):* the method
  that covers a row must be one that could have found the row's risk.

The row shape, the brief item and the dialog are operational contract and live
in `.claude/skills/ship/SKILL.md`.

## Consequences

- **Positive:** the loop's termination now depends on what the change touches,
  not only on what the reviewers happened to find; a not-reached row can no
  longer go silent.
- **Positive:** a waiver is a decision with a reason in the Step 5 report,
  where a coverage bound used to be a note the author wrote about their own
  work.
- **Negative:** rows the local machine cannot run, such as another OS or
  interpreter, are covered only by a CI lane that executes them or waived, so
  the dialog will recur on platform-bound changes.
- **Negative:** covering rows may add rounds. BK-384 reads RFC-0015's
  graduation from the next three deliveries' finding counts, and this clause
  is a composition change inside that sample, to be recorded there.
- **Negative:** the rows are only as good as the author's enumeration. A
  platform nobody names is still missed; the Pre-work rows are a cross-check,
  and BK-346 records that some of them answer a neighbouring question.
- **Neutral:** `/orchestrate` keeps its capped rounds
  ([ADR-0020](0020-orchestrate-iterative-convergence.md)) and its subject list
  stays a stated coverage bound; it has no convergence stop for this clause to
  join.
