# Audit 001 -- Adversarial Review of v0.5.0

**Date:** 2026-02-24
**Scope:** Full codebase, master branch at commit `fee322b` (v0.5.0)
**Method:** Four parallel AI agents performed independent deep audits of: (1) source code security, (2) test suite gaps, (3) API design anti-patterns, (4) CI/packaging/docs quality. Human consolidated and deduplicated findings.

**Verification note:** Findings were produced by AI agents and then spot-checked against actual code. Each finding includes a verification status: **confirmed** (verified against code), **partial** (issue exists but severity/framing overstated), **design-intent** (intentional behavior per spec), or **unverified** (not yet spot-checked). Line references are point-in-time for commit `fee322b`.

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 2 | Broken documented usage, lying capabilities |
| High | 5 | Semantic inconsistencies, leaked native exceptions, broken docs, process-wide side effect |
| Medium | 19 | Security, design, testing, and CI gaps |
| Low | 21 | Papercuts, naming, missing edge cases, inherent limitations |

---

## Critical

### C-1. S3/SFTP/S3-PyArrow backends not auto-registered -- *confirmed*

`_register_builtin_backends()` only registers `"local"` and `"azure"`. The README Quick Start example for S3 crashes with `ValueError: Unknown backend type 's3'`. The documented happy path for the three most common remote backends does not work via `Registry`. Verified: no conditional import block exists for s3, sftp, or s3-pyarrow in `_registry.py`.

### C-2. GLOB capability is a ghost -- *confirmed*

`_capabilities.py` defines `GLOB = "glob"`. Local, S3, S3-PyArrow, and Azure backends include it in their `CapabilitySet`. `store.supports(Capability.GLOB)` returns `True`. But no `glob()` method exists on `Backend`, `Store`, or any backend. The capability system promises something the code cannot deliver. See also BK-002 in backlog.

---

## High

### H-0. `S3Backend.close()` clears the global s3fs instance cache -- *partial*

`close()` in S3Backend and S3PyArrowBackend calls `S3FileSystem.clear_instance_cache()`, which is a class method affecting all cached instances in the process. However, existing references to `S3FileSystem` objects remain valid -- the cache is just a lookup table for reuse, not a lifecycle manager. The real risk is that a *new* backend created after the cache clear will create a duplicate filesystem instead of reusing the existing one. Severity downgraded from Critical: not data-corrupting, but still a process-wide side effect that can cause resource leaks.

### H-1. `get_folder_info` on empty folders: inconsistent across backends -- *unverified*

LocalBackend returns `FolderInfo(file_count=0)` (success). S3, SFTP, and Azure (non-HNS) raise `NotFound` because `file_count == 0`. The "unified interface" gives different exceptions for the same operation depending on the backend.

### H-2. `delete_folder` non-recursive on non-empty folder: wrong/inconsistent error types -- *unverified*

LocalBackend raises `NotFound("Folder not empty")` -- semantically wrong. SFTP, S3, and Azure raise `RemoteStoreError` (base class) instead of a specific error type. No `NotEmpty` error exists.

### H-3. Native exceptions leak through lazy-evaluated streams -- *unverified*

`read()` returns inside an `_errors()` context manager, but the returned `BinaryIO` is lazy. Exceptions during data reads happen after the context manager exits, so backend-native exceptions (botocore, paramiko, Azure SDK) leak unmapped.

### H-4. Azure docs page is a 404 -- *unverified*

`guides/backends/azure.md` exists but is not wired into `mkdocs.yml` nav or `generate_docs.py`. The backends index links to it, producing a broken link. `mkdocs.yml` has `not_found: info` which suppresses the error in CI.

---

## Medium -- Security

### M-1. No path traversal defense in non-local backends used directly -- *unverified*

LocalBackend has `_resolve()` with `Path.resolve()` + `relative_to(root)`. SFTP, S3, and Azure backends do pure string concatenation. Using a backend directly (public API) with `../../etc/passwd` bypasses `RemotePath` validation. Store layer blocks it; backend layer does not.

### M-2. Credentials stored as plain instance attributes -- *confirmed*

All backends store secrets (`_key`, `_secret`, `_password`, `_account_key`, `_sas_token`) as plain attributes. `repr(vars(backend))` dumps all credentials. No `__repr__` masking.

### M-3. Azure `start_copy_from_url(src_bc.url)` may expose SAS tokens -- *unverified*

`_azure.py:617`: The source blob URL may contain the SAS token. If logged by the Azure SDK, it leaks.

---

## Medium -- Design

### M-4. TOCTOU race conditions in `overwrite=False` writes -- *partial*

Every backend checks `exists()` then writes for `overwrite=False`. Between check and write, concurrent access can create conflicts. LocalBackend could use `O_CREAT | O_EXCL`; S3 could use conditional PUT. Downgraded from High: this is inherent to all filesystem abstractions without hardware transactional support. For remote backends (S3, SFTP, Azure), no portable atomic create-if-not-exists exists. For LocalBackend, it's fixable. Document as a known limitation.

