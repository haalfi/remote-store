---
name: orchestrate
description: Multi-agent orchestration — delegates to domain experts for complex tasks
disable-model-invocation: true
argument-hint: "[BACKLOG-ID] [optional: task description]"
---

Orchestrate a complex task by delegating to 5 domain experts.
See ADR-0020 for architecture rationale.

Parse `$ARGUMENTS`: first token is the backlog ID (e.g., `BK-123`, `ID-120`),
remainder is optional task description. Ask if missing.

## Step 1: Pre-check

1. Read `sdd/BACKLOG.md` — confirm item exists, note description and dependencies
2. Read linked specs and RFCs from the backlog entry
3. Read [`sdd/CLAUDE-REFERENCE.md` § Ripple-check table > Pre-work index](../../../sdd/CLAUDE-REFERENCE.md#pre-work-index) — identify triggered rows
4. Create feature branch: `git checkout -b <id>-<short-name>`

## Step 2: Plan

Before spawning experts, decide and document:
- Class/function names, method signatures, file paths
- Spec IDs that each expert will implement or reference
- Which **mode** applies (see below)

### Mode selection

| Mode | When | Steps used |
|------|------|------------|
| **Simple** | Trivial plan, clear scope | Plan → Execute → Review (1×) → Finish |
| **Standard** | Multi-domain, clear requirements | Plan → Refine → Execute → Consolidate → Review (1–2×) → Finish |
| **Complex** | Ambiguity, tight coupling, unknowns | Same as Standard, but user confirms before Execute and before each Review round |

Select mode based on scope and coupling. User can override.

**Complex mode gates:** Before spawning experts in Step 4 (Execute) and
before each review round in Step 6, present the plan/findings to the user
and wait for confirmation. This prevents wasted expert cycles when the
direction is uncertain.

### Expert activation rules

**Code change (feature, refactor, bug fix):** All 5 experts activate.
Each evaluates from their domain — even if their files aren't directly touched.
For bug fixes scope is narrower, but every expert still evaluates.

**SDD-only change (spec/RFC/ADR/process):** The SDD Expert leads
implementation. The other 4 experts **review** (not implement) from their
domain perspective.

## Step 3: Refine (Standard and Complex only)

Spawn all 5 experts in **review mode** with the plan from Step 2. Each expert
reviews the plan from their domain perspective and returns:
- Gaps, risks, or contradictions they see
- Suggestions for their domain scope
- "No concerns" if the plan is sound for their domain

**One round only.** The orchestrator integrates feedback and adjusts the plan.
Any unresolved disagreements or open questions → escalate to user. Do not
loop — if the user needs to decide, present the options and wait.

**Simple mode:** Skip this step entirely.

## Step 4: Execute

Each expert is spawned via its `subagent_type` (referenced below), with the
(refined) plan and per-call task passed in the invocation prompt.

**Feature/refactor:** Spawn all experts using multiple Agent tool calls.

**Bug fix (TDD):** Sequential — Testing Expert goes first. This follows the
bug-fix protocol in CLAUDE.md (backlog → changelog → failing test → fix):
1. Spawn **Testing Expert only** — write a failing test that clearly reproduces
   the bug, conforming to the full testing guide (`sdd/TESTING.md`).
2. Verify the test fails for the right reason.
3. Then spawn remaining experts (Store & Backend, Extension, Documentation)
   to fix the bug, plus the **SDD Expert** to assess spec/ADR impact.

### Store & Backend Expert

Spawn via the Agent tool with `subagent_type: store-backend-expert` — the
persona lives in [`.claude/agents/store-backend-expert.md`](../../agents/store-backend-expert.md),
the single source of truth. The invocation prompt carries the per-call context
from the plan.

### Extension Expert

Spawn via the Agent tool with `subagent_type: extension-expert` — the persona
lives in [`.claude/agents/extension-expert.md`](../../agents/extension-expert.md),
the single source of truth. The invocation prompt carries the per-call context
from the plan.

### Testing Expert

Spawn via the Agent tool with `subagent_type: testing-expert` — the persona
lives in [`.claude/agents/testing-expert.md`](../../agents/testing-expert.md),
the single source of truth. The invocation prompt carries the per-call context
from the plan.

### Documentation Expert

Spawn via the Agent tool with `subagent_type: documentation-expert` — the
persona lives in [`.claude/agents/documentation-expert.md`](../../agents/documentation-expert.md),
the single source of truth. The invocation prompt carries the per-call context
from the plan. The orchestrator owns README.md and CHANGELOG.md; the expert
only assesses their impact (see Rules).

### SDD Expert

Spawn via the Agent tool with `subagent_type: sdd-expert` — the persona lives
in [`.claude/agents/sdd-expert.md`](../../agents/sdd-expert.md), the single
source of truth. The invocation prompt carries the per-call context from the
plan.

## Step 5: Consolidate (Standard and Complex only)

After all experts complete, collect and categorize results:

| Status | Meaning | Action |
|--------|---------|--------|
| ✓ done | Expert completed all assigned work | No action needed |
| ✗ blocked | Expert could not complete (dependency, conflict, ambiguity) | Clarify with that expert, re-execute their task |
| ⚠ needs input | Expert needs a decision outside their domain | Escalate to user |

For blocked experts: understand the blocker, provide the missing context,
re-spawn that expert only. For needs-input: present the question to the user
and wait.

**Simple mode:** Skip this step — proceed directly to Review.

## Step 6: Review

Spawn all 5 experts in **review mode** — each reviews *all output from all
experts*, not just their own domain. Each returns:
- Issues found (with file, line, category)
- "Clean — no issues" if nothing to report

**Simple mode:** Single pass. If issues found, orchestrator fixes directly.

**Standard/Complex mode:** If issues found:
1. Route each issue to the responsible expert for fixing.
2. Re-spawn affected experts with targeted fix tasks.
3. Re-review (all 5 experts again). **Max 2 review rounds total.**
4. If issues remain after 2 rounds → present to user for decision.

## Step 7: Finish

1. **Ripple-check audit**: Walk [`sdd/CLAUDE-REFERENCE.md` § Ripple-check table > Detailed checklist](../../../sdd/CLAUDE-REFERENCE.md#detailed-checklist). For each
   triggered row, verify target files were updated. For domain-specific gaps
   (e.g., missing test), re-spawn the relevant expert. For cross-domain gaps,
   fix directly.
2. **CHANGELOG**: Add one stub line per completed item under `[Unreleased]` —
   see format in `sdd/CLAUDE-REFERENCE.md` ripple-check row **CHANGELOG entry**.
3. **BACKLOG**: Delete completed items from BACKLOG.md, add as `[x]` to
   BACKLOG-DONE.md. Partially done → split: done part to BACKLOG-DONE.md as
   `[x]`, new ID in BACKLOG.md for remainder.
4. **Validate**: Run `hatch run all`. Fix failures (max 2 attempts — see Rules).
5. Stage all changes, commit with backlog ID prefix.
6. Push feature branch (never master).
7. Report: mode used, experts spawned (count of rounds), files changed,
   ripple-checks completed, validation status, deferred items (if any).

## Rules

- Never push to master. Push the feature branch.
- If an expert reports a spec contradiction, **stop and ask the user**.
- If `hatch run all` fails after 2 fix attempts, report the failure and stop.
- Commit message: `<BACKLOG-ID>: <short description>`.
- The orchestrator handles cross-domain files (CHANGELOG, BACKLOG, README tables,
  pyproject.toml extras). Experts stay in their domain. The Documentation Expert
  assesses README/CHANGELOG impact but does not write to them.
- **User breaks ties.** The orchestrator never overrides expert disagreements
  autonomously — it presents the conflict and asks.
