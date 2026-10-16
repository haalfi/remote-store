# AsyncMemoryBackend

In-memory async backend using a tree-indexed data structure. Zero
dependencies, no filesystem access, no network. Designed as a drop-in
async backend for unit testing, interactive exploration, and documentation
examples. Supports all capabilities except `GLOB`.

`AsyncMemoryBackend` is an [`AsyncDriverBackend`](../../drivers.md#remote_store.drivers.AsyncDriverBackend)
built over `AsyncMemoryDriver`, the async twin of `MemoryDriver`: the same tree
and primitives, under an `asyncio.Lock`.

::: remote_store.aio.AsyncMemoryBackend
    options:
      show_bases: false

::: remote_store.aio.AsyncMemoryDriver
    options:
      show_bases: false

## See also

- [MemoryBackend](../../backends/memory.md) — synchronous counterpart
- [Async Store Guide](../../../../guides/async.md) — usage patterns
- [Drivers](../../drivers.md) — the protocols `AsyncMemoryDriver` implements
