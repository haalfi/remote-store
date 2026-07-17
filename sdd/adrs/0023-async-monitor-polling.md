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
the Graph sub-package, alongside `backend.py` / `http.py` /
`transfer.py` / `auth.py`), or inline in `backend.py` if it stays
under ~100 lines. The Graph backend lives under `aio/backends/`
because it is async-native (matching `aio/backends/_azure.py`); the
poller follows. It is part of the Graph sub-package, not a shared
facility. No public API surface and no Store-level capability is
introduced.

If and when a second backend genuinely needs the same shape — measured
in a follow-up implementation, not predicted here — a hoisting ADR
supersedes this one. Until then, YAGNI: one consumer, one location.

### Contract

The poller exposes an async function with these parameters:

- **`monitor_url`** — the URL returned in the `Location` header.
- **`client`** — the backend's `httpx.AsyncClient`.
- **`status_parser`** — callable that inspects a poll response and
  returns one of `pending`, `succeeded`, or `failed` along with an
  optional error payload. Graph supplies its own
  `parse_graph_monitor_response`; the contract stays parser-driven
  in case a second consumer reuses just the loop (without making the
  poller itself a generic helper today).
- **`initial_interval`** — polling interval floor. Default 1 s.
- **`max_interval`** — polling interval ceiling. Default 30 s.
- **`backoff_factor`** — multiplicative increase applied to the
  interval between successive polls that return `pending`. Default 2.
- **`timeout`** — overall wall-clock limit. On expiry, raises
  `BackendUnavailable` with the context fields specified by GR-026.

The poller honours `Retry-After` headers from the monitor endpoint
(overriding the computed interval when larger), treats transient
`5xx` responses during polling as `pending`, and propagates
`asyncio.CancelledError`.

### Why not a Store capability

A new capability (e.g. `ASYNC_COPY`) would leak an implementation
detail into the public API. Callers of `Store.copy()` already treat
the operation as synchronous from their point of view — the backend's
job is to present that synchronous result, regardless of how it gets
there. Declaring a capability would invite callers to branch on "is
this copy going to be asynchronous?", which is the wrong question.

### Why not in `ext/`

Extensions use only the public Store/Backend API (ADR-0008). The
poller operates on raw HTTP, takes an `httpx.AsyncClient`, and serves
only the backend implementer. Placing it in `ext/` would misrepresent
its audience and scope.

### What changes if a second consumer arrives

The migration path from backend-local to shared is mechanical: lift
the function to a shared location (`aio/backends/_async_monitor.py`
if both consumers are async-native; `backends/_async_monitor.py` if a
sync consumer also wants it), add a re-export from the original
`aio/backends/_graph/monitor.py` for a release, supersede this ADR.
The `status_parser` parameter is already shaped to support a second
consumer's response format; no API redesign is required at hoist
time. The current decision optimises for not paying that cost until
there is a real demand for it.

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
- **Future hoist is cheap.** Parser-driven contract means lifting
  the function does not require redesigning it.

## References

- RFC-0010: Microsoft Graph Backend (async monitor section)
- `sdd/specs/044-graph-backend.md` (GR-025 through GR-027)
- ADR-0012: Async Store / Backend API
- ADR-0008: Extension Architecture
