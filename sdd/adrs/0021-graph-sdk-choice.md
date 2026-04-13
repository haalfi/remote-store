# ADR-0021: Microsoft Graph SDK Choice — `httpx` + `msal`

## Status

Accepted

## Context

ID-127 adds a Microsoft Graph backend covering OneDrive (personal and
business), SharePoint document libraries, and Teams files. Before writing
the backend, the transport and auth-library choice has to be locked in.
Three credible options exist:

1. **Direct REST via `httpx` + `msal`.** Call the Graph HTTP surface
   ourselves; use Microsoft's MSAL library for token acquisition and
   caching.
2. **`msgraph-sdk` (Kiota-generated).** Microsoft's official Python SDK
   for Graph. Generated from the Graph OpenAPI description via Kiota.
   Async-only client. Transitive dependency on `kiota-abstractions`,
   `kiota-http`, `kiota-authentication-azure`, and `azure-identity`.
3. **`Office365-REST-Python-Client`.** Third-party library that mixes
   Graph and legacy SharePoint REST patterns.

The surface we need is narrow: a dozen Graph endpoints covering item
metadata, children listing, range download via `@microsoft.graph.downloadUrl`,
small-file `PUT /content`, resumable upload sessions, async copy with
monitor-URL polling, and delete. The non-trivial work — upload-session
chunking with resume, async-operation polling, URL-expiry-mid-read
handling — is not carried by any of these SDKs; we have to write it
regardless.

`httpx` is already a runtime option in the project for the HTTP backend
extra. `msal` is Microsoft's supported auth library, small (~350 KB
wheel), stable, and used by `azure-identity` internally.

## Decision

Build the backend on `httpx` (async client) plus `msal` for token
acquisition and cache serialization.

The `graph` optional extra installs `httpx`, `msal`, and
`platformdirs` (the latter used by the built-in `GraphAuth` for
resolving the MSAL token-cache path; see ADR-0022). The backend
constructs an `httpx.AsyncClient` internally and treats Graph as a
narrow REST surface with hand-written request helpers, pagination, and
error mapping.

`msgraph-sdk` is explicitly rejected. `Office365-REST-Python-Client` is
out of scope (legacy SharePoint REST is not a goal — see RFC-0010).

## Consequences

- **Narrow dependency footprint.** `httpx` + `msal` is lighter than
  `msgraph-sdk` + Kiota runtime + `azure-identity`. The existing
  HTTP backend already pulls `httpx`, so users combining the two pay
  for it once.
- **Full control of request layer.** Error mapping, retry, `Retry-After`
  handling, and monitor-URL polling are written directly against
  `httpx.Response` and raw status codes. No Kiota-shaped abstractions
  in the way.
- **Async-native fit.** `httpx.AsyncClient` is the transport; the
  backend implements `AsyncBackend` per ADR-0012. No forced
  adaptation layer.
- **Maintenance responsibility stays with us.** The cost of not using
  `msgraph-sdk` is that we maintain the request layer ourselves as
  the Graph surface evolves. The surface touched here is stable
  (drives/items endpoints are part of the v1.0 API), so ongoing churn
  is expected to be low.
- **Future revisit point.** If the backend later grows to cover
  a materially broader Graph surface (mail, calendar, Teams messages,
  groups), re-evaluating `msgraph-sdk` becomes reasonable. A new ADR
  would supersede this one.

## References

- RFC-0010: Microsoft Graph Backend (SDK evaluation section)
- `sdd/specs/044-graph-backend.md`
- ADR-0012: Async Store / Backend API
- `httpx` project: https://www.python-httpx.org/
- MSAL for Python: https://learn.microsoft.com/entra/msal/python/
- Microsoft Graph v1.0 reference:
  https://learn.microsoft.com/graph/api/overview
