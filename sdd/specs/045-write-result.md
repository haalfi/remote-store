# WriteResult and User Metadata

## Overview

Widening `Store.write*()` return types from `None` to `WriteResult`, adding
`Capability.WRITE_RESULT_NATIVE` (quality flag) and `Capability.USER_METADATA`
(strict capability gate on the `metadata=` kwarg), adding `Store.head()`, and
shipping the `ext.write` extension (`write_with_hash`, `open_atomic_with_hash`).

See [RFC-0011](../rfcs/rfc-0011-write-result.md) for design rationale,
alternative analysis, and the full ripple-check inventory.

---

## WR-001: Return Type Widening

**Invariant:** `Store.write()`, `Store.write_text()`, and `Store.write_atomic()`
return `WriteResult` instead of `None`. The underlying backend constructs the
`WriteResult`; the Store layer rebases `WriteResult.path` to be store-relative,
matching the rebasing applied to `FileInfo.path`.

## WR-002: WriteResult.path Is Store-Relative

**Invariant:** `WriteResult.path` is store-relative — `root_path` is stripped
exactly as `FileInfo.path` is stripped by `list_files` and `get_file_info`.
The returned path is directly usable as input to other Store methods.

## WR-003: WriteResult.size Population

**Invariant:** `WriteResult.size` equals the byte length of the written content
on every backend.

- For `bytes` / `str` input: `size` is computed from the payload directly
  (zero added I/O cost).
- For non-seekable `BinaryIO` input on backends without `WRITE_RESULT_NATIVE`:
  `size` is obtained by counting bytes as they stream or via a post-write
  `stat()` — one local `stat` on `LocalBackend`; the paramiko SFTP
  bytes-transferred counter on `SFTPBackend`; zero extra round trips in
  either case.
- For backends with `WRITE_RESULT_NATIVE` (Azure, S3, Memory, SQLBlob):
  `size` is available from the write response or trivially from the in-process
  data, never requiring an extra round trip.

## WR-004: source Field from WRITE_RESULT_NATIVE

**Invariant:** If the backend declares `Capability.WRITE_RESULT_NATIVE`, every
successful `Store.write*()` returns `WriteResult.source == "native"`. If it
does not declare the capability, `source == "basic"`.

## WR-005: Basic Source Guarantees

**Invariant:** When `WriteResult.source == "basic"`, only `path` and `size` are
guaranteed populated. All other rich fields (`digest`, `etag`, `version_id`,
`last_modified`, `content_md5`, `metadata`) are `None`.

**Note (future-compat):** No v1 backend declares `USER_METADATA` without also
declaring `WRITE_RESULT_NATIVE`, so `metadata is None` follows from the
backend set. A future backend that declared `USER_METADATA` without
`WRITE_RESULT_NATIVE` would resolve in favour of WR-012: `source == "basic"`
but `metadata` echoes the caller's mapping. WR-005's "all other rich fields
are `None`" is written against v1 backends; the `metadata` exception for a
future mismatch is governed by WR-012.

## WR-006: Sidecar Source

**Invariant:** `WriteResult.source == "sidecar"` only when the `WriteResult` is
constructed by `Store.head()`. Direct write calls never produce `source ==
"sidecar"`.

## WR-007: No Default Hashing

**Invariant:** The default write path (`Store.write*()` without `ext.write`)
returns `WriteResult.digest is None` on every backend that does not surface a
server-verified digest on its write response. No streaming hash wrapper is
inserted on the default path.

**Current backend set (v1):** No v1 backend surfaces a server-verified
digest. Azure's `content_md5` is client-supplied and stored server-side;
S3's single-PUT `ETag` is explicitly documented as *not* a content hash;
multipart `ETag` values have the form `"<md5-of-part-md5s>-<N>"`. So in
v1 the invariant simplifies to "`digest is None` on every backend," but
the invariant is written so that a future backend surfacing a
server-verified digest (e.g., opt-in S3 `ChecksumSHA256`) does not
require amending WR-007.

## WR-008: Store.head() Gating and Semantics

**Invariant:** `Store.head(path) -> WriteResult` is gated on
`Capability.METADATA` only. It is **not** gated on `Capability.WRITE` — callers
may invoke it on read-only backends that declare `METADATA`.

**Raises:** `NotFound` if the path does not exist. `CapabilityNotSupported` if
the backend lacks `METADATA`.

**Postconditions:** Returns `WriteResult` with `source == "sidecar"`,
constructed from the `FileInfo` returned by `Store.get_file_info(path)`.

