# aio.ext.write

Async write helpers with guaranteed client-side content hashing. Async counterpart of [`ext.write`](https://docs.remotestore.dev/stable/reference/api/extensions/write/index.md) — same guarantees, zero extra round trips, no buffering for async-iterator input.

See the [Write Integrity guide](https://docs.remotestore.dev/stable/guides/write-integrity/index.md) for usage examples and the [ext.write spec](https://docs.remotestore.dev/stable/explanation/design/specs/046-ext-write/index.md) for invariants.

## write

Async write helpers with client-side content hashing.

Guarantees a populated `WriteResult.digest` regardless of whether the backend declares `WRITE_RESULT_NATIVE`. The hash is always computed client-side over the bytes as they flow to the backend.

### write_with_hash

```
write_with_hash(
    store: AsyncStore,
    path: str,
    content: bytes | AsyncIterator[bytes],
    *,
    algorithm: str = "sha256",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Write *content* and return a `WriteResult` with `digest` populated.

Hash is computed client-side as data flows to the backend -- zero extra round trips, no buffering for async-iterator input. `source` is preserved from the underlying `store.write()` result.

Parameters:

- **`store`** (`AsyncStore`) – Target async store.
- **`path`** (`str`) – Destination path.
- **`content`** (`bytes | AsyncIterator[bytes]`) – bytes or AsyncIterator[bytes].
- **`algorithm`** (`str`, default: `'sha256'` ) – hashlib algorithm name. Default "sha256".
- **`overwrite`** (`bool`, default: `False` ) – Same semantics as AsyncStore.write.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user metadata; subject to USER_METADATA gate.

Returns:

- `WriteResult` – WriteResult with digest populated from the client-side hash.
