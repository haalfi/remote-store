# Spec 046 — ext.write Extension

`ext.write` provides two helpers that guarantee a populated
`WriteResult.digest` regardless of backend capability:

- `write_with_hash` — write bytes or a stream and return a `WriteResult`
  with `digest` computed client-side.
- `open_atomic_with_hash` — streaming atomic write with client-side
  hashing, yielding a `HashingAtomicWriter` whose `.result` is populated
  after successful exit.

**Moved from spec 045 (WR-014..WR-017)** per the one-spec-per-extension
convention (ADR-0008 / spec 019 / spec 023 / spec 024).  Cross-references
remain in spec 045 (WR-014..WR-017 stubs).

See [RFC-0011](../rfcs/rfc-0011-write-result.md) for design rationale.

---

## EW-001 (was WR-014): write_with_hash Returns Digest

**Invariant:** `ext.write.write_with_hash(store, path, content, *,
algorithm="sha256", overwrite=False, metadata=None) -> WriteResult`
returns a `WriteResult` with `digest` populated from a client-side
streaming hash over the written bytes. The underlying `source` value
from the backend write is preserved (`"native"` or `"basic"`); `digest`
is set independently of `source` and always represents the
client-computed hash.

**Parameter defaults (normative):**

- `algorithm: str = "sha256"` — hash algorithm name accepted by
  `hashlib.new`. Single-algorithm only in v1, matching the existing
  `ChecksumWriter` signature; multi-algorithm multiplex is deferred.
- `overwrite: bool = False` — same semantics as `Store.write`.
- `metadata: Mapping[str, str] | None = None` — optional user
  metadata; subject to the `USER_METADATA` capability gate (WR-010)
  applied inside the underlying `store.write()`.

## EW-002 (was WR-015): write_with_hash Works on Every WRITE Backend

**Invariant:** `ext.write.write_with_hash()` works on every backend
declaring `Capability.WRITE`. The hash is always computed client-side
regardless of `WRITE_RESULT_NATIVE`. No additional capability beyond
`WRITE` is required.

## EW-003 (was WR-016): open_atomic_with_hash Requires ATOMIC_WRITE

**Invariant:** `ext.write.open_atomic_with_hash(store, path, *,
algorithm="sha256", overwrite=False, metadata=None) ->
Iterator[HashingAtomicWriter]` is a `@contextmanager` that requires
`Capability.ATOMIC_WRITE` on the underlying store (inherited from
`Store.open_atomic`, SAW-002). If the capability is absent,
`CapabilityNotSupported` is raised before any I/O.

**Parameter defaults (normative):** Same as EW-001 —
`algorithm: str = "sha256"`, `overwrite: bool = False`,
`metadata: Mapping[str, str] | None = None`.

## EW-004 (was WR-017): open_atomic_with_hash Exposes result After Exit

**Invariant:** `ext.write.open_atomic_with_hash()` is a `@contextmanager`
that yields a `HashingAtomicWriter` — a `ChecksumWriter` subclass defined
in `ext.write` that adds a `.result: WriteResult | None` attribute. The
base `ChecksumWriter` (spec 006 / `ext.streams`) is unchanged.

**Lifecycle of `.result`:**

- Before the `with` block exits, `writer.result` is `None`.
- On **successful** exit of the `with` block, `writer.result` is
  populated with a `WriteResult` whose `digest` field carries the
  client-computed streaming hash and whose other fields mirror the
  underlying write result.
- On **exception** exit, `writer.result` remains `None`; the exception
  propagates unchanged.

**Testability:** Two positive tests (pre-exit `.result is None`;
post-exit `.result is WriteResult(...)`), one negative test (body raises
→ post-exit `.result is None` and exception propagates).
