# Spec Design Rules
<!-- doc: dual dest=explanation/design/spec-design.md -->

## Intent & Scope

THE source for what a spec under `sdd/specs/` states, where one spec ends,
which form each of its sections takes, and which artifact governs a clause.
Applies when a spec is written, split or rewritten, and when a review judges
one. A section edited in place keeps its spec's current form; the spec adopts
these rules when it is next rewritten. Why each rule exists:
[ADR-0048](adrs/0048-how-specs-are-designed.md).

Siblings: [`000-process.md`](000-process.md) owns section IDs, test
traceability and the attribution procedure (Rule 7);
[`formal/README.md`](formal/README.md) owns the formal layers and when their
checks gate; [`CONTENT-RULES.md`](CONTENT-RULES.md) owns how the prose is
written.

<a id="rules"></a>
## Rules

1. <a id="observable-contract"></a>**A spec states the observable contract and
    nothing else.** [review-enforced]
    Preconditions, postconditions, observable side effects, error precedence,
    and for a lifetime its states and transitions. Every sentence passes two
    tests:
    - **Two implementations:** two different correct implementations can both
      satisfy it. A sentence that fails mandates an algorithm; it moves to an
      ADR, a design note or the task's plan, relocated rather than deleted.
    - **Can fail:** a black-box test, a model check or a proof could fail it. A
      sentence that fails is not a clause: state it as an assumption (Rule 5)
      or remove it.

    Mechanism a caller can observe (the order of side effects, a visible retry,
    which refusal wins when two hold) is contract and stays. Which refusal wins
    is stated as error precedence, never as an order of steps. So is an observable
    quality bound (a cost, a security property, what a message must carry)
    that a test can fail.

2. <a id="kind-of-truth"></a>**One spec states one kind of truth about one
    subject.** [review-enforced]

    | Kind | States | A witness of its violation is |
    | --- | --- | --- |
    | Structure | What holds at one instant | One state |
    | Function | Input to output, and totality | One input and its output |
    | Single call | One operation's outcome against the state when it runs | A state, one call and its result |
    | Lifetime | The states and transitions of something that outlives a call | A sequence of calls on one object |
    | Environment | What the system relies on from outside it | A behaviour outside the library's control |
    | Liveness | That something eventually happens, or never repeats | A run past its bound |

    A clause's kind is the shape of a witness that would violate it. A clause
    whose witness needs a behaviour outside the library's control is
    environment. Otherwise a clause whose witness fits two kinds belongs to the
    larger, in this order: liveness (a run past its bound), lifetime (a call
    sequence on one object), single call, function, structure.

    A component (store, kernel, driver, session, stream) is where a property is
    enforced, not where it is stated, so no spec is cut per component. The
    second cut, inside a kind, is an interface contract between layers (the
    store's API against the backend's), so each side can be checked on its own.
    A property that spans kinds has one owning spec; the others link to it.

3. <a id="form-per-kind"></a>**Each kind takes the form it needs.** [review-enforced]

    | Kind | Form |
    | --- | --- |
    | Structure, function | One invariant per section, one line where it fits |
    | Single call | One invariant per section, with one outcome table: input state against observable result and error |
    | Lifetime | The TLA+ module is the source; a closed-world state diagram is its checked view, plus one section per invariant that spans states or objects |
    | Environment | An Assumptions section: one line per assumption, named so a conformance test can cite it |
    | Liveness | Bounded obligations a test can fail; fairness conditions go to Assumptions |

    **A lifetime's diagram is closed-world and checked both ways:** a
    transition it does not draw is forbidden, and a drawn transition no run
    reaches is a defect. It uses the declared Mermaid subset (flat states,
    `[*]`, `A --> B : Action`), and a check asserts that its edges equal the
    phase transitions of a small TLC configuration. A diagram without that
    check is a view and states nothing. Until a lifetime has a module and that
    check, its spec states the states and transitions as a table, and the
    prose governs them.

    **Examples belong to the test tier**, each traced to the section it shows.
    No section is stated as a scenario (Given/When/Then).

