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

The backend authenticates through a **token-provider callable**, not a
concrete auth class. The decisions:

- **Token-provider callable, two shapes.** The backend accepts
  `Callable[[], str]` (sync) or `Callable[[], Awaitable[str]]` (async)
  and never couples to MSAL through its constructor. Users who obtain
  tokens another way (managed identity, corporate broker, custom refresh)
  supply their own callable. **Reverse** (via a new ADR) only if the
  backend needs auth features a bare token-returning callable cannot
  express — per-request scope selection, token metadata, or tight MSAL
  coupling.
- **Built-in `GraphAuth` helper.** Wraps MSAL and exposes both callable
  shapes, covering two flows: **client-credentials** (app-only,
  admin-consented `Files.ReadWrite.All` / `Sites.ReadWrite.All`) and
  **device-code** (delegated, interactive). GR-006 / GR-007 specify each
  flow's config fields.
- **Lazy invocation.** The provider is called on first request and once
  more on a `401 InvalidAuthenticationToken` (one-shot refresh + retry,
  GR-029); the backend caches no token. Callers who bring their own
  provider load none of `msal` / `msal-extensions` / `platformdirs`.
- **Credential masking on two surfaces.** `client_secret` is a `Secret`
  (masked in `__repr__`) and auto-wrapped from config via
  `_SENSITIVE_KEYS`; the `Authorization` bearer is redacted from logs and
  never enters exception text. Mechanisms: GR-035, SEC-003 / SEC-004 /
  SEC-007.
- **Config-built backends get a default `GraphAuth`.** The registry
  builds one from static config (ADR-0001); user-supplied callables are
  expressible only through direct construction. The `graph` extra's pins
  live in `pyproject.toml` (ADR-0021 records the SDK choice).

### Token cache: why `PersistedTokenCache`

`GraphAuth` persists the MSAL cache through
`msal_extensions.PersistedTokenCache` (a cross-process lock plus a
dirty-read retry, no atomic rename) and wraps it to swallow-and-log
persistence failures, so a cache error degrades to re-acquisition rather
than breaking an in-flight `read` / `write`. Two facts a reviewer needs
to keep or reverse this choice:

- It replaced a hand-rolled `SerializableTokenCache` + truncate-at-open
  flush, under which a concurrent reader could observe a torn cache and
  be forced to re-login (BK-291).
- A bare temp-file + `os.replace` was rejected because on Windows
  `os.replace` raises `PermissionError` (`WinError 5`) when the
  destination is held open by a concurrent reader; the
  lock-plus-read-retry design sidesteps rename entirely.

The cache path, override rules, and the multi-process-safety contract are
specified by GR-007; the persistence mechanism itself lives in
`_graph/auth.py`.

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
