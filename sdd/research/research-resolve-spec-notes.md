# Resolve Specification — Research Notes (Condensed)

Working document: extracted key points from each source, to be synthesized into
a final spec proposal in Pass 2.

---

## Source 1: BACKLOG.md — ID-120 & ID-121

**ID-120 — `resolve()` -> `ResolutionPlan` introspection API**
- Unified introspection across all backends
- `Store.resolve(key)` returns `ResolutionPlan` dataclass (`kind`, `backend`, `key`, `details`)
- Replaces ad-hoc `resolve_query()` / `resolve_tier()` / `explain()` methods
- Default implementation on `Backend` returns plan with `kind=backend.name`
- SQLAlchemy + CompositeStore override with meaningful details
- Enables principled cache keys (`hash(plan)`) and debuggability

**ID-121 — CompositeStore**
- `CompositeStore(Store)` — core Store subclass composing multiple stores
- Deterministic fallthrough resolution for reads
- Union LIST (deduplicated), writes to primary tier only
- Depends on unified `resolve()` (ID-120)

---

## Source 2: research-sqlalchemy-backend.md § 1, 5, 10

### Core Insight: Key -> Byte Resolution Model
- A Store is a **deterministic key -> byte resolver** — not storage, not filesystem
- Every backend is a resolution strategy:
  - LocalBackend: key -> filesystem path -> bytes
  - S3Backend: key -> S3 object -> bytes
  - ReadOnlyHttpBackend: key -> URL -> bytes
  - SQLBlobBackend: key -> row lookup -> bytes
  - SQLQueryBackend: key -> query execution -> serialized bytes
  - CompositeStore: key -> (try hot, warm, cold) -> bytes

### ResolutionPlan Dataclass
```python
@dataclass(frozen=True)
class ResolutionPlan:
    kind: str          # "blob", "sql_query", "sql_blob", "composite", ...
    backend: str       # backend name
    key: str           # resolved key
    details: dict      # backend-specific
```

### Backend.resolve() — Default + Override Pattern
- `Backend` gains optional `resolve(key) -> ResolutionPlan` with default (`kind=backend.name`)
- Backends override to add meaningful details
- `Store.resolve()` delegates to backend, rebases the key
- No ABC change required — backward-compatible default

### CompositeStore Architecture
- True `Store` subclass (not Backend, not extension)
- Internal `_MultiplexBackend` adapter delegates to tier backends
- Compatible with `ext.cache`, `ext.observe`, `Store.child()`
- Two modes: **fallthrough** (try each tier in order) and **pattern-match** (`match="hot/**"`)
- Write: primary tier only (first tier, or configurable `write_tier`)
- List: union across all tiers, deduplicated by key (first tier wins)
- Capabilities: write-side from primary tier, read-side union/fallthrough

### Resolution Algebra (Future)
- Parallel reads (race tiers, return first)
- Shadow reads (primary + secondary compare for migration validation)
- Quorum reads (N-of-M agreement)
- All expressible as `ResolutionPlan` compositions

### Compute Stores (Future)
- SQLQueryBackend = "compute store" (key -> computation -> bytes)
- Generalizes to: Python callable, REST endpoint, Spark/DuckDB
- Extract `ComputeBackend` only if a second compute-style backend emerges

### Structured Keys (Future)
- Today: keys are strings
- Future: `Key(path=..., format=..., params=...)` for parameterized resolution
- v1: keep strings, let backends parse against config-defined patterns

---

## Source 3: research-store-middleware-architecture.md

**No direct resolve/ResolutionPlan content.** Relevant delegation patterns:
- ProxyStore base class for centralized delegation (Option G)
- Middleware pipeline with ordered middleware (Option C)
- Stream-wrapper layered abstractions (Option E)
- Max composition depth: two proxy layers (observe + cache) + stream wrappers
- Recommended path: ProxyStore base + stream wrappers, avoiding premature middleware

**Relevance to resolve:** ProxyStore is for single-store wrapping; CompositeStore
multiplexes across multiple stores — different pattern, does not inherit ProxyStore.

---

## Source 4: research-store-config.md

**Registry + multi-backend composition:**
- Two-level config: `backends -> name -> {type, options}` and `stores -> name -> {backend, root_path}`
- Multiple configs per backend type (e.g., `s3-prod`, `s3-analytics`, `s3-minio-dev`)
- Multiple stores route to same backend with different root paths
- Registry resolves store requests to appropriate backend instance
- Factory pattern: `factory(**cfg.options)` — direct kwarg splat

**Credential resolution chains:**
- Delegates to underlying cloud SDK credential chains (AWS boto3, Azure DefaultAzureCredential)
- Production: omit explicit creds, rely on IAM/managed identity

**Key design decisions:**
- Single immutable config source (ADR-0002) — no runtime merging
- Config-as-code has absolute priority over env/file
- Three-tier loaders (`from_dict`, `from_toml`, `from_yaml`) all feed same model

---

## Source 5: research-store-api-refinement.md

**No resolve/ResolutionPlan/CompositeStore content.** Focuses on API surface
normalization (listing types, write/read symmetry, ordering guarantees, atomicity docs).

---

## Source 6: Remaining research files

**research-async-store-api.md:** No resolve/CompositeStore content. Notes that
backend methods are "simple delegation, not deep ORM graph" — flat architecture.
Async boundary at Backend level. Relevant: confirms resolve() should live on Backend.

