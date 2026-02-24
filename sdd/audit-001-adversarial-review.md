# Audit 001 -- Adversarial Review of v0.5.0

**Date:** 2026-02-24
**Scope:** Full codebase, master branch at commit `fee322b` (v0.5.0)
**Method:** Four parallel AI agents performed independent deep audits of: (1) source code security, (2) test suite gaps, (3) API design anti-patterns, (4) CI/packaging/docs quality. Human consolidated and deduplicated findings.

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 3 | Broken documented usage, lying capabilities, process-wide side effects |
| High | 6 | Semantic inconsistencies, non-atomic ops, leaked native exceptions, broken docs |
| Medium | 18 | Security, design, testing, and CI gaps |
| Low | 20 | Papercuts, naming, missing edge cases |

---

## Critical

### C-1. S3/SFTP/S3-PyArrow backends not auto-registered

`_registry.py:28-42` only registers `"local"` and `"azure"`. The README Quick Start example for S3 crashes with `ValueError: Unknown backend type 's3'`. The documented happy path for the three most common remote backends does not work via `Registry`.

### C-2. GLOB capability is a ghost

`_capabilities.py:24` defines `GLOB = "glob"`. Local, S3, S3-PyArrow, and Azure backends include it in their `CapabilitySet`. `store.supports(Capability.GLOB)` returns `True`. But no `glob()` method exists on `Backend`, `Store`, or any backend. Azure spec AZ-019 describes a full implementation that was never written. The capability system promises something the code cannot deliver.

### C-3. `S3Backend.close()` nukes the global s3fs instance cache

`_s3.py:351` calls `clear_instance_cache()` which is a class method affecting ALL `S3FileSystem` instances in the process. Closing one `S3Backend` can invalidate another's cached filesystem. Same issue in `_s3_pyarrow.py:458`.

---

## High

### H-1. `get_folder_info` on empty folders: inconsistent across backends

LocalBackend returns `FolderInfo(file_count=0)` (success). S3, SFTP, and Azure (non-HNS) raise `NotFound` because `file_count == 0`. The "unified interface" gives different exceptions for the same operation depending on the backend.

### H-2. `delete_folder` non-recursive on non-empty folder: wrong/inconsistent error types

LocalBackend (`_local.py:185`) raises `NotFound("Folder not empty")` -- semantically wrong. SFTP, S3, and Azure raise `RemoteStoreError` (base class) instead of a specific error type. No `NotEmpty` error exists.

### H-3. Native exceptions leak through lazy-evaluated streams

`read()` returns inside an `_errors()` context manager, but the returned `BinaryIO` is lazy. Exceptions during data reads happen after the context manager exits, so backend-native exceptions (botocore, paramiko, Azure SDK) leak unmapped.

### H-4. TOCTOU race conditions in all write operations

Every backend checks `exists()` then writes for `overwrite=False`. Between check and write, concurrent access can create silent data loss. LocalBackend could use `O_CREAT | O_EXCL`; S3 could use conditional PUT. None do.

### H-5. S3 `move()` is non-atomic

`_s3.py:335-336`: `copy()` then `rm()`. Crash between the two leaves duplicates. Same in S3-PyArrow. Not documented.

### H-6. Azure docs page is a 404

`guides/backends/azure.md` exists but is not wired into `mkdocs.yml` nav or `generate_docs.py`. The backends index links to it, producing a broken link. `mkdocs.yml` line 65-66 has `not_found: info` which suppresses the error in CI.

---

## Medium -- Security

### M-1. No path traversal defense in non-local backends used directly

LocalBackend has `_resolve()` with `Path.resolve()` + `relative_to(root)`. SFTP, S3, and Azure backends do pure string concatenation. Using a backend directly (public API) with `../../etc/passwd` bypasses `RemotePath` validation. Store layer blocks it; backend layer does not.

### M-2. Credentials stored as plain instance attributes

All backends store secrets (`_key`, `_secret`, `_password`, `_account_key`, `_sas_token`) as plain attributes. `repr(vars(backend))` dumps all credentials. No `__repr__` masking.

### M-3. Azure `start_copy_from_url(src_bc.url)` may expose SAS tokens

`_azure.py:617`: The source blob URL may contain the SAS token. If logged by the Azure SDK, it leaks.

---

## Medium -- Design

### M-4. `FileInfo.__eq__` ignores everything except path

Two `FileInfo` objects with same path but different size/checksum/mtime are equal. Silent data loss in sets.

### M-5. Config "immutability" is shallow

`BackendConfig` and `StoreProfile` are `frozen=True` dataclasses, but `options: dict` is mutable. `config.options["key"] = "val"` works. README says "immutable."

### M-6. `RemoteFile`/`RemoteFolder` are dead code

Defined in `_models.py`, exported in `__all__`. Nothing in the codebase uses them.

### M-7. `RECURSIVE_LIST` capability declared but meaningless

No method checks for it. `list_files(recursive=True)` works regardless.

### M-8. `list_folders` returns names, `list_files` returns `FileInfo` -- asymmetric API

Folder metadata requires N+1 `get_folder_info()` calls.

### M-9. `Registry.close()` leaks backends on error

If the first `backend.close()` raises, remaining backends are never closed. No try/finally.

### M-10. Lazy initialization is not thread-safe

All backends use unsynchronized check-then-create for client instances. Two threads can create duplicate clients, orphaning one (never closed). Spec STORE-007 claims thread safety.

---

## Medium -- Testing & CI

### M-11. STORE-006 (Capability Gating) completely untested

No test creates a backend with reduced capabilities and verifies Store raises before delegation.

### M-12. Azure HNS tested only via unconstrained MagicMock

`test_azure.py:499-619`: All mocks use `MagicMock()` without `spec=True`. Accept any call, any args. Never validated against real Azure HNS.

### M-13. 95% coverage inflated by `test_coverage_gaps.py`

Contains tests like `assert WritableContent is not None` -- asserting imports succeeded. ~30 tests exist solely to hit coverage lines with zero behavioral verification.

### M-14. Zero concurrency tests despite thread safety claims

STORE-007 spec claims thread safety. No test spawns threads.

### M-15. CI runs only on Ubuntu -- claims "OS Independent"

`pyproject.toml` declares `Operating System :: OS Independent`. Zero macOS/Windows CI. Project's own history documents a Windows locale bug.

### M-16. No test for PermissionDenied/BackendUnavailable in S3/SFTP

Spec items S3-016, S3-017, SFTP-021/022/023 describe error mapping. Zero tests trigger these paths.

### M-17. SFTP retry logic (SFTP-009) never tested

Tenacity retry config could be wrong. Nothing detects it.

### M-18. Publish workflow has no CI gate

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
