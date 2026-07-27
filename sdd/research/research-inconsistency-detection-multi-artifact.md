# Research: Detecting inconsistency among multiple descriptions of the same thing

**Date:** 2026-07-27
**Status:** Advisory research. Cross-discipline synthesis (deep-research harness,
adversarially verified) narrowed to software-under-SDD and technical engineering,
then tested against one live repository case (BK-324). Not a spec or ADR. The
plan in § 8 is a proposal; no backlog items were created.
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

> **Central honesty finding.** The mechanisms surveyed here are, with two
> exceptions, *institutionalized* rather than *demonstrated*. Institutionalization
> is strong evidence that a mechanism is affordable and politically survivable,
> and weak evidence that it works. The two exceptions run opposite ways: where
> efficacy has been measured, mandated mechanisms usually **underperform** their
> reputation, and the one clear positive result is about **where a detector is
> placed**, not how good it is. Treat § 3 as a design vocabulary, not a
> league table.

---

## 1. What counts as an inconsistency, and which kinds are detectable

An inconsistency exists when two descriptions make claims about the same subject
that cannot both be true, **or** when one description silently omits a claim
another treats as binding. The second half matters more than it looks: it is the
half our tooling is worst at.

Eight classes carve the space. The first four came from the framing question; the
last four were needed to make the taxonomy cover what the discipline survey
actually found.

| Class | Definition | Instance in this repo |
|---|---|---|
| **A. Cross-domain contradiction** | Descriptions from different domains (intent / realization / verification / explanation) disagree | Spec prose demands `InvalidPath`, flat-NS backends raise `NotFound` (BK-324 facet 2) |
| **B. Cross-artifact contradiction** | Two artifacts of the same kind disagree | `MemoryBackend` vs `MemoryBackendMinimal`; `Store` vs `AsyncStore` |
| **C. Within-artifact self-contradiction** | One artifact's claims cannot all hold | A spec section whose table contradicts its own prose (BK-324 facet 3) |
| **D. Temporal drift** | Descriptions that were consistent and diverged through change | Guides describing superseded behavior |
| **E. Silent omission** | One description treats a claim as binding; another is simply silent | Empty-path `InvalidPath` enforced everywhere, specified nowhere (BK-324 facet 4) |
| **F. Referential / identity** | Same name, different subjects, or vice versa | Stale spec IDs in markers; capability name skew across sources |
| **G. Granularity mismatch** | Descriptions sit at incommensurable levels, so nothing compares | One-line contract prose vs a 400-line backend |
| **H. Authority ambiguity** | A real conflict exists and no rule says which side governs | BK-324: prose vs Dafny vs conformance, all "intent" |

**E, F, G and H are not decorative.** E is a different problem *in kind*: comparing
two present claims is a matching problem, while detecting an absent claim requires
an independent enumeration of what claims should exist. F is upstream of
everything, because every other class presupposes the descriptions are known to be
about the same subject. G is the class that masquerades as consistency, since when
nothing is comparable the checks pass. H is what makes detection output unusable:
detection succeeds, attribution is undefined, and the finding stalls.

### The detectability gradient

Detectability is not a property of the class. It is a property of the *comparison*
the class demands.

| Tier | What the check requires | Decidable? | Automation | Attribution |
|---|---|---|---|---|
| **T0** Well-formedness | Grammar of one artifact | Yes | Total | Local |
| **T1** Referential integrity | Shared identifiers, resolvable links | Yes | Total | Flags the dangling end only |
| **T2** Closure / arithmetic identity | A derivable invariant | Yes | Total | Flags the identity, rarely the term |
| **T3** Constraint / rule violation | Shared schema plus external rules | Yes, within the rule language | High | Yes, if rules carry authority |
| **T4** Behavioral comparison | One side executable, another an oracle | Over sampled inputs only | High but incomplete | By convention |
| **T5** Semantic comparison of prose | Meaning equivalence in natural language | No general oracle | Low | Rarely |
| **T6** Completeness | Independent enumeration of the claim space | Not in general | Very low | — |
| **T7** Intent and authority | Judgment about which description ought to govern | No | None | This *is* attribution |

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

Property 4 is the important one, and it produces the single most useful finding in
this research:

> **Omission (class E) is detectable in these two disciplines, and only in these
> two.** The broad survey found no discipline with a general answer to omission,
> because you cannot enumerate every binding claim in a contract or a patient's
> history. You *can* enumerate every dimension on a drawing, and every section ID
> in a spec file. That makes a completeness oracle constructible at T6, which is
> otherwise the tier nothing reaches.

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

We already run this shape. The `DafnyOracleBackend` principle — if the oracle
passes, the test is known-correct; if the oracle fails, the test has a bug — is
LVS's logic with the authority roles named explicitly.

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

---

## 5. The BK-324 case: what our gates cannot see

