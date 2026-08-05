---
name: ship
description: Deliver a task as one merge-ready PR. Plan, build, then review to convergence
disable-model-invocation: true
argument-hint: "[BACKLOG-ID ...] or [task description]"
---

Take a task from framing to a PR that is ready to merge, in one invocation.
The deliverable is **one PR whose review has converged**, not a PR that has
been reviewed a fixed number of times.

Composes the existing skills rather than reimplementing them: [`/pr`](../pr/SKILL.md)
creates the PR, [`/rvw-pr`](../rvw-pr/SKILL.md) is the reviewer's instruction set,
[`/fix-pr`](../fix-pr/SKILL.md) owns comment-fetch and thread-resolve mechanics.
[`/orchestrate`](../orchestrate/SKILL.md) remains the choice when you want expert
fan-out **without** the convergence loop.

## When not to use this

The loop is the dominant cost: every round is a reviewer pass, a fix pass, and a
full `hatch run all`. What that came to on a large delivery is recorded in
[ADR-0033](../../../sdd/adrs/0033-ship-convergence-driven-review.md).

Use `/orchestrate` or plain implementation when the change is small, mechanical,
or easily reverted. Use `/ship` when a defect that reaches `master` is costly:
contract or spec changes, cross-backend work, anything touching a published
surface.

## Roles

| Role | Who | Notes |
|---|---|---|
| Orchestrator | main loop | **Never delegated.** It holds the convergence judgement |
| Designer / planner | main loop, plan mode | One role, not two, unless the task is architectural |
| Author, fixer | domain-expert subagents | May decline an instruction **with evidence** |
| Reviewer | fresh subagent per round | **Never resumed.** A resumed reviewer inherits its own prior conclusions |

## Step 1: Frame

Parse `$ARGUMENTS` for backlog IDs, a task description, or both. No item and no
description: ask.

