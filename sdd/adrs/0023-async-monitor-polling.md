# ADR-0023: Async Monitor-URL Polling — Backend-Local in `_graph`

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
rewrite is material (it dropped the shared-helper design); a future
audit reading this file should note that the supersession discipline
was traded for in-place clarity, scoped to the four Graph ADRs
(0021..0024).

## Context

Microsoft Graph answers long-running operations with `202 Accepted`
plus a `Location` header pointing to a monitor URL the client polls
until the operation finishes. The Graph backend (ID-127, RFC-0010)
needs this for `copy` (always async) and `move` (may go async on
large or cross-folder items).

An earlier draft of this ADR proposed hoisting the polling logic into
a shared `src/remote_store/backends/_async_monitor.py` on the premise
that Azure cross-account copy and similar `202`-monitor patterns
would reuse it. Reality check before implementation: no second
consumer exists today. `AsyncAzureBackend.copy` ships in v0.27.0 by
calling `start_copy_from_url` and returning — same-account Azure
copies complete server-side without polling, and cross-account copy
is not implemented. S3 multipart-copy completion uses a different
shape (`UploadId` + `complete-multipart-upload`, not a monitor URL).
"Shared helper" was speculative reuse for a single consumer.

## Decision

Ship the polling logic **backend-local** in
`src/remote_store/aio/backends/_graph/monitor.py` (a module inside
the Graph sub-package, or inline in `backend.py` if it stays small).
The Graph backend lives under `aio/backends/` because it is
async-native (matching `aio/backends/_azure.py`); the poller follows.
It is part of the Graph sub-package, not a shared facility, and
introduces no public API surface and no Store-level capability.

The poller is **parser-driven**: a `status_parser` callable maps each
poll response to `pending` / `succeeded` / `failed`, so the loop is
already shaped for a second consumer's response format without being
made a generic helper today. The cadence and timeout contract
(intervals, backoff, `copy_timeout`, `Retry-After`, `5xx`-as-pending,
cancellation) is owned by GR-026 and not restated here.

**YAGNI: one consumer, one location.** No second `202`-monitor consumer
exists today (Context has the reality-check). Reverse this decision only
when a second backend genuinely needs the same shape, measured in a
follow-up rather than predicted here; a hoisting ADR then supersedes
this one.

**Why not a Store capability.** A capability such as `ASYNC_COPY`
would leak an implementation detail into the public API and invite
callers to branch on "is this copy asynchronous?", which is the wrong
question. `Store.copy()` is synchronous from the caller's view
(ADR-0012); the backend presents that result regardless of how it
gets there.

**Why not in `ext/`.** Extensions use only the public Store/Backend
API (ADR-0008). The poller operates on raw HTTP, takes an
`httpx.AsyncClient`, and serves only the backend implementer; placing
it in `ext/` would misrepresent its audience.

## Consequences

- **One file, one consumer.** No premature abstraction; the polling
  code lives next to the only thing that calls it, and reviewers
  reading `aio/backends/_graph/` find the loop where they expect it
  (`monitor.py` next to `backend.py`).
- **No public API surface growth.** The poller is private and
  un-exported. Changing its signature affects only Graph backend
  code.
- **Store API remains sync-from-the-caller's-view.** Async posture
  is owned by the backend (ADR-0012). The poller is an
  implementation technique, not a contract.
- **Testing shape.** The poller is tested with `respx` fixtures as
  part of the Graph backend test surface.
- **No new capability.** `CapabilitySet` is unchanged. Callers do
  not observe whether an operation polled internally.
- **Future hoist is cheap.** The migration is mechanical: lift the
  function to a shared location (`aio/backends/_async_monitor.py`, or
  `backends/_async_monitor.py` if a sync consumer also wants it), add
  a re-export from `_graph/monitor.py` for one release, and supersede
  this ADR. The parser-driven contract means no redesign at hoist
  time.

## References

- RFC-0010: Microsoft Graph Backend (async monitor section)
- `sdd/specs/044-graph-backend.md` (GR-025 through GR-027)
- ADR-0012: Async Store / Backend API
- ADR-0008: Extension Architecture
