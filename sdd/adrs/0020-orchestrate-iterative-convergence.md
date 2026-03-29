# ADR-0020: Orchestrate Iterative Convergence Model

## Status

Accepted — supersedes [ADR-0019](0019-multi-agent-orchestration.md)

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

Replace the single-pass model with an **iterative convergence model** that
adds plan refinement, consolidation, and review loops — with complexity-based
mode selection to avoid unnecessary overhead.

### Three modes

| Mode | When | Flow |
|------|------|------|
| **Simple** | Trivial plan, clear scope | Plan → Execute → Review (1×) → Finish |
| **Standard** | Multi-domain, clear requirements | Plan → Refine (1×) → Execute → Consolidate → Review (1–2×) → Finish |
| **Complex** | Ambiguity, tight coupling, unknowns | Full flow, user breaks ties at any gate |

The orchestrator selects the mode during planning. The user can override.

### Flow

```
1. PLAN         — orchestrator drafts architecture plan
2. REFINE       — experts review plan (1 round, parallel)
                  → orchestrator integrates feedback
                  → unresolved points → user decides
3. EXECUTE      — experts implement (parallel or sequential per plan)
4. CONSOLIDATE  — orchestrator collects results:
                  ✓ done  |  ✗ blocked (with reason)  |  ⚠ needs input
                  → blocked: clarify with expert, re-execute
                  → needs input: escalate to user
5. REVIEW       — all experts review all output (parallel)
                  → clean: proceed to finish
                  → issues: experts fix → re-review (max 2 rounds total)
                  → still open after 2: user decides
6. FINISH       — CHANGELOG, BACKLOG, validate, commit, summary
```

**Simple mode** skips steps 2 (Refine) and 4 (Consolidate); review is
single-pass with no loop.

### Expert responses

Structured when reporting issues (status + blockers + artifacts).
Free-form when clean ("done, no issues"). No over-engineered format.

### Tie-breaking

The user breaks all ties. The orchestrator never overrides expert
disagreements autonomously — it presents the conflict and asks.

### What stays from ADR-0019

- 4 domain experts (Store & Backend, Extension, Testing, Documentation)
- Domain boundaries and foundation docs
- Cross-domain files owned by orchestrator (CHANGELOG, BACKLOG, README)
- Bug-fix TDD mode (Testing Expert goes first)
- Ripple-check audit in finalization

## Consequences

- Complex tasks get feedback loops that catch cross-domain mismatches early.
- Simple tasks stay fast — no unnecessary refinement or consolidation.
- User is always the final authority on unresolved disagreements.
- Max 2 review rounds prevents infinite convergence loops.
- Plan refinement catches expert-identified gaps before any code is written.
- More orchestrator complexity — the skill is longer and has branching logic.
