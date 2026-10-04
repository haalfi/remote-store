# Write Integrity

Every `Store.write*()` call returns a [`WriteResult`](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.WriteResult) carrying whatever metadata the backend produced during the write — ETag, version ID, last-modified timestamp, and (on Azure) a server-echoed content hash. Backends that populate these fields from their write response declare `Capability.WRITE_RESULT_NATIVE`, each filling whatever that response carries — some fill all these fields, some none (SFTP's write response carries no metadata at all, so it leaves every rich field `None` — call `get_file_info()` for the metadata); backends without the flag return a minimal `WriteResult` with `path` and `size` only.

When you need a content hash regardless of backend, use the helpers in [`ext.write`](https://docs.remotestore.dev/stable/reference/api/extensions/write/index.md) (sync) or [`aio.ext.write`](https://docs.remotestore.dev/stable/reference/api/aio/extensions/write/index.md) (async). They compute the digest client-side as bytes flow through the stream, so the hash is always available.

## write_with_hash

Use `write_with_hash` when you have the content as `bytes` or a readable binary stream:

```
from remote_store.ext.write import write_with_hash

store = Store(MemoryBackend())
result = write_with_hash(store, "report.csv", b"col1,col2\n1,2\n")

assert result.digest is not None
print(result.digest.algorithm)  # sha256
print(result.digest.value)  # hex digest
```

`write_with_hash` returns a `WriteResult` with `digest` populated from the client-side hash — the SHA-256 is computed over the bytes as they are written, not after the fact. The default algorithm is `"sha256"`; pass `algorithm="sha512"` (or any `hashlib`-supported name) to override.

## open_atomic_with_hash

Use `open_atomic_with_hash` for streaming writes where you build the content incrementally. The context manager yields a `HashingAtomicWriter`; on clean exit `writer.result` holds the `WriteResult`:

```
from remote_store.ext.write import open_atomic_with_hash

store = Store(MemoryBackend())
with open_atomic_with_hash(store, "data.bin") as writer:
    writer.write(b"chunk one ")
    writer.write(b"chunk two")

result = writer.result
assert result is not None
assert result.digest is not None
print(result.digest.value)  # sha256 of "chunk one chunk two"
```

This requires `Capability.ATOMIC_WRITE`. When called without `metadata=`, `CapabilityNotSupported` is raised before any data is written. When `metadata=` is supplied, capability checks run on exit — see the [`open_atomic_with_hash` docstring](https://docs.remotestore.dev/stable/reference/api/extensions/write/index.md) for the metadata-branch caveat.

## Comparing write-time and read-time digests

Call `store.head()` after a write to retrieve a `WriteResult` from a metadata lookup (`source="sidecar"`). On backends that echo a digest natively, the values agree:

```
from remote_store.ext.write import write_with_hash

store = Store(MemoryBackend())
write_result = write_with_hash(store, "archive.bin", b"payload")

head = store.head("archive.bin")
print(head.size)  # 7
print(head.source)  # "sidecar"

# Compare digests if the backend echoed one back natively:
if write_result.digest and head.digest:
    assert write_result.digest.value == head.digest.value
```

`head()` is gated on `Capability.METADATA` and works on read-only backends that declare it (for example, the HTTP backend). Use it when you want a `WriteResult`-shaped view of a file that was written elsewhere.

## Storing user metadata alongside a file

Backends that declare `Capability.USER_METADATA` accept an optional `metadata=` mapping on `write*()` calls:

```
result = store.write(
    "report.csv",
    content,
    metadata={"owner": "data-team", "run-id": "2026-04-18"},
)
```

`metadata=` is a strict capability gate: passing a non-empty mapping to a backend without `USER_METADATA` raises `CapabilityNotSupported`. Check `store.supports(Capability.USER_METADATA)` before using it in backend-agnostic code. See the [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) for which backends support it.

## Async usage

For `AsyncStore`, use `write_with_hash` from `aio.ext.write` — the interface is identical, accepts `bytes` or `AsyncIterator[bytes]`, and hashes inline without buffering:

```
from remote_store.aio.ext.write import write_with_hash

store = AsyncStore(AsyncMemoryBackend())
result = await write_with_hash(store, "report.csv", b"col1,col2\n1,2\n")

assert result.digest is not None
print(result.digest.algorithm)  # sha256
print(result.digest.value)  # hex digest
```

## See also

- [`ext.write` API reference](https://docs.remotestore.dev/stable/reference/api/extensions/write/index.md)
- [`aio.ext.write` API reference](https://docs.remotestore.dev/stable/reference/api/aio/extensions/write/index.md)
- [`WriteResult` and `ContentDigest`](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.WriteResult)
- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — `WRITE_RESULT_NATIVE` and `USER_METADATA` rows
- [Concurrency guide](https://docs.remotestore.dev/stable/explanation/concurrency/index.md) — atomicity semantics for `write_atomic` and `open_atomic`