4. <a id="governing-layer"></a>**The formal layer that can prove a kind
    governs it, through a bridge.** [review-enforced]

    | Kind | Governing layer |
    | --- | --- |
    | Structure | Alloy (bounded) and Lean (unbounded) |
    | Function, single call | Dafny |
    | Lifetime, environment | TLA+ |
    | Liveness | TLA+, only as bounded obligations |

    Where a model of a clause exists and a bridge binds it to the tests, the
    model governs that clause as far as the bridge reaches, and the section
    states the invariant in one sentence and links the model's clause. Where no
    model exists, or no bridge, the prose governs; an unbridged model informs
    review. A model governs only while its own check gates in CI; when a TLA+
    check gates is [`formal/README.md` rule 3](formal/README.md#authoring-rules)'s.
    A conflict
    between contract, model, test and code is resolved under
    [`000-process.md` Rule 7](000-process.md#intent-attribution). A bridge
    reaches a clause per section ID: the model's `@spec` tags and the tests'
    spec marks citing that ID derive it, as `scripts/check_formal_trace.py`
    does for Dafny. A spec never tags a clause's reach by hand. A bridge counts
    only once Rule 8's six items are stated for it, a bridge already in the
    repo included; until then its model informs review and the prose governs.
    The table names the layer a new model of each kind is written in.

5. <a id="profiles-and-assumptions"></a>**Profiles and assumptions are
    declared, not implied.** [review-enforced]
    A behaviour that differs by backend is stated as a named profile, declared
    by a capability or a driver flag, with each outcome it allows stated in the
    clause, never implied by an example backend. A bound on wire calls is a
    cost statement per profile, never a step order. What the spec
    relies on from outside goes in its Assumptions section. Whether a given
    backend meets an assumption is conformance, not spec: the shared contract
    tests check it, and the backend's capability declaration records it.

6. <a id="skeleton"></a>**Every spec takes one skeleton**, in this order.
    [review-enforced]
    1. **Overview:** the core claim, the scope and what is out of scope, led by
       at most three sentences ([`CONTENT-RULES.md` Rule 7](CONTENT-RULES.md#kernsatz)).
    2. **Terms:** every symbol and term the sections use, including any word
       the repo also uses in another sense.
    3. **Sections:** one invariant each, under a stable ID, in the form Rule 3
       gives the spec's kind.
    4. **Assumptions:** what the spec relies on and cannot check itself, one
       line each. An assumption several specs share has one owning environment
       spec, and the others link to it.
    5. **Notes:** not normative; derived properties and the proofs behind them.
    6. **Tested against:** the reference model or suite the sections are
       checked against, named so a reader can run it. Which test cites which
       section derives from the tests' spec marks, never from a list in the
       spec.

    The template is [`templates/spec-template.md`](templates/spec-template.md).

7. <a id="no-project-state"></a>**A spec carries no project state.** [review-enforced]
    No status, no backlog IDs, no "yet", and no copy of another layer's facts.
    A link runs from the less stable artifact to the spec: a backlog item names
    the spec it serves, never the reverse. Which backends a clause is asserted
    for derives from the tests' spec marks.

8. <a id="bridge-checklist"></a>**A bridge counts under Rule 4 only once a
    change states six things about it.** [review-enforced]
    1. The observable interface it exercises.
    2. How runtime values are encoded into model values, and which glue between
       them is unverified.
    3. How executions are generated or captured.
    4. The pass criterion.
    5. Its known blind spots ([`DRIFT-RULES.md` Rule 7](DRIFT-RULES.md#miss-rate)).
    6. The CI job that owns it, and whether that job gates.

## Guides

### Review checklist

A spec is reviewed against eight properties. What each means is
[research § 6](research/research-spec-design.md#6-what-makes-a-spec-good).

| Property | Check | Rule |
| --- | --- | --- |
| Well founded | Each clause has a reason and an owner; axioms apart from what they imply | 6 (Notes) |
| Verifiable | Each clause has a defined witness of violation, or is an assumption | 1, 5 |
| Lasting | True without edits as the project moves | 7; [`CONTENT-RULES.md` Rule 1](CONTENT-RULES.md#six-month-test) |
| Correct | Says what the system must do, and it can | 4 |
| Free of contradictions | No two clauses or neighbouring specs disagree; one home per fact | 2 |
| No unstated gaps | Scope and non-scope stated; open questions declared open | 3, 6 |
| Placed | Covers only its own kind and layer | 1, 2 |
| Comprehensible | Leads with its claim, in the form its content needs | 3, 6; [`CONTENT-RULES.md` Rules 7 and 8](CONTENT-RULES.md#kernsatz) |

### Exemplar

[Spec 051](specs/051-store-tree.md) is a structure spec that meets Rules 1, 2,
3 and 7 in its sections: one invariant each, axioms apart from the lemmas they
imply, and nothing about operations or backends. It predates Rule 6's order:
it states its Terms and what it is tested against inside its Overview, and its
Name equality paragraph, which says what a coarser backend represents, is an
environment assumption Rule 6 would put under Assumptions.
