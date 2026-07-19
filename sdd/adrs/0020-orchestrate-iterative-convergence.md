# ADR-0020: Orchestrate Iterative Convergence Model

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | ADR-0019 |
| Superseded by | —        |
| Amends        | —        |

## Context

ADR-0019 introduced multi-agent orchestration with parallel domain experts.
After real-world usage (BK-123: 8 findings across 4 experts), several gaps
emerged:

1. **No cross-validation.** Testing Expert wrote tests from the *plan*, not
   the *actual code* other experts produced. If a code expert deviated from
   the plan, tests wouldn't match.
2. **No inter-expert communication.** Documentation Expert updated guides
   based on the plan, not actual code changes. Accurate by luck, not by
   design.
3. **Tightly coupled changes** (e.g., new Store method spanning backend +
   extension + tests) need sequential or phased execution, not full parallel.
4. **Expert self-review worked well.** A review round after implementation
   found 13 real issues (1 bug, spec gaps, test gaps, doc gaps). Worth
   formalizing.

The single-pass model (plan → execute → post-process) works for simple tasks
but lacks feedback loops for complex work where experts need to see each
other's output.

## Decision

**Adopt an iterative convergence model, replacing the single-pass model.**
Planning, execution, and post-processing are wrapped in feedback loops — plan
refinement before execution, result consolidation after, and expert
cross-review — so experts act on each other's *actual output*, not the plan
alone. That gap is what single-pass could not close for coupled, multi-domain
work. *Reverse if* the loops stop catching cross-domain mismatches that
single-pass missed — i.e. the loop overhead no longer pays for itself.

**Gate loop depth on task complexity, via three modes (Simple / Standard /
Complex).** Trivial single-domain work runs plan → execute → review with no
refinement or consolidation; multi-domain work adds both; ambiguous or
tightly-coupled work additionally requires user confirmation before executing
and before each review round. The loops *are* the model's cost, so trivial
tasks must be able to opt out of them. The orchestrator picks the mode; the
user overrides. *Reverse if* one mode serves in practice (collapse the tiers)
or a failure class appears that the three do not cover.

**Bound review to a fixed maximum number of rounds; the user resolves anything
still open after the cap.** A hard round cap guarantees termination instead of
unbounded convergence. *Reverse if* the cap routinely discards unresolved real
issues rather than surfacing them to the user.

**The user is the sole tie-breaker.** The orchestrator presents expert
disagreements and waits; it never adjudicates them autonomously, keeping a
human as final authority on contested changes. *Reverse only* as a deliberate
authority change — if orchestration is ever trusted to resolve domain conflicts
without a human — never as a tuning tweak.

**Carry forward ADR-0019's delegation structure; replace only its control
flow.** Domain-expert delegation, per-domain boundaries and foundation docs,
orchestrator-owned cross-domain files (CHANGELOG, BACKLOG, README), and bug-fix
TDD ordering (Testing Expert first) are unchanged. *Reverse per those
mechanisms' own records* (ADR-0019 and its amendments) if the delegation
structure itself is revisited.

The concrete step sequence, per-mode flow, consolidation status legend, exact
round cap, expert-response format, and the current expert roster are
operational contract, not decision rationale. They live in the `/orchestrate`
skill (`.claude/skills/orchestrate/SKILL.md`) and the persona files
(`.claude/agents/`), which are edited when the process is tuned.

## Consequences

- Complex tasks get feedback loops that catch cross-domain mismatches early.
- Simple tasks stay fast — no unnecessary refinement or consolidation.
- User is always the final authority on unresolved disagreements.
- The bounded review-round cap prevents infinite convergence loops.
- Plan refinement catches expert-identified gaps before any code is written.
- More orchestrator complexity — the skill is longer and has branching logic.
