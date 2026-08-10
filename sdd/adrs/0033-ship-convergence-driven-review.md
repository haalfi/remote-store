# ADR-0033: Convergence-Driven Review for Single-PR Delivery

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

Introduces a second review-loop model, in the `/ship` skill, alongside the one
[ADR-0020](0020-orchestrate-iterative-convergence.md) defines for `/orchestrate`.
ADR-0020 is unaffected and keeps its fixed cap, and its user-as-tie-breaker
clause is preserved unchanged. Which model to reach for on a given task is a use
decision the `/ship` skill documents, not one this record makes.

## Context

`/orchestrate` reviewed with five domain experts, each reading every expert's
output, capped at **two rounds**; anything unresolved goes to the user. That
model assumes review findings are a fixed population to be drained, and that two
passes drain enough of it. (The five-expert half has since been withdrawn by
[ADR-0036](0036-reviewers-by-subject-and-method.md) — `/orchestrate` now selects
reviewers by lens and method too. The two-round cap, which is what this record
argues against, is unchanged and still ADR-0020's.)

A contract-reconciliation delivery (BK-324 / BK-331, PR #945: four backend
divergences across prose, Dafny, conformance and six backends) ran six review
rounds and produced evidence against both assumptions:

| Round | Findings | Character |
| ----- | -------- | --------- |
| 1 | 7 | Wrong behaviour; also a category error the author could not see |
| 2 | 6 | Wrong behaviour; the fixed class was incomplete |
| 3 | 6 | Prose asserting false things about behaviour |
| 4 | 5 | Prose asserting false things about prose |
| 5 | 1 | One real bug, in code no earlier round had examined |
| 6 | 0 bugs | The PR's own guide taught the bug the PR had just fixed |

Three observations drive this record:

1. **Rounds 2, 3 and 4 each found defects in the previous round's fixes.** A fix
   pass is not lower-risk than original work: it is new code written quickly, in
   a file where something was already wrong. A model that reviews the original
   diff N times and never reviews the corrections has an unbounded blind spot.
2. **Finding *count* plateaued while severity fell** (6, 6, 5). Count is a poor
   termination signal; the shift from "wrong behaviour" to "wrong prose about
   prose" is the real one.
3. **The highest-severity finding arrived at round 5**, in code no earlier round
   had examined, and only because that round was explicitly aimed at neglected
   surface. It was a 403 reported as `NotFound` on four operations across two
   backends, invisible to 7 976 passing tests because the branch carried an
   accurate `# pragma: no cover`.

Under a two-round cap this PR would have merged carrying an incomplete
root-spelling fix, the `NotFound`-for-denial regression, and a published guide
instructing third-party authors to reproduce it.

The cost is real, and it is why the skill carries its own guidance on when not
to reach for this loop. That delivery's six rounds ran
roughly a million subagent tokens and eight full `hatch run all` gates: the
review loop, not the implementation, dominated. This paragraph is the single
home for that measurement; the `/ship` skill links here rather than restating
it, since the figure is one delivery's history and not a forward estimate.

## Decision

- **Terminate the review loop on convergence, not on a round count.** Stop when
  a round yields zero must-fix findings, where must-fix means wrong once merged:
  incorrect behaviour, a false statement in a durable artifact, or a shipping
  gap. A soft ceiling of five finding-rounds triggers escalation to the user
  rather than silent termination. *Reverse if* loops routinely run long without
  the extra rounds changing what ships, so a fixed cap costs less than it saves.
  *Amended by [ADR-0034](0034-ship-panel-rounds-and-unprimed-exit.md):* a
  third stop clause — no ending until an unprimed reviewer has seen the final
  state clean.
  *Amended by [ADR-0037](0037-whole-file-gate-and-derived-figures.md):* a
  further stop clause — no ending until every changed file has been read whole
  against the final state. Convergence itself is unchanged; what a round must
  have looked at before it can be clean is not.

- **The loop may not end on an unreviewed fix pass.** Whatever the last round
  changed is itself reviewed before the PR is declared ready; that verification
  round does not count toward the ceiling. This is the concrete form of "a fix
  pass is not trusted work". *Reverse if* verification rounds over fix passes
  stop finding anything across a meaningful sample of deliveries.

- **Diversify reviewers rather than repeating one.** The first round is
  *unprimed*, receiving the diff, the goal and repo conventions but never the
  author's areas of concern, and runs on a different model from the author's so
  its blind spots differ. Later rounds each take one scoped lens, chosen by what
  earlier rounds did not examine. *Reverse if* unprimed rounds reliably
  duplicate what lens rounds find, making the diversity redundant.
  *Amended by [ADR-0034](0034-ship-panel-rounds-and-unprimed-exit.md):* rounds
  may widen to panels from round 3, with an unprimed member every odd round.
  *Amended by [ADR-0035](0035-vary-method-not-model.md):* the model clause is
  withdrawn — no repo skill pins or diversifies a model — and the diversity it
  bought moves to method, one member per panel reaching its verdict by
  execution. Unprimed-ness is unchanged.

- **Reviewers are read-only and never resumed; fixers may decline with
  evidence.** A resumed reviewer inherits its own prior conclusions and stops
  being an independent check. *Reverse if* declining is used to avoid work
  rather than to correct it.

- **Factual disputes are settled by measurement; contested decisions still go
  to the user.** A disagreement about what the code does is an experiment, not
  an adjudication. ADR-0020's "user is the sole tie-breaker" is unchanged and
  still governs what the code *should* do. *Reverse only* as a deliberate
  authority change, per ADR-0020.

Which skill to reach for is a use decision, not one this record makes. That,
with the step sequence, lens menu, brief requirements and triage table, is
operational contract and lives in `.claude/skills/ship/SKILL.md`.

## Consequences

- **Positive:** fix passes are reviewed rather than trusted, closing the blind
  spot that produced three of PR #945's defect rounds.
- **Positive:** severity-based termination stops the loop when it stops paying,
  rather than at an arbitrary round.
- **Positive:** the unprimed first round catches framing errors the author is
  structurally unable to see; lens rounds reach surface a repeated broad review
  does not.
- **Negative:** substantially more expensive than `/orchestrate`, by roughly the
  factor the Context records. Keeping that cost where it pays is left to the
  skill's own guidance on when not to use it.
- **Negative:** termination now depends on a judgement (is this finding
  must-fix?) rather than a counter. Miscalibration either ships defects or
  loops longer than needed; the soft ceiling bounds the second failure mode
  only.
- **Neutral:** the repo now has two review-loop models. Choosing between them is
  a judgement the `/ship` skill documents rather than one this record fixes, and
  `/orchestrate` carries a pointer to it so the incumbent path is not a dead end.
