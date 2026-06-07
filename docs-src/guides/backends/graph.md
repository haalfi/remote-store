# Microsoft Graph Backend

The Graph backend stores files in **OneDrive, SharePoint, and Microsoft Teams**
through the [Microsoft Graph](https://learn.microsoft.com/en-us/graph/) REST API,
talking to a single drive over [`httpx`](https://www.python-httpx.org/) with bearer
tokens from [`msal`](https://learn.microsoft.com/en-us/entra/msal/python/).

It is **async-only**: there is no sync `Store` wrapper and no config `type=`
string, so it is constructed directly and used through `AsyncStore`. For the
one-time credential and app-registration setup, follow the
[Microsoft Graph access setup](graph-setup.md) guide first.

## Installation

```bash
pip install "remote-store[graph]"
```

This pulls in `httpx`, `msal`, and `platformdirs` (for the MSAL token cache).

## Usage

A backend instance targets one drive, identified by an opaque `drive_id`.
Resolve the id once at wiring time, then hand it to the backend:

```python
from remote_store.aio import AsyncStore, GraphAuth, GraphBackend, GraphUtils

# 1. A token provider. Device-code (interactive) auth against a personal
#    Microsoft account needs only tenant + client id — no secret.
auth = GraphAuth(tenant_id="consumers", client_id="<entra-app-id>")

# 2. Resolve the target drive ("me" = the signed-in user's OneDrive).
drive_id = GraphUtils.resolve_drive_id("me", token_provider=auth)

# 3. Construct the backend and use it through AsyncStore.
backend = GraphBackend(drive_id, token_provider=auth)
async with AsyncStore(backend, root_path="Documents") as store:
    await store.write("report.csv", b"col1,col2\n1,2\n", overwrite=True)
    data = await store.read_bytes("report.csv")
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
`cache_path`). Entra app registration, redirect URIs, admin consent, and the
`AADSTS*` error catalogue are covered in the [setup guide](graph-setup.md).

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

A `drive_id` is immutable for the life of a backend instance — point a second
`GraphBackend` at a different drive rather than mutating one.

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `drive_id` | `str` | *(required)* | Opaque Graph drive id (resolve via `GraphUtils`) |
| `token_provider` | `Callable` | *(required)* | Sync or async callable returning a bearer token |
| `base_url` | `str` | `https://graph.microsoft.com/v1.0` | Graph API root |
| `http_client` | `httpx.AsyncClient` | `None` | Reuse an existing client; the caller owns its lifecycle (`close()` leaves it open). When omitted, one is created lazily and closed by `close()` |
| `retry` | `RetryPolicy` | `None` | Transient-failure retry policy; `None` uses the default profile |
| `upload_chunk_size` | `int` | 10 MiB | Upload-session chunk size; must be a positive multiple of 320 KiB and `< 60 MiB` |
| `copy_timeout` | `float \| None` | `None` | Wall-clock budget for copy/move monitor polling (see [caveat](#operational-caveats)) |
| `client_options` | `dict` | `None` | Extra kwargs passed through to the internal `httpx.AsyncClient` |

## Operational caveats

### Upload spooling and `TMPDIR`

When you `write()` an `AsyncIterator[bytes]` of unknown length, Graph's
upload-session protocol requires the total size up front, so the backend
spools the stream to a `SpooledTemporaryFile` (system temp, no explicit
directory) and replays it once the length is known. On platforms with a
small or restricted temp volume (Windows, locked-down containers), redirect
the spill by setting **`TMPDIR`** (or the platform equivalent) before writing
large unknown-length streams. Passing `bytes` instead of an iterator avoids
the spool pass entirely. Spill events are logged at DEBUG with the marker
`graph.upload.spool_spilled`.

### `copy_timeout=None` is unbounded by default

Graph performs `copy()` (and sometimes `move()`) asynchronously: the backend
polls a monitor URL until completion. With the default `copy_timeout=None`
there is **no backend-imposed ceiling** — a copy against an unresponsive
endpoint can block indefinitely. The backend does not substitute a fallback.
Callers that cannot tolerate an unbounded wait must either set `copy_timeout`
to a finite value at construction, or wrap the call in an external ceiling
(`asyncio.timeout(...)`). On expiry the poller raises `BackendUnavailable`
with the (query-stripped) monitor URL, poll count, and last status.

## Write results

The backend declares `WRITE_RESULT_NATIVE`. Writes return a
[`WriteResult`](../../reference/api/models.md) populated directly from the
`driveItem` response — `size`, `etag`, and `last_modified` — with no extra
`HEAD` round trip. It does **not** declare `USER_METADATA`: passing a non-empty
`metadata=` raises `CapabilityNotSupported`; `{}` / `None` are no-ops.

## Capabilities

Supports all capabilities except `GLOB`, `SEEKABLE_READ`, `ATOMIC_MOVE`, and
`USER_METADATA`. For glob, use the portable `ext.glob.glob_files()` fallback
(Graph is `LIST`-capable). See the
[capabilities matrix](../../reference/capabilities-matrix.md) for full details.

## Streaming

`AsyncStore.read()` returns a forward-only `AsyncIterator[bytes]` streamed from
the item's pre-authenticated download URL. Some SharePoint-backed drives ignore
HTTP range requests; when that happens the backend transparently falls back to
a full re-read and flags the returned `FileInfo` (key
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
- [API reference](../../reference/api/aio.md#graphbackend)
- [Example script](../../../examples/backends/graph_backend.py)

## API Reference

::: remote_store.aio.GraphBackend
