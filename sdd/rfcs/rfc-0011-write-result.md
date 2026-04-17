# RFC-0011: WriteResult — Native Write Metadata and Opt-In Hashing

## Status

Draft

## Summary

Replace the `None` return from `Store.write*()` with a `WriteResult`
dataclass carrying whatever metadata the backend already produced for
free during the write — `etag`, `version_id`, `last_modified`, `size`,
and (on Azure) `content_md5`. A new quality flag
`Capability.WRITE_RESULT_NATIVE` advertises which backends fill the
rich fields; backends without it return a `WriteResult` containing
just `path` and `size`. A separate strict-gate capability
`Capability.USER_METADATA` adds an opt-in `metadata=` kwarg for
backends that can store user-supplied key/value pairs natively
(Azure, S3, Memory, SQLBlob). Callers that need a content hash use
the new `ext.write` extension (`write_with_hash`,
`open_atomic_with_hash`), which wraps the existing
`ext.streams.ChecksumWriter` — they pay the streaming-hash cost only
when they ask for it.

## Motivation

`Store.write*()` returns `None` today. Useful metadata is either
already in the SDK response (Azure and S3 return `etag`, `version_id`,
`last_modified`) or computable in flight from the byte stream
(content hash). We discard it all.

Two distinct consumer needs are tangled together in that "we should
return something" intuition, and untangling them is the whole
proposal:

1. **Native metadata is free.** `BlobClient.upload_blob()` returns a
   dict with `etag`, `version_id`, `last_modified`, `content_md5`.
   Wrapping it in a `WriteResult` is zero-cost — the SDK already
   computed it. The only reason callers don't have it today is that
   we throw it away at the backend boundary.
2. **Content hashes are not free.** Computing sha256 over the byte
   stream costs ~2 ns/byte and adds a wrapper to every write path,
   sync and async. Most callers don't need it. Saga consumers do —
   but they can ask.

The right design treats these as two separate features with two
separate cost models, not one tier-stack that makes every caller pay
the streaming-hash cost so saga consumers don't have to type
`write_with_hash`.

### What each backend's SDK exposes

The proposal is shaped by what the SDKs return, not what we wish
they returned:

| Backend                 | Native on write response                                                                | User metadata accepted | Server-side content hash             |
| ----------------------- | --------------------------------------------------------------------------------------- | ---------------------- | ------------------------------------ |
| Azure Blob              | `etag`, `last_modified`, `version_id`, `content_md5`                                    | yes (`metadata=`)      | yes — `content_md5`, server-verified |
| Azure DataLake (HNS)    | `etag`, `last_modified`                                                                 | yes (`metadata=`)      | MD5 via `ContentSettings`            |
| S3 (boto3 `put_object`) | `ETag`, `VersionId`                                                                     | yes (`Metadata=`)      | opt-in only (`ChecksumAlgorithm`)    |
| S3 via `s3fs.pipe_file` | same as boto3 — but s3fs **discards** the response                                      | only via raw boto3     | discarded                            |
| S3 via PyArrow          | nothing — PyArrow output stream eats the PUT response                                   | --                     | --                                   |
| SFTP (paramiko)         | nothing — SFTP has no etag/version concept                                              | --                     | --                                   |
| Local                   | nothing — `os.stat` for size + mtime after write                                        | --                     | --                                   |
| Memory                  | trivially, we own the storage                                                           | yes                    | trivially                            |
| HTTP                    | write not supported today                                                               | --                     | --                                   |
| SQLAlchemy BLOB         | rowcount only; we already track `size` and `updated_at`; row version doubles as `version_id` | yes (existing `extra` JSON column) | client-side only         |

**The free wins.** Azure and S3 hand us `etag` and `version_id` on
every write today. Surfacing them costs zero round trips and zero
new bytes on the wire. Memory and SQLBlob can synthesise everything
trivially. The remaining backends (Local, SFTP, S3-PyArrow) return a
minimal `WriteResult` with just `path` and `size`.

## Goals

