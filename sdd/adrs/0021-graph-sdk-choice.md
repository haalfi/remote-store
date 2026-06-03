# ADR-0021: Microsoft Graph SDK Choice — `httpx` + `msal`

## Status

Accepted

## Context

ID-127 adds a Microsoft Graph backend covering OneDrive (personal and
business), SharePoint document libraries, and Teams files. Three
credible options exist for the HTTP transport and auth library:

1. **Direct REST via `httpx` + `msal`.** Call the Graph HTTP surface
   ourselves; use Microsoft's MSAL library for token acquisition and
   caching.
2. **`msgraph-sdk` (Kiota-generated).** Microsoft's official Python
   SDK for Graph. Async-only client. Transitive dependency on
   `kiota-abstractions`, `kiota-http`, `kiota-authentication-azure`,
   and `azure-identity`.
3. **`Office365-REST-Python-Client`.** Third-party library that mixes
   Graph and legacy SharePoint REST patterns.

The surface this backend needs is narrow: a dozen Graph endpoints
covering item metadata, children listing, range download via
`@microsoft.graph.downloadUrl`, small-file `PUT /content`, resumable
upload sessions, async copy with monitor-URL polling, and delete. The
non-trivial work — upload-session chunking with resume, async-operation
polling, URL-expiry-mid-read handling — is not carried by any of these
SDKs; the backend has to write it regardless.

`httpx` is already in the project as an **optional** runtime
dependency: `pip install remote-store[httpx]` selects it as the HTTP
adapter for `ReadOnlyHttpBackend`. It is not in the base install and
no other backend pulls it transitively. `msal` is Microsoft's
supported auth library, lightweight, stable, and used by
`azure-identity` internally.

## Decision

Build the backend on `httpx` (async client) plus `msal` for token
acquisition and cache serialization.

The `graph` optional extra pins:

- `httpx` — async HTTP transport.
- `msal` — token acquisition (used by the built-in `GraphAuth` helper).
- `platformdirs` — resolves the MSAL token-cache path under
  `user_config_dir("remote-store")`; consumed only by `GraphAuth` and
  imported lazily so callers supplying their own token-provider
  callable never load it (see ADR-0022).

The backend constructs an `httpx.AsyncClient` internally and treats
Graph as a narrow REST surface with hand-written request helpers,
pagination, and error mapping.

`msgraph-sdk` is explicitly rejected. `Office365-REST-Python-Client`
is out of scope (legacy SharePoint REST is not a goal — see RFC-0010).

## Consequences

- **Narrow dependency footprint.** `httpx` + `msal` + `platformdirs`
  is lighter than `msgraph-sdk` + Kiota runtime + `azure-identity`.
  `httpx` is not in the base install — users who install only the
  `graph` extra pay for it once; users who already had
  `remote-store[httpx]` for `ReadOnlyHttpBackend` pay for nothing
  extra.
- **Full control of request layer.** Error mapping, retry,
  `Retry-After` handling, and monitor-URL polling are written
  directly against `httpx.Response` and raw status codes. No
  Kiota-shaped abstractions in the way.
- **Async-native fit.** `httpx.AsyncClient` is the transport; the
  backend implements `AsyncBackend` per ADR-0012. Sync callers
  bridge through `AsyncBackendSyncAdapter` (ADR-0025) — already
  landed and the conformance suite is parameterised for it.
- **Maintenance responsibility stays with us.** The Graph drives /
  items v1.0 surface is stable; ongoing churn is expected to be low.
  If the backend later grows to cover a materially broader Graph
  surface (mail, calendar, Teams messages, groups), `msgraph-sdk`
  becomes worth re-evaluating. A new ADR would supersede this one.

## References

- RFC-0010: Microsoft Graph Backend (SDK evaluation section)
- `sdd/specs/044-graph-backend.md`
- ADR-0012: Async Store / Backend API
- ADR-0025: Async-to-Sync Backend Adapter
- `httpx` project: https://www.python-httpx.org/
- MSAL for Python: https://learn.microsoft.com/entra/msal/python/
- Microsoft Graph v1.0 reference:
  https://learn.microsoft.com/graph/api/overview
