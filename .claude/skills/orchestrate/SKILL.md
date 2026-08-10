---
name: orchestrate
description: Multi-agent orchestration — delegates to domain experts for complex tasks
disable-model-invocation: true
argument-hint: "[BACKLOG-ID] [optional: task description]"
---

Orchestrate a complex task by delegating authoring to domain experts and
reviewing by lens and method. See
[ADR-0020 § Decision](../../../sdd/adrs/0020-orchestrate-iterative-convergence.md#decision)
for architecture rationale, and
[ADR-0036 § Decision](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md#decision)
for why the two halves select differently.

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

<a id="expert-activation-rules-authoring-only"></a>
### Expert activation rules (authoring only)

These govern **Step 4**, where work is written. Review selection is a different
question with a different answer — see [Reviewer selection](#reviewer-selection)
below and
[ADR-0036 § Decision](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md#decision).

**Code change (feature, refactor, bug fix):** activate the experts whose domain
the change writes into. A pure backend change needs no Extension Expert; a
docs-only change needs only the Documentation Expert.

**SDD-only change (spec/RFC/ADR/process):** The SDD Expert leads
implementation.

<a id="nobodys-domain"></a>
#### Nobody's domain

The five `DOMAIN:` lines are `src/remote_store/` (excluding
`ext/`), `src/remote_store/ext/`, `tests/`, `docs-src/` + `examples/` + `docs/` +
docstrings, and `sdd/`. **Anything else is the orchestrator's** — derive it from
those five lines rather than from a list, because a list read as exhaustive plus
the instruction below is exactly how an unlisted file gets handed to a persona
whose `DOMAIN:` excludes it. What falls out today: `scripts/`, `.claude/`,
`pyproject.toml`, `.github/`, `infra/`, and the root files — `CLAUDE.md`,
`CHANGELOG.md`, `README.md`, `CONTRIBUTING.md`.

Do not stretch a persona over them. A `DOMAIN:` line is what the persona reads
its constraints against, and widening it silently is how a change gets an owner
who has no foundation docs for it. This clause is the single home for the
question; the Rules entry below points here rather than restating the set.

<a id="reviewer-selection"></a>
### Reviewer selection (Steps 3 and 6)

**A reviewer is selected by the subject set it is aimed at and the method it
uses, never by which directory it owns.** A persona is one way to staff a lens,
not the unit of selection. Two measurements, over different samples: across the
**two** deliveries whose traces record findings round by round, a persona lens
reaches a minority of them; across **five** deliveries' changed files, the
surface no persona owns is where most of the findings on process work landed.
Both, with their samples, are in
[ADR-0036 § Context](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md#context);
the bound that the first is a per-finding judgement and the second the mechanical
one is in
[§ Consequences](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md#consequences).

1. **Write down the subject set** — whatever the change's own words claim
   something about. Not a fixed vocabulary: a backend, a capability, an
   operation, a caller, a gate and a skill have all been subjects here, and the
   next change will name something none of those cover. Ask what the words pick
   out, not which of a list they match. This is also not the file list, and the
   gap between the two is where defects survive.
2. **Pick a lens per reviewer** from `/ship`'s
   [lens menu](../ship/SKILL.md#lens-menu), which this skill shares rather than
   copies. Pick by what the work is and what earlier rounds did not look at.
3. **At least one reviewer reaches its verdict by executing**, not by reading —
   running the gate, measuring the base branch, exercising each subject. It
   reports what it *ran* and what came back, and a finding it cannot reproduce
   is reported as unreproduced. Reviewers here are plain subagents against the
   working tree, so there is no `measuring` keyword to pass: that word belongs to
   [`/rvw-pr`](../rvw-pr/SKILL.md), and it opens a permission gate this skill has
   no equivalent of. **That is a difference in mechanism, not in hazard.** What
   this skill owes instead is three cautions, each differing from `/ship`'s
   version because the state under review differs — it is uncommitted work that
   exists nowhere else, so here a bad command is unrecoverable rather than
   re-fetchable.

   **Run only the allowlisted set, and write only under `tmp/`.** No permission
   gate does not mean no bound: `/rvw-pr`'s
   [allowlist](../rvw-pr/SKILL.md) is the single home for which commands are
   safe, and it is a fact about `pyproject.toml` — that no suffix or args-shape
   rule identifies a writing alias, proved by two live counterexamples — so it
   holds identically for a reviewer spawned from here. Read it there and obey it
   here. The `tmp/` write bound matters more in this skill than in that one,
   because what a stray `format` or `drift-check refresh-baseline` would
   overwrite has never been committed.

   **Tamper check: unchanged since spawn, and content-sensitive.** These
   reviewers **can** write, so say read-only in the prompt. `/ship` requires an
   *empty* `git status --porcelain`, which works only because its tree is pushed
   and committed; here Step 6 runs **before** Step 7 commits, so the tree
   necessarily carries every authoring expert's output and porcelain is
   non-empty by construction. Requiring empty is unsatisfiable; comparing
   porcelain strings is worse, because porcelain prints status codes and paths
   and nothing derived from content — a reviewer editing a file the experts
   already modified leaves ` M path` byte-identical, and that is the single most
   likely violation. Capture three things at spawn and require all three
   unchanged before triage:

   ```bash
   git rev-parse HEAD
   ```
   ```bash
   git status --porcelain --untracked-files=all
   ```
   ```bash
   git diff HEAD
   ```

   `git diff HEAD` is the content-sensitive one; porcelain adds the paths that
   diff cannot see (new and deleted untracked files); `rev-parse` catches a moved
   revision. **Residual, stated rather than papered over:** an edit to the
   *contents* of an already-untracked file changes none of the three. The `tmp/`
   bound above is what shrinks that hole, and committing before review — which
   would restore `/ship`'s empty-porcelain model exactly — is the structural
   closure this skill has not taken.

   **Reaching the base branch.** `git checkout` would destroy the very
   uncommitted work under review, so never move the checked-out revision. Use a
   worktree under the gitignored `tmp/`, one Bash call per line, and tear it
   down — `worktree add` is not idempotent and the next round runs the same
   command:

   ```bash
   git worktree add tmp/base <base-ref>
   ```
   ```bash
   git worktree remove tmp/base
   ```

   `tmp/` is gitignored, so the worktree perturbs none of the three captures
   above — it is absent from `git diff HEAD` and from `--untracked-files=all`
   alike. If
   `worktree remove` fails on a stale entry, `git worktree prune` then retry.
   [`/rvw-pr`](../rvw-pr/SKILL.md)'s measuring block carries the same three
   commands for a *different* reason — there the checked-out revision is the
   pushed state `/ship` certifies, here it is uncommitted work that has never
   been saved anywhere. Deliberately a second copy rather than a link: sending a
   reader there would hand them a paragraph whose stated reason is false in this
   skill. Edit both when the commands change.
4. **Staff each lens.** A domain persona when the lens sits inside one domain
   and its foundation docs help; `general-purpose` otherwise — which is the
   normal case for a lens spanning domains or aimed at the surface no persona
   owns.

Never pin or prefer a model
([ADR-0035 § Decision](../../../sdd/adrs/0035-vary-method-not-model.md#decision)).

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
([ADR-0035 § Decision](../../../sdd/adrs/0035-vary-method-not-model.md#decision))
has the most to buy: a plan built on a premise nobody ran is the one that costs
rounds later.

**One round only.** The orchestrator integrates feedback and adjusts the plan.
Any unresolved disagreements or open questions → escalate to user. Do not
loop — if the user needs to decide, present the options and wait.

**Simple mode:** Skip this step entirely.

## Step 4: Execute

Each expert is spawned via its `subagent_type` (referenced below), with the
(refined) plan and per-call task passed in the invocation prompt.

Which experts spawn is decided by the [activation
rules](#expert-activation-rules-authoring-only) above — the experts whose domain
the change writes into, not a fixed list. Anything in no persona's domain, the
orchestrator authors itself.

**Feature/refactor:** Spawn the activated experts using multiple Agent tool
calls, in parallel.

**Bug fix (TDD):** Sequential — Testing Expert goes first. This follows the
bug-fix protocol in CLAUDE.md (backlog → changelog → failing test → fix):
1. Spawn **Testing Expert only** — write a failing test that clearly reproduces
   the bug, conforming to the full testing guide (`sdd/TESTING.md`).
2. Verify the test fails for the right reason.
3. Then spawn the remaining **activated** experts to fix the bug. Which those
   are follows the same rule: a bug fixed entirely in `src/remote_store/` needs
   the Store & Backend Expert and no other, and the SDD Expert joins only when
   the fix changes a spec, ADR or process doc rather than merely citing one.

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

After the activated experts complete, collect and categorize results:

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
*the whole of the authoring output*, not only its own lens's files, and returns:
- Issues found (with file, line, category)
- What it **ran** and what came back, if it is the measuring reviewer
- "Clean — no issues" if nothing to report

**Simple mode:** Single pass — **and that pass is the measuring one**, since it
is the only review the mode ever performs (Step 3 is skipped entirely), so a
reviewer that only reads leaves the execution obligation with nothing to attach
to. Simple mode is where it is cheapest to drop and most valuable to keep: the
small, clear-scope changes it exists for are where a false premise goes
unexamined and there is no second round to catch it. If issues found,
orchestrator fixes directly.

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
- The orchestrator handles cross-domain files and everything in
  [nobody's domain](#nobodys-domain), which is that clause's set and is not
  restated here. Experts stay in their domain when authoring. The Documentation
  Expert assesses README/CHANGELOG impact but does not write to them.
- **Reviewers are picked by lens and method, never by domain or model.** A
  persona staffs a lens; it is not the unit of selection.
- **Every review round carries a reviewer that runs something**, and it reports
  what it ran.
- **The orchestrator fixes and owns the sweep.** Delegate a fix only for depth
  inside one file tree.
- **User breaks ties.** The orchestrator never overrides expert disagreements
  autonomously — it presents the conflict and asks.
