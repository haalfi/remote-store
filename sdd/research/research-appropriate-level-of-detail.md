# Research: Is the level of detail appropriate?

**Date:** 2026-08-17
**Backlog items:** ID-256, which shipped the authoring test in § 5.3.
**Status:** Advisory research, not a spec or ADR. A standing reference on one
question — *is the level of detail appropriate?* — rather than a record of how it
was investigated. Point-in-time snapshot per
[`sdd/000-process.md` § Document types](../000-process.md): the repo figures in
§§ 6–7 drift with the corpus, and the sourcing tiers in § 7 record what was
reachable on the date above, so read every figure against that date.
**Related:**
[`research-id-232-detail-placement-durability.md`](research-id-232-detail-placement-durability.md)
answers the neighbouring question, *where does this detail belong?*;
[`../CONTENT-RULES.md`](../CONTENT-RULES.md) carries the rules this document
argues for.

## Decision

**Set no word count, no readability target and no general "be concise" rule.**
Appropriateness is a relation between the text, the reader's purpose and
knowledge, and the author's grasp of the subject; no property of the text alone
carries it. The author's grasp is the one part checkable while writing, so that
is where the rule sits.

For a new or substantially rewritten section:

1. **State the core claim in at most three sentences.** If they will not come,
   stop writing and return to the source.
   ([Rule 7](../CONTENT-RULES.md#kernsatz) — in force.)
2. **Keep the detail that answers a reader's question, supports a decision or
   lets an action be executed.** Everything else is a candidate for cutting.
3. **When cutting, keep worked examples, exact commands and identifiers before
   explanatory elaboration** that restates what the reader can already see — and
   keep conceptual material that fixes scope, applicability, constraints or a
   choice between alternatives.
4. **Do not cut rationale the surviving section cannot recover. Move it.**
5. **A prose review finding names the reader harm it prevents**, or it is a
   preference.

Apply 2–4 the more cautiously the less you can observe the reader's purpose: the
licence is strongest in task-oriented internal material and weakest in public
documentation and onboarding. § 9 carries the reasoning behind each, and marks
which are adopted and which are still pilots.

## TL;DR

The Decision rests on this chain, and every section below argues one link of it:

1. No text-level instrument — word budget, readability index, density metric —
   decides the question by itself, because none of them sees the reader (§ 1).
2. Both failure directions are measured, and the same text reverses its verdict
   when the reader arrives with a task rather than without one (§ 2).
3. Which *kind* of detail is cut decides more than how much: worked examples are
   safer to keep than elaboration that restates what the reader can see (§ 3).
4. Brevity is the one comprehensibility dimension whose optimum sits mid-scale,
   so "shorter" is not a direction to push monotonically (§ 4).
5. The reader is absent at writing time and the author is not, which is why the
   shipped control is an author-side test: state the section's core claim, or
   return to the source (§ 5).
6. The reader-side instruments this repo owns detect the *opposite* failure from
   the one it commits, so they cannot close the loop unaided (§ 6).
7. Therefore: keep the author-side test, condition cutting on **recoverability**
   rather than on length, and require a prose review finding to name the reader
   harm it prevents (§ 9).

Links 3 and 7 are this record's own contribution — link 3 is Charney, Reder &
Wells's Study 2 read against this repo's prose, and link 7's recoverability split
was found in the local experiment (Appendix) rather than taken from a source.
Links 1, 2, 4 and 5 are the literature. Link 6 is repo measurement. § 8 marks
where the evidence breaks, and § 10 lists what would settle the open half.

## Context

The question is asked constantly here and answered ad hoc every time. It arrives
as a review finding ("this could be tighter"), as an authoring hesitation (how
much of the reasoning goes in the ADR), and as a recurring cost: `/ship` sessions
reach stable code and tests in two to four rounds and then spend the remainder on
prose findings (§ 6.3). This record exists to give that question a standing
answer, and to say which parts of the answer are evidenced and which are not.

**Standing caveat: five sources have been read in full, one of them a primary.**
Every other external claim rests on an abstract or a search summary, because
every scholarly host returns 403 from this environment. Treat those as
directional and the repo figures as the reliable half; § 7 tiers each claim and
§ 8.2 names the five and what each carries.

---

## 1. Why the question has no text-level answer

Four traditions arrive independently at the same shape: adequacy is indexed to
something outside the text.

| Source | What it indexes adequacy to |
|---|---|
| Grice (1975), "Logic and Conversation" | The purpose and **stage** of the exchange: "such as is required, at the stage at which it occurs" |
| Nickerson (1999), "How We Know — and Sometimes Misjudge — What Others Know: Imputing One's Own Knowledge to Others", *Psychological Bulletin* 125, 737–759 | What **this specific addressee** already knows. Cite it by title: a different Nickerson paper of the same year and volume ("Enhancing creativity", 683–732) is easily substituted for it |
| Groeben (1982), *Leserpsychologie* [*Reader Psychology*] | Comprehensibility as **text × reader interaction**, explicitly not a text property |
| Göpferich, Karlsruher Verständlichkeitskonzept | Keeps the Hamburg four (as *Struktur*, *Simplizität*, *Motivation*, *Prägnanz*), **adds *Korrektheit* and *Perzipierbarkeit***, and reframes the whole around the **communication situation and the text's communicative function** — the correction to the Hamburg model's *textzentriert* [text-centred] perspective |

**[Grice and Nickerson: verified. Groeben and Göpferich: search-summary.]**

**The consequence is negative and worth stating first, because it rules out the
instruments people reach for.** No word budget, readability index or density
metric can decide appropriateness by itself, because each is blind to the
reader's purpose and prior knowledge. They remain useful for what they measure —
a readability index tracks surface features that correlate with comprehension in
aggregate — and that is not the same as deciding a particular text for a
particular reader.

## 2. Both directions are evidenced, and reader purpose decides which one bites

Both failures are real and measured. Which one a text commits depends on why its
reader opened it.

| | **Overshoot** — more detail than the reader needs | **Undershoot** — less context than the reader needs |
|---|---|---|
| Direct evidence | Reder & Anderson: textbook chapters against summaries one-fifth their length; **summary readers scored significantly higher on the main points, study after study** | The same experiment's other half: readers with no specific task performed **much worse** with the short manual |
| Robustness | Held across immediate and up-to-one-year delays, true/false, short-answer and free recall, timed and take-home reading | Charney, Reder & Wells call these readers "more greatly impeded by *under-elaborated* texts than the task-directed learners were by the *over-elaborated* version" |
| Mechanism | Encoding *and* retrieval: with study time on the main points equated, summary readers still won, so elaborations also make the main point harder to retrieve — and "may make it harder for readers to distinguish important points from unimportant ones" | Curse of knowledge: authors impute their own knowledge and omit bridging detail |
| What the repo measures | The **cost**: review rounds spent on prose (§ 6.3) | The **incidence**: trace tags dominated by missing units (§ 6.2) |

**[Verified: Charney, Reder & Wells (1988), "Studies of Elaboration in
Instructional Texts", in Doheny-Farina (ed.), *Effective Documentation*, MIT
Press, 47–72, read in full. Reder is an author of the studies she reports.]**

**The measured interaction, from their Study 1** (Reder, Charney & Morgan, 1986;
40 inexperienced users, an elaborated 11,000-word PC-DOS manual against an
unelaborated 3,500-word one, 45 minutes' reading, then tasks on the machine):

| Reader | Elaborated manual | Unelaborated manual |
|---|---:|---:|
| Knew the tasks in advance | 33.5 min, 95.8 commands | **36.1 min, 94.2 commands** |
| No specific goal | **29.4 min, 76.8 commands** | 40.2 min, 101.8 commands |

Task-directed readers did slightly better without the elaborations. Readers
without a goal did far worse without them. **Same text, opposite verdicts,
decided by what the reader came for.**

**The asymmetry that matters is in the size of the two penalties.** Overshoot is
evidenced, for readers who know what they are looking for, and the effect is
small. **The penalty for cutting too much fell on the reader who lacked a goal,
and it was the larger of the two.** A rule that only cuts is therefore aimed at
the case where cutting helps least and hurts most, which is why
`research-id-232`'s justification-sufficiency test still applies.

**The authors' own resolution is the sentence this whole document is circling:**
"It is possible for both expounders and minimalists to be right if we shift the
focus away from length per se. **Length is not really the issue.**"

## 3. What "appropriate" is a function of

Four inputs, each with a source and a direction.

**Reader expertise, and it reverses.** More explicit, more elaborated material
helps low-knowledge readers and can *harm* high-knowledge ones.

The sharpest case is Kalyuga, Chandler & Sweller (1998), described in detail by
its own senior author in Sweller, van Merriënboer & Paas (1998), "Cognitive
Architecture and Instructional Design", *Educational Psychology Review* 10(3),
251–296. **[Verified against that review, read in full; the *Human Factors*
primary is still unread.]** Novice electrical apprentices were given a wiring
diagram plus a textual description that merely re-described it. For novices the
text "was essential. They could not understand the diagram alone and required
the text", and was best **integrated** with the diagram. "In contrast, once the
learners gained additional experience … textual material re-describing a novel
circuit was redundant and it was better to **fully eliminate** the textual
material for expert learners rather than integrate it with the diagrams."

**Elimination is not confounded with integration**, which is what makes this
usable: the expert comparison is *diagram alone* against *diagram plus integrated
text*, so removal is its own condition and it wins. Mental-effort ratings ran the
same way — higher load for experienced learners given the redundant version. The
authors' own summary: "material that is redundant for some learners and so best
eliminated, may be essential for less experienced learners and best integrated."

**The two strands argue with each other, which is worth knowing before either is
cited.** Sweller et al. read McNamara, Kintsch, Songer & Kintsch (1996) — the
reverse cohesion effect, where added coherence helped low-knowledge and impeded
high-knowledge readers — as a redundancy result rather than an active-processing
one, and give a reason: if the additional material had worked by *reducing active
processing*, mental-effort ratings should have fallen, and instead they rose.
Two literatures, one prediction each, and the effort data is what separates them.
**[Verified against the same review.]** The 1996 study still manipulated coherence
rather than surplus detail, so it bounds the claim rather than proving it.

**Reader purpose and the decision at stake.** What the reader must decide or do
determines which units are load-bearing. A constraint, an exception or a
precondition is detail by appearance and structure by function. This is the input
with the cleanest measurement behind it: § 2's table is the same manual reversing
its verdict when the reader arrives with a task rather than without one.

**Which *kind* of detail, which turns out to matter more than how much.** In
Charney, Reder & Wells's Study 2, four manual versions crossed rich or sparse
**conceptual** elaboration (what a command is for, when it applies) with rich or
sparse **procedural** elaboration (worked examples of correct commands), across 40
novice and 40 experienced users. Procedural richness decided everything —
37.4 and 37.7 minutes with it, 43.5 and 45.9 without; 71.7 and 73.7 commands with
it, 88.7 and 92.4 without. **Conceptual elaboration made no difference at all**,
whether added to a rich or a sparse procedural manual, and the novices benefited
from it no more than the experienced users did. What readers wanted was "little
more than a summary of the conceptual information" plus "well-chosen examples
that illustrated what a correct computer command would look like in a specific
plausible situation". **[Verified, read in full.]**

*Repository inference, not their finding:* when a section must be reduced, test
the conceptual elaboration for redundancy first — worked examples, exact commands
and identifiers are the safer things to keep. **The transfer has a bound the
study cannot supply**: their conceptual elaboration explained what a command was
*for*, not which of several commands applied. Conceptual material that fixes
scope, applicability, a constraint or a choice between alternatives is
load-bearing here in a way theirs was not. § 9's third proposal carries both
halves.

**Text type.** The same fact belongs at different depth in an ADR, a spec, a
guide and a chat reply, because the text's function differs
(Göpferich; Brinker's *Textsorte/Textfunktion*). **[Search-summary.]**

**Prior knowledge the author cannot observe.** For public docs and package users
the expertise input is unknown, which is why expertise-conditioned rules work
inside `sdd/` and fail on `docs-src/`.

## 4. The dimension with an unconditional mid-scale optimum

The Hamburg model (Langer, Schulz von Thun & Tausch, 1974, *Sich verständlich
ausdrücken* [*Expressing Yourself Comprehensibly*]) rates a text on four
dimensions, each on a five-point bipolar scale from `−−` to `++`. *Einfachheit*
[simplicity] and *Gliederung/Ordnung* [structure/order] have their optimum at
`++`. **The optimum for *Kürze/Prägnanz* [brevity/conciseness] sits mid-scale,
between `0` and `+`: extremely terse, compressed texts impede comprehension just
as verbose ones do.** **[Two secondary sources read in full and in agreement; the
book itself remains unread.]**

**It is not the only mid-scale dimension, but it is the only unconditional one.**
*Anregende Zusätze* [stimulating additions] typically also sits between `0` and
`+`, and its optimum moves with the others: `−` or `−−` when structure is weak,
`0`/`+` or occasionally `++` when simplicity and structure are strong. Brevity's
does not move.

**The definition worth borrowing** is a ratio rather than a length: the text's
length matches the amount of information it means to communicate. That is the
same shape as § 1's relational finding, arrived at from the other side.

**The empirical base is stronger than "expert ratings", and weaker than the
optimum needs.** Four studies used *konzeptorientiertes Rating*: trained raters,
five to ten per text, judging blind, with inter-rater agreement required before
averaging. **28 texts in two versions each, over 1,100 readers** — roughly 600
pupils and 500 adults — read them and answered comprehension and retention
tasks, and the improved versions helped: effects classed "large" for about half
the texts, small or medium for a quarter, and **no effect for the remaining
quarter**. The corpus was not only instructional: schoolbooks, but also legal
codes, encyclopaedia entries, insurance conditions, a tax leaflet, a purchase
contract and scientific studies.

**What that does not establish is the optimum itself.** Those studies validate
the four dimensions against reader performance. No study varied length alone and
measured the resulting curve, so the mid-scale optimum is the authors'
recommendation derived from their model, not a measured dose-response. Usable as
a frame; not as a measurement.

**Three cautions travel with it.** The dimensions are not independent, and the
dependency runs straight through this question: **simple texts are somewhat
longer, and stimulating additions lengthen them too**, so brevity trades against
the two dimensions the model rates most valuable. Schulz von Thun's counter is
that roughly 75% of each dimension's variance is independent. The 18 contrast
pairs behind the original factor analyses were compiled ad hoc, with the counter
that the final model no longer rests strictly on them. And the studies do not
separate understanding from remembering, so some of the measured gain may be
retention rather than comprehension.

**One difference from this repo's practice, stated because it is inconvenient.**
The Hamburg authors deliberately declined to give concrete action instructions,
judging that such rules would have to be too numerous to stay practical, and
relied on model texts instead. Rule 7 (§ 5.3) is exactly the kind of instruction
they declined to write.

## 5. The author-side test

### 5.1 Why the author is the only checkable party at writing time

The reader is absent when the text is written. The author's grasp is present.
That is the whole argument for putting the test on the author.

**The channel property behind that argument has a name.** Abbaschian (2026),
"Cross-Disciplinary Taxonomy and Modeling of Misunderstanding Generation,
Amplification, and Detection", arXiv:2608.13604, separates the *materiality* of a
divergence from its **recoverability** — whether the interaction produces evidence
of the divergence, whether that evidence is observable to either party, and
whether feedback and repair are available. Durable prose is a low-recoverability
channel: no back-channel, no puzzled expression, and the reader's difficulty
surfaces months later as a trace tag if at all (§ 6.2). The same paper notes that
failures to adapt "vocabulary, form, or level of detail" to the reader are
**production-side**, and so "harder to identify than listener interpretations".
**[Single-author preprint, read in part; a taxonomy, not evidence. Cited for the
distinction it names, not for a finding.]**

### 5.2 The mechanism: the explanation attempt exposes the gap

Rozenblit & Keil (2002), "The misunderstood limits of folk science: an illusion
of explanatory depth", *Cognitive Science* 26(5), 521–562. **[Verified, read in
full — the one source in this document that was.]** Twelve studies: 1–4 document
the illusion for devices across populations, 5–6 test its robustness, 7–10 track
it across knowledge domains, 11–12 examine what drives it.

**The design is the test this document proposes, run as an experiment.**
Participants rate their understanding of an item on a 7-point scale (T1), write a
detailed step-by-step causal explanation, and re-rate (T2); T3 follows a
diagnostic question, T4 a re-rating after reading an expert explanation, T5 a
manipulation check. Ratings fall: Study 1 (16 Yale graduate students)
F(4, 56) = 16.195, p < .001, η² = .536; Study 2 (33 undergraduates)
F(4, 124) = 38.9, p < .001, η² = .555; combined F(4, 188) = 44.11, p < .001, with
no interaction between studies. In Study 5 the means run T1 3.89 → T2 3.10 →
T3 2.49.

**The drop is a correction, not a loss of nerve.** Independent raters scored the
participants' own T2 explanations, and their scores were significantly *lower*
than the participants' self-ratings at T1 and T2 but **not different from T3 and
T4**. The explanation attempt moves the author's self-assessment to where a
disinterested reader already was.

**This is metacognition research, not learning research** — a self-assessment
failure that holds for anyone explaining anything, authors included.

**The qualification is what makes it bite here, and it is measured rather than
asserted.** From the abstract: "The illusion is far stronger for explanatory
knowledge than many other kinds of knowledge, such as that for facts, procedures
or narratives." Studies 7–10 supply the contrast: **no decrease in knowledge
ratings for procedures or narratives, and a significantly smaller drop for
facts.** ADR rationale, spec reasoning and research argument are explanatory
prose, and are what this repo writes most.

**One of their four proposed mechanisms is the repo's situation exactly.** The
authors name *rarity of production*: "we rarely give explanations and therefore
have little information on past successes and failures", against facts and
procedures where past performance is easy to inspect. An author who states a
section's core claim is manufacturing precisely the missing feedback.

**The shape undigested writing takes** is described independently, and by
criteria specific enough to apply. Bereiter & Scardamalia (1987), *The Psychology
of Written Composition*, characterise **knowledge-telling** by four marks: the
task is globally reduced to "tell what I know about this topic"; text is
generated sentence by sentence from local associative cues rather than from
higher goals; planning and revision are minimal; and content is not restructured
for purpose, audience or genre. Their contrast is
**knowledge-transforming**, in which the writer moves iteratively between a
content problem space and a rhetorical one, reshaping both. **[Search-summary,
but the four marks are the authors' own criteria rather than a summariser's
gloss.]**

*Inference, not their claim:* prose that lists everything true about a subject in
discovery order conforms to the knowledge-telling marks, and an author can check
their own draft against them. **Their caution applies to that inference**: these
are models of a *process*, not types of person, so a passage "conforms more
closely to knowledge-telling" — no one is a knowledge-teller.

**Bound, stated because the temptation runs the other way.** Adjacent work is
learning research — the self-explanation effect (Bisra, Liu, Nesbit, Salimi &
Winne, 2018, g = .55 over 69 effect sizes from 64 reports), the Feynman
technique, Bloom's taxonomy, the protégé effect. Its outcome measures are
learning gains in students. Only the metacognitive core transfers: **the attempt
to state a thing plainly is a test the author can fail, and failing it is
informative about the author.** Nothing pedagogical is carried into any repo rule.

### 5.3 The test, as it ships

[`CONTENT-RULES.md` Rule 7](../CONTENT-RULES.md#kernsatz): a new or substantially
rewritten section in `sdd/` or `.claude/` opens with its core claim in at most
three sentences, using no term it does not define on the spot; if those sentences
will not come, the section is not yet understood and the author returns to the
source.

**What it does and does not claim.** It detects an author who cannot state the
claim. It says nothing about whether any reader was harmed, and it is not
evidence that shorter prose is better prose.

## 6. The reader-side instruments, and what each reaches

### 6.1 What each one reaches

| Instrument | Detects | Cannot detect |
|---|---|---|
| Reader test (`documentation-expert.md`) | A question the page promises and cannot answer | An answer that arrived buried; anything `misleading`, since a no-context reader has nothing to check against |
| Trace `outcome` tags + `report-trace-outcomes` | Reader failure after the fact, ranked by document | Anything before the document ships; the difference between too much and too little |
| Review rounds | The **cost** of unresolved prose | Whether a reader was ever harmed |

Each row's right-hand column is the reason § 9 does not propose closing the loop
with these alone. The Appendix reports the one experiment that puts a number on
the first row's blind spot.

### 6.2 What the trace corpus actually shows

`hatch run report-trace-outcomes` at `f7eb5b7`: 296 traces, 4531 steps, 2272
carrying an explicit outcome (50.1%), **267 negative tags (227 `misleading`, 40
`unclear`)**. Reading all 40 `unclear` extracts, the dominant failure is a
**missing** unit, not a buried one — "the row did not ask the question that
mattered", "no row covers a change to a skill's frontmatter", "says nothing about
placement", "does not ask about inbound references". None describes an answer that
was present but hard to find. **The repo's most direct measurement of reader
failure evidences undershoot, not overshoot.**

*The figures are pinned to a commit because the corpus grows with every trace, so
re-derive rather than quote.* Totals: the command above. The reading behind them:
load each `sdd/traces/[!_]*.yml`, collect every step whose `outcome` is `unclear`,
and read its `extract`.

### 6.3 What the round data shows, and its two limits

A script over `sdd/traces/[!_]*.yml` reading each file's first `review_rounds:`
line, at `f7eb5b7`: 232 of 296 traces carry the field, **median 2, mean 2.48,
maximum 13**, with **36 traces (15.5%) at five or more**. Pinned for the same
reason as § 6.2. The long-round tail is where prose rounds accumulate — BUG-248 at
8, whose first three to four rounds changed behaviour and whose remainder moved
ADR wording, docstrings, pointers and counts (derivation: its commit subjects read
against each round's body).

**Limits.** `review_rounds` counts rounds and never their content, so the
code-versus-prose split is not derivable from the corpus; it was read by hand for
one item. And the corpus spans the project's whole history, most of it predating
the current review loop.

**The mechanism generalises even where the measurement does not.** A code finding
runs out — there are finitely many wrong call sites. A prose finding never runs
out, because any text can be tightened and nothing bounds the request.

## 7. Figures and their derivations

Per [`CLAUDE.md` principle 9](../../CLAUDE.md#principles), each claim names how it
was obtained. **Two axes, because they come apart**: *tier* is how well the claim
is evidenced, *transfers here* is how far it reaches this repo's prose. A study of
electrical apprentices reading wiring diagrams can be well-evidenced and transfer
poorly (row 8); a repo-derived row can be weak evidence about texts in general and
apply directly here (row 22c).

**Tier** — how the claim was obtained: **verified** (adversarial vote against a
retrieved abstract or metadata record, or a source read in full where the row says
so), **secondary** (a non-primary account of a primary, read in full),
**search-summary** (a search engine's synthesis of secondary sources), **local**
(derived from this repo, reproducible by the named command), **inference** (this
document's reasoning, never a source's claim). Only rows 8, 8a–8e, 9–9c, 11–11a
and 12–12a rest on a document read in full; everything else external comes from an
abstract or a summary.

**Transfers here** — how far the claim reaches this repo's prose. *High*: the
claim is about readers doing what this repo's readers do. *Medium*: the mechanism
plausibly carries but the material or task differs. *Low*: the finding is real and
the setting is far enough away that it is a lead, not a warrant.

**Confidence** — how likely the claim is *true*, which is independent of whether it
applies here. Row 8 is Medium-high confidence and Low transfer: the apprentices
result is solid and the setting is remote. The tier sets the ceiling, and a row
goes above it only for a reason the table names:

| Tier | Ceiling | Raised to | When |
|---|---|---|---|
| Source read in full | High | — | — |
| Verified against an abstract or record | Medium-high | High | The retrieved text *is* the claim — a quoted maxim, a stated thesis (rows 1, 2) |
| Secondary read in full | Medium | Medium-high | Two independent secondaries agree (rows 9–9c) |
| Search summary | Low-medium | Medium | The row carries the authors' own criteria rather than a summariser's gloss (row 13) |
| Local, reproducible by the named command | High | — | — |
| Local, read by hand | Medium | — | — |
| Local, a single observation | Low | — | — |
| Inference | no value | — | — |

**One row goes the other way.** Row 4 is verified and sits at Medium, not
Medium-high: it is a *negative* finding, and § 8.2's blocked access makes absence
of evidence weak evidence of absence.

| # | Claim | Tier | Transfers here | Confidence |
|---|---|---|---|---|
| 1 | Adequacy is indexed to purpose and stage (Grice) | Verified | High | High |
| 2 | Adequacy is indexed to addressee knowledge (Nickerson) | Verified | High | High |
| 3 | Curse of knowledge predicts under-specification | Verified | Medium | Medium |
| 4 | No direct evidence that surplus on-topic detail conceals a claim in prose | Verified | Medium | Medium |
| 5 | Seductive detail covers interesting-and-irrelevant material only | Verified | Medium | Medium |
| 6 | McNamara et al. (1996) manipulated coherence, not surplus detail | Verified | Low | Medium |
| 7 | Carroll et al. (1987) is a four-way bundle, not a brevity result | Verified | Medium | Medium |
| 8 | Kalyuga et al. (1998): text essential and best integrated for novice apprentices, redundant and best **fully eliminated** for experienced ones; elimination is its own condition, not confounded with integration | Verified against the co-authored 1998 review, read in full | Low | Medium-high |
| 8a | The same review reads McNamara et al. (1996) as redundancy rather than active processing, because mental-effort ratings **rose** where the active-processing account predicts a fall | Verified against that review | Low | Medium |
| 8b | Reder & Anderson (1980, 1982): textbook chapters against summaries one-fifth as long; summary readers scored significantly higher on the main points, across delays up to a year and several test types | Verified against Charney, Reder & Wells (1988), read in full; an author reporting her own studies | Medium | Medium-high |
| 8c | With study time on the main points equated, summary readers still won, so the handicap is retrieval as well as encoding; the authors add that elaborations "may make it harder for readers to distinguish important points from unimportant ones" | Same | Medium | Medium |
| 8d | Study 1: task-directed readers did better with the short manual, goal-less readers far worse with it — and the goal-less readers were the more greatly impeded of the two | Same | High | Medium-high |
| 8e | Study 2: procedural (worked-example) elaboration decided performance; **conceptual elaboration made no difference at all**, for novices or experienced users | Same | Medium | Medium-high |
| 9 | *Kürze/Prägnanz*'s optimum sits between `0` and `+`; both extremes impede comprehension | Two secondary sources read in full, in agreement; book unread | Medium | Medium-high |
| 9a | It is the only **unconditional** mid-scale optimum; *anregende Zusätze* is mid-scale but conditional on the other dimensions | Same | Medium | Medium |
| 9b | The four dimensions were validated against reader performance — 28 texts in two versions, 1,100+ readers, no effect for about a quarter of texts — but no study varied length alone, so the optimum is a recommendation, not a measured curve | Same | Low | Medium |
| 9c | The dependency runs through this question: simple texts are somewhat longer, and stimulating additions lengthen them too | Same | Medium | Medium |
| 10 | Groeben's interactional turn; Göpferich keeps the Hamburg four, adds *Korrektheit* and *Perzipierbarkeit*, reframes on the communication situation | Search-summary | Medium | Low-medium |
| 11 | Hamburg dimensions not independent (Schulz von Thun: ~75% of each dimension's variance is); contrast pairs ad hoc; understanding not separated from retention | Secondary, read in full | Low | Medium |
| 11a | The Hamburg authors deliberately gave no concrete action instructions, relying on model texts — the opposite of Rule 7's approach | Secondary, read in full | Medium | Medium |
| 12 | Rozenblit & Keil: the explanation attempt lowers self-rated understanding across 12 studies, and moves it to where independent raters already scored it | **Verified, read in full** | High | High |
| 12a | The same: **no** drop for procedures or narratives, a significantly smaller drop for facts, so the effect is specific to explanatory knowledge | **Verified, read in full** | High | High |
| 13 | Bereiter & Scardamalia: knowledge-telling marked by task reduced to "tell what I know", local sentence-by-sentence generation, minimal planning and revision, and no restructuring for purpose or audience — and these are models of a process, not types of writer | Search-summary, but stated as the authors' criteria | Medium | Medium |
| 14 | Bisra et al. (2018): self-explanation g = .55, 69 effect sizes from 64 reports | Search-summary | Low | Low-medium |
| 15 | Rhetorical Structure Theory (RST) analyses a text as a tree of nucleus–satellite relations, where the nucleus carries the essential content. Annotator agreement on its reference corpus, the RST Discourse Treebank, runs 86.8 / 80.7 / 72 percent over six taggers, from the 2003 LDC corpus documentation rather than the 2001 workshop paper (which reports kappas) | Search-summary | Low | Low |
| 15a | Abbaschian (2026): *recoverability* — whether an interaction produces observable evidence of divergence and allows repair — is distinct from a divergence's size; adapting level of detail is a production-side failure and harder to detect than a reader's misreading | Preprint, read in part; taxonomy, not evidence | Medium | Low |
| 16 | Relevance is comparative, not a quotient | Search-summary | Low | Low-medium |
| 17 | Macrorules are comprehension rules, not an editing procedure | Search-summary | Low | Low |
| 18 | Verbosity bias is a property of raters, not evidence of reader harm | Search-summary | Low | Low |
| 19 | Repo at `f7eb5b7`: 267 negative trace tags, and all 40 `unclear` extracts name a missing unit rather than a buried one | Local | High | High |
| 20 | Repo at `f7eb5b7`: 232 of 296 traces carry `review_rounds`; median 2, mean 2.48, max 13; 36 (15.5%) at ≥5 | Local | High | High |
| 21 | Repo: BUG-248's eight rounds split roughly three-to-four behavioural, rest prose | Local, one item | Medium | Medium |
| 22 | Repo: **four** volume decisions taken with no authoring rule to cite — two litigated at backlog level (BK-351 declining a 5,000-word budget; BK-353 condensing `/ship`, its first cut silently deleting two load-bearing clauses) and two made in review (`bk-313-sftp-roundtrips.yml:176`, a CHANGELOG entry "grown into a verbose paragraph"; `BK-280-ci-build-improvements.yml:92,96`, an entry "too chatty" and comments "too long"). Derivation: `git grep -il` for each ID over `sdd/`, then reading the four extracts | Local | High | High |
| 22a | Repo experiment: whole against condensed ripple-check, 12 agent readers, 120 answers — obligations tied 42–42 after a 66% cut; rationale lost 12–0; zero invented answers on either page | Local, pre-registered | Medium | High for the tally, low for its reach |
| 22b | The extra material was misused only by readers who had both the whole page and advance knowledge of the question (2 of 3) | Local, discovered in data | Low | Low — hypothesis for a dedicated run |
| 22c | Rationale explaining what the reader can see is recoverable after cutting; rationale carrying an outside fact is not | Local | Medium | Medium |
| 22d | One expert human reader of the condensed page recovered less than any naïve agent reader and produced the study's only wrong answer | Local, n = 1, unblinded | Low | Low as evidence; high as a caution about who a reader test measures |
| 23 | Knowledge-telling describes this repo's overshooting prose | Inference | — | — |
| 24 | The illusion of explanatory depth applies to authors of explanatory prose | Inference | — | — |

**Unresolved rather than answered:** whether trained annotators agree well enough
for any discourse-structure rule to be usable. Every claim in that cluster was
voted down on sourcing, so nothing about RST can be asserted in either direction
beyond row 15.

**Never reached:** Zwaan & Radvansky's situation-model dimensions, defensible
modern working-memory claims, Pyramid/SCU reproducibility, and Daneš's
thematic-progression typology.

## 8. Where the evidence breaks

Three kinds of break, in descending order of how much they cost the argument:
proposals that look like answers and are not, an access limitation that weakens
every external row, and the bounds on the one experiment run here.

### 8.1 What does not answer the question

| Proposal | Why it fails |
|---|---|
| Readability formulas, word budgets | Surface proxies; blind to purpose and reader (§ 1) |
| Rhetorical Structure Theory: "keep nuclei, delete satellites" (§ 7 row 15 defines the terms) | Rests on a label trained annotators agree on about four times in five: 86.8% spans, **80.7% nuclearity**, 72% relations over six taggers. Provenance matters here, because the figures are widely quoted without it: they come from the **corpus documentation accompanying the LDC release** (Carlson, Marcu & Okurowski, 2003, LDC2002T07), not from the 2001 workshop paper, which reports kappa statistics instead, and not from the LDC catalogue entry, which carries no agreement figures at all. **[Search-summary; the documentation itself is unread here]** |
| Kintsch & van Dijk's macrorules as an editing procedure | They model what readers do, not what authors should cut. **[Search-summary]** |
| Relevance ≈ cognitive effect ÷ processing effort | Sperber and Wilson operate a **comparative** notion and distinguish it from a quantitative one; the quotient is a popularization. **[Search-summary]** |
| Verbosity bias in LLM judges | Establishes that *raters* over-reward length, not that verbose output harms a reader's task. **[Search-summary]** |
| Seductive-detail research as a general cutting licence | Covers interesting-**and**-irrelevant material whose mechanism depends on grabbing attention. Bland, on-topic surplus is a different class |
| The minimal manual as proof that cutting works | Carroll, Smith-Kerker, Ford & Mazur-Rimetz (1987), *Human-Computer Interaction* 3(2): the manual differs from its comparator on **four** dimensions at once — briefer, better attention coordination, error-recovery training, better reference support. It shows one package beating another, not that deleting detail is what did it. Charney, Reder & Wells reach the same verdict independently: Carroll's team "clarified the terminology and organized the discussion around typical situations", so "we do not know how much the results are due to differences in elaboration and how much they are due to these other clarifications". **[Verified twice]** |

### 8.2 The access limitation

Every scholarly host tried returned 403 on CONNECT from this environment's egress
proxy: `aclanthology.org`, `doi.org`, `www.semanticscholar.org`,
`api.crossref.org`, `api.openalex.org`, `journals.uic.edu`, `www.pedocs.de`,
`en.wikipedia.org`, and on retest `arxiv.org`, `pmc.ncbi.nlm.nih.gov`,
`tecfa.unige.ch`, `core.ac.uk` and `cogdevlab.yale.edu`. Derivation: the agent
proxy's status endpoint (`curl -sS "$HTTPS_PROXY/__agentproxy/status"`; the port
is session-local, so the literal URL is not reproducible), plus direct retests.
The proxy's README classifies 403 as an organization policy denial to be reported
rather than worked around.

**What that costs this document.** Apart from the five sources named below, no
source was read in full, so no figure taken from an external source should be
quoted as established, and a negative finding obtained under blocked access is
weak evidence of absence. The repo-derived rows (19–22d) carry no such
limitation and are reproducible by the commands named.

**The exceptions, and the route around the blockade.** Five documents were
supplied directly by the maintainer and read in full, and each carries one part
of the argument:

| Source | Carries | Note |
|---|---|---|
| Rozenblit & Keil (2002) | § 5.2 and rows 12, 12a — the mechanism the shipped rule rests on | The one primary read in full |
| Sweller, van Merriënboer & Paas (1998) | § 3's expertise reversal and rows 8, 8a, 8b | Supplied as Kalyuga, Chandler & Sweller (1998), *Human Factors* 40(1); it is a different paper, the CLT review in *Educational Psychology Review* 10(3), sharing one author. It describes the target study in enough detail to settle row 8; the target itself is unread |
| Charney, Reder & Wells (1988) | § 2 entire, § 3's detail-kind input, rows 8b–8e | Supplied in place of Reder & Anderson (1980, 1982), whose studies Reder reports there along with the later manual experiments. The most consequential source here after § 5.2's |
| German Wikipedia, *Hamburger Verständlichkeitsmodell* | § 4, with the row below | An encyclopaedia article is a lead rather than an authority by this document's own method, so § 4's rows are tiered secondary and the book stays on § 10's list |
| Kroop, Mangler, Hutterer & Swertz, on comprehensibility training at the University of Vienna | § 4's validation studies and standing criticisms | Agrees with the row above on the optimum and the scale |

**That is the working route for anything else in § 10: the environment cannot
fetch, but it reads what it is handed.**

### 8.3 The bounds on the local experiment

Three readers per cell, LLM readers rather than humans, a grader not blind to
condition, and both cells open-book. It is a hypothesis-generating study of one
page, and the Appendix states that before reporting any number from it. Rows 22a
through 22d carry the tiers; §§ 9.2 and 9.6 are labelled **Pilot** for this
reason.

## 9. Proposals

Six, at three levels of maturity. **Adopt** means the evidence supports acting on
it now. **Pilot** means the idea is sound and the evidence is one page or one run
— act on it as an experiment, not as a rule. Each names the section that forces
it, because a proposal without a citation is a preference.

**9.1 Keep the control on the author, and put no length rule beside it.
[Adopt — in force.]**

[Rule 7](../CONTENT-RULES.md#kernsatz) already ships. The case for it being the
only rule of its kind is three-part: § 1 rules out every text-level instrument,
§ 4 puts the brevity optimum mid-scale rather than at the floor, and § 5.1 leaves
the author as the only party present at writing time.

**9.2 Cut rationale only when the surviving section can recover it. [Pilot.]**

Cut rationale divides in two, and only one half is safe to remove. Readers
rebuilt rationale explaining something the surviving text still shows; none
rebuilt rationale carrying a fact from outside the section (Appendix). Rule 7
gives both the same licence today.

*Provisional test, because "recoverable" is otherwise just an author's assertion.*
Before removing a rationale, answer three questions:

1. What decision or action does this section support?
2. Which surviving sentence, command or example supplies the reason?
3. What becomes wrong if the removed material is absent?

**No answer to (2) means the rationale is not recoverable: move it rather than
delete it.** Evidence: three readers, one page, one probe (§ 7 row 22c). § 10
item 5 names the run that would confirm or break it.

**9.3 Test conceptual elaboration for redundancy first, and keep the conceptual
material that decides scope. [Adopt as a heuristic.]**

Procedural richness decided every measure in Charney, Reder & Wells's Study 2 and
conceptual elaboration decided none (§ 3, row 8e). So when a section must be
reduced, the sentences explaining what a thing is *for* are tested first, and
worked examples, exact commands and identifiers are kept.

**The bound is where this repo differs from their manual.** Their conceptual
elaboration re-described a command the reader had already been given. Conceptual
material that fixes **scope, applicability, a constraint, an exception or a choice
between alternatives** does work theirs did not, and it is kept on the same
footing as an example. Cutting it is the undershoot § 2 warns about, arriving
disguised as this proposal.

**9.4 A prose review finding names the reader harm it prevents, or it is a
preference. [Adopt.]**

A code finding runs out and a prose finding does not (§ 6.3), so an unbounded
licence to tighten converts directly into the round tail that section measures.
Three harms qualify: a question the reader cannot answer, a decision they would
get wrong, an action they cannot execute.

*The form that makes it checkable* — a finding states reader, task, the failure,
the harm, the change, and what must survive the change:

> **Reader:** a maintainer adding a backend.
> **Task:** find out what the change owes the conformance suite.
> **Failure:** the obligation is stated, but not which suite file carries it.
> **Harm:** they ship without the fixture and CI fails on a path they cannot map.
> **Change:** name the file in the obligation row.
> **Preserve:** the exception for read-only backends.

"This could be tighter" fills none of those lines, which is the point. § 2 supplies
the other half of the argument: a rule that only cuts is aimed at the direction
with the weaker evidence.

**9.5 Set the licence by reader purpose, with the directory as its default proxy.
[Adopt, cautiously.]**

Cutting helped the reader who arrived with a task and hurt the reader who did not
(§ 2), so purpose is the variable and the directory only stands in for it.
Defaults: **task-oriented documents are candidates for stronger compression;
exploratory, onboarding and public reference documents need stronger
justification before context is removed.** Mapped onto this repo, that makes the
licence strongest in `sdd/` and `.claude/` and weakest in `docs-src/` and the
README — the reverse of the intuition that internal notes may sprawl while
published prose must be tight.

**The proxy fails in both directions and should be overridden when it does.** An
API reference page is public and highly task-directed; an internal design record
is often read by someone with no specific question.

**9.6 Run the reader test in pairs, or do not read it as a density instrument.
[Pilot.]**

A single-version reader test detects an unanswerable question and says nothing
about surplus (§ 6.1). A paired run — the same page whole and condensed, graded
against a key written first — produced a tie on obligations and a complete loss
on rationale, two numbers neither version yields alone. Record who the reader is:
the one expert human in that run recovered less than any naïve agent reader
(§ 7 row 22d), so a reader test staffed by people who already know the page
measures their engagement rather than the page. Not yet adopted because a paired
run costs twice a single one and has been done once.

**The procedure the six compose into**, at authoring time and in order: state the
Kernsatz (§ 5.3); if it will not come, stop writing and return to the source;
then place what remains by `research-id-232`'s three-condition gate; then
classify each surviving unit as **keep / shorten / move / remove**, with 9.2, 9.3
and 9.5 deciding the last two. *Move* is the outcome that ties this question back
to placement, and it is how this repo's two litigated density disputes were
resolved (§ 7 row 22). **When placement and length conflict, § 2 decides: never
delete a load-bearing reason to reach a length.** Under-justification is the
failure with the better evidence.

**One caveat covering all six.** Rule 7 detects an author who cannot state a
claim; 9.2 through 9.6 decide *what* to cut once the claim is stated. Neither
answers whether a given reader was harmed, and § 6.1's right-hand column is the
standing reminder that this repo cannot currently find out.

## 10. What would settle the open half

1. **The non-linear reader, for humans.** No study in the literature tests
   someone *looking something up* in dense reference prose, which is how
   maintainers and API users actually read; the Hamburg corpus came closest with
   legal codes and insurance conditions (§ 4), but those readers still read
   linearly and were examined. The Appendix closes this for **agent** readers on
   one page of this corpus, and its result — a tie on obligations, total loss on
   rationale — is what a human run would have to confirm or break.
2. **Reder & Anderson (1980, 1982) in the original.** Their findings are now
   carried by an author's own later chapter (§ 2), so what the primaries would add
   is sample sizes, effect sizes and the exact time-equating design — not a
   different answer.
3. **Yeung, Jin & Sweller (1998)**, reported as finding the same expertise
   reversal using **text-comprehension** material rather than diagrams.
4. **Langer, Schulz von Thun & Tausch (1974) in full** — now a smaller question
   than it was. Two secondary sources agree on the optimum and on the validation
   studies (§ 4); what the book would add is whether the authors argue the
   mid-scale optimum from their own data or assert it from the model.
5. **A second paired reader run, on a page whose rationale carries outside
   facts.** § 9.2 rests on three readers and one page. The
   cheapest test that could break it is another whole-versus-condensed pair,
   chosen so that most of the cut rationale is of the non-recoverable kind, and it
   needs no external access.

**Answered, and no longer worth chasing:** whether any Kalyuga experiment
isolates text elimination from the integration manipulation. It does (§ 3). The
*Human Factors* primary would add sample sizes and effect sizes, not a different
answer. **Also answered:** whether a paired whole-versus-condensed reader test is
runnable here without external access. It is; the Appendix reports the run, and
item 5 above is its successor.

---

## Appendix: the ripple-check as a worked example

**This is a hypothesis-generating study of one page of this repository, not a
validation of any general theory of documentation.** Its two most useful findings
were discovered in the data rather than predicted, which is what makes them
hypotheses. Read every number below as scoped to this page, this question set and
these readers.

§ 10 records that no study in the literature tests a reader **looking something
up** rather than reading through and being examined. That reader was tested here,
on the ripple-check itself: two versions of the same page (3,255 words against
1,121, every trigger and obligation preserved), crossed with whether the reader
knew the questions before reading. Twelve agent readers, ten questions, 120
answers, graded against a key written before anyone ran.

**On what the page exists to answer, the two versions tied** — 42 of 42 each,
after setting aside one defective question that ten of twelve readers identified
as unanswerable in almost identical words. In this run, a 66% cut cost nothing on
the obligations the page carries.

**On the rationale the cut removed, none of the condensed-page readers recovered
it** — 12 answers against 0. And **no reader on either page invented an answer**:
the `misleading` class § 6.1 says the reader test cannot reach did not occur, on
either side.

Two findings the tally hides, both worth more than it:

**The extra material was misused exactly once, in one cell.** Two of three
readers who had the whole page *and* knew the question in advance answered it by
lifting a spec ID from a neighbouring row. Every goal-less reader of the same page
refused, saying it would conflate rows; so did every reader of the condensed page,
which carries both rows too. The information is identical; what differs is that
elaboration makes the row boundary less visible to a reader hunting for something.
That is Reder & Anderson's mechanism (§ 2) occurring locally — on a sample of
three, on one question, found in the data rather than predicted. A hypothesis for
a dedicated run, not a result.

**Cut rationale divides into two kinds.** Three condensed-page readers rebuilt
half of one probe from the command it described: the command searches two
phrasings, so a single phrase would obviously miss the other. None could rebuild
the half that depends on a `.gitignore` fact the page never shows. **Rationale
explaining what the reader can already see is cheap to cut; rationale carrying a
fact from elsewhere is not.** Rule 7 does not currently make that distinction,
which is what § 9.2 asks it to fix.

**Exploratory observation, n = 1.** One human reader, an expert already familiar
with the page, also took the condensed version. He recovered less than any naïve
agent reader did — twice marking unanswerable a question the page answers — and
produced the study's only wrong answer, confidently and unhedged, where 120 agent
answers had produced none. The reading that fits is engagement rather than
comprehension: an expert answers from recall rather than from the page, and recall
is where the illusion of explanatory depth (§ 5.2) does its work. **This cannot
support any conclusion about human versus agent readers**: one reader, unblinded,
and not a fair contest, since the agents were compelled to read the page and the
human was not. It is kept as a caution about who a reader test measures.

**Bounds:** three readers per cell, LLM readers rather than humans, a grader not
blind to condition, and both cells open-book so no memory effect is in view.

## Sources

No URLs are given: every scholarly host is blocked from this environment (§ 8.2),
so a link here would be one this document could not itself follow. The grouping
is by how each source was read, which is the fact a reader needs in order to
weight it.

**Read in full, supplied as documents by the maintainer:**

- Rozenblit, L. & Keil, F. (2002). "The misunderstood limits of folk science: an
  illusion of explanatory depth." *Cognitive Science* 26(5), 521–562.
- Sweller, J., van Merriënboer, J. & Paas, F. (1998). "Cognitive Architecture and
  Instructional Design." *Educational Psychology Review* 10(3), 251–296.
- Charney, D., Reder, L. & Wells, G. (1988). "Studies of Elaboration in
  Instructional Texts." In S. Doheny-Farina (ed.), *Effective Documentation: What
  We Have Learned from Research*, MIT Press, 47–72.
- *Hamburger Verständlichkeitsmodell*, German Wikipedia article (secondary
  account of Langer, Schulz von Thun & Tausch 1974).
- Kroop, S., Mangler, J., Hutterer, R. & Swertz, C. Paper on comprehensibility
  training at the University of Vienna (secondary account of the same model).

**Read in part:**

- Abbaschian, B. (2026). "Cross-Disciplinary Taxonomy and Modeling of
  Misunderstanding Generation, Amplification, and Detection." arXiv:2608.13604.

**Cited from an abstract, a metadata record or a search summary** — directional
only, per § 7's tiers:

- Grice, H. P. (1975). "Logic and Conversation." In Cole & Morgan (eds.),
  *Syntax and Semantics 3: Speech Acts*.
- Nickerson, R. (1999). "How We Know — and Sometimes Misjudge — What Others Know:
  Imputing One's Own Knowledge to Others." *Psychological Bulletin* 125, 737–759.
- Groeben, N. (1982). *Leserpsychologie: Textverständnis — Textverständlichkeit*.
- Göpferich, S. *Karlsruher Verständlichkeitskonzept*.
- Langer, I., Schulz von Thun, F. & Tausch, R. (1974). *Sich verständlich
  ausdrücken*. (The book itself: unread — see § 10 item 4.)
- Kalyuga, S., Chandler, P. & Sweller, J. (1998). *Human Factors* 40(1). (Unread;
  reached through the 1998 review above.)
- Reder, L. & Anderson, J. (1980, 1982). (Unread; reached through Charney, Reder
  & Wells 1988.)
- McNamara, D., Kintsch, E., Songer, N. & Kintsch, W. (1996). The reverse
  cohesion effect.
- Carroll, J., Smith-Kerker, P., Ford, J. & Mazur-Rimetz, S. (1987). The minimal
  manual. *Human-Computer Interaction* 3(2).
- Bereiter, C. & Scardamalia, M. (1987). *The Psychology of Written Composition*.
- Bisra, K., Liu, Q., Nesbit, J., Salimi, F. & Winne, P. (2018). Meta-analysis of
  the self-explanation effect.
- Carlson, L., Marcu, D. & Okurowski, M. E. (2003). RST Discourse Treebank
  corpus documentation, LDC2002T07.
- Kintsch, W. & van Dijk, T. (1978). Macrorules for discourse comprehension.
- Sperber, D. & Wilson, D. (1986). *Relevance: Communication and Cognition*.
- Brinker, K. *Textsorte / Textfunktion*.
- Yeung, A., Jin, P. & Sweller, J. (1998). (Unread — see § 10 item 3.)

**Derived from this repository**, reproducible by the commands named in §§ 6–7:
`hatch run report-trace-outcomes` at `2bbb802`; the `review_rounds` scan over
`sdd/traces/[!_]*.yml`; BUG-248's commit subjects; BK-351 and BK-353; and the
pre-registered reader experiment reported in the Appendix.
