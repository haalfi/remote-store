# ADR-0022: Microsoft Graph Auth Model — Dual Flows Behind a Token-Provider Protocol

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

Revised 2026-06-03 in place rather than superseded — by
the time the rewrite landed the ADR was unimplemented against, so
there was no caller state to preserve and a superseding ADR would
have added a level of indirection without aiding any reader. Per
project rule, materially-changing ADRs would normally be superseded;
this one was a user-authorised exception scoped to the four Graph
ADRs (0021..0024).

## Context

The Graph backend (ID-127, RFC-0010) has to work in two distinct
operating environments:

- **Daemon / service processes** with no human at the keyboard, using
  an app registration plus client secret or certificate. OAuth 2.0
  client-credentials flow.
- **Interactive CLI / notebook sessions** where a human can complete
  a login in a browser, typically using OAuth 2.0 device-code flow.

Both flows ultimately produce a bearer token that the backend attaches
to every Graph request as an `Authorization: Bearer …` header. The
backend does not care which flow produced the token — it only needs to
be able to obtain a current one.

Other credential sources (managed identity, workload identity, cached
Azure CLI login) are out of scope for v1 but are likely to surface
later through user-supplied providers.

## Decision

<!-- adr:decision -->
The backend depends on a **token-provider callable**, not a concrete
auth class. Two variants cover sync and async call sites:
<!-- /adr:decision -->

- `Callable[[], str]` — synchronous provider.
- `Callable[[], Awaitable[str]]` — async provider.

A built-in helper, `GraphAuth`, wraps MSAL and implements both
client-credentials and device-code flows, exposing the result as one
of the two callables. Users who already have another way to obtain a
token (managed identity, corporate auth broker, custom refresh
strategy) substitute their own callable. The backend does not couple
to MSAL through the constructor signature — only through the optional
default helper.

### Flows covered by `GraphAuth`

- **Client-credentials.** `tenant_id`, `client_id`, and
  `client_secret` (or `client_certificate`). Admin-consented
  application permissions (`Files.ReadWrite.All`,
  `Sites.ReadWrite.All`) on the target tenant.
- **Device-code.** `tenant_id` and `client_id` (public client).
  Delegated permissions. The user completes the login in a browser;
  MSAL caches the resulting refresh token.

### Token caching

The token cache is an `msal_extensions.PersistedTokenCache` backed by a
`FilePersistence` file under `platformdirs.user_config_dir("remote-store")`
(default `graph_token_cache.json`). `PersistedTokenCache` is
**multi-process-safe**: every MSAL acquisition routes through its
`modify()`, which holds a cross-process `CrossPlatLock` (a sibling
`<cache_path>.lockfile`), reload-merges the on-disk state, then writes it
back — and its `search()` read path retries on a dirty read. The write
itself is an in-place truncate-and-write (`FilePersistence.save`), **not** an
atomic rename; corruption-freedom is provided not by atomicity but by the lock
**serializing concurrent writers** and the read-retry **tolerating a torn read**
(readers do not hold the lock, so they can momentarily observe a truncated file —
which is exactly why `search()` retries). The net effect for concurrent
`GraphAuth`/`GraphBackend` instances or processes sharing the default cache (the
common multi-worker deployment) is that a consumer never observes a corrupt
cache.

This replaced the original hand-rolled `SerializableTokenCache` +
`open(path, "w").write(...)` flush, which truncated the file at `open` before
writing (BK-291): a concurrent reader could observe an empty/torn cache,
forcing a re-login. A bare temp-file + `os.replace` was rejected because on
Windows `os.replace` raises `PermissionError` (`WinError 5`) when the
destination is held open by a concurrent reader or contended by another
replace; `PersistedTokenCache` sidesteps that entirely (lock + read-retry,
no rename). Because persistence is now continuous, `GraphAuth.flush_cache`
is a best-effort no-op retained only for the GR-051 `close()` hook.

Cache access moved *inside* MSAL's acquisition — `modify()` writes through
under the lock, and `search()` reload-merges on every acquisition — so an
unguarded write failure (`OSError` / lock exception) *or* read failure (a
corrupt / persistently-contended cache making `search()` re-raise after its
dirty-read retries) would escape `get_token` untyped mid-`read` / `write`,
regressing the best-effort-swallow the old `flush_cache` provided and the
GR-006 / GR-008 typed-error contract. The multi-process design makes dirty
reads a new, more frequent failure mode (every acquisition reloads), so the
read path matters as much as the write path. `GraphAuth` therefore wraps the
cache in a thin `PersistedTokenCache` subclass: `modify()` swallows+logs
persistence failures (degrade to re-acquisition), and `search()` swallows+logs
read failures and returns `[]` (degrade to a cache miss → fresh acquisition),
keeping acquisition non-breaking while preserving multi-process safety on the
happy path. The lock wait runs on the calling thread, and because the sync
provider is invoked directly on the event loop (no `to_thread`), a *contended*
acquisition blocks the loop for the lock backend's timeout — up to ≈5 s with the
`filelock` fallback that ships when `portalocker` is absent (it is not in the
resolved `graph` lock). Offloading the acquisition off the event loop belongs to
the async-`GraphAuth` path (BK-292), not the sync provider; the bound is stated
here so the deferral is not misread as negligible.

