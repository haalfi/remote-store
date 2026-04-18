# ext.write

Client-side hashing helpers for write operations. Guarantees a populated
`WriteResult.digest` regardless of whether the backend declares
`WRITE_RESULT_NATIVE`.

See the [write-result spec](https://github.com/haalfi/remote-store/blob/master/sdd/specs/045-write-result.md) for invariants.

::: remote_store.ext.write
