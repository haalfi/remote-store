# Microsoft Graph Backend

The Graph backend stores files in **OneDrive, SharePoint, and Microsoft Teams** through the [Microsoft Graph](https://learn.microsoft.com/en-us/graph/) REST API, talking to a single drive over [`httpx`](https://www.python-httpx.org/) with bearer tokens from [`msal`](https://learn.microsoft.com/en-us/entra/msal/python/).

It is **async-only**: there is no sync `Store` wrapper and no config `type=` string, so it is constructed directly and used through `AsyncStore`. For the one-time credential and app-registration setup, follow the [Microsoft Graph access setup](https://docs.remotestore.dev/stable/guides/backends/graph-setup/index.md) guide first.

Verification coverage

The backend is live-verified against **consumer OneDrive** (device-code auth). SharePoint and OneDrive for Business drives go through the same Graph API and are covered by mocked tests, but are less exercised in practice — see the [operational caveats](#operational-caveats) for the known SharePoint-specific behaviours.

## Installation

```
pip install "remote-store[graph]"
```

This pulls in `httpx`, `msal`, `msal-extensions`, and `platformdirs` (the last two persist the MSAL token cache multi-process-safely).

## Usage

A backend instance targets one drive, identified by an opaque `drive_id`. Resolve the id once at wiring time, then hand it to the backend:

```
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

    # 3. Construct the backend and use it through AsyncStore. On the event loop,
    #    prefer the async auth.aget_token (off-loop acquisition + single-flight).
    backend = GraphBackend(drive_id, token_provider=auth.aget_token)
    async with AsyncStore(backend, root_path="Documents") as store:
        await store.write("report.csv", b"col1,col2\n1,2\n", overwrite=True)
        data = await store.read_bytes("report.csv")


asyncio.run(main())
```

`token_provider` is any `Callable[[], str]` or `Callable[[], Awaitable[str]]` returning a bearer token; `GraphAuth` is the built-in MSAL implementation but any callable works (e.g. a token minted by your own identity layer).

`GraphAuth` exposes both shapes over one instance. On the event loop, prefer the async `auth.aget_token` over passing the instance directly:

```
backend = GraphBackend(drive_id, token_provider=auth.aget_token)
```

`aget_token` offloads the blocking MSAL acquisition (and any contended token-cache lock wait) to a worker thread, so a cold or expired token never stalls sibling coroutines, and it **single-flights** concurrent acquisitions: a large `asyncio.gather` over a shared backend acquires the token once rather than once per coroutine (the same dedup covers the one-shot refresh after a `401`). Passing the instance directly (`token_provider=auth`) uses the synchronous `get_token`, which runs on the event loop and acquires per request — reserve it for synchronous wiring that has no running loop. A user-supplied async provider that wants this dedup must implement its own.

## Authentication

`GraphAuth` selects the OAuth flow from the credentials you supply:

| Supplied                                | Flow                          | Account type            | Use for                    |
| --------------------------------------- | ----------------------------- | ----------------------- | -------------------------- |
| `client_secret` or `client_certificate` | Client-credentials (app-only) | Work/school tenant      | CI, daemons, services      |
| neither                                 | Device-code (delegated)       | Personal or work/school | Notebooks, CLIs, local dev |

```
# App-only (client-credentials) against a work/school tenant:
auth = GraphAuth(
    tenant_id="<tenant-guid>",
    client_id="<entra-app-id>",
    client_secret="<secret>",  # accepts a Secret; masked in repr
)
```

The token is cached by MSAL on disk (default `<user_config_dir("remote-store")>/graph_token_cache.json`; override with `cache_path`). The cache is persisted multi-process-safely — a sibling `<cache_path>.lockfile` coordinates concurrent writers, so several workers or processes sharing the default cache will not corrupt it. Entra app registration, redirect URIs, admin consent, and the `AADSTS*` error catalogue are covered in the [setup guide](https://docs.remotestore.dev/stable/guides/backends/graph-setup/index.md).

## Resolving a drive_id

`GraphUtils.resolve_drive_id` (and its async twin `aresolve_drive_id`) turn a human-meaningful target into the opaque `drive_id` the backend needs:

| Target                                        | Resolves to                                                 |
| --------------------------------------------- | ----------------------------------------------------------- |
| `"me"`                                        | the authenticated user's default OneDrive (`GET /me/drive`) |
| a SharePoint site URL `str`                   | the site's default document library                         |
| `(site_url, library_name)` tuple              | a named document library on that site                       |
| `{"team_id": ..., "channel_id": ...}` mapping | a Teams channel's backing drive                             |

```
drive_id = GraphUtils.resolve_drive_id(
    "https://contoso.sharepoint.com/sites/Marketing",
    token_provider=auth,
)
```

The sync `resolve_drive_id` is for synchronous wiring code (config loading, CLI setup): it runs its own event loop internally, so calling it from inside a running event loop raises `RuntimeError`. Inside `async def` code, always use `await GraphUtils.aresolve_drive_id(...)`.

A `drive_id` is immutable for the life of a backend instance — point a second `GraphBackend` at a different drive rather than mutating one.

## Options

| Option              | Type                | Default                            | Description                                                                                                                                       |
| ------------------- | ------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `drive_id`          | `str`               | *(required)*                       | Opaque Graph drive id (resolve via `GraphUtils`)                                                                                                  |
| `token_provider`    | `Callable`          | *(required)*                       | Sync or async callable returning a bearer token                                                                                                   |
| `base_url`          | `str`               | `https://graph.microsoft.com/v1.0` | Graph API root                                                                                                                                    |
| `http_client`       | `httpx.AsyncClient` | `None`                             | Reuse an existing client; the caller owns its lifecycle (`aclose()` leaves it open). When omitted, one is created lazily and closed by `aclose()` |
| `retry`             | `RetryPolicy`       | `None`                             | Transient-failure retry policy; `None` uses the default profile                                                                                   |
| `upload_chunk_size` | `int`               | 10 MiB                             | Upload-session chunk size; must be a positive multiple of 320 KiB and `< 60 MiB`                                                                  |
| `copy_timeout`      | `float \| None`     | `None`                             | Wall-clock budget for copy/move monitor polling (see [caveat](#operational-caveats))                                                              |
| `base_path`         | `str`               | `""`                               | Scope every operation to this drive subfolder; keys are addressed relative to it and listings return relative keys. Defaults to the drive root    |
| `client_options`    | `dict`              | `None`                             | Extra kwargs passed through to the internal `httpx.AsyncClient`                                                                                   |

## Operational caveats

### Spooling and `TMPDIR`

When you `write()` an `AsyncIterator[bytes]` of unknown length, Graph's upload-session protocol requires the total size up front, so the backend spools the stream to a `SpooledTemporaryFile` (system temp, no explicit directory) and replays it once the length is known. On platforms with a small or restricted temp volume (Windows, locked-down containers), redirect the spill by setting **`TMPDIR`** (or the platform equivalent) before writing large unknown-length streams. Passing `bytes` instead of an iterator avoids the spool pass entirely. Spill events are logged at DEBUG with the marker `graph.upload.spool_spilled`.

The same concern exists on the **read side**: the backend does not declare `SEEKABLE_READ`, so `read_seekable()` — which the `ext.arrow` / `ext.parquet` extensions use for large files (through the [sync adapter](#extensions-sync-vs-async)) — is synthesised by spooling the entire file to the temp volume before the consumer can seek. Reading a large Parquet file over Graph therefore needs temp space for the whole file; size `TMPDIR` accordingly.

### Connection-pool tuning under high fan-out

The internal `httpx.AsyncClient` uses httpx's default connection pool — **100 connections** (`max_keepalive_connections=20`). Under very high concurrent fan-out (a large `asyncio.gather` over a shared backend, or many bridged threads) that ceiling is reached silently: requests queue and, on pool exhaustion, surface as an opaque `BackendUnavailable` rather than anything that names the pool as the cause.

Raise the ceiling by passing an [`httpx.Limits`](https://www.python-httpx.org/advanced/resource-limits/) through `client_options` (forwarded verbatim to the client):

```
backend = GraphBackend(
    drive_id="b!example-drive-id",
    token_provider=lambda: "token",
    client_options={
        "limits": httpx.Limits(
            max_connections=200,
            max_keepalive_connections=50,
        ),
    },
)
```

Size `max_connections` to your fan-out, not arbitrarily high: each connection is a socket against Graph, which itself throttles (`429`). This is the same passthrough mechanism every `client_options` key uses; supplying your own `http_client` instead lets you set limits on the client you construct.

### SharePoint-backed drives are less exercised

Live verification runs against consumer OneDrive only. SharePoint-backed drives have known divergences the backend already accounts for — some ignore HTTP range requests (see [Streaming](#streaming)) — and others that the live tier cannot reach. Treat SharePoint/business deployments as less-travelled ground and validate your workload before relying on it in production.

### `overwrite=True` can still raise `AlreadyExists`

Overwriting an existing **file** with `overwrite=True` is expected to replace it and succeed. One situation can still surface an `AlreadyExists` error despite the flag:

- **SharePoint-backed drives** may reject the replace of an existing file with a conflict. This does not happen on consumer OneDrive (the live-verified tier). The backend deliberately does **not** paper over it — silently treating the rejection as success could mask a genuine collision and would have to guess at a response shape the project cannot reproduce. If you need overwrite-or-create semantics on such a drive, delete the target first and then write, or serialise the writers.

A second situation — **concurrent creation of the same new key** (reproduced on consumer OneDrive) — is now **handled**: when several writers race to create the *same not-yet-existing* key with `overwrite=True`, a loser whose `replace` lands mid-create is re-attempted a bounded number of times. The winner's create has committed by then, so the re-issued `replace` overwrites it and the write succeeds — last-writer-wins, as `overwrite=True` promises. **Content integrity holds** throughout: one writer's bytes land intact, with no tearing or interleaving. (With `overwrite=False` the same race is a race-free create-if-absent: exactly one writer wins and the losers get `AlreadyExists` by design — see below.)

### `copy_timeout=None` is unbounded by default

Graph performs `copy()` (and sometimes `move()`) asynchronously: the backend polls a monitor URL until completion. With the default `copy_timeout=None` there is **no backend-imposed ceiling** — a copy against an unresponsive endpoint can block indefinitely. The backend does not substitute a fallback. Callers that cannot tolerate an unbounded wait must either set `copy_timeout` to a finite value at construction, or wrap the call in an external ceiling (`asyncio.timeout(...)`). On expiry the poller raises `BackendUnavailable` with the (query-stripped) monitor URL, poll count, and last status.

## Concurrency & consistency

`GraphBackend` is async-only and built for concurrent use on a single event loop:

- **One instance, one loop.** A `GraphBackend` is safe for concurrent coroutines driven by one event loop — `asyncio.gather` over a shared instance is fine. It is *not* safe to share across event loops; give each loop its own instance.
- **Safe from threaded sync code.** Driven through [`AsyncBackendSyncAdapter`](https://docs.remotestore.dev/stable/guides/async-sync-bridges/index.md), a single instance is safe for concurrent threads — the adapter serialises them onto its private loop. This is **unlike** the SFTP backend, where you need one instance per thread.
- **`overwrite=False` is a race-free create-if-absent.** It maps to a server-side atomic create (Graph's create-if-absent conflict behaviour), so two writers racing to create the same new key cannot both win — the loser gets `AlreadyExists`. There is no client-side check-then-write window, unlike the TOCTOU behaviour described in the [concurrency guide](https://docs.remotestore.dev/stable/explanation/concurrency/#overwritefalse-and-toctou).
- **`move` and `copy` are not atomic at the point of use.** `copy` (and sometimes `move`) runs server-side and is monitor-polled to completion; a crash mid-operation can leave both source and destination. Two callers racing a `move` / `copy` of the same item resolve to one winner, but the loser's error may be generic rather than typed.
- **Read-your-writes holds.** After a successful `write`, a subsequent `read` on the same instance returns the new content.

See the [concurrency guide](https://docs.remotestore.dev/stable/explanation/concurrency/#concurrent-use-posture) for the cross-backend posture table and the sync/async bridge rules.

## Write results

The backend declares `WRITE_RESULT_NATIVE`. Writes return a [`WriteResult`](https://docs.remotestore.dev/stable/reference/api/models/index.md) populated directly from the `driveItem` response — `size`, `etag`, and `last_modified` — with no extra `HEAD` round trip. It does **not** declare `USER_METADATA`: passing a non-empty `metadata=` raises `CapabilityNotSupported`; `{}` / `None` are no-ops.

## Capabilities

Supports all capabilities except `GLOB`, `SEEKABLE_READ`, `ATOMIC_MOVE`, and `USER_METADATA`. For glob, the portable `ext.glob.glob_files()` fallback works (Graph is `LIST`-capable) — but only through the sync adapter, since the `ext.*` suite is sync-only (see [below](#extensions-sync-vs-async)). See the [capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) for full details.

## Extensions: sync vs async

The extension ecosystem is split between the two Store surfaces, and the async side is much smaller:

| Extension surface                                                                                                         | Native `AsyncStore` | Sync `Store` (via adapter) |
| ------------------------------------------------------------------------------------------------------------------------- | ------------------- | -------------------------- |
| `aio.ext.write` — `write_with_hash`                                                                                       | Yes                 | —                          |
| [`ext.*`](https://docs.remotestore.dev/stable/reference/api/extensions/index.md) — the sync suite (glob, cache, arrow, …) | —                   | Yes                        |

Because `GraphBackend` is async-only, a native `AsyncStore` consumer has no `ext.*` surface at all — only `aio.ext.write.write_with_hash`. To use a sync extension over Graph, wrap the backend in [`AsyncBackendSyncAdapter`](https://docs.remotestore.dev/stable/guides/async-sync-bridges/index.md) and drive it through a sync `Store`. That works, but every call then hops through a bridged event loop and forfeits the native async streaming this backend exists to provide — reserve it for extension features you actually need (e.g. an occasional `glob_files()` or a Parquet read), not as the default way to use the backend.

## Streaming

`AsyncStore.read()` returns a forward-only `AsyncIterator[bytes]` streamed from the item's pre-authenticated download URL. Some SharePoint-backed drives ignore HTTP range requests; when that happens the backend transparently falls back to a full re-read and flags the returned `FileInfo.extra` (key `graph.read.range_fallback`), so a single read still yields correct bytes.

## Escape hatch

Access the underlying `httpx.AsyncClient` for Graph-specific calls the Store API does not expose:

```
import httpx

client = backend.unwrap(httpx.AsyncClient)
```

## See also

- [Microsoft Graph access setup](https://docs.remotestore.dev/stable/guides/backends/graph-setup/index.md) — app registration, auth flows, drive resolution
- [Async Store guide](https://docs.remotestore.dev/stable/guides/async/index.md) — the async API the backend is used through
- [Capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md)
- [API reference](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/index.md)
- [Example script](https://docs.remotestore.dev/stable/tutorial/examples/graph-backend/index.md)

## API Reference

## GraphBackend

```
GraphBackend(
    drive_id: str,
    *,
    token_provider: TokenProvider,
    base_url: str = _DEFAULT_BASE_URL,
    http_client: AsyncClient | None = None,
    retry: RetryPolicy | None = None,
    upload_chunk_size: int = _DEFAULT_UPLOAD_CHUNK_SIZE,
    copy_timeout: float | None = None,
    base_path: str = "",
    client_options: dict[str, Any] | None = None,
)
```

Bases: `AsyncBackend`

Async Microsoft Graph backend over OneDrive / SharePoint / Teams files.

A single instance targets one drive, identified by an immutable `drive_id`. Items are addressed by `/`-rooted POSIX path; transport is `httpx`; auth is a token-provider callable (the built-in `GraphAuth` helper, or any user-supplied callable).

Parameters:

- **`drive_id`** (`str`) – Opaque Graph drive id. Resolve one from a URL / "me" / Teams channel with GraphUtils.resolve_drive_id.
- **`token_provider`** (`TokenProvider`) – Callable\[[], str\] or Callable\[[], Awaitable[str]\] returning a bearer token, invoked lazily (never in __init__).
- **`base_url`** (`str`, default: `_DEFAULT_BASE_URL` ) – Graph API root (default https://graph.microsoft.com/v1.0).
- **`http_client`** (`AsyncClient | None`, default: `None` ) – Reuse an existing httpx.AsyncClient; the caller owns its lifecycle and close() does not close it. When omitted, one is created lazily on first use and closed by close().
- **`retry`** (`RetryPolicy | None`, default: `None` ) – Retry policy for transient failures; None uses the default RetryPolicy() profile.
- **`upload_chunk_size`** (`int`, default: `_DEFAULT_UPLOAD_CHUNK_SIZE` ) – Upload-session chunk size; must be a positive multiple of 320 KiB and strictly less than 60 MiB (Graph's per-request ceiling). Default 10 MiB.
- **`copy_timeout`** (`float | None`, default: `None` ) – Wall-clock budget for copy/move monitor polling, or None for no backend-imposed ceiling. When set, must be a positive float.
- **`base_path`** (`str`, default: `''` ) – Optional drive subfolder to scope every operation under. When set, all keys are addressed relative to this folder and keys returned by listing / to_key stay relative to it, so the backend behaves as if base_path were its root. Defaults to the drive root.
- **`client_options`** (`dict[str, Any] | None`, default: `None` ) – Extra options passed through to the internal httpx.AsyncClient. (When a future revision adds an explicit httpx-level constructor parameter, it takes precedence over a client_options key of the same name; the backend has no such parameter today, so this is passthrough only.)

Raises:

- `ValueError` – For an empty drive_id, a non-callable token_provider, a non-string base_path, an upload_chunk_size that is not a positive 320 KiB multiple below 60 MiB, or a non-positive copy_timeout.

### name

```
name: str
```

Unique identifier for this backend type — `"graph"`.

### capabilities

```
capabilities: CapabilitySet
```

Declared capabilities of this backend.

### drive_id

```
drive_id: str
```

The immutable target drive id.

### native_path

```
native_path(path: str) -> str
```

Return the Graph item-by-path metadata endpoint for `path`.

`/drives/{drive_id}/root:{encoded_path}:` with each segment percent-encoded. The empty key returns `/drives/{drive_id}/root:` (Graph's drive-root form, no trailing colon delimiter). A configured `base_path` is prepended so every key is scoped under it.

### to_key

```
to_key(native_path: str) -> str
```

Strip the drive-root prefix/delimiter and decode back to a key.

Inverse of `native_path`: removes `/drives/{drive_id}/root:` and the trailing `:` delimiter, then percent-decodes each segment. Inputs without the prefix are returned unchanged; the drive root maps to `""`.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` carrying the drive id and base URL.

### unwrap

```
unwrap(type_hint: type[T]) -> T
```

Return the underlying `httpx.AsyncClient` (native-handle escape hatch).

Raises:

- `CapabilityNotSupported` – For any type other than httpx.AsyncClient.

### aclose

```
aclose() -> None
```

Close the owned HTTP client, cancel pollers, and flush the auth cache.

Safe to call multiple times. A caller-supplied `http_client` is left open — the caller owns it. Any in-flight copy/move monitor poller is cancelled cooperatively, and any upload session a `write()` left mid-chunk-loop is aborted via best-effort `DELETE` — every cleanup error is swallowed so `close()` never raises. The server-side copy / move continues (Graph monitor URLs have no cancel endpoint).

After this returns, any new op raises `BackendUnavailable` via the `_client` guard, and any op still in flight surfaces a typed error rather than a bare `RuntimeError` from the closing client.

### read

```
read(path: str) -> AsyncIterator[bytes]
```

Stream file content from the pre-signed download URL.

Fetches item metadata first (so the directory check happens before any byte is yielded), then streams the response body from `@microsoft.graph.downloadUrl` with no `Range` header (the URL is pre-signed, so no `Authorization` header is attached either). If the read is interrupted — the URL expires, or the connection drops mid-body — the stream re-fetches metadata for a fresh URL and resumes from the next unread byte with a `Range` request, provided the `eTag` is unchanged.

Raises:

- `NotFound` – If the path does not exist.
- `InvalidPath` – If the path names a folder.
- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – If the download URL is missing, the file changed mid-read (eTag mismatch), the pre-signed host returns a non-success status, or the download fails at the transport level (connect/read timeout, DNS, reset).

### read_bytes

```
read_bytes(path: str) -> bytes
```

Read full file content as bytes.

Delegates to `read` so the directory check and not-found mapping live in one place.

Raises:

- `NotFound` – If the path does not exist.
- `InvalidPath` – If the path names a folder.
- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – As for read (missing URL, expiry, eTag change, host or transport failure).

### exists

```
exists(path: str) -> bool
```

Return `True` if a file or folder exists at *path*.

Any 404 — including a drive-identity `resourceNotFound` — is suppressed to `False`; never raises `NotFound`. A misconfigured or deleted drive therefore probes as missing rather than raising; it surfaces on the first error-raising operation.

Raises:

- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On throttling, 5xx, or transport failure.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if *path* exists and carries the `file` facet.

A missing item returns `False` (any 404 is suppressed, including a drive-identity `resourceNotFound`).

Raises:

- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On throttling, 5xx, or transport failure.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if *path* exists and carries the `folder` facet.

A missing item returns `False` (any 404 is suppressed, including a drive-identity `resourceNotFound`). The drive root (`""`) carries the `folder` facet and reports `True`.

Raises:

- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On throttling, 5xx, or transport failure.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Return file metadata mapped from the Graph `driveItem` body.

`file.hashes` rides `FileInfo.extra["graph.file.hashes"]`; `metadata` is `None` (user metadata is not declared) and `digest` is left unset.

Raises:

- `NotFound` – If the path does not exist.
- `InvalidPath` – If the path names a folder.
- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On throttling, 5xx, or transport failure.

### iter_children

```
iter_children(
    path: str,
) -> AsyncIterator[FileInfo | FolderEntry]
```

Yield immediate files and folders under *path* in a single pass.

Overrides the default (which would chain `list_files` + `list_folders` and double the round-trips) to consume one `/children` response: `folder`-faceted items become `FolderEntry`, `file`-faceted items become `FileInfo`, in the order Graph returns them. A missing or file path yields nothing.

Raises:

- `PermissionDenied` – If the token is rejected or lacks access (401/403), surfaced during iteration.
- `BackendUnavailable` – On throttling, 5xx, or transport failure, surfaced during iteration.

### list_files

```
list_files(
    path: str,
    *,
    recursive: bool = False,
    max_depth: int | None = None,
) -> AsyncIterator[FileInfo]
```

List files under *path*.

When `max_depth` is set it governs traversal depth and `recursive` is ignored; otherwise `recursive=True` walks the subtree unbounded and the default lists only immediate files. A missing or file path yields nothing.

Raises:

- `PermissionDenied` – If the token is rejected or lacks access (401/403), surfaced during iteration.
- `BackendUnavailable` – On throttling, 5xx, or transport failure, surfaced during iteration.

### list_folders

```
list_folders(path: str) -> AsyncIterator[FolderEntry]
```

List immediate subfolders under *path*.

A missing or file path yields nothing.

Raises:

- `PermissionDenied` – If the token is rejected or lacks access (401/403), surfaced during iteration.
- `BackendUnavailable` – On throttling, 5xx, or transport failure, surfaced during iteration.

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

Return aggregated folder metadata: recursive file count + total size.

Validates the path first — a missing item raises `NotFound` and a file item raises `InvalidPath`. `file_count` and `total_size` aggregate every file in the subtree; `modified_at` is the folder item's own timestamp.

Raises:

- `NotFound` – If the path does not exist.
- `InvalidPath` – If the path names a file.
- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On throttling, 5xx, or transport failure.

### write

```
write(
    path: str,
    content: AsyncWritableContent,
    *,
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Write a file, creating intermediate folders implicitly.

Content `<= 4 MiB` uses `PUT /content`; larger content uploads via a chunked session. An `AsyncIterator` of unknown length is spooled to size it first (the session `Content-Range` needs a known total). The returned `WriteResult` is `source="native"`, populated from the `driveItem` Graph returns. `overwrite` maps to Graph's `@microsoft.graph.conflictBehavior` (`replace` vs `fail`).

On `overwrite=True` (`conflictBehavior=replace`) a concurrent create of the *same not-yet-existing* key can still draw a `409 nameAlreadyExists` (live-reproduced on consumer OneDrive): the loser's replace lands while the winner's create is in flight. The write re-attempts the replace a bounded number of times — the winner's create has committed by the time the 409 returns, so the re-issue overwrites it. On the large-file upload-session path the same race can surface *mid-session* instead: the session opens cleanly, then a racing replace swaps the item and the next chunk `PUT` draws a `404`; under `overwrite=True` that is treated as the same create-race signal and the write re-opens a fresh session and retries. Large-file retries re-upload the whole body, so this convergence is best-effort: under sustained concurrent same-key overwrite a loser may still exhaust the budget and raise `AlreadyExists` (last-writer-wins still holds — one writer's content lands intact). A terminal conflict (a SharePoint-backed drive that rejects the replace outright) likewise keeps 409-ing and surfaces `AlreadyExists` once the budget is spent; the retry re-issues the replace, it never swallows the conflict.

Raises:

- `AlreadyExists` – If the file exists and overwrite=False, or an overwrite=True replace keeps drawing a 409 past the bounded re-attempt budget (a SharePoint-backed replace-rejection, or a loser in a sustained concurrent large-file same-key overwrite).
- `InvalidPath` – If the path names the drive root, an existing folder, or descends through a file ancestor.
- `CapabilityNotSupported` – If a non-empty metadata= reaches the backend directly (USER_METADATA is not declared).
- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On 5xx / throttling / transport failure, or a Graph contract gap (missing uploadUrl / nextExpectedRanges).
- `ResourceLocked` – If the item is locked mid-session. The session stays valid server-side, but its credentialed URL is not exposed in the exception.

### write_atomic

```
write_atomic(
    path: str,
    content: AsyncWritableContent,
    *,
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Atomic write — delegates to `write`.

Graph's own write paths already provide the no-partial-content guarantee (`PUT /content` is service-atomic; an upload session commits only on the final chunk), so no client-side temp-rename is taken. The `WriteResult` shape, the `metadata=` gate, and the raised exceptions are inherited verbatim from `write`.

### delete

```
delete(path: str, *, missing_ok: bool = False) -> None
```

Delete a file (Graph moves it to the recycle bin).

Fetches the item first so a folder is rejected before any `DELETE` is issued (a bare `DELETE` on a folder would remove the folder and its contents). A missing item is `NotFound` unless `missing_ok`.

Raises:

- `NotFound` – If the file does not exist and missing_ok is False.
- `InvalidPath` – If the path names a folder (use delete_folder).
- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On throttling, 5xx, or transport failure.

### delete_folder

```
delete_folder(
    path: str,
    *,
    recursive: bool = False,
    missing_ok: bool = False,
) -> None
```

Delete a folder, optionally requiring it to be empty.

`recursive=True` is a single `DELETE` — Graph removes the folder and all contents atomically server-side. `recursive=False` first checks the folder is empty (via the item's `folder.childCount`, falling back to a `/children` probe when the count is absent) and raises `DirectoryNotEmpty` if not.

Raises:

- `NotFound` – If the folder does not exist and missing_ok is False.
- `InvalidPath` – If the path names a file.
- `DirectoryNotEmpty` – If non-empty and recursive is False.
- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On throttling, 5xx, or transport failure.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy a file, awaiting the async monitor to completion.

Graph answers `POST copy` with `202 Accepted` and a `Location` monitor URL; this polls it to a terminal state (bounded by `copy_timeout`). `src == dst` short-circuits after a single existence-confirming `GET`. A destination conflict surfaces as `AlreadyExists` (or `InvalidPath` for a folder / file-ancestor target) when `overwrite` is `False`.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src names a folder, or dst names an existing folder or descends through a file ancestor.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On a 202 without a Location monitor URL, a copy_timeout expiry, or a transient/5xx failure.

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename a file, awaiting the monitor when Graph goes async.

Graph answers `PATCH driveItem` synchronously in most cases (`200`); a large-item move may return `202` with a monitor URL (the async trigger is item size / server-side replication, not crossing folders), which is polled to completion exactly as `copy` does. `src == dst` short-circuits after one `GET`. Item identity (id / eTag / property bag) is preserved by Graph; the backend issues no compensating writes.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src names a folder, or dst names an existing folder or descends through a file ancestor.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `PermissionDenied` – If the token is rejected or lacks access to the item (401/403).
- `BackendUnavailable` – On a 202 without a Location monitor URL, a copy_timeout expiry, or a transient/5xx failure.
