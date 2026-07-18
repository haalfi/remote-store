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
throughout.

## Motivation

Microsoft positions Graph as the unified file API across OneDrive,
SharePoint, and Teams. A Graph-first backend gives us one auth model,
one permission model, one path/item-id scheme, and one module to
maintain instead of three. Legacy SharePoint REST is a fallback only if
a specific Store operation is genuinely unavailable on Graph — and all
Store operations we target are available on Graph.

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
- Native async implementation per ADR-0012.
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

**Module:** `remote_store.aio.backends._graph` (sub-package; async-native)
**Name:** `"graph"`
**Optional extra:** `pip install "remote-store[graph]"`
**Dependencies:** the `graph` extra's pinned set lives in `pyproject.toml`; see ADR-0021 for the SDK choice.
**Spec:** `sdd/specs/044-graph-backend.md` (GR-001 through GR-058,
grouped by topic, with later additions slotted under the section
they belong to rather than appended at the end — IDs are
allocation-order, not section-order)

The backend name is `"graph"` rather than `"onedrive"` or `"sharepoint"`
because a single instance can target any of those services depending on
the `drive_id` resolved at construction. The name reflects the unified
API, not the user-visible product.

### SDK decision

Evaluated honestly against the narrow surface we need (a small set of
endpoints, async-native, custom polling and upload-session logic):

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
shapes. MSAL token caching uses a persistent backing file; the cache
path, mechanism, and override rules are specified by GR-007 in
[044-graph-backend.md](../specs/044-graph-backend.md) (single source of
truth).

Authorization headers are redacted anywhere request or response
metadata surfaces in logs, error messages, or debug dumps (AF-008).

ADR-0022 locks the auth model.

### Addressing

Single `drive_id` per backend instance, required at construction.
Identity-stable: it never changes for the lifetime of the backend,
which is important for `ext.cache` safety (the cache key derives from
backend identity).

An optional `base_path` constructor parameter (added during
implementation; GR-058) scopes the backend to a drive subfolder:
keys resolve to `{base_path}/{key}` under the drive root and keys
returned by listing stay `base_path`-relative, mirroring
`SFTPBackend.base_path`.

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

#### `GraphUtils.resolve_drive_id` helper

Users who have a drive URL or site URL rather than a raw `drive_id`
call a namespaced helper that resolves the three canonical shapes:

- **OneDrive personal / for business.** `/me/drive` → `drive.id`.
  The `GraphAuth` principal determines whose drive.
- **SharePoint document library.** `site_url` → `site_id` →
  `/sites/{site_id}/drives` → pick by name.
- **Teams channel files.** Team/channel → `filesFolder` → `drive_id`.

The helper is exposed as `GraphUtils.resolve_drive_id(...)` (and the
async counterpart `GraphUtils.aresolve_drive_id(...)`), mirroring the
`SFTPUtils` namespace pattern in `backends/_sftp.py`. It is a
one-shot translation used at application wiring time; the resolved
`drive_id` is then passed to `GraphBackend` and stored. The backend
does not repeat the resolution on each call.

### Async posture

The backend implements `AsyncBackend` natively (ADR-0012). All I/O
operations are `async def`, backed by `httpx.AsyncClient`. The
pattern parallel for this implementation is `AsyncAzureBackend`
(`src/remote_store/aio/backends/_azure.py`), not the sync
`AzureBackend` — sync Azure wraps the sync Azure SDK, which is the
wrong reference shape for a native-async backend.

`open_atomic()` has no async equivalent on `AsyncBackend` (ASYNC-062);
`GraphBackend` therefore implements only `write_atomic` (GR-040) and
ships no Graph-specific `open_atomic` surface.

The sync-side story is **out of scope for this RFC.** Sync callers
reach any `AsyncBackend` through the existing `AsyncBackendSyncAdapter`
(ADR-0025, ASYNC-080..093), which also synthesises `open_atomic` via
spool-and-flush over `write_atomic` (ASYNC-085). Graph plugs into
that bridge unchanged; no Graph-specific sync code is part of this
proposal.

### Async monitor-URL polling

Graph's `copy` operation responds with `202 Accepted` and a `Location`
header pointing to a monitor URL. The client polls that URL until the
operation completes or fails. Move is synchronous in most cases but
can also go async; both reuse the same poller.

