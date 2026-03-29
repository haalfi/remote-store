# RFC-0009: Multi-Agent Orchestration for Complex Tasks

## Status

Draft — awaiting community feedback

## Summary

Introduce a multi-agent orchestration pattern to handle complex, multi-concern tasks (backend implementation, testing, documentation) in parallel. An orchestrator breaks down the task and delegates to 4 subject matter experts (Backend, Extension, Testing, Documentation), each with mandatory SDD foundation but focused on their domain. Post-implementation ripple-checks and CHANGELOG updates are orchestrator tasks, not separate experts.

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

**Motivation:** Parallelize independent concerns via subject matter experts (backend implementation, testing, documentation), each with mandatory SDD foundation but focused on their domain. An orchestrator breaks down the task, delegates to experts, and handles post-implementation tasks (ripple-checks, CHANGELOG, BACKLOG movement).

## Proposal

### Four Subject Matter Experts + Orchestrator Role

| Role | Scope | Domain Focus | SDD Foundation |
|------|-------|--------------|-----------------|
| **Orchestrator** (meta-role) | Break down task, delegate, post-implementation ripple-checks & CHANGELOG, compile results | Task decomposition, SDD enforcement, cross-file consistency | Mandatory: CLAUDE.md, BACKLOG, ripple-check table |
| **Store & Backend Expert** | `src/remote_store/` + `src/remote_store/backends/` — Store API, Backend ABC, error mapping, capabilities | Store core logic, backend architecture, error handling, capability invariants | Specs 001 (Store API), 003 (Backend ABC), 005 (error model), backends specs |
| **Extension Expert** | `src/remote_store/ext/` — extension implementation, public API contract | Extension API design, Store contract usage, ADR-0008 pattern | Specs 024-043 (extensions), ADR-0008 (architecture), DESIGN.md |
| **Testing Expert** | `tests/` — test design, coverage targets, edge cases, conformance fixtures | Pytest patterns, spec traceability, coverage rigor | Specs (all via @pytest.mark.spec), DESIGN.md (conventions) |
| **Documentation Expert** | `docs-src/`, `guides/`, docstrings — user guides, API reference, navigation | Diátaxis structure, docstring format, mkdocs nav | DESIGN.md, DOCUMENTATION.md, example docstrings |

### Implementation Approach: Claude Code Native (KISS)

#### Primary: Approach A — Claude Code Native

Use Claude Code's built-in `Task` tool. Orchestrator (main Claude Code session) breaks down the task and delegates to subagents via the Task tool.

**Advantages:**
- ✅ Native to Claude Code — no custom Python needed (KISS principle)
- ✅ Automatic parallelism (independent experts work in parallel)
- ✅ Seamless integration with CLAUDE.md workflow
- ✅ Subagents inherit branch, git context automatically
- ✅ Simple to reason about and maintain

**How it works:**
1. Orchestrator reads BACKLOG + specs + ripple-check table
2. Spawns Task subagents:
   - Backend Expert → implement `src/remote_store/backends/_new_backend.py`
   - Testing Expert → write `tests/test_new_backend.py`
   - Documentation Expert → write `guides/new-backend.md` + docstrings
3. Experts execute in parallel
4. Orchestrator collects results → compiles PR + runs ripple-checks → commits + pushes

**Optional Future:** Custom Python orchestrator (if parallelism needs become critical and cost optimization is required) — but not the initial approach.

### SDD Discipline: Orchestrator Responsibilities

The orchestrator enforces these invariants before and after expert execution:

**Before delegating to experts:**
1. Read `BACKLOG.md` — is this item logged? ID and status?
2. Read relevant specs (`sdd/specs/`) — do they cover this task?
3. Consult `CLAUDE-REFERENCE.md` ripple-check table — which files will be affected?
4. Scope each expert: no expert touches a file outside their domain

**After experts complete:**
1. Compile all outputs (code, tests, docs)
2. Run ripple-check auditing (verify CLAUDE-REFERENCE.md table completeness)
3. Update `CHANGELOG.md` (`[Unreleased]` section)
4. Move `BACKLOG.md` item to `BACKLOG-DONE.md` or split if partially done
5. Verify all changes pass `hatch run all` (lint + typecheck + test + coverage)

