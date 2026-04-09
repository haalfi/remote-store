# Capabilities Matrix

Every backend declares which operations it supports via the
[Capability](api/capabilities.md#remote_store.Capability) enum.
Use [CapabilitySet](api/capabilities.md#remote_store.CapabilitySet) to query
at runtime before calling an operation.

## Backend x Capability

| Capability | [Local](backends/local.md) | [Memory](backends/memory.md) | [HTTP](backends/http.md) | [S3](backends/s3.md) | [S3-PyArrow](backends/s3-pyarrow.md) | [SFTP](backends/sftp.md) | [Azure](backends/azure.md) | [SQLBlob](backends/sql-blob.md) | [SQLQuery](backends/sql-query.md) |
|------------|:-----:|:------:|:----:|:--:|:----------:|:----:|:-----:|:-------:|:---------:|
| READ           | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| WRITE          | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| DELETE         | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| LIST           | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | Yes |
| MOVE           | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| COPY           | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| ATOMIC_WRITE   | Yes | Yes | —   | Yes | Yes | Yes | Yes | Yes | —   |
| ATOMIC_MOVE    | Yes | Yes | —   | —   | —   | —  | —     | Yes | —   |
| METADATA       | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| GLOB           | Yes | —  | —   | Yes | Yes | —  | Yes | Yes | Yes |
| SEEKABLE_READ  | Yes | Yes | —   | Yes | Yes | Yes | — | Yes | Yes |

**Full support (11/11):** Local, SQLBlob.

**Near-full (10/11):** Memory lacks native `GLOB`; use the portable
fallback `ext.glob.glob_files()` — see the
[Glob Pattern Matching](glob-pattern-matching.md) guide.
S3 and S3-PyArrow lack `ATOMIC_MOVE` (copy-then-delete semantics).

**Partial support (9/11):** SFTP lacks both `GLOB` and `ATOMIC_MOVE`.
Azure lacks `SEEKABLE_READ` and `ATOMIC_MOVE` (forward-only chunk
iterator, copy-then-delete move).

**Read-only (5/11):** SQLQuery supports only `READ`, `LIST`, `METADATA`, `GLOB`,
and `SEEKABLE_READ`.

**Minimal (2/11):** HTTP supports only `READ` and `METADATA` (read-only backend).

## Querying capabilities at runtime

```python
from remote_store import Capability

if Capability.GLOB in store.capabilities():
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
```

## See also

- [Choosing a Backend](choosing-a-backend.md) — decision tree for picking
  the right backend
- [API Reference: Capability](api/capabilities.md)
