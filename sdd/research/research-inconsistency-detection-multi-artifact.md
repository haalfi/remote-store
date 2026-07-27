# Research: Detecting inconsistency among multiple descriptions of the same thing

**Date:** 2026-07-27
**Status:** Advisory research, revised after external review (see § 10 revision
note). Cross-discipline synthesis (deep-research harness, adversarially verified)
narrowed to software-under-SDD and technical engineering, then tested against one
live repository case (BK-324). Not a spec or ADR. The plan in § 9 is a proposal;
no backlog items were created.
**Scope:** What makes inconsistency between parallel descriptions of one subject
*detectable*; which detection mechanisms are proven in disciplines whose artifacts
are machine-readable and whose claim spaces are mechanically enumerable; which of
them this repository already runs; where our gates are structurally blind; and
what transfers to any multi-artifact process (§ 8).
**Related:** [`sdd/000-process.md`](../000-process.md) (Rules 2, 3, 5),
[`sdd/formal/README.md`](../formal/README.md),
[`sdd/CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md) (ripple-check),
[`research-bug-prevention-beyond-testing.md`](research-bug-prevention-beyond-testing.md),
[`research-expectation-driven-review.md`](research-expectation-driven-review.md),
[`research-id-232-detail-placement-durability.md`](research-id-232-detail-placement-durability.md),
`sdd/BACKLOG.md` BK-324, BK-325.

**Context:** We maintain many parallel descriptions of one library: Markdown
specs, Dafny contracts, TLA+ invariants, the implementation, the conformance
suite, docstrings, guides, `FEATURES.md`, the CHANGELOG, the backlog, and the
ripple-check. Twenty lint gates plus a preflight family, of which roughly half
reconcile an artifact *pair* (§ 4b lists eleven) while the rest are single-artifact
rule checks, already compare pieces of
that set. BK-324 nevertheless records four descriptions of the backend contract
disagreeing with each other, undetected by any gate, found by a human writing a
backend against the guide. This document asks what detection mechanisms exist,
why ours did not fire, and what to do about it.

> **Central honesty finding.** Detection mechanisms fall into three epistemic
> categories, and conflating them is the most common error in this space.
>
> 1. **Provable bound.** The mechanism's detection power is *derivable*, not
>    measured: LVS (graph isomorphism over extracted netlists), a discharged
>    Dafny postcondition, a type system, double-entry's nullspace. These need no
>    efficacy study, because what they catch and what they miss follows from
>    their construction. The obligation is to *state the bound*, since a
>    mechanism whose blind spot is undocumented will be trusted outside its range.
> 2. **Measured efficacy.** Mutation testing has real empirical support. statcheck
>    embedded in peer review has *quasi-experimental evidence of association* — the
>    authors' own framing is "is related to", with two treatment journals against
>    two controls, so calling it measured efficacy would upgrade their claim. The
>    measurements in this category are narrow, high precision over a slice, not
>    broad claims about defect reduction.
> 3. **Mandated, unmeasured.** Requirements traceability, safety cases,
>    attestation regimes. Here institutionalization is strong evidence that a
>    mechanism is affordable and politically survivable, and weak evidence that
>    it works. Where efficacy in this category *has* been measured, it usually
>    **underperforms** its reputation.
>
> The trap is reading category 3 as category 1, i.e. treating "the standard
> requires it" as "its coverage is known". Note also that being a mandatory gate
> is not evidence of efficacy: a tape-out cannot pass without LVS by
> construction, which tells you LVS is a gate, not that it is effective. LVS's
> real warrant is category 1. Treat § 3 as a design vocabulary annotated with
> which category each mechanism sits in, not a league table.

---

## 1. What counts as an inconsistency, and which kinds are detectable

An inconsistency exists when two descriptions make claims about the same subject
that cannot both be true, **or** when one description silently omits a claim
another treats as binding. The second half matters more than it looks: it is the
half our tooling is worst at.

Eight phenomena matter, but they are **not eight peers**. An earlier draft listed
them as one flat taxonomy and that was wrong: it mixed inconsistency types with a
precondition, a representation property, and a governance failure. They sit at
four different places in the detection pipeline.

**Inconsistency types** — the things a detector can actually find:

| Class | Definition | Instance in this repo |
|---|---|---|
| **A. Cross-domain contradiction** | Descriptions from different domains (intent / realization / verification / explanation) disagree | Spec prose demands `InvalidPath`, flat-NS backends raise `NotFound` (BK-324 facet 2) |
| **B. Cross-artifact contradiction** | Two artifacts of the same kind disagree | `MemoryBackend` vs `MemoryBackendMinimal`; `Store` vs `AsyncStore` |
| **C. Within-artifact self-contradiction** | One artifact's claims cannot all hold | A spec section whose table contradicts its own prose (BK-324 facet 3) |
| **D. Temporal drift** | Descriptions that were consistent and diverged through change | Guides describing superseded behavior |
| **E. Silent omission** | One description treats a claim as binding; another is simply silent | Empty-path `InvalidPath` enforced everywhere, specified nowhere (BK-324 facet 4) |

E is a different problem *in kind* from A to D. Comparing two present claims is a
matching problem; detecting an absent claim requires an independent enumeration of
what claims should exist. That difference is the hinge of this whole document
(§ 2.1).

**Precondition — F. Referential / identity.** Same name denoting different
subjects, or different names denoting one subject. This is not a class of
inconsistency, it is the **condition under which A to E can be stated at all**.
Without identity resolution, comparison produces both false positives (comparing
unrelated things) and false negatives (never comparing related things), and it
does so silently. Instance here: stale spec IDs in markers, capability name skew
across sources. `check_capability_parity.py` and the `unknown-spec` failure modes
of `check_formal_trace.py` are identity gates, not consistency gates.

**Representation blocker — G. Granularity mismatch.** Descriptions at
incommensurable levels of detail, so no pairwise claim comparison is possible
without an intervening mapping. Instance: one-line contract prose versus a
400-line backend. G is not detected so much as *suffered*: when nothing is
comparable, every check passes and the silence reads as agreement. Note that G and
E are hard to tell apart in the field — a claim that looks absent is often present
at a coarser resolution — and both need the same remedy, a canonical enumeration.
They differ in repair, not in detection: E needs the missing claim written, G needs
a refinement relation between levels.

**Post-detection failure — H. Authority ambiguity.** A real conflict exists and no
rule says which description governs. H is emphatically *not* an inconsistency
class: detection can succeed perfectly and H still blocks everything downstream.
It belongs in this document because the framing question insisted attribution is
part of detection *output*, and because BK-324 is stalled at exactly here (§ 5).

### The detectability gradient

Detectability is not a property of the class. It is a property of the *comparison*
the class demands.

| Tier | What the check requires | Decidable? | Automation | Attribution |
|---|---|---|---|---|
| **T0** Well-formedness | Grammar of one artifact | Yes | Total | Local |
| **T1** Referential integrity | Shared identifiers, resolvable links | Yes | Total | Flags the dangling end only |
| **T2** Closure / arithmetic identity | A derivable invariant | Yes | Total | Flags the identity, rarely the term |
| **T3** Constraint / rule violation | Shared schema plus external rules | Yes, within the rule language | High | Yes, if rules carry authority |
| **T3.5** Symbolic / bounded exhaustive comparison | Both sides expressible in a decidable-enough logic; a solver or model checker | Yes, within the type domain or the bounded model | High, at authoring cost | Yes, and it produces a counterexample |
| **T4** Behavioral comparison | One side executable, another an oracle | Over sampled inputs only | High but incomplete | By convention |
| **T5** Semantic comparison of prose | Meaning equivalence in natural language | No general oracle | Low | Rarely |
| **T6** Completeness | Independent enumeration of the claim space | Not in general | Very low | — |
| **T7** Intent and authority | Judgment about which description ought to govern | Not a decision procedure | None | This *is* attribution |

**T3.5 is where this repository's strongest tools actually live**, and an earlier
draft omitted the tier, which mis-slotted them. A discharged Dafny postcondition
is not rule checking (T3) and not sampled execution (T4): it is exhaustive over
every input the declared types admit. TLC is exhaustive over a bounded model. The
tier carries a fractional number because it was added after review rather than
renumber the rest.

**T4 degrades in practice to "agreement on the tested region".** Its reach is
bounded by generator quality (for property-based testing) and by oracle fidelity —
an oracle with a modelling gap cannot detect divergence inside that gap. Our own
formal README documents one: the capability-round-trip postcondition detects
*divergence* between `WriteResult` and the readable `FileInfo`, not *absence*, so
a backend returning all-`None` on both sides verifies clean. That is a T4 blind
spot stated honestly, and it is the correct way to hold a T4 mechanism.

Three consequences worth carrying forward. Detection power is bought with
formalization, and formalization competes with the work itself. The gradient is
not the same as importance: T6 is the least detectable tier and often the most
consequential. And **attribution degrades faster than detection** — T1 and T2
mechanisms flag with near-perfect reliability and attribute almost never.

---

## 2. Why our two disciplines are special

The broad survey covered accounting, construction, aviation, law, medicine and
experimental science alongside software. Most of its pessimism came from
disciplines whose artifacts are prose and whose ground truth is contested.
Software-under-SDD and technical engineering share three properties that change
the answer:

1. Artifacts are machine-readable, so comparison can be mechanical.
2. Identifier discipline is already institutional (part numbers, net names, spec IDs).
3. **The claim space is finite and enumerable from a canonical artifact.**

**Cheapness is deliberately not on that list.** An earlier draft listed "checks
are cheap" as a fourth precondition, which is a category error worth naming
because the whole document turns on keeping these axes apart. Cost does not
determine what is *detectable*; it determines how *often* a detection runs and
whether an organization sustains it. Aviation, medicine and clinical trials detect
a great deal with expensive mechanisms — first-article inspection, as-built
survey, double data entry, audit re-performance — and none of them is cheap. The
detectability gradient above ranks tiers by what the *comparison demands*, and
cost appears nowhere in it, correctly.

Cheapness is better understood as a **consequence** of properties 1 and 2, and an
*amplifier* rather than an enabler: it is why these two disciplines can run the
same mechanisms continuously instead of periodically, which is a real advantage
(§ 6) but a different claim from "we can detect more". Treating it as a
precondition would also license the wrong inference — that an expensive check is
not worth building — when the actual design rule is the opposite: put the check
where it cannot be routed around, then let its cost set its period.

Property 3 is the important one, and it produces the central finding of this
research. An earlier draft stated it as "omission is detectable in these two
disciplines and only in these two", which is **false** and does not survive
contact with a skeptical reader. Other disciplines have completeness devices: the
WHO surgical safety checklist, aviation's minimum-equipment and
configuration-deviation lists, pre-flight checklists, clause inventories in structured
contracts. The corrected claim:

> **Omission detection always reduces to maintaining a canonical, enumerable claim
> set. What distinguishes these two disciplines is that the enumeration can be
> *derived mechanically from the authoritative artifact*, rather than maintained
> as a parallel artifact of its own.**

That distinction is not cosmetic, and it is the reason the checklist
counterexamples do not defeat the argument. A checklist is a second description.
Someone enumerated it by hand, once; it drifts against the thing it enumerates;
and it therefore needs its own consistency maintenance. A discipline that solves
omission with checklists has bought a completeness oracle at the price of one more
artifact in the inconsistency problem. When the enumeration is derived — every
ballooned characteristic read off the drawing, every section ID read off the spec
file — it cannot drift against its source, because it *is* its source.

<a id="canonical-claim-set"></a>
### 2.1 The canonical claim set is the real bottleneck

Generalizing: the binding constraint on this whole problem is not which detectors
you own, it is **where the canonical claim set lives and whether it is
machine-enumerable**. Without one:

- **E is impossible.** There is nothing to take a set difference against.
- **A and B degrade into partial comparisons.** You compare the claims you thought
  to compare, and a clean report means only that.
- **G is invisible.** Nothing reveals that two descriptions were never comparable.
- **F is unenforceable.** Identity needs an authority that assigns names, and the
  claim set is where that authority is expressed.

This reframes the practical question. Not "which mechanism is missing?" but
"**which artifact is the enumeration source, and is anything derived from it?**".
For us the honest answer is that the claim set is *fragmented*: partly in spec
Markdown headings and requirement tables, partly in Dafny `// @spec` tags, partly
in conformance markers, and — for facet-4-shaped behavior — partly in the
implementation and nowhere else. § 5 argues that this fragmentation explains BK-324
more directly than "the gates are blind" does.

Fragmentation is not the same as having many descriptions, which is the deliberate
premise of SDD and fine. The defect is that **no single description is designated
as the enumeration source, and no derivation relation connects them.** Several
parallel descriptions are healthy when one is canonical for enumeration and the
others are checked against it.

The corresponding limit is equally sharp: **T5 is exactly as unsolved here as
anywhere.** Neither discipline can mechanically compare a prose claim to a
behavior. Every mechanism below either avoids prose or checks something adjacent
to it.

---

## 3. Mechanism catalog

Ten families survive the restriction. Ranked by detection strength, which here
means: does it catch the whole class, and does it **attribute**?

| # | Mechanism | Engineering instance | Our instance |
|---|---|---|---|
| **E1** | Equivalence check against a verified reference | LVS (layout vs schematic); RTL-to-netlist equivalence checking | Dafny `MemoryBackend` compiled and run through conformance as `DafnyOracleBackend` |
| **E2** | Characteristic accountability | AS9102 Form 3: every ballooned characteristic has a traceable inspection result | `check_spec_marks.py`, `check_formal_trace.py` |
| **E3** | Generation from a canonical model | Model-based definition; drawings generated from the 3D model | `gen_features.py`, `gen_graph.py`, `check_api_docs.py` |
| **E4** | Rule checking | DRC, ERC | `ruff`, `mypy`, the `check_*.py` lint family |
| **E5** | Pairwise parity assertion | Interface control documents | `check_capability_parity`, `check_docstring_parity`, `check_ripple_parity`, `check_ci_full_matrix` |
| **E6** | One normative description driving N artifacts | One inspection plan applied to every unit of a part family | The conformance suite across all backends |
| **E7** | Meta-checking the checker | Gauge R&R, proficiency testing, seeded defects | Mutation testing |
| **E8** | Scheduled reconciliation with a tolerance band | Periodic calibration, as-built survey | `drift-guard.yml` |
| **E9** | Tracked, tolerated divergence | Waivers, deviations, non-conformance reports | Conformance xfail registry, `[~]` markers |
| **E10** | Rehearsal / build-a-real-instance | Commissioning, first-article production | The custom-backend guide walkthrough (ad hoc) |
| **E11** | User-sourced discrepancy reporting | Defect/snag reporting, confidential incident reporting | Issue tracker; the trace corpus's `outcome: misleading` tags |

Three of these deserve detail.

### E1 is the strongest mechanism either discipline has

LVS-clean is a near-universal foundry prerequisite for tapeout — waiver-with-sign-off
in practice rather than an unconditional zero. LVS extracts a netlist
from the *realization* by tracing connectivity through metal layers and vias, then
compares it device-by-device and node-by-node against the netlist from the
*intent*. Unmatched nodes are reported individually for debugging, and device
properties **can be configured** to compare against a tolerance, with
out-of-tolerance reported as a property error. Alongside it, equivalence checking
compares RTL against the synthesized gate netlist, on the reasoning that every
synthesis transformation risks the netlist no longer implementing the RTL intent.

**State the bounds, since this section is the honesty finding's category-1
exemplar and a misstated bound here would be self-refuting.** Equivalence checking
proves *combinational* equivalence at **matched compare points** (registers,
primary output ports, black-box input pins), conditional on a 1:1 state-element
correspondence. Black-box contents are not verified, their outputs being treated
as primary inputs; unmatched compare points are reported rather than folded into a
global proof; inconclusive results from timeout or complexity are an ordinary
outcome; and sequential transformations such as retiming or state re-encoding put
the comparison outside combinational equivalence checking entirely. "Bit-exact
correspondence", which an earlier draft asserted, is blog phrasing and overstates
all of that.

Why the family is still the gold standard: within those bounds it is the only
mechanism in either discipline that compares two *independently authored*
descriptions across a domain boundary, mechanically, exhaustively, **and with
localization**. Not "these disagree" but "this node differs".

**We run a weaker relative of this, and the difference matters.** An earlier draft
called the `DafnyOracleBackend` our LVS, which over-claimed. LVS compares two
*fully formalized* representations by structural correspondence: exhaustive,
mechanical, one comparison. Ours is two steps with different strengths:

1. The Dafny verifier discharges `MemoryBackend` as a refinement of
   `BackendContract`. This is genuine **T3.5**: exhaustive over the declared type
   domain.
2. The compiled oracle then meets the real backends only through **T4**: shared
   conformance test cases over sampled inputs.

So the chain is "verified reference, sampled comparison", and its weakest link is
step 2. The oracle principle — if the oracle passes, the test is known-correct; if
it fails, the test has a bug — is LVS's *authority logic* correctly imported, but
not LVS's *coverage*. Nothing here compares a backend to the contract
exhaustively. Calling it equivalence checking would invite exactly the category-1
misreading warned about in the honesty finding.

### E2 is the answer to omission

AS9102's Form 3, "Characteristic Accountability, Verification and Compatibility
Evaluation", carries every design characteristic beside its requirement, its
measured result, and a unique identifier. The clause language — every design
characteristic requirement accounted for, uniquely identified, with inspection
results traceable to each unique identifier — traces to **AS9102A § 5.2**; Rev C
(2023) renumbers Form 3's fields, so cite the revision rather than a bare section
number.

Two precision notes, because the mechanism is easy to over-describe. What the
standard mandates is **unique identification and traceability**, satisfiable by a
balloon number "or similar identifier" — the ballooned drawing is the common
method, not the requirement, and sources asserting otherwise are FAI-tool vendors.
And FAI scope excludes procured standard catalog hardware and deliverable
software, so "every characteristic" holds *within FAI scope*. Neither weakens the
pattern being borrowed.

That is a completeness oracle at T6. It works because the characteristic set is
mechanically enumerable from the authoritative artifact. `check_spec_marks.py`
enumerates spec IDs from headings and requirement-table rows and asserts each has
a `@pytest.mark.spec`; `check_formal_trace.py` builds the three-way coverage
matrix across spec sections, Dafny `// @spec` tags and conformance markers. That
is ballooning plus Form 3, in CI.

**Rule 5 of `000-process.md` (IDs are stable; deprecated sections are marked, not
removed) is what makes this work.** It is load-bearing detection infrastructure,
not bookkeeping.

### E6 beats E5 whenever it is available

Two shapes recur and they scale differently. A **pairwise parity assertion** is
written per pair: N artifacts that must agree need O(N²) hand-authored checks,
each itself an artifact that can drift. Most of our `check_*` scripts are this
shape. **One normative description driving N artifacts** converts that to O(N) and
attributes for free, because the normative side is declared authoritative in
advance. The conformance suite is this; engineering's version is one inspection
plan applied to every unit of a part family.

Whenever a new parity check is proposed, the first question is whether the pair
can be re-shaped into E6. Some can. Some genuinely cannot: the ripple-check's two
presentations are two renderings for two reading moments, so parity assertion is
correct there and single-sourcing would defeat the purpose.

**The structural limit, stated plainly: pairwise parity does not compose into
global consistency.** A green wall of pairwise checks licenses no conclusion about
the artifact set as a whole. Claims can be pairwise consistent and jointly
unsatisfiable; a claim absent from every artifact in the set violates no pairwise
assertion at all; and a check only constrains the pairs someone thought to write.
This is why E5 cannot substitute for the canonical claim set of § 2.1 no matter
how many checks are added, and it is the strongest argument against answering
BK-324 with more gates.

### E10 is more important than its position suggests

Rehearsal — building a real instance and seeing what breaks — is the only family
that reaches **E, G and H simultaneously**. An exercise stops dead at the step
nobody wrote down (E), it forces two descriptions to a common level of detail
because the builder must act (G), and it surfaces authority conflicts because the
builder must pick a side and can say which choice was unclear (H). No mechanical
gate does any of those.

It is listed near the bottom because it is manual, unschedulable-by-default, and
produces findings in prose. That ranking is about cost, not power. **In the one
case this document has evidence for, E10 is the mechanism that actually worked**
(§ 5, finding 5), and every gate ranked above it was green at the time.

### E11 scales with usage rather than with checking budget

Every other family in the catalog costs more the more you check. E11 costs almost
nothing per finding and its yield grows with how many people *use* the
descriptions. Coverage is terrible and unplannable; precision is excellent,
because a reported discrepancy is one that actually obstructed someone.

The evidence for taking it seriously is uncomfortable and comes from the
discipline with the most heavily institutionalized detection machinery in the
broad survey. In the ACFE's *Occupational Fraud 2024*, **43% of frauds were
detected by a tip — 3.07× the next method — against 14% for internal audit and
13% for management review.** The cheapest, least formal channel out-detects the
professional apparatus built for exactly that job, by a wide margin. Read it as
detection-method *share* among discovered frauds rather than sensitivity (frauds
nobody found appear in no column), and it still reorders any detection portfolio.

**We already run this and the document was mis-filing it.** The trace corpus's
`outcome: misleading | unclear` tags are readers reporting that a description
obstructed them, attributed to the file that did it. That is E11, not E7. An
earlier draft classified step 3 as meta-checking, which misstates its purpose:
aggregating those tags does not measure a checker's miss rate, it harvests a
detection channel whose yield scales with how often people read our descriptions.
The distinction matters for how the output is used — a ranked list of
frequently-misleading references is a *work queue*, not a quality metric.

For a project this size that is the single best cost-per-finding ratio available,
and it needs no new mechanism, only aggregation.

---

## 4. Answering the core question for this repository

### (a) Across description domains

Our domains: intent (`sdd/specs/`, ADRs, RFCs), intent-formalized (`sdd/formal/`),
realization (`src/`), verification (`tests/`), explanation (`docs-src/`,
docstrings, `FEATURES.md`), and process (BACKLOG, traces, ripple-check).

| Mechanism | Domains it bridges | Classes caught | Attributes? |
|---|---|---|---|
| E1 verified-reference equivalence | intent-formalized ↔ realization | A, B, C | Yes, decisively |
| E2 characteristic accountability | intent ↔ verification | **E**, F | Yes, names the unaccounted ID |
| E3 generation | realization → explanation | Prevents A, B, D | — |
| E4 / E6 executable comparison | intent ↔ realization | A, D (sampled) | By declared convention |
| Declared attribution rules | any pair | — | This *is* attribution |

That last row is where we are genuinely ahead of most engineering organizations.
Rule 3 ("if code and spec disagree, the code is wrong"), the CLAUDE.md principle-5
pair ("backlog vs history conflict: backlog is wrong"), and the oracle principle
are **pre-declared authority rules per artifact pair, in writing**. Most processes
never write the convention down, which is why their findings stall. § 5 shows
where our coverage of pairs is nevertheless incomplete.

### (b) Within one domain, across artifacts

The inventory below was **assembled by hand for this document**, because no
canonical one exists. That is itself a finding, and it is § 2.1 applied one level
up: we have no enumeration of *which artifact pairs are checked*, so the checking
layer has exactly the defect this document diagnoses in the specification layer.
The table will drift, and nothing will notice — which is why § 9 step 8 proposes
deriving it from the `check_*.py` docstrings rather than leaving the gap named and
unaddressed.

| Pair | Domain | Current detection |
|---|---|---|
| `Store` ↔ `AsyncStore` | realization | `check_docstring_parity.py` (docstrings only); behavioral parity is a DoD checkbox |
| Backend *i* ↔ backend *j* | realization | Conformance suite (E6) |
| `MemoryBackend` ↔ `MemoryBackendMinimal` | intent-formalized | **None in CI. Review only, documented** |
| `Capability` enum ↔ Dafny datatype ↔ `CapabilityName` arms | cross-source | `check_capability_parity.py` |
| `ci.yml` ALL_PYTHONS ↔ `ci-full.yml` matrix | process | `check_ci_full_matrix.py` |
| Ripple-check index ↔ detailed checklist | process | `check_ripple_parity.py` |
| API doc pages ↔ graph IR | explanation | `check_api_docs.py` |
| `infra/.env` ↔ `infra/_settings.py` | process | `check_infra_settings.py` |
| Guide tables ↔ `Backend.__abstractmethods__` and the conformance suite | explanation ↔ realization | `check_custom_backend_guide.py` |
| Workflow files ↔ `sdd/CI-OPERATIONS.md` prose | process | `check_ci_inventory.py` |
| Canonical backend order ↔ every enumeration of it | cross-surface | `check_backend_order.py` |

The last three rows are **prose-side gates**, and they matter to § 6 and G-2: each
binds prose to a mechanically derived enumeration. `check_custom_backend_guide.py`
requires the guide's abstract-methods table to list exactly
`Backend.__abstractmethods__`; `check_ci_inventory.py` differences the workflow
directory against handbook prose; `check_backend_order.py` drives every
enumeration from one canonical order. They are three working templates for
derive-and-difference, which is the pattern § 9 step 2a wants.

---

## 5. The BK-324 case: what our gates cannot see

BK-324 records contract prose, the Dafny model, the conformance suite and shipped
backends disagreeing across four facets. It is the best available evidence about
our detection coverage, because every gate was green throughout.

### Finding 1: all four facets are the prose spec

- Facet 2: prose (BE-017/BE-021) demands `InvalidPath`; flat-NS backends raise `NotFound`. Prose contradicts code.
- Facet 3: prose in [spec 037](../specs/037-depth-limited-listing.md) licenses ignoring `max_depth` while the Dafny model and DEPTH-003 tests require native pruning; 037's table is also wrong about S3 and Azure. Prose contradicts mechanism, and contradicts itself.
- Facet 4: empty-path `InvalidPath` on move/copy is Store-enforced and guarded defensively by *every* backend, but absent from BE-018/BE-019 and untested. Prose absent, behavior uniform.
- Facet 1: backend-layer obligations for `""`/`"."` are unspec'd, and `is_file("")` raises on the S3 family but not elsewhere. Prose absent **and** the backends disagree with each other.

So the split is not a tidy two-and-two. Three facets are prose-shaped, and facet 1
carries an additional **class B** component: an undetected cross-artifact
divergence with no prose to say which side is right. That is a second data point
for § 3's non-composition limit — no pairwise check covers
backend-*i*-versus-backend-*j* on `is_file("")`, because the conformance suite has no cell for it.

What survives, and it is the finding that matters: **Rule 3 makes the Markdown
spec authoritative over everything, and spec prose is the only description in the
formal layer with no mechanical counterpart.** Dafny is verified, TLA+ is
model-checked, tests are run, backends are conformance-driven. Spec prose is read.
The most authoritative artifact is the least checked one.

### Finding 2: our traceability is identifier-keyed, and BK-324's claims are not identifiers

An earlier draft said `check_formal_trace.py` is referential integrity and called
that a defect. Both halves were wrong, and the correction sharpens the argument.

The script has **three** failure modes, not two. F2 (`conformance-cites-unknown-spec`)
and F3 (`dafny-tag-unknown-spec`) are referential integrity, T1. But **F1
(`dafny-clause-untested`) is a set difference** — a spec ID carrying a verified
Dafny postcondition that no conformance marker cites. That is omission detection
over a derived enumeration: E2, tier T6, not T1.

**State its bound precisely, since this is the in-repo exemplar §§ 3 and 5 lean
on.** F1 is not `D \ T` but **`(D ∩ S) \ T`**: the script's own docstring defines
it as a Dafny-tagged ID *declared in S* that no marker cites. The `S` conjunct is
load-bearing — a Dafny tag naming an ID absent from the specs falls to F3, identity
at T1, and never reaches the completeness check. And the difference is taken
**minus a human-editable suppression set**: `_BASELINE` parks known violations, and
the docstring says so plainly — "Baseline *growth* is NOT blocked mechanically — a
new violation can be parked by editing `_BASELINE`. That edit is visible in review
and is the point where a human must refuse new debt; the check cannot make that
judgement."

So the honest characterization of our best T6 mechanism is: **a set difference over
the intersection of two derived enumerations, minus a reviewer-maintained
allow-list.** That is a category-1 bound, the script states it, and an earlier
draft of this document omitted it — which inverts the point made two paragraphs
below about stated bounds being the correct way to hold such a mechanism.

Nor is the residual gap a defect. The script's docstring states its own bound
explicitly and at length — "**Citation, not assertion.** T records that a marker
naming an ID sits on a test; it does not verify the test asserts that clause, or
that the test is even enabled ... or that the cited ID is the *right* one" — and
by this document's own honesty finding, a **stated** bound is the correct way to
hold a category-1 mechanism. Contrast finding 3, which is a genuinely *unstated*
boundary. Stating a bound is the obligation; meeting it is not.

The accurate finding is therefore narrower and more useful:

> Our traceability runs T1 **plus a bounded T6 completeness check**, over
> **identifier-granular** claim spaces: spec IDs, capability names, method names,
> workflow filenames. BK-324's claims are not identifiers. "Backends must raise
> `InvalidPath` on wrong-type access" is a sub-ID clause inside a section, so
> nothing enumerates it and no set difference can reach it.

### Finding 3: the formal layer's decoupling argument has a gap

[`sdd/formal/README.md`](../formal/README.md) argues that Dafny and TLA+ need no
joint proof obligation because both are bound to the same Markdown spec, "so a
drift surfaces as a verification failure on one side or the other". Facet 3 is a
counterexample. The Dafny model and the DEPTH-003 tests agree **with each other**
and disagree with the prose. Two mechanical sides in agreement produce two green
checks, and the drift is invisible precisely *because* the coupling is semantic.

The argument holds when drift moves one mechanical side. It does not hold when the
prose is the side that moved. This is worth recording in the formal README rather
than leaving as an unstated boundary.

### Finding 4: facet 4 is an orphan-realization defect

Our characteristic accountability runs spec → test. NASA's **SWE-064**
(bidirectional traceability between software *design and code* — an earlier draft
cited SWE-059, which is requirements ↔ design and so the wrong direction for this
finding) states the rationale explicitly: the two directions catch structurally
different defects, namely design elements not fulfilled in the code, and source
code with no parent design element. Note that NPR 7150.2 Rev C and handbook
Ver C-D consolidate these into **SWE-052**, so a bare SWE-064 cite is current only
against Rev A-B.

We have direction one. Facet 4 is a direction-two defect: a convention enforced by
`Store`, defensively guarded by every backend, in no spec, untested.

### Finding 5: BK-324 was found by rehearsal, not by a gate

Both BK-324 and BK-325 surfaced from PR #932's guide validation, i.e. a person
building a real backend against the guide. That is commissioning, and it found
what twenty gates could not. E10 is the only family that routinely reaches class E,
because an exercise stops dead at the step nobody wrote down. We currently run it
by accident, when someone happens to open a guide PR.

### Finding 6: the effort is attribution, not detection

BK-324 reads "Decide each rule once, then align". Detection finished months ago;
the L is class H. Rule 3 arbitrates spec versus code, but facets 2 and 3 need
arbitration *within* the intent domain, where the prose may be the wrong side.
Our declared attribution rules do not cover prose vs Dafny vs conformance.

### Finding 7: the trace corpus already named the culprits

Across 258 traces we have recorded **167 `misleading` and 20 `unclear`** outcome
tags, 187 combined. (An earlier draft counted `sdd/traces/*.yml`, one character
looser than `check_traces.py`'s `sdd/traces/[!_]*.yml`, and so counted
`_schema.yml` as a trace.)

**Attribution here is structural, not heuristic.** `_schema.yml` makes `file` a
required property of every step, with `outcome` a sibling and
`additionalProperties: false`, so each tag is attached to exactly one file by the
schema. A YAML parse gives exact counts — a point worth making because an
intermediate draft *softened* these numbers on the strength of a grep-derived
bound, which was an artifact of the tool rather than a property of the data.

**These numbers are exact and already perishable, which is the argument for
step 3 in miniature.** They were re-measured twice during review: once to correct
an extraction artifact, and once because a rebase onto `master` pulled in a new
trace mid-review and moved every total by one. A hand-maintained count of a
growing corpus is a description that drifts against its source by construction —
precisely the defect this document is about, committed by this document. Table
measured at the head of this branch; step 3's generated report supersedes it.

| `misleading` + `unclear` | Reference |
|---|---|
| 16 | `sdd/BACKLOG.md` |
| 8 | `src/remote_store/backends/_sftp.py` |
| 7 | `sdd/CLAUDE-REFERENCE.md` |
| 7 | `src/remote_store/backends/_local.py` |
| 6 | `sdd/BACKLOG-DONE.md` |
| 5 | `CONTRIBUTING.md` |
| 5 | `src/remote_store/backends/_azure.py` |
| 4 | `sdd/audits/audit-014-grandfathered-tests-allow-list.md` |
| 4 | [`sdd/specs/029-async-store-backend-api.md`](../specs/029-async-store-backend-api.md) |

The column is the two tag types **combined**; the sentence above reports them
separately, and spec 029's four happen to be four `misleading` and zero `unclear`,
so the two readings coincide there and nowhere else signals which metric is shown.
Two entries were missing from an earlier version of this table, both dropped at a
tie by an approximate extraction. Their return changes what it says: with
`_azure.py` included, **three backend implementations sit in the top seven**, so
misleading descriptions cluster in backend code at least as much as in process
docs.

BK-324's header reads `spec: 003, 029, 037`. **Spec 029 carries exactly four
`misleading` tags, all predating BK-324.** The signal existed, attributed and
committed, and nothing aggregates it — that absence, not any imprecision in the
data, is the argument for step 3. A description that repeatedly misleads a reader
is a drift detector with attribution already attached, and we are discarding it.

### Synthesis: the failure is a tier mismatch, not a missing detector

Compressing findings 1 to 7 against § 1's structure, BK-324 decomposes as:

| Element | Where it sits |
|---|---|
| Backend-contract claims exist in prose, Dafny, tests and code with no unified identity | **F** — precondition unmet |
| No enumeration of what the backend contract *claims*, so nothing can be differenced | **E** — and § 2.1's bottleneck |
| One-line contract prose vs 400-line backends, never comparable | **G** |
| `is_file("")` diverging across backend families with no cell to compare them (facet 1) | **B** — and a second data point for § 3's non-composition limit |
| No precedence among prose, Dafny and conformance | **H** |

An earlier draft concluded here that "every mechanism we run sits at T1 to T4,
the failure lives at T6 and T7". **That was wrong, and it contradicted § 3 of this
same document**, which correctly calls `check_spec_marks.py` and
`check_formal_trace.py` a completeness oracle at T6. Several gates do run a
derived-enumeration set difference, which is the T6 shape:

| Gate | Enumeration it differences |
|---|---|
| `check_formal_trace.py` F1 | (Dafny-tagged ∩ spec-declared) \ conformance-cited, minus the `_BASELINE` allow-list |
| `check_spec_marks.py` | Declared spec sections \ marker-cited IDs |
| `check_capability_parity.py` | Set *equality* across three sources, so omission in both directions |
| `check_docstring_parity.py` | Shared-docstring methods in neither the identical nor the divergent set |
| `check_ci_inventory.py` | Workflow files \ handbook prose |

The decisive observation is therefore not that we lack T6. It is:

> **Our T6 coverage is real but confined to identifier-granular claim spaces** —
> spec IDs, capability names, method names, workflow filenames. BK-324's claims
> are sub-ID clauses inside spec sections, so no enumeration reaches them and no
> set difference can fire. We are missing a **claim space at clause granularity**
> (T6) and an **authority model** (T7).

That is a sharper diagnosis and it changes § 9's framing materially. Step 2 is not
building an enumeration discipline from nothing; it is **extending an established
one down a granularity level**, with five working precedents in-repo. Adding a
twenty-first *identifier*-keyed check would still not have moved BK-324 by a day.

**A tempting T6 check, and why it is not the one we need.** The obvious relation is
"every invariant enforced in Dafny must appear in the spec", i.e. `I ⊆ S`. That is
a worthwhile check and § 9 step 2b proposes it. But note carefully that **it would
not have caught facet 4.** Facet 4's behavior is absent from the spec *and*
untested, and the item flags only a Dafny *coupling* to mind rather than an
existing Dafny invariant. The claim lives in the Python implementation and nowhere
else. Catching it needs the *implementation → spec* direction, `Impl ⊆ S`, which is
strictly harder because implementation invariants are not declared, only enforced.
The distinction matters: `I ⊆ S` polices the formal layer's honesty, while
`Impl ⊆ S` is what finds orphan behavior. We want both, and only the second closes
facet 4.

---

## 6. Where we lead and where we do not

**Ahead of most practice:** omission is partially mechanized (E2); reconciliation
frequency is per-change rather than periodic; attribution rules are declared per
pair in writing; and we have a real miss-rate estimator in mutation testing, which
most projects lack entirely.

**Not ahead, and worth being honest about:**

- **Spec prose is unchecked** (§ 5, finding 1), and it is authoritative. Note the
  qualifier: guide prose, handbook prose and enumeration prose all *do* have
  mechanical counterparts (§ 4b's last three rows). It is specifically the
  artifact Rule 3 makes authoritative that has none.
- **Tolerance thinking is underdeveloped.** Engineering states acceptable deviation
  *in the specification* — LVS compares device properties to a configured
  tolerance; GD&T makes acceptable variation part of the spec. We mostly treat
  every difference as pass/fail, with tolerances buried in check implementations.
- **Rehearsal is unscheduled** (§ 5, finding 5).
- **Traceability efficacy is measured on adjacent outcomes only.** Not a void:
  maintenance speed, task correctness and defect-density correlation all have
  studies (§ 10). What no study measures is **escaped-defect reduction**, which is
  the outcome the mandate rests on. E2's value
  rests on the structural omission argument, not on measured defect reduction.

---

## 7. Gaps, ranked

Ordered by consequence times cheapness.

**G-1. `MemoryBackend` ↔ `MemoryBackendMinimal` drift is invisible to CI.**
Documented in [`sdd/formal/README.md`](../formal/README.md): Dafny has no
class-to-class inheritance, so `MemoryBackendMinimal` duplicates every method
body; `dafny_verify.sh` passes on both after a one-sided edit because each proves
its own contract. A known, documented, undetected class-B inconsistency in the
layer everything else trusts. This is what LVS exists to solve, and
`check_docstring_parity.py` already implements the needed
identical-versus-intentionally-divergent distinction.

**G-2. Spec prose has no mechanical counterpart.** The structural finding of § 5,
and the rank stands, but the scope is narrower than an earlier draft claimed:
guide, handbook and enumeration prose are all mechanically bound (§ 4b). Fully
closing it for spec prose requires T5, which is unsolved. Partially closing it
does not, and the repo already has three templates for how — see steps 2 and 4.

**G-3. Traceability is unidirectional and identifier-keyed.** Two limits, not one.
Direction: spec → test only, so orphan realization (behavior with no parent spec)
is undetected, and BK-324 facet 4 is the live instance. Granularity: enumeration
stops at the identifier, so sub-ID clauses are unreachable by any set difference
(§ 5 synthesis). Step 2a addresses the first; the second is the harder half.

**G-4. The trace corpus is an unexploited drift detector.** 187 negative-outcome
tags, already attributed, never aggregated.

**G-5. No published characteristic-accountability record.** `check_formal_trace.py`
computes the coverage matrix and discards it. AS9102's insight is that the
*retained record* is the artifact: what was verified, by what, at which release.

**G-6. Rehearsal is unscheduled.** The mechanism with the best findings-per-unit-noise
in the catalog runs only when someone opens a guide PR.

**G-7. Tolerances live in check implementations, not in specs.**

**G-8. Async twin behavioral parity is a checklist item, not a gate.**

**G-9. Independence is assumed and never verified.** E1's whole warrant is that the
Dafny contract is an *independent* description of the same behavior. Nothing checks
that it is. See S8.

---

<a id="principles"></a>
## 8. Substrate-independent design principles

The sections above diagnose this repository. These are the transferable rules, and
they are the generalizable output of the exercise — a reader who does not work on
this project should be able to take these and leave the rest. Each is stated once
and points at where it is argued, rather than re-arguing it. All
`[analysis, unsourced]` except where a section carries evidence.

**S1. Prefer one normative description driving N artifacts over N² pairwise parity
checks.** Reach for a parity assertion only when the artifacts are genuinely two
renderings for two audiences. Pairwise consistency does not compose into global
consistency, so no wall of parity checks licenses a conclusion about the set (§ 3).

**S2. A mechanical check should localize, not merely fail.** LVS reports the
unmatched node. "These two disagree" leaves the expensive half of the work undone,
and is the quality bar any new gate should clear (§ 3, E1).

**S3. Enumerate the claim space from a canonical artifact, and require an
accounted-for result per claim.** The only known defense against omission, and it
lives or dies on stable identifiers (§ 2.1, § 3 E2). Its reach stops where the
enumeration's granularity stops (§ 5 synthesis).

**S4. Declare the authority rule per artifact pair, in writing, before the check
exists.** Detection without a pre-agreed authority rule stalls in class H
indefinitely, which is why BK-324 is effort L (§ 5, finding 6).

**S5. Put the detector on a path nobody can route around.** The best-evidenced
principle here: the same checker changed nothing as an optional download and moved
the numbers when embedded in review. Deployment position dominated detection power
(§ 10). Corollary: an excellent optional checker is usually worth less than a
mediocre mandatory one.

**S6. Distinguish tolerated from unnoticed, structurally.** Waiver registries and
`[~]` markers are what let an organization afford to keep looking; without them,
detection gets switched off under schedule pressure (§ 3, E9).

**S7. Estimate the miss rate, not just the finding count.** Detection reports a
numerator. Without seeded discrepancies the denominator is unknown and "we checked
and found nothing" is uninterpretable (§ 3, E7).

**S8. Independence of *derivation path* is what makes a second description
informative — and it must be verified, not assumed.** This is the principle the
narrowing nearly lost, and it has teeth here.

Knight & Leveson had 27 versions of one program written independently from a
common specification, ran a million tests, and found joint failures far above what
independence predicts: **producers being independent does not make their errors
independent**, because a specification that handles a case badly misleads everyone
who reads it. Every mechanism whose power rests on independence inherits this —
E1's verified reference, E3's canonical source, E5's parity pairs.

Applied to us, uncomfortably: **E1's entire warrant is that the Dafny contract is
an independent description of the same behavior.** If a `.dfy` postcondition was
written by reading the Python implementation rather than the Markdown spec, the
oracle certifies nothing except that the transcription was faithful — a
correlated-error failure of exactly Knight & Leveson's shape, and one that leaves
every gate green. Nothing in the repository records or checks which source a
postcondition was derived from. That is G-9, and the cheap mitigation is
procedural rather than mechanical: require the derivation source to be stated when
a Dafny clause is authored, so a reviewer can see whether the second description
is genuinely second.

**S9. Set the reconciliation period from the drift rate, not the calendar.**
Annual, at-milestone and at-admission are conventions inherited from what it used
to cost to stop and look. When the cost of a check falls, the correct period falls
with it: continuous integration is a scheduled reconciliation ritual with the
period driven toward zero, which is the one place software genuinely leads (§ 6).
Ask of every recurring check what its period would be if it were free, and anchor
it to the events that can invalidate the artifact rather than to a date — as
step 6 does. Note the boundary with § 2: cost does not decide what is *detectable*,
only how often you look.

---

## 9. Plan of next steps

Proposed, not created. Each step names the gap it closes, the mechanism family it
instantiates, and a rough size. Steps 1 to 4 are independent and can land in any
order.

**Ordering follows the § 5 synthesis, not the gap ranking.** Two steps build the
things actually missing — a canonical claim space and an authority model — and the
rest are patches, however worthwhile:

- **Strategic: step 2a** (claim space, T6) and **step 5.1** (authority model, T7).
  Nothing else addresses what BK-324 exposed.
- **Cheap and independently worth doing now: step 3** (aggregate trace tags; the
  data is already committed) and **step 1** (twin parity; a documented, undetected
  class-B defect in the layer everything trusts).

A reasonable first slice is step 3 plus step 1 for immediate value, then step 2a
as the real work.

### Step 1 — Parity gate for the Dafny twin classes
**Closes:** G-1 · **Mechanism:** E1/E5 · **Size:** M

Add `scripts/check_dafny_twin_parity.py`: normalize each method body of
`MemoryBackend` and `MemoryBackendMinimal` and assert correspondence modulo the
declared capability-set difference, with an explicit allowlist for intentional
divergence. Model it on `check_docstring_parity.py`, which already solves the
"identical versus deliberately divergent" classification problem. Wire into
`lint`. Record in the formal README that twin drift is now gated.

### Step 2 — Bidirectional traceability (the canonical claim space)
**Closes:** G-3, § 2.1's bottleneck, and BK-324 facet 4 concretely ·
**Mechanism:** E2 · **Size:** M (2a) + S (2b)

This is the T6 half of the § 5 synthesis and the strategically important step.
Framing matters: per the § 5 synthesis this is **not building an enumeration
discipline from nothing**. Five gates already run derived-enumeration set
differences, and three of them (`check_custom_backend_guide.py`,
`check_ci_inventory.py`, `check_backend_order.py`) already target prose. Step 2
extends that discipline in two directions it does not yet cover: *toward the
implementation*, and *below identifier granularity*. Two sub-steps, and **2a is
the one that closes facet 4**:

**2a. `Impl ⊆ S` — enforced behavior must have a parent spec section.** Extend
`check_formal_trace.py` (or add a sibling) with the implementation direction. The
tractable shape is a **pass over raise sites in the backend package**: each must be
reachable from a spec ID via an existing marker or an explicit allowlist entry.
**The allowlist is the deliverable**, not the gate: on day one it enumerates every
orphan behavior we have, which is precisely what facet 4 turned out to be.

**Order of magnitude, because it changes the proposition.** An AST pass over
`src/remote_store/backends/` at the time of writing finds raise statements in the
**several hundreds**, with roughly a quarter as many again in the core modules.
(Counts vary by method — whether bare re-raises inside `except` blocks are
included moves the total materially — so treat the magnitude, not any figure, as
the input to planning.) A day-one allowlist of that size is a different
proposition from a dozen entries, and it is what makes "expect the first cut to be
approximate" concrete. Two consequences the backlog item must settle:

1. **Gate or report?** Step 3 is deliberately a report, not a gate, to avoid the
   false-positive fatigue that defeats rule checkers. A gate over a
   several-hundred-site heuristic invites the same objection, and this document does not resolve it.
2. **Scope beyond the backend package.** Facet 4's *normative* enforcement lives one
   layer above the backend tree, in the path-normalization layer; the backends hold
   defensive duplicates. So a backends-only pass does reach facet 4, but through the
   duplicates, and would record the behavior one layer from where it is actually
   enforced. Covering the core modules too is probably right.

**2b. `I ⊆ S` — every Dafny invariant must appear in the spec.** Cheap, because
`// @spec` tags already exist and `check_formal_trace.py` already parses them: the
check is that a Dafny postcondition carrying no spec coordinate, or one whose
coordinate has no prose counterpart, fails. This polices the formal layer's
honesty and would catch a *different* drift than 2a. Do it second and do not
mistake it for the facet-4 fix.

### Step 3 — Aggregate trace outcome tags
**Closes:** G-4 · **Mechanism:** E11 (not E7 — see § 3) · **Size:** S

Add `scripts/report_trace_outcomes.py` producing a ranked table of references by
`misleading` + `unclear` count, with the citing traces. Run it as a report, not a
gate — there is no correct threshold, and gating it would create exactly the
false-positive fatigue that defeats rule checkers elsewhere. Review the top of the
list at the same cadence as the TLA+ status revisit.

**Specify the extraction method, do not leave it open.** Reuse `check_traces.py`'s
`sdd/traces/[!_]*.yml` glob rather than re-deriving it, and read
`phases[].steps[]` as **parsed YAML**, taking `file` from the same mapping as
`outcome`. Both details are load-bearing: a looser glob reintroduces the
`_schema.yml` off-by-one, and a nearest-preceding-key text scan reintroduces the
attribution imprecision that caused a round trip in this document's own review.
The schema guarantees exactness; only a sloppy reader loses it. That also makes
this step smaller than S suggests — the data is committed and exact.

### Step 4 — Generate spec 037's backend table
**Closes:** part of G-2, and BK-324 facet 3 · **Mechanism:** E3 · **Size:** S/M

A hand-maintained table making per-backend behavioral claims is the artifact class
that must never be hand-maintained; we already generate `FEATURES.md` from
`graph.json`. Either derive 037's table from capability declarations plus
conformance results, or delete it and link to the generated surface. Then sweep
for other hand-written per-backend claim tables and treat each the same way.

### Step 5 — Decide BK-324's four rules, with an attribution rule first
**Closes:** the BK-324 blockage · **Mechanism:** attribution · **Size:** L

The item is L because of class H, so unblock the attribution before the content.
Two sub-steps:

1. **Extend the declared attribution rules to cover the intent domain internally.**
   Rule 3 settles spec vs code. Add the missing precedence for prose vs Dafny
   postcondition vs conformance test, including the case where the prose is wrong.
   This is a `000-process.md` amendment and it generalizes well beyond BK-324.
2. **Then decide each of the four rules once** and align spec prose, Dafny model,
   conformance coverage, docstrings and backends together, per the item's own plan.

Facet 2 deserves a specific framing: flat-NS `NotFound` is either a defect or a
legitimate variation, and if it is legitimate the fix is to make it a **declared
capability** so the conformance suite parameterizes on it. That converts an
undeclared divergence into a declared one, which is our existing pattern.

**Classification note for the owner's decision:** BK-324 currently sits under
*Docs & Discoverability*. Facets 2 and 3 change runtime behavior or spec
semantics and may be breaking. Found via docs, but arguably not a docs item, and
the filing risks it reading as cosmetic.

### Step 6 — Schedule the rehearsal
**Closes:** G-6 · **Mechanism:** E10 · **Size:** S to define, M per run

Make "build a backend against the guide, from scratch, without help" a scheduled
exercise rather than a side effect of guide PRs. Its output is a list of places
the guide, the contract or the conformance suite failed the builder.

**Say the evidence level out loud: n = 1.** The justification is a single run
(PR #932), and E10's claim in § 3 to the best findings-per-unit-noise in the
catalog rests on that same run. The step is cheap and probably right, but this
document is scrupulous about evidence strength everywhere else and should not make
an exception where the ranking is most flattering to the recommendation.

**Cadence, since "S to define" is otherwise empty.** Proposed: **once per minor
release, or after any change to the `Backend` ABC or the conformance suite,
whichever comes first** — the two events that can invalidate the guide. Anchoring
it to contract change rather than to the calendar follows **S9** and gives the
step actual content beyond the word "scheduled".

### Step 7 — Publish the characteristic-accountability record
**Closes:** G-5 · **Mechanism:** E2 · **Size:** S

Render `check_formal_trace.py`'s coverage matrix as a generated artifact at
release time: every spec ID, its verification evidence (test marker, Dafny tag,
TLA+ invariant), and its status. Makes "what was verified, and by what" answerable
historically rather than only at HEAD.

### Step 8 — Derive the artifact-pair inventory instead of hand-maintaining it
**Closes:** the § 4b reflexive gap · **Mechanism:** E3 · **Size:** S

§ 4b's inventory of which artifact pairs are checked was assembled by hand and the
document says of it: "The table will drift, and nothing will notice." Leaving a
self-diagnosed gap out of the plan is conspicuous in a document whose thesis is
that unenumerated claim spaces are where things hide, so it gets a step rather
than a shrug.

The fix is this document's own E3: derive the inventory from the `check_*.py`
docstrings and publish it as a generated surface. That also gives step 7's
accountability record a natural companion — one enumerates spec coverage, the
other enumerates *checker* coverage.

**Two complications that belong in the step, not in the implementation surprise.**
First, **not every gate guards a pair.** A substantial minority are single-artifact
rule checks — this document's own E4 — whose docstrings state a *rule*, not a pair
(assertion presence, mock discipline, forbidden RST roles, em dashes in TLA+). A
derivation over the docstring corpus yields no row for those, so the deliverable is
a derived inventory of *pair* gates **plus an explicit "rule check, no pair"
classification**. Second, the `scripts/check_*.py` glob **under-reaches**:
`scripts/docs/check_links.py` is a genuine cross-artifact gate outside it.

Both mean the step needs either a docstring convention to key on or a curated
mapping — and a curated mapping is precisely the parallel-artifact-that-drifts
problem § 2.1 warns about. Naming that up front is the difference between a cheap
step and a step that quietly recreates the defect it closes.

### Deferred, with reasons

- **Standing async-parity contract suite** (G-8): the right shape is E6, but the
  DoD checkbox is currently holding. Revisit when a parity defect escapes.
- **Tolerances in specs** (G-7): worth a pass over the numeric gates, but no
  evidence yet that implicit tolerances have caused a miss.
- **Whole-implementation formal equivalence:** a category error. LVS works because
  both sides are finite Boolean functions over a common encoding. Our Dafny layer
  correctly scopes to a reference backend and per-operation contracts, and the
  formal README already reasons its way there.
- **As-built capture, first-article-per-unit, counterparty confirmation,
  attestation with personal liability:** no software analogue worth building.

---

## 10. Evidence ledger and method caveats

**Method.** A deep-research harness ran six search angles, extracted claims, and
adversarially verified them (three voters per claim, two refutations to kill). One
harness fault degraded that run: the automated verification stage lost its search
tool to a permission-handler error, so ten of eleven claims were refused
*procedurally rather than substantively*. All load-bearing claims were
subsequently re-verified by hand against search results, twice.

**A standing environmental constraint, not a one-off fault.** Full-text fetching
returns HTTP 403 for **every** external host under this repository's session
egress policy. That reproduced identically across three separate rounds of work on
this document, so it is a property of the environment rather than a failure of any
one run, and it sets a **permanent ceiling on citation quality for research docs
in this repo**: "this work exists, is correctly attributed, and reports these
numbers" is reachable; verbatim quotation and capture of methodological caveats
are not. Any future research doc here inherits the same ceiling and should
disclose it the same way. Whether that warrants a documented citation convention
is a reasonable backlog question and is not decided here.

**Verified** (search-confirmed, full text unread). **Which rows carry the
argument:** LVS and equivalence checking underwrite § 3 E1; AS9102 Form 3
underwrites § 3 E2; SWE-064 underwrites § 5 finding 4; statcheck and double entry
underwrite the honesty finding; MIL-HDBK-61A and Bosché are adjacent to E8 and the
as-built deferral; **Knight & Leveson underwrites S8** and **ACFE 2024 underwrites
E11**. Both were orphaned in an earlier revision, and the reason is worth
recording: the narrowing dropped the two mechanisms they support, leaving the
evidence in place with nothing to attach to. Restoring the mechanisms was the
correct fix, not deleting the rows.

**One row still supports no claim in §§ 1 to 9:** the clinical-decision-support
override figure. It is retained as provenance for the broad cross-discipline
survey this document was narrowed from — that survey is not in this repository,
so the row must stand on its own citation, which it now does. A reader should not
infer that alert fatigue is load-bearing here; it is background for E4's
false-positive economics, nothing more.

| Claim | Source |
|---|---|
| LVS extracts a layout netlist and compares it device-by-device and node-by-node against the schematic netlist; device-property comparison **can be configured** against a tolerance. LVS-clean is a near-universal foundry prerequisite for tapeout (waiver-with-sign-off, not an unconditional zero) | Synopsys glossary; Wikipedia LVS |
| Equivalence checking proves **combinational** equivalence at matched compare points (registers, primary outputs, black-box input pins), conditional on a 1:1 state-element correspondence; standard synthesis sign-off. Black-box contents are unverified, and sequential transformations such as retiming fall outside it | Synopsys Formality |
| AS9102 Form 3 ("Characteristic Accountability, Verification and Compatibility Evaluation") carries requirement, measured result and unique identifier per characteristic. The "accounted for, uniquely identified, results traceable to each unique identifier" clause language traces to **AS9102A § 5.2**; Rev C (2023) renumbers Form 3 fields. The mandate is unique identification, satisfiable by "a balloon number **or similar identifier**" — ballooning is the common method, not the requirement. FAI scope excludes procured standard catalog hardware and deliverable software | AS9102A § 5.2, practitioner analysis |
| NASA **SWE-064** (bidirectional traceability, software **design ↔ code**) carries the rationale used in § 5 finding 4: it surfaces design elements not fulfilled in code, and code with no parent design element. SWE-059 is requirements ↔ design. NPR 7150.2 Rev C / handbook Ver C-D consolidate these into **SWE-052** | NASA SWE handbook |
| MIL-HDBK-61A splits FCA (against the performance spec) from PCA (as-built against **its technical documentation**) | MIL-HDBK-61A, AcqNotes |
| statcheck: ~half of articles **with statcheck-detectable APA-formatted NHST results** carry an inconsistency, ~1 in 8 a gross one | Nuijten et al. 2016, *Behavior Research Methods* |
| statcheck **in peer review** is *associated with* a steeper decline than matched controls (preregistered pretest-posttest quasi-experiment, 2 treatment journals vs 2 controls, 7,000+ articles). Authors' own framing is "is related to" and "can be" | Nuijten & Wicherts 2024, *AMPPS* |
| statcheck's own accuracy is **contested**: 96–99.9% on results it detects (Nuijten et al. 2017) vs ~60% precision and ~61% recognition (Schmidt, arXiv:1610.01010); detection is tied to strict APA formatting (Böschen 2024, arXiv:2408.07948). Different denominators; the critiques are preprints | as cited |
| Knight & Leveson: independence assumption rejected; 27 versions, 1,000,000 tests, correlated failures | Knight & Leveson 1986 |
| A balance identity detects that **one** error occurred **without localizing it**, and is blind to offsetting pairs (distance-2 parity check: detects one, corrects none). Detection-**plus-correction** comes from the paper's parity-check-matrix construction, not from the trial balance | Arya, Fellingham, Schroeder & Young, *Double Entry Bookkeeping and Error Correction*, Ohio State working paper, 1996 |
| Pooled override of drug-drug-interaction alerts **90% (95% CI 85–95)** across 16 studies, **I² = 100%**, per-study range ~46–98% | Felisberto et al., *Health Informatics Journal* 30(2), 2024, doi:10.1177/14604582241263242 |
| ACFE 2024: tips detect 43% of occupational frauds, 3.07× the next method; internal audit 14%, management review 13% | ACFE Report to the Nations 2024 |
| Bosché: **ICP model-matching of a known CAD model** against laser scans for as-built dimensional compliance (not learned recognition) | Bosché 2010, *Adv. Eng. Informatics* 24(1), 107–118 |

**Traceability efficacy: an evidentiary mismatch, not a void.** An earlier draft
said no efficacy evidence exists in either direction. That is wrong as a reader
will take it, and two studies exist:

- Rempel & Mäder, *Preventing Defects: The Impact of Requirements Traceability
  Completeness on Software Quality*, IEEE TSE 43(8), 2017, 777–797. 24
  medium-to-large open-source projects; traceability completeness in three of four
  requirements-implementation activities significantly associated with lower
  defect **density**. Observational, not causal.
- Mäder & Egyed, *Do developers benefit from requirements traceability when
  evolving and maintaining a software system?*, EMSE 20, 2015. Controlled
  experiment, 71 subjects, real maintenance tasks: ~24% faster and ~50% more
  correct solutions with traceability available.

The accurate statement: **measured benefits are on adjacent outcomes** —
maintenance speed, task correctness, defect-density correlation. **No study
measures escaped-defect reduction**, which is the outcome the mandate rests on.
E2's case in this document still rests on the structural omission argument, but it
is no longer arguing into a vacuum.

**Repository claims** in §§ 4 to 7 are from reading source in this session: script
docstrings, `pyproject.toml` script lists, `sdd/000-process.md`,
`sdd/formal/README.md`, and the trace corpus. The trace tag counts are a
mechanical count over `sdd/traces/*.yml` on the date above.

**Author's inference, not sourced:** the four-layer taxonomy of § 1, the tier
table, the E5-versus-E6 scaling argument and its non-composition limit, the
canonical-claim-set argument of § 2.1, the ranking in § 7, and the whole of § 9.
The three findings held most confidently are structural rather than empirical:
that omission detection always reduces to a canonical enumerable claim set; that
what distinguishes these disciplines is the enumeration being *derived* rather
than maintained in parallel; and that our **spec** prose has no mechanical
counterpart.

### Self-validation against principle 8 (detail placement)

Checked against the three-condition gate in
[`research-id-232-detail-placement-durability.md`](research-id-232-detail-placement-durability.md).
The decisive factor is amendment-channel cost: a research doc is a point-in-time
snapshot whose updates require a *new document*, so its channel is expensive and it
must externalize volatile detail rather than absorb it.

Two items failed and were remedied by declaring a successor rather than by
deletion, per the gate's "remedy is rarely deletion":

- **The trace-tag counts (§ 5, finding 7)** are high-change-rate values in an
  expensive-amendment artifact. They are load-bearing evidence for G-4 and step 3,
  so deleting them would remove the justification for the step they motivate.
  Marked as a dated measurement, with step 3's generated report named as the
  successor SSoT.
- **The artifact-pair inventory (§ 4b)** is a hand-built enumeration with no
  authoritative home. Kept, because the gap analysis is unintelligible without it,
  and annotated with the reflexive finding that its absence is the same defect one
  layer up.

A third item was **wrongly kept** on a first pass and has since been relocated.
The path-level specifics in step 2a (module paths, specific error types) were
retained on the argument that they satisfy the gate's third condition despite
failing the first. That is precisely the trade
[ID-232 § 7](research-id-232-detail-placement-durability.md) forbids: the three
conditions are "conjunctive, not a weighted score; failing any one is a reason to
move or cut the fact, not something a high score elsewhere buys back". Applying
the gate's own remedy — relocation, not deletion — step 2a now asserts the
*shape* of the heuristic (a pass over raise sites in the backend package), which
is structurally stable and carries the feasibility argument, while the specific
modules and error types move to the backlog item when the step is opened. Worth
flagging loudly because this is the section where the document certifies its own
compliance, so a gate applied loosely here would be the most quotable precedent
in it.

A fourth item was relocated in the final round: the **round-by-round review
tables** in § 10. They were valuable during review and would read as noise in six
months — process residue whose authoritative home is the PR, not a durable
artifact. The durable *lessons* stay; the change logs moved to PR #937. This is
the same reasoning applied to this document's own history that § 2.1 applies to
the specification layer.

Deliberately *not* trimmed: the mechanism catalog, the taxonomy, the tier table and
the evidence ledger. A document is the SSoT for its own stable core, and these are
this document's core. Brevity is not the target.

### Revision note: what review changed

This document went through three rounds of correction before merge, and the
durable lessons from them are recorded here. The full round-by-round tables lived
in earlier revisions and have been relocated to PR #937, which is their
authoritative home: per principle 8, process residue does not belong in a durable
artifact once the process is over.

Four corrections carry a lesson beyond this document:

- **A flat taxonomy hid a category error.** Listing F (identity) and H (authority)
  as peer inconsistency *classes* contradicted this document's own prose, which
  already described F as upstream of everything and H as the case where detection
  *succeeds*. The four-layer split in § 1 is the fix, and the general lesson is
  that a taxonomy whose entries do not share a failure mode is a list, not a
  taxonomy.
- **A stated bound is not a defect.** An earlier draft called
  `check_formal_trace.py`'s citation-not-assertion limit a defect. The script
  documents that boundary itself, and by this document's own honesty finding that
  is the correct way to hold a category-1 mechanism. What deserves the label is an
  *unstated* boundary, such as the formal README gap in § 5 finding 3.
- **Two category-1 exemplars had overstated bounds.** Double entry was credited
  with detection-plus-localization it does not have, and equivalence checking with
  bit-exact correspondence it does not prove. In a document whose central claim is
  that provable-bound mechanisms must *state* their bounds, getting those two
  wrong was the most self-refuting error available.
- **Tool artifacts can masquerade as data limits.** The spec-029 tag count was
  softened on the strength of a grep-derived bound, then restored when a
  schema-driven YAML parse showed the count was exact all along. The schema
  guarantees attribution; only a sloppy reader loses it. Step 3 is specified
  accordingly.

One review suggestion was **not** adopted as given: `I ⊆ S` (every Dafny invariant
appears in the spec) was proposed as the check that would have caught BK-324
facet 4, on the reading that the spec states the empty-path rule and conformance
tests it. The backlog item says the opposite — the rule is "absent from
BE-018/BE-019 and untested" — so `I ⊆ S` would not have fired. It is worth having
regardless and is step 2b; the facet-4 fix is the harder `Impl ⊆ S`, step 2a.
