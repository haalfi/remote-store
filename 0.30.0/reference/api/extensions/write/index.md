# ext.write

Client-side hashing helpers for write operations. Guarantees a populated `WriteResult.digest` regardless of whether the backend declares `WRITE_RESULT_NATIVE`.

See the [ext.write spec](https://docs.remotestore.dev/stable/explanation/design/specs/046-ext-write/index.md) for invariants.

Async counterpart: [`aio.ext.write`](https://docs.remotestore.dev/stable/reference/api/aio/extensions/write/index.md).

## write

Write helpers with client-side content hashing.

Guarantees a populated `WriteResult.digest` regardless of whether the backend declares `WRITE_RESULT_NATIVE`. The hash is always computed client-side over the bytes as they are written.

### HashingAtomicWriter

```
HashingAtomicWriter(
    inner: BinaryIO, algorithm: str = "sha256"
)
```

Bases: `ChecksumWriter`

Writable stream wrapper used by `open_atomic_with_hash`.

Subclasses `ChecksumWriter` to add a `.result` attribute that is populated with a `WriteResult` after the context manager exits successfully. `result` is `None` if the block raised.

### write_with_hash

```
write_with_hash(
    store: Store,
    path: str,
    content: BinaryIO | bytes,
    *,
    algorithm: str = "sha256",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Write *content* to *path* and return a `WriteResult` with a client-computed digest.

Works on every backend declaring `Capability.WRITE`. The hash is always computed client-side regardless of `WRITE_RESULT_NATIVE`.

Parameters:

- **`store`** (`Store`) – The Store to write to.
- **`path`** (`str`) – Store-relative file path.
- **`content`** (`BinaryIO | bytes`) – bytes or readable binary stream.
- **`algorithm`** (`str`, default: `'sha256'` ) – Hash algorithm name (default "sha256").
- **`overwrite`** (`bool`, default: `False` ) – If False, raises AlreadyExists when path exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user metadata (see Store.write()).

Returns:

- `WriteResult` – WriteResult with digest populated from the client-side hash.

### open_atomic_with_hash

```
open_atomic_with_hash(
    store: Store,
    path: str,
    *,
    algorithm: str = "sha256",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> Iterator[HashingAtomicWriter]
```

Context manager for streaming atomic writes with client-side hashing.

Requires `Capability.ATOMIC_WRITE`. On successful exit, the yielded `HashingAtomicWriter.result` is a `WriteResult` with `digest` populated. On exception `result` remains `None`.

**Metadata branch:** When *metadata* is non-empty, the implementation buffers all written bytes in memory (`io.BytesIO`) and then calls `store.write_atomic()` on exit. This means (a) the full payload is held in RAM, and (b) validation errors (`ValueError`) and capability checks (`CapabilityNotSupported`) are raised after the caller has finished writing — not before. For large payloads, prefer calling `store.write()` directly with `metadata=`.

**`source` field:** Both branches always set `source="basic"` on the returned `WriteResult`. The metadata branch discards the `source` returned by `store.write_atomic()` because the rich- source contract cannot be honored for the no-metadata branch (`open_atomic` returns only a stream, not a `WriteResult`), so both branches use the same value for consistency.

Parameters:

- **`store`** (`Store`) – The Store to write to.
- **`path`** (`str`) – Store-relative file path.
- **`algorithm`** (`str`, default: `'sha256'` ) – Hash algorithm name (default "sha256").
- **`overwrite`** (`bool`, default: `False` ) – If False, raises AlreadyExists when path exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user metadata forwarded to Store.write_atomic() on backends that declare USER_METADATA.

Yields:

- `HashingAtomicWriter` – HashingAtomicWriter — write to it as a binary stream.

Raises:

- `CapabilityNotSupported` – If the backend lacks ATOMIC_WRITE.
- `AlreadyExists` – If path exists and overwrite is False.
