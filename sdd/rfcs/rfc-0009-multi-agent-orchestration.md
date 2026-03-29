# RFC-0009: Multi-Agent Orchestration for Complex Tasks

## Status

Draft — awaiting community feedback

## Summary

Introduce a multi-agent orchestration pattern to handle complex, multi-concern tasks (backend implementation, testing, documentation, spec review, ripple-checks) in parallel. A coordinator agent spawns specialized experts (Spec Reviewer, Backend Impl, Testing, Documentation, Ripple-Check Auditor) to decompose work while preserving SDD discipline and preventing hallucination.

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

**Motivation:** Parallelize independent concerns via specialized agents, each with a narrow scope and clear system prompt, while an orchestrator enforces SDD discipline.

## Proposal

### Seven Specialist Roles

| Role | Scope | Key Inputs | Risk Mitigation |
|------|-------|-----------|-----------------|
| **Orchestrator** | Break down task, delegate, synthesize, verify SDD | Task, CLAUDE.md, BACKLOG | Prevents duplicate work; enforces ripple-checks |
| **Spec Reviewer** | Validate proposals, check completeness, find gaps | RFC, specs, DESIGN.md | Incomplete specs; missing spec-code traceability |
| **Backend Impl Expert** | Backend ABC impl, error mapping, capabilities contract | Spec, CLAUDE-REFERENCE.md | Incomplete error handling; missed capability invariants |
| **Testing Expert** | Test design, coverage targets, edge cases, conformance | Spec, code, examples | Low coverage; untested error paths |
| **Doc Specialist** | User guides, docstrings, API docs, navigation | Spec, code, guides/, docs-src/ | Stale docs; missing navigation |
| **Ripple-Check Auditor** | Cross-file dependency verification (CLAUDE-REFERENCE.md) | Changed files, ripple-check table | **Critical:** forgotten README, pyproject.toml, exports |
| **Async/Perf Specialist** | ID-013 async API, ID-123 memory/perf findings | Research docs, specs, benchmarks | Incomplete async surface; missed optimizations |

### Two Implementation Approaches

#### Approach A: Claude Code Native (Recommended MVP)

Use Claude Code's built-in `Task` tool. Orchestrator prompt spawns subagents automatically.

**Advantages:**
- Native to Claude Code — no custom Python needed
- Automatic parallelism (independent tasks run in parallel)
- Simple integration with CLAUDE.md workflow
- Subagents inherit branch context automatically

**Disadvantages:**
- Less fine-grained model selection
- Context per subagent limited (2000-line read default)
- Harder to enforce "read spec first" discipline

**Best for:** MVP phase, simpler tasks (single backend, small feature)

#### Approach B: Custom Python Orchestrator (Future Scaling)

Custom orchestration script using `anthropic` SDK + `ThreadPoolExecutor`.

```python
from concurrent.futures import ThreadPoolExecutor
from anthropic import Anthropic

EXPERTS = {
    "spec_reviewer": "Validate RFC/spec, check completeness",
    "backend_impl": "Implement Backend ABC, error mapping",
    "test_designer": "Write pytest suite, coverage targets",
    "doc_writer": "Guides, docstrings, mkdocs nav",
    "ripple_auditor": "Cross-file checks",
}

def orchestrate(task: str, files_to_read: list[str]) -> str:
    # Dispatch experts in parallel
    with ThreadPoolExecutor() as pool:
        results = {
            role: pool.submit(call_expert, role, EXPERTS[role], task, files_to_read)
            for role in EXPERTS
        }

    # Compile & verify consistency
    outputs = {role: f.result() for role, f in results.items()}
    final = synthesize(task, outputs)
    return final
```

**Advantages:**
- Cheaper models per task (Haiku for narrow tasks, Sonnet for orchestration)
- Strict control: "read file X first" enforced in system prompt
- Easy SDD checklist enforcement per expert
- Scales to large teams / complex workflows

**Disadvantages:**
- Requires custom Python code
- More setup and maintenance
- Subagents don't inherit branch context (manual handling)

