# ADR-0024: `ResourceLocked` Error Type

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

Revised 2026-06-03 in place rather than superseded — by
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

Add `ResourceLocked` as a new concrete error type. The decisions:

- **A new type, not a reuse.** None of the existing errors fit HTTP
  `423`: the caller is authorised (not `PermissionDenied`), it is not a
  write conflict (not `AlreadyExists`), the backend is reachable (not
  `BackendUnavailable`), and generic `RemoteStoreError` loses the
  actionable "locked now, may clear" signal.
- **Flat under `RemoteStoreError`.** One level deep, no intermediate
  category (ERR-008).
- **`path` + `backend` only; no `lock_owner`.** Graph does not surface
  the lock holder and no other backend emits this today, so a
  speculative field is dropped (no-speculative-API rule). **Reverse
  (widen the class)** only when a backend genuinely surfaces the holder,
  via a covering spec amendment — ERR-013 points back here for exactly
  this reasoning.
- **Terminal; caller-driven retry.** Not retried by the default policy
  (RET-015); callers choose their own cadence.
- **Reusable across backends.** Future equivalents — SharePoint
  check-out, SMB lock conflicts, WebDAV `423` — map to the same type;
  that reuse is why this is a canonical error, not a Graph-local one.
  Graph's `423 resourceLocked` is the only mapped source today (GR-045
  owns the mapping).

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
- **Ships as a coupled bundle.** The runtime class, the spec 005
  ERR-013 entry, the Dafny `Error.ResourceLocked(path, backend)`
  variant, and its `_raise_if_err` test dispatch land together, never
  the variant alone. Delivered under ID-127 (GR-CONTRACT step) — see
  `sdd/BACKLOG.md`; the detailed coupling mechanics live in spec 005,
  `sdd/formal/BackendContract.dfy`, and BACKLOG ID-127.
- **No supersession.** This ADR does not supersede or deprecate any
  prior ADR.

## References

- `sdd/specs/005-error-model.md` (ERR-008 flat hierarchy, ERR-013)
- `sdd/specs/025-retry-policy.md` (RET-015)
- `sdd/specs/044-graph-backend.md` (GR-045)
- RFC-0010: Microsoft Graph Backend (error mapping section)
