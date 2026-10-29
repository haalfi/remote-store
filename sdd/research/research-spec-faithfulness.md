# Research: Keeping a spec faithful to its record (BK-503)

**Date:** 2026-10-29
**Backlog items:** BK-503 (A record's spec, model and reference model have no faithfulness gate, so a misreading of the record reaches every layer built from it)
**Status:** Research complete. Background to [RFC-0029](../rfcs/rfc-0029-faithfulness-before-spec.md); it decides nothing.

---

**No published pipeline takes prose decision records to a spec, models and an
executable reference model with gates that check faithfulness to the prose,
so the best-supported design is assembled from analogues, and its central
claim is unmeasured.** That claim is that oracles derived from the records
catch spec misreadings that every spec-derived check misses. The design's one
ordering rule binds now: the record-derived check set must be written before
the spec exists, or it can no longer be written blind to it.

## 1. Question and method

The question, from the brief: once an `/observe` record is complete, how can
the spec, formal models and reference model built from it be shown, as early
as possible, to be faithful to the record, free of conflicts, satisfiable,
and bound by two test families, one derived from the spec and one from the
record. Agents do most of that work.

The full results, with grades and a citation per claim, are five reports in
the `haalfi/research` repository at
[`fc762e6`](https://github.com/haalfi/research/tree/fc762e6ed93ed679f03ed40b078a00689b6693ac/reports),
branch `research/spec-faithfulness-and-enforcement`. Their own precedence,
stated in the summary report, is: deep dive over verified edition over the
original, which is superseded; the trial design is a separate protocol. A
follow-up on the same branch at
[`193c0bc`](https://github.com/haalfi/research/blob/193c0bcaba4a4f65c1ced5fcddaa1111f97fdcf4/reports/Spec%20faithfulness%20prior-art%20check.md)
verified nine leads another tool named and changed no recommendation (§ 2.2).

| Report | Read for this doc |
|---|---|
| `Spec faithfulness and enforcement summary.md` | whole |
| `… deep dive.md` | whole |
| `… verified.md` | Part 1; Part 2 § 1 to § 4 (lines 1 to 489) |
| `… trial design.md` | § 1 to § 2.2; § 2.3 to line 140, partway into its "Who sees what" table; § 2.8 lines 294 to 309 and § 3.1, for § 2.4's definitions |
| `Spec faithfulness prior-art check.md` (at `193c0bc`) | § 1, § 3, § 4 |
| `… .md` (original) and the research notes | not read; the reports carry their figures and recommendation IDs |

A handover note from the session that wrote the brief, outside this
repository, proposed prerequisites and decisions for a trial. It reached
this repository as a pasted note on 2026-10-29 and is not committed; § 4
records what became of each point.

Evidence labels below are the reports': grades A to D, *Inference* for the
researchers' own reasoning, *own trial* for their toy experiments (n = 1,
written and read by the same run). No recommendation rests on direct
evidence for library or API behaviour specs (summary § 1.2).

## 2. Results

### 2.1 What the evidence carries

| Finding | Strength | Source |
|---|---|---|
| Round-trip, dual formalization and compile or verify checks catch divergent readings and miss every misreading both legs share | high (mechanism) | verified § 2.1 |
| Spec-blind positive and negative examples written from the prose catch wrong specs: 90 % per requirement with 3 tests each, over 36 of 43 Alloy structural requirements, one LLM | A, one study, structural not temporal | verified § 2.1 (Cunha & Macedo, FM 2026) |
| Checks screened against one correct implementation let over-strict checks through; screening against several deliberately different ones ("wheats") cut the share of trusted suites, for example 28 % to 0 % on one assignment | A, one group evaluating its own tools, deterministic functions | deep dive § 2.1 (ICER 2018) |
| A complete-and-disjoint table checker found 17 real coverage errors that two review teams had missed, in 245 s | A | verified § 2.2 (Heitmeyer) |
| "For every environment move some allowed response exists" checks per operation in seconds, as a one-step query relative to an inductive invariant (G4a); plain satisfiability passes the conflicts it finds | medium, tool authors; own trial 40 operations in 1.3 s | deep dive § 2.4 |
| A fresh session holding only the task description writes better tests against faulty code than one that saw the code: +11.7 % on average | A-pre, one study, code not specs | deep dive § 2.5 |
| Separately written versions still fail together on hard inputs, so separating information flow is necessary and not sufficient | B | verified § 2.5 (Knight) |
| Mutation kills compare test families only at equal test counts | A | verified Part 1 S7 (Papadakis) |

### 2.2 Gates and pipelines

The deep dive's gate sequence, G0 to G9 (summary § 2), each blocking the next
stage for the clause it covers: G0 ID and schema lint; G1 upward trace; G2
faithfulness exhibition against the record; G3 tables complete and disjoint;
G4 conjunction, split into G4a per-operation response existence, G4b
invariant preservation, G4c bounded confirmation and G4d full checks run
nightly; G5 vacuity, before any G4 or G4a pass is trusted; G6 model to
reference-model conformance; G7 downward trace and coverage, a presence check
only; G8 per-family mutant kill at equal test counts; G9 spec-strength
mutation.

Of the candidate pipelines (summary § 3), **Pipeline A** is the one the
evidence calls feasible in pure Python today: a record-derived check set
written in a fresh, records-only session under a file-system read scope,
before the spec; the spec; G1 to G5 with G4a; the reference model, driven by a
Hypothesis state machine; G6 to G8. Three alternatives are kept, whose
precedents are all outside API specs: **Pipeline B** translates every clause
into one common logic over one shared signature and checks them together;
**Pipeline C** writes one executable formal source and generates the other
layers from it, literally Dafny compiled to a Python reference model;
**Pipeline C′** writes Quint as the executable source and replays its
simulated traces against a separately written Python model.

The prior-art check (`193c0bc`, § 3 and § 4) names the nearest published
pipeline: Lim et al. (FM 2026) run prose to formal assertions to a model,
with a **human** review of each assertion against its requirement, and stop
at the formal model; ARSENAL runs end to end with no check against the
prose. The one measured automated check of a formal artifact against its
prose source (claimcheck) reports recall only against mutation-built labels,
with no precision against human labels. It adds one unmeasured idea:
**freeze formal assertions** once reviewed, so an agent repairing a model
cannot weaken them.

### 2.3 What is unmeasured

- **The central claim.** The trial design (§ 1) measures it on one operation:
  60 misreadings seeded upstream, every spec-derived layer regenerated from the
  misread artifact, and the share caught by record-derived oracles and missed by
  every spec-only check (S⁺, G0 to G9 and the spec tests together) estimated
  with an interval. At n = 60 it can confirm a large effect or refute the claim
  for that operation; it cannot rank pipelines or speak to other operations.
- **How many wheats suffice**, for any stateful API (deep dive § 4).
- **How often `alpha`, the mapping from the reference model's state to the
  spec's, is itself wrong** in a test-based bridge (deep dive § 4).
- **The trial's cost.** The protocol's estimate rests on assumptions it labels
  unsourced; a dry run on a toy operation is what replaces them.

### 2.4 The trial's terms

**These are the trial design's definitions (§ 1 to § 3), restated so that
RFC-0029 can be read without the external reports.** Section numbers below
are the trial design's.

- **Reference model (R).** An executable model of the operation, here in
  Python, against which every test runs. **`alpha`** maps its state to the
  spec's.
- **E and S⁺.** **E** is every oracle written from the record alone, by a
  session that sees neither the spec nor anything built from it (the
  record-derived check set and the expectation tests). **S⁺** is every check
  that never consults the record: gates G0 to G9 and the spec-enforcing tests.
- **Seeded misreading.** A deliberate wrong reading of one record clause,
  planted in the spec, after which every spec-derived layer is regenerated
  from the misread spec (§ 2.2). Six classes, ten seeds each:

  | Class | Misreading |
  |---|---|
  | C1 | Lost case: a table row or scenario branch dropped |
  | C2 | Added commitment: a value or order fixed that the record leaves open |
  | C3 | Reinterpreted option: the record's rejected option adopted |
  | C4 | Wrong non-commitment type, for example *unspecified* retagged as *deliberately not promised* |
  | C5 | Wrong environment exposure: an environment action or fault exposed or hidden |
  | C6 | Cross-table contradiction: one cell changed so two tables disagree |

- **p10, p01, delta.** p10 is the share of seeds E catches and S⁺ misses;
  p01 the reverse; delta = p10 − p01.
- **Wheat and chaff.** A **wheat** is a correct reference model that makes
  different choices wherever the record leaves behaviour open; checks are
  screened against two before they gate, and **24 held-out wheats** measure
  what over-strictness remains. A **chaff** is a deliberately wrong model
  encoding one conceptual misreading, such as a rejected option; a useful
  check set rejects it.
- **Validity condition V.** E rejects at most 1 of the 24 held-out wheats
  (the upper bound of the 95 % Clopper–Pearson interval at most 0.25),
  majority over five runs. Without it, a suite that fails on everything
  would "catch" every seed (§ 2.0, § 3.1).
- **Hypotheses (§ 3.1),** tested in a fixed sequence:
  - **H1** (primary): E catches misreadings that every spec-only check of
    Pipeline A misses. Supported if the lower bound of p10's 95 % interval
    is at least 0.05 (at least 8 of 60) and V holds.
  - **H2**: E catches more than S⁺ overall (delta > 0).
  - **H3**: at equal test counts, expectation tests catch misreadings that
    spec-enforcing tests miss.
- **Tiers (§ 2.8).** The **core tier** runs Pipeline A only, enough for H1
  to H3; the **full tier** adds Pipelines B and C′ for a descriptive
  comparison.
- **Lineages and roles (§ 2.3).** A lineage is a model provider. Four
  distinct ones fill four roles: **X** writes the spec and regenerates the
  spec side per seed; **Y** writes E from the records alone; **Z**, used by
  neither family, seeds the misreadings; **W** judges as a spec-blind
  reviewer. Raters are people: **P1** the maintainer, **P2** an external
  second rater, optional **P3** an adjudicator.
- **Criteria for the operation, O1 to O11 (§ 2.1).** The trial operation
  has: a complete and disjoint case table of at least four rows (O1); a
  state × operation table over a handed-out object, at least three states
  (O2); at least two environment actions, one a fault or cancellation and one
  a concurrent or out-of-band actor (O3); an interval operation under a
  history predicate (O4); at least three of the five non-commitment types,
  *unspecified* and *deliberately not promised* among them (O5); at least two
  profile values with a declared deviation (O6); at least 60 distinct seed
  loci (O7); a complete record frozen at a revision (O8); at least one
  documented past real misreading (O9); no use in earlier trials or public
  reports (O10); a feasible Python reference model with a Hypothesis state
  machine (O11).

## 3. How it meets this repository

The research was briefed without the repository, so four of its premises
need correcting before they bind anything here.

1. **The observed failure modes sit in the record, one step before every
   gate.** OP-01's record carried decision text no dialog asked (`OP-01/O14`
   to `O16`, `O31`), tables and lists in one decision that another contradicts
   (`O27`, D34's E7 row against D12; `O33`, D34's changed row against D26;
   `O39`, D35's list), and a consistency check that passed and was
   wrong (`O29`, D41's "no row contradicts a decision"). The trial seeds faults
   into the spec only and assumes a correct record, so it cannot measure these.
   [RFC-0028](../rfcs/rfc-0028-observe-record-review.md) already checks a
   record before its spec with a script, two unprimed readers and a primed
   review; a mechanical table check (G3) on the record is what it lacks.
2. **"Frozen, with no reopen left open" cannot be the freeze.** BK-501's
   reopen answers each open item with a decision, but asks a ground
   conflict only its route: one routed to the ground artifact's own flow
   stays open until `Flow done` (`axes.md` § Per-question loop). `OP-01/O21`,
   TREE-001 against S3, may legitimately stay so, and RFC-0024 R1 forbids
   settling it on the side.
3. **Dafny to Python is not unavailable here.** The research judged its
   literal Pipeline C unrunnable for want of a .NET toolchain; this repository
   compiles Dafny oracles to Python in Docker (`scripts/dafny_translate.sh`,
   BK-463) and plans an ITF replayer for TLA+ traces (BK-461), the bridge
   Pipeline C′ needs. Its warning stands: nine soundness bugs found by fuzzing
   in Dafny's back-ends, the Python one among them (deep dive § 2.3).
4. **OP-01 nearly meets the trial's criteria for its operation** (trial design
   § 2.1, O1 to O11), on a first reading that the trial's own scoring replaces
   (*Inference*): case tables (D9, D34), a stream's state table (D18), an
   Environment with faults and with concurrent and out-of-band actors, an
   interval operation (D21, D22), a non-promise register (D41), profile
   deviations (D43), and documented real misreadings (the review's open
   items). It fails O8, a complete record frozen at a revision
   hash, until its open items are decided, and O10 (not used in earlier trials
   or public reports) needs a judgement: the record is public on GitHub.

## 4. The handover's points, and what became of them

Each answer below is the maintainer's, from this session's dialogs (decision
log under `sdd/decisions/`, named in the RFC).

| Handover point | Disposition |
|---|---|
| P1 a complete, frozen record | Kept, redefined by § 3 item 2; preceded by record checks (§ 3 item 1) |
| P2 the operation scored on O1 to O11 | Kept, a step of the trial |
| P3 a home for the trial | This repository, `sdd/research/` |
| P4 scripts committed, never scratchpad-only | Kept |
| D1 second rater | None: a single-rater pilot, every label-dependent measure marked unvalidated |
| D2 reading of Pipeline C, D3 runtimes | Python core; Porcupine (Go) in Docker for history checks; Dafny and TLA+ layers stay under `SPEC-DESIGN.md`, outside the trial |
| D4 trial scope | Core tier, Pipeline A only |
| D5 what to adopt before any trial | G3 on record and spec tables; membership predicates for open outcomes; relaxed comparisons run unrelaxed too. G0's typed non-commitment stays with the format RFC, which owns F3's terms |
| D6 next research topic, record quality | A brief now, with RFC-0028 and a G3 record check taken as given as its baseline |
| Order: Stage 0 dry run, then the trial | Kept; the trial precedes RFC-0024 step 6's bake-off, which reuses its harness |
