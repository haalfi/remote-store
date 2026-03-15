# Capabilities Matrix

Every backend declares which operations it supports via the
[Capability](api/capabilities.md#remote_store.Capability) enum.
Use [CapabilitySet](api/capabilities.md#remote_store.CapabilitySet) to query
at runtime before calling an operation.

## Backend x Capability

| Capability | Local | Memory | S3 | S3-PyArrow | SFTP | Azure |
|------------|:-----:|:------:|:--:|:----------:|:----:|:-----:|
| READ           | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; |
| WRITE          | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; |
| DELETE         | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; |
| LIST           | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; |
| MOVE           | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; |
| COPY           | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; |
| ATOMIC_WRITE   | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; |
| METADATA       | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; | &#x2705; |
| GLOB           | &#x2705; | &#x274C; | &#x2705; | &#x2705; | &#x274C; | &#x2705; |

**Full support (9/9):** Local, S3, S3-PyArrow, Azure.

**Partial (8/9):** Memory and SFTP lack native `GLOB`. Use the portable
fallback `ext.glob.glob_files()` instead — see the
[Glob Pattern Matching](glob-pattern-matching.md) guide.

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