Users can override the path with `cache_path=` or supply their own
token-provider callable to bypass `GraphAuth` (and MSAL) altogether.

`platformdirs`, `msal`, and `msal-extensions` are runtime dependencies of
the built-in `GraphAuth` implementation (see ADR-0021 for the full `graph`
extra dependency set). Callers that supply their own provider and never
instantiate `GraphAuth` do not load any of them at import time (standard
lazy-import pattern, applied here to the `aio/backends/_graph/auth` module).

### What the backend does with the provider

The provider is called lazily: no token acquisition happens in
`__init__`. The backend invokes the callable on first request and on
`401 InvalidAuthenticationToken` responses (one-shot refresh + retry,
per GR-029). Results are not cached inside the backend — MSAL (or the
user-supplied provider) owns the lifetime policy.

### Credential masking

Two concrete mechanisms cover credential leakage:

- **`Secret` wrapper at config and `__repr__`.** `GraphAuth` accepts
  `client_secret: str | Secret`, calls `.reveal()` internally per
  SEC-004, and exposes a `__repr__` that masks the secret per AF-008.
  `client_secret` and `client_certificate` are in the default
  `_SENSITIVE_KEYS` set (SEC-003), so `RegistryConfig.from_dict()`
  auto-wraps them — config-loaded Graph backends inherit the same
  auto-wrap protection as S3 / Azure / SFTP credentials. (ID-127 added
  the two keys to the set; they predate the Graph backend's own
  surface, landing with the GR-CORE config ripple.)
- **`Authorization` header redaction at the request boundary.** The
  bearer token is replaced with the literal `"***"` in any
  DEBUG-level log record emitted by the backend, and never appears
  in `repr()` / `str()` of any exception the backend raises (GR-035).
  `SecretRedactionFilter` (SEC-007) catches the path where headers
  are logged via `record.args`. The backend does not pass the header
  into exception messages.

### Config loader responsibility

When the registry constructs a Graph backend from TOML / YAML / dict
config (per the Registry → Backends architecture in ADR-0001), it
builds a default `GraphAuth` from the config fields and passes its
callable into the backend. User-supplied callables are not expressible
in static config and only apply to direct construction.

## Consequences

- **Testability.** Unit tests stub the callable with a lambda
  returning a known string. No MSAL in the unit-test path.
- **Extensibility without re-opening the backend API.** Managed
  identity, workload identity, broker-based auth, or any future flow
  plug in as a user-supplied callable. Adding them does not change
  the backend constructor.
- **MSAL stays an implementation detail of `GraphAuth`.** Users who
  bring their own callable do not need `msal` installed — though it
  remains in the `graph` extra because the default `GraphAuth`
  helper uses it.
- **Two callable shapes to maintain.** Sync and async variants must
  both be supported. The backend is async-native (ADR-0012), so the
  async shape is primary; the sync shape exists so sync-facing
  wrapper code can reuse the same `GraphAuth` instance without
  an event loop.
- **`_SENSITIVE_KEYS` widened.** Adding `"client_secret"` and
  `"client_certificate"` (ID-127) was a one-line config change with
  no behavioural impact on other backends (their config keys do not
  collide).

## References

- RFC-0010: Microsoft Graph Backend (auth section)
- `sdd/specs/044-graph-backend.md` (GR-006 through GR-008, GR-029,
  GR-035)
- `sdd/specs/020-credential-hygiene.md` (SEC-001 through SEC-008)
- ADR-0001: Architecture — Store, Registry, Backends
- ADR-0012: Async Store / Backend API
- AF-008: backend `__repr__` credential masking
- MSAL Python token cache:
  https://learn.microsoft.com/entra/msal/python/msal.token_cache
- msal-extensions `PersistedTokenCache` (cross-process cache lock):
  https://github.com/AzureAD/microsoft-authentication-extensions-for-python
- BK-291: multi-process-safe token-cache persistence (lock + read-retry)
