# RFC-0022: How specs are designed

## Status

Draft, 2026-10-18. Tracked as **BK-457**. Graduates to one ADR (D1, D3, D5,
D6, and the Rule 3 and Rule 7 amendment) and one authoring guide (D2, D4, D7,
D8), the new authority doc `sdd/SPEC-DESIGN.md` (Open Question 1, decided).
The outside-evidence verdicts in [research §
12](../research/research-spec-design.md#12-verdicts-per-rfc-decision) are not
yet folded into D1 to D7. The analysis behind it, a maintainer session that walked one operation,
a streaming read, from key to bytes, is
[`research-spec-design.md`](../research/research-spec-design.md); this RFC
holds only the decisions.

## Summary

**A spec states what an observer can check, split by the kind of truth it
states, in the form that kind needs, under the formal layer that can prove
it.** Everything else, how an implementation reaches the outcome, which work
is still open, and what another layer decides, lives outside the spec.

The repo has the parts: formal layers for structure, functions and protocols
([`formal/README.md` § Layers at a
glance](../formal/README.md#layers-at-a-glance)), an authority rule between
prose, model and suite ([`000-process.md` Rule
7](../000-process.md#intent-attribution)), and a spec built the way this RFC
proposes, [spec 051](../specs/051-store-tree.md). What it lacks is the rule
that says which part a given clause belongs to. This RFC proposes that rule.

## Motivation

**Without a rule for what a spec owes, specs grow mechanism, and mechanism
breeds contradictions.** BK-457's dossier records the evidence: spec 003
prescribes how a check runs (BE-032's probe set and probe table, BE-021's
per-backend remapping) beside the boundary invariants, and PR #1159's review
kept finding one section contradicting another (BK-456). Nothing in the repo
says which of the two a spec owes.

Three further gaps showed when one operation was walked end to end
([research § 2](../research/research-spec-design.md#2-one-operation-walked)):

- **Where one spec ends is undecided.** A streaming read touches key
  admission, scoping, one call's outcome, a handle's lifetime, a concurrent
  writer, and retry. Each is a different kind of truth, checked by a different
  tool.
- **The form is fixed regardless of content.** The template in
  [`000-process.md` § Spec format](../000-process.md#spec-format) gives every
  section Invariant, Preconditions, Postconditions, Raises and Example. A
  lifecycle is a state set and its transitions, which that shape can only
  narrate, and narration reads as an algorithm.
- **Which artifact governs a clause depends on the reader.** The formal layers
  exist, but nothing assigns a kind of truth to a layer, so a property can
  have a verified model and prose that still claims authority over it.

Spec 051 shows the target is reachable: one invariant per section, axioms
apart from derived lemmas, each lemma proved, the scope stated, and nothing
about operations or backends. Its one defect, project status in its layering
prose, is fixed in the change that adds this RFC and is the D8 case.

## Proposal

### D1. A spec owes the observable contract and nothing else

**A spec states preconditions, postconditions, observable side effects, error
precedence, and for a lifecycle its states and transitions.** A sentence that
tells an implementation how to reach an outcome moves to the code or the
driver, or is deleted.

Each sentence passes two tests:

1. **Two implementations.** Could two different correct implementations both
   satisfy it? If not, it mandates an algorithm.
2. **Can fail.** Could a black-box test, a model check or a proof fail it? If
   not, it is not a clause.

Some ordering is contract. Which refusal a caller sees when two hold is
observable, so it stays, stated as error precedence rather than as an order
of steps (the qualification BK-457's dossier records).

### D2. A spec's quality is a set of properties, each with a check

**A spec is reviewed against eight properties, each with a check that can
fail:** well founded, verifiable, lasting, correct, free of contradictions, no
unstated gaps, placed, comprehensible. Their meanings and checks are
[research § 6](../research/research-spec-design.md#6-what-makes-a-spec-good);
the guide carries them as its review checklist, linking
[`CONTENT-RULES.md`](../CONTENT-RULES.md) Rules 1, 7 and 8 where those already
own the check.

### D3. Specs split by kind of truth, not by component

**One spec states one kind of truth about one subject.** The kinds:

| Kind | States | Example from a streaming read |
| --- | --- | --- |
| Structure | What holds at one instant | The store tree (spec 051) |
| Function | Input to output, totality | Key admission; scoping a key to a store root |
| Single call | One operation's outcome against the state when it runs | `read(k)` on an item, a folder, an absent key, a missing capability |
| Lifetime | States and transitions of something that outlives a call | A read handle from open to close |
| Environment | What the system relies on from outside | What a backend guarantees to an open read under a concurrent writer |
| Liveness | That something eventually happens, or never repeats | Retry terminates; a resume neither duplicates nor skips bytes |

Components (store, kernel, driver, session, stream) are where a property is
enforced, not where it is stated. Ownership, state and time cross components,
so a spec per component scatters each such property over several files.

An existing spec that mixes kinds is split along these lines. For spec 003
that is BK-456's work, which this changes from a split by layer to a split by
kind where the two differ.

### D4. Each kind takes the form it needs

| Kind | Form |
| --- | --- |
| Structure, function | One invariant per section, one line where it fits |
| Single call | Invariants plus one outcome table: input state against observable result and error |
| Lifetime | A closed-world state diagram as the source of the transitions, plus the invariants that span states (closed once, one owner, nothing read after close) |
| Environment | An Assumptions section: each assumption one line, named so a conformance test can cite it |
| Liveness | Invariants over runs, stated against the TLA+ model |

**Closed world:** a transition the diagram does not draw is forbidden. A
diagram is the source only when a check parses it and compares it with the
model; otherwise it is a view and states nothing.

Executable examples (a scenario, a worked case) belong to the test tier, each
traced to the invariant it shows. A scenario covers one case and an invariant
covers all of them, so examples cannot be the spec. Gherkin is not adopted:
its Given and When steps invite exactly the step order D1 removes, and it
adds a step-definition layer beside pytest.

### D5. The formal layer that can prove a kind governs it

| Kind | Governing layer |
| --- | --- |
| Structure | Alloy (bounded) and Lean (unbounded) |
| Function, single call | Dafny |
| Lifetime, environment, liveness | TLA+ |

**Where a model of the property exists, it governs; the prose states the
invariant in one sentence and links it.** That extends item 2 of
[`000-process.md` § Attribution inside the intent
domain](../000-process.md#attribution-inside-the-intent-domain) (prose carries
no presumption against a verified postcondition) from a defeater into the
default, and amends Rule 3 ("specs are authoritative") to
"the spec and its governing model are authoritative", without superseding it.
Where no model exists, the prose governs as today. Models are not made
normative in full: every clause without one would lose its normative home
(the qualification in BK-457's dossier).

**A model governs code only through a bridge.** Without one, the proof is
about the model. The bridges in use or proposed:

| Layer | Bridge to code |
| --- | --- |
| Dafny | A Python twin checked for parity, or the compiled oracle run against the backends |
| TLA+ | Tests derived from the model's states, or recorded runs replayed against the model |
| Alloy, Lean | A reference model in the test suite (as `tests/test_store_tree.py` does for spec 051) |

A clause governed by a model whose check does not gate is not governed. TLA+
authority therefore needs `verify-tla` to gate for the clauses it governs,
which is ID-150's open decision.

### D6. Profiles and environment are declared, not implied

**A behaviour that differs by backend is a named profile, declared by a
capability or a driver flag.** The contract stays universal; the profile
decides when it is checked and what it costs. Bounds on wire calls become a
cost statement per profile, not a step order.

What the system relies on from a backend goes into the spec's Assumptions
section. Whether a given backend meets an assumption is conformance, not spec:
the shared contract tests check it per backend and its capability declaration
records it.

### D7. Every spec takes one skeleton

1. **Overview:** the core claim, the scope, and what is out of scope, led by
   at most three sentences (Rule 7).
2. **Terms:** every symbol and term the sections use.
3. **Sections:** one invariant each, with a stable ID.
4. **Assumptions:** only where the kind is environment or liveness.
5. **Notes:** non-normative; derived properties and the proofs behind them.
6. **Tested against:** the reference model or suite the sections are checked
   against.

This replaces the per-section template in `000-process.md` § Spec format. Its
Example field moves to the test tier (D4).

### D8. A spec carries no project state

**No status, no backlog IDs, no "yet" in a spec, and no copy of another
layer's facts.** A link runs from the less stable artifact to the spec: a
backlog item names the spec it serves, never the reverse. What a clause is
checked against today is stated once, as "Tested against", and which backend
it is asserted for derives from the tests' spec tags.

## Alternatives Considered

Weighed in [research § 4](../research/research-spec-design.md#4-an-external-review-challenged):

- **A spec per component**, with a topology file: rejected by D3.
- **Diagrams as illustrations only:** rejected for lifetimes by D4.
- **Executable scenarios as the spec** (Gherkin): rejected by D4.
- **Models normative in full:** rejected by D5.
- **Keep the template, add guidance:** rejected; the template's shape is what
  invites narration for lifetimes (Motivation).

## Impact

- **Public API:** none.
- **Backwards compatibility:** no behaviour changes. Spec IDs stay stable;
  splitting a spec moves sections without renumbering their meaning
  (`000-process.md` Rule 5).
- **Process:** `000-process.md` Rule 3, Rule 7 and § Spec format change through
  the ADR; `formal/README.md` § Layers at a glance gains the kind each layer
  governs.
- **Testing:** each lifecycle diagram that becomes a source needs a parser
  check against its TLA+ model; each Assumptions line needs a conformance test
  that cites it.
- **Follow-up work:** BK-456 splits spec 003 by kind and prunes it against D1.
  BK-454 and BK-455 (the read handle, the `Session` state set) are the first
  lifetimes to take D4's form. BK-435 and BK-436 tie spec 051 to operations
  and backends through D3's single-call kind and D6's assumptions.

## Open Questions

1. **The guide's home:** decided 2026-10-18, a new authority doc
   `sdd/SPEC-DESIGN.md` that `000-process.md` § Spec format links; research § 6
   becomes its doctrine.
2. **Diagram or module as source** for a lifetime: the Mermaid diagram with
   the TLA+ module checked against it, or the module with the diagram
   generated from it.
3. **`verify-tla` gating** (ID-150): D5 needs it to gate for every clause it
   governs. If ID-150 decides against, lifetime clauses stay prose-governed.
4. **Type strictness on tolerant calls per profile** (BK-457's dossier): D6
   makes it expressible; whether `delete(folder, missing_ok=True)` stays strict
   on flat backends against its wire cost is still open.
5. **Migration order:** BK-456 first, since spec 003 is where the
   contradictions were measured, or the new lifetimes first (BK-454, BK-455),
   since they are written fresh.

## References

- Analysis: [`research-spec-design.md`](../research/research-spec-design.md)
- Exemplar: [spec 051](../specs/051-store-tree.md)
- Authority today: [`000-process.md` Rules 3, 5 and
  7](../000-process.md#rules), [`formal/README.md`](../formal/README.md)
- Writing rules: [`CONTENT-RULES.md`](../CONTENT-RULES.md)
- Prior formal work: [`research-id-147-tla-augmentation.md`](../research/research-id-147-tla-augmentation.md),
  [`research-store-model-axioms.md`](../research/research-store-model-axioms.md)
- Evidence and the first two reviews: [BK-457's
  dossier](../backlog/bk-457-declarative-spec-adr.md)
