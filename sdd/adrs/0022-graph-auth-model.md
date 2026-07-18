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

The backend depends on a **token-provider callable**, not a concrete
auth class. Two variants cover sync and async call sites:

- `Callable[[], str]` — synchronous provider.
- `Callable[[], Awaitable[str]]` — async provider.

A built-in helper, `GraphAuth`, wraps MSAL and implements both
client-credentials and device-code flows, exposing the result as one
of the two callables. Users who already have another way to obtain a
token (managed identity, corporate auth broker, custom refresh
strategy) substitute their own callable. The backend does not couple
to MSAL through the constructor signature — only through the optional
default helper.

`GraphAuth` covers two flows: **client-credentials** (app-only,
admin-consented `Files.ReadWrite.All` / `Sites.ReadWrite.All`;
`tenant_id` + `client_id` + `client_secret` or `client_certificate`) and
**device-code** (delegated, interactive; `tenant_id` + `client_id` public
client). GR-006 and GR-007 specify each flow.

### Token cache: why `PersistedTokenCache`

`GraphAuth` persists the MSAL cache through
`msal_extensions.PersistedTokenCache` (a cross-process lock plus a
dirty-read retry, no atomic rename), and wraps it to swallow-and-log
persistence failures so a cache error degrades to re-acquisition instead
of escaping `get_token` and breaking an in-flight `read` / `write` (the
GR-006 / GR-008 typed-error contract). This replaced a hand-rolled
`SerializableTokenCache` + truncate-at-open flush, under which a
concurrent reader could observe an empty or torn cache and be forced to
re-login (BK-291). A bare temp-file + `os.replace` was rejected because
on Windows `os.replace` raises `PermissionError` (`WinError 5`) when the
destination is held open by a concurrent reader; the lock-plus-read-retry
design sidesteps rename entirely. The cache mechanism, canonical path,
override rules, and the contended-lock cost are specified by GR-007
(single source of truth).

### Provider invocation and lazy dependency

The provider is called lazily — never in `__init__` — on first request
and once more on a `401 InvalidAuthenticationToken` (one-shot refresh +
retry per GR-029); the backend caches no token, so MSAL or the
user-supplied provider owns lifetime. Callers who supply their own
provider and never instantiate `GraphAuth` load none of `msal` /
`msal-extensions` / `platformdirs` at import time. The `graph` extra's
pinned set lives in `pyproject.toml`; ADR-0021 records the SDK choice.

### Credential masking

Credentials are masked on two surfaces: `GraphAuth` takes
`client_secret: str | Secret`, reveals it only internally, and masks it
in `__repr__`; and config-loaded backends inherit the same auto-wrap
because `client_secret` / `client_certificate` are in the default
`_SENSITIVE_KEYS` set. The `Authorization` bearer is redacted from every
backend log record and never appears in exception text. The mechanisms
are specified by GR-035 (header redaction) and SEC-003 / SEC-004 /
SEC-007 (the `Secret` wrapper, `_SENSITIVE_KEYS`, `SecretRedactionFilter`).

### Config loader responsibility

When the registry constructs a Graph backend from static config
(ADR-0001), it builds a default `GraphAuth` from the config fields and
passes its callable in. User-supplied callables are expressible only
through direct construction, not static config.

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
