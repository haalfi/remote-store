# Development Backlog

Tracking file for prioritized work and unprioritized ideas.
Items graduate through the SDD pipeline: **Idea → Backlog → RFC/Spec → Tests → Code**.

Status legend: `[ ]` pending · `[~]` in progress · `[x]` done

---

## Backlog (Prioritized)

Active work items, ordered by priority.

*(Empty — no active prioritized work items.)*

---

## Ideas (Unprioritized)

Parking lot. Not evaluated, not committed to. Pick up when relevant.

- [ ] **ID-002 — YAML config support**
  Allow `RegistryConfig.from_yaml()` alongside the existing `from_dict()`.
  Optional dependency on `pyyaml` or `ruamel.yaml`.

- [ ] **ID-003 — Pydantic BaseSettings integration**
  Let users define backend config via Pydantic `BaseSettings` for env-var binding,
  `.env` file loading, and validation. Optional `pydantic` dependency.

- [ ] **ID-005 — Built-in `from_toml()` config loader**
  Use `tomllib` (stdlib in 3.11+, `tomli` backport for 3.10) to add
  `RegistryConfig.from_toml(path)` alongside the existing `from_dict()`.
  Eliminates boilerplate for every user who keeps config in `pyproject.toml` or a
  standalone `.toml` file.

- [ ] **ID-006 — Progress callbacks for large transfers**
  Add an optional `callback: Callable[[int], None]` parameter to `read()` and
  `write()` reporting bytes transferred. Enables progress bars (e.g. `tqdm`)
  without adding dependencies. Note: `ext.transfer` (ID-023) provides
  `on_progress` for upload/download/transfer; this item covers the lower-level
  Store API.

- [ ] **ID-008 — Checksum verification on read/write**
  Add a `verify_checksum=True` option to `read()` / `write()`. Populate
  `FileInfo.checksum` consistently across backends (S3 ETag, local SHA-256).
  Gives users data-integrity guarantees with a single flag.

- [ ] **ID-010 — Retry policy configuration**
  SFTP has hardcoded retry logic (3 attempts, 2–10 s backoff via `tenacity`).
  Expose a `RetryPolicy` dataclass in `BackendConfig.options` so users can tune
  attempts, backoff, and jitter per-backend.

- [ ] **ID-013 — Async Store / Backend API**
  Async version of `Store` and `Backend` for use in async frameworks (FastAPI,
  aiohttp, etc.). Could be a parallel `AsyncStore` class or an async mode on
  the existing `Store`. Needs design decision on whether to wrap sync backends
  with `asyncio.to_thread` or require native async backends.

- [~] **ID-018 — conda-forge publishing**
  Recipe created in `packaging/conda-forge/recipe.yaml` (v1 format,
  `noarch: python`, zero core deps, `run_constraints` for optional backends).
  CI validation via `conda-recipe.yml` workflow (rattler-build `--render-only`).
  Release checklist updated with conda version/sha256 steps (Phase 2, 3, 5).
  Remaining: fork `conda-forge/staged-recipes`, submit PR externally.

- [ ] **ID-025 — `ext.cache` — store-level caching middleware**
  Wraps a Store and caches reads, folder stats, existence checks with TTL.
  `cached = CachedStore(store, ttl=300)`. Auto-invalidates on writes.
  Reduces round-trips for read-heavy or metadata-heavy workloads.
  In-memory by default, pluggable cache backend for distributed use.

- [ ] **ID-026 — Streaming atomic writes**
  Context manager for streaming large files with atomic commit:
  `with store.open_write_atomic(key) as out: out.write(chunk)`.
  Current `write_atomic()` only accepts `bytes`, forcing callers to buffer
  entire files in memory. Needed for any large-file workflow (Parquet exports,
  log rotation, report generation). Needs temp-path strategy per backend.

- [ ] **ID-034 — Parquet lake guide (Bronze / Silver / Gold patterns)**
  User-facing guide showing how to use `Store.child()` + `ext.arrow` +
  `ext.transfer` to build a multi-layer Parquet lake on any backend.
  Patterns: Bronze (raw ingestion), Silver (cleaned/typed), Gold (aggregated).
  Example with Pandas/Polars reading and writing Parquet via `pyarrow_fs()`.
  No new code needed — purely documents existing capabilities.

