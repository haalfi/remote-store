# RFC-0011: WriteResult — Native Write Metadata and Opt-In Hashing

## Status

Implemented

## Summary

Replace the `None` return from `Store.write*()` with a `WriteResult`
dataclass carrying whatever metadata the backend already produced for
free during the write — `etag`, `version_id`, `last_modified`, `size`,
and (on Azure) a `digest` echoing the client-supplied MD5 as
`ContentDigest("md5", …)`. A new quality flag
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
   stream adds a wrapper to every write path, sync and async, plus
   per-byte CPU cost. Most callers don't need it. Saga consumers do
   — but they can ask.

The right design treats these as two separate features with two
separate cost models, not one tier-stack that makes every caller pay
the streaming-hash cost so saga consumers don't have to type
`write_with_hash`.

### What each backend's SDK exposes

The proposal is shaped by what the SDKs return, not what we wish
they returned:

| Backend                 | Native on write response                                                                | User metadata accepted | Server-side content hash             |
| ----------------------- | --------------------------------------------------------------------------------------- | ---------------------- | ------------------------------------ |
| Azure Blob              | `etag`, `last_modified`, `version_id`, MD5 when client supplied it | yes (`metadata=`)      | client-supplied MD5 surfaced as `digest=ContentDigest("md5", …)` via `ContentSettings(content_md5=…)` or `validate_content=True`; stored (not computed) server-side |
| Azure DataLake (HNS)    | `etag`, `last_modified`                                            | yes (`metadata=`)      | client-supplied MD5 surfaced as `digest=ContentDigest("md5", …)` via `ContentSettings`; same storage semantics as Azure Blob |
| S3 (boto3 `put_object`) | `ETag`, `VersionId`. Single-PUT `ETag` is the MD5 of the body. Multipart `ETag` is `"<md5-of-part-md5s>-<N>"` — **not** a content hash. | yes (`Metadata=`) | opt-in only (`ChecksumAlgorithm`)    |
| S3 via `s3fs.pipe_file` | same as boto3 — but s3fs **discards** the response                                      | only via raw boto3     | discarded                            |
| S3 via PyArrow          | nothing — PyArrow output stream eats the PUT response                                   | --                     | --                                   |
| SFTP (paramiko)         | `SFTPAttributes` from `SFTPClient.put()` / `putfo()` — exposes `st_size`, `st_mtime`, `st_mode`. No etag/version concept in the protocol. | -- | -- |
| Local                   | nothing — `os.stat` for size + mtime after write                                        | --                     | --                                   |
| Memory                  | trivially, we own the storage                                                           | yes                    | trivially                            |
| HTTP                    | write not supported today                                                               | --                     | --                                   |
| SQLAlchemy BLOB         | rowcount only; we already track `size` and `updated_at`; row version doubles as `version_id` | yes — via a dedicated `user_metadata` JSON column (see SQLBlob storage note below) | client-side only         |

**The free wins.** Azure and S3 hand us `etag` and `version_id` on
every write today. Surfacing them costs zero round trips and zero
new bytes on the wire. Memory and SQLBlob can synthesise everything
trivially. SFTP and Local cannot surface `etag` / `version_id`
(protocol-level absent) and so do not declare `WRITE_RESULT_NATIVE`,
even though SFTP's `SFTPAttributes` and Local's post-write `stat()`
can populate `size` and `last_modified` — a partial return is still
`source="basic"` per the capability table. S3-PyArrow genuinely
returns nothing (the output stream eats the PUT response).

## Goals

