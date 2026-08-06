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
[`/orchestrate`](../orchestrate/SKILL.md) remains the choice when you want a
capped, consolidate-and-decide review rather than an open-ended convergence
loop.

## When not to use this

The loop is the dominant cost: every round is one or more reviewer passes — a
panel, from round 3 — plus a fix pass and a full `hatch run all`, and the
unprimed exit gate can append a further reviewer pass at the close. What the
pre-panel shape came to on a large delivery is recorded in
[ADR-0033](../../../sdd/adrs/0033-ship-convergence-driven-review.md); the cost
the panel and exit gate add on top is recorded in
[ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md).

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
| Reviewer | fresh subagents — one per panel member | **Never resumed.** A resumed reviewer inherits its own prior conclusions |

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

| Round | Composition | Model |
|---|---|---|
| 1 | One reviewer: **broad, unprimed** | A different model than the author's. Fable preferred; Opus when the author was Fable |
| 2 | One reviewer, one scoped lens | Repo domain experts, or general-purpose |
| 3..N | Panel sized by the diff's breadth and the prior round's yield, one scoped lens per member. **Odd rounds add one unprimed member** | Scoped members: domain experts or general-purpose. Unprimed member: a different model than the author's, same tier or higher |
| Closing gate | Not a round in the sequence: whichever round ends the loop must review the last fix pass **and** satisfy the unprimed exit gate; a missing unprimed member is supplied by one appended pass (see Stop rule) | Appended pass: a different model than the author's, same tier or higher — the unprimed rule, unchanged |

**Panels run in parallel against the same pushed state.** Each member is
fresh and blind to the others: scoped members get briefs per the requirements
below; the unprimed member gets the PR number and nothing else. Two
constraints keep that parallelism sound:

- **Members are analysts, not posters.** Every subagent shares the owner
  token, and GitHub allows one pending review per user per PR — concurrent
  members running `rvw-pr`'s posting step would cross-contaminate a single
  pending review and drop findings while that skill's `totalCount`
  verification still reads success. Panel members run `rvw-pr` in its
  **analyze-only mode** (defined in that skill): Steps 0–3, Step 4 skipped,
  Step 5's report — `Subject:` line included, which the Stop rule's
  clean-round check needs — plus consolidated findings returned as the final
  message. The orchestrator merges, dedups (two members reporting one defect
  is one finding), posts the round's findings as one review, and runs a
  single triage and fix pass. A solo round — rounds 1 and 2, or a panel of
  one — keeps `rvw-pr`'s full posting flow: one reviewer, no contention.
- **Member enforcement is by instruction, and honestly so.** No tool
  restriction that leaves a reviewer functional removes the hazards: reading
  PR content needs `gh`/MCP, so the posting path cannot be tool-stripped, and
  no spawnable `subagent_type` is write-free — the repo's agents declare no
  tool restriction and the built-in read-only types keep `Bash`, which can
  mutate the shared working tree. So the read-only and analyze-only
  constraints are restated in **every** member's prompt, panel and solo
  alike, and the round carries a cheap check: `git status --porcelain` before
  triage — a working tree that moved mid-round means the members did not all
  see the same state, and the round is re-run, not trusted.

Width is a judgement, not a formula: a quiet previous round keeps the next
narrow — a panel of one scoped reviewer is still a round — and a broad diff
or a loud round widens the next.

**Unprimed reviewers — round 1, one member of every odd panel, and the exit
gate's appended pass — are unprimed on purpose.** They receive the diff, the goal, and repo conventions,
never your areas of concern, prior findings, or round history: a reviewer
handed conclusions confirms them, and the second delivery's evidence for what
that costs is in
[ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md).
Use a different model so its blind spots differ from the author's.

Spawn an `Agent` with `model:` set and a prompt instructing it to read and
execute `.claude/skills/rvw-pr/SKILL.md`. Things the prompt must carry,
because the spawn path does not supply them:

- **The PR number.** `rvw-pr/SKILL.md` read as a file still contains a literal
  `$ARGUMENTS`; only slash invocation substitutes it. Without the number the
  agent falls through to that skill's ask-the-user branch, which a subagent
  cannot answer. For an unprimed reviewer, pass the number and nothing else,
  per the unprimed rule; a scoped member's prompt adds its brief.