BK-324 records contract prose, the Dafny model, the conformance suite and shipped
backends disagreeing across four facets. It is the best available evidence about
our detection coverage, because every gate was green throughout.

### Finding 1: all four facets are the prose spec

- Facet 2: prose (BE-017/BE-021) demands `InvalidPath`; flat-NS backends raise `NotFound`. Prose contradicts code.
- Facet 3: prose in [spec 037](../specs/037-depth-limited-listing.md) licenses ignoring `max_depth` while the Dafny model and DEPTH-003 tests require native pruning; 037's table is also wrong about S3 and Azure. Prose contradicts mechanism, and contradicts itself.
- Facets 1 and 4: behavior exists and is guarded by every backend, but no prose binds it and no test covers it. Prose absent.

Two facets are prose contradicting a mechanism; two are prose absent where
behavior exists. **Rule 3 makes the Markdown spec authoritative over everything,
and the Markdown spec is the only description in the formal layer with no
mechanical counterpart.** Dafny is verified, TLA+ is model-checked, tests are run,
backends are conformance-driven. Prose is read. The most authoritative artifact is
the least checked one.

### Finding 2: our traceability is T1, and T1 cannot see this

`check_formal_trace.py` fails on `conformance-cites-unknown-spec` and
`dafny-tag-unknown-spec`: referential integrity plus a baseline registry. It
proves a link *exists and resolves*. BK-324 is four descriptions with every link
present, every gate green, and the *content* disagreeing.

This confirms a general property of traceability as a mechanism: it automates link
integrity and not link correctness. A link can be present, resolvable, and
semantically wrong. Traceability is a T1 mechanism sold as a T3 one.

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

Across 258 traces we have recorded **166 `misleading` and 19 `unclear`** outcome
tags, each attributed to a file. The most-cited:

| Count | Reference |
|---|---|
| 16 | `sdd/BACKLOG.md` |
| 8 | `src/remote_store/backends/_sftp.py` |
| 7 | `src/remote_store/backends/_local.py` |
| 6 | `sdd/CLAUDE-REFERENCE.md` |
| 6 | `sdd/BACKLOG-DONE.md` |
| 5 | `CONTRIBUTING.md` |
| 4 | [`sdd/specs/029-async-store-backend-api.md`](../specs/029-async-store-backend-api.md) |

BK-324's header reads `spec: 003, 029, 037`. **Spec 029 was tagged misleading four
times before BK-324 was written.** The signal existed, attributed and committed,
and nothing aggregates it. A description that repeatedly misleads a reader is a
drift detector with attribution already attached, and we are discarding it.

---

## 6. Where we lead and where we do not

**Ahead of most practice:** omission is partially mechanized (E2); reconciliation
frequency is per-change rather than periodic; attribution rules are declared per
pair in writing; and we have a real miss-rate estimator in mutation testing, which
most projects lack entirely.

**Not ahead, and worth being honest about:**

- **Prose is unchecked** (§ 5, finding 1), and it is authoritative.
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

**G-2. Prose has no mechanical counterpart.** The structural finding of § 5.
Fully closing it requires T5, which is unsolved. Partially closing it does not:
see steps 2 and 4 in § 8.

**G-3. Traceability is unidirectional.** Spec → test only; orphan realization
(behavior with no parent spec) is undetected. BK-324 facet 4 is the live instance.

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
order. **Recommended first: step 1 (highest consequence) and step 3 (cheapest).**

### Step 1 — Parity gate for the Dafny twin classes
**Closes:** G-1 · **Mechanism:** E1/E5 · **Size:** M

Add `scripts/check_dafny_twin_parity.py`: normalize each method body of
`MemoryBackend` and `MemoryBackendMinimal` and assert correspondence modulo the
declared capability-set difference, with an explicit allowlist for intentional
divergence. Model it on `check_docstring_parity.py`, which already solves the
"identical versus deliberately divergent" classification problem. Wire into
`lint`. Record in the formal README that twin drift is now gated.

### Step 2 — Bidirectional traceability
**Closes:** G-3, and BK-324 facet 4 concretely · **Mechanism:** E2 · **Size:** M

Extend `check_formal_trace.py` (or add a sibling) with the reverse direction:
identify enforced behavior with no parent spec section. A tractable first cut is
narrow rather than general — e.g. every `raise InvalidPath` / `raise NotFound`
site in `src/remote_store/backends/` must be reachable from a spec ID via an
existing marker or an explicit allowlist entry. The allowlist *is* the finding:
it enumerates our orphan behaviors on day one, which is what facet 4 turned out
to be.

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

**Verified** (search-confirmed, full text unread):

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

**Author's inference, not sourced:** the eight-class taxonomy, the tier table, the
E5-versus-E6 scaling argument, the ranking in § 7, and the whole of § 8. The two
findings I hold most confidently are structural rather than empirical: that
omission is detectable here because the claim space is enumerable, and that our
prose has no mechanical counterpart.
