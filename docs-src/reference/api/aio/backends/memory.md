# AsyncMemoryBackend

In-memory async backend using a tree-indexed data structure. Zero
dependencies, no filesystem access, no network. Designed as a drop-in
async backend for unit testing, interactive exploration, and documentation
examples. Supports all capabilities except `GLOB`.

::: remote_store.aio.AsyncMemoryBackend
    options:
      show_bases: false

## See also

- [MemoryBackend](../../backends/memory.md) — synchronous counterpart
- [Async Store Guide](../../../../guides/async.md) — usage patterns
