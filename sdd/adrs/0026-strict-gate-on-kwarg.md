# ADR-0026: Strict-Gate Pattern for Optional Capability Kwargs

## Status

Accepted

## Context

`USER_METADATA` (RFC-0011 / ID-146) adds an optional `metadata=` kwarg to
`Store.write*()`. The backend either supports user metadata natively
(`Capability.USER_METADATA`) or it does not. When it does not, the question
is: raise or silently drop?

The same question was settled for atomic writes in AW-007 (spec 007): if a
caller opts into `write_atomic` on a backend without `ATOMIC_WRITE`, we raise
`CapabilityNotSupported` before I/O. The pattern was called "strict gate":
every optional behaviour that the caller explicitly requests — rather than a
capability that merely upgrades a default path — raises before I/O if the
backend cannot honour it.

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

### Existing instances

| Capability        | Kwarg gated          | Method(s)              | Spec ref |
| ----------------- | -------------------- | ---------------------- | -------- |
| `ATOMIC_WRITE`    | (gates whole method) | `write_atomic()`       | AW-007   |
| `USER_METADATA`   | `metadata=`          | `write*()` variants    | WR-010   |

`ATOMIC_WRITE` is listed here because it established the raise-before-I/O
principle, even though it gates the entire method rather than a single kwarg.
`USER_METADATA` is the first true strict-gate-on-kwarg instance.

### How to apply the pattern for future capabilities

When designing a new optional kwarg on an existing Store method:

1. Define a new `Capability` enum member for the feature.
2. Add Store-layer validation: if the kwarg is non-`None` / non-default and
   the backend lacks the capability, raise `CapabilityNotSupported`.
3. Add the capability to `CAP-007` (spec 003) under the strict-gate section.
4. Document per-backend declarations in the feature spec (e.g., WR-010).
5. Add negative tests: every non-declaring backend raises on the guarded kwarg.

## Consequences

- Callers get a clear, early error rather than a silent correctness failure.
- The pattern is named and documented; future contributors have a precedent.
- Test coverage requirement: every non-declaring backend must have a negative
  test asserting `CapabilityNotSupported` when the guarded kwarg is passed.
- The Store layer is the single enforcement point — backends do not need to
  validate the kwarg themselves.