### M-5a. `FileInfo.__eq__` ignores everything except path -- *design-intent*

Two `FileInfo` objects with same path but different size/checksum/mtime are equal. This is intentional per spec MOD-007 ("equality and hashing based on `path`"). File identity is path identity in most filesystem semantics. Downgraded from Medium: not a bug, but worth noting for users who put `FileInfo` objects in sets expecting content-aware deduplication.

### M-5. Config "immutability" is shallow -- *unverified*

`BackendConfig` and `StoreProfile` are `frozen=True` dataclasses, but `options: dict` is mutable. `config.options["key"] = "val"` works. README says "immutable."

### M-6. `RemoteFile`/`RemoteFolder` are dead code -- *confirmed*

Defined in `_models.py`, exported in `__all__`. Nothing in the codebase uses them.

### M-7. `RECURSIVE_LIST` capability declared but meaningless -- *unverified*

No method checks for it. `list_files(recursive=True)` works regardless.

### M-8. `list_folders` returns names, `list_files` returns `FileInfo` -- asymmetric API -- *unverified*

Folder metadata requires N+1 `get_folder_info()` calls.

### M-9. `Registry.close()` leaks backends on error -- *confirmed*

If the first `backend.close()` raises, remaining backends are never closed. No try/finally.

### M-10. Lazy initialization is not thread-safe -- *unverified*

All backends use unsynchronized check-then-create for client instances. Two threads can create duplicate clients, orphaning one (never closed). Spec STORE-007 claims thread safety.

---

## Medium -- Testing & CI

### M-11. STORE-006 (Capability Gating) completely untested -- *unverified*

No test creates a backend with reduced capabilities and verifies Store raises before delegation.

### M-12. Azure HNS tested only via unconstrained MagicMock -- *unverified*

`test_azure.py:499-619`: All mocks use `MagicMock()` without `spec=True`. Accept any call, any args. Never validated against real Azure HNS.

### M-13. 95% coverage inflated by `test_coverage_gaps.py` -- *unverified*

Contains tests like `assert WritableContent is not None` -- asserting imports succeeded. ~30 tests exist solely to hit coverage lines with zero behavioral verification.

### M-14. Zero concurrency tests despite thread safety claims -- *unverified*

STORE-007 spec claims thread safety. No test spawns threads.

### M-15. CI runs only on Ubuntu -- claims "OS Independent" -- *confirmed*

`pyproject.toml` declares `Operating System :: OS Independent`. Zero macOS/Windows CI. Project's own history documents a Windows locale bug.

### M-16. No test for PermissionDenied/BackendUnavailable in S3/SFTP -- *unverified*

Spec items S3-016, S3-017, SFTP-021/022/023 describe error mapping. Zero tests trigger these paths.

### M-17. SFTP retry logic (SFTP-009) never tested -- *unverified*

Tenacity retry config could be wrong. Nothing detects it.

### M-18. Publish workflow has no CI gate -- *unverified*

Triggers on `v*` tag push. Does not require CI to pass.

---

## Low

### L-1. README says `azure-storage-blob`, actual dep is `azure-storage-file-datalake`

### L-2. SECURITY.md supported versions stuck at 0.4.x

### L-3. CONTRIBUTING.md repo structure missing spec 012

### L-4. `examples/configuration.py` has no Azure example

### L-5. No `[Unreleased]` section in CHANGELOG

### L-6. `hatch run all` in CONTRIBUTING.md fails -- hatch not a dev dependency

### L-7. docs extra missing paramiko, pyarrow, azure SDKs

### L-8. sdist includes tests, specs, workflows, internal docs

### L-9. SFTP `_rmtree`/`_collect_folder_stats` use Python recursion (RecursionError at depth >1000)

### L-10. `read_bytes()` has no size limit -- memory bomb

### L-11. LocalBackend `list_files` follows symlinks outside root, leaking metadata

### L-12. SFTP username logged at INFO level

### L-13. S3 error classification uses fragile string matching on exception messages

### L-14. Inconsistent root path parameter naming (`root`/`bucket`/`container`/`base_path`)

### L-15. Azurite started via npx in CI without setup-node action

### L-16. `mkdocs.yml` validation `not_found: info` suppresses broken link errors

### L-17. 18 Azure spec items have no `@pytest.mark.spec` tag

### L-18. `test_list_files_round_trip` checks `len(data) == 3` not actual content

### L-19. S3/S3-PyArrow test files are ~500 lines of near-identical copy-paste

### L-20. No tests for Unicode paths, special characters, empty files, or large files

### L-21. S3 `move()` is non-atomic -- *design-intent*

S3 `move()` is implemented as copy + delete. Crash between the two leaves duplicates. Same in S3-PyArrow and Azure (non-HNS). This is how S3 works -- there is no native rename operation. Every S3 library does copy+delete. Already documented in spec S3-013 and Azure spec. Downgraded from High: inherent platform limitation, not a bug.
