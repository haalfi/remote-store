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

*(none)*

---

## Ideas

### API Surface Enhancements

- [ ] **ID-107a — `ext.listing.list_files_deep()` extension helper (Phase 1)**
  Portable depth-limited file listing via `store.list_files(recursive=True)`
  + client-side depth filtering. Spec, tests, exports, docs.
  - Semantics: depth 0 = only items in `path` itself; depth 1 = items + direct children
  - Implementation: extension helper wrapping `list_files()`, **not** a Backend
    ABC parameter — preserves slim core interface
  - [Research](research/research-depth-limited-listing.md) §6 Phase 1.
  - Supersedes ID-107.

- [ ] **ID-107b — `Store.list_files(max_depth=N)` + backend optimization (Phase 2)**
  Add `max_depth` parameter to `Store.list_files()` and `Backend.list_files()`.
  Implement native depth limiting in Local (`os.walk()`), SFTP (recursive call
  depth tracking), Memory (DFS stack depth). S3/Azure: client-side filter (flat
  scan is often optimal). Update `ext.listing.list_files_deep()` to delegate.
  - Depends on: ID-107a.
  - [Research](research/research-depth-limited-listing.md) §6 Phase 2.

- [ ] **ID-108a — `ext.listing.list_folders_deep()` extension helper (Phase 1)**
  Portable depth-limited folder listing via BFS over `store.list_folders()`.
  Spec, tests, exports, docs.
  - Semantics: depth 0 = immediate children; depth N = N levels of nesting
  - Note: aggregate stats already available via `get_folder_info()` per folder
    (returns `FolderInfo(file_count, total_size, modified_at)`)
  - [Research](research/research-depth-limited-listing.md) §6 Phase 1.
  - Supersedes ID-108.

- [ ] **ID-108b — `Store.list_folders(depth=N)` Store-level BFS (Phase 2)**
  Add `depth` parameter to `Store.list_folders()`. Implement BFS traversal at
  Store level (no backend ABC change needed for folders). Update
  `ext.listing.list_folders_deep()` to delegate.
  - Depends on: ID-108a.
  - [Research](research/research-depth-limited-listing.md) §6 Phase 2.

### S3 Backend DX & Performance

- [ ] **ID-112 — Non-recursive `get_folder_info` optimization**
  Current `get_folder_info()` uses `s3fs.find()` for full recursive traversal.
  For bucket-wide aggregation, this rescans the same objects repeatedly
  (catastrophic for 250k+ files). A non-recursive mode using cheap `ls()`
  for direct-children stats only would avoid this.
  - Implementation: Store-level helper using `list_files()` / `list_folders()`,
    consistent with ID-107/108 extension-helper pattern — no ABC change

- [ ] **ID-113 — Documentation: S3 listing strategies and performance**
  One flat `ListObjectsV2` stream beats O(n_folders) delimiter-based `ls()`
  calls. Parallelize-BFS instinct is wrong for large buckets. Add performance
  guide section with examples and benchmark data.
  - Scope: docs + examples; no code change

- [ ] **ID-114 — PyArrow-style bucket path support (research)**
  PyArrow convention: `"bucket/prefix"` embeds bucket in path. Current
  `S3Backend` requires split (`bucket=...`, `path=...`). Research feasibility
  of factory method or native convention for easier PyArrow→remote-store
  migration.
  - Deliverable: RFC only — low commitment, no code change guaranteed

### S3 & Azure Configuration

- [ ] **ID-117 — S3Backend endpoint URL normalization**
  Accept bare `host:port` formats (e.g., `"localhost:9000"`) and auto-normalize
  to `https://host:port`. Reduces migration friction from PyArrow's
  `endpoint_override` which accepted bare endpoints. URLs with existing schemes
  returned unchanged.
  - S3Backend-specific — no ABC impact

- [ ] **ID-118 — Certificate bundle handling (S3 + Azure)**
  **Phase 1 (S3):** Dedicated `tls_ca_bundle: str | None` parameter replacing
  nested `client_options={"client_kwargs": {"verify": path}}`. Auto-read
  `AWS_CA_BUNDLE` env var (aligns with boto3 standard). Early path validation
  at construction time with clear `ValueError` if cert file missing.
  - Env vars: `AWS_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`
  - For S3PyArrowBackend: respect `SSL_CERT_FILE` (PyArrow's `tls_ca_file_path`)
  - **Phase 2 (Azure):** Extend to AzureBackend if demand materializes.
    Primarily benefits Azure Stack Hub / on-premises deployments.
    Wrap `ClientOptions(ca_cert=...)`, check `AZURE_CA_CERTIFICATE_PATH`.

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

