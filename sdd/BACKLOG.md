# Development Backlog

Tracking file for prioritized work and unprioritized ideas.
Items graduate through the SDD pipeline: **Idea → Backlog → RFC/Spec → Tests → Code**.

Status legend: `[ ]` pending · `[~]` in progress · `[x]` done

---

## Backlog (Prioritized)

Active work items, ordered by priority.

- [ ] **BK-002 — Glob / pattern matching strategy**
  Decide per-backend glob vs client-side abstraction. S3 has native prefix listing,
  SFTP does not. Spec the chosen approach or document why it stays per-backend.
  Related: ID-007 (`Store.glob()` surface API).
  → Spec: TBD (extends `003-backend-adapter-contract.md`)

- [ ] **AF-010 — Document TOCTOU and non-atomic move limitations**
  `overwrite=False` has inherent TOCTOU (audit M-4, downgraded from High: inherent
  limitation). S3 `move()` is copy+delete (audit L-21, per spec S3-013, not a bug).
  Document these in guides or API docs so users know the guarantees.

- [ ] **AF-012 — Add capability gating tests (STORE-006)**
  Test that Store methods raise `CapabilityNotSupported` for backends missing
  capabilities (audit M-11). No tests exist for this path yet.

- [~] **AF-013 — Add PermissionDenied/BackendUnavailable error path tests**
  S3-016, S3-017, SFTP-021/022/023 have zero test coverage.
  Partial: `test_coverage_gaps.py` covers LocalBackend `PermissionDenied` paths.
  Remaining: S3 and SFTP error path tests.

- [ ] **AF-014 — Add CI gate to publish workflow**
  `publish.yml` triggers on `v*` tags but does not require CI to pass first.
  Add a `needs: ci` dependency or a `workflow_run` trigger.

---

## Ideas (Unprioritized)

Parking lot. Not evaluated, not committed to. Pick up when relevant.

- [ ] **ID-001 — Cross-store transfer**
  High-level API to move/copy data between stores (e.g. SFTP → S3).
  Could be a `Store.transfer_to(other_store, path)` method or a standalone utility.

- [ ] **ID-002 — YAML config support**
  Allow `RegistryConfig.from_yaml()` alongside the existing `from_dict()`.
  Optional dependency on `pyyaml` or `ruamel.yaml`.

- [ ] **ID-003 — Pydantic BaseSettings integration**
  Let users define backend config via Pydantic `BaseSettings` for env-var binding,
  `.env` file loading, and validation. Optional `pydantic` dependency.

- [ ] **ID-004 — Structured logging & metrics hooks**
  Add optional `logging` calls at key points (connection open/close, read/write,
  retries, errors). Lets users debug in production without changing the public API.
  Consider a lightweight callback/event system for metrics collection.

- [ ] **ID-005 — Built-in `from_toml()` config loader**
  Use `tomllib` (stdlib in 3.11+, `tomli` backport for 3.10) to add
  `RegistryConfig.from_toml(path)` alongside the existing `from_dict()`.
  Eliminates boilerplate for every user who keeps config in `pyproject.toml` or a
  standalone `.toml` file.

- [ ] **ID-006 — Progress callbacks for large transfers**
  Add an optional `callback: Callable[[int], None]` parameter to `read()` and
  `write()` reporting bytes transferred. Enables progress bars (e.g. `tqdm`)
  without adding dependencies.

- [ ] **ID-007 — `Store.glob()` surface API**
  Expose a `Store.glob(pattern)` method. `Capability.GLOB` was removed in v0.6.0
  (AF-002), so this would need a new capability or a different design. Local has
  native glob, S3 can do prefix filtering, SFTP would need client-side filtering.
  Ships alongside or after BK-002.

- [ ] **ID-008 — Checksum verification on read/write**
  Add a `verify_checksum=True` option to `read()` / `write()`. Populate
  `FileInfo.checksum` consistently across backends (S3 ETag, local SHA-256).
  Gives users data-integrity guarantees with a single flag.

- [ ] **ID-009 — `Store.upload()` / `Store.download()` convenience methods**
  Dedicated methods for the most common real-world pattern: local file path in,
  remote path out (and vice versa). Eliminates the open-file-wrap-in-BytesIO
  dance.

- [ ] **ID-010 — Retry policy configuration**
  SFTP has hardcoded retry logic (3 attempts, 2–10 s backoff via `tenacity`).
  Expose a `RetryPolicy` dataclass in `BackendConfig.options` so users can tune
  attempts, backoff, and jitter per-backend.

- [ ] **ID-013 — Async Store / Backend API**
  Async version of `Store` and `Backend` for use in async frameworks (FastAPI,
  aiohttp, etc.). Could be a parallel `AsyncStore` class or an async mode on
  the existing `Store`. Needs design decision on whether to wrap sync backends
  with `asyncio.to_thread` or require native async backends.

