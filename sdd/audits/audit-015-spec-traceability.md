# Audit 015 — Spec-to-Test Traceability

**Backlog item:** BK-250
**Date:** 2026-06-01
**Scope:** All 48 spec files in `sdd/specs/` — every numbered spec ID in every file.
**Method:** For each spec file, all invariant IDs were extracted by reading the file.
Each ID was then searched across the entire `tests/` tree for a matching
`@pytest.mark.spec("ID")` decorator. Findings fall into three categories:

- **(a) No test at all:** the behavior has no coverage and no mark — higher effort,
  requires writing new tests before adding marks.
- **(b) Test exists, mark absent:** a test exercises the behavior under a sibling or
  parent ID but the spec-file-specific ID is not applied — low-effort label backfill.
- **(c) Spec defect:** the spec file itself is the root problem (e.g. duplicate ID,
  out-of-sequence numbering) — cannot be marked or traced until the spec is repaired.

---

## Findings

| Spec | ID | Invariant summary | Finding |
|------|----|-------------------|---------|
| 001 | STORE-007 | Thread Safety | No mark, no test |
| 001 | STORE-009 | Context manager / resource management | Test exists (`test_coverage_gaps.py:83`); mark absent |
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
| 003 | BE-027 | \_BACKEND\_GATING graph IR metadata | Test exists (`test_gen_graph.py:219`); no BE-027 mark |
| 005 | ERR-013 | ResourceLocked | No test; class absent from source entirely |
| 006 | SIO-004 | No partial reads on error | No mark, no test |
| 006 | SIO-005 | Cancellation propagation | Test exists (`aio/test_async_cancellation.py`); SIO-005 absent |
| 006 | SIO-006 | No framework dependencies | No mark, no test (design principle) |
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
| 010 | NPR-006 | LocalBackend.to_key | Test exists (`local/test_config.py`); NPR-006 absent |
| 010 | NPR-007 | S3Backend.to_key | Test exists; NPR-007 absent |
| 010 | NPR-008 | SFTPBackend.to_key | Test exists (`sftp/test_config.py::TestSFTPToKey`); NPR-008 absent |
| 010 | NPR-011 | Store.to_key composition | Test exists; NPR-011 absent |
| 010 | NPR-015 | list_folders store-relative names | No mark, no test |
| 010 | NPR-021 | Backend.native_path contract | Test exists (marked BE-025 only); NPR-021 absent |
| 010 | NPR-022 | Store.native_path | Test exists (marked STORE-015 only); NPR-022 absent |
| 011 | S3PA-001 | Constructor Parameters | No mark, no test |
| 011 | S3PA-006 | Dual-Library Architecture | No mark, no test |
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
| 016 | BATCH-010 | batch_copy error collection | Test exists as parametrized case (`test_batch.py:163`); BATCH-010 absent |
| 016 | BATCH-013 | batch_copy empty input | Test exists as parametrized case (`test_batch.py:264`); BATCH-013 absent |
| 016 | BATCH-017 | batch_exists empty input | Test exists as parametrized case (`test_batch.py:264`); BATCH-017 absent |
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
| 027 | ITER-008 | Spec Updates (meta) | No mark |
| 028 | RTXT-002..004 | No Backend ABC change, STORE-008 update, ext.cache integration | No marks |
| 028 | RTXT-006 | Spec Updates (meta) | No mark |
| 029 | ASYNC-043 | Delegation | No mark |
| 029 | ASYNC-045a | Capability-Gated Methods Graph IR | No mark |
| 029 | ASYNC-052f | head() | No mark |
| 029 | ASYNC-056 | No New Dependencies | No mark |
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
| 047 | DOCFRAME-005 | Bridge Replaces Not Augments | No mark |
| 047 | DOCFRAME-006 | Strict Build, Strict Links | No mark |
| 047 | DOCFRAME-007 | Nav and URL Alignment | No mark |
| 048 | TEST-002 | Conformance is Cross-Backend Spine | No mark |
| 048 | TEST-003 | Backend-Specific Tests Isolated Per Backend | No mark |
| 048 | TEST-007 | HTTP Cassette and Replay Layer | No mark |
| 048 | TEST-008 | Replay Scope is HTTP-Transport Only | No mark |
| 048 | TEST-009 | Cassette Refresh is Explicit | No mark |
