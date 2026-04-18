# Write Integrity

Every `Store.write*()` call returns a [`WriteResult`](api/models.md#remote_store.WriteResult)
carrying whatever metadata the backend produced during the write —
ETag, version ID, last-modified timestamp, and (on Azure) a server-echoed
content hash. Backends that fully populate these fields declare
`Capability.WRITE_RESULT_NATIVE`; others return a minimal `WriteResult`
with `path` and `size` only.

When you need a content hash regardless of backend, use the helpers in
[`ext.write`](api/extensions/write.md). They compute the digest client-side
as bytes flow through the stream, so the hash is always available.

## write_with_hash

Use `write_with_hash` when you have the content as `bytes` or a readable
binary stream:

```python
--8<-- "examples/snippets/write_integrity.py:write-with-hash"
```

`write_with_hash` returns a `WriteResult` with `digest` populated from the
client-side hash — the SHA-256 is computed over the bytes as they are written,
not after the fact. The default algorithm is `"sha256"`; pass
`algorithm="sha512"` (or any `hashlib`-supported name) to override.

## open_atomic_with_hash

Use `open_atomic_with_hash` for streaming writes where you build the content
incrementally. The context manager yields a `HashingAtomicWriter`; on clean
exit `writer.result` holds the `WriteResult`:

```python
--8<-- "examples/snippets/write_integrity.py:open-atomic-with-hash"
```

This requires `Capability.ATOMIC_WRITE`. If the backend lacks it,
`CapabilityNotSupported` is raised before any data is written.

## Comparing write-time and read-time digests

Call `store.head()` after a write to retrieve a `WriteResult` from a metadata
lookup (`source="sidecar"`). On backends that echo a digest natively, the
values agree:

```python
--8<-- "examples/snippets/write_integrity.py:head-after-write"
```

`head()` is gated on `Capability.METADATA` and works on read-only backends
that declare it (for example, the HTTP backend). Use it when you want a
`WriteResult`-shaped view of a file that was written elsewhere.

## Storing user metadata alongside a file

Backends that declare `Capability.USER_METADATA` accept an optional
`metadata=` mapping on `write*()` calls:

```python
result = store.write(
    "report.csv",
    content,
    metadata={"owner": "data-team", "run-id": "2026-04-18"},
)
```

`metadata=` is a strict capability gate: passing a non-empty mapping to a
backend without `USER_METADATA` raises `CapabilityNotSupported`. Check
`store.supports(Capability.USER_METADATA)` before using it in
backend-agnostic code. See the
[Capabilities Matrix](capabilities-matrix.md) for which backends support it.

## See also

- [`ext.write` API reference](api/extensions/write.md)
- [`WriteResult` and `ContentDigest`](api/models.md#remote_store.WriteResult)
- [Capabilities Matrix](capabilities-matrix.md) — `WRITE_RESULT_NATIVE` and `USER_METADATA` rows
- [Concurrency guide](concurrency.md) — atomicity semantics for `write_atomic` and `open_atomic`
