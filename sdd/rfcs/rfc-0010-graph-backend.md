# RFC-0010: Microsoft Graph Backend (OneDrive, SharePoint, Teams Files)

## Status

Accepted

## Summary

Add a `GraphBackend` that implements the `AsyncBackend` ABC against the
Microsoft Graph v1.0 API, covering OneDrive (personal and business),
SharePoint document libraries, and Teams files (which are SharePoint
document libraries under the hood). The backend targets a single
`drive_id` per instance and addresses items by path. It uses `httpx` as
the HTTP transport, `msal` for token acquisition, and native async I/O
throughout. A sync-facing wrapper keeps the backend usable from
synchronous code paths.

## Motivation

Microsoft positions Graph as the unified file API across OneDrive,
SharePoint, and Teams. A Graph-first backend gives us one auth model,
one permission model, one path/item-id scheme, and one module to
maintain instead of three. Legacy SharePoint REST is a fallback only if
a specific Store operation is genuinely unavailable on Graph — and the
ten Store operations we target are all on Graph.

Users on Microsoft 365 tenants currently have no supported way to plug
`remote-store` into their existing OneDrive or SharePoint document
libraries without wrapping the raw REST API themselves. Closing that
gap is the point of this RFC.

## Goals

- One backend covering OneDrive personal, OneDrive for business,
  SharePoint document libraries, and Teams files.
- Path-based addressing against a single `drive_id`.
- Both daemon (client-credentials) and interactive (device-code) auth
  flows in v1.
- Native async implementation per ADR-0012, with a sync-facing wrapper
  so existing sync callers and extensions keep working.
- Honest capability declarations. Where Graph's semantics differ from
  the ideal Store contract, the backend says so rather than pretending.
- Round-trip large-file transfers via resumable upload sessions with
  retry and resume on chunk failure.

## Non-goals

- **Item-id addressing** (`/drive/items/{id}`). Deferred from v1. The
  spec records the deferral explicitly so a future RFC can add it
  without ambiguity.
- **Legacy SharePoint REST API.** Not targeted. Graph covers the
  operations we need.
- **Mail, calendar, Teams messages, groups, users**, or any non-file
  Graph surface.
- **Managed-identity and workload-identity auth.** Supported via the
  token-provider protocol (user supplies their own callable), but not
  packaged in v1.
- **Cross-drive operations.** Each `GraphBackend` is scoped to one
  drive. Copying across drives is out of scope for the first cut.

## Proposal

### New backend

**Module:** `remote_store.backends._graph`
**Name:** `"graph"`
**Optional extra:** `pip install "remote-store[graph]"`
**Dependencies:** `httpx`, `msal`, `platformdirs` (used by the
built-in `GraphAuth` token cache; see ADR-0022)
**Spec:** `sdd/specs/044-graph-backend.md` (GR-001 through GR-057,
contiguous; topic-grouped by section order)

The backend name is `"graph"` rather than `"onedrive"` or `"sharepoint"`
because a single instance can target any of those services depending on
the `drive_id` resolved at construction. The name reflects the unified
API, not the user-visible product.

### SDK decision

Evaluated honestly against the narrow surface we need (~12 endpoints,
async-native, custom polling and upload-session logic):

| Option | Verdict |
|---|---|
| `httpx` + `msal` direct REST | **Chosen.** Narrow dependency footprint, full control of the request layer, async-native fit, reuses the `httpx` dependency already used by the HTTP backend. |
| `msgraph-sdk` (Kiota) | Heavyweight transitive deps (Kiota runtime, `azure-identity`). Generated abstractions add little value over the thin surface we touch. Async-only in a way that complicates the sync-wrapper path. Revisit if the surface ever broadens materially. |
| `Office365-REST-Python-Client` | Mixes Graph with legacy SharePoint REST patterns; not a clean fit. |

ADR-0021 locks this decision.

### Auth model

Dual flows in v1, both implemented in a small `GraphAuth` helper:

- **Client-credentials** (app-only). Tenant admin consents
  `Files.ReadWrite.All` and/or `Sites.ReadWrite.All` application
  permissions on the app registration. Used by daemon services.
- **Device-code** (interactive). The user completes login in a browser.
  Used by CLIs, notebooks, and demo scripts.

