# Capabilities Matrix

Every backend declares which operations it supports via the
[Capability](../api/capabilities.md#remote_store.Capability) enum.
Use [CapabilitySet](../api/capabilities.md#remote_store.CapabilitySet) to query
at runtime before calling an operation.

## Backend x Capability

| Capability | [Local](../how-to/backends/local.md) | [Memory](../how-to/backends/memory.md) | [HTTP](../how-to/backends/http.md) | [S3](../how-to/backends/s3.md) | [S3-PyArrow](../how-to/backends/s3-pyarrow.md) | [SFTP](../how-to/backends/sftp.md) | [Azure](../how-to/backends/azure.md) | [SQLBlob](../how-to/backends/sql-blob.md) | [SQLQuery](../how-to/backends/sql-query.md) |
|------------|:-----:|:------:|:----:|:--:|:----------:|:----:|:-----:|:-------:|:---------:|
| READ           | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| WRITE          | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| DELETE         | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| LIST           | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | Yes |
| GLOB           | Yes | —   | —   | Yes | Yes | —   | Yes | Yes | Yes |
| MOVE           | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| COPY           | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| ATOMIC_WRITE   | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| ATOMIC_MOVE    | Yes | Yes | —   | —   | —   | —   | —   | Yes | —   |
| METADATA       | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| SEEKABLE_READ  | Yes | Yes | —   | Yes | Yes | Yes | —   | Yes | Yes |
| LAZY_READ      | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   | —   |
| WRITE_RESULT_NATIVE | Yes | Yes | — | Yes | Yes | Yes | Yes | Yes† | — |
| USER_METADATA  | —   | Yes | —   | Yes | —   | —   | Yes | Yes† | —   |

† `WRITE_RESULT_NATIVE` and `USER_METADATA` are declared by `SQLBlobBackend` only when the backing table includes a `user_metadata` column (see the SQLBlob guide for schema requirements). Legacy tables without this column do not declare either capability.

**Near-full:** Local lacks `USER_METADATA` — passing non-empty `metadata=` raises `CapabilityNotSupported`. S3 and S3-PyArrow lack `ATOMIC_MOVE` (copy-then-delete
semantics). SQLBlob lacks `LAZY_READ` — the entire blob is loaded into memory
before a stream is returned. Writes also materialize the full stream before
the SQL INSERT/UPDATE because BLOB columns require complete data.

**Partial support:** Memory lacks native `GLOB` and `LAZY_READ` (all
data lives in process memory; use the portable fallback
`ext.glob.glob_files()` — see the [Glob Pattern Matching](../how-to/glob-pattern-matching.md) guide).
SFTP lacks both `GLOB` and `ATOMIC_MOVE`.
Azure lacks `SEEKABLE_READ` and `ATOMIC_MOVE` (forward-only chunk iterator,
copy-then-delete move).

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

# Seekable read — works on any backend
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

- [Choosing a Backend](../how-to/choosing-a-backend.md) — decision tree for picking
  the right backend
- [API Reference: Capability](../api/capabilities.md)
