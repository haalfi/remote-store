# Research: Is the level of detail appropriate?

**Date:** 2026-08-17
**Backlog items:** ID-256, which shipped the authoring test in § 5.3.
**Status:** Advisory research, not a spec or ADR. A standing reference on one
question — *is the level of detail appropriate?* — rather than a record of how it
was investigated.
**Related:**
[`research-id-232-detail-placement-durability.md`](research-id-232-detail-placement-durability.md)
answers the neighbouring question, *where does this detail belong?*;
[`../CONTENT-RULES.md`](../CONTENT-RULES.md) carries the rules this document
argues for.

> **Appropriateness is not a property of a text.** It is a relation between the
> text, the reader's purpose and knowledge, and the author's grasp of the
> subject. Of those three, only the last can be checked at the moment of writing,
> which is why the practical rule is an author-side test and not a length budget.
>
> **Standing caveat: five sources have been read in full, and one of them is a
> primary.** Rozenblit & Keil (2002), the mechanism the authoring test rests on
> (§ 5.2); Sweller, van Merriënboer & Paas (1998) and Charney, Reder & Wells
> (1988), each describing experiments their own authors ran (§§ 2–3); and two
> secondary accounts of the Hamburg model (§ 4). All were supplied by the
> maintainer. Every other external claim rests on an abstract, a metadata record
> or a search summary, because every scholarly host returns 403 from this
> environment (Appendix B). Each carries a tier: treat the rest as directional,
> and the repo figures as the reliable half.

---

## 1. Why the question has no text-level answer

Four traditions arrive independently at the same shape: adequacy is indexed to
something outside the text.

| Source | What it indexes adequacy to |
|---|---|
| Grice (1975), "Logic and Conversation" | The purpose and **stage** of the exchange: "such as is required, at the stage at which it occurs" |
| Nickerson (1999), "How We Know — and Sometimes Misjudge — What Others Know: Imputing One's Own Knowledge to Others", *Psychological Bulletin* 125, 737–759 | What **this specific addressee** already knows. Cite it by title: a different Nickerson paper of the same year and volume ("Enhancing creativity", 683–732) is easily substituted, and was, by one external review of this document |
| Groeben (1982), *Leserpsychologie* [*Reader Psychology*] | Comprehensibility as **text × reader interaction**, explicitly not a text property |
| Göpferich, Karlsruher Verständlichkeitskonzept | Keeps the Hamburg four (as *Struktur*, *Simplizität*, *Motivation*, *Prägnanz*), **adds *Korrektheit* and *Perzipierbarkeit***, and reframes the whole around the **communication situation and the text's communicative function** — the correction to the Hamburg model's *textzentriert* [text-centred] perspective |

**[Grice and Nickerson: verified. Groeben and Göpferich: search-summary.]**

**The consequence is negative and worth stating first, because it rules out the
instruments people reach for.** No word budget, readability index or density
metric can answer the question, since none of them can see the reader's purpose
or knowledge. Readability formulas are the standing wrong turn: they measure
surface features that correlate with comprehension in aggregate and decide
nothing about a particular text for a particular reader.

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

**So the asymmetry this document previously reported has a better basis than the
one it was resting on.** It is no longer "overshoot is unevidenced": overshoot is
evidenced, for readers who know what they are looking for. What survives is the
practical asymmetry — **the penalty for cutting too much fell on the reader who
lacked a goal, and it was the larger of the two**. A rule that only cuts is aimed
at the case where cutting helps least and hurts most, which is why
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

**That answers the question this document previously left open.** Elimination is
not confounded with integration: the expert comparison is *diagram alone* against
*diagram plus integrated text*, so removal is its own condition and it wins.
Mental-effort ratings ran the same way — higher load for experienced learners
given the redundant version. The authors' own summary: "material that is
redundant for some learners and so best eliminated, may be essential for less
experienced learners and best integrated."

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

*Inference, applied to this repo:* worked examples and concrete specifics earn
their place; explanations of what a thing is for often do not, and are the first
place to look when a section has grown. That is a sharper instruction than "cut
detail", and it points at a different target than a length rule would.

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