- [ ] **ID-035 — Parallel batch operations**
  Add `concurrent=True` (or `max_workers=N`) option to `ext.batch` functions
  (`batch_delete`, `batch_copy`, `batch_exists`). Cloud backends benefit
  significantly from concurrent I/O — sequential execution over hundreds of
  partition files is a bottleneck. Use `concurrent.futures.ThreadPoolExecutor`
  (stdlib). Needs spec update to `016-ext-batch.md`. Related: ID-013 (async).

- [ ] **ID-036 — Hive-style partition path helpers**
  Thin utility for building and parsing Hive partition paths
  (e.g., `year=2026/month=03/day=01/data.parquet`). Could live in `ext/` or
  as a helper on `Store`. Scope: `partition_path(key, **parts) -> str` and
  `parse_partition(path) -> dict`. Useful for Parquet lake workloads alongside
  PyArrow datasets. No external dependencies.

- [ ] **ID-038 — Re-run comparative benchmarks post-cache-invalidation fix**
  Listing numbers in `benchmarks/results/comparative.md` pre-date the ID-032
  cache-invalidation fix (`invalidate_cache()` on `BenchTarget`). Re-run all
  benchmark tiers with Docker backends to produce accurate baseline data.
  64KB write values for S3-PyArrow and Azure are also outlier-skewed.

- [ ] **ID-037 — PyArrow adapter Phase 2 — Tier 1 native fast-path reads**
  Complete the deferred Phase 2 work from ID-016: `Store.native_path()`,
  `Backend.native_path()`, Tier 1 native fast-path reads (PA-010) bypassing
  Python I/O for data-path operations. Critical for large Parquet workloads
  where GIL contention in `PythonFile` limits throughput. See spec
  `014-pyarrow-filesystem-adapter.md` Phase 2 sections.

---

## Done

Completed items, grouped by origin. Kept for traceability — full context
preserved to support future design decisions.

### Release blockers (v0.3.0–v0.4.1)

All v1.0 release blockers were resolved across v0.3.0–v0.4.1.

- [x] **BL-001 — PyPI publish workflow** (v0.3.0)
  Added GitHub Actions job (`publish.yml`) triggered on `v*` tags.
  Build sdist + wheel, publish via trusted publishing (OIDC).

- [x] **BL-002 — SFTP backend documentation** (v0.3.0)
  Created `docs/backends/sftp.md` (installation, usage, options, API ref).
  Updated `docs/backends/index.md` to mark SFTP as built-in, not planned.

- [x] **BL-003 — README backends table outdated** (v0.3.0)
  SFTP was listed as "Planned" but shipped in v0.2.0. Updated to "Built-in".

- [x] **BL-004 — README & project description tone rework** (v0.3.0)
  Rewrote README and pyproject description: approachable, dev-friendly,
  scannable. Practical over formal.

- [x] **BL-005 — CITATION.cff** (v0.3.0)
  Added `CITATION.cff` to repo root for GitHub's citation button.

- [x] **BL-006 — Protect master branch with ruleset** (v0.3.0)
  Ruleset "Protect master" active: require PRs (0 approvals for solo dev),
  require CI status checks (lint, typecheck, test 3.10–3.14), block force
  pushes, restrict branch deletion. Admin bypass enabled.

- [x] **BL-007 — Pin minimum dependency versions & clean up extras** (v0.3.0)
  Added minimum pins: `paramiko>=2.2` (needs `posix_rename`),
  `tenacity>=4.0` (`before_sleep_log`, `retry_if_exception_type`),
  `s3fs>=2022.1` (`clear_instance_cache`, `client_kwargs`). Removed
  `typing-extensions` (unused — Python 3.10+ covers all needs) and `adlfs`
  (no Azure backend yet at the time).

- [x] **BL-008 — Set up docs hosting** (v0.3.0)
  Pages enabled (source: GitHub Actions) at https://haalfi.github.io/remote-store/.
  Workflow `.github/workflows/docs.yml` deploys on push to master.

- [x] **BL-009 — Fix broken PyPI logo and badges** (v0.4.1)
  README logo used relative path — changed to absolute raw GitHub URL.
  Added PyPI version, Python versions, RTD, and license badges.

- [x] **BL-010 — Publish documentation to Read the Docs** (v0.4.1)
  Updated `.readthedocs.yaml` (ubuntu-24.04), pointed `Documentation` URL in
  `pyproject.toml` to `https://remote-store.readthedocs.io/`, added RTD badge.
  Docs live at https://remote-store.readthedocs.io/.

