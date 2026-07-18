# Research: Scope, abstraction, and the placement of detail in durable authoritative texts

**Date:** 2026-07-18
**Backlog items:** ID-232 (Rewrite ADR Decision sections to state decisions, not spec/impl detail)
**Status:** Advisory research informing ID-232 (not a spec or ADR). Synthesis
authored by hand from two adversarial-verification passes of the deep-research
harness: pass 1 (19 confirmed claims) covers the *staleness* half; pass 2 (12
confirmed) covers the *concealment* half. See the claim ledger and method caveats in
the appendix.
**Related:** [`research-doc-content-longevity.md`](research-doc-content-longevity.md)
and [`sdd/CONTENT-RULES.md`](../CONTENT-RULES.md), the *documentation*
instantiation of the same principle. This document is the cross-domain foundation
beneath them, extended to decision records.

> **Central honesty finding.** The two harms do not have equally strong evidence.
> **Staleness (harm B)** transfers *directly*: Parnas and Kaplow argue about
> locating content by rate-of-change in their own terms. **Concealment (harm A)**
> is supported only by **analogy**. Every anchor for it (cognitive load,
> deep/shallow modules, information foraging) studies problem-solving, code
> modules, or web hyperlinks. None studies inline detail in authoritative prose
> documents. The mechanism is well-evidenced; its application to ADRs is our
> inference, not a claim any source makes. This asymmetry is stated wherever it
> matters and must survive into the final doc.

---

## 1. The question, and why it is not self-evidently true

The prompt was general, not ADR-specific. **What distinguishes authoritative texts
that stay useful and correct over long horizons from ones that look thorough and
precise but decay into distraction and staleness?** The working hypothesis was that
excess detail is not neutral padding but an *active* harm that (a) conceals the core
signal by surrounding it with equal-weight trivia, and (b) couples a slow-changing
artifact to fast-changing facts, so it goes silently stale.

The candidate unifying principle was **Parnas-style information hiding applied to
prose**: a durable text states things at the level whose truth-conditions change
slowly, and relocates fast-changing detail to whatever artifact changes at that
rate. Locate content by *rate of change*.

The naive form of that thesis is wrong, and the evidence says so plainly (§3). The
interesting principle survives, but only after the counter-evidence forces it to be
restated. The single-line result, stated up front:

> **Durable artifacts do not minimize detail. They minimize *mismatched* detail.**
> A fact belongs in an artifact only if it passes three conditions together: it
> changes at a rate compatible with how expensive the artifact is to revise; its
> correctness actually matters at that layer; and it is needed to justify or
> constrain the decisions made there. This is a strict conjunction: all three must
> hold, and failure of any one is disqualifying. Rate-of-change is one condition of
> three, not the whole rule, and it is not the primary one; do not collapse the gate
> back into "fast-changing, therefore exclude."

### 1.1 Two distinct harms, two distinct anchor sets, unequal evidence

The report separates two failure modes that want different evidence.

- **Harm A, concealment (a reader-now problem).** Equal-weight trivia raises the
  cost of finding the load-bearing claim and lowers its apparent weight. Anchored
  by **Cognitive Load Theory** (Sweller, *primary*, mechanism only), **Ousterhout's
  deep/shallow modules** (*canonical but verified against secondary notes, medium
  confidence*), and **information foraging** (Fitzsimmons et al., *primary, but on
  web hyperlinks*). All three are mechanism-by-analogy for prose (see the central
  finding above).
- **Harm B, staleness (an artifact-over-time problem).** A slow artifact housing a
  fast-changing fact goes silently wrong. Anchored by the directly-transferring
  verified set: Parnas (§2), Kaplow (§4), and the repo's own one-copy-per-fact rule.

A single "keep it short" slogan cannot serve both. The concealment cure
(relocate/link out) can *worsen* a distinct failure, **under-justification**, if it
strips the reasoning a reader needs to trust the decision. That counterweight is
itself now evidenced (§5, the hypertext link-cost studies) and is operationalized by
the justification-sufficiency test (§7). Holding the two harms apart is what stops
the model collapsing into naive minimalism.

---

## 2. Deep anchor 1, the mechanism: information hiding (Parnas, 1972)

Parnas's *On the Criteria To Be Used in Decomposing Systems into Modules* gives the
causal core, and it is more precise than "keep it short."

- **The criterion is rate-of-change, stated literally.** "We propose instead that
  one begins with a list of difficult design decisions, or design decisions which
  are likely to change. Each module is then designed to hide such a decision from
  the others." [C1, primary, 3-0] The module boundary is drawn *around what
  changes*, not around what the thing does.

