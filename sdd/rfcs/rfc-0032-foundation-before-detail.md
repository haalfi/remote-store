# RFC-0032: Durable prose stands on a stated foundation

## Status

Draft, 2026-11-25. Tracked as **BK-513**. Nothing in it binds until the
maintainer accepts it. It amends no record and no authority doc: what changes
in each of them is open (§ Open Questions 1) and is settled by the map of § 5,
which runs during this RFC's review. Decisions taken in its session: decision
log `sdd/decisions/b7a95816-4b77-51cb-8393-4179d5eec51c.jsonl` ("First step":
an RFC for the whole repo; "Sources": cite, commit nothing external; "Reach":
new and rewritten work).

## Summary

**Durable prose in this repo is written against a stated foundation: a few
fixed terms and a few principles, each with its reason and a way to show it
broken. Detail is judged against that foundation, never against other
detail.** This RFC states what a foundation, a principle and a decision are,
gives six principles for writing them, and proposes that they bind an
artifact when it is written or substantially rewritten. A map of where each
artifact kind stands is made during review and decides what else changes.

## Motivation

**Review of prose here does not converge, and the findings are about
substance, not wording.** The figures are
[`research/token-usage/report.md` § 5](../research/token-usage/report.md#5-review-loop-anatomy)'s,
from the 41 traces with a derived `review:` block:

- Of 650 top-level review comments, 399 are on prose files and 186 on code or
  tests.
- From round 4 on, 49 to 78% of a round's findings were caused by an earlier
  fix in the same loop.
- 17 of the 41 PRs drew prose and trace findings only, in loops of up to 13
  rounds.
- Of 321 prose findings in the 13 longest loops, 6 are wording (CLARITY). The
  rest are an overstated extent or a missing case (SCOPE 91), a wrong fact
  (FACT 89), two places that disagree (MIRROR 82), a broken written rule
  (RULE 34) and disagreement with the decision itself (DESIGN 19). The classes
  are defined in
  [`prose_classes.py`](../research/token-usage/prose_classes.py) and were
  assigned by a model, 9 of 10 right on a spot check (report § What this does
  not establish).

**The rules we have act on text after it exists.**
[`CONTENT-RULES.md`](../CONTENT-RULES.md), [`SPEC-DESIGN.md`](../SPEC-DESIGN.md)
and [`DRIFT-RULES.md`](../DRIFT-RULES.md) say how a sentence, a spec section
or a check is shaped. They help, and they stay. None of them says what a
piece of prose must agree with, so a reviewer compares one detail with
another, and each fix adds claims for the next round to compare.

**Where a foundation existed, the work held.**
[Spec 051](../specs/051-store-tree.md) states the store tree in 122 lines
(`wc -l`): its terms, then axioms, then the lemmas they imply, each axiom
justified by a structure that breaks only that clause
([research § 5](../research/research-store-model-axioms.md#5-why-each-axiom-is-there)).
OP-01's record has no such layer. It holds 179 decisions
(`rg -c '^### OP-01/D' sdd/observe/records/OP-01.md`) in 6,017 lines, and its
consistency lines named 61 of the 946 decision pairs and caught none of the
four known defect pairs among them
([`research-observe-record-quality.md` § 2](../research/research-observe-record-quality.md#2-results)).

**The words themselves are not fixed.** In `sdd/` and `CLAUDE.md`,
"principle" names four different things, and a decision has seven homes:

| "Principle" names | Example |
|---|---|
| A rule of behaviour | [`CLAUDE.md` § Principles](../../CLAUDE.md#principles) 1 to 9 |
| The idea behind a set of rules | `CONTENT-RULES.md` § How the rules interact: "Rules 1–6 are expressions of a single principle" |
| A lesson | P1 to P5 of the format brief, [`research-spec-first-reset.md` § 5](../research/research-spec-first-reset.md#5-format-research) |
| One design decision | `OP-01/D27`, "The typing principle" |

| A decision is recorded in | Form |
|---|---|
| An ADR | Context, Decision, Consequences ([template](../templates/adr-template.md)) |
| An RFC | Numbered rows, such as RFC-0024's D1 to D11 |
| A research doc | `research-spec-first-reset.md` calls itself "a point-in-time decision record" |
| A dialog log | `sdd/decisions/*.jsonl` ([RFC-0018](rfc-0018-decision-capture-at-dialog-time.md)) |
| An `/observe` record | `<entry>/D<n>` ([`observe/axes.md` § Per-question loop](../observe/axes.md)) |
| `observe/shared.md` | Sections for decisions that bind every operation |
| A backlog dossier or done entry | A "Decision" section; § Decided against |

Both tables list what this session's reads found, not every use.

## Proposal

**Convention.** In § 1 to § 4 a present-tense statement is a rule of the
proposal. A statement that cites a file is a fact the proposal relies on.

### 1. Terms

Each term has one meaning in this RFC, and each concept one term.

| Term | Meaning |
|---|---|
| **Durable prose** | Text in the repo that later work reads to learn what holds: a spec, an ADR, an RFC, an authority doc, a skill file, a backlog item, a record. Not a chat reply or a commit message |
| **Subject** | What a body of durable prose is about: the store, the review loop, the backlog |
| **Foundation** | The terms and principles of one subject, which everything else written about it is judged against |
| **Term** | One fixed word for one concept of a subject |
| **Principle** | A rule that holds for every part of a subject, with its reason and a way to show it broken. Not a rule of one part, which is a clause |
| **Clause** | A promise about one part of a subject. It refines a principle |
| **Premise** | A fact about the world that a principle or a clause relies on and does not itself establish |
| **Open choice** | Something the subject needs settled and has not, stated as such |
| **Decision** | A selection that settles an open choice. Its result becomes a term, a principle or a clause |
| **Record of deciding** | The question, the options and the reason behind a decision. Never the place where the result is read |

An axiom, in spec 051's sense, is a principle of a structure subject whose
test is a countermodel. This RFC renames nothing in that spec.

### 2. Principles

Each states its rule, why it is needed, what shows it broken, and an example
from this repo.

#### F1. Foundation first

> Detail about a subject is written against the subject's foundation and
> judged against it, never against other detail.

**Why:** comparing details with each other does not end; comparing each with
a few principles does.

**Broken when:** a clause can be defended only by pointing at another clause.

**Example:** spec 051's TREE-010 to TREE-012 are checked against its axioms
(its Notes name the proofs), not against each other.

#### F2. Fixed words

> A subject's terms exist before the statements made from them. Each term has
> one meaning and each concept one term.

**Why:** two statements cannot agree or contradict while their words shift.

**Broken when:** one word carries two meanings, or one concept two words.

**Example:** [`observe/shared.md` § Session](../observe/shared.md) splits
"session" into design session and caller session, "never written bare".

#### F3. Breakable

> Every principle and every clause says what would show it false.

**Why:** prose has no test. A stated counterexample is the nearest thing to
one, and it lets a reviewer check instead of judge.

**Broken when:** no observation could contradict the statement.

**Example:** `SPEC-DESIGN.md` Rule 1's can-fail test, and the countermodel
per axiom clause in the store-model research § 5.

#### F4. Result, not history

> An artifact that states what holds states only that. How it was decided is
> kept in a record of deciding, apart from it.

**Why:** the deciding buries the decided, and a reader can no longer see the
design or its errors.

**Broken when:** a reader must follow a discussion to learn the rule.

**Example:** spec 051 holds no options and no dialog; its rationale is the
research doc it links.

#### F5. Say what kind

> A rule, a premise and an open choice can always be told apart.

**Why:** an open choice that reads as a rule gets relied on, and one that
reads as freedom gets filled with a guess.

**Broken when:** a reader cannot tell whether something is promised, assumed
or undecided.

**Example:** `observe/axes.md`'s non-commitment answers: "A term is a
decision; 'not decided yet' is an open item, not a term."

#### F6. Few and distinct

> A foundation holds few principles, and each answers a question none of the
> others answers.

**Why:** only a set a reader can hold at once steers their work, and overlap
between principles brings back the comparison F1 removes.

**Broken when:** removing a principle changes nothing that is allowed.

**Example:** each of spec 051's axiom clauses has a structure that satisfies
every other clause and breaks that one.

#### How the six fit together

F1 says what detail is judged against. F2 says what the statements are made
of. F3 says how one is checked. F4 says what an artifact leaves out. F5 says
how a reader knows the status of what they read. F6 says how large the
foundation may be.

### 3. Written forms

**A principle is written as five parts in one order:** a short name; the
rule; why it is needed, as the harm without it; what shows it broken, phrased
as the violation; one example from the subject. Consequences follow where
other text cites them. § 2 is written this way.

**A decision is written as five parts:** the open choice it settles; the
selection; why this one over the alternatives it names; what follows from it;
what would show it not kept. The first three are the record of deciding. The
selection also appears, as a result, where it holds (F4).

**A foundation opens by saying what it binds.** One statement gives its
subject, what is bound by it, and what is not until another artifact adopts
it. Its open choices are listed, each with what settles it.

### 4. What binds, and when

**F1 to F6 and § 3 bind an artifact of durable prose when it is written or
substantially rewritten.** "Substantially rewritten" is
[`CONTENT-RULES.md` Rule 7](../CONTENT-RULES.md#kernsatz)'s: the claim
changed, not the wording. An artifact left untouched keeps its form.

**A subject gets its foundation before new detail is written about it.**
Which subjects of this repo need one, and in which order, is open (§ Open
Questions 2).

**On acceptance, § 1 to § 3 move to one authority doc under `sdd/`** in the
[Authoritative Document Format](../../CONTRIBUTING.md#authoritative-document-format),
and an ADR records why. Until then no skill, template or authority doc
changes.

### 5. The map

**During this RFC's review, each kind of durable prose is read against F1 to
F6, and the result is reported, not fixed.** It is an audit
([`000-process.md` § Document types](../000-process.md#document-types)): it
reviews existing quality and stays as written.

- **Kinds:** the five of `000-process.md` § Document types, plus authority
  docs, skill and agent files, backlog items and dossiers, `/observe` records,
  traces and `CLAUDE.md`.
- **Per kind:** two artifacts, the most recent and the one with the most
  review findings where a `review:` block names one. For each principle: holds
  or broken, with the passage that shows it.
- **Output:** a table of kind against principle, and for each broken cell
  what kind of change would mend it. It proposes no wording.

The map settles § Open Questions 1 and 2. It also tests F3 on this RFC: a
principle that two readers apply to one passage with different results is
not yet breakable.

### 6. The measure

**The proposal is kept or dropped by what happens to review loops, read from
each trace's `review:` block.** Backlog § 8 promises that a change to how
sessions work is measured before it becomes process.

- **Read:** rounds, findings, and the share of findings that an earlier fix
  caused, for each delivery whose main artifact is durable prose written under
  F1 to F6.
- **Against:** report § 5's figures, quoted in § Motivation.
- **Bound:** the first deliveries are few and are not a rate. FACT findings,
  89 of the 321, are wrong counts and paths; no principle here addresses them,
  and [`CLAUDE.md` principle 9](../../CLAUDE.md#principles) already does.

The threshold that decides keep or drop is open (§ Open Questions 3) and is
fixed before the first measured delivery, as
[report § Learnings](../research/token-usage/report.md#learnings) asks.

## Alternatives Considered

- **More rules about prose.** A further rule in `CONTENT-RULES.md`. Rejected:
  such rules act on wording and placement, and wording is 6 of the 321
  findings.
- **A template per artifact kind.** Fixes shape, as the spec template does.
  Rejected as the first step: a shape does not say what the content must agree
  with.
- **A checker that reads prose.** Rejected: pairwise conflict detectors ran at
  19 to 67% precision and miss conflicts that need three or more statements
  (`research-observe-record-quality.md` § 2).
- **The map first, then the RFC.** Rejected by the maintainer in this session:
  the map needs the principles it reads against, and making it during review
  tests them.
- **Bind every existing artifact, with a migration.** Rejected by the
  maintainer in this session: it commits to an extent before the map shows
  where the pain is.
- **An authority doc without an RFC.** Rejected: it would bind before any
  trial.

## Impact

- **Public API:** none.
- **Backwards compatibility:** none; no released behaviour changes.
- **Process:** none until acceptance. This file is outside the process-budget
  ratchet, whose globs are `CLAUDE.md`, `.claude/` files,
  `sdd/CLAUDE-REFERENCE.md` and `sdd/traces/_schema.yml`
  (`sdd/process-budget.json`). Text a later change adds to those files is a
  recorded raise.
- **Testing:** none.

## Open Questions

Each names what settles it.

1. **What changes in each existing authority doc, template and skill.**
   Settled by: the map, then the maintainer, before acceptance.
2. **Which subjects get a foundation, and in which order.** The store's is
   being written under BK-485; the process's own (how work is done here) is
   the other candidate this session saw. Settled by: the map.
3. **The keep-or-drop threshold of § 6.** Settled by: the maintainer, before
   the first measured delivery.
4. **Which of the seven decision homes hold a record of deciding and which a
   result.** `/observe` records hold both today. Settled by: the map for the
   finding; a change to `/observe` is BK-485's.
5. **The name and place of the authority doc of § 4.** Settled by: the
   maintainer at acceptance.
6. **Whether F6's test can be applied to prose principles** as spec 051
   applies it to axioms, by a case that breaks one and keeps the rest.
   Settled by: the map's attempt on § 2.

## References

- Evidence: [`research/token-usage/report.md`](../research/token-usage/report.md)
  § 5 and § Learnings;
  [`research-observe-record-quality.md`](../research/research-observe-record-quality.md);
  [`research-store-model-axioms.md`](../research/research-store-model-axioms.md);
  [`research-appropriate-level-of-detail.md`](../research/research-appropriate-level-of-detail.md);
  [`research-code-abundance-goals-and-values.md`](../research/research-code-abundance-goals-and-values.md)
  § 2.3.
- Related: [RFC-0018](rfc-0018-decision-capture-at-dialog-time.md), the
  record of deciding at dialog time;
  [RFC-0024](rfc-0024-spec-first-reset.md) and
  [ADR-0048](../adrs/0048-how-specs-are-designed.md), how specs are designed.
- Unpublished input, not committed here: the maintainer's reference on
  principles and decisions (v0.4), and a problem note on durable prose written
  and reviewed with coding agents (2026-11-16). This RFC restates what it
  takes from them in its own words and rests its figures on this repo's
  records only.