**Correction to an earlier claim of this document.** It is not the *only*
mid-scale dimension. *Anregende Zusätze* [stimulating additions] typically also
sits between `0` and `+` — but its optimum is **conditional**: `−` or `−−` when
structure is weak, `0`/`+` or occasionally `++` when simplicity and structure are
strong. Brevity's mid-scale optimum is the only **unconditional** one, which is a
narrower and more useful claim than the one it replaces.

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

| Instrument | Detects | Cannot detect |
|---|---|---|
| Reader test (`documentation-expert.md`) | A question the page promises and cannot answer | An answer that arrived buried; anything `misleading`, since a no-context reader has nothing to check against |
| Trace `outcome` tags + `report-trace-outcomes` | Reader failure after the fact, ranked by document | Anything before the document ships; the difference between too much and too little |
| Review rounds | The **cost** of unresolved prose | Whether a reader was ever harmed |

### 6.2 What the trace corpus actually shows

`hatch run report-trace-outcomes` at `2bbb802`: 279 traces, 4052 steps, 1826
carrying an explicit outcome (45.1%), **223 negative tags (191 `misleading`, 32
`unclear`)**. Reading the `unclear` extracts, the dominant failure is a **missing**
unit, not a buried one — "the row did not ask the question that mattered", "no row
covers a change to a skill's frontmatter". **The repo's most direct measurement of
reader failure evidences undershoot, not overshoot.**

### 6.2a The one experiment this corpus could run

§ 9 records that no study in the literature tests a reader **looking something
up** rather than reading through and being examined. That reader was tested here,
on the ripple-check itself: two versions of the same page (3,255 words against
1,121, every trigger and obligation preserved), crossed with whether the reader
knew the questions before reading. Twelve agent readers, ten questions, 120
answers, graded against a key written before anyone ran.

**On what the page exists to answer, the two versions tied exactly** — 42 of 42
each, after setting aside one defective question that ten of twelve readers
identified as unanswerable in almost identical words. A 66% cut cost nothing.

**On the rationale the cut removed, the loss was total** — 12 answers against 0.
And **no reader on either page invented an answer**: the `misleading` class this
document keeps saying the reader test cannot reach did not occur, on either side.

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
fact from elsewhere is not.** Rule 7 does not currently make that distinction.

**One human reader also took the condensed page**, an expert already familiar
with it. He recovered **less** than any naïve agent reader did — twice marking
unanswerable a question the page answers — and produced **the only wrong answer
in the study**, confidently and unhedged, where 120 agent answers had produced
none. The mechanism is not comprehension but engagement: an expert answers from
recall rather than reading, and recall is where the illusion of explanatory depth
(§ 5.2) does its work. n = 1, unblinded, and not a fair contest, since the agents
were compelled to read the page and the human was not.

**Bounds:** three readers per cell, LLM readers rather than humans, a grader not
blind to condition, and both cells open-book so no memory effect is in view.

### 6.3 What the round data shows, and its two limits