- **Organizing by surface structure is the failure mode.** "It is almost always
  incorrect to begin the decomposition of a system into modules on the basis of a
  flowchart... Since in most cases, design decisions transcend time of execution,
  modules will not correspond to steps in the processing." [C2, primary, 3-0] The
  load-bearing transfer to prose: organizing an artifact by its *narrative surface*
  (what reads naturally in sequence) rather than by rate-of-change is what couples a
  slow section to fast-changing detail. An ADR Decision section bloats precisely
  because dependency facts read as if they belong next to the decision they support.
  That is surface adjacency, not change-rate adjacency.

- **The interface reveals as little as possible.** "Every module... is
  characterized by its knowledge of a design decision which it hides from all
  others. Its interface or definition was chosen to reveal as little as possible
  about its inner workings." [C3, primary, 3-0] The prose analogue: the visible
  layer states the durable claim and *points to* the volatile detail. It does not
  inline it.

**Why this reduces the two harms.** Concealment (harm A) is reduced because the
visible layer carries only load-bearing sentences, so the reader can find the
signal. Staleness (harm B) is reduced because the volatile facts now live in the
artifact that is edited when they change, so the durable artifact's truth-conditions
no longer include them and it cannot silently go wrong about them.

**The half of Parnas the naive reading drops.** Information hiding is not only "hide
what changes." Its *point* is locality of change and **independent reasoning**: a
module can be understood and validated without tracing into the others. Transferred
to prose, that is a hard constraint on how far relocation may go. **A layer must
carry enough to support independent validation, not merely be stable.** "Link out
the detail" is correct for *volatile* facts and wrong for *justifying* facts. Strip
the reasoning a reader needs to trust or reverse the decision, and you have
optimized the artifact for the writer's brevity at the cost of the reader's closure.
This is the counterweight that §7's justification-sufficiency test operationalizes,
and it is why the model's third condition (decision relevance) is not optional.

---

## 3. Deep anchor 2, the evidence that breaks the naive thesis: constitutional endurance

This anchor exists to keep the report honest, and it earns its place by
contradicting the hypothesis in its crude form.

- **Durability is the rare exception.** Average life expectancy of a national
  constitution is about 19 years; median about 8; mode 1 [C16, primary
  Elkins/Ginsburg/Melton, 3-0]. So "what makes an authoritative text endure" is a
  real question about a rare outcome, not a description of the default.

- **The counter-finding, stated without softening: detail *promotes* endurance.**
  "Constitutions will have a long life if they are flexible, inclusive and
  detailed... Key stability-promoting characteristics included inclusiveness, ease
  of amendment, and specificity in constitutional design." [C4, primary, 3-0]
  Restated from the secondary summary: "more-detailed constitutions are... more
  likely to survive" [C11, 3-0]. **This directly cuts against "excess detail is
  inherently an active harm."** In the constitutional domain, specificity buys
  clarity that reduces disputes and forecloses bad-faith reinterpretation, and that
  clarity *aids* survival.

- **What actually does the work is a change-channel, not brevity.** Endurance comes
  paired with **flexibility, operationalized as ease of amendment**: "the
  constitution must be sufficiently stable... yet sufficiently flexible to allow
  future generations to respond to political and social developments" [C5, 3-0; C12,
  3-0]. And **scope of inclusion** matters more than length: the most inclusive
  constitutions last about 5× longer than the least (69 vs 14 years) [C15, primary,
  2-1, one verifier dissented, so hold this figure loosely].

**What this forces.** The thesis cannot be "less detail is more durable." Nor is
rate-of-change the whole story: the constitutional evidence shows detail that
changes rarely *and* reduces ambiguity earns its place. The defensible rule is the
three-condition gate from §1, and the constitutional domain sharpens its second and
third conditions:

> Detail is not the enemy. **Mismatched detail** is: a fact housed in an artifact
> whose revision cost does not match the fact's change rate, *or* whose correctness
> does not matter at that layer, *or* which is not needed to justify or constrain
> the local decision. The remedy is rarely deletion. It is (i) relocation to an
> artifact whose change-rate fits, plus (ii) a low-cost amendment channel so a
> durable artifact can *absorb* change rather than resist it.

The causal chain, made explicit, is the whole point:

- Constitution → **cheap** amendment (Article V) → can *tolerate* embedded detail,
  because when the detail dates, amending it is low-cost.
- ADR → **expensive** revision (a superseding ADR) → must *externalize* volatile
  detail, because when it dates there is no cheap way to correct it in place, so it
  rots silently.

A constitution can afford detail because it has a cheap-enough amendment channel
matched to the volatility it carries. An ADR Decision section cannot afford
spec-detail because its amendment channel is heavy, so mislocated volatile detail
there goes stale silently rather than being cheaply amended. Same principle,
opposite prescription, because the *change-channel cost differs*. That asymmetry is
the actual insight, and it only appears once you refuse to force the tidy story.

