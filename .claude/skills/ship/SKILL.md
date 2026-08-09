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
panel, from round 3, one of whose members runs the code rather than reading it —
plus a fix pass and a full `hatch run all`, and the two exit gates can append
up to two further reviewer passes at the close — one unprimed, one measuring,
and never the same reviewer. What the
pre-panel shape came to on a large delivery is recorded in
[ADR-0033](../../../sdd/adrs/0033-ship-convergence-driven-review.md); the cost
the panel and exit gate add on top is recorded in
[ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md); and
what the measuring member costs and replaces is in
[ADR-0035](../../../sdd/adrs/0035-vary-method-not-model.md).

Use `/orchestrate` or plain implementation when the change is small, mechanical,
or easily reverted. Use `/ship` when a defect that reaches `master` is costly:
contract or spec changes, cross-backend work, anything touching a published
surface.

## Roles

| Role | Who | Notes |
|---|---|---|
| Orchestrator | main loop | **Never delegated.** It holds the convergence judgement |
| Designer / planner | main loop, plan mode | One role, not two, unless the task is architectural |
| Author | domain-expert subagents where the work is theirs | May decline an instruction **with evidence** |
| Fixer | **main loop by default.** Delegate only for depth inside one file tree | The fixer owns the sibling sweep ([ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md)), and the sweeps that pay are cross-file — a domain-scoped fixer cannot perform them ([ADR-0036](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md)). A delegate still returns the sweep across what it touched |
| Reviewer | fresh subagents — one per panel member | **Never resumed.** A resumed reviewer inherits its own prior conclusions |

## Step 1: Frame

Parse `$ARGUMENTS` for backlog IDs, a task description, or both. No item and no
description: ask.