- Surface native write metadata (`etag`, `version_id`,
  `last_modified`, `content_md5`, `size`) on every backend that
  produces it, with zero added round trips and zero added bytes on
  the wire.
- Give saga consumers a one-call API
  (`ext.write.write_with_hash`) for verified content hashes when
  they actually need them.
- Keep the default write path's runtime cost identical to today's
  `None`-returning write, modulo dataclass construction.
- No silent surprises with user metadata. If a backend cannot store
  it, the call raises before any I/O.

## Non-goals

- **Mandatory client-side hashing on every write.** This was the
  v1 design and is explicitly rejected here — see Alternatives
  Considered.
- **Server-side sha256 verification on S3 by default.** Passing
  `ChecksumAlgorithm="SHA256"` to every S3 PUT changes wire
  behaviour and may interact with bucket policies. Off by default;
  available as an opt-in flag on `ext.write.write_with_hash`.
- **Local xattr / SFTP extended-attribute user metadata.** Backends
  without native metadata channels do not declare `USER_METADATA`
  in v1.
- **Tier-3 portable extension that always populates every field.**
  The `ext.write` extension is opt-in and scoped to hashing.
  Callers wanting "every field populated" combine the default
  `WriteResult` with `Store.head(path)` if they need
  `last_modified` on S3 (which doesn't return it from PutObject).

## Proposal

### `WriteResult` shape

```python
# src/remote_store/_models.py

@dataclasses.dataclass(frozen=True)
class WriteResult:
    """Immutable summary of a completed write.

    Attributes:
        path: Normalized remote path written, store-relative.
        size: Bytes written. Always populated.
        digest: Verified content digest. ``None`` unless the caller
            opted into a streaming hash (``ext.write.write_with_hash``)
            or the backend surfaces a server-verified digest on its
            write response.
        etag: Backend-provided change tag. ``None`` when the backend
            does not produce one.
        version_id: Backend-provided immutable version identifier.
            ``None`` when the backend does not version objects.
        last_modified: Server timestamp from the write response.
            ``None`` when the backend's write response omits it; call
            ``Store.head(path)`` if needed.
        content_md5: Backend-verified MD5. ``None`` when the backend
            does not return one on write.
        metadata: Echo of the user metadata that was stored. ``None``
            when ``metadata=`` was not passed or the backend does not
            declare ``USER_METADATA``.
        source: Provenance of the rich fields.
            ``"native"`` -- populated from the backend's write
            response.
            ``"basic"`` -- the backend produced no rich fields; only
            ``path`` and ``size`` are guaranteed.
            ``"sidecar"`` -- constructed post-write from
            ``Store.get_file_info()`` via ``Store.head()``.

    The ``source`` field tells callers what they can trust.
    A ``"native"`` ``etag`` is the backend's confirmation of what it
    stored. A ``"basic"`` result means the backend cannot confirm
    anything beyond size; if you need more, opt in via
    ``ext.write.write_with_hash`` or call ``Store.head(path)`` after.
    """

    path: RemotePath
    size: int
    digest: ContentDigest | None = None
    etag: str | None = None
    version_id: str | None = None
    last_modified: datetime | None = None
    content_md5: str | None = None
    metadata: Mapping[str, str] | None = None
    source: Literal["native", "basic", "sidecar"] = "basic"
```

`digest` reuses the existing `ContentDigest` model from spec 035 for
shape consistency with `FileInfo.digest`.

### Default write path — zero added overhead

`Store.write()`, `Store.write_text()`, and `Store.write_atomic()`
return `WriteResult` instead of `None`. The Store layer adds no
hashing wrapper, no proxying, no extra round trip. It calls
`Backend.write*()` exactly as today, and the backend constructs the
`WriteResult` from whatever it knows:

```python
# Backends with WRITE_RESULT_NATIVE -- Azure example
def write(self, path, content, *, overwrite=False, metadata=None) -> WriteResult:
    response = blob_client.upload_blob(content, overwrite=overwrite, metadata=metadata)
    return WriteResult(
        path=RemotePath(path),  # backend-native; Store rebases to store-relative
        size=response.get("size", _measure_after(content)),
        etag=response["etag"],
        version_id=response.get("version_id"),
        last_modified=response["last_modified"],
        content_md5=response.get("content_md5"),
        metadata=metadata,
        source="native",
    )

# Backends without native metadata -- Local example
def write(self, path, content, *, overwrite=False, metadata=None) -> WriteResult:
    full = self._resolve(path)
    size = _write_and_count(full, content, overwrite=overwrite)
    return WriteResult(
        path=RemotePath(path),  # backend-native; Store rebases to store-relative
        size=size,
        source="basic",
    )
```

Backends construct `WriteResult` with the backend-native path. The Store
layer rebases `WriteResult.path` into the store's root the same way it
rebases `FileInfo.path` returned from `get_file_info()` today. Backends
do not see and do not need to know the store root.

### `Capability.WRITE_RESULT_NATIVE` — quality flag

A new quality flag in the same family as `ATOMIC_MOVE`,
`SEEKABLE_READ`, `LAZY_READ`. It does not gate any method.
`Store.write()` works on every backend. The flag advertises **which
fields you can trust on the result**:

| Backend            | Declares `WRITE_RESULT_NATIVE`? | Resulting `source` |
| ------------------ | ------------------------------- | ------------------ |
| `AzureBackend`     | yes                             | `"native"`         |
| `S3Backend`        | yes                             | `"native"`         |
| `MemoryBackend`    | yes                             | `"native"`         |
| `SQLBlobBackend`   | yes                             | `"native"`         |
| `S3PyArrowBackend` | no — PyArrow eats the response  | `"basic"`          |
| `SFTPBackend`      | no — protocol has no etag       | `"basic"`          |
| `LocalBackend`     | no — no write-time metadata     | `"basic"`          |

S3's bytes-path switches from `s3fs.pipe_file` (which discards the
response) to `boto3.put_object` directly to keep the response. The
streaming path uses `boto3.upload_fileobj`. Both paths add `boto3`
as an explicit `s3` extras dependency rather than relying on the
existing transitive from `s3fs`.

