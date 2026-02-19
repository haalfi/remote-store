# SDD Process — How Specs Work in This Repo

## Overview

This repository follows **Spec-Driven Development (SDD)**: every feature, contract, and design decision is captured in a written specification *before* code is written. Specs are the single source of truth.

## Workflow

```
1. SPEC      → Write sdd/specs/NNN-<topic>.md defining contracts, invariants, error behavior
2. TEST      → Write tests derived from the spec, each referencing its section ID
3. IMPLEMENT → Write code to satisfy the tests (and thus the spec)
4. VALIDATE  → Verify spec ↔ test ↔ code traceability
```

## Directory Structure

```
sdd/
  000-process.md              # This file — how specs work
  BACKLOG.md                  # Tiered work tracker (blockers → backlog → ideas → done)
  specs/
    001-store-api.md          # Store API + metadata models
    002-registry-config.md    # Registry lifecycle + configuration
    003-backend-adapter-contract.md  # Backend ABC + capabilities
    004-path-model.md         # RemotePath value object
    005-error-model.md        # Error hierarchy
    006-streaming-io.md       # Streaming I/O semantics
    007-atomic-writes.md      # Atomic write contract
  adrs/
    0001-*.md                 # Architecture Decision Records
  rfcs/
    rfc-template.md           # Template for new proposals
```

## Spec Format

Each spec uses numbered section IDs with a module prefix:

```markdown
# <Topic> Specification

## Overview
One-paragraph purpose statement.

## <PREFIX>-NNN: <Rule Title>
**Invariant:** <what must always be true>
**Preconditions:** <what the caller must ensure>
**Postconditions:** <what the callee guarantees>
**Raises:** <error conditions>
**Example:**
    <short code example>
```

### ID Prefixes

| Prefix | Module | Spec File |
|--------|--------|-----------|
| `STORE` | Store API | `001-store-api.md` |
| `MOD` | Metadata models | `001-store-api.md` |
| `REG` | Registry | `002-registry-config.md` |
| `CFG` | Configuration | `002-registry-config.md` |
| `BE` | Backend contract | `003-backend-adapter-contract.md` |
| `CAP` | Capabilities | `003-backend-adapter-contract.md` |
| `PATH` | RemotePath | `004-path-model.md` |
| `ERR` | Errors | `005-error-model.md` |
| `SIO` | Streaming I/O | `006-streaming-io.md` |
| `AW` | Atomic writes | `007-atomic-writes.md` |
| `S3` | S3 backend | `008-s3-backend.md` |
| `SFTP` | SFTP backend | `009-sftp-backend.md` |
| `NPR` | Native path resolution | `010-native-path-resolution.md` |

## Test ↔ Spec Traceability

Tests reference their spec section via a `pytest.mark.spec` marker:

```python
@pytest.mark.spec("PATH-003")
def test_double_dot_rejected():
    """RemotePath rejects '..' segments with InvalidPath."""
    with pytest.raises(InvalidPath):
        RemotePath("foo/../bar")
```

This enables:
- `pytest -m "spec"` — run all spec-derived tests
- Traceability audits — every spec section has tests, every test traces to a spec
- Living documentation — specs + passing tests = proven contracts

## ADRs (Architecture Decision Records)

ADRs capture *why* a design decision was made. They are immutable once accepted — if a decision is reversed, a new ADR supersedes the old one.

Format: `sdd/adrs/NNNN-<short-title>.md`

See any existing ADR for the template structure.

## RFCs (Requests for Comments)

RFCs are proposals for new features or significant changes. They follow the spec-first contribution model:

1. Open a PR with an RFC in `sdd/rfcs/`
2. Community discusses and iterates
3. If accepted, the RFC graduates to a spec in `sdd/specs/`
4. The RFC file is kept for historical reference

Format: `sdd/rfcs/rfc-NNNN-<short-title>.md` — see `rfc-template.md`.

## Backlog

All work — from half-formed ideas to ship-blocking tasks — is tracked in
`sdd/BACKLOG.md`. Items live in one of four tiers and graduate upward as they
are evaluated and prioritized:

```
Ideas  →  Backlog (Prioritized)  →  Release Blockers  →  Done
```

| Tier | Prefix | Meaning |
|------|--------|---------|
| **Release Blockers** | `BL-NNN` | Must be resolved before the next PyPI publish. |
| **Backlog** | `BK-NNN` | Committed work, queued behind blockers. |
| **Ideas** | `ID-NNN` | Parking lot — not evaluated, not committed to. |
| **Done** | `DONE-NNN` | Completed items kept for reference. |

### How items move

- Anyone can add an **Idea** at any time — just append to the Ideas section.
- An Idea is promoted to **Backlog** when it has a clear scope and someone
  commits to writing an RFC or spec for it.
- A Backlog item becomes a **Release Blocker** when it is required for the
  upcoming release (e.g. missing docs, broken extras, CI gaps).
- Once completed, items move to **Done** with their original description
  preserved.

### Relationship to specs

Backlog items that involve code changes must still go through the SDD pipeline:
the item tracks *what* needs doing; the RFC/spec tracks *how*.

```
BACKLOG.md (what)  →  rfcs/rfc-NNNN.md (proposal)  →  specs/NNN-*.md (contract)  →  tests  →  code
```

Operational items (CI config, branch protection, dependency pins) skip the
RFC/spec step — they are tracked and closed directly in the backlog.

## Versioning

See [CONTRIBUTING.md § Versioning](../CONTRIBUTING.md#versioning) for the canonical
versioning policy, bump rules, and tooling.

## Rules

1. **No code without a spec** — every testable contract must have a spec section ID.
2. **No spec without tests** — every spec section must have at least one test with `@pytest.mark.spec("ID")`.
3. **Specs are authoritative** — if code and spec disagree, the code is wrong.
4. **ADRs are immutable** — supersede, don't edit.
5. **IDs are stable** — once assigned, a section ID never changes meaning. Deprecated sections are marked `[DEPRECATED]`, not removed.
