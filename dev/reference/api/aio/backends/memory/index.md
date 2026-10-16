# AsyncMemoryBackend

In-memory async backend using a tree-indexed data structure. Zero dependencies, no filesystem access, no network. Designed as a drop-in async backend for unit testing, interactive exploration, and documentation examples. Supports all capabilities except `GLOB`.

`AsyncMemoryBackend` is an [`AsyncDriverBackend`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.AsyncDriverBackend) built over `AsyncMemoryDriver`, the async twin of `MemoryDriver`: the same tree and primitives, under an `asyncio.Lock`.

## AsyncMemoryBackend

```
AsyncMemoryBackend()
```

In-memory async backend: a tree-indexed store on the contract kernel.

Zero dependencies, no filesystem access, no network. Designed as a drop-in async backend for unit testing, interactive exploration, and documentation examples.

Supports all capabilities except `GLOB`.

Note

`LAZY_READ` is included here but absent from `MemoryBackend` (the sync mirror). Both copy the whole stored value; the async read is deferred to its first iteration and yields that copy as one chunk. The `mirrors` graph edge between the two does not imply capability parity.

## AsyncMemoryDriver

```
AsyncMemoryDriver(
    capabilities: CapabilitySet = _ALL_CAPABILITIES,
)
```

The async Memory driver: the shared tree's primitives, each under one `asyncio.Lock`.

The same tree and the same primitives as `MemoryDriver`; the lock, the stream shape, the `name` and the default capabilities (`LAZY_READ` here) differ. It declares no `probe`, inheriting the driver protocol's no-op: an in-memory store is always healthy.

*capabilities* narrows what is declared; construction refuses a set the protocols cannot back.

### counts

```
counts: tuple[int, int]
```

The number of files and of folders the tree holds.

Read without the lock, as `repr` needs. A coroutine on the loop never sees a step in progress, since no locked primitive awaits; a debugger paused inside one, or another thread (`AsyncBackendSyncAdapter` runs the loop on its own), may, so it is a display figure, not a snapshot.

### get

```
get(key: str) -> AsyncIterator[bytes]
```

The stored bytes as one chunk, copied under the lock.

### aclose

```
aclose() -> None
```

Nothing to release; the store stays usable.

### open_write

```
open_write(
    key: str,
    *,
    overwrite: bool,
    metadata: Mapping[str, str] | None,
) -> _AsyncMemoryWriteHandle
```

A buffer in memory that `commit` stores at *key* in one locked step.

Refuses on open what the commit would refuse now; the commit checks again under the lock.

## See also

- [MemoryBackend](https://docs.remotestore.dev/stable/reference/api/backends/memory/index.md) — synchronous counterpart
- [Async Store Guide](https://docs.remotestore.dev/stable/guides/async/index.md) — usage patterns
- [Drivers](https://docs.remotestore.dev/stable/reference/api/drivers/index.md) — the protocols `AsyncMemoryDriver` implements
