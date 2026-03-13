# Development Backlog

Tracking file for prioritized work and unprioritized ideas.
Items graduate through the SDD pipeline: **Idea → Backlog → RFC/Spec → Tests → Code**.

Status legend: `[ ]` pending · `[~]` in progress · `[x]` done

Ordering: newest first within each section (see `sdd/000-process.md` § Backlog tiers).

---

## Backlog (Prioritized)

Active work items, ordered by priority.

### Feature work

*(none)*

### Ops / CI

*(none)*

---

## Known Bugs

*(none)*

---

## Ideas

### In Progress

Started but not yet prioritized for completion.

- [~] **ID-064 -- Docs site enhancements (colored types, Material features, Fira Code)**
  Apply findings from `sdd/research/research-fastapi-docs.md`.
  - Done: P1 -- added `separate_signature`, `signature_crossrefs`,
    `show_symbol_type_heading`, `show_symbol_type_toc` to mkdocstrings config.
  - Remaining: P3 (Fira Code font via `extra_css`), P4 (`navigation.tabs.sticky`,
    `search.suggest`, `search.highlight`).

- [~] **ID-018 — conda-forge publishing**
  Recipe, CI validation, release checklist steps all done.
  - Done: `packaging/conda-forge/recipe.yaml`, `conda-recipe.yml` workflow,
    staged-recipes PR `conda-forge/staged-recipes#32401` (CI green).
  - Remaining: waiting for conda-forge reviewer approval. Update recipe to
    v0.15.0 when approved.

- [~] **ID-013 — Async Store / Backend API**
  Async version of Store and Backend for async frameworks (FastAPI, aiohttp).
  - Done: research complete (`sdd/research/research-async-store-api.md`),
    ADR-0012 draft (`sdd/adrs/0012-async-store-backend-api.md`),
    spec 029 draft (`sdd/specs/029-async-store-backend-api.md`).
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

### Parking Lot

Not evaluated, not committed to. Pick up when relevant.

- [ ] **ID-076 — AzureConfig transfer concurrency (`max_concurrency`)**
  Expose `max_concurrency: int = 1` on `AzureConfig` (or as a per-call kwarg)
  and thread it through to `DataLakeFileClient.upload_data()` and
  `DataLakeFileClient.download_file()`. The Azure SDK supports parallel block
  uploads and parallel chunk downloads natively — today the parameter is
  silently left at its SDK default of 1 (sequential).

  **Context:**
  Research into dagster-azure (`dagster_azure/adls2/io_manager.py`) confirmed
  that no Dagster-native IO manager sets this parameter either — all fall back
  to the SDK default. Setting `max_concurrency=4` (or higher on wide hosts)
  would benefit all large-asset workloads without any API-surface change for
  users who don't configure it.

  **Proposed change:**
  ```python
  # AzureConfig
  transfer_concurrency: int = 1   # or 4 as an opinionated default

  # AzureBackend.write()
  file_client.upload_data(data, overwrite=True,
                          max_concurrency=self._cfg.transfer_concurrency)

  # AzureBackend.read() / chunks()
  downloader = file_client.download_file(
      max_concurrency=self._cfg.transfer_concurrency)
  ```

  **Scope:** `src/remote_store/backends/_azure.py`, `AzureConfig` dataclass,
  spec `sdd/specs/012-azure-backend.md`, Azure backend docs page.

  **Note:** SFTP has no equivalent (Paramiko is sequential by design);
  S3 concurrency is controlled via `s3fs` / `aiobotocore` at the fs level.
  This item is Azure-specific.

- [ ] **ID-075 — Dagster integration (`ext.dagster`)**
  Thin Dagster IO manager adapter for teams already using remote-store who
  adopt Dagster. Lets any existing `Store` serve as a Dagster IO manager
  with zero config duplication — no need to re-specify backend credentials
  in `dagster-aws` / `dagster-azure` alongside an existing remote-store setup.

  **Background:**
  Dagster already provides backend-specific IO managers (`dagster-aws`,
  `dagster-azure`, `dagster-gcp`) that handle S3/Azure/GCS portability
  natively. The gap this fills: teams that already have a configured
  remote-store `Store` (with credentials, retry policy, caching, observability)
  should not need to duplicate that config into Dagster-native IO managers.
  Additionally, Dagster has no native SFTP IO manager — remote-store covers
  that backend directly.

  **Scope (v1):** `remote_store_io_manager(store)` factory function only.
  Wraps any existing `Store` as a Dagster `IOManager` with pluggable
  serialisation (pickle, JSON, Parquet via `ext.arrow`). Caller owns Store
  lifecycle.

  **Scope (v2, deferred):** `DagsterStoreResource` — Dagster
  `ConfigurableResource` that constructs a `Store` from Dagster config fields.
  Targets Dagster-first users who don't already have a `Store`. Includes
  `teardown_after_execution()` for Store lifecycle management.

  **Dependencies:** `dagster>=1.9` (aligns with remote-store's Python 3.10+
  floor); optional `pyarrow>=14.0` for Parquet serialiser.

  **Packaging:** `ext/dagster.py` in-tree (consistent with `ext/arrow.py`,
  `ext/otel.py`); `pip install "remote-store[dagster]"`.

  **Maintenance note:** Dagster's API surface has high churn (renamed classes,
  metadata changes). v1 scope minimises exposure by wrapping only the stable
  `IOManager` base class. Floor at `dagster>=1.9`, not 1.7.

  Research: `sdd/research/research-dagster-extension.md`.

- [ ] **ID-006 — Progress callbacks for large transfers**
  Add an optional `callback: Callable[[int], None]` parameter to `read()` and
  `write()` reporting bytes transferred. Enables progress bars (e.g. `tqdm`)
  without adding dependencies. Note: `ext.transfer` (ID-023) provides
  `on_progress` for upload/download/transfer; this item covers the lower-level
  Store API.