The backend itself depends on a **token-provider callable**, not on
`GraphAuth`. Two shapes are supported:

- `Callable[[], str]`
- `Callable[[], Awaitable[str]]`

Users with their own auth plumbing (managed identity, corporate
broker, custom refresh) supply any callable matching one of those
shapes. MSAL token caching uses `SerializableTokenCache` with a
persistent backing file. Token cache location: see ADR-0022 § Token
caching for the canonical path and override rules (single source of
truth).

Authorization headers are redacted anywhere request or response
metadata surfaces in logs, error messages, or debug dumps (AF-008).

ADR-0022 locks the auth model.

### Addressing

Single `drive_id` per backend instance, required at construction.
Identity-stable: it never changes for the lifetime of the backend,
which is important for `ext.cache` safety (the cache key derives from
backend identity).

Path-only. Store paths are `/`-rooted POSIX strings. The backend
translates:

- `path` → `/drives/{drive_id}/root:{encoded_path}:` for metadata
  endpoints.
- Content reads go through `@microsoft.graph.downloadUrl` (see below).
- Content writes go through `/content` (small) or
  `createUploadSession` (large).

Path segments are percent-encoded per RFC 3986 before substitution.
Graph is fussy about spaces, `#`, `?`, `+`, and trailing dots in
segment names; the spec enumerates the encoding rules (GR-010).

#### `resolve_drive_id` helper

Users who have a drive URL or site URL rather than a raw `drive_id`
call a helper that resolves the three canonical shapes:

- **OneDrive personal / for business.** `/me/drive` → `drive.id`.
  The `GraphAuth` principal determines whose drive.
- **SharePoint document library.** `site_url` → `site_id` →
  `/sites/{site_id}/drives` → pick by name.
- **Teams channel files.** Team/channel → `filesFolder` → `drive_id`.

The helper is a one-shot translation used at application wiring time;
the resolved `drive_id` is then passed to `GraphBackend` and stored.
The backend does not repeat the resolution on each call.

### Async posture

The backend implements `AsyncBackend` natively (ADR-0012). All I/O
operations are `async def`, backed by `httpx.AsyncClient`.

Sync callers are supported through a wrapper rather than a second
implementation:

- **`AsyncStore`** consumes `GraphBackend` directly — no wrapping.
- **Sync `Store`** wraps the async backend via an async-to-sync
  adapter that runs operations on a private event loop. This is the
  mirror image of `SyncBackendAdapter` (which wraps sync into async).

The implementation phase will either reuse the existing adapter
machinery for the opposite direction or add a `AsyncBackendSyncAdapter`
companion. The spec does not prescribe which — it is an internal
detail — but the wrapper must preserve the flat capability set and
all error mappings.

### Async monitor-URL polling

Graph's `copy` operation responds with `202 Accepted` and a `Location`
header pointing to a monitor URL. The client polls that URL until the
operation completes or fails. Move is synchronous in most cases but
can also go async; both reuse the same poller.

The polling logic lives in a shared module
`src/remote_store/backends/_async_monitor.py`. Its contract —
interval, backoff, timeout, transient-5xx handling, cancellation — is
specified in ADR-0023 and referenced by the spec (GR-026).

### Capability matrix

Honest, not 10/10. `--` (dash) indicates a capability not declared.

| Capability | Declared | Rationale |
|---|---|---|
| `READ` | Yes | `GET /content` via `@microsoft.graph.downloadUrl`. |
| `WRITE` | Yes | `PUT /content` or upload session. |
| `DELETE` | Yes | `DELETE /items/{id}` (resolved from path). |
| `LIST` | Yes | `/children` endpoint with `@odata.nextLink` pagination. |
| `MOVE` | Yes | `PATCH` with new `parentReference`; may-be-async. |
| `COPY` | Yes | `POST copy`; async with monitor URL. |
| `METADATA` | Yes | `GET /items/{path}` with `$select`. |
| `GLOB` | -- | No native glob. `ext.glob` (prefix + fnmatch over `list_files`) serves the need. |
| `ATOMIC_WRITE` | Yes | Small PUT is atomic service-side; upload-session is atomic on commit. |
| `ATOMIC_MOVE` | -- | Graph move may be async; atomicity is not guaranteed. |
| `LAZY_READ` | Yes | Range reads via the download URL avoid loading the full file. |
| `SEEKABLE_READ` | -- | Graph streams are forward-only. `Store.read_seekable()` falls back to the default spool per ADR-0017. |

