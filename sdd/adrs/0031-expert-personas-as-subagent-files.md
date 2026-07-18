# ADR-0031: Expert Personas as Standalone Subagent Files

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0019 |

Amends the persona-definition realization of
[ADR-0019](0019-multi-agent-orchestration.md) (its "Domain boundaries" clause).
Orthogonal to [ADR-0020](0020-orchestrate-iterative-convergence.md), which owns
the convergence flow and is unaffected.

## Context

ADR-0019 chose "Option C — Claude Code native agents": the orchestrator spawns
domain experts via the Agent tool. In the shipped `/orchestrate` skill, however,
each expert persona (identity, domain, foundation, constraints, done-when) lived
as a fenced prompt block **inline in `SKILL.md`**. That had three costs:

1. **No reuse.** The personas could only be reached through `/orchestrate`. A
   plain "have the testing expert assess coverage" needed the whole skill.
2. **Skill bloat.** Five fenced personas were ~170 lines of `SKILL.md`, mixing
   orchestration *logic* (modes, rounds, consolidation) with persona *content*.
3. **Template drift risk.** The inline blocks carried `TASK: [orchestrator
   fills this]` slots and skill-relative markdown links (`../../../sdd/...`)
   whose depth was tied to the skill's location.

Claude Code resolves `subagent_type` from `.claude/agents/*.md` files, which are
also independently invocable and model-routable via their `description`. That is
the native home ADR-0019's "native agents" decision pointed at; the inline blocks
were a partial realization of it.

A two-path trial (direct `subagent_type: testing-expert` invocation vs the same
persona reached through the skill) confirmed the persona behaves identically
either way — structurally identical, constraint-faithful output, differing only
within normal run-to-run variance. See BK-315.

## Decision

Each expert persona is a **standalone Claude Code subagent** in
`.claude/agents/<name>.md` — the single source of truth for that persona.
The `/orchestrate` skill no longer embeds personas; it references each expert by
`subagent_type` (in its Step 4 execute sections) and supplies the per-call task
and mode in the invocation prompt.

- **Repo-root-relative paths.** Personas cite `sdd/TESTING.md` etc. as plain
  paths (agents run with cwd at the repo root).
- **Per-call context via the prompt.** The static persona holds identity, domain,
  constraints, and done-when; the invocation prompt carries the task, the specs
  to trace, and the mode (implement vs review).

Domain boundaries, the three orchestration modes, the convergence flow, and
cross-domain file ownership (README/CHANGELOG owned by the orchestrator) are
unchanged.

## Consequences

- **Positive:** personas are reusable outside `/orchestrate` and routable by the
  main loop via their `description`; `SKILL.md` shrinks to orchestration logic
  only; each persona has one authoritative location instead of an inline block.
- **Positive:** native subagent frontmatter (`description`, and optionally
  `tools`/`model`) is now available per expert, which inline blocks could not
  carry.
- **Negative / neutral:** the skill's `disable-model-invocation: true` guard
  scopes only the skill; the extracted agents are model-routable, so the main
  loop may spawn an expert outside an orchestration run. This is the intended
  reuse, but it is a behavior change from the fully-gated inline model.
- **Neutral:** editing a persona is now a `.claude/agents/` change rather than a
  `SKILL.md` change; the skill and the agents must agree on `subagent_type`
  names.
