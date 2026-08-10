# ADR-0037: A Whole-File Exit Gate, and Figures That Name Their Derivation

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0033, ADR-0034 |

Amends [ADR-0033](0033-ship-convergence-driven-review.md)'s *terminate the
review loop on convergence* clause, which a further stop clause joins, and
[ADR-0034](0034-ship-panel-rounds-and-unprimed-exit.md)'s *the loop cannot end
until an unprimed reviewer has seen the final state* clause, whose exit-gate
shape this record instantiates a third time. Neither clause loses anything.
[ADR-0036](0036-reviewers-by-subject-and-method.md) and
[ADR-0020](0020-orchestrate-iterative-convergence.md) are untouched: nothing
here changes how a reviewer is selected, only what the loop may close on and how
an artifact states a figure.
**[ADR-0035](0035-vary-method-not-model.md)'s decisions are untouched, but one
sentence of its Consequences is not**: it argued from the stop rule "expressly
permit[ting] ending on a clean round 1", and the gate below removes that
permission. Qualified in place rather than amended — the reasoning it supports
holds a fortiori — and named here because a reader checking this claim against
that record would otherwise find the two disagreeing.

## Context

BK-348, from PR #956. Two sequences meet here and they have different lengths,
so both are stated with their membership rather than as bare ordinals. PR #956
is the **fourth** delivery whose review evidence produced a record —
[ADR-0033](0033-ship-convergence-driven-review.md) (PR #945),
[ADR-0034](0034-ship-panel-rounds-and-unprimed-exit.md) (PR #949),
[ADR-0035](0035-vary-method-not-model.md) (PR #952), this one. BK-348 is the
**third** item in the *Adapt … from PR #NNN's … evidence* series — BK-342,
BK-344, BK-348. (The two earlier titles carry "review evidence" and this one
does not, so the ellipsis before "evidence" is load-bearing: a pattern without
it finds one of the three.) It is the first of either sequence drawn from a
delivery whose own subject was review. Two of its signals are structural rather
than incidental.

**The loop converged and the files were still wrong.** Five posted rounds, a
clean final round, green CI — then an author-initiated pass that read each
changed file *whole* rather than as a diff found defects no round had named,
in seven of the eight files it then had to touch, every one a sibling of an
earlier fix. That is the fix-pass blind spot ADR-0034 exists for, in a run
that had been told about it five times. What survived five rounds: frontmatter
falsified by the very change it describes; an antecedent broken by a paragraph
inserted above it; a premise true for one of a section's two callers; a
cross-file cardinality claim. None of them is visible in a diff hunk. All of
them are visible in the file. Derivation: the finishing commit
`1fe4749`, whose message enumerates the defects per file
(`gh api repos/haalfi/remote-store/commits/1fe4749`).

**Review attention concentrated, and nothing in the loop measured it.** `/ship`
obliges every scoped brief to say what previous rounds have not examined and
supplies no instrument for knowing. Measured over
`gh api "repos/haalfi/remote-store/pulls/956/comments?per_page=100&page=1"`,
keeping the rows with a null `in_reply_to_id` (the endpoint returns replies
too), grouped by `.path` and set against `.../pulls/956/files?per_page=100`:
12 changed files, **28 findings across 5 review submissions** — 5, 8, 4, 7, 4 —
with 17 on one file. Over rounds 1–4: **24 findings, 16 of them still on that
one file, and 8 of the 12 files carrying none at all**. On that run the
distribution was discovered by an ad-hoc query while a brief was being written,
and the round it redistributed put three of its four findings on two of those
eight untouched files.

That filter is not a detail. The first cut of this record counted every row and
reported 29 comments over 6 submissions, "correcting" the item's 28 — which was
right. The extra row was a reply, and the extra submission was the review that
carried it. A derivation was named, so the error survived one round and no
longer; the instrument in `.claude/skills/ship/SKILL.md` now tags replies rather
than counting them.

**Eight claims across that delivery were asserted from memory and were
wrong**: seven numbers across three unrelated fields and one claim about an
action. Seven sat in PR #956 and the eighth in a review reply on its follow-up
#957, which is why the scope is the delivery rather than the one PR. The count
is the row count of the table in
[`sdd/BACKLOG-DONE.md`](../BACKLOG-DONE.md)'s BK-348 entry rather than a
remembered total. The invariant is not who caught them. **Not one was caught by
re-reading the artifact the claim sat in** — including in rounds explicitly
hunting stale claims — and every one fell when someone opened the source the
figure derived from: a schema clause, a commit, a corpus, a diff.

The correction to **row 7** is the sharpest evidence for the second decision
below, and re-running its own stated derivation is what found it.
`sdd/traces/bk-338-review-roster.yml` recorded the finishing pass's defect count
as counted from the diff hunks of `1fe4749`, six of them in
`.claude/skills/orchestrate/SKILL.md`; the commit has **four** hunks in that
file, and its 15 hunks total are reached only by counting the three in the trace
file itself — and even those are not all record, since two of them correct
defects (a re-pointed "this one", and instance 6's false clause) while one adds
the new steps. A correction written to document a miscount carries a derivation
that does not reproduce — and it was checkable in one command precisely because
it named one. This is the argument in miniature: a reader can disagree with a
derivation, and can only trust a total.

## Decision

- **The loop cannot end until a pass has read every changed file whole against
  the final state.** A third exit gate, on the same terms as the unprimed and
  measuring gates: the closing round supplies it or one pass is appended, and
  like a verification round it counts toward the ceiling only if it finds
  something. The gate is a reading mode, not a lens — its subject is each
  file's current state, with the diff as context rather than as the thing
  reviewed. It is a *detection* backstop for an obligation that already exists
  and demonstrably did not fire: ADR-0034 put the sibling sweep on the fixer,
  and every one of the defects a whole-file pass found was a sibling of a fix
  made under that obligation. *Reverse if* whole-file passes stop finding what
  the diff-anchored rounds do not, or if the sibling sweep starts catching
  those defects where they are born.

- **A figure, or a claim about an action, names the derivation it came from,
  and the derivation is run before the sentence is written.** Binding on every
  durable artifact — spec, ADR, trace, backlog item, commit message, PR body,
  review reply — and stated once as [`CLAUDE.md`
  principle 9](../../CLAUDE.md#principles) rather than per skill. The measured
  failure mode is that re-reading never worked and opening the source always
  did, so the remedy is the one that leaves the source named where the claim
  sits. Neither [CONTENT-RULES Rule 3](../CONTENT-RULES.md#rules) nor BK-330's
  stale-hand-count lesson covers this class: these figures were about fixed
  history and were simply never counted. *Reverse if* stated derivations prove
  as unreliable as the totals they replace, at which point the cheaper honest
  answer is to state fewer figures.

## Consequences

- **Positive:** the defect class that survived a whole convergence loop now has
  a structural interception, and it sits at the close, where the state being
  certified is the state that ships.
- **Positive:** brief requirement 3 gains an instrument. Under-examined surface
  was previously a reviewer's impression; it is now a query, and its recipe is
  operational contract in `.claude/skills/ship/SKILL.md`.
- **Positive:** a wrong figure becomes findable by a reader rather than only by
  the author who happens to re-derive it. Row 7's own correction failed this
  way in this delivery, in one command — instance 8's *shape* rather than a
  ninth instance, since row 8 itself was caught during PR #957.
- **Negative:** a third gate compounds the closing cost ADR-0034 already
  records. Worst case the close appends three passes rather than two — none may
  be the same reviewer, and a whole-file brief primes, so it can never double
  as the unprimed one.
- **Negative:** the derivation rule taxes every artifact that states a number,
  and it will be under-applied silently. Nothing gates it; the whole-file pass
  and the review rounds are its only enforcement, which is weaker than the
  mechanical checks the repo prefers.
- **Negative:** a whole-file pass reads the file as it is. It cannot see a
  false premise about behaviour that exists only on the base branch — that
  remains the measuring gate's job, and the two gates are not substitutes.
- **Negative:** the evidence is one delivery, as ADR-0034's was two. Both
  decisions follow from measured failures rather than from a schedule, which is
  why each carries its own reversal condition.
- **Neutral:** the *gate* does not reach `/orchestrate`, which has no exit gate
  for it to join — its rounds are capped by ADR-0020, and nothing there is
  waiting on a clean state to close. The *reading mode* is a different question
  and is left open rather than answered: methods reach that skill by
  restatement, not by the shared lens-menu link, which is how the measuring
  reviewer got there, so "it is a method, not a lens" would not have excluded
  it. Its reviewers read a diff-shaped surface too, and the same evidence would
  apply. Not adopted here because this record's evidence is one `/ship`
  delivery; adopt it there on that skill's own evidence, as ADR-0036 did for
  selection.
