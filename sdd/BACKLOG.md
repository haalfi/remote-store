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

## Known Bugs

*(none)*

---

## Ideas

### Integrations

- [~] **ID-103 — Benchmark suite v2: user-decision framing**
  Expand Toxiproxy to all Docker backends, generate overhead charts,
  reframe performance guide for user decisions, add README performance
  section.
  - [x] [Research](research/research-benchmark-suite-v2.md) (PR #263)
  - [x] Phase 1: Toxiproxy expansion (docker-compose, fixtures, profiles)
  - [x] Phase 2: Chart generation + "worth it?" verdicts in reporting
  - [x] Phase 3: README section + performance guide reframe
  - [x] Phase 4: seekable_read() + cache hit/miss benchmarks

- [~] **ID-102 — Azure PyArrow column pruning via seekable range reads**
  Enable column pruning for Parquet/PyArrow workloads on Azure via a seekable
  range reader backed by `download_blob(offset=, length=)`, exposed through a
  separate path alongside the existing chunked-streaming `read()`. The existing
  Tier 3 path in `ext/arrow.py` wraps seekable streams in `pa.PythonFile`,
  which exposes `read_at(nbytes, offset)` — giving PyArrow's Parquet reader
  byte-range access without a new backend class.
  - Done: [research](research/research-azure-pyarrow-optimization.md).
  - Remaining:
    - Phase 1: `_AzureRangeReader` with dual-mode integration (~150–200
      LOC) + PoC measuring bytes transferred / time / memory vs Tier 2.
    - Phase 2: benchmark on real workloads (Parquet column pruning, dataset
      scans, Dagster). Decide if `PythonFile` overhead is acceptable.
    - Phase 3 (only if Phase 2 shows need): spike
      `pyarrow.fs.AzureFileSystem` (C++ Tier 1) for GIL-free I/O coalescing.
    - Phase 4 (only if Phase 3 viable): `AzurePyArrowBackend` following
      `S3PyArrowBackend` pattern, spec, tests, docs.

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

