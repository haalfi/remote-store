# Research: Detecting inconsistency among multiple descriptions of the same thing

**Date:** 2026-07-27
**Status:** Advisory research, revised after external review (see § 9 revision
note). Cross-discipline synthesis (deep-research harness, adversarially verified)
narrowed to software-under-SDD and technical engineering, then tested against one
live repository case (BK-324). Not a spec or ADR. The plan in § 8 is a proposal;
no backlog items were created.
**Scope:** What makes inconsistency between parallel descriptions of one subject
*detectable*; which detection mechanisms are proven in disciplines whose artifacts
are machine-readable and whose checks are cheap; which of them this repository
already runs; and where our gates are structurally blind.
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
ripple-check. Twenty lint gates plus a preflight family already compare pieces of
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
> 2. **Measured efficacy.** Mutation testing, and statcheck embedded in peer
>    review, have real empirical support. The measurements are narrow — high
>    precision over a slice — not broad claims about defect reduction.
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
Software-under-SDD and technical engineering share four properties that change the
answer:

1. Artifacts are machine-readable, so comparison can be mechanical.
2. Re-derivation is cheap, so checks run per change rather than per quarter.
3. Identifier discipline is already institutional (part numbers, net names, spec IDs).
4. **The claim space is finite and enumerable from a canonical artifact.**

Property 4 is the important one, and it produces the central finding of this
research. An earlier draft stated it as "omission is detectable in these two
disciplines and only in these two", which is **false** and does not survive
contact with a skeptical reader. Other disciplines have completeness devices: the
WHO surgical safety checklist, aviation's minimum-equipment and configuration-
deviation lists, pre-flight checklists, clause inventories in structured
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

Three of these deserve detail.

### E1 is the strongest mechanism either discipline has

Chip design does not tape out until layout-versus-schematic returns zero. LVS
extracts a netlist from the *realization* by tracing connectivity through metal
layers and vias, then compares it device-by-device and node-by-node against the
netlist from the *intent*. Unmatched nodes are reported individually for
debugging, and device properties are compared against a configured **tolerance**,
with out-of-tolerance reported as a property error. Alongside it, formal
equivalence checking proves bit-exact correspondence between RTL and the
synthesized gate netlist, on the reasoning that every synthesis transformation
risks the netlist no longer implementing the RTL intent.

Why it is the gold standard: it is the only mechanism in either discipline that
compares two *independently authored* descriptions across a domain boundary,
mechanically, exhaustively, **and with localization**. Not "these disagree" but
"this node differs".

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

AS9102 requires an inspection drawing on which every characteristic carries a
uniquely numbered balloon, and Form 3 lists every design characteristic beside its
actual measured result. Section 5.2 requires verification that every design
characteristic requirement is accounted for, uniquely identified, and has
inspection results traceable to each unique identifier.

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

It is listed last because it is manual, unschedulable-by-default, and produces
findings in prose. That ranking is about cost, not power. **In the one case this
document has evidence for, E10 is the mechanism that actually worked** (§ 5,
finding 5), and every gate ranked above it was green at the time.

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
The table will drift, and nothing will notice.

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
derive-and-difference, which is the pattern § 8 step 2a wants.

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
for § 3's non-composition limit — no pairwise check covers backend-*i*-versus-
backend-*j* on `is_file("")`, because the conformance suite has no cell for it.

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
(`dafny-clause-untested`) is the set difference D \ T** — a spec ID carrying a
verified Dafny postcondition that no conformance marker cites. That is omission
detection over a derived enumeration: E2, tier T6, not T1.

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

Our characteristic accountability runs spec → test. NASA's SWE-059 requires
*bidirectional* traceability on the explicit rationale that the two directions
catch structurally different defects: design elements not fulfilled in code, and
source code with no parent design element. We have direction one. Facet 4 is a
direction-two defect: a convention enforced by `Store`, defensively guarded by
every backend, in no spec, untested.

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

Across 257 traces we have recorded **166 `misleading` and 19 `unclear`** outcome
tags, each attributed to a file. (An earlier draft said 258: the count used
`sdd/traces/*.yml`, one character looser than `check_traces.py`'s
`sdd/traces/[!_]*.yml`, and so counted `_schema.yml` as a trace. Step 3's
aggregator should reuse that gate's glob rather than re-derive it, or it inherits
the same off-by-one. A mechanical count miscounted, in a document arguing for
mechanical counts.) The most-cited, **measured on this document's
date and not maintained thereafter** — step 3 proposes the generated report that
becomes the authoritative version of this table, at which point the numbers below
are superseded rather than merely stale:

