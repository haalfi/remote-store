# RFC-0015: A `/ship` loop that does not review its own record

## Status

Draft. Tracked as BK-367. If accepted it graduates to an ADR amending
[ADR-0033](../adrs/0033-ship-convergence-driven-review.md),
[ADR-0034](../adrs/0034-ship-panel-rounds-and-unprimed-exit.md) and
[ADR-0037](../adrs/0037-whole-file-gate-and-derived-figures.md), and to
rewrites of `.claude/skills/ship/SKILL.md`, `/rvw-pr`, `/fix-pr`,
`sdd/traces/_schema.yml` § `review_rounds` and `CLAUDE.md` § Trace authoring.

**Date:** 2026-09-07. Every repo figure below is pinned to `2a1bbfe` and names
the command that produced it; the two commands that are longer than a line are
committed beside this file as `rfc-0015-findings.py` and `rfc-0015-rounds.py`.
The corpus moves on every merge, so re-run rather than quote.

## Summary

`/ship` converges on the work in one or two rounds and then keeps running,
because each fix pass writes new claims into the files the next round reads,
and since ADR-0037 those files include the loop's own diary. Over the nineteen
deliveries reviewed since the whole-file gate landed, the share of findings
that sit on text a fix pass wrote runs from 3% in round 1 to 46% in round 2 and
77% or more from round 3 on (Table 2). This RFC proposes that the deliverable
and the loop's record become two surfaces with the PR as the record's only
source of truth; that a fix may remove, measure, narrow or enumerate but never
argue; that every review pass reads a worktree pinned at the certified commit;
and that every figure about the loop is derived by one script after the loop
ends, which also tags each finding's origin and so gives BK-366 its data.

## Motivation

### The loop's length tripled, and the extra rounds review the loop

Deliveries under the loop as it now runs take three times the review rounds
of everything before it, and the findings the added rounds produce sit on what
the loop itself wrote. Three tables carry that, each with its derivation.

**Table 1. `review_rounds` per trace, split at the whole-file gate's merge
(`24d9464`).** Derivation: `python sdd/rfcs/rfc-0015-rounds.py 24d9464`, whose
docstring states the population and the value rule. The field counts
review-driven commits, so it is a proxy for rounds; the traces' own derivation
comments give the round count where they differ, and the shape does not change.

| Population | n | median | mean |
|---|---|---|---|
| Traces added since `24d9464` | 26 | 7 | 6.50 |
| All other traces | 213 | 2 | 2.14 |

The 26 values, so the median is checkable: 1, 1, 2, 2, 2, 3, 3, 5, 6, 6, 7, 7,
7, 7, 7, 7, 8, 8, 8, 8, 9, 9, 11, 11, 11, 13. The "before" population contains
the five deliveries that produced ADR-0033 through ADR-0037 (PRs #945, #949,
#952, #956, #958; traces `bk-324` 6, `bk-340` 6, `bug-243` 10, `bk-338` 6,
`bk-348` 8), which sit at 6 to 10, so the split is between the loop as it now
runs and everything before it, not between `/ship` and no `/ship`.

**Table 2. Where the findings sit, by round index.** Sample: the 19 traces in
Table 1's first row with `review_rounds` of five or more, mapped to their merge
PRs by the `(#N)` suffix of `git log --format=%s 24d9464..HEAD`:
#964 #965 #968 #971 #972 #973 #974 #976 #977 #978 #983 #986 #987 #989 #990 #991
#992 #994 #996. Derivation: `python sdd/rfcs/rfc-0015-findings.py <those 19>`.
For each finding (a review comment with no `in_reply_to_id`) the script blames
the commented line at the head the reviewer saw and classifies the blamed
commit against that head's own history: **original** if it is the
implementation push, **pre-existing** if it is reachable from the merge-base
with `master`, **loop-introduced** otherwise, which means a fix-pass commit.
Rounds are review submissions in posting order.

| round | original | loop-introduced | loop share of classified | unclassifiable |
|---|---|---|---|---|
| 1 | 121 | 4 | 3% | 2 |
| 2 | 50 | 43 | 46% | 2 |
| 3 | 20 | 68 | 77% | 59 |
| 4 | 2 | 27 | 93% | 34 |
| 5 | 4 | 16 | 80% | 28 |
| 6 | 2 | 11 | 85% | 18 |
| 7 | 2 | 11 | 85% | 10 |
| total | 201 | 180 | 47% | 160 |

