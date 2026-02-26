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
  capabilities. No tests exist for this path yet.

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

- [~] **ID-016 — PyArrow FileSystemHandler adapter**
  Implement a `StoreFileSystemHandler` in `ext/arrow.py` that wraps any
  `Store` into a `pyarrow.fs.PyFileSystem` via `pyarrow.fs.FileSystemHandler`.
  Enables seamless use of any backend with PyArrow, Pandas, Iceberg, Delta Lake,
  DuckDB, and Polars. Optional `pyarrow` dependency, zero impact on core.
  Aligns with ADR-0003.
  → RFC: `sdd/rfcs/rfc-0002-pyarrow-filesystem-adapter.md`
  → Spec: `sdd/specs/013-pyarrow-filesystem-adapter.md` (drafting)

- [ ] **ID-017 — Memory backend**
  In-memory backend backed by a `dict[str, bytes]`. Zero dependencies, no
  filesystem access. Primary use cases: unit testing (no temp dir setup/teardown),
  interactive exploration, documentation examples, CI speed. Simpler than
  `LocalBackend` — no path resolution, no OS errors, no atomicity concerns.
  Should pass the full conformance suite. Built-in (no optional extra needed).

- [ ] **ID-018 — conda-forge publishing**
  Submit a staged-recipes PR to conda-forge so users can `conda install -c
  conda-forge remote-store`. Pure-Python wheel, so the recipe should be
  straightforward. Consider once the project reaches Beta or if user demand
  appears.

---

## Done

Completed items, grouped by origin. Kept for traceability.

### Release blockers (v0.3.0–v0.4.1)

All v1.0 release blockers were resolved across v0.3.0–v0.4.1.

- [x] **BL-001 — PyPI publish workflow** (v0.3.0)
- [x] **BL-002 — SFTP backend documentation** (v0.3.0)
- [x] **BL-003 — README backends table outdated** (v0.3.0)
- [x] **BL-004 — README & project description tone rework** (v0.3.0)
- [x] **BL-005 — CITATION.cff** (v0.3.0)
- [x] **BL-006 — Protect master branch with ruleset** (v0.3.0)
- [x] **BL-007 — Pin minimum dependency versions & clean up extras** (v0.3.0)
- [x] **BL-008 — Set up docs hosting** (v0.3.0)
- [x] **BL-009 — Fix broken PyPI logo and badges** (v0.4.1)
- [x] **BL-010 — Publish documentation to Read the Docs** (v0.4.1)

### Backlog items

- [x] **BK-001 — Azure backend** (v0.5.0)
  `AzureBackend` with HNS adaptive behavior, streaming reads, Azurite CI,
  and full conformance suite.
  → RFC: `sdd/rfcs/rfc-0001-azure-backend.md` · Spec: `sdd/specs/012-azure-backend.md`

- [x] **BK-003 — Native path resolution (`to_key`)** (v0.3.0)
  Fixed Store round-trip bug; added `Store.to_key()` / `Backend.to_key()`.
  → Spec: `sdd/specs/010-native-path-resolution.md`

- [x] **BK-004 — Python 3.14 support** (v0.3.0)
  Added to CI matrix and PyPI classifiers. No code changes needed.

### Audit findings (v0.6.0–v0.6.1)

From adversarial review of v0.5.0. Full report: `sdd/audit-001-adversarial-review.md`.

- [x] **AF-001 — Auto-register S3/SFTP/S3-PyArrow in Registry** (v0.6.0)
- [x] **AF-002 — Remove GLOB/RECURSIVE_LIST ghost capabilities** (v0.6.0)
- [x] **AF-003 — Fix `S3Backend.close()` global cache side effect** (v0.6.0)
- [x] **AF-004 — Unify `get_folder_info` on empty folders** (v0.6.0/v0.6.1)
- [x] **AF-005 — Fix `delete_folder` error types** (v0.6.0)
- [x] **AF-006 — Fix native exception leakage through lazy streams** (v0.6.0)
- [x] **AF-007 — Wire Azure backend into docs site** (v0.6.0)
- [x] **AF-008 — Add credential masking to backend `__repr__`** (v0.6.1)
- [x] **AF-009 — Fix `Registry.close()` to close all backends on error** (v0.6.1)
- [x] **AF-011 — Remove dead `RemoteFile`/`RemoteFolder`** (v0.6.1)
- [x] **AF-015 — Update stale v0.5.0 docs** (v0.6.1)

### Ideas shipped

- [x] **ID-011 — Python 3.14 support** (v0.3.0) → graduated to BK-004
- [x] **ID-012 — Performance benchmarks** (v0.5.0)
  Benchmark suite with Docker-hosted backends: throughput, TTFB, memory,
  large-file, listing, metadata, and destructive operation scenarios.
- [x] **ID-014 — Streaming conformance tests** (v0.4.4)
  `TestStreamingConformance` in `test_conformance.py`: 5 tests × 4 backends.

### Other completed work

- [x] **DONE-001 — PEP 604 type hints**
  All source uses `X | Y` with `from __future__ import annotations`. mypy strict in CI.

- [x] **DONE-004 — S3-PyArrow hybrid backend** (v0.4.0)
  PyArrow C++ data path + s3fs control path. Optional extra: `s3-pyarrow`.
  → Spec: `sdd/specs/011-s3-pyarrow-backend.md`
