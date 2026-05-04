# aio.ext.write

Async write helpers with guaranteed client-side content hashing. Async
counterpart of [`ext.write`](write.md) — same guarantees, zero extra round
trips, no buffering for async-iterator input.

See the [Write Integrity guide](../../../guides/write-integrity.md) for usage examples
and the [ext.write spec](../../../../sdd/specs/046-ext-write.md) for invariants.

::: remote_store.aio.ext.write
