# Microsoft Graph Backend Specification

## Overview

`GraphBackend` implements the `AsyncBackend` ABC against the Microsoft
Graph v1.0 file API, covering OneDrive (personal and business),
SharePoint document libraries, and Teams files. A single instance
targets one drive, identified by an immutable `drive_id`. Items are
addressed by path. Transport is `httpx`; auth is handled by a
token-provider callable (built-in `GraphAuth` helper covers
client-credentials and device-code flows via `msal`).

The module prefix for this spec is **GR**. See [RFC-0010](../rfcs/rfc-0010-graph-backend.md)
for design rationale, SDK evaluation, and onboarding guidance. Related
ADRs: [0021](../adrs/0021-graph-sdk-choice.md) (SDK),
[0022](../adrs/0022-graph-auth-model.md) (auth),
[0023](../adrs/0023-async-monitor-polling.md) (monitor poller),
[0024](../adrs/0024-resource-locked-error.md) (`ResourceLocked`).

**Dependencies:** see [ADR-0021](../adrs/0021-graph-sdk-choice.md) for the locked dependency set.
**Optional extra:** `pip install "remote-store[graph]"`
**Backend name:** `"graph"`

---

## Construction

### GR-001: Constructor Parameters

**Invariant:** `GraphBackend` is constructed with a required
`drive_id` and a required token provider.
**Signature:**
```python
GraphBackend(
    drive_id: str,
    *,
    token_provider: Callable[[], str] | Callable[[], Awaitable[str]],
    base_url: str = "https://graph.microsoft.com/v1.0",
    http_client: httpx.AsyncClient | None = None,
    retry: RetryPolicy | None = None,
    upload_chunk_size: int = 10 * 1024 * 1024,  # 10 MiB
    copy_timeout: float | None = None,
    client_options: dict[str, Any] | None = None,
)
```
**Postconditions:**
- The backend stores configuration but performs no network I/O in
  `__init__`.
- If `http_client` is not supplied, an `httpx.AsyncClient` is created
  lazily on first use and closed by `close()`.