The polling logic lives **backend-local** in
`src/remote_store/aio/backends/_graph/monitor.py` (a module inside
the Graph sub-package alongside `backend.py` / `http.py` /
`transfer.py` / `auth.py`), or inline in `backend.py` while it
stays small. ADR-0023 records the reality check: an earlier draft
proposed a shared `backends/_async_monitor.py` on the premise that
Azure cross-account copy would reuse it, but `AsyncAzureBackend.copy`
ships in v0.27.0 without any polling, and there is no second consumer
today. The contract — interval, backoff, timeout, transient-5xx
handling, cancellation, `status_parser` — is in ADR-0023 and
referenced by the spec (GR-026). If a second backend genuinely needs
the same shape, a follow-up ADR supersedes ADR-0023 and the function
moves to a shared location.

### Capability matrix

Honest capability declarations are central to this backend's design — several capabilities are
explicitly withheld with rationale (for example, `SEEKABLE_READ` is withheld because Graph
streams are forward-only; `ATOMIC_MOVE` because Graph move may be asynchronous). See GR-003
in `sdd/specs/044-graph-backend.md` for the complete declaration and per-capability rationale.

### Error mapping

Graph returns structured error bodies with a `code` field under
`error`. The mapping uses HTTP status plus `code`, not string
matching — no fragile string parsing. `backend` is set to `"graph"`
on every mapped error. See GR-028 through GR-034 plus GR-045 / GR-046
/ GR-054 / GR-055 in `sdd/specs/044-graph-backend.md` for the
complete mapping table.

### Throttling

Graph throttling is mapped to `BackendUnavailable` with the
`Retry-After` header value honoured by the in-backend retry loop
before the next attempt (it is not carried on the raised error; see
GR-034 / GR-048). No new `RateLimitError` is introduced; the existing `RetryPolicy`
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

An internal `_read_bytes(path, start, length)` helper (private; not
a public Store method — see GR-015) issues a `GET` with `Range:
bytes=<start>-<end>` directly to the download URL (no `Authorization`
header; the URL is pre-signed). If the URL expires mid-read
(`403` / `401` from the pre-signed host), the backend re-fetches the
item metadata to obtain a fresh download URL and resumes the read
from the next unread byte using another `Range` request. The retry
budget is bounded by `RetryPolicy`.

### Module layout

Referenced here for the implementation-phase work — the spec does
not hard-wire file names but does hard-wire responsibilities and
location. `GraphBackend` is async-native, so it sits under
`aio/backends/` (matching `aio/backends/_azure.py` and
`aio/backends/_memory.py`), not under the sync `backends/` package.
The component count (backend, HTTP wrapper, transfer drivers,
monitor poller, auth helper, utils) makes a sub-package preferable
to the sibling-file form used by smaller `aio/backends/` modules.