**The constraint case, why rate alone would mislocate.** Some facts change rarely
yet are decision-critical *because they are invariants the choice must respect*:
"must support async I/O due to the concurrency model," "must avoid global state due
to multi-tenant isolation," "dependency floor ≥ X because of a CVE." A pure
rate-of-change model has no quarrel with these (they are slow), but that is luck,
not reasoning. Their claim to the decision layer comes from conditions two and three
(cost of being wrong is high; they justify or bound the choice), not from their
clock. These are best treated **not as a fourth rate-tier but as a category**,
*constraints*, whose placement the three-condition gate decides, and which almost
always lands in the decision layer's rationale.

---

## 4. Broad corroboration for harm B (staleness, placement over time)

**Legal drafting, rules vs. standards (Kaplow).** The rule/standard choice is "the
extent to which efforts to give content to the law are undertaken before or after
individuals act" [C6, primary, 3-0], i.e. it reframes *how much detail* as *when the
detail's content is fixed*. This is the placement-by-rate-of-change thesis in a
second field: "detail should live in the artifact whose timing matches when its
truth-conditions are actually known" [C8, primary Duke, 3-0]. And it supplies the
economic mechanism. Front-loading precise content is costly to produce and must
anticipate contingencies at drafting time [C7, C17, 3-0], so it pays off *only* when
the governed situation is frequent enough to amortize the cost: "the more often a
norm is applied, the more a rule with a higher degree of specificity ex ante is
desirable" [C18, C19, 3-0]. Detail fixed in advance for rare or heterogeneous cases
is wasted specification. This is a genuine convergence, not analogy. It is
independently the same tradeoff.

