# Research: SQLAlchemy Backends & Composite Store

**Item ID:** ID-119 (SQLAlchemy backends), ID-120 (composite store)
**Date:** 2026-03-26
**Status:** Research complete

---

## 1. Problem Statement

### The unifying concept: key → byte resolution

A Store is a **deterministic key → byte resolver**. Not storage. Not filesystem.
Not database. A resolver. Every existing backend already works this way:

- `LocalBackend`: key → filesystem path → bytes
- `S3Backend`: key → S3 object → bytes
- `ReadOnlyHttpBackend`: key → URL → bytes

This framing makes two new ideas feel natural rather than bolted on:

1. **SQLAlchemy backends** — resolvers that map keys to SQL. `SQLBlobBackend`
   resolves key → row lookup → bytes. `SQLQueryBackend` resolves key → query
   execution → serialized bytes. From the caller's perspective, identical to
   reading from S3.

2. **Composite store** — a resolver that delegates to other resolvers.
   `CompositeStore` resolves key → (try hot store, then warm, then cold) → bytes.
   The caller sees one Store.

### Why these belong together

The SQLAlchemy backends are useful standalone (database as key-value store, or
query results as portable data products). The composite store is useful standalone
(multi-tier blob storage). Combined, they enable the full hot/warm/cold lifecycle
without consumer code changes.

### The deeper pattern

Every backend is a resolution strategy. The capability system already describes
*what resolution strategies are available*, not what a filesystem can do.
SQLAlchemy backends and CompositeStore make this explicit — they extend the
resolution model into databases and across backend boundaries.

---

## 2. Prior Art & Comparable Abstractions

### 2.1 Query Results as Data Products

| Project | Approach | Key insight for us |
|---------|----------|--------------------|
| **Dagster IO Managers** | `DbIOManager` maps asset keys to tables by convention (`path[-1]` = table, `path[-2]` = schema). Parquet variants exist (DuckDB). | Closest architectural match. Convention-based key→table, serialization on read. |
| **Intake (intake-sql)** | YAML catalog maps logical names to SQL connections/queries. Returns DataFrames via `pd.read_sql`. | Config-based key→query pattern. Catalog YAML is a proven UX. |
| **dbt** | `.sql` files as named models. Materialization strategies: view, table, incremental. Filename = table name. | Convention-based naming. Proves "SQL as named data product" at scale. |
| **Feast** | `FeatureView` → `DataSource` mapping. SQL Registry backed by SQLAlchemy. | Logical name → physical source indirection via registry. |
| **DuckLake** (2025) | SQL database as metadata catalog, Parquet files in object storage. All metadata ops are pure SQL transactions. | Proves "SQL catalog + Parquet files" pattern works at scale. |
| **dlt** | SQLAlchemy source → filesystem destination (Parquet/CSV/JSON on S3/GCS/Azure). | Full pipeline from SQL to serialized files. |
| **aiosql / PugSQL** | Named SQL queries in `.sql` files, loaded as callable Python methods. | Clean key→query registry pattern. Comment-based naming (`-- name: get_users`). |

### 2.2 Database as Blob Store

| Project | Approach | Key insight for us |
|---------|----------|--------------------|
| **SQLite SQLAR format** | Single table: `(name TEXT PK, mode INT, mtime INT, sz INT, data BLOB)`. Each row = one file, Deflate-compressed. Only ~2% larger than ZIP. | Proves file-in-DB works. Minimal schema. |
| **Fossil SCM** | ALL content (source, wiki, tickets) in SQLite `blob` table. Delta-compressed. | Entire VCS backed by SQLite blob storage — extreme validation of the pattern. |
| **PostgreSQL BYTEA** | Up to 1 GB per value. TOAST transparently chunks into ~2 KB. `EXTERNAL` storage avoids double-compression. | Works but ~10x slower than filesystem for retrieval. Hybrid recommended for >100 MB. |
| **SQLite Blob API** (Python 3.11+) | `connection.blobopen()` returns file-like `Blob` with `read()`, `write()`, `seek()`. | Native file-like interface to DB blobs — maps directly to `Backend.read() → BinaryIO`. |
| **django-db-file-storage** | Drop-in Django `FileSystemStorage` replacement using DB. | Proves the pattern is wanted in web frameworks. All docs warn about performance. |
| **Zarr SQLiteStore** | `CREATE TABLE zarr_table (key TEXT PK, value BLOB)`. Zarr v3 proposal adds async. | Key-value blob store in SQLite. ~2x faster than LocalStore at 10 KB, ~0.6x at 1 MB. |