```
src/remote_store/aio/backends/_graph/
  __init__.py         # re-exports GraphBackend, GraphAuth, GraphUtils
  backend.py          # GraphBackend (AsyncBackend implementation)
  http.py             # httpx client wrapper, error mapper, pagination
  transfer.py         # upload-session driver, range-download driver
  monitor.py          # backend-local monitor-URL poller (ADR-0023)
  auth.py             # GraphAuth helper
  utils.py            # GraphUtils namespace (resolve_drive_id, …)
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
- **`GraphUtils.resolve_drive_id` usage.** Example snippets for
  OneDrive, SharePoint, and Teams.

### Documentation deliverables (implementation phase)

Tracked here so the implementation run does not lose them:

- `guides/backends/graph.md` — primary backend guide (usage,
  configuration, capability notes).
- `guides/backends/graph-setup.md` — initial setup walkthrough
  modelled on `docs-src/guides/backends/azure-hns-setup.md`:
  Microsoft Entra app registration, redirect URIs, client-secret vs
  certificate, admin-consent URL construction, common `AADSTS*`
  errors and their fixes. Onboarding is the largest UX hurdle for
  this backend and merits a dedicated step-by-step doc separate
  from the usage guide.
- `examples/graph-backend.md` or the corresponding module docstring
  rendered by `gen_pages.py`.
- `FEATURES.md` row for Graph (capabilities, extras, status); the
  capability columns must match GR-003, including `WRITE_RESULT_NATIVE`
  and the explicit absence of `USER_METADATA`.
- `__all__` ↔ `index.md` parity (ID-173): every public symbol added by
  this work (`GraphBackend`, `GraphAuth`, `GraphUtils`,
  `ResourceLocked`) must appear in the rendered API reference. The
  `check_api_docs.py` parity check is a hard CI gate; the
  implementation PR ships the docs entries in the same commit as the
  `__all__` additions.
- README backends line and Quick Start snippet (optional).
- Docstrings on `GraphBackend`, `GraphAuth`, `GraphUtils` (including
  each `@staticmethod`), and public helpers.

### Test plan

This plan is the Graph-specific overlay on the **contract-expanding
feature** Definition of Done (000-process.md § Feature-type Definition
of Done — owned by BK-237). The DoD checklist takes precedence on any
overlap; the items below are additions, not substitutes.

The plan uses the kind/stage axes from ADR-0028. Graph is an HTTP
backend — the full Stage 1 (replay), Stage 3 (live) demotion path
applies. Graph has no Stage 2 (no Docker emulator exists for the
Microsoft Graph surface), and that gap is explicit: Stage 3 is the
authoritative tier; Stage 1 replay is what runs in default CI.

- **Stage 1 — unit (`respx` direct).** `respx`-stubbed
  `httpx.AsyncClient` covering every operation, every error-code
  mapping, pagination across multiple pages, async copy polling
  (success + failure), upload-session chunking (small, exact
  boundary, large, retry, resume, abort), and
  `@microsoft.graph.downloadUrl` range reads (including URL expiry
  mid-read). These exercise the request-construction layer; they do
  not exercise the live wire format.
- **Stage 1 — replay (`graph_replay` fixture).** Per the
  HTTP-backend recipe in ADR-0028, a `graph_replay` Stage 1 fixture
  exercises the real `GraphBackend` code path with the HTTP transport
  stubbed by a recorded cassette. Refresh follows the explicit
  `pytest --stage=3 --record` recipe (TEST-009 cassette-refresh
  policy) — CI does not silently re-record. **Prerequisite work for
  the impl PR-set** (not free against today's spine): the existing
  replay machinery is Azure-hardcoded and has to be generalised
  before Graph can plug in. Concretely:
  - `tests/backends/conformance/conftest.py:vcr_cassette_dir`
    currently returns `CASSETTE_DIR_AZURE` unconditionally; TEST-007
    mandates `cassettes/<backend>/`, so a per-backend dispatch is
    needed (Graph gets `cassettes/graph/`, not "alongside" Azure).
  - The id-alias map, `_AZURE_REAL_FIXTURE_IDS` set, and missing-cassette
    → skip hook in `tests/backends/fixtures/registry.py` recognise
    only `azure_*` ids; `graph_replay` needs the same recognition.
  - **Cassette scrub layer** (`tests/backends/fixtures/_cassettes.py`)
    is Azure-specific (`x-ms-*`, SharedKey, connection-string,
    Azurite). Graph uses `Authorization: Bearer` plus pre-signed
    `@microsoft.graph.downloadUrl` hosts — without a Graph-aware
    scrub list, **a bearer token would survive and leak into
    committed cassettes.** This is a security-critical prerequisite,
    not a polish item.
  - `scripts/record_cassettes.py` `_BACKENDS` carries only `azure`
    today; a `graph` entry is part of the same work.
  - **`httpx` streaming-replay path is unproven.** Azure async needed
    a bespoke `AsyncioRequestsTransport` shim because vcrpy 8.1.1's
    aiohttp stub cannot stream a response body
    (`azure_replay_async.py:9-23`); whether vcrpy can capture/replay
    `httpx.AsyncClient.stream()` for GR-012 (chunked reads) and
    GR-015 (`Range`-over-`downloadUrl`) is open. `respx` has no
    record-from-live mode and is unit-only.

  If the generic spine + scrub + httpx-streaming-replay package
  cannot land alongside the Graph backend, the Stage-1-replay scope
  shrinks to the operations that don't require streaming and the
  conformance matrix runs against Graph at Stage 3 only — call this
  out explicitly in the impl PR.
- **Stage 3 — live (`graph_live` fixture).** Gated by the
  `RS_TEST_LIVE_GRAPH=1` opt-in **plus** the three credential env
  vars `GRAPH_CLIENT_ID`, `GRAPH_TENANT_ID` (`consumers`),
  `GRAPH_DRIVE_ID`. The shipped tier is device-code / consumer — no
  client secret; the MSAL token cache the first interactive sign-in
  writes keeps later runs non-interactive. Missing opt-in skips
  cleanly; opt-in with a missing credential var fails loud. This
  mirrors the Azure live-test pattern at
  `tests/backends/fixtures/fixtures.toml` and `_live_env.py` —
  credential presence alone is deliberately not enough to opt into
  live runs. Stage 3 is the authoritative tier for any behaviour that
  depends on Graph service semantics (chunk alignment, real
  throttling with authentic `Retry-After`, real `423 resourceLocked`,
  real `507`/quota responses); Stage 3 discoveries get cassetted
  back into the `graph_replay` fixture so the next default CI run
  catches the regression at Stage 1 cost.
- **`WriteResult` conformance.** `TestWriteResultConformance` in
  `tests/backends/conformance/test_atomic.py` is sync-fixtured today
  (via `fixture_params(Capability.WRITE)`, default `is_async=False`);
  it cannot host a native-async backend without modification, and
  the async sister in `test_async_extended.py` covers only WR-013.
  Pick one and ship it with the impl PR-set: (a) land an async
  `TestWriteResultConformance` parametrised over async fixtures so
  WR-001a / 004 / 005 / 012 / 013 exist for `AsyncBackend` before
  Graph plugs in, or (b) register a sync fixture entry that wraps
  `GraphBackend` in `AsyncBackendSyncAdapter` to consume the existing
  sync suite. Either way, both the small-file and upload-session
  paths populate the rich fields from the `driveItem` response
  (GR-018, GR-019).
- **`USER_METADATA` strict-gate test** — non-empty `metadata=` raises
  `CapabilityNotSupported` per WR-010; empty mapping and `None` are
  no-ops (GR-003).
- **Capability matrix test** asserting that declared capabilities
  match the matrix in GR-003 and that unsupported capabilities raise
  `CapabilityNotSupported` where applicable.
- **Round-trip test** writing a 10 MiB file via upload session,
  reading it back via `Range` to validate byte-equality across the
  large-file path. (This is the largest payload the conformance
  matrix carries today — ~1 MiB is the prior precedent — and is
  deliberately Stage-3-only on the cost side; Stage 1 cassettes
  record a single representative round-trip.)
- **Dafny-oracle ripple.** ADR-0024 ships a Dafny
  `Error.ResourceLocked(path: string, backend: string)` variant
  plus dispatch in `tests/backends/dafny/_helpers.py::_raise_if_err`.
  The `dafny_oracle` and `dafny_oracle_async` fixtures
  (`fixtures.toml:83-99`) participate in the conformance spine, so
  the variant addition and dispatcher update are conformance-fixture-
  affecting changes — bundled with the impl PR per ADR-0024
  (Consequences: "Ships as a coupled bundle").
- **e2e chain.** `tests/e2e/test_async_streaming_integrity.py`
  builds its async chain by hand in the test body; there is no
  registration seam. Wiring Graph in requires (a) adding two-layer-
  gate credential plumbing to `tests/e2e/conftest.py` (today wires
  only Docker-service settings), (b) editing the chain construction
  to insert a conditional Graph hop alongside the existing
  `if _async_azure_available():` branch (e.g.
  `AsyncMemory(seed) → AsyncAzure → AsyncGraph → SyncWrapped(Local) →
  AsyncMemory(sink)` when both Azurite and Graph live credentials
  are reachable), and (c) handling the `LAZY_READ` chunk-exemption
  if Graph's range-fallback path (GR-015) materialises during the
  test. The integrity assertion (SHA-256 identical across hops) and
  the lazy-read chunking assertion (count > 1, max_chunk < file_size)
  then cover the streaming contract Graph is required to honour. The
  Graph hop is conditional on the same two-layer gate as the live
  fixture and skips cleanly otherwise. Non-trivial — not a "plug in".

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

- **Public API.** Adds `GraphBackend`, `GraphAuth`, and `GraphUtils`
  (namespace class carrying `resolve_drive_id`, mirroring `SFTPUtils`)
  under `remote_store.aio.backends._graph`, re-exported from
  `remote_store.aio.backends` behind a guarded import (the pattern
  used by the other async-native backends in
  `src/remote_store/aio/backends/__init__.py`). Adds `ResourceLocked`
  to the top-level error exports.
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
- **Extras.** New `graph` extra in `pyproject.toml`, which holds the
  pinned dependency set; ADR-0021 records the SDK choice.
- **Spec 005 (errors).** Amended at RFC acceptance to add ERR-013
  `ResourceLocked`. The runtime class (`remote_store._errors.ResourceLocked`)
  and Dafny variant ship with the backend implementation per the
  ID-127 bundled-sub-task note in `sdd/BACKLOG.md`.
- **Spec 025 (retry).** Amended at RFC acceptance to add RET-015 Graph
  retry mapping.
- **Spec 045 (`WriteResult`).** Graph honours WR-001..WR-013 unchanged;
  `WRITE_RESULT_NATIVE` is declared (GR-003), `source="native"` on both
  small-file and upload-session paths (GR-018, GR-019). No amendment
  to spec 045 required.
- **Capabilities.** `WRITE_RESULT_NATIVE` declared; `USER_METADATA`
  withheld with rationale (GR-003). No new capability defined.
- **ADRs.** ADR-0021, ADR-0022, ADR-0023, ADR-0024 all accepted at
  RFC acceptance.

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
