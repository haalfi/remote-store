# Multi-Agent Orchestration Plan for remote-store

**Date:** 2026-03-29
**Status:** Draft — awaiting user feedback on strategy choice
**Scope:** Introducing subject matter experts to handle complex, multi-concern tasks while preserving SDD discipline.

---

## Executive Summary

remote-store has grown to ~2MB across 41 source files, 55 test files, and 72 doc files. The codebase spans multiple non-trivial concerns: backend implementations, testing, documentation (Diátaxis structure), SDD materials (specs, RFCs, ADRs), and process (BACKLOG, CHANGELOG, ripple-checks).

**Problem:** A single agent (Claude Code session) must juggle all concerns simultaneously. Complex tasks like implementing a new backend or major feature (ID-013 async API, ID-018 conda-forge publishing) require switching context between:
- Code implementation (backend logic, error handling)
- Test design (coverage, edge cases, conformance)
- Spec verification (matching design intent, cross-file consistency)
- Documentation (guides, docstrings, navigation updates)
- Process (CHANGELOG, BACKLOG movement, ripple-checks)

Risk: Incomplete work (gaps in tests, missing doc updates, incomplete ripple-checks) and hallucination (agents inventing solutions instead of reading specs).

**Solution:** Multi-agent orchestration with specialized experts, coordinated by an orchestrator, while preserving SDD discipline and preventing duplicate work.

---

## Specialist Roles (Proposed)

| Role | Scope | Key Inputs | Risk/Mitigation |
|------|-------|-----------|-----------------|
| **Orchestrator** | Break down task, delegate, synthesize results, verify SDD discipline | Task description, CLAUDE.md, BACKLOG | Prevents duplicate work; enforces ripple-checks |
| **Spec Reviewer** | Validate proposals against SDD, check spec completeness, identify dependencies | RFCs, specs, ADRs, DESIGN.md | Mitigates: accepting incomplete specs; missing ID-XNN links |
| **Backend Impl Expert** | Backend ABC implementation, error mapping, capabilities contract | spec, CLAUDE-REFERENCE.md (backends row) | Mitigates: incomplete error handling; missed capability invariants |
| **Testing Expert** | Test design, coverage, edge cases, conformance fixtures | spec, code, examples | Mitigates: low coverage; untested error paths; missing backends in conformance suite |
| **Doc Specialist** | User guides, docstrings, API docs, navigation (mkdocs.yml, _nav.yml) | spec, code, guides/, docs-src/ | Mitigates: stale docs; missing navigation; incomplete docstring examples |
| **Ripple-Check Auditor** | Cross-file dependency verification (CLAUDE-REFERENCE.md table) | changed files, ripple-check table, related files | Mitigates: **critical** — prevents forgotten README updates, missing extras in pyproject.toml, unregistered backends |
| **Async/Perf Specialist** | For ID-013 (async API) and ID-123 (memory findings) — deep research & implementation | research/, specs/029, ID-123 findings, benchmarks | Mitigates: incomplete async surface; missed optimization opportunities |

---

## Implementation Strategy: Two Approaches

### Approach A: Claude Code Native (Easiest, Recommended for Initial MVP)

**How it works:**
- Orchestrator prompt spawns subagents via the `Task` tool (Claude Code built-in).
- Each subagent receives a scoped system prompt + focused task + access to relevant files only.
- Orchestrator compiles results into a final delivery (PR, commit message, updated docs).

**Advantages:**
- Native to Claude Code — no custom Python needed.
- Automatic parallelism (independent tasks run in parallel).
- Simpler integration with existing CLAUDE.md workflow.
- Subagents inherit branch context, git state automatically.

**Disadvantages:**
- Less fine-grained model selection (all subagents use same model unless explicitly overridden).
- Context per subagent is limited (2000-line read default).
- Harder to enforce "read spec first" discipline (agents may hallucinate instead).

**When to use:** MVP phase, simpler tasks (single backend addition, small feature).

---

### Approach B: Custom Python Orchestrator (Full Control, Future Scaling)

**How it works:**
```python
# Pseudocode (simplified)
from concurrent.futures import ThreadPoolExecutor
from anthropic import Anthropic

EXPERTS = {
    "spec_reviewer": "Read RFC/spec, validate completeness, list dependencies",
    "backend_impl": "Implement Backend ABC, error mapping, capabilities",
    "test_designer": "Write pytest suite, coverage targets, conformance",
    "doc_writer": "Guides, docstrings, mkdocs nav updates",
    "ripple_auditor": "Cross-file checks against CLAUDE-REFERENCE table",
}

def orchestrate(task: str, files_to_read: list[str]) -> str:
    # 1. Dispatch experts in parallel (independent tasks)
    with ThreadPoolExecutor() as pool:
        results = {
            role: pool.submit(call_expert, role, EXPERTS[role], task, files_to_read)
            for role in EXPERTS
        }

    # 2. Orchestrator compiles & verifies
    outputs = {role: f.result() for role, f in results.items()}

    # 3. Synthesize: verify consistency, generate PR, check ripple-checks
    final = synthesize(task, outputs)
    return final
```

