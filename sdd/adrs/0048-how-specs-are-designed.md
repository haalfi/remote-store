# ADR-0048: A Spec States the Observable Contract, Cut by Kind of Truth, Governed Through a Bridge

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

Records the decisions of
[RFC-0022](../rfcs/rfc-0022-how-specs-are-designed.md) (BK-457), accepted by
the maintainer on 2026-10-19: its D1, D3, D4, D5, D7 and D8, D6's rule for
how a spec states a backend variation, the amendment of
[`000-process.md`](../000-process.md) Rules 3 and 7, the gating bar of
[`formal/README.md`](../formal/README.md#authoring-rules) rule 3, and the
maintainer's answers of 2026-10-19 to Open Questions 6 and 8 (decision log
`sdd/decisions/d8d56944-7c57-56f1-9c46-bc7c6222fa45.jsonl`). The rules that
carry them out, D2's review properties and Open Question 7's checklist are
[`SPEC-DESIGN.md`](../SPEC-DESIGN.md)'s; this record gives their why and does
not restate them. Two answers are not spec design and live
elsewhere: Open Question 4, whether a tolerant call stays strict about type on
every backend, is backend behaviour and spec 003's (BE-012, BE-021); Open
Question 5, the order in which existing specs are reworked, organises work and
is BK-456's.

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
(BUG-337's dossier), and it held 84 backlog-ID occurrences at `32a5653`
(BK-456's dossier). The spec template gives every section the same five
fields, which can only narrate a lifecycle, and the formal layers exist
([`formal/README.md` § Layers at a glance](../formal/README.md#layers-at-a-glance)) without any rule for which of them
governs a clause, so a property could have a verified model and prose that
still claimed authority over it.

[Audit 023](../audits/audit-023-kernel-migration-readiness.md), measuring the
kernel before backends migrate onto it, found the same design gaps as content
failures. The contract was stated call by call, with no states joining store,
kernel, driver and session (T20). Two formal models of one store drifted, and
in T3, T12 and T14 the model, not the kernel, was wrong (its P3); in T14 the
compiled oracle ran keys outside the domain it was proven for.

The forces: an implementer measurably benefits from a step plan, so mechanism
cannot just be deleted; some ordering is observable and therefore contract; a
model governs code only as far as something checks the two against each other,
and every working bridge in the outside evidence is empirical rather than a
proof ([research § 9](../research/research-spec-design.md#9-model-to-code-bridges-every-working-bridge-is-empirical));
making the models normative in full would leave every clause without a model
with no normative home.

## Decision

- **A spec states what a caller can observe, never how it is produced.** An
  order or a precedence a caller can observe is contract; mechanism moves to an
  ADR, a design note or a plan, relocated rather than deleted. *Why:* mechanism
  written beside invariants is where specs contradict themselves, while callers
  rely only on outcomes. *Reverse when* relocated mechanism proves to be what
  callers rely on.

- **A spec is cut by kind of truth, never by component.** A clause's kind is
  the shape of a witness that would violate it; inside a kind, specs are cut at
  an interface between layers. *Why:* ownership, state and time cross
  components, so a spec per component scatters one property over several
  files. *Reverse when* specs cut by kind show more duplication or
  cross-linking than one operation contract with linked lifecycle and
  consistency models would.

- **Each kind takes a form that can state it, and a view no check holds to its
  model states nothing.** A lifetime's source is its TLA+ module; examples and
  scenarios live in the test tier. *Why:* one field template can only narrate a
  lifecycle, a diagram notation such as Mermaid has no execution semantics, and
  a scenario is one trace, which cannot forbid every undrawn transition.
  *Reverse when* a diagram notation with checked semantics is adopted, or
  scenario tests are shown to catch what invariants miss.

- **A spec's shape is fixed and its content timeless.** One skeleton in one
  order, an empty heading stated as empty, and no project state. *Why:* a fixed
  shape lets every review check a spec the same way, and a stated absence can
  be checked where a missing one cannot; project state changes with every
  backlog move, so a spec carrying it goes stale between its own edits.
  *Reverse when* the skeleton forces empty sections on most specs.

- **What varies by backend is declared, never implied.** A variation is a
  named profile with each outcome it allows. *Why:* variation implied by an
  example backend is where per-backend contradictions hide.

- **Where a bridged model governs a clause, the model is that clause's
  spec.** It governs only as far as its bridge reaches, and only once the
  bridge is documented to
  [`SPEC-DESIGN.md` Rule 8](../SPEC-DESIGN.md#bridge-checklist), a bridge
  already in the repo included; everywhere else the prose governs. *Why:* a model with no
  bridge drifts from the code, a bridge whose reach is unstated cannot be
  judged, and making every model normative would leave each clause without a
  model with no normative home.

- **A bridge grades confidence, not authority.** When contract, model, test
  and code disagree, the [`000-process.md`](../000-process.md#intent-attribution)
  attribution rules settle it, whatever the bridge level. *Why:* a test can
  encode a bug, and a bridged model can rest on a mistaken contract.

- **A TLA+ check blocks merges only once its module is bridged; a Dafny proof
  always does.** An unbridged module's check still runs, without blocking.
  *Why:* model checking an unbridged module proves only that the model agrees
  with itself, while a postcondition the Dafny verifier rejects is a
  contradiction in the contract itself.

## Consequences

- Positive: a review can fail a spec sentence on a stated test (two
  implementations, can fail) instead of on taste, and each kind names the
  layer that can govern it, so a model and the prose never both claim one
  clause.
- Positive: one invariant per section gives each clause its own ID, the
  granularity the repo's cross-artifact checks already reach
  ([research § 16](../research/research-spec-design.md#16-spec-003-as-a-test-case),
  an inference not yet tested).
- Negative: a kind is model-governed only once its layer's check gates in CI,
  so adopting a layer means adopting its CI cost; a layer that runs in no CI
  job governs nothing, and its specs stay prose-governed.
- Negative: a lifetime takes its full form only once a diagram-to-model check
  and a bridge exist for it; without them it is a prose-governed table.
- Negative: splitting a spec adds files and cross-links, and every anchor
  into it moves with its section.
- Neutral: the review properties and the bridge checklist live in
  [`SPEC-DESIGN.md`](../SPEC-DESIGN.md), review-enforced like
  [`CONTENT-RULES.md`](../CONTENT-RULES.md); no gate checks them.
- Neutral: the rules bind the sections a change writes, so until every
  section has been rewritten two shapes coexist, sometimes within one spec.