Three bounds travel with this table. **Pre-existing is zero throughout**, and
that is the posting rule at work rather than a fact about untouched code:
`/rvw-pr` anchors a line comment to a `+` line, so a finding about unchanged
text is posted at file level and falls in the last column. **The last column
grows with the round**: panels post merged findings as `subjectType: "FILE"`,
so from round 3 to round 7 between 40% and 58% of each round is
unclassifiable (that column against the row total), and the percentages from
round 4 rest on under thirty classified findings each. The direction is unambiguous; the
figures are not precise. **A submission is not always a round**: BUG-264's
trace records eight rounds where the endpoint shows two submissions, so some
rows merge rounds. None of the three bounds moves a round-1 finding into a
later row or a loop-introduced one into the original column.

**Table 3. What the findings are about.** Same script, same sample:
92 submissions, **190 findings on `src/` or `tests/` files and 351 on
everything else**, and **133 of the 351 sit on `sdd/traces/`, `sdd/BACKLOG.md`
or `sdd/BACKLOG-DONE.md`**. A quarter of everything the loop found, it found
in its own record. Bound: a docstring finding in `tests/` counts as code here,
so the code share is a ceiling.

### Four failures from one delivery, each with a structural cause

PR #996 (BUG-274, seven rounds) is the delivery whose close report prompted
this RFC. Its trace,
[`bug-274-unreachable-host-connect-budget.yml`](../traces/bug-274-unreachable-host-connect-budget.yml),
records each of the four, and each maps onto one of the causes in the next
section:

1. **A false reachability argument, written because a reviewer asked for one.**
   The round-1 fix pass wrote a paragraph on which guard sites a connect
   failure can reach; the round-2 measuring pass drove a transport death into
   `_promote` and refuted it (trace, `fix_round_2`). Cause B.
2. **An attribution carried from a report, transposed.** The round-4 fix pass
   took a consultation triple from a previous round's report and paired it
   with a sentence's subject order without re-deriving; all three round-5
   members found the transposition (trace, `fix_round_5`). Causes B and D.
3. **A test that claimed two guards and covered one, with an assertion that
   could not fail.** Written in round 5 to pin a live-channel change; round 6
   measured that both cells stopped at the first guard and that the
   client-cleared assertion held on both revisions (trace, `fix_round_5`, last
   step). Cause B.
4. **A fix pass started while a read-only reviewer was still certifying the
   commit.** The reviewer's tree check caught it; the reviewer refused to
   proceed and rebuilt its baseline. The check detected the failure after it
   had happened, which is all a check can do. Cause C.

The same shapes recur in the deliveries before it. BUG-265 wrote a
reachability rationale three times, each refuted by running something, until
the repeat-site check fired and the condition was enumerated instead
([trace](../traces/bug-265-sftp-refused-connect.yml), `fix_enumerated`); the
same delivery claimed `EPERM` in round 5 on a safety argument that was "true
of the dispatch and false of the module" and reverted it in round 6, which is
a behaviour change born in a fix pass. BK-359's round 2 is titled *"Withdraw
the logging advice the fix pass invented and got wrong twice"* and its round 5
reverted the guide prose on the user's call
([trace](../traces/bk-359-stalled-sftp-error-detail.yml)). BUG-264's rounds 3
and 4 were "all prose, all in artifacts the round-3 pass had rewritten", and
the loop escaped by cutting the narrative rather than patching it, again on
the user's call ([trace](../traces/bug-264-azure-blank-error-message.yml)).

### The mechanism, in four parts

