# Development Backlog — Done

Completed items, newest first. Active work lives in [BACKLOG.md](BACKLOG.md).

---

## New Backends

- [x] **ID-119 — SQLAlchemy backends**
  Two concrete backends sharing `_SQLAlchemyBaseBackend`:
  - `SQLBlobBackend` (v1) — KV blob store, full read-write. PR #292.
  - `SQLQueryBackend` (v2) — read-only query materializer, explicit query
    mappings via `ResultSerializer` protocol. Spec 041.
  - [Research](research/research-sqlalchemy-backend.md)
  - Future: view/convention discovery (`strict=False`), ADBC fast path (v3).

## Process

- [x] **BK-125 — Multi-agent orchestration for complex tasks**
  `/orchestrate` skill: orchestrator + 4 domain experts (Store & Backend,
  Extension, Testing, Documentation) via Claude Code Agent tool. Parallel
  execution, two modes (implementation + review). ADR-0019 documents
  architecture. [RFC](rfcs/rfc-0009-multi-agent-orchestration.md).

- [x] **BK-124a — Codify testing rules in `sdd/TESTING.md`**
  8 testing quality rules extracted from
  [research-testing-best-practices](research/research-testing-best-practices.md)
  and formalized as an authoritative process doc. Enforcement tags
  (`[CI-enforced]` / `[review-enforced]`), good-vs-bad examples, and
  Testing Expert quick reference table for BK-125. Cross-referenced from
  DESIGN.md § 11 and CLAUDE-REFERENCE.md.

- [x] **BK-015 — Replace mypy `ignore_missing_imports` overrides with proper type stubs**
  Added `types-requests` stub, removed overrides for `requests`, `urllib3`,
  `pydantic`, `pydantic_settings`, `tomli`, `tomllib`, `httpx`, `ruamel.yaml`.
  Cleaned up now-unnecessary `type: ignore` comments in HTTP transport modules.
  Keep: `dagster` (no `py.typed`, no stubs). PR #293.

- [x] **BK-001 — Audit workflow and bug-fix protocol**
  Added `/audit` skill (scope-first, report-only), bug-fix protocol
  (backlog → changelog → failing test → fix), ripple-check row,
  process rule. PR #288.

## Bug Fixes

- [x] **BUG-005 — SFTP TOFU host key not persisted when known_hosts absent**
  `TRUST_ON_FIRST_USE` now persists accepted host keys to disk on disconnect.
  Creates the known_hosts file and parent directories if absent. Inline keys
  (code/config/env) are never persisted. Spec SFTP-028.

- [x] **BUG-006 — Cache coherency in move/copy operations**
  `CachedStore.move()` and `CachedStore.copy()` now clear the entire cache
  to prevent stale cached entries for nested paths that are relocated or
  overwritten. Previously only invalidated source/destination paths, missing
  nested paths (e.g., `dst/file.txt`). Now consistent with `delete_folder()`
  safety strategy. Spec CACHE-010 updated.

## Benchmarks & Performance

