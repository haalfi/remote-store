---
name: orchestrate
description: Multi-agent orchestration — delegates to domain experts for complex tasks
disable-model-invocation: true
argument-hint: "[BACKLOG-ID] [optional: task description]"
---

Orchestrate a complex task by delegating authoring to domain experts and
reviewing by lens and method. See ADR-0020 for architecture rationale, and
[ADR-0036](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md) for why
the two halves select differently.

Reviews here are capped at two rounds. When a defect reaching `master` would be
costly enough to justify reviewing to convergence instead, [`/ship`](../ship/SKILL.md)
delivers the whole task as one PR and stops on findings rather than on a count;
its "When not to use this" section is the authority on which to pick.

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

### Expert activation rules (authoring only)

These govern **Step 4**, where work is written. Review selection is a different
question with a different answer — see [Reviewer selection](#reviewer-selection)
below and [ADR-0036](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md).

**Code change (feature, refactor, bug fix):** activate the experts whose domain
the change writes into. A pure backend change needs no Extension Expert; a
docs-only change needs only the Documentation Expert.

**SDD-only change (spec/RFC/ADR/process):** The SDD Expert leads
implementation.

**Nobody's domain.** `scripts/`, `.claude/`, `pyproject.toml`, `CLAUDE.md`,
`CHANGELOG.md`, `.github/` and `infra/` are in no persona's `DOMAIN:` line. The
orchestrator authors those directly. Do not stretch a persona over them — a
`DOMAIN:` line is what the persona reads its constraints against, and widening
it silently is how a change gets an owner who has no foundation docs for it.

<a id="reviewer-selection"></a>
### Reviewer selection (Steps 3 and 6)

**A reviewer is selected by the subject set it is aimed at and the method it
uses, never by which directory it owns.** A persona is one way to staff a lens,
not the unit of selection. Measured across four deliveries, a persona lens
reaches a minority of findings, and the surface no persona owns carried most of
the findings on process work: [ADR-0036](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md).

1. **Write down the subject set** — what the change's own words claim something
   about (a backend, a capability, an operation, a caller, a gate, a skill).
   This is not the file list, and the gap between the two is where defects
   survive.
2. **Pick a lens per reviewer** from `/ship`'s
   [lens menu](../ship/SKILL.md#lens-menu), which this skill shares rather than
   copies. Pick by what the work is and what earlier rounds did not look at.
3. **At least one reviewer reaches its verdict by executing**, not by reading —
   running the gate, measuring the base branch, exercising each subject. It
   reports what it *ran* and what came back, and a finding it cannot reproduce
   is reported as unreproduced. Reviewers here are plain subagents against the
   working tree, so there is no permission to open and no `measuring` keyword to
   pass: that word belongs to [`/rvw-pr`](../rvw-pr/SKILL.md), which reviews a
   *pushed PR* under an allowlist this skill's reviewers do not run under. What
   this skill owes instead is the opposite caution — these reviewers **can**
   write, so say read-only in the prompt and confirm a clean
   `git status --porcelain` before trusting a round.
4. **Staff each lens.** A domain persona when the lens sits inside one domain
   and its foundation docs help; `general-purpose` otherwise — which is the
   normal case for a lens spanning domains or aimed at the surface no persona
   owns.

Never pin or prefer a model
([ADR-0035](../../../sdd/adrs/0035-vary-method-not-model.md)).

## Step 3: Refine (Standard and Complex only)

Spawn reviewers per [Reviewer selection](#reviewer-selection) with the plan from
Step 2 — lenses aimed at the plan's subject set, not one reviewer per domain.
Each returns:
- Gaps, risks, or contradictions they see
- Suggestions within their lens
- "No concerns" if the plan is sound under that lens

A plan has nothing built yet, so the measuring reviewer measures **what the plan
asserts about existing behaviour**. That is the cheapest place in the whole run
to catch a false premise, and it is where the premise obligation
([ADR-0035](../../../sdd/adrs/0035-vary-method-not-model.md)) has the most to
buy: a plan built on a premise nobody ran is the one that costs rounds later.

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

Spawn reviewers per [Reviewer selection](#reviewer-selection). Each reviews
*all output from all experts*, within its lens, and returns:
- Issues found (with file, line, category)
- What it **ran** and what came back, if it is the measuring reviewer
- "Clean — no issues" if nothing to report

**Simple mode:** Single pass. If issues found, orchestrator fixes directly.

**Standard/Complex mode:** If issues found:
1. **The orchestrator fixes, and owns the sweep.** A fix changes a thing, and
   every other description of that thing is now suspect — the sweeps that pay
   are cross-file, so a domain-scoped fixer cannot perform them. Apply
   [`/fix-pr`](../fix-pr/SKILL.md)'s Rules: the finding's class, not only the
   lines it names; the sibling descriptions of your own changes; a fix to a
   quantified claim scoped to the quantifier.
2. **Delegate a fix only when it needs depth inside one file tree** — a backend
   invariant, a conformance fixture, an extension contract. Re-spawn that expert
   with the targeted task. The orchestrator still owns the sweep across
   everything the fix touched outside that tree.
3. Re-review, re-selecting lenses by what round 1 found and did not look at.
   **Max 2 review rounds total.**
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
7. Report: mode used, authoring experts spawned, **the lens and method of each
   reviewer per round** and what the measuring one ran, the subject set with
   each entry marked executed / read only / not reached, files changed,
   ripple-checks completed, validation status, deferred items (if any). A
   subject left `not reached` is a stated coverage bound, not an oversight —
   say so rather than letting silence imply coverage.

## Rules

- Never push to master. Push the feature branch.
- If an expert reports a spec contradiction, **stop and ask the user**.
- If `hatch run all` fails after 2 fix attempts, report the failure and stop.
- Commit message: `<BACKLOG-ID>: <short description>`.
- The orchestrator handles cross-domain files (CHANGELOG, BACKLOG, README tables,
  pyproject.toml extras) and everything in no persona's domain (`scripts/`,
  `.claude/`, `CLAUDE.md`, `.github/`, `infra/`). Experts stay in their domain
  when authoring. The Documentation Expert assesses README/CHANGELOG impact but
  does not write to them.
- **Reviewers are picked by lens and method, never by domain or model.** A
  persona staffs a lens; it is not the unit of selection.
- **Every review round carries a reviewer that runs something**, and it reports
  what it ran.
- **The orchestrator fixes and owns the sweep.** Delegate a fix only for depth
  inside one file tree.
- **User breaks ties.** The orchestrator never overrides expert disagreements
  autonomously — it presents the conflict and asks.