- [ ] **ID-057 — Tested code snippets in docs (single-source snippets)**
  All code snippets in the docs site should come from real, tested Python
  source files — not hand-written markdown fences. One or more "snippet
  scripts" (e.g. `examples/snippets/`) contain named regions
  (`# snippet: quickstart-read` / `# end-snippet`). A mkdocs hook or
  `pymdownx.snippets` pulls regions into docs at build time. CI runs the
  snippet scripts as part of `hatch run all` to guarantee they stay valid.
  Inspired by Rust rustdoc, Go Example functions, Java `@snippet` tags.
  Research: `sdd/research/research-example-testing.md`.

- [ ] **ID-008 — Checksum verification on read/write**
  Add a `verify_checksum=True` option to `read()` / `write()`. Populate
  `FileInfo.checksum` consistently across backends (S3 ETag, local SHA-256).
  Gives users data-integrity guarantees with a single flag.

- [ ] **ID-058 — Auto-generate example docs wrappers via mkdocs-gen-files**
  Extend `docs-src/scripts/gen_pages.py` to scan `examples/*.py`, extract
  the module docstring, and generate `docs-src/examples/<name>.md` wrappers
  automatically. Eliminates the class of "forgot to add a wrapper" bugs
  (see AF-022, health-check.md used wrong include pattern).
  The existing API reference pages are already auto-generated this way.
  Each generated wrapper should also include links to relevant API reference
  pages at the bottom (e.g. caching example links to `ext.cache` reference).
  Also: add a CI/build-time check that every symbol in `__all__` (both
  `remote_store.__init__` and `remote_store.backends.__init__`) has a
  matching `:::` directive in `docs-src/api/*.md` and a row in
  `docs-src/api/index.md`. Prevents the class of miss where a public
  export (e.g. `SFTPUtils`, `RetryPolicy`) ships without API docs
  (see AF-037 follow-up).

- [ ] **ID-063 — `write_text()` convenience method**
  Symmetric to `read_text()`. `Store.write_text(path, text, encoding="utf-8",
  errors="strict", *, overwrite=False)` — thin wrapper around `.encode()` +
  `write()`. Lower priority since `store.write(path, text.encode())` is a
  trivial one-liner. Add if users request it.

- [ ] **ID-066 -- PR preview deployments**
  Deploy PR previews to Cloudflare Pages, Netlify, or GitHub Pages artifacts.
  Inspired by FastAPI's Cloudflare Pages pattern. Infrastructure decision needed.
  Research: `sdd/research/research-fastapi-docs.md` P6.

- [ ] **ID-067 -- griffe-typingdoc for `Annotated[T, Doc("...")]` docstrings**
  Only relevant if migrating from Sphinx-style docstrings to PEP 727
  `Annotated[T, Doc("...")]`. Not recommended near-term.
  Research: `sdd/research/research-fastapi-docs.md` P5.

- [~] **ID-071 — Store API refinement: Phase 1 docstring fixes, `write_text()`, docs gaps**
  Subsumed by **ID-074**. Kept for traceability.
  Research: `sdd/research/research-store-api-refinement.md`.

- [ ] **ID-072 — Store API refinement: Phase 2-3 listing normalization**
  Design decision and implementation for listing normalization (Option D preferred:
  `PathEntry` protocol + `FolderEntry` dataclass — but see approachability
  trade-off for citizen developers noted in research doc).
  Depends on ID-071 completion and owner sign-off on design choice.
  `write_text()` moved to ID-071 (Phase 1). Related: ID-063.
  Research: `sdd/research/research-store-api-refinement.md`.

- [ ] **ID-062 — Remove redundant `exists()` guard from S3 listing methods**
  `list_files`, `list_folders`, and `iter_children` in S3Backend and
  S3PyArrowBackend call `self._fs.exists()` before `self._fs.ls()`, adding
  an extra API round-trip. The `FileNotFoundError` handler already covers
  the non-existent path case. Removing the `exists()` check would halve
  the API calls for listing operations. Low priority — consistent across
  all S3 listing methods today.

---

## Done

Completed items, grouped by origin. Kept for traceability — full context
preserved to support future design decisions.

### Release blockers (v0.3.0–v0.4.1)

All v1.0 release blockers were resolved across v0.3.0–v0.4.1.

- [x] **BL-009 — Fix broken PyPI logo and badges** (v0.4.1)
  README logo used relative path — changed to absolute raw GitHub URL.
  Added PyPI version, Python versions, RTD, and license badges.

- [x] **BL-010 — Publish documentation to Read the Docs** (v0.4.1)
  Updated `.readthedocs.yaml` (ubuntu-24.04), pointed `Documentation` URL in
  `pyproject.toml` to `https://remote-store.readthedocs.io/`, added RTD badge.
  Docs live at https://remote-store.readthedocs.io/.

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

### Backlog items

- [x] **BK-005 — SFTP backend test coverage gaps** (v0.14.0)
  Coverage improved from 90% to 100% on `_sftp.py`. 35 new tests covering
  all uncovered branches: `to_key()`, string-to-enum coercion, `_map_exception()`
  edge cases, `write_atomic()` stream paths, type guards, recursive stats,
  non-ENOENT OSError re-raises, generic exception wrapping, `_rmtree` fallbacks.

- [x] **BK-006 — Memory backend test coverage gaps** (v0.14.0)
  Coverage improved from 90% to 100% on `_memory.py`. 30 new tests covering
  all uncovered branches: `_split_path` validation (null bytes, absolute paths,
  `..` segments), `_traverse` file-as-directory, `_ensure_parents` file conflict,
  empty-path guards (write, delete, delete_folder, get_file_info, move, copy),
  directory-at-destination guards, `delete_folder` non-recursive non-empty,
  `get_folder_info` nested subdirectory traversal, move same-path branch,
  source/destination type guards in move/copy.

- [x] **BK-002 — Glob / pattern matching strategy** (v0.12.0)
  Three-tier design chosen (ADR-0009): (1) `list_files(pattern=…)` for universal
  fnmatch name filtering, (2) `Capability.GLOB` + `Store.glob()` for native backend
  access (like `unwrap`), (3) `ext.glob.glob_files()` for portable full-glob
  fallback. All backends (Local, S3, S3-PyArrow, Azure) now implement native glob
  with prefix-optimized listing.
  Related: ID-007.
  → Spec: `sdd/specs/018-glob.md` (GLOB-018, GLOB-019, GLOB-020)
  → ADR: `sdd/adrs/0009-glob-three-tier-design.md`

