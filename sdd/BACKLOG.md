# Development Backlog

Tracking file for release blockers, prioritized work, and unprioritized ideas.
Items graduate through the SDD pipeline: **Idea → Backlog → RFC/Spec → Tests → Code**.

Status legend: `[ ]` pending · `[~]` in progress · `[x]` done

---

## Release Blockers (v1.0)

Must be resolved before PyPI + ReadTheDocs publish.

- [x] **BL-001 — PyPI publish workflow**
  Add GitHub Actions job (new `publish.yml` or extend `ci.yml`) triggered on `v*` tags.
  Build sdist + wheel, publish via trusted publishing (OIDC) or API token.

- [x] **BL-002 — SFTP backend documentation**
  Create `docs/backends/sftp.md` (installation, usage, options, API ref).
  Update `docs/backends/index.md` to mark SFTP as built-in, not planned.

- [x] **BL-003 — README backends table outdated**
  SFTP is listed as "Planned" but shipped in v0.2.0. Update to "Built-in".

- [x] **BL-004 — README & project description tone rework**
  Current tone is too academic. Rewrite README and pyproject description to be
  approachable, dev-friendly, and scannable. Keep it practical over formal.

- [x] **BL-005 — CITATION.cff**
  Add `CITATION.cff` to repo root for GitHub's citation button.
  Include author, title, version, license, repository URL, DOI (if applicable).

- [x] **BL-006 — Protect master branch with ruleset**
  Create a GitHub repository ruleset that enforces all changes go through pull
  requests. Include: require PR (0 approvals for solo dev), require CI status
  checks, block force pushes, restrict branch deletion. Apply to `master`.
  Done: repo public, ruleset "Protect master" active -- require PRs (0 approvals),
  require CI (lint, typecheck, test 3.10-3.14), block force push. Admin bypass enabled.

- [x] **BL-007 — Pin minimum dependency versions & clean up extras**
  Public extras have no lower bounds — pip can resolve ancient, incompatible
  versions. Add minimum pins: `paramiko>=2.2` (needs `posix_rename`),
  `tenacity>=4.0` (`before_sleep_log`, `retry_if_exception_type`),
  `s3fs>=2022.1` (`clear_instance_cache`, `client_kwargs`). Remove
  `typing-extensions` (unused — Python 3.10+ covers all needs) and `adlfs`
  (no Azure backend yet).

- [x] **BL-008 — Set up docs hosting**
  Configure GitHub Pages so the documentation site is reachable.
  Done: Pages enabled (source: GitHub Actions) at https://haalfi.github.io/remote-store/.
  Workflow `.github/workflows/docs.yml` deploys on push to master.

- [x] **BL-009 — Fix broken PyPI logo and badges**
  README logo used a relative path (`assets/logo.png`) which doesn't resolve on PyPI's
  CDN. Changed to absolute raw GitHub URL. Added PyPI version, Python versions, RTD,
  and license badges.

- [x] **BL-010 — Publish documentation to Read the Docs**
  Set up Read the Docs hosting alongside GitHub Pages. Updated `.readthedocs.yaml`
  (bumped to ubuntu-24.04), pointed `Documentation` URL in `pyproject.toml` to
  `https://remote-store.readthedocs.io/`, added RTD badge to README.
  Done: project imported on RTD, docs live at https://remote-store.readthedocs.io/.

---

## Backlog (Prioritized)

Next actions once release blockers are cleared.

- [x] **BK-001 — Azure backend**
  Write RFC (`sdd/rfcs/rfc-0001-azure-backend.md`), graduate to spec
  (`sdd/specs/012-azure-backend.md`), implement with `azure-storage-file-datalake`
  directly (not `adlfs`). See RFC-0001 for rationale.
  Done: `AzureBackend` implemented in v0.5.0 with HNS adaptive behavior,
  streaming reads, Azurite CI, and full conformance suite.
  → RFC: `sdd/rfcs/rfc-0001-azure-backend.md` (accepted)
  → Spec: `sdd/specs/012-azure-backend.md`

- [ ] **BK-002 — Glob / pattern matching strategy**
  Decide per-backend glob vs client-side abstraction. S3 has native prefix listing,
  SFTP does not. Spec the chosen approach or document why it stays per-backend.
  → Spec: TBD (extends `003-backend-adapter-contract.md`)

---

## Audit Findings (AUD-001)

From adversarial review of v0.5.0. Full details: `sdd/audit-001-adversarial-review.md`.

**Critical (confirmed) -- fix before next release:**

- [x] **AF-001 — Auto-register S3/SFTP/S3-PyArrow backends in Registry**
  `_register_builtin_backends()` only registers `local` and `azure`. README S3 Quick Start is broken.
  → Audit: C-1 (confirmed)
  Done: v0.6.0 — `_register_builtin_backends()` now registers S3, SFTP, and S3-PyArrow
  when their dependencies are installed.

