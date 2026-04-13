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

**Dependencies:** `httpx`, `msal`
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
- `upload_chunk_size` is a positive multiple of 320 KiB;
  non-conforming values raise `ValueError`.
- `drive_id` is a non-empty string; empty or whitespace-only values
  raise `ValueError`.

### GR-002: Backend Name

**Invariant:** `name` property returns `"graph"`.

### GR-003: Capability Declaration

**Invariant:** `GraphBackend` declares the capabilities `READ`,
`WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `METADATA`, `ATOMIC_WRITE`,
`LAZY_READ`. It does not declare `GLOB`, `ATOMIC_MOVE`, or
`SEEKABLE_READ`.
**Rationale:**
- `ATOMIC_WRITE`: small-file `PUT /content` is service-side atomic;
  upload sessions are atomic on commit (see GR-018, GR-019).
- `LAZY_READ`: range reads target `@microsoft.graph.downloadUrl`
  (GR-015) and do not materialise the full file.
- `ATOMIC_MOVE` is withheld because Graph move may go async (GR-027);
  atomicity is not guaranteed.
- `SEEKABLE_READ` is withheld because the Graph content stream is
  forward-only. `Store.read_seekable()` uses the default spool
  fallback (ADR-0017). A native `Backend.read_seekable()` override
  built on `Range` reads over `@microsoft.graph.downloadUrl` was
  considered and declined: SharePoint-backed drives have been
  observed to return the full body (or a non-`416` `4xx`) in
  response to `Range`, so declaring `SEEKABLE_READ` would
  advertise a guarantee the backend cannot honour (see GR-015,
  GR-017).
- `GLOB` is withheld; callers use `ext.glob` over `list_files`.

Async monitor polling for `copy` and may-be-async `move` is a
backend-internal technique, not a capability — see ADR-0023.

### GR-004: Lazy Connection

**Invariant:** No network call occurs during `__init__`. HTTP client
creation, token acquisition, and drive validation are deferred to
first use.
**Rationale:** Matches the lazy-connection convention shared with
`S3Backend` (S3-004) and `AzureBackend` (AZ-004).

### GR-005: Construction Validation

**Invariant:** `drive_id` must be a non-empty string. `token_provider`
must be callable. `upload_chunk_size` must be a positive multiple of
320 KiB (Graph's alignment requirement). `copy_timeout`, when set,
must be a positive float. Violations raise `ValueError` at
construction time.
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
  `Authorization: Bearer <token>` (except to `@microsoft.graph.downloadUrl`
  targets, which are pre-signed — see GR-015).
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

### GR-057: `resolve_drive_id` Helper

**Invariant:** The public helper `resolve_drive_id(target, *,
token_provider, http_client=None) -> str` resolves a drive id from
one of three target shapes and returns the opaque Graph
`drive.id` string for use as `GraphBackend(drive_id=...)`. It is a
sync function; internally it runs an async resolution under a
private event loop (per ADR-0012 sync-wrapper pattern).

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
while providing an ergonomic on-ramp. The helper is separate from
the backend so it is testable and usable without instantiating a
full `GraphBackend` first.

---

## Read Operations

### GR-012: read()

**Invariant:** `read(path)` returns a read stream per BE-006 and spec
006 (streaming-io) — the project's stream abstraction, not a raw
iterator. The async backend's implementation pulls chunks from the
download URL via `httpx.AsyncClient.stream`; the public return type is
the stream abstraction required by the backend contract.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if
the path names a directory (per BE-021).

### GR-013: get_file_info()

**Invariant:** `get_file_info(path)` returns a `FileInfo` populated
from the Graph `driveItem` metadata (`name`, `size`,
`lastModifiedDateTime`, `eTag`).
**Postconditions:** ETag is stripped of outer quotes and lowercased.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if
the path names a folder.

### GR-014: list_files() and list_folders()

**Invariant:** `list_files(path, recursive=False)` and
`list_folders(path)` call `/children` on the target item and filter
the results by `folder` presence.
**Missing-path behavior:** Matches BE-014 and BE-015 — yields nothing
for non-existent paths, never raises `NotFound`.

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
(`200 OK` to a `Range` request) or rejects the range with `416`
outside the valid extent, the backend falls back to the spool
strategy rather than pretending to stream.
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

**Invariant:** `write(path, content, overwrite=False)` with content
size <= 4 MiB uses `PUT /drives/{drive_id}/root:{encoded_path}:/content`.
**Postconditions:**
- Intermediate folders are created automatically (matches BE-009);
  Graph creates missing parent folders implicitly on path-based
  writes.
- The write is atomic at the service level.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`.
`InvalidPath` if the path names a folder.
**Note on the 4 MiB threshold:** Graph documents the
`PUT .../content` endpoint as suitable for files up to ~4 MiB and
recommends upload sessions beyond that. In practice the endpoint
accepts larger payloads (commonly up to ~60 MiB) but the behaviour
is not contractually guaranteed and varies by drive backing store.
4 MiB is the conservative default the backend uses; it is not a
tuning knob in v1.

