# ADR-0035: Vary Method, Not Model, in `/ship` Review

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0033, ADR-0034 |

Amends one clause in each: [ADR-0033](0033-ship-convergence-driven-review.md)'s
*Diversify reviewers rather than repeating one*, and
[ADR-0034](0034-ship-panel-rounds-and-unprimed-exit.md)'s *Every odd round
carries one unprimed reviewer* together with the model terms its exit-gate
clause inherits. Both records keep everything else, including the unprimed
requirement itself, which this record strengthens rather than weakens.

## Context

The third delivery under the loop (BUG-243, PR #952) ran eight rounds, ten
commits, and discovered four backlog items and one spec-vs-spec conflict. It did
not converge; it stopped because the work had to ship. The evidence is recorded
in full under BK-344 and in
[`sdd/traces/bug-243-missing-ok-absent-container.yml`](../traces/bug-243-missing-ok-absent-container.yml).

Two of its signals bear on reviewer composition, and they point the same way.

1. **Method, not identity, separated the productive rounds.** Three premises in
   that work were asserted and disproved, and every one fell to *running*
   something: that Local treats an absent root as an absent path (round 4), that
   a gate covered the in-memory cases (round 7), and that a new rule merely
   ratified existing behaviour on every flat-namespace backend (round 8,
   measured on `origin/master`). Rounds that read the diff for internal
   consistency found real defects — stale summaries, mis-scoped spec marks — and
   never a false premise. In the final round the two reviewers differed most in
   method: one read the artifact set, one measured `master` and enumerated
   thirteen backends against `Capability.DELETE`, and the second found the false
   premise and a fifth defect the first did not.

2. **The loop varied every reviewer axis except that one.** ADR-0033 and
   ADR-0034 diversify *who* reviews — persona, model, primed-ness — and nothing
   diversifies *how*. A false premise is consistent with everything in the diff,
   so reviewers who share a method share the blind spot regardless of how many
   of them there are.

The model axis also stopped being cheap: Fable moved to usage-based pricing, so
"use a different model" is now a per-round cost rather than a free variation. No
finding across three deliveries has been attributed to model difference, while
three false premises are directly attributable to method. The axis that was
never measured to pay now has a bill.

An open item, BK-338, already held that no repo skill should pin a model; the
pin predated it and survived.

## Decision

- **No repo skill pins, prefers, or diversifies an LLM model.** `/ship` selects
  reviewers by lens and method only. Unprimed-ness carries reviewer diversity on
  its own: what makes an unprimed pass independent is what it was *not* told,
  which is a property of the brief and not of who reads it. *Reverse if* a
  measured comparison attributes findings to model difference at a rate that
  justifies the per-round cost.

- **Every panel carries one measuring member**, reaching its verdict by
  execution rather than reading. This is the axis the model requirement vacates,
  and the trade is deliberate: one member per panel, spent on method instead of
  identity. *Reverse if* measuring members stop finding what reading members
  miss across a meaningful sample of deliveries.

- **A premise about existing behaviour is executed, not read, before it ships**,
  enforced by a stop-rule clause and not by the panel obligation alone. A PR
  asserting no such claim satisfies it vacuously. A false premise is consistent
  with the diff, so no amount of reading reaches it. *Reverse if* premise checks
  reliably confirm what a reading round already established.

- **Panel width follows the subject set, not the diff** — the reach of what the
  change's own words pick out, alongside the diff's breadth and the prior
  round's yield. Breadth alone cannot see a subject the change binds and the
  diff never touches. *Reverse if* subject enumeration reliably reproduces the
  file list.

- **The soft ceiling stays at five finding-rounds and stays soft, but the
  escalation carries evidence** — severity trend, per-round yield, unreached
  subjects — rather than the count. Three deliveries is too thin to move the
  loop's only bound, and too much to keep deciding on the one number ADR-0033
  already identified as a poor termination signal. *Reverse if* a meaningful
  sample shows rounds past the ceiling reliably finding nothing.

The step sequence, panel mechanics, lens menu, brief requirements, the
repeat-site check and the CI check are operational contract and live in
`.claude/skills/ship/SKILL.md`, `.claude/skills/fix-pr/SKILL.md` and
`.claude/skills/rvw-pr/SKILL.md`.

## Consequences

- **Positive:** the diversity budget moves from an axis with no measured yield
  to one with three measured catches in a single delivery. Each of those three
  was a false premise that survived every reading-based round — one of them
  eight rounds, including a round explicitly hunting stale claims.
- **Positive:** panel width now reaches subjects the diff does not. A
  DELETE-capable backend that contradicted the new clause by *specification*
  went unnamed for six rounds under breadth-only sizing, because the diff never
  touched it.
- **Positive:** reviewer selection no longer depends on which models exist or
  what they cost, so the skill stops carrying a fact that changes underneath it.
  BK-338's "do not pin a model in a repo skill" is discharged; its roster
  question is untouched and still open.
- **Positive:** solo reviewer passes now invoke `/rvw-pr` directly instead of
  spawning an `Agent`, since the model override was the only reason to spawn.
  That restores the skill's `allowed-tools` withholding of `Edit` and `Write`,
  which the spawn path loses and must restate as an instruction. It is not a
  read-only guarantee — that frontmatter grants `Bash` — and what covers the
  `Bash` residue is the unchanged-`HEAD` and clean-tree check every pass
  carries. `Agent` spawning remains for panels, which `/rvw-pr` cannot form.
- **Negative:** a measuring member costs more than a reading one. It runs code,
  which means environment setup, gate time, and a longer round.
- **Negative:** it also widens a reviewer's tool surface. `/rvw-pr` confined
  `Bash` to `gh` PR-content reads, which would have made this decision inert —
  the obligation to measure with no permission to run. That constraint is now
  bounded rather than removed, and the bound and the measurement showing it
  keeps the review round's clean-tree guarantee live in that skill. It is
  enforced by instruction, so a reviewer that ignores it invalidates the round
  rather than being stopped.
- **Negative:** the premise obligation has no mechanical trigger. Nothing detects
  that a sentence is a claim about existing behaviour, so it rests on the
  brief and on review, like the sibling-sweep obligation it sits beside. It
  needed the stop-rule clause because the panel obligation alone starts at
  round 3: a one- or two-round delivery is solo throughout, and the stop rule
  expressly permits ending on a clean round 1, so the absolute wording would
  have been aspirational on exactly the short deliveries where nobody is
  watching. Same structure, and the same reason, as ADR-0034's unprimed exit
  gate.
- **Negative:** subject enumeration is a new judgement at Step 1, made before
  the work exists to be judged, and an under-enumerated list understates panel
  width for the whole run.
- **Neutral:** the evidence base is three deliveries, and the measuring member
  is the only decision here derived from a direct comparison — the final round's
  two reviewers differed in method and yielded differently. The rest follow from
  single-delivery failures, which is why each carries its own reversal
  condition.