*Analytical extension (ours, not Kaplow's).* A productive lens the verified claims
do **not** themselves state: an ADR decision behaves like a **meta-rule**, a
*standard selecting which rule-system to adopt* (the spec being the rules that encode
it). "Build on httpx + msal" under-determines the precise contract and defers it to
the spec, the way a standard defers content to later application. But be precise
about the axis. On **Kaplow's own axis (timing)** an ADR decision is *rule-like*:
its content is fixed before implementation, not deferred to adjudication. It is
standard-like only on the **abstraction axis**, in that it under-specifies. So the
meta-rule reading is a real analytical gain, but it rides a different axis than the
evidence, and is flagged as interpretation rather than a cited finding.

**Jurisprudence, holding vs. dicta.** The binary "binding holding vs. non-binding
dictum" is "too simplistic to adequately model the complex system of precedent";
authority is better modeled as a continuous spectrum [C10, primary GWU, 3-0]. Useful
as a caution, *not* as support for the thesis. Here the harness earned its keep: the
adjacent, tempting claim that *narrower statements carry stronger binding force* was
**refuted 0-3**. The intuition "more scoped ⇒ more authoritative" did not survive
verification. Do not lean on it.

---

## 5. Harm A evidence, concealment is a real reader cost, not an aesthetic preference

This is the pass-2 material. It is genuinely evidenced, and it is genuinely analogy.
Read the caveats as carefully as the claims.

**Cognitive Load Theory (Sweller), the mechanism. [primary; mechanism-only.]**
Sweller (1988) established that a processing method can consume limited
working-memory capacity that is "consequently unavailable for schema acquisition"
[D1, primary, 3-0], i.e. *how* information is presented competes with understanding
it, independent of the material's inherent difficulty. This is the mechanism behind
the concealment claim: equal-weight trivia around a core sentence is
presentation-imposed load that crowds out the reader's grasp of the signal. Two
honest limits. First, the intrinsic/**extraneous**/germane taxonomy, the part the
concealment argument actually wants, is *later* work (extraneous, Sweller 1994;
germane, 1998), not the 1988 paper; cite it as "the tradition Sweller founded," not
as 1988. Second, CLT's evidence base is learning and problem-solving tasks, not
reading authoritative documents. The mechanism is solid; the application is ours.

**Ousterhout, deep vs. shallow modules, the design vocabulary. [canonical; medium,
verified against secondary notes, not the book.]** "The best modules are deep: they
have a lot of functionality behind a simple interface," and it is "much more
important for your module to have a simple interface than to have a simple
implementation" [D2, medium, 3-0]. Interface complexity is a cost borne by *every*
user; "classitis," many individually-simple pieces, produces interfaces that
"accumulate to create tremendous complexity" [D2]. Two corollaries transfer directly
to prose: **pull complexity downward** (the author absorbs complexity to spare the
reader) and **comments that merely repeat the obvious add negative value**, since a
good comment "describes things that aren't obvious from the code" [D3, medium, 3-0].
Mapping (ours): **a good decision record is a *deep* artifact**, a narrow visible
statement over hidden or linked detail; a bloated one is *shallow*, its surface
nearly as large as what it hides. *Confidence is medium* because the primary book
was 403-blocked and claims were verified against a secondary study-note plus
corroborating snippets. The principle is uncontested, but say "verified via
secondary sources" in the final doc.

*Two formulations worth adopting (surfaced by a practitioner walkthrough; grounded
here in Ousterhout canon, the walkthrough itself left uncited as tertiary):*

1. **The cover-the-body test, corrected.** Cover the implementation and read only
   the interface: *can you state the contract in fewer words than it takes to read
   the body?* If yes, the abstraction is doing compression work (deep). If the
   "summary" is the same size as the body, it only renamed it (shallow). This is a
   sharper phrasing of the concealment test (§7.1): it distinguishes
   *predict-the-contract* (should be possible) from *predict-the-implementation*
   (should not).
2. **Shallow = relocating complexity, not removing it.** This is the important one,
   because the report's remedy is *relocate, don't delete*, and this is the guard
   that keeps that advice from backfiring. Relocation reduces harm only when the
   durable layer becomes a **deep** interface (narrow surface over hidden or linked
   detail). If instead it fans the same complexity into many thin cross-referencing
   artifacts, total surface *rises*, the shallow anti-pattern. So: **relocate a fact
   into an existing authoritative home (deep), never into newly-minted thin
   satellites (shallow); if relocation would add more cross-reference surface than
   it removes, the detail was probably load-bearing, so send it back through the
   justification-sufficiency test.** This ties the deep/shallow lens to the
   single-source-of-truth test (§7.4).

**Information foraging (Fitzsimmons et al., 2020), how readers actually scan.
[primary; but on web hyperlinks.]** In a peer-reviewed eye-tracking study, "readers
use hyperlinks as markers to suggest important information and use them to navigate
through the text in an efficient and effective way"; when skim reading they fully
lexically processed *only* linked words, shallow-processing the surrounding text,
deliberately "minimis[ing] comprehension loss while maintaining a high reading
speed" [D4, primary, 3-0]. The paper itself grounds this in Pirolli & Card's
information-foraging and scent theory, so the scent framing is *source-stated, not
our analogy*. Transfer to the concealment claim: readers forage by salience, so
volatile detail given equal typographic weight to the core competes for the scarce
attention the core needs. Caveat, stated plainly: the stimuli are clickable
hyperlinks with a navigation affordance; whether the salience effect holds for
non-link emphasis (bold, headings, callouts) that better resembles prose is an open
question the source does not answer.

**The counterweight, relocation is not free. [primary review; cite DeStefano &
LeFevre, not the blog.]** Against naive "link everything out": each link forces a
micro-decision (click or not) that itself imposes load, and comprehension can decline
as link count rises *whether or not the reader clicks*. The falsifiable burden
belongs to the peer-reviewed review DeStefano & LeFevre (2007), "Cognitive Load in
Hypertext Reading," which states "the number of links (and therefore the accompanying
decision-making requirements) may be an important source of cognitive load" [D5,
medium, 3-0]. (A popular blog restating Nicholas Carr was the harness's entry point
but is derivative; the effect is also mediated by working-memory and prior
knowledge, so it is a tendency, not a law.) This is the empirical backing for the
justification-sufficiency counterweight: past some point, extraction *adds* reader
cost, so "keep it inline" can be correct for load-bearing justification.

**Observable symptoms, since the evidence is analogy.** The harm-A anchors do not
study prose, so do not wait for them to. Detect concealment by its *local, visible*
proxies instead, which need no citation to act on:

- **Reviewers miss or misstate the decision.** If readers of a Decision section
  cannot reliably repeat the choice back, the signal is buried, whatever the word
  count says.
