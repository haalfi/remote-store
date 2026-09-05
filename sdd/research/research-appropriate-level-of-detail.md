# Research: Is the level of detail appropriate?

**Date:** 2026-08-17
**Backlog items:** ID-250, which shipped the authoring test in § 5.3.
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
> **Standing caveat: one source has been read in full, and only one.** Rozenblit
> & Keil (2002) — the mechanism the authoring test rests on — was supplied by the
> maintainer and verified against its own text (§ 5.2). Every other external claim
> rests on an abstract, a metadata record or a search summary, because every
> scholarly host returns 403 from this environment (Appendix B). Each carries a
> tier: treat the rest as directional, and the repo figures as the reliable half.

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

## 2. The two failure directions are not symmetric

| | **Overshoot** — more detail than the reader needs | **Undershoot** — less context than the reader needs |
|---|---|---|
| Evidence it harms readers | **None found direct.** See § 7 | Stronger, and it is the *predicted* failure |
| Nearest supporting work | Seductive detail (interesting-**and**-irrelevant material only); expertise reversal (material redundant **for experts**) | Curse of knowledge: authors impute their own knowledge and omit bridging detail |
| What the repo measures | The **cost**: review rounds spent on prose (§ 6.3) | The **incidence**: trace tags dominated by missing units (§ 6.2) |

**The asymmetry is the most useful single finding in this document.** The failure
authors fear is overshoot; the failure the evidence predicts is undershoot. That
does not make overshoot harmless — this repo pays for it in review rounds — but
it means a rule that only cuts is aimed at the less-evidenced direction, and will
eventually delete something load-bearing. `research-id-232`'s
justification-sufficiency test exists for exactly that reason and still applies.

## 3. What "appropriate" is a function of

Four inputs, each with a source and a direction.

**Reader expertise, and it reverses.** More explicit, more elaborated material
helps low-knowledge readers and can *harm* high-knowledge ones. Two independent
strands: the reverse cohesion effect (McNamara, Kintsch, Songer & Kintsch, 1996)
found high-knowledge readers learning more from the less coherent text, and the
expertise reversal effect (Kalyuga, Ayres, Chandler & Sweller, 2003; Kalyuga,
Chandler & Sweller, 1998) found the best design shifting toward *eliminating*
explanatory text as expertise rose. **[Search-summary; the 1996 study manipulated
coherence rather than surplus detail, so it bounds the claim rather than proving
it.]**

**Reader purpose and the decision at stake.** What the reader must decide or do
determines which units are load-bearing. A constraint, an exception or a
precondition is detail by appearance and structure by function.

