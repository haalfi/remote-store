# ext.arrow

## arrow

PyArrow FileSystem adapter — wraps any Store into a [pyarrow.fs.PyFileSystem](https://arrow.apache.org/docs/python/generated/pyarrow.fs.PyFileSystem.html).

Install with `pip install "remote-store[arrow]"`.

Example

```
from remote_store.ext.arrow import pyarrow_fs

fs = pyarrow_fs(store)
pq.write_table(table, "data.parquet", filesystem=fs)
```

### StoreFileSystemHandler

```
StoreFileSystemHandler(
    store: Store,
    materialization_threshold: int = 64 * 1024 * 1024,
    write_spill_threshold: int = 64 * 1024 * 1024,
)
```

Bases: `FileSystemHandler`

`pyarrow.fs.FileSystemHandler` backed by a `Store`.

Parameters:

- **`store`** (`Store`) – The Store to expose as a PyArrow filesystem.
- **`materialization_threshold`** (`int`, default: `64 * 1024 * 1024` ) – Max file size (bytes) for Tier 2 full-file materialization in open_input_file. Default 64 MB.
- **`write_spill_threshold`** (`int`, default: `64 * 1024 * 1024` ) – Max in-memory buffer size (bytes) for \_StoreSink before spilling to disk. Default 64 MB.

**Thread safety:** The handler itself holds no shared mutable state. PyArrow's C++ layer may call handler methods from background threads (with the GIL acquired). Thread safety therefore depends on the backend: `MemoryBackend` uses a lock (safe), `LocalBackend` relies on OS file semantics (safe), cloud backends use thread-safe HTTP clients (safe). If using a custom backend, ensure its methods are safe under concurrent calls.

### pyarrow_fs

```
pyarrow_fs(
    store: Store,
    *,
    materialization_threshold: int = 64 * 1024 * 1024,
    write_spill_threshold: int = 64 * 1024 * 1024,
) -> PyFileSystem
```

Create a `pyarrow.fs.PyFileSystem` backed by *store*.

Parameters:

- **`store`** (`Store`) – The Store to expose.
- **`materialization_threshold`** (`int`, default: `64 * 1024 * 1024` ) – See StoreFileSystemHandler.
- **`write_spill_threshold`** (`int`, default: `64 * 1024 * 1024` ) – See StoreFileSystemHandler.

## See also

- [PyArrow Adapter](https://docs.remotestore.dev/stable/guides/pyarrow-adapter/index.md) — guide to using Store as a PyArrow filesystem
- [PyArrow Adapter example](https://docs.remotestore.dev/stable/tutorial/examples/pyarrow-adapter/index.md) — PyArrow adapter in action
