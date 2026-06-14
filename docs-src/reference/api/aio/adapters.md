# Adapters & types

Bridges between the synchronous and asynchronous backend worlds, plus the
async content type alias. The adapters let a sync backend run under
[`AsyncStore`](store.md) and an async backend run under the synchronous
[`Store`](../store.md). See [Async-sync bridges](../../../guides/async-sync-bridges.md)
for when to reach for each.

## SyncBackendAdapter

Wraps any synchronous `Backend` as an `AsyncBackend` by dispatching each
blocking call to the default executor via `asyncio.to_thread`. `AsyncStore`
auto-wraps sync backends on construction; explicit construction is only
required when you want to introspect the adapter.

::: remote_store.aio.SyncBackendAdapter
    options:
      show_bases: false

## AsyncBackendSyncAdapter

Wraps any `AsyncBackend` as a synchronous `Backend` by running a private
event loop on a dedicated daemon thread for the adapter's lifetime. See
[Async-sync bridges](../../../guides/async-sync-bridges.md) for the full
behaviour contract and the [async-to-sync adapter decision record](https://github.com/haalfi/remote-store/blob/master/sdd/adrs/0025-async-to-sync-backend-adapter.md)
for the design rationale.

::: remote_store.AsyncBackendSyncAdapter
    options:
      show_bases: false

## AsyncWritableContent

::: remote_store.aio.AsyncWritableContent

## See also

- [AsyncStore](store.md) — the async Store the adapters plug into
- [AsyncBackend](backend.md) — the async backend protocol
- [Async-sync bridges](../../../guides/async-sync-bridges.md) — choosing a direction
