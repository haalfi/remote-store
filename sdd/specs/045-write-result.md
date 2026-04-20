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

## WR-001a: WriteResult Fields

**Invariant:** `WriteResult` is a frozen dataclass with the following
fields. This is the normative field schema — every other WR- invariant
is expressed against it.

**Required:**

- `path` (`RemotePath`) — normalised written path, store-relative
  (WR-002).
- `size` (`int`) — bytes written (WR-003).

**Optional (default `None` unless noted):**

- `digest` (`ContentDigest | None`) — verified content digest:
  client-computed via `ext.write.write_with_hash` (WR-014), a
  backend-echoed content hash from the write response (e.g., Azure
  `content_md5`), or a server-verified hash surfaced by the write path
  (e.g., S3 auto-CRC32 via `head_object(ChecksumMode="ENABLED")`);
  `None` when the backend does not surface any digest on write (WR-007).
- `etag` (`str | None`) — backend change tag; not a content hash on
  every backend (see RFC-0011 § Proposal for per-backend semantics).
- `version_id` (`str | None`) — backend-provided immutable version
  identifier; `None` when the backend does not version objects.
- `last_modified` (`datetime | None`) — server timestamp from the
  write response; `None` when the backend's write response omits it.
- `metadata` (`Mapping[str, str] | None`) — echo of the user
  metadata that was stored (WR-012).

**Default-valued:**

- `source` (`Literal["native", "basic", "sidecar"]`, default
  `"basic"`) — provenance of the rich fields (WR-004, WR-006).

**Postconditions:**

- Attribute assignment raises `FrozenInstanceError`.
- `WriteResult` supports equality by field-wise value (standard dataclass
  behaviour). It is hashable when all field values are hashable; `metadata`
  (typed `Mapping[str, str] | None`) is hashable only when `None` or
  backed by an immutable mapping — a plain `dict` makes `hash(wr)` raise
  `TypeError`. Use `_hashable_write_result_st` (the PBT strategy) when
  hash properties must be tested.

**See also:** [035-content-digest.md](035-content-digest.md) for
`ContentDigest`; RFC-0011 § Proposal for the canonical Python
dataclass definition and docstring.

**Formal coverage:** `WriteResult` is modelled in
`sdd/formal/BackendContract.dfy` as a datatype with the fields listed
above (`path`, `size`, `digest`, `etag`, `version_id`, `last_modified`,
`metadata`, `source`). The `Write` method's postcondition chain
discharges `r.value.path == path`, `r.value.size == |content|`, and —
when `CapWriteResultNative in capabilities` — that rich fields on the
returned `WriteResult` match the stored `FileInfo`, so a subsequent
`GetFileInfo` (and `head()` via `WriteResultFromFileInfo`) returns
consistent fields. Verified in `MemoryBackend.dfy`. Python backstop in
`tests/backends/test_conformance.py::TestWriteResultConformance`
(`test_result_is_write_result_with_path_and_size`,
`test_size_matches_written_bytes_for_streaming_input`,
`test_native_populates_last_modified`,
`test_native_file_info_matches_write_result`,
`test_digest_matches_file_info`). See ID-151.

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

**Formal coverage:** encoded in `BackendContract.dfy` as a `Write`
postcondition: `r.Ok? ⇒ r.value.source == (if CapWriteResultNative in
capabilities then NativeSource else BasicSource)`. A backend that
declares the capability but fails to populate `source = Native` — or
fails to populate the rich fields that the spec promises alongside it —
does not satisfy the refinement. Verified in `MemoryBackend.dfy`. Python
backstop in
`tests/backends/test_conformance.py::TestWriteResultConformance::test_source_matches_write_result_native`.
See ID-151.

## WR-005: Basic Source Guarantees

**Invariant:** When `WriteResult.source == "basic"`, only `path` and `size` are
guaranteed populated. The rich fields `digest`, `etag`, `version_id`, and
`last_modified` are `None`. The `metadata` field is
**not** governed by `source` — it is governed independently by WR-012:
`WriteResult.metadata` echoes the caller's mapping whenever the
`USER_METADATA` gate was passed, and is `None` otherwise, regardless of
whether `source` is `"native"`, `"basic"`, or `"sidecar"`.

**Note (future-compat):** No v1 backend declares `USER_METADATA` without
also declaring `WRITE_RESULT_NATIVE`, so in v1 a `"basic"` result also
has `metadata is None` by construction. A future backend that declared
`USER_METADATA` without `WRITE_RESULT_NATIVE` would produce a `"basic"`
result whose `metadata` echoes the caller's mapping — fully consistent
with the invariant above, because `metadata` is excluded from the
source-gated field list.

**Formal coverage:** encoded in `BackendContract.dfy` as the basic-source
branch of the `Write` postcondition chain — when `CapWriteResultNative
!in capabilities`, the returned `WriteResult` has
`digest/etag/version_id/last_modified` pinned to `None`. Verified in
`MemoryBackend.dfy`. Python backstop in
`tests/backends/test_conformance.py::TestWriteResultConformance::test_basic_source_leaves_rich_fields_none`.
See ID-151.

