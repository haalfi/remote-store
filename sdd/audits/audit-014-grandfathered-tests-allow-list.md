# Audit 014 — `_BACKEND_AT_ROOT_GRANDFATHERED` allow-list

**Backlog item:** BK-191
**Date:** 2026-05-13
**Scope:** The seven `tests/test_*.py` files grandfathered into the TEST-003
placement exception via `scripts/check_test_placement.py::_BACKEND_AT_ROOT_GRANDFATHERED`.
**Method:** AST-level enumeration of every `from remote_store.backends._<x>` / `import remote_store.backends._<x>` / `from remote_store.backends import <Name>` site (top-level and function-local). Each test was read in context to determine whether its assertions are per-backend, cross-backend, or example-driven.

---

## Background

`scripts/check_test_placement.py` Rule B forbids any test file at `tests/`
root from importing concrete cloud / network backend modules. Allowed
backends are `_memory`, `_local`, `_fileinfo`. Banned backends are
discovered dynamically from `src/remote_store/backends/`. Three import
styles are flagged:

1. `from remote_store.backends._<x> import …` (private path)
2. `import remote_store.backends._<x>` (with/without alias)
3. `from remote_store.backends import <BannedName>` or `import *`

The checker walks the **full AST**, so function-local and conditional
imports fire Rule B just as top-level imports do. The grandfather list
exists because seven legacy files had concrete-backend imports nested
inside tests that were intended to exercise cross-protocol contracts.

The checker also has stale-grandfather detection (`stale = grandfathered
- grandfather_actually_violating`): if a grandfathered file no longer
fires Rule B, the entry is reported as dead weight to remove. **As of this
audit (2026-05-13), all seven entries actively fired Rule B** — removing any
one of them produced real violations. This rules out the "easy keep +
document" disposition sketched in the chat-only audit summary that preceded
this document.

## Allow-list as of 2026-05-13

```python
_BACKEND_AT_ROOT_GRANDFATHERED: frozenset[str] = frozenset(
    {
        "test_config.py",
        "test_coverage_gaps.py",
        "test_depth_listing.py",
        "test_examples.py",
        "test_pbt_write_result.py",
        "test_ping.py",
        "test_seekable.py",
    }
)
```

## Per-file findings

### `tests/test_config.py` — disposition: **(a) per-backend split**

| Line | Backend | Test |
|---|---|---|
| 351, 359, 367 | `_sftp` | `test_sftp_enum_coercion`, `test_sftp_invalid_policy_raises`, `test_sftp_enum_passthrough` (SEC-005) |
| 759 | `_sftp` | `test_sftp_retry` (RET-011) |
| 767 | `_s3` | `test_s3_accepts_retry` (RET-011) |
| 775 | `_azure` | `test_azure_accepts_retry` (RET-012) |
| 787 | `_s3_pyarrow` | `test_s3_pyarrow_accepts_retry` (RET-013) |
| 838, 851, 863, 881 | `_azure`, `_s3`, `_s3_pyarrow` | RET-012-style retry mapping per backend |

Every nested-import site is a **per-backend** assertion. The tests are not cross-cutting — each touches exactly one backend. They are bundled into `test_config.py` only because they all test "the config layer," but the config layer is itself per-backend. TEST-003 directly applies: move each backend's tests into `tests/backends/<x>/test_config.py`.

**Refactor cost:** moderate. ~13 tests split across `sftp/`, `s3/`, `azure/`, plus the S3-PyArrow tests (which append to `tests/backends/s3/test_pyarrow.py` — no `tests/backends/s3_pyarrow/` directory exists). Existing per-backend test files already exist (e.g., `tests/backends/sftp/test_config.py`), so the new tests land alongside neighbours.

**Risk:** low. No shared fixtures across the per-backend tests; each is self-contained.

### `tests/test_coverage_gaps.py` — disposition: **(b) conformance reshape (secret-masking) + (a) per-backend split (init coverage)**

| Line | Backend | Construct |
|---|---|---|
| 378, 384 | `_s3` | `_s3_with_secrets()` / `_s3_no_secrets()` factories |
| 390, 396 | `_s3_pyarrow` | factories |
| 402, 408 | `_sftp` | factories |
| 414, 427 | `_azure` | factories |
| 491–512 | `_s3`, `_s3_pyarrow`, `_sftp`, `_azure` | `__import__` lambda forms (string-loaded, **invisible to the AST checker**) |