- [ ] **ID-015 — Audit external deep links**
  v0.4.3 fixed a broken ReadTheDocs link in the README (missing `/en/latest/`
  prefix). Other docs, docstrings, or example files may contain similar
  bare RTD URLs. Sweep for `readthedocs.io/` links without a version prefix
  and fix them. One-time task.

- [ ] **ID-016 — PyArrow FileSystemHandler adapter**
  Implement a `StoreFileSystemHandler` in `ext/arrow.py` that wraps any
  `Store` into a `pyarrow.fs.PyFileSystem` via `pyarrow.fs.FileSystemHandler`.
  Enables seamless use of any backend with PyArrow, Pandas, Iceberg, Delta Lake,
  DuckDB, and Polars. Optional `pyarrow` dependency, zero impact on core.
  Aligns with ADR-0003.
  → RFC: `sdd/rfcs/rfc-0002-pyarrow-filesystem-adapter.md`

- [ ] **ID-019 — Update stale CAP-001 in spec 003**
  `sdd/specs/003-backend-adapter-contract.md` CAP-001 still lists `GLOB` and
  `RECURSIVE_LIST` as `Capability` enum members. These were removed in v0.6.0
  (AF-002). Update CAP-001 to list only the 8 current members. Pre-existing
  inconsistency, not introduced by ID-017.

- [ ] **ID-018 — conda-forge publishing**
  Submit a staged-recipes PR to conda-forge so users can `conda install -c
  conda-forge remote-store`. Pure-Python wheel, so the recipe should be
  straightforward. Consider once the project reaches Beta or if user demand
  appears. Reference: https://conda-forge.org/docs/maintainer/adding_pkgs/

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

### Audit findings (v0.6.0–v0.6.1)

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

- [x] **AF-004 — Unify `get_folder_info` on empty folders** (v0.6.0/v0.6.1)
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

- [x] **AF-008 — Add credential masking to backend `__repr__`** (v0.6.1)
  Added `__repr__` to all 5 backends. Sensitive fields (key, secret, password,
  pkey, account_key, sas_token, connection_string, credential) display as
  `'***'` when set and `None` when unset. Non-sensitive fields (bucket, host,
  container, etc.) shown in clear text.

- [x] **AF-009 — Fix `Registry.close()` to close all backends on error** (v0.6.1)
  `close()` now catches exceptions from individual backends, continues closing
  the rest, always runs `_backends.clear()`, and re-raises the first error.

- [x] **AF-011 — Remove dead `RemoteFile`/`RemoteFolder`** (v0.6.1)
  Removed class definitions from `_models.py`, imports from `__init__.py` and
  `__all__`, associated tests (MOD-006), docs entries, and spec section.
  Updated MOD-007 spec to reference only `FileInfo` and `FolderInfo`.

- [x] **AF-015 — Update stale v0.5.0 docs** (v0.6.1)
  L-1 (README `azure-storage-file-datalake`), L-2 (SECURITY.md), L-3
  (CONTRIBUTING.md spec 012), L-4 (Azure config example), L-5 (`[Unreleased]`
  section in CHANGELOG).

### Ideas shipped

- [x] **ID-017 — Memory backend** (v0.7.0)
  Tree-indexed in-memory backend. Zero dependencies, no filesystem access.
  Supports all 8 capabilities, full conformance suite with zero skips.
  Registered as `"memory"` type unconditionally. Store test fixtures migrated
  from `LocalBackend` + `tempfile` to `MemoryBackend`.
  Done: implementation, registry, conformance wiring, Store fixture migration,
  guide, docs nav, example, CHANGELOG, README.

- [x] **ID-011 — Python 3.14 support** (v0.3.0) → graduated to BK-004

- [x] **ID-012 — Performance benchmarks** (v0.5.0)
  Benchmark suite with Docker-hosted backends: throughput, TTFB, memory,
  large-file, listing, metadata, and destructive operation scenarios.

- [x] **ID-014 — Streaming conformance tests** (v0.4.4)
  `TestStreamingConformance` in `test_conformance.py`: 5 tests × 4 backends.
  Spec: SIO-001, SIO-003.

### Other completed work

- [x] **DONE-001 — PEP 604 type hints**
  All source uses `X | Y` with `from __future__ import annotations`. mypy
  strict mode enforced in CI. No action needed.

- [x] **DONE-004 — S3-PyArrow hybrid backend** (v0.4.0)
  Hybrid S3 backend using PyArrow's C++ S3 filesystem for data-path operations
  (read, write, copy) and s3fs for control-path operations (listing, metadata,
  deletion). Drop-in alternative to S3Backend with the same constructor
  signature. New optional extra: `s3-pyarrow`.
  → Spec: `sdd/specs/011-s3-pyarrow-backend.md`
