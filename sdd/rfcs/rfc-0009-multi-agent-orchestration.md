# RFC-0009: Multi-Agent Orchestration for Complex Tasks

## Status

Superseded by [ADR-0019](../adrs/0019-multi-agent-orchestration.md) / [ADR-0020](../adrs/0020-orchestrate-iterative-convergence.md)

## Summary

Introduce a multi-agent orchestration pattern to handle complex, multi-concern tasks (backend implementation, extension development, testing, documentation) in parallel. An orchestrator breaks down the task and delegates to 4 subject matter experts (Store & Backend, Extension, Testing, Documentation), each with mandatory SDD foundation but focused on their domain. Post-implementation ripple-checks and CHANGELOG updates are orchestrator tasks, not separate experts.

## Motivation

remote-store has grown to ~2MB across 41 source files, 55 test files, and 72 documentation files, spanning multiple non-trivial concerns:

1. **Backend implementation** — ABC contract, error mapping, capabilities
2. **Testing** — coverage targets, edge cases, conformance fixtures
3. **Documentation** — user guides, API docs, navigation (mkdocs.yml, _nav.yml)
4. **Spec verification** — RFC review, spec completeness, dependency mapping
5. **Process compliance** — BACKLOG entries, CHANGELOG, ripple-checks against CLAUDE-REFERENCE.md

**Current bottleneck:** A single Claude Code agent must juggle all concerns simultaneously, risking:

- Incomplete work (missed doc updates, incomplete ripple-checks, untested error paths)
- Hallucination (agents inventing design instead of reading specs)
- Context switching overhead (large task = many file reads, many context windows)

## Proposal

### Four Subject Matter Experts + Orchestrator Role

| Role | Scope | Domain Focus | SDD Foundation |
|------|-------|--------------|-----------------|
| **Orchestrator** (meta-role) | Break down task, delegate, post-implementation ripple-checks & CHANGELOG, compile results | Task decomposition, SDD enforcement, cross-file consistency | Mandatory: CLAUDE.md, BACKLOG, ripple-check table |
| **Store & Backend Expert** | `src/remote_store/` + `src/remote_store/backends/` — Store API, Backend ABC, error mapping, capabilities | Store core logic, backend architecture, error handling, capability invariants | Specs 001 (Store API), 003 (Backend ABC), 005 (error model), backend-specific specs |
| **Extension Expert** | `src/remote_store/ext/` — extension implementation, public API contract | Extension API design, Store contract usage, ADR-0008 pattern | Specs 024 (partition), 031 (dagster), 033 (streams), 034 (integrity); ADR-0008 (architecture), DESIGN.md |
| **Testing Expert** | `tests/` — test design, coverage targets, edge cases, conformance fixtures | Pytest patterns, spec traceability, coverage rigor | Specs (all via @pytest.mark.spec), DESIGN.md (conventions) |
| **Documentation Expert** | `docs-src/`, `guides/`, docstrings — user guides, API reference, navigation | Diátaxis structure, docstring format, mkdocs nav | DESIGN.md, DOCUMENTATION.md, example docstrings |

Not every task requires all 4 experts. The orchestrator decides which experts to spawn based on the task scope. A pure backend task may skip the Extension Expert; a docs-only task may only need the Documentation Expert.

### Implementation Approach: Claude Code Native (KISS)

Use Claude Code's built-in `Task` tool. Orchestrator (main Claude Code session) breaks down the task and delegates to subagents via the Task tool.

**Advantages:**
- Native to Claude Code — no custom Python needed (KISS principle)
- Automatic parallelism (independent experts work in parallel)
- Seamless integration with CLAUDE.md workflow
- Subagents inherit branch, git context automatically
- Simple to reason about and maintain

**Optional future:** Custom Python orchestrator (if parallelism needs become critical and cost optimization is required) — but not the initial approach.

### Worked Example: New Backend with Extension

**Trigger:** User asks to add a GCS backend with a `ext.gcs_datasets` extension.

**Orchestrator workflow:**

1. Pre-check: BACKLOG entry exists, spec drafted, ripple-check table consulted
2. Spawn experts in parallel (Task tool):
   - **Store & Backend Expert** → `src/remote_store/backends/_gcs.py` (ABC impl, error mapping, capabilities)
   - **Extension Expert** → `src/remote_store/ext/gcs_datasets.py` (extension impl, ADR-0008 pattern, public API contract)
   - **Testing Expert** → `tests/test_gcs_conformance.py` + `tests/ext/test_gcs_datasets.py` (conformance fixtures, extension tests, coverage)
   - **Documentation Expert** → `guides/backends/gcs.md` + `guides/extensions/gcs-datasets.md` (user guides, docstrings)
