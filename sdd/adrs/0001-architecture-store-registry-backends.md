# ADR-0001: Architecture — Store, Registry, Backends

## Status

Accepted

## Context

We need a layered architecture for backend-agnostic remote storage. Key tensions:

- Users want simplicity (one object to interact with)
- Backends have wildly different capabilities and lifecycles
- Configuration should be declarative, not imperative
- Multiple stores may share a single backend connection

## Decision

Three-layer architecture:

1. **Store** — user-facing, immutable, folder-scoped. All operations use relative paths. Delegates all I/O to a backend. Thin wrapper with path scoping and capability gating.

2. **Registry** — owns backend lifecycle. Lazily instantiates backends from config. Shares backend instances across stores. Acts as context manager for cleanup.

3. **Backend (ABC)** — encapsulates all storage-specific behavior. Declares capabilities. Maps native errors to normalized types. Never exposed directly to end users.

```
User → Store → Backend (ABC) → Local/S3/Azure/SFTP
         ↑
      Registry (lifecycle, config, factory)
```

## Consequences

- Users interact only with `Store` — simple, safe API
- Adding a backend = implement the ABC + add conformance fixture
- Backend lifecycle is centralized in Registry, not scattered
- Store is cheap and immutable — safe for concurrent use
- No dependency on async frameworks (sync-only initially)
