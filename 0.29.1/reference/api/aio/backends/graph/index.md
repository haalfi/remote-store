# GraphBackend

Native async Microsoft Graph backend over OneDrive, SharePoint document libraries, and Teams files. A single instance targets one drive (`drive_id`); transport is `httpx` and auth is a token-provider callable (the built-in `GraphAuth` helper, or any user-supplied callable). Requires the `graph` extra. See the [Graph setup guide](https://docs.remotestore.dev/stable/guides/backends/graph-setup/index.md) for provisioning credentials and resolving a `drive_id`.

Graph is async-only — there is no synchronous `GraphBackend`. To use it from synchronous code, wrap it with [`AsyncBackendSyncAdapter`](https://docs.remotestore.dev/stable/reference/api/aio/adapters/index.md).

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

## GraphAuth

MSAL-backed token provider for `GraphBackend`. Wraps the client-credentials (app-only) and device-code (interactive) flows and exposes the bearer token through the token-provider protocol — a `GraphAuth` instance is itself a `Callable[[], str]`.

## GraphAuth

```
GraphAuth(
    tenant_id: str,
    client_id: str,
    *,
    client_secret: str | Secret | None = None,
    client_certificate: dict[str, Any] | None = None,
    scopes: Sequence[str] | None = None,
    cache_path: str | None = None,
    prompt_callback: Callable[[dict[str, Any]], None]
    | None = None,
)
```

MSAL-backed token provider for `GraphBackend`.

Selects the OAuth flow from the supplied credentials: a `client_secret` or `client_certificate` selects client-credentials (app-only); their absence selects device-code (interactive). The resulting bearer token is reachable synchronously through `get_token()` (and through calling the instance directly) and asynchronously through `aget_token()`, which offloads the blocking MSAL work off the event loop and single-flights concurrent acquisitions — prefer it on the event loop.

Parameters:

- **`tenant_id`** (`str`) – Entra tenant id, or "consumers" / "common" / "organizations" for the device-code multi-tenant authorities.
- **`client_id`** (`str`) – Application (client) id of the Entra app registration.
- **`client_secret`** (`str | Secret | None`, default: `None` ) – Client secret for client-credentials. Accepts a Secret and is masked in repr.
- **`client_certificate`** (`dict[str, Any] | None`, default: `None` ) – Certificate dict for client-credentials, as MSAL's client_credential mapping. Mutually exclusive with client_secret.
- **`scopes`** (`Sequence[str] | None`, default: `None` ) – Override the default scope set. Client-credentials defaults to ["https://graph.microsoft.com/.default"]; device-code defaults to the delegated ["Files.ReadWrite", "User.Read"] (the signed-in user's OneDrive — consumer-compatible). Add Sites.ReadWrite.All for delegated SharePoint access.
- **`cache_path`** (`str | None`, default: `None` ) – Override the MSAL token-cache file location. Defaults to \<user_config_dir("remote-store")>/graph_token_cache.json. The cache is persisted multi-process-safely: a sibling \<cache_path>.lockfile coordinates concurrent writers so a shared default cache survives the common multi-worker deployment.
- **`prompt_callback`** (`Callable[[dict[str, Any]], None] | None`, default: `None` ) – Invoked with the MSAL device-flow dict on device-code login; defaults to printing flow["message"].

Raises:

- `ValueError` – If tenant_id or client_id is empty, or if both client_secret and client_certificate are supplied.

### authority

```
authority: str
```

The MSAL authority URL derived from `tenant_id`.

### get_token

```
get_token() -> str
```

Acquire (or silently refresh) a bearer token.

The token-provider callable the backend invokes. Re-invoking it after a `401` refreshes through MSAL's cache. The acquisition writes the refreshed cache through to disk itself — the backing `PersistedTokenCache` persists under a cross-process lock on every change, so no explicit flush is needed here.

Raises:

- `PermissionDenied` – If MSAL returns no token (auth failure); the error_description is included, never the secret. A typed RemoteStoreError so a failure surfacing mid-read / write stays catchable via except RemoteStoreError.

### __call__

```
__call__() -> str
```

Return a bearer token — makes the instance a token-provider callable.

### aget_token

```
aget_token() -> str
```

Acquire a bearer token without blocking the event loop.

The async token-provider entry point: pass `token_provider=auth.aget_token` (a bound async method is a `Callable[[], Awaitable[str]]`) so the backend awaits it instead of calling the synchronous instance. It offloads the synchronous MSAL acquisition — including any contended token-cache lock wait — to a worker thread so sibling coroutines keep running, and single-flights concurrent callers: N coroutines acquiring at once share **one** acquisition rather than each hitting the identity provider (which also dedupes the one-shot refresh after a `401`).

Use this on the event loop; reuse the synchronous `get_token` / `__call__` from synchronous wiring code that has no running loop. The single-flight state is bound to the loop the first caller runs on — share one instance per loop, mirroring the backend's own single-loop posture. Cancelling one caller (e.g. a `gather` sibling that times out) neither cancels the shared acquisition nor disturbs the other joiners.

Raises:

- `PermissionDenied` – Propagated from get_token to the owning caller and every joiner sharing the in-flight acquisition; a later call retries afresh.

### flush_cache

```
flush_cache() -> None
```

Best-effort no-op retained for the `GraphBackend.close()` hook.

The token cache is a `PersistedTokenCache` that writes through to disk under a cross-process lock on every acquisition, so there is nothing to flush at close. The method stays because `GraphBackend.close()` invokes it duck-typed and user-supplied providers may implement their own. Never raises — teardown must not fail.

## GraphUtils

Namespace helpers for Graph configuration. `resolve_drive_id` turns "my OneDrive" (`"me"`), a SharePoint site URL, or a Teams channel mapping into the opaque `drive_id` the backend requires.

### resolve_drive_id

```
resolve_drive_id(
    target: str | tuple[str, str] | Mapping[str, str],
    *,
    token_provider: TokenProvider,
    http_client: AsyncClient | None = None,
    base_url: str = _DEFAULT_BASE_URL,
) -> str
```

Resolve a `drive_id` from one of the three target shapes.

Sync entry point for application wiring; runs `aresolve_drive_id` under a private event loop. See `aresolve_drive_id` for the accepted shapes and raised errors.

### aresolve_drive_id

```
aresolve_drive_id(
    target: str | tuple[str, str] | Mapping[str, str],
    *,
    token_provider: TokenProvider,
    http_client: AsyncClient | None = None,
    base_url: str = _DEFAULT_BASE_URL,
) -> str
```

Resolve a `drive_id` from one of three target shapes.

Accepted shapes:

- `"me"` — the authenticated user's default drive (`GET /me/drive`).
- a SharePoint site URL `str` — the site's default drive; or a `(site_url, library_name)` tuple — the named document library.
- a `{"team_id": ..., "channel_id": ...}` mapping — a Teams channel's backing drive.

Parameters:

- **`target`** (`str | tuple[str, str] | Mapping[str, str]`) – One of the shapes above.
- **`token_provider`** (`TokenProvider`) – Bearer-token callable (sync or async).
- **`http_client`** (`AsyncClient | None`, default: `None` ) – Reuse an existing client; one is created and closed per call when omitted.
- **`base_url`** (`str`, default: `_DEFAULT_BASE_URL` ) – Graph API root.

Returns:

- `str` – The opaque Graph drive.id string.

Raises:

- `InvalidPath` – If target matches no accepted shape, the SharePoint site URL has no host, or the named library does not exist.
- `NotFound` – If a site/team/channel id resolves but returns 404.
- `PermissionDenied` – If Graph returns 403 for the lookup.
- `BackendUnavailable` – For a transport error, a retryable 5xx / 429 / 507, or a malformed @odata.nextLink while paging a site's document libraries.

## See also

- [Graph Backend Guide](https://docs.remotestore.dev/stable/guides/backends/graph/index.md) — usage patterns and capabilities
- [Graph setup guide](https://docs.remotestore.dev/stable/guides/backends/graph-setup/index.md) — provisioning credentials and resolving a `drive_id`
- [Adapters](https://docs.remotestore.dev/stable/reference/api/aio/adapters/index.md) — run `GraphBackend` from synchronous code