### Backlog items

- [x] **BK-001 — Azure backend** (v0.5.0)
  `AzureBackend` implemented with HNS adaptive behavior, streaming reads,
  Azurite CI, and full conformance suite. Uses `azure-storage-file-datalake`
  directly (not `adlfs`).
  → RFC: `sdd/rfcs/rfc-0001-azure-backend.md` (accepted)
  → Spec: `sdd/specs/012-azure-backend.md`

- [x] **BK-002 — Glob / pattern matching strategy** (v0.12.0)
  Three-tier design chosen (ADR-0009): (1) `list_files(pattern=…)` for universal
  fnmatch name filtering, (2) `Capability.GLOB` + `Store.glob()` for native backend
  access (like `unwrap`), (3) `ext.glob.glob_files()` for portable full-glob
  fallback. All backends (Local, S3, S3-PyArrow, Azure) now implement native glob
  with prefix-optimized listing.
  Related: ID-007.
  → Spec: `sdd/specs/018-glob.md` (GLOB-018, GLOB-019, GLOB-020)
  → ADR: `sdd/adrs/0009-glob-three-tier-design.md`

- [x] **BK-003 — Native path resolution (`to_key`)** (v0.3.0)
  Fixed the Store round-trip bug (listing returned backend-relative paths that
  included `root_path`, breaking re-use as input) and added public
  `Store.to_key(path)` / `Backend.to_key()` for converting native paths to
  store-relative keys.
  → Spec: `sdd/specs/010-native-path-resolution.md`

- [x] **BK-004 — Python 3.14 support** (v0.3.0)
  Added `3.14` to CI test matrix and `Programming Language :: Python :: 3.14`
  classifier. No code changes needed — codebase already uses
  `from __future__ import annotations` everywhere and performs no runtime
  annotation inspection, so PEP 649 is a non-issue.

### Audit findings (v0.6.0–v0.9.0)

From adversarial review of v0.5.0. Full report: `sdd/audit-001-adversarial-review.md`.

- [x] **AF-001 — Auto-register S3/SFTP/S3-PyArrow in Registry** (v0.6.0)
  `_register_builtin_backends()` only registered `local` and `azure`. Now
  registers S3, SFTP, and S3-PyArrow when their dependencies are installed.

- [x] **AF-002 — Remove GLOB/RECURSIVE_LIST ghost capabilities** (v0.6.0)
  4 backends claimed GLOB support; no `glob()` method existed. Removed
  `Capability.GLOB` and `Capability.RECURSIVE_LIST` enum members.
  BK-002 remains open for future glob design.

- [x] **AF-003 — Fix `S3Backend.close()` global cache side effect** (v0.6.0)
  `clear_instance_cache()` is a class method — new backends after the clear
  created duplicates instead of reusing. Removed the call from S3/S3-PyArrow
  `close()`.

- [x] **AF-004 — Unify `get_folder_info` on empty folders** (v0.6.0/v0.7.0)
  S3 and S3-PyArrow now return `FolderInfo(file_count=0)` when a folder exists
  but has no files (the `exists()` check gates non-existent folders). Azure
  non-HNS retains `NotFound` for `file_count==0` — correct because non-HNS
  has no concept of empty folders (they are virtual prefixes).

- [x] **AF-005 — Fix `delete_folder` error types** (v0.6.0)
  Added `DirectoryNotEmpty` error type; non-empty folder deletes now raise
  `DirectoryNotEmpty` instead of generic errors.

- [x] **AF-006 — Fix native exception leakage through lazy streams** (v0.6.0)
  Added `_ErrorMappingStream` wrapper that catches `OSError` during lazy
  reads and maps them through each backend's error classifier.

- [x] **AF-007 — Wire Azure backend into docs site** (v0.6.0)
  Azure guide added to docs navigation in `mkdocs.yml` and `generate_docs.py`.

- [x] **AF-008 — Add credential masking to backend `__repr__`** (v0.7.0)
  Added `__repr__` to all 5 backends. Sensitive fields (key, secret, password,
  pkey, account_key, sas_token, connection_string, credential) display as
  `'***'` when set and `None` when unset. Non-sensitive fields (bucket, host,
  container, etc.) shown in clear text.

- [x] **AF-009 — Fix `Registry.close()` to close all backends on error** (v0.7.0)
  `close()` now catches exceptions from individual backends, continues closing
  the rest, always runs `_backends.clear()`, and re-raises the first error.

