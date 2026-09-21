# RFC-0015: A `/ship` loop that does not review its own record

## Status

Draft. Tracked as **BK-382**; BK-378 built D1 and D4 and closed, and BK-379
piloted the rest before them. Minted as BK-367 and re-homed twice: ID-182's
branch minted BK-367 in parallel, then ID-018's minted BK-368 and closed it
before this PR merged. Both are ID-257's scenario, and the second is recorded
there.
BK-379 piloted D2, D3's worktree half with the one-measurer cap left up, D5's
posting half and D6's repeat-site half before the rest was built; what that
pilot can and cannot decide is stated with the acceptance criterion
(§ Impact), and what it measured is § Pilot result. **The pilot missed
clause 1 by three points and refuted D6's retirement of the repeat-site
check.** What the criterion prescribes for a miss without D1 and D4 is to build
them and re-measure, and it declines to let such a miss bear on status; BK-378
built them, so **every decision here is now in force and none has been measured
together**. This RFC is Draft because it has never been accepted.
If accepted it graduates to an ADR amending
[ADR-0033](../adrs/0033-ship-convergence-driven-review.md),
[ADR-0034](../adrs/0034-ship-panel-rounds-and-unprimed-exit.md),
[ADR-0035](../adrs/0035-vary-method-not-model.md), whose *one member per
panel* trade D3 widens to at least one, the floor of a measuring member on
every panel unchanged, and
[ADR-0037](../adrs/0037-whole-file-gate-and-derived-figures.md), and to
rewrites of `.claude/skills/ship/SKILL.md`, `/rvw-pr`, `/fix-pr`,
`/orchestrate`, `sdd/traces/_schema.yml` § `review_rounds` and `CLAUDE.md`
§ Trace authoring.

**Date:** 2026-09-07. Every repo figure below is pinned to `2a1bbfe` and names
the command that produced it, with three named exceptions: the PR #997
postscript reads that PR's head `3cd4acb`, the worktree timings are single
runs on one container, and § Pilot result is pinned at `2bd34cc` and says so,
because it measures deliveries that did not exist at the date above. The two commands that are longer than a line are
committed beside this file as `rfc-0015-findings.py` and `rfc-0015-rounds.py`;
the second takes `--at 2a1bbfe` so Table 1 can be re-derived at the pin
rather than at whatever the working tree holds. The corpus moves on every
merge, so re-run rather than quote.

## Summary

`/ship` converges on the work in one or two rounds and then keeps running,
because each fix pass writes new claims into the files the next round reads,
and since ADR-0037 those files include the loop's own diary. Over the nineteen
deliveries reviewed since the whole-file gate landed, the share of findings
that sit on text a fix pass wrote runs from 0% in round 1 to 46% in round 2 and
77% or more from round 3 on, and the same shape holds when only findings the
fixer confirmed as must-fix are counted (Tables 2 and 4). This RFC proposes that the deliverable
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
(`24d9464`).** Derivation: `python sdd/rfcs/rfc-0015-rounds.py 24d9464 --at
2a1bbfe`, whose docstring states the population (traces first added since the
split, renames followed), the value rule and the exclusion rule. The field counts
review-driven commits, so it is a proxy for rounds; the traces' own derivation
comments give the round count where they differ, and the shape does not change.

| Population | n | median | mean |
|---|---|---|---|
| Traces added since `24d9464` | 26 | 7 | 6.50 |
| All other traces carrying the field | 213 | 2 | 2.14 |

The 26 values, so the median is checkable: 1, 1, 2, 2, 2, 3, 3, 5, 6, 6, 7, 7,
7, 7, 7, 7, 8, 8, 8, 8, 9, 9, 11, 11, 11, 13. The "before" population contains
the five deliveries that produced ADR-0033 through ADR-0037 (PRs #945, #949,
#952, #956, #958; traces `bk-324` 6, `bk-340` 6, `bug-243` 10, `bk-338` 6,
`bk-348` 8), which sit at 6 to 10, so the split is between the loop as it now
runs and everything before it, not between `/ship` and no `/ship`.

Two more bounds sit on this table, beside the proxy bound above. **The field
is not required by the schema, and traces without it are excluded**: the
script prints them, and at `2a1bbfe` that is 61 of the 274 pre-split traces
and none of the 26 post-split ones, so `n=213` is the before-population that
carries the field, not the before-population. **The split commit is also the
commit from which the field's derivation had to be named**: `_schema.yml`
§ `review_rounds` binds its derivation-comment clause "from BK-348 onward" and
does not retrofit the corpus, and the field is a post-merge judgement. An
author made to recover the commit list plausibly records a higher value than
one who did not, so part of the step in Table 1 may be the rule changing what
gets written down rather than the loop changing how long it runs. Neither
bound moves the direction; both are why Table 1 is the opening figure and not
the load-bearing one. Tables 2 and 3 do not depend on the field.

