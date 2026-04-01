# Changelog

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor bumps may contain breaking changes.

## [Unreleased]

### Added

- **Async Store API (`remote_store.aio`)** (ID-013): `AsyncStore` --
  async counterpart to `Store` with coroutine methods for all operations.
  `AsyncBackend` abstract base class for native async backends.
  `SyncBackendAdapter` wraps any synchronous backend for async use
  (delegates to a thread-pool executor). `AsyncMemoryBackend` for
  async testing. Phase 1 -- core primitives.
- **`AsyncAzureBackend` native async backend** (ID-013 Phase 2): First native
  async backend for `remote_store.aio`. Uses Azure SDK async clients
  (`azure.storage.blob.aio`, `azure.storage.filedatalake.aio`) for true
  non-blocking I/O. Shared helpers extracted to `_azure_common.py` for
  sync/async code reuse. Zero new dependencies.
- `FEATURES.md` at repo root — versioned snapshot of backends, extensions,
  capabilities, and install extras for agent and human discoverability (BK-136).
- `remote_store.info()` public function — runtime introspection of available
  backends and extensions in the current environment (BK-136).
- `CLAUDE.md` now references `FEATURES.md` for cold-start agent sessions (BK-136).
- Release checklist in `CONTRIBUTING.md` now includes `FEATURES.md` update (BK-136).
- **Dagster multi-partition loading** — `load_input` now returns
  `dict[str, Any]` when the input context carries multiple partition keys
  (time-window aggregation). Applies to both the bytes-serializer IO manager
  and the dataset IO manager (ID-124, spec DAG-020).

### Changed