| Count | Reference |
|---|---|
| 16 | `sdd/BACKLOG.md` |
| 8 | `src/remote_store/backends/_sftp.py` |
| 7 | `src/remote_store/backends/_local.py` |
| 6 | `sdd/CLAUDE-REFERENCE.md` |
| 6 | `sdd/BACKLOG-DONE.md` |
| 5 | `CONTRIBUTING.md` |
| 4 | [`sdd/specs/029-async-store-backend-api.md`](../specs/029-async-store-backend-api.md) |

BK-324's header reads `spec: 003, 029, 037`. **Spec 029 was tagged misleading
repeatedly before BK-324 was written.** Treat the per-file counts as approximate:
attribution here is a heuristic that walks back from each `outcome:` tag to the
nearest preceding `file:` key, and independent search bounds spec 029's count to
between two and five rather than confirming four. The imprecision is itself the
argument for step 3 — the signal exists, attributed and committed, and nothing
aggregates it reliably. A description that repeatedly misleads a reader is a drift
detector with attribution already attached, and we are discarding it.

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
| `check_formal_trace.py` F1 | Dafny-tagged spec IDs \ conformance-cited IDs |
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

That is a sharper diagnosis and it changes § 8's framing materially. Step 2 is not
building an enumeration discipline from nothing; it is **extending an established
one down a granularity level**, with five working precedents in-repo. Adding a
twenty-first *identifier*-keyed check would still not have moved BK-324 by a day.

**A tempting T6 check, and why it is not the one we need.** The obvious relation is
"every invariant enforced in Dafny must appear in the spec", i.e. `I ⊆ S`. That is
a worthwhile check and § 8 step 2b proposes it. But note carefully that **it would
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
- **Traceability efficacy is unevidenced**, here and in the literature. E2's value
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

**G-4. The trace corpus is an unexploited drift detector.** 185 negative-outcome
tags, already attributed, never aggregated.

**G-5. No published characteristic-accountability record.** `check_formal_trace.py`
computes the coverage matrix and discards it. AS9102's insight is that the
*retained record* is the artifact: what was verified, by what, at which release.

**G-6. Rehearsal is unscheduled.** The mechanism with the best findings-per-unit-noise
in the catalog runs only when someone opens a guide PR.

**G-7. Tolerances live in check implementations, not in specs.**

**G-8. Async twin behavioral parity is a checklist item, not a gate.**

---

## 8. Plan of next steps

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
tractable shape is a **heuristic over raise sites in the backend package**: each
must be reachable from a spec ID via an existing marker or an explicit allowlist
entry. **The allowlist is the deliverable**, not the gate: on day one it
enumerates every orphan behavior we have, which is precisely what facet 4 turned
out to be. Harder than 2b because implementation invariants are enforced rather
than declared, so expect the first cut to be approximate and to grow by hand.
Which error types and which modules to start with belong in the backlog item when
this is opened, not here — they are high-change-rate specifics with no claim on
this layer.

**2b. `I ⊆ S` — every Dafny invariant must appear in the spec.** Cheap, because
`// @spec` tags already exist and `check_formal_trace.py` already parses them: the
check is that a Dafny postcondition carrying no spec coordinate, or one whose
coordinate has no prose counterpart, fails. This polices the formal layer's
honesty and would catch a *different* drift than 2a. Do it second and do not
mistake it for the facet-4 fix.

### Step 3 — Aggregate trace outcome tags
**Closes:** G-4 · **Mechanism:** E7 · **Size:** S

Add `scripts/report_trace_outcomes.py` producing a ranked table of references by
`misleading` + `unclear` count, with the citing traces. Run it as a report, not a
gate — there is no correct threshold, and gating it would create exactly the
false-positive fatigue that defeats rule checkers elsewhere. Review the top of the
list at the same cadence as the TLA+ status revisit. This is the cheapest item
here and the data is already committed.

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
exercise with a fixed cadence rather than a side effect of guide PRs. Its output is
a list of places the guide, the contract or the conformance suite failed the
builder. BK-324 and BK-325 are one run's worth of findings, which is the
justification.

### Step 7 — Publish the characteristic-accountability record
**Closes:** G-5 · **Mechanism:** E2 · **Size:** S

