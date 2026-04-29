# Development Backlog — Done

Completed items, newest first. All items must use `[x]` status.
Active work lives in [BACKLOG.md](BACKLOG.md).

---

## [Unreleased]

- [x] **BUG-185 — `S3Backend(client_options={"config_kwargs": ...})` collides on `config=`**
  The BUG-178 fix landed `_S3Base._build_s3fs_kwargs()` writing the merged
  `botocore.config.Config` into `client_kwargs["config"]`, but
  `s3fs.S3FileSystem.set_session` always calls
  `aiobotocore.create_client("s3", config=AioConfig(**self.config_kwargs), **client_kwargs)`.
  Any `client_kwargs["config"]` therefore duplicates `config=` and raises
  `TypeError: got multiple values for keyword argument 'config'` —
  with or without `RetryPolicy`. Reproduced on s3fs 2026.3.0 against an
  internal MinIO-style endpoint that requires `s3.addressing_style="path"`
  and `proxies={http: None, https: None}`. Fixed by routing every Config
  source (top-level `config_kwargs`, caller's pre-built
  `client_kwargs["config"]`, retry policy) through a single merged dict at
  `opts["config_kwargs"]`; `client_kwargs["config"]` is never set. Spec
  S3-026 / S3PA-026 updated to pin the new invariant. Existing merge
  precedence preserved: caller's `config_kwargs` < caller's pre-built
  `client_kwargs["config"]` < retry policy. Tests in
  `tests/backends/test_s3_options.py` extended with the no-RetryPolicy
  reproduction from the report.

- [x] **ID-174 — Diátaxis-aligned docs filesystem reorg (Phases 1 + 2)**
  **Phase 1:** Moved 36 prose files from `guides/` and repo root into
  `docs/<bucket>/` (how-to, explanation, reference, further). Mirrored
  `docs-src/` wrappers into the same hierarchy so relative links resolve
  identically in the GitHub repo and the MkDocs rendered output. Updated all
  cross-bucket links across docs-src/ API and extension stubs (50+ files),
  26 Python example docstrings, and hardcoded links in `scripts/docs/render.py`.
  **Phase 2:** Collapsed `docs/` entirely into `docs-src/` — inlined all 35
  prose files directly, replacing `include-markdown` stubs. `docs/` layer
  deleted. Absolute GitHub URLs used for links to repo files outside `docs-src/`
  (sdd/, CONTRIBUTING.md, etc.). Updated `context7.json`, `pyproject.toml`
  bumpversion, CI path filters, `scripts/gen_features.py`,
  `tests/scripts/test_gen_features.py`, `CLAUDE.md`, `sdd/CLAUDE-REFERENCE.md`,
  `sdd/DOCUMENTATION.md`, `CONTRIBUTING.md`, `README.md`,
  `.claude/skills/release/SKILL.md`, `src/remote_store/ext/__init__.py`,
  example files, and notebook. `docs/` directory removed.
  `docs-build --strict` passes with 0 warnings. Unblocks ID-161.

- [x] **ID-160 — Submit remote-store to Context7 library index**
  `context7.json` was already in place. Library registered and indexed at
  `/haalfi/remote-store`: 691 snippets, Source Reputation High, Benchmark
  Score 91.3, version v0.24.0. Verified 2026-04-29 via `resolve-library-id`.
  No code change required.

- [x] **ID-171 — `check_api_docs.py` Phase 2, sub-task 1 — `Backend` → `backend.md`**
  Precondition discovered and fixed: `gen_graph.py` only emitted `gates` edges
  for `Store`; `Backend` had no edges, making any PAGES entry vacuous.
  - Added `_BACKEND_GATING: dict[str, str]` (16 capability-name string entries)
    directly to `scripts/gen_graph.py` — its only consumer. Placing it in
    `_backend.py` would have no runtime use (Backend has no `_gate()` equivalent)
    and triggered a CodeQL unused-variable alert.
  - Extended `gen_graph.py` with a Backend method/requirement nodes + gates/of
    edges loop. Graph grows from 75 → 107 nodes, 158 → 222 edges.
  - Added `remote_store._backend.Backend` to `PAGES` in `check_api_docs.py`.
    Error-hint message updated to cover both gating dicts.
  - **No drift found** — `backend.md` was already correctly annotated.
  - Added `test_real_graph_backend_methods`; `TestLivePages` auto-covers
    `backend.md` via PAGES. 23 tests total.
  - **Remaining** (split per convention): `__all__` ↔ `index.md` → ID-173;
    `AsyncStore`/`AsyncBackend` ↔ `aio.md` → ID-172 (blocked on aio rework).

- [x] **ID-170 — `check_api_docs.py` — verify `Store` page against graph IR (Phase 1)**
  New verifier script projects `graph.json` and `docs-src/api/store.md` through
  two pure extractors (`graph_class_methods`, `page_class_methods`) into the
  same canonical IR `{method: frozenset(required_capabilities)}`, then a
  trivial coverage compare reports a missing `:::` directive or an admonition
  that fails to claim a required capability. Each extractor is independently
  testable; the live page+graph round-trip runs in CI.
  - **Caught:** `!!! note "Requires Capability.GLOB"` was placed before
    `::: Store.glob` instead of after, against the file's own placement-rule
    comment. Moved.
  - **Wiring:** `hatch run gen-api-check`; CI lint step inserted immediately
    after `gen-graph.py --check` (the data-flow source).
  - **Tests:** 22 in `tests/scripts/test_check_api_docs.py` covering each
    extractor in isolation, the no-bleed-backward and no-bleed-forward
    invariants, the orphan-gate skip path, and a live integration round-trip.
  - **Next:** ID-171 (Phase 2 — `Backend`, `AsyncStore`/`AsyncBackend`,
    `index.md`).

- [x] **ID-169 — Sort generated lists in FEATURES.md alphabetically**
  Backend rows in `backends_main` and `backends_flags`, and entries in
  `install_extras`, are now sorted alphabetically by type string / extra name.
  Previously they followed source-file declaration order
  (`_register_builtin_backends()` and `pyproject.toml` key order), which is
  not a meaningful sort criterion for readers. Three new tests assert the
  ordering invariant.

- [x] **ID-162 — `mirrors` edges in the graph: `capability_delta` metadata**
  `mirrors` edges now carry `capability_delta: {async_only: [str], sync_only: [str]}`
  so graph consumers can render sync↔async capability asymmetries instead of
  treating peers as equivalent. Names are anchored to the canonical async→sync
  direction kept by the dedup pass; lists are sorted and always present (empty
  when peers are symmetric). Real example: `AsyncMemoryBackend` declares
  `LAZY_READ`; `MemoryBackend` does not — the edge now reports
  `async_only: ["LAZY_READ"]`. RFC-0012 edge-taxonomy table and Open Questions
  updated; schema bumped to `"1.2"`. New test
  `test_mirrors_edge_carries_capability_delta` covers the AsyncMemoryBackend
  pair plus a shape invariant on every `mirrors` edge.

- [x] **ID-168 — Audit and enforce non-src test subpackage placement**
  Sweep complete: one remaining misplacement found and resolved.
  `tests/test_gen_features.py` moved to `tests/scripts/test_gen_features.py`; `ROOT`
  anchor updated from `.parent.parent` to `.parent.parent.parent`.
  Placement rule formalised in `sdd/TESTING.md` § Test Subpackage Placement.
  `scripts/check_test_placement.py` (AST-based) added; wired into the `lint` CI
  job and `check-test-quality` hatch script to prevent regression.

- [x] **ID-167 — Move `test_dafny_classorder.py` to `tests/scripts/`**
  `tests/backends/test_dafny_classorder.py` moved to `tests/scripts/test_dafny_classorder.py`.
  File content unchanged (`parents[2]` resolves correctly to the repo root from the new location).

- [x] **ID-166 — Move `test_gen_graph.py` to `tests/scripts/`**
  `tests/test_gen_graph.py` moved to `tests/scripts/test_gen_graph.py`.
  `ROOT` anchor updated from `.parent.parent` to `.parent.parent.parent` to reach the repo root from the new depth.
  `pyproject.toml` dev-extra comment updated to reflect new path.

- [x] **ID-165 — `gen_graph_viz.py` — interactive graph visualization**
  `scripts/gen_graph_viz.py` reads `docs-src/_data/graph/graph.json` and writes a
  self-contained D3 v7 force-directed HTML file to `docs-src/_data/graph/graph_viz.html`.
  Nodes are color-coded by kind (cap/cls/mtd/pkg/req/xtr); edges styled by type
  (declares/enables/gates/inherits/mirrors/of) with directional arrowheads.
  Schema 1.1 fields used: abstract methods rendered with dashed stroke; async methods
  labelled with a small badge.  Sidebar filter checkboxes, click-to-inspect detail panel,
  drag/zoom/pan.  `gen-graph-viz` / `gen-graph-viz-check` hatch scripts added.

- [x] **ID-164 — Complete `method` node properties in graph IR**
  `build_graph()` now emits `is_abstract`, `is_async`, `file`, and `line` on
  every `method` node (RFC-0012 taxonomy). `_rel_file()` generalized to
  `_rel_path(filepath: Path | None)`. Schema bumped to version `"1.1"`.
  New test: `test_method_nodes_carry_introspection_fields` in `tests/scripts/test_gen_graph.py`.

- [x] **ID-163 — `FEATURES.md` projection from graph IR**
  `scripts/gen_features.py` reads `graph.json` and regenerates three mechanical
  sections of `FEATURES.md` via `<!-- BEGIN_GENERATED:X --> / <!-- END_GENERATED:X -->`
  region tags (`backends_main`, `backends_flags`, `install_extras`).
  `gen-features` / `gen-features-check` hatch scripts added; idempotency gate
  in `tests/test_gen_features.py`.
  `gen_graph.py` updated: `version = None` hardcode removed; `source_version`
  and `snapshot` now read from `pyproject.toml["project"]["version"]`; `--check`
  mode and `gen-graph-check` hatch script added; `test_graph_json_is_up_to_date`
  idempotency gate added to `tests/scripts/test_gen_graph.py`.
  Release Phase 2 checklist updated: `bump-my-version` → `gen-graph` → `gen-features`
  → commit (stamps version; FEATURES.md and graph.json included in release commit).
  CI lint job extended: `gen-graph-check` + `gen-features-check` run before pytest;
  `CODE_PAT` updated to trigger on `scripts/`, `FEATURES.md`, and `graph.json`.

- [x] **ID-159 — Documentation graph model: preconditions + gen_graph.py**
  RFC-0012 accepted. All preconditions implemented:
  `CAPABILITIES: ClassVar[CapabilitySet]` added to all 11 backend classes (sync and async);
  `_GATING: dict[str, Capability]` + `Store._gate()` added to `_store.py`;
  `__mirror__` class annotation added to `AsyncMemoryBackend` and `AsyncAzureBackend`.
  `scripts/gen_graph.py` generates `docs-src/_data/graph/graph.json`:
  capability, class, extra, method, requirement, and package nodes;
  declares, gates, of, enables, mirrors, and inherits edges.
  Deterministic output (nodes sorted by id URI, edges by (kind, src, dst), sort_keys=True).
  Golden test: `tests/scripts/test_gen_graph.py`.
  Remaining work (gen_features.py projection → FEATURES.md): ID-163.

## v0.24.0

- [x] **BUG-184 — `AsyncMemoryBackend.delete(dir_path, missing_ok=True)` silently returns; sync `MemoryBackend` raises `InvalidPath`**
  Lock-step divergence between the two backends on the same call: when
  `path` exists as a directory and `missing_ok=True`, `MemoryBackend.delete`
  raises `InvalidPath("Not a file: ...")` while `AsyncMemoryBackend.delete`
  treated the `_DirNode` like a missing key and silently returned
  (`_async_memory.py:268-271`). Fixed by inserting the `isinstance(existing,
  _DirNode)` guard before the `missing_ok` branch, mirroring `_memory.py:204-205`.
  Spec ASYNC-012 tightened to pin the directory-path outcome (cross-link to
  BE-012). PBT guard in `_do_delete_missing_ok` removed so Hypothesis now
  exercises the directory-path case.

- [x] **ID-155 — Async stateful PBT (`tests/aio/test_async_pbt_stateful.py`)**
  Hypothesis `RuleBasedStateMachine` driving `AsyncMemoryBackend` (native)
  and `SyncBackendAdapter(MemoryBackend())` (adapted) in lock-step against a
  shared dict + dirs model. Rules cover write / overwrite / write_atomic /
  read_bytes / streaming read / exists / is_file / delete / delete_missing_ok /
  delete_folder / move / copy / list_files; content verification fires whenever
  Hypothesis schedules the `read_bytes` or `read_streaming` rule. Divergence
  between the two contract implementations or between either implementation
  and the model fails the test — the same shape that caught BUG-183 on the
  sync side.
  Hypothesis 6.x has no built-in async state machine; rules dispatch through a
  per-instance event loop with `loop.run_until_complete`, keeping
  `asyncio.Lock` and `asyncio.to_thread` executor identity stable across the
  whole rule sequence (a per-rule `asyncio.run` would not). The two
  reproducer-style tests from the sync suite are mirrored against both
  backends. Surfaced BUG-184 (`AsyncMemoryBackend.delete(dir_path,
  missing_ok=True)` divergence from sync `MemoryBackend`) — guarded out at
  `_do_delete_missing_ok` until the divergence is resolved.

- [x] **ID-156 — Adapter conformance across S3 / SFTP / Azurite**
  Extended `tests/aio/test_sync_adapter_conformance.py` with a separate
  `live_adapted_backend` fixture (S3/moto, SFTP/in-process server,
  Azure/Azurite) and five `@pytest.mark.integration` test classes that
  mirror the existing Memory/Local suite. Each class covers streaming reads,
  write materialisation, listing, move/copy/delete, and concurrency —
  exercising the `asyncio.to_thread` bridges against real network I/O,
  connection pools, and SDK-level retries that Memory/Local cannot reach.
  The fast path (<1 s) is preserved: `adapted_backend` (Memory/Local) is
  unchanged, and the live classes only run when explicitly selected via
  `-m integration`. `sftp_server` was moved from `tests/backends/conftest.py`
  to root `tests/conftest.py` so it is accessible to `tests/aio/` modules
  without duplicating the fixture.

- [x] **ID-157 — Live Azurite integration suite for `AsyncAzureBackend`**
  Added `tests/aio/test_async_azure_live.py` (17 tests + 1 conditional HNS
  test) running against a live Azurite container, gated on
  `_azurite_reachable()` from `tests/conftest.py`. Covers what the
  mock-only `tests/aio/test_async_azure.py` cannot: real ETag / `last_modified`
  propagation through `_build_azure_write_result`, multi-chunk download
  via `download_blob().chunks()` (forced with a per-test backend setting
  `max_single_get_size` / `max_chunk_get_size` to 256 KiB so the test
  stays fast), USER_METADATA round-trip via `get_file_info`, and live
  404 / 409 / 412 wire responses mapped through `classify_azure_error`.
  The 412 If-Match precondition test drives the underlying async
  `BlobClient` directly (the public API does not expose `if_match`),
  asserting that the resulting `HttpResponseError` flows through the same
  classifier the backend's `_errors()` async context manager uses.
  Stand-alone fixture (per-test container) rather than parametrised with
  the sync `tests/backends/test_azure.py`: async needs `aclose()` and
  async generators, so structural convergence with the sync bodies wasn't
  clean. Container provisioning reuses the sync `BlobServiceClient` via
  `azurite_server` to avoid spinning up an event loop just to create a
  container. HNS class is gated on `_ensure_hns()` and skips against
  Azurite (no HNS emulation); ready to activate against a live ADLS Gen2
  account.

- [x] **BK-164 — Close high-value async test-coverage gaps**
  Three new files under `tests/aio/` targeting async-specific concerns absent
  from the existing suite:
  (1) `test_async_drift.py` (53 tests) — API parity guard: asserts every public
  `Store`/`Backend` method has a matching `AsyncStore`/`AsyncBackend` method
  with identical parameter names, kinds, and defaults, modulo explicit
  sync-only (`read_seekable`, `open_atomic`, `close`) and async-only
  (`aclose`) allowlists. Prevents the sync side from growing features the
  async side silently lacks.
  (2) `test_async_cancellation.py` (9 tests) — verifies invariants under
  `asyncio.CancelledError`: a cancelled `write`/`write_atomic` leaves no
  partial file; a cancelled overwrite preserves original content; a cancelled
  read does not mutate state; `read`/`list_files` async generators close
  cleanly on early-break; the backend lock is released so subsequent ops
  succeed. Uses explicit `asyncio.Event` synchronisation (no sleeps) for
  deterministic cancellation points.
  (3) `test_sync_adapter_conformance.py` (42 tests) — parametrises conformance
  checks across `SyncBackendAdapter(MemoryBackend())` and
  `SyncBackendAdapter(LocalBackend(tmp_path))`. Exercises adapter code paths
  that the existing memory-only adapter tests don't hit: 64 KiB streaming-read
  loop at `_sync_adapter.py:137-147` with 250 KiB payloads, `_materialize()`
  drain of async iterators, sync-iterator→async-iterator bridging for
  `list_files`/`list_folders`/`iter_children`, error passthrough (`NotFound`,
  `AlreadyExists`) across the executor boundary, and concurrent `to_thread`
  dispatch under `asyncio.gather`.
  Scope deliberately excludes async extensions (batch/transfer/cache/observe)
  which are feature gaps, not test gaps — those modules have no async
  implementation yet.

