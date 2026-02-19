# Development Backlog

Tracking file for release blockers, prioritized work, and unprioritized ideas.
Items graduate through the SDD pipeline: **Idea → Backlog → RFC/Spec → Tests → Code**.

Status legend: `[ ]` pending · `[-]` in progress · `[x]` done

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

---

## Backlog (Prioritized)

Next actions once release blockers are cleared.

- [ ] **BK-001 — Azure Blob backend**
  Write RFC (`sdd/rfcs/rfc-0002-azure-backend.md`), graduate to spec
  (`sdd/specs/010-azure-backend.md`), implement with `adlfs`.
  → Spec: TBD

- [ ] **BK-002 — Glob / pattern matching strategy**
  Decide per-backend glob vs client-side abstraction. S3 has native prefix listing,
  SFTP does not. Spec the chosen approach or document why it stays per-backend.
  → Spec: TBD (extends `003-backend-adapter-contract.md`)

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
  Expose a `Store.glob(pattern)` method backed by `Capability.GLOB` (already
  declared but unused). Local has it, S3 can do prefix filtering natively, SFTP
  would need client-side filtering. Ships alongside or after BK-002.

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
