# Development Backlog

Active work items and ideas. Completed items live in
[BACKLOG-DONE.md](BACKLOG-DONE.md).

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

## How this file works

**Status legend:** `[ ]` pending · `[~]` in progress · `[x]` done

**Ordering:** newest first within each section.

**Completing work:**

- Fully done → move to `BACKLOG-DONE.md` (same commit as the code change).
- Partially done → split: ship the done part to `BACKLOG-DONE.md` under its
  original ID, create a new ID here for the remaining work, and link both.

**ID prefixes:**

| Prefix | Meaning |
|--------|---------|
| `BL-NNN` | Release blocker — must resolve before next PyPI publish. |
| `BK-NNN` | Committed backlog work, queued behind blockers. |
| `BUG-NNN` | Confirmed defect with reproduction steps. |
| `ID-NNN` | Idea — not evaluated, not committed to. |

---

## Release Blockers

*(none)*

---

## Backlog (Prioritized)

### Developer Tooling

- [ ] **BK-016 — Eliminate avoidable `# type: ignore` comments in src/**
  ~9 `type: ignore` comments can likely be removed with better typing:
  - `ext/cache.py` (6× `no-any-return`): cache `get()` returns `object`;
    narrowing with `TypeVar` or `@overload` could eliminate the ignores.
  - `_stream.py` (3× `no-any-return`): `RawIOBase.readinto`/`read`/`readline`
    return `T | None`; explicit `None` guards or `assert` could replace ignores.
  - `_path.py:21` (`misc`): `Final[str]` on a frozen-style class; may be
    resolvable with a different typing pattern.
  Not in scope: `import-untyped` (untyped third-party libs) and `override`
  (intentional `RawIOBase` signature narrowing) — those are genuinely needed.

---

## Ideas

### API Surface Enhancements

### S3 Backend DX & Performance

- [ ] **ID-114 — PyArrow-style bucket path support (research)**
  PyArrow convention: `"bucket/prefix"` embeds bucket in path. Current
  `S3Backend` requires split (`bucket=...`, `path=...`). Research feasibility
  of factory method or native convention for easier PyArrow→remote-store
  migration.
  - Deliverable: RFC only — low commitment, no code change guaranteed

### S3 & Azure Configuration

- [ ] **ID-118b — TLS CA bundle for Azure (Phase 2)**
  Extend `tls_ca_bundle` to `AzureBackend` if demand materializes.
  Primarily benefits Azure Stack Hub / on-premises deployments.
  Wrap `ClientOptions(ca_cert=...)`, check `AZURE_CA_CERTIFICATE_PATH`.
  S3 Phase 1 shipped — see BACKLOG-DONE.md.

### New Backends

- [ ] **ID-121 — `resolve()` → `ResolutionPlan` introspection API**
  Unified introspection across all backends. `Store.resolve(key)` returns a
  `ResolutionPlan` dataclass (`kind`, `backend`, `key`, `details`). Replaces
  ad-hoc `resolve_query()` / `resolve_tier()` / `explain()` methods.
  - [Research](research/research-sqlalchemy-backend.md#51-resolutionplan--unified-introspection)
  - Default implementation on `Backend` returns plan with `kind=backend.name`
  - SQLAlchemy + CompositeStore override with meaningful details
  - Enables principled cache keys (`hash(plan)`) and debuggability
  - Next: spec after ID-119 spike validates the pattern

- [~] **ID-119 — SQLAlchemy backends (research complete, v1 in progress)**
  Two concrete backends sharing `_SQLAlchemyBaseBackend`:
  - `SQLBlobBackend` (v1) — KV blob store, `(key TEXT PK, data BLOB, ...)`,
    full read-write. SQLite specialization (blobopen, WAL, PRAGMA tuning).
  - `SQLQueryBackend` (v2) — read-only query materializer, maps path keys to SQL
    queries via `ResultSerializer` protocol, extension-based output format.
  - [Research](research/research-sqlalchemy-backend.md)
  - Dependencies: `sqlalchemy` (required), `pyarrow` (SQLQueryBackend), `adbc` (v3)
  - Next: spike `SQLBlobBackend` with SQLite, then draft spec

- [ ] **ID-120 — CompositeStore (research complete)**
  `CompositeStore(Store)` — core Store subclass (not extension) that composes
  multiple stores into one. Deterministic fallthrough resolution for reads, union
  LIST (deduplicated), writes to primary tier only.
  - [Research](research/research-sqlalchemy-backend.md#52-compositestore-id-120)
  - Depends on: unified `resolve()` → `ResolutionPlan` (ID-121); at least two
    working backends to be useful; pairs well with ID-119
  - Next: design as separate spec — backend-agnostic, useful independently

### Integrations

- [ ] **ID-105 — AzurePyArrowBackend (C++ Tier 1)**
  Optional upgrade from the Tier 3 range reader shipped in
  [ID-102](BACKLOG-DONE.md#streaming--io). Only worth pursuing if real-Azure
  benchmarks show GIL overhead or missing I/O coalescing matters for target
  workloads. Approach: `pyarrow.fs.AzureFileSystem` (C++, ships with PyArrow)
  following the `S3PyArrowBackend` dual-library pattern.
  [Research § 6](research/research-azure-pyarrow-optimization.md#6-full-tier-1-path-if-needed).
  - Spike: validate auth methods, HNS/non-HNS, `ReadRangeCache` activation.
  - If viable: `AzurePyArrowBackend` — spec, tests, docs.

- [~] **ID-018 — conda-forge publishing**
  Recipe, CI validation, release checklist steps all done.
  - Done: [recipe](../packaging/conda-forge/recipe.yaml),
    [conda-recipe workflow](../.github/workflows/conda-recipe.yml),
    staged-recipes PR `conda-forge/staged-recipes#32401` (CI green).
  - Blocked: waiting for conda-forge reviewer approval. When merged: add
    `conda install -c conda-forge remote-store` to README.

- [~] **ID-013 — Async Store / Backend API**
  Async version of Store and Backend for async frameworks (FastAPI, aiohttp).
  - Done: [research](research/research-async-store-api.md),
    [ADR-0012](adrs/0012-async-store-backend-api.md) draft,
    [spec 029](specs/029-async-store-backend-api.md) draft.
  - Remaining:
    - **Second research round** (required before implementation):
      sync API has evolved significantly since initial research; async
      would nearly double codebase, package surface, and docs; unclear
      if target audience (citizen developers) benefits; unclear if
      sync + async belong in the same package.
    - Spec 029 amendments: add `SyncBackendAdapter` streaming write
      conversion (materialize `AsyncIterator[bytes]` → `bytes`), add
      `AsyncMemoryBackend` section (ASYNC-060..063), add explicit
      `open_atomic` deferral note, add `check_health()` / `ping()`
      async equivalents.
    - Implementation Phase 1: core async surface.
    - Implementation Phase 2: native async backends.
    - Implementation Phase 3: async extensions.

- [ ] **ID-122 — Parquet Dataset Storage extension (`ext.parquet`)**
  `ParquetDatasetStore` — high-level Parquet dataset read/write with manifests,
  `_SUCCESS` markers, and atomic-commit semantics. Composes `Store`, `ext.arrow`,
  and `ext.partition`.
  - [RFC-0008](rfcs/rfc-0008-parquet-dataset-storage.md) (Draft)
  - Next: finalize RFC, write spec `041-ext-parquet.md`, implement

- [ ] **ID-083 — Dagster extension v2: ConfigurableResource + IOManagerFactory**
  Follow-up to [ID-075](BACKLOG-DONE.md#post-v0170).
  Remaining features deferred from v1:
  - `DagsterStoreResource` (`ConfigurableResource`)
  - `RemoteStoreIOManager` (`ConfigurableIOManagerFactory`)
  - `teardown_after_execution()`

  [Research](research/research-dagster-extension.md),
  [showcase architecture](research/research-medallion-dagster-showcase.md).

### Documentation & Developer Experience

- [ ] **ID-066 — PR preview deployments**
  Deploy PR previews to Cloudflare Pages, Netlify, or GitHub Pages artifacts.
  Inspired by FastAPI's Cloudflare Pages pattern. Infrastructure decision needed.
  [Research](research/research-fastapi-docs.md) P6.

- [ ] **ID-067 — griffe-typingdoc for `Annotated[T, Doc("...")]` docstrings**
  Only relevant if migrating from Google-style docstrings to PEP 727
  `Annotated[T, Doc("...")]`. Not recommended near-term.
  [Research](research/research-fastapi-docs.md) P5.

