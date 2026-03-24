# Capabilities Matrix

Every backend declares which operations it supports via the
[Capability](api/capabilities.md#remote_store.Capability) enum.
Use [CapabilitySet](api/capabilities.md#remote_store.CapabilitySet) to query
at runtime before calling an operation.

## Backend x Capability

| Capability | [Local](backends/local.md) | [Memory](backends/memory.md) | [HTTP](backends/http.md) | [S3](backends/s3.md) | [S3-PyArrow](backends/s3-pyarrow.md) | [SFTP](backends/sftp.md) | [Azure](backends/azure.md) |
|------------|:-----:|:------:|:----:|:--:|:----------:|:----:|:-----:|
| READ           | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| WRITE          | Yes | Yes | —   | Yes | Yes | Yes | Yes |
| DELETE         | Yes | Yes | —   | Yes | Yes | Yes | Yes |
| LIST           | Yes | Yes | —   | Yes | Yes | Yes | Yes |
| MOVE           | Yes | Yes | —   | Yes | Yes | Yes | Yes |
| COPY           | Yes | Yes | —   | Yes | Yes | Yes | Yes |
| ATOMIC_WRITE   | Yes | Yes | —   | Yes | Yes | Yes | Yes |
| METADATA       | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| GLOB           | Yes | —  | —   | Yes | Yes | —  | Yes |
| SEEKABLE_READ  | Yes | Yes | —   | Yes | Yes | Yes | — |

**Full support (10/10):** Local, S3, S3-PyArrow.

**Near-full (9/10):** Memory and SFTP lack native `GLOB`. Use the portable
fallback `ext.glob.glob_files()` instead — see the
[Glob Pattern Matching](glob-pattern-matching.md) guide.
Azure lacks `SEEKABLE_READ` (forward-only chunk iterator). Use
`ext.seekable.seekable_read()` for portable seekable reads.

**Partial (2/10):** HTTP supports only `READ` and `METADATA` (read-only backend).

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
```

## See also

- [Choosing a Backend](choosing-a-backend.md) — decision tree for picking
  the right backend
- [API Reference: Capability](api/capabilities.md)