3. Experts execute in parallel, each reading their relevant specs first
4. Orchestrator collects results → runs ripple-checks:
   - README backends table, `pyproject.toml` extras, examples, auto-registration
   - CHANGELOG + BACKLOG updates
5. Compile PR, push, report

**Success criteria:**
- Experts work in parallel (no blocking)
- Code passes `hatch run all` (95% coverage)
- Ripple-checks 100% complete (no forgotten updates)
- PR ready to merge with no follow-ups

### Invariants

All experts and the orchestrator enforce these rules:

**Orchestrator (before delegating):**
1. Verify BACKLOG entry exists with correct ID and status
2. Read relevant specs — confirm they cover the task
3. Consult `CLAUDE-REFERENCE.md` ripple-check table — identify affected files
4. Scope each expert: no expert touches files outside their domain

**Orchestrator (after experts complete):**
1. Run ripple-check audit (verify cross-file consistency)
2. Update `CHANGELOG.md` and `BACKLOG.md`
3. Verify `hatch run all` passes

**All experts:**
- Read the spec first, before writing code/tests/docs. If spec contradicts code, spec is source of truth. Flag contradictions immediately.
- Follow DESIGN.md conventions for their domain
- Do not invent behavior — all design traces to a spec

## Alternatives Considered

1. **No orchestration** — Continue single-agent workflow
   - **Rejected:** Scales poorly as backlog grows; ID-013 and BK-123 are already context-constrained

2. **Seven specialist experts** (Spec Reviewer, Backend, Extension, Testing, Doc, Ripple Auditor, Async/Perf)
   - **Rejected:** Over-engineered; ripple-checks and audits are orchestrator tasks, not separate experts

3. **Custom Python orchestrator (ThreadPoolExecutor + Anthropic SDK)**
   - **Considered:** Needed if cost optimization or fine-grained model selection becomes critical
   - **Deferred:** Start with Claude Code native (KISS), optional future upgrade

4. **Per-concern specialized sessions** (separate Claude Code session per role)
   - **Rejected:** No coordination; duplicate work; complex state management

## Impact

- **Public API:** No change
- **Backwards compatibility:** Non-breaking (internal orchestration only)
- **Performance:** Faster task completion (parallelism) for complex features
- **Testing:** No automated tests — validation is manual via trial runs on a real backlog item
- **Docs:** New guide in DEVELOPMENT_STORY.md or sdd/000-process.md on using orchestrator

## Open Questions

1. **First test case:** Which task to validate orchestration on?
   - New backend (e.g., GCS) — isolated, fast feedback
   - Existing backlog item (ID-013, BK-123) — real-world complexity
2. **Skill or ad-hoc?** Should orchestrator be a dedicated skill (e.g., `/orchestrate`), or ad-hoc prompt in main session?
   - Recommendation: Start ad-hoc, formalize as skill if it becomes routine
3. **Model selection:** Which model for expert subagents (Haiku vs Sonnet)?
4. **Expert prompt templates:** Detailed prompt templates for each expert role belong in the implementation (skill definition or CLAUDE.md section), not in this RFC. To be designed during implementation.

## References

- **SDD workflow:** `sdd/000-process.md`
- **Ripple-check table:** `sdd/CLAUDE-REFERENCE.md` (§ "If you changed…") — orchestrator must verify post-implementation
- **Code conventions:** `sdd/DESIGN.md` (experts follow domain-specific conventions)
- **Documentation standards:** `sdd/DOCUMENTATION.md`, `CONTRIBUTING.md` (authoritative document format)
- **Expert domain specs:**
  - **Store & Backend:** `sdd/specs/001-store-api.md`, `sdd/specs/003-backend-adapter-contract.md`, `sdd/specs/005-error-model.md`, backend-specific specs
  - **Extension:** `sdd/specs/024-ext-partition.md`, `031-ext-dagster.md`, `033-ext-streams.md`, `034-ext-integrity.md`; `sdd/adrs/0008-extension-architecture.md`
  - **Testing:** `sdd/DESIGN.md` (test conventions), `@pytest.mark.spec("ID")` traceability
  - **Documentation:** `sdd/DOCUMENTATION.md` (Diátaxis structure), docstring examples in codebase
- **In-progress work:** `sdd/BACKLOG.md` (ID-013 async, ID-018 conda-forge, BK-123 memory audit)
- **Claude Code instructions:** `CLAUDE.md` (ripple-checks, spec discipline, branch workflow)