The spec pins the declaration in GR-003 and the rationale in
GR-012 through GR-027.

### Error mapping

Graph returns structured error bodies with a `code` field under
`error`. The mapping uses HTTP status plus `code`, not string
matching. `backend` is set to `"graph"` on every mapped error.

| HTTP | Graph code | remote_store error | Retryable? | Notes |
|---|---|---|---|---|
| 400 | `invalidRequest` | `RemoteStoreError` | -- | Bad request; typically a caller bug. |
| 401 | `InvalidAuthenticationToken` | (re-acquire + retry once) | Internal | One-shot token refresh; on second failure raise `PermissionDenied`. |
| 401 | `unauthenticated` | `PermissionDenied` | -- | Not recoverable by re-auth alone. |
| 401 | `tokenNotFound` | `PermissionDenied` | -- | Terminal; no refresh attempt (GR-029). |
| 401 | `invalidRequest` (401 scope) | `PermissionDenied` | -- | Terminal; no refresh attempt (GR-029). |
| 401 | any other `code` | `PermissionDenied` | -- | Only `InvalidAuthenticationToken` triggers the one-shot refresh (GR-029). |
| 403 | `accessDenied` | `PermissionDenied` | -- | |
| 404 | `itemNotFound` (item/path scope) | `NotFound` | -- | |
| 404 | `resourceNotFound` / drive scope | `BackendUnavailable` | -- | Drive misconfigured or deleted (GR-031). |
| 404 | Hidden-resource `accessDenied` | `PermissionDenied` | -- | Graph hides some denials as 404 (GR-031). |
| 409 | `nameAlreadyExists` | `AlreadyExists` | -- | Respect `conflictBehavior` for writes. |
| 409 | `invalidRange` | `RemoteStoreError` | -- | Upload-session `Content-Range` mismatch; not retried. |
| 416 | `invalidRange` | `RemoteStoreError` | -- | Range read beyond EOF. |
| 423 | `resourceLocked` | `ResourceLocked` | -- | ADR-0024. Not retried by default policy. |
| 429 | `activityLimitReached` | `BackendUnavailable` | Yes | `Retry-After` surfaced to the retry extension. |
| 500, 502, 503, 504 | (varies) | `BackendUnavailable` | Yes | Retry per policy. |
| 507 | `insufficientStorage` / `quotaLimitReached` | `BackendUnavailable` | -- | Quota exhausted; context carries `quota.*` fields. Not retryable (GR-054). |
| Network / timeout | (httpx exceptions) | `BackendUnavailable` | Yes | |

### Throttling

Graph throttling is mapped to `BackendUnavailable` with the
`Retry-After` header value propagated so the retry policy can honour
it. No new `RateLimitError` is introduced; the existing `RetryPolicy`
extension handles the backoff. Because `httpx` has no native retry,
the backend itself honours the full five-field `RetryPolicy`
(`max_attempts`, `backoff_base`, `backoff_max`, `jitter`, `timeout`)
in-backend. The spec 025 retry-policy spec gains RET-015 describing
this mapping.

### Resource locked

`423 Locked` / `resourceLocked` maps to a new `ResourceLocked` error
type (ADR-0024). Not retried by the default policy; callers decide
their own cadence.

### Upload session

Files larger than 4 MiB go through a resumable upload session:

1. `POST createUploadSession` → session URL with `expirationDateTime`.
2. Chunks uploaded as `PUT {sessionUrl}` with `Content-Range`.
3. Chunk size is a multiple of **320 KiB** (Graph's documented
   alignment requirement), capped at a backend-configurable maximum.
4. On chunk failure (5xx or network error), retry the same chunk
   according to `RetryPolicy`. Do not restart the session.
5. On `401` mid-session, re-acquire the token via the provider and
   retry the chunk. Do not restart the session (session URL is
   pre-authorised).
