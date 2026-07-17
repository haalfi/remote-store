# ADR-0019: Multi-Agent Orchestration Architecture

## Status

| Field         | Value      |
| ------------- | ---------- |
| Status        | Superseded |
| Supersedes    | —          |
| Superseded by | ADR-0020   |
| Amends        | —          |

## Context

As remote-store grows (~41 source files, 55 test files, 72 doc files), complex
tasks (new backends, cross-cutting features, spec-driven changes) require
coordinating work across four concerns: implementation, extensions, testing,
and documentation. A single agent juggling all concerns risks incomplete work,
hallucination, and context switching overhead (RFC-0009).

Three approaches were considered:

**Option A — Single agent (status quo).** One Claude Code session handles
everything sequentially. Works for small tasks but scales poorly: missed doc
updates, incomplete ripple-checks, untested error paths.

**Option B — Custom Python orchestrator.** `ThreadPoolExecutor` + Anthropic SDK.
Full control over model selection, cost optimization, and parallelism. But adds
infrastructure to maintain, breaks Claude Code integration (no git context
inheritance), and violates KISS for a problem that has a native solution.

**Option C — Claude Code native agents.** Orchestrator (main session) spawns
domain experts via the Agent tool. Experts run in parallel with full repo
access. Orchestrator aggregates results and handles cross-domain concerns.

## Decision

<!-- adr:decision -->
**Option C — Claude Code native agents.** An orchestrator (the main session)
spawns domain-scoped experts (Backend, Ext, Test, Doc) in parallel via the
Agent tool; each runs with full repo access, and the orchestrator aggregates
their results and handles cross-domain concerns (ripple-checks, CHANGELOG,
BACKLOG, validation).
<!-- /adr:decision -->

```
Task (user invokes /orchestrate)
         ↓
    Orchestrator
    (pre-check, plan architecture)
         ↓
┌────────┬────────┬────────┬────────┐
│Backend │  Ext   │ Test   │  Doc   │
│Expert  │Expert  │Expert  │Expert  │
└────────┴────────┴────────┴────────┘
  (parallel, domain-scoped agents)
         ↓
    Orchestrator
    (ripple-checks, CHANGELOG, BACKLOG, validate)
```

### Two modes

- **Implementation mode** (code changes): experts write code/tests/docs within
  their domain. Orchestrator handles cross-domain files.
- **Review mode** (SDD-only changes): experts review from their domain
  perspective but do not implement. Reports go to the orchestrator for
  aggregation.

### Expert activation

All code changes activate all 4 experts. Each evaluates from their domain —
the Extension expert always assesses downstream impact on `ext/` even when
extension files aren't directly modified. For SDD-only changes, all 4 review.

### Aggregation

The orchestrator:
1. Collects expert outputs (files changed, issues found, assessments)
2. Runs ripple-check audit against `CLAUDE-REFERENCE.md`
3. Fixes cross-domain gaps (README, pyproject.toml, nav files)
4. Validates via `hatch run all`

### Domain boundaries

> **Superseded by [ADR-0031](0031-expert-personas-as-subagent-files.md).** The
> per-expert persona definitions (identity, domain, foundation, constraints) now
> live as standalone Claude Code subagents in `.claude/agents/`, referenced by
> the `/orchestrate` skill via `subagent_type`, rather than inline in the skill.
> The domain boundaries themselves are unchanged.

| Expert | Domain | Foundation |
|--------|--------|-----------|
| Store & Backend | `src/remote_store/` (excluding `ext/`) | DESIGN.md + relevant specs/ADRs |
| Extension | `src/remote_store/ext/` | DESIGN.md + relevant specs/ADRs |
| Testing | `tests/` | TESTING.md, DESIGN.md § 11 |
| Documentation | `docs-src/`, `examples/`, `guides/`, docstrings | DOCUMENTATION.md, DESIGN.md § 4 |

README.md and CHANGELOG.md are cross-domain files owned by the orchestrator.
The Documentation Expert assesses their impact but does not write to them.

## Consequences

- Complex tasks can be parallelized across 4 domain experts.
- Each expert reads specs before writing — hallucination mitigation.
- Extension impact is always evaluated, even for non-extension changes.
- No custom infrastructure — uses Claude Code's native Agent tool.
- Orchestrator is the single point of cross-domain consistency.
- Overhead for simple tasks: the skill is optional, not mandatory.