`Capability.WRITE_RESULT_NATIVE` is added to the "Quality flags"
section of the `Capability` enum docstring, alongside the existing
three.

### `Capability.USER_METADATA` — strict gate

A separate capability that gates the `metadata=` kwarg on `write*`.
**Strict gate** — passing `metadata=` to a backend that does not
declare `USER_METADATA` raises `CapabilityNotSupported` before any
I/O. Same rationale as AW-007 (atomic writes never silently
degrade): silent drop is the worst correctness pattern for saga
consumers, who treat "write returned" as "metadata durable."

Backend declarations for v1:

| Backend            | Declares `USER_METADATA`?                          |
| ------------------ | -------------------------------------------------- |
| `AzureBackend`     | yes — `metadata=` kwarg                            |
| `S3Backend`        | yes — boto3 `Metadata=`                            |
| `MemoryBackend`    | yes                                                |
| `SQLBlobBackend`   | yes — uses existing unused `extra` JSON column     |
| `S3PyArrowBackend` | no                                                 |
| `SFTPBackend`      | no                                                 |
| `LocalBackend`     | no                                                 |
| `HTTPBackend`      | no — write unsupported today                       |

`metadata` is `Mapping[str, str]`. Validation happens in the Store
layer (one place, not seven) **before** capability dispatch:

- Keys are non-empty ASCII, no leading underscore.
- Values are strings.
- Total serialised size ≤ 2 KB (S3's hard limit; applied
  uniformly for portability).

Validation failures raise `ValueError` with the offending key/value.

`Capability.USER_METADATA` is added to the gated-method section of
the `Capability` enum docstring, with explicit "raises
`CapabilityNotSupported` before I/O" language.