- **The summary is longer than the conclusion it summarizes.** A digest entry, or an
  opening paragraph, that runs longer than the thing it abstracts is doing no
  compression (the shallow-module tell, §5's cover-the-body test).
- **A section with a *simple core* is reread.** Reread is a noisy signal on its own,
  since genuinely complex material is legitimately reread (intrinsic load, not
  concealment). It indicates concealment only when the underlying claim is simple but
  the reader still has to loop to extract it past surrounding detail.

These are diagnostic heuristics, not measurements; they turn the analogy into
something a reviewer can check without instrumentation.

**What produced no citation-grade evidence.** Anchors 4 (ADR practice beyond Nygard:
AWS, ThoughtWorks, Azure) and 5 (policy-vs-configuration separation: OPA, 12-factor)
returned **zero verified claims** this pass; every candidate source was rated
unreliable. They remain **plausible but unverified priors** and are *not* cited as
evidence anywhere in this report. If they matter to the final doc, a third pass must
fetch primary pages and quote them.

---

## 6. Where the convergence is genuine, and where it is stretched

Being critical about the cross-domain move, since that is where a report like this
is most tempted to overclaim:

| Cross-domain link | Verdict | Why |
| --- | --- | --- |
| Parnas information hiding → prose layering | **Genuine** | "Hide what changes" is domain-neutral and transfers by direct restatement. Import the *whole* of it, locality and independent-reasoning too (§2), not just volatility. |
| Kaplow rules/standards → placement by change-rate/amortization | **Genuine** | Independently the same tradeoff (when is content fixed; is the cost amortized). Two fields, one structure. |
| Kaplow → "ADR decision is a meta-rule" | **Analytical, not cited** | A useful reframe (§4) but on the abstraction axis, not Kaplow's timing axis; ours, not the source's. |
| Constitutional detail → *ambiguity reduction* and *amendment-cost matching* | **Genuine (narrowed)** | What actually transfers: reducing interpretive ambiguity aids stability, and amendment cost must match volatility. |
| Constitutional detail → "specificity itself is stabilizing in software" | **Does NOT transfer** | Constitutions are interpretive systems under adversarial pressure; their "detail" is constraint-encoding. In code artifacts over-specificity often *reduces* adaptability. Domain-conditional: high interpretation-cost systems reward specificity; high change-frequency systems reward abstraction. |
| Constitutional endurance → "less detail lasts longer" | **Refuted** | Evidence runs the other way; used only as a falsifier of the naive thesis. |
| CLT / Ousterhout / foraging → concealment harm in **prose documents** | **Genuine mechanism, applied by analogy** | The mechanism (load, interface-cost, salience-foraging) is well-evidenced, but the sources study problem-solving, code, and hyperlinks. None studies inline detail in authoritative prose. The application to ADRs is our inference. This is the report's weakest transfer and is labeled as such. |
| Holding/dicta spectrum → "scoped statements are more durable/authoritative" | **Stretched / partly refuted** | Spectrum claim holds; the appealing corollary was killed 0-3. |
| ADR-beyond-Nygard; policy-vs-config | **Unverified** | No citation-grade source survived pass 2; priors only, not cited as evidence. |
| IMRaD / MDL / Grice | **Dropped** | Superseded as anchors by CLT/Ousterhout/foraging. |

The principle that survives without stretching is the three-condition gate: **house
each fact where its change-rate, its cost-of-being-wrong, and its local justificatory
need all fit, and give slow artifacts a cheap way to absorb change.** The staleness
half (harm B) has direct cross-domain support; the concealment half (harm A) has a
well-evidenced *mechanism* applied to prose by *analogy*. Brevity is a *consequence*
of the gate (the durable layer ends up short because mismatched detail left it),
never the rule itself.

---

## 7. Operational tests

The model is the **three-condition placement gate**. A fact stays in a layer only if
it passes all three: (1) its change-rate fits the artifact's revision cost, (2) its
correctness matters at that layer, (3) it is needed to justify or constrain the local
decision. These are conjunctive, not a weighted score; failing any one is a reason to
move or cut the fact, not something a high score elsewhere buys back. The tests below
apply the gate. They extend, and deliberately do not replace, the repo's existing
[6-month test](../CONTENT-RULES.md#six-month-test) and
[one-copy-per-fact](../CONTENT-RULES.md) rules.

They come in two families matching the two harms (§1.1). The **signal pair**
(concealment ↔ justification-sufficiency) is a *dual*: one guards against too much,
the other against too little, and a decision-grade artifact must pass both.

*Signal family (harm A, comprehension):*

1. **Concealment test / cover-the-body.** Cover every sentence but one, or cover the
   whole body and read only the heading and opening. Can a reader still name the
   single load-bearing claim, and *state the contract in fewer words than the body
   takes to read*? If the core is not recoverable, or the "summary" is the same size
   as what it summarizes, the detail is burying the signal. Cut or relocate. (Catches
   over-inclusion. Biases toward minimalism, which is why it must be paired with the
   next test.)

2. **Justification-sufficiency test.** Reading only what is present, no links
   followed, could a competent engineer (a) understand *why* this decision was made
   and (b) identify *when* it should be reversed? If not, the artifact is
   over-extracted: you relocated a *justifying* fact as if it were merely a *volatile*
   one. This is the concealment test's dual and the operational form of Parnas's
   reasoning-closure (§2). It has empirical backing on the cost side (§5, hypertext
   link-cost): past some point, extraction *adds* reader cost, so keeping load-bearing
   justification inline is correct, not lazy.

*Staleness family (harm B, correctness over time):*

3. **Rate-of-change test.** Would this sentence still be true after a routine change
   *one level down*, a dependency bump, a refactor, a config edit? If no, it is
   volatile relative to this artifact and belongs one layer down, with a link up.
   (The 6-month test made mechanism-explicit: the clock that matters is the lower
   layer's edit rate. Necessary, not sufficient. A fact can pass this and still fail
   the gate via condition 2 or 3, and a slow-changing constraint can fail this yet
   belong here; see §3.)

4. **Single-source-of-truth / duplication test.** Does this fact already have an
   authoritative home? A home qualifies on three counts: it is **versioned** (tracked,
   with a definite location), **owned** (it is the single source of truth for that
   fact, so no other artifact restates it), and **updated via a cheaper path than the
   ADR**. The last is the discriminating criterion, since it is the change-channel
   logic (§3) reappearing; "versioned" is table-stakes in this repo and should not
   carry the decision by itself. Examples: a spec, `FEATURES.md`, the code,
   `pyproject.toml`, a benchmark artifact. If a home exists, state the principle and
   link; every inline copy is a future contradiction. Relocate *into* that home (a
   **deep** move), never into a new thin satellite (a **shallow** move that just
   spreads surface; §5). If no qualifying home exists, that is a signal the fact may
   be load-bearing here after all, not that you should mint a satellite to hold it.

5. **Amortization test (from Kaplow).** How often is this detail actually read or
   applied? Precise, front-loaded detail earns its maintenance cost only when the
   thing it governs is frequent and stable. Detail specified in advance for a rare or
   one-off case is specification waste. Defer it to the point of use.

6. **Change-channel test (from constitutional endurance).** If this detail *must*
   live here despite changing, does the artifact have a cheap amendment path? A slow
   artifact (heavy to revise) must hold only slow-changing content; a fast artifact
   can hold specifics *because* it is cheap to keep current. Match content volatility
   to revision cost.

The signal pair (1–2) and the staleness set (3–6) are jointly the gate. Tests 5–6
are the additions the contradictory evidence forced: sometimes the right move is
*not* deletion but relocation, a better change-channel, or, via test 2, *keeping* a
fact the rate test would have evicted because it is load-bearing for justification.

---

## 8. Bridge, a three-layer rate-of-change model for decision records

Domain-illustrative, not an ADR how-to. The general principle maps onto three layers
distinguished by how fast their content's truth-conditions change.

- **Decision-rate** (changes only when the choice itself is revisited, years): the
  choice and the one or two reasons that would have to be false to reverse it.
- **Spec-rate** (changes on the ordinary development clock, versions, releases):
  exact contracts, version floors, dependency pins, lazy-import mechanics,
  transitive-dependency notes.
- **Consequence-rate** (accrues as the system lives with the choice): tradeoffs
  realized, follow-on obligations, escalation triggers for revisiting.

Cutting across these is a **constraint category** (§3): invariants the choice must
respect ("must support async I/O," "floor ≥ X due to a CVE"). Usually slow-changing,
but they earn the decision layer through cost-of-being-wrong and justificatory need,
not through their clock. The three-condition gate, not the rate tier, places them.

In deep/shallow terms (§5): **a good Decision section is a deep artifact**, a narrow
visible statement over spec-detail that is hidden behind links. A bloated one is
shallow: its surface (everything inline) is nearly as large as what it should be
hiding.

**Worked example (from the repo's own `ADR-0021`).** The decision-rate content is a
single sentence: *build the Graph backend on `httpx` (async) + `msal`.* Verify
against the actual Decision section and it then carries the full `graph` extra pin
list, `msal-extensions >=1.3` "keeps `portalocker` an optional extra rather than a
hard transitive dependency," `platformdirs` "imported lazily so callers... never load
it," and BK-291 cross-references. Those are **spec-rate content living in a
decision-rate artifact**, and it fails the signal pair *and* the rate test.

The fix is relocation, not deletion, but the justification-sufficiency test (§7.2)
makes it sharper than "evict all the dependency detail." Distinguish two kinds of
dependency fact.

- **Bookkeeping pins**, such as "`msal-extensions >=1.3` keeps `portalocker` an
  optional extra" and the lazy-`platformdirs` note. These fail all three gate
  conditions at the Decision layer: fast-changing, correctness irrelevant to *why
  httpx*, not needed to justify the choice. They move to the spec / `pyproject.toml`
  (their authoritative home, already edited when they change, a *deep* relocation
  into an existing home, not a new satellite).
- **Constraint-bearing dependency facts**, such as "`msal` is required because token
  flow X is unsupported in the alternatives," or a floor that exists "≥ X due to a
  CVE." These *pass* condition three: they are the reason the decision is what it is,
  and a reviewer needs them to reverse it competently. They **stay** in the Decision
  rationale even though they mention a version.

So the Decision keeps the choice, the irreducible "why httpx not `msgraph-sdk`," and
any *constraint-bearing* dependency reasons; the spec takes the bookkeeping;
Consequences keeps the "re-evaluate if the Graph surface grows" trigger. (In ADR-0021
the actual pins read as bookkeeping: the `>=1.3` floor preserves optionality, it is
not an external hard constraint, so eviction is right *there*. The test is what tells
you that, and would tell you to keep a CVE floor.) "Relocate everything
non-decisional" would have been the over-correction §3 warns against.

**Enforcement, so the discipline stays visible, not aspirational.** `gen_adr_digest`
(PR #909) already surfaces the problem by lifting each `## Decision` into a digest,
and a shorter, decision-only digest is the success signal. A lightweight structural
heuristic can keep it from re-eroding: warn when a Decision section exceeds a length
budget or nests beyond a shallow H3 depth (deep nesting inside a decision is the shape
of spec-detail that wandered in). Line-length linters such as markdownlint's `MD013`
are prior art for "structural size limits as an enforceable discipline," though that
specific claim was **not** independently verified. Treat the enforcement design as a
proposal to validate, not a settled fact. The heuristic is a smell detector, not a
proof; it flags for human judgment, matching the repo's `[review-enforced]` posture
in `CONTENT-RULES.md`.

---

## 9. Relationship to existing repo work (single source of truth)

This is **not** a competing framework. `sdd/CONTENT-RULES.md` already codifies this
principle for documentation prose ("stable prose describes shape; volatile detail
lives in its authoritative location"), derived from
`research-doc-content-longevity.md`. That work owns the *documentation* rules and
remains authoritative for them.

What this research adds, and why it is not duplication:

1. **Evidentiary foundation.** It grounds the repo's existing rules in cross-domain
   evidence (Parnas, Kaplow for staleness; CLT, Ousterhout, foraging for
   concealment) and, more valuably, stress-tests them against the one domain
   (constitutional endurance) where the naive version fails, yielding the
   change-channel refinement the docs rules do not currently state.
2. **Extension to decision records.** `CONTENT-RULES.md` is scoped to README,
   guides, and docstrings. ADRs are a different artifact class with a *heavier
   amendment channel*, which is exactly why the same principle produces a stricter
   prescription there (§3). ID-232 is that extension.

If any of this is promoted into rules, it should be by *reference from*
`CONTENT-RULES.md` (e.g. a decision-record note pointing here), not by copying, per
the one-copy-per-fact rule this research is itself about.

---

## 10. Recommendations for ID-232

1. **Apply the three-condition gate (§7), not a length target.** Decision layer keeps
   decision-rate content *plus* constraint-bearing rationale (§3); relocate
   bookkeeping spec-rate to the spec/`pyproject.toml`; consequence-rate to
   `## Consequences`. Placement is decided by the gate, not word count.
2. **Run the signal pair on every rewritten Decision.** Concealment/cover-the-body
   (is the choice recoverable, contract shorter than body?) *and*
   justification-sufficiency (could a reviewer reverse it from what's here, no
   links?). Passing only the first yields concise but not decision-grade ADRs.
3. **Relocate deep, not shallow (§5).** Move detail into an existing authoritative
   home (spec, `pyproject.toml`, `FEATURES.md`); do not spawn thin new satellite docs
   that just move the surface around.
4. **Do the Graph ADRs (0021–0024) first.** The backlog and the digest both name them
   as worst; highest-signal before/after, and they validate the gate before a 30-ADR
   sweep.
5. **Prototype the digest heuristic as advisory-only** (length / H3-depth warning) and
   confirm a shorter decision-only digest results. Treat the heuristic design as
   unverified (§8); validate MD013-style enforcement empirically before relying on it.
6. **Resist over-correction.** The evidence (§3) says detail is not the enemy;
   deleting a load-bearing reason to hit a length target is the same mistake inverted.
   Test 2 is the guardrail against it.

---

## Appendix, claim ledger

### Pass 1, the staleness half (durability, placement over time)

19 claims confirmed by 3-vote adversarial verification (2/3 refutes required to
kill); 1 refuted; 5 unverified (verifier votes errored on a session limit, not on
merit).

| ID | Claim (abbrev.) | Source | Vote |
| --- | --- | --- | --- |
| C1 | Parnas: decompose by hiding decisions likely to change | dl.acm.org (primary) | 3-0 |
| C2 | Flowchart/execution-order decomposition is wrong criterion | dl.acm.org (primary) | 3-0 |
| C3 | Interface reveals as little as possible about inner workings | dl.acm.org (primary) | 3-0 |
| C4 | Detail + flexibility + inclusiveness → longer endurance | ResearchGate EGM (primary) | 3-0 |
| C5 | Ease of amendment is an independent endurance factor | ResearchGate EGM (primary) | 3-0 |
| C6 | Rule/standard = when content is fixed, before/after acting | Kaplow (primary) | 3-0 |
| C7 | Front-loading detail (rules) costs more to produce | Kaplow (primary) | 3-0 |
| C8 | Detail belongs where timing matches truth-conditions | Duke L.J. (primary) | 3-0 |
| C9 | Specifying in advance is costly (must resolve cases ahead) | Duke L.J. (primary) | 3-0 |
| C10 | Holding/dicta binary too simplistic; spectrum better | GWU (primary) | 3-0 |
| C11 | More-detailed constitutions more likely to survive | SSRN (secondary) | 3-0 |
| C12 | Flexibility = ease of amendment is stability-promoting | SSRN (secondary) | 3-0 |
| C13 | ADRs should be pithy/factual; excess elaboration a fault | MS Learn (secondary) | 3-0 |
| C14 | Decision must stand alone; justification goes behind a link | MS Learn (secondary) | 3-0 |
| C15 | Most-inclusive constitutions last about 5× longest (69 vs 14 yr) | ResearchGate EGM (primary) | 2-1 |
| C16 | Constitution life expectancy about 19 yr avg, 8 median, 1 mode | ResearchGate EGM (primary) | 3-0 |
| C17 | Rule author must anticipate contingencies at drafting time | Kaplow (primary) | 3-0 |
| C18 | Up-front specificity pays off with frequency of application | Kaplow (primary) | 3-0 |
| C19 | Pre-specified detail amortizes only when conduct is frequent | Duke L.J. (primary) | 3-0 |
| R1 | **Refuted:** narrower statements carry stronger binding force | GWU | 0-3 |
| U1–U5 | Unverified (errored): dicta-spectrum candor; 19-yr baseline (dup); ADRs append-only/superseding; context + rationale needed for longevity; MD013 line-length enforcement | mixed | — |

### Pass 2, the concealment half (comprehension, reader-now)

12 confirmed; the one "refutation" was a note that a blog could not be fetched
verbatim, not a substantive kill. **All harm-A anchors apply to prose by analogy;
see §1.1 and §6.**

| ID | Claim (abbrev.) | Source | Confidence / Vote |
| --- | --- | --- | --- |
| D1 | Processing load "unavailable for schema acquisition," the mechanism behind extraneous load | Sweller 1988, *Cognitive Science* (primary) | high / 3-0 · taxonomy is later work |
| D2 | Deep module = functionality behind a simple interface; simple interface > simple implementation; classitis accumulates interface complexity | Ousterhout, *APoSD* (canonical) | medium / 3-0 · verified via secondary notes |
| D3 | Pull complexity downward; comments repeating the obvious are negative-value | Ousterhout, *APoSD* (canonical) | medium / 3-0 · verified via secondary notes |
| D4 | Readers forage by salience; hyperlinks as importance markers; skim = process only linked words | Fitzsimmons et al. 2020, *PLOS ONE* (primary) | high / 3-0 · web hyperlinks, not prose |
| D5 | Number of links imposes decision-making load; relocation is not free | DeStefano & LeFevre 2007, *Comp. in Human Behavior* (primary review) | medium / 3-0 · cite the review, not the blog |
| D6 | ADR-beyond-Nygard (AWS/ThoughtWorks) and policy-vs-config: **no citation-grade evidence** | — | low / unverified priors |

**Primary sources (pass 1):** Parnas (1972), ACM · Elkins, Ginsburg & Melton (2009),
ResearchGate/SSRN · Kaplow, Harvard Olin & Duke L.J. vol. 42 · GWU holding/dicta.
**Primary sources (pass 2):** Sweller (1988), *Cognitive Science* 12(2) ·
Fitzsimmons, Jayes, Weal & Drieghe (2020), *PLOS ONE* 15(9):e0239134 · DeStefano &
LeFevre (2007), *Computers in Human Behavior* 23:1616-1641. **Canonical
(secondary-verified):** Ousterhout, *A Philosophy of Software Design* (2018).
**Unverified priors:** AWS/ThoughtWorks/Azure ADR guidance; OPA/12-factor
policy-vs-config.

**Method caveats.** (1) The pass-1 harness synthesis was cut off by a session limit
and reconstructed by hand from the verified claim set. (2) In pass 2 the strongest
primaries (Sweller PDF, PLOS ONE, Ousterhout's book) were 403-blocked to direct
fetch; quotes are verbatim but confirmed via multiple search retrievals, not
end-to-end fetch, hence Ousterhout's medium confidence. (3) The analytical
refinements (three-condition gate, justification-sufficiency test, constraint
category, two-harm split, deep/shallow relocation guard) are *reasoning*, not new
verified evidence. (4) The load-bearing honesty point: harm B transfers across
domains directly; harm A is a well-evidenced mechanism applied to prose by analogy.
The *claims* are machine-verified; the *argument connecting them* is mine and should
be reviewed as such.
