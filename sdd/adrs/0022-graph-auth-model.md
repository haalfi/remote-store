# ADR-0022: Microsoft Graph Auth Model — Dual Flows Behind a Token-Provider Protocol

## Status

Accepted

## Context

The Graph backend (ID-127, RFC-0010) has to work in two distinct
operating environments:

- **Daemon / service processes** with no human at the keyboard, using an
  app registration plus client secret or certificate. OAuth 2.0
  client-credentials flow.
- **Interactive CLI / notebook sessions** where a human can complete a
  login in a browser, typically using OAuth 2.0 device-code flow.

Both flows ultimately produce a bearer token that the backend attaches
to every Graph request as an `Authorization: Bearer …` header. The
backend does not care which flow produced the token — it only needs to
be able to obtain a current one.

Other credential sources (managed identity, workload identity, cached
Azure CLI login) are out of scope for v1 but are likely to surface
later.

## Decision

The backend depends on a **token-provider callable**, not a concrete
auth class. Two variants cover sync and async call sites:

- `Callable[[], str]` — synchronous provider.
- `Callable[[], Awaitable[str]]` — async provider.

A built-in helper, `GraphAuth`, wraps MSAL and implements both client-
credentials and device-code flows, exposing the result as one of the
two callables. Users who already have another way to obtain a token
(managed identity, corporate auth broker, custom refresh strategy)
substitute their own callable. The backend does not couple to MSAL
through the constructor signature — only through the optional default
helper.

### Flows covered by `GraphAuth`

- **Client-credentials.** `tenant_id`, `client_id`, and
  `client_secret` (or `client_certificate`). Admin-consented
  application permissions (`Files.ReadWrite.All`,
  `Sites.ReadWrite.All`) on the target tenant.
- **Device-code.** `tenant_id` and `client_id` (public client).
  Delegated permissions. The user completes the login in a browser;
  MSAL caches the resulting refresh token.

### Token caching

MSAL's `SerializableTokenCache` is serialized to a file in the user's
config directory, resolved via `platformdirs.user_config_dir("remote-store")`.
Users can override the path or disable persistent caching by passing a
`SerializableTokenCache` directly or by supplying their own callable.

`platformdirs` is a runtime dependency of the built-in `GraphAuth`
implementation (see ADR-0021 for the full `graph` extra dependency set).
Callers that supply their own provider and never instantiate `GraphAuth`
do not load `platformdirs` at import time (standard lazy-import pattern
for `ext/*`, applied here to the `backends/_graph_auth` module).

### What the backend does with the provider

The provider is called lazily: no token acquisition happens in
`__init__`. The backend invokes the callable on first request and on
`401 InvalidAuthenticationToken` responses (one-shot refresh + retry).
Results are not cached inside the backend — MSAL (or the user-supplied
provider) owns the lifetime policy.

### Credential masking

`Authorization` headers are redacted anywhere request or response
metadata surfaces in logs, error messages, or debug dumps, following
AF-008 rules.

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
  wrapper code can reuse the same `GraphAuth` instance without an
  event loop.
- **Config-loader responsibility.** When the Registry constructs a
  Graph backend from YAML/JSON config (ADR-0002), it builds a
  default `GraphAuth` from the config fields and passes its callable
  into the backend. User-supplied callables are not expressible in
  config and only apply to direct construction.

## References

- RFC-0010: Microsoft Graph Backend (auth section)
- `sdd/specs/044-graph-backend.md` (GR-006 through GR-008)
- ADR-0012: Async Store / Backend API
- MSAL Python token cache:
  https://learn.microsoft.com/entra/msal/python/msal.token_cache
- AF-008: credential masking
