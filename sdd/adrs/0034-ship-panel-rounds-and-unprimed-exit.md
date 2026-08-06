# ADR-0034: Panel Rounds and an Unprimed Exit Gate for `/ship` Review

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0033 |

Amends the round-composition and termination clauses of
[ADR-0033](0033-ship-convergence-driven-review.md). Everything else in that
record — convergence over round counts, severity over counts, read-only
never-resumed reviewers, measurement over adjudication — is unchanged, and
[ADR-0020](0020-orchestrate-iterative-convergence.md) remains untouched.

## Context

ADR-0033 was derived from one delivery. The second delivery under the loop
(BK-340 / BUG-244, PR #949) ran six rounds — findings per round 2, 6, 4, 4, 2,
3 — with severity falling to zero bugs across the last two rounds while counts
held. It produced two signals the first delivery did not:

1. **Five findings shared one shape** — a thing changed, one description of it
   updated, a sibling description left stale — and every one arose from a fix
   the author generated mid-loop, not from the original work. BK-336's sweep
   rule attaches to review findings; nothing pointed a sweep at the author's
   own corrections, which is exactly where all five landed.
2. **A deliberately unprimed round 6** (no areas, no prior findings, no round
   history, run at the user's instruction after the soft ceiling) found a stale
   docstring three lines above a comment the author had edited in the same
   commit, inside a function four scoped rounds had read. A primed reviewer
   confirms what it is pointed at; the surface nobody named stayed unexamined
   through five rounds. ADR-0033 placed its one unprimed round *first*, where
   none of the mid-loop fixes yet existed to be seen.

Both signals are structural, not incidental: scoped rounds are aimed by
construction, and fixes are authored by someone the loop has already caught
being wrong in that file. n = 2 is thin evidence for a schedule; it is
sufficient evidence for guarantees about the closing state and about fix
passes, which is how the decisions below are split.

## Decision

- **From round 3 a round may widen to a panel**: parallel single-lens
  reviewers, each fresh and blind to the others, merged into one triage and
  one fix pass. Width follows the diff's breadth and the prior round's yield.
  This stays inside the convergence loop and its stop rule — it is not
  `/orchestrate`'s capped fan-out, which ADR-0020 still owns. *Reverse if*
  merging and deduplication cost more than the serial rounds they replace, or
  members mostly duplicate one another.

- **Every odd round carries one unprimed reviewer.** Round 1's sole reviewer
  is that member, as ADR-0033 already required; from round 3 the odd-round
  panel includes one, briefed with the PR alone, on a different model from the
  author's, same tier or higher. The cadence half: unprimed eyes on mid-loop
  state, not only the endpoints. *Reverse if* interleaved unprimed members
  reliably find nothing the exit gate's terminal pass would not.

- **The loop cannot end until an unprimed reviewer has seen the final state
  and found nothing must-fix.** The load-bearing half: the second delivery's
  defects were created mid-loop by fixes, so an earlier unprimed pass proves
  nothing about what ships. A closing round with no unprimed member gets one
  appended; like ADR-0033's verification round it counts toward the ceiling
  only if it finds something. *Reverse if* terminal unprimed passes stop
  finding anything across a meaningful sample of deliveries.

- **A fix pass sweeps the sibling descriptions of what it changed.** BK-336's
  sweep obligation extends from review findings to the fixer's own
  corrections — a coverage question, not a grep. The obligation and its report
  clause live in `/fix-pr`; `/ship` inherits them by citation. *Reverse if*
  these sweeps stop catching anything the review rounds do not.

The step sequence, panel mechanics, brief requirements and the amended stop
rule are operational contract and live in `.claude/skills/ship/SKILL.md` and
`.claude/skills/fix-pr/SKILL.md`.

## Consequences

- **Positive:** the two blind spots the second delivery measured — fixes
  nobody sweeps, surface nobody names — each get a structural interception
  where they arise, rather than a convention downstream of it.
- **Positive:** panels compress wall-clock: PR #949's four serial scoped
  rounds were four review-fix-gate cycles that plausibly fit in two panel
  rounds.
- **Negative:** both amendments raise compute cost on independent axes, on
  top of the bill ADR-0033's Context records. A panel multiplies reviewer
  passes per round — tokens rise even as wall-clock compresses — and the exit
  gate appends a terminal unprimed pass whenever the closing round lacks one
  (by parity, roughly every other delivery), plus a further fix pass and gate
  run when that pass finds something.
- **Negative:** triage and dedup load on the orchestrator grows with panel
  width, and width itself is a new judgement that can be miscalibrated in
  either direction.
- **Negative:** the evidence base is two deliveries. The exit gate and the
  fix-pass sweep follow directly from measured failures; the odd-round cadence
  and panel sizing are defaults chosen ahead of the evidence, which is why
  each carries its own reversal condition.
- **Neutral:** `/ship` moves closer to `/orchestrate`'s multi-reviewer shape.
  The boundary that matters is preserved: panels serve a convergence loop with
  an open-ended round count, not a capped consolidation.