- `upload_chunk_size` is a positive multiple of 320 KiB and strictly
  less than 60 MiB (Graph's per-request ceiling); non-conforming
  values raise `ValueError`.
- `drive_id` is a non-empty string; empty or whitespace-only values
  raise `ValueError`.

### GR-002: Backend Name

**Invariant:** `name` property returns `"graph"`.

### GR-003: Capability Declaration

**Invariant:** `GraphBackend` declares the capabilities `READ`,
`WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `METADATA`, `ATOMIC_WRITE`,
`LAZY_READ`, and `WRITE_RESULT_NATIVE`. It does not declare `GLOB`,
`ATOMIC_MOVE`, `SEEKABLE_READ`, or `USER_METADATA`.
**Rationale:**
- `ATOMIC_WRITE`: small-file `PUT /content` is service-side atomic;
  upload sessions are atomic on commit (see GR-018, GR-019).
- `LAZY_READ`: range reads target `@microsoft.graph.downloadUrl`
  (GR-015) and do not materialise the full file.
- `WRITE_RESULT_NATIVE`: both `PUT /content` and the final upload-session
  chunk response return a full `driveItem` body carrying `size`, `eTag`,
  `lastModifiedDateTime`, and (for SharePoint-backed drives)
  version identifiers. `WriteResult` is populated from that response per
  WR-004 — no post-write `HEAD` round trip needed (see GR-018, GR-019).
- `ATOMIC_MOVE` is withheld because Graph move may go async (GR-027);
  atomicity is not guaranteed.
- `SEEKABLE_READ` is withheld. The Graph content stream is
  forward-only. Sync `Store.read_seekable()` synthesises a seekable
  stream via the spool fallback at the Store layer (ADR-0017);
  `AsyncStore` has no `read_seekable` (ASYNC-061), so there is no
  async surface to declare against. A `Range`-backed implementation
  over `@microsoft.graph.downloadUrl` was considered as a future
  optimisation and declined: SharePoint-backed drives have been
  observed to return the full body (or a non-`416` `4xx`) in
  response to `Range`, so declaring `SEEKABLE_READ` would advertise
  a guarantee the backend cannot honour (see GR-015, GR-017).
- `GLOB` is withheld. Sync callers reach the backend via
  `AsyncBackendSyncAdapter` (ADR-0025) and use `ext.glob` over
  `list_files` (the extension takes a sync `Store`). Async callers
  compose pattern matching over `list_files` themselves until an
  async equivalent of `ext.glob` lands as a separate backlog item.
- `USER_METADATA` is withheld. Graph exposes per-item user properties
  only on SharePoint-backed drives (via `driveItem.listItem.fields`,
  scoped to a backing site list); personal OneDrive has no equivalent
  surface. Declaring `USER_METADATA` would advertise a behaviour that
  varies by drive backing — the exact dishonest-declaration failure
  mode the project guards against. Callers that need the SharePoint
  property bag reach it through `unwrap(httpx.AsyncClient)` (GR-037 —
  async only; sync callers via `AsyncBackendSyncAdapter` get
  `CapabilityNotSupported` per ASYNC-086, since the underlying
  `httpx.AsyncClient` is bound to the adapter's private event loop).
  Because `USER_METADATA` is not declared, the WR-010/WR-011 strict
  gate in the **Store layer** (`Store.write` / `AsyncStore.write` —
  one place, not per-backend) raises `CapabilityNotSupported` on any
  non-empty `metadata=` before `GraphBackend.write` is entered. A
  backend-level rejection mirroring the Store gate is permitted as
  defense-in-depth (and is exercised by the conformance suite when
  the backend is invoked directly without a Store wrapper), but the
  authoritative gate lives at the Store layer per spec 045.

Async monitor polling for `copy` and may-be-async `move` is a
backend-internal technique, not a capability — see ADR-0023.

`open_atomic()` is not declared by `AsyncBackend` (it has no async
equivalent — ASYNC-062); sync callers receive it via
`AsyncBackendSyncAdapter`, which synthesises it as spool-and-flush
over `write_atomic` (ASYNC-085). `head()` is synthesised by `Store`
from `get_file_info()` (GR-013); no backend method is required.

### GR-004: Lazy Connection

**Invariant:** No network call occurs during `__init__`. HTTP client
creation, token acquisition, and drive validation are deferred to
first use.
**Rationale:** Matches the lazy-connection convention shared with
`S3Backend` (S3-004) and `AzureBackend` (AZ-004).

### GR-005: Construction Validation

**Invariant:** `drive_id` must be a non-empty string. `token_provider`
must be callable. `upload_chunk_size` must be a positive multiple of
320 KiB (Graph's alignment requirement) and strictly less than 60 MiB
(Graph rejects any single upload-session chunk PUT at or above that
per-request ceiling). `copy_timeout`, when set, must be a positive
float. Violations raise `ValueError` at construction time.
**Postconditions:** Drive existence and caller permissions are not
validated at construction; they surface on the first operation and
are mapped per GR-028 through GR-033.

---

## Authentication

### GR-006: Client-Credentials Flow

**Invariant:** The bundled `GraphAuth` helper supports OAuth 2.0
client-credentials flow (tenant_id + client_id + client_secret or
client certificate), producing a token provider consumable by
`GraphBackend`.
**Postconditions:** Application permissions must be admin-consented
on the tenant. Tokens acquired via this flow carry app-only claims;
operations that require delegated permissions raise
`PermissionDenied` mapped from `403 accessDenied`.

### GR-007: Device-Code Flow

**Invariant:** `GraphAuth` supports OAuth 2.0 device-code flow for
interactive scenarios. On first use, the user is prompted with a
code and URL; completion yields a token and refresh token cached by
MSAL.
**Postconditions:** The MSAL cache is serialised to a persistent
file; see ADR-0022 § Token caching for the canonical path and
override rules (single source of truth).

### GR-008: Token-Provider Protocol

**Invariant:** `GraphBackend` accepts either `Callable[[], str]` or
`Callable[[], Awaitable[str]]` as its `token_provider`. The backend
invokes the callable lazily — never from `__init__`.
**Postconditions:**
- The returned string is attached to every Graph request as
  `Authorization: Bearer <token>`, except to pre-signed targets that
  carry their own credential: `@microsoft.graph.downloadUrl` (see
  GR-015) and the upload-session `uploadUrl` (see GR-038).
- The callable is re-invoked on `401 InvalidAuthenticationToken`
  responses (GR-029). A second `401` after refresh is mapped to
  `PermissionDenied`.
- `GraphAuth` is one implementation of the protocol; user-supplied
  callables are first-class equivalents (ADR-0022).

---

## Addressing

### GR-009: Path Resolution

**Invariant:** Store paths are `/`-rooted POSIX strings. The backend
resolves them to Graph endpoints of the form
`/drives/{drive_id}/root:{encoded_path}:` for metadata and
`/drives/{drive_id}/root:{encoded_path}:/content` for content.
**Postconditions:** The resolution is pure, deterministic, and does
not issue any network request.

### GR-010: RFC 3986 Segment Encoding

**Invariant:** Each path segment is percent-encoded per RFC 3986
before substitution into the Graph URL. The backend encodes spaces,
`#`, `?`, `+`, and trailing dot characters, which Graph handles
incorrectly otherwise.
**Example:** `/My Folder/file #1.txt` resolves to
`/drives/{drive_id}/root:/My%20Folder/file%20%231.txt:`.
**Raises:** `InvalidPath` for paths containing null bytes or `..`
segments (per PATH-001 through PATH-014).

### GR-011: Item-Id Addressing Deferred

**Invariant:** `GraphBackend` does not accept `item:{id}`-style
addresses in v1. Only path-based addressing is supported.
**Rationale:** Store paths are the user-facing addressing model
across every backend. Item-id mode is deferred to a future RFC; this
spec ID reserves the contract slot so a later addition can reference
`GR-011` as the point of extension.

### GR-057: `GraphUtils.resolve_drive_id` Helper

**Invariant:** The public helper
`GraphUtils.resolve_drive_id(target, *, token_provider,
http_client=None) -> str` resolves a drive id from one of three
target shapes and returns the opaque Graph `drive.id` string for
use as `GraphBackend(drive_id=...)`. `GraphUtils` is a namespace
class with `@staticmethod` helpers, mirroring `SFTPUtils` (see
`src/remote_store/backends/_sftp.py`). The method is a sync
entry point; internally it runs an async resolution under a
private event loop (per ADR-0012 sync-wrapper pattern). An
async counterpart `GraphUtils.aresolve_drive_id(...)` is provided
for callers already in an async context.

**Accepted target shapes:**

1. **OneDrive (personal / business of the authenticated user).**
   The literal string `"me"` resolves the authenticated user's
   default drive via `GET /me/drive`.
2. **SharePoint document library.** A site URL (e.g.
   `https://contoso.sharepoint.com/sites/marketing`), optionally
   followed by a document library name in `(site_url,
   library_name)` tuple form. A bare site URL selects the site's
   default drive (`GET /sites/{site_id}/drive`); the tuple form
   selects a named drive from `GET /sites/{site_id}/drives` by
   matching `drive.name`.
3. **Teams channel.** A `{team_id, channel_id}` mapping (dict with
   those two keys) resolves via `GET /teams/{team_id}/channels/
   {channel_id}/filesFolder` to that channel's backing drive id.

**Raises:**

- `InvalidPath` when `target` does not match any accepted shape or
  when the SharePoint `library_name` does not exist on the site.
- `NotFound` when the site/team/channel id resolves but returns 404
  (deleted or inaccessible).
- `PermissionDenied` when Graph returns 403 for the lookup.
- Other Graph-mapped errors per GR-028..GR-034, GR-045, GR-054.

**Rationale:** Citizen developers rarely have a raw `drive_id` at
hand — they have a SharePoint URL, a Teams channel, or just "my
OneDrive". Exposing the three accepted shapes as one helper keeps
the `GraphBackend` constructor contract simple (`drive_id: str`)
while providing an ergonomic on-ramp. The helper lives in a
namespace class (`GraphUtils`, per SFTPUtils precedent) rather than
on the backend itself so it is testable and usable without
instantiating a full `GraphBackend` first, and so future Graph
configuration helpers (token-cache inspection, scope-resolution
probes, etc.) have a designated home that doesn't crowd the public
top-level namespace.

---

## Read Operations

### GR-012: read()

**Invariant:** `async def read(path)` returns `AsyncIterator[bytes]`
per ASYNC-006 (the `AsyncBackend` ABC contract). The backend streams
the response body from `@microsoft.graph.downloadUrl` via
`httpx.AsyncClient.stream`, yielding chunks as they arrive. Sync
callers reach the backend through `AsyncBackendSyncAdapter`
(ADR-0025), which converts the async iterator to a `BinaryIO` via
the spool-and-pump pattern; that conversion is the adapter's
responsibility, not the backend's.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if
the path names a directory (per BE-021).

### GR-013: get_file_info()

**Invariant:** `get_file_info(path)` returns a `FileInfo` populated
from the Graph `driveItem` body. Field mapping:
- `driveItem.name` → `FileInfo.name`
- `driveItem.size` → `FileInfo.size`
- `driveItem.lastModifiedDateTime` (RFC 3339 string) → parsed to
  `datetime` → `FileInfo.modified_at`
- `driveItem.eTag` → `FileInfo.etag` (stripped of outer quotes and
  lowercased)
- `driveItem.file.mimeType` → `FileInfo.content_type`
- `driveItem.file.hashes` → `FileInfo.extra["graph.file.hashes"]`
  per GR-049
- `FileInfo.metadata` is `None` (`USER_METADATA` is not declared —
  GR-003; the `Mapping[str, str] | None` default per WR-013 applies)
- `FileInfo.digest` is left `None`; the canonical-digest selection
  among Graph's three hash variants is reserved for a future
  `ext.integrity` fast-path (GR-049)

**Postconditions:** Used unchanged by `Store.head()`, which wraps
`get_file_info` to produce a `WriteResult` with `source="sidecar"`
per WR-006 — no Graph-specific work is required.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if
the path names a folder.

### GR-014: list_files(), list_folders(), iter_children()

**Invariant:** `list_files(path, recursive=False)` returns
`AsyncIterator[FileInfo]`, `list_folders(path)` returns
`AsyncIterator[FolderEntry]`, and `iter_children(path)` returns
`AsyncIterator[FileInfo | FolderEntry]` per BE-014, BE-015, BE-026 (and
their async ASYNC-* equivalents in spec 029). All three are backed by
`GET /drives/{drive_id}/root:{encoded_path}:/children`, which interleaves
file items (carrying the `file` facet) and folder items (carrying the
`folder` facet) in one response.
**`iter_children` override:** The backend overrides the default
`BE-026` implementation (which would chain `list_files` + `list_folders`
and double the round-trips) to consume the shared `/children` response
directly, yielding `FileInfo` for `file`-faceted items and `FolderEntry`
for `folder`-faceted items in the order Graph returns them.
**Missing-path behavior:** Matches BE-014, BE-015, BE-026 — yields
nothing for non-existent paths, never raises `NotFound`.
**`recursive`, `max_depth`, `pattern`:** `AsyncBackend.list_files`
accepts `recursive` and `max_depth` (ASYNC-014) but no `pattern`;
`AsyncBackend.list_folders` does not accept `max_depth` (ASYNC-015).
Pattern-limited listing is composed at `AsyncStore` level (ASYNC-052).
**Precedence (per ASYNC-014):** when `max_depth` is set, `recursive`
is ignored — `max_depth` governs traversal depth alone; `recursive=True`
with `max_depth=None` means unbounded; `recursive=False` (the default)
with `max_depth=None` yields only immediate children. The Graph backend
honours this by short-circuiting the recursive `/children` walk at the
configured depth (or after one level for the non-recursive default).

### GR-015: Range Download via `@microsoft.graph.downloadUrl`

**Invariant:** The backend uses an internal `_read_bytes(path, start,
length)` helper for range reads: it issues `GET` with a `Range:
bytes=<start>-<end>` header directly to the
`@microsoft.graph.downloadUrl` returned in item metadata, not to the
`/content` endpoint. This helper is **not** a public Store method;
it services the non-seekable read pipeline and the spool fallback
for `read_seekable()`. `SEEKABLE_READ` remains withheld (GR-003).
**SharePoint caveat:** On some SharePoint-backed drives the
pre-signed download URL has been observed to ignore or reject
`Range` headers depending on tenant configuration (WebDAV-style
backends in particular). When the server returns the full entity
(`200 OK` to a `Range` request) or rejects the range with a
non-`416` `4xx` — the range-incapable signals — the backend falls
back to the spool strategy rather than pretending to stream. A
`416` is **not** a range-incapability signal and does not trigger
this fallback: a start at or past EOF is a legitimate empty read and
an inverted-bounds `416` is a backend bug, both owned by GR-055 (the
single source of truth for `416` on a range read). When the fallback
fires, the backend logs a WARNING with the `graph.read.range_fallback`
marker and sets
`FileInfo.extra["graph.read.range_fallback"] = True` on any
`FileInfo` returned for the same item within the operation context.
The `extra` channel is the v0.27.0 supported surface for
backend-specific signal (see GR-049 for `graph.file.hashes`);
`ext.observe` is **not** used as a delivery channel —
`StoreEvent.metadata` is constructed by `ObservedStore._observe_op`
at the proxy layer before the inner backend call, so the backend
has no handle on the event object (per OBS-001's `StoreEvent`
dataclass and the proxy's `finally`-block emit; OBS-015's
post-operation `WriteResult` injection is the one exception, and it
runs in the proxy method's closure after the inner call returns —
not from inside the backend). Tests assert against the WARNING log
record (always reachable) and against `FileInfo.extra`. Note that
`ext.observe` and `ext.otel` are sync-only (they subclass
`ProxyStore`; `aio/ext/` ships no `observe`/`otel` module today), so
they reach `GraphBackend` only when it is wrapped by
`AsyncBackendSyncAdapter` into a sync `Store`. A native-`AsyncStore`
Graph consumer gets no observe/otel surface at all; native-async
observability is a separate, unscheduled item.
**Rationale:** The `/content` endpoint returns `302` redirecting to
the download URL, and only the download URL honours `Range`
reliably. The download URL is pre-signed; no `Authorization` header
is attached.
**Postconditions:** Full-file reads use the same download URL with
no `Range` header. The helper is internal implementation detail and
may change without a public-API deprecation.

### GR-016: Pagination via `@odata.nextLink`

**Invariant:** List operations follow `@odata.nextLink` in the
response body until it is absent.
**Postconditions:**
- Empty `value` arrays with a `nextLink` are handled correctly (no
  premature termination).
- Missing `nextLink` terminates iteration.
- A malformed `@odata.nextLink` (not a parseable absolute URL, or
  pointing to an unrelated host) is a Graph contract violation and
  maps to `BackendUnavailable`. The backend does not attempt to
  repair or second-guess the value.

### GR-017: downloadUrl Expiry Mid-Read

**Invariant:** If the pre-signed download URL expires mid-read
(`401` or `403` from the pre-signed host), the backend re-fetches the
item metadata to obtain a fresh download URL and resumes the read
from the next unread byte using a `Range` request.
**ETag validation on re-fetch:** The re-fetch compares the item's
`eTag` against the value observed at the original metadata fetch.
If the eTag has changed, the item was mutated mid-read; the backend
raises `BackendUnavailable` with context carrying the old and new
eTag values rather than silently returning a mixed-version byte
stream.
**Postconditions:** The re-fetch is bounded by `RetryPolicy`;
exhaustion raises `BackendUnavailable`.
**SharePoint caveat:** Some SharePoint drive backings issue
download URLs that reject subsequent `Range` requests even while
unexpired. If the re-fetched URL yields a `200` (full body) or
non-`416` `4xx` to a `Range` request, the backend treats the
download URL as range-incapable and completes the remaining bytes
by re-reading from offset zero into the existing spool rather than
streaming mid-file.

---

## Write Operations

### GR-018: Small-File Write (<= 4 MiB)

**Invariant:** `async def write(path, content, *, overwrite=False,
metadata=None) -> WriteResult` (BE-008 / ASYNC-008; content typed
per ASYNC-021) with content size <= 4 MiB uses
`PUT /drives/{drive_id}/root:{encoded_path}:/content`.
**Postconditions:**
- Intermediate folders are created automatically (matches BE-009);
  Graph creates missing parent folders implicitly on path-based
  writes.
- The write is atomic at the service level.
- The returned `WriteResult` carries `source="native"` (WR-004) with
  `size`, `etag`, `last_modified`, and `version_id` populated from the
  `driveItem` body Graph returns in the `200 OK` response. `digest` is
  left `None` until a future extension selects a canonical hash from
  `driveItem.file.hashes` (see GR-049). `metadata` echoes the caller's
  input mapping when one is supplied (WR-012), `None` otherwise.
**`metadata=` gate:** Because `GraphBackend` does not declare
`USER_METADATA` (GR-003), the WR-010/WR-011 strict gate at the Store
layer raises `CapabilityNotSupported` on any non-`None`, non-empty
`metadata=` before `GraphBackend.write` is entered. `metadata=None`
and `metadata={}` are no-ops at the Store layer per the
empty-mapping carve-out. The backend itself may optionally re-raise
the same error as defense-in-depth for direct-backend callers; this
is permitted but not required.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`.
`InvalidPath` if the path names a folder, or if a slash-aligned ancestor
of `path` is a regular file (BE-008 ID-209 clause).
**BE-008 precondition discrimination:** Graph is not a flat
namespace — folders are first-class `driveItem`s with a `folder`
facet, and the service rejects path traversal through a file item
natively. The ID-211 opt-in `reject_write_under_file_ancestor` kwarg
therefore does **not** apply to `GraphBackend`; ancestor-as-file
rejection is delivered by Graph's own `409 nameAlreadyExists`
(carrying a `file`-faceted ancestor in `error.details`) without an
explicit pre-walk. BE-008's precondition order (path validity →
overwrite conflict → I/O) applies in full; Graph's
`409 nameAlreadyExists` alone is not sufficient to discriminate the
outcomes. The backend inspects the 409 response body:
- when `error.details` (or the returned `driveItem` on
  `@microsoft.graph.conflictBehavior=fail`) carries the `folder` facet
  on the **target** name, the existing item is a folder and the backend
  raises `InvalidPath`;
- when the conflict is on an **ancestor** carrying the `file` facet
  (file-as-directory-component, ID-209), the backend raises
  `InvalidPath` regardless of `overwrite`;
- otherwise the existing item is a file at the target name and the
  backend raises `AlreadyExists`.

This rule applies equally to GR-019, GR-025 (copy), and GR-027 (move)
destinations.
**Known limitation — `overwrite=True` on a file conflict:** with
`@microsoft.graph.conflictBehavior=replace`, an existing *file* at the
target is expected to be overwritten (`200`). Some backing stores
(observed on SharePoint-backed drives in Graph issue reports) instead
return `409 nameAlreadyExists` for a file even under `replace`, which
the discrimination above would surface as `AlreadyExists` — a spurious
failure for an intended overwrite. This is not reproduced on the
consumer OneDrive drive used for live verification, so no guard is
taken in v1; the edge is unverified on SharePoint-backed drives and
tracked in BK-261.
**Note on the 4 MiB threshold:** Graph documents the
`PUT .../content` endpoint as suitable for files up to ~4 MiB and
recommends upload sessions beyond that. In practice the endpoint
accepts larger payloads (commonly up to ~60 MiB) but the behaviour
is not contractually guaranteed and varies by drive backing store.
4 MiB is the conservative default the backend uses; it is not a
tuning knob in v1.

### GR-019: Large-File Write via Upload Session

**Invariant:** `write(path, content, *, overwrite=False, metadata=None)
-> WriteResult` (BE-008 / ASYNC-008) with content size > 4 MiB opens
an upload session via `POST createUploadSession` and uploads chunks to
the returned session URL.
**Content shape:** `AsyncBackend.write` accepts `AsyncWritableContent =
bytes | AsyncIterator[bytes]` (ASYNC-021). The size-detection branch
is therefore binary:
- `bytes`: total is `len(content)`; the session is opened with the
  true total and chunks are sliced from the in-memory buffer.
- `AsyncIterator[bytes]`: total is unknown until the iterator is drained.
  Graph's upload-session `PUT` requires `Content-Range: bytes
  {start}-{end}/{total}` with a known total (`bytes X-Y/*` is rejected),
  so the backend spools the iterator to a `SpooledTemporaryFile`,
  records the final length once the iterator is exhausted, and only
  then opens the session and replays chunks from the spool. Callers
  that already know the size and want to avoid the spool pass `bytes`.

There is no separate `content_length` keyword on `AsyncBackend.write()`
(ASYNC-008); inferring size from the input is the only mechanism.

- **Spool-file location:** When an on-disk spill occurs, the backend
  uses `SpooledTemporaryFile()` with no explicit `dir=` — system temp,
  matching every other spool site in the codebase
  (`_backend.py`, `_async_to_sync_adapter.py`, `_azure.py`, `_s3.py`,
  `_s3_pyarrow.py`, `ext/arrow.py`). Cross-drive / small-`TMPDIR`
  redirection is the caller's `TMPDIR` (or platform-specific equivalent)
  to set, not a per-backend policy. **The documentation-phase guide for
  this backend must note `TMPDIR` redirection** so callers running on
  small-capacity temp volumes (Windows, restricted containers) can plan
  accordingly.
- **Spool-spill observability:** When an on-disk spill occurs, the
  backend logs a DEBUG record with the marker
  `graph.upload.spool_spilled` carrying the spool path. The DEBUG
  channel is the supported v0.27.0 mechanism for backend-internal
  diagnostics; tests assert against the log record (via `caplog`).
  `ext.observe` is not used as a backend-push channel — `StoreEvent`
  is built by the proxy layer (OBS-001) before the inner call, so a
  backend cannot inject into it; OBS-015's `WriteResult` injection
  is the one exception and lives in the proxy's post-call closure,
  not in the backend. As with GR-015, `ext.observe`/`ext.otel`
  themselves are sync-only and reach `GraphBackend` only through
  `AsyncBackendSyncAdapter`.

**Postconditions:**
- The upload is atomic on commit: the item becomes visible only
  after the final chunk succeeds.
- The returned `WriteResult` carries `source="native"` (WR-004) with
  `size`, `etag`, `last_modified`, and (where present) `version_id`
  populated from the `driveItem` body Graph returns in the **final**
  chunk's `201 Created` / `200 OK` response. `digest` is left `None`
  per GR-049. `metadata` echoes the caller's input mapping when one is
  supplied (WR-012), `None` otherwise.
- On unrecoverable failure, the session is deleted as a best-effort
  cleanup (GR-024).

**`metadata=` gate:** Identical to GR-018 — the WR-010/WR-011 strict
gate fires at the Store layer (not in the backend) because
`USER_METADATA` is not declared (GR-003); a non-`None`, non-empty
`metadata=` raises `CapabilityNotSupported` before
`GraphBackend.write` is entered.

### GR-020: Chunk Size Alignment

**Invariant:** Upload-session chunks are aligned to a multiple of
320 KiB. The effective chunk size is
`min(upload_chunk_size, remaining_bytes)` rounded down to the
nearest 320 KiB multiple, except for the final chunk which carries
the trailing bytes.
**Rationale:** 320 KiB is Graph's documented alignment; non-aligned
chunks are rejected.

### GR-021: Upload-Session Chunk PUT

**Invariant:** Each chunk is sent as `PUT {sessionUrl}` with a
`Content-Range: bytes {start}-{end}/{total}` header and the chunk
bytes as the body.
**Raises:** `RemoteStoreError` (non-retryable) on `409 invalidRange`.

### GR-022: Upload-Session Chunk Retry

**Invariant:** On a transient failure (`5xx`, `429`, network error)
the backend retries the same chunk per `RetryPolicy`. The upload
session is not restarted.
**Postconditions:** `429` honours `Retry-After` (GR-034).

### GR-023: Upload-Session Resume from `nextExpectedRanges`

**Invariant:** When a chunk response carries `nextExpectedRanges`,
the backend resumes uploading from the server's expected offset
rather than trusting the client-side cursor.
**Format:** Graph returns `nextExpectedRanges` as a JSON array of
string ranges of the form `"{start}-{end}"` or `"{start}-"` (open
upper bound), e.g. `["524288-"]` or
`["0-262143", "786432-"]`. The backend parses the first range's
start offset and resumes from there.
**Postconditions:** Enables recovery from partial chunk receipt
without restarting the session — a legitimate resume offset advances
by at least one byte past the start of the chunk just sent (the server
consumed some of it). A missing or malformed `nextExpectedRanges`, or
a resume offset that does not advance past the chunk just sent (a
stalled or regressing session), is treated as a Graph contract
violation and maps to `BackendUnavailable`. The resume offset is
therefore strictly increasing, so the chunk loop is guaranteed to
terminate rather than re-PUT the same chunk indefinitely.

### GR-024: Upload-Session Abort

**Invariant:** On unrecoverable failure or caller cancellation, the
backend issues `DELETE {sessionUrl}` as best-effort cleanup. Errors
during cleanup are logged but not propagated.
**Postconditions:** Orphan sessions eventually expire server-side
(Graph documents session lifetime on the order of hours).

### GR-038: Upload-Session Authentication

**Invariant:** Upload-session chunk PUTs and the abort `DELETE` are
sent **unauthenticated**. The `uploadUrl` returned by
`createUploadSession` is pre-signed, lives on a different host than
`graph.microsoft.com`, and carries its own credential in the query
string; attaching the Graph bearer would leak it cross-host and is
rejected by the service. The backend performs no mid-session token
refresh.
**Postconditions:** Graph documents the session lifetime on the order
of hours (GR-024). A session URL that expires or is revoked mid-upload
surfaces through the standard error mapping — a `401` / `403` on the
pre-signed URL maps to `PermissionDenied` (GR-029 / GR-030) — with no
refresh attempt, since the bearer is not the credential in play.

### GR-039: Auto-Mkdir on Write

**Invariant:** Graph creates missing intermediate folders implicitly
when a path-based write targets a nested path. The backend does not
issue explicit `mkdir` calls. This satisfies BE-009.
**Postconditions:** Folder creation inherits the parent's
permissions; permission failures surface as `PermissionDenied`.

### GR-040: write_atomic()

**Invariant:** `async def write_atomic(path, content, *,
overwrite=False, metadata=None) -> WriteResult` (BE-010 / ASYNC-010;
content typed per ASYNC-021) delegates to the same path as `write`:
small files use `PUT /content` (atomic at the service); large files
use upload sessions (atomic on commit). No temporary file is created
client-side.
**Rationale:** Graph's own write paths already provide the
no-partial-content guarantee (AW-001); a client-side temp-rename
dance would add latency without strengthening the contract. The
`WriteResult` shape (WR-001..WR-005, WR-012) and the WR-010
`metadata=` gate are inherited verbatim from GR-018 / GR-019.
**`open_atomic()`:** Not implemented by the backend.
`AsyncBackendSyncAdapter` synthesises it for sync callers as
spool-and-flush over `write_atomic` (ASYNC-085); no Graph-specific
override is taken in v1. A future revision could back `open_atomic`
on the upload session directly (the session URL admits incremental
`PUT` per chunk without the spool) — captured as a known follow-up,
not in scope here.

---

## Delete, Move, Copy

### GR-041: delete()

**Invariant:** `delete(path, missing_ok=False)` issues `DELETE` on
the resolved item. Graph moves deleted items to the recycle bin by
default.
**Raises:** `NotFound` if the item does not exist and
`missing_ok=False`. `InvalidPath` if the path names a folder (per
BE-012).

### GR-042: delete_folder() Recursive

**Invariant:** `delete_folder(path, recursive=True)` issues a single
`DELETE` on the folder item. Graph deletes folders and their
contents atomically server-side.
**Raises:** `NotFound` if the folder does not exist and
`missing_ok=False`.

### GR-043: delete_folder() Non-Recursive

**Invariant:** `delete_folder(path, recursive=False)` first checks
the folder's `folder.childCount` (or a single `/children?$top=1`
probe). If non-empty, raises `DirectoryNotEmpty`. If empty, issues
`DELETE`.
**Raises:** `NotFound` if the folder does not exist and
`missing_ok=False`. `DirectoryNotEmpty` if children exist.

### GR-025: Copy

**Invariant:** `copy(src, dst, overwrite=False)` issues `POST
copy` with a `parentReference` and `name` derived from `dst`. Graph
responds with `202 Accepted` and a `Location` header pointing to a
monitor URL.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if
`dst` exists and `overwrite=False`. `InvalidPath` per BE-021.

### GR-026: Monitor-URL Polling Contract

**Invariant:** The backend polls the monitor URL from GR-025 (and
GR-027) using a backend-local poller in
`src/remote_store/aio/backends/_graph/monitor.py` (or inline in
`backend.py` if it stays small). Not a shared facility in v1 — see
ADR-0023 for the reality-check that turned the earlier
shared-helper design backend-local.
**Postconditions:**
- Initial interval defaults to 1 s; ceiling 30 s; multiplicative
  backoff factor 2.
- Overall poll budget is controlled by a dedicated
  `copy_timeout: float | None` parameter on `GraphBackend.__init__`
  (default `None`, meaning no backend-imposed ceiling — the operation
  runs until Graph reports terminal status). `RetryPolicy.timeout` is
  **not** used as the poll budget: `RetryPolicy.timeout` bounds a
  retry loop on the order of seconds, whereas a copy of a large item
  can legitimately take minutes, so conflating the two would
  prematurely abort long copies. A caller who wants a wall-clock
  bound on `copy`/`move` sets `copy_timeout` explicitly.
- **`copy_timeout=None` is intentional but unsafe by default.** With
  no ceiling, a `copy()`/`move()` against an unresponsive Graph
  endpoint can block the caller indefinitely. The backend does **not**
  substitute a fallback timeout. Callers that cannot tolerate an
  unbounded wait must either (a) set `copy_timeout` to a finite value
  at `GraphBackend.__init__`, or (b) wrap the call in an external
  ceiling (e.g. `asyncio.timeout(...)` for async callers, thread-level
  cancellation for sync). The documentation-phase guide for this
  backend must call this out.
- On `copy_timeout` expiry the poller raises `BackendUnavailable`
  whose message embeds the monitor URL, the poll count, and a
  `last_status` token from a closed set: `"pending"` (terminal poll
  returned a still-running status), `"5xx"` (last response was a
  transient server error treated as pending per below), or
  `"parse-error"` (last response could not be classified by the
  `status_parser`). Tests assert against the message text. (A
  `RemoteStoreError.context` carrier was considered as a structured
  alternative but is not part of spec 005 today; introducing it is
  out of scope for ID-127 and tracked separately if a backend ever
  needs it.) The server-side operation is **not** cancelled (Graph
  monitor URLs have no public cancel endpoint); the caller is
  expected to check the final state out-of-band if needed.
- `Retry-After` on poll responses overrides the computed interval
  when larger.
- `5xx` responses during polling are treated as `pending`, not
  `failed`.
- A poll-response payload with `status: "failed"` has the shape
  `{"status": "failed", "error": {"code": str, "message": str, ...}}`
  with optional resource and operation identifiers. The poller maps
  `error.code` through the standard error-mapping table (GR-028
  through GR-034, GR-045, GR-054). Unknown or malformed `error.code`
  values map to `BackendUnavailable`.
- Cancellation propagates `asyncio.CancelledError`.

**`ext.observe` interaction:** When Graph is wrapped via
`AsyncBackendSyncAdapter` into a sync `Store`, `Store.copy()` and
`Store.move()` emit one event in `finally` per the OBS-001
`StoreEvent` shape and the `ObservedStore._observe_op` proxy
contract; the internal polling loop is not observable. The backend
does **not** inject per-poll attributes into `StoreEvent.metadata` —
the proxy builds metadata before the inner backend call, so the
backend has no handle on the event object. (OBS-015's post-operation
`WriteResult` injection is the one exception and lives in the
proxy's post-call closure, not in any backend.) Native-`AsyncStore`
Graph consumers see no `ext.observe` surface at all (no
`aio/ext/observe.py` exists in v0.27.0). Poll-count and duration
diagnostics are emitted as DEBUG log records carrying the marker
`graph.copy.poll_complete`; `caplog` is the test channel and is
reachable on both async and sync surfaces.

### GR-027: Move (May-Be-Async)

**Invariant:** `move(src, dst, overwrite=False)` issues `PATCH` on
the source item with a new `parentReference` and optional new
`name`. Graph responds synchronously in most cases; large-item or
cross-drive moves may return `202 Accepted`, in which case the
backend reuses the GR-026 poller.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if
`dst` exists and `overwrite=False`. `InvalidPath` per BE-021 and
GR-018's BE-008 precondition discrimination (including the
ancestor-as-file case, ID-209).
**Atomicity:** Not declared — `ATOMIC_MOVE` is not in the capability
set (GR-003).
**Metadata preservation (BE-018):** Graph's `PATCH driveItem`
preserves the item's identity — `id`, `eTag`, and any user-supplied
property bag on the underlying `listItem` survive the move. The
backend issues no compensating writes; `get_file_info(dst).metadata`
returns whatever `get_file_info(src).metadata` would have returned
before the move. Since the backend does not declare `USER_METADATA`,
the BE-018 metadata-preservation conformance test skips on Graph
without a backend-specific carve-out; the WR-013 round-trip is
satisfied vacuously by the `metadata = None` postcondition (GR-013).
The invariant is asserted here so a future revision that declares
`USER_METADATA` for SharePoint-backed drives does not have to
revisit move semantics.

### GR-044: Self-Move and Self-Copy

**Invariant:** `move(src, dst)` and `copy(src, dst)` with
`src == dst` complete without mutating the item, consistent with
BE-018 and BE-019.
**Oracle:** The backend honours BE-019's `NotFound` precondition for
the self-copy/self-move case the same as for any other call: it
issues a single `GET` (item-by-path metadata fetch) to verify that
`src` exists and raises `NotFound` if it does not. Once existence is
confirmed, no further HTTP traffic is issued — no `POST /copy`, no
`PATCH`, no monitor poll. The behaviour is therefore "one metadata
GET, then short-circuit", not "zero HTTP calls".

### GR-056: Cross-Drive Operations Are Structurally Impossible

**Invariant:** `copy(src, dst)` and `move(src, dst)` cannot address
a different drive from the backend's configured `drive_id`. There
is no detection branch at runtime: Store paths are `/`-rooted POSIX
strings (PATH-001, GR-009) with no syntax for embedding a
`drive_id`, a site id, or an absolute Graph URL. A `GraphBackend`
instance is scoped to exactly one drive (GR-050); every `src` and
`dst` it sees resolves against that drive by construction.
**Rationale:** Cross-drive transfers would require either a path
grammar extension or a composite-store abstraction. Neither is in
scope. This ID exists as the extension point should a future RFC
introduce either mechanism; until then it documents the vacuous
condition so reviewers do not look for a runtime check that cannot
be written against the current path model.
**No runtime check required:** Implementations MUST NOT introduce a
synthetic cross-drive detector (e.g. URL-parsing `dst`) — doing so
would advertise a capability the API surface does not admit.

---

## Error Mapping

### GR-028: Structured Error Classification

**Invariant:** Graph error responses are mapped using HTTP status
plus the `error.code` field in the JSON body. String matching on
error messages is forbidden.
**Postconditions:** `backend="graph"` is set on every mapped error.
No `httpx` or `msal` exceptions propagate to callers (per BE-021).

### GR-029: 401 InvalidAuthenticationToken

**Invariant:** On `401` with `error.code == "InvalidAuthenticationToken"`,
the backend re-invokes `token_provider` and retries the request once.
A second `401` with the same code raises `PermissionDenied`.
**Postconditions:** This handling is independent of `RetryPolicy` —
it is a one-shot refresh, not a retry loop. `401` responses with any
other `error.code` (e.g. `unauthenticated`, `tokenNotFound`,
`invalidRequest` at 401 scope) map directly to `PermissionDenied`
without a refresh attempt; the token is valid but the caller lacks
the required permission for this operation, and refreshing would not
change the outcome.

### GR-030: 403 accessDenied

**Invariant:** `403 accessDenied` maps to `PermissionDenied`.

### GR-031: 404 Discrimination (item vs drive)

**Invariant:** `404` responses are disambiguated by Graph `error.code`
and by the resource scope of the failing URL:
- `404` with `error.code == "itemNotFound"` at an item or path scope
  (e.g. `/drives/{drive_id}/root:{path}:`) maps to `NotFound` for
  operations where missing-path is an error (read, get_file_info,
  delete without `missing_ok`, move/copy source). For `exists`,
  `is_file`, `is_folder`, it is suppressed and returns `False` per
  BE-004 and BE-005.
- `404` at drive scope (the `/drives/{drive_id}` resource itself, or
  `error.code == "resourceNotFound"` at drive scope) maps to
  `BackendUnavailable` — the configured drive is deleted or
  misconfigured, which is a backend identity failure, not a per-item
  condition.
- The backend does **not** attempt to discriminate "404 masking
  403" (Graph occasionally returns `404 itemNotFound` where `403
  accessDenied` would be semantically correct on restricted
  resources). All `404 itemNotFound` at item scope map to
  `NotFound`. Rationale: Graph offers no reliable, caller-agnostic
  signal to tell a real not-found from a hidden permission denial,
  and guessing would require the backend to track what the caller
  "should" be able to enumerate — which it cannot. Callers that
  need to distinguish run a drive-root probe (`exists("/")`) to
  confirm the drive is reachable, then treat `NotFound` as
  authoritative for the item.

### GR-032: 409 nameAlreadyExists

**Invariant:** `409 nameAlreadyExists` maps to `AlreadyExists`. For
write operations, the backend uses Graph's `@microsoft.graph.conflictBehavior`
parameter (`fail` vs `replace`) to control whether the error is
raised or the write overwrites.

### GR-033: 5xx and Network Errors

**Invariant:** `500`, `502`, `503`, `504`, and httpx transport
errors (connect, read, write timeouts; DNS; connection reset) map
to `BackendUnavailable` and are retryable per `RetryPolicy`.

### GR-034: 429 activityLimitReached

**Invariant:** `429 activityLimitReached` maps to
`BackendUnavailable`. The `Retry-After` header value is propagated
via the error's context so the retry policy can honour it.
**Postconditions:** No new `RateLimitError` is introduced. The
five-field `RetryPolicy` drives the in-backend retry (`httpx` has
no native retry); see RET-015.

### GR-045: 423 resourceLocked

**Invariant:** `423 resourceLocked` maps to `ResourceLocked`
(ERR-013, ADR-0024).
**Postconditions:**
- Not retried by the default retry policy (terminal per RET-015).
- Mid-session case: a `423` observed during an upload-session chunk
  `PUT` surfaces as `ResourceLocked` to the caller. The session URL
  remains valid — Graph does not invalidate it on `423` — but the
  backend does not auto-retry or auto-resume. Caller retry is the
  caller's decision; if it chooses to retry, the session URL and
  `nextExpectedRanges` discipline (GR-023) still apply. The
  unfinished session URL and last-known `nextExpectedRanges` list
  are included in the exception message text so callers (and tests)
  can resume without re-deriving them. (Spec 005 has no structured
  `RemoteStoreError.context` surface today; adding one is out of
  scope for ID-127.)

### GR-054: 507 insufficientStorage / quotaLimitReached

**Invariant:** HTTP `507 insufficientStorage`, and any response
carrying `error.code == "quotaLimitReached"`, map to
`BackendUnavailable` whose message text names the quota whenever
Graph returns it (e.g. `quota.total`, `quota.used`, `quota.remaining`,
`quota.state`).
**Postconditions:** Not retryable by the default policy — the
condition does not clear on short-term retry. Callers diagnose via
the message text and react at their own cadence.
**Upstream limits:** Graph enforces a documented maximum single-file
size of 250 GiB per upload session for OneDrive and SharePoint
drives (smaller on consumer OneDrive). The backend does not
pre-validate against this limit; attempts to upload larger files
surface as `507` / `quotaLimitReached` from Graph and reach the
caller via this mapping.

### GR-055: 416 invalidRange on Range Read

**Invariant:** `416 invalidRange` returned on a range read via the
download URL is not coined as a fresh `RemoteStoreError`. Spec 036
(seekable-read, `SEEK-*`) governs the seekable-stream surface but
does not specify HTTP range-error mapping; this spec ID owns the
mapping for the Graph backend:
- A range request whose start is at or past EOF yields an empty
  byte stream (length-zero `BinaryIO`, no exception). This matches
  what a `seek()` past EOF on a local file followed by `read()`
  produces and lets `Store.read_seekable()` wrappers (SEEK-002)
  behave uniformly across backends.
- A malformed `Range` header (backend bug, e.g. inverted bounds)
  is a programming error and surfaces as `RemoteStoreError` with
  the HTTP status and Graph error code in the message.
**Rationale:** Keeps range-read semantics colocated with the
backend that emits them, while preserving the seekable-read
contract that spec 036 owns at the Store API layer.

### GR-046: Failure Paths per Operation

**Invariant:** Every public operation has a documented failure
postcondition:

- `read` on a folder → `InvalidPath`.
- Range-read failure paths follow GR-055 (the `416 invalidRange`
  mapping owned by this spec); the seekable-stream surface itself
  is governed by spec 036 (`SEEK-*`).
- `write` with malformed `Content-Range` (upload session) →
  `RemoteStoreError` mapped from `409 invalidRange`.
- `list_files` / `list_folders` on a file path → yields nothing
  (BE-014, BE-015).
- `get_file_info` on a folder → `InvalidPath`.
- `copy` with `src == dst` → no-op (GR-044).
- `delete_folder(recursive=False)` on non-empty folder →
  `DirectoryNotEmpty`.

---

## Throttling and Retry

### GR-047: RetryPolicy Honoured In-Backend

**Invariant:** `GraphBackend` honours all five `RetryPolicy` fields
in-backend, applying exponential backoff with jitter between retries
of retryable responses (GR-033, GR-034).
**Rationale:** `httpx` has no native retry mechanism; unlike the
Azure and S3 backends, retry cannot be delegated to the SDK.
See RET-015 in spec 025.

### GR-048: Retry-After Precedence

**Invariant:** When a retryable response carries a `Retry-After`
header, the backend waits for at least that duration before the
next attempt, overriding the computed backoff when the header value
is larger.
**Postconditions:** `Retry-After` values expressed as HTTP-date
(RFC 7231) and as delta-seconds are both supported.

---

## Metadata

### GR-049: File Hashes in FileInfo.extra

**Invariant:** `FileInfo.extra` populates `graph.file.hashes` with
the `quickXorHash`, `sha1Hash`, and `sha256Hash` values from Graph's
`file.hashes` object when present.
**Postconditions:**
- Not wired into `ext.integrity` in v1 — reserved for a future
  fast-path.
- Callers that need a canonical digest today use
  `FileInfo.digest`; the Graph backend leaves `digest` unset
  unless a single authoritative hash is selected by a future
  extension.
- **Availability caveat:** Graph's `/children` list endpoint
  frequently omits `file.hashes` on SharePoint-backed drives even
  when a per-item `GET /items/{id}` would return them. Callers
  that require hashes should fetch individual items; the backend
  does not paper over the gap by back-filling hashes during list
  operations.

### GR-050: Drive-Id as Store Identity

**Invariant:** `drive_id` is immutable after construction.
**Postconditions:** Changing the target drive requires constructing
a new backend. `drive_id` is reserved as a component of any future
identity-derived consumer (e.g. a `cache_key`-discipline `ext.cache`
revision per ID-123 — `ext.cache` in v0.27.0 builds plain
`(op, path[, …])` tuples and does not yet derive keys from backend
identity).

---

## Interface Contract

### GR-036: to_key()

**Invariant:** `to_key(native_path)` strips the
`/drives/{drive_id}/root:` prefix (and the trailing `:` delimiter, if
present) from a native Graph path and returns the remaining
backend-relative key.
**Postconditions:** Pure, deterministic, total (per BE-023). Inputs
without the prefix are returned unchanged. The empty key (the drive
root) round-trips through `to_key(native_path(""))` per BK-234.

### GR-036a: native_path()

**Invariant:** `native_path(key)` returns
`/drives/{drive_id}/root:{encoded_key}:` — the path-addressed metadata
endpoint form per GR-009 — with each segment of `key` percent-encoded
per GR-010. The empty key returns `/drives/{drive_id}/root:` (no
trailing colon delimiter; this is Graph's drive-root form). The
inverse of GR-036: `backend.to_key(backend.native_path(k)) == k` for
every valid key (BE-025).
**Postconditions:** Pure, deterministic, total. The returned string is
usable as the URL path component of any Graph item-by-path metadata
request (content endpoints append `/content` or `:/content`; the helper
covers the metadata form only — content composition is the caller's
responsibility).
**Rationale:** Graph clearly has a native path form, so the BE-025
identity default would be a poor fit; backends with a native root
**must** override (BE-025).

### GR-037: unwrap()

**Invariant:** `unwrap(httpx.AsyncClient)` returns the backend's
underlying `httpx.AsyncClient` instance, enabling callers to issue
custom Graph calls.
**Raises:** `CapabilityNotSupported` for any other type hint.
**Sync-via-adapter caveat:** Sync callers that reach the backend
through `AsyncBackendSyncAdapter` also receive `CapabilityNotSupported`
for `unwrap(httpx.AsyncClient)` per ASYNC-086 — the async client is
bound to the adapter's private event loop and is unsafe to use from
the caller's thread. The escape hatch is therefore async-only;
sync callers needing the SharePoint property bag construct a
separate `httpx.AsyncClient` on their own event loop.
**Rationale:** Escape hatch per ADR-0003.

### GR-035: Credential Masking

**Invariant:** The `Authorization` header is redacted from any log
output, error message, or debug dump produced by the backend. Token
values never appear in exception messages or logging records.
**Observable surface (test anchors):**
- Any DEBUG-level log record the backend emits that includes
  headers replaces the `Authorization` value with `"***"` before
  formatting.
- The raw bearer token never appears in `str(exc)`, `repr(exc)`, or
  any backend-emitted log record at any level — the backend never
  passes the header into an exception message.
**Postconditions:** Satisfies AF-008 (extended to a per-request
header rather than just backend `__repr__`; this goes beyond the
HTTP backend's `repr`-only precedent in HTTP-CRED-001).

---

## Resource Management

### GR-051: close()

**Invariant:** `close()` (and `aclose()` on the async path) closes
the backend's `httpx.AsyncClient`, flushes the MSAL token cache to
disk if the built-in `GraphAuth` owns it, cancels any pending
monitor-URL pollers, and issues best-effort `DELETE` against any
upload sessions the backend currently owns.
**Postconditions:**
- Safe to call multiple times.
- User-supplied `http_client` instances are not closed — the caller
  owns that resource.
- After close, subsequent operations re-initialise the HTTP client
  on demand (consistent with `AzureBackend.close()` — AZ-029).
- **Upload-session abort on close:** For every in-flight upload
  session whose URL is reachable from the backend (i.e. a `write()`
  call is mid-chunk-loop when `close()` fires), the backend issues
  `DELETE {sessionUrl}` as described in GR-024. Failures are
  swallowed — `close()` must not raise on cleanup. This mirrors the
  GR-024 unrecoverable-failure path; the difference is only the
  trigger.
- **Monitor pollers** are cancelled cooperatively (`asyncio.Task.cancel`
  on async, futures cancelled on sync); the server-side copy/move
  continues per GR-026's "server-side operation not cancelled" note.

---

## Configuration

### GR-052: Client Options Passthrough

**Invariant:** `client_options` is merged into the internal
`httpx.AsyncClient` configuration. Explicit constructor parameters
(e.g. timeouts configured directly) take precedence over
`client_options` keys with the same name.

### GR-053: RetryPolicy Parameter

**Invariant:** `GraphBackend` accepts `retry: RetryPolicy | None =
None`. When `None`, uses the backend's default retry profile (3
attempts, 1-60 s exponential backoff, 1 s jitter — matching
`RetryPolicy()` defaults). When provided, replaces the default
entirely. See RET-015.

---

## Integration-only

Some invariants cannot be validated against `respx` fixtures because
they depend on Graph service-imposed behaviour that the mock does
not reproduce. These IDs require a real tenant. The gate is
two-layered (matching the Azure live-test pattern): `RS_TEST_LIVE_GRAPH=1`
**plus** the four credential env vars `GRAPH_TENANT_ID`,
`GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_DRIVE_ID`. Either
layer missing → skip cleanly. Marked `@pytest.mark.integration`:

- **GR-007** — device-code flow end-to-end. MSAL's device-code
  handshake cannot be meaningfully mocked at the protocol layer.
- **GR-020** — real chunk-alignment verification. `respx` will
  accept any `Content-Range`; only Graph enforces the 320 KiB rule.
- **GR-034** — real tenant throttling with authentic `Retry-After`
  values under sustained load.
- **GR-026** — end-to-end async copy monitor polling against a
  genuine `202`-returning `POST copy` and real monitor URL.
- **GR-054** — real `507 insufficientStorage` / `quotaLimitReached`
  can only be elicited against a drive that is actually at quota;
  `respx` can assert the mapping but cannot reproduce the condition.
- **Round-trip 10 MiB upload-session + range-read test** (RFC test
  plan). Validates byte-equality across the large-file path.

`respx`-based unit tests cover the request/response mapping for
every ID, including the ones listed above. Integration runs are the
only place the service-imposed invariants are exercised.