Render `check_formal_trace.py`'s coverage matrix as a generated artifact at
release time: every spec ID, its verification evidence (test marker, Dafny tag,
TLA+ invariant), and its status. Makes "what was verified, and by what" answerable
historically rather than only at HEAD.

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

## 9. Evidence ledger and method caveats

**Method.** A deep-research harness ran six search angles, extracted claims, and
adversarially verified them (three voters per claim, two refutations to kill).
**Two harness faults degraded that run and must be disclosed:** full-text fetching
returned HTTP 403 for every host under the session's egress policy, and the
automated verification stage lost its search tool to a permission-handler error,
so ten of eleven claims were refused *procedurally rather than substantively*.
Thirteen load-bearing claims were subsequently re-verified by hand against search
results. **No source was read at full text.** Verification therefore supports "this
work exists, is correctly attributed, and reports these numbers"; it does **not**
support direct quotation or capture of methodological caveats.

**Verified** (search-confirmed, full text unread). **Which rows carry the
argument:** LVS and formal equivalence checking underwrite § 3 E1; AS9102 Form 3
underwrites § 3 E2; SWE-059 underwrites § 5 finding 4; statcheck and double entry
underwrite the honesty finding; MIL-HDBK-61A and Bosché are adjacent to E8 and the
as-built deferral. **Knight & Leveson, the clinical-decision-support override
figure and ACFE 2024 support no claim in §§ 1 to 8** — they are retained as
provenance for the broad cross-discipline survey this document was narrowed from,
so that the narrowing is auditable, and a reader should not infer that N-version
independence, alert fatigue or fraud-detection channels are load-bearing here.

| Claim | Source |
|---|---|
| LVS extracts a layout netlist and compares device-by-device against the schematic netlist; property comparison is tolerance-configured; zero violations required before tapeout | Synopsys glossary; Wikipedia LVS |
| Formal equivalence checking of RTL vs gate netlist is standard synthesis sign-off | Synopsys Formality |
| AS9102 Form 3 requires every design characteristic uniquely identified with inspection results traceable to each identifier | AS9102 practitioner references |
| NASA SWE-059 requires bidirectional traceability; the two directions catch unimplemented requirements vs orphan code | NASA SWE handbook |
| MIL-HDBK-61A splits FCA (performance spec) from PCA (as-built vs as-designed) | MIL-HDBK-61A, AcqNotes |
| statcheck: ~half of NHST psychology articles carry an inconsistency, ~1 in 8 gross | Nuijten et al. 2016, *Behavior Research Methods* |
| statcheck **in peer review** produced a steeper decline than matched controls (preregistered, 7,000+ articles) | Nuijten & Wicherts 2024, *AMPPS* |
| Knight & Leveson: independence assumption fails; 27 versions, 1M tests, correlated failures | Knight & Leveson 1986 |
| Double entry is analyzable as an error-detecting code; detects two counterbalancing errors, localizes a single error | Arya & Fellingham |
| Clinical decision support: ~90% override of drug-drug-interaction alerts | override meta-analysis, 2024 |
| ACFE 2024: 43% of occupational frauds detected by tip, >3× the next method; internal audit 14% | ACFE Report to the Nations 2024 |
| Bosché: automated CAD-object recognition in laser scans for as-built dimensional compliance | Bosché 2010, *Adv. Eng. Informatics* |

**Unverified and load-bearing:** whether requirements traceability *reduces
escaped defects*, in either direction. It is the most heavily mandated mechanism
in both disciplines and no efficacy evidence was found. E2's case rests on the
structural omission argument alone.

**Repository claims** in §§ 4 to 7 are from reading source in this session: script
docstrings, `pyproject.toml` script lists, `sdd/000-process.md`,
`sdd/formal/README.md`, and the trace corpus. The trace tag counts are a
mechanical count over `sdd/traces/*.yml` on the date above.

**Author's inference, not sourced:** the four-layer taxonomy of § 1, the tier
table, the E5-versus-E6 scaling argument and its non-composition limit, the
canonical-claim-set argument of § 2.1, the ranking in § 7, and the whole of § 8.
The three findings held most confidently are structural rather than empirical:
that omission detection always reduces to a canonical enumerable claim set; that
what distinguishes these disciplines is the enumeration being *derived* rather
than maintained in parallel; and that our prose has no mechanical counterpart.

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