- [x] **BK-001 — Azure backend** (v0.5.0)
  `AzureBackend` implemented with HNS adaptive behavior, streaming reads,
  Azurite CI, and full conformance suite. Uses `azure-storage-file-datalake`
  directly (not `adlfs`).
  → RFC: `sdd/rfcs/rfc-0001-azure-backend.md` (accepted)
  → Spec: `sdd/specs/012-azure-backend.md`

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

### Audit findings (v0.6.0–v0.9.0, v0.13.0–v0.14.0, post-v0.15.0)

From adversarial review of v0.5.0. Full report: `sdd/audits/audit-001-adversarial-review.md`.
Design-compliance audit of v0.13.0: `sdd/audits/audit-002-design-compliance.md`.
Documentation audit of v0.15.0: `sdd/audits/audit-003-documentation.md`.

- [x] **AF-022 — 7 example scripts missing from docs-site nav** (post-v0.15.0)
  Created `docs-src/examples/*.md` wrappers and nav entries for `caching`,
  `glob_pattern_matching`, `pyarrow_adapter`, `observe_hooks`, `otel_tracing`,
  `path_model`, `capabilities_and_errors`. Added "example docs wrapper" step
  to CONTRIBUTING.md extension checklist.

- [x] **AF-023 — ObservedStore: 24 method overrides lack docstrings** (post-v0.15.0)
  Resolved via `show_if_no_docstring: false` in mkdocstrings config. Enhanced
  class-level docstring to explain delegation pattern. Adding 40+ boilerplate
  "Delegate to inner store." docstrings would be noise.

- [x] **AF-024 — CachedStore: 20+ method overrides lack docstrings** (post-v0.15.0)
  Same approach as AF-023. Enhanced class-level docstring to describe
  caching vs delegation vs invalidation behavior.

- [x] **AF-025 — CacheBackend protocol: 6 methods undocumented** (post-v0.15.0)
  Added docstrings to all 6 protocol methods (`get`, `set`, `delete`,
  `clear`, `clear_prefix`, `size`). These are a public extension point.

- [x] **AF-026 — 6 guides missing API reference links** (post-v0.15.0)
  Closed — not a defect. 3 of 6 guides already have proper cross-links
  (`choosing-a-backend`, `troubleshooting`, `concurrency`). Remaining gaps
  are covered by AF-027 (retry) and AF-028 (backends/index).

- [x] **AF-027 — `guides/retry.md` missing "See also" section** (post-v0.15.0)
  Added "See also" with links to retry policy example and backend guides.

- [x] **AF-028 — `guides/backends/index.md` sparse** (post-v0.15.0)
  Added intro paragraph and "See also" with links to choosing-a-backend
  guide and capabilities matrix.

- [x] **AF-031 — `transfer()` missing `:returns:` docstring** (post-v0.15.0)
  Added `:returns: None` to `upload()`, `download()`, and `transfer()`.

- [x] **AF-032 — `guides/observe.md` on_write hook table omits `open_atomic`** (post-v0.15.0)
  Added `open_atomic` to the `on_write` row in the hook table.

- [x] **AF-033 — `guides/observe.md` on_ping hook row missing** (post-v0.15.0)
  Added `on_ping` row to the hook table.

- [x] **AF-034 — `observe()` docstring on_write omits `open_atomic`** (post-v0.15.0)
  Updated `:param on_write:` to include `open_atomic`.

- [x] **AF-035 — `guides/cache.md` private import** (post-v0.15.0)
  Changed `from remote_store.backends._memory` to `from remote_store.backends`.

- [x] **AF-036 — `guides/health-check.md` private import** (post-v0.15.0)
  Changed `from remote_store.backends._local` to `from remote_store.backends`.

- [x] **AF-037 — `guides/backends/sftp.md` private imports** (post-v0.15.0)
  Created `SFTPUtils` utility class grouping `load_private_key` (staticmethod)
  and `HostKeyPolicy` (class attribute). Re-exported from `backends/__init__.py`.
  Guide imports updated to `from remote_store.backends import SFTPUtils`.
  Follow-up: added `SFTPUtils` to API reference (`docs-src/api/sftp-utils.md`,
  `_nav.yml`, `index.md`). Also filled missing `RetryPolicy`, `Secret`,
  `SecretRedactionFilter` rows in `api/index.md`.

- [x] **AF-038 — `CONTRIBUTING.md` stale counts** (post-v0.15.0)
  Root cause: hand-maintained spec file listing and hardcoded ADR/RFC counts
  go stale on every addition. Replaced exhaustive listing with descriptive
  tree structure. Also fixed stale "notebooks not run in CI" statement.

- [x] **AF-039 — `sdd/CLAUDE-REFERENCE.md` wrong path** (post-v0.15.0)
  Changed `docs/` to `docs-src/` in repository layout section.

- [x] **AF-040 — `guides/migration.md` documents unreleased v0.16.0** (post-v0.15.0)
  Changed "v0.15.0 to v0.16.0" to "v0.15.0 to next release (unreleased)"
  since the YAML loader move hasn't shipped yet.

- [x] **AF-029 — `guides/performance.md` guide-style violations** (post-v0.15.0)
  Closed — not a defect. The guide is already placed under Explanation in
  the nav, which matches its explanatory content style.

- [x] **AF-030 — Research nested 3 levels deep in nav** (post-v0.15.0)
  Closed — not a defect. The Explanation > Design > Research nesting is
  intentional Diataxis structure.

- [x] **AF-016 — Fix stale capability sections in specs 008, 011, 012** (v0.14.0)
  Added `GLOB` to capability lists in S3-003, S3PA-003, and AZ-003. Cross-referenced
  `018-glob.md` (GLOB-018/019/020).

- [x] **AF-017 — Add ID-043 to CHANGELOG [Unreleased]** (v0.14.0)
  Added `### Changed` entry for ID-043 in `[Unreleased]`.

