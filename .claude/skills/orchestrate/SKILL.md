---
name: orchestrate
description: Multi-agent orchestration — domain experts author, lens-and-method reviewers review
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
docstrings, and `sdd/`. **Anything else is the orchestrator's.** Derive it by
checking a path against those five lines — do not look for it in a list here,
because a list read as exhaustive plus the instruction below is exactly how an
unlisted file gets handed to a persona whose `DOMAIN:` excludes it. No list is
given for that reason: the residue is most of the repository root plus several
whole trees, and any enumeration written here goes stale the next time something
is added.

Two examples, offered as traps rather than as coverage. **`benchmarks/`** is a
source tree with its own `bench-*` aliases, so it reads as Store & Backend or
Testing work and is neither. **`FEATURES.md`** is the authoritative feature
reference per `CLAUDE.md`, so it reads as Documentation work and is not — the
Documentation `DOMAIN:` is `docs-src/`, `examples/`, `docs/` and docstrings, and
a root file matches none of them. If a path looks like a persona's work, that is
the moment to check the `DOMAIN:` line rather than the moment to assume.

Do not stretch a persona over anything the derivation puts outside its
`DOMAIN:` — not the two examples above, and not the rest of the residue they
stand for. A `DOMAIN:` line is what the persona reads
its constraints against, and widening it silently is how a change gets an owner
who has no foundation docs for it. This clause is the single home for the
question; the Rules entry below points here rather than restating the set.

<a id="reviewer-selection"></a>
### Reviewer selection (Steps 3 and 6)

**Open question, deliberately untracked.** Whether this skill's reviewers should
read each changed file *whole* rather than diff-shaped — the gate `/ship` adopted
— is unsettled. [ADR-0037 §
Consequences](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md)
states the case and declines to decide it on `/ship`'s evidence alone. Deciding
it needs evidence from an `/orchestrate` delivery's own traces; no backlog item
carries it, so this note is where a reader of this skill meets the question.