**A. One file carries both the deliverable and the diary.** The loop records
what it did inside the artifacts it is reviewing: `Retrospective:` and
`Annotated after round N` passages in traces (54 occurrences across 17 trace
files, `rg -c 'Retrospective|Annotated after|annotated after' sdd/traces`),
"until round N" and "this line said X" passages in specs, code and register
entries (14 across five files at the same commit, pattern set in this RFC's
derivation comment below), retrospective passages in one spec section going
from two to seven within one PR (BUG-265 trace, `fix_user_review`), and a
`review_rounds` derivation comment that went stale five times in BK-359, four
in BUG-272 and once each in BUG-265 and BUG-274, each staleness a finding in a
later round (each trace's own comment above the field); BUG-265's trace also
records one test-count figure wrong four times, each time differently. The whole-file gate then obliges
a reviewer to read all of it, because the diary sits in the file. ADR-0037 was
right about the defect class it named, and its gate enlarged the reviewed
surface by exactly the diary. BK-365 measures the same growth from the
reader's side: the median completed backlog entry went from 10 words to 649.

**B. A fix is an unconstrained authoring act.** The triage table says
*must-fix, file, refute*; nothing says what shape a fix may take. So a request
for a reason is answered by writing one, a figure is corrected by writing a
new figure, a test is added and its passing is taken as its power. The
research behind Rule 7 names why this is the worst place to author:
Rozenblit and Keil measured the illusion of explanatory depth as strongest
for exactly explanatory knowledge, and the fixer is "someone already wrong
once in this file" (ADR-0033's phrase) writing explanations under time
pressure ([research § 5.2](../research/research-appropriate-level-of-detail.md)).
The same record's § 6.3 shows the supply is self-generating: each fix to
explanatory prose adds claims, and claims are what the next round reads.
The repeat-site check exists for this and fires after two refutations, each of
which is a round.

**C. One agent, three roles, one tree.** The orchestrator, the fixer and the
author are the main loop; the reviewers are subagents told to be read-only,
sharing the working tree the fixer edits. Enforcement is by instruction plus a
post-hoc check on `HEAD` and `git status --porcelain`
(`.claude/skills/ship/SKILL.md` § Reviewer permissions). A check can only
detect; failure 4 above is what detection looks like.

**D. Reviewers measure, and the fixer reasons.** ADR-0035 moved reviewer
diversity from identity to method because every false premise fell to
execution. Nothing moved the fixer: it reads the finding, reasons about the
code and writes. Every one of the four failures is the fixer writing something
it had not run, and the measuring member catching it one round later. The loop
alternates a method-diverse review with a method-poor fix, which is why the
pattern reads as "auditing its own prose".

### Why the existing rules did not stop it

Each rule below is sound, and each is aimed at a different point of the loop
than the one where the defects are born.

- **ADR-0034's sibling sweep** puts an obligation on the fixer. The fixer is
  the bottleneck, not the reviewer, so a rule that adds to what the fixer must
  write cannot reduce what it writes wrongly.
- **ADR-0037's whole-file gate** catches the class and, per A, grows the
  surface it has to read.
- **Principle 9** binds figures and action claims. Failure 2 was an attribution
  "one level up from where principle 9 usually bites" (BUG-274 trace,
  `fix_round_5`); the fixer applied the rule to the numbers and carried the
  mapping.
- **The repeat-site check** is a late detector by design, and each detection
  costs the rounds that triggered it.
- **Research § 9.4** (a prose finding names the reader harm it prevents, or
  it is a preference) was marked *Adopt* on 2026-08-17 and is adopted in no
  skill: `rg -n 'reader harm' .claude` returns nothing at `2a1bbfe`.
- **ADR-0037's corollary** (retire a figure refuted twice) covers figures. It
  does not cover a rationale refuted twice, or a test that could not fail.

## Proposal

Six decisions. Each states the rule, the mechanism that enforces it, the
evidence it rests on, and the observation that would reverse it.

### D1. Two surfaces: the deliverable, and the record whose source of truth is the PR

**Rule.** A durable artifact carries the current claim and its derivation,
never the history of getting there. The history lives in the PR, and what the
repo keeps of it is derived from the PR once, after the loop ends.

**Mechanism.**

- The *deliverable surface* is code, tests, specs, docs, `CHANGELOG.md`, the
  migration guide, and a register entry's *what shipped* and *found by*
  paragraphs. It carries no retrospective: no `Retrospective:`, no *until
  round N*, no *an earlier revision said*, no *corrected in round N*. A claim
  found false is corrected or deleted; a claim found unmeasured is measured
  or deleted. A derivation is not a retrospective and stays.
- The *record* is the PR: commits, review comments, replies, CI. The trace's
  review block (`review_rounds`, findings per round, origin counts, per-file
  distribution) and the Step 5 report are derived from it by D4's script,
  once, after the stop rule fires, and pasted verbatim. The trace's *reads*
  are still logged as they happen; only the review fields move to the close.
  BUG-265's annotate-versus-correct rule for traces is retired, because the
  annotated half no longer lives in the trace.
- `CLAUDE.md` § Trace authoring is amended for the review fields only;
  `_schema.yml` § `review_rounds` replaces its hand-enumeration clause with
  the script's output block and names the script as the derivation.
- A check, `scripts/check_no_retrospective.py`, greps the deliverable surface
  for the marker phrases above and fails on a hit. Its bound is stated per
  [`DRIFT-RULES.md` Rule 7](../DRIFT-RULES.md#miss-rate): it matches phrases,
  not the diary written in other words, and it is on the mandatory path per
  Rule 5 because the alternative is exactly the review-enforced rule that did
  not hold. At `2a1bbfe` the phrase set hits 14 lines in five files.

**Evidence.** Cause A; Table 3's 133 findings on the record; the five stale
derivation comments; BK-365.

**Reverse if** a defect's correction is lost that the in-file diary would
have preserved, or the derived block proves as disputed as the hand one.

### D2. A fix removes, measures, narrows or enumerates; it never argues

**Rule.** The fixer's output is constrained by shape. A must-fix finding is
closed by exactly one of: (1) a behaviour change pinned by a test seen
failing first; (2) deleting the false claim; (3) replacing the claim with its
derivation, which is a command, a test name or an enumeration; (4) narrowing
the claim to what was measured; (5) filing. *Write a rationale* is not a
shape.

**Mechanism.**

- The triage table gains a required *fix shape* column, and a reply names the
  shape.
- A reviewer's *why* is answered by shape (3), or by the sentence *no reason is
  recorded; the behaviour is pinned by `<test>`*. This is Rule 7 applied to
  the fix pass: if the three sentences will not come, return to the source,
  and for a behaviour claim the source is running it. The repeat-site check's
  trigger moves from two refutations to zero, and the check is retired.
- A test added in a fix pass is mutation-checked before push, and the reply
  names the mutation and the assertion that fired. BUG-265 round 5 and
  BUG-274's `verify` phase both did this after the fact; the rule makes it
  the condition of the push.
- A reviewer's figure or attribution is a claim to re-derive, never a fact to
  carry. This is what failure 2 needed and principle 9 did not reach.
- A prose finding that does not state reader, task, failure, harm, change and
  what must survive ([research § 9.4](../research/research-appropriate-level-of-detail.md))
  is triaged *file as preference* and is never fixed in-loop. `/rvw-pr`'s
  Consistency category adopts the six-line form.

**Evidence.** Causes B and D; failures 1, 2, 3; BUG-265's three rationales and
its `EPERM` round trip; BK-359's invented advice.

**Reverse if** a delivery ships a defect that a written rationale would have
prevented and the enumeration did not, across more than one delivery.

### D3. Every review pass reads a worktree pinned at the certified commit

**Rule.** No reviewer reads the working tree the fixer edits.

**Mechanism.**

- After each push, the orchestrator runs `git worktree add tmp/review/<sha>
  <sha>` and every pass of that round, solo or panel member, is told that its
  repository root is that path. Whole-file reads come from it; measuring
  members run gates in it. `hatch run` creates the worktree's own environment,
  measured at **31.5 s wall clock for environment creation plus the full
  `lint` gate** on this container (`python -c` timer around
  `subprocess.run(['hatch','run','lint'], cwd=<worktree>)`, one run).
- The `HEAD` and `git status --porcelain` check moves to the worktree and
  stays as the residue check for a reviewer that wrote there. The main tree
  is never what is certified, so the fixer cannot dirty a certification and
  failure 4 cannot occur.
- Each measuring member measures the base branch in its own
  `tmp/review/<sha>/tmp/base` inside its worktree, so the *one measurer per
  panel* rule, whose only reason is the shared `tmp/base` path, is lifted.
- Worktrees are removed at round close; a stale one is a failed precondition
  for the next round, as a dirty tree is today.

**Evidence.** Cause C; failure 4; ADR-0035's own statement that the
constraint is "enforced by instruction, so a reviewer that ignores it
invalidates the round rather than being stopped".

**Reverse if** the worktree cost dominates a round, or a reviewer is found
reading outside its worktree at a rate the residue check misses.

### D4. Every figure about the loop is derived by one script after the loop ends

**Rule.** No hand-written figure about the loop exists while the loop runs.

**Mechanism.** `scripts/ship_report.py <PR>`, aliased `hatch run ship-report`
and guarded under `tests/scripts/`, reads the PR's comments (paged, per
`/rvw-pr` Step 4's discipline) and `git log`, and emits: findings per
submission; the per-file distribution, which replaces brief requirement 3's
two-call recipe; the origin tag per finding (D5); the review-driven commit
list and count; and CI's verdict on the head. Its output is the Step 5 report
and the trace's review block, verbatim. Mid-loop, a brief quotes its output
for the distribution and the origin counts; the orchestrator computes nothing
by hand. BK-348 declined a script because "it guards nothing"; the hand
enumerations since went stale eleven times across four traces (five, four,
one and one, the traces named under cause A), and every staleness was a
round.

**Evidence.** Cause A; ADR-0037's corollary that a figure refuted twice is
replaced by the query that regenerates it.

**Reverse if** the script's figures are disputed as often as the hand ones.

### D5. Each finding is tagged by origin, and two self-audit rounds trigger retraction

**Rule.** The loop can tell whether it is reviewing the work or reviewing
itself, and when it is reviewing itself the next fix pass retracts rather than
corrects.

**Mechanism.**

- Origin is the blame classification in `rfc-0015-findings.py`, run by
  `ship-report`: original, pre-existing, loop-introduced.
- Posting discipline follows: a finding is posted with a `LINE` anchor
  whenever a line exists, and `FILE` is reserved for a subject that is the
  file. 160 of the 541 findings in Table 2 were file-level and could not be
  classified, and from round 3 they are a third to a half of every round.
- Stop-rule clause: if two consecutive rounds' must-fix findings are all
  loop-introduced, the next fix pass is a *retraction pass*. Each affected
  passage is restored to its last state that no round found false, and then,
  if a finding still stands against it, closed by shape (2) or (3). This is
  what BUG-264's round 4 and BK-359's round 5 did on the user's call; the rule
  makes it the loop's.
- BK-366 gets its data as a side effect. Every `BUG-` filed from a loop is
  born in a round with an origin tag, so a delivery reports which of its
  discoveries were caught on new code, caught on pre-existing code, or
  escaped, which is the separation that item says the repo cannot make.

**Evidence.** Table 2; the two user-called retractions.

**Reverse if** a retraction pass removes a load-bearing reason a later round
has to restore, more than once.

### D6. The exit gates read the deliverable surface

The unprimed, whole-file and measuring gates are unchanged in kind. The
whole-file pass reads deliverable files whole and reads derived blocks not at
all: a derived block is verified by re-running the script, which a measuring
member may do. The floor of two passes, the soft ceiling of five
finding-rounds, the divergence check and the subject list all stay. The
repeat-site check is retired because D2 absorbs its trigger.

### A round under this RFC

Push, worktree at the pushed commit, passes, `ship-report` for distribution
and origin, triage with a fix shape per must-fix finding, fix in the main
tree, mutation-check any new test, gate, push, replies naming shape and
mutation, worktree removed. At the close: stop rule, `ship-report`, its output
pasted into the trace and the Step 5 report, and a register entry that states
what shipped and who found it.

## Alternatives Considered

- **A round cap.** ADR-0033 rejected it on PR #945, where the most severe
  finding arrived in round 5 in untouched code. That finding would be
  *original* under Table 2; the late findings now are *loop-introduced*, and
  D1 and D2 stop them being written rather than stop them being reviewed.
- **Drop the whole-file gate.** It found defects in all eight files on
  PR #956, and BUG-265's round-3 whole-file member found three docstrings no
  diff reached. The surface is the problem, not the reading mode.
- **Rule 7 alone.** It tests whether a section leads with its claim. A diary
  can lead with its claim; BK-365 says the same about entries.
- **A separate fixer subagent.** ADR-0036 keeps the fixer in the main loop
  because the sweeps that pay are cross-file. D2 constrains the fixer's output,
  not its identity.
- **A "reviewers in flight" lock, by instruction.** Enforcement by instruction
  is what failed. D3 makes the shared tree irrelevant instead.
- **A word budget for entries or skills.** Research §§ 1 and 4; declined by
  BK-351 and BK-353 for the `/ship` skill itself, on the same grounds.
- **Fewer reviewers, or no panels.** Method diversity found every false
  premise (ADR-0035). The panels are not the cost; the fix pass between them
  is.

## Impact

The change is confined to the repo's process surface: no public API, no
runtime behaviour, no published page other than this RFC's own.

- **Artifacts changed on acceptance:** `.claude/skills/ship/SKILL.md`
  (triage, stop rule, worktree, report), `/rvw-pr` (worktree root, `LINE`
  discipline, the six-line prose form), `/fix-pr` (fix shape, mutation check,
  re-derived attributions), `CLAUDE.md` § Trace authoring, `_schema.yml`
  § `review_rounds`, a new ADR, `scripts/ship_report.py` and
  `scripts/check_no_retrospective.py` with hatch aliases and guards,
  `sdd/GATE-INVENTORY.md` (generated).
- **Cost:** 31.5 s per pass for the worktree environment, measured once above;
  script work of size S; skill rewrites of size M.
- **Risk:** a retraction pass could remove a reason principle 8 protects,
  which is why it restores to the last clean state rather than deleting.
  `LINE`-anchor discipline moves work onto the orchestrator's posting step.
  The origin tag needs the reviewed heads, which `refs/pull/N/head` plus
  `git fetch origin <sha>` supplied for every head in the sample.
- **Backwards compatibility:** existing traces keep their hand-derived blocks;
  the schema clause dates the derived form from the ADR.
- **Testing:** guards for both scripts; one delivery run under the rules
  before the ADR is written, with Table 2 re-derived for it.

## Open Questions

1. Does `/orchestrate` take D2 and D5? Its rounds are capped (ADR-0020) and it
   has no exit gate; BK-349 declined the whole-file mode there. Proposed: D2
   yes, since it is a rule about fixes rather than loops; D5 no.
2. The `.claude/skills/` files carry loop history themselves ("measured on
   PR #956", "PR #958's round 1 returned 15 rows"). Under D1 that history is
   the ADRs' and is cited, not restated (principle 4); the sweep is BK-353's
   line of work and out of this RFC's scope.
3. Retraction against principle 8: the restore-to-last-clean rule is the
   answer offered, and it wants one delivery's evidence before it binds.
4. Whether file-level findings can be given a line after the fact, since their
   bodies usually name one, or whether Table 2's last column is accepted as
   the bound.
5. Where the mid-loop `ship-report` output lives. A PR comment from the
   orchestrator primes nobody, because reviewers never fetch comments.

## References

- ADRs: [0033](../adrs/0033-ship-convergence-driven-review.md),
  [0034](../adrs/0034-ship-panel-rounds-and-unprimed-exit.md),
  [0035](../adrs/0035-vary-method-not-model.md),
  [0036](../adrs/0036-reviewers-by-subject-and-method.md),
  [0037](../adrs/0037-whole-file-gate-and-derived-figures.md).
- [`research-appropriate-level-of-detail.md`](../research/research-appropriate-level-of-detail.md)
  §§ 5.2, 6.3, 9.2, 9.4; [`CONTENT-RULES.md` Rule 7](../CONTENT-RULES.md#kernsatz);
  `CLAUDE.md` principles 8 and 9; [`DRIFT-RULES.md`](../DRIFT-RULES.md#rules)
  Rules 5 and 7.
- Backlog: BK-365, BK-366, BK-348, BK-353, BK-349.
- Traces: BUG-274, BUG-265, BUG-264, BUG-272, BK-359, BK-360, BK-358.
- Derivations: `rfc-0015-findings.py`, `rfc-0015-rounds.py`; the phrase set
  behind the 14-line count is
  `Retrospective|Annotated after|annotated after|until round \d|an earlier revision of this|this (line|sentence|figure|step) (said|read|was)|corrected in round|Round \d (caught|found|corrected)`
  over `sdd/specs/*.md`, `sdd/BACKLOG*.md`, `src/**/*.py`, `tests/**/*.py`,
  `docs-src/**/*.md` and `CHANGELOG.md`.