- Surface native write metadata (`etag`, `version_id`,
  `last_modified`, `size`, and backend-echoed content hashes via
  `digest`) on every backend that produces it, with zero added round
  trips and zero added bytes on the wire.
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
        digest: Content digest — client-computed via
            ``ext.write.write_with_hash``, or a backend-echoed hash
            from the write response (e.g., Azure ``content_md5``
            surfaced as ``ContentDigest("md5", …)``). ``None`` on the
            default write path for all v1 backends.
        etag: Backend-provided change tag. ``None`` when the backend
            does not produce one. **Not a content hash** on every
            backend — on S3, single-PUT ETags are the MD5 of the
            body but multipart ETags have the form
            ``"<md5-of-part-md5s>-<N>"``. Callers doing content
            verification should use ``digest`` from
            ``ext.write.write_with_hash`` rather than comparing
            ``etag`` to a client-computed hash.
        version_id: Backend-provided immutable version identifier.
            ``None`` when the backend does not version objects.
        last_modified: Server timestamp from the write response.
            ``None`` when the backend's write response omits it; call
            ``Store.head(path)`` if needed.
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
    source: Literal["native", "basic", "sidecar"] = "basic"
    digest: ContentDigest | None = None
    etag: str | None = None
    version_id: str | None = None
    last_modified: datetime | None = None
    metadata: Mapping[str, str] | None = None
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
    # Azure's upload_blob response does not include "size" — measure
    # the body directly (bytes: len; BinaryIO: counting wrapper).
    size = _measure(content)
    response = blob_client.upload_blob(content, overwrite=overwrite, metadata=metadata)
    return WriteResult(
        path=RemotePath(path),  # backend-native; Store rebases to store-relative
        size=size,
        etag=response["etag"],
        version_id=response.get("version_id"),
        last_modified=response["last_modified"],
        # Azure returns content_md5 as a base64-encoded bytes object when the
        # caller supplied one; convert to hex for ContentDigest, or None.
        digest=(
            ContentDigest("md5", response["content_md5"].hex())
            if response.get("content_md5") else None
        ),
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
| `SFTPBackend`      | no — no etag/version in protocol; `size` and `last_modified` are available from `SFTPAttributes` but the capability requires the full rich set | `"basic"` |
| `LocalBackend`     | no — no write-time metadata     | `"basic"`          |

S3's bytes-path switches from `s3fs.pipe_file` (which discards the
response) to `boto3.put_object` directly to keep the response.
The streaming path cannot use `boto3.upload_fileobj` —
`upload_fileobj` delegates to `boto3.s3.transfer.S3Transfer` and
returns `None`, discarding the final `CompleteMultipartUpload`
ETag/VersionId just as `s3fs.pipe_file` does. Two viable shapes:

1. **Direct low-level multipart** when the stream exceeds a
   configurable threshold: `create_multipart_upload` →
   `upload_part` per chunk → `complete_multipart_upload`. We own
   the response at the end and build the `WriteResult` from it.
   Below the threshold, read the body into memory and use
   `put_object`.
2. **Narrow `WRITE_RESULT_NATIVE`** to the bytes path only; declare
   the streaming path `"basic"` with just `path` and `size`. Saga
   consumers needing `etag`/`version_id` after a streaming write
   then call `Store.head(path)`.

The implementation picks between (1) and (2); spec 045 nails it
down. Both add `boto3` as an explicit `s3` extras dependency rather
than relying on the existing transitive from `s3fs`. See also the
`WriteResult.etag` docstring note below: the multipart `ETag` has
format `"<md5-of-part-md5s>-<N>"`, not a content hash — saga
consumers must use `digest` from `ext.write.write_with_hash` for
content verification above the multipart threshold.

`Capability.WRITE_RESULT_NATIVE` is added to the "Quality flags"
section of the `Capability` enum docstring, alongside the existing
three.

### `Capability.USER_METADATA` — strict gate

A separate capability that gates the `metadata=` kwarg on `write*`.
**Strict gate** — passing `metadata=` to a backend that does not
declare `USER_METADATA` raises `CapabilityNotSupported` before any
I/O. Same rationale as AW-002 (atomic writes never silently
degrade): silent drop is the worst correctness pattern for saga
consumers, who treat "write returned" as "metadata durable." See
also ADR-0026, which names the strict-gate-on-kwarg pattern.

Backend declarations for v1:

| Backend            | Declares `USER_METADATA`?                          |
| ------------------ | -------------------------------------------------- |
| `AzureBackend`     | yes — `metadata=` kwarg                            |
| `S3Backend`        | yes — boto3 `Metadata=`                            |
| `MemoryBackend`    | yes                                                |
| `SQLBlobBackend`   | yes — via a dedicated `user_metadata` JSON column (see below) |
| `S3PyArrowBackend` | no                                                 |
| `SFTPBackend`      | no                                                 |
| `LocalBackend`     | no                                                 |
| `HTTPBackend`      | no — write unsupported today                       |

`metadata` is `Mapping[str, str]`. Validation happens in the Store
layer (one place, not seven) **before** capability dispatch:

- Keys are non-empty ASCII, no leading underscore.
- Values are strings.
- `sum(len(k.encode("ascii")) + len(v.encode("utf-8")) for k, v in metadata.items()) ≤ 2048`.
  This measures the payload bytes only — not HTTP-header framing or
  backend-specific prefixes like `x-amz-meta-`. The bound matches the
  narrowest portable limit (S3's 2 KB user-metadata cap) while giving
  the validator a deterministic, backend-agnostic formula.

Validation failures raise `ValueError` with the offending key/value.

`Capability.USER_METADATA` is added to the gated-method section of
the `Capability` enum docstring, with explicit "raises
`CapabilityNotSupported` before I/O" language.

`FileInfo` gains a typed `metadata: Mapping[str, str] | None = None`
field (rather than stuffing into `extra`) so user metadata
round-trips cleanly through `get_file_info()` on backends that
declare `USER_METADATA`.

#### SQLBlob storage note

`SQLBlobBackend` stores user metadata in a **dedicated** `user_metadata`
column (JSON-typed; `sa.Text` with JSON payload on SQLite, `JSONB` on
Postgres where available), not in the existing `extra` column. Two
reasons:

1. **Type mismatch.** `FileInfo.extra` is `dict[str, object]` — a
   catch-all for backend-internal annotations. `FileInfo.metadata` is
   `Mapping[str, str]` (validated per WR-011). Co-locating them in one
   column would require a sub-key discipline (`extra["_user_metadata"]`)
   that leaks the `USER_METADATA` schema into every existing `extra`
   consumer.
2. **Migration surface.** A dedicated column lets existing rows keep
   `user_metadata IS NULL` until they are re-written, and lets future
   queries filter on user metadata without a JSON path expression over
   `extra`.

The schema change is additive (new nullable column); `_optional_columns`
gains `"user_metadata"` alongside `"extra"`.

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
- A caller on a read-only backend (no `WRITE`, has `METADATA`)
  wants the `WriteResult` shape for a file it did not write —
  `head()` is gated on `METADATA` only.

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
) -> Iterator[HashingAtomicWriter]:
    """Streaming atomic write with hash; ``writer.result`` after exit.

    Yields a ``HashingAtomicWriter`` — a ``ChecksumWriter`` subclass
    defined in ``ext.write`` that adds a ``.result: WriteResult | None``
    attribute. ``writer.result`` is ``None`` during the ``with`` block;
    on successful exit it holds the ``WriteResult`` (with ``digest``
    populated from the streaming hash). On exception exit, ``.result``
    remains ``None`` and the exception propagates unchanged. See WR-017.
    """
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
| WR-003 | `WriteResult.size` equals the byte length of the written content on every backend. For `bytes`/`str` input, `size` is computed from the payload directly (zero added cost). For non-seekable `BinaryIO` input on backends without `WRITE_RESULT_NATIVE`, `size` is obtained by counting bytes as they stream or via a post-write `stat()` call — costs one local `stat` on `LocalBackend`, zero extra round trips on `SFTPBackend` (paramiko returns bytes transferred). |
| WR-004 | If the backend declares `WRITE_RESULT_NATIVE`, every successful `Store.write*()` returns `WriteResult.source == "native"`; otherwise `source == "basic"`. |
| WR-005 | When `source == "basic"`, only `path` and `size` are guaranteed populated; the rich fields `digest`, `etag`, `version_id`, and `last_modified` are `None`. `metadata` is governed independently by WR-012 regardless of `source`. |
| WR-006 | `WriteResult.source == "sidecar"` only when constructed by `Store.head()`.                                        |
| WR-007 | The default write path (`Store.write*()` without `ext.write`) returns `WriteResult.digest is None` on every backend that does not surface a server-verified or backend-echoed content hash on its write response. |
| WR-008 | `Store.head(path) -> WriteResult` is gated on `Capability.METADATA` only. It is **not** gated on `WRITE` — callers may invoke it on read-only backends that declare `METADATA`. Raises `NotFound` if the path doesn't exist; raises `CapabilityNotSupported` if the backend lacks `METADATA`. |
| WR-009 | `Capability.WRITE_RESULT_NATIVE` is a quality flag — it does not gate any method.                                 |
| WR-010 | `Capability.USER_METADATA` gates the `metadata=` kwarg. Passing `metadata=` to a non-declaring backend raises `CapabilityNotSupported` before any I/O. |
| WR-011 | `metadata` is `Mapping[str, str]`. Keys must be non-empty ASCII without a leading underscore; values must be strings; `sum(len(k.encode("ascii")) + len(v.encode("utf-8")))` over all entries must be ≤ 2048. Violations raise `ValueError` before any I/O. |
| WR-012 | When `metadata=` is passed, `WriteResult.metadata` echoes the caller's mapping verbatim (same keys, same values, same case — no normalisation). Backend-side normalisation is observable only through `FileInfo.metadata` on a subsequent `get_file_info()`. |
| WR-013 | User metadata survives round-trip through `get_file_info()` on backends declaring `USER_METADATA`, accessible as `FileInfo.metadata`. |
| WR-014 | `ext.write.write_with_hash()` returns a `WriteResult` with `digest` populated from a streaming hash; the underlying `source` value is preserved. |
| WR-015 | `ext.write.write_with_hash()` works on every backend declaring `WRITE` — the hash is always computed client-side regardless of `WRITE_RESULT_NATIVE`. No additional capability is required beyond what `Store.write()` already requires. |
| WR-016 | `ext.write.open_atomic_with_hash()` requires `Capability.ATOMIC_WRITE` on the underlying store (inherited from `Store.open_atomic`, SAW-002); absence raises `CapabilityNotSupported` before any I/O. |
| WR-017 | `ext.write.open_atomic_with_hash()` yields a `HashingAtomicWriter` (a `ChecksumWriter` subclass in `ext.write` adding `.result: WriteResult \| None`). `.result` is `None` during the `with` block; populated on successful exit; remains `None` on exception exit (exception propagates unchanged). |
| WR-018 | The proxy stack (`ext.observe`, `ext.cache`, `_proxy`) widens `write*` override return types from `None` to `WriteResult` and forwards the underlying `WriteResult` unchanged. `Store.head()` is added to the same proxies and forwards to the wrapped store. |
| WR-019 | The post-operation `StoreEvent` emitted by `ext.observe` after `write`, `write_text`, and `write_atomic` carries the returned `WriteResult` under `StoreEvent.metadata["write_result"]`. The pre-operation event is unchanged. |

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

