# PyArrow FileSystem Adapter

The `ext.arrow` module wraps any `Store` into a `pyarrow.fs.PyFileSystem`,
unlocking seamless interop with the PyArrow ecosystem: datasets, Pandas,
Polars, DuckDB, PyIceberg, and Delta Lake all accept `pyarrow.fs.FileSystem`
objects for I/O.

## Installation

```bash
pip install "remote-store[arrow]"
```

This installs `pyarrow >= 12.0.0` as an optional dependency. The adapter works
with any backend -- no extra configuration needed.

## Quick Start

```python
import pyarrow as pa
import pyarrow.parquet as pq

from remote_store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.arrow import pyarrow_fs

store = Store(backend=MemoryBackend())
fs = pyarrow_fs(store)

# Now use `fs` anywhere PyArrow accepts a filesystem:
table = pa.table({"col": [1, 2, 3]})
pq.write_table(table, "data.parquet", filesystem=fs)
result = pq.read_table("data.parquet", filesystem=fs)
```

## Parquet Round-Trip

```python
import pyarrow as pa
import pyarrow.parquet as pq
from remote_store.ext.arrow import pyarrow_fs

fs = pyarrow_fs(store)

# Write
table = pa.table({"id": [1, 2], "value": ["a", "b"]})
pq.write_table(table, "output.parquet", filesystem=fs)

# Read
result = pq.read_table("output.parquet", filesystem=fs)
```

## Pandas Integration

```python
import pandas as pd

df = pd.DataFrame({"x": [10, 20], "y": ["foo", "bar"]})
df.to_parquet("pandas.parquet", engine="pyarrow", filesystem=fs)

result = pd.read_parquet("pandas.parquet", engine="pyarrow", filesystem=fs)
```

## Dataset Discovery

PyArrow's dataset API discovers partitioned data automatically:

```python
import pyarrow.dataset as ds

dataset = ds.dataset("data/", filesystem=fs, format="parquet")
table = dataset.to_table()
```

## Configuration

The adapter accepts two tuning parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `materialization_threshold` | 64 MB | Max file size for full-file read in `open_input_file`. Files above this threshold stream via `PythonFile` (if seekable) or fall back to materialization with a warning. |
| `write_spill_threshold` | 64 MB | Max in-memory buffer size for writes. Exceeding this spills to a temporary file on disk. |

```python
fs = pyarrow_fs(
    store,
    materialization_threshold=128 * 1024 * 1024,  # 128 MB
    write_spill_threshold=32 * 1024 * 1024,        # 32 MB
)
```

## Tiered Read Strategy

`open_input_file` (used by Parquet readers) selects the best approach:

| Condition | Strategy | Memory | Notes |
|-----------|----------|--------|-------|
| File <= threshold | **Tier 2**: `read_bytes()` -> `BufferReader` | Full file | Zero GIL overhead |
| File > threshold, seekable stream | **Tier 3**: `read()` -> `PythonFile` | Streaming | GIL per read call |
| File > threshold, non-seekable | **Tier 2 fallback** (with warning) | Full file | S3/Azure HTTP streams |

A future Phase 2 will add **Tier 1** (backend-native fast path) for backends
like S3-PyArrow that expose a native `pyarrow.fs.FileSystem` via `unwrap()`.

## Limitations

- **No append support.** `open_append_stream` raises `NotImplementedError`.
  Most backends (S3, Azure) lack native append semantics.
- **Root deletion blocked.** `delete_dir("")` and `delete_root_dir_contents()`
  raise `NotImplementedError` as a safety guard.
- **Write buffering.** Writes are buffered until `close()` -- data is not
  visible in the Store during the write. This is inherent to the Store's
  single-shot `write()` API.
- **No Tier 1 fast path yet.** Phase 1 uses Tier 2/3 for all backends.
  Phase 2 will add Tier 1 for backends with native PyArrow support.

## Error Mapping

Store errors are translated to standard Python exceptions:

| Store error | Python exception |
|-------------|-----------------|
| `NotFound` | `FileNotFoundError` |
| `AlreadyExists` | `FileExistsError` |
| `PermissionDenied` | `PermissionError` |
| `InvalidPath` | `ValueError` |
| `CapabilityNotSupported` | `NotImplementedError` |
| Other `RemoteStoreError` | `OSError` |

No `RemoteStoreError` leaks to PyArrow callers -- all exceptions are mapped
with `from` chaining for debuggability.
