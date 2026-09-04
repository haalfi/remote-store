# Research: Reader-fit and communication density as a second axis for principle 8

**Date:** 2026-08-17
**Backlog items:** ID-250, filed and shipped after this document was written.
It took a variant of § 10.1 (option A) on the commissioner's decision, justified
by the local round split rather than by the literature below; § 10 records the
four options as they stood, and is not rewritten.
**Status:** Advisory research, not a spec or ADR. Commissioned to test whether
[`CLAUDE.md` principle 8](../../CLAUDE.md#principles) should gain a second axis:
not only *where* a piece of detail belongs, but whether it earns its place at
all for its reader, and whether the level of detail and communication density is
appropriate. **Presents options and recommends none**, at the commissioner's
instruction.
**Related:**
[`research-id-232-detail-placement-durability.md`](research-id-232-detail-placement-durability.md)
(the predecessor this either confirms or overturns),
[`../CONTENT-RULES.md`](../CONTENT-RULES.md) (the documentation instantiation),
and `.claude/agents/documentation-expert.md` § Reader test (the existing
instrument that covers half of the proposed axis).

> **Central finding, and the honesty statement that governs it.** The headline
> question resolves **negatively**: no source reached in this pass supplies
> direct empirical evidence that surplus on-topic detail conceals a load-bearing
> claim in authoritative prose. The predecessor's standing finding is
> **confirmed, not overturned**. What *is* supported, and consistently, is the
> weaker relational claim: how much to say is a property of the
> text–reader–purpose tuple, never of the text alone.
>
> **No source in this report was read in full.** Every scholarly host is blocked
> by this environment's egress policy (§ 2.2). Claims rest on abstracts, search
> summaries and verifiers' knowledge of canonical texts. That is a weaker
> evidence base than the predecessor's, and every section below carries the
> label rather than hiding it. **A negative headline finding obtained under
> blocked access is weak evidence of absence**, and must not be read as proof
> that the harm is not real.

---

## 1. The question, and what principle 8 does not currently decide

Principle 8 reads:

> **Minimize mismatched detail, not detail**: durable artifacts — code, docs,
> specs, tests — keep the detail whose change-rate and correctness-locus fit the
> artifact, and relocate detail that belongs to another layer to its
> authoritative home (per principle 4). Brevity is a byproduct of correct
> placement, never the target: never delete a load-bearing reason to hit a
> length budget.

It decides **placement**. It does not decide **volume**. The repo has hit that
gap twice in its own history and resolved it ad hoc both times (§ 9.2). The
proposed second axis has two halves that must not be collapsed:

- **(a) Earn-its-place.** Does this unit do anything for this reader's purpose?
- **(b) Density.** Is the *level of detail* right, given that a passage can be
  made entirely of units that individually earn their place and still be too
  dense, or too thin, for the reader it addresses?

The commissioned reader set is wider than principle 8's "durable artifacts": the
maintainer, contributors, source-code readers, PyPI and API users, docs readers,
**and human↔agent chat turns**.

## 2. Method, and the limitation that governs every claim

### 2.1 What was run

A fan-out research pass: 6 search angles, 31 sources fetched, 72 claims
extracted, 25 put to 3-vote adversarial verification, 8 confirmed and 17
refuted; 114 agent calls total. Derivation: the workflow's own `stats` block,
run `wf_f2435a61-ff1`. A second pass by the authoring session added the leads the
first pass never reached (§ 5, § 6, § 8), at search-summary level only.

### 2.2 The access limitation

Every scholarly host tried returned 403 on CONNECT from this environment's egress
proxy. Derivation: the agent proxy's status endpoint
(`curl -sS "$HTTPS_PROXY/__agentproxy/status"`; the port is session-local, so the
literal URL is not reproducible), whose
`recentRelayFailures` named `aclanthology.org`, `doi.org`,
`www.semanticscholar.org`, `api.crossref.org`, `api.openalex.org`,
`journals.uic.edu`, `www.pedocs.de` and `en.wikipedia.org`; `arxiv.org` and
`pmc.ncbi.nlm.nih.gov` were re-tested directly and also returned 403. The proxy's
own README classifies 403/407 as an organization policy denial to be reported
rather than worked around.

**Consequences that must travel with every claim below:**

1. **Not one source was read in full.** Where a figure or quotation appears, it
   came from an abstract, an official metadata record, or a search summary.
2. **"Refuted" mostly means "not established at the strength asserted"**, not
   "the literature says the opposite". Of the 17 refutations, the majority were
   sourcing failures under abstract-only access.
3. **Two commissioned angles returned nothing** in the first pass: the German
   strand and the human↔agent strand. Both are covered below only at
   search-summary level, which is the weakest tier in this document.

### 2.3 Evidence tiers used below

| Tier | Meaning |
|---|---|
| **Verified** | Confirmed by adversarial vote against a retrieved abstract or metadata record. Still not read in full. |
| **Search-summary** | Taken from a search engine's synthesis of secondary sources. Directionally useful, individually unreliable, and never sufficient for a figure. |
| **Inference** | This document's own reasoning from the above to the repo's situation. Never presented as a finding of any source. |

## 3. The headline: no direct evidence for concealment harm in prose

The predecessor recorded that concealment harm (excess detail hiding the
load-bearing claim) rested only on analogy: its anchors studied problem-solving,
code modules and web hyperlinks, never inline detail in authoritative prose. Four
candidate upgrades were examined and each fails. **[Verified]**

| Candidate | Why it does not transfer |
|---|---|
| McNamara, Kintsch, Songer & Kintsch (1996), *Cognition and Instruction* 14(1), 1–43, DOI 10.1207/s1532690xci1401_1 | The manipulated variable is **coherence**, built by *adding* connectives, explicit noun phrases, headers and macropropositions. That is not surplus on-topic detail, and the mechanism offered is inference suppression, not raised cost of locating a claim. |
| Rey (2012), *Educational Research Review* 7(3), DOI 10.1016/j.edurev.2012.05.003 | The construct is "interesting but irrelevant information that are not necessary to achieve the instructional objective" — detail that never earned its place, not relevant-but-excessive detail. |
| Carroll, Smith-Kerker, Ford & Mazur-Rimetz (1987), *Human-Computer Interaction* 3(2) | The minimal manual differs on **four** dimensions at once (briefer, attention coordination, error recovery, reference support). It supports "this package beat that package", not "deleting detail is what helped". |
| Liu & Demberg (2024), RST-LoRA, NAACL, DOI 10.18653/v1/2024.naacl-long.121 | Asserts importance-discrimination as uncited background; every dependent variable is a summary-quality score. A search of the authors' cloned repository for human-subjects instrumentation returned only vendored dependencies. |

**One primary source does state the harm — and marks it disputable itself.**
Grice (1975), "Logic and Conversation", pp. 45–46, on the second Quantity
submaxim: "The second maxim is disputable; it might be said that to be
overinformative is not a transgression of the Cooperative Principle but merely a
waste of time. However, it might be answered that such overinformativeness may be
confusing in that it is liable to raise side issues". Note the hedge stack —
"may", "liable to", "may also be" — with no experiment and no citation.
**[Search-summary; the source could not be retrieved from any mirror.]**

**Inference.** The harm hypothesis is at least stated in a primary source rather
than being an artifact of the downstream analogy chain. It is not evidenced
there, and its own author flags it as arguable.

## 4. What the evidence does support: the relational finding

Axis (c) of the commission — whether appropriateness is a property of the text,
the reader, or the pair — is answered consistently across four traditions, and
answered the same way. **[Verified for Grice and Nickerson; search-summary for
the German pair.]**

- **Grice (1975)** indexes adequacy to purpose and stage: "Make your
  conversational contribution such as is required, **at the stage at which it
  occurs**, by the accepted purpose or direction of the talk exchange." The
  indexing is to a joint property of an exchange, not to an individual reader's
  knowledge state. Extending it to durable written artifacts is an extension,
  though one Grice licenses via his own generalisation to transactions that are
  not talk exchanges.
- **Nickerson (1999)**, *Psychological Bulletin* 125(6), 737–759: "To communicate
  effectively, people must have a reasonably accurate idea about what specific
  other people know." This supplies the addressee-knowledge half that Grice does
  not.
- **Groeben's interaktionaler Ansatz** [interactional approach]: comprehensibility
  is understood as an **interaction between text and reader**, and explicitly no
  longer as a pure text property in the way readability research and the
  Hamburg model treated it. Groeben, N. (1982), *Leserpsychologie:
  Textverständnis — Textverständlichkeit* [*Reader Psychology: Text Comprehension
  — Text Comprehensibility*], Aschendorff.
- **Göpferich's Karlsruher Verständlichkeitskonzept** [Karlsruhe Comprehensibility
  Concept] was developed because the Hamburg model's perspective is
  **textzentriert** [text-centred]; it adds reader, addressee and purpose as
  factors.