Deliberately *not* trimmed: the mechanism catalog, the taxonomy, the tier table and
the evidence ledger. A document is the SSoT for its own stable core, and these are
this document's core. Brevity is not the target.

### Revision note: what external review changed

This document was reviewed before merge and materially corrected. Recording the
changes because the review found real errors, not stylistic ones:

| Was | Now | Kind |
|---|---|---|
| "Omission is detectable in these two disciplines, and only in these two" | Corrected: surgical checklists, MEL/CDL and clause inventories are counterexamples. The real distinction is *derived* versus *parallel-maintained* enumeration (§ 2) | Factual error |
| `DafnyOracleBackend` presented as our LVS | Corrected to a two-step chain: T3.5 verification plus T4 sampled comparison. Not equivalence checking (§ 3, E1) | Factual error |
| Flat eight-class taxonomy | Split into types (A–E), precondition (F), representation blocker (G), post-detection failure (H). The old form contradicted its own prose, which already called F "upstream" and H a detection-succeeded case | Structural |
| Gradient jumped T3 → T4 | Added T3.5, symbolic/bounded exhaustive. The old table had no home for Dafny or TLC, i.e. for this repo's strongest tools | Omission |
| "Institutionalized rather than demonstrated", with two exceptions | Three epistemic categories: provable bound, measured efficacy, mandated-unmeasured. Mutation testing has real empirical support; LVS's warrant is a derivable bound, not a study | Over-claim |
| E5 scaling described as O(N²) cost | Added the stronger limit: pairwise parity does not compose into global consistency (§ 3) | Under-claim |
| E10 listed last, treated as minor | Elevated: the only family reaching E, G and H at once, and the one that actually worked on BK-324 | Under-claim |
| § 5 ended at seven findings | Added the tier-mismatch synthesis: mechanisms at T1–T4, failure at T6–T7 | Missing synthesis |

**Second round (PR #937 review).** Nine findings, all verified against source
before applying, all accepted:

| Was | Now |
|---|---|
| "Every mechanism we run sits at T1 to T4" | Wrong, and it contradicted § 3 of this document. Five gates run derived-enumeration set differences. Corrected to: our T6 coverage is real but **identifier-granular**, and BK-324's claims are sub-ID clauses (§ 5 synthesis) |
| § 4b inventory omitted three prose-side gates | Added `check_custom_backend_guide.py`, `check_ci_inventory.py`, `check_backend_order.py`. They are working templates for derive-and-difference, which reframes step 2a as extending a discipline rather than inventing one |
| "Prose is unchecked" (§ 6), "Prose has no mechanical counterpart" (G-2) | Narrowed to **spec** prose. Guide, handbook and enumeration prose are all mechanically bound |
| Finding 2 cited only F2/F3 and called the gap a defect | F1 is the set difference D \ T, i.e. T6 not T1. And the residual bound is *stated* in the script's own docstring, which by this document's honesty finding is the correct way to hold the mechanism, not a defect |
| Facet 1 grouped as "guarded by every backend" | That is facet 4's property. Facet 1 is `is_file("")` diverging across the S3 family, so it carries a class-B component now assigned in the synthesis table |
| "Across 258 traces" | 257. The count used a glob one character looser than `check_traces.py`'s, counting `_schema.yml` |
| "Spec 029 was tagged misleading four times" | Softened. The attribution heuristic bounds it to two-to-five; the imprecision is itself an argument for step 3 |
| Self-validation kept step 2a's path specifics on condition 3 despite failing condition 1 | The gate is conjunctive and forbids that trade. Specifics relocated to the future backlog item; the stable *shape* stays |
| Evidence ledger implied all rows were load-bearing | Header now separates rows that carry an argument from rows retained as provenance for the broad survey |
| No backlog pointer back to this doc | `Related:` links added to BK-324 and BK-325, matching the convention on eight other items. The trace convention and the backlog-pointer convention are separate rules; conflating them was the original error |

One review suggestion from the **first** round was **not** adopted as given. The reviewer proposed `I ⊆ S`
(every Dafny invariant appears in the spec) as the check that "would have caught
BK-324 facet 4 immediately", on the reading that the spec states the empty-path
rule, Dafny enforces it, conformance tests it, and only the guide omits it. The
backlog item says the opposite: the rule is "absent from BE-018/BE-019 and
untested". So `I ⊆ S` would not have caught it. The check is still worth having
and is step 2b; the facet-4 fix is the harder `Impl ⊆ S` direction, step 2a.