**Table 2. Where the findings sit, by round index.** Sample: the 19 traces in
Table 1's first row with `review_rounds` of five or more, mapped to their merge
PRs by the `(#N)` suffix of `git log --format=%s 24d9464..HEAD`:
#964 #965 #968 #971 #972 #973 #974 #976 #977 #978 #983 #986 #987 #989 #990 #991
#992 #994 #996. Derivation: `python sdd/rfcs/rfc-0015-findings.py <those 19>`.
For each finding (a review comment with no `in_reply_to_id`) the script blames
the commented line at the head the reviewer saw. The blamed commit is
**pre-existing** if it is reachable from `origin/master`; otherwise its author
date is compared with the submission time of the PR's first review that
carried a finding: **original** if authored before that, **loop-introduced**
if after, which means a fix-pass commit. Author dates survive a rebase and do
not care how many commits the first push had; an earlier revision of the
script equated "original" with a single first commit, which was false for 3 of
the 19 PRs (#968 and #971 pushed three commits before review, #991 two) and
moved four round-1 findings into the loop-introduced column. Rounds are review
submissions in posting order.

| round | original | loop-introduced | loop share of classified | unclassifiable |
|---|---|---|---|---|
| 1 | 125 | 0 | 0% | 2 |
| 2 | 50 | 43 | 46% | 2 |
| 3 | 20 | 68 | 77% | 59 |
| 4 | 2 | 27 | 93% | 34 |
| 5 | 4 | 16 | 80% | 28 |
| 6 | 2 | 11 | 85% | 18 |
| 7 | 2 | 11 | 85% | 10 |
| 8 | 0 | 0 | — | 2 |
| 9 | 0 | 0 | — | 3 |
| 10 | 0 | 0 | — | 2 |
| total | 205 | 176 | 46% | 160 |

Every column sums: 205 + 176 + 160 = 541 findings, which Table 3 reaches
independently. Rounds 8 to 10 belong to one PR (#990) and carry file-level
findings only.

Four bounds travel with this table. **Pre-existing is zero throughout**, and
that is the posting rule at work rather than a fact about untouched code:
throughout the sample `/rvw-pr` anchored a line comment to a `+` line, so a
finding about unchanged text was posted at file level and falls in the last
column. So the *loop share of classified* column here equals
`loop-introduced / (original + loop-introduced)`; under D5's `LINE`
discipline the two part company, the
script prints the latter as `share l/(o+l)` with pre-existing in its own
column, and a table re-derived over the pilot carries that ratio under this
heading, which is the acceptance criterion's clause 1 (§ Impact). **The last column
grows with the round**: panels post merged findings as `subjectType: "FILE"`,
so from round 3 to round 7 between 40% and 58% of each round is
unclassifiable (that column against the row total), rounds 8 to 10 are
entirely so, and the percentages from round 4 rest on under thirty classified
findings each. The script counts four unclassifiable causes separately;
in this sample all 160 are file-level and none is a `LEFT`-side, null-line or
blame-failure finding. The comments endpoint's row order agreed with review
submission order in every sampled PR, which the script now checks rather than
assumes. The direction is unambiguous; the figures are not precise.
**A submission is not always a round**: BUG-264's trace records eight rounds
where the endpoint shows two submissions, so some rows merge rounds. **A
commit authored before round 1 but pushed after it would read as original**;
the loop pushes before it spawns reviewers, so the case is not expected, and
it is not measured. None of the four bounds moves a round-1 finding into a
later row or a loop-introduced one into the original column.

**Table 4. The same, counting must-fix findings only.** Severity is what the
proposal's rules key on, so the script reads the fixer's first reply in each
thread for its verdict. This repo's replies open with the verdict, so the
opening word decides where it is present: "Must-fix" opens a *must-fix* reply
whatever follows, "Filed as" a *filed* one, "Refuted", "Not a defect",
"Declined", "Rejected" or "Decided" a *refuted* one. Otherwise the reply is
searched with word boundaries, filed before refuted before must-fix
("Filed as" or a minted ID; "refut", "not a defect", "declin", "rejected",
"stays"; "Fixed in", "Confirmed", "Correct", "Taken", "Added", "Annotated");
*unknown* otherwise, including an unanswered thread. Over the sample: 295
must-fix, 10 filed, 56 refuted, 180 unknown. An earlier revision matched
substrings and counted "incorrect" and "added to the backlog" as must-fix; it
reported 1 filed and 8 refuted. The unknown third is the heuristic's bound, and
it is not spread evenly: #968's 50 findings are all unknown, as are most of
#977's, #990's and #994's later rounds, where the fixer answered in review
summaries rather than in the threads. Within the classified must-fix findings:

| round | original | loop-introduced | loop share of classified | unclassifiable |
|---|---|---|---|---|
| 1 | 73 | 0 | 0% | 2 |
| 2 | 39 | 23 | 37% | 1 |
| 3 | 16 | 34 | 68% | 23 |
| 4 | 1 | 17 | 94% | 14 |
| 5 | 2 | 10 | 83% | 12 |
| 6 | 2 | 8 | 80% | 6 |
| 7 | 1 | 8 | 89% | 3 |

Restricting to must-fix lowers rounds 2 and 3 by nine points each and leaves
rounds 4 to 7 within five points of Table 2, so the late rounds are not many
filed nits around a few real defects: the fixer confirmed and fixed them, and
they were on its own text. Round 3 carries more classified must-fix findings
than rounds 4 to 7 together (50 against 49, summing the rows), so its 68% is
the figure the conclusion leans on most, and it is below the 77% Table 2 gives
for the same round.

**Table 3. What the findings are about.** Same script, same sample, and
unaffected by the origin classifier:
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

### A fifth delivery, read after this draft was written

PR #997 (BUG-275, nine rounds, `2a1bbfe..3cd4acb`, 19 files, +1,551/−223 by
its own close report) is the strongest single instance of the pattern and adds
one defect shape the four causes above do not name. Its shipped code change is
one line, unchanged since its second commit; everything after it was making
the repo's claims about that line true. Its rounds 1 to 3 did find behaviour
defects, and every one was in code a fix pass had written: a scoped guard that
answered a connect-time denial as `PermissionDenied` on seven of nine entry
points, abandoned when the divergence check fired and the work was re-planned
onto the dispatch arm ([trace](../traces/bug-275-raise-if-dir-eperm.yml),
`replan`). Rounds 4 to 9 found prose.

**The fifth shape: a fact measured through an injected fixture, written as a
rule about the library.** The session's close report names it as its one
recurring defect, and the trace records three instances: a `check_health`
diagnostic that was constant across the two cases it claimed to separate
(`fix_6`), an "identical before and after" that held for one errno only
(`fix_6`), and a published upgrade note describing an ancestor carve-out
"only the test produces" (`fix_8`), which took four rounds to restate and three
to get wrong before it was removed from the published layer. Every one of them
*was* measured, so ADR-0035's rule was met; what was missing was the
instrument's reach beside the claim. No `EPERM` trigger exists on a working
SFTP channel, so every test of the new behaviour is injection-based, and a
sentence that drops the injection becomes a claim about what a user can meet.

**The same delivery missed a ripple on its own measurement.** Round 8 measured
that a permission-refused connect pays two connect budgets on two operations,
recorded it against BUG-273, and did not ask whether it falsified a spec
clause; SFTP-031 says "whichever connect-time shape occurred", and round 9
caught it. A measurement is a change to what the repo may claim, and nothing
routed from the number to the clauses it bears on.

**Its findings are mostly unclassifiable by the origin tag**, which is
Table 2's unclassifiable bound in its sharpest form: `python sdd/rfcs/rfc-0015-findings.py 997`
at `3cd4acb` returns 4 submissions and 20 inline findings for nine rounds, ten
of the twenty file-level, so the loop-introduced share can be read for rounds 1
and 2 only (0% and 40%). Nine rounds of review left a record from which the
question this RFC asks cannot be answered, and that is the posting discipline
D5 requires, not a new bound.

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
evidence it rests on, and the observation that would reverse it. Each reversal
condition names something a reader can count in the PR record or in
`ship-report`'s output (D4), so that it can be evaluated rather than argued.

### D1. Two surfaces: the deliverable, and the record whose source of truth is the PR

**Rule.** A durable artifact carries the current claim and its derivation,
never the history of getting there. The history lives in the PR, and what the
repo keeps of it is derived from the PR once, after the loop ends.

**Mechanism.**

- **The unit is the file, and the boundary is what the text is about, not
  where it sits.** A *retrospective* is text whose subject is an earlier
  version of the artifact it sits in: `Retrospective:`, *until round N*, *an
  earlier revision said*, *corrected in round N*, *this figure was wrong four
  times*. Text whose subject is the repository or the work is content, however
  historical: ID-257's "a second instance" paragraph records a collision that
  happened in the repo, not a previous draft of ID-257, and stays. That is the
  distinction the phrase set encodes, and it is what lets the check run over
  whole files without a paragraph parser.
- The *deliverable surface* is code, tests, specs, docs, `CHANGELOG.md`, the
  migration guide, and `sdd/BACKLOG*.md` in full. A register entry is
  deliverable in every paragraph: what shipped, the mechanism, figures with
  their derivations, what was deliberately not done, who found it. What leaves
  it is the round-by-round account of getting there, which is the record's.
  Whether the remaining paragraphs are too long is BK-365's question and not
  this RFC's. A claim found false is corrected or deleted; a claim found
  unmeasured is measured or deleted. A derivation is not a retrospective and
  stays.
- The *record* is the PR: commits, review comments, replies, CI. The trace's
  review block (`review_rounds`, findings per round, origin counts, per-file
  distribution) and the Step 5 report are derived from it by D4's script,
  once, after the stop rule fires, and pasted verbatim under one YAML key
  (`review:`), so the trace's boundary is a key the check can see. The trace's
  *reads* are still logged as they happen; only the review fields move to the
  close. BUG-265's annotate-versus-correct rule for traces is retired, because
  the annotated half no longer lives in the trace.
- `CLAUDE.md` § Trace authoring is amended for the review fields only;
  `_schema.yml` § `review_rounds` replaces its hand-enumeration clause with
  the script's output block and names the script as the derivation.
- A check, `scripts/check_no_retrospective.py`, greps the deliverable surface
  for the marker phrases above and fails on a hit, naming file and line
  ([`DRIFT-RULES.md` Rule 2](../DRIFT-RULES.md#localize)). It declares a
  `Drift-gate::` block and its bound per
  [Rule 7](../DRIFT-RULES.md#miss-rate): it matches phrases, not the diary
  written in other words, and a retrospective that avoids the phrase set is a
  reviewer's to catch. It sits on the mandatory path per Rule 5 because the
  alternative is exactly the review-enforced rule that did not hold. The extent
  is whatever `python scripts/check_no_retrospective.py` reports at the head
  being read; stated as the command rather than a figure because the figure
  moves with every register entry, and the one pinned here at `2a1bbfe` ("14
  lines in five files") was already wrong in its file count by the time the
  check was built (BK-378 measured 14 lines in **four** files at `e109686`).
  **Built under BK-378**, with the surface widened to include `examples/` as a
  surface users read.

**Evidence.** Cause A; Table 3's 133 findings on the record; the five stale
derivation comments; BK-365.

**Reverse if** a defect's correction is lost that the in-file diary would
have preserved, or `ship-report`'s per-file finding count shows the derived
trace block drawing findings in more than one round per delivery, which is the
rate the hand-written block drew (eleven stalenesses across four traces, at
least one per delivery).

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
- **A measured claim is bounded by its instrument, and says so.** A fact
  established through injection (a patched method, a fake client, a forced
  errno) is written as a fact about that injection unless a trigger a user can
  produce is named beside it; a rule about the library needs the producer. The
  question to ask once before publishing is the one PR #997's close report
  ends on: *could a user reach this?* Shape (4) is the fix when the answer is
  no. This is the fifth shape above, and ADR-0035 does not cover it because
  measuring is exactly what those three claims had done.
- **A new measurement is swept like a fix.** The number is not the deliverable;
  the clauses it bears on are. Before a measured fact is recorded anywhere, the
  artifacts that assert something about the same behaviour are listed and each
  is left true, which is principle 2 applied to a measurement rather than to a
  diff. PR #997's round-8 counter-example to SFTP-031 sat in a backlog item
  for a round because nothing asked this.
- A prose-quality finding with no rule behind it that does not state reader,
  task, failure, harm, change and what must survive
  ([research § 9.4](../research/research-appropriate-level-of-detail.md))
  is triaged *preference*: replied to as such, not filed as a backlog item,
  and never fixed in-loop. `/rvw-pr`'s Consistency category adopts the
  six-line form; a false statement in prose is a Bug or Spec finding, a
  finding citing a CONTENT-RULES or DRIFT-RULES rule is a violation, and both
  are closed by shape (2), (3) or (4) like any other.

**Evidence.** Causes B and D; failures 1, 2, 3; BUG-265's three rationales and
its `EPERM` round trip; BK-359's invented advice.

**Reverse if** a `BUG-` filed after merge against a delivery run under this
rule is closed by restoring a rationale the loop removed under shape (2) or
(3), more than once. That is observable in the fix PR's diff; a counterfactual
about what a rationale would have prevented is not, and is not the condition.

### D3. Every review pass reads a worktree pinned at the certified commit

**Rule.** No reviewer reads the working tree the fixer edits.

**Mechanism.**

- After each push, the orchestrator runs `git worktree add tmp/review/<sha>
  <sha>` and every pass of that round, solo or panel member, is told that its
  repository root is that path. Whole-file reads come from it; measuring
  members run gates in it. `hatch run` creates the worktree's own environment
  on first use, once per worktree and so once per round, not per pass. The
  repo has one hatch environment (`hatch env show` lists `default` alone), so
  lint and the test gates share it and the creation cost is the same whichever
  a member runs first. Measured on this container, one run each, `python -c`
  timers around `subprocess.run(..., cwd=<fresh worktree>)`: **`hatch env
  create` 25.6 s**; `hatch run lint` in another fresh worktree 31.5 s, so the
  gate itself was under six seconds of that. Gate time after creation is the
  gate's cost, not the worktree's, and is paid today.
- The `HEAD` and `git status --porcelain` check moves to the worktree and
  stays as the residue check for a reviewer that wrote there, with one
  porcelain capture kept in the main tree beside it, required unchanged at
  triage: a reviewer's default working directory is the main tree, and a
  stray write there is what the next fix pass would commit. A detached
  worktree's `HEAD` cannot move on its own, so the other thing the old check
  caught, the branch advancing under a certifying reviewer, needs its own
  capture: at triage the branch's pushed head is fetched and required to still
  equal the certified commit. The main tree is never what is certified, so the
  fixer cannot dirty a certification and failure 4 cannot occur.
- Each measuring member measures the base branch in a base path of its own
  under the round's worktree, `tmp/review/<sha>/tmp/base-<member>`, so the
  *exactly one measurer per panel* cap is lifted. The cap is `/ship`'s, and
  the skill gives it one reason: the fixed `tmp/base` path two concurrent measurers
  would collide on (`.claude/skills/ship/SKILL.md` § Rules), which
  per-member paths remove. ADR-0035's *Every panel carries one measuring
  member* bullet says something else: a floor, which stays, and a
  diversity-budget trade, one seat spent on method instead of identity,
  which the lift widens to at least one seat rather than repeals. That
  widening is what the graduating ADR amends in ADR-0035 (§ Status); the
  bullet's own reverse condition, measuring members ceasing to find what
  reading members miss, is not what D3 touches and stays as written.
  **The cap stays up until this RFC's final measurement**: BK-379's three
  deliveries took the worktree and not the lift, because lifting it changes
  panel composition and moves finding counts independently of fix shape, which
  is what the pilot measured. That reason outlived the pilot — § Pilot result
  prescribes a re-measurement with D1 and D4 shipped, and a composition that
  moved in between would be comparable with neither the 78% baseline nor the
  pilot's 53%. The cap comes down with the graduating ADR, on BK-382's
  account.
- Worktrees are removed at round close, with a `prune` for the base worktree a
  measuring member left nested inside (measured on git 2.43.0: ignored
  leftovers and the nested worktree do not block the removal, and the nested
  entry becomes prunable). A leftover from an earlier round collides with
  nothing, since the path carries its commit; it blocks only a pass re-spawned
  for that same commit, and carries a hatch environment, so it is removed
  before adding rather than treated as a wrong-commit hazard.

**Evidence.** Cause C; failure 4; ADR-0035's own statement that the
constraint is "enforced by instruction, so a reviewer that ignores it
invalidates the round rather than being stopped".

**Reverse if** environment creation exceeds the round's shortest review pass
(the per-pass durations `ship-report` reads from review submission times), or
a reviewer is found reading outside its worktree at a rate the residue check
misses.

### D4. Every figure about the loop is derived by one script after the loop ends

**Rule.** No hand-written figure about the loop exists while the loop runs.

**Mechanism.** `scripts/ship_report.py <PR>`, aliased `hatch run ship-report`
and guarded under `tests/scripts/`, reads the PR's comments (paged, per
`/rvw-pr` Step 4's discipline) and `git log`, and emits: findings per
submission; the per-file distribution, which replaces brief requirement 3's
two-call recipe; the origin tag per finding (D5); the review-driven commit
list and count; per-pass durations from review submission times; and CI's
verdict on the head. Its output is the Step 5 report and the trace's review
block, verbatim. The per-file count includes the trace, which is how D1's
reversal condition is read.

**The backlog ID-set check is a gate, not a report line.** A rebase that drops
a live item, or a PR body that claims to close another branch's open item
(PR #997 did both, in rounds 5 and 7, and no gate covers either) is two
artifacts disagreeing, which is [`DRIFT-RULES.md`](../DRIFT-RULES.md#rules)'s
subject, and that file says a report is not a reduced-obligation category. So
it ships as `scripts/check_backlog_ids_vs_base.py`: the set difference of
`PREFIX-NNN` item headers between the working tree and `origin/master`,
failing on an ID that master has open and the head lacks, or that the head
closes while master has it open on another branch's account, and naming the
ID and the side (Rule 2). It runs in the PR validation gates `/pr` and
`/fix-pr` already share, which fetch `origin/master` first (Rule 5: the
mandatory path, at push time rather than at the close). Each of the three
scripts this RFC names, `ship_report.py` included, declares the `Drift-gate::`
block Rule 7 requires, so `gen_gate_inventory.py` populates their rows rather
than passing a `ship_` prefix silently. Mid-loop, a brief quotes its output
for the distribution and the origin counts; the orchestrator computes nothing
by hand. BK-348 declined a script because "it guards nothing"; the hand
enumerations since went stale eleven times across four traces (five, four,
one and one, the traces named under cause A), and every staleness was a
round.

**Evidence.** Cause A; ADR-0037's corollary that a figure refuted twice is
replaced by the query that regenerates it.

**Reverse if** the script's own output draws findings in more than one round
per delivery, which is the hand-written block's measured rate (cause A), read
from the per-file count the script emits about itself.

### D5. Each finding is tagged by origin, and two self-audit rounds trigger retraction

**Rule.** The loop can tell whether it is reviewing the work or reviewing
itself, and when it is reviewing itself the next fix pass retracts rather than
corrects.

**Mechanism.**

- Origin is the blame classification in `rfc-0015-findings.py`, run by
  `ship-report`: original, pre-existing, loop-introduced.
- Posting discipline follows, in its conservative reading: a finding is
  anchored to its true line when that line falls inside a diff hunk, context
  lines included, and stays `FILE` otherwise; it is never anchored to an
  unrelated line. `/rvw-pr`'s comment rules, as BK-379 found them, attached a
  finding on unchanged text to the nearest `+` line, and `origin()` blames the
  line the comment carries, so that reading would tag a finding on untouched
  text as loop-introduced whenever a fix pass wrote the nearest `+` line,
  inflating the share this RFC measures against a baseline that excluded such
  findings rather than misattributing them. The `+`-line bullet is amended,
  not read around. 160 of the 541 findings in Table 2 could not be
  classified, and the script separates the four causes it has: all 160 are file-level, and the
  `LEFT`-side, null-line and blame-failure counts are zero in this sample, so
  the discipline's reach here is bounded by 160 and not measured: it reaches
  the findings whose true line sits inside a hunk, which the sample does not
  record, and what no hunk reaches stays `FILE` (Open Question 4). From
  round 3 they are 40% to 58% of every round, and PR #997's nine rounds left
  twenty inline findings, half of them file-level.
- Stop-rule clause: when two consecutive rounds each carry **at least two
  classified must-fix findings of which at least 80% are loop-introduced**,
  the next fix pass is a *retraction pass*. Each affected passage is restored
  to its last state that no round found false, and then, if a finding still
  stands against it, closed by shape (2) or (3). This is what BUG-264's round
  4 and BK-359's round 5 did on the user's call; the rule makes it the loop's.
  **The constants are chosen from a dry run, not asserted.** The script runs
  three readings over the 19 sampled deliveries. "All classified must-fix
  findings loop-introduced" fires in 2 PRs and 5 rounds (#973 four times,
  #987 once) and never on #996, because one original finding in a round of
  ten silences it. "Unclassifiable counts as loop-introduced" fires in 5 PRs
  and 13 rounds, but #991's four and #976's three are rounds posted entirely
  at file level, so that reading fires on the posting artifact rather than on
  the loop. The 80% share over at least two classified findings fires in 3 PRs
  and 9 rounds (#973 four, #986 one, #996 four) and in none of the file-level
  rounds; it is the reading adopted. Unclassifiable findings are excluded from
  the ratio, so under today's posting the trigger under-fires rather than
  over-fires, and the `LINE` discipline above raises its reach. Under that
  discipline a second bias runs the same direction: the dry run's clean count
  is `mf-original + mf-pre-existing` (`clean`, feeding `hot()`, in
  `rfc-0015-findings.py`'s D5 dry run), and a finding anchored to a context
  line blames a commit reachable from `origin/master` and is tagged
  pre-existing, a category the
  baseline has at zero (Table 2's first bound). So the trigger under-fires
  under the `LINE` discipline too, and its count is read as a floor.
- BK-366 gets its data as a side effect. Every `BUG-` filed from a loop is
  born in a round with an origin tag, so a delivery reports which of its
  discoveries were caught on new code, caught on pre-existing code, or
  escaped, which is the separation that item says the repo cannot make.

**Evidence.** Tables 2 and 4; the dry run above; the two user-called
retractions.

**Reverse if** a retraction pass removes a load-bearing reason a later round
has to restore, more than once (a finding whose fix re-adds text the
retraction removed, visible in the round's diff), or the trigger fires in a
round whose classified must-fix findings are later refuted as a majority.

### D6. The exit gates read the deliverable surface

**Rule.** The unprimed, whole-file and measuring gates are unchanged in kind
and read the deliverable surface; a derived block is verified by re-running
its script, never by reading it.

**Mechanism.** The whole-file brief names the deliverable files and excludes
the trace's `review:` key; a measuring member may re-run `ship-report` and
diff its output against the block.
**That second half has a permission conflict, found while building D4 and
unresolved here.** `/rvw-pr`'s measuring allowlist is by name and does not
carry `ship-report`, and the script reads comment *bodies* where that skill's
metadata carve-out is bounded to paths, review ids and counts — so a member
running it would have read the conversation, which is what keeps unprimed
passes unprimed. BK-378 narrowed `/ship` to *no reviewer runs `ship-report`*
rather than widen the permission. Whoever takes this deferred half has to
supply a reach that does not read feedback: a `--no-triage` mode, or a
verification the orchestrator performs and the reviewer only reads. The floor of two passes, the soft ceiling
of five finding-rounds, the divergence check and the subject list all stay.
**The repeat-site check stays too, and this is a withdrawal.** The decision as
drafted retired it because D2 moves its trigger from two refutations to zero,
which is this decision's reverse condition read forward; the pilot fired it
twice in three deliveries run under D2 (§ Pilot result), so the check keeps
its text in the skill and D2's rule is a second route to the same response
rather than a replacement for the detector.

**Evidence.** ADR-0037's gate found real defects (eight files on PR #956,
three docstrings no diff reached on BUG-265); what it read was the problem,
not that it read (Alternatives). The repeat-site check's two firings in the
sample (BUG-265 round 4, BUG-275 round 2) each cost the two rounds that
triggered them.

**Reverse if** a whole-file pass finds a defect in a derived block that
re-running the script does not reproduce. The second condition — a condition
argued and refuted twice in one delivery under D2, meaning the retired check's
trigger still has work — **fired in the pilot**, and the retirement it
governed is withdrawn above rather than left standing with its own reversal
met.

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
  re-derived attributions), `/orchestrate` (its `tmp/base` rule names
  `/ship`'s one measuring member per panel as what keeps `/rvw-pr`'s fixed
  path safe, and D3 lifts that cap; D3's own mechanism does not run there,
  since its reviewers read uncommitted work and no per-round review worktree
  exists, so this RFC leaves its exactly-one rule as written, and whether
  per-reviewer base paths lift it is Open Question 1; D2's fix shapes at its
  fix step and the six-line prose form in its reviewer contract, per that
  question's settled half), `CLAUDE.md`
  § Trace authoring, `_schema.yml`
  § `review_rounds`, a new ADR, `scripts/ship_report.py`,
  `scripts/check_no_retrospective.py` and
  `scripts/check_backlog_ids_vs_base.py` with hatch aliases, guards and
  `Drift-gate::` blocks, `sdd/GATE-INVENTORY.md` (generated).
- **Cost:** 25.6 s of environment creation once per round, measured once
  above (D3); script work of size S; skill rewrites of size M.
- **Acceptance criterion, stated before the run.** Three deliveries run under
  the rules, pooled, then `rfc-0015-findings.py` over them. Graduate to an ADR
  if (1) the loop-introduced share of must-fix findings from round 3 on,
  over `original + loop-introduced`, is below 50% (Table 4's pooled rounds 3
  to 7: 77 of 99, 78%, summing its rows), (2) the derived trace block draws a
  finding in at most one round across the three, and (3) the retraction
  trigger fires at most once. **Clause 1's denominator is not *classified*
  in the sense Tables 2 and 4 and clause 3's stop rule use**, which includes
  pre-existing; it is the two categories the baseline was measured over.
  Pre-existing is a category the baseline has at zero throughout (Table 2's
  first bound) and D5's `LINE` discipline newly populates, so a denominator
  that counted it would lower the share for a reason that has nothing to do
  with D2 or D3; clause 3 keeps the full sense on purpose, which is the floor
  bias D5 names. The pre-existing and unclassifiable counts are reported
  beside the share, and they bound what the discipline newly reached rather
  than measure it. Pre-existing is a floor: the other half of Table 2's
  residue, findings panels posted as `FILE` by practice though a `+` line
  existed (Table 2's second bound), anchors under the rule to lines that read
  as original or loop-introduced and is not separated from the findings the
  baseline classified. That half enters clause 1's numerator and denominator
  from a population the 78% baseline excluded, which is the comparability
  bound in the other direction, and the fall in the unclassifiable count
  against Table 2's 40% to 58% per round is the only measure of its size.
  Its sign is not measured. If that half resembles the classified findings of
  its own round, which from round 3 are 77% to 93% loop-introduced (Table 2),
  it raises the share, so the bias runs against passing; the per-round
  unclassifiable count is what lets a reader see how much of the figure it
  could account for. `rfc-0015-findings.py` prints clause 1 as one line, `POOLED r>=3
  must-fix`, over the PR numbers given, with `o`, `l`, `p` and `u` beside
  the share, and its `BY ROUND INDEX` share excludes pre-existing for the
  same reason; the per-finding classification is what Tables 2 to 4 rest
  on, and the print change does not touch it. With every decision shipped,
  any of the three failing sends the RFC
  back to Draft with the measured figures attached, not to the ADR with a
  softened threshold. One delivery is one draw and is not the criterion.
- **What BK-379's pilot decided**, written before it ran. It took D2, D3's
  worktree half with the one-measurer cap left up, D5's posting half and D6's
  repeat-site half, without D1 and D4, and reported clauses 1 and 3 only.
  Clause 2 has no referent until D4 generates the block it names; it is
  deferred with D4, not dropped. Clause 3 is reported as a dry run, since the
  retraction pass is not wired into the loop there, and is read as a floor
  (D5). A clause-1 miss in the pilot does not send the RFC back to Draft: D1
  targets the record surface, where a quarter of the sample's findings sit
  (Table 3), and a share at or above 50% without it is equally consistent
  with D2 and D3 being too weak alone and with the record surface carrying
  the late rounds. The pilot cannot tell the two apart. A miss says build D1
  and D4 and re-measure; only a miss with those shipped is the sentence
  above. **It reported in § Pilot result**, and that is the branch it took.
- **Risk:** a retraction pass could remove a reason principle 8 protects,
  which is why it restores to the last clean state rather than deleting.
  `LINE`-anchor discipline moves work onto the orchestrator's posting step.
  The origin tag needs the reviewed heads, which `refs/pull/N/head` plus
  `git fetch origin <sha>` supplied for every head in the sample.
- **Backwards compatibility:** existing traces keep their hand-derived blocks;
  the schema clause dates the derived form from the ADR.
- **Testing:** guards for the three scripts; the three-delivery run above
  before the ADR is written.

## Pilot result

BK-379 ran D2, D3's worktree half, D5's posting half and D6's repeat-site half
over three deliveries and measured them. **The loop-introduced share of
must-fix findings from round 3 on fell from 78% to 53%, which misses clause 1's
bar of below 50% by three points, and the repeat-site check D6 proposed
retiring fired twice.** Clause 3 passed at zero firings and clause 2 has no
referent without D4, so the branch § Impact prescribes for a clause-1 miss
without D1 and D4 is the one taken: build them and re-measure.

**Sample.** PRs #1021 (BUG-254), #1022 (BK-375, BK-373, BK-377) and #1023
(BK-370) — the three deliveries opened after the skill amendments merged
(#1020, merged `2026-09-17T19:42Z`; the three opened at 20:38, 21:13 and
`2026-09-18T19:34Z`, from `gh api repos/haalfi/remote-store/pulls/<N> --jq
'{created_at, merged_at}'`), so no round in the sample ran under the old rules.
Every figure below comes from `python sdd/rfcs/rfc-0015-findings.py 1021 1022
1023` at `2bd34cc` unless it names another derivation. 69 findings over 14
submissions. Their traces record `review_rounds` 7 for #1021, 7 in each of
#1022's three and 4 for #1023, against Table 1's post-gate median of 7: **the pilot does not show the loop getting shorter**, it
shows what the late rounds are about.

**Table 2 re-derived over the pilot.** Same classifier, same columns, with
pre-existing given its own column because the `LINE` discipline populates it:

| round | original | loop-introduced | loop share of `o + l` | pre-existing | unclassifiable |
|---|---|---|---|---|---|
| 1 | 13 | 0 | 0% | 1 | 1 |
| 2 | 10 | 3 | 23% | 0 | 0 |
| 3 | 6 | 1 | 14% | 2 | 12 |
| 4 | 3 | 3 | 50% | 0 | 3 |
| 5 | 3 | 7 | 70% | 0 | 0 |
| 6 | 0 | 1 | 100% | 0 | 0 |
| total | 35 | 15 | 30% | 3 | 16 |

**Table 4 re-derived, which is clause 1.** Must-fix findings only:

| round | original | loop-introduced | loop share of `o + l` | pre-existing | unclassifiable |
|---|---|---|---|---|---|
| 1 | 8 | 0 | 0% | 1 | 1 |
| 2 | 8 | 3 | 27% | 0 | 0 |
| 3 | 5 | 1 | 17% | 2 | 6 |
| 4 | 2 | 3 | 60% | 0 | 3 |
| 5 | 2 | 5 | 71% | 0 | 0 |
| 6 | 0 | 1 | 100% | 0 | 0 |
| **pooled 3 to 6** | **9** | **10** | **53%** | **2** | **9** |

The pooled row is the script's `POOLED r>=3 must-fix` line and the criterion's
clause 1: 53% against the bar of below 50% and against the baseline's 78%
(77 of 99). **The verdict is one finding wide.** Nineteen classified findings
carry it, so one finding is five points and a single reclassification — 9 of
19, 47% — passes it; the baseline's denominator is five times larger. Three
deliveries are a small draw, which is what the criterion says about one and
does not stop being true of three.

**What D5's posting half reached.** Pre-existing is 3 against zero throughout
the baseline's 541, all three in #1021: the rule anchors findings on unchanged
text, which is the thing it exists to do, and the 78% comparison excludes them
for that reason. Unclassifiable is 16 of 69 (23%) against 160 of 541 (30%);
from round 3 it is 12 of 21, 3 of 9, 0 of 10 and 0 of 1, against the baseline's
40% to 58% of every round. Ten of that 12 are #1023's round 3, which posted all
ten of its findings at file level, so the residue is still a whole-file round
rather than a spread across rounds. All 16 are file-level and the `LEFT`-side,
null-line and blame-failure counts are zero, as in the baseline, so Open
Question 4 is untouched.

**Triage classified more of the sample**: 51 must-fix, 1 filed, 9 refuted, 8
unknown over 69 (12% unknown), against 295, 10, 56 and 180 over 541 (33%). D2's
reply rule puts the verdict and the fix shape in the thread, which is where the
heuristic reads; the baseline's unknown third was fixers answering in review
summaries instead.

**D2 was adopted in practice.** 67 of the 72 fix replies name a fix shape
(#1021 35 of 38, #1022 13 of 15, #1023 19 of 19), citing (4) narrow the claim
21 times, (1) a behaviour change pinned by a test 18, (3) replace the claim
with its derivation 16, (2) delete the false claim 13 and (5) file it once.
Derivation: the reply bodies from `gh api
repos/haalfi/remote-store/pulls/<N>/comments --paginate --jq '.[] |
select(.in_reply_to_id) | .body'`, matched against
`shapes?\b[^.\n]{0,40}?\*{0,2}\([1-5]\)` — once per reply for the adoption
count, every match for the histogram. Bound: the pattern reads what a reply
*claims*, not whether the diff took that shape.

**Clause 3, the retraction trigger, as a dry run.** It fires in 0 of 3 PRs and
0 rounds under all three readings, the adopted 80%-over-two included, which is
inside the *at most once* bound and is read as a floor: both biases D5 names
(unclassifiable findings excluded from the ratio, pre-existing ones counted as
clean) under-fire rather than over-fire.

**D6's repeat-site half is refuted.** The check fired twice in three
deliveries, both run under D2: #1021's `_azure.py` thread records "the second
consecutive round to refute the same condition" — what a closed backend answers
at the root — and closed it by enumerating the axis in a test rather than
patching the operation the round found; #1023's feedstock-divergence thread
records a condition "refuted three times" before a register replaced the
argument. Derivation: the same reply bodies matched against `repeat-site`, one
reply each in #1021 and #1023 and none in #1022, each naming the check. D6's
own reverse condition is therefore met, the retirement is withdrawn there, and
`/ship` keeps the check.

**What the record surface still carries.** 16 findings sit on `src/` or
`tests/` and 53 on everything else, and **14 of the 53** sit on `sdd/traces/`,
`sdd/BACKLOG.md` or `sdd/BACKLOG-DONE.md` — the same nesting Table 3 states,
since `record` is a subset of `prose` in the script rather than a third class.
That is 20% of the 69 against the baseline's 133 of 541 (25%). Correction 2's
non-separability holds exactly as filed: a share at or above 50% with D1
unbuilt is equally consistent with D2 and D3 being too weak alone and with the
record surface carrying the late rounds, and this sample cannot tell them
apart.

**Dispositions.**

- **D1** — not piloted. The clause-1 miss is the RFC's own reason to build it,
  not evidence against the RFC. **Built under BK-378**, which also answered
  Open Question 5 and widened the deliverable surface to `examples/`.
- **D4** — not piloted. Clause 2 kept no referent until `ship_report.py`
  existed, and every figure in this section was produced by a hand-run script,
  which is D4's argument. **Built under BK-378**; clause 2 is askable from the
  next delivery on.
- **D5** — the posting half is measured above and stays as written. The
  stop-rule clause was never wired into the loop and the dry run gives no
  firing to tune its constants against, so the constants shipped unchanged
  alongside `ship-report` and the wiring is still owed (BK-382).
- **D6** — the repeat-site half is withdrawn above. Its deferred half (the
  whole-file brief excluding the trace's `review:` key, and a measuring member
  re-running `ship-report`) had nothing to read until D1 and D4 existed; it now
  has, and is owed under BK-382.
- **D2, and D3's worktree half** — in force in the four skills since #1020,
  unchanged by this result; D3's cap lift waits for the re-measurement, for the
  reason D3 now states.

**The pilot's measurements above are not amended by the build; the dispositions
are, and were.** BK-378 shipped D1 and D4, so the four bullets it changed now
say what became of each decision rather than what was still owed. Every figure
in this section remains the pilot's, read over PRs #1021 to #1023. BK-382
carries the re-measurement, and the RFC stays **Draft** until that sample is
read against § Impact's three clauses.

## Open Questions

1. Does `/orchestrate` take D2 and D5? Its rounds are capped (ADR-0020) and it
   has no exit gate; BK-349 declined the whole-file mode there. D2: settled
   yes by BK-379's pilot, whose skill amendment names the five shapes at
   `/orchestrate`'s fix step, since it is a rule about fixes rather than
   loops. D5: proposed no. And whether
   its exactly-one measuring rule, whose reason is the same fixed `tmp/base`
   path, is lifted by per-reviewer base paths: D3's per-round worktree cannot
   supply that there, and nothing is proposed either way.
2. The `.claude/skills/` files carry loop history themselves ("measured on
   PR #956", "PR #958's round 1 returned 15 rows"). Under D1 that history is
   the ADRs' and is cited, not restated (principle 4); the sweep is BK-353's
   line of work and out of this RFC's scope.
3. Retraction against principle 8: the restore-to-last-clean rule is the
   answer offered, and it wants one delivery's evidence before it binds.
4. Whether file-level findings can be given a line after the fact, since their
   bodies usually name one, or whether Table 2's last column is accepted as
   the bound. The pilot leaves it where it found it: all 16 of its
   unclassifiable findings are file-level, and ten of them are one whole-file
   round (§ Pilot result).
5. Where the mid-loop `ship-report` output lives. A PR comment from the
   orchestrator primes nobody, because reviewers never fetch comments.
   **Answered under BK-378: nowhere durable.** `--out tmp/ship-report-<PR>.md`
   writes a scratch copy (`tmp/` is gitignored), the orchestrator quotes the
   per-file distribution and origin counts into the brief, and reviewers read
   the brief. The durable copy is the trace's `review:` block, written once at
   the close. The PR-comment option was declined for the reason this question
   already gives; a committed mid-loop artifact was declined because it would
   put a generated file in the tree D3 pins as the certified commit.
6. Whether the instrument-bound clause in D2 can be checked at all. A test
   that patches a method is recognisable (`monkeypatch`, `patch(`, a fake
   client class); a prose claim that generalises from it is not. The clause
   binds the fixer and the reviewer, and the `/rvw-pr` Premise lens is the
   natural place to ask *could a user reach this?* of every published claim.

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
- Traces: BUG-274, BUG-265, BUG-264, BUG-272, BK-359, BK-360, BK-358, and
  BUG-275 (read at PR #997's head `3cd4acb`, merged as `4452d26`).
- Derivations: `rfc-0015-findings.py`, `rfc-0015-rounds.py`; the phrase set
  behind the 14-line count is
  `Retrospective|Annotated after|annotated after|until round \d|an earlier revision of this|this (line|sentence|figure|step) (said|read|was)|corrected in round|Round \d (caught|found|corrected)`
  over `sdd/specs/*.md`, `sdd/BACKLOG*.md`, `src/**/*.py`, `tests/**/*.py`,
  `docs-src/**/*.md` and `CHANGELOG.md`.
