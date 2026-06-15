# Microsoft Graph Backend

The Graph backend stores files in **OneDrive, SharePoint, and Microsoft Teams**
through the [Microsoft Graph](https://learn.microsoft.com/en-us/graph/) REST API,
talking to a single drive over [`httpx`](https://www.python-httpx.org/) with bearer
tokens from [`msal`](https://learn.microsoft.com/en-us/entra/msal/python/).

It is **async-only**: there is no sync `Store` wrapper and no config `type=`
string, so it is constructed directly and used through `AsyncStore`. For the
one-time credential and app-registration setup, follow the
[Microsoft Graph access setup](graph-setup.md) guide first.

!!! note "Verification coverage"
    The backend is live-verified against **consumer OneDrive** (device-code
    auth). SharePoint and OneDrive for Business drives go through the same
    Graph API and are covered by mocked tests, but are less exercised in
    practice — see the [operational caveats](#operational-caveats) for the
    known SharePoint-specific behaviours.

## Installation

```bash
pip install "remote-store[graph]"
```

This pulls in `httpx`, `msal`, `msal-extensions`, and `platformdirs` (the last
two persist the MSAL token cache multi-process-safely).

## Usage

A backend instance targets one drive, identified by an opaque `drive_id`.
Resolve the id once at wiring time, then hand it to the backend:

```python
import asyncio

from remote_store.aio import AsyncStore, GraphAuth, GraphBackend, GraphUtils


async def main() -> None:
    # 1. A token provider. Device-code (interactive) auth against a personal
    #    Microsoft account needs only tenant + client id — no secret.
    auth = GraphAuth(tenant_id="consumers", client_id="<entra-app-id>")

    # 2. Resolve the target drive ("me" = the signed-in user's OneDrive).
    #    Inside async code, use the async resolver — the sync
    #    GraphUtils.resolve_drive_id runs its own event loop internally and
    #    raises RuntimeError when called from a running one.
    drive_id = await GraphUtils.aresolve_drive_id("me", token_provider=auth)

    # 3. Construct the backend and use it through AsyncStore.
    backend = GraphBackend(drive_id, token_provider=auth)
    async with AsyncStore(backend, root_path="Documents") as store:
        await store.write("report.csv", b"col1,col2\n1,2\n", overwrite=True)
        data = await store.read_bytes("report.csv")


asyncio.run(main())
```

`token_provider` is any `Callable[[], str]` or `Callable[[], Awaitable[str]]`
returning a bearer token; `GraphAuth` is the built-in MSAL implementation but
any callable works (e.g. a token minted by your own identity layer).

## Authentication

`GraphAuth` selects the OAuth flow from the credentials you supply:

| Supplied | Flow | Account type | Use for |
|----------|------|--------------|---------|
| `client_secret` or `client_certificate` | Client-credentials (app-only) | Work/school tenant | CI, daemons, services |
| neither | Device-code (delegated) | Personal or work/school | Notebooks, CLIs, local dev |

```python
# App-only (client-credentials) against a work/school tenant:
auth = GraphAuth(
    tenant_id="<tenant-guid>",
    client_id="<entra-app-id>",
    client_secret="<secret>",  # accepts a Secret; masked in repr
)
```

The token is cached by MSAL on disk (default
`<user_config_dir("remote-store")>/graph_token_cache.json`; override with
`cache_path`). The cache is persisted multi-process-safely — a sibling
`<cache_path>.lockfile` coordinates concurrent writers, so several workers or
processes sharing the default cache will not corrupt it. Entra app
registration, redirect URIs, admin consent, and the `AADSTS*` error catalogue
are covered in the [setup guide](graph-setup.md).

## Resolving a drive_id

`GraphUtils.resolve_drive_id` (and its async twin `aresolve_drive_id`) turn a
human-meaningful target into the opaque `drive_id` the backend needs:

| Target | Resolves to |
|--------|-------------|
| `"me"` | the authenticated user's default OneDrive (`GET /me/drive`) |
| a SharePoint site URL `str` | the site's default document library |
| `(site_url, library_name)` tuple | a named document library on that site |
| `{"team_id": ..., "channel_id": ...}` mapping | a Teams channel's backing drive |

```python
drive_id = GraphUtils.resolve_drive_id(
    "https://contoso.sharepoint.com/sites/Marketing",
    token_provider=auth,
)
```

The sync `resolve_drive_id` is for synchronous wiring code (config loading,
CLI setup): it runs its own event loop internally, so calling it from inside
a running event loop raises `RuntimeError`. Inside `async def` code, always
use `await GraphUtils.aresolve_drive_id(...)`.

A `drive_id` is immutable for the life of a backend instance — point a second
`GraphBackend` at a different drive rather than mutating one.

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `drive_id` | `str` | *(required)* | Opaque Graph drive id (resolve via `GraphUtils`) |
| `token_provider` | `Callable` | *(required)* | Sync or async callable returning a bearer token |
| `base_url` | `str` | `https://graph.microsoft.com/v1.0` | Graph API root |
| `http_client` | `httpx.AsyncClient` | `None` | Reuse an existing client; the caller owns its lifecycle (`aclose()` leaves it open). When omitted, one is created lazily and closed by `aclose()` |
| `retry` | `RetryPolicy` | `None` | Transient-failure retry policy; `None` uses the default profile |
| `upload_chunk_size` | `int` | 10 MiB | Upload-session chunk size; must be a positive multiple of 320 KiB and `< 60 MiB` |
| `copy_timeout` | `float \| None` | `None` | Wall-clock budget for copy/move monitor polling (see [caveat](#operational-caveats)) |
| `base_path` | `str` | `""` | Scope every operation to this drive subfolder; keys are addressed relative to it and listings return relative keys. Defaults to the drive root |
| `client_options` | `dict` | `None` | Extra kwargs passed through to the internal `httpx.AsyncClient` |

## Operational caveats

### Spooling and `TMPDIR`

When you `write()` an `AsyncIterator[bytes]` of unknown length, Graph's
upload-session protocol requires the total size up front, so the backend
spools the stream to a `SpooledTemporaryFile` (system temp, no explicit
directory) and replays it once the length is known. On platforms with a
small or restricted temp volume (Windows, locked-down containers), redirect
the spill by setting **`TMPDIR`** (or the platform equivalent) before writing
large unknown-length streams. Passing `bytes` instead of an iterator avoids
the spool pass entirely. Spill events are logged at DEBUG with the marker
`graph.upload.spool_spilled`.

The same concern exists on the **read side**: the backend does not declare
`SEEKABLE_READ`, so `read_seekable()` — which the `ext.arrow` / `ext.parquet`
extensions use for large files (through the
[sync adapter](#extensions-sync-vs-async)) — is synthesised by spooling the
entire file to the temp volume before the consumer can seek. Reading a large
Parquet file over Graph therefore needs temp space for the whole file; size
`TMPDIR` accordingly.

### Connection-pool tuning under high fan-out

The internal `httpx.AsyncClient` uses httpx's default connection pool —
**100 connections** (`max_keepalive_connections=20`). Under very high
concurrent fan-out (a large `asyncio.gather` over a shared backend, or many
bridged threads) that ceiling is reached silently: requests queue and, on pool
exhaustion, surface as an opaque `BackendUnavailable` rather than anything that
names the pool as the cause.

Raise the ceiling by passing an [`httpx.Limits`](https://www.python-httpx.org/advanced/resource-limits/)
through `client_options` (forwarded verbatim to the client):

```python
--8<-- "examples/snippets/graph_client_tuning.py:pool-limits"
```

Size `max_connections` to your fan-out, not arbitrarily high: each connection is
a socket against Graph, which itself throttles (`429`). This is the same
passthrough mechanism every `client_options` key uses; supplying your own
`http_client` instead lets you set limits on the client you construct.

### SharePoint-backed drives are less exercised

Live verification runs against consumer OneDrive only. SharePoint-backed
drives have known divergences the backend already accounts for — some ignore
HTTP range requests (see [Streaming](#streaming)) — and others that the live
tier cannot reach. Treat SharePoint/business deployments as less-travelled
ground and validate your workload before relying on it in production.

### `overwrite=True` can still raise `AlreadyExists`

Overwriting an existing **file** with `overwrite=True` is expected to replace it and
succeed. Two situations can still surface an `AlreadyExists` error despite the flag:

- **SharePoint-backed drives** may reject the replace of an existing file with a conflict.
  This does not happen on consumer OneDrive (the live-verified tier).
- **Concurrent creation of the same new key**, reproduced on consumer OneDrive: when several
  writers race to create the *same not-yet-existing* key, the losers can receive
  `AlreadyExists` even with `overwrite=True`. **Content integrity holds** — one writer's bytes
  land intact, with no tearing or interleaving; only the error surfaced to the losers diverges
  from the single-writer expectation.

In both cases the backend deliberately does **not** paper over the conflict — silently
treating it as success could mask a genuine collision and would have to guess at a response
shape the project cannot reproduce. If you need overwrite-or-create semantics under
contention, delete the target first and then write, or serialise the writers.

### `copy_timeout=None` is unbounded by default

Graph performs `copy()` (and sometimes `move()`) asynchronously: the backend
polls a monitor URL until completion. With the default `copy_timeout=None`
there is **no backend-imposed ceiling** — a copy against an unresponsive
endpoint can block indefinitely. The backend does not substitute a fallback.
Callers that cannot tolerate an unbounded wait must either set `copy_timeout`
to a finite value at construction, or wrap the call in an external ceiling
(`asyncio.timeout(...)`). On expiry the poller raises `BackendUnavailable`
with the (query-stripped) monitor URL, poll count, and last status.

## Concurrency & consistency

`GraphBackend` is async-only and built for concurrent use on a single event loop:

- **One instance, one loop.** A `GraphBackend` is safe for concurrent coroutines driven
  by one event loop — `asyncio.gather` over a shared instance is fine. It is *not* safe to
  share across event loops; give each loop its own instance.
- **Safe from threaded sync code.** Driven through
  [`AsyncBackendSyncAdapter`](../async-sync-bridges.md), a single instance is safe for
  concurrent threads — the adapter serialises them onto its private loop. This is **unlike**
  the SFTP backend, where you need one instance per thread.
- **`overwrite=False` is a race-free create-if-absent.** It maps to a server-side atomic
  create (Graph's create-if-absent conflict behaviour), so two writers racing to create the
  same new key cannot both win — the loser gets `AlreadyExists`. There is no client-side
  check-then-write window, unlike the TOCTOU behaviour described in the
  [concurrency guide](../../explanation/concurrency.md#overwritefalse-and-toctou).
- **`move` and `copy` are not atomic at the point of use.** `copy` (and sometimes `move`)
  runs server-side and is monitor-polled to completion; a crash mid-operation can leave both
  source and destination. Two callers racing a `move` / `copy` of the same item resolve to
  one winner, but the loser's error may be generic rather than typed.
- **Read-your-writes holds.** After a successful `write`, a subsequent `read` on the same
  instance returns the new content.

See the [concurrency guide](../../explanation/concurrency.md#concurrent-use-posture) for the
cross-backend posture table and the sync/async bridge rules.

## Write results

The backend declares `WRITE_RESULT_NATIVE`. Writes return a
[`WriteResult`](../../reference/api/models.md) populated directly from the
`driveItem` response — `size`, `etag`, and `last_modified` — with no extra
`HEAD` round trip. It does **not** declare `USER_METADATA`: passing a non-empty
`metadata=` raises `CapabilityNotSupported`; `{}` / `None` are no-ops.

## Capabilities

Supports all capabilities except `GLOB`, `SEEKABLE_READ`, `ATOMIC_MOVE`, and
`USER_METADATA`. For glob, the portable `ext.glob.glob_files()` fallback works
(Graph is `LIST`-capable) — but only through the sync adapter, since the
`ext.*` suite is sync-only (see [below](#extensions-sync-vs-async)). See the
[capabilities matrix](../../reference/capabilities-matrix.md) for full details.

## Extensions: sync vs async

The extension ecosystem is split between the two Store surfaces, and the
async side is much smaller:

| Extension surface | Native `AsyncStore` | Sync `Store` (via adapter) |
|-------------------|---------------------|----------------------------|
| `aio.ext.write` — `write_with_hash` | Yes | — |
| [`ext.*`](../../reference/api/extensions/index.md) — the sync suite (glob, cache, arrow, …) | — | Yes |

Because `GraphBackend` is async-only, a native `AsyncStore` consumer has no
`ext.*` surface at all — only `aio.ext.write.write_with_hash`. To use a sync
extension over Graph, wrap the backend in
[`AsyncBackendSyncAdapter`](../async-sync-bridges.md) and drive it through a
sync `Store`. That works, but every call then hops through a bridged event
loop and forfeits the native async streaming this backend exists to provide —
reserve it for extension features you actually need (e.g. an occasional
`glob_files()` or a Parquet read), not as the default way to use the backend.

## Streaming

`AsyncStore.read()` returns a forward-only `AsyncIterator[bytes]` streamed from
the item's pre-authenticated download URL. Some SharePoint-backed drives ignore
HTTP range requests; when that happens the backend transparently falls back to
a full re-read and flags the returned `FileInfo.extra` (key
`graph.read.range_fallback`), so a single read still yields correct bytes.

## Escape hatch

Access the underlying `httpx.AsyncClient` for Graph-specific calls the Store
API does not expose:

```python
import httpx

client = backend.unwrap(httpx.AsyncClient)
```

## See also

- [Microsoft Graph access setup](graph-setup.md) — app registration, auth flows, drive resolution
- [Async Store guide](../async.md) — the async API the backend is used through
- [Capabilities matrix](../../reference/capabilities-matrix.md)
- [API reference](../../reference/api/aio/backends/graph.md)
- [Example script](../../../examples/backends/graph_backend.py)

## API Reference

::: remote_store.aio.GraphBackend