6. On `PUT` responses containing `nextExpectedRanges`, resume from
   the server's expected range rather than trusting the client's
   view.
7. Session URLs live for a bounded time (Graph documents ~several
   hours). Session expiry mid-upload surfaces as an error; the
   retry handling is documented in the spec.
8. On caller cancellation or unrecoverable failure, the backend
   issues `DELETE {sessionUrl}` as a best-effort cleanup.

### Range download via downloadUrl

Graph returns item metadata containing an `@microsoft.graph.downloadUrl`
— a short-lived unauthenticated pre-signed URL. The `/content`
endpoint returns a `302` redirect to this URL, and only the URL
reliably honours the `Range` header.

`read_bytes(path, start, length)` issues a `GET` with `Range:
bytes=<start>-<end>` directly to the download URL (no `Authorization`
header; the URL is pre-signed). If the URL expires mid-read
(`403` / `401` from the pre-signed host), the backend re-fetches the
item metadata to obtain a fresh download URL and resumes the read
from the next unread byte using another `Range` request. The retry
budget is bounded by `RetryPolicy`.

### Module layout

Referenced here for the implementation-phase work — the spec does
not hard-wire file names but does hard-wire responsibilities.

```
src/remote_store/backends/
  _graph.py           # GraphBackend (AsyncBackend implementation)
  _graph_http.py      # httpx client wrapper, error mapper, pagination
  _graph_transfer.py  # upload-session driver, range-download driver
  _async_monitor.py   # shared monitor-URL poller (ADR-0023)
  _graph_auth.py      # GraphAuth helper (optional; inlined if small)
```

### User onboarding

Graph onboarding is the single largest UX hurdle for this backend, so
the implementation phase ships a dedicated guide. The guide covers:

- **OAuth flow decision.** Daemon service → client-credentials.
  Interactive user → device-code. If you are not sure, start with
  device-code.
- **App registration.** Walkthrough of registering an application in
  Microsoft Entra (formerly Azure AD), configuring redirect URIs for
  device-code (`https://login.microsoftonline.com/common/oauth2/nativeclient`),
  creating a client secret for client-credentials, and enabling the
  right permissions.
- **Permissions (scopes).** `Files.ReadWrite.All` and
  `Sites.ReadWrite.All` as the typical baseline. Read-only variants
  exist for read-only workloads. Application vs delegated permission
  types.
- **Admin consent.** Client-credentials requires a tenant admin to
  grant admin consent on the application permissions. Direct link to
  the admin-consent URL construction.
- **Token cache location.** Where the cache file lives, how to change
  it, how to clear it.
- **Common errors.** `AADSTS65001` (consent missing), `AADSTS700016`
  (app not found in tenant), `AADSTS50076` (MFA required), and the
  403 `accessDenied` case where scopes are correct but Graph denies
  access because the target drive is outside the principal's
  permissions.
- **`resolve_drive_id` usage.** Example snippets for OneDrive,
  SharePoint, and Teams.

### Documentation deliverables (implementation phase)

Tracked here so the implementation run does not lose them:

- `guides/backends/graph.md` — primary backend guide.
- `examples/graph-backend.md` or the corresponding module docstring
  rendered by `gen_pages.py`.
- `FEATURES.md` row for Graph (capabilities, extras, status).
- README backends line and Quick Start snippet (optional).
- Docstrings on `GraphBackend`, `GraphAuth`, `resolve_drive_id`, and
  public helpers.

### Test plan

- **Unit tests** via `respx` (httpx mock transport) covering every
  operation, every error-code mapping, pagination across multiple
  pages, async copy polling (success + failure), upload-session
  chunking (small, exact boundary, large, retry, resume, abort), and
  `@microsoft.graph.downloadUrl` range reads (including URL expiry
  mid-read).
- **Integration tests** gated by `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`,
  `GRAPH_CLIENT_SECRET`, `GRAPH_DRIVE_ID`. Skip cleanly when unset.
  Gate pattern mirrors Azure integration tests.
- **Capability matrix test** asserting that declared capabilities
  match the matrix in GR-003 and that unsupported capabilities raise
  `CapabilityNotSupported` where applicable.
- **Round-trip test** writing a 10 MiB file via upload session,
  reading it back via `Range` to validate byte-equality across the
  large-file path.
