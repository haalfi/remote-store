# ADR-0026: Strict-Gate Pattern for Optional Capability Kwargs

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

`USER_METADATA` (RFC-0011 / ID-146) adds an optional `metadata=` kwarg to
`Store.write*()`. The backend either supports user metadata natively
(`Capability.USER_METADATA`) or it does not. When it does not, the question
is: raise or silently drop?

The same question was settled for atomic writes. Two atomic-write
invariants together establish the precedent:

- **AW-007 (spec 007) — "Atomicity is Never Assumed":** the core never
  silently falls back to non-atomic writes when `ATOMIC_WRITE` is
  missing. This is the *never-silently-degrade* principle the present
  ADR inherits for `USER_METADATA`.
- **AW-002 (spec 007) — "Capability Gate":** `write_atomic` raises
  `CapabilityNotSupported` before any I/O if the backend lacks
  `ATOMIC_WRITE`. This is the *raise-before-I/O* mechanism the present
  ADR inherits for `USER_METADATA`.

Together, these two invariants name a pattern: every optional
behaviour that the caller explicitly requests — rather than a
capability that merely upgrades a default path — raises before I/O
if the backend cannot honour it, and never silently drops.

`USER_METADATA` is a second instance of this pattern. The decision deserves
its own ADR to name the pattern so future contributors can follow it
deliberately rather than rediscovering it case by case.

### The case against silent drop

Saga consumers treat "write returned" as "metadata is durable." A silent drop
means:

- The write succeeds.
- The caller believes metadata was stored.
- A downstream `get_file_info()` returns `FileInfo.metadata == None`.
- Data integrity invariants break silently, without a traceable error.

Silent degradation is worse than a loud failure: the failure is deferred,
possibly to a different service or audit step, and by then the context that
would explain it is gone.

### The case against silent drop even for idempotent metadata

One might argue that metadata is "advisory" and a drop is tolerable. This
argument fails for the target consumer: saga orchestrators use metadata to
carry correlation IDs and idempotency tokens. A drop is not a degraded
experience; it is a correctness failure.

### Why not a capability guard on the method?

`WRITE` already gates `write()`. Adding a second gate (`USER_METADATA`) to
gate the entire method would prevent callers from writing on non-declaring
backends when `metadata=` is absent — which is wrong. The capability gates
only the use of the kwarg, not the method.

This is a new pattern: a capability that gates a specific **kwarg** on an
existing method rather than the method as a whole.

## Decision

When a caller passes an optional kwarg that requires a specific capability,
and the backend does not declare that capability, raise
`CapabilityNotSupported` **before any I/O**. Never silently drop the kwarg.

### Naming the pattern: strict gate on kwarg

A *strict gate on kwarg* is a capability that:

1. Does not gate the method — the method works without it.
2. Does gate a specific optional argument — passing that argument requires
   the capability.
3. Raises `CapabilityNotSupported` before any I/O if the backend lacks the
   capability and the argument is supplied.

The validation happens in the Store layer (one place), not in each backend.

### Precedent (method-level raise-before-I/O gate)

| Capability       | Gate target   | Method(s)         | Spec ref |
| ---------------- | ------------- | ----------------- | -------- |
| `ATOMIC_WRITE`   | whole method  | `write_atomic()`  | AW-002   |

`ATOMIC_WRITE` is not a strict-gate-on-kwarg instance — it gates the
entire method, not an optional kwarg. It appears here because it
established the raise-before-I/O principle that the strict-gate-on-kwarg
pattern inherits. Future contributors should not use this row as a
pattern template.

### Strict-gate-on-kwarg instances

| Capability       | Gate target        | Method(s)             | Spec ref |
| ---------------- | ------------------ | --------------------- | -------- |
| `USER_METADATA`  | `metadata=` kwarg  | `write*()` variants   | WR-010   |

`USER_METADATA` is the first true strict-gate-on-kwarg instance. New
instances of this pattern go in this table.

### How to apply the pattern for future capabilities

When designing a new optional kwarg on an existing Store method:

1. Define a new `Capability` enum member for the feature.
2. Add Store-layer validation: if the kwarg is non-`None` / non-default and
   the backend lacks the capability, raise `CapabilityNotSupported`.
3. Add the capability to `CAP-007` (spec 003) under the strict-gate section.
4. Document per-backend declarations in the feature spec (e.g., WR-010).
5. Add negative tests: every non-declaring backend raises on the guarded kwarg.

### Adapter masking as a defensive application of the strict-gate pattern

`AsyncBackendSyncAdapter` applies the pattern defensively via capability masking.
It strips `USER_METADATA` (and `WRITE_RESULT_NATIVE`) from the inner async
backend's capability set, even when the wrapped backend declares them.  Without
masking, the Store-layer WR-010 gate would pass a non-empty `metadata=` argument
through to the adapter, but the adapter has no forwarding target — the async ABC
does not yet accept `metadata=`.  A silent drop would violate WR-012 (the
`WriteResult.metadata` echo guarantee) without triggering any error.

Masking is the mechanism that keeps the strict-gate invariant intact across
adapter wrapping: the gate fires at the Store layer (`CapabilityNotSupported`)
before the adapter is reached, so no I/O runs and no metadata is silently lost.
This is not an exception to the pattern; it is the same pattern applied one layer
earlier.  When the async ABC grows `metadata=` support (Step 3c), the masking is
removed and the adapter naturally inherits the inner backend's declarations.

## Consequences

- Callers get a clear, early error rather than a silent correctness failure.
- The pattern is named and documented; future contributors have a precedent.
- Test coverage requirement: every non-declaring backend must have a negative
  test asserting `CapabilityNotSupported` when the guarded kwarg is passed.
- The Store layer is the single enforcement point — backends do not need to
  validate the kwarg themselves.
