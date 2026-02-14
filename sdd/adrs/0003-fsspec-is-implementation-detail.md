# ADR-0003: fsspec Is an Implementation Detail

## Status

Accepted

## Context

[fsspec](https://filesystem-spec.readthedocs.io/) provides a unified filesystem interface for Python. Many storage backends (S3, Azure, HDFS) have fsspec implementations. We could either:

1. Expose fsspec as part of our public API
2. Use fsspec internally but hide it behind our own ABC

## Decision

**fsspec is an implementation detail, never exposed in the public API.**

- Backend adapters *may* use fsspec internally (e.g., S3 via `s3fs`, Azure via `adlfs`)
- The `Backend` ABC is our own contract — it does not extend or depend on fsspec
- The `unwrap()` escape hatch allows extensions to access native handles (including fsspec filesystems) when they knowingly accept the coupling

```python
# Extension that needs native access:
fs = backend.unwrap(fsspec.AbstractFileSystem)  # explicit, type-safe
```

## Consequences

- Public API is stable regardless of fsspec changes
- Users don't need to learn fsspec
- Backend implementors can use fsspec, boto3, paramiko, or raw stdlib — their choice
- Extensions that need native access use `unwrap()` — explicit coupling, not accidental
- The local backend uses only stdlib (no fsspec) — proves the abstraction works without it
- Trade-off: we must maintain our own ABC instead of reusing fsspec's. This is intentional — our contract is stricter (capability-driven, error-normalized, streaming-first).