- [x] **AF-010 — Document TOCTOU and non-atomic move limitations** (v0.9.0)
  `overwrite=False` has inherent TOCTOU (audit M-4, downgraded from High: inherent
  limitation). S3 `move()` is copy+delete (audit L-21, per spec S3-013, not a bug).
  Added `guides/concurrency.md` with full explanation, summary table, and workarounds.
  Cross-referenced from all backend guides.

- [x] **AF-011 — Remove dead `RemoteFile`/`RemoteFolder`** (v0.7.0)
  Removed class definitions from `_models.py`, imports from `__init__.py` and
  `__all__`, associated tests (MOD-006), docs entries, and spec section.
  Updated MOD-007 spec to reference only `FileInfo` and `FolderInfo`.

- [x] **AF-012 — Add capability gating tests (STORE-006)** (v0.9.0)
  Test that Store methods raise `CapabilityNotSupported` for backends missing
  capabilities (audit M-11). 14 tests covering all 12 gated methods plus
  backend-name propagation and gating-before-path-validation ordering.

- [x] **AF-013 — Add PermissionDenied/BackendUnavailable error path tests** (v0.9.0)
  S3-016, S3-017, SFTP-021, SFTP-022, SFTP-023 now tested via mock injection.
  S3: `_classify_error()` exercised for 403/accessdenied (PermissionDenied) and
  endpoint/connect/timeout/dns/name-or-service (BackendUnavailable).
  SFTP: `_map_exception()` exercised for `errno.EACCES` (PermissionDenied),
  `errno.EEXIST` (AlreadyExists), and `paramiko.SSHException` (BackendUnavailable).
  `pragma: no cover` removed from tested paths. LocalBackend paths covered in
  `test_coverage_gaps.py`.

- [x] **AF-014 — Add CI gate to publish workflow** (v0.9.0)
  Added inline `ci` job (lint + typecheck + test on Python 3.10 + 3.13)
  as a prerequisite for `build`, which `publish` already depends on.
  Subsumes into ID-028 if that ships first.

- [x] **AF-015 — Update stale v0.5.0 docs** (v0.7.0)
  L-1 (README `azure-storage-file-datalake`), L-2 (SECURITY.md), L-3
  (CONTRIBUTING.md spec 012), L-4 (Azure config example), L-5 (`[Unreleased]`
  section in CHANGELOG).

### Ideas shipped

- [x] **ID-001 — Cross-store transfer** *(subsumed by ID-023 `ext.transfer`)* (v0.9.0)
  Shipped as `transfer()` in `ext.transfer`. See spec `017-ext-transfer.md`.

- [x] **ID-004 — Structured logging & metrics hooks** (unreleased)
  Superseded by ID-024 (`ext.observe`). Intrinsic stdlib logging added to all
  modules: `NullHandler`, `log = logging.getLogger(__name__)`, `%`-style with
  `extra={}`. DEBUG for method entry, INFO for write/delete/move/copy completion.

- [x] **ID-007 — `Store.glob()` surface API** (v0.12.0)
  Three-tier pattern matching: `list_files(pattern=…)` for universal name filtering,
  `Store.glob(pattern)` for native backend glob (capability-gated on `GLOB`),
  `ext.glob.glob_files()` for portable full-glob fallback. All backends (Local, S3,
  S3-PyArrow, Azure) now implement native glob with prefix-optimized listing.
  → Spec: `sdd/specs/018-glob.md` (GLOB-018, GLOB-019, GLOB-020)
  → ADR: `sdd/adrs/0009-glob-three-tier-design.md`

- [x] **ID-009 — `Store.upload()` / `Store.download()` convenience methods** *(subsumed by ID-023 `ext.transfer`)* (v0.9.0)
  Shipped as `upload()` and `download()` in `ext.transfer`. See spec `017-ext-transfer.md`.

- [x] **ID-011 — Python 3.14 support** (v0.3.0) → graduated to BK-004

- [x] **ID-012 — Performance benchmarks** (v0.5.0)
  Benchmark suite with Docker-hosted backends: throughput, TTFB, memory,
  large-file, listing, metadata, and destructive operation scenarios.

- [x] **ID-014 — Streaming conformance tests** (v0.4.4)
  `TestStreamingConformance` in `test_conformance.py`: 5 tests × 4 backends.
  Spec: SIO-001, SIO-003.