**This is the strongest result in the report, and it is theory-level.** No
experiment here manipulates detail volume against reader expertise in prose. What
the four traditions agree on is the *shape* of the answer, not a measured effect.

**Direction check, and it cuts against the convenient reading.** Nickerson's
mechanism predicts authors **under**-specify: assuming the reader shares their
knowledge, they omit bridging detail. **[Verified, 3-0.]** Recruiting him as
evidence for concealment harm inverts his vector. He supports the predecessor's
justification-sufficiency counterweight instead.

## 5. The strongest positive lead, which the first pass never reached

**Kalyuga, Chandler & Sweller (1998), "Levels of expertise and instructional
design", *Human Factors* 40(1), 1–17.** Three experiments; as expertise
increased, the best instructional design changed from diagrams and text
physically integrated to **the text eliminated**. The stated mechanism is that
the same diagram is intelligible in isolation to more experienced learners, who
require the elimination of redundant text to reduce cognitive load.
**[Search-summary.]**

**Independently corroborated on the citation, not on the finding.** The
commissioner later supplied the same reference — title, journal, volume and pages
all matching — hedged as "the likely reference", together with a summary of the
**expertise-reversal effect**: techniques that help novices (worked examples,
explanatory guidance, additional cues) become ineffective or harmful for more
knowledgeable learners through redundant processing, so guidance should taper as
prior knowledge grows. **That corroborates the bibliographic record and the
general mechanism. It does not corroborate the specific result this section leans
on** — three experiments in which the winning design became *text eliminated*.
The two are compatible and are not the same claim, and neither has been checked
against the paper. Two further hosts carrying candidate copies
(`tecfa.unige.ch`, `core.ac.uk`) were tried after the input arrived and both
returned the same egress denial as § 2.2, so the paper remains unread here.