- [x] **AF-002 — Remove or gate GLOB/RECURSIVE_LIST ghost capabilities**
  4 backends claim GLOB support; no `glob()` method exists. Either remove from `CapabilitySet` or
  implement BK-002 first. `RECURSIVE_LIST` is also unused.
  → Audit: C-2, M-7 (confirmed). Related: BK-002 (glob strategy).
  Done: v0.6.0 — Removed `Capability.GLOB` and `Capability.RECURSIVE_LIST` enum members.
  BK-002 remains open for future glob design.

**High -- semantic bugs & process-wide side effects:**

- [x] **AF-003 — Fix `S3Backend.close()` global cache side effect**
  `clear_instance_cache()` is a class method. Existing refs still work, but new backends after
  the clear create duplicates instead of reusing. Resource leak risk, not data corruption.
  → Audit: H-0 (partial, downgraded from Critical)
  Done: v0.6.0 — Removed `clear_instance_cache()` call from S3/S3-PyArrow `close()`.

- [x] **AF-004 — Unify `get_folder_info` behavior on empty folders**
  LocalBackend returns success; S3/SFTP/Azure raise `NotFound`. Pick one semantic.
  → Audit: H-1 (unverified)
  Done: S3 and S3-PyArrow now return `FolderInfo(file_count=0)` when a folder
  exists but has no files (the `exists()` check gates non-existent folders).
  Azure non-HNS retains `NotFound` for `file_count==0` — this is correct
  because non-HNS has no concept of empty folders (they are virtual prefixes).

- [x] **AF-005 — Fix `delete_folder` error types**
  LocalBackend raises `NotFound` for non-empty folders (wrong). Others use base `RemoteStoreError`.
  Consider adding a `NotEmpty` error or documenting the chosen behavior.
  → Audit: H-2 (unverified)
  Done: v0.6.0 — Added `DirectoryNotEmpty` error type; non-empty folder deletes now
  raise `DirectoryNotEmpty` instead of generic errors.

- [x] **AF-006 — Fix native exception leakage through lazy streams**
  `read()` returns inside `_errors()` context manager but the stream is lazy. Backend-native
  exceptions during data reads leak unmapped.
  → Audit: H-3 (unverified)
  Done: v0.6.0 — Added `_ErrorMappingStream` wrapper that catches `OSError` during
  lazy reads and maps them through each backend's error classifier.

- [x] **AF-007 — Wire Azure backend into docs site**
  Add to `mkdocs.yml` nav, `generate_docs.py`, and remove `not_found: info` suppression.
  → Audit: H-4 (unverified)
  Done: v0.6.0 — Azure guide added to docs navigation.

**Medium -- security & design:**

- [x] **AF-008 — Add credential masking to backend `__repr__`**
  All backends store secrets as plain attributes. Add `__repr__` that masks sensitive fields.
  → Audit: M-2 (confirmed)
  Done: Added `__repr__` to all 5 backends. Sensitive fields (key, secret,
  password, pkey, account_key, sas_token, connection_string, credential)
  display as `'***'` when set and `None` when unset. Non-sensitive fields
  (bucket, host, container, etc.) shown in clear text. Masking verified by
  unit tests for every backend and conformance-level test for live backends.

- [x] **AF-009 — Fix `Registry.close()` to close all backends on error**
  Wrap in try/finally so one failed `close()` doesn't skip the rest.
  → Audit: M-9 (confirmed)
  Done: `close()` now catches exceptions from individual backends, continues
  closing the rest, always runs `_backends.clear()`, and re-raises the first
  error encountered.

- [ ] **AF-010 — Document TOCTOU and non-atomic move limitations**
  `overwrite=False` has inherent TOCTOU (M-4, downgraded from High: inherent limitation).
  S3 `move()` is copy+delete (L-21, downgraded from High: per spec S3-013, not a bug).
  Document these in guides or API docs so users know the guarantees.
  → Audit: M-4 (partial), L-21 (design-intent)

- [x] **AF-011 — Remove dead `RemoteFile`/`RemoteFolder` from public API**
  Nothing uses them. Remove from `_models.py` and `__all__`.
  → Audit: M-6 (confirmed)
  Done: Removed class definitions from `_models.py`, imports from `__init__.py`
  and `__all__`, associated tests (MOD-006), docs entries, and spec section.
  Updated MOD-007 spec to reference only `FileInfo` and `FolderInfo`.

**Medium -- testing & CI:**

- [ ] **AF-012 — Add capability gating tests (STORE-006)**
  Test that Store methods raise `CapabilityNotSupported` for backends missing capabilities.
  → Audit: M-11 (unverified)

- [ ] **AF-013 — Add PermissionDenied/BackendUnavailable error path tests**
  S3-016, S3-017, SFTP-021/022/023 have zero test coverage.
  → Audit: M-16 (unverified)