- Forces every caller to pay streaming-hash CPU cost even when they
  don't need the hash. Saga consumers do — most callers don't.
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

Rejected. Same reasoning as AW-002: silent degradation is a
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

> **Scope of this PR.** This RFC PR is **spec-only**: it lands the RFC
> and the `WR-` / `OBS-015` / `WTXT-004` / `MOD-003` spec invariants.
> User-facing surfaces that describe release output (`FEATURES.md`,
> `CHANGELOG.md`) and documentation pages (`docs-src/api/*`, new
> `guides/write-integrity.md`) are **deferred to the implementation PR**
> that lands the behaviour; this PR intentionally does not edit them.
> They appear in the ripple-check below as forward-looking ripple targets,
> not as PR deliverables. Tracked under ID-146 in `sdd/BACKLOG.md`.

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

- Default write path with `bytes` / `str` input: negligible added
  cost (one frozen-dataclass construction).
- Default write path with streaming `BinaryIO` input on `"basic"`
  backends: adds a post-write `size` measurement (one `os.stat` on
  `LocalBackend`; paramiko's SFTP bytes-transferred counter on
  `SFTPBackend`). See WR-003.
- Backends with `WRITE_RESULT_NATIVE` (Azure, S3, Memory, SQLBlob):
  zero new bytes on the wire, zero added round trips. The SDK
  response was produced anyway; we now wrap it.
- `ext.write.write_with_hash`: streaming sha256 has non-trivial CPU
  cost; callers who don't need a hash never pay it. Absolute
  throughput depends on hardware and input size — no figures are
  quoted here; per-release benchmark results ship separately.

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
  non-ASCII, oversize, empty key, non-string value. An empty
  `Mapping[str, str]` is accepted — it is semantically
  indistinguishable from `metadata=None`, which WR-010 allows — and
  so is not a negative case.