- [x] **ID-015 — Audit external deep links** (v0.9.0)
  Swept all RTD, GitHub Pages, and GitHub links. All 3 RTD deep links
  in README already have `/en/latest/` prefix. Base-URL-only references
  (CITATION.cff, pyproject.toml, mkdocs.yml, etc.) auto-redirect and
  need no prefix. No broken or stale links found.

- [x] **ID-016 — PyArrow FileSystemHandler adapter (Phase 1)** (v0.9.0, PR #55)
  `StoreFileSystemHandler` in `ext/arrow.py` wraps any Store into a
  `pyarrow.fs.PyFileSystem`. Tier 2/3 reads, `_StoreSink` write buffer,
  `pyarrow_fs()` factory, `Store.unwrap()` delegation, error mapping
  (PA-019/020), conditional top-level export, 89 tests (`test_arrow.py`)
  + 2 `Store.unwrap()` tests (`test_store.py`), user guide, example, CI.
  → RFC: `sdd/rfcs/rfc-0002-pyarrow-filesystem-adapter.md`
  → Spec: `sdd/specs/014-pyarrow-filesystem-adapter.md`
  Phase 2 remaining: `Store.native_path()`, `Backend.native_path()`,
  Tier 1 native fast-path reads (PA-010), streaming error-mapping wrapper,
  double-RPC optimization in `open_input_file`.

- [x] **ID-017 — Memory backend** (v0.7.0)
  Tree-indexed in-memory backend. Zero dependencies, no filesystem access.
  Supports all 8 capabilities, full conformance suite with zero skips.
  Registered as `"memory"` type unconditionally. Store test fixtures migrated
  from `LocalBackend` + `tempfile` to `MemoryBackend`.
  Done: implementation, registry, conformance wiring, Store fixture migration,
  guide, docs nav, example, CHANGELOG, README.

- [x] **ID-019 — Update stale CAP-001 in spec 003** (v0.9.0)
  Removed `GLOB` and `RECURSIVE_LIST` from capability lists in specs
  003 (CAP-001), 008 (S3-003), 009 (SFTP-003), 011 (S3PA-003),
  012 (AZ-003) and backend guides (SFTP, Azure). These enum members
  were removed in v0.6.0 (AF-002) but the specs/guides were never updated.

- [x] **ID-020 — Benchmark tiered modes and single-backend filtering** (v0.10.0)
  Replaced binary slow/not-slow with three tiers (quick/standard/full).
  `--backend` CLI filter deselects tests (avoids fixture setup). `--bench-timeout`
  watchdog (Windows-compatible via `threading.Timer`). `report.py` gains
  `--comparative` and `--markdown` modes for remote-store vs raw SDK vs fsspec
  tables. Updated hatch scripts (14 bench-* commands). Comparative results
  integrated into docs site. No spec needed (ops/tooling change).

- [x] **ID-021 — `Store.child(subpath)` — runtime sub-scoping** (v0.8.0)
  Return a new Store scoped to a subfolder without recreating backend/registry.
  Child shares the parent's backend (identity); `child.close()` does not close
  the shared backend. Validated via RemotePath, chainable, equality-transparent.
  → Spec: `sdd/specs/015-store-child.md`

- [x] **ID-022 — `ext.batch` — batch operations** (v0.9.0)
  `batch_delete`, `batch_copy`, `batch_exists` convenience functions for
  operating on collections of paths. Sequential execution with error
  aggregation via `BatchResult`. Pure Python, no extra dependencies,
  unconditional top-level export.
  → Spec: `sdd/specs/016-ext-batch.md`

- [x] **ID-023 — `ext.transfer` — cross-store and local-path transfers** (v0.9.0)
  `upload`, `download`, `transfer` in `ext/transfer.py`. Streaming, `on_progress`
  callback, `overwrite` flag. Unconditional top-level export. Spec: `017-ext-transfer.md`.
  Resume support deferred.

- [x] **ID-024 — `ext.observe` — hooks / middleware / instrumentation** (unreleased)
  All three layers shipped: Layer 1 (intrinsic logging), Layer 2 (`ext.observe`
  callback hooks), Layer 3 (`ext.otel` OpenTelemetry bridge). `otel_observe()`
  wraps Store with OTel spans and metrics. Optional extra `otel` depends on
  `opentelemetry-api>=1.28.0`. ADR-0010, spec `019-ext-observe.md` (OBS-001
  through OBS-014). Supersedes ID-004.

- [x] **ID-027 — Extension architecture (`ext.*` namespace)** (v0.10.0)
  Formalized the `remote_store.ext` contract: ADR-0008 (extension rules),
  expanded CONTRIBUTING.md checklist, `ext/__init__.py` contract docstring,
  extensions guide, CLAUDE-REFERENCE.md ripple-check row. Entry-point plugin
  discovery deferred until third-party extensions emerge.

- [x] **ID-028 — Release-triggered publish and docs deploy** (v0.10.0)
  Change `publish.yml` and `docs.yml` to trigger on `release: published`
  instead of `v*` tag push / master push. The GitHub Release becomes the
  single trigger for all release automation: PyPI publish, GitHub Pages
  deploy, and RTD build. Subsumes AF-014: the release-triggered workflow
  must include an explicit CI gate (`needs: ci` or equivalent) since the
  `release: published` event does not verify CI status on its own.

- [x] **ID-029 — Versioned documentation (mike + RTD tags)** (v0.10.0)
  Add version-aware docs so readers know which release they are viewing.
  GitHub Pages: use `mike` (MkDocs Material's versioning tool) to deploy
  each release as a versioned subdirectory with a version switcher dropdown.
  RTD: configure tag-based builds so each release tag gets its own version.
  Keep a `dev` / `latest` alias tracking master for unreleased changes.

- [x] **ID-030 — Claude Code reusable skills** (v0.8.0)
  Create `.claude/commands/` slash-command skills to standardize and speed up
  recurring workflows: ripple-check, release, add-backend, backlog-sync,
  pr-preflight, add-spec. Addresses top systemic issues: backlog drift
  (7/9 AF commits forgot backlog), CHANGELOG skipped (62% of code changes),
  and version-file sync misses.
  Done: Added 6 skills in `.claude/commands/`.

- [x] **ID-031 — S3-PyArrow read path optimization** (v0.10.0)
  Drop `BufferedReader` from `S3PyArrowBackend.read()`, add `read()` + chunked
  `readline()` to `_PyArrowBinaryIO`. Eliminates double-copy per chunk on
  streaming reads (56% peak memory overhead in benchmarks). Non-breaking,
  S3-PyArrow only.
  → RFC: `sdd/rfcs/rfc-0003-s3-pyarrow-read-optimization.md`
  PR #66 (code), PR #67 (review fixes: seek guard, __next__ bypass, bytes()
  copy removal, 9 edge-case tests, RFC status -> Implemented, RawIOBase
  cross-backend note, BACKLOG update, chunk-boundary test).

- [x] **ID-032 — Fix listing benchmark fixture caching** (v0.12.0)
  Added `invalidate_cache()` to `BenchTarget` protocol and all fsspec targets
  (S3fsTarget, AdlfsTarget, SshfsTarget) + `RemoteStoreTarget`. Called after
  fixture population in listing tests so benchmarks measure real I/O, not
  cached results from the write phase.

- [x] **ID-033 — Cloud benchmark quick tier timing budget** (v0.12.0)
  Moved 1000-file listing test (`TestListPerformanceLarge`) from quick to
  `@pytest.mark.standard` tier. Updated README with per-tier cloud timing
  estimates (~5 min quick, ~15 min standard, ~60+ min full).

### Other completed work

- [x] **DONE-005 — Reorganize examples into core + backends groups** (v0.8.0)
  Moved 4 cloud backend scripts (S3, S3-PyArrow, SFTP, Azure) into
  `examples/backends/`. README, CI, docs, and CLAUDE-REFERENCE updated
  to reflect the grouped structure. CI examples job now covers all 8
  core scripts (memory_backend and store_child were missing). Added
  docs page for memory-backend example.

- [x] **DONE-001 — PEP 604 type hints**
  All source uses `X | Y` with `from __future__ import annotations`. mypy
  strict mode enforced in CI. No action needed.

- [x] **DONE-004 — S3-PyArrow hybrid backend** (v0.4.0)
  Hybrid S3 backend using PyArrow's C++ S3 filesystem for data-path operations
  (read, write, copy) and s3fs for control-path operations (listing, metadata,
  deletion). Drop-in alternative to S3Backend with the same constructor
  signature. New optional extra: `s3-pyarrow`.
  → Spec: `sdd/specs/011-s3-pyarrow-backend.md`
