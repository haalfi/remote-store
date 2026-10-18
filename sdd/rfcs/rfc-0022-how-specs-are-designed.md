# RFC-0022: How specs are designed

## Status

Draft, 2026-10-18. Tracked as **BK-457**. Graduates to one ADR (D1, D3, D5,
D6, and the Rule 3 and Rule 7 amendment) and one authoring guide (D2, D4, D7,
D8), the new authority doc `sdd/SPEC-DESIGN.md` (Open Question 1, decided).
The analysis behind it, a maintainer session that walked one operation, a
streaming read, from key to bytes, tested against outside evidence, is
[`research-spec-design.md`](../research/research-spec-design.md); this RFC
holds only the decisions, with the verdicts of [research §
12](../research/research-spec-design.md#12-verdicts-per-rfc-decision) folded
in.

## Summary

**A spec states what an observer can check, split by the kind of truth it
states, in the form that kind needs, governed by the formal layer that can
prove it as far as a bridge binds that layer to the code.** Everything else,
how an implementation reaches the outcome, which work is still open, and what
another layer decides, lives outside the spec. The research's core synthesis,
a bounded hypothesis rather than an established result, sets the direction:
agents do not need more prose; they need tighter feedback loops, refereed by
the spec.

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
tells an implementation how to reach an outcome moves to an ADR, a design note
or the per-task plan; it is relocated, not deleted, because step plans
measurably help whoever implements. Mechanism a caller can observe (the order
of side effects, a visible retry) is contract and stays.

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

In this RFC, a *lifecycle* is a clause of the Lifetime kind, and only that
kind; Environment and Liveness are named as such.

Components (store, kernel, driver, session, stream) are where a property is
enforced, not where it is stated. Ownership, state and time cross components,
so a spec per component scatters each such property over several files.

Within a kind, the second cut is an interface contract between layers (the
store's API against the backend's), so each side can be checked on its own. A
property that spans kinds names one owning spec, and the others link to it.

This partition is a candidate, not a shown optimum: the evidence does not
establish cutting by property, and it is not yet compared with one operation
contract plus linked lifecycle and consistency models (Open Question 8).

An existing spec that mixes kinds is split along these lines. For spec 003
that is BK-456's work, which this proposes changing from a split by layer to a
split by kind where the two differ (BK-456's open decision).

### D4. Each kind takes the form it needs

| Kind | Form |
| --- | --- |
| Structure, function | One invariant per section, one line where it fits |
| Single call | Invariants plus one outcome table: input state against observable result and error |
| Lifetime | The TLA+ module is the source; a closed-world state diagram is its checked view, plus the invariants that span states or objects (closed once, one owner, a closed session has no open handle) |
| Environment | An Assumptions section: each assumption one line, named so a conformance test can cite it |
| Liveness | Bounded obligations a test can fail (a retry completes within N attempts under injected delay M); fairness conditions go to Assumptions |

**Closed world, checked both ways:** a transition the diagram does not draw is
forbidden, and a drawn transition no run reaches is a defect. The diagram uses
a declared Mermaid subset (flat states, `[*]`, `A --> B : Action`), read by a
parser in this repo, and a check asserts that its edges equal the phase
transitions of a small TLC configuration. A diagram without that check is a
view and states nothing. Mermaid is not the source because it has no execution
semantics ([research § 10](../research/research-spec-design.md#10-lifecycle-as-checked-source-the-module-wins-the-diagram-is-a-checked-view)).

Executable examples (a scenario, a worked case) belong to the test tier, each
traced to the invariant it shows. A scenario covers one case and an invariant
covers all of them, so examples cannot be the spec. Gherkin is not adopted:
scenarios are traces and cannot state "an undrawn transition is forbidden",
their Given and When steps invite the step order D1 removes, and they add a
step-definition layer beside pytest. This departs from spec-kit's
Given/When/Then; no evidence shows either form helps agents more.

### D5. The formal layer that can prove a kind governs it, through a bridge

| Kind | Governing layer |
| --- | --- |
| Structure | Alloy (bounded) and Lean (unbounded) |
| Function, single call | Dafny |
| Lifetime, environment | TLA+ |
| Liveness | TLA+ as a design aid; governs only as bounded obligations |

**Where a model of the property exists and a bridge binds it to the tests, it
governs, as far as the bridge reaches; the prose states the invariant in one
sentence and links it.** That extends item 2 of
[`000-process.md` § Attribution inside the intent
domain](../000-process.md#attribution-inside-the-intent-domain) (prose carries
no presumption against a verified postcondition) from a defeater into the
default, and amends Rule 3 ("specs are authoritative") to
"the spec and its governing model are authoritative", without superseding it.
Where no model exists, the prose governs as today. Models are not made
normative in full: every clause without one would lose its normative home
(the qualification in BK-457's dossier).

**A model governs code only through a bridge, and only for the executions the
bridge observes or generates.** No bridge in industrial use is a proof; each
establishes agreement on what it exercises. An unbridged model informs review.
The bridge level grades verification confidence, not normative authority: a
conflict between contract, model, test and code is a finding to investigate
and resolve under Rule 7, since a test can encode a bug and a bridged model can
rest on a mistaken contract. The bridges, in order of adoption:

| Layer | Bridge to code | Governs |
| --- | --- | --- |
| Dafny | The compiled oracle with differential tests, and the Python twin parity check | Single-call semantics on the generated inputs |
| TLA+ | First, tests generated from the model (ITF traces replayed by pytest); second, recorded runs validated against the model | The generated, then the observed, transitions |
| TLA+ (concurrency) | Black-box history checking against a sequential model | Observable histories, under the checker's assumptions; highest cost |
| Alloy, Lean | A reference model in the test suite (as `tests/test_store_tree.py` does for spec 051) and the axioms as Hypothesis properties | Sampled structures |

What each level may claim is [research §
9](../research/research-spec-design.md#9-model-to-code-bridges-every-working-bridge-is-empirical)'s
ladder. A clause's level is derived from its bridges and their tests, never
tagged in the spec by hand (D8).

**Graduation path.** Every clause starts with contract tests. A formal model is
added only where review measurably fails: ownership, interleavings, time. The
layers are adopted one kind at a time, Dafny for single calls first since its
bridge exists.

A clause governed by a model whose check does not gate is not governed. TLA+
authority therefore needs `verify-tla` to gate for the clauses it governs,
which Open Question 3 settles: per module, from the PR that adds its bridge.

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
   against, named so an agent can read or run it. Which tests cite which
   section derives from the tests' spec marks, not from a list in the spec.

This replaces the per-section template in `000-process.md` § Spec format. Its
Example field moves to the test tier (D4).

### D8. A spec carries no project state

**No status, no backlog IDs, no "yet" in a spec, and no copy of another
layer's facts.** A link runs from the less stable artifact to the spec: a
backlog item names the spec it serves, never the reverse. What a clause is
checked against today is stated once, as "Tested against", and which backend
it is asserted for derives from the tests' spec tags.

## Alternatives Considered

Weighed in [research § 4](../research/research-spec-design.md#4-an-external-review-challenged)
and §§ 9 to 11:

- **A spec per component**, with a topology file: rejected by D3.
- **Diagrams as illustrations only:** rejected for lifetimes by D4.
- **The diagram as source**, with the model checked against it: rejected by
  D4; Mermaid has no execution semantics.
- **Authority by layer alone**, without a bridge: rejected by D5; models
  without one are documented to drift.
- **Executable scenarios as the spec** (Gherkin): rejected by D4.
- **Models normative in full:** rejected by D5.
- **Keep the template, add guidance:** rejected; the template's shape is what
  invites narration for lifetimes (Motivation).

## Impact

- **Public API:** none.
- **Backwards compatibility:** no behaviour changes. Spec IDs stay stable;
  splitting a spec moves sections without renumbering their meaning
  (`000-process.md` Rule 5).
- **Process:** `000-process.md` Rule 3 and Rule 7 change through the ADR;
  § Spec format is replaced by the guide `sdd/SPEC-DESIGN.md`, which it then
  links (D7, Open Question 1); `formal/README.md` § Layers at a glance gains the
  kind each layer governs.
- **Testing:** each lifecycle diagram needs the edge-equality check against
  its TLA+ model, and generated lifecycle tests need a Python ITF replayer,
  which no tool provides today; each Assumptions line needs a conformance test
  that cites it.
- **Follow-up work:** BK-456 splits spec 003 and prunes it against D1.
  BK-454 and BK-455 (the read handle, the `Session` state set) are the first
  lifetimes to take D4's form. BK-435 and BK-436 tie spec 051 to operations
  and backends through D3's single-call kind and D6's assumptions.

## Open Questions

1. **The guide's home:** decided 2026-10-18, a new authority doc
   `sdd/SPEC-DESIGN.md` that `000-process.md` § Spec format links; research § 6
   becomes its doctrine.
2. **Diagram or module as source** for a lifetime: decided 2026-10-18 by the
   research, the TLA+ module, with the diagram a checked view (D4).
3. **`verify-tla` gating:** decided 2026-10-18 by ID-150. Gating follows the
   bridge, per module: a TLA+ module gates from the PR that adds its bridge,
   and an unbridged one stays informational, since gating it would prove only
   that the model agrees with itself. `Observer.tla` has no bridge, so it
   stays informational under the successor revisit, ID-270. Until a bridged
   module lands, lifetime clauses stay prose-governed. The ADR replaces
   [`formal/README.md` § Authoring rules](../formal/README.md#authoring-rules)
   rule 3's catch-first bar with this rule.
4. **Type strictness on tolerant calls per profile** (BK-457's dossier): D6
   makes it expressible; whether `delete(folder, missing_ok=True)` stays strict
   on flat backends against its wire cost is still open.
5. **Migration order:** BK-456 first, since spec 003 is where the
   contradictions were measured, or the new lifetimes first (BK-454, BK-455),
   since they are written fresh.
6. **Conflicts under `000-process.md` Rule 7:** how the ADR amends Rule 7's
   defeaters so that a clause's bridge level informs, but does not decide, a
   conflict between contract, model, test and code.
7. **A bridge acceptance checklist** for the guide (observable interface,
   encoding of runtime values into model values, generation or capture method,
   pass criterion, known blind spots, owning CI job), proposed in review
   ([research § 14](../research/research-spec-design.md#14-external-reviews-considered)).
8. **The partition against an alternative:** whether D3's split beats one
   operation contract with linked lifecycle and consistency models, judged by
   duplication, cross-reference burden, change propagation and test ownership.

## References

- Analysis and outside evidence: [`research-spec-design.md`](../research/research-spec-design.md)
- Exemplar: [spec 051](../specs/051-store-tree.md)
- Authority today: [`000-process.md` Rules 3, 5 and
  7](../000-process.md#rules), [`formal/README.md`](../formal/README.md)
- Writing rules: [`CONTENT-RULES.md`](../CONTENT-RULES.md)
- Prior formal work: [`research-id-147-tla-augmentation.md`](../research/research-id-147-tla-augmentation.md),
  [`research-store-model-axioms.md`](../research/research-store-model-axioms.md)
- Evidence and the first two reviews: [BK-457's
  dossier](../backlog/bk-457-declarative-spec-adr.md)