**FileInfo → WriteResult field mapping:**

| `WriteResult` field | Source                                            |
| ------------------- | ------------------------------------------------- |
| `path`              | `info.path`                                       |
| `size`              | `info.size`                                       |
| `digest`            | `info.digest`                                     |
| `etag`              | `info.etag`                                       |
| `last_modified`     | `info.modified_at` (field rename)                 |
| `metadata`          | `info.metadata`                                   |
| `version_id`        | `None` (no corresponding `FileInfo` field in v1)  |
| `content_md5`       | `None` (client-supplied only at write time)       |
| `source`            | `"sidecar"` (always, for `head()`-produced results) |

`FileInfo.name`, `FileInfo.content_type`, and `FileInfo.extra` are **not**
propagated to `WriteResult` — they are file-listing concerns, not
write-result concerns. A subsequent `get_file_info()` remains the path for
callers needing the full `FileInfo`.

## WR-009: WRITE_RESULT_NATIVE Is a Quality Flag

**Invariant:** `Capability.WRITE_RESULT_NATIVE` is a quality flag — it does not
gate any method. `Store.write()` works on every backend regardless of whether
the capability is declared. The flag advertises which fields in the returned
`WriteResult` are populated from the backend's write response.

**Backend declarations:**

| Backend            | Declares `WRITE_RESULT_NATIVE`? |
| ------------------ | ------------------------------- |
| `AzureBackend`     | yes                             |
| `S3Backend`        | yes                             |
| `MemoryBackend`    | yes                             |
| `SQLBlobBackend`   | yes                             |
| `S3PyArrowBackend` | no                              |
| `SFTPBackend`      | no                              |
| `LocalBackend`     | no                              |

## WR-010: USER_METADATA Gates the metadata= Kwarg

**Invariant:** `Capability.USER_METADATA` is a strict gate (see
[ADR-0026](../adrs/0026-strict-gate-on-kwarg.md)). Passing `metadata=` to
`Store.write*()` on a backend that does not declare `USER_METADATA` raises
`CapabilityNotSupported` before any I/O.

**Backend declarations:**

| Backend            | Declares `USER_METADATA`? |
| ------------------ | ------------------------- |
| `AzureBackend`     | yes                       |
| `S3Backend`        | yes                       |
| `MemoryBackend`    | yes                       |
| `SQLBlobBackend`   | yes                       |
| `S3PyArrowBackend` | no                        |
| `SFTPBackend`      | no                        |
| `LocalBackend`     | no                        |

## WR-011: metadata Validation

**Invariant:** `metadata` is `Mapping[str, str]`. Validation is performed at the
Store layer (one place, not per-backend) before capability dispatch:

- Keys must be non-empty ASCII strings with no leading underscore.
- Values must be strings.
- `sum(len(k.encode("ascii")) + len(v.encode("utf-8")) for k, v in
  metadata.items()) ≤ 2048`. This measures payload bytes only — not HTTP-header
  framing or backend-specific prefixes such as `x-amz-meta-`. The bound matches
  the narrowest portable limit (S3's 2 KB user-metadata cap).
- An empty mapping (`{}`) is accepted — it is semantically equivalent to
  `metadata=None`, which WR-010 allows — and **must not** be treated as a
  validation failure.

Violations raise `ValueError` with the offending key or value before any I/O.

## WR-012: WriteResult.metadata Echo

**Invariant:** When `metadata=` is passed and the backend declares
`USER_METADATA`, `WriteResult.metadata` echoes the mapping **verbatim, as the
caller passed it** — same keys, same values, same case. No normalisation
(no key lowercasing, no whitespace trimming) is applied at the Store layer
or recorded on `WriteResult.metadata`, even when the backend itself
normalises on write (e.g., S3 lowercases `x-amz-meta-*` header names in the
HTTP response). Backend-side normalisation is observable only through
`FileInfo.metadata` on a subsequent `get_file_info()` call (see WR-013).

When `metadata=` is not passed, `WriteResult.metadata` is `None`. This
holds regardless of `source`: a `"basic"` result that nonetheless passed
the `USER_METADATA` gate (a configuration not used in v1 — see WR-005
footnote) still echoes the caller's mapping.

## WR-013: User Metadata Round-Trip

**Invariant:** User metadata passed to `Store.write*()` on a backend declaring
`USER_METADATA` survives round-trip through `Store.get_file_info()`, accessible
as `FileInfo.metadata: Mapping[str, str] | None`. On backends that do not
declare `USER_METADATA`, `FileInfo.metadata` is always `None`.

## WR-014: ext.write.write_with_hash Returns Digest

**Invariant:** `ext.write.write_with_hash(store, path, content, *, algorithm,
overwrite, metadata) -> WriteResult` returns a `WriteResult` with `digest`
populated from a client-side streaming hash over the written bytes. The
underlying `source` value from the backend write is preserved (`"native"` or
`"basic"`); `digest` is set independently of `source` and always represents
the client-computed hash.

## WR-015: ext.write.write_with_hash Works on Every WRITE Backend

**Invariant:** `ext.write.write_with_hash()` works on every backend declaring
`Capability.WRITE`. The hash is always computed client-side via
`ext.streams.ChecksumWriter` regardless of `WRITE_RESULT_NATIVE`. No additional
capability beyond `WRITE` is required.

## WR-016: open_atomic_with_hash Requires ATOMIC_WRITE

**Invariant:** `ext.write.open_atomic_with_hash()` requires
`Capability.ATOMIC_WRITE` on the underlying store (inherited from
`Store.open_atomic`, SAW-002). If the capability is absent,
`CapabilityNotSupported` is raised before any I/O.

## WR-017: open_atomic_with_hash Exposes result After Exit

**Invariant:** `ext.write.open_atomic_with_hash()` is an `@contextmanager`
that yields a `HashingAtomicWriter` — a `ChecksumWriter` subclass defined in
`ext.write` that adds a `.result: WriteResult | None` attribute. The base
`ChecksumWriter` (spec 006 / `ext.streams`) is unchanged.

**Lifecycle of `.result`:**

- Before the `with` block exits, `writer.result` is `None`.
- On **successful** exit of the `with` block, `writer.result` is populated
  with a `WriteResult` whose `digest` field carries the client-computed
  streaming hash and whose other fields mirror the underlying
  `Store.write_atomic()` result.
- On **exception** exit (the `with` body or the inner `write_atomic`
  raised), `writer.result` remains `None`; the exception propagates
  unchanged. `HashingAtomicWriter` does not record a partial or
  failed result.

**Testability:** Two positive tests (pre-exit `.result is None`; post-exit
`.result is WriteResult(...)`), one negative test (body raises →
post-exit `.result is None` and exception propagates).

## WR-018: Proxy Stack Forwarding

**Invariant:** The proxy stack (`ext.observe`, `ext.cache`, `_proxy`) widens
the return type of `write`, `write_text`, and `write_atomic` overrides from
`None` to `WriteResult` and forwards the underlying store's `WriteResult`
unchanged. Proxies never substitute, mutate, or synthesise fields on the
forwarded result. `Store.head()` is added to the same proxies and forwards
to the wrapped store's `head()`. `ext.cache` does not cache `WriteResult` —
it forwards the write and invalidates the cache entry for the written path
as today.

**`open_atomic` is explicitly excluded** from the widening: SAW-001 /
SAW-013 keep the `Iterator[BinaryIO]` contract, and the proxy stack's
`open_atomic` override returns `Iterator[BinaryIO]` unchanged. Callers
needing a `WriteResult` for a streaming atomic write use `Store.head()`
after the `with` block or `ext.write.open_atomic_with_hash()` (see
WR-017).

**See also:** [019-ext-observe.md](019-ext-observe.md),
[023-ext-cache.md](023-ext-cache.md),
[022-streaming-atomic-writes.md](022-streaming-atomic-writes.md)
(SAW-001, SAW-013).

## WR-019: StoreEvent Carries WriteResult

**Invariant:** On successful `write`, `write_text`, and `write_atomic`, the
post-operation `StoreEvent` emitted by `ext.observe` carries the returned
`WriteResult` under `StoreEvent.metadata["write_result"]`. All three
operations route through `on_write` (per OBS-003a, updated in this PR to
add `write_text`). `StoreEvent.metadata` keeps its existing
`dict[str, Any]` type — access via `event.metadata["write_result"]` is
explicitly untyped; callers narrow with `isinstance(..., WriteResult)` if
static checking is required. On failure (wrapped write raised), no
`"write_result"` key is present.

**Implementation note:** The current `_observe_op` helper is a context
manager that constructs the `StoreEvent` before the wrapped call returns;
injecting `write_result` requires mutating `event.metadata` after the
wrapped call completes but before hook dispatch, or a minor
`_observe_op` refactor. The invariant is neutral between implementations.

**See also:** [019-ext-observe.md](019-ext-observe.md) (OBS-003a, OBS-015).
