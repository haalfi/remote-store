# Architecture Overview

This page explains *why* `remote-store` is structured the way it is. For API details, see the [API Reference](https://docs.remotestore.dev/stable/reference/api/index.md). For how-to instructions, see the Guides section in the sidebar.

## Three-layer design

```
+-----------+     +-----------+     +-----------+
|   Store   |---->|  Registry |---->|  Backend  |
| (user API)|     | (lifecycle|     | (storage  |
|           |     |  manager) |     |  adapter) |
+-----------+     +-----------+     +-----------+
      |                                   |
      v                                   v
  Relative paths                   Native paths
  (logical keys)                   (bucket/prefix)
```

### Store

The primary user-facing abstraction. A Store is a **logical remote folder** scoped to a root path. All operations use relative paths within that scope.

Stores are **immutable and thread-safe** — cheap to create, safe to share across threads. A Store does not own its backend; multiple stores can share one backend instance.

`Store.child(subpath)` creates a sub-scoped store without additional backend connections.

### Registry

The lifecycle manager. It:

- Loads and validates configuration (`RegistryConfig`)
- Lazily creates backend instances (one per backend config, shared across stores)
- Manages cleanup via `close()`

The Registry is a **passive resource** — it does not spawn threads or async tasks, making it compatible with any concurrency model.

### Backend

The storage adapter layer. Each backend encapsulates all provider-specific behavior:

- Path normalization and validation
- Native I/O operations (streaming-first)
- Error mapping (native exceptions to `remote-store` error types)
- Capability declaration

Backends are an **implementation detail** — user code never interacts with backends directly (except via `Store.unwrap()` for escape-hatch access).

## Error hierarchy

All backend-specific exceptions are normalized into a small set of errors. Backend exceptions **never leak** to user code.

```
RemoteStoreError
  +-- NotFound
  +-- AlreadyExists
  +-- PermissionDenied
  +-- InvalidPath
  +-- CapabilityNotSupported
  +-- DirectoryNotEmpty
  +-- BackendUnavailable
```

Each error carries structured attributes: `message`, `path`, and `backend`.

## Extension model

Extensions in `ext.*` add functionality without modifying the core — covering observability, caching, glob pattern matching, PyArrow integration, and more. Some extensions are always available (no extra dependencies); others require optional extras such as `arrow`, `otel`, or `dagster`.

See the [Extensions guide](https://docs.remotestore.dev/stable/guides/extensions/index.md) for the full list and installation instructions.

Extensions follow the [extension architecture contract](https://docs.remotestore.dev/stable/explanation/design/adrs/0008-extension-architecture/index.md): no singleton state, no global registries, composable with the core Store API.

## Capability system

Backends declare supported operations via the `Capability` enum. This enables:

- **Compile-time clarity** — users know what to expect from each backend
- **Runtime guards** — operations fail fast with `CapabilityNotSupported` instead of mysterious backend errors
- **Portable fallbacks** — extensions like `ext.glob` provide software implementations for backends that lack native support

See the [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) for the full table.

## Configuration philosophy

Configuration follows [strict resolution rules](https://docs.remotestore.dev/stable/explanation/design/adrs/0002-config-resolution-no-merge/index.md):

1. Config-as-code has absolute priority (TOML, YAML, or dict)
1. No merging, no overrides, no magic environment variable layering
1. Deterministic and test-safe — same config always produces same behavior

## Design decisions

Detailed rationale lives in the ADRs under [`sdd/adrs/`](https://docs.remotestore.dev/stable/explanation/design/adrs/index.md).

## See also

- [Security Model](https://docs.remotestore.dev/stable/explanation/security-model/index.md) — credential handling and trust boundaries
- [Performance](https://docs.remotestore.dev/stable/explanation/performance/index.md) — benchmark data and optimization guidance
- [Concurrency](https://docs.remotestore.dev/stable/explanation/concurrency/index.md) — thread safety and atomicity guarantees
