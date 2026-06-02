# SDD Process
<!-- doc: dual dest=explanation/design/process.md -->

## Intent & Scope

Authoritative source for the Spec-Driven Development workflow, spec/ADR/RFC formats, backlog tiers, and test traceability. Governs all `sdd/` content.

## Rules

1. **No code without a spec**: every testable contract must have a spec section ID.
2. **No spec without tests**: every spec section must have at least one test with `@pytest.mark.spec("ID")`.
3. **Specs are authoritative**: if code and spec disagree, the code is wrong.
4. **ADRs are immutable once Accepted**: supersede an Accepted ADR, never edit it. Drafts may be refined before acceptance.
5. **IDs are stable**: once assigned, a section ID never changes meaning. Deprecated sections are marked `[DEPRECATED]`, not removed.
6. **Workflows**:
   - **Features**: SPEC → TEST → IMPLEMENT → VALIDATE → DOCS. Operational items (CI, docs, pins) skip the spec step.
   - **Bug fixes**: BACKLOG → CHANGELOG → failing TEST → FIX → COMMIT together. If the bug contradicts a spec invariant, update the spec.

## Guides

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

### Feature-type Definition of Done

Rule 6's feature workflow (SPEC → TEST → IMPLEMENT → VALIDATE → DOCS) says
*what order*; the two checklists below say *when a feature is actually done*.
Pick the row that matches the change and treat the boxes as gates, not
suggestions. Both were distilled from the v0.23.0→v0.24.0 retrospective,
where a single feature line (ID-146 → ID-151c) sprawled into eight sub-IDs
over two weeks because the conformance, doc-ripple, and scope-estimation work
was discovered after the fact instead of enumerated up front.

#### Contract-expanding feature

Use when the change adds or widens a public contract. The canonical trigger
is a new `Capability.X`, but any new Store method or error class qualifies.

- [ ] **Spec / RFC updated**, and the RFC scope **enumerates the conformance,
  PBT, and Dafny extensions the feature will need up front** — apply the
  memory `feedback_estimation.md` 2-3× rule at RFC time, not as a string of
  follow-ups discovered later.
- [ ] **Capability declaration reviewed for both over- *and* under-declaration**:
  a backend that claims a capability it does not honour is as wrong as one
  that omits a capability it does.
- [ ] **Conformance test + xfail registry landed _before_ the first backend
  implementation** — the contract is proven against the suite first, then
  backends move themselves off the xfail list.
- [ ] **Wrapper forwarding verified** across every layer that must pass the
  new surface through: `ProxyStore`, `ObservedStore`, `CachedStore`, the sync
  adapter, and the oracle adapter.
- [ ] **Docs ripple swept**: `docs-src/guides/`, `examples/snippets/`,
  `FEATURES.md`, and the capabilities matrix.
- [ ] **Audit-PR gate** run against the unreleased work — the audit-PR pattern
  (PR #465) filed six pre-release bugs against in-flight v0.23.0→v0.24.0 work;
  treat a focused audit pass as a recommended gate before the feature is done.

#### Bridge / adapter feature

Use when the change introduces a cross-layer wrapper — anything that adapts
one Store or backend surface onto another (sync↔async adapters, oracle
adapters, caching or observing proxies).

- [ ] **API-parity test against the wrapped layer** — the bridge exposes the
  same contract it wraps, proven rather than assumed.
- [ ] **Event-loop / resource-lifecycle test** — loops, connections, and
  handles are created and torn down without leaks.
- [ ] **Cancellation-invariant test** — cancelling mid-operation leaves no
  half-state and raises the right error.
- [ ] **Live-backend coverage**, not just doubles — the bridge is exercised
  against at least one real backend, since doubles hide loop and lifecycle
  bugs.
- [ ] **`filterwarnings = error` clean** — the suite passes under the global
  error-on-warning policy (configured in `pyproject.toml` `[tool.pytest.ini_options]`).

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