1. Read the item(s) in `sdd/BACKLOG.md` and every spec/RFC they link.
2. Read [`sdd/CLAUDE-REFERENCE.md` § Ripple-check > Pre-work index](../../../sdd/CLAUDE-REFERENCE.md#pre-work-index); note triggered rows.
3. **Enumerate the subjects** (below).
4. Open or create the trace per [CLAUDE.md § Trace authoring](../../../CLAUDE.md#trace-authoring).
5. Branch: `git checkout -b <id>-<short-name>`.

### Enumerate the subjects, not the files

**Write down every subject the change's own words pick out**, as a list, before
building. A subject is whatever the change claims something about: a backend, a
capability, an operation, a caller. This is a different question from which
files the diff edits, and the gap between the two answers is where defects
survive review — the diff is what you touched, the subject set is what you are
answerable for.

Mark each subject as **executed**, **read only**, or **not reached**, and keep
the list current: it is what sizes panels (below), what a completeness critic
checks, and what the Step 5 report accounts for. A subject that stays
`not reached` to the end is a stated coverage bound, not an oversight — say so
in the report rather than letting silence imply coverage.

The third delivery under this skill was scoped by where a symptom was reported,
and a capable backend the new clause bound by *specification* went unnamed for
six rounds because the diff never touched it. No round asked which subjects the
change's words pick out; nothing in the loop was structured to ask.

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

**The PR body states what changed and why, not what to doubt.** Every
unprimed reviewer — round 1, each odd panel's unprimed member, and the
closing gate's appended pass — reads the body as part of PR content, so
anything you would
flag as risky primes the passes that must not be primed, and the body must
stay doubt-free for the life of the loop, not only at round 1. Doubts belong
in scoped briefs, where priming is the point. The same discipline covers
round history: by the closing gate the PR carries every round's findings and
replies, and the appended pass stays unprimed only because `rvw-pr` Step 1
fetches diff and files, not comments — do not defeat that by restating round
history in the body.

## Step 4: Review loop

The heart of this skill. Each round is: brief → review → triage → fix → gate →
push → reply and resolve.

### Round composition

| Round | Composition |
|---|---|
| 1 | One reviewer: **broad, unprimed** |
| 2 | One reviewer, one scoped lens |
| 3..N | Panel sized by the subject set's reach, the diff's breadth and the prior round's yield, one scoped lens per member. **Odd rounds add one unprimed member; every panel carries one measuring member** |
| Closing gate | Not a round in the sequence: whichever round ends the loop must review the last fix pass **and** satisfy both exit gates — unprimed, and measuring if the PR asserts anything about existing behaviour. Each missing member is supplied by one appended pass; they may be the same round but never the same reviewer (see Stop rule) |

Reviewers are chosen by **lens and method**, never by model and never by domain.
Nothing in this skill pins, prefers, or diversifies an LLM model: the axis was
never measured to pay, and the axis that was — reading versus executing — is the
measuring member below
([ADR-0035](../../../sdd/adrs/0035-vary-method-not-model.md)). A domain persona
is one way to **staff** a lens, never the unit of selection: pick it when the
lens sits inside one domain and its foundation docs help, `general-purpose`
otherwise, which is the normal case for a lens spanning domains or aimed at the
surface no persona owns
([ADR-0036](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md)).

**Panels run in parallel against the same pushed state.** Each member is
fresh and blind to the others: scoped members get briefs per the requirements
below; the unprimed member's prompt carries no content beyond the PR number
and the constraint boilerplate every spawn requires (below) — being unprimed
excludes areas, findings and history, not mode and tool constraints. Two
constraints keep that parallelism sound:

- **Members are analysts, not posters.** Every subagent shares the owner
  token, and GitHub allows one pending review per user per PR — concurrent
  members running `rvw-pr`'s posting step would cross-contaminate a single
  pending review and drop findings while that skill's posting verification
  still reads success. Panel members run `rvw-pr` in its
  **analyze-only mode** (defined in that skill): Steps 0–3, Step 4 skipped,
  Step 5's report — `Subject:` line included, which the Stop rule's
  clean-round check needs — plus consolidated findings returned as the final
  message. The orchestrator merges, dedups (two members reporting one defect
  is one finding), posts the round's findings as one review — **via `rvw-pr`
  Step 4's pending-review flow and its posted-count delta verification**, which
  bind the poster, not just reviewers: the single create-with-`comments:`
  call that flow forbids drops findings silently, and the members who would
  have caught it no longer post — and runs a single triage and fix pass. A
  round with exactly one reviewer — rounds 1 and 2, an **even** round
  narrowed to a single scoped member, or the closing gate's appended pass —
  keeps `rvw-pr`'s full posting flow: one reviewer, no contention. From
  round 3 on, an odd round is never solo; it always carries its unprimed
  member.
- **Member enforcement is by instruction, and honestly so.** No tool
  restriction that leaves a reviewer functional removes the hazards: reading
  PR content needs `gh`/MCP, so the posting path cannot be tool-stripped, and
  no spawnable `subagent_type` is write-free — the repo's agents declare no
  tool restriction and the built-in read-only types keep `Bash`, which can
  mutate the shared working tree. So the read-only and analyze-only
  constraints are restated in **every panel member's** prompt — a solo pass
  needs no restatement because direct `/rvw-pr` invocation carries the
  frontmatter itself — and **every reviewer pass — panel, solo, and the closing
  gate's appended pass** — carries a cheap check: capture `git rev-parse HEAD` when
  the reviewers spawn (the just-pushed, gate-green state — the premise that
  makes the check meaningful), then require an unchanged HEAD **and** a clean
  `git status --porcelain` before triage. Dirtiness or a moved HEAD means the
  reviewers did not see the state being certified, and the pass is re-run,
  not trusted. A tree already dirty at spawn is a failed precondition, not
  tampering — clean it and re-push before spawning, since the check cannot
  tell the two apart. The appended pass is the reviewer whose silence ends
  the loop; it is the last place to skip the check, not the first.

Width is a judgement, not a formula: a quiet previous round keeps the next
narrow — a panel of one scoped member is still a round, though from round 3
on an odd round's unprimed sibling always rides along — and a broad diff, a
loud round, or a subject list with entries still marked `not reached` widens
the next. Width follows the subject set, not the file list: sizing a panel by
the diff's breadth is how a bound subject the diff never touched goes unnamed.

**Unprimed reviewers — round 1, one member of every odd panel, and the exit
gate's appended pass — are unprimed on purpose.** They receive the diff, the
goal, and repo conventions, never your areas of concern, prior findings, or
round history: a reviewer handed conclusions confirms them, and the second
delivery's evidence for what that costs is in
[ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md).
Unprimed-ness is the whole of the mechanism — what differs is what the reviewer
was *not* told, and that is independent of who or what reviews.

**Solo passes invoke [`/rvw-pr`](../rvw-pr/SKILL.md) directly.** That is rounds
1 and 2, an even round narrowed to a single scoped member, and the closing
gate's appended pass. Direct invocation keeps the skill's `allowed-tools`
frontmatter, which withholds `Edit` and `Write` — the guarantee the spawn path
loses and has to restate as an instruction. It is not a read-only guarantee:
that frontmatter grants `Bash`, and this file's own panel-constraints bullet
says why that is not write-free. What covers the `Bash` residue is the
`git rev-parse HEAD` plus `git status --porcelain` check, which is why that
check binds solo passes too.

**Argument order is `<PR number> [mode flags] [brief]`** — `/rvw-pr 954
measuring <brief>`. That skill consumes leading `analyze-only` / `measuring`
tokens as flags and treats only the remainder as reviewer context; without that
parse the mode word would be read as a claim to verify. An unprimed pass gets
the number alone.

**Panels spawn `Agent`s**, because `/rvw-pr` cannot form one. Each member gets a
prompt instructing it to read and execute `.claude/skills/rvw-pr/SKILL.md`.
Things the prompt must carry, because the spawn path does not supply them:

- **The PR number.** `rvw-pr/SKILL.md` read as a file still contains a literal
  `$ARGUMENTS`; only slash invocation substitutes it. Without the number the
  agent falls through to that skill's ask-the-user branch, which a subagent
  cannot answer. An unprimed member's prompt carries the number plus the
  two constraint bullets below and no other content — the unprimed rule
  excludes priming, not constraints; a scoped member's prompt adds its brief.
- **The word `analyze-only`.** `rvw-pr` defines the mode: Steps 0–3, Step 4
  skipped, Step 5's report plus findings returned as the final message.
- **For the measuring member: the word `measuring`.** It opens `rvw-pr`'s
  bounded execution set. Without it that skill permits `Bash` only for `gh`
  PR-content reads and its own Step 4 count, and the member cannot run the
  thing it exists to run. A solo measuring pass carries the word too.
- **The read-only constraint, restated — in every panel member's prompt.**
  `rvw-pr`'s `allowed-tools` frontmatter grants no `Edit` or `Write`, and that
  guarantee is *lost* when a general agent merely reads the file: it keeps its
  own full tool set, and no spawnable `subagent_type` closes the gap (see the
  panel constraints above). Enforcement is by instruction, which is weaker
  than the frontmatter it stands in for — restate it for every member.
  This is the reason solo passes take the direct route instead.

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
- **Tooling and process contract.** The repo's own machinery: gates in
  `scripts/`, skills and personas in `.claude/`, aliases in `pyproject.toml`, CI
  in `.github/`, `infra/`, and the root process docs. **No persona's `DOMAIN:`
  line contains any of it**, so a roster cannot aim at it and a reviewer staffed
  by domain will not look — 9 of PR #954's 12 findings landed here
  ([ADR-0036](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md)). Staff
  this lens with `general-purpose`. Ask what a *reader* of the changed
  instruction would be permitted to do, not whether the instruction reads well:
  the recurring defect is an obligation written without the permission that
  makes it executable.
- **Premise.** Every claim the PR makes about behaviour that already exists —
  in prose, a docstring, a commit message, or a rationale — is executed on the
  base branch and reported as measured or refuted. A reading lens cannot find a
  false premise: it checks the diff against itself, and a false premise is
  consistent with everything in the diff.

### The measuring member

**Every panel carries one member whose brief is to run something, not to read
something.** Its lens may be any of the above, but its instruction is to reach
its verdict by execution: run the code, measure on the base branch, enumerate
the subject set and exercise each entry. It reports what it *ran* and what came
back, and a finding it cannot reproduce is reported as unreproduced.

**Its prompt must carry the word `measuring`.** That word is what opens
`rvw-pr`'s bounded command set — check-only gates, read-only `git`, `python`
against the library — which is otherwise closed: that skill confines `Bash` to
`gh` PR-content reads and its own Step 4 count, and a member spawned without the word can read
the diff and nothing else. The obligation and the permission ship together or
the obligation is inert.

**Measuring does not endanger the clean-tree check above.** Running the gate is
safe; what would break the check is regenerating a baseline or moving the
checked-out revision, and `rvw-pr`'s measuring-pass block forbids both, states
the bound, and carries the measurement behind it. Read it there rather than
here — a second copy of that reasoning is the failure the sibling-sweep rule
exists to catch.

This is the axis that separated the productive rounds in the third delivery.
Three premises there were asserted and disproved, every one by running
something; the rounds that read the diff for internal consistency found stale
summaries and mis-scoped marks, and never a false premise. Reviewers who differ
only in *who* they are share a method, and a shared method has shared blind
spots no amount of further diversity along that axis reaches.

**The measuring member is always a scoped member, never the unprimed one.** A
measuring brief names what to run and against which revision, and that is a
brief; handing it to the unprimed member would prime it. On a two-member odd
panel the scoped member is the measuring one.

The obligation is a floor, not a cap: a solo round may be a measuring round, and
on a diff whose whole risk is a behavioural claim it should be.

### Every scoped brief must carry

1. **Areas as areas, not conclusions:** "verify or refute each independently."
2. **What the previous fix pass changed**, so it gets reviewed.
3. **What previous rounds have not examined.**
4. **Whether the verdict is to be reached by reading or by running**, and for a
   measuring member, what to run and against which revision.
5. **Explicit permission to find nothing**, or round N manufactures a finding.
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

`hatch run all` green → commit → push → **check CI** → reply to **every** thread
and resolve it. Use [`/fix-pr`](../fix-pr/SKILL.md)'s comment-fetch and
thread-resolve mechanics, and its Rules — a fix pass here owes the finding's
class and the sibling sweep of its own changes exactly as one run under that
skill does. Never start the next round against unpushed code: the reviewer would
target stale lines.

**The local gate does not stand in for CI, and cannot.** `hatch run all` is a
Stage-1, no-Docker variant on one interpreter; the CI matrix runs Docker-gated
lanes and interpreters the local gate never touches, so a whole class of failure
is invisible to it by construction rather than by accident. Read the PR's checks
after each push (`gh pr checks <N>`, or `pull_request_read` with
`get_check_runs`). **A red check is a finding for the next round** and gets
triaged like any other; a still-running matrix is not a green one, so a round
does not close on a pending check without saying so. In the third delivery CI
went red on a rebase and stayed red across four commits and four review rounds,
because every round's gate was the local one and the failure was interpreter-
specific. The user noticed. Nothing in the loop was looking.

Replies carry the reasoning that does not belong in the diff: what was measured,
what was refuted and why. The PR record is where that survives.

### Stop rule

> **Stop when the most recent round yields zero must-fix findings, that round
> reviewed the most recent fix pass, an unprimed reviewer has seen the
> final state and found nothing must-fix, *and* every behavioural claim the PR
> makes has been executed by a measuring pass.**

The second, third and fourth clauses close the loop's measured blind spots.
**The loop cannot end on an unreviewed fix pass**: a fix pass is not trusted
work — it is new code written under time pressure by someone who has already
been wrong once in this file. **It cannot end on a state no unprimed reviewer
has seen**: scoped rounds confirm what they are pointed at, and the defects a
loop creates are created by its fixes, after round 1's unprimed pass has come
and gone. If the would-be closing round had no unprimed member, append one
unprimed pass; like a verification round, it counts toward the ceiling only if
it finds something.

**And it cannot end on a behavioural claim nobody ran.** The measuring member
is a panel obligation, and panels start at round 3 — so without this clause a
one- or two-round delivery ships with zero execution-based review while the
Rules below assert a premise was executed. Same structure as the unprimed
gate, for the same reason: an obligation that only fires mid-loop proves
nothing about what ships. If the closing round had no measuring pass and the
PR asserts anything about existing behaviour, append one, on the same terms as
the unprimed pass. A PR that makes no such claim satisfies the clause
vacuously, exactly as a round that fixed nothing satisfies the fix-pass clause.

A clean unprimed round 1 on a diff warranting no other lens still satisfies all
four **provided the diff asserts nothing about existing behaviour** — stopping
there is still correct. It cannot satisfy the fourth clause any other way: an
unprimed pass gets the PR number alone, so it never carries the `measuring`
token and never reaches a measuring brief, by the two rules above. A one-round
delivery that *does* assert something therefore closes on the appended
measuring pass, never on round 1 itself.

- **Floor: lens coverage, not a round count.** Every lens the diff *warrants*
  must have been applied. A one-surface change may warrant only the broad round,
  and then a clean round 1 ends the loop; stopping there is correct. A diff that
  adds code the gate never executes, spreads a claim across artifacts that can
  disagree, or changes a published surface warrants those lenses, and round 1 by
  construction did not apply them: a clean sweep is silent about questions
  nobody asked.
- **Ceiling: 5 finding-rounds, and it is soft.** On reaching it, escalate to the
  user **with the evidence, not the count**: findings per round with their
  character, the severity trend across rounds, what the last round found, and
  which subjects are still `not reached`. The count is what triggers the
  escalation; it is not what the decision is made on, and a bare "five rounds
  elapsed, continue?" hands the user the one number the loop already knows is a
  poor termination signal. Both escalations in the third delivery found more than
  the round before them, and the round that found that run's most severe finding
  was past the ceiling. Do not terminate silently. A verification round
  over an otherwise unreviewed fix pass does not count *if it finds nothing*; a
  verification round that finds something is a finding-round like any other, and
  its own fix pass still owes a verification. Without that, the
  verify-fix-verify tail is exempt from the bound it exists under.
- **Judge severity, not count.** Counts plateau while severity falls.
- **A round that fixed nothing leaves nothing unreviewed.** The fix-pass clause
  is satisfied vacuously, so a clean round needs no successor to verify it.

**Check a clean round before trusting it.** `/rvw-pr` makes every reviewer
state the PR's subject in its own words precisely so this is cheap — a solo
reviewer posts it, a panel member returns it in its analyze-only report.
Check **every** member's line: a panel's clean verdict is the conjunction of
its members' silences, so one mismatched line makes that member's silence
worthless and the clean unvalidated. The remedy is member-scoped — re-spawn
the mis-aimed member, keep the valid passes; a solo round is re-run whole. Do
not count an unvalidated clean.

The delivery this rule was derived from is tabulated in
[ADR-0033](../../../sdd/adrs/0033-ship-convergence-driven-review.md), round by
round; the second delivery — the one that added the panel structure and
the unprimed exit gate — in
[ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md); and
the third — which dropped the model axis and added the measuring member — in
[ADR-0035](../../../sdd/adrs/0035-vary-method-not-model.md).
Read all three before tuning any of the above: they are the evidence that finding
counts plateau while severity keeps falling, that consecutive rounds each
found defects in the previous round's fixes, that scoped rounds leave
unnamed surface unexamined, and that what separated the productive rounds was
method rather than reviewer identity.

**Repeat-site check:** if two consecutive rounds refute **the same condition** —
a gate, a predicate, a carve-out, a scope criterion — stop arguing the condition
and **enumerate its space**. Each narrowing is argued from a reading of what the
hazard is, and each is refuted by a state the argument did not consider; a third
reading is not more likely to be exhaustive than the first two. Identify the
condition's axes, parametrise them, and generate the product as a test. Nothing
else in the loop escalates from "argue the condition again" to "enumerate the
space", and the rounds themselves cannot: each is correct about the defect in
front of it.

This fires on repetition of a *site*, where the Divergence check below fires on
*severity*, so neither substitutes for the other. In the third delivery one gate
was narrowed across rounds 5, 6 and 7 and withdrawn at the last; its condition
space was four booleans, enumerable in one test the whole time.

If the enumeration shows the condition cannot be stated without being circular
or false — three criteria, three refutations — that is the answer. Drop the
carve-out and make the subject comply, which is cheaper than a fourth attempt at
justifying its absence.

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
   per must-fix finding and the sibling sweep per fix — each with what it
   caught — what was filed rather than fixed, any surface the gate never
   executed, the **final state of the Step 1 subject list** with each entry
   marked executed / read only / not reached, and **CI's verdict on the final
   push**.

Then stop. **`/ship` never merges.** It hands over a PR that is ready to be.

## Rules

- Never push to master.
- Never end the loop on an unreviewed fix pass.
- Never end the loop on a state no unprimed reviewer has seen.
- Never end the loop on a behavioural claim no measuring pass has executed.
- Never end the loop on a red or unread CI.
- Reviewers are read-only and fresh each round; fixers may decline with evidence.
- Reviewers are picked by lens and method. **Never pin or prefer a model, and
  never by domain** — a persona staffs a lens, it does not select one.
- Every panel carries a member that runs something.
- The main loop fixes and owns the sweep; delegate a fix only for depth inside
  one file tree.
- Findings that are real but out of scope get filed, not silently dropped.
- If a reviewer and a fixer disagree on fact, **measure**. Neither wins by assertion.
- A premise about existing behaviour is executed before it ships, not read.
- A verification step that can fail silently is worse than none, because it is
  trusted. Fix the instrument or delete it.
