# ADR-0029: Offload Graph Transfer Spool I/O off the Event Loop

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0025 |

Amends the "Worker-thread starvation under high concurrency" risk of
[ADR-0025](0025-async-to-sync-backend-adapter.md) § Risks (that bullet only;
the rest of ADR-0025 stays in effect).

## Context

ADR-0025 introduced `AsyncBackendSyncAdapter` and, in its § Risks, flagged that
all sync callers share one event loop and that a CPU-bound backend could stall
sibling calls. It named a concrete example — "`_graph_transfer`'s chunk
hashing" — and deferred any mitigation "to backend authors via
`asyncio.to_thread` for hot CPU paths."

That example is wrong on inspection: the Graph transfer path computes no hash.
There is no `hashlib` use in `aio/backends/_graph/transfer.py`; the only
"hashes" the backend touches are the server-provided `file.hashes` metadata in
`items.py`, which it copies, never computes.

The real loop-stall source in the Graph backend is **blocking spool file I/O**,
not hashing. Two paths drain or replay a `SpooledTemporaryFile` that rolls over
from memory to disk once it exceeds its threshold:

- the **read** path's SharePoint range-fallback (`_spooled_window`) re-reads the
  full entity into a spool and serves the requested window from it
  (`write` / `seek` / `read`); and
- the **write** path's unknown-length upload (`spool_content` +
  `_upload_chunks`) drains the iterator into a spool and replays it in chunks
  (`write` / `tell` / `seek`, then `seek` + `read` of up to one
  `upload_chunk_size` — 10 MiB by default).

Once spilled to disk, each of those calls is synchronous file I/O. Run directly
on the event-loop thread, a large disk-spilled transfer head-of-line-blocks
every sibling coroutine for the duration of the disk op — the exact
"sibling-call stall" ADR-0025 anticipated, reached through I/O rather than CPU.

## Decision

Dispatch the Graph transfer's blocking spool file I/O off the event loop via
`asyncio.to_thread`, on both the read-path range fallback and the write-path
unknown-length upload. The spool objects are accessed sequentially under `await`,
with nothing else holding the reader concurrently, so single-threaded offload is
safe. *Reverse if* a spool ever gains a concurrent reader: the sequential-access
invariant that makes single-threaded offload safe would no longer hold.

The exact spool methods and per-operation thread hops are code-level and live in
`transfer.py`, with the spool contracts in [spec 044](../specs/044-graph-backend.md)
§ GR-015 (range-fallback spool) and § GR-019 (upload-session spool).

## Consequences

- **No event-loop stall on disk-spilled Graph transfers.** A large fallback read
  or unknown-length upload no longer blocks sibling coroutines while the spool
  spills to or replays from disk.
- **One thread hop per spool op.** Small, in-memory spools (below the rollover
  threshold) pay a cheap hop they did not before; the trade is deliberate — the
  cost is bounded and the win is loop liveness under the disk-spill case the
  offload exists for.
- **ADR-0025's chunk-hashing example is retired.** The risk it described is real
  but I/O-bound, and is now mitigated here rather than deferred.
- **Connection-pool capacity is the orthogonal half of BK-290** and is addressed
  by documentation (the `client_options={"limits": httpx.Limits(...)}` knob), not
  this ADR.

## References

- Supersedes: ADR-0025 § Risks, "Worker-thread starvation under high
  concurrency" bullet only
- Backlog: BK-290
- Specs: GR-015 (range-fallback spool), GR-019 (upload-session spool)