**Text type.** The same fact belongs at different depth in an ADR, a spec, a
guide and a chat reply, because the text's function differs
(Göpferich; Brinker's *Textsorte/Textfunktion*). **[Search-summary.]**

**Prior knowledge the author cannot observe.** For public docs and package users
the expertise input is unknown, which is why expertise-conditioned rules work
inside `sdd/` and fail on `docs-src/`.

## 4. The one dimension with a stated optimum

The Hamburg model's *Kürze/Prägnanz* [brevity/conciseness] is the only dimension
in that framework whose optimum sits **mid-scale**: terse, compressed texts
hinder comprehension as much as verbose ones (Langer, Schulz von Thun & Tausch,
1974, *Sich verständlich ausdrücken* [*Expressing Yourself Comprehensibly*]).
**[Search-summary.]**

That is the closest external formulation of the question this document answers,
and it is 52 years old. Two cautions travel with it: the four dimensions are
criticised as not precisely operationalised and **not independent of one
another**, and the contrast pairs behind the factor analyses were compiled ad hoc.
So the optimum is usable as a *frame* and not as a measurement.

## 5. The author-side test

### 5.1 Why the author is the only checkable party at writing time

The reader is absent when the text is written. The author's grasp is present.
That is the whole argument for putting the test on the author.

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

**The shape undigested writing takes** is described independently: Bereiter &
Scardamalia (1987), *The Psychology of Written Composition*, separate
**knowledge-telling** — retrieving content on topic-and-genre cues and
transcribing it in arrival order — from **knowledge-transforming**, a dialectic
between a content problem space and a rhetorical one. **[Search-summary.]**
*Inference, not their claim:* prose that lists everything true about a subject in
discovery order is knowledge-telling, and it is detectable by its author.

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
| RST "keep nuclei, delete satellites" | Rests on a label trained annotators agree on ~4 times in 5: RST-DT reports 86.8% spans, **80.7% nuclearity**, 72% relations over six taggers. **[Search-summary]** |
| Kintsch & van Dijk's macrorules as an editing procedure | They model what readers do, not what authors should cut. **[Search-summary]** |
| Relevance ≈ cognitive effect ÷ processing effort | Sperber and Wilson operate a **comparative** notion and distinguish it from a quantitative one; the quotient is a popularization. **[Search-summary]** |
| Verbosity bias in LLM judges | Establishes that *raters* over-reward length, not that verbose output harms a reader's task. **[Search-summary]** |
| Seductive-detail research as a general cutting licence | Covers interesting-**and**-irrelevant material whose mechanism depends on grabbing attention. Bland, on-topic surplus is a different class |
| The minimal manual as proof that cutting works | Carroll, Smith-Kerker, Ford & Mazur-Rimetz (1987), *Human-Computer Interaction* 3(2): the manual differs from its comparator on **four** dimensions at once — briefer, better attention coordination, error-recovery training, better reference support. It shows one package beating another, not that deleting detail is what did it. **[Verified]** |

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

1. **A study manipulating detail volume in non-instructional reference prose,
   read non-linearly by domain experts.** None was found. Every anchor here uses
   novice learners reading linearly for a retention test. If it does not exist,
   the reader-side question can be argued but not evidenced.
2. **Kalyuga, Chandler & Sweller (1998) in full**, to establish whether any
   experiment isolates text elimination from the integration manipulation.
3. **Langer, Schulz von Thun & Tausch (1974) in full**, for whether the
   *Kürze/Prägnanz* optimum is the authors' claim and whether it was measured.
4. **Locally and cheaply:** run the reader test against one page twice, whole and
   condensed, and compare unanswerable counts. The one experiment available
   without external access, and it tests overshoot directly on this corpus.

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
| 8 | Kalyuga et al. (1998): text elimination best for experts across three experiments | Search-summary | Low-medium |
| 9 | *Kürze/Prägnanz* is a mid-scale optimum | Search-summary | Low-medium |
| 10 | Groeben's interactional turn; Göpferich keeps the Hamburg four, adds *Korrektheit* and *Perzipierbarkeit*, reframes on the communication situation | Search-summary | Low-medium |
| 11 | Hamburg dimensions not independent; contrast pairs ad hoc | Search-summary | Low-medium |
| 12 | Rozenblit & Keil: the explanation attempt lowers self-rated understanding across 12 studies, and moves it to where independent raters already scored it | **Verified, read in full** | High |
| 12a | The same: **no** drop for procedures or narratives, a significantly smaller drop for facts, so the effect is specific to explanatory knowledge | **Verified, read in full** | High |
| 13 | Bereiter & Scardamalia: knowledge-telling versus knowledge-transforming | Search-summary | Low-medium |
| 14 | Bisra et al. (2018): self-explanation g = .55, 69 effect sizes from 64 reports | Search-summary | Low-medium |
| 15 | RST-DT agreement 86.8 / 80.7 / 72 percent over six taggers | Search-summary | Low |
| 16 | Relevance is comparative, not a quotient | Search-summary | Low-medium |
| 17 | Macrorules are comprehension rules, not an editing procedure | Search-summary | Low |
| 18 | Verbosity bias is a property of raters, not evidence of reader harm | Search-summary | Low |
| 19 | Repo: 223 negative trace tags, dominated by missing units | Local | High |
| 20 | Repo: 219 traces carry `review_rounds`; median 2, mean 2.15, max 10; 24 at ≥5 | Local | High |
| 21 | Repo: BUG-248's eight rounds split roughly three-to-four behavioural, rest prose | Local, one item | Medium |
| 22 | Repo: two density disputes resolved ad hoc, one cut silently lossy (BK-351, BK-353) | Local | High |
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

**The exception, and the route around the blockade.** Rozenblit & Keil (2002) was
supplied directly by the maintainer as a PDF and read in full, which moved rows
12 and 12a from search-summary to verified and sharpened § 5.2 from an assertion
to a measured contrast. That is the working route for anything else in § 9: the
environment cannot fetch, but it can read what is handed to it.