- **`ParquetSerializer.deserialize()` now returns a PyArrow Table** instead of
  a pandas DataFrame (BUG-135). Removes the hidden hard dependency on pandas
  for users installing `remote-store[dagster,arrow]` without pandas. Callers
  that need pandas call `table.to_pandas()` on the result. See
  [Migration Guide](migration.md#v0200-to-next).

### Documentation

- **Spec 029 amendments** (ID-013b): add round 2 §2.4 items (ASYNC-036/037,
  ASYNC-052a–e, ASYNC-057/058, ASYNC-061/062) and Phase 2 `AsyncAzureBackend`
  spec (ASYNC-070–079). Update `max_depth` on ASYNC-014/015/017, `resolve()`
  in ASYNC-034 passthrough list, and ASYNC-046 enumeration.
- Expand async guide with native backend section (`AsyncAzureBackend`),
  health check (`ping()`), and updated limitations.
- Fix CHANGELOG migration-guide link for GitHub (move `guides/migration.md`
  to repo root so `migration.md#…` resolves in both GitHub and docs).
- Fix stale pandas reference in Dagster guide — Parquet serializer
  deserializes to a PyArrow Table, not a pandas DataFrame.

### Internal

- Fix 72 `ResourceWarning: unclosed database` in SQL backend tests by adding
  proper fixture teardown and `close()` calls. Filter residual SQLAlchemy pool
  warning on Python 3.13+ (BK-135).
- Replace `isinstance`-only assertions (12 tests) and private attribute
  assertions (~15 instances) with behavioral checks (BK-134).
- Upgrade `setup-uv` from v7 to v8.0.0 (immutable tags) across all workflows.
- Disable uv caching on lightweight CI jobs to eliminate cache-contention warnings.

## [0.20.0] - 2026-03-30

### Added

- **Dagster extension v2 (`ext.dagster`)** (ID-083): `DagsterStoreResource`
  (`ConfigurableResource`) for direct Store access in assets, and
  `RemoteStoreIOManager` (`ConfigurableIOManagerFactory`) for config-driven
  IO management with automatic Store lifecycle. Dataset mode via
  `dagster_dataset_io_manager()` or `serializer="parquet-dataset"` writes
  Parquet datasets through `ParquetDatasetStore`. Spec 031 (DAG-012 -- DAG-019).

- **Parquet Dataset Storage extension (`ext.parquet`)** (ID-122):
  `ParquetDatasetStore` — high-level Parquet dataset read/write with manifest
  metadata, `_SUCCESS` completion markers, and atomic-commit semantics. Supports
  single-file and multi-part layouts, column projection on read, and
  overwrite semantics. Extension-specific errors: `DatasetIncomplete`,
  `ManifestCorrupted` (import from `remote_store.ext.parquet`). Spec 042.

- **`resolve()` introspection API** (ID-120): `Store.resolve(key)` returns a
  frozen `ResolutionPlan` dataclass describing how a key maps to its storage
  location, backend identity, and backend-specific context. Available on all
  backends with no I/O. Enables debugging ("which backend handled this key?"),
  principled cache key derivation, and future composite store composition.
  Spec 043.

- **`max_listing_size` parameter for `cache()`** (BK-123 M-1): Skips caching
  listing results (`list_files`, `list_folders`, `iter_children`, `glob`) that
  exceed the given item count. Complements the existing `max_content_size` guard
  for `read_bytes`.

- **`SQLQueryBackend` — read-only SQL query materializer** (ID-119 v2): Maps
  path keys to SQL queries and serializes results to Parquet, CSV, or Arrow
  IPC based on the key's file extension. Explicit query mappings via `queries`
  dict; `strict=True` default (view/convention discovery deferred).
  `ResultSerializer` protocol with built-in `ArrowSerializer`. New optional
  extra: `pip install remote-store[sql-query]`. Spec 041.

- **SQLBlobBackend — SQL key-value blob storage** (ID-119 v1): New
  `SQLBlobBackend` backed by SQLAlchemy. Uses a SQL table as key-value store
  with full Backend contract (all 10 capabilities). SQLite optimizations:
  WAL mode, `PRAGMA synchronous=NORMAL`. Supports owned or borrowed
  engines, custom table names, existing
  table introspection (`create_table=False`), and `max_blob_size` guard.
  Optional extra: `pip install remote-store[sql]`. Spec 040.

- **TLS CA bundle support for S3 backends** (ID-118): New `tls_ca_bundle`
  parameter on `S3Backend` and `S3PyArrowBackend` replaces nested
  `client_options={"client_kwargs": {"verify": path}}`. Falls back to
  `AWS_CA_BUNDLE` / `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` env vars.
  Early path validation at construction time. Spec 039.

- **S3 endpoint URL normalization** (ID-117): `S3Backend` and
  `S3PyArrowBackend` now accept bare `host:port` values for `endpoint_url`
  and auto-prefix them with `https://`. Reduces migration friction from
  PyArrow's `endpoint_override` which accepted bare endpoints. URLs with
  existing schemes are unchanged. Spec S3-025 / S3PA-023.

- **Non-recursive `get_folder_info`** (ID-112):
  `Store.get_folder_info(path, max_depth=N)` controls traversal depth for
  folder statistics. `max_depth=0` aggregates only direct children;
  `max_depth=N` includes files up to N levels deep. `None` (default) preserves
  the existing full-recursive backend delegation. Store-level computation
  using `list_files()`; no Backend ABC change. `CachedStore` and
  `ObservedStore` forward the parameter. Spec 038.

- **Depth-limited listing** (ID-107, ID-108): `Store.list_files(max_depth=N)`
  and `Store.list_folders(max_depth=N)` control traversal depth without
  fetching the full recursive tree. When `max_depth` is set on `list_files`,
  `recursive` is ignored. Client-side filtering at the Store level; no
  Backend ABC change. Spec 037.

- **Backend-native `max_depth` optimization** (ID-107b):
  `Backend.list_files()` now accepts optional `max_depth` kwarg. Local, SFTP,
  and Memory backends prune traversal natively, reducing filesystem and network
  I/O. S3/Azure accept the parameter but defer to Store-level client-side
  filtering. Spec 037 (DEPTH-003).

- **Azure range reader** (ID-102): `AzureBackend.read_seekable()` returns
  a seekable stream backed by `download_blob(offset=, length=)`. Each
  `read()` issues a single HTTP Range request — no full-file download.
  Enables PyArrow Tier 3 column pruning for Parquet on Azure.

- **S3-PyArrow in comparative benchmarks** (ID-104): S3-PyArrow now appears
  in overhead charts, comparative reports, and user-facing verdicts with boto3
  as its raw SDK baseline. New S3 vs S3-PyArrow comparison chart.

- **Overhead-vs-RTT chart** (ID-104): Replaces the placeholder with a real
  line chart showing how overhead % changes across network latency profiles
  (clean, rtt20, rtt50, rtt100). Raw SDK targets added for latency backends
  for apples-to-apples comparison. Network profile metadata saved in
  benchmark JSON.

- **`--file` flag for benchmark tools** (ID-104): `report.py` and `charts.py`
  accept `--file PATH` to load a specific JSON file instead of auto-detecting
  the latest.

- **Latency matrix benchmark command** (ID-104):
  `hatch run bench-latency-matrix` runs rtt20/rtt50/rtt100 profiles
  sequentially. Cross-platform Python script with configurable `--profiles`,
  `--pool-size`, `--bench-timeout`.

- **Seekable read and cache benchmarks** (ID-103 Phase 4):
  `test_seekable.py` measures `read_seekable()` cost (open+read, sequential
  chunks, random seeks) across backends with different seek strategies.
  `test_cache.py` measures CachedStore cold read (miss) vs warm read (hit)
  vs uncached baseline.

- **Benchmark charts and user-facing report** (ID-103 Phases 2--3):
  SVG chart generation (`hatch run bench-charts`) for overhead %, overhead
  vs RTT, and throughput by file size. User-facing verdict report
  (`hatch run bench-report-user`) classifying overhead as
  Negligible/Moderate/Visible/Favorable. Performance guide reframed to
  lead with the answer. README gains a Performance section.

- **Toxiproxy latency simulation for all backends** (ID-103 Phase 1):
  Toxiproxy now proxies all three network backends (MinIO, Azurite, SFTP).
  New `--network-profile` flag with named profiles (`clean`, `rtt20`,
  `rtt50`, `rtt100`). New `s3-latency` and `sftp-latency` backend params
  alongside the existing `azure-latency`.

- **ProxyStore added to API reference** (ID-101): `ProxyStore` is now exported
  from `remote_store` and documented. It remains an internal delegation base by
  design (ADR-0014) but is visible in the inheritance chain of `ObservedStore`
  and `CachedStore`, and useful for building custom Store extensions.

### Fixed

- **Publish workflow no longer runs full CI suite** (BK-132): Removed redundant
  lint/typecheck/test jobs from `publish.yml` — master branch protection already
  gates these. Publish now only builds, checks, and uploads. Fixes Python 3.10
  dependency resolution failure caused by `pytest-gremlins>=1.5` (requires 3.11+).

- **`MemoryCache.size()` no longer rebuilds dict** (BK-127 L-1): Replaced dict
  comprehension with `sum()` generator — avoids transient 2× memory spike on
  large caches. Trade-off: `size()` no longer evicts expired entries as a
  side-effect; they remain in `_data` until the next `get()`, `clear_prefix()`,
  or `clear_prefixes()` call.

- **Replaced mypy `ignore_missing_imports` overrides with proper type stubs**
  (BK-015): Removed 8 `[[tool.mypy.overrides]]` entries that suppressed
  import errors for packages shipping `py.typed` or having PyPI stubs
  (`pydantic`, `pydantic_settings`, `tomli`, `tomllib`, `ruamel.yaml`,
  `requests`, `urllib3`, `httpx`). Added `types-requests` to dev
  dependencies. Cleaned up now-unnecessary `# type: ignore` comments in
  `_http_requests.py` and `_http_httpx.py`. Mypy now sees real types
  instead of `Any` for these imports.

- **SFTP TOFU host key persistence** (BUG-005): `TRUST_ON_FIRST_USE` now
  persists accepted host keys to disk on disconnect, creating the known_hosts
  file and parent directories if absent. Inline keys (code/config/env) are
  never persisted. Spec SFTP-028.

- **Cache coherency in move/copy operations** (BUG-006): `CachedStore.move()`
  and `CachedStore.copy()` now clear the entire cache (instead of selective
  invalidation) to prevent stale cached entries for nested paths that are
  relocated or overwritten. Consistent with `delete_folder()` safety strategy.
  Spec CACHE-010 updated.

- **Snippet indentation in docs code blocks** (BUG-004): named snippet
  regions inside function bodies rendered with extra leading whitespace.
  Fixed via pymdownx.snippets `dedent_subsections` option.

### Changed

- **S3 recursive listing memory optimization** (BK-123 H-1/H-2):
  `list_files(recursive=True)` and `get_folder_info` now use paginated
  per-directory `ls()` calls instead of `find()`, reducing peak memory from
  O(total objects) to O(widest directory).

- **MemoryBackend listing lock reduction** (BK-123 M-3/M-4/M-5): `list_files`,
  `list_folders`, and `iter_children` now snapshot state under lock and build
  results lazily outside it, reducing lock contention during long iterations.

- **MemoryBackend write memory optimization** (BK-123 M-6): Stream writes
  accumulate directly into a `bytearray` via chunked reads, halving peak memory.

- **CachedStore pre-flight size check** (BK-123 M-2): `read_bytes` checks
  cached `get_file_info` size before reading to skip caching oversized files
  earlier. Zero extra backend calls.

- **Performance messaging rewrite** (ID-104): README and performance guide now
  present overhead as measured values in ms (with percentages in brackets)
  instead of judgmental language. Users see the numbers and decide for
  themselves.

- **Seekable read promoted to Store API** (ID-100, ID-102): New
  `Store.read_seekable()` method — always returns a seekable stream,
  backend-optimized. On seekable backends (Local, S3, SFTP) it's
  zero-overhead passthrough. On Azure it returns `_AzureRangeReader`
  (HTTP Range requests per read — ideal for PyArrow column pruning).
  On HTTP it spools to `SpooledTemporaryFile`. Replaces
  `ext.seekable.seekable_read()` (removed, never released).
  ADR-0017 supersedes ADR-0016. Spec 036 revised.

### Removed

- **Deprecated function aliases removed** (BK-130): `cached_store()`,
  `remote_store_io_manager()`, and `pydantic_to_registry_config()` are removed.
  Use `cache()`, `dagster_io_manager()`, and `from_pydantic()` respectively.
  The `_deprecated_alias()` helper in `ext/_helpers.py` is also removed.
  Pre-v1 — no deprecation shim needed.

### Documentation

- **Fix docs list completeness findings** (BK-129): Add SQLBlob and SQLQuery
  backends to all backend lists, tables, and matrices across 14 doc files.
  Remove ghost "Seekable read" entries from extension lists. Add missing
  extensions to architecture.md. Add `read_seekable()` directive to Store API
  reference. Add `sql` and `sql-query` extras to README installation section.

- **RFC-0008: Parquet Dataset Storage extension** (ID-122): Draft RFC proposing
  `ParquetDatasetStore` — high-level Parquet dataset read/write with manifests,
  `_SUCCESS` markers, and atomic-commit semantics on top of existing Store
  primitives.

- **S3 listing strategies and performance** (ID-113): New comprehensive guide in
  `guides/backends/s3.md` explaining shallow vs. recursive listing, why flat
  `ListObjectsV2` streams beat delimiter-based folder iteration, and why
  parallelization is wrong for large buckets. Includes performance data and
  examples showing when to use each approach. New example file
  `examples/backends/s3_listing_strategies.py` demonstrates shallow, recursive,
  and filtered listing patterns.

### Internal

- **CI test quality gates** (BK-126): AST-based assertion checker
  (`scripts/check_test_assertions.py`) and MagicMock spec checker
  (`scripts/check_mock_spec.py`) now run in CI lint job. Rules 1 and 4 from
  `sdd/TESTING.md` are machine-enforced.

- **MagicMock `spec=` migration** (BK-126): All 67 unconstrained
  `MagicMock()` calls now use `spec=` with the correct class, preventing
  mocks from silently accepting invalid attribute access.

- **Assertion migration** (BK-126): 87 test functions that lacked explicit
  `assert` or `pytest.raises` now have meaningful post-condition assertions.

- **pytest-gremlins integration** (BK-126): Added `pytest-gremlins>=1.5` for
  mutation testing. New hatch scripts: `check-test-quality`,
  `test-cov-branch` (branch coverage diagnostic). No CI threshold yet.

- **Fix mutation testing scripts** (BK-131): Replaced broken `mutate` /
  `mutate-report` scripts with 6 scoped scripts (`mutate-core-api`,
  `mutate-core-infra`, `mutate-ext-proxy`, `mutate-ext-format`,
  `mutate-backends-local`, `mutate-backends-cloud`). Original scripts passed
  source dir as positional arg instead of `--gremlin-targets`. Scoped runs
  avoid Windows command-line length limits. Added `[tool.pytest-gremlins]`
  config with incremental caching enabled.

- **Eliminate avoidable `type: ignore` comments** (BK-016): Replaced 9
  `no-any-return` suppressions with `cast()` in `ext/cache.py` (6) and
  `_stream.py` (3). 1 `misc` in `_path.py` kept (mypy `Final` on `__slots__`
  limitation).

- Document `list()` materialisation in concurrent batch helpers (BK-127 L-2).
- Clarify module-level sqlalchemy import rationale (BK-127 L-3).

- **Ruff PT rules enabled** (BK-124b): `flake8-pytest-style` enforced in
  `pyproject.toml`. 152 auto-fixed, 13 `match=` added to `pytest.raises`,
  9 intentional PT012 suppressed. Ruff PT section in TESTING.md marked enabled.

- **Multi-agent orchestration skill** (BK-125): `/orchestrate` skill delegating
  to 4 domain experts (Store & Backend, Extension, Testing, Documentation) via
  Claude Code Agent tool. Two modes: implementation and review. ADR-0019
  documents the architecture decision.

- **Orchestrate v2: iterative convergence model** (BK-128): Redesigned
  `/orchestrate` from single-pass parallel to iterative convergence with three
  complexity modes (Simple, Standard, Complex). Adds plan refinement with
  experts (1 round), consolidation step, review loop (max 2 rounds), and
  user as tie-breaker. ADR-0020 supersedes ADR-0019.

- **Testing standards guide** (BK-124a): New `sdd/TESTING.md` codifying 8 test
  quality rules from research-testing-best-practices. Companion to DESIGN.md
  § 11 (style). Includes Testing Expert quick reference for BK-125.

- **RFC-0009: Multi-agent orchestration** (BK-125): Draft RFC proposing
  orchestrator + 4 subject matter experts for complex multi-concern tasks.
  Claude Code native (Agent tool) approach. No code change — process only.

- **Test coverage and ResourceWarning fixes**: SQLBlob test fixtures now
  dispose engines on teardown (ResourceWarning eliminated). ProxyStore
  delegation coverage 68% → 100% (new `test_proxy.py`). SQLAlchemy backend
  coverage 90% → 99% (`_glob_to_like`, optional columns, health check).
  `/pr` skill now gates on `hatch run test-cov` (95% threshold) before
  creating PRs.

## [0.19.0] - 2026-03-23

### Changed

- **Renamed ext factory functions for naming consistency** (BK-010):
  - `pydantic_to_registry_config()` → `from_pydantic()` — matches the `from_*`
    pattern used by `from_yaml`, `from_dict`, `from_toml`.
  - `remote_store_io_manager()` → `dagster_io_manager()` — drops redundant
    `remote_store_` prefix, matches `pyarrow_fs` pattern.
  - `cached_store()` → `cache()` — bare verb, matches `observe()`.
  - Old names remain as deprecated aliases emitting `DeprecationWarning`.

### Documentation

- **Single-source code snippets for docs** (ID-057): docs code blocks are now
  pulled from tested Python files in `examples/snippets/` via pymdownx.snippets
  named regions. CI runs snippet scripts to guarantee they stay valid.

- **Auto-generated example doc wrappers** (ID-058): `scripts/gen_pages.py` now
  scans `examples/*.py`, extracts the module docstring, and generates wrapper
  pages + index + nav entries automatically. Eliminates the class of "forgot to
  add a wrapper" bugs. Added `tests/test_api_coverage.py` to verify every
  `__all__` symbol has API documentation.

- **Cross-link compliance pass** (BK-013): `## See also` sections added to all
  27 example pages and all API reference pages. Backend names in capability
  matrices, choosing-a-backend, concurrency, health-check, performance, and API
  reference tables now link to their respective guide pages. Added Rule 4
  ("Table header/key-column → documented entity") to `DOCUMENTATION.md` § 4.

- **Docstring and API doc fixes**: replaced private-module imports with public
  API paths in docs, completed extensions table, fixed Sphinx-style remnants.

### Internal

- **S3 backend code deduplication** (BK-011): extracted `_S3Base` base class,
  `_fileinfo` helpers, and error factories from the two S3 backends. Net −94
  lines, single maintenance point for 155 previously duplicated lines.

- **Extension code deduplication** (BK-012): `_StreamWrapper` base class in
  `ext/streams.py`, generic `_run_batch()` executor in `ext/batch.py`,
  `_deprecated_alias()` helper in `ext/_helpers.py`.

- **Test suite deduplication and parametrization** (BK-014): refactored 30 of 40
  test files (~17,800 → ~16,300 lines, −8.6%) while preserving identical
  coverage. Parametrized similar tests, extracted shared fixtures, merged
  single-method classes, and consolidated repeated assertion patterns.

- **SDD document category consolidation** (ID-099): merged `proposals/` →
  `rfcs/` and `plans/` → `research/`, reducing SDD categories from 7 to 5.
  Added Document Types table to `000-process.md`.

- **Fixed compound-command PreToolUse hook**: replaced `jq` (not installed) with
  Python for JSON parsing. Also blocks `git -C` pattern.

## [0.18.0] - 2026-03-18

### Added

- **S3 backend now populates `FileInfo.digest` from `x-amz-checksum-*`** —
  `get_file_info` calls `HeadObject` with `ChecksumMode: ENABLED` unconditionally,
  returning both metadata and any checksum headers in a single request. The
  base64-encoded checksum is converted to a hex `ContentDigest`. Listing paths
  (`list_files`, `iter_children`) still return `digest=None` to avoid per-file
  overhead. (ID-098, S3-024)
- **S3 backend now populates `FileInfo.etag`** — `_info_to_fileinfo` strips
  the double-quoted S3 ETag and stores it as a lowercase string.
  (ID-096, S3-023)
- **Azure backend now populates `FileInfo.etag` and `FileInfo.digest`** —
  `_props_to_fileinfo` strips and lowercases the Azure blob ETag (`etag`), and
  converts `content_settings.content_md5` bytes to a `ContentDigest("md5", hex)`
  when the blob was uploaded with Content-MD5 set. (ID-097, AZ-034)

- **`ContentDigest` frozen dataclass** — immutable model with `algorithm: str`
  and `value: str` (both lowercase-normalized, validated). Convenience
  `content_digest()` function in `ext.integrity`. (ID-095, CDG-001–CDG-003)
- **`FileInfo.digest` and `FileInfo.etag` fields** — `digest: ContentDigest | None`
  for verified checksums, `etag: str | None` for opaque server tags.
  `FileInfo.checksum` is removed (pre-1.0, no deprecation shim).
  (ID-095, CDG-004)
- **`ext.streams` module** — composable `BinaryIO` wrappers for progress
  tracking and checksum computation: `ProgressReader`, `ProgressWriter`,
  `ChecksumReader`, `ChecksumWriter`, `read_with_progress()`. Stream-level
  primitives that compose with any `BinaryIO`, including from `open_atomic()`.
  (ID-092)
- **`ext.integrity` module** — pure functions for checksum verification over
  Store's public API: `checksum()`, `verify()`, `verify_hex()`. (ID-093)
- **`ProxyStore` base class** — shared delegation base for `ObservedStore`
  and `CachedStore`. Centralizes private-attribute coupling, provides default
  delegation for all Store methods, and enables `child()` propagation.
  Internal only — not part of the public API. (ID-094, ADR-0014)
- **HTTP backend: HEAD fallback for CDN-blocked servers** — when `HEAD` returns
  401/403, `exists()`, `get_file_info()`, and `check_health()` retry with
  `GET` + `Range: bytes=0-0`. The result is cached for the backend's lifetime.
  Discovered during live testing against CDN-fronted endpoints. (ID-085)
- **`@pytest.mark.os_sensitive` CI marker** — macOS and Windows CI jobs now run
  only tests that exercise OS-specific behaviour (path separators, atomic writes
  via `os.replace`, local filesystem operations). Network-protocol backends
  (HTTP, S3, SFTP) are Linux-only. Reduces cross-platform CI time significantly.
  (ID-087)
- **Medallion + Dagster showcase** (`examples/medallion_dagster/`) —
  self-contained Dagster project demonstrating 4 extensions composing over live
  MeteoSwiss weather data in a Bronze/Silver/Gold medallion architecture.
  Uses `ReadOnlyHttpBackend`, `ext.cache`, `ext.otel`,
  and `ext.dagster`. (BK-008)
- **Read-only HTTP backend** (`ReadOnlyHttpBackend`) — read files from
  HTTP/HTTPS URLs. Capabilities: `{READ, METADATA}`. Zero runtime dependencies
  (uses stdlib `urllib`); optional `requests` and `httpx` transports via extras
  for connection pooling. Install with `pip install "remote-store[requests]"` or
  `pip install "remote-store[httpx]"`. (ID-082)
- **Conformance suite capability gates** — WRITE, DELETE, LIST, MOVE, COPY
  capabilities are now gated in the backend conformance suite, enabling testing
  of partial-capability backends.
- **`ext.dagster` — Dagster IO Manager adapter** (ID-075 v1) — wraps any
  existing `Store` as a Dagster `IOManager` via `remote_store_io_manager()`.
  Pluggable serialization (pickle, JSON, Parquet). Install with
  `pip install "remote-store[dagster]"`. Spec `031-ext-dagster.md`
  (DAG-001 through DAG-011).

### Changed

- **`ext.transfer.download()` now uses `ProgressReader` wrapper** — progress
  tracking in `download()` is now consistent with `upload()` and `transfer()`,
  using the `ProgressReader` stream wrapper instead of an inline callback.
  (ID-006, XFER-009)
- **`ext.transfer` now uses public `ProgressReader`** from `ext.streams`
  instead of its private `_ProgressReader`. No public API change. (ID-091)
- **`ObservedStore` and `CachedStore` now extend `ProxyStore`** — reduces
  boilerplate, centralizes delegation, and removes duplicated init coupling.

### Fixed

- **`child()` now propagates proxy behavior** in `ObservedStore` and
  `CachedStore`. Previously, `cached_store(s).child("sub")` returned a plain
  `Store`, silently losing caching/observation. (BUG-003)
- **`pydantic_to_registry_config()` now unwraps `SecretStr` fields** —
  Pydantic `SecretStr` values in backend `options` dicts are automatically
  converted to plain strings before reaching `from_dict()`, so sensitive-key
  detection wraps them in `Secret` correctly. Previously, `SecretStr` objects
  bypassed the `isinstance(v, str)` check and were not wrapped.

### Documentation

- **Backend API reference pages** (ID-088) — added class documentation for all
  7 backends (Local, Memory, HTTP, S3, S3-PyArrow, SFTP, Azure) under a new
  "Backends" section in the API reference. Each page links to the corresponding
  backend guide.
- **Extensions API reference section** (ID-089) — moved all 11 extension API
  pages into a nested "Extensions" section with an index page, matching the
  Backends section structure.
- **Docs landing page** (ID-090) — replaced the 1:1 README include with a
  purpose-built orientation page: architecture diagram, six key messages,
  quick start, and navigation links.

### Removed

- **Top-level re-exports of optional-dependency extensions** (ADR-0013) —
  `from remote_store import pyarrow_fs` and similar shortcuts for arrow, otel,
  pydantic, and yaml extensions are removed.
  Use the canonical import path instead:
  `from remote_store.ext.arrow import pyarrow_fs`.  Pure-Python extensions
  (batch, cache, glob, observe, partition, transfer) are unchanged.

## [0.17.0] - 2026-03-14

### Added

- **`AzureBackend(max_concurrency=)` parameter** (ID-076) — controls parallel
  connections for blob uploads and downloads. Default `1` (sequential, matching
  prior behavior). Set higher for improved throughput on large files.

- **`FolderInfo.name` property** (ID-079) — derived `@property` returning the
  final path component (`self.path.name`). `FolderInfo` now satisfies the
  `PathEntry` protocol alongside `FileInfo` and `FolderEntry`.

- **`FolderEntry` dataclass and `PathEntry` protocol** (ID-072) — `FolderEntry`
  is an immutable identity object returned by listing operations with `.name`
  and `.path` attributes. `PathEntry` is a runtime-checkable protocol satisfied
  by both `FileInfo` and `FolderEntry`, enabling uniform iteration.

- **`Store.write_text()` convenience method** (ID-074) — writes a string to a
  file with configurable encoding. Wraps `write()` with `encoding` and
  `overwrite` parameters matching `pathlib.Path.write_text()`. Store-level only
  (no backend changes). `ext.observe` `on_write` hook, `ext.cache` routes through
  `write`. Spec `030-write-text.md` (WTXT-001 through WTXT-006).

### Changed

- **Docstrings migrated from Sphinx to Google style** (ID-080) — all 367
  Sphinx-style markers (`:param:`, `:returns:`, `:raises:`) across 25 source
  files converted to Google-style sections (`Args:`, `Returns:`, `Raises:`).
  `mkdocs.yml` updated to `docstring_style: google`. `sdd/DESIGN.md` §4
  updated with the new convention. Unlocks inline admonitions and markdown
  cross-references inside docstrings.

- **S3 listing methods no longer call `exists()` before listing** (ID-062) —
  removes a redundant API round-trip from `list_files`, `list_folders`, and
  `iter_children` in `S3Backend` and `S3PyArrowBackend`. The existing
  `FileNotFoundError` handler already covers non-existent paths.

- **`list_folders()` returns `Iterator[FolderEntry]`** (ID-072) — was
  `Iterator[str]`. Use `.name` for the folder name, `.path` for the full path.

- **`iter_children()` returns `Iterator[FileInfo | FolderEntry]`** (ID-072) —
  was `Iterator[FileInfo | str]`. Use `isinstance(entry, FolderEntry)` instead
  of `isinstance(entry, str)` to distinguish folders from files.

- **Store docstring rewrite** (ID-074) — rewrote all Store method docstrings for
  accuracy and consistency. Fixed `write`/`write_atomic` str claim, corrected
  `read_text` errors reference.

- **`store.md` restructured with per-method `:::` directives** (ID-074) —
  individual method headings, admonitions for ordering, atomicity, metadata, and
  thread-safety. Added backend behavior matrix verified against backend source.

### Docs

- **README medium pass** (ID-081) — streamlined onboarding flow, added backend
  behavior matrix, restored correct extras and library names, fixed method count
  (27).

- **Docs site polish** (ID-064) — property return types now visible
  (`show_signature_annotations`), Fira Code font for code blocks,
  sticky navigation tabs, search suggest/highlight, tighter parameter
  list spacing, capability matrix icons.

## [0.16.0] - 2026-03-10

### Added

- **`Store.read_text()` convenience method** (ID-056) — reads a file and
  decodes to string. Wraps `read_bytes()` with `encoding` and `errors`
  parameters matching `pathlib.Path.read_text()`. Store-level only (no backend
  changes). `ext.observe` `on_read` hook, `ext.cache` routes through cached
  `read_bytes`. Spec `028-read-text.md` (RTXT-001 through RTXT-006).

- **`Store.iter_children()` combined listing** (ID-055) — yields both files
  (`FileInfo`) and folders (`str`) in a single pass, avoiding two round-trips.
  All 6 backends override with single-call implementations. `ext.observe`
  `on_list` hook, `ext.cache` caching and invalidation. Spec
  `027-iter-children.md` (ITER-001 through ITER-008).

- **`Store.ping()` health check** (ID-054) — lightweight, non-destructive
  backend connectivity verification. Delegates to `Backend.check_health()`.
  Per-backend strategies: Local (`exists` + `os.access`), S3 (`head_bucket`),
  S3-PyArrow (`get_file_info`), SFTP (`stat`), Azure
  (`get_container_properties`), Memory (no-op). `ext.observe` `on_ping` hook.
  Spec `026-health-check.md` (PING-001 through PING-010).

- **`RetryPolicy` dataclass** (ID-010) — unified retry configuration for transient
  backend errors. Frozen dataclass with `max_attempts`, `backoff_base`, `backoff_max`,
  `jitter`, and `timeout` fields. Each backend maps the policy to its native retry
  mechanism: SFTP (tenacity), S3 (botocore), Azure (ExponentialRetry), S3-PyArrow
  (PyArrow C++ + botocore). `RetryPolicy.disabled()` factory for single-attempt
  mode. Configurable via constructor (`retry=RetryPolicy(...)`) or dict config
  (`"retry": {"max_attempts": 5}`). ADR-0011, spec `025-retry-policy.md`.

- **`SFTPUtils` utility class** — groups `load_private_key` and `HostKeyPolicy`
  into a public re-export (`from remote_store.backends import SFTPUtils`).
  Replaces private `backends._sftp` imports in user-facing code.

### Changed

- **Authoritative docs restructured to ADF standard** (ID-059) — `sdd/DESIGN.md`
  trimmed to code style conventions only (sections 1-10 removed, duplicated specs).
  `sdd/DOCUMENTATION.md` condensed to rules + guides (~130 lines from ~456).
  `sdd/000-process.md` restructured to Intent/Rules/Guides (~75 lines from ~152).
  Audit files moved to `sdd/audits/`. `CONTRIBUTING.md` spec format section
  replaced with cross-ref to `000-process.md`. `CLAUDE.md` environment note removed,
  gh CLI `Forbidden operations` denylist replaced with ask-gated confirmation.

- **`from_yaml()` moved from `RegistryConfig` classmethod to `ext/yaml.py`** (ID-002)
  YAML config loading requires an optional dependency (`pyyaml` or `ruamel.yaml`),
  same as the Pydantic adapter. Moved to `ext.yaml` for consistency with the
  extension architecture (ADR-0008). Import changes:
  `from remote_store.ext.yaml import from_yaml`.

### Docs

- **RTD docs now default to stable release** — changed all docs deep links in
  user-facing files (README, guides) from `/en/latest/` to `/stable/`, dropping
  the `/en/` language prefix (single-language project) and pointing to the most
  recent PyPI release instead of unreleased master. Updated DOCUMENTATION.md
  canonical URL policy and CONTRIBUTING.md release checklist. Requires RTD admin:
  default version = `stable`, URL versioning scheme = `/version/path/`.

- **README API table audit** — added missing `iter_children()` to Browse &
  Inspect section, added 5 missing example scripts to Examples table
  (`caching`, `config_loaders`, `capabilities_and_errors`, `path_model`,
  `retry_policy`), added `ext.yaml` to Extensions table, updated method count
  from 23 to 26 in comparison table, fixed stale PyArrow `native_path()`
  limitation note. Added `ext-yaml.md` API reference page and nav entry.

- **Audit 003 fixes** (AF-022 through AF-040) — documentation quality audit
  follow-up. 16 findings fixed, 3 closed as non-defects. Key changes:
  7 missing example doc pages added, observe hook table completed (`on_ping`,
  `open_atomic`), private imports replaced with public API in 4 guides,
  `CacheBackend` protocol docstrings added, CONTRIBUTING.md spec listing
  simplified (no longer goes stale), mkdocstrings `show_if_no_docstring: false`
  for proxy class overrides.

## [0.15.0] - 2026-03-08

### Added

- **`hatch run notebooks` smoke-test runner** (ID-048) — lightweight script (`tests/scripts/run_notebooks.py`) that executes tutorial notebook code cells via `exec()` without requiring Jupyter. Wired into `hatch run all` and CI `examples` job. Skips `benchmark_analysis.ipynb` (needs pre-generated data).
- **`Store.open_atomic(path, overwrite=False)`** — context manager for streaming atomic writes (ID-026, SAW-001 through SAW-015). Yields a writable file object backed by a temporary location; on successful exit the file is atomically promoted to the target path, on exception the temporary artifact is cleaned up. Eliminates the memory-buffering requirement of `write_atomic()` for large files. All 6 backends supported.
- **`Backend.open_atomic(path, overwrite=False)`** — new abstract method on the Backend ABC. Per-backend temp-path strategies: `mkstemp`+`os.replace` (Local), `.~tmp.*`+`posix_rename` (SFTP), `SpooledTemporaryFile`+PUT (S3, S3-PyArrow, Azure non-HNS), temp blob+DFS rename (Azure HNS), `BytesIO` buffer (Memory).
- **Data lake medallion notebook** (`examples/notebooks/04_data_lake_medallion.ipynb`) — end-to-end Bronze/Silver/Gold pipeline using `Store.child()`, PyArrow, Polars, and DuckDB. Generates ~3,500 sensor readings with realistic quality issues, cleans through medallion layers, and runs analytical queries on gold. Runs entirely on `MemoryBackend`.
- **`Store.native_path(key)`** — converts a store-relative key to the backend-native path (STORE-015). Inverse of `to_key()`. Used by the PyArrow adapter for Tier 1 fast-path reads.
- **`Backend.native_path(path)`** — converts a backend-relative key to the backend-native path (BE-025). Default is identity; `S3PyArrowBackend` prepends bucket prefix.
- **PyArrow adapter Tier 1 native fast-path reads** (ID-037, PA-010) — `StoreFileSystemHandler` now probes for a native PyArrow filesystem at construction via `store.unwrap(pyarrow.fs.FileSystem)`. When available (e.g., `S3PyArrowBackend`), `open_input_file` delegates directly to the native FS, bypassing Python I/O for zero GIL overhead with C++ range requests and I/O coalescing.
- **`S3PyArrowBackend.unwrap()`** now accepts `pyarrow.fs.FileSystem` base class in addition to `pyarrow.fs.S3FileSystem`.
- **Parallel batch operations** (ID-035) — `batch_delete`, `batch_copy`, and `batch_exists` now accept `concurrent=True` and `max_workers=N` keyword arguments for parallel execution via `ThreadPoolExecutor`. Cloud backends benefit significantly from concurrent I/O over sequential execution. `stop_on_error` is incompatible with `concurrent=True` (raises `ValueError`). Spec: BATCH-020 through BATCH-025.
- **`ext.cache` — store-level caching middleware** (ID-025) — `cached_store(store, ttl=300)` wraps a Store in a proxy that caches read-only operations (`exists`, `is_file`, `is_folder`, `read_bytes`, `get_file_info`, `get_folder_info`, `list_files`, `list_folders`, `glob`) with TTL-based expiration. All mutating operations automatically invalidate affected entries. `max_content_size` limits memory for large files. Thread-safe. Spec: CACHE-001 through CACHE-015.
- **`ext.partition` — Hive-style partition path helpers** (ID-036) — `partition_path(filename, **partitions)` builds paths like `year=2026/month=03/data.parquet`, `parse_partition(path)` extracts the partition dict and filename. Pure Python, zero dependencies. Spec: PART-001 through PART-013.

### Documentation

- **Documentation overhaul** (DOC-001) — Diataxis nav restructure (Getting Started / Guides / Reference / Explanation), extension API reference pages for all 9 ext modules, 7 new content pages (capabilities matrix, choosing a backend, troubleshooting, migration, architecture overview, security model, further reading), research docs surfaced on site, docstring audit for Store/Backend/errors with complete `:param:`/`:returns:`/`:raises:` and examples, cross-links between guides and API reference pages.

## [0.14.0] - 2026-03-07

### Changed

- **`_stacklevel` removed from public `from_dict()` signature** (ID-043)
  Internal `_stacklevel` parameter no longer leaks into the public
  `RegistryConfig.from_dict()` API. Warning stack-level control is now handled
  via a private `_from_dict()` helper.

### Fixed

- **`Registry.get_store()` no longer owns the shared backend** (ID-041)
  Stores returned by `get_store()` now set `_owns_backend = False`, preventing
  a store's `close()` from shutting down the cached backend and breaking sibling
  stores. `Registry.close()` remains the lifecycle owner.

- **`Store.move()` and `Store.copy()` short-circuit when `src == dst`** (ID-040)
  Moving or copying a file to itself is now a uniform no-op across all backends.
  Source existence is verified via `is_file()` (not `exists()`), so folders at
  the source path correctly raise `NotFound`. Spec: STORE-008a.

### Added

- **Data lake patterns guide** (ID-034)
  New guide (`guides/data-lake-patterns.md`) documenting Bronze/Silver/Gold
  medallion architecture using `Store.child()` + `ext.arrow` + `ext.transfer`.
  Covers PyArrow, Polars, DuckDB, Delta Lake integration, batch partition
  operations, cross-backend transfer, and testing without cloud credentials.
  Includes honest assessment of where remote-store fits vs. Databricks/Spark.

- **Credential hygiene documentation** (ID-042)
  Added "Credential hygiene" section to README and updated `examples/configuration.py`
  with `Secret` wrapping, `from_dict()` auto-wrapping, and `.reveal()` usage.

- **`RegistryConfig.from_toml()` — TOML config loader** (ID-005)
  Load config from a standalone `.toml` file or from `pyproject.toml` via
  `table=("tool", "remote-store")`. Zero dependencies on Python 3.11+;
  optional `tomli` backport for 3.10. Spec: CFG-008, CFG-009.

- **`RegistryConfig.from_yaml()` — YAML config loader** (ID-002)
  Load config from a YAML file. Accepts `pyyaml` (primary) or `ruamel.yaml`
  (fallback). Spec: CFG-010, CFG-011.

- **Unknown top-level key warning in `from_dict()`** (CFG-012)
  `from_dict()` now emits `UserWarning` for unrecognized keys like `"backend"`
  (typo for `"backends"`), preventing silently empty configs.

- **`pydantic_to_registry_config()` — Pydantic adapter** (ID-003)
  Convert any Pydantic `BaseModel` or `BaseSettings` instance to a
  `RegistryConfig` via `model_dump() → from_dict()`. Supports env-var binding,
  `.env` file loading, and validation via `pydantic-settings`. Optional
  `pydantic` extra. Spec: CFG-015, CFG-016, CFG-017.

## [0.13.0] - 2026-03-03

### Added

- **`Secret` wrapper and credential hygiene** (ID-039, SEC-001 through SEC-008)
  `Secret` type in `_config.py` wraps sensitive credential strings: `repr()`
  and `str()` return `'***'`, `.reveal()` returns the plain value.
  `RegistryConfig.from_dict()` auto-wraps known sensitive keys (`key`, `secret`,
  `password`, `account_key`, `sas_token`, `connection_string`). All backends
  accept `str | Secret` for credential params via `_reveal()`. SFTP coerces
  `host_key_policy` strings to `HostKeyPolicy` enum. `SecretRedactionFilter`
  logging filter scrubs `Secret` instances from log record args.
  Spec: `sdd/specs/020-credential-hygiene.md`.

- **Intrinsic stdlib logging** (ID-004, OBS-008)
  Core modules and extensions now use `log = logging.getLogger(__name__)` with `NullHandler`
  on the `"remote_store"` root logger. DEBUG for method entry, INFO for
  write/delete/move/copy completion. Structured `extra={}` with `op`, `path`,
  `backend` keys. Existing logger names standardised (`_log` -> `log`,
  `logger` -> `log`).

- **`ext.observe` — observability hooks** (ID-024, ADR-0010, OBS-001 through OBS-010)
  `observe(store, on_read=..., on_write=..., on_any=..., around=...)` wraps a
  Store in an `ObservedStore` proxy that fires callbacks after each operation.
  `StoreEvent` frozen dataclass carries operation, path, backend, timing, error,
  and metadata. `BufferedObserver` queues events for batched delivery on a
  background thread. Drift-protection test ensures new Store methods cannot
  silently bypass observation. Spec: `sdd/specs/019-ext-observe.md`.

- **`ext.otel` — OpenTelemetry bridge** (ID-024, OBS-011 through OBS-014)
  Pre-built hooks that emit OpenTelemetry spans and metrics. `otel_observe(store)`
  wraps a Store with distributed tracing (`store.{op}` spans with `CLIENT` kind)
  and three metric instruments (operations counter, errors counter, duration
  histogram). Depends only on `opentelemetry-api` (zero-cost no-ops without SDK).
  New optional extra: `pip install "remote-store[otel]"`.
  Spec: `sdd/specs/019-ext-observe.md` (OBS-011--OBS-014).

### Fixed

- **`get_folder_info("")` crashed with `InvalidPath` for root folders** (BUG-001)
  Added `RemotePath.ROOT` class-level sentinel that bypasses `__init__` validation
  (`str(ROOT) == "."`). Fixed all 6 backends and `_rebase_folder_info` to return
  `RemotePath.ROOT` for root-level queries. Store methods now accept `"."` as a
  root alias so that `str(folder_info.path)` round-trips correctly.
  Spec: `sdd/specs/004-path-model.md` (PATH-015).

## [0.12.0] - 2026-03-01

### Added

- **S3, S3-PyArrow, and Azure native glob** (BK-002, ID-007, GLOB-018/019/020)
  All cloud backends now override `Backend.glob()` with prefix-optimized listing
  and client-side regex filtering. Local, S3, S3-PyArrow, and Azure backends
  now declare `Capability.GLOB`.
  Shared glob helpers extracted to internal `_glob.py` module.

## [0.11.0] - 2026-03-01

### Added

- **Glob pattern matching — three-tier design (ADR-0009)** (BK-002, ID-007)
  - **Tier 1:** `list_files(pattern=…)` — universal `fnmatch` name filtering, works with every backend (needs only `LIST`)
  - **Tier 2:** `Store.glob()` / `Capability.GLOB` — native backend glob, capability-gated (like `unwrap()`). `LocalBackend` implements via `pathlib`
  - **Tier 3:** `ext.glob.glob_files()` — portable full-glob fallback with `**` recursive patterns and `[abc]`/`[!abc]` character classes; delegates to native glob when available, otherwise `list_files` + client-side regex
### Changed

- **Beta status.** Project classifier changed from Alpha to Beta. Core API
  (Store, Registry, Backend, models, errors) is now considered stable.
  See CONTRIBUTING.md § Stability tiers.

## [0.10.0] - 2026-02-28

### Added

- **Extension namespace contract (ADR-0008)** — formalized the `ext.*` namespace contract: public API only, no lifecycle ownership, `CapabilityNotSupported` propagation, export rules for pure-Python vs optional-dependency extensions, development lifecycle, and third-party naming convention. Added extensions guide, expanded CONTRIBUTING.md checklist, contract enforcement tests, updated CLAUDE-REFERENCE.md ripple-check table (ID-027)

### Changed

- **S3-PyArrow read path optimization** — removed `BufferedReader` from `S3PyArrowBackend.read()`, added `read()` + chunked `readline()` to `_PyArrowBinaryIO`, eliminating double-copy overhead on streaming reads (ID-031, RFC-0003)
- **Benchmark tiered modes, backend filtering, and comparative docs** — replaced binary `slow`/not-slow split with three tiers (quick/standard/full), added `--backend` filter for single-backend runs (deselects instead of skipping to avoid fixture setup), added `--bench-timeout` watchdog (Windows-compatible), added `--comparative` and `--markdown` modes to `report.py` for remote-store vs raw SDK vs fsspec comparison tables, updated hatch scripts. Comparative results and performance guide now populated with measured Docker benchmark data across 4 backends (ID-020)
- **Release CI: GitHub Release as single trigger** — `publish.yml` now triggers on `release: types: [published]` instead of `push: tags: ["v*"]`. The GitHub Release becomes the single event that triggers PyPI publish (ID-028)
- **Versioned documentation with mike** — `docs.yml` split into two jobs: `deploy-dev` (master push deploys "dev" alias) and `deploy-release` (release published deploys versioned docs with "latest" alias). Version switcher dropdown added to docs site. Requires changing GitHub Pages source to "Deploy from a branch" (`gh-pages`) (ID-029)

## [0.9.0] - 2026-02-28

### Added

- **Transfer operations (`ext.transfer`)** — `upload`, `download`, and `transfer` functions for moving data between local files and Stores or between two Stores. All streaming (never loads full file into memory), with optional `on_progress` callback per chunk. `upload` streams a local file to a Store, `download` reads in 1 MiB chunks to a local file, `transfer` pipes between any two Stores. Supports `overwrite` flag. Pure Python, no extra dependencies, unconditional top-level export (ID-023, unifies ID-001 + ID-009)
- **Batch operations (`ext.batch`)** — `batch_delete`, `batch_copy`, and `batch_exists` convenience functions for operating on collections of paths. Sequential execution with error aggregation via `BatchResult` (succeeded/failed split). Supports `stop_on_error`, `missing_ok`, and `overwrite` options. Pure Python, no extra dependencies, unconditional top-level export (ID-022)
- **PyArrow FileSystem adapter (Phase 1)** — `StoreFileSystemHandler` wraps any `Store` into a `pyarrow.fs.PyFileSystem`, enabling seamless interop with PyArrow datasets, Pandas, Polars, DuckDB, PyIceberg, and Delta Lake. Includes `pyarrow_fs()` convenience factory, `_StoreSink` write buffer with spill-to-disk, tiered read strategy (Tier 2 BufferReader for small files, Tier 3 PythonFile for large seekable files), complete error mapping (PA-019/020), and conditional top-level export. Install with `pip install "remote-store[arrow]"`. Tier 1 native fast-path deferred to Phase 2 (ID-016)
- **`Store.unwrap(type_hint)`** — delegates to `Backend.unwrap()`, exposing the backend's native handle through the public Store surface. Used by the PyArrow adapter and available to all callers (STORE-013)
- **Concurrency and atomicity guide** — new `guides/concurrency.md` documenting TOCTOU race on `overwrite=False` (all backends) and non-atomic `move()` (S3, S3-PyArrow, Azure non-HNS, SFTP fallback), with per-backend summary table and practical workarounds. Cross-referenced from all backend guides (AF-010)
- **Capability gating tests** — 14 tests verifying all 12 Store methods that require a capability raise `CapabilityNotSupported` when the backend lacks it, with correct `.capability` attribute value and backend name propagation (AF-012, STORE-006)
- **S3 and SFTP error path tests** — mock-based tests for `PermissionDenied` (S3-016: HTTP 403/accessdenied, SFTP-021: `errno.EACCES`), `AlreadyExists` (SFTP-022: `errno.EEXIST`), and `BackendUnavailable` (S3-017: endpoint/connect/timeout/dns errors, SFTP-023: `paramiko.SSHException`). Removed `pragma: no cover` from now-tested `_classify_error`/`_map_exception` branches (AF-013)
- **CI gate in publish workflow** — `publish.yml` now runs lint, typecheck, and tests (Python 3.10 + 3.13) before building and publishing to PyPI, preventing broken tags from reaching the registry (AF-014)

## [0.8.0] - 2026-02-27

### Added

- **`Store.child(subpath)` — runtime sub-scoping** — returns a new Store scoped to a subfolder, sharing the parent's backend instance (no new connections). Child stores do not close the shared backend on `close()` or context manager exit. Validated via `RemotePath`, chainable (`store.child("a").child("b")`), equality-transparent with directly constructed stores. Spec: `015-store-child.md` (ID-021)
- **Cloud backend examples** — 5 new example scripts (`s3_backend.py`, `s3_pyarrow_backend.py`, `sftp_backend.py`, `azure_backend.py`, `store_child.py`) demonstrating each backend with self-contained env-var configuration and graceful failure messages. All Store API methods now have example coverage
- **Claude Code reusable skills** — 6 slash-command skills in `.claude/commands/` codifying recurring workflows: `/ripple-check` (cross-reference validation), `/release` (6-phase release checklist), `/add-backend` (12-step scaffolding), `/backlog-sync` (backlog update helper), `/pr-preflight` (11-check pre-submission validation), `/add-spec` (SDD spec + test scaffolding) (ID-030)

### Changed

- **Release checklist expanded** — replaced the 5-item release checklist in CONTRIBUTING.md with a 6-phase process covering pre-flight, content freeze, version bump, validation, ship with PR review gate, and post-release verification. GitHub Release is the intended single trigger for PyPI publish and docs deploy (ID-028, ID-029 track the CI changes)

### Fixed

- **`streaming_io.py` example leaked file handles on Windows** — `store.read()` streams were not closed before `TemporaryDirectory` cleanup, causing `PermissionError` on Windows due to file locking. Streams are now used as context managers

## [0.7.0] - 2026-02-27

### Added

- **`MemoryBackend` — in-memory backend** — tree-indexed, zero dependencies, no filesystem access. Supports all 8 capabilities with zero conformance test skips. Primary use cases: unit testing, interactive exploration, documentation examples, CI speed. Registered as `"memory"` backend type, always available (no optional extra). Store test fixtures migrated from `LocalBackend` + `tempfile` to `MemoryBackend` (ID-017)
- **PyArrow FileSystemHandler adapter spec** — drafted `sdd/specs/014-pyarrow-filesystem-adapter.md` for `StoreFileSystemHandler` wrapping any `Store` into a `pyarrow.fs.PyFileSystem`. Tiered read strategy (native fast path / BufferReader / PythonFile), spill-to-disk writes, complete error mapping (ID-016)
- **Backend `__repr__` with credential masking** — all 6 backends now implement `__repr__()`. Secrets display as `'***'` when set and `None` when unset; identifiers (bucket, host, container) are shown in clear text (AF-008)

### Changed

- **S3/S3-PyArrow `get_folder_info()` on empty folders** — no longer raises `NotFound`; the `exists()` check already gates non-existent paths. Azure non-HNS retains current behavior since virtual folders can't be empty (AF-004)
- **`Registry.close()` error handling** — now closes all backends even if one raises, always clears the cache, and re-raises the first error (AF-009)

### Removed

- **`RemoteFile` / `RemoteFolder` model classes** — removed dead code from models, `__all__`, tests, docs, and specs (AF-011)

### Fixed

- **README Azure SDK name** — corrected from wrong package name to `azure-storage-file-datalake` (AF-015)
- **CONTRIBUTING.md** — added spec 012 reference (AF-015)
- **Azure configuration example** — added to `examples/configuration.py` (AF-015)

## [0.6.0] - 2026-02-25

### Added

- **`DirectoryNotEmpty` error type** — new `RemoteStoreError` subclass raised when a non-recursive folder delete targets a non-empty folder. Replaces generic `NotFound` with a descriptive error (AF-005)
- **`_ErrorMappingStream`** — `io.RawIOBase` proxy that wraps streams returned by `Backend.read()`, catching `OSError` during lazy reads and mapping them through each backend's error classifier. Prevents native exceptions from leaking after `_errors()` context manager exits (AF-006)
- **Auto-registration of all backends** — `_register_builtin_backends()` now registers S3, SFTP, and S3-PyArrow backends (in addition to local and Azure) when their dependencies are installed (AF-001)
- **SFTP `_map_exception()` method** — single source of truth for SFTP error classification, used by both `_errors()` and `_ErrorMappingStream` (AF-006)
- **SFTP empty folder support** — `get_folder_info()` on an empty SFTP directory now returns `FolderInfo(file_count=0)` instead of raising `NotFound` (AF-004)

### Changed

- **BREAKING**: Removed `Capability.GLOB` and `Capability.RECURSIVE_LIST` enum members that had no corresponding backend methods (AF-002)
- **S3/S3-PyArrow `close()`** — no longer calls `clear_instance_cache()`, which was a global side-effect affecting all s3fs instances in the process (AF-003)
- **Azure/S3-PyArrow `read()`** — eliminated double-buffering by wrapping `_ErrorMappingStream` directly in `BufferedReader` instead of nesting two `BufferedReader` layers

### Fixed

- **Lazy stream error mapping** — `OSError` raised during `stream.read()` after `Backend.read()` returns is now properly mapped to `RemoteStoreError` subtypes instead of leaking as raw exceptions (AF-006)
- **Exception chaining** — stream error mapping uses `from exc` to preserve original traceback for debugging

---

## [0.5.0] - 2026-02-23

### Added

- **Azure backend** (`AzureBackend`) — new built-in backend for Azure Blob Storage and ADLS Gen2 using `azure-storage-file-datalake` directly. Adapts at runtime to Hierarchical Namespace (HNS) accounts for atomic rename and real directories, while remaining fully functional on plain Blob Storage. Install with `pip install "remote-store[azure]"`. (BK-001, spec 012)
- **Streaming reads for Azure** — `read()` returns a forward-only streaming `BinaryIO` via `_AzureBinaryIO` adapter wrapping `StorageStreamDownloader.chunks()`, consistent with other backends
- **Azurite CI integration** — Azure backend tests run against Azurite Docker emulator in CI
- **Azure backend guide** — `guides/backends/azure.md` with installation, auth options, HNS vs non-HNS behavior, and Azurite local development

### Changed

- **SIO-001 seekability clarification** — `read()` streams are not guaranteed to be seekable; seekability is a backend-level property. Callers needing seekability should use `read_bytes()` + `BytesIO`
- **AZ-020 spec updated** — changed from BytesIO wrapper to streaming adapter

---

## [0.4.4] - 2026-02-23

### Added

- **Community standards** — CODE_OF_CONDUCT.md (Contributor Covenant v2.1), SECURITY.md (vulnerability reporting policy), issue templates (bug report + feature request), PR template, and CODEOWNERS
- **Dependabot** — automated dependency updates for pip and GitHub Actions (weekly, Mondays)
- **CodeQL** — GitHub code scanning workflow for Python on push/PR and weekly schedule
- Security section in README linking to vulnerability reporting
- **Streaming conformance tests** — 5 tests (x4 backends) that prevent regression of v0.4.3 streaming fixes: not-BytesIO assertion, chunked reads, stream position, BinaryIO write, and write-from-current-position (SIO-001, SIO-003)

---

## [0.4.3] - 2026-02-19

### Fixed

- **Streaming read/write loaded entire files into memory** — all four backends (Local, S3, S3-PyArrow, SFTP) now use true streaming for `read()` and `write()` with `BinaryIO` content, matching the spec's streaming-first intent
- **SFTP copy/move buffered entire files** — `copy()` and `move()` fallback now stream chunks using `_CHUNK_SIZE` instead of loading source into memory
- **Broken API reference link in README** — ReadTheDocs URL was missing `/en/latest/` prefix, causing 404 on PyPI

### Changed

- **Versioning docs consolidated** — removed outdated duplicate from `sdd/000-process.md`, canonical source is now `CONTRIBUTING.md`

---

## [0.4.2] - 2026-02-19

### Fixed

- **PyPI relative links broken** — README example scripts, notebooks, and CONTRIBUTING.md links used relative paths (`examples/quickstart.py`, `CONTRIBUTING.md`, etc.) which resolve to 404 on PyPI; converted all to absolute GitHub URLs

---

## [0.4.1] - 2026-02-19

### Fixed

- **PyPI logo broken** — README image used relative path (`assets/logo.png`) which doesn't resolve on PyPI's CDN; changed to absolute raw GitHub URL
- **Documentation site out of date** — specs 010 (native path resolution) and 011 (S3-PyArrow backend) and ADR-0005 were missing from the MkDocs site and navigation
- **Navigation on RTD** — added `navigation.instant` to MkDocs Material config so sidebar stays visible across page loads

### Added

- PyPI version, Python versions, Read the Docs, and license badges in README
- Read the Docs publishing (`remote-store.readthedocs.io`)
- "Going Public" section in DEVELOPMENT_STORY.md

### Changed

- `Documentation` URL in `pyproject.toml` now points to Read the Docs instead of GitHub Pages
- `CITATION.cff` URL updated to Read the Docs
- `.readthedocs.yaml` build OS bumped to ubuntu-24.04

---

## [0.4.0] - 2026-02-19

### Added

- **S3-PyArrow hybrid backend** — uses PyArrow's C++ S3 filesystem for reads/writes/copies (higher throughput for large files) and s3fs for listing/metadata/deletion. Drop-in alternative to `S3Backend` with the same constructor signature.
  - Install via `pip install "remote-store[s3-pyarrow]"`
  - Spec: `sdd/specs/011-s3-pyarrow-backend.md`
- New optional extra: `s3-pyarrow` (requires `s3fs>=2024.2.0` and `pyarrow>=14.0.0`)
- Dual `unwrap()` support: returns either `pyarrow.fs.S3FileSystem` or `s3fs.S3FileSystem`

---

## [0.3.0] - 2026-02-18

### Added

- **`Store.to_key(path)`** — public method to convert backend-native paths to store-relative keys
- **`Backend.to_key()`** — backend-level native-path-to-key conversion
- Python 3.14 support — added to CI test matrix and PyPI classifiers
- **PyPI publish workflow** — trusted publishing (OIDC) via GitHub Actions on `v*` tags (BL-001)
- **SFTP backend documentation** — `docs/backends/sftp.md` with installation, usage, and API reference (BL-002)
- **CITATION.cff** — enables GitHub's "Cite this repository" button (BL-005)
- **Development backlog** — `sdd/BACKLOG.md` for tracking release blockers, prioritized work, and ideas
- Versioning policy added to SDD process doc (`sdd/000-process.md`)
- Set up GitHub Pages docs hosting via `actions/deploy-pages` (BL-008)

### Fixed

- Store round-trip bug: `list()` returned backend-relative paths that included `root_path`, breaking re-use as input to `read()`/`delete()`
- CI: fixed cross-platform `type: ignore` comments for S3 backend

### Changed

- **README rewritten** — approachable, dev-friendly tone with scannable layout (BL-003, BL-004)
- Pinned minimum versions on public extras: `s3fs>=2024.2.0`, `paramiko>=2.2`, `tenacity>=4.0`
- Removed `typing-extensions` from core dependencies (unused — Python 3.10+ covers all needs)
- Removed `azure` extra (`adlfs`) — no Azure backend exists yet; will be re-added with the backend

---

## [0.2.0] - 2026-02-17

### Added

- **SFTP backend** via pure paramiko with host key policies (STRICT / TOFU / AUTO_ADD), PEM key sanitization, and tenacity retry on transient SSH errors
- Simulated atomic writes (temp file + rename) with documented orphan-file caveat
- `HostKeyPolicy` enum and `load_private_key()` utility for key management
- `_sanitize_pem()` for Azure Key Vault PEM compatibility

### Changed

- `sftp` optional dependency changed from `paramiko + sshfs` to `paramiko + tenacity`
- Version bumped to 0.2.0

---

## [0.1.0] - 2026-02-14

### Added

- **Store** — primary user-facing abstraction for folder-scoped file operations
- **Registry** — backend lifecycle management with lazy instantiation and context manager support
- **RegistryConfig / BackendConfig / StoreProfile** — declarative, immutable configuration with `from_dict()` for TOML/JSON parsing
- **RemotePath** — immutable, validated path value object with normalization and safety checks
- **Local backend** — stdlib-only reference implementation with full capability support
- **Capability system** — backends declare supported features; unsupported operations fail explicitly
- **Normalized error hierarchy** — `NotFound`, `AlreadyExists`, `InvalidPath`, `PermissionDenied`, `CapabilityNotSupported`, `BackendUnavailable`
- **Streaming-first I/O** — `read()` returns `BinaryIO`, `write()` accepts `bytes | BinaryIO`
- **Atomic writes** — `write_atomic()` via temp-file-and-rename
- **Empty path support** — `""` resolves to store root for folder/query operations (see ADR-0004)
- **Full type safety** — mypy strict mode, `py.typed` marker
- **Spec-driven development** — 7 specifications, 4 ADRs, full test traceability with `@pytest.mark.spec`
- **Examples** — 6 runnable Python scripts and 3 Jupyter notebooks
- **CI** — ruff, mypy, pytest (Python 3.10–3.13), example validation

### Known Limitations

- Only the local filesystem backend is implemented. S3, Azure, and SFTP backends are planned.
- No glob/pattern matching support yet (`Capability.GLOB` is declared but unused).
- No async API (sync-only by design; compatible with structured concurrency).