### 2.3 Tiered / Federated Storage

| Project | Approach | Key insight for us |
|---------|----------|--------------------|
| **Trino spooling protocol** | Query results written to object storage (S3/ABFS/GCS) for parallel retrieval. ~4x speedup. | DB→object-store materialization at query engine level. |
| **Redash QRDS** | Caches latest query result in PostgreSQL. Query cached results via SQLite syntax. Pluggable storage proposed. | Query result caching with storage abstraction. |
| **Superset** | `RESULTS_BACKEND` configurable: Redis, S3, Memcached, filesystem. | Pluggable result storage backends — same pattern we'd build. |
| **Data mesh output ports** | Data products expose multiple ports: tables, files, APIs. Consumer picks format. | Multi-format output is the standard pattern, not an edge case. |
| **Litestream / LiteFS** | SQLite replication to S3 / FUSE-based cluster replication. | SQLite as primary store with object-store backup — tiered storage at DB level. |

### 2.4 Filesystem Abstractions That Considered SQL

- **fsspec**: No SQL backend exists. The `FSMap` / `get_mapper()` provides key-value
  interface over any filesystem, but nobody has built a SQL filesystem.
- **pyfilesystem2**: Community requested SQL backends (issues #498, #534). Maintainer
  said "certainly doable" but warned of "a lot of corner-cases." Never implemented.
  The full filesystem API (mkdir, rename, permissions) is hard to map onto SQL.

**Takeaway**: Nobody has built this exact thing. The filesystem abstractions considered
it and backed off due to API surface mismatch. But remote-store's capability system
(declare what you support, gate the rest) solves exactly that problem.

---

## 3. Architecture: Two Backends, Shared Base

The research reveals two distinct and valid use cases. After review, the decision is
**two concrete backends** sharing a common base — not one backend with a mode flag.

**Rationale**: the modes have fundamentally different invariants (read-only vs
read-write KV store), different capability sets, and will evolve independently.
A `mode` parameter would spread `if mode == ...` branching throughout. Separate
classes give cleaner capability contracts and independent evolution.

```
_SQLAlchemyBaseBackend (ABC)
├── SQLQueryBackend   (Mode A — read-only query materializer)
└── SQLBlobBackend    (Mode B — read-write key-value blob store)
```

**Shared base** (`_SQLAlchemyBaseBackend`) provides:
- Engine/connection management, pooling
- Health check (`check_health()` → `SELECT 1`)
- Error mapping (SQLAlchemy exceptions → remote-store errors)
- `unwrap()` → returns SQLAlchemy `Engine`
- `close()` → dispose engine

**Engine lifecycle:**
- Accepts either a URL string (creates and owns the engine) or a pre-existing
  `sqlalchemy.Engine` (borrows — `close()` is a no-op). This lets web apps share
  their connection pool.
- `Store.child()` shares the parent's backend and therefore the same engine/pool.
- Context manager (`with Store(...) as s:`) calls `close()` on exit, which disposes
  owned engines. Borrowed engines are left to their owner.

### SQLQueryBackend (read-only query materializer)

Maps path keys to SQL queries. On `read()`, executes the query and serializes the
result set to the format implied by the key extension.

```python
backend = SQLQueryBackend(
    url="postgresql://...",
    queries={
        "reports/daily_sales.parquet": "SELECT date, SUM(amount) FROM orders GROUP BY date",
        "reports/user_summary.csv": "SELECT * FROM user_summary_mv",
    },
    strict=True,  # only explicit mappings — no view or convention fallback
)
store = Store(backend)
data = store.read_bytes("reports/daily_sales.parquet")  # → parquet bytes
```

**Capabilities**: `READ`, `LIST`, `METADATA`, `GLOB`, `SEEKABLE_READ`. Everything
else raises `CapabilityNotSupported`.

**Key-to-query resolution** (strict precedence):
1. Explicit mapping (config dict) — highest priority
2. View-based — key maps to a database view by name
3. Convention — `"schema/table.ext"` → `SELECT * FROM schema.table`

**`strict` defaults to `True`** (security-by-default). Only explicit mappings are
used. Set `strict=False` to enable view and convention fallback — but note that
convention mode (`schema/table.ext → SELECT * FROM schema.table`) can expose
arbitrary tables to anyone with Store access. Use only with trusted callers or
read-only database users.

**Introspection** (via unified `resolve()` — see §5.1):
```python
store.resolve("reports/daily_sales.parquet")
# → ResolutionPlan(kind="sql_query", source="explicit",
#      query="SELECT ...", format="parquet")
```

### SQLBlobBackend (read-write key-value store)

Uses a table as key-value storage. Each row holds one "file."

```python
backend = SQLBlobBackend(
    url="sqlite:///store.db",
    # Uses default schema: (key TEXT PK, data BLOB, size INT, modified_at TIMESTAMP, content_type TEXT)
    max_blob_size=10 * 1024 * 1024,  # 10 MB — optional safety limit
)
store = Store(backend)
store.write("models/v3.pkl", model_bytes)
data = store.read_bytes("models/v3.pkl")
```

**Capabilities**: `READ`, `WRITE`, `DELETE`, `LIST`, `METADATA`, `ATOMIC_WRITE`,
`MOVE`, `COPY`, `GLOB`, `SEEKABLE_READ`.

**Schema** (inspired by SQLAR + Zarr SQLiteStore):
```sql
CREATE TABLE remote_store_objects (
    key         TEXT PRIMARY KEY CHECK (length(key) > 0),
    data        BLOB NOT NULL,
    size        INTEGER NOT NULL,
    modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_type TEXT,
    digest      TEXT,
    extra       TEXT  -- JSON blob for backend-specific metadata
);
```

The `PRIMARY KEY` on `key` already creates a B-tree index that supports prefix
range scans (`WHERE key LIKE 'prefix/%'`). No separate index needed.

**Schema flexibility:**
- Default: auto-creates `remote_store_objects` table with the schema above.
- `table_name="my_table"` to use a different table name (still auto-created with
  the default schema).
- `create_table=False` for existing tables — requires at minimum `(key TEXT PK,
  data BLOB)`. Optional columns (`size`, `modified_at`, `content_type`, `digest`,
  `extra`) are detected by introspection; missing columns degrade gracefully
  (e.g., no `modified_at` → `FileInfo.modified_at` returns `None`).
- Column name mapping is a v2 consideration if demand materializes.

**Performance guidelines**:
- <10 MB per blob: works well across all supported databases
- 10–100 MB: use with caution; consider `max_blob_size` guard
- >100 MB: discouraged — use a blob storage backend (S3, local) instead

**SQLite specialization** (worth it — zero-infrastructure persistent store):
- Use `blobopen()` for streaming reads (Python 3.11+). On 3.10: fall back to
  `SELECT data FROM ... WHERE key = ?` into `BytesIO` (full materialization,
  no streaming). This mirrors the `SpooledTemporaryFile` 3.10 compat pattern
  already used in `ext/seekable.py`.
- Enable WAL mode (`PRAGMA journal_mode=WAL`)
- Set `PRAGMA synchronous=NORMAL` for better write performance
- Use `GLOB` operator instead of `LIKE` for pattern matching

---

## 4. Serialization Pipeline (SQLQueryBackend)

### ResultSerializer abstraction

Serialization needs a clean boundary — not inline logic in `read()`.

```python
class ResultSerializer(Protocol):
    """Converts a SQL result set to bytes in a specific format."""
    def serialize(self, result: CursorResult, format: str) -> BinaryIO: ...
```

Built-in implementations:
- `ArrowSerializer` — default, uses PyArrow: result → Arrow Table → Parquet/CSV/IPC
- `ADBCSerializer` — optional fast path, zero-copy Arrow-native for supported DBs

Benefits: testable in isolation, swappable, enables future formats without touching
backend logic.

### SQL → Bytes pipeline

| Stage | Options | Recommendation |
|-------|---------|----------------|
| **SQL execution** | SQLAlchemy Core `connection.execute()` | Use `stream_results=True` + `yield_per` for memory-bounded reads |
| **Result → Arrow** | ADBC (zero-copy, fastest), ConnectorX (Rust, parallel), SQLAlchemy + PyArrow (widest support) | Arrow-native paths (ADBC/ConnectorX) preferred; SQLAlchemy + PyArrow as fallback |
| **Arrow → bytes** | Parquet (`pyarrow.parquet`), CSV (`pyarrow.csv`), Arrow IPC (`pyarrow.ipc`) | Extension-based: `.parquet` → Parquet, `.csv` → CSV, `.arrow` → IPC |

**Prefer Arrow-native paths** over manual batching. ADBC and ConnectorX go directly
from wire protocol to Arrow columnar format, bypassing Python row-by-row conversion.
Manual `partitions()` + `RecordBatch.from_pydict()` is the fallback when Arrow-native
drivers aren't available.

### Type mapping concerns

SQL types don't map 1:1 to Arrow/Parquet: `DECIMAL`, `INTERVAL`, `JSONB`, `ARRAY`,
`GEOGRAPHY` all need explicit handling. SQLAlchemy's type reflection + PyArrow's type
coercion handles most cases, but edge cases will need documented escape hatches.

### Dependencies

- **Required**: `sqlalchemy` (already widely used, pure Python)
- **SQLQueryBackend**: `pyarrow` (already an optional dep for `S3PyArrowBackend`)
- **Optional fast path**: `adbc-driver-postgresql`, `adbc-driver-sqlite`, `connectorx`

Packaging: `pip install remote-store[sql]` for SQLBlobBackend (sqlalchemy only),
`pip install remote-store[sql-query]` for SQLQueryBackend (sqlalchemy + pyarrow).

### Caching

Caching is **not embedded** in the backend. Use `ext.cache` (existing infrastructure).

Cache key for query results (deterministic across processes):
```python
cache_key = hashlib.sha256(
    (query_text + "\0" + str(sorted(params)) + "\0" + schema_version).encode()
).hexdigest()
```

Note: Python's built-in `hash()` is randomized per process (PYTHONHASHSEED) and
must not be used for persistent or cross-process cache keys.

The backend provides `resolve()` for introspection (see §5.1); ext.cache wraps
the Store. No built-in TTL, no `refresh()` method — that's the cache extension's
job. Future: cache keys could derive from `hash(plan)` for principled
invalidation.

---

## 5. Resolution Model & Composite Store

### 5.1 ResolutionPlan — unified introspection

Every backend already resolves keys to bytes through different strategies.
`ResolutionPlan` makes this explicit and inspectable:

```python
@dataclass(frozen=True)
class ResolutionPlan:
    kind: str          # "blob", "sql_query", "sql_blob", "composite", ...
    backend: str       # backend name
    key: str           # resolved key
    details: dict      # backend-specific (query, table, tier chain, ...)
```

Every Store gains a `resolve()` method:

```python
# SQLQueryBackend
store.resolve("reports/daily_sales.parquet")
# → ResolutionPlan(kind="sql_query", backend="postgresql",
#      key="reports/daily_sales.parquet",
#      details={"source": "explicit", "query": "SELECT ...", "format": "parquet"})

# SQLBlobBackend
store.resolve("models/v3.pkl")
# → ResolutionPlan(kind="sql_blob", backend="sqlite",
#      key="models/v3.pkl",
#      details={"table": "remote_store_objects"})

# CompositeStore
store.resolve("sales/2024-Q1.parquet")
# → ResolutionPlan(kind="composite", backend="composite",
#      key="sales/2024-Q1.parquet",
#      details={"resolved_tier": "warm", "tried": ["hot", "warm"]})
```

This replaces the separate `resolve_query()`, `resolve_tier()`, and `explain()`
methods with one unified concept. `plan.details` carries backend-specific
information; `plan.kind` lets callers branch on strategy without `isinstance`.

**Implementation:** `Backend` gains an optional `resolve(key) → ResolutionPlan`
method with a sensible default (returns plan with `kind=backend.name`). Backends
override to add meaningful details. `Store.resolve()` delegates to the backend
and rebases the key. No ABC change required — default is backward-compatible.

### 5.2 CompositeStore (ID-120)

A composition layer above stores. A `Store` subclass (not a Backend, not an
extension) that delegates to child stores based on resolution rules.

**Construction:** `Store.__init__` requires a `Backend` instance. CompositeStore
handles this by creating an internal `_MultiplexBackend` adapter that delegates
to tier backends based on resolution rules, then passes it to
`super().__init__()`. This keeps CompositeStore as a true Store subclass
(compatible with `ext.cache`, `ext.observe`, `Store.child()`) without fragile
`__init__` overrides.

**Core, not extension.** CompositeStore composes Stores — it's a first-class
construct like `Store.child()`, not a decorator. Extensions (`ext.cache`,
`ext.observe`) wrap a single Store; CompositeStore multiplexes across several.

**Relationship to ProxyStore:** `ProxyStore(Store)` delegates to a single inner
store. CompositeStore delegates to *multiple* stores, so it does not inherit
from ProxyStore — it subclasses Store directly and overrides the same methods.
Each tier's store can independently be wrapped with `ext.cache` or `ext.observe`:

```python
composite = CompositeStore(
    tiers=[
        Tier("hot", store=observe(cached_sql_store)),
        Tier("warm", store=observe(s3_store)),
    ],
)
# The CompositeStore itself can also be wrapped:
observed = observe(composite)
```

**Write-then-read visibility caveat:** In fallthrough mode, a write goes to the
primary tier. A subsequent read tries tiers in order — if the primary tier is not
the first tier checked, or if caching hides the write, the caller may not see
their own write immediately. `resolve()` helps diagnose this. v1 keeps it simple:
writes always go to the first tier, reads try tiers in order, so write-then-read
is consistent as long as the primary tier is first.

### Architecture

```python
from remote_store import Store, CompositeStore, Tier

# Pattern-match mode:
composite = CompositeStore(
    tiers=[
        Tier("hot",     store=sql_store,     match="hot/**"),
        Tier("warm",    store=s3_store,      match="warm/**"),
        Tier("archive", store=glacier_store, match="archive/**"),
    ],
)
# Fallthrough mode (v1 default):
composite = CompositeStore(
    tiers=[
        Tier("hot",     store=sql_store),
        Tier("warm",    store=s3_store),
        Tier("archive", store=glacier_store),
    ],
)
```

### Read resolution (deterministic fallthrough)

```text
for tier in tiers:
    try:
        return tier.store.read(key)
    except NotFound:
        continue
raise NotFound
```

Deterministic: tier order defines priority. No ambiguity.

### Write semantics

- Writes go to **primary tier only** (first tier, or configurable `write_tier`)
- No cross-tier overwrite — `write()` never touches non-primary tiers
- Cross-tier migration is explicit: `composite.migrate(key, from_tier, to_tier)`
- Optional: `write_through=True` for writing to multiple tiers simultaneously

### LIST behavior

- Default: **union across all tiers**, deduplicated by key (first tier wins on conflicts)
- Stable ordering: tier priority, then alphabetical within tier
- Optional: `composite.list_files(path, tier="hot")` to scope to a single tier

### Capability model

- `READ`, `SEEKABLE_READ` → union/fallthrough across tiers
- `WRITE`, `ATOMIC_WRITE`, `MOVE`, `COPY`, `DELETE` → primary tier only (gated by primary tier's capabilities)
- `LIST`, `GLOB` → union across tiers that support them
- `METADATA` → union/fallthrough (like READ)

Since write operations target the primary tier only, CompositeStore advertises the
primary tier's write-side capabilities — not the intersection across all tiers.
This avoids unnecessarily disabling MOVE/COPY/ATOMIC_WRITE when read-only tiers
lack them.

---

## 6. Capability Profile

### SQLQueryBackend

| Capability | Supported | Notes |
|------------|-----------|-------|
| `READ` | Yes | Execute query, serialize, return bytes |
| `WRITE` | -- | Query results are read-only |
| `DELETE` | -- | Cannot delete a query |
| `LIST` | Yes | List registered query keys |
| `MOVE` | -- | — |
| `COPY` | -- | — |
| `ATOMIC_WRITE` | -- | — |
| `METADATA` | Yes | `size: int \| None` — `None` until query executes. `modified_at` from config. |
| `GLOB` | Yes | Pattern match against registered keys (not SQL) |
| `SEEKABLE_READ` | Yes | Serialize to buffer, return seekable `BytesIO` |

**`FileInfo.size` contract change** (v2 only — not needed for SQLBlobBackend):
`size: int | None` where `None` means "unknown until materialized." This is
first-class — do not fake or estimate. Callers that need size must handle `None`
(or read first, which populates the cache). SQLBlobBackend always knows the size
(`size INTEGER NOT NULL` in its schema), so this contract change is deferred to
v2 when SQLQueryBackend ships.

### SQLBlobBackend

| Capability | Supported | Notes |
|------------|-----------|-------|
| `READ` | Yes | `SELECT data FROM ... WHERE key = ?` |
| `WRITE` | Yes | `INSERT` / `UPDATE` |
| `DELETE` | Yes | `DELETE FROM ... WHERE key = ?` |
| `LIST` | Yes | `SELECT key FROM ...` with prefix filter |
| `MOVE` | Yes | `UPDATE ... SET key = ? WHERE key = ?` |
| `COPY` | Yes | `INSERT INTO ... SELECT ... FROM ... WHERE key = ?` |
| `ATOMIC_WRITE` | Yes | `write_atomic()`: single INSERT/UPDATE. `open_atomic()`: buffer in `BytesIO`, commit via INSERT on success, discard on exception (MemoryBackend pattern). |
| `METADATA` | Yes | All metadata columns available |
| `GLOB` | Yes | `LIKE` / `GLOB` (SQLite) pattern on key column |
| `SEEKABLE_READ` | Yes | `BytesIO(data)` |

---

## 7. Decisions Made & Remaining Open Questions

### Decided

| # | Question | Decision |
|---|----------|----------|
| 1 | One backend or two? | **Two**: `SQLQueryBackend` + `SQLBlobBackend`, shared `_SQLAlchemyBaseBackend` |
| 2 | Priority | **SQLBlobBackend first** (v1), SQLQueryBackend second (v2) |
| 3 | Caching | **ext.cache only** — no embedded caching in backend |
| 4 | CompositeStore scope | **Core `Store` subclass** (not ProxyStore subclass) — multiplexes, not delegates |
| 5 | FileInfo.size | **`size: int \| None`** — deferred to v2 (SQLBlobBackend always knows size) |
| 6 | SQLite specialization | **Worth it** — blobopen(), WAL, PRAGMA tuning |
| 7 | Serialization | **ResultSerializer protocol** — clean abstraction boundary |
| 8 | Strict mode | **`strict=True` default** — security-by-default, no convention fallback |
| 9 | Engine lifecycle | **Owned or borrowed** — URL string = owned, `Engine` instance = borrowed |
| 10 | Schema flexibility | **Auto-create default, introspect existing** — `create_table=False` for BYO |

### Remaining open questions

1. **Config format for key→query mapping** — Python dict? YAML file? SQLAlchemy
   `text()` objects? View-only (no custom SQL)?

2. **ADBC fast path** — Worth the dependency complexity for SQLQueryBackend? ADBC
   bypasses Python row-by-row conversion, going directly to Arrow columnar format.
   (Deferred to v3.)

3. **Partitioned queries** — `store.read("sales/2024-Q1.parquet")` where the key
   encodes a WHERE clause parameter. Config-driven or convention-driven?

4. **`FileInfo.size: int | None` ripple effects** — Deferred to v2 (SQLBlobBackend
   always knows size). Before implementing for SQLQueryBackend, audit all callers
   that assume `size` is always `int`. May need a deprecation path or type guard.

---

## 8. Prioritization & Next Steps

### v1 — Foundation
- [ ] `SQLBlobBackend` with SQLite (full Backend contract, SQLite optimizations)
- [ ] `CompositeStore` (prefix-based + fallthrough, union LIST, primary-tier writes)

### v2 — Query Materializer
- [ ] `SQLQueryBackend` (basic: explicit mappings + view fallback, `strict=True` default)
- [ ] `ResultSerializer` protocol + `ArrowSerializer` implementation
- [ ] `resolve()` → `ResolutionPlan` introspection API (unified across all backends)
- [ ] `FileInfo.size: int | None` contract change (audit ripple effects first)

### v3 — Performance & Advanced
- [ ] ADBC / ConnectorX fast path for SQLQueryBackend
- [ ] Partitioned queries (key encodes WHERE clause parameters)
- [ ] CompositeStore `write_through=True` option
- [ ] CompositeStore `migrate()` for cross-tier data movement

### Immediate next step
- [ ] Spike `SQLBlobBackend` with SQLite — validates Backend contract fit with
  minimal infrastructure. A few hundred lines of code. Separate spec after spike.

---

## 9. Key Risks

| Risk | Mitigation |
|------|------------|
| **SQLQueryBackend complexity underestimated** | Ship SQLBlobBackend first; SQLQueryBackend gets its own spec after spike |
| **CompositeStore LIST semantics unclear at scale** | v1 = simple union + dedup; document edge cases; defer optimization |
| **`FileInfo.size: int \| None` ripple effects** | Deferred to v2; SQLBlobBackend always knows size. Audit callers before v2 ships |
| **Debuggability** | `resolve()` → `ResolutionPlan` is required, not nice-to-have — unified across all backends |
| **Performance expectations** | Document blob size guidelines explicitly; `max_blob_size` guard for SQLBlobBackend |

---

## 10. Future Directions

These ideas follow naturally from the resolution model but are **not committed
work** — they are documented here so future decisions can be evaluated against
a coherent vision rather than invented ad hoc.

### Resolution algebra

CompositeStore v1 supports fallthrough (try each tier in order). The resolution
model generalizes to other composition strategies:

- **Parallel reads** — race multiple tiers, return first response (latency optimization)
- **Shadow reads** — read from primary, also read from secondary and compare (migration validation)
- **Quorum reads** — require N-of-M tiers to agree (consistency guarantee)

These are all different `ResolutionPlan` compositions. No new abstraction
needed — just new `CompositeStore` strategy options.

### Compute stores

SQLQueryBackend is a "compute store" — key → computation → bytes. SQL is one
implementation. The pattern generalizes:

- Python callable store (key → function → bytes)
- REST endpoint store (key → HTTP request → bytes)
- Spark/DuckDB store (key → query plan → bytes)

If a second compute-style backend materializes, extract a `ComputeBackend`
base. Until then, SQLQueryBackend stands alone — premature abstraction is
worse than duplication.

### Structured keys

Today keys are strings. Partitioned queries (open question #3) suggest
structured keys: `Key(path="sales/2024-Q1", format="parquet", params={"year": 2024})`.
The backend would extract params from the key to parameterize queries.

The simpler v1 path: keep keys as strings, let SQLQueryBackend parse them
against config-defined patterns. Structured keys are a v3+ consideration if
multiple backends need parameterized resolution.

### README messaging

The "key → byte resolver" framing belongs in the README when SQLAlchemy backends
ship. It retroactively explains why the capability system works — capabilities
describe available resolution strategies, not filesystem features. Current
tagline ("Write file storage code once") remains accurate but undersells the
system once it resolves queries and composes backends.

---

## 11. References

### Existing projects

- [Dagster IO Managers](https://docs.dagster.io/concepts/io-management/io-managers) — closest architectural match
- [DuckLake](https://ducklake.select/) — SQL catalog + Parquet storage at scale
- [intake-sql](https://github.com/intake/intake-sql) — YAML catalog for SQL sources
- [dlt](https://github.com/dlt-hub/dlt) — SQL source → file destination pipelines
- [Feast SQL Registry](https://docs.feast.dev/reference/registries/sql) — feature store with SQL metadata
- [aiosql](https://github.com/nackjicholson/aiosql) — named SQL queries from files
- [sqlalchemy-media](https://github.com/pylover/sqlalchemy-media) — file storage tracked by SQLAlchemy models
- [Zarr SQLiteStore](https://github.com/zarr-developers/zarr-python/issues/3319) — key-value blob store in SQLite

### Database blob storage

- [SQLite SQLAR format](https://www.sqlite.org/sqlar.html) — file archive in SQLite
- [PostgreSQL Binary Data](https://wiki.postgresql.org/wiki/BinaryFilesInDB) — BYTEA vs Large Objects
- [SQLite Blob API (Python 3.11+)](https://docs.python.org/3/library/sqlite3.html#sqlite3.Blob) — native file-like blob access
- [django-db-file-storage](https://pypi.org/project/django-db-file-storage/) — DB-backed Django file storage

### Serialization & performance

- [Arrow query result transfer](https://arrow.apache.org/blog/2025/01/10/arrow-result-transfer/) — Arrow IPC performance
- [ADBC introduction](https://arrow.apache.org/blog/2023/01/05/introducing-arrow-adbc/) — Arrow-native DB connectivity
- [ConnectorX](https://www.vldb.org/pvldb/vol15/p2994-wang.pdf) — Rust-based parallel SQL→Arrow loading
- [SQLAlchemy streaming results](https://docs.sqlalchemy.org/en/20/_modules/examples/performance/large_resultsets.html)
- [Pandas SQL chunking](https://pythonspeed.com/articles/pandas-sql-chunking/) — memory-bounded SQL reads

### Tiered storage precedent

- [Trino spooling protocol](https://www.starburst.io/blog/trino-spooling-protocol/) — query results to object storage
- [Litestream](https://litestream.io/) — SQLite replication to S3
- [Data mesh principles](https://martinfowler.com/articles/data-mesh-principles.html) — data products with output ports
