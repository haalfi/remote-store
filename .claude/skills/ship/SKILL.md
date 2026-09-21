---
name: ship
description: Deliver a task as one merge-ready PR. Plan, build, then review to convergence
disable-model-invocation: true
argument-hint: "[BACKLOG-ID ...] or [task description]"
---

Take a task from framing to a PR that is ready to merge, in one invocation. The
deliverable is **one PR whose review has converged**, not a PR reviewed a fixed
number of times.

Composes rather than reimplements: [`/pr`](../pr/SKILL.md) creates the PR,
[`/rvw-pr`](../rvw-pr/SKILL.md) is the reviewer's instruction set,
[`/fix-pr`](../fix-pr/SKILL.md) owns comment-fetch and thread-resolve mechanics.
[`/orchestrate`](../orchestrate/SKILL.md) is the choice when you want a capped,
consolidate-and-decide review instead of an open-ended loop.

## When not to use this

The loop is the dominant cost: each round is one or more reviewer passes — from
round 3 a panel, one of whose members runs the code rather than reading it — plus
a fix pass and a full `hatch run all`, and the close can append up to three more
passes (unprimed, whole-file, measuring), never the same reviewer twice. Costs
are recorded per delivery in
[ADR-0033](../../../sdd/adrs/0033-ship-convergence-driven-review.md) (pre-panel
shape), [ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md)
(panel and exit gate), [ADR-0035](../../../sdd/adrs/0035-vary-method-not-model.md)
(measuring member) and
[ADR-0037 § Consequences](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md#consequences)
(third gate).

Use `/orchestrate` or plain implementation when the change is small, mechanical,
or easily reverted. Use `/ship` when a defect reaching `master` is costly:
contract or spec changes, cross-backend work, anything touching a published
surface.

## Roles

| Role | Who | Notes |
|---|---|---|
| Orchestrator | main loop | **Never delegated.** It holds the convergence judgement |
| Designer / planner | main loop, plan mode | One role, not two, unless the task is architectural |
| Author | domain-expert subagents where the work is theirs | May decline an instruction **with evidence** |
| Fixer | **main loop by default.** Delegate only for depth inside one file tree | The fixer owns the sibling sweep ([ADR-0034 § Decision](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md#decision)), and the sweeps that pay are cross-file — a domain-scoped fixer cannot perform them ([ADR-0036 § Decision](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md#decision)). A delegate still returns the sweep across what it touched |
| Reviewer | fresh subagents — one per panel member | **Never resumed.** A resumed reviewer inherits its own prior conclusions |

## Step 1: Frame

Parse `$ARGUMENTS` for backlog IDs, a task description, or both. Neither: ask.

1. Read the item(s) in `sdd/BACKLOG.md` and every spec/RFC they link.
2. Read [`sdd/CLAUDE-REFERENCE.md` § Ripple-check > Pre-work index](../../../sdd/CLAUDE-REFERENCE.md#pre-work-index); note triggered rows.
3. **Enumerate the subjects** (below).
4. Open or create the trace per [CLAUDE.md § Trace authoring](../../../CLAUDE.md#trace-authoring).
5. Branch: `git checkout -b <id>-<short-name>`.

### Enumerate the subjects, not the files

**Write down every subject the change's own words pick out**, before building. A
subject is whatever the change claims something about — not a fixed vocabulary. A
backend, a capability, an operation, a caller, a gate, a skill: illustrations, not
a menu, and the next change will name something none of them cover. Ask what the
words pick out, not which of a list they match. This is a different question from
which files the diff edits, and the gap between the two answers is where defects
survive review — the diff is what you touched, the subject set is what you are
answerable for.

Mark each subject **executed**, **read only**, or **not reached**, and keep the
list current: it sizes panels, it is what a completeness critic checks, and the
Step 5 report accounts for it. A subject still `not reached` at the end is a
stated coverage bound, not an oversight — say so rather than letting silence
imply coverage.

The third delivery was scoped by where a symptom was reported, and a capable
backend the new clause bound by *specification* went unnamed for six rounds
because the diff never touched it. No round asked which subjects the change's
words pick out; nothing in the loop was structured to ask.

## Step 2: Design (plan mode)

Enter plan mode. Produce a plan naming files, signatures, spec IDs, and Step 1's
ripple targets. Use `AskUserQuestion` for decisions the item leaves open, with a
recommendation per question. Exit via `ExitPlanMode` for approval. Do not build
before the plan is approved.

## Step 3: Build and open the PR

Implement, delegating to domain experts where the work is theirs. Then
`hatch run all` green; commit with the item ID prefix and push; run
[`/pr`](../pr/SKILL.md), which owns the validation gates, the trace gate and the
template.

**The PR body states what changed and why, not what to doubt.** Every unprimed
reviewer — round 1, each odd panel's unprimed member, the closing gate's unprimed
pass — reads the body as PR content, so anything you flag as risky primes the
passes that must not be primed, and the body must stay doubt-free for the life of
the loop, not only at round 1. Doubts belong in scoped briefs, where priming is
the point. Same for round history: by the closing gate the PR carries every
round's findings, and the appended pass stays unprimed only because `rvw-pr`
Step 1 fetches diff and files, not comments — do not defeat that by restating
round history in the body.

## Step 4: Review loop

The heart of this skill. Each round is: worktree at the pushed commit → brief →
review → triage, with a fix shape per must-fix finding → fix in the main tree →
gate → push → reply and resolve → worktree removed.

### Round composition

| Round | Composition |
|---|---|
| 1 | One reviewer: **broad, unprimed** |
| 2 | One reviewer, one scoped lens |
| 3..N | Panel sized by the subject set's reach, the diff's breadth and the prior round's yield, one scoped lens per member. **Odd rounds add one unprimed member; every panel carries one measuring member** |
| Closing gate | Not a round in the sequence: whichever round ends the loop must review the last fix pass **and** satisfy all three exit gates — unprimed, whole-file, and measuring if the PR asserts anything about existing behaviour. Each missing member is supplied by one appended pass; they may be the same round but **never the same reviewer** — reviewers are fresh per pass (Roles) and none is ever resumed |

Reviewers are chosen by **lens and method**, never by model and never by domain.
Nothing here pins, prefers or diversifies an LLM model: that axis was never
measured to pay, and the axis that was — reading versus executing — is the
measuring member below
([ADR-0035 § Decision](../../../sdd/adrs/0035-vary-method-not-model.md#decision)).
A domain persona **staffs** a lens, it never selects one: pick it when the lens
sits inside one domain and its foundation docs help, `general-purpose` otherwise,
which is the normal case for a lens spanning domains or aimed at the surface no
persona owns
([ADR-0036 § Decision](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md#decision)).

Width is a judgement, not a formula: a quiet round keeps the next narrow — a panel
of one scoped member is still a round, though from round 3 an odd round's
unprimed sibling always rides along — and a broad diff, a loud round, or subjects
still `not reached` widen it. Width follows the subject set, not the file list:
sizing a panel by the diff's breadth is how a bound subject the diff never touched
goes unnamed.

<a id="reviewer-permissions"></a>
### Reviewer permissions and the tree check

**This block is the single home for what a reviewer may do and how that is
enforced.** Everything below cites it rather than restating it; a second copy of
this reasoning is the failure the sibling-sweep rule exists to catch.

- **What `/rvw-pr`'s `allowed-tools` frontmatter gives.** No `Edit`, no `Write`,
  no agent-spawning tool. It does grant `Bash`, so it is **not** a read-only
  guarantee.
- **The spawn path loses it.** A general `Agent` told to read
  `rvw-pr/SKILL.md` keeps its own full tool set, and no spawnable
  `subagent_type` closes the gap — the repo's agents declare no tool restriction
  and the built-in read-only types keep `Bash`, which can mutate the review
  worktree the round's passes share. So panel members get the read-only and
  analyze-only constraints **restated in every prompt**. Enforcement by
  instruction is weaker than the frontmatter it stands in for, and that is the
  reason solo passes take the direct route instead.
- **No reviewer reads the working tree the fixer edits.** After each push the
  orchestrator adds a worktree at the pushed commit, and every pass of that
  round — panel member, solo pass, each of the closing gate's appended passes —
  is told that its repository root is that path:

  ```bash
  git worktree add tmp/review/<sha> <sha>
  ```

  Whole-file reads come from it and a measuring member runs the gates in it;
  `hatch run` creates the worktree's own environment on first use, once per
  worktree and so once per round, not per pass (25.6 s, measured once,
  [RFC-0015 D3](../../../sdd/rfcs/rfc-0015-ship-two-surfaces.md)). A solo pass
  gets the root as `/rvw-pr`'s `root=` flag; a panel member gets it in its
  prompt (Running a round). What is certified is the pushed commit `<sha>`:
  the files come from the worktree and the diff is pinned to it too
  (`/rvw-pr` Step 1's root form), so nothing a reviewer reads can come from
  the main tree. The round order is unchanged — the fix pass follows triage —
  so this is not a licence to fix while reviewers run; it means the main tree
  is no longer load-bearing for the certification, and an edit there
  mid-round, PR #996's failure 4, which the old check could only detect after
  the fact, no longer dirties anything a reviewer sees.
- **The check that covers the residue, and it binds every pass** — panel, solo,
  and each of the closing gate's appended passes. It runs in the worktree,
  where it catches a reviewer that wrote there, with one capture kept in the
  main tree (below). Capture
  `git -C tmp/review/<sha> rev-parse HEAD` when reviewers spawn (the
  just-pushed, gate-green state, which is the premise that makes the check
  meaningful), then require an unchanged HEAD **and** a clean
  `git -C tmp/review/<sha> status --porcelain` before triage. Dirtiness or a
  moved HEAD means the reviewers did not see the state being certified: re-run
  the pass, do not trust it. The worktree's HEAD is detached and cannot move on
  its own, so the other thing the old check caught — the branch advancing under
  a certifying reviewer — needs its own capture: at triage, `git fetch origin
  <branch>` and require `git rev-parse origin/<branch>` still equal to `<sha>`.
  A push during the round means the passes certified a superseded commit;
  re-run them against the new one. And keep one capture in the main tree:
  `git status --porcelain` at spawn, required unchanged before triage. An
  `Agent`'s Bash runs in the main tree on every call (measured, `/rvw-pr`
  § Review root), so a member that drops the `-C` / `env -C` prefix and runs a
  writing alias dirties the tree the next fix pass commits from while the
  worktree check stays green. The main tree is idle during the round, since
  the fix pass follows triage, so *unchanged* is the test there, not *clean*.
  An appended pass is a reviewer whose silence ends the loop; it is the last
  place to skip this, not the first.
- **The worktree is removed at round close**: `git worktree remove
  tmp/review/<sha>`, then `git worktree prune` for the base worktree a
  measuring member may have left nested inside it. Measured on git 2.43.0:
  ignored leftovers (`.coverage`, a nested `tmp/base`) do not block the
  removal, and the nested entry becomes prunable; a non-ignored untracked file
  does block it, and that is the dirtiness the tree check above already
  refused to certify. A leftover from an earlier round collides with nothing,
  since the path carries its commit, but a pass re-spawned for the same commit
  fails its `worktree add` on the existing path and every leftover carries a
  hatch environment: remove before adding, and treat a leftover as hygiene, not
  as a wrong-commit hazard.

### Running a round: panels and solo passes

Rounds 1 and 2 are always solo, so a reader who has not yet reached a panel needs
this section too — the solo mechanism, the solo-round posting rule and the
argument order that binds both paths are all below.

**Panels run in parallel against the round's review worktree.** Each member is
fresh and blind to the others: scoped members get briefs; the unprimed member's
prompt carries only the PR number, the worktree root and the constraint
boilerplate — being unprimed excludes areas, findings and history, not mode,
root and tool constraints.

**Members are analysts, not posters.** Every subagent shares the owner token and
GitHub allows one pending review per user per PR, so concurrent members running
`rvw-pr`'s posting step would cross-contaminate one pending review and drop
findings while that skill's verification still reads success. Panel members run
`rvw-pr` in **analyze-only mode**: Steps 0–3, Step 4 skipped, Step 5's report —
`Subject:` line included, which the Stop rule's clean-round check needs — plus
consolidated findings as the final message. The orchestrator merges, dedups (two
members reporting one defect is one finding), posts the round as one review
**via `rvw-pr` Step 4's pending-review flow and its posted-count delta
verification** — those bind the poster, not only reviewers: the single
create-with-`comments:` call that flow forbids drops findings silently, and the
members who would have caught it no longer post — then runs one triage and fix
pass.

**A round with exactly one reviewer keeps `rvw-pr`'s full posting flow**: rounds
1 and 2, an even round narrowed to a single scoped member, or a close appending
exactly one pass. One reviewer, no contention. From round 3 an odd round is never
solo; it always carries its unprimed member. **A close appending two or three
passes takes the panel path** — analyze-only members, orchestrator posts —
because the contention does not care that passes are appended rather than
scheduled. Serial solo passes are the alternative, and their cost is not priming
(`rvw-pr` Step 1 never fetches comments, so a later pass cannot see an earlier
one's findings however they run) but that **each pass certifies a different
moment**: fix anything between them and the earlier passes attested to a state
that no longer exists, so the gates they discharged are undischarged.

**Solo passes invoke [`/rvw-pr`](../rvw-pr/SKILL.md) directly**, which keeps the
frontmatter instead of restating it as an instruction — see
[Reviewer permissions](#reviewer-permissions) for what that is worth and why the
tree check still binds.

**Argument order is `<PR number> [mode flags] [root=<path>] [brief]`** —
`/rvw-pr 954 measuring root=tmp/review/<sha> <brief>`. That skill consumes
leading `analyze-only` / `measuring` tokens and a `root=` token as flags and
treats only the remainder as reviewer context; without that parse the mode word
would be read as a claim to verify. An unprimed pass gets the number and the
root alone.

**Panels spawn `Agent`s**, because `/rvw-pr` cannot form one. Each prompt
instructs the member to read and execute `.claude/skills/rvw-pr/SKILL.md`, and
must carry what the spawn path does not supply:

- **The PR number.** Read as a file, `rvw-pr/SKILL.md` still contains a literal
  `$ARGUMENTS`; only slash invocation substitutes it. Without the number the
  agent falls through to that skill's ask-the-user branch, which a subagent
  cannot answer.
- **The worktree root**, as `root=tmp/review/<sha>`. Without it the member
  reads the main tree, which is the tree the fixer edits and the one thing the
  round must not certify ([Reviewer permissions](#reviewer-permissions)).
- **The word `analyze-only`**, which selects the mode above.
- **For the measuring member, the word `measuring`**, which opens `rvw-pr`'s
  bounded execution set. Without it that skill permits `Bash` only for its
  content reads (`gh`, and the pinned diff under a root) and its own Step 4
  count, and the member cannot run the thing it exists to run. A solo measuring pass carries the word too.
- **The read-only constraint, restated**, per
  [Reviewer permissions](#reviewer-permissions).

**Unprimed reviewers — round 1, one member of every odd panel, and the closing
gate's *unprimed* appended pass — are unprimed on purpose.** They receive the
diff, the goal and repo conventions, never your areas of concern, prior findings
or round history: a reviewer handed conclusions confirms them, and the second
delivery's evidence for the cost is in
[ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md).
Unprimed-ness is the whole of the mechanism — what differs is what the reviewer
was *not* told, independent of who or what reviews.

**Only that one pass.** The close can append three, and the other two are
*scoped*: a whole-file brief and a measuring brief are briefs, so **every scoped
member — measuring, whole-file, reader — is never the unprimed one.** Handing an
appended whole-file or measuring pass the PR number and root alone leaves it never told
what it was appended to do, and the gate is discharged by a pass that could not
have satisfied it — the same inert-obligation failure this file warns about for
the `measuring` token, one gate later.

<a id="lens-menu"></a>
### Lens menu

Pick one per scoped reviewer, by what the work is and what previous rounds
missed. [`/orchestrate`](../orchestrate/SKILL.md#reviewer-selection) takes this
menu by link rather than copying it.

- **Neglected surface.** What have prior rounds *not* looked at? Historically the
  highest-yield lens; behavioural bugs hide where review attention has not gone.
- **Fix-pass.** Treat the previous round's corrections as suspect work.
- **Self-contradiction.** Does the PR disagree with its own other additions?
- **Coverage reachability.** What does the gate structurally never execute?
  Docker-gated fixtures, backends with no fixture, `# pragma: no cover`. A green
  gate proves the *covered* code works; it never says what is covered.
- **Consumer.** Docs, guides, and API read from outside.
- **Reader.** Can someone who was not in this conversation answer the questions
  the changed documentation exists to answer? **The method is not stated here.**
  Its one normative home is the `READER TEST` block in
  [`.claude/agents/documentation-expert.md`](../../agents/documentation-expert.md);
  a brief cites that block rather than paraphrasing it, because a paraphrase is a
  second description that drifts
  ([`DRIFT-RULES.md` Rules 1 and 4](../../../sdd/DRIFT-RULES.md#one-driver)).
  **What belongs here is only what is true of this lens and not of that block** —
  that bound governs what this section may *contain*, where the clause above
  governs what a *brief* may do, and it is what stops a later editor growing this
  lens back into a second copy of the block.
  **The verdict is the reader's failure, not the reviewer's opinion** — that is
  what separates this from Consumer above, which judges docs from outside. The
  defect it reaches is a page that is accurate, correctly placed and
  CONTENT-RULES-clean and still leaves a reader unable to act, which no lens
  judging correctness can see.
  **Assume the self-administered form and brief for it.** The block's step 2
  spawns a fresh reader; assume no member can — no reviewer here has an
  agent-spawning tool ([Reviewer permissions](#reviewer-permissions)), and
  nesting from a panel member, or from an `/orchestrate` reviewer that is a plain
  subagent with a full tool set, is not established either. So brief the member
  to self-administer and **label it as such**,
  which the block already requires; never to attempt the spawn and report what it
  could not do. A brief citing the spawn step is this file's inert-obligation
  failure in its own newest lens.
  **Two bounds, and the second is sharper.** Priming: the member has read the
  change under review, so it is weaker than a reader who has not — here the diff
  and PR body, under `/orchestrate` the authoring output in the working tree;
  same bound, same reason, only what was read differs. Administration: it cannot
  run the test on anyone, only on itself, against a page it has already read.
  **That binds both skills for one reason** — no host in this repo guarantees a
  spawned no-context reader. **So there is no escape hatch to route to**: the
  persona is where a spawn would be *attempted*, and its own block says to assume
  the fallback. If a guaranteed spawned reader is ever wanted, it has to be
  built. This lens is the prospective half of a signal the repo otherwise
  collects only after the fact, as trace `outcome: unclear` tags aggregated by
  `hatch run report-trace-outcomes`.
- **Tooling and process contract.** The repo's own machinery — **everything no
  `DOMAIN:` line contains**. Derive it by checking a path against the five lines
  rather than against a list: `/orchestrate`'s
  [Nobody's domain](../orchestrate/SKILL.md#nobodys-domain) is the single home for
  that reasoning and for why no enumeration is given, and this lens covers the
  same set. It is wider than it looks — `benchmarks/` and `FEATURES.md` both fall
  in it and both read as some persona's work. **No persona's `DOMAIN:` line
  contains any of it**, so a roster cannot aim at it and a reviewer staffed by
  domain will not look — 9 of PR #954's 12 findings landed here
  ([ADR-0036 § Context](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md#context)).
  Staff it with `general-purpose`. Ask what a *reader* of the changed instruction
  would be permitted to do, not whether it reads well: the recurring defect is an
  obligation written without the permission that makes it executable.
- **Premise.** Every claim the PR makes about behaviour that already exists — in
  prose, a docstring, a commit message, a rationale — is executed on the base
  branch and reported as measured or refuted. A reading lens cannot find a false
  premise: it checks the diff against itself, and a false premise is consistent
  with everything in the diff.

### The measuring member

**Every panel carries one member whose brief is to run something, not read
something.** Its lens may be any above, but it reaches its verdict by execution:
run the code, measure on the base branch, exercise each entry in the subject set.
It reports what it *ran* and what came back, and a finding it cannot reproduce is
reported as unreproduced.

**Its prompt must carry the word `measuring`**, which opens `rvw-pr`'s bounded
command set — check-only gates, read-only `git`, `python` against the library.
Without it the member can read the diff and nothing else. The obligation and the
permission ship together or the obligation is inert. It runs that set in the
round's review worktree, and measures the base branch in a `tmp/base` worktree
under that root.

**Measuring does not endanger the tree check.** Running the gate is safe; what
would break it is regenerating a baseline or moving the checked-out revision, and
`rvw-pr`'s measuring-pass block forbids both, states the bound, and carries the
measurement behind it. Read it there.

This is the axis that separated the productive rounds in the third delivery.
Three premises there were asserted and disproved, every one by running something;
the rounds that read the diff for internal consistency found stale summaries and
mis-scoped marks, and never a false premise. Reviewers differing only in *who*
they are share a method, and a shared method has shared blind spots no further
diversity along that axis reaches.

The obligation is a floor, not a cap: a solo round may be a measuring round, and
on a diff whose whole risk is a behavioural claim it should be. On a two-member
odd panel the scoped member is the measuring one.

### The whole-file member

**Its subject is each changed file's current state; the diff is context, not the
thing under review.** The other method axis, and the third exit gate
([ADR-0037 § Decision](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md#decision)).
Every reviewer already reads the changed files in full — `rvw-pr` Step 1 requires
it — so what this brief changes is not *what is read* but *what is judged*: the
file as it now stands has to be true, whether or not the untrue part sits in a
hunk.

That is where a whole class of defect lives and diff-anchored rounds do not reach
it. The shapes measured on PR #956, all siblings of an earlier fix and all
invisible in a hunk: frontmatter falsified by the change it describes; an
antecedent broken by a paragraph inserted above it; a premise true for one of a
section's two callers; a cardinality claim disagreeing with a different file. Ask
of each file: does its opening still describe what it now does, does every "the X
above" still have its referent, and is each claim it makes about another file
still true of that file?

**A finding here is postable — do not drop it for want of a hunk.** `rvw-pr`
Step 4's first Comment rule anchors it to its true line when that line sits
inside a hunk, context lines included, which is what lets RFC-0015 D5's origin
tag classify it; only a finding whose line no hunk reaches, or whose subject is
the file itself, goes as `subjectType: "FILE"` with no `line`.

It is not the measuring member either: a whole-file pass reads, and cannot see a
false premise about behaviour that exists only on the base branch. The two gates
are not substitutes.

### Every scoped brief must carry

1. **Areas as areas, not conclusions:** "verify or refute each independently."
2. **What the previous fix pass changed**, so it gets reviewed.
3. **What previous rounds have not examined** — computed, not recalled:

   ```bash
   hatch run ship-report <N> --out tmp/ship-report-<N>.md
   ```

   Quote its **Per-file distribution** section into the brief — the *named
   untouched files*, not the adjective "neglected". The alternative is an
   impression: on PR #956 the loop ran four rounds with 16 of its 24 findings on
   one file and 8 of 12 files carrying none, and nobody knew until an ad-hoc
   query while a brief was being written. The round that query redistributed put
   three of its four findings on two of those eight files
   ([ADR-0037 § Context](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md#context)).

   This replaces a two-call `gh api` recipe that each round ran by hand. Three
   shaping decisions in it each fixed a measured regression — findings are rows
   with no `in_reply_to_id`, *both* endpoints are paged, and untouched is the
   changed-file list minus the **union** across every page, never minus page
   one's. They now live in `scripts/ship_report.py`'s docstring, beside the code
   that implements them, which is where a reason belongs once it stops being a
   rule someone has to remember ([RFC-0015](../../../sdd/rfcs/rfc-0015-ship-two-surfaces.md) D4).
   The orchestrator no longer re-derives them, and cannot get them subtly wrong.

   **`tmp/` is gitignored, and nothing durable holds this until the close.**
   That is RFC-0015 Open Question 5's answer: a PR comment would prime nobody,
   because reviewers never fetch comments, and the durable copy is the trace's
   `review:` block written once the loop ends.

   **Running it is the orchestrator's job, done while writing the brief. Put the
   *result* in the brief; never the command.** It reads PR *comments*, and
   `/rvw-pr` Step 1 forbids a reviewer from fetching those — that prohibition is
   the whole mechanism keeping unprimed passes unprimed, so a brief asking a
   member to run `ship-report` turns that member into one that has read the
   conversation.

   **No reviewer runs `ship-report`, including a measuring member**, and that is
   a narrowing from what the two-call recipe allowed. Two independent reasons,
   either sufficient: `hatch run ship-report` is not on `/rvw-pr`'s by-name
   measuring allowlist, which is an enumeration and not a pattern; and the
   script reads comment **bodies**, where that skill's metadata carve-out is
   bounded to paths, review ids and counts — so a member running it would have
   read the conversation, which is the one thing the unprimed discipline cannot
   survive. Its behavioural claims are pinned by its guards under
   `tests/scripts/`, which every `hatch run all` executes, so nothing is
   unverified by the narrowing; what is lost is a reviewer re-deriving the
   figures independently, and that is RFC-0015 D6's deferred half to solve
   (BK-382), not a gap to paper over by widening a permission.

4. **Whether the verdict is reached by reading the diff, by reading each changed
   file whole, or by running**, and for a measuring member, what to run and
   against which revision.
5. **Explicit permission to find nothing**, or round N manufactures a finding. On
   the closing round add: weight toward what would be *wrong once merged*, away
   from stylistic refinement.

An unprimed member's brief carries none of this — the PR number and the
worktree root only.

### Triage each finding

| Verdict | Action | Fix shape |
|---|---|---|
| Must-fix | Wrong once merged: bad behaviour, a false statement in a durable artifact, a shipping gap. Fix in this PR. | Exactly one of shapes (1) to (4) below, named in the reply |
| File-it | Real, but outside this PR's scope. Backlog item, cited in the reply. | Shape (5) |
| Refute | Wrong or already handled. Reply with the evidence; do not fix. | — |
| Preference | A `Consistency:` finding on prose that cites no rule and arrived without the six lines. Reply *preference, six lines absent*; no backlog item; never fixed in-loop. A finding citing a `CONTENT-RULES` or `DRIFT-RULES` rule is a violation and is triaged as a Must-fix. | — |

**A fix removes, measures, narrows or enumerates; it never argues.** A finding
is closed by exactly one of: **(1)** a behaviour change pinned by a test seen
failing first; **(2)** deleting the false claim; **(3)** replacing the claim
with its derivation — a command, a test name or an enumeration; **(4)** narrowing
the claim to what was measured; **(5)** filing, which is the File-it verdict. A
Must-fix takes (1) to (4), as the table says. *Write a rationale* is not a
shape. The fix-shape column is required, and the
fix pass owes what [`/fix-pr`](../fix-pr/SKILL.md) Step 3 lists under each
shape: a reviewer's *why* answered by shape (3) or the no-reason sentence, a
test added in a fix pass mutation-checked before push, a reviewer's figure
re-derived rather than carried, a measured claim bounded by its instrument, and
a `Consistency:` finding on prose that cites no rule and lacks the six-line
form triaged *Preference*, the fourth row above (a false statement in prose is
a `Bug:` or `Spec:` finding, a rule violation is a Must-fix, and neither needs
the six lines). The evidence is
[RFC-0015 D2](../../../sdd/rfcs/rfc-0015-ship-two-surfaces.md): every one of the
four failures it maps was the fixer writing something it had not run, and the
measuring member catching it one round later.

Refuting is a first-class outcome. Reviewers are wrong often enough that
accepting every finding degrades the work, so verify before fixing.

### Close each round

`hatch run all` green → commit → push → **check CI** → reply to **every** thread
and resolve it → remove the round's review worktree. Use
[`/fix-pr`](../fix-pr/SKILL.md)'s comment-fetch and thread-resolve mechanics and
its Rules — a fix pass here owes the finding's class, the sibling sweep of its own
changes, the fix shape per must-fix reply and the mutation per added test exactly
as one run under that skill does. Never start the next round against unpushed
code: the reviewer would target stale lines.

**The local gate does not stand in for CI, and cannot.** `hatch run all` is a
Stage-1, no-Docker variant on one interpreter; the CI matrix runs Docker-gated
lanes and interpreters it never touches, so a whole class of failure is invisible
to it by construction. Read the PR's checks after each push (`gh pr checks <N>`,
or `pull_request_read` with `get_check_runs`). **A red check is a finding for the
next round** and is triaged like any other; a still-running matrix is not a green
one, so a round does not close on a pending check without saying so. In the third
delivery CI went red on a rebase and stayed red across four commits and four
rounds, because every round's gate was the local one and the failure was
interpreter-specific. The user noticed. Nothing in the loop was looking.

Replies carry the reasoning that does not belong in the diff: what was measured,
what was refuted and why. The PR record is where that survives.

### Stop rule

> **Stop when the most recent round yields zero must-fix findings, that round
> reviewed the most recent fix pass, an unprimed reviewer has seen the final
> state and found nothing must-fix, every changed file has been read whole
> against that final state, *and* every behavioural claim the PR makes has been
> executed by a measuring pass.**

The last four clauses close the loop's measured blind spots. **Three of them name
a member and an append; the fix-pass clause names neither** — its remedy is a
verification round (see the Ceiling bullet), and it can be satisfied vacuously
with no successor at all. An appended pass counts toward the ceiling only if it
finds something.

**It cannot end on an unreviewed fix pass**: a fix pass is not trusted work — it
is new code written under time pressure by someone already wrong once in this
file.

**It cannot end on a state no unprimed reviewer has seen**: scoped rounds confirm
what they are pointed at, and the defects a loop creates are created by its fixes,
after round 1's unprimed pass has come and gone. If the would-be closing round had
no unprimed member, append one unprimed pass.

**It cannot end on a file nobody read whole.** Every round before the close
reviews a diff, and the defect surviving all of them is the one the diff does not
contain: on PR #956 a loop converged clean with green CI, and a single whole-file
pass then found defects in all eight files it had to touch, each a sibling of a
fix made under an obligation to sweep exactly those
([ADR-0037 § Context](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md#context)).
If the closing round had no whole-file member, append one, on the same terms as
the unprimed pass. This clause has **no vacuous case**: a diff that changes a file
can falsify that file's surrounding text, so it always applies. A one-round
delivery therefore closes on an appended pass, never on round 1 — **the floor
under this skill is two passes.**

**And it cannot end on a behavioural claim nobody ran.** The measuring member is a
panel obligation and panels start at round 3, so without this clause a one- or
two-round delivery ships with zero execution-based review while the Rules below
assert a premise was executed. An obligation that only fires mid-loop proves
nothing about what ships. If the closing round had no measuring pass **and the PR
asserts anything about existing behaviour**, append one, on the same terms as the
unprimed pass. A PR making no such claim satisfies it vacuously, exactly as a
round that fixed nothing satisfies the fix-pass clause.

A clean unprimed round 1 on a diff warranting no other lens still leaves the
whole-file clause to discharge, plus the measuring clause when the diff asserts
anything about existing behaviour. It can discharge neither itself: an unprimed
pass gets the PR number and the root alone, so it never carries a whole-file
brief or the `measuring` token. Such a delivery closes on one appended pass, or two, never on
round 1.

- **Floor: lens coverage, not a round count.** Every lens the diff *warrants* must
  have been applied. A one-surface change may warrant only the broad round; a diff
  that adds code the gate never executes, spreads a claim across artifacts that can
  disagree, or changes a published surface warrants those lenses, and round 1 by
  construction did not apply them — a clean sweep is silent about questions nobody
  asked. **This is a floor on what has been *looked at*, never a licence to stop**:
  that is the stop rule's five clauses, and they bind independently.
- **Ceiling: 5 finding-rounds, and it is soft.** On reaching it, escalate to the
  user **with the evidence, not the count**: findings per round with their
  character, the severity trend, what the last round found, and which subjects are
  still `not reached`. The count triggers the escalation; it is not what the
  decision is made on, and a bare "five rounds elapsed, continue?" hands the user
  the one number the loop already knows is a poor termination signal. Both
  escalations in the third delivery found more than the round before them, and the
  round that found that run's most severe finding was past the ceiling. Do not
  terminate silently. A verification round over an otherwise unreviewed fix pass
  does not count *if it finds nothing*; one that finds something is a
  finding-round like any other, and its own fix pass still owes a verification.
  Without that, the verify-fix-verify tail is exempt from the bound it exists
  under.
- **Judge severity, not count.** Counts plateau while severity falls.
- **A round that fixed nothing leaves nothing unreviewed.** The fix-pass clause is
  satisfied vacuously, so a clean round needs no successor to verify it.

**Check a clean round before trusting it.** `/rvw-pr` makes every reviewer state
the PR's subject in its own words precisely so this is cheap — a solo reviewer
posts it, a panel member returns it in its analyze-only report. Check **every**
member's line: a panel's clean verdict is the conjunction of its members'
silences, so one mismatched line makes that member's silence worthless and the
clean unvalidated. The remedy is member-scoped — re-spawn the mis-aimed member,
keep the valid passes; a solo round is re-run whole. Do not count an unvalidated
clean.

**Four records carry the round-by-round evidence** — one per delivery whose review
was itself measured, which is the set; the ordinals are positions in it and in no
other series. [ADR-0033](../../../sdd/adrs/0033-ship-convergence-driven-review.md)
tabulates the first (PR #945) round by round;
[ADR-0034](../../../sdd/adrs/0034-ship-panel-rounds-and-unprimed-exit.md) the
second (PR #949), which added the panel structure and the unprimed exit gate;
[ADR-0035](../../../sdd/adrs/0035-vary-method-not-model.md) the third (PR #952),
which dropped the model axis and added the measuring member; and
[ADR-0037](../../../sdd/adrs/0037-whole-file-gate-and-derived-figures.md) the
fourth (PR #956), which added the whole-file gate after a converged, CI-green loop
left defects in all eight files a single whole-file read then had to touch. Read
all four before tuning any of the above: they are the evidence that finding counts
plateau while severity keeps falling, that consecutive rounds each found defects
in the previous round's fixes, that scoped rounds leave unnamed surface
unexamined, that what separated the productive rounds was method rather than
reviewer identity, and that a clean round is silent about everything outside the
hunks it read.

**Reviewer *selection* is not in that set** —
[ADR-0036](../../../sdd/adrs/0036-reviewers-by-subject-and-method.md) decides it,
from a classification of findings across two traces rather than one delivery's
rounds, and it is the record behind the lens-and-method rule and the fixer role
above. Tuning either sends you there, not to the four.

**Repeat-site check:** if two consecutive rounds refute **the same condition** — a
gate, a predicate, a carve-out, a scope criterion — stop arguing the condition and
**enumerate its space**. Each narrowing is argued from a reading of what the hazard
is, and each is refuted by a state the argument did not consider; a third reading
is not more likely to be exhaustive than the first two. Identify the condition's
axes, parametrise them, and generate the product as a test. Nothing else in the
loop escalates from "argue the condition again" to "enumerate the space", and the
rounds themselves cannot: each is correct about the defect in front of it. In the
third delivery one gate was narrowed across rounds 5, 6 and 7 and withdrawn at the
last; its condition space was four booleans, enumerable in one test the whole
time. If the enumeration shows the condition cannot be stated without being
circular or false — three criteria, three refutations — that is the answer. Drop
the carve-out and make the subject comply.

Under the fix-shape rule this check should never fire: a condition is closed by
shape (3), an enumeration, the first time it is questioned, so its trigger has
moved from two refutations to zero and the check is a detector for a fix pass
that argued anyway. [RFC-0015 D6](../../../sdd/rfcs/rfc-0015-ship-two-surfaces.md)
proposed retiring it on that ground and **withdrew that on the evidence**: it
fired in two of BK-379's three deliveries run under the fix-shape rule, once on
what a closed backend answers at the root and once on a divergence register
argued three times (RFC-0015 § Pilot result). The check stays, and the Step 5
report keeps stating whether it fired and on what condition.

**Divergence check:** if a round finds something *more severe* than the previous
round **in code the fix passes changed**, the corrections are spawning worse
defects than they fix. Stop and re-plan rather than keep patching. The qualifier
is load-bearing: a latent defect surfaced in untouched code by a new lens is the
opposite signal, and is what the neglected-surface lens is for — the delivery this
rule came from hit its most severe finding at round 5 that way, and proceeding was
correct. Unqualified, this check would have condemned it.

This check fires on *severity*, the repeat-site check on repetition of a *site*;
neither substitutes for the other.

## Step 5: Close

1. Ripple-check audit: [`sdd/CLAUDE-REFERENCE.md` § Detailed checklist](../../../sdd/CLAUDE-REFERENCE.md#detailed-checklist).
2. CHANGELOG, BACKLOG/BACKLOG-DONE, and the trace — `discovery_followups` and
   `surprising_ripples` by hand, and the **`review:` block pasted verbatim**
   from `hatch run ship-report <N>`. Nothing in that block is hand-written or
   hand-edited, `review_rounds` included
   ([CLAUDE.md § Trace authoring](../../../CLAUDE.md#trace-authoring)).
3. Report: run `hatch run ship-report <N>`. Its output **is** the Step 5 report
   for everything derived from the PR — rounds run, findings per round, the
   final per-file distribution, the origin tag per finding, the review-driven
   commits and **CI's verdict on the final push**. Add by hand only what the PR
   record does not hold: the fix shape per must-fix finding and the mutation per
   added test, the class swept per must-fix finding and the sibling sweep per
   fix — each with what it caught — whether the repeat-site check fired and on
   what condition, or that it did not, what was filed rather than fixed, any
   surface the gate never executed, and the **final state of the Step 1 subject
   list** with each entry marked executed / read only / not reached. Every figure
   names its derivation
   ([CLAUDE.md principle 9](../../../CLAUDE.md#principles)); a report about a loop
   cannot be the one artifact asserting its counts from memory, which is why the
   derived half is a script's output rather than a recollection.

Then stop. **`/ship` never merges.** It hands over a PR that is ready to be.

## Rules

- Never push to master.
- Never end the loop on an unreviewed fix pass.
- Never end the loop on a state no unprimed reviewer has seen.
- Never end the loop on a changed file no pass has read whole.
- Never end the loop on a behavioural claim no measuring pass has executed.
- Never end the loop on a red or unread CI.
- Reviewers are read-only and fresh each round; the **subagents** — authors, and
  fixers delegated for depth — may decline an instruction with evidence. The
  default fixer is the main loop, which has nobody to decline to.
- Reviewers are picked by lens and method. **Never pin or prefer a model, and
  never by domain** — a persona staffs a lens, it does not select one.
- Every panel carries **exactly one** member that runs something — one, because
  `rvw-pr`'s base-branch recipe uses a fixed `tmp/base` path, under the round's
  review worktree, that two concurrent measurers would collide on. RFC-0015 D3
  lifts this cap by giving each measuring member a base path of its own under
  the round's worktree (`tmp/base-<member>`); it stays up until that RFC's
  final measurement, so that panel composition does not move finding counts
  while fix shape is what is measured.
- No reviewer reads the working tree the fixer edits: every pass reads and runs
  in the round's review worktree at the pushed commit, the tree check runs
  there, and one porcelain capture stays in the main tree for the write that
  missed the prefix.
- A fix takes exactly one of the five shapes and the reply names it. A
  rationale written on request is not a fix.
- The main loop fixes and owns the sweep; delegate a fix only for depth inside one
  file tree.
- Findings that are real but out of scope get filed, not silently dropped.
- If a reviewer and a fixer disagree on fact, **measure**. Neither wins by
  assertion.
- A premise about existing behaviour is executed before it ships, not read.
- Every figure this loop states — in the PR body, a brief, a reply, a commit
  message or the Step 5 report — names the derivation it came from, and the
  derivation is run before the sentence is written
  ([CLAUDE.md principle 9](../../../CLAUDE.md#principles)). Round counts and
  finding counts are the figures this loop invents, so they are the ones it is
  answerable for.
- A verification step that can fail silently is worse than none, because it is
  trusted. Fix the instrument or delete it.