A script over `sdd/traces/[!_]*.yml` reading each file's first `review_rounds:`
line: 219 traces carry the field, **median 2, mean 2.15, maximum 10**, with **24
traces (11.0%) at five or more**. The long-round tail is where prose rounds
accumulate — BUG-248 at 8, whose first three to four rounds changed behaviour and
whose remainder moved ADR wording, docstrings, pointers and counts (derivation:
its commit subjects read against each round's body).

**Limits.** `review_rounds` counts rounds and never their content, so the
code-versus-prose split is not derivable from the corpus; it was read by hand for
one item. And the corpus spans the project's whole history, most of it predating
the current review loop.

**The mechanism generalises even where the measurement does not.** A code finding
runs out — there are finitely many wrong call sites. A prose finding never runs
out, because any text can be tightened and nothing bounds the request.

## 7. What does not answer the question

| Proposal | Why it fails |
|---|---|
| Readability formulas, word budgets | Surface proxies; blind to purpose and reader (§ 1) |
| RST "keep nuclei, delete satellites" | Rests on a label trained annotators agree on about four times in five: 86.8% spans, **80.7% nuclearity**, 72% relations over six taggers. Provenance matters here, because the figures are widely quoted without it: they come from the **corpus documentation accompanying the LDC release** (Carlson, Marcu & Okurowski, 2003, LDC2002T07), not from the 2001 workshop paper, which reports kappa statistics instead, and not from the LDC catalogue entry, which carries no agreement figures at all. **[Search-summary; the documentation itself is unread here]** |
| Kintsch & van Dijk's macrorules as an editing procedure | They model what readers do, not what authors should cut. **[Search-summary]** |
| Relevance ≈ cognitive effect ÷ processing effort | Sperber and Wilson operate a **comparative** notion and distinguish it from a quantitative one; the quotient is a popularization. **[Search-summary]** |
| Verbosity bias in LLM judges | Establishes that *raters* over-reward length, not that verbose output harms a reader's task. **[Search-summary]** |
| Seductive-detail research as a general cutting licence | Covers interesting-**and**-irrelevant material whose mechanism depends on grabbing attention. Bland, on-topic surplus is a different class |
| The minimal manual as proof that cutting works | Carroll, Smith-Kerker, Ford & Mazur-Rimetz (1987), *Human-Computer Interaction* 3(2): the manual differs from its comparator on **four** dimensions at once — briefer, better attention coordination, error-recovery training, better reference support. It shows one package beating another, not that deleting detail is what did it. Charney, Reder & Wells reach the same verdict independently: Carroll's team "clarified the terminology and organized the discussion around typical situations", so "we do not know how much the results are due to differences in elaboration and how much they are due to these other clarifications". **[Verified twice]** |

## 8. The decision procedure this supports

**At authoring time**, in order: state the Kernsatz (§ 5.3); if it will not come,
stop writing and return to the source; then place what remains by
`research-id-232`'s three-condition gate; then classify each surviving unit as
**keep / shorten / move / remove**. *Move* is the outcome that ties this question
back to placement, and it is how both of this repo's real density disputes were
resolved.

**At review time**: a prose finding names the reader harm it prevents — an
unanswerable question, a wrong decision, an action that cannot be executed — or it
is a preference. This follows from § 2: a rule that only cuts is aimed at the
less-evidenced direction.

**When the two conflict**, § 2 decides: never delete a load-bearing reason to
reach a length. Under-justification is the failure with the better evidence.

## 9. What would settle the open half

1. **The non-linear reader, for humans.** No study in the literature tests
   someone *looking something up* in dense reference prose, which is how
   maintainers and API users actually read; the Hamburg corpus came closest with
   legal codes and insurance conditions (§ 4), but those readers still read
   linearly and were examined. § 6.2a closes this for **agent** readers on one
   page of this corpus, and its result — a tie on obligations, total loss on
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
5. **Locally and cheaply:** run the reader test against one page twice, whole and
   condensed, and compare unanswerable counts. The one experiment available
   without external access, and it tests overshoot directly on this corpus.

**Answered, and no longer worth chasing:** whether any Kalyuga experiment
isolates text elimination from the integration manipulation. It does (§ 3). The
*Human Factors* primary would add sample sizes and effect sizes, not a different
answer.

---

## Appendix A — evidence ledger

Tiers: **verified** (adversarial vote against a retrieved abstract or metadata
record), **search-summary** (a search engine's synthesis of secondary sources),
**local** (derived from this repo, reproducible by the named command),
**inference** (this document's reasoning, never a source's claim).

| # | Claim | Tier | Confidence |
|---|---|---|---|
| 1 | Adequacy is indexed to purpose and stage (Grice) | Verified | High |
| 2 | Adequacy is indexed to addressee knowledge (Nickerson) | Verified | High |
| 3 | Curse of knowledge predicts under-specification | Verified | Medium |
| 4 | No direct evidence that surplus on-topic detail conceals a claim in prose | Verified | High |
| 5 | Seductive detail covers interesting-and-irrelevant material only | Verified | Medium |
| 6 | McNamara et al. (1996) manipulated coherence, not surplus detail | Verified | Medium |
| 7 | Carroll et al. (1987) is a four-way bundle, not a brevity result | Verified | Medium |
| 8 | Kalyuga et al. (1998): text essential and best integrated for novice apprentices, redundant and best **fully eliminated** for experienced ones; elimination is its own condition, not confounded with integration | Verified against the co-authored 1998 review, read in full | Medium-high |
| 8a | The same review reads McNamara et al. (1996) as redundancy rather than active processing, because mental-effort ratings **rose** where the active-processing account predicts a fall | Verified against that review | Medium |
| 8b | Reder & Anderson (1980, 1982): textbook chapters against summaries one-fifth as long; summary readers scored significantly higher on the main points, across delays up to a year and several test types | Verified against Charney, Reder & Wells (1988), read in full; an author reporting her own studies | Medium-high |
| 8c | With study time on the main points equated, summary readers still won, so the handicap is retrieval as well as encoding; the authors add that elaborations "may make it harder for readers to distinguish important points from unimportant ones" | Same | Medium |
| 8d | Study 1: task-directed readers did better with the short manual, goal-less readers far worse with it — and the goal-less readers were the more greatly impeded of the two | Same | Medium-high |
| 8e | Study 2: procedural (worked-example) elaboration decided performance; **conceptual elaboration made no difference at all**, for novices or experienced users | Same | Medium-high |
| 9 | *Kürze/Prägnanz*'s optimum sits between `0` and `+`; both extremes impede comprehension | Two secondary sources read in full, in agreement; book unread | Medium-high |
| 9a | It is the only **unconditional** mid-scale optimum; *anregende Zusätze* is mid-scale but conditional on the other dimensions | Same | Medium |
| 9b | The four dimensions were validated against reader performance — 28 texts in two versions, 1,100+ readers, no effect for about a quarter of texts — but no study varied length alone, so the optimum is a recommendation, not a measured curve | Same | Medium |
| 9c | The dependency runs through this question: simple texts are somewhat longer, and stimulating additions lengthen them too | Same | Medium |
| 10 | Groeben's interactional turn; Göpferich keeps the Hamburg four, adds *Korrektheit* and *Perzipierbarkeit*, reframes on the communication situation | Search-summary | Low-medium |
| 11 | Hamburg dimensions not independent (Schulz von Thun: ~75% of each dimension's variance is); contrast pairs ad hoc; understanding not separated from retention | Secondary, read in full | Medium |
| 11a | The Hamburg authors deliberately gave no concrete action instructions, relying on model texts — the opposite of Rule 7's approach | Secondary, read in full | Medium |
| 12 | Rozenblit & Keil: the explanation attempt lowers self-rated understanding across 12 studies, and moves it to where independent raters already scored it | **Verified, read in full** | High |
| 12a | The same: **no** drop for procedures or narratives, a significantly smaller drop for facts, so the effect is specific to explanatory knowledge | **Verified, read in full** | High |
| 13 | Bereiter & Scardamalia: knowledge-telling marked by task reduced to "tell what I know", local sentence-by-sentence generation, minimal planning and revision, and no restructuring for purpose or audience — and these are models of a process, not types of writer | Search-summary, but stated as the authors' criteria | Medium |
| 14 | Bisra et al. (2018): self-explanation g = .55, 69 effect sizes from 64 reports | Search-summary | Low-medium |
| 15 | RST-DT agreement 86.8 / 80.7 / 72 percent over six taggers, from the 2003 LDC corpus documentation rather than the 2001 workshop paper (which reports kappas) | Search-summary | Low |
| 15a | Abbaschian (2026): *recoverability* — whether an interaction produces observable evidence of divergence and allows repair — is distinct from a divergence's size; adapting level of detail is a production-side failure and harder to detect than a reader's misreading | Preprint, read in part; taxonomy, not evidence | Low |
| 16 | Relevance is comparative, not a quotient | Search-summary | Low-medium |
| 17 | Macrorules are comprehension rules, not an editing procedure | Search-summary | Low |
| 18 | Verbosity bias is a property of raters, not evidence of reader harm | Search-summary | Low |
| 19 | Repo: 223 negative trace tags, dominated by missing units | Local | High |
| 20 | Repo: 219 traces carry `review_rounds`; median 2, mean 2.15, max 10; 24 at ≥5 | Local | High |
| 21 | Repo: BUG-248's eight rounds split roughly three-to-four behavioural, rest prose | Local, one item | Medium |
| 22 | Repo: two density disputes resolved ad hoc, one cut silently lossy (BK-351, BK-353) | Local | High |
| 22a | Repo experiment: whole against condensed ripple-check, 12 agent readers, 120 answers — obligations tied 42–42 after a 66% cut; rationale lost 12–0; zero invented answers on either page | Local, pre-registered | High for the tally, low for its reach |
| 22b | The extra material was misused only by readers who had both the whole page and advance knowledge of the question (2 of 3) | Local, discovered in data | Low — hypothesis for a dedicated run |
| 22c | Rationale explaining what the reader can see is recoverable after cutting; rationale carrying an outside fact is not | Local | Medium |
| 22d | One expert human reader of the condensed page recovered less than any naïve agent reader and produced the study's only wrong answer | Local, n = 1, unblinded | Low as evidence; high as a caution about who a reader test measures |
| 23 | Knowledge-telling describes this repo's overshooting prose | Inference | — |
| 24 | The illusion of explanatory depth applies to authors of explanatory prose | Inference | — |

**Unresolved rather than answered:** whether trained annotators agree well enough
for any discourse-structure rule to be usable. Every claim in that cluster was
voted down on sourcing, so nothing about RST can be asserted in either direction
beyond row 15.

**Never reached:** Zwaan & Radvansky's situation-model dimensions, defensible
modern working-memory claims, Pyramid/SCU reproducibility, and Daneš's
thematic-progression typology.

## Appendix B — the access limitation

Every scholarly host tried returned 403 on CONNECT from this environment's egress
proxy: `aclanthology.org`, `doi.org`, `www.semanticscholar.org`,
`api.crossref.org`, `api.openalex.org`, `journals.uic.edu`, `www.pedocs.de`,
`en.wikipedia.org`, and on retest `arxiv.org`, `pmc.ncbi.nlm.nih.gov`,
`tecfa.unige.ch`, `core.ac.uk` and `cogdevlab.yale.edu`. Derivation: the agent
proxy's status endpoint (`curl -sS "$HTTPS_PROXY/__agentproxy/status"`; the port
is session-local, so the literal URL is not reproducible), plus direct retests.
The proxy's README classifies 403 as an organization policy denial to be reported
rather than worked around.

**What that costs this document.** With one exception, no source was read in
full, so no figure taken from an external source should be quoted as established,
and a negative finding obtained under blocked access is weak evidence of absence.
The repo-derived rows (19–22) carry no such limitation and are reproducible by
the commands named.

**The exceptions, and the route around the blockade.** Two PDFs were supplied
directly by the maintainer and read in full: Rozenblit & Keil (2002), which moved
rows 12 and 12a from search-summary to verified and sharpened § 5.2 from an
assertion to a measured contrast; and Sweller, van Merriënboer & Paas (1998),
which settled the design question behind row 8 and produced two claims nothing
else in this pass had reached (rows 8a and 8b). That is the working route for
anything else in § 9: the environment cannot fetch, but it reads what it is
handed.

**Note on the second one.** It was supplied as Kalyuga, Chandler & Sweller (1998),
*Human Factors* 40(1), and is a different paper — the CLT review in *Educational
Psychology Review* 10(3), sharing one author. It happens to describe the target
study in enough detail to answer the question, which is why row 8 moved; the
target itself remains unread, and row 8's tier says so.

**The fifth was supplied in place of Reder & Anderson (1980, 1982)** and is
Charney, Reder & Wells (1988), a chapter in which Reder reports her own studies
and the later manual experiments. It carried § 2 from "no direct evidence on the
overshoot side" to a measured interaction, and it is the single most consequential
source in this document after § 5.2's.

**The German strand went the same way.** Two secondary sources were supplied in
place of Langer, Schulz von Thun & Tausch (1974) — the German Wikipedia article
on the Hamburg model, and Kroop, Mangler, Hutterer & Swertz's paper on
comprehensibility training at the University of Vienna. Both were read in full,
they agree on the optimum and on the scale, and between them they carry the
validation studies and the standing criticisms. That moved § 4 from one
search-summary sentence to the best-evidenced section after § 5.2, and it
corrected a claim this document had been making. An encyclopaedia article is a
lead rather than an authority by this document's own method, so § 4's rows are
tiered as secondary, and the book stays on the § 9 list for one narrower question.