- `ext.write.write_with_hash` round-trip test on every backend:
  written hash matches a re-stream hash on a 10 MiB payload
  generated from a **fixed seed** (`random.Random(seed=0xB17ED1E5).randbytes(10 * 1024 * 1024)`
  or equivalent) so the test is deterministic across runs and CI
  shards. Marked as an **integration** test (`@pytest.mark.integration`)
  on backends requiring a live service (Azure, S3); unit-tier on
  `LocalBackend`, `MemoryBackend`, and `SQLBlobBackend`.

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
  `FileInfo` optional fields list in spec 001) amended to include
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
  (no holder, no tuple). Captured normatively in WR-018 (spec 045).
  For `ext.observe` specifically: the post-operation `StoreEvent`
  emitted after `write`, `write_text`, and `write_atomic` carries
  the returned `WriteResult` under
  `StoreEvent.metadata["write_result"]`. `StoreEvent.metadata`
  keeps its existing `dict[str, Any]` type — access to
  `event.metadata["write_result"]` is explicitly untyped; callers
  narrow with `isinstance(..., WriteResult)` if static checking is
  required. A typed field on `StoreEvent` is deferred (see Open
  Questions). The pre-operation event is unchanged. Captured
  normatively in WR-019 (spec 045). `ext.cache` does not cache
  `WriteResult` — it forwards the write and invalidates the cache
  entry as today. **Spec 019 (ext.observe)** is amended in this PR:
  OBS-015 (new) captures `write_result` injection into the
  post-operation `StoreEvent`; OBS-001 gains `"head"` and
  `"write_text"` in its operation list; OBS-003a is updated so the
  hook-to-operation mapping covers `write_text` (on `on_write`) and
  `head` (on `on_list`). **Spec 023 (ext.cache)** receives no
  per-spec amendments in this PR — the proxy forwarding contract
  is fully captured by WR-018 at the Store-API level, and will be
  reflected in spec 023 only if cache-specific invariants become
  necessary during implementation.
- **Documentation.** `docs-src/api/models.md` (WriteResult),
  `docs-src/api/capabilities.md` (two new capabilities),
  `docs-src/api/store.md` (return types + `head()`),
  `guides/custom-backend-guide.md` (method reference table updated),
  new `guides/write-integrity.md` covering when to use
  `ext.write.write_with_hash` vs. `WriteResult.etag` for saga
  consumers.
- **Dependencies.** `boto3` added explicitly to the `s3` extra in
  `pyproject.toml` (was previously transitive via `s3fs`). Per the
  "A dependency" row of `sdd/CLAUDE-REFERENCE.md`, this also ripples
  to `README.md` (install instructions — `pip install
  'remote-store[s3]'` wording unchanged, but the extras table needs
  `boto3` listed explicitly), and `docs-src/api/backends.md` /
  `docs-src/guides/s3.md` prerequisites.
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

4. **Typed `StoreEvent.write_result` field?** Subscribers currently
   read `event.metadata["write_result"]` as `Any`. A dedicated
   `write_result: WriteResult | None` field on `StoreEvent` would
   give static guarantees, at the cost of a `StoreEvent` shape
   change that ripples into `ext.observe` public API and every
   subscriber. Deferred: accept the untyped access in v1; revisit
   if subscriber type-safety becomes a pain point.

## References

- Spec 045 (WriteResult — WR-001..WR-019): `sdd/specs/045-write-result.md`.
  `@pytest.mark.spec("WR-NNN")` traceability applies per
  `sdd/000-process.md` Rule 2.
- Spec 001 (Store API — STORE-008 amendment for `head` and `write_text`; MOD-003 amendment for `FileInfo.metadata`): `sdd/specs/001-store-api.md`
- Spec 003 (Backend Adapter Contract — CAP-001, CAP-007 amendment, BE write return types): `sdd/specs/003-backend-adapter-contract.md`
- Spec 029 (Async Store API — async write return types, ASYNC-052a return-type widening): `sdd/specs/029-async-store-backend-api.md`
- Spec 030 (write_text — WTXT-001 return-type widening): `sdd/specs/030-write-text.md`
- Spec 035 (ContentDigest — used by `WriteResult.digest`): `sdd/specs/035-content-digest.md`
- Spec 007 (atomic writes — referenced for AW-002 strict-gate precedent): `sdd/specs/007-atomic-writes.md`
- Spec 022 (streaming atomic writes — SAW-001 / SAW-013 unchanged, SAW-002 gate inherited by `open_atomic_with_hash`): `sdd/specs/022-streaming-atomic-writes.md`
- ADR-0008 (extension architecture — pattern for `ext.write`): `sdd/adrs/0008-extension-architecture.md`
- ADR-0012 (async store/backend API): `sdd/adrs/0012-async-store-backend-api.md`
- Existing hashing wrappers: `src/remote_store/ext/streams.py`
  (`ChecksumWriter`, `ChecksumReader`). `HashingAtomicWriter`
  (`ChecksumWriter` subclass adding `.result`) lands in
  `src/remote_store/ext/write.py` alongside `open_atomic_with_hash`.
- Models: `src/remote_store/_models.py` (`FileInfo`, `ContentDigest`)
- Capability enum: `src/remote_store/_capabilities.py`
- Azure SDK upload response: https://learn.microsoft.com/python/api/azure-storage-blob/azure.storage.blob.blobclient#azure-storage-blob-blobclient-upload-blob
- S3 PutObject + checksums: https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html
