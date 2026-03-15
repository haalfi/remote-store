# Capabilities Matrix

Every backend declares which operations it supports via the
[Capability](api/capabilities.md#remote_store.Capability) enum.
Use [CapabilitySet](api/capabilities.md#remote_store.CapabilitySet) to query
at runtime before calling an operation.

## Backend x Capability

| Capability | Local | Memory | HTTP | S3 | S3-PyArrow | SFTP | Azure |
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

**Full support (9/9):** Local, S3, S3-PyArrow, Azure.

**Partial (8/9):** Memory and SFTP lack native `GLOB`. Use the portable
fallback `ext.glob.glob_files()` instead — see the
[Glob Pattern Matching](glob-pattern-matching.md) guide.

**Partial (2/9):** HTTP supports only `READ` and `METADATA` (read-only backend).

## Querying capabilities at runtime

```python
from remote_store import Capability

if Capability.GLOB in store.capabilities():
    results = store.glob("**/*.csv")
else:
    from remote_store import glob_files
    results = glob_files(store, "**/*.csv")
```

## See also

- [Choosing a Backend](choosing-a-backend.md) — decision tree for picking
  the right backend
- [API Reference: Capability](api/capabilities.md)