- [x] **BUG-183 — PBT model in `test_pbt_stateful.py` tracks empty dir nodes**
  `BackendModel` derived implicit dirs by scanning the live-file map. After
  `write('0/0') → delete('0/0')` the model forgot the `_DirNode('0')` that
  `MemoryBackend` deliberately retains per MEM-DS-006
  (`delete()` does not auto-prune parent dirs). The next `write_new('0')`
  passed the model's conflict guard and reached the backend, which raised
  `InvalidPath`. Fix tracks live dirs in a separate `self.dirs` set on
  `BackendModel`: writes add all ancestors; `delete()` deliberately leaves
  them; a new `delete_folder` rule calls `backend.delete_folder(recursive=True)`
  and prunes the target path plus all descendants from both `self.dirs` and
  `self.model`, so the dir set is now the sole mutator-symmetric state (no
  monotonic growth). The `_can_write` / `exists` / `read_bytes` /
  `delete_missing_ok` rules consult `self.dirs` instead of re-deriving from
  files. Deterministic regressions
  `test_bug183_empty_dir_persists_after_file_delete` and
  `test_delete_folder_rule_prunes_dirs_and_descendants` lock the minimised
  sequence and the pruning invariant. No change to `_memory.py` or any spec
  — the backend was correct.
  Related: MEM-DS-006, MEM-014 (`sdd/specs/013-memory-backend.md`); BK-139 P4.

- [x] **BK-163 — Share duplicate S3/S3PA tests via parametrized test_s3_shared.py**
  Moved 5 tests with identical/near-identical bodies from `test_s3.py` and
  `test_s3_pyarrow.py` into new shared classes in `test_s3_shared.py`:
  `TestS3SharedErrorMapping` (S3-015/S3PA-018, S3-018/S3PA-019),
  `TestS3SharedUnwrap` (S3-020/S3PA-021), and `TestS3SharedETagAndDigest`
  (S3-023/S3PA-017, S3-024/S3PA-017). Removed now-empty `TestS3Lifecycle`,
  `TestS3PyArrowErrorMapping`, and `TestS3PyArrowMetadata` classes.

- [x] **BK-162 — Fix 16 documentation gaps from Audit-011 (v0.23.0+)**
  Fixed all 16 findings from `sdd/audits/audit-011-docs-v023-gaps.md` across 4 commits:
  (1) custom-backend guide + snippet: corrected `write()`/`write_atomic()` return types,
  added `metadata=` kwarg, `WriteResult` import, and new capability descriptions
  (USER_METADATA, WRITE_RESULT_NATIVE, LAZY_READ); (2) async.md: added Write Results
  section, `aio.ext.write` prose, and Async-Sync Bridges cross-reference; extensions.md:
  added `aio.ext.write` table row and `ext.write` imports to always-available block;
  (3) capabilities-matrix.md and local.md: corrected USER_METADATA claim for Local;
  s3.md and azure.md: added Write Results sections documenting WRITE_RESULT_NATIVE and
  USER_METADATA; s3-pyarrow.md: fixed "fully interchangeable" claim; (4) getting-started
  examples: all write calls now capture and use the returned `WriteResult`.

- [x] **BK-159 — Audit handwritten docs for v0.23.0+ feature & API changes**
  Reviewed guides, tutorials, and examples against post-v0.23.0 API changes.
  16 findings: 3 Critical (custom-backend guide write methods return `None`
  instead of `WriteResult`, missing `metadata=` kwarg in snippet and reference
  table), 6 Major (new capabilities and `aio.ext.write` undocumented, `ext.write`
  imports absent from extensions guide, async guide missing `WriteResult`/
  `metadata=`/`aio.ext.write`), 7 Minor (local.md and capabilities-matrix.md prose
  both wrong re `USER_METADATA`; s3-pyarrow.md "fully interchangeable" claim wrong;
  per-backend write-result docs missing; example write calls treat API as void).
  Report: `sdd/audits/audit-011-docs-v023-gaps.md`.

- [x] **BK-161 — Enforce public import paths in extensions (checker + fixes + Cat 1 comments)**
  Added `test_no_private_module_imports` AST checker to `test_ext_contract.py` (excluding
  `TYPE_CHECKING` blocks, catching deferred function-body imports). Fixed 10 Cat 2 import
  paths across 10 modules (`from remote_store._x import Y` → `from remote_store import Y`).
  Added inline justification comments to 3 Cat 1 sites (`ext/glob.py`, `ext/write.py`,
  `ext/dagster.py`). Audit-010 also surfaced a previously missed deferred `Store` import
  in `dagster.py:383`. See BK-160 for the rule codification.

- [x] **BK-160 — Codify extension import-time private access rule in `DESIGN.md`**
  Added Rule 12 "Extension API contract" to `sdd/DESIGN.md`: MUST use public import
  path when one exists; SHOULD avoid private module imports with no public path (justify
  with inline comment). Enforced by `test_no_private_module_imports` (BK-161).

- [x] **ID-138 — Async streaming integrity e2e test**
  Added `tests/e2e/test_async_streaming_integrity.py` mirroring the sync e2e
  test. Chain: `AsyncMemoryBackend` (seed) → `AsyncAzureBackend` (Azurite,
  native async) → `AsyncMemoryBackend` (native async, mid-chain) →
  `SyncBackendAdapter(LocalBackend)` (adapter contract) →
  `AsyncMemoryBackend` (sink). Transfer via manual `async for chunk in store.read()`
  loop fed into `store.write()` — no `ext.transfer`.
  Validates: (1) async streaming integrity on native Azure (SHA-256 per hop);
  (2) native async memory backend as mid-chain writer and reader; (3)
  `SyncBackendAdapter` streaming read contract (64 KiB chunks from
  `asyncio.to_thread`). Fallback chain (no Azurite): seed → local-wrapped → sink.
  `SyncBackendAdapter.write()` materialization is documented as an exemption.
  Residual scope (native `AsyncStore.transfer()` variant) tracked as ID-154.

- [x] **ID-153 — Consolidate moto / Azurite fixtures at `tests/conftest.py`**
  Promoted `_free_port`, `moto_server`, `_AZURITE_CONN_STR`, and `azurite_server`
  (plus the `_s3_available`, `_azure_available`, `_azurite_reachable` helpers they
  need) to `tests/conftest.py`. Removed the duplicate `_moto_endpoint`
  module-scoped fixture from `test_pbt_write_result.py`; that file now uses the
  shared session-scope `moto_server`. Eliminated all cross-boundary
  `from tests.backends.conftest import …` calls.

- [x] **BK-156 — Refactor per-backend test files to remove conformance duplication**
  Deleted ~110 duplicate tests across `test_sftp.py`, `test_azure.py`, and `test_sqlblob.py`.
  SFTP: removed TestSFTPReadWrite, TestSFTPListing, TestSFTPDelete, TestSFTPMoveCopy,
  TestSFTPDeleteFolder, and 3/4 of TestSFTPAtomicWrite; kept SFTP-specific empty-folder
  persistence and temp-file cleanup tests.
  Azure: gutted TestAzureIntegration from 31 tests to 3; kept lazy-stream assertion,
  max_depth regression guard, and unwrap test.
  SQLBlob: removed TestMove, TestCopy, test_iter_children, standalone read/write/delete/atomic
  duplicate functions, and trimmed TestExistence/TestListFiles/TestListFolders/TestGetFileInfo/
  TestGetFolderInfo to root-path and SQL-specific assertions only; kept seekable-stream check,
  max_blob_size, delete_folder non-recursive (extended conformance skips flat-namespace), and
  all schema-variant/path-validation/concurrency/WR/glob tests.
  Per-backend spec IDs orphaned by the deletions (SFTP-015–019, SQL-BLOB-021/023/024/031/032)
  were restored by adding the corresponding `@pytest.mark.spec` markers alongside the
  existing BE-xxx markers on the conformance tests that exercise the same behavior.
  No spec content was changed — the conformance suite is accepted as the traceability
  proxy for these per-backend IDs (sdd/000-process.md Rule 2 satisfied).
  S3/S3-PyArrow/Local files were already lean or contain specific assertions beyond
  what conformance covers.

- [x] **BK-152 — Single conformance test for WriteResult/FileInfo consistency + fix violating backends**
  Added `test_write_result_rich_fields_match_file_info` (gated on `WRITE + METADATA`,
  not `WRITE_RESULT_NATIVE`) to `TestWriteResultConformance`; removed the two
  narrower superseded tests (`test_native_file_info_matches_write_result`,
  `test_digest_matches_file_info`) and their xfail tables. Fixed four backends:
  S3PyArrow (post-upload `head_object` for `etag`/`digest`/`last_modified`),
  Local (reuse post-write `stat()` for `last_modified`), SFTP (post-upload
  `sftp.stat()` for `last_modified`), SQLAlchemy (decouple `last_modified` gate
  from `user_metadata` column). All four now declare `WRITE_RESULT_NATIVE` (except
  SQLAlchemy legacy schema, which remains `basic` pending etag/digest support).
  Guard direction flipped to `if info.modified_at is not None` to catch backends
  that return richer data from `get_file_info()` than from `write()`.

- [x] **BUG-181 — Verify HNS `write_atomic` WriteResult rich-field parity**
  Added four mock-based tests to `TestAsyncAzureHNSPaths`: rich fields (`etag`,
  `last_modified`, `size`, `source`) populated from `get_file_properties()` response;
  `version_id` and `digest` confirmed `None` on HNS (ADLS Gen2 `PathProperties` does not
  surface `content_md5` or `version_id` via `get_file_properties()`);
  `metadata=` kwarg forwarded to the pre-rename `upload_data` call; `WriteResult.metadata`
  echo is by construction per WR-012 (post-rename preservation on the live file deferred — see BUG-182); `overwrite=True`
  skips the existence check; `overwrite=False` with existing file raises `AlreadyExists`.
  Removed stale `# pragma: no cover` from the HNS `write_atomic` block.
  Spec: WR-004, WR-010, WR-012, ASYNC-010.

- [x] **ID-013b — Async Store API Phase 3: async extensions**
  `AsyncStore.write*()` now returns `WriteResult` and accepts `metadata=`.
  `AsyncBackend.write` / `write_atomic` ABC updated with `metadata=` kwarg and
  `WriteResult` return type. `AsyncMemoryBackend`, `AsyncAzureBackend`, and
  `SyncBackendAdapter` all updated. `AsyncBackendSyncAdapter` unmasked
  `USER_METADATA` and `WRITE_RESULT_NATIVE` capabilities. New module
  `aio.ext.write` with `write_with_hash` helper. Resolves BUG-179 as a subset.

- [x] **BUG-179 — `AsyncBackend.write` / `write_atomic` missing `metadata=` kwarg**
  Fixed as part of ID-013b. All async write methods now accept `metadata=` and
  enforce `Capability.USER_METADATA` at the `AsyncStore` layer.

- [x] **BUG-180 — ResourceWarning in tests under Python 3.14 (HTTPError not closed)**
  `UrllibTransport._request()` discarded the caught `HTTPError` without calling
  `close()`. On Python 3.14 this emits a `ResourceWarning` during GC, surfaced
  in tests as `PytestUnraisableExceptionWarning`. The fd leak is in the production
  urllib transport path, but only manifests visibly in the test environment;
  fixed with `contextlib.closing(exc)` in `_http.py`.

- [x] **ID-158 — pytest-asyncio ↔ `AsyncBackendSyncAdapter` event-loop leak**
  Root cause: pytest-asyncio 1.3 calls `asyncio.get_event_loop()` when setting up
  each async test; Python 3.11 auto-creates a new loop when none is set and stores it
  in the thread-local policy. pytest-asyncio saves it as `old_loop` and restores it as
  the policy default after teardown. A subsequent sync test calling `asyncio.run()`
  orphans it: `asyncio.run` replaces the policy default and sets it to `None` without
  closing the old loop. The loop's internal cyclic reference (`_read_from_self` bound
  method ↔ Handle) keeps it alive until `gc.collect()` at session teardown, where
  `BaseEventLoop.__del__` emits `ResourceWarning` (promoted to error by BK-158).
  Fix: session-scoped autouse fixture `_close_leaked_event_loops` in
  `tests/conftest.py` closes all unclosed non-running event loops before pytest's
  `gc_collect_harder()` runs (session fixtures finalise before
  `config._ensure_unconfigure()`). Also restored the `os_sensitive` marker on the
  `adapter-local` param of `adapted_backend` in
  `tests/aio/test_sync_adapter_conformance.py` (unblocked by this fix).
  Regression test: `TestCloseSemantics::test_loop_closed_after_close` in
  `tests/aio/test_async_to_sync_adapter.py`.

- [x] **BK-158 — Promote unhandled warnings to errors in pytest**
  Added `filterwarnings = error` to `[tool.pytest.ini_options]`; existing SQLAlchemy
  suppressors retained with inline justification.

- [x] **BK-157 — Tighten docs site spacing via custom CSS**
  Reduced whitespace noise across all docs pages. Table cell padding halved.
  Classic typography rule applied to all headings (h1–h6 and mkdocstrings
  `.doc-heading`): generous `padding-top` above, tight `margin-bottom` below.
  Compact mkdocstrings section paragraphs (`Parameters:`, `Returns:`, `Raises:`),
  bullet lists, signature blocks, and `<hr>` dividers. Adjacent-sibling rule
  cancels double-gap when a prose heading immediately precedes a method block.

- [x] **BK-153 — Address backend-specifics visibility findings from audit-009**
  Added three-tier admonition vocabulary (info/note/warning) to all
  `docs-src/api/` pages: capability-gate notes on all B-series methods,
  backend-conditional argument notes on `metadata=` and `max_depth=`,
  backend-conditional field notes on `FileInfo`, `WriteResult`, `FolderInfo`,
  `ResolutionPlan`, and `BackendConfig.options`, interop-section warnings on
  `Backend`, `AsyncBackend`, `AsyncStore`, `ProxyStore`, `ReadOnlyHttpBackend`,
  and module warning on `SFTPUtils`. Documented the three-tier vocabulary in
  `sdd/DOCUMENTATION.md`. Fixed region tag naming in `_store.py` and
  `_async_store.py`. Closed all 20 findings from audit-009.

- [x] **BK-155 — Consolidate S3 + S3-PyArrow tests and specs against shared base**
  Extracted shared invariants to `tests/backends/test_s3_shared.py`,
  parametrized over both `S3Backend` and `S3PyArrowBackend` with per-param
  `pytest.mark.spec(...)` marks preserving both `S3-NNN` and `S3PA-NNN`
  traceability. Category-1 duplicates already covered by
  `test_conformance.py` (ReadWrite, Listing, Metadata, Delete, Operations,
  generic error mapping, close/unwrap-wrong-type, Glob patterns) were
  deleted from `test_s3.py` and `test_s3_pyarrow.py`. Category-2
  genuinely-shared invariants (construction validation, endpoint-URL
  normalization, `client_options` non-mutation, tls_ca_bundle s3fs-control
  path, folder semantics, resolve details, BK-123 BFS listing,
  s3fs-path retry debug log) moved into the shared file. Added a
  `test_glob_yields_fileinfo_only` conformance test (GLOB-004) to close the
  one coverage gap. Slimmed `sdd/specs/011-s3-pyarrow-backend.md` to a
  delta-spec over `sdd/specs/008-s3-backend.md`; only PyArrow-specific
  invariants (S3PA-002/003/006/007/012/021) retain full bodies.
  Normalized `backend._fs` → `backend._s3fs` in the two remaining call
  sites in `test_s3.py`. Net -1300 lines of test code; spec duplication
  eliminated. Follow-up to BUG-178 (code-layer dedup).

- [x] **BUG-178 — s3fs lazy init raises "got multiple values for keyword argument 'config'" when `client_options={"config_kwargs": {...}}` and `retry=RetryPolicy` are both supplied**
  Moved the s3fs kwargs builder into `_S3Base._build_s3fs_kwargs()`. The helper pops
  `config_kwargs` from the options dict and folds it into `client_kwargs["config"]` as a
  `botocore.config.Config` *before* the retry-derived `Config` is applied, so
  `aiobotocore.create_client()` only ever sees one `config=` argument. Retry-policy values
  win on conflicts. Both `S3Backend._fs` and `S3PyArrowBackend._s3fs` now delegate to the
  shared builder. `_S3PyArrowBackend._pa_fs` (PyArrow data path) is unaffected.

- [x] **BUG-175 — `SQLBlobBackend.glob` drops zero-segment `**/` matches on SQLite**
  Replaced the SQLite `GLOB` pre-filter with `extract_prefix` + `LIKE` narrowing
  (option b). The old `GLOB` operator treated `**` as two independent `*`s and
  required a literal `/` between them, dropping zero-directory matches. The new
  path extracts the longest literal prefix and uses `key LIKE 'prefix/%'`; the
  existing regex handles final filtering. Conformance skip removed.

- [x] **BUG-172 — `_ChunkPullReader.read`/`readinto` return empty on closed stream instead of raising `ValueError`**
  Added `_closed_on_error` flag to distinguish user-close (raises `ValueError`)
  from error-close (returns `b""`/`0`, per ASYNC-090 spec). Tests updated.