**research-readonly-http-backend.md:** Shows URL resolution pattern:
- `native_path(path)` returns full URL; `to_key(native_path)` strips base prefix
- Base URL + relative path model (path appended to base_url)
- Relevant: demonstrates that each backend has its own "native resolution" which
  ResolutionPlan.details should capture (URL for HTTP, S3 URI for S3, file path
  for Local, SQL query for SQLQuery, etc.)

**research-dagster-extension.md:** IOManager adapter wraps Store. Asset key -> file
path mapping with partition support. No resolve/CompositeStore content. Relevant:
Dagster IOManager dispatches based on asset type — similar to CompositeStore's
tier-based dispatch.

---

## Source 7: Existing Source Code

**No `resolve()` or `ResolutionPlan` exists yet.** Current state:

**Backend ABC** (`_backend.py:34`):
- `native_path(path) -> str` — converts backend-relative key to native path
- `to_key(native_path) -> str` — inverse of native_path

**Per-backend native_path implementations:**
- LocalBackend: `root_str + "/" + path` (filesystem path)
- S3Backend: `bucket/path` (S3 object key)
- S3PyArrowBackend: delegates to PyArrow path
- AzureBackend: `container/path`
- SFTPBackend: `base_path/path` (POSIX remote path)
- ReadOnlyHttpBackend: `base_url + quote(path)` (full URL)

**Store** (`_store.py:30`):
- `native_path(key) -> str` — delegates to `_backend.native_path(_full_path(key))`
- `to_key(path) -> str` — inverse

**ProxyStore** (`_proxy.py`):
- `native_path(key)` — delegates to `_inner.native_path(key)`

**Key insight:** `native_path()` is already the "resolve to native representation"
primitive. `ResolutionPlan` generalizes this by adding `kind`, `backend`, and
`details` metadata alongside the resolved path.

---

## Source 8: External Prior Art (Web Research)

### Apache Iceberg — Catalog-Based Resolution
- Catalog stores pointer to current metadata file (the "resolve" entry point)
- Resolution: table name -> catalog lookup -> metadata file location -> manifest
  list -> manifest files -> data files
- REST Catalog Specification: HTTP API, language-agnostic, cloud-agnostic
- Field resolution by field ID (not column name) — schema evolution safe
- Versions 1-3 complete, v4 under development
- **Relevance to remote-store:** Iceberg's `ResolutionPlan` equivalent is the
  metadata tree (metadata -> manifest list -> manifests -> data files). Each
  layer adds detail. remote-store's `ResolutionPlan.details` serves the same
  role at a simpler level.

### Delta Lake / Unity Catalog — Name-Based Resolution
- Shift from path-based to name-based table resolution
- Clients reference by name, catalog resolves storage location
- Three-level namespace: `<catalog>.<schema>.<table>`
- Catalog-managed tables (Delta 4.1.0): catalog is coordinator and source of
  truth for table state, manages concurrency control
- Path-based access discouraged (bypasses access controls, risks corruption)
- **Relevance to remote-store:** Validates the pattern of `Store.resolve(key)`
  returning a plan rather than a raw path. The plan IS the resolved identity —
  name-to-location indirection with metadata. remote-store already has this
  with `native_path()` but ResolutionPlan adds the metadata layer.

### Apache Hudi — Timeline-Based Resolution
- Metadata table under `.hoodie/metadata` (itself a Hudi MoR table)
- Resolution: table version + metadata table -> committed data files
- Record-level metadata (metafields) for uniqueness, indexing, tracking
- Query types resolve differently: snapshot (latest), time-travel (timestamp),
  incremental (timeline walk)
- Metadata table reduces O(N) LIST to O(1) GET per partition
- **Relevance to remote-store:** Hudi's query-type-dependent resolution maps to
  CompositeStore's tier-based resolution. Different "resolution strategies" for
  the same key depending on context (hot/warm/cold vs snapshot/incremental).

### fsspec — Protocol-Based Resolution
- Registry maps protocol strings (`s3`, `file`, `http`) to filesystem classes
- `fsspec.open("s3://bucket/key")` -> protocol extraction -> registry lookup ->
  filesystem instantiation -> file-like object
- `universal_pathlib` (UPath): `pathlib.Path` API extended with fsspec backends
- Multi-backend as "filesystem proxy" — one level higher abstraction
- Acknowledged as "leaky/unwieldy" when shoehorned into filesystem interface
- **Relevance to remote-store:** fsspec resolves protocol -> class -> instance.
  remote-store resolves key -> backend -> native path. ResolutionPlan makes the
  second step inspectable (like fsspec's registry makes the first step inspectable).

### Industry Convergence Pattern (2025-2026)
- Catalog-managed tables are becoming the norm (Iceberg REST, Unity, Polaris)
- Resolution = name-to-location indirection with metadata + access control
- All major formats converge on: catalog as coordinator, not just metadata store
- The "resolve" concept is universal: every system needs key/name -> location +
  metadata + access rules
- Open standards: Iceberg REST Catalog spec, Unity Catalog OpenAPI spec

### Synthesis: What Makes a Good Resolve Specification
1. **Indirection over direct paths** — resolve returns metadata, not just location
2. **Extensible details** — each backend/format adds its own context
3. **Hashable/cacheable** — resolution results can be cache keys
4. **Composable** — composite resolution (try tier A, then B) is a first-class pattern
5. **Inspectable** — callers can branch on `kind` without `isinstance`
6. **Backward-compatible default** — backends that don't override get a sensible plan
7. **Immutable** — frozen dataclass, safe for concurrent use and hashing
