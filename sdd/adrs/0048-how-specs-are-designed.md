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

- **A spec states only the observable contract.** It states preconditions,
  postconditions, observable side effects, error precedence, and a lifetime's
  states and transitions. A sentence that two correct implementations could
  not both satisfy prescribes mechanism, and mechanism belongs in an ADR, a
  design note or a plan, never in a spec. Ordering a caller can observe is
  contract, stated as error precedence. *Why:* mechanism written beside
  invariants is where specs contradict themselves, while callers rely only on
  outcomes. *Reverse when* relocated mechanism proves to be what callers rely
  on.

- **A spec is cut by kind of truth, never by component.** The kinds are
  structure, function, single call, lifetime, environment and liveness; a
  clause's kind is the shape of a witness that would violate it. Inside a
  kind, a spec is cut at an interface contract between layers. *Why:*
  ownership, state and time cross components, so a spec per component
  scatters one property over several files. *Reverse when* specs cut by kind
  show more duplication or cross-linking than one operation contract with
  linked lifecycle and consistency models would.

- **Where a formal model governs a clause, the model is that clause's
  spec.** A model governs a clause only where a bridge binds it to the tests,
  only as far as the bridge reaches, and only while the model's check gates
  in CI; everywhere else the prose governs. The prose states a governed
  clause once and links the model. *Why:* a model with no bridge drifts from
  the code, and making every model normative would leave each clause without
  a model with no normative home.

- **A bridge grades confidence, not authority.** When contract, model, test
  and code disagree, the disagreement is investigated and settled by the
  attribution rules of [`000-process.md`](../000-process.md#intent-attribution),
  whatever the bridge level. *Why:* a test can
  encode a bug, and a bridged model can rest on a mistaken contract.

- **A model check blocks merges only once its model is bridged.** An
  unbridged model's check still runs, without blocking. *Why:* gating an
  unbridged model proves only that the model agrees with itself.

- **A behaviour that differs by backend is a named profile, and the outcome
  stays the same on every profile.** A profile, declared by a capability or a
  driver flag, decides when a clause is checked and what it costs, never what
  a caller sees. So a call that tolerates a missing path still refuses a
  wrong-typed one on every profile: `delete(folder, missing_ok=True)` raises
  `InvalidPath` on a flat backend as on a hierarchical one. *Why:* the
  tolerance is for absence, not for a wrong type, and an outcome that depends
  on the backend is the divergence profiles exist to remove. *Reverse when*
  the type check's cost is measured dominating real callers; the remedy is
  then an opt-out the caller chooses, not a different default per profile.

- **An existing spec is reshaped in steps that each do one kind of change.**
  Project state leaves first, then the spec is split as a pure move, then each
  new file is pruned against the rules. A spec adopts the rules when it is
  next rewritten, not all at once. *Why:* a move kept apart from a rewrite can
  be reviewed as a move.

## Consequences

- Positive: a review can fail a spec sentence on a stated test (two
  implementations, can fail) instead of on taste, and each kind names the
  layer that can govern it, so a model and the prose never both claim one
  clause.
- Positive: one invariant per section gives each clause its own ID, the
  granularity the repo's cross-artifact checks already reach (research § 16,
  an inference not yet tested).
- Negative: a kind is model-governed only once its layer's check gates in CI,
  so adopting a layer means adopting its CI cost; a layer that runs in no CI
  job governs nothing, and its specs stay prose-governed.
- Negative: a lifetime takes its full form only once a diagram-to-model check
  and a bridge exist for it; without them it is a prose-governed table.
- Negative: on a flat backend the type check costs a probe on every miss of a
  tolerant call; the flat profile's cost statement records it.
- Negative: splitting a spec adds files and cross-links, and every anchor
  into it moves with its section.
- Neutral: the review properties and the bridge checklist live in
  `SPEC-DESIGN.md`, review-enforced like `CONTENT-RULES.md`; no gate checks
  them.
- Neutral: until every spec has been rewritten, two spec shapes coexist.
