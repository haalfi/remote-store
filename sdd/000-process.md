# SDD Process
<!-- doc: dual dest=explanation/design/process.md -->

## Intent & Scope

Authoritative source for the Spec-Driven Development workflow, spec/ADR/RFC formats, backlog tiers, and test traceability. Governs all `sdd/` content.

<a id="rules"></a>
## Rules

1. **No code without a spec**: every testable contract must have a spec section ID.
2. <a id="spec-test-traceability"></a>**No spec without tests**: every spec section must have at least one test with `@pytest.mark.spec("ID")`.
3. **Specs are authoritative**: if code and spec disagree, the code is wrong — unless the spec's claim was never enforced, which [Rule 7](#intent-attribution) qualifies: that makes the claim undecided, not the code right.
4. **ADRs are immutable once Accepted**: supersede an Accepted ADR, never edit it. Drafts may be refined before acceptance.
5. **IDs are stable**: once assigned, a section ID never changes meaning. Deprecated sections are marked `[DEPRECATED]`, not removed.
6. <a id="workflows"></a>**Workflows**:
   - **Features**: SPEC → TEST → IMPLEMENT → VALIDATE → DOCS. Operational items (CI, docs, pins) skip the spec step.
   - **Bug fixes**: BACKLOG → CHANGELOG → failing TEST → FIX → COMMIT together. If the bug contradicts a spec invariant, update the spec.