- [x] **BK-154 — pyarrow 24.x mypy compatibility**
  pyarrow 24.0.0 shipped partial type stubs that surfaced `attr-defined`,
  `name-defined`, and `no-untyped-call` errors under mypy strict mode. Added
  `follow_imports = "skip"` for `pyarrow`/`pyarrow.*` in `pyproject.toml`;
  removed `# type: ignore[import-untyped]` from pyarrow imports in
  `ext/arrow.py`, `ext/parquet.py`, `backends/_s3_pyarrow.py`, and
  `backends/_sqlalchemy.py`. Included in PR #485 alongside BUG-176.

- [x] **BUG-176 — `SQLBlobBackend.copy(src, src, overwrite=True)` silently destroys data**
  Mirrored the `src == dst` early-return guard from `move()` into `copy()`:
  check source exists, then return. Fixes both the data-destruction case
  (`overwrite=True` deleted the row before `INSERT ... SELECT`) and the
  spurious `AlreadyExists` case (`overwrite=False`). Both
  `test_self_copy_preserves_data` and `test_self_copy_no_overwrite_preserves_data`
  now pass on `sql-blob`; `_NO_SELF_COPY_BACKENDS` removed from tests.

- [x] **BUG-177 — `S3Backend.write` does not surface the auto-CRC32 digest that `get_file_info` returns**
  `write()` called `s3fs.info()` after the upload, which omits checksum
  fields, leaving `WriteResult.digest = None` while `get_file_info()` issued
  `head_object(..., ChecksumMode="ENABLED")` and returned
  `ContentDigest('crc32', …)` — a WR-001a divergence.
  Fix: replaced `self._fs.info(...)` with `self._fs.call_s3("head_object",
  ..., ChecksumMode="ENABLED")` in `_s3.py:write()`, then extracted `digest`
  via `_digest_from_head_response()` (the same path `get_file_info` uses).
  New conformance test `TestWriteResultConformance.test_digest_matches_file_info`
  enforces `result.digest == info.digest` across all `WRITE_RESULT_NATIVE +
  METADATA` backends. `_DIGEST_XFAIL` table is empty (no known lags).
  WR-007 comment in `test_native_file_info_matches_write_result` updated to
  point to the new test.

- [x] **ID-147 — TLA+ augmentation: Observer dispatch module + informational CI**
  `Observer.tla` shipped under `sdd/formal/tla/` shadowing spec 019
  § OBS-003, OBS-003a, OBS-009. Six independent invariants (I1
  `EventPerCompletedOp`, I2 `RoutingByOpClass`, I3a
  `ClassHookOutcomeIndependent`, I3b `ErrorHookFiresOnErrorOnly`, I4
  `ErrorAlwaysReraise`, I5 `AfterHookExceptionIsolated`) — the shortlist
  grew from five to six when `HookOutcomeContract` was split into I3a / I3b
  under break-and-catch. Full break-and-catch matrix verified each invariant
  is independently falsifiable. `Backend.tla` and `Store.tla` dropped — no
  valid bundled target per the authoring rules. Informational `verify-tla`
  CI job added to `.github/workflows/ci.yml` (non-blocking; first revisit
  tracked as ID-150, due 2026-10-19). PRs #458 (formal-layer principles)
  and #460 (Observer.tla + CI job).

- [x] **ID-152 — Dafny `last_modified` spec-opacity follow-up (oracle xfail closed)**
  Prerequisite (BUG-169) landed: the Python `MemoryBackend.write` now populates
  `last_modified`, so the Dafny spec could drop its opaque `Option_None()`
  hardcode.  `MemoryBackend.dfy:Write` now returns a capability-conditional
  timestamp witness (`Some(0)` when `CapWriteResultNative in capabilities`,
  `None` otherwise) for both `FileInfo.last_modified` and
  `WriteResult.last_modified`; the adapter at `tests/backends/dafny_oracle.py`
  lifts `Some(n)` to `datetime.fromtimestamp(n, tz=timezone.utc)`.
  `MemoryBackendMinimal` is untouched (it does not declare
  `CapWriteResultNative`).  `MemoryBackend-py/module_.py` regenerated via
  `scripts/dafny_translate.sh` + `_dafny_classorder.py`.  The `"dafny-oracle"`
  entry in `_LAST_MODIFIED_XFAIL` was removed; the dict is now empty.

  **Exit criteria met:** `test_native_populates_last_modified[dafny-oracle-*]`
  passes without xfail; `bash scripts/dafny_verify.sh` green (98 verified, 0
  errors).

  Related: BUG-169 (done), ID-151 (done).

- [x] **BUG-173 — Azure HNS `write_atomic` leaks WriteResult-construction failures as write failures**
  `_azure.py:write_atomic` (HNS branch): after a successful
  `tmp_fc.rename_file()` commit, `dst_fc.get_file_properties()` was called
  to populate `etag`/`last_modified`; a failure there (eventual
  consistency, network blip, permissions) propagated through
  `self._errors(path)` as a write failure even though the data was
  already at the destination. Callers that retried saw `AlreadyExists`
  (with `overwrite=False`) or silently double-wrote. Fix wraps the
  post-rename `get_file_properties` in try/except, logs a
  `log.warning`, and returns a native-source `WriteResult` with rich
  fields left unset. New mock-based regression test
  `TestAzureHNSPaths.test_write_atomic_hns_swallows_post_rename_read_failure`
  pins the behaviour (conformance/Azurite cannot reach this failure mode).

  Related: ID-151 (done), BUG-169 (done), BUG-170 (done).

- [x] **BUG-170 — `SQLBlobBackend.write` omits `last_modified` from `WriteResult` under `WRITE_RESULT_NATIVE`**
  `_sqlalchemy.py:write` advertised `WRITE_RESULT_NATIVE` when the
  `user_metadata` column was present but returned
  `WriteResult(last_modified=None, ...)` while the `now` timestamp was
  being written to the DB — WR-001a rich-field obligation violation. Fix
  derives the WriteResult's `last_modified` from the same float →
  datetime round-trip that `get_file_info` already uses
  (`datetime.fromtimestamp(now, tz=timezone.utc)`), gated on both
  `user_metadata` and `modified_at` column presence so that a subset
  schema still returns `None`. The `"sql-blob"` entry in
  `_LAST_MODIFIED_XFAIL` flipped from strict-xfail to pass and was
  removed.

  Related: ID-151 (done), BUG-169 (done).

- [x] **BUG-169 — `MemoryBackend.write` omits `last_modified` from `WriteResult` under `WRITE_RESULT_NATIVE`**
  `_memory.py:write` declared `WRITE_RESULT_NATIVE` but returned
  `WriteResult(last_modified=None, ...)` while the node's `modified_at`
  was populated — WR-001a rich-field obligation violation on a declaring
  backend. Fix captures a single `now = datetime.now(timezone.utc)` under
  the lock and uses it for both `_FileEntry.modified_at` (new and updated
  paths) and `WriteResult.last_modified`, giving `result.last_modified ==
  info.modified_at` on a subsequent `get_file_info`. The `"memory"` entry
  in `_LAST_MODIFIED_XFAIL` (strict-xfail in
  `TestWriteResultConformance.test_native_populates_last_modified`) flipped
  and was removed.

  Related: ID-151 (done), BUG-170.

- [x] **ID-151c — Hypothesis property coverage for `WriteResult`**
  Step 3 of the WriteResult testing plan. `TestWriteResultConformance`
  (ID-151 Part 3 / ID-151b) covers fixed-example WR-001a / WR-003 / WR-004 /
  WR-005 / WR-012 / WR-013 across the full fixture matrix; a property net
  then exercises size-regime randomness and metadata-shape randomness that
  example-based cases cannot enumerate. Adds `tests/test_pbt_write_result.py`
  with two properties:
  1. `WriteResult.size == len(payload)` for `write` / `write_atomic` across
     payload regimes (0 B, `<` 4 KiB small, 256 KiB–1 MiB BUG-168 buffer
     boundary) on `MemoryBackend` (fast oracle) and `LocalBackend` (only
     backend that exercises a real `BufferedWriter`), for both `bytes` and
     `BinaryIO` inputs under `overwrite=True` / `overwrite=False`.
  2. Metadata round-trip (WR-012 echo + WR-013 `get_file_info` round-trip)
     on S3 via `moto` (server mode) and Azure via Azurite (when reachable)
     — the two v1 backends that declare `USER_METADATA` and go through a
     real SDK serialisation path. Strategies are module-scope and
     WR-011-compliant (ASCII keys, printable-ASCII values, 2 KB cap).
     Profiles inherit from `tests/conftest.py` (dev 50 / ci 100 /
     nightly 1000). Per TESTING.md Rules 5 + 6, no mocks of third-party
     SDKs — Azurite / moto are used as the real dependencies.

  Related: ID-151 (done), ID-151b (done), BUG-168 (done).

- [x] **ID-151b — Retire per-backend `WriteResult` test duplication**
  Follow-up to ID-151 Part 3. With `TestWriteResultConformance` now covering
  every backend's `WriteResult` path+size, source, rich-field gating,
  last_modified, `get_file_info` divergence, and metadata echo/round-trip,
  the per-backend `write` / `write_atomic` / size / metadata-echo methods
  were redundant. Deleted `TestLocalWriteResult`, `TestSFTPWriteResult`,
  `TestS3PyArrowWriteResult`, and the generic overlap from `TestS3WriteResult`,
  `TestAzureWriteResult`, `TestAzureWriteResultIntegration`. Kept SDK-level
  assertions not expressible at the conformance layer: Azure etag stripping,
  version_id population, digest-None-on-default, metadata-passed-to-SDK (mock
  kwargs), non-HNS `write_atomic` path, `WRITE_RESULT_NATIVE` /
  `USER_METADATA` capability declarations, and Azurite-wire etag /
  last_modified checks. S3 `test_write_metadata_passed_to_sdk` retained as
  the only HeadObject-verifying metadata test on that backend. Accepted
  trade-off: WR-001 / WR-003 / WR-004 on Azure are now covered by
  `TestWriteResultConformance` via the `azure_backend` Azurite fixture only;
  Azurite-less matrix runs (Windows, macOS, Docker-less Linux) skip those
  assertions rather than keep a mock-of-third-party smoke, per TESTING.md
  Rules 5 (don't mock what you don't own) and 6 (prefer real dependencies).
  `hatch run lint` clean; `hatch run test-cov` 97.98 %.

  Related: ID-151 (done).

- [x] **ID-151 — Dafny `WriteResult` extension: field-mapping + capability round-trip**
  Five-part series extending `sdd/formal/BackendContract.dfy` to model
  `WriteResult` and encoding WR-001a, WR-004, WR-008, WR-012, WR-013 as
  backend-layer postconditions on `Write`; refining `MemoryBackend.dfy`;
  regenerating and wiring the compiled oracle; and adding Python conformance
  assertions for every backend.

  - **Part 1** — `BackendContract.dfy`: `Option<T>`, `ContentDigest`,
    `WriteSource`, `FileInfo`, `WriteResult` datatypes; `CapWriteResultNative`
    and `CapUserMetadata` capabilities; `HasUserMetadata` predicate +
    `BasicFileInfo` helper; `Write` widened to `Result<WriteResult>` with
    fourth `metadata` parameter; WR-001a/004/005/010/012/013 postconditions;
    `WriteResultFromFileInfo` function + `WR008FieldMapping` lemma.
    `MemoryBackend.dfy` refinement discharges all new postconditions.
  - **Part 2** — Docker-based Dafny translate (`scripts/dafny_translate.sh`)
    lifted the toolchain blocker. Regenerated `MemoryBackend-py/module_.py`;
    automated class reorder (`scripts/_dafny_classorder.py`). Oracle-gated
    conformance: 154 passed, 5 skipped.
  - **Part 3** — Adds `TestWriteResultConformance` in
    `tests/backends/test_conformance.py` exercising every backend's `write` /
    `write_atomic` return value against the Dafny postconditions. Surfaces
    BUG-169, BUG-170 as strict `xfail`s; catches BUG-168.
  - **Part 4** — `MemoryBackendMinimal` sibling refinement in
    `MemoryBackend.dfy` declares neither `CapWriteResultNative` nor
    `CapUserMetadata`, making the WR-010 `CapabilityNotSupported` gate live
    code and always producing `BasicSource` — closes the refinement coverage
    gap. 98 verified, 0 errors.
  - **Part 5** — `DafnyOracleBackend` adapter widening: `write()` /
    `write_atomic()` accept `metadata=` and return `WriteResult`;
    `get_file_info()` / `list_files()` marshal `FileInfo.metadata`. All
    oracle skips in `TestWriteResultConformance` removed; 101 passed,
    2 xfailed (BUG-169 parity).

  Related: ID-146 (done), ID-134, ID-147.

- [x] **BUG-168 — `LocalBackend.write_atomic` reports stale `WriteResult.size` for streaming input**
  `_local.py:197-203`: `size = os.path.getsize(tmp_path)` was called *inside*
  the `with os.fdopen(fd, "wb") as f:` block, before the `BufferedWriter`
  had flushed. For `BinaryIO` content whose tail was still buffered the
  returned `size` was truncated to the last-flushed offset. Originally
  demoted to LOW when the conformance xfail went XPASS on Linux 3.13 and
  Windows cross-OS CI, but Python 3.14 surfaced the defect as
  `size == 0` on a 100 KiB payload (the 3.14 `BufferedWriter` default
  block size is large enough that none of the payload reaches disk
  before `getsize` runs). Fix: move the `size` capture after the `with`
  block closes and after `os.replace`, using `full.stat().st_size`
  (matching the pattern already used by the non-atomic `write()`
  branch on line 173). Caught by
  `TestWriteResultConformance.test_size_matches_written_bytes_for_streaming_input`
  under ID-151 Part 3.