### GR-019: Large-File Write via Upload Session

**Invariant:** `write(path, content, overwrite=False)` with content
size > 4 MiB opens an upload session via `POST createUploadSession`
and uploads chunks to the returned session URL.
**Size requirement:** Graph's upload-session `PUT` requires a
`Content-Range: bytes {start}-{end}/{total}` header with a known
total. `Content-Range: bytes X-Y/*` is rejected by Graph and is not
used. Consequently:
- For known-size inputs (`bytes`, objects exposing `size` /
  `content_length`, or `FileInfo.size` for copy paths), the session
  carries the true total.
- For streams of unknown size that exceed the small-upload threshold,
  the backend spools the payload to a `SpooledTemporaryFile` (matching
  the pattern used by the SharePoint-Azure-Write / SAW path) to
  determine the total length before opening the session. Callers that
  want to avoid the spool must supply an explicit `content_length` (or
  `size`) at the write call site.
- **Spool-file location:** When an on-disk spill occurs, the temporary
  file is written to the current working directory rather than the
  system temp dir. This follows the project-wide convention for
  temporary-file placement (cross-drive / small-`TMPDIR` environments,
  particularly Windows, where the system temp volume may lack space
  for multi-GiB uploads). The policy is owned by this spec, not
  `tempfile` defaults; the implementation passes an explicit `dir=`.
  **The documentation-phase guide for this backend must note this
  placement** so callers running from read-only or small-capacity
  working directories can redirect the spool explicitly.
**Postconditions:**
- The upload is atomic on commit: the item becomes visible only
  after the final chunk succeeds.
- On unrecoverable failure, the session is deleted as a best-effort
  cleanup (GR-024).

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
without restarting the session. A missing or malformed
`nextExpectedRanges` (when one is expected) is treated as a Graph
contract violation and maps to `BackendUnavailable`.

### GR-024: Upload-Session Abort

**Invariant:** On unrecoverable failure or caller cancellation, the
backend issues `DELETE {sessionUrl}` as best-effort cleanup. Errors
during cleanup are logged but not propagated.
**Postconditions:** Orphan sessions eventually expire server-side
(Graph documents session lifetime on the order of hours).

### GR-038: Upload-Session Token Expiry Mid-Session

**Invariant:** If a chunk PUT returns `401 InvalidAuthenticationToken`,
the backend re-acquires the token via `token_provider` and retries
the same chunk. The session URL is pre-authorised and is **not**
recreated.
**Postconditions:** A second `401` after refresh maps to
`PermissionDenied`.

### GR-039: Auto-Mkdir on Write

**Invariant:** Graph creates missing intermediate folders implicitly
when a path-based write targets a nested path. The backend does not
issue explicit `mkdir` calls. This satisfies BE-009.
**Postconditions:** Folder creation inherits the parent's
permissions; permission failures surface as `PermissionDenied`.

### GR-040: write_atomic()

**Invariant:** `write_atomic(path, content, overwrite=False)`
delegates to the same path as `write`: small files use `PUT /content`
(atomic at the service); large files use upload sessions (atomic on
commit). No temporary file is created client-side.
**Rationale:** Graph's own write paths already provide the
no-partial-content guarantee (AW-001); a client-side temp-rename
dance would add latency without strengthening the contract.

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
GR-027) using the shared `_async_monitor` module (ADR-0023).
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
- On `copy_timeout` expiry the poller raises
  `BackendUnavailable(context={"monitor_url": ..., "poll_count": ...,
  "last_status": ...})`. The server-side operation is **not**
  cancelled (Graph monitor URLs have no public cancel endpoint); the
  caller is expected to check the final state out-of-band if needed.
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

**Single-event contract for `ext.observe`:** The internal polling
loop is not observable to `ext.observe`. `Store.copy()` and
`Store.move()` emit one start/end event pair regardless of how many
polls ran. Poll count and total duration may surface as event
attributes (e.g. `graph.copy.poll_count`,
`graph.copy.duration_ms`) but no intermediate `polling` events are
emitted. See ADR-0023: the poller is an implementation technique,
not a Store-level concept.

### GR-027: Move (May-Be-Async)