Two clusters in this file:

- **Secret-masking parametrize tests** (`_MASKING_UNSET_CASES`, `_SECRET_CASES`) verify the same `repr()` masking contract across S3, S3-PyArrow, SFTP, Azure. The AST-invisible `__import__` form on lines 491–512 was added specifically to evade the placement checker on string-form imports. This is a **cross-protocol invariant** ideal for conformance parametrize.
- **Function-local imports at 378–427** are still classic per-backend init/repr assertions, not the cross-protocol set.

Recommend: lift the secret-masking parametrize block into `tests/backends/conformance/test_secret_masking.py` (parametrize over registry fixtures); move the per-backend init tests into their respective `tests/backends/<x>/test_coverage_gaps.py`; replace the `__import__` string trick with proper conformance fixtures.

**Refactor cost:** moderate-to-high. The secret-masking machinery uses `Secret()` wrappers and per-backend `__repr__` substrings — conformance form needs a `secret_masking_spec` registry attribute or backend-side helper.

**Risk:** medium. The `__import__` lambdas signal an intentional checker bypass; whoever wrote them likely tried the obvious split and stopped. Worth checking the git blame for context before refactoring.

### `tests/test_depth_listing.py` — disposition: **(a) lift three backend-specific snippets + (b) consolidate into existing conformance — reconsidered, see below**

| Line | Backend | Construct |
|---|---|---|
| 294 | `_sftp` | `SFTPBackend` import in the `sftp_stub` fixture of `TestSFTPBackendNativeDepth` |
| 459 | `_s3_base` | `_S3Base` import in `test_s3_base_accepts_max_depth` (an `inspect.signature` check) |
| 469 | `_azure` | `AzureBackend` import in `test_azure_accepts_max_depth` (an `inspect.signature` check) |

Only the three function-local imports above fire Rule B; the top-level imports (`_memory`, `_local`) are allowed and the rest of the file is clean. DEPTH-001 / DEPTH-002 are Store-level features (spec 037: "Client-side filtering at the Store level" / "No Backend ABC change"); DEPTH-003 is the backend-native `max_depth` optimisation, whose result is identical whether a backend prunes natively or the Store filters client-side.

**Shipped (BK-218):**

- **(a)** The three backend-specific snippets each move to a per-backend `test_depth_listing.py`. `TestSFTPBackendNativeDepth` → `tests/backends/sftp/test_depth_listing.py` — its `listdir_attr` call-count assertions verify that SFTP's recursive traversal *prunes* at the depth limit, observable only by counting SDK round-trips. `test_s3_base_accepts_max_depth` → `tests/backends/s3/test_depth_listing.py` and `test_azure_accepts_max_depth` → `tests/backends/azure/test_depth_listing.py` — `_s3_base` and `_azure` both import without their cloud SDKs, so these stay unguarded Stage-1 `inspect.signature` checks for each family's ABC.
- **(b)** The cross-protocol DEPTH-003 *result* invariant is consolidated onto pre-existing tests rather than duplicated into a new conformance file: `tests/backends/conformance/test_listing.py::TestListFilesCompleteness` already parametrizes `list_files(max_depth=…)` over the full fixture registry, and `tests/backends/azure/test_config.py::test_list_files_max_depth` (BUG-155) already exercises it behaviourally for Azure (Azurite, Stage 2). `@pytest.mark.spec("DEPTH-003")` was stacked onto both.
- DEPTH-001 / DEPTH-002 and the in-process-backend DEPTH-003 tests stay at root in `tests/test_depth_listing.py`, a TEST-010-compliant home once the concrete-cloud imports leave.

`"test_depth_listing.py"` retired from `_BACKEND_AT_ROOT_GRANDFATHERED`.

**Reconsidered against CLAUDE.md § Audits rule 3.** The audit's original (b) prescription — "move the file body to a new `tests/backends/conformance/test_depth_listing.py`" — would have duplicated `conformance/test_listing.py`'s existing registry-parametrised depth coverage, and it mis-modelled DEPTH-001/002 as backend-conformance when spec 037 makes them Store-level. The diagnosed pain (three concrete-cloud imports firing Rule B) is authoritative and is fully addressed by the (a) lift; the (b) reshape was reframed as consolidation onto pre-existing tests. Shipped under BK-218.