**Why this matters more than anything in § 3.** Every disqualified candidate
manipulated something other than load-bearing material: coherence, or
interesting-but-irrelevant trivia, or a four-way bundle. This one **removes
correct, on-topic, explanatory material** and measures better outcomes for more
expert readers. It is the closest thing found to the proposed axis, and the
generalisation is named in the same tradition as the **expertise reversal
effect** (Kalyuga, Ayres, Chandler & Sweller, 2003, *Educational Psychologist*
38(1), 23–31): instructional techniques that are highly effective with
inexperienced learners lose effectiveness and can harm more experienced ones.

**The gap that remains, stated plainly.** The materials are instructional
(diagram-plus-text training), the readers are learners, and the measure is
learning performance. The repo's readers are maintainers and API users doing
non-linear lookup in reference prose. **This is still an analogy step — but a
much shorter one than the predecessor's anchors, because the manipulated variable
is finally the right one.** Whether it closes the gap is a judgement this
document does not make.

## 6. The German strand: an optimum, and a warning about measuring it

**Kürze/Prägnanz is stated as an optimum, not a monotone.** In the Hamburg model
the optimum for *Kürze/Prägnanz* [brevity/conciseness] lies in the middle of the
scale: terse, compressed texts hinder comprehension **as much as** verbose ones.
Langer, I., Schulz von Thun, F. & Tausch, R. (1974), *Sich verständlich
ausdrücken* [*Expressing Yourself Comprehensibly*], Reinhardt.
**[Search-summary.]**

**Inference.** This is the one dimension in that model with a stated wrong end in
*both* directions, and it is precisely the density axis. If a single external
formulation of axis 2(b) exists, this is it — and it is 52 years old, from the
tradition the commissioner named first.

**Christmann & Groeben (1999)** are reported as finding that **content and
cognitive structuring outranked stylistic simplicity**, and that **semantic
redundancy helps only in combination with stylistic simplicity**.
**[Search-summary; the ranking is a density claim and is unverified.]**

**The warning.** The Hamburg dimensions are criticised as not precisely
operationalised and **not independent of one another**, with the contrast pairs
behind the factor analyses compiled ad hoc. **[Search-summary.]** A rubric that
borrows the four dimensions inherits that problem: the axis may be real while
being unmeasurable dimension by dimension.

## 7. What the evidence does not license