- [x] **BUG-174 — `test_streaming_integrity` SFTP→Azure pipe-threshold flake**
  Intermittent CI failure on the 7-backend streaming chain, always on the
  `sftp -> azure` hop, always `pipe memory 2.00 MiB > threshold 1.50 MiB` on
  payloads of 7–14 MiB (e.g. PR #460 run 2026-04-19). Isolated reproducer
  (`tmp/sftp_azure_pipe_probe.py`) shows the violation is structural: 35/35
  runs across sizes 7/10/11.4/13/14 MiB × 7 seeds measure exactly 2.00 MiB,
  100 % attributed to `ext/streams.py`. Root cause is a tracemalloc
  attribution pile-up: Azure SDK's staged-block uploader retains the
  previously-staged 1 MiB chunk until the next `stage_block` ack returns,
  and when the source is wrapped in `io.BufferedReader` (SFTP, Azure) the
  C-level bytes allocation is attributed to `ProgressReader.read` in
  `ext/streams.py`, landing both chunks in the pipe filter. Stripping
  `BufferedReader` in the probe drops the measurement to 0.00 MiB
  (allocations then live in paramiko's Python code, outside the filter) —
  confirming it's an attribution artifact, not a real regression. Fix:
  `PIPE_THRESHOLD` raised 1.5 MiB → 2.25 MiB in
  `tests/e2e/test_streaming_integrity.py`, with the comment updated to
  document the two-chunk hold. No production-code change.

- [x] **ID-149 — e2e coverage for write_with_hash / open_atomic_with_hash across real backends**
  New `tests/e2e/test_ext_write_e2e.py`: two test classes (`TestWriteWithHash`,
  `TestOpenAtomicWithHash`) exercise both helpers against all available Docker
  backends (S3/MinIO, SFTP, Azure/Azurite, S3-PyArrow, SQLBlob, Memory). Each
  test writes a deterministic 4 KiB payload and asserts the returned
  `WriteResult.digest` matches the pre-computed SHA-256. EW-004 pre/post-exit
  invariant (`writer.result is None` before, populated after) verified inline.
  Backends degrade gracefully when Docker infra is unavailable.

- [x] **ID-148 — ID-146 docs ripple: WriteResult / head() / ext.write in guides and API reference**
  `docs-src/write-integrity.md` new guide (write_with_hash, open_atomic_with_hash,
  head(), user metadata). `Store.head()` exposed in `docs-src/api/store.md`.
  `ext.write` surfaced in extensions nav and index. `FEATURES.md` gains `head()`
  and ext.write row. README "What you get" and extensions table updated.
  RFC-0011 status flipped to Implemented. PR #455.

- [x] **ID-146 — Land RFC-0011: `WriteResult` + opt-in hashing**
  `Store.write*()` returns `WriteResult`; `Store.head()` added (requires
  `Capability.METADATA`); `metadata=` kwarg gated by `Capability.USER_METADATA`;
  `Capability.WRITE_RESULT_NATIVE` signals rich backend write responses.
  All backends updated; proxy stack (`ProxyStore`, `ObservedStore`, `CachedStore`)
  forwards `WriteResult` and `head()`; `StoreEvent.metadata["write_result"]`
  populated on successful writes. `ext.write` ships `write_with_hash` and
  `open_atomic_with_hash` (`HashingAtomicWriter`) for guaranteed client-side
  digest. `FileInfo.metadata` added. Spec 045 (WR-001..WR-019), spec 046
  (EW-001..004), RFC-0011, ADR-0026. PRs #452, #453, #454.

- [x] **ID-147b — TLA+ PoC: WriteResult spec consistency**
  Minimal TLA+ spike targeting spec 045 (WriteResult) to evaluate TLA+
  as both bug-finder and spec-decomposition discipline. Two modules
  (`WriteHeadRoundTrip`, `WR018ProxyForwarding`), five independently
  verified invariants, Docker-based TLC toolchain
  (`scripts/tlc_check.sh`). Findings: WR-018's single Markdown paragraph
  bundles four distinct claims; three are independently breakable TLC
  invariants. Workflow recommendation in
  `sdd/research/research-id-147b-tla-poc.md`. PR #451.

- [x] **ID-145 — `scripts/gen_pages.py` refactor**
  Split the 840-line mkdocs-gen-files hook into
  `scripts/docs/{scan,render,nav,link}.py` plus a 70-line orchestrator;
  example metadata and link rewrites are now data-driven via `SddKind`,
  self-describing example docstrings, and `LinkResolver`. PR #444.

- [x] **BUG-167 — `AsyncBackendSyncAdapter.close()` and stream paths leak unawaited coroutines**
  Five additional `run_coroutine_threadsafe` call sites had the same
  build-coroutine-before-submit pattern as BUG-166: `close()` (`aclose` and
  `_drain_tasks`), `_ChunkPullReader._pull_chunk` and `close()`, and
  `_AsyncIteratorBridge.__next__` and `__del__`. When the loop was already
  stopped, `RuntimeError` was caught but the coroutine was discarded
  unawaited, leaking `RuntimeWarning: coroutine '_drain_tasks' was never
  awaited` (and equivalents). All six sites now close the coroutine on every
  fail-fast path. Regression test
  `TestCloseSemantics::test_close_does_not_leak_coroutine_when_loop_already_stopped`
  asserts close() is leak-free after a forced-stop loop. Bundled with the test
  warning hygiene cleanup in this PR: every test helper that builds a backend
  now registers it on a per-test list aclose'd by an autouse fixture,
  eliminating the `ResourceWarning`s previously emitted at GC time across the
  Azure, SFTP, and conformance suites.

- [x] **BUG-166 — `AsyncBackendSyncAdapter` leaks unawaited coroutine on closed/running-loop guard**
  Scalar methods (e.g. `exists`) build the coroutine before `_submit` runs
  the closed/running-loop guard, so a `RuntimeError` from the guard left the
  coroutine uncollected and surfaced `RuntimeWarning: coroutine '…' was never
  awaited`. `_submit` now closes the coroutine on every fail-fast path. Five
  `@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:…")`
  workarounds in `tests/aio/test_async_to_sync_adapter.py` were removed and a
  `recwarn`-based regression test in `TestClosedAdapterReuse` asserts the
  closed-guard no longer leaks. Bundled with a companion test-hygiene fix in
  `tests/test_backend_sqlblob.py::test_close_owned_engine`: the brittle
  post-close `read_bytes` probe (which silently re-opened a connection on the
  disposed engine and triggered `ResourceWarning: unclosed database`) is
  replaced with a direct pool-identity assertion against SQL-BLOB-041.

- [x] **BUG-165 — `AsyncAzureBackend.write` violates streaming promise**
  `AsyncAzureBackend.write` / `write_atomic` materialized any
  `AsyncIterable[bytes]` payload into a single ``bytes`` buffer before
  calling ``upload_blob`` / ``upload_data``, breaking the streaming contract
  (SIO-003, ASYNC-021) and holding the full file in memory — caught by the
  e2e streaming-integrity chain on the `sftp -> azure-bridged` hop (pipe
  memory == file size). Azure SDK accepts ``AsyncIterable[bytes]`` directly
  and streams in bounded memory; the materialization block is removed and
  the unit test now asserts pass-through. Found while landing ID-143b.

- [x] **ID-143b — `AsyncBackendSyncAdapter` real-backend coverage**
  Integration test suite (`tests/aio/test_async_to_sync_adapter_integration.py`)
  exercises the full sync `Backend` API contract through the adapter backed by
  a live `AsyncAzureBackend` against Azurite — lifecycle (ASYNC-088, ASYNC-092),
  capabilities (ASYNC-084), core I/O and streaming (ASYNC-080, ASYNC-081, ASYNC-087),
  atomic write (ASYNC-085), listing (ASYNC-032), error mapping (ASYNC-087), health
  check (ASYNC-093), and closed-adapter reuse (ASYNC-083). Bridged-Azure variant
  added to `tests/e2e/test_streaming_integrity.py` with a dedicated
  `BRIDGED_AZURE_THRESHOLD_FACTOR` (0.80) to account for per-chunk thread-crossing
  overhead (ASYNC-080); the `_measure_transfer` helper gains a
  `total_threshold_override` parameter for per-hop threshold control.
  Depends on: ID-143, ID-143c (done).

- [x] **ID-144 — Codify content rule 6: doc code blocks sourced from `examples/snippets/`**
  Added rule 6 to `sdd/CONTENT-RULES.md` making the existing `examples/snippets/`
  practice (ID-057, ID-106) a review-enforced rule. Doc code blocks come from
  `examples/snippets/` via `pymdownx.snippets` `--8<--` regions, so CI catches
  API drift. Hand-written fences allowed only when a snippet cannot execute in
  CI (e.g. needs real credentials); reason noted inline.

- [x] **ID-143c — `AsyncBackendSyncAdapter` review follow-ups**
  `_ChunkPullReader` promoted to `io.RawIOBase` subclass; `_AsyncIteratorBridge`
  gains best-effort `__del__` for GC-path `aclose()`; `close()` drain loop
  repeats until the private loop is quiet (closes close-race window); docstrings
  on `close`, `read`, `unwrap`, `check_health` completed; test suite extended
  (concurrent-close, abandoned-stream GC, `write_atomic` mid-BinaryIO);
  `TestRunningLoopFailFast` / `TestPropertyPassthrough` / `TestScalarIODelegation`
  parametrized; new guide `guides/async-sync-bridges.md`.
  Depends on: ID-143 (done).

- [x] **ID-143 — `AsyncBackendSyncAdapter` implementation + unit test suite**
  Implemented `AsyncBackendSyncAdapter(Backend)` — wraps any `AsyncBackend`
  as a synchronous `Backend` via a private event loop on a dedicated daemon
  thread. Covers the full behaviour contract in
  [ADR-0025](adrs/0025-async-to-sync-backend-adapter.md) and
  [spec 029](specs/029-async-store-backend-api.md) § AsyncBackendSyncAdapter
  (ASYNC-080…093). Unit test suite in `tests/aio/`, every test traced to its
  spec ID via `@pytest.mark.spec`; uses the doubles from `tests/aio/_doubles.py`.
  Real-backend coverage (Azurite + e2e) deferred to ID-143b.
  Unblocks ID-127 (Graph backend). PR #439.

- [x] **ID-142 — `AsyncBackendSyncAdapter` spec block + test doubles**
  Pinned the invariants
  [ADR-0025](adrs/0025-async-to-sync-backend-adapter.md) records in
  prose as a normative `ASYNC-NNN` block in
  [spec 029](specs/029-async-store-backend-api.md) § AsyncBackendSyncAdapter,
  and added async-backend test doubles under `tests/aio/` for adapter
  failure-path coverage. Unblocks the ID-127 implementation PR.

- [x] **ID-141 — Async-to-sync backend adapter ADR**
  Drafted [ADR-0025](adrs/0025-async-to-sync-backend-adapter.md):
  `AsyncBackendSyncAdapter` owns a private event loop on a dedicated
  thread, submits via `asyncio.run_coroutine_threadsafe`, fails fast
  when invoked from a running loop, no `nest_asyncio` dependency,
  per-capability translation (`SEEKABLE_READ` masked, rest forwarded),
  `open_atomic` synthesised over `write_atomic`. Updated RFC-0010
  § Async posture. Spec-ID allocation deferred to ID-142
  (prerequisite for the ID-127 implementation PR). PR #435.

- [x] **BK-151 — PR #426 test-quality cleanup**
  Addressed review feedback on the ID-013b coverage PR: removed `os.getuid()`
  at module import (Windows collection crash); monkeypatched `tempfile.mkstemp`
  to exercise the `PermissionDenied` mapping cross-platform; added `spec=` to
  every `MagicMock()` so `scripts/check_mock_spec.py` stays green; added real
  assertions and `caplog` checks to S3-PyArrow retry debug-log tests; made
  `test_s3fs_retry_with_existing_config_merges` verify the merged
  `botocore.config.Config`; replaced class-dict mutation in the cache invalidate
  fallback with a bespoke `CacheBackend` lacking `clear_prefixes`; switched the
  `AsyncBackend.iter_children` default test to a concrete subclass that inherits
  it. PR #426.

- [x] **BUG-164 — `docs.yml` `pages` job blocked by environment protection rules on release tags**
  `docs.yml` ran in tag ref context (`refs/tags/vX.Y.Z`) on `release: published` events;
  the `github-pages` environment protection rules only allow branch refs. Extracted the
  `pages` job into a new `gh-pages-deploy.yml` triggered by `workflow_run` on `Docs`
  completion — which always runs in the default branch context (branch ref), satisfying
  the environment protection. (`push: gh-pages` was ruled out: `GITHUB_TOKEN` pushes
  do not re-trigger workflows.) Removed now-unused `pages` and `id-token` permissions
  from `docs.yml`.
  PR #424.

## v0.23.0

- [x] **BK-150 — Design index and Further Reading reshape**
  Fixed the mixed-mode / overlap state left after PR #418. `design/` now
  surfaces every `sdd/` process document: added `documentation-standards.md`
  and `content-rules.md` include-wrappers for `sdd/DOCUMENTATION.md` and
  `sdd/CONTENT-RULES.md`; added Audits section — `gen_pages.py` scans
  `sdd/audits/` and generates `design/audits/index.md` plus per-audit wrapper
  pages; `_scan_entries` extended to accept `audit-NNN-*` stems.
  `further-reading.md` stops duplicating the SDD / conventions / research
  enumeration (CONTENT-RULES rule 4 — one copy per fact) and points at
  `design/`; documentation-convention links switched from GitHub to on-site
  relative links now that the pages exist (DOCUMENTATION.md § 4).
  PR #420.

- [x] **BK-149b — Apply CONTENT-RULES.md to Guides, Explanation, and remaining sections**
  Guides, Explanation, Getting Started, and README: pseudo-precise values removed
  from performance prose and comparison table; manually-maintained benchmark
  snapshot replaced with pointer to generated comparative tables; inline extension
  enumerations replaced with principle descriptions; capability counts removed from
  backend decision guide; conformance test counts removed from custom-backend guide;
  security SLAs deferred to SECURITY.md; source path replaced with API reference
  link. Completes BK-149.

- [x] **BK-149 — Apply CONTENT-RULES.md to Reference section (part 1)**
  Reference section cleanup: stale capability counts removed from 8 backend
  guides; duplicate capability tables replaced with links to
  `capabilities-matrix.md`; Capability enum reordered logically; RemotePath
  unified into `models.md` (path.md deleted); API pages rebuilt with
  DOCUMENTATION.md § 8 building blocks; ext module docstrings converted to
  MkDocs admonition syntax. Remainder (Guides, Explanation) tracked as BK-149b.
  PR #416.

- [x] **ID-134c — Remove SumSizesAddOneLocal workaround after Dafny upgrade**
  Dafny 4.11.0 fixes the Boogie procedure emission bug for lemmas from included
  files that transitively use `:|` in ghost functions. Replaced
  `SumSizesAddOneLocal` call with direct `SumSizesAddOne` from
  `BackendContract.dfy`; deleted the local duplicate lemma and workaround
  comment. Verification: 53 proofs (was 55 — 2-lemma reduction is the deleted
  duplicate). Script and toolchain reference updated to 4.11.0/ubuntu-22.04.

- [x] **BK-148 — Documentation content longevity rules**
  New `sdd/CONTENT-RULES.md` keeps prose from drifting out of sync with code
  and generated artefacts; `sdd/research/research-doc-content-longevity.md`
  records the motivating analysis. Wired into the existing doc ecosystem via
  `CLAUDE.md`, `DOCUMENTATION.md`, `CONTRIBUTING.md`, and `CLAUDE-REFERENCE.md`.
  Cleanup of existing docs against the rules is tracked as BK-149. PR #413.

- [x] **ID-137 — Reduce per-backend streaming overhead**
  All five sub-items addressed: (1) S3-PyArrow `open_output_stream` now passes
  `buffer_size=_COPY_BUFSIZE`; (2) Memory `read()` constructs `BytesIO`
  directly inside the lock (one fewer allocation); (3) SFTP `_CHUNK_SIZE`
  raised 32 KiB → 256 KiB; (4) Memory write ~10% over-allocation confirmed
  as standard Python `bytearray` growth, by-design; (5) Azure
  `max_block_size`/`max_single_put_size` raised 256 KiB → 1 MiB via new
  `_AZURE_BLOCK_SIZE` constant, decoupled from `_COPY_BUFSIZE`.
  Azure backend guide table updated. Spec MEM-010 updated.

- [x] **ID-136 — Document SQL backend non-lazy write as by-design**
  Backend guide, capabilities matrix, and docstring updated. Code comment
  shipped in PR #407.

- [x] **ID-134 — Verify `GetFolderInfo` aggregate fields (`file_count`, `total_size`) in Dafny postcondition**
  Part 1 (PR #406): Ghost infrastructure — `ChildFiles`, `SetToSeq`,
  `SumSizesSeq`, `SumSizes`, and five induction lemmas in
  `BackendContract.dfy`. Part 2 (PR #409): Strengthened `GetFolderInfo`
  postcondition to assert `file_count == |ChildFiles(fs, path)|` and
  `total_size == SumSizes(fs, ChildFiles(fs, path))`. `MemoryBackend.dfy`
  proves the loop correct via ghost set tracking and `SumSizesAddOne`
  induction. 55 verified proofs total. `MemoryBackend-py/module_.py` did not
  need regeneration — all ID-134 changes are ghost-only (lemmas, invariants,
  ghost variables produce no compiled Python output). Extended conformance
  tests added: `TestGetFolderInfoAggregates` in `test_conformance_extended.py`
  bridges Dafny postcondition to oracle-backed test suite.

- [x] **BUG-163 — `_ensure_known_hosts_file` 0o600 not enforced on Windows**
  NTFS ignores POSIX mode bits; `os.open(..., 0o600)` creates the file with
  `0o666`. Mode-assertion test now skipped on Windows with explanatory note.
  New cross-platform test asserts file creation succeeds without raising. PR #408.

- [x] **BUG-161 — Azure `write()` buffers entire stream into memory**
  Set `max_single_put_size`, `max_block_size` (256 KiB), and
  `min_large_block_upload_threshold` (1) on both `BlobServiceClient` and
  `DataLakeServiceClient` so uploads use staged blocks. PR #407.

- [x] **BUG-162 — Transfer pipe layer ~2 MiB overhead**
  All backends now use `_COPY_BUFSIZE` (256 KiB) for `shutil.copyfileobj`
  instead of platform default (1 MiB on Windows). Azure block size also
  set to 256 KiB. E2e streaming test hardened: warnings → assertions,
  random file size (7--14 MiB), random backend order. PR #407.

- [x] **BK-147 — Add SDD Expert to orchestrate skill**
  5th domain expert focused on spec-code consistency, ADR coverage, and
  process guide accuracy. Scoped to `sdd/` only. PR #405.

- [x] **ID-135 — E2e streaming integrity test**
  Proves the streaming contract — round-robin SHA-256 verification and
  `tracemalloc` memory profiling across all backends. PR #403.

- [x] **BK-146 — Eliminate string-literal `cast()` arguments (CodeQL + ruff); add `Capability.LAZY_READ`**
  All `cast("TypeName", value)` call sites replaced with `cast(TypeName, value) # noqa: TC006`.
  `BufferedReader`-over-`BytesIO` pattern removed from Memory and SQL backends (`BytesIO` is
  `BufferedIOBase`, returning it directly is correct). `BufferedReader` also removed from S3
  (s3fs `AbstractBufferedFile` already provides internal buffering).
  `FileInfo`/`FolderInfo` moved to runtime imports in `cache.py`.
  Added `Capability.LAZY_READ` quality flag: distinguishes backends that fetch data lazily
  from the native source (Local, HTTP, S3, S3-PyArrow, SFTP, Azure) from those that
  pre-load into memory (Memory, SQLBlob, SQLQuery). Spec SIO-009 added; conformance tests
  `test_read_is_lazy` and `test_read_is_lazy_readinto` added; capabilities matrix, backend
  guides (sql-blob, memory, sftp), and `FEATURES.md` updated.
  PR #401.

- [x] **BK-145 — Mutation testing CI workflow (manual + scheduled)**
  Added `.github/workflows/mutation.yml` with `workflow_dispatch` (manual) and
  weekly `schedule` (Saturday 05:00 UTC) triggers. Matrix strategy runs all 6
  scoped mutation targets in parallel (`core-api`, `core-infra`, `ext-proxy`,
  `ext-format`, `backends-local`, `backends-cloud`). Cloud-backend scope
  conditionally starts MinIO, Azurite, and SFTP Docker services. HTML reports
  uploaded as artifacts with 30-day retention. Gremlins cache persisted across
  runs via `actions/cache` (keyed on source hash). Report-only initially;
  threshold gate can be added later. PR #399.

- [x] **BUG-144 — Pages deployment fails: multiple artifacts + punycode deprecation**
  Duplicate `mike --push` calls triggered multiple built-in deployments.
  Fix: single push + explicit `pages` job with `deploy-pages@v4` (Node 20).

- [x] **BK-143 — Resolve all 31 open CodeQL security/quality alerts** (v0.22.1)
  Resolved all 31 alerts: file permissions, resource cleanup (`__del__`
  helpers), unused imports, type-stub no-ops. Regression tests added for
  the High (file permissions) and Error (unclosed resources) findings.
  Follow-up: `BinaryIO` kept as runtime import to prevent CodeQL false
  positives from ruff's `TCH003`/`TC006` auto-quoting.

- [x] **BK-142 — Harden CodeQL CI: scope, query suite, gating, dep review, annotations**
  Scoped CodeQL analysis to `src/remote_store/` via config file; upgraded query
  suite to `security-and-quality`; added `on.paths` filter on push (skip doc-only
  merges); removed `paths` filter from `pull_request` trigger so the status check
  is always posted (prevents branch-protection merge blocks); added
  `dependency-review` job for CVE scanning on PRs; annotated intentional
  `pickle.loads` and `ruamel.yaml` safe-mode loader with CodeQL justification
  comments. Manual step: enable "CodeQL / Analyze (Python)" as a required status
  check in GitHub branch protection settings.

- [x] **BK-139c — Dafny-compiled oracle as conformance gate**
  Compiled `MemoryBackend.dfy` to Python via `dafny translate py` (53 verified
  proofs, 0 errors) and wrapped it as `DafnyOracleBackend` in
  `tests/backends/dafny_oracle.py`. Runs through the full conformance suite
  (150 passed, 3 expected skips). Validates the conformance suite: if the
  mathematically verified oracle passes a test, the test is known-correct.
  Absorbs ID-133 (regenerated `MemoryBackend-py/module_.py` with `CapAtomicMove`,
  `AncestorsTraversableCheck`, `IsFileMethod`, `IsFolderMethod`, `GetFolderInfo`).
  Dafny spec updated: `EnsureParents` for implicit directory creation in
  Write/Move/Copy, `FolderInfo` enriched with `file_count`/`total_size` —
  adapter contains zero behavioral logic (pure type marshaling only).
  Deleted `sdd/formal/POC/` (handwritten oracle superseded by compiled oracle).
  Related: BK-139a, BK-139b, BK-140, ID-128.

- [x] **ID-133 — Regenerate `MemoryBackend-py/module_.py` after `CapAtomicMove` addition**
  Absorbed into BK-139c. Regenerated with Dafny v4.9.1; class-ordering fix
  applied (types/Backend moved before MemoryBackend). Related: ID-128.

- [x] **ID-128 — `Capability.ATOMIC_MOVE` enum member**
  Added `ATOMIC_MOVE` to the `Capability` enum. Declared by Local, Memory,
  SQLBlob; excluded from S3, S3-PyArrow, Azure, SFTP. Updated spec CAP-001
  (+ new CAP-007 quality-flag invariant), capabilities matrix, formal layer
  (BackendContract.dfy, MemoryBackend.dfy), and conformance tests.
  `MemoryBackend-py/module_.py` regenerated in BK-139c. Related: BE-018, BK-140.

## Bugs

- [x] **BUG-160 — PBT stateful model: `read_bytes` called on implicit directory**
  `BackendModel.read_bytes` did not skip paths that are implicit directories
  (created as side-effects of `write_new(path='d/0')`). Calling
  `backend.read_bytes('d')` on such a path raises `InvalidPath`, not `NotFound`,
  causing the `else` branch's `pytest.raises(NotFound)` to fail. Fixed by
  adding an early-return guard: `if path in _implicit_dirs(self.model): return`.
  Fixed in PR #386 (ID-128). See `tests/test_pbt_stateful.py`.

- [x] **BUG-159 — S3 `read()` leaks file handle if stream wrapping fails**
  Fixed via `_safe_wrap()` helper in `_stream.py`. Both `S3Backend.read()`
  and `S3PyArrowBackend.read()` now use `_safe_wrap()` to close raw handles
  if wrapping constructors raise. See BK-139a.

- [x] **BUG-158 — Sync `AzureBackend.read()` doesn't protect raw stream on wrapping failure** (v0.21.1)
  `_AzureBinaryIO` is now closed if `_ErrorMappingStream` or `BufferedReader`
  construction fails, matching the BUG-142 (SFTP) defensive pattern.

- [x] **BUG-157 — Sync `AzureBackend.delete_folder` non-HNS materializes all blobs** (v0.21.1)
  Existence check now uses `for ... break` to stop after the first blob
  instead of `list()` which eagerly fetched all pages.

- [x] **BUG-156 — Sync `AzureBackend.close()` doesn't close `DefaultAzureCredential`** (v0.21.1)
  `_resolve_credential()` now caches the credential in `_resolved_credential`.
  `close()` calls `credential.close()` if available, matching the async
  backend's `aclose()` pattern.

- [x] **BUG-155 — Azure `list_files` ignores `max_depth`** (v0.21.1)
  Both `AzureBackend.list_files` and `AsyncAzureBackend.list_files` now
  filter by depth when `recursive=True` and `max_depth` is specified,
  consistent with S3 (BUG-152) and Local backends.

- [x] **BUG-154 — `LocalBackend.write(overwrite=True)` leaks `IsADirectoryError` for directory paths** (v0.21.1)
  `write()`, `write_atomic()`, and `open_atomic()` now catch
  `IsADirectoryError` and raise `InvalidPath`, consistent with MemoryBackend.

- [x] **BUG-153 — `LocalBackend` leaks `IsADirectoryError` for directory paths** (v0.21.1)
  `read()`, `read_bytes()`, and `delete()` now catch `IsADirectoryError`
  and raise `NotFound`, consistent with MemoryBackend.
  `delete(missing_ok=True)` on a directory is silenced, matching
  MemoryBackend's behavior.

- [x] **BUG-149 — S3 `tls_ca_bundle` doesn't override `client_options` verify** (v0.21.1)
  Investigated and closed: `setdefault` behavior is spec-compliant per
  TLS-005 ("explicit `client_options.client_kwargs.verify` is NOT
  overridden"). Existing test confirms. Not a defect.

- [x] **BUG-152 — S3 `list_files` ignores `max_depth`** (v0.21.1)
  `_S3Base.list_files` now tracks depth in BFS traversal and prunes
  directories beyond `max_depth`, consistent with all other backends.

- [x] **BUG-151 — S3PyArrow `_extract_etag` scope too broad** (v0.21.1)
  `_extract_etag` override now only affects listing paths; `get_file_info`
  extracts ETag from the HeadObject response via `_head_to_fileinfo`.

- [x] **BUG-150 — S3PyArrow `get_file_info` returns no ETag and no digest** (v0.21.1)
  `get_file_info` now uses `call_s3("head_object", ChecksumMode="ENABLED")`
  like `S3Backend`, returning both ETag and digest when available.

- [x] **BUG-148 — S3 `client_options` shallow copy mutates caller's nested dicts** (v0.21.1)
  Lazy filesystem init now uses `copy.deepcopy(client_options)` instead
  of `dict(client_options)`. Both `S3Backend` and `S3PyArrowBackend`.

- [x] **BUG-147 — SFTP `delete_folder` masks `listdir` permission errors** (v0.21.1)
  Non-recursive `delete_folder` now re-raises non-ENOENT errors from
  `listdir` instead of silently treating them as empty.

- [x] **BUG-146 — SFTP listing methods silently swallow non-ENOENT errors** (v0.21.1)
  `list_files`, `list_folders`, and `iter_children` now only suppress ENOENT
  from `listdir_attr`; other errors propagate as `RemoteStoreError`.

- [x] **BUG-145 — SFTP `_ensure_parent_dirs` swallows permission errors** (v0.21.1)
  Parent directory creation now only catches ENOENT on `stat` and EEXIST
  on `mkdir`; other errors propagate.

- [x] **BUG-144 — SFTP SSH client leaked on connection failure** (v0.21.1)
  `_connect()` now closes the `SSHClient` if the retry-wrapped connect
  exhausts attempts.

- [x] **BUG-143 — SFTP `st_mode` None causes TypeError in listing/traversal** (v0.21.1)
  Entries with `st_mode is None` are now skipped in listing, traversal,
  and stats methods.

- [x] **BUG-142 — SFTP `read()` leaks file handle if stream wrapping fails** (v0.21.1)
  The paramiko file handle is now closed if `_ErrorMappingStream` or
  `BufferedReader` construction raises.

- [x] **BUG-141 — partition_path allows `=` in key, round-trip fails** (v0.21.1)
  Added `=` validation for partition keys (matching existing value
  validation). Updated PART-006 spec.
  Audit: [008 B-5](audits/audit-008-package-bugs.md#b-5)

- [x] **BUG-140 — RegistryConfig.from_dict converts null fields to string "None"** (v0.21.1)
  `type` and `backend` now validated as strings with `TypeError` on null.
  `root_path` null treated as empty string (same as omitted).
  Audit: [008 B-4](audits/audit-008-package-bugs.md#b-4)

- [x] **BUG-139 — RegistryConfig.from_dict crashes on null options** (v0.21.1)
  Changed `cfg.get("options", {})` to `cfg.get("options") or {}` so null
  values are treated as empty dict instead of crashing.
  Audit: [008 B-3](audits/audit-008-package-bugs.md#b-3)

- [x] **BUG-138 — CachedStore.child() creates isolated cache** (v0.21.1)
  `_wrap_child()` now passes the parent's `CacheBackend` instance to the
  child instead of `None`, so child and parent share one cache. A `_prefix`
  tracks the child's path namespace so mutations through the child also
  invalidate the corresponding fully-qualified keys in the shared cache.
  Audit: [008 B-2](audits/audit-008-package-bugs.md#b-2)

- [x] **BUG-137 — CachedStore write doesn't invalidate parent directory metadata** (v0.21.1)
  New `_delete_path_and_ancestors` helper invalidates cached
  `exists`/`is_file`/`is_folder` entries for every ancestor directory of
  the mutated path, not just the leaf. Called from `_invalidate_path`.
  Audit: [008 B-1](audits/audit-008-package-bugs.md#b-1)

## Specification & API Contract

- [x] **ID-129 — Spec gap: query methods under path-type conflicts**
  Codified behavior for `exists()`, `is_file()`, `is_folder()` when paths
  contain file-as-directory-component ancestors (e.g., querying `a/b/c` when
  `a/b` is a file). All backends return `False` — accidental consensus now
  made explicit and formally verified.
  - **Phase 1:** BE-004, BE-005, BE-021 spec amendments
  - **Phase 2:** Dafny formal methods `IsFileMethod()`, `IsFolderMethod()` with
    `AllAncestorsTraversable` predicate; reference refinement in `MemoryBackend.dfy`
  - **Phase 3:** Extended conformance tests (5 test methods, all backends) in
    `test_conformance_extended.py` marked with `@pytest.mark.extended_conformance`
  - **Phase 4:** CHANGELOG entry and documentation updates
  Related: BK-140, BE-004, BE-005, BE-021, ID-130 (Dafny coverage).

- [x] **ID-130 — Dafny formal coverage for `get_folder_info()` (BE-017)**
  Added `GetFolderInfo` method to `BackendContract.dfy` with postconditions
  `IsFile → InvalidPath`, `!PathExists → NotFound`, `IsDir → Ok`. Verified
  in `MemoryBackend.dfy` reference refinement. Symmetric with `GetFileInfo`.
  Related: BE-017, BK-140, ID-129.

## Backlog

- [x] **BK-141 — `ext.arrow` suppresses `CapabilityNotSupported` during Tier 1 probe** (RESOLVED via Option A + B)
  Codified the Tier 1 probe as an explicit "capability-probe" exception pattern
  in ADR-0008 § "Capability-probe exception pattern" (Option A). Updated
  `StoreFileSystemHandler.__init__` to narrow exception catch from `Exception`
  to `(CapabilityNotSupported, TypeError, OSError)` with explicit documentation
  referencing ADR-0008 (Option B). OSError catches cloud backend initialization
  failures (e.g., S3 endpoint unreachable during lazy PyArrow client init). The
  pattern is now ADR-endorsed for optional feature detection during extension
  initialization, with explicit exception scope. Spec PA-001 updated to match
  narrowed-catch behavior: expected failures suppressed, unexpected exceptions
  propagate. Related: ADR-0008, sdd/specs/014-pyarrow-filesystem-adapter.md,
  BK-139b (BLE annotations), ID-132 (self-review).

- [x] **BK-140 — Dafny formal verification layer for backend contract**
  Machine-checkable specification encoding all six BK-140 gaps:
  BE-008 (precondition ordering), BE-021 (error mapping), BE-014/015
  (listing semantics), DEPTH-001 (depth counting), BE-018 (move
  atomicity), SIO-001 (resource safety).  Includes MemoryBackend
  reference refinement (87 verified, 0 errors), CI gate, and
  DepthCounting + ResourceSafety standalone proofs.
  Spec `.md` amendments completed as BK-140a (see below).

- [x] **BK-140a — Tighten backend behavioral contract (spec amendments)**
  Six spec amendments to close behavioral gaps identified in
  [research-backend-contract-completeness.md](research/research-backend-contract-completeness.md),
  validated against the Dafny formal model in `sdd/formal/`:
  1. BE-008: precondition evaluation order (path validity → type conflict → overwrite) + flat-namespace exemption
  2. BE-021: canonical error mapping table + broad-handler rule
  3. BE-014/BE-015: listing on missing paths MUST yield nothing, not raise `NotFound`
  4. DEPTH-001: reference depth algorithm (`RemotePath.parts` counting, inclusive `<=`)
  5. BE-018/BE-019: move and copy atomicity notes (backend-dependent, MUST NOT swallow errors)
  6. SIO-001: acquire-then-wrap safety invariant

- [x] **BK-139b — Bug prevention: BLE rules, extended conformance, ResourceWarning (deliverables 4, 5, 7)**
  From [research-bug-prevention-beyond-testing.md](research/research-bug-prevention-beyond-testing.md):
  4. Enabled ruff `BLE` rule set — 44 intentional broad catches annotated
  5. Extended conformance suite — 42 test functions derived from Dafny
     postconditions (`@pytest.mark.extended_conformance`)
  7. `ResourceWarning` safety net — `__del__` on SFTP, Azure, AsyncAzure
  Item 6 (`check_error_handling.py` AST script) deferred; see BK-139b
  remainder in BACKLOG.md.

- [x] **BK-139a — Bug prevention: `_safe_wrap` + PBT (deliverables 1–3)**
  From [research-bug-prevention-beyond-testing.md](research/research-bug-prevention-beyond-testing.md):
  1. `_safe_wrap()` helper in `_stream.py` + fix BUG-159 S3 `read()` leak
  2. Hypothesis P4 — stateful backend model via `RuleBasedStateMachine`
  3. Hypothesis P1–P3 — partition, config, path roundtrip properties
  Remaining items 4–7 tracked as BK-139b.

## Documentation & Developer Experience

- [x] **ID-132 — Custom backend guide: conformance suite integration and flat-namespace docs**
  Expanded `guides/custom-backend-guide.md` § "Testing your backend" to connect
  external authors to the real conformance infrastructure:
  1. Conformance suite overview table (`test_conformance.py` BE-001–BE-025 + ancillary
     specs, `test_conformance_extended.py` 50 Dafny-derived tests) with GitHub links.
  2. Step-by-step fixture registration guide for contributing backends
     (`conftest.py` availability guard → `pytest.param` → fixture `elif` branch).
  3. `_require()` / capability-gating explanation with example — skip-not-fail
     semantics for partial-capability backends.
  4. Flat-namespace vs. hierarchical distinction: definition, `_FLAT_NAMESPACE_BACKENDS`
     set, behavioral differences table, when to add your backend name to the set.
  5. Conformance checklist (basic, extended, error mapping, repr safety).
  6. Standalone testing section retained with categories aligned to conformance suite.
  Related: BK-139b, BK-139c, CONTRIBUTING.md § Adding a New Backend.

- [x] **BK-137 — Post-v0.20.0 test quality: TESTING.md compliance + coverage gaps** (v0.21.0)
  Audited new async/dagster test files against `sdd/TESTING.md` rules.
  Fixed Rule 2 (sole `isinstance` → behavioral assertions) and Rule 7
  (copy-paste → parametrize) violations. Coverage improved for
  `_azure_common` (69→100%), `_async_azure` (89→95%),
  `_sync_adapter` (93→98%), `_async_store` (96→98%).

- [x] **BK-136 — Feature discoverability for agents and humans** (v0.21.0)
  Implemented all three recommendations from
  [research](research/research-feature-discoverability.md):
  R-1: `FEATURES.md` at repo root — versioned snapshot of backends,
  extensions, capabilities, and install extras.
  R-2: `remote_store.info()` public function with `InfoResult` TypedDict —
  runtime introspection of available backends and extensions.
  R-3: Reference `FEATURES.md` in `CLAUDE.md` for agent cold-start discovery.
  Updated release checklist, API docs nav, and `__init__.py` exports.

---

## Bug Fixes

- [x] **BUG-136 — `config_loaders.py` example crashes on Windows** (v0.21.1)
  `Path` interpolation into TOML/YAML strings produced backslashes
  (`C:\Users\...`) which are invalid escape sequences in TOML.
  Fixed with `.as_posix()`. Extracted `demo()` function and added
  test in `test_examples.py`.

- [x] **BUG-135 — `ParquetSerializer.deserialize()` returns Arrow Table** (v0.21.0)
  `deserialize()` called `table.to_pandas()`, hard-requiring pandas for
  `remote-store[dagster,arrow]` users. Changed to return `pyarrow.Table`
  directly. Callers convert to pandas/polars as needed. Updated spec DAG-004,
  migration guide, medallion example.

## Integrations

- [x] **ID-013 — Async Store / Backend API (Phase 1 + Phase 2)** (v0.21.0)
  Phase 1: `remote_store.aio` module with `AsyncStore`, `AsyncBackend`,
  `SyncBackendAdapter`, `AsyncMemoryBackend`. Phase 2: `AsyncAzureBackend` --
  first native async backend using Azure SDK async clients
  (`azure.storage.blob.aio`, `azure.storage.filedatalake.aio`). Shared helpers
  in `_azure_common.py` for sync/async code reuse.
  Remainder: Phase 3 (async extensions) tracked as ID-013b in BACKLOG.md.

- [x] **ID-124 — Dagster multi-partition loading** (v0.21.0)
  When `load_input` receives multiple partition keys (time-window aggregation),
  return `dict[str, Any]` mapping partition key to deserialized object.
  Both `_RemoteStoreIOManagerImpl` and `_DatasetIOManagerImpl` updated.
  Spec DAG-020, tests, guide update. Deferred from ID-083 scope.

- [x] **ID-083 — Dagster extension v2: ConfigurableResource + IOManagerFactory** (v0.20.0)
  `DagsterStoreResource` (`ConfigurableResource`) for direct Store access in
  assets, `RemoteStoreIOManager` (`ConfigurableIOManagerFactory`) for
  config-driven IO management with automatic lifecycle. Dataset mode via
  `dagster_dataset_io_manager()` or `serializer="parquet-dataset"`. Spec 031
  (DAG-012 -- DAG-019), tests, guide update, example script. Deferred:
  multi-partition loading (ID-124), showcase update (ID-125).

## Cleanup

- [x] **BK-138 — Deduplicate `pyproject.toml` dependency lists** (v0.21.1)
  Hatch env uses `features` key instead of re-listing 43 packages.
  `dev`, `docs`, and `bench` extras compose from user-facing extras via
  self-referential dependencies. Removed cargo-culted `s3fs` from `docs`.

- [x] **BK-135 — Fix 72 ResourceWarning in SQL backend tests** (v0.21.0)
  Added `close()` / `dispose()` teardown to `test_backend_sqlquery.py` fixtures
  and inline backends. Filtered residual SQLAlchemy pool ResourceWarning on
  Python 3.13+ via pytest `filterwarnings`.
- [x] **BK-134 — Fix test behavior assertion anti-patterns** (v0.21.0)
  Replaced `isinstance`-only assertions (12 tests) with behavioral checks and
  replaced ~15 private attribute assertions with public API equivalents across
  10 test files. ~60 remaining private attribute assertions are legitimate
  (config storage, internal helper testing, mock introspection).
- [x] **BK-133 — Upgrade GitHub Actions Node.js 20 → 24** (v0.21.0)
  Audited all workflows. Core actions (`checkout@v6`, `setup-python@v6`,
  `codeql-action@v4`) already use Node.js 24. Upgraded `setup-uv` from
  `@v7` to `@v8.0.0` (immutable tags). Disabled uv caching on lightweight
  CI jobs (lint, typecheck, notebooks, examples, docs, package) to
  eliminate cache-contention warnings. Remaining Node.js 20 warning comes
  from GitHub's built-in `pages-build-deployment` (not user-configurable).

- [x] **BK-131 — Fix mutation testing scripts (pytest-gremlins)** (v0.20.0)
  `hatch run mutate` was broken: passed source dir as positional arg instead
  of `--gremlin-targets`. Replaced with 6 scoped scripts (`mutate-core-api`,
  `mutate-core-infra`, `mutate-ext-proxy`, `mutate-ext-format`,
  `mutate-backends-local`, `mutate-backends-cloud`) using comma-separated
  `--gremlin-targets` and matching test files. Scoping avoids Windows
  `WinError 206` (command-line length limit). Added `[tool.pytest-gremlins]`
  config with incremental caching. Updated CLAUDE.md dev commands.

- [x] **BK-130 — Remove deprecated function aliases (pre-v1 cleanup)** (v0.20.0)
  Removed `cached_store()`, `remote_store_io_manager()`,
  `pydantic_to_registry_config()`, `_deprecated_alias()` helper, and
  `ext.glob` private re-exports. Updated migration guide, tests, and
  `__init__.py`. Pre-v1: no deprecation shim needed.

## Documentation

- [x] **BK-129 — Address docs list completeness findings from audit-006** (v0.20.0)
  Follow-up to [audit-006](audits/audit-006-docs-list-completeness.md)
  (2026-03-30). All 20 findings fixed: SQL backends added to all backend
  lists/tables (A), ghost "Seekable read" removed from extension lists (B),
  missing extensions added to architecture.md (C), `read_seekable()` directive
  added to Store API reference (D), SQL extras added to README install (E).

## Performance & Memory

- [x] **BK-127 — Audit-005 low-priority polish (L-1, L-2, L-3)** (v0.20.0)
  Remainder of BK-123. `size()` uses `sum()` generator (L-1), concurrent
  batch `list()` materialisation documented (L-2), sqlalchemy module-level
  import rationale commented (L-3).

- [x] **BK-123 — Address laziness & memory findings from audit-005** (v0.20.0)
  Follow-up to [audit-005](audits/audit-005-laziness-memory.md) (2026-03-28).
  Shipped High + Medium findings (H-1, H-2, M-1..M-6). S3 paginated
  listing, MemoryBackend snapshot-under-lock, cache `max_listing_size`
  guard, pre-flight size check, chunked write. PR #314.
  Low-priority remainder tracked as BK-127.

## API Surface

- [x] **ID-131 — Fix `InvalidPath` type-mismatch conditions across backends**
  Fixed `read()`, `read_bytes()`, `delete()`, `get_file_info()`, `get_folder_info()`,
  `delete_folder()` to raise `InvalidPath` (not `NotFound`) when the path names
  the wrong type (directory vs file) in LocalBackend, MemoryBackend, and
  SFTPBackend. Added directory type checks to `move()`/`copy()` source and
  destination in LocalBackend, MemoryBackend, and SFTPBackend. Self-move/self-copy
  (`src == dst`) now no-op in Local, Memory, S3, S3-PyArrow, and SFTP backends.
  Tightened 9 weakened conformance tests from `RemoteStoreError` to `InvalidPath`.
  Related: BK-140a, BE-021, BK-139b.

- [x] **ID-126 — `resolve_env()` — env-var interpolation for config loaders** (v0.21.0)
  `resolve_env(data)` resolves `${VAR}` and `${VAR:-default}` placeholders in
  config dicts. Opt-in `resolve_env_vars=True` on `from_yaml()` and
  `from_toml()`. Standalone function exported from `remote_store` for custom
  loaders. Spec: CFG-018..CFG-021.

- [x] **ID-122 — Parquet Dataset Storage extension (`ext.parquet`)** (v0.20.0)
  `ParquetDatasetStore` — high-level Parquet dataset read/write with manifest
  metadata, `_SUCCESS` completion markers, and atomic-commit semantics.
  Single-file and multi-part layouts, column projection, overwrite semantics.
  New errors: `DatasetIncomplete`, `ManifestCorrupted`.
  [Spec 042](specs/042-ext-parquet.md),
  [RFC-0008](rfcs/rfc-0008-parquet-dataset-storage.md).

- [x] **ID-120 — `resolve()` → `ResolutionPlan` introspection API** (v0.20.0)
  `Store.resolve(key)` returns a frozen `ResolutionPlan` dataclass describing
  how a key maps to its storage location. Available on all 9 backends with no
  I/O. `details` wrapped in `MappingProxyType` for immutability. Security:
  no credentials in details, userinfo stripped from URLs.
  [Spec 043](specs/043-resolution-plan.md),
  [Research](research/research-resolve-spec-proposal.md).
  Phase 2 (cache key derivation) and Phase 3 (CompositeStore) deferred.

## New Backends

- [x] **ID-119 — SQLAlchemy backends** (v0.20.0)
  Two concrete backends sharing `_SQLAlchemyBaseBackend`:
  - `SQLBlobBackend` (v1) — KV blob store, full read-write. PR #292.
  - `SQLQueryBackend` (v2) — read-only query materializer, explicit query
    mappings via `ResultSerializer` protocol. Spec 041.
  - [Research](research/research-sqlalchemy-backend.md)
  - Future: view/convention discovery (`strict=False`), ADBC fast path (v3).

## Process

- [x] **BK-126 — CI assertion/mock checks + existing test migration** (v0.20.0)
  CI enforcement of Testing Rules 1 and 4: AST-based assertion checker
  (`scripts/check_test_assertions.py`) and MagicMock spec checker
  (`scripts/check_mock_spec.py`) wired into CI lint job. Migration: added
  `spec=` to all 67 unconstrained `MagicMock()` calls, added meaningful
  assertions to 87 test functions. Added `pytest-gremlins>=1.5` for mutation
  testing (diagnostic, no CI threshold yet). Hatch scripts:
  `check-test-quality`, `mutate`, `mutate-report`, `test-cov-branch`
  (branch coverage diagnostic). Remainder of BK-124b.

- [x] **BK-128 — Orchestrate skill v2: iterative convergence model** (v0.20.0)
  Redesign `/orchestrate` from single-pass parallel to iterative convergence.
  Three complexity modes (Simple, Standard, Complex). Plan refinement with
  experts (1 round), consolidation step, review loop (max 2 rounds), user as
  tie-breaker. ADR-0020 supersedes ADR-0019. Based on BK-123 learnings.

- [x] **BK-125 — Multi-agent orchestration for complex tasks** (v0.20.0)
  `/orchestrate` skill: orchestrator + 4 domain experts (Store & Backend,
  Extension, Testing, Documentation) via Claude Code Agent tool. Parallel
  execution, two modes (implementation + review). ADR-0019 documents
  architecture. [RFC](rfcs/rfc-0009-multi-agent-orchestration.md).

- [x] **BK-124b — Enable Ruff PT rules (partial)** (v0.20.0)
  Enabled Ruff `PT` rules (`flake8-pytest-style`) in `pyproject.toml` with
  `raises-require-match-for` config. Auto-fixed 152 violations (PT006, PT001,
  PT022). Added `match=` to 13 `pytest.raises` calls (PT011). Suppressed 9
  intentional PT012 violations (open_atomic exception tests).
  Remainder: [BK-126](BACKLOG.md) (CI assertion/mock checks, existing
  test migration).

- [x] **BK-124a — Codify testing rules in `sdd/TESTING.md`** (v0.20.0)
  8 testing quality rules extracted from
  [research-testing-best-practices](research/research-testing-best-practices.md)
  and formalized as an authoritative process doc. Enforcement tags
  (`[CI-enforced]` / `[review-enforced]`), good-vs-bad examples, and
  Testing Expert quick reference table for BK-125. Cross-referenced from
  DESIGN.md § 11 and CLAUDE-REFERENCE.md.

- [x] **BK-016 — Eliminate avoidable `# type: ignore` comments in src/** (v0.20.0)
  Replaced 9 `no-any-return` suppressions with `cast()` in `ext/cache.py` (6)
  and `_stream.py` (3). `_path.py:21` `misc` kept — mypy does not support
  `Final` on `__slots__` descriptors.

- [x] **BK-015 — Replace mypy `ignore_missing_imports` overrides with proper type stubs** (v0.20.0)
  Added `types-requests` stub, removed overrides for `requests`, `urllib3`,
  `pydantic`, `pydantic_settings`, `tomli`, `tomllib`, `httpx`, `ruamel.yaml`.
  Cleaned up now-unnecessary `type: ignore` comments in HTTP transport modules.
  Keep: `dagster` (no `py.typed`, no stubs). PR #293.

- [x] **BK-001 — Audit workflow and bug-fix protocol** (v0.20.0)
  Added `/audit` skill (scope-first, report-only), bug-fix protocol
  (backlog → changelog → failing test → fix), ripple-check row,
  process rule. PR #288.

## Bug Fixes

- [x] **BUG-005 — SFTP TOFU host key not persisted when known_hosts absent** (v0.20.0)
  `TRUST_ON_FIRST_USE` now persists accepted host keys to disk on disconnect.
  Creates the known_hosts file and parent directories if absent. Inline keys
  (code/config/env) are never persisted. Spec SFTP-028.

- [x] **BUG-006 — Cache coherency in move/copy operations** (v0.20.0)
  `CachedStore.move()` and `CachedStore.copy()` now clear the entire cache
  to prevent stale cached entries for nested paths that are relocated or
  overwritten. Previously only invalidated source/destination paths, missing
  nested paths (e.g., `dst/file.txt`). Now consistent with `delete_folder()`
  safety strategy. Spec CACHE-010 updated.

## Benchmarks & Performance

- [x] **ID-104 — S3-PyArrow comparison chart, overhead-vs-RTT, benchmark tooling** (v0.20.0)
  S3-PyArrow in comparative charts/reports with boto3 baseline. New S3 vs
  S3-PyArrow comparison chart. Overhead-vs-RTT chart with real multi-profile
  data. Performance messaging rewrite (numbers, not judgment). `--file` flag
  for `report.py` and `charts.py`. Raw SDK targets for latency backends.
  Network profile metadata in saved JSON. `bench-latency-matrix` command.
  - [x] Performance messaging rewrite (PR #273)
  - [x] Charts, `--file` flag, latency raw SDK targets (PR #274, 4 review rounds)
  - [x] Regenerated SVGs + updated text with run 0022 numbers (PR #275)
  - [x] Fix S3-PyArrow messaging: analytical workloads, not
    high-throughput (PR #276)

- [x] **ID-103 — Benchmark suite v2: user-decision framing** (v0.20.0)
  Expand Toxiproxy to all Docker backends, generate overhead charts,
  reframe performance guide for user decisions, add README performance
  section.
  - [x] [Research](research/research-benchmark-suite-v2.md) (PR #263)
  - [x] Phase 1: Toxiproxy expansion (docker-compose, fixtures, profiles) (PR #267)
  - [x] Phase 2: Chart generation + "worth it?" verdicts in reporting (PR #268)
  - [x] Phase 3: README section + performance guide reframe (PR #268)
  - [x] Phase 4: seekable_read() + cache hit/miss benchmarks (PR #270)

---

## Docs & DX

- [x] **ID-117 — S3Backend endpoint URL normalization** (v0.20.0)
  `S3Backend` and `S3PyArrowBackend` accept bare `host:port` for
  `endpoint_url` and auto-prefix with `https://`. Shared
  `_normalize_endpoint_url()` helper in `_s3_base.py`.
  Spec S3-025 / S3PA-023.

- [x] **ID-113 — Documentation: S3 listing strategies and performance** (v0.20.0)
  Comprehensive guide added to `guides/backends/s3.md` explaining shallow vs.
  recursive listing trade-offs, why flat `ListObjectsV2` streams beat
  delimiter-based folder iteration, and why parallelization is wrong for large
  buckets. Includes performance data from benchmark suite and practical examples.
  New example file `examples/backends/s3_listing_strategies.py` demonstrates shallow,
  recursive, and filtered listing patterns.

- [x] **BUG-004 — Snippet indentation leaks into docs code blocks** (v0.20.0)
  pymdownx.snippets extracts named regions verbatim; regions inside
  function bodies carry 4–8 spaces of indentation into rendered docs.
  Fix: enable `dedent_subsections: true` in pymdownx.snippets config.
  Affects `homepage.py` (4 regions) and `core_operations.py` (3 regions).

---

## Streaming & I/O

- [x] **ID-102 — Azure PyArrow column pruning via seekable range reads** (v0.20.0)
  `Store.read_seekable()` + `_AzureRangeReader` (HTTP Range per `readinto()`)
  enables Parquet column pruning on Azure without full-file download. 2–17x
  speedup for selective reads on 10 MB+ files. Arrow adapter Tier 3 uses
  `read_seekable()` for files above the materialization threshold.
  - [x] [Research](research/research-azure-pyarrow-optimization.md) (PR #260)
  - [x] Phase 1: `_AzureRangeReader`, `Store.read_seekable()`, spec 036,
    ADR-0017, arrow integration (PR #262)
  - [x] Phase 2: Benchmarks — column pruning, batch reads, dataset scans.
    `PythonFile` overhead acceptable. Phases 3–4 not needed.
    ([Verdict](research/research-azure-pyarrow-optimization.md#9-phase-2-verdict-real-workload-benchmarks))
  - Deferred: C++ Tier 1 via `pyarrow.fs.AzureFileSystem` — see
    [ID-105](BACKLOG.md#integrations).

- [x] **ID-100 — Seekable read capability + extension** (v0.20.0)
  `Capability.SEEKABLE_READ` flag for backends that always return seekable
  streams (Local, Memory, S3, S3-PyArrow, SFTP). `ext.seekable.seekable_read()`
  portable wrapper with `SpooledTemporaryFile` fallback for non-seekable
  backends (Azure, HTTP). ADR-0016, spec 036.

---

## API Surface

- [x] **ID-118 — Certificate bundle handling (S3, Phase 1)** (v0.20.0)
  Dedicated `tls_ca_bundle: str | None` parameter on `S3Backend` and
  `S3PyArrowBackend`. Env var fallback chain (`AWS_CA_BUNDLE` >
  `REQUESTS_CA_BUNDLE` > `SSL_CERT_FILE`), early path validation,
  `setdefault` injection for backward compat. Spec 039.
  Phase 2 (Azure) deferred as ID-118b.

- [x] **ID-112 — Non-recursive `get_folder_info` optimization** (v0.20.0)
  Added `max_depth` parameter to `Store.get_folder_info()`. When set,
  aggregates stats using `list_files(max_depth=N)` at the Store level
  instead of the backend's full recursive traversal. `CachedStore` and
  `ObservedStore` forward the parameter. No Backend ABC change. Spec 038.

- [x] **ID-107b — `Backend.list_files(max_depth=N)` native optimization** (v0.20.0)
  Added optional `max_depth` kwarg to `Backend.list_files()` ABC. Native depth
  limiting in Local (`os.walk()` depth counter), SFTP (recursive call depth
  tracking), Memory (DFS stack depth). S3/Azure/HTTP accept the parameter but
  rely on Store-level client-side filter. Store passes `max_depth` through to
  backend; client-side filter remains as safety net. Spec 037 (DEPTH-003).

- [x] **ID-107 — `Store.list_files(max_depth=N)` with client-side filtering** (v0.20.0)
  Added `max_depth` parameter to `Store.list_files()`. When set, `recursive`
  is ignored. Client-side depth filtering at Store level via path component
  count. No Backend ABC change. Spec 037 (DEPTH-001).

- [x] **ID-108 — `Store.list_folders(max_depth=N)` with BFS traversal** (v0.20.0)
  Added `max_depth` parameter to `Store.list_folders()`. BFS using
  `Backend.list_folders()` at each level. `max_depth=None`/`0` returns
  immediate children (unchanged default). No Backend ABC change.
  Spec 037 (DEPTH-002).

- [x] **ID-101 — Add ProxyStore to API reference** (v0.20.0)
  Exported `ProxyStore` from `remote_store`, added API reference page
  (`docs-src/api/proxy.md`), rewrote docstrings for extension authors.
  ProxyStore remains an internal delegation base by design (ADR-0014)
  but is documented because it is visible in the inheritance chain and
  useful for custom extensions. PR #258.

---

## SDD Housekeeping

- [x] **ID-099 — Consolidate SDD document categories from 7 to 5**
  Merged `proposals/` → `rfcs/` (renamed to rfc-0005, rfc-0006, rfc-0007 with
  accepted status), `plans/` → `research/` (docs landing page plan renamed;
  HTTP backend plan merged into existing research doc § 20). Removed completed
  fix-list (`audits/fix-docs-structural-issues.md`). Added Document Types table
  to `000-process.md`. Updated all cross-references in BACKLOG-DONE.md,
  CLAUDE-REFERENCE.md, DOCUMENTATION.md. PR #252.

---

## Test Suite Refactoring

- [x] **BK-014 — Test code deduplication and parametrization**
  Aggressive refactoring of the test suite (~17,800 → ~16,300 lines, −8.6%)
  while maintaining identical coverage (1866 passed, 170 skipped).
  Applied across 30 of 40 test files.
  - Parametrized similar tests (error mapping, validation, operation variants)
  - Extracted shared fixtures and factory helpers (`_make_backend`, etc.)
  - Merged single-method test classes into parent classes
  - Consolidated repeated assertion patterns
  - Addressed audit M-13: reviewed `test_coverage_gaps.py` for pure-import assertions
  Key files with largest reductions: `test_config.py` (−26%), `test_batch.py` (−24%),
  `test_cache.py` (−23%), `test_coverage_gaps.py` (−23%), `test_examples.py` (−15%),
  `test_s3.py` (−14%), `test_arrow.py` (−12%).

---

## Documentation Tooling

- [x] **ID-106 — "Build Your Own Backend" guide**
  Step-by-step tutorial showing how to implement the Backend protocol, using
  a Redis backend as the running example. Covers capabilities, error mapping,
  listing, metadata, registry integration, and extension compatibility.
  Tested snippet file with 17 named regions. API ref links throughout.
  Cross-link from CONTRIBUTING.md.
  - [x] Guide, snippets, docs wiring (PR #277)

- [x] **ID-057 — Tested code snippets in docs (single-source snippets)**
  Created `examples/snippets/` with named regions using pymdownx.snippets'
  `# --8<-- [start:name]` / `# --8<-- [end:name]` syntax. Two snippet files
  (`homepage.py`, `core_operations.py`) replace hand-written fences in
  `docs-src/index.md`. Snippet scripts run as part of `hatch run examples`;
  `tests/test_snippets.py` verifies they execute. CI guarantees docs code
  blocks stay in sync with the actual API. Note: the S3Backend
  "backend-switching" example on the homepage remains inline because
  `S3Backend` cannot be instantiated without real credentials; this block
  is not CI-tested by design.
  [Research](research/research-example-testing.md).

- [x] **ID-058 — Auto-generate example docs wrappers via mkdocs-gen-files**
  Extended `scripts/gen_pages.py` to scan `examples/*.py` and
  `examples/backends/*.py`, extract module docstrings, and generate
  `docs-src/examples/<slug>.md` wrappers + `index.md` + nav entries
  automatically. Deleted 28 hand-maintained wrapper files and the static
  `_nav.yml`. Medallion showcase handled as special case (README inlined).
  Added `tests/test_api_coverage.py` CI check verifying every `__all__`
  symbol has a `:::` directive in `docs-src/api/` and every core symbol
  appears in `docs-src/api/index.md`.

---

## Documentation Cross-Linking

- [x] **BK-013 — Documentation cross-link compliance**
  Enforced DOCUMENTATION.md § 4 cross-linking rules across all ~64 docs pages.
  All additive, no code changes.
  [RFC](rfcs/rfc-0007-doc-cross-links.md).
  - Phase 1a: Core example pages — add `## See also` (10 pages)
  - Phase 1b: Backend example pages — add `## See also` (6 pages)
  - Phase 1c: Extension + showcase example pages — add `## See also` (11 pages)
  - Phase 2a: Core + extension API ref pages — add `## See also` (23 pages)
  - Phase 2b: Backend API ref pages — convert to `## See also` (7 pages)
  - Phase 3: Link plain-text names in table headers/key columns (6 files)
  - Phase 4: Add Rule 4 to DOCUMENTATION.md § 4

---

## Naming & Consistency

- [x] **BK-012 — Code deduplication Phases 2--4**
  `_StreamWrapper` base class in `ext/streams.py` (eliminates 56 lines of
  repeated context-manager/close/getattr boilerplate).  Generic `_run_batch()`
  executor in `ext/batch.py` (consolidates sequential/concurrent scaffolding).
  `_deprecated_alias()` helper in `ext/_helpers.py` (replaces 3 hand-written
  deprecation wrappers).  `_require_extra()` dropped — ruff E402 cascade made
  it impractical.  [RFC](rfcs/rfc-0005-code-deduplication.md).  PR #243.

- [x] **BK-011 — S3 backend deduplication (Phase 1)**
  Extract shared listing, error handling, and FileInfo construction from
  `_s3.py` and `_s3_pyarrow.py` into `_S3Base` base class
  (`backends/_s3_base.py`).  Add FileInfo helpers (`backends/_fileinfo.py`)
  and error factories (`_not_found`, `_permission_denied`,
  `_classify_by_message` in `_errors.py`).  Net -94 lines, single
  maintenance point for 155 previously duplicated lines.
  [RFC](rfcs/rfc-0005-code-deduplication.md).  PR #242.

- [x] **BK-010 — Naming consistency: rename ext factory functions**
  Renamed three public factory functions for naming consistency:
  `pydantic_to_registry_config` → `from_pydantic`, `remote_store_io_manager` →
  `dagster_io_manager`, `cached_store` → `cache`. Old names kept as deprecated
  aliases emitting `DeprecationWarning`. All specs, guides, examples, migration
  guide updated. [RFC](rfcs/rfc-0006-naming-inconsistencies.md). PR #241.

## Middleware Path 1 (Post-v0.17.0)

- [x] **ID-090 — Docs landing page (replace README include)**
  Replaced the `README.md` include with a purpose-built landing page:
  architecture diagram, six key messages (Store-as-folder, zero deps, proven
  libs, backend-native API, extensions alongside, bring your own), quick start,
  and navigation links. Diagram rework (flowchart → architecture-beta) deferred.
  [Research](research/research-docs-landing-page.md).

- [x] **ID-006 — Progress tracking via stream wrappers (`ext.streams`)**
  `ext.transfer.download()` now uses `ProgressReader` wrapper for progress
  tracking, consistent with `upload()` and `transfer()`. Replaces inline
  callback. Spec 017 §XFER-009, Spec 033.

- [x] **ID-098 — S3 backend: populate `FileInfo.digest` from `x-amz-checksum-*`**
  `get_file_info` now calls `HeadObject` with `ChecksumMode: ENABLED`
  unconditionally, returning both metadata and any checksum headers in a single
  request. The base64-encoded checksum is decoded to hex and wrapped in a
  `ContentDigest`. Listing paths (`list_files`, `iter_children`) still return
  `digest=None` to avoid per-file overhead. Spec 008 §S3-024.

- [x] **ID-097 — Azure backend: populate `FileInfo.etag` and `digest`**
  `_props_to_fileinfo` now populates `etag` from `BlobProperties.etag`
  (stripped/lowercased) and `digest` from `content_settings.content_md5`
  when present (bytes → lowercase hex → `ContentDigest("md5", value)`).
  Spec 012 §AZ-034.

- [x] **ID-096 — S3 backend: populate `FileInfo.etag`** (partial; see ID-098 for digest)
  `_info_to_fileinfo` now populates `etag` from the `ETag` key in the s3fs
  info dict (stripped/lowercased). Digest via `x-amz-checksum-*` is deferred
  — it requires `ChecksumMode: ENABLED` on HeadObject, which s3fs does not
  issue by default. Spec 008 §S3-023.

- [x] **ID-095 — `ContentDigest` model + `FileInfo.digest`/`etag` fields**
  `ContentDigest` frozen dataclass (`algorithm: str`, `value: str` — both
  lowercase-normalized, validated). `FileInfo.checksum` replaced with
  `FileInfo.digest: ContentDigest | None` and `FileInfo.etag: str | None`.
  `ext.integrity.content_digest()` function added. Spec 035.

- [x] **BUG-003 — `child()` now propagates proxy behavior in ObservedStore/CachedStore**
  `ObservedStore.child()` and `CachedStore.child()` now return wrapped
  stores that preserve observation/caching behavior. Previously, child
  stores silently lost all middleware. Fixed via `_wrap_child()` in
  `ProxyStore` base class.

- [x] **ID-094 — Extract ProxyStore base class**
  Shared delegation base for `ObservedStore` and `CachedStore` in
  `_proxy.py`. Centralizes `_backend`/`_root`/`_owns_backend` coupling,
  provides default delegation for all 27 Store methods, enables `child()`
  propagation via `_wrap_child()`. ADR-0014.

- [x] **ID-008 — Checksum verification on read/write**
  Verification functions (`ext.integrity`, ID-093), stream wrappers
  (`ext.streams`, ID-092), `ContentDigest` model (ID-095),
  S3 etag population (ID-096), and Azure etag/digest population (ID-097).

- [x] **ID-093 — `ext.integrity` module — checksum verification helpers**
  `checksum()`, `verify()`, `verify_hex()`. Pure functions over
  Store's public API. Spec 034.

- [x] **ID-092 — `ext.streams` module — stream-level wrappers**
  `ProgressReader`, `ProgressWriter`, `ChecksumReader`, `ChecksumWriter`,
  `read_with_progress()`. Composable `BinaryIO` wrappers. Spec 033.

- [x] **ID-091 — Refactor `ext.transfer` to use public `ProgressReader`**
  Replaced private `_ProgressReader` with `ProgressReader` from
  `ext.streams`. No public API change.

---

## Post-v0.17.0

- [x] **ID-085 — HTTP backend: HEAD fallback for CDN-blocked servers**
  When `HEAD` returns 401/403, `exists()`, `get_file_info()`, and
  `check_health()` retry with `GET` + `Range: bytes=0-0` (single byte).
  On success, the backend caches that HEAD is blocked for its lifetime.
  `_build_file_info` extracts total size from `Content-Range` header.
  Spec HTTP-FALLBACK-001, 11 new tests, guide updated with CDN section.
  Depends on: ID-082.

- [x] **BK-009 — Fix slow local test suite (IPv6 dual-stack + HTTP server lifecycle)**
  Local test suite took ~2:41 due to two HTTP-related bottlenecks:
  (1) pytest-httpserver defaulted to `localhost` which triggers IPv6 dual-stack
  timeout on Windows (~2 s per urllib request); fixed by overriding
  `httpserver_listen_address` to `("127.0.0.1", 0)`.
  (2) Conformance HTTP backend started/stopped a new server per test (~0.5 s
  teardown each); fixed by adding a session-scoped `http_server` fixture.
  Result: 161 s → 37 s (4.3x speedup), no test changes needed.

- [x] **ID-089 — Extensions API reference section**
  Moved all 11 extension API pages into a nested "Extensions" section under
  the API reference, with an index page and summary table. Updated cross-links
  from 7 guide pages. Matches the Backends section structure from ID-088.

- [x] **ID-087 — Speed up macOS & Windows CI test runs**
  Replaced the broad `pytest -m "not requires_docker"` filter with a focused
  `@pytest.mark.os_sensitive` marker. Tests that exercise OS-specific behaviour
  (path separators, `os.replace` atomicity, `tempfile`, local filesystem) are
  marked at module level (`test_path.py`, `test_open_atomic.py`, `test_glob.py`,
  `backends/test_local.py`) or at fixture-param level (`local` and `memory`
  params in `backends/conftest.py`, propagating to the full conformance suite
  for those backends). macOS and Windows CI now run only `-m os_sensitive`.
  Network-protocol backends (HTTP, S3, SFTP) have no OS-specific behaviour and
  are Linux-only. Ripple-check guidance added to `sdd/CLAUDE-REFERENCE.md`.

- [x] **ID-088 — Backend classes in API reference**
  Added class documentation for all 7 backends (Local, Memory, HTTP, S3,
  S3-PyArrow, SFTP, Azure) under a new "Backends" section in the API reference.
  Each page: hand-written intro linking to the backend guide, then mkdocstrings
  `:::` directive with `show_bases: false`. Backends index page with summary
  table. Old standalone `http-backend.md` removed.

- [x] **BK-008 — Medallion + Dagster showcase implementation**
  Self-contained Dagster project in `examples/medallion_dagster/`
  demonstrating 4 extensions composing over live MeteoSwiss data
  (Bronze/Silver/Gold medallion architecture).
  Uses `ReadOnlyHttpBackend`, `ext.cache`, `ext.otel`,
  and `ext.dagster`.
  [Showcase architecture](research/research-medallion-dagster-showcase.md),
  [docs page](../docs-src/examples/medallion-dagster.md).

- [x] **ID-082 — Read-only HTTP backend (`ReadOnlyHttpBackend`)**
  7th backend: read-only access to HTTP/HTTPS URLs with `{READ, METADATA}`
  capabilities. [Spec 032](specs/032-http-backend.md), 3 transports
  (urllib/requests/httpx), streaming adapters (`_HttpxStreamAdapter`,
  `_Urllib3StreamAdapter`), conformance suite capability gates, 85 tests,
  [guide](../guides/backends/http.md), [example](../examples/http_backend.py),
  API docs. 4 review rounds (31 threads). Resource leak fix, thread-safety
  docs, CI coverage floor adjustment (90% non-primary, 95% primary).
  [Research](research/research-readonly-http-backend.md) (§ 20: implementation plan).
  Lesson learned: research and initial estimation significantly underestimated
  complexity — transport abstraction, streaming adapters, error mapping across
  3 HTTP libraries, CDN edge cases, and conformance suite changes made this
  ~2,700 lines across 32 files, far beyond the initial "simple read-only
  wrapper" estimate.
  Follow-up: ID-085 (HEAD fallback for CDN-blocked servers).

- [x] **BK-007 — Docs quick fixes: dashes, See also, table booleans, SFTP blockquotes**
  All 20 items from the Audit 004 fix list resolved:
  AF-041 (`--` → `—`; first pass 33 files, second pass extended to 45 files covering
  sdd/ specs, ADRs, RFCs, research, audits, and `docs-src/design/*.tmpl` templates),
  AF-042 (See also unified to Pattern B), AF-043 (table booleans to `Yes` / `—`),
  AF-044 (SFTP blockquotes → admonitions), AF-046 (extensions table disambiguation),
  AF-047/048 (Installation stubs), AF-049 (`!!! tip` accepted as intentional).
  Added `.editorconfig` (UTF-8, LF). Supersedes ID-086 (all T-16 through T-20 resolved here).

- [x] **ID-086 — Docs structural harmonization** — superseded by BK-007 above.

- [x] **BUG-001 — `pydantic_to_registry_config()` fails to wrap `SecretStr` in `Secret`**
  `model_dump()` returns `SecretStr` objects (not a `str` subclass), which
  bypassed `from_dict()`'s `isinstance(v, str)` check. Added
  `_unwrap_secret_strs()` helper to convert `SecretStr` → `str` in backend
  options before `from_dict()`. Spec CFG-015 updated.

- [x] **ID-084 — Drop optional-extension re-exports from `__init__.py` (ADR-0013)**
  Removed `try/except ImportError` re-export blocks for arrow, otel, pydantic,
  and yaml extensions from `remote_store/__init__.py`. Each extension is now
  imported only from `remote_store.ext.<name>`. Eliminates import-time overhead
  from heavy optional deps (e.g. Dagster ~2-5 s). Pure-Python extensions
  unchanged. ADR-0013, migration guide entry, CHANGELOG entry.

- [x] **ID-075 — Dagster integration v1 (`ext.dagster`)**
  Thin Dagster IO manager adapter: `remote_store_io_manager(store)` factory,
  serializers (pickle, JSON, Parquet), [spec 031](specs/031-ext-dagster.md)
  (DAG-001 -- DAG-011), tests, guide, docs wiring.
  v2 tracked as ID-083.
  [Research](research/research-dagster-extension.md).

- [x] **ID-081 — README medium pass: trim density, add backend behavior matrix**
  Streamlined onboarding flow: trimmed duplicate explanations, added backend
  comparison matrix, restored correct extras list, fixed method count (27).

- [x] **ID-064 — Docs site enhancements (colored types, Material features, Fira Code)**
  Applied findings from [research](research/research-fastapi-docs.md).
  P1: `separate_signature`, `signature_crossrefs`, `show_symbol_type_heading`,
  `show_symbol_type_toc`. P3: Fira Code font via `extra_css`. P4: `navigation.tabs.sticky`,
  `search.suggest`, `search.highlight`. Also added `show_signature_annotations` for
  property return type visibility.

- [x] **ID-080 — Migrate docstrings from Sphinx to Google style**
  Converted 367 Sphinx markers across 25 files to Google-style sections.
  Updated `mkdocs.yml` (`docstring_style: google`) and `sdd/DESIGN.md` §4.
  [Research](research/research-google-docstring-migration.md).

- [x] **ID-062 — Remove redundant `exists()` guard from S3 listing methods**
  Removed `exists()` pre-check from `list_files`, `list_folders`, and
  `iter_children` in S3Backend and S3PyArrowBackend. Halves API calls
  for listing operations.

- [x] **ID-076 — AzureBackend `max_concurrency` parameter**
  Added `max_concurrency: int = 1` constructor parameter to `AzureBackend`.
  Threaded through to `upload_blob()`, `download_blob()`, and HNS
  `upload_data()` calls. [Spec AZ-033](specs/012-azure-backend.md).

- [x] **ID-079 — FolderInfo.name property and PathEntry protocol notes**
  Added `name` property to `FolderInfo` so it satisfies `PathEntry`
  alongside `FileInfo` and `FolderEntry`.

- [x] **ID-080b — Document lazy-import pattern for mixed optional deps**
  Superseded by ADR-0013: optional-dependency extensions are no longer
  re-exported from `__init__.py` at all.

- [x] **ID-071 — Store API refinement: Phase 1**
  Subsumed by ID-074. Kept for traceability.
  [Research](research/research-store-api-refinement.md).

## v0.17.0

- [x] **ID-072 — Store API refinement: listing normalization (Option D)**
  `list_folders()` returns `Iterator[FolderEntry]`, `iter_children()` returns
  `Iterator[FileInfo | FolderEntry]`. Added `FolderEntry` dataclass and
  `PathEntry` protocol. All 6 backends updated.
  [Research](research/research-store-api-refinement.md).

## v0.16.0

- [x] **ID-078 — Document Store at a new root**
  Added docstring note on `Store` class and admonition in
  `docs-src/api/store.md`.

- [x] **ID-077 — Switch docstring rendering from tables to lists**
  Changed `docstring_section_style` to `list` in mkdocstrings config.

- [x] **ID-074 — Store API refinement (pre-v1 audit)**
  Systematic pre-v1 audit of the Store public API. Rewrote all Store
  docstrings, implemented `write_text()`, restructured `store.md` with
  per-method `:::` directives, built backend behavior matrix.
  Subsumes ID-071 Phase 1.

- [x] **ID-073 — Use uv as hatch installer backend**
  Set `installer = "uv"` in `[tool.hatch.envs.default]`. ~10x faster
  env creation.

- [x] **ID-063 — `write_text()` convenience method**
  Shipped as part of ID-074.

## v0.15.0

- [x] **ID-056 — `read_text()` convenience method**
  [Spec 028](specs/028-read-text.md) (RTXT-001 -- RTXT-006).

- [x] **ID-055 — `iter_children()` — combined file + folder listing**
  [Spec 027](specs/027-iter-children.md) (ITER-001 -- ITER-008).

- [x] **ID-025 — `ext.cache` — store-level caching middleware**
  `cached_store(store, ttl=300)`. Auto-invalidation on writes/deletes/moves/copies.
  [Spec 023](specs/023-ext-cache.md) (CACHE-001 -- CACHE-015). 52 tests.

- [x] **ID-035 — Parallel batch operations**
  `concurrent=True` and `max_workers=N` on batch operations.
  [Spec](specs/016-ext-batch.md) BATCH-020 -- BATCH-025. 20 new tests.

- [x] **ID-036 — Hive-style partition path helpers**
  `partition_path()` and `parse_partition()`.
  [Spec 024](specs/024-ext-partition.md) (PART-001 -- PART-013). 23 tests.

- [x] **ID-048 — Verify notebook examples in CI**
  `tests/scripts/run_notebooks.py` executes notebook code cells via `exec()`.

- [x] **ID-026 — Streaming atomic writes**
  `Store.open_atomic()` and `Backend.open_atomic()`.
  [RFC-0004](rfcs/rfc-0004-streaming-atomic-writes.md),
  [spec 022](specs/022-streaming-atomic-writes.md) (SAW-001 -- SAW-015).

- [x] **ID-037 — PyArrow adapter Phase 2 — Tier 1 native fast-path reads**
  `Backend.native_path()` (BE-025), `Store.native_path()` (STORE-015).

- [x] **ID-038 — Re-run comparative benchmarks post-cache-invalidation fix**

- [x] **DOC-001 — Documentation overhaul per Documentation Master**
  Full Diataxis restructure of the docs site (Phase 1--7).

## v0.14.0

- [x] **ID-002 — YAML config support** (moved to `ext/yaml.py` post-v0.15.0)
  [Spec 021](specs/021-config-loaders.md) (CFG-010/CFG-011).

- [x] **ID-003 — Pydantic BaseSettings integration**
  [Spec 021](specs/021-config-loaders.md) (CFG-015 -- CFG-017).

- [x] **ID-005 — Built-in `from_toml()` config loader**
  [Spec 021](specs/021-config-loaders.md) (CFG-008/CFG-009).

- [x] **ID-034 — Parquet lake guide (Bronze / Silver / Gold patterns)**

- [x] **ID-040 — `move(src, dst)` and `copy(src, dst)` same-path consistency**
  Spec: STORE-008a.

- [x] **ID-041 — `Registry.get_store()` backend ownership foot-gun**
  `get_store()` now sets `_owns_backend = False`.

- [x] **ID-042 — Document Secret usage in README and examples**

- [x] **ID-043 — Remove `_stacklevel` from public `from_dict()` signature**

- [x] **ID-046 — Audit version-conditional imports for mypy coverage**

- [x] **ID-047 — Spec accuracy fixes**

- [x] **BK-005 — SFTP backend test coverage gaps**
  Coverage improved from 90% to 100%. 35 new tests.

- [x] **BK-006 — Memory backend test coverage gaps**
  Coverage improved from 90% to 100%. 30 new tests.

## v0.13.0

- [x] **ID-004 — Structured logging & metrics hooks**
  Superseded by ID-024.

- [x] **ID-024 — `ext.observe` — hooks / middleware / instrumentation**
  [ADR-0010](adrs/0010-observe-hooks-middleware.md),
  [spec 019](specs/019-ext-observe.md) (OBS-001 -- OBS-014).

- [x] **ID-039 — Credential hygiene: `Secret` wrapper and central redaction**
  [Spec 020](specs/020-credential-hygiene.md) (SEC-001 -- SEC-008).

## v0.12.0

- [x] **ID-007 — `Store.glob()` surface API**
  [ADR-0009](adrs/0009-glob-three-tier-design.md),
  [spec 018](specs/018-glob.md).

- [x] **BK-002 — Glob / pattern matching strategy**
  Related: ID-007.

- [x] **ID-032 — Fix listing benchmark fixture caching**
- [x] **ID-033 — Cloud benchmark quick tier timing budget**

## v0.10.0

- [x] **ID-020 — Benchmark tiered modes and single-backend filtering**
- [x] **ID-027 — Extension architecture (`ext.*` namespace)**
  [ADR-0008](adrs/0008-extension-architecture.md).
- [x] **ID-028 — Release-triggered publish and docs deploy**
  Subsumes AF-014.
- [x] **ID-029 — Versioned documentation (mike + RTD tags)**
- [x] **ID-031 — S3-PyArrow read path optimization**
  [RFC-0003](rfcs/rfc-0003-s3-pyarrow-read-optimization.md).

## v0.9.0

- [x] **ID-001 — Cross-store transfer** *(subsumed by ID-023)*
- [x] **ID-009 — `Store.upload()` / `Store.download()`** *(subsumed by ID-023)*
- [x] **ID-015 — Audit external deep links**
- [x] **ID-016 — PyArrow FileSystemHandler adapter (Phase 1)**
  [RFC-0002](rfcs/rfc-0002-pyarrow-filesystem-adapter.md),
  [spec 014](specs/014-pyarrow-filesystem-adapter.md). 89 tests.
- [x] **ID-019 — Update stale CAP-001 in spec 003**
- [x] **ID-022 — `ext.batch` — batch operations**
  [Spec 016](specs/016-ext-batch.md).
- [x] **ID-023 — `ext.transfer` — cross-store and local-path transfers**
  [Spec 017](specs/017-ext-transfer.md).

## v0.8.0

- [x] **ID-021 — `Store.child(subpath)` — runtime sub-scoping**
  [Spec 015](specs/015-store-child.md).
- [x] **ID-030 — Claude Code reusable skills**
- [x] **DONE-005 — Reorganize examples into core + backends groups**

## v0.7.0

- [x] **ID-017 — Memory backend**
- [x] **AF-008 — Add credential masking to backend `__repr__`**
- [x] **AF-009 — Fix `Registry.close()` to close all backends on error**
- [x] **AF-011 — Remove dead `RemoteFile`/`RemoteFolder`**
- [x] **AF-015 — Update stale v0.5.0 docs**

## v0.6.0

- [x] **AF-001 — Auto-register S3/SFTP/S3-PyArrow in Registry**
- [x] **AF-002 — Remove GLOB/RECURSIVE_LIST ghost capabilities**
- [x] **AF-003 — Fix `S3Backend.close()` global cache side effect**
- [x] **AF-004 — Unify `get_folder_info` on empty folders**
- [x] **AF-005 — Fix `delete_folder` error types**
- [x] **AF-006 — Fix native exception leakage through lazy streams**
- [x] **AF-007 — Wire Azure backend into docs site**

## v0.5.0

- [x] **BK-001 — Azure backend**
  [RFC-0001](rfcs/rfc-0001-azure-backend.md),
  [spec 012](specs/012-azure-backend.md).
- [x] **ID-012 — Performance benchmarks**
- [x] **DONE-004 — S3-PyArrow hybrid backend**
  [Spec 011](specs/011-s3-pyarrow-backend.md).

## v0.4.x

- [x] **ID-014 — Streaming conformance tests** (v0.4.4)
- [x] **ID-011 — Python 3.14 support** → graduated to BK-004
- [x] **DONE-001 — PEP 604 type hints**

## v0.3.0

- [x] **BK-003 — Native path resolution (`to_key`)**
  [Spec 010](specs/010-native-path-resolution.md).
- [x] **BK-004 — Python 3.14 support** (graduated from ID-011)
- [x] **BL-001 — PyPI publish workflow**
- [x] **BL-002 — SFTP backend documentation**
- [x] **BL-003 — README backends table outdated**
- [x] **BL-004 — README & project description tone rework**
- [x] **BL-005 — CITATION.cff**
- [x] **BL-006 — Protect master branch with ruleset**
- [x] **BL-007 — Pin minimum dependency versions & clean up extras**
- [x] **BL-008 — Set up docs hosting**
- [x] **BL-009 — Fix broken PyPI logo and badges**
- [x] **BL-010 — Publish documentation to Read the Docs**

## Post-release housekeeping

Items that shipped outside a version bump, newest first.

- [x] **ID-070 — Add third-party doc links in extension module docstrings**
- [x] **ID-069 — Automated Claude PR review workflow** (reverted)
- [x] **ID-068 — Replace `dorny/paths-filter` with bash path filtering**
- [x] **ID-065 — Use uv in docs deployment workflow**
- [x] **ID-061 — Use uv for CI dependency installs**
- [x] **ID-060 — Multi-platform CI (Linux, Windows, macOS)**
- [x] **ID-059 — Restructure authoritative docs to ADF standard**
- [x] **ID-054 — `store.ping()` / backend health check**
  [Spec 026](specs/026-health-check.md).
- [x] **ID-053 — Fix code block highlighting in docs**
- [x] **ID-052 — Custom domain: remotestore.dev**
- [x] **ID-051 — Sweep stale backlog references in docs and guides**
- [x] **ID-050 — End-to-end integration tests against Docker backends**
- [x] **ID-049 — Enable GitHub Vigilant Mode**
- [x] **ID-045 — Fill example coverage gaps for specs 003, 004, 020, 021**
- [x] **ID-044 — Harden examples into assertion-based expectation tests**
- [x] **ID-010 — Retry policy configuration**
  [Spec 025](specs/025-retry-policy.md), [ADR-0011](adrs/0011-retry-policy.md).
- [x] **BUG-002 — Windows drive letter case mismatch in `warnings` module**
- [x] **BUG-001 — `get_folder_info("")` fails for empty-root stores**

## Audit findings

From [adversarial review](audits/audit-001-adversarial-review.md) (v0.5.0),
[design-compliance audit](audits/audit-002-design-compliance.md) (v0.13.0), and
[documentation audit](audits/audit-003-documentation.md) (v0.15.0).

- [x] **AF-010 — Document TOCTOU and non-atomic move limitations** (v0.9.0)
- [x] **AF-012 — Add capability gating tests (STORE-006)** (v0.9.0)
- [x] **AF-013 — Add PermissionDenied/BackendUnavailable error path tests** (v0.9.0)
- [x] **AF-014 — Add CI gate to publish workflow** (v0.9.0)
- [x] **AF-016 — Fix stale capability sections in specs** (v0.14.0)
- [x] **AF-017 — Add ID-043 to CHANGELOG** (v0.14.0)
- [x] **AF-018 — Correct BACKLOG version tags** (v0.14.0)
- [x] **AF-019 — Fix spec count in DEVELOPMENT_STORY.md** (v0.14.0)
- [x] **AF-020 — Fix §11.6 method ordering** (v0.14.0)
- [x] **AF-021 — Add backlog ID to unlinked TODO** (v0.14.0)
- [x] **AF-022 — 7 example scripts missing from docs-site nav**
- [x] **AF-023 — ObservedStore: proxy overrides lack docstrings** (resolved via config)
- [x] **AF-024 — CachedStore: proxy overrides lack docstrings** (resolved via config)
- [x] **AF-025 — CacheBackend protocol: 6 methods undocumented**
- [x] **AF-026 — 6 guides missing API reference links** (closed — not a defect)
- [x] **AF-027 — `guides/retry.md` missing "See also" section**
- [x] **AF-028 — `guides/backends/index.md` sparse**
- [x] **AF-029 — `guides/performance.md` guide-style violations** (closed — not a defect)
- [x] **AF-030 — Research nested 3 levels deep in nav** (closed — not a defect)
- [x] **AF-031 — `transfer()` missing `:returns:` docstring**
- [x] **AF-032 — `guides/observe.md` on_write hook table omits `open_atomic`**
- [x] **AF-033 — `guides/observe.md` on_ping hook row missing**
- [x] **AF-034 — `observe()` docstring on_write omits `open_atomic`**
- [x] **AF-035 — `guides/cache.md` private import**
- [x] **AF-036 — `guides/health-check.md` private import**
- [x] **AF-037 — `guides/backends/sftp.md` private imports** (created SFTPUtils)
- [x] **AF-038 — `CONTRIBUTING.md` stale counts**
- [x] **AF-039 — `sdd/CLAUDE-REFERENCE.md` wrong path**
- [x] **AF-040 — `guides/migration.md` documents unreleased v0.16.0**