7. <a id="intent-attribution"></a>**Prose records the resolution; it does not win the argument**: when spec prose, a Dafny postcondition and a conformance test disagree, the decision is written into the prose — but prose carries no presumption of correctness against a verified postcondition or against a claim the conformance suite never asserted. See [§ Attribution inside the intent domain](#attribution-inside-the-intent-domain).

## Guides

<a id="spec-format"></a>
### Spec format

Each spec uses numbered section IDs with a module prefix declared at the top of each file:

```markdown
## <PREFIX>-NNN: <Rule Title>
**Invariant:** <what must always be true>
**Preconditions:** <what the caller must ensure>
**Postconditions:** <what the callee guarantees>
**Raises:** <error conditions>
**Example:**
    <short code example>
```

Each spec declares its prefix (e.g. `STORE`, `PATH`, `ERR`, `CACHE`). A test referencing `STORE-005` traces back to section 005 in the Store API spec.

Specs cover both library contracts and build/CI tooling contracts.
Library specs use subsystem prefixes (`STORE`, `S3`, `ERR`, ...) and
are tested against runtime code. Tooling specs use a tool/framework
prefix (e.g. `DOCFRAME`) and are tested against the script's output
or repository state. Tooling specs declare `**Scope:** Build & CI
tooling` near the top so the category is visible without reading
the body. The two coexist in the flat `sdd/specs/NNN-*.md` numbering;
no subdirectory split is used while the tooling-spec count is small.

### Test traceability

```python
@pytest.mark.spec("PATH-003")
def test_double_dot_rejected():
    """RemotePath rejects '..' segments with InvalidPath."""
    with pytest.raises(InvalidPath):
        RemotePath("foo/../bar")
```

`pytest -m "spec"` runs all spec-derived tests.

<a id="attribution-inside-the-intent-domain"></a>
### Attribution inside the intent domain

Rule 3 settles intent against code. These settle the intent domain against
itself: spec prose, the Dafny model, and the conformance suite. *Where the
resolution is written* and *which side was wrong* are two questions; answer them
in that order.

1. **The resolution is written into the prose spec.** A disagreement closed by
   editing only a postcondition, only a test, or only a backend is not closed.
   Amend the spec section in the same change.
2. **Prose carries no presumption of correctness.** It is the only description in
   this domain with no mechanical counterpart, so a prose claim is evidence of
   intent and of nothing else. Three defeaters strip that presumption. Only the
   first two also settle which side moves; the third reopens the question:

   | Defeater | What you observe | What follows |
   |---|---|---|
   | **Unsatisfiable** | The verifier rejects the postcondition form the prose requires | Prose moves — the section contradicts itself. Owned by [`formal/README.md`](formal/README.md#layers-at-a-glance) and stated here only to complete the procedure |
   | **Under-determined** | Prose is silent, or permits a variation, where shipped behaviour is uniform | Prose moves — state the behaviour and add the test it never had. Silence is not a licence to diverge; uniformity is not proof of intent, so where it is defensive duplication of a rule enforced elsewhere, spec it at the layer that enforces it |
   | **Unenforced** | Prose demands X and no test asserts X. A clause-level question: [Rule 2](#spec-test-traceability)'s marker is section-level, so a marked section is not evidence the clause is covered. Backends diverging is how you notice, not what decides | Nothing moves yet. An unenforced claim is not a default, so decide it once: adopt the divergence as a declared variation, or enforce X as a breaking change on the ordinary path |

3. **Two mechanical sides agreeing is not a vote.** A postcondition and a test
   written in one change from one reading are one description, not two. Establish
   independence per [`DRIFT-RULES.md` Rule 8](DRIFT-RULES.md#independence) before
   counting them as agreement.
4. **ADRs and RFCs record decisions, not contracts.** Where either disagrees with
   a spec about what the system must do, the spec governs; supersede the ADR
   rather than editing it ([Rule 4](#rules) above).
5. **A divergence you keep is registered, not remembered.** Give it an owner and a
   rationale, in one of the register forms
   [`DRIFT-RULES.md` Rule 6](DRIFT-RULES.md#tolerated) admits.

One case has nothing to attribute: **prose absent *and* shipped behaviour
non-uniform**, so no defeater has an observation to fire on. Prose silence by
itself does not qualify — that is the under-determined row's territory. Here the
conformance suite is the one driver
([`DRIFT-RULES.md` Rule 1](DRIFT-RULES.md#one-driver)) and the contract is
undecided rather than misattributed.

What that moots is the *arbitration*, not item 1 and not [Rule 1](#rules):
deciding the behaviour creates a testable contract, so it gets a spec section and
the decision still lands in prose. A conformance cell with no parent section is
the orphan realization this procedure exists to prevent.

Dafny against the conformance suite is settled separately by the compiled-oracle
principle in [`formal/README.md`](formal/README.md#compiled-oracle), which these
rules do not restate. The evidence and argument behind them:
[research § 5](research/research-inconsistency-detection-multi-artifact.md).

### Backlog

Active work and ideas are tracked in [`sdd/BACKLOG.md`](BACKLOG.md).
Completed items live in [`sdd/BACKLOG-DONE.md`](BACKLOG-DONE.md).

`BACKLOG.md` is the single source of truth for ID prefixes, status conventions,
completion workflow, and section structure. See its "How this file works" header.

<a id="feature-type-definition-of-done"></a>
### Feature-type Definition of Done

Rule 6 gives a feature's lifecycle order; the two checklists below give its
exit criteria. Pick the row that matches the change and treat each box as a
gate, not a suggestion. For why each gate exists, see the originating backlog
item BK-237 and its trace.

#### Contract-expanding feature

Use when the change adds or widens a public contract — a new `Capability`,
Store method, or error class.

- [ ] **Spec / RFC updated**, with the conformance, property-based, and
  formal-proof work the feature needs scoped up front in the RFC, not
  discovered as a string of follow-ups.
- [ ] **Capability declaration reviewed for both over- and under-declaration**:
  claiming a capability a backend does not honour is as wrong as omitting one
  it does.
- [ ] **Conformance test + xfail registry landed _before_ the first backend
  implementation**, so backends move themselves off the xfail list against a
  contract that already exists.
- [ ] **Wrapper forwarding verified** — every `Store`-wrapping layer forwards
  the new surface. The wrapping layers are the `ProxyStore` base, the wrappers
  under `src/remote_store/ext/`, and the sync and oracle adapters; consult
  those locations rather than a fixed class list, which drifts as wrappers are
  added.
- [ ] **Docs ripple swept** — every guide, snippet, and reference surface the
  new contract appears in.
- [ ] **Audit pass run against the unreleased work** as a pre-merge gate.

#### Bridge / adapter feature

Use when the change introduces a cross-layer wrapper — anything that adapts
one `Store` or backend surface onto another.

- [ ] **API-parity test against the wrapped layer** — the bridge exposes the
  contract it wraps.
- [ ] **Event-loop and resource-lifecycle test** — loops, connections, and
  handles are torn down without leaks.
- [ ] **Cancellation-invariant test** — cancelling mid-operation leaves no
  half-state and raises the right error.
- [ ] **Live-backend coverage**, not just doubles.
- [ ] **`filterwarnings = error`-clean suite** under the global policy in
  `pyproject.toml`.

<a id="document-types"></a>
### Document types

Five document categories live under `sdd/`. Each has a clear purpose and lifecycle:

| Category | Path pattern | Purpose | Lifecycle |
|----------|-------------|---------|-----------|
| **Specs** | `sdd/specs/NNN-<topic>.md` | Declarative contracts — what must be true | Lives forever, versioned. IDs are stable and immutable. |
| **ADRs** | `sdd/adrs/NNNN-<short-title>.md` | Decision records — why we chose this approach | Immutable once status is Accepted. Before acceptance a draft may be refined; after acceptance supersede with a new ADR, never edit. |
| **RFCs** | `sdd/rfcs/rfc-NNNN-<short-title>.md` | Proposals for any significant change (features, refactors, process improvements) | If accepted, graduates to a spec and/or ADR. Kept as historical reference. |
| **Research** | `sdd/research/research-<topic>.md` | Exploration, feasibility analysis, implementation plans | Point-in-time snapshot. Should remain as written; only update if a factual error is corrected — all other updates require a new document. Never treat as a living doc. |
| **Audits** | `sdd/audits/audit-NNN-<topic>.md` | Systematic quality reviews (security, compliance, docs) | Permanent record. Never edited after writing — findings may be actioned via backlog, but the report stays as written. |

**Decision rule:** If you're asking "should we do X?" → research. If you're proposing "let's do X this way" → RFC. If the decision is made → ADR. If it defines a testable contract → spec. If it reviews existing quality → audit.

### Versioning

See [CONTRIBUTING.md § Versioning](../CONTRIBUTING.md#versioning).
