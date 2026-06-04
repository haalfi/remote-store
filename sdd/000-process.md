# SDD Process
<!-- doc: dual dest=explanation/design/process.md -->

## Intent & Scope

Authoritative source for the Spec-Driven Development workflow, spec/ADR/RFC formats, backlog tiers, and test traceability. Governs all `sdd/` content.

<a id="rules"></a>
## Rules

1. **No code without a spec**: every testable contract must have a spec section ID.
2. <a id="spec-test-traceability"></a>**No spec without tests**: every spec section must have at least one test with `@pytest.mark.spec("ID")`.
3. **Specs are authoritative**: if code and spec disagree, the code is wrong.
4. **ADRs are immutable once Accepted**: supersede an Accepted ADR, never edit it. Drafts may be refined before acceptance.
5. **IDs are stable**: once assigned, a section ID never changes meaning. Deprecated sections are marked `[DEPRECATED]`, not removed.
6. <a id="workflows"></a>**Workflows**:
   - **Features**: SPEC → TEST → IMPLEMENT → VALIDATE → DOCS. Operational items (CI, docs, pins) skip the spec step.
   - **Bug fixes**: BACKLOG → CHANGELOG → failing TEST → FIX → COMMIT together. If the bug contradicts a spec invariant, update the spec.

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