- **Conformance suite** reusing the shared backend conformance tests,
  parameterised for async.

Every spec ID in GR-NNN is traceable to at least one test via
`@pytest.mark.spec("GR-NNN")` per 000-process.md Rule 2.

## Alternatives Considered

### Option A — `msgraph-sdk`

Rejected. See ADR-0021.

### Option B — Legacy SharePoint REST API

Rejected. Would require separate code paths for OneDrive vs
SharePoint and does not cover Teams files as a first-class target.
Graph replaces all of these with a single unified surface.

### Option C — One backend per product (OneDrive, SharePoint, Teams)

Rejected. The underlying storage model in Graph is identical — they
are all drives identified by a `drive_id`. Splitting them into
separate backends would triple the maintenance surface for zero
semantic benefit.

### Option D — Item-id addressing in v1

Rejected for v1. Store paths are the user-facing addressing model
across every other backend; introducing a second mode in the same
backend adds complexity without an urgent use case. Explicitly
deferred in GR-011 so the deferral is tracked.

## Impact

- **Public API.** Adds `GraphBackend`, `GraphAuth`, and
  `resolve_drive_id` under `remote_store.backends._graph`, re-exported
  from `remote_store.backends` behind a guarded import (the pattern
  used for every optional-dependency backend in
  `src/remote_store/backends/__init__.py`). Adds `ResourceLocked` to
  the top-level error exports.
- **Backwards compatibility.** Purely additive. No existing behaviour
  changes except the new `ResourceLocked` error class — which is
  unreachable from backends other than Graph.
- **Performance.** Native async throughout. The sync wrapper pays
  the event-loop overhead that all async-to-sync bridges pay; this
  matches ADR-0012's design for async-native backends.
- **Testing.** `respx` becomes a test-only dependency if not already
  pulled in by the HTTP backend tests. Integration tests need a
  real Microsoft 365 tenant; gated by env vars.

### Ripple-check

Per `sdd/CLAUDE-REFERENCE.md`, this RFC touches:

- **Backends.** New `graph` backend. `FEATURES.md` row added in the
  implementation phase.
- **Extras.** New `graph` extra in `pyproject.toml` pulling `httpx`
  and `msal`.
- **Spec 005 (errors).** Amended in this PR to add ERR-013
  `ResourceLocked`.
- **Spec 025 (retry).** Amended in this PR to add RET-015 Graph retry
  mapping.
- **Capabilities.** No new capabilities; existing flags used as
  declared.
- **ADRs.** ADR-0021, ADR-0022, ADR-0023, ADR-0024 all new.

## Open Questions

None blocking. Secondary items deferred to post-v1:

- Item-id addressing (tracked in GR-011).
- Managed-identity / workload-identity auth (supported via
  token-provider protocol today; first-class packaging deferred).
- Surfacing `file.hashes` into `ext.integrity` (plumbed through
  `FileInfo.extra` in v1 per GR-049; wired up when the extension
  gains a Graph fast-path).

## References

- Spec: `sdd/specs/044-graph-backend.md`
- ADRs: `sdd/adrs/0021-graph-sdk-choice.md`,
  `sdd/adrs/0022-graph-auth-model.md`,
  `sdd/adrs/0023-async-monitor-polling.md`,
  `sdd/adrs/0024-resource-locked-error.md`
- Backend contract: `sdd/specs/003-backend-adapter-contract.md`
- Error model: `sdd/specs/005-error-model.md`
- Retry policy: `sdd/specs/025-retry-policy.md`
- Async API: `sdd/adrs/0012-async-store-backend-api.md`
- Seekable read: `sdd/adrs/0017-seekable-read-on-store-api.md`
- Azure backend (pattern reference): `sdd/rfcs/rfc-0001-azure-backend.md`,
  `sdd/specs/012-azure-backend.md`
- Microsoft Graph v1.0: https://learn.microsoft.com/graph/api/overview
- Graph drives and items:
  https://learn.microsoft.com/graph/api/resources/onedrive
- Upload sessions:
  https://learn.microsoft.com/graph/api/driveitem-createuploadsession
- MSAL Python: https://learn.microsoft.com/entra/msal/python/
