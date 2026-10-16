# MemoryBackend

API reference for `MemoryBackend`: stores files in an in-process tree. No filesystem access, no network. Ideal for testing and prototyping.

`MemoryBackend` is a [`DriverBackend`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.DriverBackend) built over `MemoryDriver`: the driver reads and changes the tree, and the contract kernel validates keys, guards the root and types every refusal. `MemoryDriver` is public as a complete, dependency-free example of a driver.

## MemoryBackend

```
MemoryBackend()
```

In-memory backend: a tree-indexed store on the contract kernel.

Zero dependencies, no filesystem access, no network. Designed as a drop-in backend for unit testing, interactive exploration, and documentation examples.

All capabilities except `GLOB` and `LAZY_READ` are supported. Every primitive runs under the backend's one lock, so `write`, `write_atomic`, `move` and `copy` are atomic with respect to concurrent callers in the same process (`ATOMIC_MOVE` is advertised). Reads materialise the value: a stream wraps a copy of the stored bytes.

## MemoryDriver

```
MemoryDriver(
    capabilities: CapabilitySet = _ALL_CAPABILITIES,
)
```

The sync Memory driver: the tree's primitives, each under one `threading.Lock`.

The contract kernel validates and normalises every key before it reaches a primitive, decides the root and types every refusal; the driver only reads and changes the tree. It declares no `probe`, inheriting the driver protocol's no-op: an in-memory store is always healthy.

Optional protocols: `open_write` (a buffer in memory, so `open_atomic` never spills to disk), an atomic `move`, `copy`, `delete_tree`, `remove_folder` and `folder_stats`.

*capabilities* narrows what is declared; construction refuses a set the protocols cannot back.

### counts

```
counts: tuple[int, int]
```

The number of files and of folders the tree holds.

Read without the lock, which is not reentrant: `repr` reads these, and a debugger may call it from a thread paused inside a locked step. So under concurrent writers a read may show a step in progress (the two counts out of step with each other); it is a display figure, not a snapshot.

### get

```
get(key: str) -> BinaryIO
```

A stream over a copy of the stored bytes: the value materialises in memory.

### close

```
close() -> None
```

Nothing to release; the store stays usable.

### open_write

```
open_write(
    key: str,
    *,
    overwrite: bool,
    metadata: Mapping[str, str] | None,
) -> _MemoryWriteHandle
```

A buffer in memory that `commit` stores at *key* in one locked step.

Refuses on open what the commit would refuse now, so `open_atomic` fails before its body runs; the commit checks again under the lock.

## See also

- [Memory Backend Guide](https://docs.remotestore.dev/stable/guides/backends/memory/index.md) — usage patterns, configuration, and examples
- [Memory Backend example](https://docs.remotestore.dev/stable/tutorial/examples/memory-backend/index.md) — in-memory backend in action
- [Drivers](https://docs.remotestore.dev/stable/reference/api/drivers/index.md) — the protocols `MemoryDriver` implements
- [Build Your Own Backend](https://docs.remotestore.dev/stable/guides/custom-backend-guide/index.md) — writing a driver of your own