- [x] **AF-018 — Correct BACKLOG version tags for ID-040/041/042** (v0.14.0)
  Changed `(v0.13.1)` annotations to `(v0.14.0)`.

- [x] **AF-019 — Fix spec count in DEVELOPMENT_STORY.md** (v0.14.0)
  Updated `20 specs` to `21 specs`.

- [x] **AF-020 — Fix §11.6 method ordering** (v0.14.0)
  Reordered all 7 class files (`_store.py`, 6 backends) to follow DESIGN.md
  §11.6: `__init__` → properties → public methods → dunder methods → private
  helpers. `# region:` comments restructured to match.

- [x] **AF-021 — Add backlog ID to unlinked TODO in `ext/arrow.py`** (v0.14.0)
  Changed `# TODO(Phase 2):` to `# TODO(ID-037 Phase 2):`.

- [x] **AF-010 — Document TOCTOU and non-atomic move limitations** (v0.9.0)
  `overwrite=False` has inherent TOCTOU (audit M-4, downgraded from High: inherent
  limitation). S3 `move()` is copy+delete (audit L-21, per spec S3-013, not a bug).
  Added `guides/concurrency.md` with full explanation, summary table, and workarounds.
  Cross-referenced from all backend guides.

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

- [x] **AF-004 — Unify `get_folder_info` on empty folders** (v0.6.0/v0.7.0)
  S3 and S3-PyArrow now return `FolderInfo(file_count=0)` when a folder exists
  but has no files (the `exists()` check gates non-existent folders). Azure
  non-HNS retains `NotFound` for `file_count==0` — correct because non-HNS
  has no concept of empty folders (they are virtual prefixes).

- [x] **AF-008 — Add credential masking to backend `__repr__`** (v0.7.0)
  Added `__repr__` to all 5 backends. Sensitive fields (key, secret, password,
  pkey, account_key, sas_token, connection_string, credential) display as
  `'***'` when set and `None` when unset. Non-sensitive fields (bucket, host,
  container, etc.) shown in clear text.

- [x] **AF-009 — Fix `Registry.close()` to close all backends on error** (v0.7.0)
  `close()` now catches exceptions from individual backends, continues closing
  the rest, always runs `_backends.clear()`, and re-raises the first error.

- [x] **AF-011 — Remove dead `RemoteFile`/`RemoteFolder`** (v0.7.0)
  Removed class definitions from `_models.py`, imports from `__init__.py` and
  `__all__`, associated tests (MOD-006), docs entries, and spec section.
  Updated MOD-007 spec to reference only `FileInfo` and `FolderInfo`.

- [x] **AF-015 — Update stale v0.5.0 docs** (v0.7.0)
  L-1 (README `azure-storage-file-datalake`), L-2 (SECURITY.md), L-3
  (CONTRIBUTING.md spec 012), L-4 (Azure config example), L-5 (`[Unreleased]`
  section in CHANGELOG).

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

- [x] **AF-005 — Fix `delete_folder` error types** (v0.6.0)
  Added `DirectoryNotEmpty` error type; non-empty folder deletes now raise
  `DirectoryNotEmpty` instead of generic errors.

- [x] **AF-006 — Fix native exception leakage through lazy streams** (v0.6.0)
  Added `_ErrorMappingStream` wrapper that catches `OSError` during lazy
  reads and maps them through each backend's error classifier.

- [x] **AF-007 — Wire Azure backend into docs site** (v0.6.0)
  Azure guide added to docs navigation in `mkdocs.yml` and `generate_docs.py`.

### Known bugs

