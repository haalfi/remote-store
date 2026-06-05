# ADR-0024: `ResourceLocked` Error Type

## Status

Accepted. Revised 2026-06-03 in place rather than superseded — by
the time the rewrite landed the ADR was unimplemented against, so
there was no caller state to preserve and a superseding ADR would
have added a level of indirection without aiding any reader. The
rewrite is material (it dropped the speculative `lock_owner`
attribute reservation and triggered the spec 005 ERR-013
co-amendment); a future audit reading this file should note that the
supersession discipline was traded for in-place clarity, scoped to
the four Graph ADRs (0021..0024).

## Context

Microsoft Graph returns HTTP `423 Locked` with an error code of
`resourceLocked` when an item is held by another session — typical
causes are an open co-authoring session in the Office clients, a
checked-out document in SharePoint, or an in-progress upload session
on the same item. The condition is:

- **Not a permissions problem.** The caller is authenticated and
  authorised; the resource itself is temporarily unavailable.
- **Not a throttling problem.** There is no `Retry-After` promise,
  and the condition may last seconds, minutes, or indefinitely.
- **Not "resource missing".** The item exists.
- **Retryable with caution.** A short bounded retry may succeed, but
  blind exponential retry could wait forever.

None of the existing `remote_store` errors capture this accurately:

- `PermissionDenied` — wrong: the caller has permission.
- `AlreadyExists` — wrong: the file is not a write conflict.
- `BackendUnavailable` — wrong: the backend is reachable and
  responsive.
- `RemoteStoreError` (generic) — loses the actionable signal.

No other backend in the project today emits `423` or an equivalent
condition, so the error type does not exist yet. With Graph, it does.

## Decision

Add `ResourceLocked` as a new concrete error type in
`src/remote_store/_errors.py`, alongside the other canonical errors.
It inherits directly from `RemoteStoreError` per the flat hierarchy
rule (ERR-008): one level deep, no intermediate categories.

### Semantics

- **Meaning.** The target resource exists and the caller is
  authorised, but the resource is currently locked by another
  session or process and the operation cannot proceed right now.
- **Attributes.** Standard `path` and `backend` per the existing
  error constructor pattern (ERR-001). No new fields. Earlier
  drafts reserved an optional `lock_owner: str | None` — dropped
  on reality check: Graph does not surface the lock holder, no
  other backend emits this condition today, and adding a field "in
  case" violates the project's no-speculative-API rule. A future
  backend that genuinely surfaces the holder widens this class via
  a covering spec amendment. (Spec 005 has no structured
  `RemoteStoreError.context` surface today; routing extras through
  `.context["lock_owner"]` is not available as a fallback and is
  not part of this decision.)
- **Retry guidance.** Not safely retried by the default retry policy
  — RET-015 classifies `ResourceLocked` as terminal. Callers may
  retry at their own cadence.

### Mapped conditions

- Graph `423 Locked` / `resourceLocked` → `ResourceLocked`.

Future backends that emit equivalent conditions (SharePoint REST
check-out, SMB lock conflicts, WebDAV `423`) map to the same type
when added.

### Bundled implementation

`ResourceLocked` is unreachable from any backend other than Graph in
v1, so the runtime class, the spec 005 entry (ERR-013), the Dafny
`Error.ResourceLocked(path: string, backend: string)` variant
(matching the `(path: string, backend: string)` shape every other
non-`BackendUnavailable` variant uses in
`sdd/formal/BackendContract.dfy`, so `_raise_if_err` can dispatch it
through the existing `err.path` / `err.backend` reader), and its
dispatch in `tests/backends/dafny/_helpers.py::_raise_if_err` ship as
one coupled bundle, never the variant alone. Spec 005 records ERR-013
at RFC acceptance.

**Delivery under ID-127.** This ADR was written assuming a single Graph
backend PR, in which the bundle would land "in the same PR as the Graph
sub-package (`aio/backends/_graph/`)." ID-127's phased roadmap instead
lands the bundle one step earlier — in the GR-CONTRACT step, ahead of the
sub-package, which follows in GR-CORE. The decision is unchanged and its
intention still honoured: the variant never ships orphaned (its only
raiser, the Graph `423` mapper, lands in the same ID-127 delivery) and the
bundle stays coupled. See ID-127 in `sdd/BACKLOG.md` for the
bundled-sub-task note.

## Consequences

- **Honest error signal.** Graph callers distinguish "locked right
  now" from "permission denied" or "service unavailable" and react
  appropriately (e.g. surface a user-visible "this file is open in
  Word, close it and retry" message).
- **Hierarchy growth, one member.** ERR-008's flat shape is
  preserved. `remote_store.__all__` gains `ResourceLocked`.
- **Retry-policy interaction.** The default retry policy does not
  treat `ResourceLocked` as transient. Documented in spec 025
  (RET-015).
- **Future-proofing without speculation.** The error exists for any
  future backend that genuinely needs it; the class stays minimal
  until a real second consumer arrives.
- **No supersession.** This ADR does not supersede or deprecate any
  prior ADR.

## References

- `sdd/specs/005-error-model.md` (ERR-008 flat hierarchy, ERR-013)
- `sdd/specs/025-retry-policy.md` (RET-015)
- `sdd/specs/044-graph-backend.md` (GR-045)
- RFC-0010: Microsoft Graph Backend (error mapping section)