- [x] **ID-104 — S3-PyArrow comparison chart, overhead-vs-RTT, benchmark tooling**
  S3-PyArrow in comparative charts/reports with boto3 baseline. New S3 vs
  S3-PyArrow comparison chart. Overhead-vs-RTT chart with real multi-profile
  data. Performance messaging rewrite (numbers, not judgment). `--file` flag
  for `report.py` and `charts.py`. Raw SDK targets for latency backends.
  Network profile metadata in saved JSON. `bench-latency-matrix` command.
  - [x] Performance messaging rewrite (PR #273)
  - [x] Charts, `--file` flag, latency raw SDK targets (PR #274, 4 review rounds)
  - [x] Regenerated SVGs + updated text with run 0022 numbers (PR #275)
  - [x] Fix S3-PyArrow messaging: analytical workloads, not
    high-throughput (PR #276)

- [x] **ID-103 — Benchmark suite v2: user-decision framing**
  Expand Toxiproxy to all Docker backends, generate overhead charts,
  reframe performance guide for user decisions, add README performance
  section.
  - [x] [Research](research/research-benchmark-suite-v2.md) (PR #263)
  - [x] Phase 1: Toxiproxy expansion (docker-compose, fixtures, profiles) (PR #267)
  - [x] Phase 2: Chart generation + "worth it?" verdicts in reporting (PR #268)
  - [x] Phase 3: README section + performance guide reframe (PR #268)
  - [x] Phase 4: seekable_read() + cache hit/miss benchmarks (PR #270)

---

## Docs & DX

- [x] **ID-117 — S3Backend endpoint URL normalization**
  `S3Backend` and `S3PyArrowBackend` accept bare `host:port` for
  `endpoint_url` and auto-prefix with `https://`. Shared
  `_normalize_endpoint_url()` helper in `_s3_base.py`.
  Spec S3-025 / S3PA-023.

- [x] **ID-113 — Documentation: S3 listing strategies and performance**
  Comprehensive guide added to `guides/backends/s3.md` explaining shallow vs.
  recursive listing trade-offs, why flat `ListObjectsV2` streams beat
  delimiter-based folder iteration, and why parallelization is wrong for large
  buckets. Includes performance data from benchmark suite and practical examples.
  New example file `examples/backends/s3_listing_strategies.py` demonstrates shallow,
  recursive, and filtered listing patterns.

- [x] **BUG-004 — Snippet indentation leaks into docs code blocks**
  pymdownx.snippets extracts named regions verbatim; regions inside
  function bodies carry 4–8 spaces of indentation into rendered docs.
  Fix: enable `dedent_subsections: true` in pymdownx.snippets config.
  Affects `homepage.py` (4 regions) and `core_operations.py` (3 regions).

---

## Streaming & I/O

- [x] **ID-102 — Azure PyArrow column pruning via seekable range reads**
  `Store.read_seekable()` + `_AzureRangeReader` (HTTP Range per `readinto()`)
  enables Parquet column pruning on Azure without full-file download. 2–17x
  speedup for selective reads on 10 MB+ files. Arrow adapter Tier 3 uses
  `read_seekable()` for files above the materialization threshold.
  - [x] [Research](research/research-azure-pyarrow-optimization.md) (PR #260)
  - [x] Phase 1: `_AzureRangeReader`, `Store.read_seekable()`, spec 036,
    ADR-0017, arrow integration (PR #262)
  - [x] Phase 2: Benchmarks — column pruning, batch reads, dataset scans.
    `PythonFile` overhead acceptable. Phases 3–4 not needed.
    ([Verdict](research/research-azure-pyarrow-optimization.md#9-phase-2-verdict-real-workload-benchmarks))
  - Deferred: C++ Tier 1 via `pyarrow.fs.AzureFileSystem` — see
    [ID-105](BACKLOG.md#integrations).

- [x] **ID-100 — Seekable read capability + extension**
  `Capability.SEEKABLE_READ` flag for backends that always return seekable
  streams (Local, Memory, S3, S3-PyArrow, SFTP). `ext.seekable.seekable_read()`
  portable wrapper with `SpooledTemporaryFile` fallback for non-seekable
  backends (Azure, HTTP). ADR-0016, spec 036.

---

## API Surface

- [x] **ID-118 — Certificate bundle handling (S3, Phase 1)**
  Dedicated `tls_ca_bundle: str | None` parameter on `S3Backend` and
  `S3PyArrowBackend`. Env var fallback chain (`AWS_CA_BUNDLE` >
  `REQUESTS_CA_BUNDLE` > `SSL_CERT_FILE`), early path validation,
  `setdefault` injection for backward compat. Spec 039.
  Phase 2 (Azure) deferred as ID-118b.

- [x] **ID-112 — Non-recursive `get_folder_info` optimization**
  Added `max_depth` parameter to `Store.get_folder_info()`. When set,
  aggregates stats using `list_files(max_depth=N)` at the Store level
  instead of the backend's full recursive traversal. `CachedStore` and
  `ObservedStore` forward the parameter. No Backend ABC change. Spec 038.

- [x] **ID-107b — `Backend.list_files(max_depth=N)` native optimization**
  Added optional `max_depth` kwarg to `Backend.list_files()` ABC. Native depth
  limiting in Local (`os.walk()` depth counter), SFTP (recursive call depth
  tracking), Memory (DFS stack depth). S3/Azure/HTTP accept the parameter but
  rely on Store-level client-side filter. Store passes `max_depth` through to
  backend; client-side filter remains as safety net. Spec 037 (DEPTH-003).

- [x] **ID-107 — `Store.list_files(max_depth=N)` with client-side filtering**
  Added `max_depth` parameter to `Store.list_files()`. When set, `recursive`
  is ignored. Client-side depth filtering at Store level via path component
  count. No Backend ABC change. Spec 037 (DEPTH-001).

- [x] **ID-108 — `Store.list_folders(max_depth=N)` with BFS traversal**
  Added `max_depth` parameter to `Store.list_folders()`. BFS using
  `Backend.list_folders()` at each level. `max_depth=None`/`0` returns
  immediate children (unchanged default). No Backend ABC change.
  Spec 037 (DEPTH-002).

- [x] **ID-101 — Add ProxyStore to API reference**
  Exported `ProxyStore` from `remote_store`, added API reference page
  (`docs-src/api/proxy.md`), rewrote docstrings for extension authors.
  ProxyStore remains an internal delegation base by design (ADR-0014)
  but is documented because it is visible in the inheritance chain and
  useful for custom extensions. PR #258.

---

## SDD Housekeeping

- [x] **ID-099 — Consolidate SDD document categories from 7 to 5**
  Merged `proposals/` → `rfcs/` (renamed to rfc-0005, rfc-0006, rfc-0007 with
  accepted status), `plans/` → `research/` (docs landing page plan renamed;
  HTTP backend plan merged into existing research doc § 20). Removed completed
  fix-list (`audits/fix-docs-structural-issues.md`). Added Document Types table
  to `000-process.md`. Updated all cross-references in BACKLOG-DONE.md,
  CLAUDE-REFERENCE.md, DOCUMENTATION.md. PR #252.

---

## Test Suite Refactoring

- [x] **BK-014 — Test code deduplication and parametrization**
  Aggressive refactoring of the test suite (~17,800 → ~16,300 lines, −8.6%)
  while maintaining identical coverage (1866 passed, 170 skipped).
  Applied across 30 of 40 test files.
  - Parametrized similar tests (error mapping, validation, operation variants)
  - Extracted shared fixtures and factory helpers (`_make_backend`, etc.)
  - Merged single-method test classes into parent classes
  - Consolidated repeated assertion patterns
  - Addressed audit M-13: reviewed `test_coverage_gaps.py` for pure-import assertions
  Key files with largest reductions: `test_config.py` (−26%), `test_batch.py` (−24%),
  `test_cache.py` (−23%), `test_coverage_gaps.py` (−23%), `test_examples.py` (−15%),
  `test_s3.py` (−14%), `test_arrow.py` (−12%).

---

## Documentation Tooling

- [x] **ID-106 — "Build Your Own Backend" guide**
  Step-by-step tutorial showing how to implement the Backend protocol, using
  a Redis backend as the running example. Covers capabilities, error mapping,
  listing, metadata, registry integration, and extension compatibility.
  Tested snippet file with 17 named regions. API ref links throughout.
  Cross-link from CONTRIBUTING.md.
  - [x] Guide, snippets, docs wiring (PR #277)

- [x] **ID-057 — Tested code snippets in docs (single-source snippets)**
  Created `examples/snippets/` with named regions using pymdownx.snippets'
  `# --8<-- [start:name]` / `# --8<-- [end:name]` syntax. Two snippet files
  (`homepage.py`, `core_operations.py`) replace hand-written fences in
  `docs-src/index.md`. Snippet scripts run as part of `hatch run examples`;
  `tests/test_snippets.py` verifies they execute. CI guarantees docs code
  blocks stay in sync with the actual API. Note: the S3Backend
  "backend-switching" example on the homepage remains inline because
  `S3Backend` cannot be instantiated without real credentials; this block
  is not CI-tested by design.
  [Research](research/research-example-testing.md).

- [x] **ID-058 — Auto-generate example docs wrappers via mkdocs-gen-files**
  Extended `scripts/gen_pages.py` to scan `examples/*.py` and
  `examples/backends/*.py`, extract module docstrings, and generate
  `docs-src/examples/<slug>.md` wrappers + `index.md` + nav entries
  automatically. Deleted 28 hand-maintained wrapper files and the static
  `_nav.yml`. Medallion showcase handled as special case (README inlined).
  Added `tests/test_api_coverage.py` CI check verifying every `__all__`
  symbol has a `:::` directive in `docs-src/api/` and every core symbol
  appears in `docs-src/api/index.md`.

---

## Documentation Cross-Linking

- [x] **BK-013 — Documentation cross-link compliance**
  Enforced DOCUMENTATION.md § 4 cross-linking rules across all ~64 docs pages.
  All additive, no code changes.
  [RFC](rfcs/rfc-0007-doc-cross-links.md).
  - Phase 1a: Core example pages — add `## See also` (10 pages)
  - Phase 1b: Backend example pages — add `## See also` (6 pages)
  - Phase 1c: Extension + showcase example pages — add `## See also` (11 pages)
  - Phase 2a: Core + extension API ref pages — add `## See also` (23 pages)
  - Phase 2b: Backend API ref pages — convert to `## See also` (7 pages)
  - Phase 3: Link plain-text names in table headers/key columns (6 files)
  - Phase 4: Add Rule 4 to DOCUMENTATION.md § 4

---

## Naming & Consistency

- [x] **BK-012 — Code deduplication Phases 2--4**
  `_StreamWrapper` base class in `ext/streams.py` (eliminates 56 lines of
  repeated context-manager/close/getattr boilerplate).  Generic `_run_batch()`
  executor in `ext/batch.py` (consolidates sequential/concurrent scaffolding).
  `_deprecated_alias()` helper in `ext/_helpers.py` (replaces 3 hand-written
  deprecation wrappers).  `_require_extra()` dropped — ruff E402 cascade made
  it impractical.  [RFC](rfcs/rfc-0005-code-deduplication.md).  PR #243.

- [x] **BK-011 — S3 backend deduplication (Phase 1)**
  Extract shared listing, error handling, and FileInfo construction from
  `_s3.py` and `_s3_pyarrow.py` into `_S3Base` base class
  (`backends/_s3_base.py`).  Add FileInfo helpers (`backends/_fileinfo.py`)
  and error factories (`_not_found`, `_permission_denied`,
  `_classify_by_message` in `_errors.py`).  Net -94 lines, single
  maintenance point for 155 previously duplicated lines.
  [RFC](rfcs/rfc-0005-code-deduplication.md).  PR #242.

- [x] **BK-010 — Naming consistency: rename ext factory functions**
  Renamed three public factory functions for naming consistency:
  `pydantic_to_registry_config` → `from_pydantic`, `remote_store_io_manager` →
  `dagster_io_manager`, `cached_store` → `cache`. Old names kept as deprecated
  aliases emitting `DeprecationWarning`. All specs, guides, examples, migration
  guide updated. [RFC](rfcs/rfc-0006-naming-inconsistencies.md). PR #241.

## Middleware Path 1 (Post-v0.17.0)

- [x] **ID-090 — Docs landing page (replace README include)**
  Replaced the `README.md` include with a purpose-built landing page:
  architecture diagram, six key messages (Store-as-folder, zero deps, proven
  libs, backend-native API, extensions alongside, bring your own), quick start,
  and navigation links. Diagram rework (flowchart → architecture-beta) deferred.
  [Research](research/research-docs-landing-page.md).

- [x] **ID-006 — Progress tracking via stream wrappers (`ext.streams`)**
  `ext.transfer.download()` now uses `ProgressReader` wrapper for progress
  tracking, consistent with `upload()` and `transfer()`. Replaces inline
  callback. Spec 017 §XFER-009, Spec 033.

- [x] **ID-098 — S3 backend: populate `FileInfo.digest` from `x-amz-checksum-*`**
  `get_file_info` now calls `HeadObject` with `ChecksumMode: ENABLED`
  unconditionally, returning both metadata and any checksum headers in a single
  request. The base64-encoded checksum is decoded to hex and wrapped in a
  `ContentDigest`. Listing paths (`list_files`, `iter_children`) still return
  `digest=None` to avoid per-file overhead. Spec 008 §S3-024.

- [x] **ID-097 — Azure backend: populate `FileInfo.etag` and `digest`**
  `_props_to_fileinfo` now populates `etag` from `BlobProperties.etag`
  (stripped/lowercased) and `digest` from `content_settings.content_md5`
  when present (bytes → lowercase hex → `ContentDigest("md5", value)`).
  Spec 012 §AZ-034.

- [x] **ID-096 — S3 backend: populate `FileInfo.etag`** (partial; see ID-098 for digest)
  `_info_to_fileinfo` now populates `etag` from the `ETag` key in the s3fs
  info dict (stripped/lowercased). Digest via `x-amz-checksum-*` is deferred
  — it requires `ChecksumMode: ENABLED` on HeadObject, which s3fs does not
  issue by default. Spec 008 §S3-023.

- [x] **ID-095 — `ContentDigest` model + `FileInfo.digest`/`etag` fields**
  `ContentDigest` frozen dataclass (`algorithm: str`, `value: str` — both
  lowercase-normalized, validated). `FileInfo.checksum` replaced with
  `FileInfo.digest: ContentDigest | None` and `FileInfo.etag: str | None`.
  `ext.integrity.content_digest()` function added. Spec 035.

- [x] **BUG-003 — `child()` now propagates proxy behavior in ObservedStore/CachedStore**
  `ObservedStore.child()` and `CachedStore.child()` now return wrapped
  stores that preserve observation/caching behavior. Previously, child
  stores silently lost all middleware. Fixed via `_wrap_child()` in
  `ProxyStore` base class.

- [x] **ID-094 — Extract ProxyStore base class**
  Shared delegation base for `ObservedStore` and `CachedStore` in
  `_proxy.py`. Centralizes `_backend`/`_root`/`_owns_backend` coupling,
  provides default delegation for all 27 Store methods, enables `child()`
  propagation via `_wrap_child()`. ADR-0014.

- [x] **ID-008 — Checksum verification on read/write**
  Verification functions (`ext.integrity`, ID-093), stream wrappers
  (`ext.streams`, ID-092), `ContentDigest` model (ID-095),
  S3 etag population (ID-096), and Azure etag/digest population (ID-097).

- [x] **ID-093 — `ext.integrity` module — checksum verification helpers**
  `checksum()`, `verify()`, `verify_hex()`. Pure functions over
  Store's public API. Spec 034.

- [x] **ID-092 — `ext.streams` module — stream-level wrappers**
  `ProgressReader`, `ProgressWriter`, `ChecksumReader`, `ChecksumWriter`,
  `read_with_progress()`. Composable `BinaryIO` wrappers. Spec 033.

- [x] **ID-091 — Refactor `ext.transfer` to use public `ProgressReader`**
  Replaced private `_ProgressReader` with `ProgressReader` from
  `ext.streams`. No public API change.

---

## Post-v0.17.0

- [x] **ID-085 — HTTP backend: HEAD fallback for CDN-blocked servers**
  When `HEAD` returns 401/403, `exists()`, `get_file_info()`, and
  `check_health()` retry with `GET` + `Range: bytes=0-0` (single byte).
  On success, the backend caches that HEAD is blocked for its lifetime.
  `_build_file_info` extracts total size from `Content-Range` header.
  Spec HTTP-FALLBACK-001, 11 new tests, guide updated with CDN section.
  Depends on: ID-082.

- [x] **BK-009 — Fix slow local test suite (IPv6 dual-stack + HTTP server lifecycle)**
  Local test suite took ~2:41 due to two HTTP-related bottlenecks:
  (1) pytest-httpserver defaulted to `localhost` which triggers IPv6 dual-stack
  timeout on Windows (~2 s per urllib request); fixed by overriding
  `httpserver_listen_address` to `("127.0.0.1", 0)`.
  (2) Conformance HTTP backend started/stopped a new server per test (~0.5 s
  teardown each); fixed by adding a session-scoped `http_server` fixture.
  Result: 161 s → 37 s (4.3x speedup), no test changes needed.

- [x] **ID-089 — Extensions API reference section**
  Moved all 11 extension API pages into a nested "Extensions" section under
  the API reference, with an index page and summary table. Updated cross-links
  from 7 guide pages. Matches the Backends section structure from ID-088.

- [x] **ID-087 — Speed up macOS & Windows CI test runs**
  Replaced the broad `pytest -m "not requires_docker"` filter with a focused
  `@pytest.mark.os_sensitive` marker. Tests that exercise OS-specific behaviour
  (path separators, `os.replace` atomicity, `tempfile`, local filesystem) are
  marked at module level (`test_path.py`, `test_open_atomic.py`, `test_glob.py`,
  `backends/test_local.py`) or at fixture-param level (`local` and `memory`
  params in `backends/conftest.py`, propagating to the full conformance suite
  for those backends). macOS and Windows CI now run only `-m os_sensitive`.
  Network-protocol backends (HTTP, S3, SFTP) have no OS-specific behaviour and
  are Linux-only. Ripple-check guidance added to `sdd/CLAUDE-REFERENCE.md`.

- [x] **ID-088 — Backend classes in API reference**
  Added class documentation for all 7 backends (Local, Memory, HTTP, S3,
  S3-PyArrow, SFTP, Azure) under a new "Backends" section in the API reference.
  Each page: hand-written intro linking to the backend guide, then mkdocstrings
  `:::` directive with `show_bases: false`. Backends index page with summary
  table. Old standalone `http-backend.md` removed.

- [x] **BK-008 — Medallion + Dagster showcase implementation**
  Self-contained Dagster project in `examples/medallion_dagster/`
  demonstrating 4 extensions composing over live MeteoSwiss data
  (Bronze/Silver/Gold medallion architecture).
  Uses `ReadOnlyHttpBackend`, `ext.cache`, `ext.otel`,
  and `ext.dagster`.
  [Showcase architecture](research/research-medallion-dagster-showcase.md),
  [docs page](../docs-src/examples/medallion-dagster.md).

- [x] **ID-082 — Read-only HTTP backend (`ReadOnlyHttpBackend`)**
  7th backend: read-only access to HTTP/HTTPS URLs with `{READ, METADATA}`
  capabilities. [Spec 032](specs/032-http-backend.md), 3 transports
  (urllib/requests/httpx), streaming adapters (`_HttpxStreamAdapter`,
  `_Urllib3StreamAdapter`), conformance suite capability gates, 85 tests,
  [guide](../guides/backends/http.md), [example](../examples/http_backend.py),
  API docs. 4 review rounds (31 threads). Resource leak fix, thread-safety
  docs, CI coverage floor adjustment (90% non-primary, 95% primary).
  [Research](research/research-readonly-http-backend.md) (§ 20: implementation plan).
  Lesson learned: research and initial estimation significantly underestimated
  complexity — transport abstraction, streaming adapters, error mapping across
  3 HTTP libraries, CDN edge cases, and conformance suite changes made this
  ~2,700 lines across 32 files, far beyond the initial "simple read-only
  wrapper" estimate.
  Follow-up: ID-085 (HEAD fallback for CDN-blocked servers).

- [x] **BK-007 — Docs quick fixes: dashes, See also, table booleans, SFTP blockquotes**
  All 20 items from the Audit 004 fix list resolved:
  AF-041 (`--` → `—` across 33 files), AF-042 (See also unified to Pattern B),
  AF-043 (table booleans to `Yes` / `—`), AF-044 (SFTP blockquotes → admonitions),
  AF-046 (extensions table disambiguation), AF-047/048 (Installation stubs),
  AF-049 (`!!! tip` accepted as intentional). Added `.editorconfig` (UTF-8, LF).
  Supersedes ID-086 (all T-16 through T-20 resolved here).

- [x] **ID-086 — Docs structural harmonization** — superseded by BK-007 above.

- [x] **BUG-001 — `pydantic_to_registry_config()` fails to wrap `SecretStr` in `Secret`**
  `model_dump()` returns `SecretStr` objects (not a `str` subclass), which
  bypassed `from_dict()`'s `isinstance(v, str)` check. Added
  `_unwrap_secret_strs()` helper to convert `SecretStr` → `str` in backend
  options before `from_dict()`. Spec CFG-015 updated.

- [x] **ID-084 — Drop optional-extension re-exports from `__init__.py` (ADR-0013)**
  Removed `try/except ImportError` re-export blocks for arrow, otel, pydantic,
  and yaml extensions from `remote_store/__init__.py`. Each extension is now
  imported only from `remote_store.ext.<name>`. Eliminates import-time overhead
  from heavy optional deps (e.g. Dagster ~2-5 s). Pure-Python extensions
  unchanged. ADR-0013, migration guide entry, CHANGELOG entry.

- [x] **ID-075 — Dagster integration v1 (`ext.dagster`)**
  Thin Dagster IO manager adapter: `remote_store_io_manager(store)` factory,
  serializers (pickle, JSON, Parquet), [spec 031](specs/031-ext-dagster.md)
  (DAG-001 -- DAG-011), tests, guide, docs wiring.
  v2 tracked as ID-083.
  [Research](research/research-dagster-extension.md).

- [x] **ID-081 — README medium pass: trim density, add backend behavior matrix**
  Streamlined onboarding flow: trimmed duplicate explanations, added backend
  comparison matrix, restored correct extras list, fixed method count (27).

- [x] **ID-064 — Docs site enhancements (colored types, Material features, Fira Code)**
  Applied findings from [research](research/research-fastapi-docs.md).
  P1: `separate_signature`, `signature_crossrefs`, `show_symbol_type_heading`,
  `show_symbol_type_toc`. P3: Fira Code font via `extra_css`. P4: `navigation.tabs.sticky`,
  `search.suggest`, `search.highlight`. Also added `show_signature_annotations` for
  property return type visibility.

- [x] **ID-080 — Migrate docstrings from Sphinx to Google style**
  Converted 367 Sphinx markers across 25 files to Google-style sections.
  Updated `mkdocs.yml` (`docstring_style: google`) and `sdd/DESIGN.md` §4.
  [Research](research/research-google-docstring-migration.md).

- [x] **ID-062 — Remove redundant `exists()` guard from S3 listing methods**
  Removed `exists()` pre-check from `list_files`, `list_folders`, and
  `iter_children` in S3Backend and S3PyArrowBackend. Halves API calls
  for listing operations.

- [x] **ID-076 — AzureBackend `max_concurrency` parameter**
  Added `max_concurrency: int = 1` constructor parameter to `AzureBackend`.
  Threaded through to `upload_blob()`, `download_blob()`, and HNS
  `upload_data()` calls. [Spec AZ-033](specs/012-azure-backend.md).

- [x] **ID-079 — FolderInfo.name property and PathEntry protocol notes**
  Added `name` property to `FolderInfo` so it satisfies `PathEntry`
  alongside `FileInfo` and `FolderEntry`.

- [x] **ID-080b — Document lazy-import pattern for mixed optional deps**
  Superseded by ADR-0013: optional-dependency extensions are no longer
  re-exported from `__init__.py` at all.

- [x] **ID-071 — Store API refinement: Phase 1**
  Subsumed by ID-074. Kept for traceability.
  [Research](research/research-store-api-refinement.md).

## v0.17.0

- [x] **ID-072 — Store API refinement: listing normalization (Option D)**
  `list_folders()` returns `Iterator[FolderEntry]`, `iter_children()` returns
  `Iterator[FileInfo | FolderEntry]`. Added `FolderEntry` dataclass and
  `PathEntry` protocol. All 6 backends updated.
  [Research](research/research-store-api-refinement.md).

## v0.16.0

- [x] **ID-078 — Document Store at a new root**
  Added docstring note on `Store` class and admonition in
  `docs-src/api/store.md`.

- [x] **ID-077 — Switch docstring rendering from tables to lists**
  Changed `docstring_section_style` to `list` in mkdocstrings config.

- [x] **ID-074 — Store API refinement (pre-v1 audit)**
  Systematic pre-v1 audit of the Store public API. Rewrote all Store
  docstrings, implemented `write_text()`, restructured `store.md` with
  per-method `:::` directives, built backend behavior matrix.
  Subsumes ID-071 Phase 1.

- [x] **ID-073 — Use uv as hatch installer backend**
  Set `installer = "uv"` in `[tool.hatch.envs.default]`. ~10x faster
  env creation.

- [x] **ID-063 — `write_text()` convenience method**
  Shipped as part of ID-074.

## v0.15.0

- [x] **ID-056 — `read_text()` convenience method**
  [Spec 028](specs/028-read-text.md) (RTXT-001 -- RTXT-006).

- [x] **ID-055 — `iter_children()` — combined file + folder listing**
  [Spec 027](specs/027-iter-children.md) (ITER-001 -- ITER-008).

- [x] **ID-025 — `ext.cache` — store-level caching middleware**
  `cached_store(store, ttl=300)`. Auto-invalidation on writes/deletes/moves/copies.
  [Spec 023](specs/023-ext-cache.md) (CACHE-001 -- CACHE-015). 52 tests.

- [x] **ID-035 — Parallel batch operations**
  `concurrent=True` and `max_workers=N` on batch operations.
  [Spec](specs/016-ext-batch.md) BATCH-020 -- BATCH-025. 20 new tests.

- [x] **ID-036 — Hive-style partition path helpers**
  `partition_path()` and `parse_partition()`.
  [Spec 024](specs/024-ext-partition.md) (PART-001 -- PART-013). 23 tests.

- [x] **ID-048 — Verify notebook examples in CI**
  `tests/scripts/run_notebooks.py` executes notebook code cells via `exec()`.

- [x] **ID-026 — Streaming atomic writes**
  `Store.open_atomic()` and `Backend.open_atomic()`.
  [RFC-0004](rfcs/rfc-0004-streaming-atomic-writes.md),
  [spec 022](specs/022-streaming-atomic-writes.md) (SAW-001 -- SAW-015).

- [x] **ID-037 — PyArrow adapter Phase 2 — Tier 1 native fast-path reads**
  `Backend.native_path()` (BE-025), `Store.native_path()` (STORE-015).

- [x] **ID-038 — Re-run comparative benchmarks post-cache-invalidation fix**

- [x] **DOC-001 — Documentation overhaul per Documentation Master**
  Full Diataxis restructure of the docs site (Phase 1--7).

## v0.14.0

- [x] **ID-002 — YAML config support** (moved to `ext/yaml.py` post-v0.15.0)
  [Spec 021](specs/021-config-loaders.md) (CFG-010/CFG-011).

- [x] **ID-003 — Pydantic BaseSettings integration**
  [Spec 021](specs/021-config-loaders.md) (CFG-015 -- CFG-017).

- [x] **ID-005 — Built-in `from_toml()` config loader**
  [Spec 021](specs/021-config-loaders.md) (CFG-008/CFG-009).

- [x] **ID-034 — Parquet lake guide (Bronze / Silver / Gold patterns)**

- [x] **ID-040 — `move(src, dst)` and `copy(src, dst)` same-path consistency**
  Spec: STORE-008a.

- [x] **ID-041 — `Registry.get_store()` backend ownership foot-gun**
  `get_store()` now sets `_owns_backend = False`.

- [x] **ID-042 — Document Secret usage in README and examples**

- [x] **ID-043 — Remove `_stacklevel` from public `from_dict()` signature**

- [x] **ID-046 — Audit version-conditional imports for mypy coverage**

- [x] **ID-047 — Spec accuracy fixes**

- [x] **BK-005 — SFTP backend test coverage gaps**
  Coverage improved from 90% to 100%. 35 new tests.

- [x] **BK-006 — Memory backend test coverage gaps**
  Coverage improved from 90% to 100%. 30 new tests.

## v0.13.0

- [x] **ID-004 — Structured logging & metrics hooks**
  Superseded by ID-024.

- [x] **ID-024 — `ext.observe` — hooks / middleware / instrumentation**
  [ADR-0010](adrs/0010-observe-hooks-middleware.md),
  [spec 019](specs/019-ext-observe.md) (OBS-001 -- OBS-014).

- [x] **ID-039 — Credential hygiene: `Secret` wrapper and central redaction**
  [Spec 020](specs/020-credential-hygiene.md) (SEC-001 -- SEC-008).

## v0.12.0

- [x] **ID-007 — `Store.glob()` surface API**
  [ADR-0009](adrs/0009-glob-three-tier-design.md),
  [spec 018](specs/018-glob.md).

- [x] **BK-002 — Glob / pattern matching strategy**
  Related: ID-007.

- [x] **ID-032 — Fix listing benchmark fixture caching**
- [x] **ID-033 — Cloud benchmark quick tier timing budget**

## v0.10.0

- [x] **ID-020 — Benchmark tiered modes and single-backend filtering**
- [x] **ID-027 — Extension architecture (`ext.*` namespace)**
  [ADR-0008](adrs/0008-extension-architecture.md).
- [x] **ID-028 — Release-triggered publish and docs deploy**
  Subsumes AF-014.
- [x] **ID-029 — Versioned documentation (mike + RTD tags)**
- [x] **ID-031 — S3-PyArrow read path optimization**
  [RFC-0003](rfcs/rfc-0003-s3-pyarrow-read-optimization.md).

## v0.9.0

- [x] **ID-001 — Cross-store transfer** *(subsumed by ID-023)*
- [x] **ID-009 — `Store.upload()` / `Store.download()`** *(subsumed by ID-023)*
- [x] **ID-015 — Audit external deep links**
- [x] **ID-016 — PyArrow FileSystemHandler adapter (Phase 1)**
  [RFC-0002](rfcs/rfc-0002-pyarrow-filesystem-adapter.md),
  [spec 014](specs/014-pyarrow-filesystem-adapter.md). 89 tests.
- [x] **ID-019 — Update stale CAP-001 in spec 003**
- [x] **ID-022 — `ext.batch` — batch operations**
  [Spec 016](specs/016-ext-batch.md).
- [x] **ID-023 — `ext.transfer` — cross-store and local-path transfers**
  [Spec 017](specs/017-ext-transfer.md).

## v0.8.0

- [x] **ID-021 — `Store.child(subpath)` — runtime sub-scoping**
  [Spec 015](specs/015-store-child.md).
- [x] **ID-030 — Claude Code reusable skills**
- [x] **DONE-005 — Reorganize examples into core + backends groups**

## v0.7.0

- [x] **ID-017 — Memory backend**
- [x] **AF-008 — Add credential masking to backend `__repr__`**
- [x] **AF-009 — Fix `Registry.close()` to close all backends on error**
- [x] **AF-011 — Remove dead `RemoteFile`/`RemoteFolder`**
- [x] **AF-015 — Update stale v0.5.0 docs**

## v0.6.0

- [x] **AF-001 — Auto-register S3/SFTP/S3-PyArrow in Registry**
- [x] **AF-002 — Remove GLOB/RECURSIVE_LIST ghost capabilities**
- [x] **AF-003 — Fix `S3Backend.close()` global cache side effect**
- [x] **AF-004 — Unify `get_folder_info` on empty folders**
- [x] **AF-005 — Fix `delete_folder` error types**
- [x] **AF-006 — Fix native exception leakage through lazy streams**
- [x] **AF-007 — Wire Azure backend into docs site**

## v0.5.0

- [x] **BK-001 — Azure backend**
  [RFC-0001](rfcs/rfc-0001-azure-backend.md),
  [spec 012](specs/012-azure-backend.md).
- [x] **ID-012 — Performance benchmarks**
- [x] **DONE-004 — S3-PyArrow hybrid backend**
  [Spec 011](specs/011-s3-pyarrow-backend.md).

## v0.4.x

- [x] **ID-014 — Streaming conformance tests** (v0.4.4)
- [x] **ID-011 — Python 3.14 support** → graduated to BK-004
- [x] **DONE-001 — PEP 604 type hints**

## v0.3.0

- [x] **BK-003 — Native path resolution (`to_key`)**
  [Spec 010](specs/010-native-path-resolution.md).
- [x] **BK-004 — Python 3.14 support** (graduated from ID-011)
- [x] **BL-001 — PyPI publish workflow**
- [x] **BL-002 — SFTP backend documentation**
- [x] **BL-003 — README backends table outdated**
- [x] **BL-004 — README & project description tone rework**
- [x] **BL-005 — CITATION.cff**
- [x] **BL-006 — Protect master branch with ruleset**
- [x] **BL-007 — Pin minimum dependency versions & clean up extras**
- [x] **BL-008 — Set up docs hosting**
- [x] **BL-009 — Fix broken PyPI logo and badges**
- [x] **BL-010 — Publish documentation to Read the Docs**

## Post-release housekeeping

Items that shipped outside a version bump, newest first.

- [x] **ID-070 — Add third-party doc links in extension module docstrings**
- [x] **ID-069 — Automated Claude PR review workflow** (reverted)
- [x] **ID-068 — Replace `dorny/paths-filter` with bash path filtering**
- [x] **ID-065 — Use uv in docs deployment workflow**
- [x] **ID-061 — Use uv for CI dependency installs**
- [x] **ID-060 — Multi-platform CI (Linux, Windows, macOS)**
- [x] **ID-059 — Restructure authoritative docs to ADF standard**
- [x] **ID-054 — `store.ping()` / backend health check**
  [Spec 026](specs/026-health-check.md).
- [x] **ID-053 — Fix code block highlighting in docs**
- [x] **ID-052 — Custom domain: remotestore.dev**
- [x] **ID-051 — Sweep stale backlog references in docs and guides**
- [x] **ID-050 — End-to-end integration tests against Docker backends**
- [x] **ID-049 — Enable GitHub Vigilant Mode**
- [x] **ID-045 — Fill example coverage gaps for specs 003, 004, 020, 021**
- [x] **ID-044 — Harden examples into assertion-based expectation tests**
- [x] **ID-010 — Retry policy configuration**
  [Spec 025](specs/025-retry-policy.md), [ADR-0011](adrs/0011-retry-policy.md).
- [x] **BUG-002 — Windows drive letter case mismatch in `warnings` module**
- [x] **BUG-001 — `get_folder_info("")` fails for empty-root stores**

## Audit findings

From [adversarial review](audits/audit-001-adversarial-review.md) (v0.5.0),
[design-compliance audit](audits/audit-002-design-compliance.md) (v0.13.0), and
[documentation audit](audits/audit-003-documentation.md) (v0.15.0).

- [x] **AF-010 — Document TOCTOU and non-atomic move limitations** (v0.9.0)
- [x] **AF-012 — Add capability gating tests (STORE-006)** (v0.9.0)
- [x] **AF-013 — Add PermissionDenied/BackendUnavailable error path tests** (v0.9.0)
- [x] **AF-014 — Add CI gate to publish workflow** (v0.9.0)
- [x] **AF-016 — Fix stale capability sections in specs** (v0.14.0)
- [x] **AF-017 — Add ID-043 to CHANGELOG** (v0.14.0)
- [x] **AF-018 — Correct BACKLOG version tags** (v0.14.0)
- [x] **AF-019 — Fix spec count in DEVELOPMENT_STORY.md** (v0.14.0)
- [x] **AF-020 — Fix §11.6 method ordering** (v0.14.0)
- [x] **AF-021 — Add backlog ID to unlinked TODO** (v0.14.0)
- [x] **AF-022 — 7 example scripts missing from docs-site nav**
- [x] **AF-023 — ObservedStore: proxy overrides lack docstrings** (resolved via config)
- [x] **AF-024 — CachedStore: proxy overrides lack docstrings** (resolved via config)
- [x] **AF-025 — CacheBackend protocol: 6 methods undocumented**
- [x] **AF-026 — 6 guides missing API reference links** (closed -- not a defect)
- [x] **AF-027 — `guides/retry.md` missing "See also" section**
- [x] **AF-028 — `guides/backends/index.md` sparse**
- [x] **AF-029 — `guides/performance.md` guide-style violations** (closed -- not a defect)
- [x] **AF-030 — Research nested 3 levels deep in nav** (closed -- not a defect)
- [x] **AF-031 — `transfer()` missing `:returns:` docstring**
- [x] **AF-032 — `guides/observe.md` on_write hook table omits `open_atomic`**
- [x] **AF-033 — `guides/observe.md` on_ping hook row missing**
- [x] **AF-034 — `observe()` docstring on_write omits `open_atomic`**
- [x] **AF-035 — `guides/cache.md` private import**
- [x] **AF-036 — `guides/health-check.md` private import**
- [x] **AF-037 — `guides/backends/sftp.md` private imports** (created SFTPUtils)
- [x] **AF-038 — `CONTRIBUTING.md` stale counts**
- [x] **AF-039 — `sdd/CLAUDE-REFERENCE.md` wrong path**
- [x] **AF-040 — `guides/migration.md` documents unreleased v0.16.0**