- [x] **BUG-002 — Windows drive letter case mismatch in `warnings` module** (post-v0.15.0)
  `warnings.warn()` normalizes file paths to lowercase drive letter (`f:\`)
  while `__file__` preserves the original case (`F:\`). Fixed with
  `os.path.normcase()` on both sides of the comparison in
  `test_from_yaml_unknown_key_warning_stacklevel`.

- [x] **ID-047 — Spec accuracy fixes** (v0.14.0)
  Add ERR-010 (`DirectoryNotEmpty`) to error model spec. Clarify `around`-hook
  propagation vs after-hook suppression in `ext.observe`. Add ownership
  qualifier to STORE-009 `close()` contract. Scope `ext.transfer` memory
  guarantee to extension layer. List both `yaml.YAMLError` and
  `ruamel.yaml.YAMLError` in config loader spec.

- [x] **BUG-001 — `get_folder_info("")` fails for empty-root stores** (v0.13.0)
  Fixed via `RemotePath.ROOT` sentinel (bypasses `__init__` validation,
  `str(ROOT) == "."`). All 6 backends + `_rebase_folder_info` updated.
  19 new tests (15 ROOT unit tests + 4 regression tests now passing).

### Ideas shipped

- [x] **ID-074 — Store API refinement (pre-v1 audit)**
  Systematic pre-v1 audit of the Store public API. Rewrote all Store docstrings
  (fixed `write`/`write_atomic` str claim, `read_text` errors reference).
  Implemented `write_text()` with encoding param and 8 tests. Restructured
  `store.md` with per-method `:::` directives, admonitions for ordering,
  atomicity, metadata, and thread-safety. Built backend behavior matrix
  (verified against backend code). Created hand-written `store-api.md` target
  API reference page. Updated README API table. Subsumes ID-071 Phase 1.

- [x] **ID-073 — Use uv as hatch installer backend** (v0.16.0)
  Set `installer = "uv"` in `[tool.hatch.envs.default]`. Hatch >=1.12 has
  native uv support — no plugin needed. ~10x faster env creation (2m → 12s).
  Zero CI impact, zero workflow change.

- [x] **ID-056 — `read_text()` convenience method** (post-v0.15.0)
  `Store.read_text(path, encoding="utf-8", errors="strict")` -- thin wrapper
  around `read_bytes()` + `.decode()`. Store-level only (no backend changes).
  `ext.observe` `on_read` hook, `ext.cache` routes through cached `read_bytes`.
  Spec: `028-read-text.md` (RTXT-001 through RTXT-006). 8 Store tests,
  1 observe parametrized case, 1 cache test.

- [x] **ID-055 — `iter_children()` — combined file + folder listing** (post-v0.15.0)
  `Store.iter_children(path)` yields both `FileInfo` (files) and `str` (folder
  names) in a single pass. All 6 backends override with single-call
  implementations (Local `iterdir`, S3/S3PA `ls`, SFTP `listdir_attr`, Azure
  `walk_blobs`/`get_paths`, Memory single traversal). `ext.observe` `on_list`
  hook, `ext.cache` caching. Spec: `027-iter-children.md` (ITER-001 through
  ITER-008).

- [x] **ID-025 — `ext.cache` — store-level caching middleware** (v0.15.0)
  `cached_store(store, ttl=300)` wraps a Store in a caching proxy.
  Caches: `exists`, `is_file`, `is_folder`, `read_bytes`, `get_file_info`,
  `get_folder_info`, `list_files`, `list_folders`, `glob`. Auto-invalidates
  on writes/deletes/moves/copies. `max_content_size` guard for large files.
  `MemoryCache` default backend, thread-safe. `CacheStats` for monitoring.
  Spec: `023-ext-cache.md` (CACHE-001 through CACHE-015). 52 tests.

- [x] **ID-035 — Parallel batch operations** (v0.15.0)
  Added `concurrent=True` and `max_workers=N` keyword arguments to
  `batch_delete`, `batch_copy`, `batch_exists`. Uses `ThreadPoolExecutor`
  (stdlib). `stop_on_error=True` + `concurrent=True` raises `ValueError`.
  Spec: BATCH-020 through BATCH-025 in `016-ext-batch.md`. 20 new tests.

- [x] **ID-036 — Hive-style partition path helpers** (v0.15.0)
  `partition_path(filename, **partitions)` and `parse_partition(path)` in
  `ext/partition.py`. Builds and parses paths like
  `year=2026/month=03/data.parquet`. Pure Python, zero dependencies.
  Spec: `024-ext-partition.md` (PART-001 through PART-013). 23 tests.

- [x] **ID-048 — Verify notebook examples in CI** (v0.15.0)
  `tests/scripts/run_notebooks.py` executes notebook code cells via `exec()`.
  Wired into `hatch run notebooks`, `hatch run all`, and CI `notebooks` job.
  Skips `benchmark_analysis.ipynb`. PR #130.

- [x] **ID-026 — Streaming atomic writes** (v0.15.0)
  `Store.open_atomic()` and `Backend.open_atomic()` — context manager yielding
  a writable file object backed by a temporary location. On success, atomically
  promoted; on exception, cleaned up. All 6 backends: `mkstemp`+`os.replace`
  (Local), `.~tmp.*`+`posix_rename` (SFTP), `SpooledTemporaryFile`+PUT (S3,
  S3-PyArrow, Azure non-HNS), temp blob+DFS rename (Azure HNS), `BytesIO`
  (Memory). RFC-0004 accepted. Spec: `022-streaming-atomic-writes.md`
  (SAW-001 through SAW-015). `ext.observe` maps to `on_write` hook.

- [x] **ID-037 — PyArrow adapter Phase 2 — Tier 1 native fast-path reads** (v0.15.0)
  Tier 1 native fast-path reads (PA-010) implemented: `Backend.native_path()`
  (BE-025), `Store.native_path()` (STORE-015), `S3PyArrowBackend.unwrap()`
  accepts `pyarrow.fs.FileSystem` base class, `StoreFileSystemHandler` probes
  at construction and dispatches reads directly to the native PyArrow FS.
  `native_path()` overrides for all backends (Local, S3, SFTP, Azure) done.
  Streaming error-mapping wrapper deferred — currently inert (cloud backends
  materialize via Tier 2, no mid-read exceptions on PythonFile possible).

- [x] **ID-038 — Re-run comparative benchmarks post-cache-invalidation fix** (v0.15.0)
  Re-ran quick + standard tier benchmarks with Docker backends (MinIO, Azurite,
  SFTP). Updated `benchmarks/results/comparative.md` with post-ID-032 data.
  Listing numbers now reflect real I/O without fsspec caching bias.

- [x] **ID-002 — YAML config support** (v0.14.0, moved to `ext/yaml.py` post-v0.15.0)
  `from_yaml(path)` in `ext/yaml.py` — optional `pyyaml` or `ruamel.yaml`.
  Originally shipped as `RegistryConfig.from_yaml()` classmethod in v0.14.0;
  moved to extension for consistency (YAML requires optional deps, same as Pydantic).
  Spec: `sdd/specs/021-config-loaders.md` (CFG-010/CFG-011).

- [x] **ID-003 — Pydantic BaseSettings integration** (v0.14.0)
  `pydantic_to_registry_config()` in `ext/pydantic.py`. Converts any Pydantic
  `BaseModel`/`BaseSettings` to `RegistryConfig` via `model_dump() → from_dict()`.
  Optional `pydantic-settings` dependency. Spec: `sdd/specs/021-config-loaders.md`
  (CFG-015, CFG-016, CFG-017).

- [x] **ID-005 — Built-in `from_toml()` config loader** (v0.14.0)
  `RegistryConfig.from_toml(path, table=())` — zero-dep on 3.11+, `tomli` on 3.10.
  Spec: `sdd/specs/021-config-loaders.md` (CFG-008/CFG-009).

- [x] **ID-034 — Parquet lake guide (Bronze / Silver / Gold patterns)** (v0.14.0)
  User-facing guide (`guides/data-lake-patterns.md`) documenting Bronze/Silver/Gold
  medallion architecture using `Store.child()` + `ext.arrow` + `ext.transfer`.
  Covers PyArrow, Polars, DuckDB, Delta Lake integration, batch partition
  operations, cross-backend transfer, and testing without cloud credentials.
  Docs-src wrapper and nav entry included. PR #114.

- [x] **ID-040 — `move(src, dst)` and `copy(src, dst)` same-path consistency** (v0.14.0)
  Added `src == dst` short-circuit in `Store.move()` and `Store.copy()` with
  `is_file()` verification (`NotFound` for missing files or folders at source
  path). MemoryBackend retains its own move guard for defense in depth.
  Spec: STORE-008a.

- [x] **ID-041 — `Registry.get_store()` backend ownership foot-gun** (v0.14.0)
  `get_store()` now sets `_owns_backend = False` on returned stores (same
  pattern as `Store.child()`). `Registry.close()` remains the lifecycle owner.

- [x] **ID-042 — Document Secret usage in README and examples** (v0.14.0)
  Added "Credential hygiene" section to README and updated
  `examples/configuration.py` with `Secret` wrapping, `from_dict()`
  auto-wrapping, and `.reveal()` demonstration. Related: ID-039.

- [x] **ID-043 — Remove `_stacklevel` from public `from_dict()` signature** (v0.14.0)
  `RegistryConfig.from_dict()` exposes a `_stacklevel: int = 2` keyword
  argument — a private implementation detail leaking into the public API.
  Fixed: extracted `_from_dict()` private impl; `from_dict()`, `from_toml()`,
  `from_yaml()` call it with correct `stacklevel`. `ext/pydantic.py` now calls
  only the public `from_dict()` API. `from_dict()` gains a protected
  `_extra_frames` param so adapter layers (e.g. the pydantic adapter) can
  correctly offset the warning stacklevel.

- [x] **ID-046 — Audit version-conditional imports for mypy coverage** (v0.14.0)
  Swept all `try/except` import patterns in `src/` and `tests/`. The only
  version-conditional import is `tomllib`/`tomli` in `_config.py` and
  `test_config.py` — already covered by `[[tool.mypy.overrides]]` entries
  for `tomli`, `tomllib`, `ruamel.yaml`, `pydantic`/`pydantic_settings`,
  plus `warn_unused_ignores = false` on `_config` module. No gaps found.

- [x] **ID-004 — Structured logging & metrics hooks** (v0.13.0)
  Superseded by ID-024 (`ext.observe`). Intrinsic stdlib logging added to all
  modules: `NullHandler`, `log = logging.getLogger(__name__)`, `%`-style with
  `extra={}`. DEBUG for method entry, INFO for write/delete/move/copy completion.

- [x] **ID-024 — `ext.observe` — hooks / middleware / instrumentation** (v0.13.0)
  All three layers shipped: Layer 1 (intrinsic logging), Layer 2 (`ext.observe`
  callback hooks), Layer 3 (`ext.otel` OpenTelemetry bridge). `otel_observe()`
  wraps Store with OTel spans and metrics. Optional extra `otel` depends on
  `opentelemetry-api>=1.28.0`. ADR-0010, spec `019-ext-observe.md` (OBS-001
  through OBS-014). Supersedes ID-004.

- [x] **ID-039 — Credential hygiene: `Secret` wrapper and central redaction** (v0.13.0)
  `Secret` type in `_config.py`: wraps sensitive strings, `__repr__`/`__str__`
  → `'***'`, `.reveal()` → actual value. `from_dict()` wraps `_SENSITIVE_KEYS`.
  Backends accept `str | Secret` via `_reveal()`. SFTP enum coercion for
  `host_key_policy`. `SecretRedactionFilter` logging filter. Regression tests.
  → Spec: `sdd/specs/020-credential-hygiene.md` (SEC-001 through SEC-008)

- [x] **ID-007 — `Store.glob()` surface API** (v0.12.0)
  Three-tier pattern matching: `list_files(pattern=…)` for universal name filtering,
  `Store.glob(pattern)` for native backend glob (capability-gated on `GLOB`),
  `ext.glob.glob_files()` for portable full-glob fallback. All backends (Local, S3,
  S3-PyArrow, Azure) now implement native glob with prefix-optimized listing.
  → Spec: `sdd/specs/018-glob.md` (GLOB-018, GLOB-019, GLOB-020)
  → ADR: `sdd/adrs/0009-glob-three-tier-design.md`

- [x] **ID-032 — Fix listing benchmark fixture caching** (v0.12.0)
  Added `invalidate_cache()` to `BenchTarget` protocol and all fsspec targets
  (S3fsTarget, AdlfsTarget, SshfsTarget) + `RemoteStoreTarget`. Called after
  fixture population in listing tests so benchmarks measure real I/O, not
  cached results from the write phase.

- [x] **ID-033 — Cloud benchmark quick tier timing budget** (v0.12.0)
  Moved 1000-file listing test (`TestListPerformanceLarge`) from quick to
  `@pytest.mark.standard` tier. Updated README with per-tier cloud timing
  estimates (~5 min quick, ~15 min standard, ~60+ min full).

- [x] **ID-020 — Benchmark tiered modes and single-backend filtering** (v0.10.0)
  Replaced binary slow/not-slow with three tiers (quick/standard/full).
  `--backend` CLI filter deselects tests (avoids fixture setup). `--bench-timeout`
  watchdog (Windows-compatible via `threading.Timer`). `report.py` gains
  `--comparative` and `--markdown` modes for remote-store vs raw SDK vs fsspec
  tables. Updated hatch scripts (14 bench-* commands). Comparative results
  integrated into docs site. No spec needed (ops/tooling change).

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

- [x] **ID-031 — S3-PyArrow read path optimization** (v0.10.0)
  Drop `BufferedReader` from `S3PyArrowBackend.read()`, add `read()` + chunked
  `readline()` to `_PyArrowBinaryIO`. Eliminates double-copy per chunk on
  streaming reads (56% peak memory overhead in benchmarks). Non-breaking,
  S3-PyArrow only.
  → RFC: `sdd/rfcs/rfc-0003-s3-pyarrow-read-optimization.md`
  PR #66 (code), PR #67 (review fixes: seek guard, __next__ bypass, bytes()
  copy removal, 9 edge-case tests, RFC status -> Implemented, RawIOBase
  cross-backend note, BACKLOG update, chunk-boundary test).

- [x] **ID-001 — Cross-store transfer** *(subsumed by ID-023 `ext.transfer`)* (v0.9.0)
  Shipped as `transfer()` in `ext.transfer`. See spec `017-ext-transfer.md`.

- [x] **ID-009 — `Store.upload()` / `Store.download()` convenience methods** *(subsumed by ID-023 `ext.transfer`)* (v0.9.0)
  Shipped as `upload()` and `download()` in `ext.transfer`. See spec `017-ext-transfer.md`.

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

- [x] **ID-019 — Update stale CAP-001 in spec 003** (v0.9.0)
  Removed `GLOB` and `RECURSIVE_LIST` from capability lists in specs
  003 (CAP-001), 008 (S3-003), 009 (SFTP-003), 011 (S3PA-003),
  012 (AZ-003) and backend guides (SFTP, Azure). These enum members
  were removed in v0.6.0 (AF-002) but the specs/guides were never updated.

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

- [x] **ID-021 — `Store.child(subpath)` — runtime sub-scoping** (v0.8.0)
  Return a new Store scoped to a subfolder without recreating backend/registry.
  Child shares the parent's backend (identity); `child.close()` does not close
  the shared backend. Validated via RemotePath, chainable, equality-transparent.
  → Spec: `sdd/specs/015-store-child.md`

- [x] **ID-030 — Claude Code reusable skills** (v0.8.0)
  Create `.claude/commands/` slash-command skills to standardize and speed up
  recurring workflows: ripple-check, release, add-backend, backlog-sync,
  pr-preflight, add-spec. Addresses top systemic issues: backlog drift
  (7/9 AF commits forgot backlog), CHANGELOG skipped (62% of code changes),
  and version-file sync misses.
  Done: Added 6 skills in `.claude/commands/`.

- [x] **ID-017 — Memory backend** (v0.7.0)
  Tree-indexed in-memory backend. Zero dependencies, no filesystem access.
  Supports all 8 capabilities, full conformance suite with zero skips.
  Registered as `"memory"` type unconditionally. Store test fixtures migrated
  from `LocalBackend` + `tempfile` to `MemoryBackend`.
  Done: implementation, registry, conformance wiring, Store fixture migration,
  guide, docs nav, example, CHANGELOG, README.

- [x] **ID-012 — Performance benchmarks** (v0.5.0)
  Benchmark suite with Docker-hosted backends: throughput, TTFB, memory,
  large-file, listing, metadata, and destructive operation scenarios.

- [x] **ID-014 — Streaming conformance tests** (v0.4.4)
  `TestStreamingConformance` in `test_conformance.py`: 5 tests × 4 backends.
  Spec: SIO-001, SIO-003.

- [x] **ID-011 — Python 3.14 support** (v0.3.0) → graduated to BK-004

### Post-v0.15.0 housekeeping

- [x] **ID-070 — Add third-party doc links in extension module docstrings** (post-v0.16.0)
  Added hyperlinks to upstream docs for `pyarrow.fs.PyFileSystem` (ext.arrow),
  OpenTelemetry (ext.otel), and pyyaml/ruamel.yaml (ext.yaml).

- [x] **ID-069 — Automated Claude PR review workflow** (post-v0.16.0, reverted)
  Shipped `claude-review.yml` using `anthropics/claude-code-action@v1` with
  `/review-pr` skill. Findings: action runs Claude Code in a sandboxed
  environment — 18 permission denials blocked `gh` CLI calls the skill depends
  on, so no review was posted. Run took ~10 min and cost ~$2 (1M+ tokens) for
  a trivial 3-file docstring PR. Not cost-effective; removed workflow.

- [x] **ID-068 — Replace `dorny/paths-filter` with bash path filtering** (post-v0.15.0)
  `dorny/paths-filter@v3` runs on Node.js 20 (deprecated on GitHub Actions from
  2026-06-02; PR #294 updating to Node 24 was still open at fix time). Replaced
  the action in `ci.yml` with a native bash step using `git diff`/`git ls-files`
  and `grep -E` — no third-party action runtime required. Added `fetch-depth: 0`
  to the `changes` job checkout for full history access.

- [x] **ID-065 -- Use uv in docs deployment workflow** (post-v0.15.0)
  Switched `docs.yml` from `pip install` to `astral-sh/setup-uv@v6` + `uv pip install`
  for consistency with `ci.yml` and `publish.yml`. Added `UV_SYSTEM_PYTHON: 1` env var.

- [x] **ID-061 — Use uv for CI dependency installs** (post-v0.15.0)
  Replace `pip install` with `uv pip install` in `ci.yml` and `publish.yml`.
  uv is 10-100x faster at dependency resolution and installation, cutting
  per-job install time from ~1-2 min to seconds (worst case: Windows at ~2 min).
  Drop-in replacement -- no changes to dev workflow or dependency specs.

- [x] **ID-060 — Multi-platform CI (Linux, Windows, macOS)** (post-v0.15.0)
  `requires_docker` pytest marker, `test-cross-platform` CI job (Windows +
  macOS, py3.13, `-m "not requires_docker"`), wired into gate. Fixed macOS
  `/var` → `/private/var` symlink resolution in tempdir-based tests. PR #166.

- [x] **ID-059 — Restructure authoritative docs to ADF standard** (post-v0.15.0)
  Restructure SDD root-level and repo root-level docs to Authoritative Document
  Format (Intent & Scope, Rules, Guides). Move audit files to `sdd/audits/`.
  Trim DESIGN.md to code style only, condense DOCUMENTATION.md and 000-process.md.

- [x] **ID-044 — Harden examples into assertion-based expectation tests** (post-v0.15.0)
  Examples expose `demo(store)` functions; `tests/test_examples.py` imports
  each and wraps with assertions. Examples stay print-based and user-friendly.
  14 examples refactored, 14 test classes in `test_examples.py`. Research:
  `sdd/research/research-example-testing.md` (cross-language ecosystem survey).

- [x] **ID-049 — Enable GitHub Vigilant Mode** (post-v0.15.0)
  Commit signing with SSH for supply chain transparency. Soft enforcement
  (visual badges, no blocking of unsigned commits). Ops-only, no code changes.
  - Done: Vigilant Mode enabled on maintainer GitHub account. Local SSH signing
    configured. CONTRIBUTING.md § Code Signing added with setup instructions.
    Master merge commits show "Verified" badge.
  - Future: Consider SIGNING.md verification guide if moving to hard enforcement.

- [x] **ID-010 — Retry policy configuration** (post-v0.15.0)
  `RetryPolicy` frozen dataclass for unified retry configuration. Per-backend
  native mapping: SFTP (tenacity), S3 (botocore), Azure (ExponentialRetry),
  S3-PyArrow (AwsStandardS3RetryStrategy + botocore). ADR-0011, spec
  `025-retry-policy.md`, `BackendConfig.retry` field, `from_dict()` parsing,
  Registry passthrough. User guide (`guides/retry.md`), example
  (`examples/retry_policy.py`), docs page. 39 tests.

- [x] **ID-054 — `store.ping()` / backend health check** (post-v0.15.0)
  `Store.ping()` delegates to `Backend.check_health()` -- lightweight,
  non-destructive connectivity verification. Per-backend: Local
  (`exists` + `os.access`), S3 (`head_bucket`), S3-PyArrow
  (`get_file_info`), SFTP (`stat`), Azure (`get_container_properties`),
  Memory (no-op). `ext.observe` `on_ping` hook. Spec `026-health-check.md`
  (PING-001 through PING-010). Guide, example, docs page.

- [x] **ID-050 — End-to-end integration tests against Docker backends** (post-v0.15.0)
  19 e2e tests: medallion pipeline (4 backends), SFTP workflow (5 tests:
  check/fetch/place, incremental pickup, folders, atomic write, overwrite),
  cross-backend transfer (10 tests: S3/SFTP/Azure pairs with progress +
  overwrite guard). CI: MinIO + Azurite + SFTP Docker.

- [x] **ID-051 — Sweep stale backlog references in docs and guides** (post-v0.15.0)
  Swept all docs-src, guides, and examples for stale backlog references.
  One stale item found and fixed: `guides/pyarrow-adapter.md` Limitations
  section claimed Tier 1 was "only for S3-PyArrow" (stale since ID-037
  shipped `native_path()` for all backends in v0.15.0). Data lake guide
  "What comes next" section was already fixed in PR #146.

- [x] **ID-045 — Fill example coverage gaps for specs 003, 004, 020, 021** (post-v0.15.0)
  Added `capabilities_and_errors.py` (spec 003: Capability enum, CapabilitySet,
  supports/require, CapabilityNotSupported, error hierarchy with structured
  attributes, to_key/native_path round-trip) and `path_model.py` (spec 004:
  normalization rules, properties, / operator, ROOT sentinel, InvalidPath
  exceptions, immutability, FileInfo.path usage). Specs 020 and 021 were
  already covered by `configuration.py` and `config_loaders.py`.

- [x] **ID-053 — Fix code block highlighting in docs** (post-v0.15.0)
  Audited all markdown in docs-src, guides, specs, ADRs, and RFCs for bare
  opening code fences (` ``` ` without language tag). Found 13 actual bare
  openers across 11 files (original estimate of ~135 was inflated by counting
  closing fences). All 13 fixed with explicit `text` tags (ASCII diagrams,
  flow sequences, directory trees, output examples). No bare fences in Python
  source docstrings. All Python code blocks in docs already had `python` tags.