**A reviewer is selected by the subject set it is aimed at and the method it
uses, never by which directory it owns.** A persona is one way to staff a lens,
not the unit of selection. Two measurements, over different samples: across the
**two richest** traces of the four deliveries run under `/ship`, a persona lens
reaches a minority of the findings; across **five** deliveries' changed files,
the surface no persona owns is where most of the findings on process work
landed. The first sample is two chosen from four, not two that were all there
were — which is what its *Reverse if* turns on.
Both, with their samples, are in
[ADR-0036 § Context](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md#context);
the bound that the first is a per-finding judgement and the second the mechanical
one is in
[§ Consequences](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md#consequences).

1. **Write down the subject set** — whatever the change's own words claim
   something about. Not a fixed vocabulary. A backend, a capability, an
   operation, a caller, a gate, a skill: illustrations, not a menu, and the next
   change will name something none of them cover. Ask what the words pick
   out, not which of a list they match. This is also not the file list, and the
   gap between the two is where defects survive.
2. **Pick a lens per reviewer** from `/ship`'s
   [lens menu](../ship/SKILL.md#lens-menu), which this skill shares rather than
   copies. Pick by what the work is and what earlier rounds did not look at.
3. **Exactly one reviewer per round reaches its verdict by executing**, not by
   reading — running the gate, measuring the base branch, exercising each
   subject. It reports what it *ran* and what came back, and a finding it cannot
   reproduce is reported as unreproduced. **One, not "at least one"**: the
   base-branch recipe below uses a fixed `tmp/base` path, and two measuring
   reviewers in a round would collide on it — the second `worktree add` fails,
   or one tears down a worktree the other is mid-measurement in, and both
   failures reach the orchestrator as an unreproduced finding, which reads like
   a clean result. This matches `/ship`'s one measuring member per panel.

   Reviewers here are plain subagents against the working tree, so there is no
   `measuring` keyword to pass: that word belongs to
   [`/rvw-pr`](../rvw-pr/SKILL.md), and it opens a permission gate this skill has
   no equivalent of. **That is a difference in mechanism, not in hazard.**

   **Run only the allowlisted set, and write only under `tmp/`.** No permission
   gate does not mean no bound: `/rvw-pr`'s
   [allowlist](../rvw-pr/SKILL.md) is the single home for which commands are
   safe, and it is a fact about `pyproject.toml` — that no suffix or args-shape
   rule identifies a writing alias, proved by two live counterexamples — so it
   holds identically for a reviewer spawned from here. Read it there and obey it
   here. The `tmp/` write bound matters more in this skill than in that one,
   because what a stray `format` or `drift-check refresh-baseline` would
   overwrite has never been committed.

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
   below — it is absent from `git diff HEAD` and from `--untracked-files=all`
   alike. If
   `worktree remove` fails on a stale entry, `git worktree prune` then retry.
   [`/rvw-pr`](../rvw-pr/SKILL.md)'s measuring block carries the same three
   commands for a *different* reason — there the checked-out revision is the
   pushed state `/ship` certifies, here it is uncommitted work that has never
   been saved anywhere. Deliberately a second copy rather than a link: sending a
   reader there would hand them a paragraph whose stated reason is false in this
   skill. Edit both when the commands change. A fixed path is safe on each side
   for its own reason: here, the exactly-one rule above; there, `/ship`'s one
   measuring member per panel. Neither rule protects the other skill.
4. **Staff each lens.** A domain persona when the lens sits inside one domain
   and its foundation docs help; `general-purpose` otherwise — which is the
   normal case for a lens spanning domains or aimed at the surface no persona
   owns.

**Read-only, and checked — for every reviewer, not only the measuring one.**
This applies to all four numbered items above, in both steps that use them:
every reviewer this skill spawns is a plain subagent with a full tool set,
pointed at a working tree nothing has pushed. At Step 6 that tree holds the
**only** copy of the authoring experts' output; at Step 3 it holds whatever
planning the orchestrator has not committed. Either way a reviewer write is
unrecoverable. The reading reviewers are if
anything the likelier tamperers, since the most probable violation is a reviewer
editing a file it was asked to review — what a reviewer with an opinion
about the prose does, not what a reviewer running the gate does. So say
read-only in **every** member's prompt, and check it the same way for all of
them. `/ship` hoists its equivalent for the same reason.

**The invariant is *unchanged since spawn*, whatever the baseline holds.** That
phrasing is deliberate, because the two steps that route here start from
different trees: at Step 3 nothing has been built yet, so the baseline may be
empty; at Step 6 it never is, since Step 6 runs **before** Step 7 commits and the
tree carries every authoring expert's output. `/ship` can require an *empty*
`git status --porcelain` because its tree is pushed and committed; requiring that
here is unsatisfiable for Step 6, and comparing porcelain strings is worse than
useless, because porcelain prints status codes and paths and nothing derived from
content — a reviewer editing an already-modified file leaves ` M path`
byte-identical. Capture three things when the reviewers
spawn and require all three unchanged before triage:

```bash
git rev-parse HEAD
```
```bash
git status --porcelain --untracked-files=all
```
```bash
git diff HEAD
```

`git diff HEAD` is the content-sensitive one, and it is what catches an edit to a
file the authors already modified — porcelain prints ` M path` either way.
Porcelain adds the paths diff cannot see: new and deleted untracked files, **as
long as they are not gitignored**. `rev-parse` catches a moved revision.

**Residual, measured rather than reasoned.** Running the three captures against
each tamper in a throwaway worktree:

| Tamper | Detected by |
|---|---|
| Edit a tracked file the authors already modified | `git diff HEAD` |
| Create or delete an untracked, non-ignored file | porcelain |
| Overwrite an existing untracked file's contents | — |
| Create or edit **anything on a gitignored path** | — |

The last row is the wide one, and it is not restricted to content edits or to
files that already exist: `--untracked-files=all` lists untracked-but-not-ignored
paths only, so a *creation* under `site/`, `dist/`, `build/`, `htmlcov/`,
`.venv/`, `__pycache__/`, `.benchmarks/` or the ignored part of `.claude/` is as
invisible as an overwrite. A reviewer writing `.claude/settings.local.json` —
plausible for a subagent with a full tool set — defeats all three.

The `tmp/` write bound narrows the *honest* reviewer's blast radius, but it is
not the answer here: these captures exist for the reviewer that broke the bound,
so assuming the bound holds is assuming what the check is testing. Committing
before review — which would restore `/ship`'s empty-porcelain model exactly, and
with it detection of every case above — is the structural closure this skill has
not taken.

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
   triggered row, verify target files were updated. **Close the gaps yourself**,
   and delegate only where a fix needs depth inside one file tree — the same
   routing as Step 6, for the same reason. This step is where cross-file sweeps
   are most likely, which is exactly what a domain-scoped fixer cannot do.
2. **CHANGELOG**: Add one stub line per completed item under `[Unreleased]` —
   see format in `sdd/CLAUDE-REFERENCE.md` ripple-check row **CHANGELOG entry**.
3. **BACKLOG**: Delete completed items from BACKLOG.md, add as `[x]` to
   BACKLOG-DONE.md. Partially done → split: done part to BACKLOG-DONE.md as
   `[x]`, new ID in BACKLOG.md for remainder. Decided against → delete and
   record one line under BACKLOG-DONE.md § Decided against. Authoritative:
   [`sdd/BACKLOG.md` § How this file works](../../../sdd/BACKLOG.md#how-this-file-works).
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
- **Every review round carries exactly one reviewer that runs something**, and
  it reports what it ran.
- **Every reviewer is read-only, and the round proves it** — read-only in each
  member's prompt, plus the three-capture check in
  [Reviewer selection](#reviewer-selection). Not only the measuring one: they
  all have a full tool set and the tree is the only copy of the work.
- **The orchestrator fixes and owns the sweep.** Delegate a fix only for depth
  inside one file tree.
- **User breaks ties.** The orchestrator never overrides expert disagreements
  autonomously — it presents the conflict and asks.
