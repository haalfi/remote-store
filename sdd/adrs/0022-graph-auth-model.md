# ADR-0022: Microsoft Graph Auth Model — Dual Flows Behind a Token-Provider Protocol

## Status

Accepted. Revised 2026-06-03 (in-place, per user override of the
project's normally-immutable ADR rule — see CHANGELOG `[Unreleased]`).

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

### Flows covered by `GraphAuth`

- **Client-credentials.** `tenant_id`, `client_id`, and
  `client_secret` (or `client_certificate`). Admin-consented
  application permissions (`Files.ReadWrite.All`,
  `Sites.ReadWrite.All`) on the target tenant.
- **Device-code.** `tenant_id` and `client_id` (public client).
  Delegated permissions. The user completes the login in a browser;
  MSAL caches the resulting refresh token.

### Token caching

MSAL's `SerializableTokenCache` is serialized to a file under
`platformdirs.user_config_dir("remote-store")`. Users can override the
path or disable persistent caching by passing a
`SerializableTokenCache` directly or by supplying their own callable.

`platformdirs` is a runtime dependency of the built-in `GraphAuth`
implementation (see ADR-0021 for the full `graph` extra dependency
set). Callers that supply their own provider and never instantiate
`GraphAuth` do not load `platformdirs` at import time (standard
lazy-import pattern, applied here to the `backends/_graph_auth`
module).

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
  `client_secret` is **not** in the default `_SENSITIVE_KEYS` set
  (SEC-003) — `RegistryConfig.from_dict()` therefore does **not**
  auto-wrap it. The implementation amends `_SENSITIVE_KEYS` to add
  `"client_secret"` (and `"client_certificate"`) so config-loaded
  Graph backends inherit the same auto-wrap protection as S3 / Azure /
  SFTP credentials. The amendment ships with the implementation PR.
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
- **`_SENSITIVE_KEYS` widens.** The amendment to add
  `"client_secret"` (and `"client_certificate"`) is a one-line
  config change with no behavioural impact on other backends
  (their config keys do not collide).

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