- [ ] **AF-014 — Add CI gate to publish workflow**
  Require CI workflow to pass before PyPI publish.
  → Audit: M-18 (unverified)

- [x] **AF-015 — Update stale v0.5.0 docs**
  SECURITY.md versions, CONTRIBUTING.md structure, examples/configuration.py Azure example,
  README Azure SDK name, CHANGELOG `[Unreleased]` section.
  → Audit: L-1 through L-5
  Done: L-1 (README `azure-storage-file-datalake`), L-2 (SECURITY.md, earlier),
  L-3 (CONTRIBUTING.md spec 012), L-4 (Azure config example), L-5 (`[Unreleased]`
  section in CHANGELOG).

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

- [x] **ID-011 — Python 3.14 support** *(promoted to BK-004)*

- [ ] **ID-012 — Performance benchmarks**
  Add benchmarks for large file operations, streaming throughput, and atomic
  writes across backends. Use `pytest-benchmark` or a standalone script suite.
  Establishes a baseline before optimizing and catches regressions.

- [ ] **ID-013 — Async Store / Backend API**
  Async version of `Store` and `Backend` for use in async frameworks (FastAPI,
  aiohttp, etc.). Could be a parallel `AsyncStore` class or an async mode on
  the existing `Store`. Needs design decision on whether to wrap sync backends
  with `asyncio.to_thread` or require native async backends.

- [x] **ID-014 — Streaming conformance tests** *(done)*
  Added `TestStreamingConformance` class in `test_conformance.py` with 5 tests
  (x4 backends = 20 test cases): not-BytesIO assertion, chunked reads, stream
  position, BinaryIO write, and write-from-current-position. Spec: SIO-001, SIO-003.

- [ ] **ID-015 — Audit external deep links**
  v0.4.3 fixed a broken ReadTheDocs link in the README (missing `/en/latest/`
  prefix). Other docs, docstrings, or example files may contain similar
  bare RTD URLs. Sweep for `readthedocs.io/` links without a version prefix
  and fix them. One-time task.

- [~] **ID-017 — Memory backend**
  Tree-indexed in-memory backend. Zero dependencies, no filesystem access.
  Primary use cases: unit testing (no temp dir setup/teardown), interactive
  exploration, documentation examples, CI speed, large in-process data
  structures. Simpler than `LocalBackend` — no path resolution, no OS errors,
  no atomicity concerns. Passes the full conformance suite with zero skips.
  Built-in (no optional extra needed).
  → Spec: `sdd/specs/013-memory-backend.md`

- [ ] **ID-016 — PyArrow FileSystemHandler adapter**
  Implement a `StoreFileSystemHandler` in `ext/arrow.py` that wraps any
  `Store` into a `pyarrow.fs.PyFileSystem` via `pyarrow.fs.FileSystemHandler`.
  Enables seamless use of any backend with PyArrow, Pandas, Iceberg, Delta Lake,
  DuckDB, and Polars. Optional `pyarrow` dependency, zero impact on core.
  Aligns with ADR-0003.
  → RFC: `sdd/rfcs/rfc-0002-pyarrow-filesystem-adapter.md`

- [ ] **ID-018 — conda-forge publishing**
  Submit a staged-recipes PR to conda-forge so users can `conda install -c
  conda-forge remote-store`. Pure-Python wheel, so the recipe should be
  straightforward. Consider once the project reaches Beta or if user demand
  appears. Reference: https://conda-forge.org/docs/maintainer/adding_pkgs/

---

## Done

Items completed and kept here for reference.

- [x] **DONE-001 — PEP 604 type hints**
  All source files already use `X | Y` syntax with `from __future__ import annotations`.
  mypy strict mode enforced in CI. No action needed.

- [x] **DONE-002 — Native path resolution (`to_key`)** *(was BK-003)*
  Fixed the Store round-trip bug (listing returned backend-relative paths that
  included `root_path`, breaking re-use as input) and added public
  `Store.to_key(path)` / `Backend.to_key()` for converting native paths to
  store-relative keys.
  → Spec: `sdd/specs/010-native-path-resolution.md`

- [x] **DONE-003 — Python 3.14 support** *(was BK-004)*
  Added `3.14` to CI test matrix and `Programming Language :: Python :: 3.14`
  classifier. No code changes needed — codebase already uses
  `from __future__ import annotations` everywhere (DONE-001) and performs no
  runtime annotation inspection, so PEP 649 is a non-issue.

- [x] **DONE-004 — S3-PyArrow hybrid backend** *(v0.4.0)*
  Hybrid S3 backend using PyArrow's C++ S3 filesystem for data-path operations
  (read, write, copy) and s3fs for control-path operations (listing, metadata,
  deletion). Drop-in alternative to S3Backend with the same constructor
  signature. New optional extra: `s3-pyarrow`.
  → Spec: `sdd/specs/011-s3-pyarrow-backend.md`