**Refactor cost:** low (pure test relocation + marker stacking).

**Risk:** low.

### `tests/test_examples.py` — disposition: **(c) keep at root with documented justification**

| Line | Backend | Notes |
|---|---|---|
| 25 | `MemoryBackend` (allowed via public import; not banned) | Test helper |
| 63 | `LocalBackend` (allowed) | Test helper |
| 531 | `ReadOnlyHttpBackend` (banned: `_http`-derived) | HTTP example test |

Only one banned-backend site: `ReadOnlyHttpBackend` at line 531. The file's purpose (per ID-044) is to wrap every published example demo (quickstart, file ops, streaming, atomic writes, transfers, HTTP read-only) and verify their postconditions. The HTTP example is intrinsically backend-specific: it documents the HTTP read-only use case for end users.

Two valid paths:

- **(c) keep at root**, with the `_BACKEND_AT_ROOT_GRANDFATHERED` comment block extended to call out: "test_examples.py exists to harness every example demo at one place; moving the HTTP example test breaks the 1:1 mapping between `examples/<demo>.py` and its postcondition test."
- (a) extract the HTTP example postcondition to `tests/backends/http/test_examples.py`. Adds an exception to the example/test 1:1 invariant — harder to maintain over time.

Recommend **(c)**. The justification is structural (example-test 1:1) not just historical.

**Refactor cost:** trivial (comment update only).

**Risk:** none.

### `tests/test_pbt_write_result.py` — disposition: **(a) per-backend split (SDK metadata round-trip only)**

| Line | Backend | Notes |
|---|---|---|
| 267 | `_s3` | metadata round-trip via moto |
| 299 | `_azure` | metadata round-trip via Azurite |

The Hypothesis-driven WR-001a / WR-003..WR-005 / WR-011..WR-013 tests use `LocalBackend` (real BufferedWriter path) and `MemoryBackend` (oracle). The S3/Azure imports are guarded by `pytest.importorskip` / fixture availability and verify metadata round-trip under real SDK serialization (PBT discovered BUG-168 in this path).

Recommend: lift size-regime PBT into `tests/backends/conformance/test_write_result_pbt.py` parametrized over the fixture registry (natural fixture-availability skipping replaces the conditional import pattern). Move S3/Azure metadata round-trip into `tests/backends/s3/test_write_result_pbt.py` and `tests/backends/azure/test_write_result_pbt.py`.

**Refactor cost:** moderate. Hypothesis strategies and the BUG-168 boundary table are reusable; the parametrize wrapper is the main new code.

**Risk:** low-to-medium. The PBT runs slow; re-tuning Hypothesis `max_examples` per parametrize slot may be necessary.

**Reconsidered against CLAUDE.md § Audits rule 3 — shipped BK-221.** The audit's (b) prescription ("lift size-regime PBT into a conformance parametrize over the fixture registry") was reframed: PBT 1 uses `MemoryBackend` and `LocalBackend` only — both are allowed at `tests/` root, and the BUG-168 boundary is `LocalBackend`-specific (the only v1 backend with a real `BufferedWriter` path). Running arbitrary-payload Hypothesis examples against all conformance fixtures (including SFTP and Azure network backends) would be slow and contrary to the "deliberately narrow" backend selection documented in the module docstring (TESTING.md Rules 5 and 6). The diagnosed pain (Rule B violations at lines 267/299) is fully addressed by the (a) lift alone. PBT 1 size-regime tests stay at root. PBT 2 metadata round-trip tests moved to `tests/backends/s3/test_write_result_pbt.py` and `tests/backends/azure/test_write_result_pbt.py`. `"test_pbt_write_result.py"` removed from `_BACKEND_AT_ROOT_GRANDFATHERED`. One migration-pending entry remains (`test_coverage_gaps`) plus the permanently-justified `test_examples.py`.

### `tests/test_ping.py` — disposition: **(b) conformance + (a) per-backend split**

| Line | Backend | Helper / test |
|---|---|---|
| 46 | `_s3` | `_s3_backend()` builds an S3Backend with mocked `head_bucket` |
| 61 | `_sftp` | `_sftp_backend()` builds an SFTPBackend with mocked `stat` |
| 79 | `_azure` | `_azure_backend()` builds an AzureBackend with mocked `get_container_properties` |
| 206 | `_s3_pyarrow` | S3PyArrow ping path |