**Advantages:**
- Cheaper models for narrow tasks (Haiku for test design, Sonnet for spec review).
- Strict control: "read file X first" → enforced in system prompt.
- Easy to enforce SDD discipline (each expert has a checklist in their prompt).
- Can run as a background service (scheduled, triggered on PR, etc.).
- Scales to very large teams / complex workflows.

**Disadvantages:**
- Requires custom Python code (outside Claude Code's built-in tools).
- More setup, more to maintain.
- Subagents don't inherit branch/git context — must handle manually.

**When to use:** Production phase (recurring backlog work, complex features like ID-013).

---

## Critical Design Decisions

### 1. **SDD Discipline is Non-Negotiable**

Every orchestrator (native or custom) MUST enforce:

- ✅ Spec exists (or is drafted) before code begins.
- ✅ Ripple-check auditor ALWAYS runs before commit.
- ✅ BACKLOG entry exists before implementation (bug-fix protocol).
- ✅ CHANGELOG updated in same commit.
- ✅ No agent invents behavior — all design must trace to a spec.

**Mechanism:** Orchestrator prompt includes a pre-execution checklist:

```
BEFORE DELEGATING TO EXPERTS:
1. Read BACKLOG.md — is this item already logged? What's its ID and status?
2. Read relevant specs (sdd/specs/) — do they cover this task?
3. Check CLAUDE-REFERENCE.md ripple-check table — which files will be affected?
4. Scope subagents: no expert touches a file unless it's in the ripple-check list.
```

---

### 2. **Hallucination Mitigation**

Agents writing code must read specs first. System prompt template:

```
You are a [ROLE] expert. Your task:
{task}

CRITICAL: Before writing code/docs, you MUST read these files:
- {spec_file}
- {related_backend_file}
- {existing_test_file}

Only code/doc that matches the spec is acceptable. If spec contradicts code,
spec is source of truth. Flag any contradictions immediately.

Output format:
[READ SUMMARY]: What you learned from reading the files
[FINDINGS]: Any gaps, contradictions, or missing pieces
[IMPLEMENTATION]: Your contribution (code, tests, docs, or spec edits)
```

---

### 3. **Orchestrator Never Skips Ripple-Checks**

The **Ripple-Check Auditor** expert must run on EVERY change:

```
If you changed {files}, also verify:
- sdd/CLAUDE-REFERENCE.md ripple-check table
- README.md (if backend, capabilities, version)
- pyproject.toml (if new extra, dependency, version)
- docs-src/_nav.yml (if new guide, extension, API page)
- guides/backends/index.md (if backend added/modified)
- src/remote_store/__init__.py __all__ exports
- examples/ (if new feature, backend example needed?)
```

This expert produces a checklist. Orchestrator halts commit if any items are unchecked.

---

### 4. **Prevent Duplicate Work: Clear Scope Boundaries**

Each expert gets a precise scope. Template:

```
TASK: Implement ID-013 async Store (Phase 1)

ORCHESTRATOR → SPEC_REVIEWER:
  - Read: sdd/specs/029-async-store-backend-api.md (draft)
  - Validate: is spec complete for Phase 1? List gaps.
  - Output: amended spec section + list of dependencies (IDs)

ORCHESTRATOR → BACKEND_IMPL:
  - Read: spec section from spec_reviewer output
  - Scope: AsyncStore + AsyncBackend ABC only (NOT native backends yet)
  - Output: src/remote_store/async_/store.py + backends.py

ORCHESTRATOR → TEST_DESIGNER:
  - Read: backend_impl output + spec
  - Scope: conformance tests for AsyncStore + AsyncBackend (NOT native backends)
  - Output: tests/test_async_store.py + tests/async_/conftest.py

ORCHESTRATOR → DOC_SPECIALIST:
  - Read: spec + code outputs
  - Scope: user guide (guides/async-guide.md) + docstrings + mkdocs nav
  - Output: updated docs-src/, guides/, docstrings (via code edits)

ORCHESTRATOR → RIPPLE_AUDITOR:
  - Read: all outputs + CLAUDE-REFERENCE.md
  - Scope: verify nothing was missed (e.g., __all__ exports, README async examples)
  - Output: final checklist + PR description
```

---

## Phased Rollout

### Phase 1: Spec Review & Validation (Immediate, Low Risk)

**Trigger:** When a new RFC or spec amendment is proposed.
**Experts:** Spec Reviewer only.
**Scope:** Read RFC, validate against SDD, list gaps and dependencies. No code changes.

**Example:**
- User proposes RFC-0009 (new feature).
- Spec Reviewer reads RFC, checks: completeness, ID links, examples, error cases, test structure.
- Output: annotated RFC + gap list → user decides whether to amend before moving to Backlog.

**Risk:** Low (read-only, no commits).

---

### Phase 2: Single Backend Implementation (Initial MVP)

**Trigger:** User asks to implement a new backend (e.g., "add GCS backend").
**Experts:** Backend Impl, Testing, Doc Specialist, Ripple-Check Auditor.
**Orchestration:** Claude Code native (Task tool).

**Workflow:**
1. Orchestrator reads spec (GCS backend spec).
2. Dispatches:
   - Backend Impl → write `src/remote_store/backends/_gcs.py`
   - Testing → write `tests/backends/test_gcs_conformance.py`
   - Doc Specialist → write `guides/backends/gcs.md` + update mkdocs nav
3. Ripple Auditor → verify README backends table, pyproject.toml extras, examples.
4. Compile into PR, commit message, CHANGELOG entry.

**Risk:** Medium (code changes, but scoped to single backend).

---

### Phase 3: Major Feature (Complex Multi-Phase)

**Trigger:** User works on ID-013 (async API) or similar complex feature.
**Experts:** All roles (custom Python orchestrator recommended).
**Orchestration:** Custom Python orchestrator (async-capable).

**Workflow:**
1. Orchestrator reads ID-013 BACKLOG entry + spec.
2. Cascades:
   - Spec Reviewer → validate spec 029, list Phase 1 vs Phase 2/3 boundaries.
   - Backend Impl → core AsyncStore + AsyncBackend ABC.
   - Testing → conformance tests for async surface.
   - Doc Specialist → async user guide, docstrings.
   - Ripple Auditor → cross-check exports, deps, navigation.
3. Orchestrator compiles results, asks user for feedback on Phase 2 (native backends).
4. Generate PR, update BACKLOG (move Phase 1 to BACKLOG-DONE, create Phase 2 item).

**Risk:** High (large scope, multiple phases, new async surface). Mitigated by: spec-first, ripple-checks, phase gates.

---

## Integration with Existing Workflow (CLAUDE.md)

### No Changes to Core SDD Discipline

The orchestrator enhances, not replaces:
- ✅ Specs remain source of truth.
- ✅ Ripple-checks still apply (now verified by auditor expert).
- ✅ BACKLOG still drives all work.
- ✅ Commit protocol (bug-fix protocol, ID-XXX prefixes) unchanged.

### Orchestrator as "Intelligent Coordinator"

```
Current workflow (single agent):
  User request → Claude reads files → writes code → commits → pushes

New workflow (orchestrated):
  User request → Orchestrator reads BACKLOG + specs
             ↓ (dispatch subagents in parallel)
      Backend Impl ─┬─ writes code
      Testing ──────┼─ writes tests
      Doc ──────────┼─ writes docs
      Ripple Audit ─┴─ verifies completeness
             ↓ (collect results)
      Orchestrator synthesizes → commits + pushes
```

### System Prompt Template (Orchestrator)

```
You are an orchestrator for the remote-store project.

CONTEXT:
- Repository: Python library for unified file storage (SDD-driven)
- CLAUDE.md governs your work (read it first)
- CLAUDE-REFERENCE.md contains ripple-check table (MUST verify before commit)
- BACKLOG.md drives all work (create entries, move to BACKLOG-DONE)

TASK: {user_request}

YOUR JOB:
1. Read BACKLOG.md — find the item ID and status.
2. Read relevant specs (sdd/specs/) — understand design.
3. Consult CLAUDE-REFERENCE.md ripple-check table — list affected files.
4. Dispatch subagents (if needed):
   - If RFC/spec draft only: Spec Reviewer
   - If single backend: Backend Impl + Testing + Doc + Ripple Auditor
   - If complex feature: All roles (custom Python needed)
5. Collect results, verify consistency.
6. Generate final deliverable: code, tests, docs, commit message, CHANGELOG.

CRITICAL RULES:
- Specs are source of truth (code vs spec conflict = code is wrong)
- No agent writes code without reading the spec first
- Ripple-Check Auditor ALWAYS runs (prevents forgotten updates)
- BACKLOG entry + CHANGELOG + tests + code = shipped together (or mark [~])
- Commit message starts with ID (e.g., "ID-123: Add feature")
```

---

## Risks & Mitigations

| Risk | Cause | Mitigation |
|------|-------|-----------|
| **Hallucination** | Agents invent design instead of reading specs | System prompt: "Read spec first, flag contradictions" + Spec Reviewer validates |
| **Incomplete ripple-checks** | Auditor misses a file/update | Orchestrator enforces: no commit until checklist is 100% signed off |
| **Stale specs** | Code diverges from spec (code is wrong) | Spec Reviewer runs on every major change; CLAUDE.md rule: specs are source of truth |
| **Duplicate work** | Multiple agents write same code | Clear scope boundaries + orchestrator dispatch (each expert owns 1 concern) |
| **Lack of context** | Subagents don't understand domain | System prompt includes: "You are an expert in [role]. Read these files first." |
| **Context window limits** | Subagent reads hit 2000-line default limit | Orchestrator pre-selects relevant files to read (ripple-check table) |
| **Integration bugs** | Tests pass but feature broken in real use | "Run it, don't just type-check it" rule: examples, manual testing before commit |

---

## Decision Tree: Which Approach?

```
START: User requests a task

Is it spec/RFC review only?
  → YES: Use Spec Reviewer expert (Phase 1)
  → NO: continue

Is it a single, isolated concern (e.g., add GCS backend)?
  → YES: Use Claude Code native (Task tool) with 4 experts (Phase 2)
  → NO: continue

Is it a complex, multi-phase feature (e.g., ID-013, ID-123)?
  → YES: Use custom Python orchestrator with all experts (Phase 3)
  → NO: unclear — ask user
```

---

## Success Criteria (MVP)

For Phase 1 (Spec Review) to be successful:

- [ ] Spec Reviewer expert reads RFC, validates completeness, lists gaps
- [ ] Output: annotated RFC + checklist (no false positives)
- [ ] User confirms gaps are accurate and actionable
- [ ] Zero hallucinated feedback (everything traces to SDD rules)

For Phase 2 (Single Backend) to be successful:

- [ ] Orchestrator dispatches 4 experts in parallel (Task tool)
- [ ] All ripple-checks from CLAUDE-REFERENCE.md are verified
- [ ] Code passes `hatch run all` (lint + test + coverage)
- [ ] PR is ready to merge with no follow-up edits needed
- [ ] CHANGELOG + BACKLOG updated in same commit

---

## Next Steps (User Decision Required)

### Option A: Start with Phase 1 (Spec Review)
- Low risk, read-only.
- Validate approach on an RFC or spec amendment.
- **Timeline:** ~1–2 hours implementation, immediate feedback.

### Option B: Start with Phase 2 MVP (Single Backend)
- Medium risk, full CI/CD pipeline (code → tests → docs).
- Pick a simple backend (e.g., GCS, SFTP) as test case.
- **Timeline:** ~3–4 hours to build, 1–2 hours to verify.

### Option C: Start with Full Custom Python Orchestrator
- Highest risk, most powerful.
- Suitable for immediate use on ID-013 (async API, currently blocked).
- **Timeline:** ~6–8 hours to build, requires testing.

### Option D: Skip for Now
- Continue single-agent workflow (current approach).
- Revisit after ID-013 and ID-018 are shipped.
- **Rationale:** Phase 1–2 are low priority; Phase 3 (custom) is overkill until more backlog accumulates.

---

## Appendix: File Layout (If Custom Python Orchestrator Chosen)

```
remote-store/
├── sdd/
│   └── agents/                      # NEW: orchestrator & expert configs
│       ├── orchestrator.py          # Main coordinator
│       ├── experts/
│       │   ├── spec_reviewer.py
│       │   ├── backend_impl.py
│       │   ├── test_designer.py
│       │   ├── doc_writer.py
│       │   └── ripple_auditor.py
│       ├── prompts/                 # System prompt templates
│       │   ├── orchestrator.md
│       │   └── expert_*.md
│       └── tests/
│           └── test_orchestrator.py
├── pyproject.toml                   # add: orchestrator optional deps
└── CLAUDE.md                        # update: reference orchestrator
```

---

## Questions for User

1. **Which phase appeals most?** (1=spec review, 2=single backend, 3=complex feature)
2. **Is there an RFC or spec amendment you'd like to test the Spec Reviewer on?**
3. **Which current backlog item would be a good test case for the full orchestrator?** (ID-013, ID-018, or other?)
4. **Should orchestrator run automatically (on every task) or on-demand?** (hook vs explicit request)
5. **Model preferences:** Should cheaper Haiku models be used for narrow expert tasks, or stick with a single model?

