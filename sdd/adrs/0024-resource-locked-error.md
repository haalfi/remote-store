# ADR-0024: `ResourceLocked` Error Type

## Status

Accepted

## Context

Microsoft Graph returns HTTP `423 Locked` with an error code of
`resourceLocked` when an item is held by another session: typical
causes are an open co-authoring session in the Office clients, a
checked-out document in SharePoint, or an in-progress upload session
on the same item. The condition is:

- **Not a permissions problem.** The caller is authenticated and
  authorised; the resource itself is temporarily unavailable.
- **Not a throttling problem.** There is no `Retry-After` promise,
  and the condition may last seconds, minutes, or indefinitely.
- **Not a "resource missing" problem.** The item exists.
- **Retryable with caution.** A short bounded retry may succeed, but
  blind exponential retry could wait forever.

None of the existing `remote_store` errors capture this accurately:

- `PermissionDenied` — wrong: the caller has permission.
- `AlreadyExists` — wrong: the file is not a write conflict.
- `BackendUnavailable` — wrong: the backend is reachable and
  responsive.
- `RemoteStoreError` (generic) — loses the actionable signal.

No other backend in the project today emits 423 or an equivalent
condition, so the error type did not exist. With Graph, it does.

## Decision

Add `ResourceLocked` as a new concrete error type in the project's
error hierarchy, defined in `remote_store._errors` next to the other
canonical errors. It inherits directly from `RemoteStoreError`
(flat hierarchy per ERR-008).

### Semantics

- **Meaning.** The target resource exists and the caller is
  authorised, but the resource is currently locked by another
  session or process and the operation cannot proceed right now.
- **Attributes.** Standard `path` and `backend` attributes (ERR-001);
  no new required fields. An optional `lock_owner: str | None` field
  is reserved for future backends that can surface who holds the
  lock — Graph does not expose this today, so it remains `None`.
- **Retry guidance.** Not safely retried by the standard retry
  policy (RET-015 classifies `ResourceLocked` as terminal). Callers
  may retry at their own cadence.
  Documented alongside the error.

### Mapped conditions

- Graph `423 Locked` / `resourceLocked` → `ResourceLocked`.

Future backends that emit equivalent conditions (SharePoint REST
check-out, SMB lock conflicts, WebDAV `423`) map to the same type
when added.

### Spec 005 amendment

Spec `005-error-model.md` adds ERR-013 describing `ResourceLocked`.
The rationale for adding the new type lives in this ADR; the spec
records only the contract.

## Consequences

- **Honest error signal.** Graph callers can distinguish "locked
  right now" from "permission denied" or "service unavailable" and
  react appropriately (e.g. surface a user-visible "this file is
  open in Word, close it and retry" message).
- **Hierarchy growth.** The flat error hierarchy gains one member.
  `__all__` of `remote_store` gains `ResourceLocked`.
- **Retry-policy interaction.** The default retry policy does not
  treat `ResourceLocked` as transient. Documented in the policy
  reference.
- **Future-proofing.** The error exists for other backends without
  requiring a new ADR if they ever need it.
- **No supersession.** This ADR does not supersede or deprecate any
  prior ADR.

## References

- `sdd/specs/005-error-model.md` (ERR-013)
- `sdd/specs/044-graph-backend.md` (GR-028 through GR-033)
- RFC-0010: Microsoft Graph Backend (error mapping section)