`Backend.check_health()` is an ABC method (PING-002), not a capability. Every backend either inherits the default no-op or overrides it; the healthy-path invariant (`backend.check_health() is None` when reachable and authorized) is the **same single line** for every backend. That's conformance-shaped by definition.

What is genuinely backend-specific is narrower than the audit's first reading:

- **Probe identity:** `head_bucket(Bucket=...)` (S3, PING-004), `stat(base_path)` (SFTP, PING-006), `get_container_properties()` (Azure, PING-007), `get_file_info(bucket)` (S3-PyArrow, PING-005). These pin the implementation's choice of probe and require SDK mocks to assert.
- **Error mapping (PING-009):** SDK-specific exception types map to the standard taxonomy. Botocore's exception model, paramiko's `OSError(ENOENT)`, and azure-core's `ResourceNotFoundError` are unrelated. Per-backend.
- **LocalBackend filesystem failure injection:** `rmdir(root)` → NotFound; `patch("os.access")` → PermissionDenied. Filesystem-specific.

Recommend (hybrid disposition):

- **(b)** Add `tests/backends/conformance/test_check_health.py` with one parametrize over the registry: `check_health()` returns None or raises a `RemoteStoreError` subclass. (A naive "returns None" form overreaches — fixture preconditions vary, and the HTTP backend's check_health legitimately fails on a directory URL per the PING-004 spec note even when individual files are reachable. The PING-002 + PING-009 combined invariant — "outcome is None or a properly-mapped error class; native SDK exceptions never leak" — is the actual ABC contract.)
- **(a)** Move SDK-mocked probe-identity + error-mapping tests to `tests/backends/<x>/test_ping.py` for S3 / SFTP / Azure and to `tests/backends/local/test_ping.py` for LocalBackend's missing-root / unreadable-root branches. The S3-PyArrow test appends to the existing `tests/backends/s3/test_pyarrow.py` (no `tests/backends/s3_pyarrow/` directory; mirrors BK-216).

Root `tests/test_ping.py` keeps only `Store.ping()` delegation / propagation / child-store (PING-001) and the observe `on_ping` / `on_error` integration (PING-010). `test_default_check_health_is_noop` (PING-002 via memory), `test_memory_backend_always_healthy` (PING-008), and `test_healthy_local` (PING-003 happy) are dropped as duplicates of what the conformance parametrize now covers via the memory and local fixtures.

**Refactor cost:** moderate. Conformance test is one class with one test; per-backend files are ~30 lines each; helpers transplant cleanly.

**Risk:** low. Conformance reuses the existing `backend` indirect fixture and auto-walk pattern (`tests/backends/conformance/conftest.py`). Mocks remain localised to each per-backend helper.

**Reconsidered against CLAUDE.md § Audits rule 3.** The audit's original (a) prescription would have created four near-identical per-backend "healthy returns None" assertions — the kind of cross-protocol duplication the conformance registry exists to eliminate. The pain point (TEST-003 violation at root) is fully addressed by the hybrid split. Shipped under BK-217.

**Discovery during BK-217.** The conformance test surfaced a previously-untested code path: `S3Backend.check_health()` calls `self._fs.s3.head_bucket(...)` where `self._fs.s3` is an `aiobotocore.client.S3` whose `head_bucket` returns a coroutine — the current code never awaits it. `check_health()` silently returns None regardless of bucket state. Every pre-BK-217 test mocked `head_bucket` on a `MagicMock` and missed this. Filed as BUG-208 under a new `## S3 Correctness` section in `sdd/BACKLOG.md`; the conformance test xfails `s3_moto` until BUG-208 lands.

### `tests/test_seekable.py` — disposition: **(b) conformance reshape (capability) + (a) per-backend split (Azure range reader)**

| Line | Backend | Notes |
|---|---|---|
| 64–68 | various | `pytest.param("remote_store.backends._<x>", "<Name>", …)` — string-form, AST-invisible |
| 85 | `_azure` | `from remote_store.backends._azure import _ALL_CAPABILITIES` |
| 91 | `_http` | `_CAPABILITIES` |
| 97 | `_memory` (allowed) | |
| 324, 333, 346, 364, 378, 388 | `_azure` | `_AzureRangeReader` direct construction and behaviour tests |

Two distinct concerns:

- **Capability declaration** (SEEK-001: "backends that always return seekable streams declare SEEKABLE_READ"). The string-form parametrize table at 64–68 plus the imports at 85/91 verify this contract across backends. Conformance is the natural home: parametrize over the registry and gate on `SEEKABLE_READ`.
- **`_AzureRangeReader` internal behaviour** (6 tests, lines 324–388). This is Azure-specific implementation detail (range-read coalescing, seek semantics). Belongs in `tests/backends/azure/test_seekable.py` or `tests/backends/azure/test_range_reader.py`.

Recommend: split as described. The `_AzureRangeReader` cluster is the larger lift.

**Refactor cost:** moderate. The Azure cluster is six tests; the conformance reshape is one parametrize.

**Risk:** low.

**Shipped under BK-220.** Disposition confirmed as described above. **(b)** All of `TestCapabilityDeclaration` (SEEK-001 — both the string-form parametrize table and the `_azure` / `_http` function-local imports) moved to `tests/backends/conformance/test_identity.py::TestSeekableCapability`; uses `BackendFixture.capabilities` from the fixture registry, no concrete backend class imports. **(a)** `TestAzureRangeReader` plus helpers `_FakeBlobClient` / `_FakeDownloader` moved verbatim to a new `tests/backends/azure/test_seekable.py`. Root file retains Store-API tests SEEK-002 through SEEK-012 (excluding SEEK-006); `test_seekable.py` removed from `_BACKEND_AT_ROOT_GRANDFATHERED`. Two migration-pending entries remain plus the permanently-justified `test_examples.py`.

## Summary

| File | Disposition | Refactor effort | Removable from allow-list after split? |
|---|---|---|---|
| `test_config.py` | (a) per-backend split | moderate | yes |
| `test_coverage_gaps.py` | (b) + (a) | moderate-to-high | yes |
| `test_depth_listing.py` | (a) lift 3 + (b) consolidate — reconsidered, see § per-file findings | low | yes |
| `test_examples.py` | (c) keep at root | trivial (comment) | no (justified) |
| `test_pbt_write_result.py` | (a) per-backend split (metadata round-trip) — reconsidered, see § per-file findings — shipped BK-221 | moderate | yes (done) |
| `test_ping.py` | (b) + (a) — reconsidered, see § per-file findings | moderate | yes |
| `test_seekable.py` | (b) + (a) Azure cluster — shipped BK-220, see § per-file findings | moderate | yes (done) |

**Zero files qualify for the "easy remove from allow-list" path.** Six need real refactoring (a/b); one needs only a justification comment (c). The per-file work is independently scopeable but is not single-turn-sized — each `(a)` / `(b)` slice is its own small PR.

## Correction to chat-only audit (pre-2026-05-13)

A preceding chat-only audit (an Explore-agent classification of the same files) concluded that `test_config.py`, `test_coverage_gaps.py`, and `test_examples.py` could be retired from the allow-list with documentation only. That conclusion was incorrect: the agent's signal was the **top-level** `from remote_store ...` imports, which for those three files do not touch banned backends. The placement checker walks the full AST including function-local imports, and all three files have multiple nested `from remote_store.backends._<x>` sites that fire Rule B. Removing `test_config.py` from the allow-list, for instance, produces 11 fresh violations. This document supersedes that chat-only summary.

## Recommended follow-up backlog items

Spin one new BK-prefix item per disposition slice when scheduling. Consult
`sdd/backlogid.json` for the next safe BK ID at the time of scheduling.
The (c) `test_examples.py` slice was shipped together with this audit (see
BACKLOG-DONE entry for slice 7/7); the other six slices were migration-pending
at audit time, one BK-prefixed follow-up each (live status lives in
`BACKLOG.md` / `BACKLOG-DONE.md`, not here):

- Split `tests/test_config.py` into per-backend `tests/backends/<x>/test_config.py` (disposition (a)).
- Split `tests/test_ping.py` per backend (a).
- Reshape `tests/test_depth_listing.py` into conformance + lift 3 backend-specific snippets (b + a).
- Reshape `tests/test_seekable.py` + lift `_AzureRangeReader` cluster (b + a).
- Reshape `tests/test_pbt_write_result.py` PBT into conformance + per-backend metadata round-trip (b + a).
- Reshape `tests/test_coverage_gaps.py` secret-masking into conformance + per-backend init split (b + a).

BK-191 stays open in `BACKLOG.md` as the umbrella until every slice closes.