- **For panel members: the word `analyze-only`.** `rvw-pr` defines the mode:
  Steps 0–3, Step 4 skipped, Step 5's report plus findings returned as the
  final message.
- **The read-only constraint, restated — in every member's prompt.**
  `rvw-pr`'s `allowed-tools` frontmatter grants no `Edit` or `Write`, and that
  guarantee is *lost* when a general agent merely reads the file: it keeps its
  own full tool set, and no spawnable `subagent_type` closes the gap (see the
  panel constraints above). Enforcement is by instruction, which is weaker
  than the frontmatter it stands in for — restate it every time, panel and
  solo alike.

Invoking `/rvw-pr` directly keeps both guarantees and is the right choice
whenever model diversity does not matter; it cannot take a model override.

### Lens menu

Pick one per scoped reviewer, by what the work is and what previous rounds
missed:

- **Neglected surface.** What have prior rounds *not* looked at? Historically the
  highest-yield lens; behavioural bugs hide where review attention has not gone.
- **Fix-pass.** Treat the previous round's corrections as suspect work.
- **Self-contradiction.** Does the PR disagree with its own other additions?
- **Coverage reachability.** What does the gate structurally never execute?
  Docker-gated fixtures, backends with no fixture, `# pragma: no cover`. A green
  gate proves the *covered* code works; it never says what is covered.
- **Consumer.** Docs, guides, and API read from outside.

### Every scoped brief must carry

1. **Areas as areas, not conclusions:** "verify or refute each independently."
2. **What the previous fix pass changed**, so it gets reviewed.
3. **What previous rounds have not examined.**
4. **Explicit permission to find nothing**, or round N manufactures a finding.
   On the closing round, add: weight toward what would be *wrong once merged*,
   away from stylistic refinement.

An unprimed member's brief carries none of this — the PR number only, per the
unprimed rule above.

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
mechanics, and its Rules — a fix pass here owes the finding's class and the
sibling sweep of its own changes exactly as one run under that skill does.
Never start the next round against unpushed code: the reviewer would target
stale lines.

Replies carry the reasoning that does not belong in the diff: what was measured,
what was refuted and why. The PR record is where that survives.

### Stop rule

> **Stop when the most recent round yields zero must-fix findings, that round
> reviewed the most recent fix pass, *and* an unprimed reviewer has seen the
> final state and found nothing must-fix.**

The second and third clauses close the loop's two measured blind spots. **The
loop cannot end on an unreviewed fix pass**: a fix pass is not trusted work —
it is new code written under time pressure by someone who has already been
wrong once in this file. And **it cannot end on a state no unprimed reviewer
has seen**: scoped rounds confirm what they are pointed at, and the defects a
loop creates are created by its fixes, after round 1's unprimed pass has come
and gone. If the would-be closing round had no unprimed member, append one
unprimed pass; like a verification round, it counts toward the ceiling only if
it finds something. A clean unprimed round 1 on a diff warranting no other
lens satisfies all three clauses at once — stopping there is still correct.

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
round, and the second delivery — the one that added the panel structure and
the unprimed exit gate — in
[ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md).
Read both before tuning any of the above: they are the evidence that finding
counts plateau while severity keeps falling, that consecutive rounds each
found defects in the previous round's fixes, and that scoped rounds leave
unnamed surface unexamined.

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
3. Report: rounds run, findings per round with their character, the class swept
   per must-fix finding and the sibling sweep per fix pass — each with what it
   caught — what was filed rather than fixed, and any surface the gate never
   executed.

Then stop. **`/ship` never merges.** It hands over a PR that is ready to be.

## Rules

- Never push to master.
- Never end the loop on an unreviewed fix pass.
- Never end the loop on a state no unprimed reviewer has seen.
- Reviewers are read-only and fresh each round; fixers may decline with evidence.
- Findings that are real but out of scope get filed, not silently dropped.
- If a reviewer and a fixer disagree on fact, **measure**. Neither wins by assertion.