`FileInfo` gains a typed `metadata: Mapping[str, str] | None = None`
field (rather than stuffing into `extra`) so user metadata
round-trips cleanly through `get_file_info()` on backends that
declare `USER_METADATA`.

### `Store.head(path) -> WriteResult`

Convenience wrapper that returns `WriteResult` for an existing file
without re-uploading. Delegates to `Store.get_file_info()` so it
inherits path-rebasing and the `METADATA` capability gate:

```python
# src/remote_store/_store.py

def head(self, path: str) -> WriteResult:
    info = self.get_file_info(path)
    return WriteResult(
        path=info.path,
        size=info.size,
        digest=info.digest,
        etag=info.etag,
        last_modified=info.modified_at,
        metadata=info.metadata,
        source="sidecar",
    )
```

Useful when:

- A caller used `open_atomic` (which keeps its existing
  `Iterator[BinaryIO]` contract — no `WriteResult`) and now wants
  the post-write metadata.
- A caller wrote on a `"basic"` backend and wants whatever the
  backend can derive after the fact (mtime, etag if the backend
  has one but doesn't return it on PUT).

`STORE-008` (the exhaustive Store API surface in spec 001) is
amended to include `head` and `write_text`. `write_text` is not
currently enumerated in STORE-008 even though it ships as a public
method; the return-type widening in this RFC is the natural point to
close that gap.

### `open_atomic` — unchanged

`Store.open_atomic()` continues to return `Iterator[BinaryIO]` per
SAW-001 / SAW-013 in spec 022. No tuple-yield, no
`WriteResultHolder`, no signature change. Callers wanting a
`WriteResult` from a streaming atomic write use one of:

- `Store.head(path)` after the `with` block — one HEAD round trip.
- `ext.write.open_atomic_with_hash(store, path, ...)` — wraps the
  stream in `ChecksumWriter` and exposes the result on the context
  manager.

This is a deliberate cost shift: callers who need the
`WriteResult` from a streaming write opt in. Callers who don't
keep the existing zero-overhead path.

### `ext.write` extension — opt-in hashing

A new extension at `src/remote_store/ext/write.py` providing
streaming-hash variants of write and open_atomic. Reuses the existing
`ext.streams.ChecksumWriter` rather than introducing a parallel
implementation.

```python
# src/remote_store/ext/write.py

def write_with_hash(
    store: Store,
    path: str,
    content: bytes | BinaryIO,
    *,
    algorithm: str = "sha256",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult:
    """Write ``content`` and return a ``WriteResult`` with ``digest`` populated.

    The bytes are streamed through ``ext.streams.ChecksumWriter`` so
    no extra round trip and no full-payload buffering are required.
    The returned ``WriteResult`` has the same fields the underlying
    ``store.write()`` would return, plus ``digest`` set from the
    streaming hash. ``source`` is preserved from the underlying write
    (``"native"`` if the backend declares ``WRITE_RESULT_NATIVE``,
    otherwise ``"basic"``); the ``digest`` field is independent of
    ``source`` and always represents the client-computed hash.

    Args:
        store: Target store.
        path: Destination path.
        content: Bytes or readable stream.
        algorithm: Hash algorithm name accepted by ``hashlib.new``.
            Default ``"sha256"``. Single-algorithm only in v1, matching
            the existing ``ChecksumWriter`` signature; multi-algorithm
            multiplex is deferred to a follow-up.
        overwrite: Same semantics as ``Store.write``.
        metadata: Optional user metadata; subject to ``USER_METADATA``
            capability gate.
    """


@contextlib.contextmanager
def open_atomic_with_hash(
    store: Store,
    path: str,
    *,
    algorithm: str = "sha256",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> Iterator[ChecksumWriter]:
    """Streaming atomic write with hash; ``writer.result`` after exit."""
```

`ext.write` activates when the caller imports it. No proxy
wrapping, no dependency on the underlying capability flag. It works
on every backend — it computes the hash client-side regardless.

An async sibling (`aio.ext.write`) follows the same pattern,
streaming through the existing async `ChecksumWriter` analogue
(or its in-process tee — see Open Questions on the async hashing
sibling).

### Async parity

`AsyncStore.write*()` return `WriteResult` with identical semantics.
The aio backends construct `WriteResult` from their async SDK
responses (Azure async, future Graph). The default async path,
like the sync default, performs no extra hashing. Only
`aio.ext.write.write_with_hash` introduces the async tee — and only
the call sites that opt in have to consider the
async-materialise-anti-pattern (BUG-165).

### Spec additions — `045-write-result.md`

Single prefix `WR-` covering both `WriteResult` and `USER_METADATA`
(one-prefix-per-file convention). Conceptually the two are a single
contract — what comes back from a write, including the metadata
echoed back if the caller passed `metadata=`.

| ID     | Requirement                                                                                                       |
| ------ | ----------------------------------------------------------------------------------------------------------------- |
| WR-001 | `Store.write()`, `Store.write_text()`, and `Store.write_atomic()` return `WriteResult` (return-type widening from `None`). |
| WR-002 | `WriteResult.path` is store-relative, matching the rebasing applied to `FileInfo.path` returned from `get_file_info()`. |
| WR-003 | `WriteResult.size` equals the byte length of the written content on every backend.                                |
| WR-004 | If the backend declares `WRITE_RESULT_NATIVE`, every successful `Store.write*()` returns `WriteResult.source == "native"`; otherwise `source == "basic"`. |
| WR-005 | When `source == "basic"`, only `path` and `size` are guaranteed populated; all other rich fields are `None`.      |
| WR-006 | `WriteResult.source == "sidecar"` only when constructed by `Store.head()`.                                        |
| WR-007 | The default write path (`Store.write*()` without `ext.write`) returns `WriteResult.digest is None` on every backend that does not surface a server-verified digest. |
| WR-008 | `Store.head(path) -> WriteResult` raises `NotFound` if the path doesn't exist; raises `CapabilityNotSupported` if the backend lacks `METADATA`. |
| WR-009 | `Capability.WRITE_RESULT_NATIVE` is a quality flag — it does not gate any method.                                 |
| WR-010 | `Capability.USER_METADATA` gates the `metadata=` kwarg. Passing `metadata=` to a non-declaring backend raises `CapabilityNotSupported` before any I/O. |
| WR-011 | `metadata` is `Mapping[str, str]`. Keys must be non-empty ASCII without a leading underscore; values must be strings; total serialized size must be ≤ 2 KB. Violations raise `ValueError` before any I/O. |
| WR-012 | When `metadata=` is passed, `WriteResult.metadata` echoes the stored canonicalised mapping.                       |
| WR-013 | User metadata survives round-trip through `get_file_info()` on backends declaring `USER_METADATA`, accessible as `FileInfo.metadata`. |
| WR-014 | `ext.write.write_with_hash()` returns a `WriteResult` with `digest` populated from a streaming hash; the underlying `source` value is preserved. |
| WR-015 | `ext.write.write_with_hash()` works on every backend — the hash is always computed client-side regardless of `WRITE_RESULT_NATIVE`. |
| WR-016 | `ext.write.open_atomic_with_hash()` exposes the `WriteResult` on the yielded writer's `.result` attribute after successful exit; access before exit raises `RuntimeError`. |

`open_atomic` retains its `Iterator[BinaryIO]` contract (SAW-001 / SAW-013) and does **not** return a `WriteResult`. This is design context, not a new requirement — see "open_atomic — unchanged" above and Alternative E.

Per `sdd/000-process.md` Rule 2, every WR- ID is traceable to at
least one test via `@pytest.mark.spec("WR-NNN")`.

### Backlog item

Tracked as **ID-146** at the top of the "API Surface Enhancements"
section of `sdd/BACKLOG.md`.

## Alternatives Considered

### A. Mandatory streaming hash on every write (the v1 design)

Rejected. The v1 RFC required a `_HashingStream` wrapper between
`Store.write()` and every `Backend.write()` so `WriteResult.sha256`
was always populated. The cost analysis was wrong:

- Forces every caller to pay ~2 ns/byte even when they don't need
  the hash. Saga consumers do — most callers don't.
- Pulls a hashing wrapper into the Store layer, breaking the
  "Store adds no I/O logic" rule (STORE-004).
- Forces a parallel async hashing implementation (`_AsyncHashingStream`)
  with the BUG-165 async-materialise-anti-pattern as a permanent
  sharp edge on the default code path.
- Forces all proxy-stack overrides (`ext.observe`, `ext.cache`,
  `_proxy`) to coordinate around the wrapper.
- Spreads the no-materialisation invariant across the entire write
  surface, where it is hard to assert and easy to regress.

The v2 design moves the hash into `ext.write` where it is opt-in
and lives in one place — the same place `ChecksumWriter` already
lives. None of the above costs are paid on the default path.

### B. Three-tier design with `ext.write` as Tier 3

Rejected. The v1 RFC mirrored ADR-0009's glob three-tier design.
The analogy is wrong: glob has a real Tier 2 (`store.glob()`) that
gives the caller backend-native semantics for an opt-in cost. Write
has nothing to opt into beyond "do you want a hash?" — and that's
one bit, not three tiers. Two states (native fields populated /
not) suffice.

### C. `verify="sha256"` kwarg on `Store.write()` instead of an extension

Rejected. Two reasons:

- Adding hash-related kwargs to the core write surface mixes
  concerns. `Store.write()` is for writing bytes; verification is a
  separable feature.
- `ext.write` can grow (multi-algorithm, digest comparison against
  caller-supplied expected, etc.) without bloating `Store.write()`'s
  signature.

The v1 review found that `ext.streams.ChecksumWriter` already
exists. Putting the wrapper in `ext.write` next to it keeps the
implementation in one place.

### D. `WriteResult.sha256: str` instead of `digest: ContentDigest`

Rejected. `FileInfo.digest` is `ContentDigest | None`. `WriteResult`
serves the symmetric role on the write side. Using a bare `str`
here would create a type schism between read and write metadata
that every saga consumer would have to bridge. `ContentDigest`
also enforces lowercase hex via `__post_init__` (CDG-003), so the
format guarantee is structural rather than asserted.

### E. `open_atomic` returns a tuple-yielding context manager

Rejected. Yielding `(BinaryIO, WriteResultHolder)` would break
every existing `with store.open_atomic(path) as f:` consumer (an
SAW-001 / SAW-013 contract change), require coordinated updates to
every proxy in the ext stack, and create a new public type
(`WriteResultHolder`). The cost-per-benefit is poor: callers
needing a `WriteResult` from a streaming atomic write either call
`Store.head(path)` (one HEAD) or use
`ext.write.open_atomic_with_hash` (no extra round trip, full
result). Both options are cheap and explicit.

### F. Silent fallthrough for `metadata=` on non-declaring backends

Rejected. Same reasoning as AW-007: silent degradation is a
correctness pit for saga consumers. A raised exception forces the
caller to either confirm capability or implement a sidecar
explicitly.

### G. Always pass `ChecksumAlgorithm="SHA256"` to S3 PutObject

Deferred. Server-verified sha256 from S3 is appealing, but it
changes wire behaviour, may interact with bucket policies that
restrict header use, and forces a re-upload on mismatch (which the
caller cannot suppress). Available as an explicit
`server_verify=True` flag on `ext.write.write_with_hash` in a
follow-up; off by default in v1.

## Impact

### Public API

- `WriteResult` added to `remote_store._models` and re-exported from
  `remote_store`.
- `Capability.WRITE_RESULT_NATIVE` and `Capability.USER_METADATA`
  added to `Capability` enum.
- `Store.head()` added to `Store` and `AsyncStore`.
- `Store.write*()` return type widens from `None` to `WriteResult`.
- `FileInfo.metadata: Mapping[str, str] | None = None` field added.
- `ext.write` module added with `write_with_hash` and
  `open_atomic_with_hash`.

### Backwards compatibility

Pre-v1 semver — return-type changes are acceptable in a minor bump.

- Callers writing `store.write(...)` without capturing the return
  value continue to work unchanged (Python ignores returned values).
- Callers writing `result: None = store.write(...)` need to update
  their type annotation; runtime behaviour unaffected.
- The `metadata=` gating raise is genuinely new behaviour, but only
  fires when callers explicitly pass `metadata=`. Pure addition.
- `open_atomic` is unchanged. No SAW-001 / SAW-013 amendment.
- Adding `FileInfo.metadata` requires updating the `test_defaults`
  assertion in `tests/test_models.py` to include the new default.

### Performance

- Default write path: identical runtime cost to today's
  `None`-returning write, modulo dataclass construction (~50 ns).
- Tier-2-equivalent backends (Azure, S3, Memory, SQLBlob): zero new
  bytes on the wire, zero added round trips. The SDK response was
  produced anyway; we now wrap it.
- `ext.write.write_with_hash`: ~2 ns/byte for sha256 (~500 MB/s),
  paid only by callers who opt in.

### Testing

- WR- spec IDs traced via `@pytest.mark.spec("WR-NNN")` per
  `sdd/000-process.md` Rule 2.
- Per-backend write tests gain a `WriteResult` assertion. Conformance
  test: `WriteResult.size` matches actual bytes written across every
  backend (SQLBlob added to the conformance fixture as a prerequisite).
- Capability-matrix test asserts which backends declare
  `WRITE_RESULT_NATIVE` and `USER_METADATA`.
- Negative tests (parametrised) for `metadata=` raising
  `CapabilityNotSupported` on every non-declaring backend.
- MD validation negative tests (parametrised): leading underscore,
  non-ASCII, oversize, empty key, non-string value, empty mapping.
- `ext.write.write_with_hash` round-trip test on every backend:
  written hash matches a re-stream hash on a 10 MiB random payload.

### Ripple-check

Per `sdd/CLAUDE-REFERENCE.md`, this RFC touches:

- **Backends.** All seven gain `WriteResult` returns. Azure, S3,
  Memory, SQLBlob declare `WRITE_RESULT_NATIVE` and `USER_METADATA`.
- **`FEATURES.md`.** Capability matrix updated for both new
  capabilities, per backend.
- **Errors.** No new error types. `CapabilityNotSupported` covers
  the metadata gate.
- **Capabilities.** `WRITE_RESULT_NATIVE` and `USER_METADATA` added
  to `_capabilities.py`. CAP-001 (capability enum) and CAP-007
  (quality-flag list) in spec 003 amended.
- **Models.** `FileInfo.metadata` field added. MOD-003 (the
  `FileInfo` optional fields list in spec 002) amended to include
  `metadata`. `tests/test_models.py` defaults assertion updated.
- **Store API.** `Store.head()` added. `STORE-008` in spec 001
  amended to include it. `Store.write*` return types widened in
  spec 001.
- **Backend ABC.** `Backend.write*()` return types widened in spec
  003 (BE-008 etc.).
- **Async API.** `ASYNC-008` and async write entries in spec 029
  amended to mirror the sync return-type widening.
- **Atomic-write specs.** Spec 007 (AW-) and spec 022 (SAW-) **not
  amended**: `write_atomic` return type widens via WR-001;
  `open_atomic` keeps SAW-001 / SAW-013 contract.
- **Proxy stack (ext.observe, ext.cache, _proxy).** All three need
  return-type widening on `write*` overrides — they currently
  return `None` and must forward the underlying `WriteResult`
  unchanged. `Store.head()` is added to the same proxies and
  forwards to the wrapped store's `head()`. No structural changes
  (no holder, no tuple). For `ext.observe` specifically: the post-
  operation `StoreEvent` emitted after `write`, `write_text`, and
  `write_atomic` carries the returned `WriteResult` under
  `StoreEvent.metadata["write_result"]`. The pre-operation event is
  unchanged. Subscribers can read `event.metadata["write_result"].etag`
  (etc.) without a follow-up HEAD. `ext.cache` does not cache
  `WriteResult` — it forwards the write and invalidates the cache
  entry as today.
- **Documentation.** `docs-src/api/models.md` (WriteResult),
  `docs-src/api/capabilities.md` (two new capabilities),
  `docs-src/api/store.md` (return types + `head()`),
  `guides/custom-backend-guide.md` (method reference table updated),
  new `guides/write-integrity.md` covering when to use
  `ext.write.write_with_hash` vs. `WriteResult.etag` for saga
  consumers.
- **Dependencies.** `boto3` added explicitly to the `s3` extra in
  `pyproject.toml` (was previously transitive via `s3fs`).
- **CHANGELOG.** Added: `WriteResult`, `Store.head`,
  `WRITE_RESULT_NATIVE`, `USER_METADATA`, `FileInfo.metadata`,
  `ext.write`. Changed: `Store.write*` return types from `None` to
  `WriteResult` (with one-line migration note for callers using
  `-> None` annotations).
- **ADR.** One new ADR ratifying the **strict-gate-on-kwarg** pattern
  established by `USER_METADATA` (raise before I/O on unsupported
  capability for an optional kwarg). The three-tier shape from v1 is
  abandoned; ADR-0009 / ADR-0016 do not need amendment.

## Open Questions

1. **Async `ChecksumWriter` sibling.** `ext.streams.ChecksumWriter`
   wraps a sync `BinaryIO`. The aio mirror (`aio.ext.write`) needs
   an async-iterable analogue. Options: (a) add it to `ext.streams`
   alongside `ChecksumWriter`; (b) put it in `aio/ext/streams.py`
   for symmetry with the rest of `aio/`. Either works; (b) follows
   the existing `aio/` mirror convention more cleanly.

2. **`open_atomic_with_hash` writer attribute name.** `.result`
   reads cleanly but conflicts with `concurrent.futures.Future.result`
   in callers' mental models. Alternatives: `.write_result`,
   `.summary`. Minor naming question.

3. **Should `ext.write.write_with_hash` accept an
   `expected: ContentDigest | None` kwarg for built-in verification?**
   Symmetric with `ext.integrity.verify`. Could keep v1 to just
   "compute and return", and let callers do their own comparison;
   or add the kwarg for ergonomic verification. Lean: keep v1 minimal,
   add later if requested.

## References

- Spec (new): `sdd/specs/045-write-result.md`
- Spec 001 (Store API — STORE-008 amendment): `sdd/specs/001-store-api.md`
- Spec 003 (Backend Adapter Contract — CAP-001, CAP-007 amendment, BE write return types): `sdd/specs/003-backend-adapter-contract.md`
- Spec 029 (Async Store API — async write return types): `sdd/specs/029-async-store-backend-api.md`
- Spec 035 (ContentDigest — used by `WriteResult.digest`): `sdd/specs/035-content-digest.md`
- Spec 007 (atomic writes — referenced for AW-007 strict-gate precedent): `sdd/specs/007-atomic-writes.md`
- Spec 022 (streaming atomic writes — SAW-001 / SAW-013 unchanged): `sdd/specs/022-streaming-atomic-writes.md`
- ADR-0008 (extension architecture — pattern for `ext.write`): `sdd/adrs/0008-extension-architecture.md`
- ADR-0012 (async store/backend API): `sdd/adrs/0012-async-store-backend-api.md`
- Existing hashing wrappers: `src/remote_store/ext/streams.py`
  (`ChecksumWriter`, `ChecksumReader`)
- Models: `src/remote_store/_models.py` (`FileInfo`, `ContentDigest`)
- Capability enum: `src/remote_store/_capabilities.py`
- Azure SDK upload response: https://learn.microsoft.com/python/api/azure-storage-blob/azure.storage.blob.blobclient#azure-storage-blob-blobclient-upload-blob
- S3 PutObject + checksums: https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html