## WR-006: Sidecar Source

**Invariant:** `WriteResult.source == "sidecar"` only when the `WriteResult` is
constructed by `Store.head()`. Direct write calls never produce `source ==
"sidecar"`.

## WR-007: No Default Hashing

**Invariant:** The default write path (`Store.write*()` without `ext.write`)
returns `WriteResult.digest is None` on every backend that does not surface a
server-verified or backend-echoed content hash on its write response. No
streaming hash wrapper is inserted on the default path.

**Current backend set (v1):**

- *Server-verified digest:* S3 only. `S3Backend.write()` calls
  `head_object(..., ChecksumMode="ENABLED")` after the upload — the same
  call used by `get_file_info` (S3-024) — and wraps the returned
  auto-CRC32 in `ContentDigest("crc32", …)`. Amazon S3 has automatically
  stored CRC32 checksums for new objects since late 2022, so this digest
  is present for all standard single-PUT uploads. S3's `ETag` is separately
  *not* a content hash; this invariant refers to the `digest` field only.
- *Backend-echoed digest:* Azure only. Azure echoes the client-supplied MD5
  as `ContentDigest("md5", …)` in `WriteResult.digest` when the caller
  supplied an MD5 on the write request. That value is client-originated but
  surfaces what the backend stored, satisfying the "backend-echoed" clause.
- All other v1 backends return `WriteResult.digest is None`.

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
| `source`            | `"sidecar"` (always, for `head()`-produced results) |

`FileInfo.name`, `FileInfo.content_type`, and `FileInfo.extra` are **not**
propagated to `WriteResult` — they are file-listing concerns, not
write-result concerns. A subsequent `get_file_info()` remains the path for
callers needing the full `FileInfo`.