**Experts (all domains) MUST:**
- Read the spec first, before writing code/tests/docs
- Flag any spec contradictions or gaps immediately
- Follow DESIGN.md conventions for their domain (code style, test markers, docstring format)
- Do not invent behavior — all design traces to a spec

### Hallucination Mitigation

**System prompt template for every expert:**

```
You are a {ROLE} expert. Task: {task}

CRITICAL: Before writing code/docs, READ these files:
- {spec_file}
- {related_backend_file}
- {existing_code_file}

Only design matching the spec is acceptable.
If spec contradicts code, spec is source of truth.
Flag all contradictions immediately.

Output format:
[READ SUMMARY]: What you learned
[FINDINGS]: Gaps, contradictions, missing pieces
[IMPLEMENTATION]: Your contribution
```

### First Test Case: New Backend Implementation

**Trigger:** User asks to implement a new backend (e.g., add GCS backend)

**Orchestrator workflow:**
1. Pre-check: BACKLOG entry exists, spec drafted
2. Spawn 4 experts in parallel (Task tool):
   - **Store & Backend Expert** → `src/remote_store/backends/_gcs.py` (ABC impl, error mapping, capabilities)
   - **Testing Expert** → `tests/test_gcs_conformance.py` (conformance fixtures, coverage)
   - **Documentation Expert** → `guides/backends/gcs.md` (user guide, docstrings)
3. Orchestrator post-processing:
   - Ripple-check: README backends table, `pyproject.toml` extras, examples, auto-registration
   - CHANGELOG + BACKLOG updates
4. Compile PR, push, report

**Success criteria:**
- All 4 experts work in parallel (no blocking)
- Code passes `hatch run all` (95% coverage)
- Ripple-checks 100% complete (no forgotten updates)
- PR ready to merge with no follow-ups

## Alternatives Considered

1. **No orchestration** — Continue single-agent workflow
   - **Rejected:** Scales poorly as backlog grows; ID-013 and ID-123 are already context-constrained

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
- **Testing:** New tests for orchestrator (e.g., ripple-check verification, spec compliance)
- **Docs:** New guide in DEVELOPMENT_STORY.md or sdd/000-process.md on using orchestrator

## Implementation Decision: What's Next?

Agreed approach: **Claude Code native (KISS), 4 subject matter experts, orchestrator as meta-role**.

**Ready to implement?**

1. **Immediate next step:** Test orchestration on a new backend addition (e.g., GCS backend)
   - Low risk (isolated change), fast feedback, validates workflow
   - Or: test on existing backlog item (ID-013, ID-123)?

2. **System prompt templates needed:**
   - Orchestrator prompt (pre-check, delegate, post-process)
   - Store & Backend Expert prompt (src/remote_store/ + backends/)
   - Extension Expert prompt (src/remote_store/ext/)
   - Testing Expert prompt (tests/)
   - Documentation Expert prompt (docs-src/, guides/)

3. **Open:** Should orchestrator be a dedicated skill (e.g., `/orchestrate`), or ad-hoc prompt in main session?
   - Recommendation: Start ad-hoc, formalize as skill if it becomes routine

## References

- **SDD workflow:** `sdd/000-process.md`
- **Ripple-check table:** `sdd/CLAUDE-REFERENCE.md` (§ "If you changed…") — orchestrator must verify post-implementation
- **Code conventions:** `sdd/DESIGN.md` (experts follow domain-specific conventions)
- **Documentation standards:** `sdd/DOCUMENTATION.md`, `CONTRIBUTING.md` (authoritative document format)
- **Expert domain specs:**
  - **Store & Backend:** `sdd/specs/001-store-api.md`, `sdd/specs/003-backend-adapter-contract.md`, `sdd/specs/005-error-model.md`, backend-specific specs
  - **Extension:** `sdd/specs/024-041.md` (extensions), `sdd/adrs/0008-extension-architecture.md`
  - **Testing:** `sdd/DESIGN.md` (test conventions), `@pytest.mark.spec("ID")` traceability
  - **Documentation:** `sdd/DOCUMENTATION.md` (Diátaxis structure), docstring examples in codebase
- **In-progress work:** `sdd/BACKLOG.md` (ID-013 async, ID-018 conda-forge, ID-123 memory audit)
- **Claude Code instructions:** `CLAUDE.md` (ripple-checks, spec discipline, branch workflow)
