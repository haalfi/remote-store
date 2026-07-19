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

**Option B: two concrete backends over a shared private base.**

```
_SQLAlchemyBaseBackend(Backend)   # private, not exported
├── SQLBlobBackend                # v1, full read-write KV store
└── SQLQueryBackend               # v2, read-only query materializer
```

- **Two classes, not one `mode` flag.** The blob and query use cases have
  fundamentally different invariants (read-write vs read-only), capability sets,
  and dependencies (`[sql]` vs `[sql-query]`); a `mode="blob"|"query"` parameter
  would spread `if mode == ...` branching through every method. *Reverse if* the
  two use cases converge on one invariant set and dependency footprint.
- **A shared base, not two independent classes.** `_SQLAlchemyBaseBackend`
  centralises engine lifecycle, health check, error mapping, and SQLite
  detection, avoiding Option C's duplication while each subclass keeps its own
  Backend contract and evolves independently. *Reverse if* the shared surface
  shrinks to near nothing, making the base pure indirection.
- **The base is private.** It is not exported or documented for users, so it
  stays free to evolve. *Reverse if* third parties need to subclass it to build
  their own SQL backend.

The engine `url`-vs-`engine` (owned vs borrowed) lifecycle and the virtual
prefix-based folder model are spec-rate and live in
[spec 040](../specs/040-sql-blob-backend.md) (SQL-BLOB-001, SQL-BLOB-025,
SQL-BLOB-041, SQL-BLOB-061).

## Consequences

- `SQLBlobBackend` ships as v1 with `sqlalchemy` as its only dependency.
- `SQLQueryBackend` ships later (v2) with an additional `pyarrow` dependency.
- The shared base (`_SQLAlchemyBaseBackend`) is private API — not exported,
  not documented for users, free to evolve.
- Two registry types: `"sql-blob"` and (future) `"sql-query"`.
- Two optional extras: `[sql]` and (future) `[sql-query]`.
