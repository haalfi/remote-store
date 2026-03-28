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

### Performance & Memory

- [ ] **ID-123 — Address laziness & memory findings from audit-005**
  Follow-up to [audit-005](audits/audit-005-laziness-memory.md) (2026-03-28).
  11 findings across High / Medium / Low. Suggested work order:

  **High (most impact):**
  - H-1/H-2: `backends/_s3_base.py` — replace `_s3fs.find()` (full dict) with
    a paginated/streaming approach in both `list_files(recursive=True)` and
    `get_folder_info`. Options: `s3fs.walk()`, manual paginated `ls()` loop, or
    AWS `list_objects_v2` with `ContinuationToken` directly.

  **Medium:**
  - M-1: `ext/cache.py` — add `max_listing_size: int | None` guard to
    `iter_children`, `list_files`, `list_folders`, `glob` — parallel to the
    existing `max_content_size` guard on `read_bytes`. Skip caching when result
    tuple would exceed the limit.
  - M-2: `ext/cache.py` — pre-flight `get_file_info` size check in `read_bytes`
    before calling `_inner.read_bytes()` when `max_content_size` is set.
  - M-3/M-4/M-5: `backends/_memory.py` — `list_files`, `list_folders`,
    `iter_children` all build full lists under `_lock` then yield outside.
    Snapshot `node.children` under lock (cheap), release lock, build/yield
    lazily. Eliminates lock contention for long-running iterations.
  - M-6: `backends/_memory.py` — `write()` double-copy: accumulate stream
    into a `bytearray` via chunked `read()` to halve peak memory.

  **Low (optional / polish):**
  - L-1: `ext/cache.py` — `MemoryCache.size()` rebuilds dict on every call;
    consider a separate `_size: int` counter maintained on set/delete.
  - L-2/L-3: `ext/batch.py` — document `list()` materialisation in public API
    docstrings; no code change required unless a streaming concurrent executor
    is added.
  - L-3: `backends/_sqlalchemy.py` — defer `sqlalchemy` import to `__init__`
    body (minor consistency issue only).

  Each fix must follow the bug-fix protocol (backlog → changelog → failing test
  → fix). Split into sub-items or a single PR depending on scope at the time.

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

- [x] **ID-119 — SQLAlchemy backends** → moved to [BACKLOG-DONE.md](BACKLOG-DONE.md)

- [ ] **ID-120 — `resolve()` → `ResolutionPlan` introspection API**
  Unified introspection across all backends. `Store.resolve(key)` returns a
  `ResolutionPlan` dataclass (`kind`, `backend`, `key`, `details`). Replaces
  ad-hoc `resolve_query()` / `resolve_tier()` / `explain()` methods.
  - [Research](research/research-sqlalchemy-backend.md#51-resolutionplan--unified-introspection)
  - Default implementation on `Backend` returns plan with `kind=backend.name`
  - SQLAlchemy + CompositeStore override with meaningful details
  - Enables principled cache keys (`hash(plan)`) and debuggability
  - Next: spec now that ID-119 validates the pattern

- [ ] **ID-121 — CompositeStore (research complete)**
  `CompositeStore(Store)` — core Store subclass (not extension) that composes
  multiple stores into one. Deterministic fallthrough resolution for reads, union
  LIST (deduplicated), writes to primary tier only.
  - [Research](research/research-sqlalchemy-backend.md#52-compositestore-id-120)
    (anchor uses historical ID-120 from research doc; now ID-121 after swap)
  - Depends on: unified `resolve()` → `ResolutionPlan` (ID-120); at least two
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
  - Depended on by: ID-083 (Dagster v2 `RemoteStoreIOManager` dispatches to
    `ParquetDatasetStore` for dataset-type assets)
  - Next: finalize RFC, write spec `042-ext-parquet.md`, implement

- [ ] **ID-083 — Dagster extension v2: ConfigurableResource + IOManagerFactory**
  Follow-up to [ID-075](BACKLOG-DONE.md#post-v0170).
  Remaining features deferred from v1:
  - `DagsterStoreResource` (`ConfigurableResource`)
  - `RemoteStoreIOManager` (`ConfigurableIOManagerFactory`) — dispatches to
    `ParquetDatasetStore` for dataset-type assets (PDS-009)
  - `teardown_after_execution()`
  - Depends on: ID-122 (`ext.parquet`)

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

