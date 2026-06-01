# Audit 015 — Spec-to-Test Traceability

**Backlog item:** BK-250
**Date:** 2026-06-01
**Scope:** All 48 spec files in `sdd/specs/` — every numbered spec ID in every file.
**Method:** For each spec file, all invariant IDs were extracted by reading the file.
Each ID was then searched across the entire `tests/` tree for a matching
`@pytest.mark.spec("ID")` decorator. Findings fall into four categories:

- **(a) No test at all:** the behavior has no coverage and no mark — higher effort,
  requires writing new tests before adding marks.
- **(b) Test exists, mark absent:** a test exercises the behavior under a sibling or
  parent ID but the spec-file-specific ID is not applied — low-effort label backfill.
- **(c) Spec defect:** the spec file itself is the root problem (e.g. duplicate ID,
  out-of-sequence numbering) — cannot be marked or traced until the spec is repaired.
- **(d) Meta / architectural:** the invariant describes a design constraint, dependency
  rule, or process obligation rather than a testable runtime behavior — not mark-able.

**Total:** 226 IDs in the table. Of these: 13 are type (d) (not actionable as mark
work); 1 is type (c) (spec defect requiring renumber before it can be marked); the
remaining 212 are type (a) or (b) and actionable.

> **Superseded by the [Verified addendum](#verified-addendum-2026-06-01).** This
> first-pass split did not separate (a) from (b). Verification resolves the 212 into
> **5** genuine coverage gaps (a), **~127** label backfills (b), and **~33**
> not-actionable rows (deferred/design-only, plus the ~57 unbuilt-Graph IDs owned by
> ID-127). Read the addendum, not this line, for the actionable counts.

---

## Findings

| Spec | ID | Invariant summary | Finding |
|------|----|-------------------|---------|
| 001 | STORE-007 | Thread Safety | No mark, no test |
| 001 | STORE-009 | Context manager / resource management | Test exists (`tests/test_coverage_gaps.py::TestStoreBehavior::test_context_manager`); mark absent |
| 001 | STORE-010 | Store equality | No mark, no test |
| 001 | STORE-011 | Store.to_key | Tests use NPR marks; STORE-011 absent |
| 001 | STORE-014 | list_files(pattern=) | Tests use GLOB-001; STORE-014 absent |
| 001 | STORE-015 | **Spec ID collision (type c)** | Two distinct invariants share STORE-015 (native_path and glob); STORE-014 appears between them out of sequence — spec defect, cannot be marked until renumbered |
| 001 | STORE-016 | Depth-limited listing | Tests use DEPTH-001; STORE-016 absent |
| 002 | CFG-007 | Config priority / no env-var merge | No mark, no test |
| 003 | CAP-007 | Quality-flag capabilities | No mark, no test |
| 003 | BE-011 | write_atomic capability gate | Class docstring says "BE-010 through BE-011"; no mark on any test method |
| 003 | BE-023 | Backend.to_key | Tests use NPR-003..005; BE-023 absent |
| 003 | BE-024 | Backend.glob | Tests use GLOB-004; BE-024 absent |
| 003 | BE-026 | iter_children | Tests use ITER-004/005; BE-026 absent |
| 003 | BE-027 | \_BACKEND\_GATING graph IR metadata | Test exists (`tests/scripts/test_gen_graph.py::test_backend_gating_keys_match_backend_members`); no BE-027 mark |
| 005 | ERR-013 | ResourceLocked | No test; class absent from source entirely |
| 006 | SIO-004 | No partial reads on error | No mark, no test |
| 006 | SIO-005 | Cancellation propagation | Test exists (`tests/aio/test_async_cancellation.py`); SIO-005 absent |
| 006 | SIO-006 | No framework dependencies | No mark (d: design principle — not test-markable) |
| 006 | SIO-007 | read_text convenience | Tests use RTXT-001; SIO-007 absent |
| 007 | AW-002 | Capability gate | No mark, no test |
| 007 | AW-004 | Cleanup on failure | Tests use SAW-004/005; AW-004 absent |
| 007 | AW-005 | Intermediate directories for write_atomic | No mark, no test |
| 007 | AW-006 | Local mkstemp + os.replace | No mark, no test |
| 007 | AW-007 | No fallback to non-atomic | No mark, no test |
| 008 | S3-001 | Constructor Parameters | No mark, no test |
| 008 | S3-006 | Virtual Folder Semantics | No mark, no test |
| 008 | S3-011 | delete_folder Recursive | No mark, no test |
| 008 | S3-012 | delete_folder Non-Recursive | No mark, no test |
| 008 | S3-013 | move Via Copy + Delete | No mark, no test |
| 008 | S3-014 | copy Via S3 Server-Side Copy | No mark, no test |
| 010 | NPR-002 | Store.to_key as public helper | No mark, no test |
| 010 | NPR-006 | LocalBackend.to_key | Test exists (`tests/backends/local/test_config.py::TestLocalBackendToKeyRoot`); NPR-006 absent |
| 010 | NPR-007 | S3Backend.to_key | Test exists; NPR-007 absent |
| 010 | NPR-008 | SFTPBackend.to_key | Test exists (`tests/backends/sftp/test_config.py::TestSFTPToKey`); NPR-008 absent |
| 010 | NPR-011 | Store.to_key composition | Test exists; NPR-011 absent |
| 010 | NPR-015 | list_folders store-relative names | No mark, no test |
| 010 | NPR-021 | Backend.native_path contract | Test exists (marked BE-025 only); NPR-021 absent |
| 010 | NPR-022 | Store.native_path | Test exists (marked STORE-015 only); NPR-022 absent |
| 011 | S3PA-001 | Constructor Parameters | No mark, no test |
| 011 | S3PA-006 | Dual-Library Architecture | No mark (d: architectural decision — not test-markable) |
| 011 | S3PA-007 | Credential Translation | No mark, no test |
| 011 | S3PA-008 | Virtual Folder Semantics | No mark, no test |
| 011 | S3PA-014 | Copy Via PyArrow | No mark, no test |
| 011 | S3PA-015 | Move Via Hybrid | No mark, no test |
| 011 | S3PA-016 | Delete Via s3fs | No mark, no test |
| 012 | AZ-007 | Container Scope | No mark, no test |
| 012 | AZ-008 | Directory Semantics (HNS) | Tests use BE-005/021; AZ-008 absent |
| 012 | AZ-009 | Virtual Folder Semantics (no HNS) | Tests use BE-* marks; AZ-009 absent |
| 012 | AZ-010 | Write Does Not Create Folder Markers (no HNS) | Tests use BE-008; AZ-010 absent |
| 012 | AZ-012 | exists() | Tests use BE-004; AZ-012 absent |
| 012 | AZ-013 | is_file() / is_folder() | Tests use BE-005; AZ-013 absent |
| 012 | AZ-015 | delete_folder Recursive | Tests use BE-013; AZ-015 absent |
| 012 | AZ-016 | delete_folder Non-Recursive | Tests use BE-013; AZ-016 absent |
| 012 | AZ-017 | Move | Tests use BE-018; AZ-017 absent |
| 012 | AZ-018 | Copy | Tests use BE-019; AZ-018 absent |
| 012 | AZ-019 | Glob | Tests use GLOB-020; AZ-019 absent |
| 012 | AZ-024 | get_folder_info | Tests use BE-017; AZ-024 absent |
| 012 | AZ-036 | HNS Directory-Marker Probe Contract | Tests use BE-021; AZ-036 absent |
| 013 | MEM-001..005 | Constructor, name, capabilities, repr, registration | Tests use BE-001..003; MEM marks absent |
| 013 | MEM-011 | read_bytes() copy semantics | No mark |
| 013 | MEM-013 | write_atomic identical to write | No mark |
| 013 | MEM-016b | copy() deep copy content | No mark |
| 013 | MEM-017..020 | to_key, close, unwrap, no exceptions | Tests use BE-020..022; MEM marks absent |
| 013 | MEM-025 | Single-Lock Serialization | No mark |
| 013 | MEM-026 | Atomicity Scope | No mark |
| 014 | PA-005 | Root Path Is Empty String | No mark |
| 014 | PA-023 | Optional Dependency | No mark |
| 014 | PA-026 | Conformance Across Backends | No mark |
| 016 | BATCH-010 | batch_copy error collection | Test exists (`tests/ext/test_batch.py::test_error_continues`); BATCH-010 absent |
| 016 | BATCH-013 | batch_copy empty input | Test exists (`tests/ext/test_batch.py::test_empty_paths`); BATCH-013 absent |
| 016 | BATCH-017 | batch_exists empty input | Test exists (`tests/ext/test_batch.py::test_empty_paths`); BATCH-017 absent |
| 016 | BATCH-023 | Concurrent result ordering | No mark, no test |
| 016 | BATCH-024 | Concurrent error semantics | No mark, no test |
| 016 | BATCH-025 | Concurrent empty input | No mark, no test |
| 018 | GLOB-015 | No Backend Coupling | Comment in `test_glob.py`; no mark |
| 018 | GLOB-017 | Empty Results | No mark |
| 018 | GLOB-019 | S3PyArrowBackend Native Glob | No mark |
| 019 | OBS-003a | Hook-to-Operation Mapping | No mark |
| 019 | OBS-015 | WriteResult in Post-Operation StoreEvent | No mark |
| 021 | CFG-014 | Optional Extras | No mark |
| 022 | SAW-009 | SFTPBackend .~tmp + posix_rename | Comment in `test_atomic.py`; no mark |
| 022 | SAW-010 | S3 buffer + PUT | Comment in `test_atomic.py`; no mark |
| 022 | SAW-011 | Azure non-HNS buffer + PUT; HNS temp + rename | Comment in `test_atomic.py`; no mark |
| 022 | SAW-015 | ext.otel span lifecycle | No mark |
| 025 | RET-015 | Graph Retry Mapping | No mark |
| 026 | PING-009 | Error Classification | Docstring in `test_check_health.py`; no mark |
| 027 | ITER-002 | Capability Gating | No mark |
| 027 | ITER-003 | STORE-008 Update | No mark |
| 027 | ITER-005 | Backend Overrides | Docstring in `test_listing.py`; no mark |
| 027 | ITER-006 | ext.observe integration | No mark |
| 027 | ITER-008 | Spec Updates (meta) | No mark (d: meta section — not test-markable) |
| 028 | RTXT-002..004 | No Backend ABC change, STORE-008 update, ext.cache integration | No marks |
| 028 | RTXT-006 | Spec Updates (meta) | No mark (d: meta section — not test-markable) |
| 029 | ASYNC-043 | Delegation | No mark |
| 029 | ASYNC-045a | Capability-Gated Methods Graph IR | No mark |
| 029 | ASYNC-052f | head() | No mark |
| 029 | ASYNC-056 | No New Dependencies | No mark (d: architectural constraint — not test-markable) |
| 029 | ASYNC-061 | read_seekable() Deferral | No mark |
| 029 | ASYNC-062 | open_atomic() Deferral | No mark |
| 029 | ASYNC-070..079 | AsyncAzureBackend specifics (dual-mode, lazy init, write strategy, move/copy, content materialization, check_health, capabilities, shared helpers, cleanup, error mapping) | No marks |
| 030 | WTXT-002..003 | No Backend ABC change, STORE-008 update | No marks |
| 030 | WTXT-006 | Symmetric with read_text | No mark |
| 031 | DAG-001 | Serializer Protocol | No mark |
| 032 | HTTP-CON-001..004 | Construction | No marks (test_examples.py uses stale `HTTP-001`; tests use BE/NPR/SIO marks) |
| 032 | HTTP-TR-001..003 | Transport protocol | No marks |
| 032 | HTTP-PATH-001..004 | URL construction, native_path, to_key, round-trip | No marks (tests use NPR-003) |
| 032 | HTTP-READ-001..002 | read / read_bytes | No marks (tests use SIO-001) |
| 032 | HTTP-EXIST-001..003 | exists / is_file / is_folder | No marks |
| 032 | HTTP-META-001..003 | get_file_info, get_folder_info, known limitations | No marks |
| 032 | HTTP-UNSUP-001 | Write / delete / list unsupported | No mark |
| 032 | HTTP-ERR-001..002 | Error mapping | No marks |
| 032 | HTTP-HEALTH-001 | check_health | No mark |
| 032 | HTTP-LIFE-001..002 | close, unwrap | No marks |
| 032 | HTTP-CRED-001 | Credential masking | No mark |
| 032 | HTTP-RETRY-001 | Retry integration | No mark |
| 036 | SEEK-007 | Azure read() Unchanged | No mark |
| 039 | TLS-008 | tls_ca_bundle on AzureBackend | No mark |
| 039 | TLS-009 | Env var fallback chain for Azure | No mark |
| 039 | TLS-010 | Azure connection_verify injection | No mark |
| 040 | SQL-BLOB-011 | Custom Table Name | No mark |
| 040 | SQL-BLOB-070 | Blob Size Guidelines | No mark |
| 041 | SQL-QUERY-010 | Explicit Query Mapping | No mark |
| 041 | SQL-QUERY-061 | close() | No mark |
| 041 | SQL-QUERY-063 | SQLite PRAGMAs | No mark |
| 041 | SQL-QUERY-090 | Query Execution | No mark |
| 041 | SQL-QUERY-091 | Serialization Overhead | No mark |
| 042 | PDS-009 | Dagster Integration | No mark |
| 043 | RES-001 | Resolution Opacity | No mark |
| 044 | GR-001..057 | Entire Graph backend spec (~55 IDs: constructor, auth, path, read, write, upload session, delete, move, copy, error mapping, retry, file hashes, drive identity, credential masking, to_key, unwrap, close, client options) | No marks anywhere |
| 045 | WR-006 | Sidecar Source | No mark |
| 047 | DOCFRAME-005 | Bridge Replaces Not Augments | No mark (d: doc framework principle — not test-markable) |
| 047 | DOCFRAME-006 | Strict Build, Strict Links | No mark (d: build constraint — not test-markable) |
| 047 | DOCFRAME-007 | Nav and URL Alignment | No mark (d: docs nav rule — not test-markable) |
| 048 | TEST-002 | Conformance is Cross-Backend Spine | No mark (d: testing-process spec — not test-markable) |
| 048 | TEST-003 | Backend-Specific Tests Isolated Per Backend | No mark (d: testing-process spec — not test-markable) |
| 048 | TEST-007 | HTTP Cassette and Replay Layer | No mark (d: testing-process spec — not test-markable) |
| 048 | TEST-008 | Replay Scope is HTTP-Transport Only | No mark (d: testing-process spec — not test-markable) |
| 048 | TEST-009 | Cassette Refresh is Explicit | No mark (d: testing-process spec — not test-markable) |

---

## Verified addendum (2026-06-01)

The original table classified rows by *mark presence* and used inconsistent wording
("No mark, no test" vs. bare "No mark"), which left the actionable count ambiguous:
212 rows were reported as "type (a) or (b)" without a split between them. This
addendum resolves that ambiguity. Every row not already proven type (b) ("test
exists" / "tests use X") was re-verified by reading the invariant text and searching
the entire `tests/` tree for **any** test that exercises the behavior, marked or not.

**Method:** per ID — read the invariant, grep the test tree for the behavior (method
names, class names, keywords; not just the literal ID), classify as A (no test
anywhere), B (tested under a different/absent mark), or D (not a runtime-testable
behavior: design principle, meta/process section, or explicitly deferred feature).

### Revised totals

| Category | Count | Meaning |
|----------|-------|---------|
| **(a) Untested shipped behavior** | **5** | The real coverage debt — table below |
| (b) Tested, mark absent | ~127 | Label gap; behavior runs (largely via cross-backend conformance under sibling marks) |
| (d) Not runtime-testable | ~33 | Design principles, meta/process sections, and **deferred** features (TLS Phase 2, ext.parquet Dagster-v2, async `read_seekable`/`open_atomic` deferrals, graph retry) — more than the 13 the first pass tagged, because several bare "No mark" rows are deferred or design-only |
| Implementation-pending (Graph) | ~57 | Spec 044 `GR-001..GR-057` + `ERR-013` describe `GraphBackend`, which is **not implemented** (absent from source and `FEATURES.md`). Owned by backlog **ID-127**; tests and marks land when the backend is built. Not traceability debt. |
| (c) Spec defect | 1 | `STORE-015` duplicate ID (unchanged from first pass) |

The first pass's "212 actionable" therefore resolves to **5 genuine coverage gaps**,
**~127 mechanical label backfills**, and **~33 not-actionable** rows that were
deferred/design-only or belong to the unbuilt Graph backend.

### (a) The 5 untested shipped behaviors

| Spec | ID | Untested behavior | Evidence / note |
|------|----|-------------------|-----------------|
| 008 / 011 | S3-012 | S3 & S3-PyArrow non-recursive `delete_folder` on a **non-empty** folder must raise `DirectoryNotEmpty` | Code raises it (`_s3.py:270`), but `tests/backends/conformance/test_errors.py::...::test_delete_folder_non_recursive_non_empty_raises` calls `_skip_flat_namespace`, skipping S3 and S3PA. SQLBlob has a dedicated test (`SQL-BLOB-025`); S3/S3PA have none. **Highest-severity gap** (data-safety guard). |
| 032 | HTTP-CON-004 | `HttpBackend.capabilities == {READ, METADATA}` | No test asserts the set (conformance checks type + absence of ATOMIC_MOVE/SEEKABLE_READ only). **Also a code/spec divergence:** the implementation declares `{READ, METADATA, LAZY_READ}` (`_http.py:41`). Resolve the conflict (per process principle 5, the spec is authoritative unless `LAZY_READ` is intended) before writing the test. |
| 022 | SAW-015 | `ext.otel` span over the `open_atomic` lifecycle | `tests/ext/test_otel.py` asserts spans for read/write/exists/delete only. The `around`-hook plumbing for `open_atomic` is exercised via `ext.observe`, but no otel-span assertion exists. |
| 016 | BATCH-023 | Sequential batch preserves input order; concurrent order is non-deterministic | All concurrent multi-item tests in `tests/ext/test_batch.py` assert via `set(...)`, so ordering is never pinned. |
| 032 | HTTP-CON-003 | `HttpBackend.name == "http"` (literal) | Conformance asserts only that `name` is a non-empty string. Trivial. |

### Partial sub-clause gaps (within otherwise-covered invariants)

Not full type (a), but flagged for completeness — these invariants are covered except
for one clause:

- **STORE-007** — share-across-threads is tested (CHILD-010 concurrency test); the *immutability* clause has no dedicated test (Store is not a frozen dataclass).
- **PA-005** — root-as-empty-string mapping is tested; *file ops on root raising `FileNotFoundError`* is not.
- **HTTP-TR-002** — auto-detect + urllib fallback is tested; the *httpx-before-requests preference ordering* is not directly asserted.
- **HTTP-TR-003** — explicit transport override is tested; the *ImportError-when-library-missing* branch is `pytest.skip`-ped, never asserted.

### Caveats on the type-(b) verdicts

- **SQL-QUERY-061 / SQL-QUERY-063** ride entirely on shared-base coverage via
  `SqlBlobBackend` tests; there is no `sqlquery` conformance fixture and no
  `SqlQueryBackend`-specific close / PRAGMA assertion. The weakest type-(b) rows.
- **GLOB-019** is type (b) only when `s3_pyarrow_moto` is live in the conformance run;
  under `pyarrow>=24` / moto-unavailable skips, the native S3-PyArrow glob path is not
  exercised.
- **SAW-009 / SAW-011** are exercised both by the `fixture_params(Capability.ATOMIC_WRITE)`-parametrized
  conformance success path *and* backend-specific assertions (SFTP `.~tmp` cleanup,
  Azure `rename_file.assert_called_once`); **SAW-010**'s S3 buffer mechanism is
  exercised but not mechanism-asserted (closest is the test that a stream failure
  mid-write leaves no truncated object).

### Discovery follow-up

`HTTP-CON-004` surfaced a **code/spec divergence** not visible to the first pass:
`HttpBackend` declares `LAZY_READ` in its capability set while spec 032 lists only
`{READ, METADATA}`. This is a type-(c)-flavoured defect (the spec and code disagree)
and must be resolved as part of, or before, writing the HTTP-CON-004 test.