**Formal coverage:** `head()` is a Store-layer composition over
`get_file_info()`, so the field mapping is encoded at the Backend
contract level as a pure function `WriteResultFromFileInfo: FileInfo →
WriteResult` with `source = SidecarSource`. The `WR008FieldMapping`
lemma in `BackendContract.dfy` pins the Dafny function to the Dafny
`FileInfo` datatype — it does not anchor this Markdown table to the
Dafny function. Cross-check between this table and the Dafny function
body is a human-review obligation; a reviewer who edits only this
table does not get a Dafny failure. The WR-006 negative direction
(`Write` never produces `SidecarSource`) is enforced structurally by
`Write`'s postcondition restricting `source` to `NativeSource |
BasicSource`. See ID-151.

## WR-009: WRITE_RESULT_NATIVE Is a Quality Flag

**Invariant:** `Capability.WRITE_RESULT_NATIVE` is a quality flag — it does not
gate any method. `Store.write()` works on every backend regardless of whether
the capability is declared. The flag advertises which fields in the returned
`WriteResult` are populated from the backend's write response.

**Backend declarations:**

| Backend                      | Declares `WRITE_RESULT_NATIVE`? |
| ---------------------------- | ------------------------------- |
| `AzureBackend`               | yes                             |
| `S3Backend`                  | yes                             |
| `MemoryBackend`              | yes                             |
| `SQLBlobBackend`             | yes — when `user_metadata` column is present; no otherwise (dynamic) |
| `S3PyArrowBackend`           | no                              |
| `SFTPBackend`                | no                              |
| `LocalBackend`               | no                              |
| `AsyncBackendSyncAdapter`    | no — masked unconditionally regardless of what the inner async backend declares (see WR-010) |

## WR-010: USER_METADATA Gates the metadata= Kwarg

**Invariant:** `Capability.USER_METADATA` is a strict gate (see
[ADR-0026](../adrs/0026-strict-gate-on-kwarg.md)). Passing a **non-empty**
`metadata` mapping to `Store.write*()` on a backend that does not declare
`USER_METADATA` raises `CapabilityNotSupported` before any I/O.

**Empty-mapping carve-out.** `metadata=None` and `metadata={}` are treated
identically by this gate: neither triggers `CapabilityNotSupported`. The
gate fires only when `metadata` is a non-`None`, non-empty mapping — an
empty mapping is semantically equivalent to not passing the kwarg (see
WR-011). This keeps the gate consistent with WR-011's rule that
`metadata={}` is a valid no-op and never a validation failure.

**Backend declarations:**

| Backend                      | Declares `USER_METADATA`? |
| ---------------------------- | ------------------------- |
| `AzureBackend`               | yes                       |
| `S3Backend`                  | yes                       |
| `MemoryBackend`              | yes                       |
| `SQLBlobBackend`             | yes — when `user_metadata` column is present; no otherwise (dynamic) |
| `S3PyArrowBackend`           | no                        |
| `SFTPBackend`                | no                        |
| `LocalBackend`               | no                        |
| `AsyncBackendSyncAdapter`    | no — masked unconditionally (see below) |

**Adapter masking.** `AsyncBackendSyncAdapter` strips both `WRITE_RESULT_NATIVE`
and `USER_METADATA` from the inner async backend's capability set, even when the
wrapped backend declares them. This is the strict-gate-on-kwarg pattern (ADR-0026)
applied defensively: without masking, the Store layer's WR-010 gate would pass a
non-empty `metadata=` through to the adapter, but the adapter's `write*()` methods
do not forward `metadata=` to the async backend (the async ABC does not yet accept
it — Step 3c). Masking ensures `CapabilityNotSupported` is raised at the gate
rather than silently dropping the metadata, preserving the WR-012 echo guarantee.

## WR-011: metadata Validation

**Invariant:** `metadata` is `Mapping[str, str]`. Validation is performed at the
Store layer (one place, not per-backend) **before** the WR-010 capability
dispatch. The precedence is fixed:

1. **Shape validation first.** Validate `metadata` against the rules below.
   On any violation, raise `ValueError` before any I/O — regardless of
   whether the backend declares `USER_METADATA`.
2. **Capability dispatch second.** Only after shape validation passes does
   the Store check for `Capability.USER_METADATA` (WR-010) and raise
   `CapabilityNotSupported` on a non-declaring backend.

This ordering means a malformed `metadata=` kwarg always surfaces as
`ValueError`, even on backends that do not declare `USER_METADATA`.

Validation rules:

- Keys must be non-empty ASCII strings with no leading underscore.
- Values must be strings.
- `sum(len(k.encode("ascii")) + len(v.encode("utf-8")) for k, v in
  metadata.items()) ≤ 2048`. This measures payload bytes only — not HTTP-header
  framing or backend-specific prefixes such as `x-amz-meta-`. The bound matches
  the narrowest portable limit (S3's 2 KB user-metadata cap).
- An empty mapping (`{}`) is accepted — it is semantically equivalent to
  `metadata=None`, which WR-010 allows — and **must not** be treated as a
  validation failure. A non-declaring backend therefore treats `metadata={}`
  the same as `metadata=None`: no `CapabilityNotSupported` is raised.

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

**Formal coverage:** encoded in `BackendContract.dfy` as a `Write`
postcondition: `r.Ok? ⇒ r.value.metadata == (if HasUserMetadata(metadata)
∧ CapUserMetadata in capabilities then metadata else None)`. The
`HasUserMetadata` predicate captures the empty-mapping carve-out
(WR-010). A backend that declares `CapUserMetadata` but silently drops
the caller's mapping does not satisfy the refinement. Verified in
`MemoryBackend.dfy`. Python backstop in
`tests/backends/test_conformance.py::TestWriteResultConformance`
(`test_metadata_echoed_when_gate_passes`,
`test_metadata_is_none_when_not_passed`). See ID-151.

## WR-013: User Metadata Round-Trip

**Invariant:** User metadata passed to `Store.write*()` on a backend declaring
`USER_METADATA` survives round-trip through `Store.get_file_info()`, accessible
as `FileInfo.metadata: Mapping[str, str] | None`. On backends that do not
declare `USER_METADATA`, `FileInfo.metadata` is always `None`.

**Formal coverage:** encoded in `BackendContract.dfy` as a `Write`
postcondition pinning `fs[path].info.metadata` to the same value that
`WriteResult.metadata` carries, under the same `HasUserMetadata ∧
CapUserMetadata in capabilities` condition. Since `GetFileInfo`'s
postcondition is `r.value == fs[path].info`, the round-trip is
structural: what `Write` stores is what `GetFileInfo` returns.
Verified in `MemoryBackend.dfy`. Python backstop in
`tests/backends/test_conformance.py::TestWriteResultConformance`
(`test_metadata_round_trips_via_get_file_info`,
`test_file_info_metadata_none_when_capability_absent`). See ID-151.

## ext.write invariants

WR-014..WR-017 have been moved to
[`046-ext-write.md`](046-ext-write.md) under the `EW-` prefix per the
one-spec-per-extension convention (ADR-0008).  Cross-reference stubs are
kept here for traceability.

## WR-014: ext.write.write_with_hash Returns Digest

**Moved to [EW-001](046-ext-write.md#ew-001-was-wr-014-write_with_hash-returns-digest).**

## WR-015: ext.write.write_with_hash Works on Every WRITE Backend

**Moved to [EW-002](046-ext-write.md#ew-002-was-wr-015-write_with_hash-works-on-every-write-backend).**

## WR-016: open_atomic_with_hash Requires ATOMIC_WRITE

**Moved to [EW-003](046-ext-write.md#ew-003-was-wr-016-open_atomic_with_hash-requires-atomic_write).**

## WR-017: open_atomic_with_hash Exposes result After Exit

**Moved to [EW-004](046-ext-write.md#ew-004-was-wr-017-open_atomic_with_hash-exposes-result-after-exit).**

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
