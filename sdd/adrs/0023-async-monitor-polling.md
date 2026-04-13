# ADR-0023: Async Monitor-URL Polling as a Shared Backend-Local Module

## Status

Accepted

## Context

Several cloud APIs answer long-running operations with HTTP `202
Accepted` plus a `Location` header pointing to a monitor URL that the
client polls until the operation finishes. Graph uses this pattern for
item copy and may-be-async move; Azure Blob copy uses a similar
`x-ms-copy-status` polling model; S3 multipart-copy completion has a
related shape.

The Graph backend (ID-127, RFC-0010) is the first to need a full
monitor-URL poller in this project. Writing it inside `_graph.py`
would duplicate the logic the moment a second backend needs it (Azure
cross-account copy is already a known candidate). At the same time,
this is not a Store API concept — callers of `Store.copy()` see a
sync-shaped return; the async polling is entirely internal to the
backend.

## Decision

Hoist the polling logic into `src/remote_store/backends/_async_monitor.py`
as a shared backend-local helper. It is part of the `backends` package
(private API) and is consumed only by backend implementations.

### Contract

The module exposes an async poller with these parameters:

- **`monitor_url`** — the URL returned in the `Location` header.
- **`client`** — an `httpx.AsyncClient` (or compatible) the caller owns.
- **`initial_interval`** — polling interval floor. Default 1 s.
- **`max_interval`** — polling interval ceiling. Default 30 s.
- **`backoff_factor`** — multiplicative increase applied to the
  interval between successive polls that return `running`. Default 2.
- **`timeout`** — overall wall-clock limit. Raises a timeout error
  when exceeded.
- **`status_parser`** — callable that inspects the poll response and
  returns one of `pending`, `succeeded`, or `failed` along with an
  optional error message. Backends supply this because different APIs
  encode operation status differently.

The poller honours `Retry-After` headers from the monitor endpoint
(overriding the computed interval when larger) and treats transient
`5xx` responses during polling as pending, not failed.

Cancellation is cooperative: the poller is a standard `async def`
coroutine and respects `asyncio.CancelledError`.

### Why not a Store capability

A new capability (e.g. `ASYNC_COPY`) would leak an implementation
detail into the public API. Callers of `Store.copy()` already treat
the operation as synchronous from their point of view — the backend's
job is to present that synchronous result, regardless of how it gets
there. Declaring a capability would invite callers to branch on
"is this copy going to be asynchronous?", which is the wrong
question.

### Why backend-local, not a utility in `ext/`

Extensions use only the public Store/Backend API (ADR-0008). The
poller operates on raw HTTP, takes an `httpx.AsyncClient`, and serves
only backend implementers. Placing it in `ext/` would misrepresent
its audience and scope.

## Consequences

- **Reuse across backends.** Graph consumes the poller on day one.
  Azure cross-account copy (a future path) and any future Graph
  operation that returns `202` (e.g. large-item rename propagation)
  share the same implementation.
- **No public API surface growth.** The poller is private and
  un-exported. Changing its signature affects only backend code in
  the `backends` package.
- **Store API remains sync-from-the-caller's-view.** Async posture
  is owned by the backend (ADR-0012). The poller is an
  implementation technique, not a contract.
- **Testing shape.** The poller is tested independently with `respx`
  fixtures; backends test their integration with it via the same
  fixtures, without re-testing timing logic.
- **No new capability.** `CapabilitySet` is unchanged. Callers do
  not observe whether an operation polled internally.

## References

- RFC-0010: Microsoft Graph Backend (async monitor section)
- `sdd/specs/044-graph-backend.md` (GR-025 through GR-027)
- ADR-0012: Async Store / Backend API
- ADR-0008: Extension Architecture