Four claims from the material that commissioned this research, checked. Detail in
Appendix B.

| Claim as supplied | Status |
|---|---|
| Relevance ≈ cognitive effect / processing effort, as a quotient | **Not supported as stated.** Sperber and Wilson distinguish comparative from quantitative notions and operate the comparative one; relevance is a positive function of effects and a negative function of effort, not a computable ratio. The formula is a popularization. **[Search-summary.]** |
| RST: remove satellites, keep nuclei | **Weaker than stated, and unresolved.** RST-DT inter-annotator agreement over six taggers is reported as 86.8% spans, **80.7% nuclearity**, 72% relations, as percentages rather than kappa. **[Search-summary.]** Every first-pass claim about nuclearity instability was voted down for sourcing, so nothing about RST can be asserted in either direction from the verified set. |
| Macrorules (deletion, generalization, construction) as an editing procedure | **Category error, on the evidence available.** Kintsch and van Dijk present them as general rules underlying comprehension, not as rules for carrying out a summary-writing task. Brown & Day (1983) then found younger students using a simpler copy-delete strategy, so even as description they are expertise-dependent. **[Search-summary.]** |
| Seductive-detail research licenses "cut what does not serve the goal" | **Licenses a narrower rule only.** The construct is interesting-**and**-irrelevant material, and all three mechanism accounts depend on the detail grabbing attention. Bland purposeless detail falls under a different principle. Sundararajan & Adesope (2020), *Educational Psychology Review* 32, 707–734, synthesise 68 studies and report the effect **moderated** by eight factors. **[Verified for the bound; search-summary for the 68.]** |

## 8. The human↔agent half

The commission included agent-read and agent-written text. The first pass
returned **no surviving claims**; a second search finds a consistent but
differently-aimed literature. **[Search-summary throughout.]**

What exists is **verbosity bias in evaluation**: LLM judges and human raters both
prefer longer responses at equal quality, with reported length preference larger
for LLM judges than for humans, and the bias heterogeneous across model families.
The documented consequence is that preference-trained models emit longer
responses than the task needs.

**What this does and does not say.** It establishes that *raters* over-reward
length. It does **not** establish that verbose agent output measurably harms the
human's task performance, which is the claim axis 2 would need. That study was
not found.

**Inference, and the reason the axis is self-applying.** An instruction file such
as `CLAUDE.md` is a text whose density affects an agent reader. If the axis is
adopted, the file stating it is within its own scope.

## 9. What the repo's own evidence says

Gathered for this document from the repo itself, since no external source studies
this corpus. Each figure names its derivation.

### 9.1 The local instrument points the other way

`hatch run report-trace-outcomes`, run on this branch at `2bbb802` (the state
this document was written against; the corpus grows with every trace, so the
figures are pinned to that base rather than to "now"): 279 traces, 4052 steps,
1826 carrying an explicit outcome (45.1%), **223 negative tags (191 `misleading`,
32 `unclear`)** across 115 traces and 114 references. Reading the `unclear`
extracts, the dominant failure is a **missing** unit, not a buried one: "the row
did not ask the question that mattered", "**no row covers** a change to a skill's
frontmatter", "a semantic change behind an unchanged signature has no row".

**The repo's most direct measurement of reader failure evidences under-coverage,
not concealment.** BK-352 reasoned to the same split independently
(`BACKLOG-DONE.md`): only 30 of its 219 negative tags were `unclear`, and a
reader test "cannot catch `misleading`".

### 9.2 What does support the axis locally

- **BK-351** declined a 5,000-word budget for `/ship` citing principle 8, whose
  recorded reasoning is that principle 8 "forbids one *kind* of condensing" while
  setting no positive test. **The gap is documented in the repo before this
  research began.**
- **BK-353** then condensed `/ship` from 6,916 to 6,369 words (−547, −7.9%), one
  argument having been stated at four sites. **Its first cut claimed nothing was
  removed and that claim was false twice**; whole-file review found two deleted
  load-bearing clauses. The recorded lesson is that a token check "cannot answer
  'was anything removed' — only 'were these things removed'".
- **Principle 8's own guard failed its reader twice inside ID-232**, tagged
  `unclear`: "read the 'don't over-correct' warning, still over-corrected".
- Two further density calls (`bk-313` line 176, `BK-280` line 96) were made by
  reviewers with no rule to cite, both resolved by **relocation**.

### 9.3 The instrument that already exists

