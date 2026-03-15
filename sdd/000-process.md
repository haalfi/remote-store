# SDD Process

## Intent & Scope

Authoritative source for the Spec-Driven Development workflow, spec/ADR/RFC formats, backlog tiers, and test traceability. Governs all `sdd/` content.

## Rules

1. **No code without a spec**: every testable contract must have a spec section ID.
2. **No spec without tests**: every spec section must have at least one test with `@pytest.mark.spec("ID")`.
3. **Specs are authoritative**: if code and spec disagree, the code is wrong.
4. **ADRs are immutable**: supersede, don't edit.
5. **IDs are stable**: once assigned, a section ID never changes meaning. Deprecated sections are marked `[DEPRECATED]`, not removed.
6. **Workflow**: every feature follows this pipeline:

```text
1. SPEC      → Write sdd/specs/NNN-<topic>.md defining contracts, invariants, error behavior
2. TEST      → Write tests derived from the spec, each referencing its section ID
3. IMPLEMENT → Write code to satisfy the tests (and thus the spec)
4. VALIDATE  → Verify spec ↔ test ↔ code traceability
5. DOCS      → Write or update examples, guides, docstrings, CHANGELOG
```

Operational items (CI config, docs, dependency pins) skip the spec step: tracked and closed directly in the backlog. Backlog items track *what* needs doing; the RFC or spec tracks *how*.

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

### ADRs, RFCs, research, and audits

- **ADRs** (`sdd/adrs/NNNN-<short-title>.md`): capture *why* a design decision was made. Immutable once accepted: if reversed, a new ADR supersedes the old one.
- **RFCs** (`sdd/rfcs/rfc-NNNN-<short-title>.md`): proposals for new features. If accepted, the RFC graduates to a spec in `sdd/specs/`. Kept for historical reference.
- **Research** (`sdd/research/research-<topic>.md`): exploratory analysis done before a feature is specified. Not edited after the related feature ships.
- **Audits** (`sdd/audits/audit-NNN-<topic>.md`): systematic reviews (adversarial, compliance, documentation). Findings tracked as backlog items.

### Versioning

See [CONTRIBUTING.md § Versioning](../CONTRIBUTING.md#versioning).