1. Read the item(s) in `sdd/BACKLOG.md` and every spec/RFC they link.
2. Read [`sdd/CLAUDE-REFERENCE.md` § Ripple-check > Pre-work index](../../../sdd/CLAUDE-REFERENCE.md#pre-work-index); note triggered rows.
3. Open or create the trace per [CLAUDE.md § Trace authoring](../../../CLAUDE.md#trace-authoring).
4. Branch: `git checkout -b <id>-<short-name>`.

## Step 2: Design (plan mode)

Enter plan mode. Produce a plan naming files, signatures, spec IDs, and the
ripple targets from Step 1. Use `AskUserQuestion` for decisions the item leaves
open, with a recommendation per question. Exit via `ExitPlanMode` for approval.

Do not start building before the plan is approved.

## Step 3: Build and open the PR

Implement, delegating to domain experts where the work is theirs. Then:

1. `hatch run all` green.
2. Commit with the item ID prefix; push the feature branch.
3. Run [`/pr`](../pr/SKILL.md), which owns the validation gates, the trace gate, and the template.

**The PR body states what changed and why, not what to doubt.** Round 1 reads
the body as part of PR content, so anything you would flag as risky primes the
round that must not be primed. Doubts belong in the round-2 and later briefs,
where priming is the point.

## Step 4: Review loop

The heart of this skill. Each round is: brief → review → triage → fix → gate →
push → reply and resolve.

### Round composition

| Round | Lens | Model |
|---|---|---|
| 1 | **Broad, unprimed** | A different model than the author's. Fable preferred; Opus when the author was Fable |
| 2..N | One scoped lens per round | Repo domain experts, or general-purpose |
| Final | Whatever the last fix pass touched | Fresh general reviewer |

**Round 1 is unprimed on purpose.** It receives the diff, the goal, and repo
conventions, never your areas of concern: a reviewer handed conclusions confirms
them. Use a different model so its blind spots differ from the author's.

Spawn an `Agent` with `model:` set and a prompt instructing it to read and
execute `.claude/skills/rvw-pr/SKILL.md`. Two things the prompt must carry,
because the spawn path does not supply them:

- **The PR number.** `rvw-pr/SKILL.md` read as a file still contains a literal
  `$ARGUMENTS`; only slash invocation substitutes it. Without the number the
  agent falls through to that skill's ask-the-user branch, which a subagent
  cannot answer. Pass the number and nothing else, per the unprimed rule.
- **The read-only constraint, restated.** `rvw-pr`'s `allowed-tools` frontmatter
  grants no `Edit` or `Write`, and that guarantee is *lost* when a general agent
  merely reads the file: it keeps its own full tool set. Restate the constraint
  in the prompt, and prefer a `subagent_type` without write tools where one
  fits. Until then "reviewers are read-only" is enforced by instruction rather
  than by tooling, which is weaker than the frontmatter it stands in for.

Invoking `/rvw-pr` directly keeps both guarantees and is the right choice
whenever model diversity does not matter; it cannot take a model override.

### Lens menu

Pick per round, by what the work is and what previous rounds missed:

- **Neglected surface.** What have prior rounds *not* looked at? Historically the
  highest-yield lens; behavioural bugs hide where review attention has not gone.
- **Fix-pass.** Treat the previous round's corrections as suspect work.
- **Self-contradiction.** Does the PR disagree with its own other additions?
- **Coverage reachability.** What does the gate structurally never execute?
  Docker-gated fixtures, backends with no fixture, `# pragma: no cover`. A green
  gate proves the *covered* code works; it never says what is covered.
- **Consumer.** Docs, guides, and API read from outside.

### Every brief must carry

1. **Areas as areas, not conclusions:** "verify or refute each independently."
2. **What the previous fix pass changed**, so it gets reviewed.
3. **What previous rounds have not examined.**
4. **Explicit permission to find nothing**, or round N manufactures a finding.
   On the final round, add: weight toward what would be *wrong once merged*,
   away from stylistic refinement.

### Triage each finding

| Verdict | Action |
|---|---|
| Must-fix | Wrong once merged: bad behaviour, a false statement in a durable artifact, a shipping gap. Fix in this PR. |
| File-it | Real, but outside this PR's scope. Backlog item, cited in the reply. |
| Refute | Wrong or already handled. Reply with the evidence; do not fix. |

Refuting is a first-class outcome. Reviewers are wrong often enough that
accepting every finding degrades the work, so verify before fixing.

### Close each round

`hatch run all` green → commit → push → reply to **every** thread and resolve
it. Use [`/fix-pr`](../fix-pr/SKILL.md)'s comment-fetch and thread-resolve
mechanics. Never start the next round against unpushed code: the reviewer would
target stale lines.

Replies carry the reasoning that does not belong in the diff: what was measured,
what was refuted and why. The PR record is where that survives.

### Stop rule

> **Stop when the most recent round yields zero must-fix findings *and* that
> round reviewed the most recent fix pass.**

The second clause is the one that matters: **the loop cannot end on an
unreviewed fix pass.** A fix pass is not trusted work. It is new code written
under time pressure by someone who has already been wrong once in this file.

- **Floor: lens coverage, not a round count.** Every lens the diff *warrants*
  must have been applied. A one-surface change may warrant only the broad round,
  and then a clean round 1 ends the loop; stopping there is correct. A diff that
  adds code the gate never executes, spreads a claim across artifacts that can
  disagree, or changes a published surface warrants those lenses, and round 1 by
  construction did not apply them: a clean sweep is silent about questions
  nobody asked.
- **Ceiling: 5 finding-rounds, and it is soft.** On reaching it, escalate to the
  user with what is still open. Do not terminate silently. A verification round
  over an otherwise unreviewed fix pass does not count *if it finds nothing*; a
  verification round that finds something is a finding-round like any other, and
  its own fix pass still owes a verification. Without that, the
  verify-fix-verify tail is exempt from the bound it exists under.
- **Judge severity, not count.** Counts plateau while severity falls.
- **A round that fixed nothing leaves nothing unreviewed.** The fix-pass clause
  is satisfied vacuously, so a clean round needs no successor to verify it.

**Check a clean round before trusting it.** `/rvw-pr` makes its reviewer state
the PR's subject in its own words precisely so this is cheap: if that line does
not match what the PR does, the reviewer reviewed the wrong thing and its
silence is worthless. Re-run the round; do not count it.

The delivery this rule was derived from is tabulated in
[ADR-0033](../../../sdd/adrs/0033-ship-convergence-driven-review.md), round by
round. Read it before tuning any of the above: it is the evidence that finding
counts plateau while severity keeps falling, and that consecutive rounds each
found defects in the previous round's fixes.

**Divergence check:** if a round finds something *more severe* than the previous
round **in code the fix passes changed**, the corrections are spawning worse
defects than they fix. Stop, and re-plan rather than keep patching.

The qualifier is load-bearing. A latent defect surfaced in untouched code by a
new lens is the opposite signal, and it is what the neglected-surface lens is
for: the delivery this rule came from hit its most severe finding at round 5
that way, and proceeding was correct. Unqualified, this check would have
condemned it.

## Step 5: Close

1. Ripple-check audit: [`sdd/CLAUDE-REFERENCE.md` § Detailed checklist](../../../sdd/CLAUDE-REFERENCE.md#detailed-checklist).
2. CHANGELOG, BACKLOG/BACKLOG-DONE, and the trace, including `review_rounds`,
   `discovery_followups`, and `surprising_ripples`.
3. Report: rounds run, findings per round with their character, what was filed
   rather than fixed, and any surface the gate never executed locally.

Then stop. **`/ship` never merges.** It hands over a PR that is ready to be.

## Rules

- Never push to master.
- Never end the loop on an unreviewed fix pass.
- Reviewers are read-only and fresh each round; fixers may decline with evidence.
- Findings that are real but out of scope get filed, not silently dropped.
- If a reviewer and a fixer disagree on fact, **measure**. Neither wins by assertion.
