# ADR-0018: SQLAlchemy Backend — Two-Class Architecture with Shared Base

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

ID-119 introduces SQL-backed storage. The research
(`sdd/research/research-sqlalchemy-backend.md`, section 3) identified two
distinct use cases:

1. **Key-value blob store** — read-write, full Backend contract, maps keys
   to table rows (`SQLBlobBackend`).
2. **Query materializer** — read-only, maps keys to SQL queries, serializes
   result sets to Parquet/CSV/Arrow (`SQLQueryBackend`, v2).

Three design options were considered:

**Option A — Single backend with `mode` parameter.** One class,
`SQLAlchemyBackend(mode="blob"|"query")`. Fewer imports, simpler registry.
But the modes have fundamentally different invariants (read-only vs
read-write), different capability sets, and different dependencies
(`sqlalchemy` only vs `sqlalchemy` + `pyarrow`). A `mode` flag spreads
`if mode == ...` branching throughout every method.

**Option B — Two concrete backends, shared base.** `_SQLAlchemyBaseBackend`
(private ABC) provides engine lifecycle, health check, error mapping, and
SQLite detection. `SQLBlobBackend` and `SQLQueryBackend` inherit it and
implement their own Backend contract. Clean capability contracts, independent
evolution, independent dependency extras (`[sql]` vs `[sql-query]`).

**Option C — No shared base, fully independent.** Two unrelated classes.
Duplicates engine lifecycle, health check, error mapping, and SQLite PRAGMA
setup.

## Decision

**Option B — Two concrete backends, shared base.**

```
_SQLAlchemyBaseBackend(Backend)   # private, not exported
├── SQLBlobBackend                # v1 — full read-write KV store
└── SQLQueryBackend               # v2 — read-only query materializer
```

### Engine lifecycle: owned vs borrowed

The base accepts exactly one of `url: str` or `engine: Engine`:

- `url` → creates and **owns** the engine. `close()` disposes it.
- `engine` → **borrows** it. `close()` is a no-op.

This lets standalone scripts get automatic cleanup while web apps share
their connection pool.

### Folder semantics: virtual prefixes

Unlike `MemoryBackend` and `LocalBackend` (which use explicit folder nodes),
`SQLBlobBackend` uses **virtual prefix-based folders** — a "folder" is any
key prefix that has child keys. This matches the S3/Azure pattern and avoids
maintaining a separate folder table or marker rows.

## Consequences

- `SQLBlobBackend` ships as v1 with `sqlalchemy` as its only dependency.
- `SQLQueryBackend` ships later (v2) with an additional `pyarrow` dependency.
- The shared base (`_SQLAlchemyBaseBackend`) is private API — not exported,
  not documented for users, free to evolve.
- Two registry types: `"sql-blob"` and (future) `"sql-query"`.
- Two optional extras: `[sql]` and (future) `[sql-query]`.
