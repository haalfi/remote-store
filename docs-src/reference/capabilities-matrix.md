# Capabilities Matrix

Every backend declares which operations it supports via the
[Capability](api/capabilities.md#remote_store.Capability) enum.
Use [CapabilitySet](api/capabilities.md#remote_store.CapabilitySet) to query
at runtime before calling an operation.

## Backend x Capability

| Capability | [Local](../guides/backends/local.md) | [Memory](../guides/backends/memory.md) | [HTTP](../guides/backends/http.md) | [S3](../guides/backends/s3.md) | [S3-PyArrow](../guides/backends/s3-pyarrow.md) | [SFTP](../guides/backends/sftp.md) | [Azure](../guides/backends/azure.md) | [Graph](../guides/backends/graph.md)¹ | [SQLBlob](../guides/backends/sql-blob.md) | [SQLQuery](../guides/backends/sql-query.md) |
|------------|:-----:|:------:|:----:|:--:|:----------:|:----:|:-----:|:-----:|:-------:|:---------:|
| READ           | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| WRITE          | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | Yes | —   |
| DELETE         | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | Yes | —   |
| LIST           | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| GLOB           | Yes | —   | —   | Yes | Yes | —   | Yes | —   | Yes | Yes |
| MOVE           | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | Yes | —   |
| COPY           | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | Yes | —   |
| ATOMIC_WRITE   | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | Yes | —   |
| ATOMIC_MOVE    | Yes | Yes | —   | —   | —   | —   | —   | —   | Yes | —   |
| METADATA       | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| SEEKABLE_READ  | Yes | Yes | —   | Yes | Yes | Yes | —   | —   | Yes | Yes |
| LAZY_READ      | Yes | —   | Yes | Yes | Yes | Yes | Yes | Yes | —   | —   |
| WRITE_RESULT_NATIVE | Yes | Yes | — | Yes | Yes | Yes | Yes | Yes | Yes² | — |
| USER_METADATA  | —   | Yes | —   | Yes | —   | —   | Yes | —   | Yes² | —   |

¹ Graph is an **async-only** backend — construct it via
`AsyncStore(backend=GraphBackend(...))`; there is no sync `Store` wrapper or
config `type=` string. The column lists its declared capabilities.

² `WRITE_RESULT_NATIVE` and `USER_METADATA` are declared by `SQLBlobBackend` only when the backing table includes a `user_metadata` column (see the SQLBlob guide for schema requirements). Legacy tables without this column do not declare either capability.

**Near-full:** Local lacks `USER_METADATA` — passing non-empty `metadata=` raises `CapabilityNotSupported`. S3 and S3-PyArrow lack `ATOMIC_MOVE` (copy-then-delete
semantics). SQLBlob lacks `LAZY_READ` — the entire blob is loaded into memory
before a stream is returned. Writes also materialize the full stream before
the SQL INSERT/UPDATE because BLOB columns require complete data.

**Partial support:** Memory lacks native `GLOB` and `LAZY_READ` (all
data lives in process memory; use the portable fallback
`ext.glob.glob_files()` — see the [Glob Pattern Matching](../guides/glob-pattern-matching.md) guide).
SFTP lacks both `GLOB` and `ATOMIC_MOVE`.
Azure lacks `SEEKABLE_READ` and `ATOMIC_MOVE` (forward-only chunk iterator,
copy-then-delete move). Missing `SEEKABLE_READ` means only that `read()` is
forward-only, not that random access is expensive: on the sync backend
`read_seekable()` uses a native HTTP-Range reader (one ranged download per
read, no temp-file spill) — see the
[Azure guide](../guides/backends/azure.md#streaming-and-seekable-reads).
Graph lacks `GLOB`, `SEEKABLE_READ`, `ATOMIC_MOVE`, and `USER_METADATA`
(Microsoft Graph has no server-side glob, forward-only download streams,
a native server-side move that may complete asynchronously so atomicity is
not guaranteed, and no OneDrive/SharePoint user-metadata surface).

**Read-only:** SQLQuery supports `READ`, `LIST`, `METADATA`, `GLOB`,
and `SEEKABLE_READ` — no write operations.

**Minimal:** HTTP supports `READ`, `METADATA`, and `LAZY_READ` (read-only backend).

## Querying capabilities at runtime

```python
from remote_store import Capability

if store.supports(Capability.GLOB):
    results = store.glob("**/*.csv")
else:
    from remote_store import glob_files
    results = glob_files(store, "**/*.csv")

# Seekable read — works on any backend. Native/lazy where the backend
# optimizes it (S3, sync Azure's HTTP-Range reader); spooled to a temp
# file otherwise (HTTP, an async backend bridged to sync). SEEKABLE_READ
# reports only whether read() itself is seekable, not this cost.
from remote_store import seekable_read

with seekable_read(store, "report.csv") as f:
    header = f.read(128)
    f.seek(0)  # guaranteed seekable

# Atomic move — quality flag, not a method gate.
# move() is always callable (when MOVE is declared), but only atomic
# on backends that declare ATOMIC_MOVE.
if store.supports(Capability.ATOMIC_MOVE):
    # Atomic: readers see either the old or the new path, never both.
    store.move("staging/data.parquet", "prod/data.parquet")
else:
    # Non-atomic backend: copy-then-delete. A failure between the two
    # steps may leave both paths present — handle errors explicitly.
    store.copy("staging/data.parquet", "prod/data.parquet")
    store.delete("staging/data.parquet")

# Lazy read — quality flag. read() always works, but on backends without
# LAZY_READ the entire file is loaded into memory before the stream is
# returned. Use this flag to decide whether partial reads are efficient.
if store.supports(Capability.LAZY_READ):
    # Stream is connected to the native source; only the bytes you read
    # are transferred. Safe to read a small prefix of a large file.
    with store.read("large_file.bin") as f:
        header = f.read(256)
else:
    # Data is pre-loaded; reading any amount costs the full file.
    # For large files prefer read_bytes() or avoid partial reads.
    data = store.read_bytes("large_file.bin")
    header = data[:256]
```

## See also

- [Choosing a Backend](../guides/choosing-a-backend.md) — decision tree for picking
  the right backend
- [API Reference: Capability](api/capabilities.md)