**Best for:** Production phase, recurring backlog work (ID-013, ID-123)

### SDD Discipline: Non-Negotiable Invariants

Every orchestrator MUST enforce:

1. ✅ **Spec-first:** Spec exists (or is drafted) before code begins
2. ✅ **Ripple-check auditor always runs** before commit (prevents forgotten README, exports, deps)
3. ✅ **BACKLOG entry exists** before implementation (bug-fix protocol)
4. ✅ **CHANGELOG updated** in same commit as code
5. ✅ **No hallucination:** All design traces to a spec; agents flag contradictions

**Orchestrator pre-execution checklist:**

```
BEFORE DELEGATING:
1. Read BACKLOG.md — is this item logged? ID and status?
2. Read relevant specs (sdd/specs/) — do they cover this task?
3. Consult CLAUDE-REFERENCE.md ripple-check table — which files affected?
4. Scope subagents — no expert touches a file outside ripple-check list
```

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

### Phased Rollout

#### Phase 1: Spec Review (Immediate, Low Risk)

**Trigger:** RFC or spec amendment proposed
**Experts:** Spec Reviewer only
**Scope:** Read RFC, validate against SDD, list gaps
**Output:** Annotated RFC + gap list (no code changes)

#### Phase 2: Single Backend Implementation (MVP)

**Trigger:** User asks to implement a new backend
**Experts:** Backend Impl, Testing, Doc Specialist, Ripple-Check Auditor
**Orchestration:** Claude Code native (Task tool)
**Scope:** New backend only (e.g., add GCS backend)

#### Phase 3: Major Feature (Complex Multi-Phase)

**Trigger:** Complex feature (ID-013 async API, ID-123 memory findings)
**Experts:** All roles
**Orchestration:** Custom Python orchestrator
**Scope:** Multi-phase, large ripple (touches Store, Backend ABC, extensions)

## Alternatives Considered

1. **No orchestration** — Continue single-agent workflow
   - **Rejected:** Scales poorly as backlog grows; ID-013 and ID-123 are already blocked by context overhead

2. **Orchestrator without strict SDD enforcement**
   - **Rejected:** Risk of hallucinated specs, incomplete ripple-checks; violates CLAUDE.md principle "specs are source of truth"

3. **Per-concern specialized sessions** (e.g., separate Claude Code session per role)
   - **Rejected:** No coordination; duplicate work; complex state management

## Impact

- **Public API:** No change
- **Backwards compatibility:** Non-breaking (internal orchestration only)
- **Performance:** Faster task completion (parallelism) for complex features
- **Testing:** New tests for orchestrator (e.g., ripple-check verification, spec compliance)
- **Docs:** New guide in DEVELOPMENT_STORY.md or sdd/000-process.md on using orchestrator

## Open Questions

1. **Start with Approach A (Claude Code native) or Approach B (custom Python)?**
   - Recommendation: Approach A for MVP (Phase 1–2), migrate to Approach B if backlog scales

2. **Which current backlog item is a good test case?**
   - Candidates: ID-013 (async API, currently blocked), ID-018 (conda-forge, nearly done), or simpler backend addition

3. **Should orchestrator run automatically or on-demand?**
   - On-demand (explicit `/orchestrate` command or user request) preferred initially
   - Could add hook-based auto-triggering later

4. **Model selection:** Use cheaper Haiku for narrow expert tasks?
   - Yes: reduces cost for routine work (e.g., conformance test generation)
   - Orchestrator itself should use Sonnet/Opus (complex synthesis)

## References

- **SDD workflow:** `sdd/000-process.md`
- **Ripple-check table:** `sdd/CLAUDE-REFERENCE.md` (§ "If you changed…")
- **Code conventions:** `sdd/DESIGN.md`
- **In-progress work:** `sdd/BACKLOG.md` (ID-013, ID-018, ID-123)
- **Claude Code instructions:** `CLAUDE.md`
- **Contributing:** `CONTRIBUTING.md` (spec-first workflow, release checklist)
