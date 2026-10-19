# ADR-0048: A Spec States the Observable Contract, Cut by Kind of Truth, Governed Through a Bridge

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Proposed |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

Records the decisions of
[RFC-0022](../rfcs/rfc-0022-how-specs-are-designed.md) (BK-457), proposed for
the RFC's acceptance; Open Questions 4 to 8 carry the maintainer's answers of
2026-10-19 (decision log
`sdd/decisions/d8d56944-7c57-56f1-9c46-bc7c6222fa45.jsonl`). It covers D1, D3,
D5 and D6, the amendment of
[`000-process.md`](../000-process.md) Rules 3 and 7, the gating bar of
[`formal/README.md`](../formal/README.md#authoring-rules) rule 3, and the
answers to its Open Questions 4 to 8. Its D2, D4, D7 and D8 are rules of
[`SPEC-DESIGN.md`](../SPEC-DESIGN.md), which this record does not restate.

It amends no record. A search of `sdd/adrs/` for `Specs are authoritative`,
`spec format`, `Rule 3`, `normative`, `catch-first` and `informational until`,
and of its titles for `Dafny`, `TLA`, `formal`, `spec`, `oracle` and `model`,
finds no ADR that decides what a spec states, its form, or which artifact
governs it.

## Context

Nothing in the repo said what a spec owes, so spec 003 grew mechanism beside
its invariants: a probe set and its order, per-backend error remapping, named
helpers. PR #1159's review kept finding one of its sections contradicting
another, and a read against RFC-0022 confirmed four such contradictions
(BUG-337's dossier). The spec template gives every section the same five
fields, which can only narrate a lifecycle, and the formal layers exist
(`formal/README.md` § Layers at a glance) without any rule for which of them
governs a clause, so a property could have a verified model and prose that
still claimed authority over it.

The forces: an implementer measurably benefits from a step plan, so mechanism
cannot just be deleted; some ordering is observable and therefore contract; a
model governs code only as far as something checks the two against each other,
and every working bridge in the outside evidence is empirical rather than a
proof ([research § 9](../research/research-spec-design.md#9-model-to-code-bridges-every-working-bridge-is-empirical));
making the models normative in full would leave every clause without a model
with no normative home.

## Decision

- **A spec states the observable contract; mechanism is relocated, not
  deleted.** A sentence two correct implementations could not both satisfy
  moves to an ADR, a design note or the plan; observable ordering stays, as
  error precedence. *Why:* the measured contradictions sat in the mechanism.
  *Reverse when* a relocated sentence proves to be what callers rely on.

- **Specs are cut by kind of truth, then by interface contract**, never per
  component; this answers Open Question 8 for spec 003. *Why:* ownership,
  state and time cross components. *Reverse when* spec 003's split shows more
  duplication or cross-linking than one operation contract with linked models
  would: the cut is a candidate, judged on its first use.

- **The spec and its governing model are authoritative.** A model bound to the
  tests by a bridge governs its clause as far as the bridge reaches, and the
  prose states the clause once and links it; elsewhere prose governs. Rule 3 is
  amended, not superseded. *Why:* unbridged models drift, and models
  normative in full orphan every clause without one.

- **A bridge level informs a conflict, never decides it** (Open Question 6):
  a new Rule 7 item; the defeaters are unchanged. *Why:* a test can encode a
  bug and a bridged model can rest on a mistaken contract.

- **A TLA+ check gates per module, from the change that bridges it** (Open
  Question 3, decided by ID-150), replacing rule 3's bar of a first live
  catch. *Why:* gating an unbridged model proves only self-agreement.

- **Backend differences are named profiles, and type mismatch outranks
  `missing_ok` on every profile** (Open Question 4). *Why:* it is a verified
  Dafny postcondition, and a quiet return on flat backends alone would make
  one call answer differently per backend. *Reverse when* the probe is
  measured dominating a bulk delete, and then by an opt-out the caller
  chooses, not a per-profile default.

- **Spec 003 migrates first, in stages** (Open Question 5, BK-456); other specs
  adopt the rules when next rewritten. *Why:* the contradictions were measured
  there.

## Consequences

- Positive: a review can fail a spec sentence on a stated test (two
  implementations, can fail) instead of on taste; each kind's governing layer
  is named, so a model and the prose no longer both claim one clause.
- Positive: one invariant per section gives each clause its own ID, the
  granularity the repo's cross-artifact checks already reach (research § 16,
  an inference not yet tested).
- Negative: no lifetime can take its full form yet. The Mermaid-subset parser
  with its edge-equality check, and a Python replayer for model-generated
  traces, do not exist; until they do, lifetime clauses stay prose-governed
  tables. Each is a follow-up item.
- Negative: spec 003's split adds files and cross-links, and every anchor that
  points into it moves with its section.
- Neutral: the eight review properties and the bridge checklist live in
  `SPEC-DESIGN.md`, review-enforced like `CONTENT-RULES.md`; no gate checks
  them.
- Negative: on a flat backend the strict `missing_ok` costs a probe on every
  miss: one prefix listing off the kernel, one `stat` and one
  `list_page(limit=1)` on it (spec 003's BE-021 and BE-032 cost tables). It
  becomes a line in the flat profile's cost statement.
- Neutral: spec 003 moves in three changes, project state out, a split by kind
  as a pure move, then a prune per file, so each is reviewed as what it is.
- Neutral: specs other than 003 keep their current form until rewritten, so
  for a while two shapes coexist.