`.claude/agents/documentation-expert.md:44`: "A page can be accurate, correctly
placed and CONTENT-RULES-clean and still leave a reader unable to act; nothing
else you apply reaches that." **The repo has already asserted that correct
placement does not imply reader success.** Its reader test covers axis 2(a) for
one artifact class. It is structurally blind to 2(b): every question detects a
*missing* answer, none detects an answer that arrived buried.

## 10. Options

Presented without a recommendation, per the commission. Each carries the evidence
for and against.

### 10.1 Option A — amend principle 8 with a reader-fit clause

Add that detail is also judged by whether it serves this artifact's reader and
purpose, with the density half stated as an optimum rather than a minimum.

**For:** the relational finding (§ 4) is the best-supported result here and is
what the amendment would encode; the Hamburg optimum (§ 6) gives it a
formulation; the repo has twice needed the rule and lacked it (§ 9.2).
**Against:** theory-level support only; the local instrument does not show the
harm (§ 9.1); principle 8 is already the most-cited principle in condensing
arguments and a second clause invites the over-correction it warns against, which
is measured as having happened twice (§ 9.2).

### 10.2 Option B — extend the existing reader test instead

Leave principle 8 alone; add a density question to the reader test in
`documentation-expert.md`, whose normative home is already established.

**For:** the instrument exists, is advisory, and states its own bounds; § 9.3's
blind spot is a concrete gap in a live mechanism; no principle-level change means
no ripple through the authority documents.
**Against:** reaches only pages that persona writes, not specs, ADRs, commit
messages or chat turns — most of the commissioned reader set; a question-based
instrument is structurally the wrong shape for density (§ 9.3).

### 10.3 Option C — amend, but scope the density half to the evidenced case

State the axis only where evidence reaches: units that are interesting-and-
irrelevant to the reader's goal (§ 7 row 4), and explanatory material redundant
for an expert reader (§ 5).

**For:** every clause traceable to a manipulated variable; matches the expertise
reversal shape, which is the repo's actual situation (maintainer-expert readers,
contributor-novice readers, one corpus).
**Against:** narrow enough that it may not cover the `/ship` case that motivated
the question; requires the reader's expertise to be known, which for public docs
and PyPI users it is not.

### 10.4 Option D — file nothing, record the negative result

Treat the research as having answered the question: the evidence does not support
a general density rule, and the repo's own instrument points at under-coverage.

**For:** honest to § 3 and § 9.1; the admission test in `BACKLOG.md` says an item
that fits no section's promise "has no demonstrated value and is not filed";
avoids encoding a rule whose measured failure mode is confident over-correction.
**Against:** the § 9.2 gap is real and stays unaddressed; three of the four
leads that could change the answer were never read in full, so this closes a
question that the access limitation, not the literature, left open.

### 10.5 The filing decision, which is separate

If an item is filed, it needs a section, and **no current section's promise fits
cleanly**. Section 6 ("The repo does not mislead the next person") is the nearest,
but its promise is about artifacts asserting what is true, its `Closes when` is
"bounded to those five deliberately", and every one of its six open items is a
closing condition. Filing a seventh that is not one would break that pattern.
Next free ID is **250**, confirmed by `hatch run lint` (`gen_backlogid.py
--check` reports `ID=250`). Worth noting for whoever files it: `sdd/backlogid.json`
reads `"ID": 248` while `rg -o 'ID-[0-9]{3}' sdd/BACKLOG*.md` returns an open
`ID-249` at `sdd/BACKLOG.md:1360`, so the JSON alone would have given the wrong
answer and the generator is the derivation that matters.

## 11. What would settle it

1. **Kalyuga, Chandler & Sweller (1998) in full.** Whether any experiment
   isolates text elimination from the integration manipulation decides whether
   § 5 is evidence or another bundle.
2. **Langer, Schulz von Thun & Tausch (1974) in full**, for whether the
   *Kürze/Prägnanz* optimum is the authors' claim or a summariser's gloss, and
   whether it was measured.
3. **A study manipulating detail volume in non-instructional reference prose read
   non-linearly by domain experts.** None was found. Every anchor in this report
   uses novice learners reading linearly for a retention test. If that study does
   not exist, the axis cannot be evidenced and can only be argued.
4. **Locally, and cheaply:** the repo could measure its own case by running the
   reader test against a page twice, once whole and once condensed, and comparing
   unanswerable counts. That is the one experiment available without external
   access, and it would test 2(b) directly on this corpus.