**Invariant:** `move(src, dst, overwrite=False)` issues `PATCH` on
the source item with a new `parentReference` and optional new
`name`. Graph responds synchronously in most cases; large-item or
cross-drive moves may return `202 Accepted`, in which case the
backend reuses the GR-026 poller.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if
`dst` exists and `overwrite=False`. `InvalidPath` per BE-021.
**Atomicity:** Not declared — `ATOMIC_MOVE` is not in the capability
set (GR-003).

### GR-044: Self-Move and Self-Copy

**Invariant:** `move(src, dst)` and `copy(src, dst)` with
`src == dst` are no-ops (consistent with BE-018 and BE-019).
**Oracle:** "No-op" means **zero HTTP calls** — the backend
short-circuits on a source/destination identity check before
contacting Graph. Source existence is not verified on the self-copy
path. Callers that want an existence check for the self-copy case
call `exists(src)` explicitly.

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
- `404` that Graph uses to hide an `accessDenied` condition on certain
  restricted resources (recognisable by the absence of an
  `itemNotFound` code at a resource the caller cannot enumerate) maps
  to `PermissionDenied`. Note: Graph sometimes returns `404` where
  `403` would be semantically correct; callers relying on the
  distinction should consult operation context.

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
  `nextExpectedRanges` discipline (GR-023) still apply.

### GR-054: 507 insufficientStorage / quotaLimitReached

**Invariant:** HTTP `507 insufficientStorage`, and any response
carrying `error.code == "quotaLimitReached"`, map to
`BackendUnavailable` with context fields naming the quota whenever
Graph returns them (e.g. `quota.total`, `quota.used`,
`quota.remaining`, `quota.state`).
**Postconditions:** Not retryable by the default policy — the
condition does not clear on short-term retry. Callers diagnose via
the context fields and react at their own cadence.
**Upstream limits:** Graph enforces a documented maximum single-file
size of 250 GiB per upload session for OneDrive and SharePoint
drives (smaller on consumer OneDrive). The backend does not
pre-validate against this limit; attempts to upload larger files
surface as `507` / `quotaLimitReached` from Graph and reach the
caller via this mapping.

### GR-055: 416 invalidRange on Range Read

**Invariant:** `416 invalidRange` returned on a range read via the
download URL is handled per spec 036 (seekable-read) SEK-* rules,
not coined as a fresh `RemoteStoreError`:
- A range request whose start is at or past EOF yields an empty
  byte stream (per SEK semantics for past-EOF reads).
- A malformed `Range` header (backend bug) maps per spec 036 to
  `InvalidPath` or `RemoteStoreError` as that spec dictates.
**Rationale:** Keeps range-read semantics in one place; the Graph
backend participates in the SEK contract rather than inventing a
parallel error shape.

### GR-046: Failure Paths per Operation

**Invariant:** Every public operation has a documented failure
postcondition:

- `read` on a folder → `InvalidPath`.
- Range-read failure paths follow spec 036 (seekable-read) SEK-*
  rules; see GR-055 for the `416 invalidRange` mapping.
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

**Invariant:** `drive_id` is immutable after construction. The
backend's identity (for `ext.cache` key derivation and similar
consumers) includes `drive_id`.
**Postconditions:** Changing the target drive requires constructing
a new backend.

---

## Interface Contract

### GR-036: to_key()

**Invariant:** `to_key(native_path)` strips the
`/drives/{drive_id}/root:` prefix (if present) from a native Graph
path and returns the remaining key.
**Postconditions:** Pure, deterministic, total (per BE-023). Inputs
without the prefix are returned unchanged.

### GR-037: unwrap()

**Invariant:** `unwrap(httpx.AsyncClient)` returns the backend's
underlying `httpx.AsyncClient` instance, enabling callers to issue
custom Graph calls.
**Raises:** `CapabilityNotSupported` for any other type hint.
**Rationale:** Escape hatch per ADR-0003.

### GR-035: Credential Masking

**Invariant:** The `Authorization` header is redacted from any log
output, error message context, or debug dump produced by the
backend. Token values never appear in exception messages or
logging records.
**Observable surface (test anchors):**
- The `Authorization` header value is replaced with the literal
  string `"***"` in `RemoteStoreError.context` whenever headers or
  request metadata appear there.
- Any DEBUG-level log record the backend emits that includes
  headers replaces the `Authorization` value with `"***"` before
  formatting.
- The raw bearer token never appears in `str(exc)`, `repr(exc)`,
  `exc.context`, or any backend-emitted log record at any level.
**Postconditions:** Satisfies AF-008.

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
not reproduce. These IDs require a real tenant (credentials gated by
`GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`,
`GRAPH_DRIVE_ID`) and are marked `@pytest.mark.integration`:

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
