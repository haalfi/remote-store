# ext.write

Client-side hashing helpers for write operations. Guarantees a populated
`WriteResult.digest` regardless of whether the backend declares
`WRITE_RESULT_NATIVE`.

See the [ext.write spec](../../../../sdd/specs/046-ext-write.md) for invariants.

Async counterpart: [`aio.ext.write`](../aio/extensions/write.md).

::: remote_store.ext.write