---

## Appendix A — claim ledger

Every row is **not read in full**; the access limitation in § 2.2 applies without
exception. "Vote" is the adversarial verification result where one was run.

| # | Claim | Tier | Vote | Confidence |
|---|---|---|---|---|
| A1 | No direct prose evidence for concealment harm; predecessor finding confirmed | Verified | 3-0 on three constituents, 2-1 on two | High |
| A2 | Adequacy is indexed to purpose and stage (Grice) | Verified | 2-1 | High |
| A3 | Adequacy is indexed to addressee knowledge (Nickerson) | Verified | 2-1 | High |
| A4 | Curse of knowledge predicts under-specification, opposite vector to concealment | Verified | 3-0 | Medium |
| A5 | Grice states the harm and concedes it is disputable | Search-summary | 0-3 on provenance | Medium |
| A6 | Seductive detail licenses only the interesting-and-irrelevant rule | Verified | 3-0 | Medium |
| A7 | McNamara et al. manipulated coherence, not surplus detail | Verified | 3-0 | Medium |
| A8 | Carroll et al. is a four-way bundle | Verified | 3-0 | Medium |
| A9 | Kalyuga et al. (1998): text elimination best for experts across three experiments | Search-summary; citation corroborated by the commissioner, the specific result not (§ 5) | — | Low-medium |
| A10 | Kürze/Prägnanz is a mid-scale optimum | Search-summary | — | Low-medium |
| A11 | Groeben's interactional turn; Göpferich's text-centred critique | Search-summary | — | Low-medium |
| A12 | Hamburg dimensions not independent, contrast pairs ad hoc | Search-summary | — | Low-medium |
| A13 | RST-DT agreement 86.8 / 80.7 / 72 percent, six taggers | Search-summary | — | Low |
| A14 | Relevance is comparative, not a quotient | Search-summary | — | Low-medium |
| A15 | Macrorules are comprehension rules, not an editing procedure | Search-summary | — | Low |
| A16 | Verbosity bias in LLM and human raters; no task-performance harm shown | Search-summary | — | Low |
| A17 | Repo: 223 negative trace tags, dominated by under-coverage | Verified locally | — | High |
| A18 | Repo: two ad-hoc density litigations, one silently lossy cut | Verified locally | — | High |

**Refuted in the first pass, and what that means.** Seventeen claims were voted
down. The RST cluster (cross-framework agreement, nuclearity instability,
continuous-importance modelling) was refuted **on sourcing**, leaving search angle
1's central question genuinely unresolved rather than answered. Do not cite
discourse-structure instability as a finding of this report.

**Angles that returned nothing in the first pass:** the German strand and the
human↔agent strand, both covered here at search-summary level only.
**Never reached at all:** Zwaan & Radvansky's situation-model dimensions,
defensible modern working-memory claims, and Pyramid/SCU reproducibility.

## Appendix B — the commissioning material, checked

The research was commissioned with two prose briefs and roughly sixty links.
Claim-by-claim:

| Supplied claim | Verdict |
|---|---|
| RST nucleus/satellite as a deletability rule | Weaker than stated; nuclearity agreement ~80.7% and the framework question unresolved (§ 7) |
| Relevance as effect-over-effort quotient | Not supported as stated; comparative, not quantitative (§ 7) |
| Given/new and Thema-Rhema detect redundancy | Not reached. Daneš's typology was never retrieved; no claim survives either way |
| Pyramid/SCU as a unit-weighting method | Not reached; reproducibility across annotator pools unexamined |
| Hamburg model, and *Kürze/Prägnanz* as an optimum | **Supported** at search-summary level, and the single most usable external formulation found (§ 6) |
| Situation model as the test of necessity | Partially reached; Kintsch and van Dijk's macrorules are descriptive, not an editing procedure (§ 7) |
| "Trivial is not the same as omissible" | No source contradicts it, and § 4 supports the reasoning behind it. Not itself tested |
| Textsorte determines appropriate detail | Not reached directly; Göpferich's purpose-and-addressee factors are the nearest support (§ 4) |

**The one structural idea in the commissioning material that the evidence
supports and this document has kept:** the four outcomes keep / shorten / **move**
/ remove. "Move" is what ties axis 2 back to principle 8's placement axis, and
both repo density calls in § 9.2 resolved that way.
