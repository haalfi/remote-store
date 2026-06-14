# GraphBackend

Native async Microsoft Graph backend over OneDrive, SharePoint document
libraries, and Teams files. A single instance targets one drive
(`drive_id`); transport is `httpx` and auth is a token-provider callable
(the built-in `GraphAuth` helper, or any user-supplied callable). Requires
the `graph` extra. See the [Graph setup guide](../../../../guides/backends/graph-setup.md)
for provisioning credentials and resolving a `drive_id`.

Graph is async-only — there is no synchronous `GraphBackend`. To use it from
synchronous code, wrap it with [`AsyncBackendSyncAdapter`](../adapters.md).

::: remote_store.aio.GraphBackend
    options:
      members: false
      show_bases: false

## GraphAuth

MSAL-backed token provider for `GraphBackend`. Wraps the client-credentials
(app-only) and device-code (interactive) flows and exposes the bearer token
through the token-provider protocol — a `GraphAuth` instance is itself a
`Callable[[], str]`.

::: remote_store.aio.GraphAuth
    options:
      show_bases: false

## GraphUtils

Namespace helpers for Graph configuration. `resolve_drive_id` turns "my
OneDrive" (`"me"`), a SharePoint site URL, or a Teams channel mapping into the
opaque `drive_id` the backend requires.

::: remote_store.aio.GraphUtils.resolve_drive_id
    options:
      show_root_heading: true
      heading_level: 3

::: remote_store.aio.GraphUtils.aresolve_drive_id
    options:
      show_root_heading: true
      heading_level: 3

## See also

- [Graph Backend Guide](../../../../guides/backends/graph.md) — usage patterns and capabilities
- [Graph setup guide](../../../../guides/backends/graph-setup.md) — provisioning credentials and resolving a `drive_id`
- [Adapters](../adapters.md) — run `GraphBackend` from synchronous code