- [x] **ID-052 — Custom domain: remotestore.dev** (post-v0.15.0)
  Registered `remotestore.dev` with redirect to GitHub project home.
  DNS CNAME points `docs.remotestore.dev` to `remote-store.readthedocs.io`.
  **Step 1 [x]:** Updated all user-facing URLs across the repo: `pyproject.toml`
  Homepage/Documentation, `CITATION.cff`, conda recipe, README (badge + 14 deep
  links), CONTRIBUTING release checklist, release skill, DOCUMENTATION.md
  canonical URL policy, data lake guide, repo_stats.py label. Historical
  references (CHANGELOG, BACKLOG done items, research docs) left as-is.
  **Step 2 [x]:** Configured `docs.remotestore.dev` as canonical docs URL.
  RTD custom domain admin done. `mkdocs.yml` `site_url` updated from
  GitHub Pages to `https://docs.remotestore.dev/`. Old RTD URL
  (`remote-store.readthedocs.io`) 302-redirects to custom domain.

### Documentation

- [x] **DOC-001 — Documentation overhaul per Documentation Master** (v0.15.0)
  Full Diataxis restructure of the docs site. Phase 1: nav restructure into
  Getting Started / Guides / Reference / Explanation. Phase 2: extension API
  reference pages for all 9 ext modules. Phase 3: 7 new content pages
  (capabilities matrix, choosing a backend, troubleshooting, migration,
  architecture overview, security model, further reading). Phase 4: research
  docs surfaced under Explanation > Design > Research with auto-generated
  index. Phase 5: docstring audit for Store, Backend, errors, and
  capabilities with complete `:param:`/`:returns:`/`:raises:` and examples.
  Phase 6: cross-links between guides, API reference, and example scripts.
  Phase 7: final polish (broken link fixes, Secret/SecretRedactionFilter
  added to config API page, CHANGELOG entry).

### Other completed work

- [x] **DONE-005 — Reorganize examples into core + backends groups** (v0.8.0)
  Moved 4 cloud backend scripts (S3, S3-PyArrow, SFTP, Azure) into
  `examples/backends/`. README, CI, docs, and CLAUDE-REFERENCE updated
  to reflect the grouped structure. CI examples job now covers all 8
  core scripts (memory_backend and store_child were missing). Added
  docs page for memory-backend example.

- [x] **DONE-004 — S3-PyArrow hybrid backend** (v0.4.0)
  Hybrid S3 backend using PyArrow's C++ S3 filesystem for data-path operations
  (read, write, copy) and s3fs for control-path operations (listing, metadata,
  deletion). Drop-in alternative to S3Backend with the same constructor
  signature. New optional extra: `s3-pyarrow`.
  → Spec: `sdd/specs/011-s3-pyarrow-backend.md`

- [x] **DONE-001 — PEP 604 type hints**
  All source uses `X | Y` with `from __future__ import annotations`. mypy
  strict mode enforced in CI. No action needed.
