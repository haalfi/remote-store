# Development Backlog — Done
<!-- doc: repo-only -->

Completed items, newest first. All items must use `[x]` status.
Active work lives in [BACKLOG.md](BACKLOG.md).

---

## Unreleased

- [x] **BK-294 — Retry Graph `overwrite=True` 409-under-replace (create-race) as transient**
  spec: GR-018, GR-032 · effort: M · audience: user.api
  BK-288 documented two ways `overwrite=True` (`conflictBehavior=replace`) can
  still surface `AlreadyExists`: a terminal SharePoint-backed replace-rejection
  (unreproducible on this project's consumer-only live tier, per **BK-261**) and a
  live-reproduced concurrent create of the *same new key* (the loser's replace
  lands mid-create). **Evaluation outcome: retry.** A bounded re-attempt of the
  `replace` re-issues the *actual* write rather than swallowing the 409, so it
  sidesteps BK-261's blocker — it needs no SharePoint 409-body classification. The
  create-race loser re-issues and wins (last-writer-wins); a terminal conflict
  exhausts the budget and still raises `AlreadyExists`. Gated on `overwrite=True`
  (the `overwrite=False` create-once-race single-winner outcome, GR-059, is
  untouched) and only the `AlreadyExists` discrimination is retried — folder /
  file-ancestor `409`s discriminate to `InvalidPath` and propagate on the first
  attempt. **Live finding (BK-294 tuning):** the first cut used immediate retries
  and a live consumer-OneDrive 8-way race left one straggler 409-ing in lockstep;
  a **full-jitter backoff** (`_REPLACE_RACE_MAX_ATTEMPTS=6`, sub-second cap)
  desynchronises the retriers and resolves every writer (verified 8/8 and 12/12
  across repeated rounds, content intact). Spec GR-018/GR-032, Graph guide, respx
  mechanism tests, and Tier-3 live probe `test_live_overwrite_create_race_all_succeed`
  (opt-in `RS_TEST_LIVE_GRAPH=1`). SharePoint tier stays documented-as-unverified.
  Trace `sdd/traces/bk-294-graph-overwrite-replace-retry.yml`.

- [x] **BK-291 — `GraphAuth` MSAL token-cache write is non-atomic and unlocked**
  spec: GR-007 · effort: M (filed S) · audience: user.api, library.maintainer
  `flush_cache` did a plain `open(path, "w").write(...)` at the default shared
  cache path with no atomicity and no lock; concurrent `GraphAuth`/`GraphBackend`
  instances or processes sharing it (the common multi-worker deployment) could
  truncate/tear the cache, forcing a re-login. **Reproduced** (sandbox repro, 6
  writers + 2 readers): the current pattern produced empty reads (the truncate
  window is payload-independent — `open(path,"w")` zeroes the file before any
  write) and torn JSON. **A bare temp-file + `os.replace` was rejected**: the
  same repro showed `os.replace` raises `PermissionError` (`WinError 5`) on
  Windows when the destination is held open by a concurrent reader / contended
  by another replace, and since `flush_cache` is best-effort that would become a
  *silent* non-persistence → re-login. Fixed by adopting
  `msal_extensions.PersistedTokenCache` (`FilePersistence`): every acquisition
  writes through under a cross-process `CrossPlatLock` with reload-merge, and the
  read path retries on a dirty read — corruption **and** lost-updates resolved
  with no `os.replace`. `flush_cache` is now a best-effort no-op kept for the
  GR-051 `close()` hook. Added `msal-extensions>=1.3` to the `graph` extra
  (`>=1.3` keeps `portalocker` optional). Effort reclassified S→M (dependency +
  ADR/spec/test rework). GR-007 / GR-051 amended; ADR-0021 / ADR-0022 updated.
  Trace: `sdd/traces/BK-291-token-cache-atomic.yml`.

- [x] **BK-290 — Graph async I/O robustness under concurrent load**
  spec: GR-015, GR-019 · effort: S · audience: user.api, library.maintainer
  Closed the two I/O-robustness gaps the expectation-driven review surfaced.
  **(1) Blocking spool I/O off the loop:** `transfer.py` ran `SpooledTemporaryFile`
  `write` / `seek` / `read` / `tell` synchronously on the event-loop thread in
  three sites — the SharePoint range-fallback (`_spooled_window`) and the
  unknown-length upload spool (`spool_content` + `_upload_chunks`' per-chunk
  `reader.read` of up to one `upload_chunk_size`). Once the spool spilled to disk,
  a large transfer head-of-line-blocked sibling coroutines. All four call shapes
  now dispatch through `asyncio.to_thread` (the chunk replay bundled into one
  `_seek_read` hop). Two deterministic tests assert the **thread of execution**
  (blocking I/O lands on a worker thread, never the loop) rather than timing —
  `test_transfer.py::TestSpoolOffloadOffLoop`, `test_write.py::TestUploadSpoolOffloadOffLoop`.
  **(2) Connection-pool ceiling documented, not parameterised:** the silent httpx
  100-conn default surfaces high fan-out as opaque `BackendUnavailable`. Chose the
  S3 precedent — document the existing `client_options` passthrough
  (`{"limits": httpx.Limits(...)}`) with a "Connection-pool tuning" guide caveat
  and an executable snippet (`examples/snippets/graph_client_tuning.py`) — rather
  than add a first-class `limits=` parameter (keeps the API surface minimal).
  **ADR correction:** ADR-0025 § Risks misattributed the loop-stall to
  "`_graph_transfer` chunk hashing," which does not exist (no `hashlib` in
  `transfer.py`); per the immutability rule, **ADR-0029** supersedes that one
  bullet (the real cause is blocking spool I/O, now mitigated in-backend) and a
  pointer was added at the superseded bullet. Spec: GR-015 / GR-019 gained
  event-loop-liveness postconditions. Out of scope and left as follow-ups: token
  single-flight (**BK-292**), `ext.cache` stampede (**ID-218**). Trace:
  `sdd/traces/BK-290-graph-io-robustness.yml`.

- [x] **BK-288 — Cross-backend concurrent-use-posture documentation (docs leg of the concurrency contract)**
  spec: — · effort: M · audience: user.site, user.api_docs
  **Rescoped** from "Graph concurrency & consistency docs" to the docs leg of the
  BK-287 (spec) / BK-289 (test-registry) concurrency-contract work: `concurrency.md`
  documented only per-operation atomicity and had **no** concurrent-use-posture axis
  for any backend, so adding "a Graph row" meant building the table first. Added a
  **Concurrent-use posture** section to `explanation/concurrency.md` — a per-backend
  `thread-safe` / `single-connection` table (the user-facing shadow of the registry
  `concurrency` field and the BE-028 clause), the SQLBlob/SQLQuery `sqlite:///:memory:`
  single-connection footnote and the S3-PyArrow to-be-confirmed hedge from the BK-289
  discoveries, plus a **Bridge asymmetry** subsection (ASYNC-094: `AsyncBackendSyncAdapter`
  serialises onto one loop = safe; `SyncBackendAdapter` + a single-connection backend under
  `asyncio.gather` = unsafe). Corrected the `overwrite=False` "all backends" framing — Graph
  is a server-side atomic create-if-absent, not TOCTOU — and added Graph rows to the move /
  summary tables. Added a **Concurrency & consistency** section to the Graph guide
  (one-loop posture, bridged-sync safety, create-if-absent, non-atomic move/copy,
  read-your-writes), a one-line contract to the async-guide FastAPI example, and a
  posture-aware Limitations bullet. **Widened the BK-261 caveat**: the `overwrite=True`
  replace-409 is no longer framed SharePoint-only — the live-reproduced consumer-OneDrive
  concurrent-create race (losers get `AlreadyExists`; content integrity holds) is now
  documented. Spec coordinates kept out of the published prose (the `check_no_tracker_refs`
  gate treats `BE-028` / `ASYNC-094` / `GR-059` as tracker leakage); the mapping lives in
  the trace. Discovery: the code-side alternative (retry Graph's 409-under-replace as
  transient) was evaluated and routed to a follow-up (**BK-294**) rather than changed
  here. Trace: `sdd/traces/bk-288-concurrency-docs.yml`.

- [x] **BUG-220 — LocalBackend `_resolve` races on concurrent intermediate-dir creation (Windows)**
  spec: BE-008 · effort: S · audience: user.api, library.maintainer
  Discovered by the BK-289 concurrency lane. `LocalBackend._resolve` did
  `(self._root / path).resolve()` then `relative_to(self._root)`; on Windows,
  `Path.resolve()` over a path whose intermediate dirs are being created by
  sibling threads transiently returns an 8.3 short-name form that is **not**
  `relative_to` the init-time root, so a legitimate concurrent write raised a
  spurious `InvalidPath("Path escapes root directory")`. **Repro recipe
  corrected:** the bug needs **long (>8 char) path components** to trigger 8.3
  short-name generation — short components reproduce 0/20 (the BACKLOG recipe
  under-specified this; the lane's own `cc/write/{i}` write-stress uses short
  components and likely never reproduced it, so its `xfail(strict=False)` was
  defensive/xpassing). Fix: lexical `os.path.normpath` containment for the `..`
  case, plus a symlink-escape check that resolves only the deepest **existing**
  ancestor — the non-existent / in-flight tail is never re-canonicalised, killing
  the flicker, while existing symlinks are still followed and rejected if they
  escape root. Cross-platform (POSIX `realpath` shares the resolve()-based escape
  contract; the fix preserves it). Removed the sync + aio lane xfail helpers so
  `local` / `local_async_adapted` assert for real on Windows. New regression +
  symlink-escape tests in `tests/backends/local/test_concurrency.py`. The sibling
  `glob()` `.resolve().relative_to` site (lower-severity latent skip, not the
  reported bug) was assessed and left to a focused follow-up. Trace:
  `sdd/traces/bug-220-local-resolve-race.yml`.

- [x] **BK-289 — Cross-backend posture-gated concurrency conformance lane**
  spec: TEST-010, TEST-003, 003, 029 · effort: L · audience: infra.test
  Design: [research-bk-289-concurrency-test-lane.md](research/research-bk-289-concurrency-test-lane.md).
  Added a posture-gated concurrency lane: each fixture declares a `concurrency`
  posture (`thread_safe` / `single_connection`, sourced from `backends.toml` like
  `transport`, required per family), and the lane tests each backend against its
  own declaration — not a blanket thread-stress. New
  `tests/backends/conformance/test_concurrency.py` (+ `aio/` sibling): Tier-1
  in-process ThreadPool / `asyncio.gather` stress over the `thread_safe` set
  (concurrent reads, distinct-key writes, read-after-write) and the
  `single_connection` one-instance-per-thread carve-out + the ASYNC-055 cross-loop
  guard; Tier-3 large-upload + live probes ride the registry's stage/live marks.
  Graph create-once-race (`overwrite=False` → exactly one winner via respx) and
  the live race probes live in `tests/backends/graph/aio/test_concurrency.py`
  (TEST-010 keeps concrete backends out of `conformance/`); BUG-219 aclose and
  bridge deadlock-freedom are cross-referenced, not duplicated. Invariant-only,
  fixed fan-out, `@pytest.mark.concurrency`. Closes audit-001 **M-14**. Marks cite
  the backend-posture IDs from BK-287 — `BE-028` (sync), `ASYNC-094` (async),
  `GR-059` (Graph create-once-race), and the per-backend `S3-028` / `AZ-037` /
  `SFTP-029` the lane's fixtures exercise (retiring those design-allowlist
  entries).
  **Discoveries:** the lane proved the `sqlblob` (`sqlite:///:memory:`,
  SingletonThreadPool) fixture is `single_connection`, not `thread_safe`; and
  reproduced a Windows LocalBackend concurrency defect (filed **BUG-220**;
  `local` writes xfail on Windows). Expectations-repo mirror split to **BK-293**.
  Trace: `sdd/traces/bk-289-concurrency-lane.yml`.

- [x] **BK-287 — Cross-backend concurrency-posture contract: `GR-059` + per-backend clauses**
  spec: BE-028 (new), ASYNC-094 (new), GR-059 (new), 008, 009, 011, 012, 032, 040, 041 · effort: M · audience: contributor.process, user.api_docs
  `STORE-007`/`ASYNC-055` promise a shared `Store`/`AsyncStore` is concurrency-safe,
  but a `Store` merely delegates, so the promise bottoms out in the backend — and
  the backend-level obligation was unstated (spec 044 had zero concurrency text;
  SFTP's caveat lived only in `async.md` + the docstring). Added a two-value
  posture taxonomy (`thread_safe` default / `single_connection`) as an explicit
  per-backend spec obligation: `BE-028` (003) for the sync contract, `ASYNC-094`
  (029) for the async mirror encoding the bridge asymmetry
  (`AsyncBackendSyncAdapter` safe vs `SyncBackendAdapter` + `single_connection`
  unsafe), and `GR-059` (044) declaring Graph's posture — one-loop-safe, no
  `Lock`, bridged-sync-safe unlike SFTP, `overwrite=False` server-atomic
  create-if-absent (live-confirmed consumer-OneDrive), close-terminal (GR-051),
  with the move-race error-fidelity gap pinned as a known limitation. Per-backend
  posture clauses added for S3 (S3-028), S3-PyArrow (S3PA-028, Tier-3 probe
  pending), Azure (AZ-037), SFTP (SFTP-029, pins the docstring caveat), HTTP
  (HTTP-CONC-001, transport-dependent), SQLBlob (SQL-BLOB-072), SQLQuery
  (SQL-QUERY-092). User chose all-backends scope. Spec-only (no code change);
  no ADR (a `bool` flag under asyncio's single thread, not a new mechanism).
  The taxonomy is the authoritative source for **BK-289**'s registry
  `concurrency` enum, which later converts the subset its conformance fixtures
  cover (S3-028, AZ-037, SFTP-029) to real marks; S3PA-028 (live-probe only) and
  the SQL clauses (no conformance fixture) stay allowlisted. Trace: `sdd/traces/bk-287-concurrency-contract.yml`.

- [x] **BUG-219 — `GraphBackend.aclose()` concurrent with in-flight ops raises untyped `RuntimeError`**
  spec: GR-051 · effort: S · audience: user.api, library.maintainer
  Found in the Graph concurrency / DX review and live-reproduced (FastAPI-shutdown
  shape: 5/5 in-flight ops → bare `RuntimeError`). `aclose()` closed the shared
  `httpx.AsyncClient` out from under in-flight ops, and there was no
  use-after-close guard — a new op after close *silently re-initialised* a fresh
  client (the old GR-051 contract) or hit a closed caller-client with httpx's bare
  `RuntimeError`. Fix: a `_closed` flag flipped at the start of `aclose()` gates
  the central `_client` accessor (every op reaches the client through it), so a
  use-after-close raises typed `BackendUnavailable` instead of re-initialising;
  and the request layer (`graph_send`, `transfer.stream_range`) translates httpx's
  closed-client `RuntimeError` (detected via `client.is_closed`, no string-match)
  to `BackendUnavailable` so an in-flight op surfaces typed. `aclose()` stays
  non-raising and idempotent; the abort loop uses the raw client ref (the guard
  would otherwise raise) and lazily creates a client only if sessions need
  aborting. No `Lock` added — a `bool` flag suffices under asyncio's single
  thread, so no ADR (BK-287 threshold not crossed). GR-051 amended (the old
  "re-initialise on demand" postcondition was the bug); the deliberate divergence
  from `AzureBackend.close()`'s AZ-029 re-initialise behavior is flagged for the
  cross-backend concurrency-contract work (BK-287 / ID-219). Reproduced with a
  failing test (`TestUseAfterClose`, GR-051) that hung/leaked pre-fix. Trace:
  `sdd/traces/bug-219-graph-aclose-guard.yml`.

- [x] **BUG-218 — Graph copy/move monitor hangs on a non-throttle `4xx` poll response**
  spec: GR-026 · effort: S · audience: user.api, user.api_docs, user.site
  Found in the ID-127 release-readiness review (live consumer-OneDrive
  validated). `poll_monitor` special-cased only `>=500` as transient-pending;
  every other non-2xx fell to the status-parser, whose `4xx` error body carries
  no `status` field, so it returned pending-unclassified and the loop re-polled.
  With `copy_timeout` defaulting to `None` (unbounded), a permission revoked
  mid-operation (`403`) or an expired/deleted monitor URL (`404`) hung
  `copy()`/`move()` forever — the only backend branch with neither replay nor
  live coverage (the live copy test exercises the success path only). Fix: a
  non-throttle `4xx` on the poll request is now terminal — mapped through the
  GR-028 table (`status` + `error.code`) and raised immediately; `429` stays
  pending (throttle, `Retry-After`) like a `5xx`. Reproduced with a test that
  hung pre-fix (`TestPollHttpError`, GR-026); spec GR-026 gained the symmetric
  4xx-terminal clause. Co-shipped the missed sibling of audit-016 M5 / BK-265:
  the async guide's drive-resolution snippet (`docs-src/guides/async.md`) used
  the sync `resolve_drive_id` adjacent to `async with AsyncStore`, which raises
  `RuntimeError` from a running loop — now `await aresolve_drive_id`. Trace:
  `sdd/traces/bug-218-graph-monitor-4xx-terminal.yml`.

- [x] **BUG-217 — Register a non-strict `azurite_async` fixture for the large-write consistency path**
  spec: WR-001a · effort: S · audience: infra.test
  BUG-216's resolution left the async large/streamed WriteResult↔FileInfo
  consistency test (`test_large_streamed_write_result_matches_file_info`) running
  on **no offline** async fixture: the sync side had the non-strict `azurite`
  baseline, but the async side only had `azurite_async_strict` (`strict_only`,
  excluded from default enumeration), so the test ran solely on the live
  `azure_live_async` (skipped without `RS_TEST_LIVE_HNS=1`). Registered a
  non-strict **`azurite_async`** fixture mirroring the sync `azurite`
  (`large_write_distinct = true`, flat-NS, not `strict_only`): added the TOML
  entry and refactored `azurite_async.py` to register both the baseline and the
  strict variant via a parametrised `_make_factory(reject_…)`, matching the sync
  `azurite.py` shape. Pinned the emulator gap on the async side with an
  `"azurite_async"` entry in `_ASYNC_LARGE_RICH_FIELDS_XFAIL` (`strict=True`,
  keyed on the fixture name so it cannot mask the live lane). Updated the
  `test_bk286_large_write_distinct_opt_in_set` opted-in set. Verified against the
  Azurite emulator (`--stage=2 -k azurite_async`): full async conformance is
  96 passed / 40 skipped / 2 strict XFAIL (the staged-path divergence), no
  unexpected failures, and the refactor leaves `azurite_async_strict`
  file-ancestor coverage intact. No CHANGELOG (infra.test). Trace:
  `sdd/traces/bug-217-azurite-async-baseline.yml`.

- [x] **BUG-216 — Azure large/block-staged `WriteResult.digest` vs `get_file_info().digest`: Azurite emulator gap, not a backend defect**
  spec: WR-001a · effort: S · audience: infra.test, contributor.process
  Filed by BK-286 when the new `test_large_streamed_write_result_matches_file_info`
  failed on the `azurite` fixture: on the staged path `WriteResult.digest` carries
  the commit response's MD5 while `get_file_info().digest` is `None`. The backlog
  required confirming against **real ADLS Gen2** before fixing (Azurite ≠ real
  ADLS). Verified live this session (`RS_TEST_LIVE_HNS=1 --stage=3 -m live -k
  azure_live`, `--runxfail` to lift the mask): both `write` and `write_atomic`,
  sync (`azure_live`) and async (`azure_live_async`), **pass** — real Azure stores
  `Content-MD5` on block-list commit and the two sides agree. The divergence is an
  Azurite emulator-fidelity gap, so no production code change is warranted (rules
  out the proposed fix options a/b). Resolution: (1) scoped the sync
  `_LARGE_RICH_FIELDS_XFAIL` to the `azurite` fixture by keying on
  `_fixture_record(backend).name` instead of `backend.name` (the emulator and the
  live fixture share `backend.name == "azure"`), and flipped it to `strict=True`
  so a future Azurite that starts persisting the MD5 fails loud to prompt removal;
  (2) **removed** the `_ASYNC_LARGE_RICH_FIELDS_XFAIL["async-azure"]` entry — it
  was masking the live `azure_live_async` lane as an allowed xpass (no async
  Azurite baseline runs this test), and re-keyed the async lookup on the fixture
  name too; (3) reworded the WR-001a spec note and the `_s3.py` contrast comment
  to say emulator-only. Discovery follow-up: the async side has no non-strict
  Azurite baseline for this path → **BUG-217** (see BACKLOG.md).
  No CHANGELOG (infra.test). Trace: `sdd/traces/bug-216-azure-digest-azurite-gap.yml`.

- [x] **BK-286 — Conformance: WriteResult↔FileInfo `size` cross-check + large/streamed-path consistency**
  spec: WR-001a · effort: S · audience: infra.test, library.maintainer
  The WR-001a consistency backstop (`test_write_result_rich_fields_match_file_info`,
  sync + async) compared `etag`/`digest`/`last_modified` against `get_file_info()`
  but never `size`, and only ever exercised a tiny single-`bytes` write — so the
  multipart / block-staged / upload-session write paths went unchecked for
  result/info agreement. Gap 3 (a `version_id` cross-check) is a non-gap:
  `FileInfo` carries no `version_id` field, so there is nothing to round-trip
  against (it stays covered as a capability-implication via
  `test_populated_field_implies_declared_capability`). Closed by: (1) adding
  `assert result.size == info.size` to both consistency tests; (2) a new
  `test_large_streamed_write_result_matches_file_info` (sync + async) that
  streams an 8 MiB payload — over Graph's 4 MiB `createUploadSession` boundary,
  S3's 5 MiB multipart floor, and Azure's 1 MiB single-put default — and asserts
  the returned `WriteResult` still matches `get_file_info()`. Gated by a new
  per-fixture `large_write_distinct` opt-in (registry + `backends`/`fixtures`
  TOML + loader), set only on real emulator/live fixtures of the distinct-path
  backends (`azurite`, `azure_live`(`_async`), `s3_live`, `s3_pyarrow_minio`,
  `s3_pyarrow_live`, `graph_live`) — deliberately off on the moto mocks
  (multipart fidelity untrusted) and `graph_replay` (a >4 MiB committed cassette
  is the cost `GRAPH_PROFILE` avoids, so Graph's upload-session path is a
  live-lane concern). Validated live against the real Graph drive
  (`RS_TEST_LIVE_GRAPH=1 --stage=3 -m live -k graph_live`): the upload-session
  WriteResult is consistent — first live coverage of that path. PR-review caught
  that `s3_live`'s large path was opted in but never executed; confirmed live on
  real AWS (`RS_TEST_LIVE_S3`): `s3_live` and `s3_pyarrow_live` both pass.
  Note: plain s3fs does a single PUT even at the 8 MiB test size (the
  always-multipart S3 lane is `s3_pyarrow`); S3 reads `etag`/`digest` from
  `head_object` on write and `get_file_info` alike (same source), so it agrees by
  construction and needs no xfail — structurally unlike Azure. The Azurite run
  surfaced **BUG-216**: Azure's large/block-staged write fills `WriteResult.digest`
  from the commit response while the staged blob stores no Content-MD5, so
  `get_file_info().digest` is `None` and the two diverge; xfailed via a
  large-path-only roster (`_LARGE_RICH_FIELDS_XFAIL` / `_ASYNC_LARGE_RICH_FIELDS_XFAIL`
  keyed by the divergent sync/async backend names, `strict=False` pending
  real-ADLS verification) so the test lands green while tracking the defect.
  This effort began from the e2e-Graph-coverage question, so it also wires the
  live-only Graph hop (async-only `GraphBackend` bridged to sync via
  `AsyncBackendSyncAdapter`) into the e2e tests that lacked async Graph coverage:
  `test_transfer.py` (memory↔Graph pairs), `test_data_lake.py` (full medallion
  pipeline), and `test_ext_write_e2e.py` (via the shared `store_chain`). The sync
  streaming chain stays Graph-free on purpose — the async streaming test already
  covers Graph. All six paths verified live against the real drive.
  No CHANGELOG (infra.test). Trace:
  `sdd/traces/bk-286-write-result-fileinfo-consistency.yml`.

- [x] **BK-285 — API reference: mirror the package, split the async monolith, surface async-only backends**
  spec: — · effort: M · audience: user.site, user.discoverability.human, contributor.tooling
  The sync API reference mirrored the `remote_store` package (one page per
  namespace member; backends under `backends/`, extensions under
  `extensions/`), but the entire `remote_store.aio` namespace collapsed into a
  single ~660-line `aio.md`. Three reader-facing symptoms followed: (1) the
  index grouped symbols by role without disclosing the grouping basis or the
  import paths; (2) async-only backends — `GraphBackend`, `AsyncAzureBackend`,
  `AsyncMemoryBackend` — appeared only inside the async dump, so a reader
  scanning Backends concluded Graph was not a backend; (3) `aio.md` mixed five
  page-types (Rich class, Protocol/ABC, support classes, backends, utilities)
  the framework documents as separate pages. A latent fourth: `aio.ext.write`
  was filed under the sync `extensions/` directory.
  Resolved with the **full mirror** option: added a `reference/api/aio/`
  subtree whose internal shape parallels the top level —
  `aio/store.md` (AsyncStore), `aio/backend.md` (AsyncBackend),
  `aio/adapters.md` (SyncBackendAdapter, AsyncBackendSyncAdapter,
  AsyncWritableContent), `aio/backends/` (memory, azure, graph — Graph now a
  first-class backend page carrying GraphAuth + GraphUtils), and
  `aio/extensions/write.md` (moved from `extensions/aio-write.md`). The async
  section index (`aio/index.md`) carries a sync ↔ async counterpart table; the
  main `index.md` states its grouping basis and cross-links async-native
  backends from the Backends section, and `backends/index.md` gained an
  "Async-native backends" block. `aio.md` and `extensions/aio-write.md` were
  deleted; every inbound link (guides, the async-store example, the API index)
  was repointed. Tooling: `scripts/check_api_docs.py` `PAGES` now points at the
  split pages and `AsyncAzureBackend` left `_INDEX_EXEMPT` for a real index row.
  Verified: `check-links`, `docs-check`, `gen-api-check`, `docs-build --strict`,
  full test suite. Trace: `sdd/traces/BK-285-api-docs-async-mirror.yml`.

- [x] **BK-259 — Graph `_range_fallback_paths` flag: scope to drive, self-heal, not backend-lifetime per-path set**
  spec: GR-015 · effort: S · audience: user.api, library.maintainer
  The per-instance `set[str]` of range-failed paths grew unbounded, never
  cleared, keyed on the raw caller string (so `"/x"` and `"x"` diverged), and
  reported a stale `extra["graph.read.range_fallback"]` long after the read
  that set it (audit-016 L2 / PR #760 review). Resolved with **solution-space
  option 1 + 3** (self-heal + spec align), landed as a single drive-scoped
  tri-state rather than a still-growing per-path set: range capability is a
  tenant/drive property, so `GraphBackend` now tracks one `_range_capable:
  bool | None` (None = untested, True = a `206` honoured Range, False = the
  drive ignored/rejected it). `stream_range` gained an `on_range_success`
  callback (mirroring `on_fallback`) that fires on a `206`, so a later honoured
  ranged read clears the mark; `get_file_info` flags `FileInfo` while the mark
  is False. This is O(1) (no per-path growth), self-healing (no stale flag),
  and kills the raw-string-key divergence (no path keys at all). GR-015 was
  amended: the marker is now documented as a drive-scoped, self-healing hint
  surfaced on a subsequent `get_file_info`, not an operation-scoped marker on
  the read — with native-async observability (tracked as ID-217, the deferred
  async-native `ext.*` surface) named as the eventual home for a true
  operation-scoped `StoreEvent.metadata` signal; building it was explicitly
  deferred to ID-217 rather than taken on here. Tests: drive-scope (flag rides
  a *different* path's `get_file_info`)
  and self-heal (a `206` clears the stale flag) added to
  `tests/backends/graph/aio/test_transfer.py`. Trace:
  `sdd/traces/BK-259-range-fallback-drive-scope.yml`.

- [x] **ID-179 — Trace schema validator: jsonschema-validate every trace in `hatch run lint`**
  spec: — · effort: S · audience: contributor.tooling, contributor.process
  `sdd/traces/_schema.yml` declared the trace shape (`audience` required,
  id/phase patterns, `additionalProperties: false`) but nothing validated a
  trace at commit time — BK-193 left enforcement as an authoring convention
  pending an aggregator that never landed, so drift accumulated unnoticed.
  Added `scripts/check_traces.py`, which `jsonschema`-validates every
  `sdd/traces/[!_]*.yml` against the *whole* schema (draft selected from the
  schema's `$schema` keyword), plus two self-checks: the schema itself via
  `check_schema`, and every entry in the schema's `examples` block (a JSON
  Schema annotation jsonschema never validates on its own). Wired into the
  `lint` hatch script list; the CI `lint` job picks it up automatically via
  `uvx hatch run lint` (single-source delegation, BK-269), satisfying the
  dual-wire convention without a second listing. Fixed three pre-existing
  violations the new gate surfaced: hyphenated phase ids in
  `bk-284` (`implement-pr2`/`verify-pr2`) and `id-195` (`prior-art`) →
  snake_case per the `^[a-z][a-z0-9_]*$` pattern, and a disallowed top-level
  `notes` field in `bug-197` (relocated the worktree caveat into the
  `verify_replay` step extract). Added `jsonschema>=4.18` to dev deps and
  `tests/scripts/test_check_traces.py`. No CHANGELOG
  (contributor.tooling / contributor.process, no `user.*` audience). Trace:
  `sdd/traces/ID-179-trace-schema-validator.yml`.

- [x] **BK-268 — File the deferred Graph async-ext follow-ups (backlog hygiene)**
  spec: GR-003 · effort: S · audience: library.maintainer, contributor.process
  Audit-016 L10 flagged two promised async-ext follow-ups with no tracked owner.
  Both are now filed (the audit's "file or explicitly decline" resolved toward
  *file*, since each is a legitimate deferred improvement, not a dead promise):
  - **ID-217 — Async-native extension surface.** Owns GR-003's promised "async
    equivalent of `ext.glob`" and broadens it to the whole deferred async `ext.*`
    cliff (glob / observe / otel / integrity; audit-016 M6) — a native
    `AsyncStore` consumer reaches `ext.*` only via `AsyncBackendSyncAdapter`,
    forfeiting async streaming. Decision (build vs. formally decline) left to
    scoping.
  - **ID-218 — `ext.cache` warn over a bridged backend.** Owns ADR-0025 § Risks'
    promised guard: `CachedStore` with unset `max_content_size` over an
    async-native backend silently materialises what the backend exists to stream.
  Closing the loop on the source side: GR-003 now cites ID-217 instead of "a
  separate backlog item", and ADR-0025 § Risks cites ID-218 instead of "(tracked
  separately)" — so neither promise dangles. The named async-ext surface
  (glob / observe / otel / cache / integrity) now has owners: glob / observe /
  otel / integrity under ID-217, the sync-cache guard under ID-218. No code, no
  spec-behaviour change, no CHANGELOG (library.maintainer / contributor.process,
  no `user.*` audience). Trace: `sdd/traces/BK-268-file-deferred-async-ext-followups.yml`.

- [x] **BUG-215 — Mutation run goes red on a scope with zero mutation candidates**
  spec: — · effort: S · audience: infra.ci, contributor.tooling
  The weekly `[mutation]` run opened the rolling issue for `ext-glob` with
  "job was green but wrote no gremlins JSON report (reporting half broke)".
  Root cause: `src/remote_store/ext/glob.py` has zero mutation candidates under
  pytest-gremlins' operator set (no arithmetic / boolean / comparison /
  boundary operator, no literals, only a value-less `return`), so the plugin
  returns from `pytest_terminal_summary` *before* the report write (plugin.py
  `if not gremlin_session.gremlins: ... return`). `mutation_report.py record`
  treats a green leg with no `coverage/gremlins/gremlins.json` as a silent
  reporting break (counts `None` → harness failure), which fires the issue and
  reddens the leg — a scope with nothing to mutate would stay red forever.
  Not a regression in glob.py and not silenceable per the `/mutation` skill
  (skip / filter / pardon are forbidden), so the fix lives in the harness:
  `scripts/run_mutate.py` now synthesises the canonical all-zero report the
  plugin would write for an empty score, but only when the scope is positively
  confirmed to have zero candidates via pytest-gremlins' own `transform_source`
  (so it can never drift from what the plugin counts). The genuine break case —
  gremlins exist but no report — still leaves the file absent and fails the leg,
  preserving the original guard. `record`/`classify_scopes` are unchanged: an
  all-zero report classifies `ok`. No CHANGELOG (infra.ci / contributor.tooling,
  no `user.*` audience). Trace: `sdd/traces/bug-215-mutation-zero-candidate-scope.yml`.

- [x] **BK-267 — Graph test hardening**
  spec: GR-012, GR-040 · effort: S · audience: infra.test, contributor.process
  Closed the three respx-tier gaps audit-016 L7 / G5 flagged in the Graph
  backend's sole automated coverage:
  - **read() first-iteration timing**: `test_folder_raises_before_yield` and
    `test_missing_raises_not_found` wrapped the whole `async for` in
    `pytest.raises`, so they would pass whether the raise fired on the first
    `__anext__` or after partial yields. Strengthened both in place to collect
    yielded chunks and assert the list stayed empty — pinning that the
    folder→`InvalidPath` / missing→`NotFound` raise fires before any byte (and,
    for the missing case, before the download URL is reached; that route is
    left unmocked). To make this a contract rather than an implementation
    accident, **GR-012 gained an `Ordering` invariant** stating the
    metadata-fetch and directory check precede the body stream; the tests trace
    to it. (PR #799 review flagged that an earlier draft *added* two
    `__anext__`-driven tests alongside the originals, strictly subsuming them —
    replaced-in-place instead, net 2 tests not 4.)
  - **write_atomic failure path**: it had only a delegation test
    (`test_write_atomic_delegates_to_write`). Added a direct failure-path test
    (409→`AlreadyExists` naming the path) so the public method carries its own
    `pytest.raises` per TESTING.md Rule 1, not only transitive coverage via
    `write`.
  - **per-method 403→`PermissionDenied`**: the mapping was exercised only
    centrally at `graph_send` / `classify_graph_error`. Added per-method guards
    on `get_file_info`, `read`, and `write` pinning that the centralised
    mapping reaches the public data-plane methods unchanged.
  No CHANGELOG: the GR-012 amendment documents an already-shipped guarantee (the
  `read()` docstring already promised it), not new behaviour or a new spec.
  Trace: `sdd/traces/bk-267-graph-test-hardening.yml`.

- [x] **BK-283 — Drive the Graph example snippet from replayed cassettes in CI**
  spec: GR-015, GR-019 · effort: S · audience: infra.test
  `examples/backends/graph_backend.py` was the one published snippet with zero
  CI execution: live-credentials-only, excluded from the `run_examples.py`
  sweep, no emulator. Shipped as Option B of the settled design
  ([research-bk-283-example-replay-design.md](research/research-bk-283-example-replay-design.md),
  PR #795) rather than the item's `run_examples.py` sketch (sketches are
  advisory): one parametrized `runpy` test in
  `tests/backends/conformance/test_examples.py` whose param ids `graph_live` /
  `graph_replay` inherit the entire cassette stack — per-backend dir routing,
  the shared cassette name, the `GRAPH_PROFILE` record/replay scrub configs,
  the missing-cassette skip, and `--record`-mode vcr marking — with zero
  conftest or `record_cassettes.py` changes; the recorder's `-k graph_live`
  sweep records (and a full `record-graph` regenerates) the example cassette
  alongside the conformance corpus. The test is an executable-documentation
  guard asserting the script's stdout (including one line of demonstrated
  file content), not backend coverage — every layer it traverses is
  contract-covered elsewhere. On replay a `_StubGraphAuth` with a call
  counter replaces MSAL (a silent fall-through to the real device-code flow
  fails loudly); the cassette's recorded token-exchange interactions stay
  inert under `record_mode="none"`, verified on first replay. Live-param
  hygiene best-effort-purges the drive's `remote-store-example` folder before
  and after the run, mirroring `graph_live._aclose`. `run_examples.py` keeps
  its credential-free subprocess scope (docstring pointer added). Carried
  forward from BK-262; no CHANGELOG (infra.test, BK-262 precedent). Trace:
  `sdd/traces/bk-283-example-replay.yml`.

- [x] **BK-261 — Graph small-write `overwrite=True`: replace-returns-409-for-files quirk**
  spec: GR-018 · effort: S · audience: user.api, library.maintainer
  Disposition: **documented as a hard backend limitation**, not guarded. On the
  small-file `PUT /content` replace path, some SharePoint-backed drives return
  `409 nameAlreadyExists` for a *file* even under
  `@microsoft.graph.conflictBehavior=replace`, which the BE-008 409 discrimination
  surfaces as `AlreadyExists` — a spurious overwrite failure. The guard disposition
  needs a live SharePoint-backed reproduction to confirm the exact 409 body, and
  this project's live tier is consumer-only / device-code, so it stays blocked; a
  speculative guard would guess the body shape blind and risk masking a genuine
  conflict. GR-018's known-limitation note promoted from a v1 deferral to a settled
  hard-limitation statement (with the delete-then-write workaround), the GR-027
  `parentReference` cross-reference repointed off the BK-261 anchor, and the Graph
  user guide gains a SharePoint overwrite caveat. No change to `_write_small`; the
  existing `AlreadyExists` mapping is now the contracted behaviour. Trace:
  `sdd/traces/bk-261-graph-overwrite-409-limitation.yml`.

- [x] **BK-266 — Graph backend correctness edges**
  spec: GR-031, GR-044, GR-006 · effort: S · audience: user.api, library.maintainer
  Audit-016 L1 / L3 / M7, three independent fixes shipped together:
  - **L1**: `classify_graph_error` gained a `"probe"` scope; `exists` /
    `is_file` / `is_folder` request it via `_get_item(scope="probe")`, so any
    404 — including a drive-identity `resourceNotFound` — maps to `NotFound`
    and is suppressed to `False` (BE-004/BE-005). Diverged from the item's
    literal "scope the mapping to drive scope" sketch per the audit-authority
    principle: no call site ever passes `scope="drive"`, so `resourceNotFound`
    is the *only* drive-identity signal and the write path deliberately relies
    on it (`_write_small` routes its 404 back through the classifier); a
    strict drive-scope-only mapping would have regressed deleted-drive writes
    from `BackendUnavailable` to `NotFound`. Error-raising operations keep the
    escalation; GR-031 amended to authorise both halves.
  - **L3**: `_short_circuit_self_op` compares `native_path(src) ==
    native_path(dst)` instead of raw strings, so direct-backend
    `copy("/a.txt", "a.txt")` short-circuits per GR-044 instead of POSTing and
    surfacing `AlreadyExists`. GR-044 postcondition added.
  - **M7**: the bundled `GraphAuth.get_token` raises typed `PermissionDenied`
    (`backend="graph"`) instead of stdlib `PermissionError`, keeping MSAL's
    `error_description` and never the secret; GR-006 postcondition added. The
    device-flow-start `ValueError` (`auth.py`) is deliberately kept — it is a
    config-shaped failure mirroring `__init__`'s `ValueError`s, and M7 scoped
    the finding to the no-token path.
  Trace: `sdd/traces/bk-266-graph-correctness-edges.yml`.

- [x] **BK-265 — Graph guide & docstring accuracy**
  spec: GR-058, GR-001 · effort: S · audience: user.site, user.api_docs
  Audit-016 M4 / M5 / M6 / L5 / L6 / L9. `graph-setup.md` rewritten to present
  tense; the shipped `GraphUtils.resolve_drive_id` route now leads the
  drive-id section and the hand-rolled `msal`/`httpx` snippet is reframed as
  the no-install alternative. `graph.md`'s headline Usage snippet became a
  runnable `asyncio.run(main())` program using `await aresolve_drive_id`
  (the sync resolver runs its own event loop and raised `RuntimeError` on
  copy-paste), with sync-vs-async resolver guidance in the drive-id section.
  Added an "Extensions: sync vs async" matrix (native `AsyncStore` has only
  `aio.ext.write.write_with_hash`; the `ext.*` suite reaches Graph only via
  `AsyncBackendSyncAdapter`), a consumer-OneDrive verification admonition
  plus a "SharePoint-backed drives are less exercised" caveat, and read-side
  `TMPDIR` spooling for `read_seekable` / arrow / parquet reads. Completed
  `Raises:` clauses on `GraphBackend` public methods — `PermissionDenied`
  everywhere it can surface, `BackendUnavailable` made consistent across
  read/list/info/delete/copy/move.

- [x] **BK-264 — Graph spec / RFC reality-sync**
  spec: GR-001, GR-005, GR-018, GR-019, GR-034 · effort: S · audience: library.maintainer, contributor.process
  Swept `sdd/specs/044-graph-backend.md` + `rfc-0010` where they lagged shipped
  code (audit-016 M1/M2/M3/L4/L6/H2). GR-018/GR-019 now state `WriteResult.size`
  is the byte count the backend wrote (the WR-003 contract) while
  `etag`/`last_modified`/`version_id` still come from the returned `driveItem`
  body — the spec was the less-authoritative side per principle 5; the GR-003
  `WRITE_RESULT_NATIVE` rationale carries the same size exception. `base_path`
  (GR-058) joined the GR-001 signature block and the GR-005 validation list,
  and the RFC's Addressing section + spec-range note now mention it. The
  Integration-only section and RFC Stage 3 describe the shipped live tier:
  device-code / consumer, three env vars (no `GRAPH_CLIENT_SECRET`), opt-in
  absent → skip, opt-in with a missing var → fail loud. GR-034 drops the
  nonexistent "Retry-After propagated via the error's context" surface in
  favour of the in-loop honouring GR-048 states (RFC Throttling aligned). A
  new coverage-disclosure paragraph records that the integration tier never
  runs in automated CI and that all live exercise — that tier plus the BK-262
  cassette recordings driving Stage-1 replay — is consumer-OneDrive-only, with
  no SharePoint/business coverage. The audit predated BK-262, so its
  "conformance matrix is skip-only" disclosure was re-evaluated: the matrix
  now replays in default CI and the disclosure says so instead. One ripple
  beyond the item's `sdd/`-only framing: the `test_integration.py` module
  docstring claimed "four" credential vars against its own three-var fixture
  and cited the spec section by raw line numbers — both corrected. No
  CHANGELOG (no `user.*` audience). Audit-016 M1 / M2 / M3 / L4 / L6 / H2.
  Trace: `sdd/traces/bk-264-graph-spec-reality-sync.yml`.

- [x] **BK-284 — Cassette recording layer redesign: backend-agnostic core + REC-NNN spec**
  spec: REC-001..REC-008 (new spec 049) + TEST-007 cross-link · effort: L · audience: infra.test, library.maintainer
  `tests/backends/fixtures/_cassettes.py` had grown two parallel hand-rolled
  scrub stacks (Azure-first, Graph by accretion): four body-scrub lists with
  no audit identity, Azure helpers in the shared module, hand-rolled header
  scrubs where vcrpy ships native filters. Shipped as the planned two PRs.
  **PR 1 (#791):** request-header deletes + the User-Agent rewrite migrated
  to vcrpy-native `filter_headers` (tuple form rewrites-never-adds;
  capitalised key keeps re-records byte-identical); security-gate tests
  reworked onto vcrpy's composed pipeline; live `--verify-only` + single-node
  byte-identity dogfood on both backends proved equivalence. Divergence from
  the filing sketch on empirical grounds: `filter_post_data_parameters`
  rejected — vcrpy 8.1.1 re-serialises every `application/json` POST body
  even on no match, churning the security-review diff — so the OAuth POST
  scrub stays a named bytes regex (and is therefore audit-visible).
  **PR 2:** the module rewritten as the backend-agnostic core —
  `RedactPattern` / `UriRewrite` / `EnvRedact` named rules with
  required-to-fire/opportunistic expectations, `PresignedPolicy`, one frozen
  `CassetteProfile` per family (`_cassettes_azure.py` / `_cassettes_graph.py`),
  one generic `build_profile_vcr_config` — registered via
  `BackendFixture.cassette_profile` as the single registration act (the
  conformance conftest derives directory routing, name aliases, the
  missing-cassette skip, and the scrub config from the registry; fail-loud
  guards intact). Forbidden markers split into `FORBIDDEN_ENVELOPE` +
  per-profile additions, consumed identically by the recorder's Step-4 gate
  and a creds-free CI sweep generalised over every profile's committed tree
  (the Azure corpus now swept too). Step-4 gained the named-rule audit: the
  core counts per-rule fires, the conformance session dumps a manifest, and
  required-to-fire rules fail at zero (skipped in `--verify-only`/`--node`).
  The X-AnchorMailbox gap the PR-1 dogfood surfaced is closed three ways:
  hyphen-split cid form in the Graph `EnvRedact.forms`, a native
  `x-anchormailbox` delete, and an oid-anchor envelope marker. Expectations
  calibrated against the corpus before wiring (uploadUrl and the Azure
  body-filesystem rule demoted to opportunistic — zero-hit on the recorded
  slice). Spec 049 (REC-001..REC-008) carries the invariants; spec-only
  per review discussion — the layer sits beneath ADR-0028's threshold, so
  design rationale lives in the clauses, not a separate ADR. The
  unchanged corpus was the oracle throughout: full Stage-1 replay green with
  zero cassette diffs, and the #787 review hardening survives as profile
  declarations. CHANGELOG N/A (audience `infra.test`). Trace:
  `sdd/traces/bk-284-cassette-recording-redesign.yml`.

- [x] **BK-274 — Dependabot approval is the only gate before auto-merge to `master`, with no codified criteria**
  spec: — · effort: S · audience: library.maintainer, infra.ci
  `dependabot-auto-merge.yml` fired `gh pr merge --auto --squash` on any
  maintainer approval, for both ecosystems — for github-actions bumps a green
  check means "the workflow parsed", not "the action behaves" (nothing in the
  test suite exercises a bumped action), so approval was a rubber-stamp path
  straight to `master` (#766). Took audit-018 A2's strongest option — a
  **control, not a runbook**: the workflow's job condition now excludes the
  `github-actions` ecosystem via its head-ref prefix
  (`!startsWith(head.ref, 'dependabot/github_actions/')`, prefix verified
  against a live actions-bump PR); those PRs are merged manually
  (`gh pr merge <N> --squash --delete-branch`) after the changelog +
  `with:`/permissions checklist. `pip` keeps approve-to-merge: its bumps are
  exercised by the suite, so the approval has a real signal, and the
  red-CI "real ceiling vs transient" triage stays codified in the
  [`sdd/CI-OPERATIONS.md`](CI-OPERATIONS.md) dependabot runbook (per the
  BK-275 handbook, no standalone doc). The control is pinned by
  `tests/scripts/test_dependabot_automerge_control.py` so a workflow refactor
  cannot silently restore auto-merge for actions. A `/deps` skill is
  deferred per A4 — the surviving triage is a checklist, not a multi-step
  procedure; promote only if it proves otherwise. The optional label gate
  from A2(c) was not adopted: with the actions path removed, pip approval is
  already a deliberate, signal-bearing step. No CHANGELOG (no `user.*`
  audience). Audit-018 M1. Trace:
  `sdd/traces/bk-274-dependabot-automerge-control.yml`.

- [x] **BK-273 — `mutation` testing produces no durable TODO; failures reach the maintainer by email only**
  spec: — · effort: M · audience: library.maintainer, infra.ci
  `mutation.yml` let its jobs fail with no durable surface: a red X plus
  GitHub's actor email was the entire notification path — exactly how the
  weekend implementation failure (#763) surfaced. Resolved audit-018's
  C-DECISION on run-history evidence (A3): across the scheduled Saturday runs
  on record, every failure was a **harness/implementation break** (a timeout
  cascade ending in "no tests ran", a setup `ModuleNotFoundError`, a plugin
  INTERNALERROR) and **never a surviving mutant** — pytest-gremlins has no
  fail-on-survivor mechanism, so survivors never turn a run red and were never
  actioned as TODOs. Shipped accordingly: **harness failure → rolling
  `[mutation]` issue AND red run** (the leg keeps propagating pytest's exit
  code); **surviving mutants → advisory only** (run stays green, counts in the
  run-summary table + HTML artifacts, never the issue) — a recorded divergence
  from drift-guard's never-red model. Each `mutate-<scope>` leg now records a
  per-scope outcome JSON (`job.status` + `--gremlin-report=json` counts, since
  `job.status` alone cannot see survivors — audit-018 L2), and the `summary`
  job runs `scripts/mutation_report.py reconcile`: create/update on any
  harness failure (including a dead `setup` with no scope list), comment-and-
  close on a healthy **full** run; a single-scope dispatch never closes (a
  deliberate tightening of `drift_report.py`'s regenerate-everything
  semantics). Lifted drift-guard's single-writer `concurrency` guard and
  least-privilege `permissions` deliberately per A5. Added the
  `/mutation` triage skill and flipped the `mutation.yml` row + runbook in
  [`sdd/CI-OPERATIONS.md`](CI-OPERATIONS.md); `check_ci_inventory` keeps the
  row honest. No CHANGELOG (no `user.*` audience). Audit-018 H1 / L2.
  Trace: `sdd/traces/bk-273-mutation-issue-surface.yml`.

- [x] **BK-275 — CI-operations handbook + the scheduled-guard consistency principle**
  spec: — · effort: S · audience: library.maintainer
  No document inventoried the scheduled/automated workflows; the knowledge lived
  only in one guard's docs (`/drift` + `drift-guard.yml` header + `CONTRIBUTING §
  Dependency drift guard`). Shipped [`sdd/CI-OPERATIONS.md`](CI-OPERATIONS.md) as
  the authority doc: the durable-TODO principle (every scheduled-maintenance guard
  emits a durable GitHub Issue + has a triage entry point; email / red-X /
  green-check are insufficient alone), the family inventory table, and
  `codeql.yml`'s Security-tab surface recorded as a deliberate exception. Per
  audit-018 A1, the inventory is kept honest by a lint gate rather than prose:
  `scripts/check_ci_inventory.py` parses `.github/workflows/*.yml` for the family
  triggers (`on.schedule` / `on.pull_request_review`) and fails if a family
  workflow is absent from the handbook. Diverged from the pre-agreed in-script
  exceptions allowlist: the gate verifies documented *presence*, so `codeql.yml`
  passes by being named in the handbook's Exceptions section — a separate in-script
  allowlist would duplicate that single source (principle 4). Existing guards
  (`/drift` skill, `drift-guard.yml` header, `CONTRIBUTING § Dependency drift
  guard`) now point at the handbook. BK-273/BK-274 will upgrade the `mutation` and
  dependabot rows from "partial" to the rolling-issue + triage shape. Audit-018 M2
  / L1. Trace: `sdd/traces/bk-275-ci-operations-handbook.yml`.

- [x] **BK-262 — Graph conformance cassettes: replay-able pre-signed URLs**
  spec: GR-015, GR-019 · effort: M · audience: infra.test
  ID-127 GR-DONE recorded the Graph conformance suite live (green) but never
  committed the cassettes, and `record_cassettes.py` kept graph
  `min_cassettes=0`, so the cross-backend conformance spine **skip-cleaned** for
  Graph in CI. The blocker was a redaction *format* bug, not a security
  weakening: the GR-035 scrub redacted `@microsoft.graph.downloadUrl` and the
  upload-session `uploadUrl` to the bare string `"REDACTED"`, which is not a URL
  — on replay the backend reads it back and issues `GET :///REDACTED`, no
  cassette matches, and the read/write slices fail. Fix: redact every
  pre-signed-host URL (downloadUrl / uploadUrl / copy-move monitor `Location`)
  to one **valid placeholder URL** (`https://graph-download.invalid/REDACTED`)
  consistently in the response body, the `Location` header, **and** the recorded
  pre-signed-host request URI. `before_record_request` runs on record *and*
  replay, so the request the backend re-issues from the scrubbed body/header
  normalises to the same placeholder and vcrpy matches it. The first live
  recording then exposed a PII leak the prior scrub never covered: the
  case-sensitive `drive_id` replace of the lower-cased env value missed the
  UPPER-cased cid Graph echoes inside item ids / eTags / webUrls, and
  `createdBy` / `lastModifiedBy` carried the account email + displayName + a
  `siteId`, and the async copy/move monitor `Location` embedded the cid and the
  long `b!…` drive id in its **path** (not query). Closed all three: the
  `drive_id` rewrite is now case-insensitive (every casing → one `FAKE_DRIVE_ID`
  so eTag/id self-comparisons still match), an identity/site key scrub blanks
  `email` / `displayName` / `userPrincipalName` / `loginName` / `siteId` (none
  read by the backend or asserted by conformance; the load-bearing item `name`
  shares no key so survives), and a pre-signed-host `Location` collapses whole
  to the placeholder. PR review then caught a fourth leak the body scrub could
  not reach: the `docID` response header
  (`microsoftpersonalcontent.com_<site-guid>_<doc-guid>`) carried the same site
  GUID in 26 cassettes — dropped the whole header (the backend never reads it).
  Hardened the recorder to match: `min_cassettes` `0 → 100` (full slice records
  118, headroom for capability skips), the Step-4 scrub-verify is now
  case-insensitive (it caught the upper-cased cid the case-sensitive check had
  missed), and Step-4 additionally asserts env-independent `forbidden_patterns`
  (bare `Bearer`, the `docID` site-GUID host form, the long `b!…` id) so a
  re-record cannot silently reintroduce them. A second review round hardened
  the redaction guarantee further: the pre-signed branch now rewrites the
  `Host` request header to the placeholder host (the live URI was redacted but
  the live content host — tenant-identifying on a business drive — survived
  next to it) and scrubs the request body before its early return (an OAuth
  exchange against an auth host outside the API allow-list would otherwise
  commit the credential form verbatim); the per-request correlation/diagnostic
  response headers (`x-ms-request-id`, `x-ms-ests-server`, SharePoint/CDN ids)
  are dropped for parity with the Azure profile and stable re-record diffs; and
  the leak markers moved to one shared `GRAPH_FORBIDDEN_CASSETTE_PATTERNS`
  constant — expanded to JWT, tenant SharePoint host, credential form fields,
  identity keys, and bare email — asserted by **both** the recorder's Step-4
  gate **and** a new creds-free CI sweep over the committed tree, so the
  guarantee no longer rests on a one-time manual grep. The new JWT marker then
  earned its keep on re-record: it caught a *real* leak the prior process had
  committed only by luck — when MSAL refreshes mid-suite (a warm token cache hid
  it before), the OAuth token response carries an `id_token` (JWT) and
  `client_info` (base64) whose payloads embed the account email / tenant id / an
  `oid` holding the cid, none caught by the drive-id or email scrubs because they
  are base64-encoded. All four token-response fields are now redacted wholesale
  (replay is unaffected: the replay backend uses a constant stub token).
  Recorded 118 cassettes
  (PII-swept clean: zero cid / `b!` id / email / siteId / Bearer / docID GUID);
  `graph_replay` Stage-1 runs 109 passed / 9 capability-skips / 0
  missing-cassette. No CHANGELOG (infra.test). Consolidated the former BK-260;
  the example-test replay extension is carried forward as BK-283. Trace:
  `sdd/traces/BK-262-graph-cassettes.yml`.

- [x] **BK-282 — Forward CLI args through the `gen-*` hatch script targets**
  spec: — · effort: S · audience: contributor.tooling
  The bare generator targets (`gen-graph`, `gen-features`, `gen-graph-viz`,
  `gen-backlogid`) were defined as plain strings with no `{args}` placeholder, so
  `hatch run gen-backlogid --check` (and the equivalent for the others) **dropped
  the `--check`** and ran the script in **write mode** — printing `Updated …` and
  verifying nothing. Harmless when already in sync (identical bytes, no git diff),
  but a silent write-instead-of-verify if the artifact had drifted. The repo had
  worked around this with dedicated `gen-*-check` siblings (the canonical lint
  targets, called directly in `preflight`/`lint`), but the bare-target footgun
  remained for anyone typing the natural `--check` form. Fix: add `{args}` to all
  four bare targets (mirroring the existing `drift-check = "… {args}"` precedent),
  so the flag forwards. Non-breaking — bare invocation still runs write mode
  (empty `{args}`), the `gen-*-check` targets and the direct-script composite
  lists are untouched. Applied uniformly across all four to keep the paired
  pattern consistent. No CHANGELOG (contributor.tooling). Surfaced during BK-272
  verification (PR #785). Trace: `sdd/traces/bk-282-gen-args-forwarding.yml`.

- [x] **BK-272 — Resolve the dead mypy pre-push hook**
  spec: — · effort: S · audience: contributor.tooling, contributor.process
  `.pre-commit-config.yaml` declared a mypy hook gated `stages: [pre-push]`, but
  the config had no `default_install_hook_types` and no doc mentioned
  `--hook-type pre-push`, so the documented `pre-commit install` wired only the
  `pre-commit` stage — the hook never fired on `git push`. Type-checking already
  runs via `hatch run typecheck` (inside `hatch run all`, the documented local
  gate) and the CI `typecheck` job, so this was dead config, not a correctness
  hole. Took audit-017 R5's second option (**drop** the hook) over the first
  (add `default_install_hook_types: [pre-commit, pre-push]`): the audit-017 epic
  was a consolidation story (BK-269/270/271 collapsed three divergent "lint"
  definitions into one), so adding a *third* local mypy surface beside `hatch run
  all` and CI runs against that grain — and the hook's hand-synced
  `additional_dependencies` stub list was a standing staleness vector that only
  existed to serve it. Dropping it removes both with zero contributor-facing
  change (the hook never fired and no doc promised it) and no slower `git push`.
  No CHANGELOG: audience is contributor.tooling / contributor.process, neither of
  which trips the trace-schema derived rule. Audit-017 R5 (M4). Trace:
  `sdd/traces/bk-272-dead-mypy-pre-push-hook.yml`.

- [x] **BK-271 — `/pr` and `/fix-pr` compose hatch targets instead of re-encoding gate logic**
  spec: — · effort: M · audience: library.maintainer, contributor.process
  The gate logic was already deduplicated into one shared reference section
  (`sdd/CLAUDE-REFERENCE.md#pr-validation-gates`) both skills call — but that
  shared gate was a hand-rolled gate that re-encoded a subset of CI: `/pr` ran
  neither `hatch run lint` nor `all` (so it could open a PR failing any of the ~13
  `lint` checks — `check_mock_spec`, `check_spec_marks`, `check_formal_trace`,
  `check_no_tracker_refs`, …) (M1), and its coverage step keyed on
  `src/`/`tests/`/`examples/` sent a docs/spec-only diff to `hatch run test` — the
  least-relevant gate — while skipping `lint`, the relevant one (M2). Replaced the
  hand-rolled gate with a mechanical gate composed from existing hatch targets that
  follows CI's code-vs-docs split: a diff touching the test-bearing and
  interpreter-defining members of CI's `CODE_PAT`
  (`src/`/`tests/`/`examples/`/`scripts/`/`pyproject.toml`/`.python-version` —
  `scripts/` included because its guards live under `tests/scripts/`) runs
  `hatch run all` (the full superset); any other diff (docs / specs / skills /
  config) runs `hatch run lint` + `hatch run docs-gate` — lint (the gate `/pr`
  skipped) plus the strict mkdocs build, link scan, and version-drift check, but
  not the test suite / examples / notebooks a non-code change does not exercise.
  This keeps the local pre-PR gate no heavier than CI (which path-filters the same
  way and was praised for it in the audit), composes targets rather than re-encoding
  checks, and routes each change type to its *relevant* gate. Two gates sit beside
  the mechanical one because no hatch target covers them: the local-machine-reference
  grep (no `check_*` script enforces it) and a thin qualitative TESTING/CONTENT
  review (assertion depth, mock discipline, prose longevity are not mechanized).
  The skill gate uses `test-cov-s1` (via `all`), not `test-cov-strict`, so it
  carries no local Azurite dependency — the 95% strict floor stays CI/publish-only
  by design. Diverges from audit-017 R3's literal prescription (advisory per the
  Audits rule) in two ways: R3 said to *drop* the per-type branch and collapse to a
  single `hatch run all`, and — where a lighter fast-iteration gate was wanted — to
  "document **one** thin target … but only one." This design keeps a (CI-mirroring)
  branch and uses two existing targets for the non-code path. The branch earns its
  keep by making the local gate no heavier than CI without skipping relevant checks
  (M1 / M2). The two-target choice over R3's "but only one" is deliberate: no single
  existing target spans both the `lint` check-family (spec / docs / trace scripts)
  and the `docs-gate` build / link / drift family, and minting a new composite would
  duplicate what `lint` + `docs-gate` already express — against the audit's own
  compose-don't-add north star. Net: fixes the diagnosed pain without billing every
  doc/spec PR the full ~4-minute superset.
  Audit-017 R3 (M1 / M2 / L2). Trace: `sdd/traces/bk-271-skills-delegate-hatch-all.yml`.

- [x] **BK-281 — Reap adapter daemon thread in close-timeout tests (BK-276 residual loop leak)**
  spec: — · effort: S · audience: infra.test
  BK-276/ID-217 fixed the teardown-time unclosed-`ProactorEventLoop` flake but a
  residual leak recurred under bounded-worker `test-cov-strict` (non-deterministic
  `PytestUnraisableExceptionWarning: unclosed event loop`, cross-attributed by
  xdist to innocent nodes — azure-aio HNS, s3_boto3_moto). Tracemalloc traced the
  real owners to `tests/aio/test_async_to_sync_adapter.py`: the failure-path tests
  that drive `AsyncBackendSyncAdapter.close(timeout=…)` against a hanging
  `aclose()`. By design `close()` schedules the loop stop and returns *before* the
  daemon thread runs its `finally: loop.close()` — the loop is "left for
  process-exit reaping" — so the private `ProactorEventLoop` lingers
  non-running-and-unclosed in the gap between `close()` returning and the thread
  winding down. Under load that gap widens enough for the cyclic GC to collect it
  and fire the warning. The BK-276 per-test sweep cannot catch it: at the
  offending test's own teardown the loop is still winding down (`is_running()`),
  so the sweep spares it (the documented adapter-daemon carve-out in
  `tests/_helpers.py`). Fix is test-hygiene, not product: a shared
  `_reap_adapter` helper joins the daemon thread so the loop closes
  deterministically before each such test returns; applied to the three
  `_HangingAsyncBackend` close-timeout sites and folded in the one test that
  already hand-rolled the join. Verified by re-running the tracemalloc
  leak-detector over `tests/aio` + `tests/backends/{s3,azure/aio}`: distinct
  abandoned loops went 2 → 0. Not a product defect — the `close(timeout)`
  abandonment is intentional, documented behavior for a genuinely-hung backend.

- [x] **BK-270 — Route `sdd/specs`-only and docs-only changes through their gates**
  spec: — · effort: S · audience: library.maintainer, infra.test
  The CI `setup` path filter (`CODE_PAT`) did not match `sdd/`, so a `sdd/specs`-only
  PR **skipped the entire `lint` job** — `check_spec_marks` (spec ↔ test-mark drift,
  BK-251) and `check_formal_trace` (spec ↔ Dafny ↔ test, ID-206) ran in neither CI
  nor commit. Separately a docs-only PR (`docs-src/guides/*.md`) ran only
  `check_docs_framework` + `mkdocs build --strict` in the `docs` job, skipping
  `check_no_tracker_refs` (the gate built for guide prose), `check_links`, and
  `drift_check render-docs --check` (the last in no PR CI lane at all). Both fixes
  route *existing* gates to the change types they validate; no new gate. For specs,
  wired `check_spec_marks` + `check_formal_trace` into the `verify-formal` job
  (which already triggers on `^sdd/specs/` via `FORMAL_PAT` and already runs a
  stdlib check, `check_capability_parity`) rather than widening `CODE_PAT` — the
  latter would fire the whole code matrix (test ×5, typecheck, e2e, …) on a
  markdown-only PR, against the path-filter design's own intent. These two run
  inline as `python3 scripts/…` alongside the pre-existing `check_capability_parity`
  (no `uv`/`hatch` setup in that Dafny job). For docs, the `docs` job now delegates
  to a single combined hatch target, `docs-gate` (`docs-check` +
  `check-no-tracker-refs` + `check-links` + `drift-docs-check` + `docs-build`), via
  `uvx hatch run` — extending BK-269's "CI calls hatch, pyproject is the single
  source" pattern rather than hand-listing scripts. Audit-017 H2 / M3 / M5. Trace:
  `sdd/traces/bk-270-route-spec-docs-gates.yml`.

- [x] **BK-280 — CI build improvements: split tooling tests off `test-primary` + single-source the priority Python**
  spec: — · effort: S · audience: infra.ci, contributor.tooling
  Two CI-build changes, no runtime impact.
  **(1) `tooling-tests` job.** `test-primary` (the longest job) ran `pytest
  tests/scripts/ -q` as a third serial pass behind `start-backends` + the two
  coverage passes, though those tests hit `scripts/`, not `remote_store` — no
  backends, no coverage. Moved to a backend-free job that runs in parallel,
  trimming ~34s off the critical path. Reinstates the standalone job BK-207 had
  before a roll-up merged it into `test-primary`.
  **(2) `.python-version`.** New root file is the single source for the priority
  Python across CI, replacing the hardcoded literals (BK-219 removed ~12 from
  `ci.yml`; this removes the last one plus the copies in `publish.yml`,
  `docs.yml`, `mutation.yml`, `drift-guard.yml`). `ci.yml`'s `setup` reads it to
  resolve the matrix's primary slot (with a `jq` guard that fails if it drifts
  from `ALL_PYTHONS`); the other workflows read it via `setup-python`'s
  `python-version-file`; local `uv` / `pyenv` auto-select it. It is in `CODE_PAT`
  so a lone bump still triggers `ci.yml`'s gating jobs (without that,
  `code=false` skips them and `gate` greens without testing the new version; the
  release/scheduled workflows are not PR-gating, so this only matters for
  `ci.yml`). Runtime is unaffected: `UV_SYSTEM_PYTHON=1` keeps `uv pip install`
  on each job's matrix interpreter, not the file (verified — `typecheck (3.10)`
  stayed green with the file present).
  Trace: [`sdd/traces/BK-280-ci-build-improvements.yml`](traces/BK-280-ci-build-improvements.yml).

- [x] **BK-269 — CI `lint` job delegates to `hatch` (one source of truth for "lint")**
  spec: — · effort: S · audience: infra.ci, contributor.tooling
  The CI `lint` job inlined all 18 lint commands as `- run:` steps, hand-duplicating
  the hatch `preflight` (5), `lint` (13), and `format-check` (1) targets — three
  divergent definitions of "lint" (the pre-commit subset, `hatch run lint`, and the
  CI job) that drifted independently (audit-017 H1 / L1 / L3). The job now runs
  `uvx hatch run preflight` + `lint` + `format-check` (`uvx` tool-runs the hatch CLI
  ephemerally; `setup-uv` retained, the inline `uv pip install -e ".[dev]"` dropped),
  so the `pyproject.toml` script lists are the single source and CI inherits any
  future checker automatically. `actionlint` is unchanged (not a hatch target). Side
  effect: `drift_check render-docs --check` (in `preflight`, previously in no PR CI
  lane) now gates tested-versions drift, closing part of audit M5. The CI env uses
  the **pip** installer via a `GITHUB_ACTIONS`-keyed `[tool.hatch.envs.default.overrides]`
  in `pyproject.toml`; local dev keeps uv. This is required, not precautionary: the
  PR's own `lint` run confirmed the `mutation.yml` hatch + uv bug — the uv installer
  silently dropped the env `features` and the job came up without `griffe` — even
  though it did not reproduce locally. Did not fold
  the targets into a single `lint` (preserves `preflight`'s fast-fail ordering in
  `hatch run all`); the `sdd/specs`/docs-only filter gaps and skill delegation remain
  BK-270 / BK-271. Trace: `sdd/traces/bk-269-ci-lint-delegates-to-hatch.yml`.

- [x] **BK-263 — Graph upload-session `ResourceLocked` leaked the pre-signed `uploadUrl` (credential)**
  spec: GR-045, GR-035, GR-026 · effort: M · audience: user.api, library.maintainer
  The mid-session `423` handler embedded the full pre-signed `uploadUrl` verbatim
  in the `ResourceLocked` message (`transfer.py:_resource_locked_mid_session`); that
  URL carries its own write/DELETE credential in its query (GR-038), so any caller
  logging the exception leaked a live credential, defeating GR-035 — while the
  sibling monitor path already query-stripped the identical credential class
  (`monitor.py`, GR-026). Root cause was a spec contradiction: GR-045 mandated
  embedding the session URL for resume, GR-035/GR-026 forbid tokens in messages, and
  for the upload session the credential *is* the resume handle. Resolved in favour of
  GR-035 (audit-016 H1): the query-strip redaction was hoisted into a shared
  `redact_presigned_url` helper in `http.py` used by both the monitor poller and the
  `423` handler; the session URL is now redacted (scheme/host/path only) before it
  reaches the message; and GR-045 was amended to drop the resume-from-message promise
  (the redacted URL + `nextExpectedRanges` still identify the operation for
  diagnosis, but resume requires re-deriving the URL — there is no public resume API,
  and a structured `RemoteStoreError.context` carrier stays out of scope). The GR-045
  test that asserted the credential was *present* was flipped to assert its absence,
  and a masking regression test (`str`/`repr`) was added. Trace:
  `sdd/traces/bk-263-graph-resourcelocked-cred-leak.yml`.

- [x] **BK-279 — Share CI service images via a cache instead of pulling per job**
  spec: — · effort: M · audience: infra.ci, contributor.tooling
  BK-278's per-job backoff retry still pulled every backend image (MinIO from
  `cgr.dev`, Azurite from `mcr.microsoft.com`, SFTP from Docker Hub) on each of
  the ~8 backend jobs per run, so a Microsoft WAF block or Docker Hub timeout
  that outlasted the ~75s retry window could still redden `gate` — and
  `fail-fast` then cancelled the sibling matrix shards. New `prepare-images` job
  primes an `actions/cache` tar once per run: on a miss it pulls each image
  (reusing `ci_docker_pull.sh`'s backoff) and `docker save`s them via
  `scripts/ci_save_images.sh`; on a hit nothing is pulled. The backend jobs
  (`test`, `test-primary`, `pyarrow24-check`, `e2e`) `needs: prepare-images`,
  restore the same tar, and `docker load` it (`scripts/ci_load_images.sh`)
  before `start-backends`, which now does `docker image inspect || pull` so a
  loaded image skips the upstream pull and an unloaded one still falls back to
  the retry. Only the two block-prone, tag-referenced images are cached
  (`RS_CACHED_IMAGES` = Azurite/mcr.microsoft.com + SFTP/Docker Hub): on
  cross-run cache reuse those registries see ZERO upstream pulls and are immune
  to blocks; the first run after a ref change pulls once to re-prime. MinIO is
  deliberately excluded — its ref is digest-pinned and a digest reference does
  not survive `docker save`/`docker load` (verified on CI: the loaded image
  can't be resolved by `docker image inspect "$MINIO_IMAGE"`), so start-backends
  pulls it regardless; cgr.dev is reliable, so per-job MinIO pulls are the
  pre-existing non-flaky behavior and caching it would only bloat the tar for no
  benefit (measured on CI: the saved tar drops from ~160 MB to ~90 MB without
  MinIO — Azurite, not MinIO, dominates the bundle).
  `fail-fast: false` on the `test` matrix stops one block from cancelling
  siblings. The three refs are single-sourced in `scripts/ci_service_images.sh`
  (sourced by `start-backends`, the new job, and — removing the prior
  duplication — `publish.yml` + `mutation.yml`); the cache key hashes that file
  so a ref bump busts and re-primes the cache. The cache is best-effort:
  `ci_save_images.sh` only persists when every cached image bundles, so a
  partial/empty tar never sticks under the key. `publish.yml` and
  `mutation.yml` are not exercised by PR CI; their edits are static-validated
  (`bash -n`, actionlint, `check_infra_settings.py`) only. Trace:
  `sdd/traces/bk-279-ci-share-service-images.yml`.

- [x] **BK-278 — Retry CI service image pulls (Azurite/MinIO/SFTP) with backoff**
  spec: — · effort: S · audience: infra.ci, contributor.tooling
  CI service containers were started with a bare `docker run`, so a single
  transient registry hiccup failed the whole job: `mcr.microsoft.com` edge/WAF
  rejections ("The request is blocked" / pull access denied), Docker Hub
  anonymous rate limits (`atmoz/sftp`), and blob-store "reduce your rate of
  simultaneous reads" throttling all surfaced this way. Added
  `scripts/ci_docker_pull.sh` (5-attempt exponential backoff) and pre-pull every
  service image before `docker run` across the three start sites:
  `.github/actions/start-backends/action.yml` (minio/azurite/sftp — shared by the
  `e2e`, `test`, and `test-primary` jobs), `.github/workflows/publish.yml`
  (azurite), and `.github/workflows/mutation.yml` (the three `-mut` services).
  Each block single-sources its image ref via `$img`. Digest pinning (already
  done for minio) stays a future option for azurite/sftp. Promoted from a
  deferred CI-flake memo once the failure recurred. Trace:
  `sdd/traces/bk-278-ci-image-pull-retry.yml`.

- [x] **BK-277 — Resource-bounded local test runner + randomised-order isolation lane**
  spec: — · effort: M · audience: contributor.tooling, infra.test
  `pytest -n auto` spawned one worker per logical CPU; on a high-core machine
  with several suites running at once it saturated and crashed the box. New
  `scripts/run_tests.py` caps workers to `max(1, floor(cpu*0.75) - 1)`
  (`RS_TEST_WORKERS=auto`/`=<n>` overrides) and forwards the rest to pytest; the
  five local `test*` hatch scripts now route their parallel pass through it.
  CI's **worker count** is unchanged — its workflows call pytest inline
  (`-n auto`), not these scripts, so the bound is local-only. Added
  `pytest-randomly`; because it auto-activates on install, order is held
  deterministic by default via `-p no:randomly` in `[tool.pytest.ini_options]`
  `addopts` — so every invocation (CI's inline pytest, the publish strict gate,
  bench/e2e, ad-hoc) stays reproducible. The new `test-isolation` lane
  re-enables shuffling with `-p randomly` (a command-line `-p` overrides the
  addopts opt-out) — the explicit "prove no hidden state" run. Verified:
  `test-isolation` green under randomised order, launcher guard
  `tests/scripts/test_run_tests.py` (32 cases, incl. `main()` end-to-end). The
  suite uses no GPU — GPU load during tests is from concurrent ollama/MCP
  sessions (documented in CLAUDE.md). Builds on BK-276: without that fix the
  randomised lane resurfaces ID-217. Trace:
  `sdd/traces/bk-277-resource-bounded-test-runner.yml`.

- [x] **BK-276 — Flaky `PytestUnraisableExceptionWarning` cross-attribution under `pytest -n auto`** (promoted from ID-217)
  spec: — · effort: M · audience: infra.test
  pytest-asyncio 1.3 on Python 3.13 (Windows `ProactorEventLoop`) left each
  per-test event loop unclosed after teardown; its self-pipe loopback socket
  pair fired `ResourceWarning` on the next cyclic GC, cross-attributed by xdist
  to whichever test was running on that worker, and `filterwarnings = error`
  promoted it to a spurious hard failure (the blamed test varied run-to-run and
  always passed in isolation). `tracemalloc` pinned two creation paths: pytest-
  asyncio's `asyncio.Runner` loop and the ID-158 `asyncio.get_event_loop()`
  phantom (3.13 auto-creates a loop). Fix (`tests/_helpers.py`,
  `tests/conftest.py`): patch `BaseEventLoop.__init__` — the constructor every
  loop class funnels through — to weakly track every loop, then a
  `pytest_runtest_teardown` hookwrapper closes abandoned (non-running, unclosed)
  tracked loops after each test, before the next GC can free their sockets. (An
  initial `BaseDefaultEventLoopPolicy.new_event_loop` patch broke on Python 3.14,
  which removed the event-loop policy framework; the constructor patch is
  version-agnostic.) The `WeakSet` sweep adds ~1.5% wall-time; a whole-heap
  `gc.get_objects()` sweep doubled it, and a GC-start callback closed in-use
  loops mid-test and was rejected. The session sweep (ID-158) stays as a broad
  backstop. Verified clean under a per-boundary-GC stress (was 12 leaked loops,
  now 0). Regression: `tests/test_async_loop_leak_guard.py`. Trace:
  `sdd/traces/bk-276-event-loop-leak-guard.yml`.

- [x] **ID-127 — OneDrive / SharePoint backend (Microsoft Graph)**
  spec: GR-001..GR-058, ERR-013 · effort: L · audience: user.api
  Unified async backend covering OneDrive (personal & business) and SharePoint
  document libraries via the Microsoft Graph REST API; a single `drive_id`
  selects the target drive (async-only — construct via
  `AsyncStore(backend=GraphBackend(...))`). Design: RFC-0010, ADR-0021 (SDK),
  ADR-0022 (auth), ADR-0023 (async polling), ADR-0024 (ResourceLocked); spec
  [044](specs/044-graph-backend.md) (GR-001..GR-058), ERR-013 in spec 005,
  RET-015 in spec 025.
  - **Bundled sub-task — `ResourceLocked` (ERR-013, ADR-0024):** landed in
    GR-CONTRACT — the `ResourceLocked` exception (`_errors.py`), the
    `Error.ResourceLocked(path, backend)` Dafny variant
    (`sdd/formal/BackendContract.dfy`), and its `_raise_if_err` dispatch
    (`tests/backends/dafny/_helpers.py`). Folded from the former ID-189.
  - Shipped across nine steps: GR-FOUNDATION, GR-CONTRACT, GR-CORE, GR-READ,
    GR-TRANSFER, GR-WRITE, GR-MUTATE, GR-DOCS-E2E, and **GR-DONE** (BK-237 DoD
    umbrella + close-out).
  - **GR-DONE** landed: the combined `close()` assertion (GR-051 — cancels
    pending pollers *and* aborts in-flight upload sessions on one assembled
    backend); the integration-only tier (GR-007/020/026/034/054 + 10 MiB
    round-trip, two-layer `graph_live`-gated); the spec↔mark traceability sweep
    (removed the coarse `GR-*` allowlist in `check_spec_marks.py`, marked
    GR-004/021/046/050/053, allowlisted the deferred GR-011); a wrapper-forwarding
    proof (`ResourceLocked` survives the async→sync adapter); and a capability
    review (no over/under-declaration).
  - **Live conformance exposed and fixed real backend bugs.** Recording the
    previously-skip-clean (vacuous) conformance suite live for the first time
    surfaced error-fidelity divergences the respx unit tests had masked by
    mocking 409+facet responses live Graph never returns: `write`/`move`/`copy`
    now raise `InvalidPath` for folder targets (live 501), file-ancestor descents
    (404/400), and directory destinations, via error-path metadata-confirm remaps
    (mirrors Azure). Added **`base_path` (GR-058)** to scope a backend to a drive
    subfolder (the per-test isolation mechanism + a real feature). Full live
    conformance is green (109/0/9).
  - **Cassette CI replay deferred to [BK-262]** — committable replay cassettes
    need pre-signed `downloadUrl` redaction to a replay-able placeholder URL;
    the prerequisite scrub infra (vcr-mark hook, request-body `drive_id` scrub,
    `base_path` uuid scrub) landed here. Conformance was proven green live, so
    this is strictly better than the prior vacuous-skip state.
  - Trace: `sdd/traces/ID-127-gr-done.yml` (+ the eight prior step traces).

- [x] **ID-180 — Stable HTML-anchor IDs across non-spec docs under `sdd/`**
  spec: — · effort: M · audience: library.maintainer, contributor.process
  Cross-doc references between framework docs (CLAUDE.md, CONTRIBUTING.md,
  the seven `sdd/` framework docs, `sdd/formal/README.md`, `sdd/BACKLOG.md`)
  used heading text or GitHub auto-slugs that rot silently on heading rename.
  Prose `§ Section` references were invisible to the link checker entirely.
  Added `<a id="…">` anchors next to currently-cited sections (concept-named,
  not numbered — `#workflows` not `#rule-6`, `#bug-fix-protocol` not
  `#section-30`), converted prose refs to Markdown anchor links across CLAUDE.md,
  CONTRIBUTING.md, the framework docs, and the consumer skills under
  `.claude/skills/`. Extended `scripts/docs/check_links.py` with M1 (fragment
  resolution against `<a id>` tags and GitHub-style heading slugs), M2 (anchor
  uniqueness), and M3 (orphan-anchor heuristic). Denylist: CHANGELOG,
  BACKLOG-DONE, audits, research, traces. mkdocstrings dotted symbol refs
  (`#remote_store.Store.read`) are skipped (rendered at docs-build time).
  Tests: 17 new in `tests/scripts/test_check_links.py`, including a live-repo
  positive control. No CHANGELOG entry: audience is library.maintainer +
  contributor.process. Followup not pursued: ID-179 (trace `section:` validator)
  stays parked separately per the user's "traces are a lightweight tool" framing.
  Trace: `sdd/traces/id-180-stable-anchor-ids.yml`.

- [x] **BK-256 — Test hygiene: real restricted backend + misfiled test**
  spec: — · effort: S · audience: infra.test
  Two independent cleanups from the test-suite review (sibling to BK-255).
  - **Real restricted backend.** Three capability-gate tests in
    `tests/test_store.py` built ad-hoc `MagicMock(spec=Backend)` backends
    instead of using the canonical `make_restricted_store` helper in
    `tests/conftest.py`: `test_supports_atomic_move_false_when_backend_lacks_it`,
    `test_head_requires_metadata_capability`,
    `test_metadata_validation_before_capability_check`. Rewrote each onto
    `make_restricted_store(exclude={...})` — consistent with
    `tests/test_open_atomic.py` and TESTING.md Rule 6 (prefer real
    dependencies). `test_head_maps_all_fields` stays on a mock because it
    injects a fully-populated `FileInfo` via `get_file_info.return_value`,
    which `MemoryBackend` can't reproduce.
  - **Relocate misfiled test.** Moved `test_write_text_roundtrip` from
    `TestListFilesDepthFilter` into `TestStoreWriteText` (the existing
    WTXT-001 owner). Deleted the now-empty `TestListFilesDepthFilter` class —
    the BK-255 docstring breadcrumb's only purpose was flagging the misfile
    for this item.
  CHANGELOG skipped per infra.test (BK-255 precedent).

- [x] **BK-245 — Cross-source capability-parity check (Python ↔ Dafny)**
  spec: — · effort: S · audience: infra.test, contributor.tooling
  Added `scripts/check_capability_parity.py`, a sibling to
  `check_formal_trace.py`, asserting
  `{c.value for c in Capability} == {CapabilityName(c) for c in <Dafny Capability>}`.
  `check_formal_trace.py` matches `@spec` tags, not capability-enum
  membership, so the `CapLazyRead` ↔ `Capability.LAZY_READ` parity ID-188
  added on a comment alone (PR #689) had no mechanical guard; a future
  `Capability.<NAME>` drift between `_capabilities.py` and the Dafny
  `Capability` datatype / `CapabilityName` cases would have slipped through.
  - Two checks, both parsed from source (AST for the Python enum, scoped
    regexes for the Dafny datatype and `CapabilityName` arms — no package
    import, no Dafny toolchain): (1) Dafny-internal, every `Capability`
    datatype variant has a `CapabilityName` arm and vice versa; (2)
    cross-language, the arm strings equal the Python `.value` set. The gate
    fails on a mismatch *or* an empty parse of any source. Parity is
    per-name; Dafny datatype ordering/grouping is out of scope.
  - Check (1) makes the gate self-contained: a variant added without an arm
    is otherwise caught only by Dafny's exhaustive-match verification, which
    runs in the path-gated `verify-formal` CI job, not `lint`. To fire on a
    `BackendContract.dfy`-only change (FORMAL_PAT, not CODE_PAT), the gate is
    wired into both the `lint` and `verify-formal` CI jobs.
  - Runs in `hatch run lint`; covered by
    `tests/scripts/test_check_capability_parity.py`.
  - No CHANGELOG entry (infra.test + contributor.tooling, not user-facing).

- [x] **BK-241 — `tests/aio/README.md` orientation for next async backend**
  spec: — · effort: S · audience: contributor.process, infra.test
  Added [`tests/aio/README.md`](../tests/aio/README.md), a thin repo-only
  landing page so the next async backend (ID-127 Graph) does not re-derive the
  async test layout and repeat the conftest sprawl BK-164 and ID-156 cleaned up.
  It is a **map, not a copy**: an authorities table (spec 029, spec 048,
  ADR-0025, `sdd/TESTING.md`) plus four short sections — what lives in
  `tests/aio/`, the two opposite-direction adapters (`SyncBackendAdapter`
  sync→async vs `AsyncBackendSyncAdapter` async→sync, the standing confusion),
  the live-vs-doubles layering (registry fixtures vs `_doubles.py` failure
  paths), and an add-a-backend checklist that links the fixture/test templates.
  - Chose the standalone README over a `sdd/TESTING.md` section: orientation is
    a different genre from TESTING.md's authoritative rules, it belongs where a
    contributor lands (`cd tests/aio`), and keeping it a thin linking index
    avoids duplicating spec 048 (principle 4).
  - No CHANGELOG entry: `contributor.process` + `infra.test`, and the README is
    not a new user-facing framework or spec (BK-258 precedent).
  - Completes the ID-127 (Graph) process/test prerequisite gate; with BK-239
    also landed, both gates ahead of the Graph backend are now clear.

- [x] **BK-240 — Streaming-iteration counting wrapper for write paths**
  spec: SIO-003, ASYNC-021 · effort: S · audience: infra.test
  BUG-165 (Azure async materialized payloads), BUG-181 (HNS size counting),
  and BUG-194 (`gotcha_async_materialize_antipattern`) were three faces of one
  defect: a write path collapsed an `AsyncIterator[bytes]` / `BinaryIO` into a
  single `bytes` before the SDK call. The type signature tolerates it, so it
  recurred; each recurrence was caught only by an ad-hoc per-path assertion.
  - **Discriminator:** chunk-boundary preservation at the SDK boundary. A
    faithful stream forwards N chunks as N chunks; *any* materialization (join
    to bytes, or join then re-emit as one chunk) collapses N>1 chunks into one.
    The plan's initial peak-memory probe was dropped — it cannot run in the
    Stage-1 no-container pass and is confounded by the Azure SDK's own
    multi-MiB block buffering; the SDK-boundary chunk count is what the backlog
    actually described and is robust.
  - **Closes a real hole:** the existing async non-HNS guard
    (`hasattr(forwarded, "__aiter__")` + payload reconstruction) passes a
    materialize-then-re-emit-as-one-chunk wrapper; sync non-HNS had no
    stream-vs-bytes guard; sync HNS reconstructed but never asserted `>1`
    append. (Async HNS already asserted `append_data.await_count == 2`.)
  - **Lands:** reusable `tests/backends/azure/_materialization_guard.py`
    (`MULTI_CHUNK`, `async_chunks`, `collect_async_upload`, `collect_sync_upload`,
    `chunks_from_append_calls`, `assert_streamed_not_materialized`) +
    `TestAsyncAzureNoMaterialization` (async non-HNS) and
    `TestAzureNoMaterialization` (sync non-HNS + sync HNS). Future SDK-streaming
    backends reuse the helper by pointing their mocked SDK call at the
    collectors.
  - infra.test only → no CHANGELOG entry (derived rule).

- [x] **BK-239 — Generic field-vs-capability symmetry check for `WriteResult`**
  spec: WR-001a, WR-005, WR-012 · effort: S · audience: infra.test
  The two existing per-pair under-declaration guards on the `WriteResult`
  fields (`test_basic_source_leaves_rich_fields_none` for the rich fields,
  `test_metadata_is_none_when_not_passed` for `WriteResult.metadata`) did
  not scale: the next contract-expanding feature could add a field/capability
  pair without a matching guard. Closed by two additions to
  `tests/backends/conformance/test_atomic.py`:
  - **`_FIELD_CAPABILITY`** — a single map from every `WriteResult` field to
    the capability that gates a non-`None` value (`digest` / `etag` /
    `version_id` / `last_modified` → `WRITE_RESULT_NATIVE`, `metadata` →
    `USER_METADATA`, `path` / `size` / `source` unconditional).
  - **`test_field_capability_map_covers_every_write_result_field`** — a
    backend-independent guard pinning `_FIELD_CAPABILITY` to
    `dataclasses.fields(WriteResult)`, so a new field cannot land unclassified.
    This is the mechanism that makes future pairs inherit the symmetry.
  - **`test_populated_field_implies_declared_capability`** — runs across every
    WRITE backend (both `write` and `write_atomic`): for each populated field,
    the gating capability must be declared. Generalises the basic-source guard
    to all backends and both declaration directions; exercises the `metadata`
    branch non-vacuously where `USER_METADATA` is declared.
  - **Spec:** WR-001a / WR-005 / WR-012 Python-backstop lists in
    `sdd/specs/045-write-result.md` now name the new tests.
  - No CHANGELOG entry (audience `infra.test`, not user-facing). Lands ahead
    of ID-127 (Graph backend) so the guard is generic when a new backend joins.

## v0.27.0

- [x] **BK-237 — Feature-type DoD checklists in `sdd/000-process.md`**
  spec: — · effort: S · audience: contributor.process
  Added a **Feature-type Definition of Done** guide section to
  `sdd/000-process.md` with two complementary checklists distilled from the
  v0.23.0→v0.24.0 retrospective, so the next contract-expanding feature and
  the next bridge/adapter wrapper follow a written gate instead of
  rediscovering the ID-146 → ID-151c sprawl (eight sub-IDs over two weeks).
  - **Contract-expanding feature** (trigger: new `Capability.X`, Store method,
    or error class): spec/RFC update with conformance/PBT/Dafny extensions
    enumerated up front (budget 2-3× the research estimate at RFC time),
    capability over- *and* under-declaration review, conformance test + xfail
    registry landed before the first backend, wrapper-forwarding check
    (`ProxyStore`, `ObservedStore`, `CachedStore`, sync adapter, oracle
    adapter), docs ripple (`docs-src/guides/`, `examples/snippets/`,
    `FEATURES.md`, capabilities matrix), and the audit-PR gate.
  - **Bridge / adapter feature** (trigger: any cross-layer wrapper): API-parity,
    event-loop/lifecycle, and cancellation-invariant tests, live-backend
    coverage, and a `filterwarnings = error`-clean suite.
  - **Co-shipped BK-238** (Promote `filterwarnings = error` and audit-PR to
    feature-DoD): the audit-PR pattern (PR #465) and the global
    `filterwarnings = error` policy are now explicit checked steps in the two
    checklists above, per BK-238's "folds into BK-237 if both ship in the same
    PR." Docs-only, no behavior change; no CHANGELOG entry (contributor.process,
    not a user-facing framework).
  - Unblocks the BK-237 prerequisite gate ahead of ID-127 (Graph backend).

- [x] **BK-238 — Promote `filterwarnings = error` and audit-PR to feature-DoD**
  spec: — · effort: S · audience: contributor.process
  Folded into **BK-237** (shipped same PR): both `filterwarnings = error` and
  the audit-PR pattern (PR #465) are now checked steps in the Feature-type
  Definition of Done in `sdd/000-process.md`. See the BK-237 entry above.

- [x] **BK-234 — Reconcile `to_key` empty-key / bare-root behaviour across backends**
  spec: NPR-005, NPR-020, NPR-021 · effort: M · audience: library.maintainer
  Resolved **toward a universal round-trip** (option A): all rooted backends now
  special-case the bare native root to the empty key `""`, so
  `to_key(native_path(k)) == k` (NPR-001 / NPR-020) holds for `k == ""` as well
  as every non-empty key. Previously `S3Backend` (`_s3_base.py`, shared by s3fs +
  PyArrow), `S3Boto3Backend` (`_s3_boto3.py`), and `AzureBackend` (`_azure.py`
  sync + `aio/backends/_azure.py`) returned the bare bucket/container unchanged,
  while `LocalBackend` / `SFTPBackend` already special-cased it to `""` — so the
  invariant failed only on the S3/Azure family.
  - **Fix:** added the bare-root → `""` branch to the four divergent `to_key`
    implementations; Local/SFTP unchanged.
  - **Spec:** NPR-005 now defines the bare-root → `""` rule (the inverse of
    NPR-021's `native_path("")` → root); NPR-020's "for all valid keys" claim is
    now true unmodified.
  - **Formal:** `BackendContract.dfy` `ToKey` gained the bare-root branch and
    `NativePathRoundTrip` dropped its `key != "" || root == ""` precondition —
    the lemma now holds unconditionally (verified, 51/0).
  - **Test:** the conformance `test_native_path_round_trip` is parametrised over
    `["some/key", ""]`, exercising the empty key across the full fixture registry
    (the cross-backend home per BK-255 — no per-backend re-assertion added).
  - Surfaced during ID-190 review.

- [x] **BK-258 — Residual branch coverage for `AsyncBackendSyncAdapter`**
  spec: ASYNC-080, ASYNC-083, ASYNC-085, ASYNC-088 · effort: S · audience: infra.test, library.maintainer
  `src/remote_store/_async_to_sync_adapter.py` was the worst-covered module
  (87%). Closed the gap with seven focused test classes in
  `tests/aio/test_async_to_sync_adapter.py` (BK-258 block) covering the
  genuine-but-untested branches: the `_submit` and `_AsyncIteratorBridge`
  close-race (loop stopped after `_guard`, canonical `_CLOSED_MSG`, no leaked
  coroutine); the `_ChunkPullReader.readinto` data path including the
  `io.BufferedReader` consumer; stream `close()` idempotency and its
  debug-logged swallow of a raising `aclose()`; `_aclose_best_effort`'s
  submit-failure handler; `_SpoolAndFlush.__exit__` re-exit no-op; and the
  `close()` drain loop with pending loop tasks (clean drain + drain-timeout
  warning, exercising `_drain_tasks`). The five remaining lines are genuine
  race/dead guards marked `# pragma: no cover` with a justification each — the
  `_SyncSafeHandleProvider` Protocol stub, `_pull_chunk`'s redundant `_eof`
  guard (both public callers gate on `_eof` first), `_snapshot_tasks`'
  "Set changed size" iteration-race except, and the two drain-loop branches
  (loop-stops-mid-submit race; `_drain_tasks` cannot raise under
  `gather(return_exceptions=True)`). Chosen over brittle stdlib monkeypatching
  per TESTING.md Rule 5. No behaviour change — tests + pragmas only; CHANGELOG
  skipped per infra.test (BK-223/BK-254 precedent).

- [x] **BK-257 — Default the s3fs S3 lanes to `use_listings_cache=False`**
  spec: S3-027, S3PA-027 · effort: M · audience: user.api
  Implemented ID-201's disposition **(a)**: `_S3Base._build_s3fs_kwargs()` now
  injects `use_listings_cache=False` via `opts.setdefault(...)` (the same idiom
  as the `anon` default), so both s3fs lanes (`s3`, `s3-pyarrow`) get fresh
  listings by default. s3fs's `DirCache` never expires
  (`listings_expiry_time=None`), so a cached listing is permanently blind to a
  cross-writer write — 100% silent staleness (ID-201). `setdefault` preserves
  caller precedence: `client_options={"use_listings_cache": True}` re-enables
  caching; `ext.cache` stays the portable, explicit-invalidation path.
  - **Spec:** new atomic invariant **S3-027** in `008-s3-backend.md` with a
    pointer from S3-021 (the listings default is a precedence rule in the
    opposite direction — `client_options` overrides our injected default — so
    it earns its own ID rather than a compound S3-021 postcondition).
    `011-s3-pyarrow-backend.md` inherits it as **S3PA-027**.
  - **Tests:** `test_options.py::TestListingsCacheDefault` pins the kwarg shape
    (default-fresh + `client_options` override) for both backends;
    `test_moto.py::TestListingsCacheStalenessMoto` is the wire-level regression
    (cache-off reader sees a cross-instance write; opt-in cache reproduces the
    stale read). The moto test must force `skip_instance_cache=True`: fsspec
    caches `S3FileSystem` by kwargs, so two same-config backends would otherwise
    share one `DirCache` and the writer's own write would invalidate the
    reader's cache, masking the staleness the test exists to pin.
  - **Docs / CHANGELOG:** new "Directory-listing cache (off by default)"
    subsection in `guides/backends/s3.md`; `[Unreleased]` stub. Pre-v1 minor
    behaviour change.
  - **Ripple (PR review):** the default-flip made the benchmark `s3` and
    `s3-nocache` lanes behaviourally identical and left two docs asserting the
    s3fs path was cached by default. Reconciled in the same PR — the `s3`
    benchmark lane now opts the cache back on explicitly (`benchmarks/conftest.py`,
    `benchmarks/README.md`), and the `docs-src/explanation/performance.md`
    listing caveat now states the cache is off by default.

- [x] **BK-255 — Trim cross-backend invariants re-asserted outside conformance**
  spec: — · effort: S · audience: infra.test
  Removed per-backend and root tests that re-assert a cross-backend invariant
  conformance already parametrises over the fixture registry, gated on
  zero coverage loss (BK-014 style: `_memory`/`_local`/`_azure`/`_store`
  term-missing identical before and after, captured with Azurite up so the
  Azure deletion's counterpart actually executed). Net **−126 lines**.
  - **Deleted (fully redundant):** the five
    `tests/backends/memory/test_coverage.py::TestMemoryListingCorrectness`
    listing tests (kept MEM-025 deadlock + BK-006 open_atomic);
    `tests/backends/azure/test_config.py::TestAzureIntegration::test_list_files_max_depth`
    (Azurite); `tests/test_store.py::TestListFilesDepthFilter::test_depth_filter_trims_files_beyond_max_depth`.
  - **Trimmed to the named slivers:** `TestMemoryWriteResult` → the
    `source == "native"` pin; `TestMemoryCopyMetadataRoundTrip` → the two
    `list_files`-projection metadata tests; `TestMemoryBackendNativeDepth` /
    `TestLocalBackendNativeDepth` → `test_max_depth_without_recursive`
    (recursive=False ignores max_depth, not in conformance);
    `TestStoreOpenAtomicMemory` → the empty-path `InvalidPath` sliver.
  - **Regression breadcrumbs preserved.** Conformance markers may cite only
    real spec IDs (`scripts/check_formal_trace.py` F2), so the BK-123
    (memory lock-reduction) and the deleted Azure test's BUG-155 breadcrumbs
    moved to conformance **docstrings**, not markers. Deleting the only test
    citing STORE-012 and SAW-012 would have orphaned two declared specs
    (`check_spec_marks` zero-tolerance), so those **real** marks relocated:
    STORE-012 onto `test_depth_listing.py`'s child-store path test (the
    round-trip-path invariant it genuinely exercises) and SAW-012 onto
    conformance `test_open_atomic_creates_file` (memory buffer-then-commit).
  - **Doc ripple.** Repointed the stale "owned by …
    azure/test_config.py::test_list_files_max_depth" back-reference in
    `tests/test_depth_listing.py` and the "owns the Azure behavioural
    invariant" claim in `tests/backends/azure/test_depth_listing.py` at the
    conformance owner. The backlog also named `tests/backends/s3/test_depth_listing.py`,
    but that file already pointed at the conformance owner — no Azure
    back-reference to fix. The backlog's "BUG-201" was a mislabel: the
    deleted Azure test's breadcrumb is BUG-155 (BUG-201 is the unrelated
    self-op short-circuit).
  - **Out of scope (BK-256).** The deletion leaves the misfiled
    `test_write_text_roundtrip` alone in `TestListFilesDepthFilter`; BK-256
    owns relocating it (left in place, flagged in a class docstring).
  CHANGELOG skipped per infra.test (BK-223 precedent).

- [x] **BK-254 — Store-level failure-path coverage for delegated raises**
  spec: STORE-004, STORE-008 · effort: S · audience: infra.test
  Several documented `Store` raises were verified only against the raw
  `Backend` in `tests/backends/conformance/test_errors.py`, never through a
  `Store`. Added one parametrized test
  (`tests/test_store.py::TestStoreDelegatedRaises`, MemoryBackend substrate,
  15 `(method, bad-precondition) -> expected-raise` cases) pinning the
  contract at the consumer surface: `move`/`copy` cross-path `NotFound`
  (missing src) and `AlreadyExists` (existing dst, no overwrite);
  `delete_folder` `DirectoryNotEmpty` / `NotFound` / file-target `InvalidPath`;
  `read` / `read_bytes` `NotFound`; `get_file_info` `NotFound` and
  `get_folder_info` `NotFound` on the `max_depth=None` delegating branch;
  `InvalidPath`-on-directory for `read` / `read_bytes` / `delete` /
  `get_file_info`. Each case carries the Store-API marks `STORE-004` /
  `STORE-008` (method-level) plus the backend-contract clause it surfaces
  (`BE-006/007/012/013/016/017/018/019`), mirroring `TestStoreSamePathOps`'
  dual Store-API/`BE-*` tagging. No behaviour change — `Store` is a thin
  delegator, so this is contract-proof, not new behaviour. CHANGELOG skipped
  per infra.test (BK-223 precedent).

- [x] **BK-252 — Bulk spec-mark backfill + full disposition (audit-015 traceability)**
  spec: — · effort: L · audience: library.maintainer
  Closed the spec ↔ test traceability debt audit-015 surfaced and BK-251 gated.
  `scripts/check_spec_marks.py`'s `_BASELINE` started at **159** shipped-but-unmarked
  spec IDs and is now **drained to empty** — the gate reports "spec ↔ mark traceability
  is complete" (0 violations, 804 mark-cited IDs).
  - **Backfill (102 marks, 5 grouped PRs #724/#726/#727).** Type-(b) labels stamped
    onto the tests that already exercise each behavior, across backend-restatement
    (AZ/S3/S3PA), core-API/paths (STORE/NPR/BE/CAP/MEM), text/stream/iter/pyarrow,
    extensions (BATCH/OBS/SAW/DAG/WR/GLOB), and HTTP/Async/SQL. Reviewer caught and
    fixed several mark-placement slips (BE-011→hold, BE-023/DAG-001/HTTP-TR-002/003
    relocated) — verify-against-the-named-test, not rubber-stamp.
  - **Disposition (final PR).** All 57 residual `_BASELINE` rows were resolved, not
    deferred — **37 allowlisted + 20 newly tested = 57**. The **37 allowlisted** into
    `_ALLOWLIST_DESIGN`: 31 type-(d) design/meta/perf (incl. CFG-007 reclassified), the
    2 optional-dependency/packaging declarations PA-023/CFG-014, and the 4 `WR-014..017`
    moved-to-`EW-001..004` cross-reference stubs (ADR-0008). The **20 genuine type-(a)
    coverage gaps closed with new tests**: STORE-007/010, BE-011 (+AW-002/AW-007, same
    capability-gate raise), ITER-002, MEM-001/005, PA-026, AW-005, AW-006, S3-001,
    NPR-007, S3PA-001/007, PING-009, SAW-010, SEEK-007, AZ-010, ASYNC-074. AW-006 (Local
    `mkstemp`+`os.replace`) was first allowlisted, then moved to a real mechanism test in
    review — which is why a snapshot count taken mid-review read 35/22.
  - **Spec defect found & fixed (ASYNC-074).** Writing the ASYNC-074 test reproduced
    the real behavior: non-HNS `write()` streams the `AsyncIterator` straight to
    `upload_blob` (BUG-165, bounded memory) — it does **not** materialize to bytes as
    the spec claimed. Corrected spec 029 ("Content Streaming") before marking; see
    `gotcha_async_materialize_antipattern`.
  The gate is now a hard zero-tolerance check: any new shipped spec ID without a mark
  or allowlist entry fails CI immediately.

- [x] **ID-201 — Spike: default `S3Backend` to `use_listings_cache=False`?**
  spec: — · effort: S · audience: user.api
  Measured the s3fs directory-listing-cache trade (fsspec #324) for `Store`-shape
  workloads across moto / MinIO / real AWS, using the `benchmarks/` `s3` (cached)
  vs `s3-nocache` (`use_listings_cache=False`) vs `s3-boto3` lanes plus a throwaway
  staleness probe. **Disposition: (a)** — default the cache off with a
  `client_options` override. Spawned **BK-257** (implementation).

  Latency (#1/#2): the cache is the only real speed differentiator — on AWS it
  turns a 38 ms flat list into 0.26 ms and a 393 ms recursive walk into ~1 ms
  (150–360x). Fresh-vs-fresh, s3fs and the boto3 lane are at parity for flat /
  recursive lists and single-object metadata (RTT-bound); the boto3 lane's single
  flat `list_objects_v2` beats fresh s3fs on `get_folder_info` (83 vs 467 ms AWS).
  The moto "s3fs 2.4–3x faster" gap was a library-CPU artifact (gone on a real
  network).

  Staleness (#3): with the default cache a write from a second instance is **100%
  invisible and permanently so** (25/25, moto + MinIO) — s3fs `DirCache` defaults
  to `listings_expiry_time=None`, so a listed directory never re-fetches until
  `invalidate_cache()`. cached+invalidate, `s3-nocache`, and `s3-boto3` are all
  0/25. Rationale for (a): the cache buys repeated-list latency only when nothing
  writes in between, against 100% silent cross-instance staleness that breaks the
  "a listing shows what's there" model for a multi-writer Store; the fresh-list
  cost is one bounded RTT (the boto3 lane already pays it and stays competitive),
  and cache-wanters opt in via `client_options` / `ext.cache`.

- [x] **ID-202 — PoC: `s3-boto3` backend lane alongside `s3` and `s3-pyarrow`**
  spec: — · effort: L · audience: library.maintainer, infra.test
  (Opened as `audience: user.api`; the PoC landed **test-only** — not registered,
  not in `FEATURES.md`, not in `__all__` — so nothing user-facing shipped and the
  dominant audience is maintainer + test infra. The `user.api` framing and a
  CHANGELOG entry attach if a future Ship verdict promotes the lane.)
  Built `S3Boto3Backend` (`src/remote_store/backends/_s3_boto3.py`): a standalone,
  boto3-only S3 backend (no `s3fs` / `aiobotocore` / `pyarrow`) with capability
  parity to `S3Backend` minus `ATOMIC_MOVE`, a `get_object` Range-backed seekable
  reader, and `ClientError`-code → typed-error mapping per ID-200. The
  `s3-boto3 = ["boto3>=1.34"]` extra is **proposed, not declared** — declaring it
  would advertise `pip install remote-store[s3-boto3]` in the generated
  `FEATURES.md` for an unregistered backend, so it is deferred to Ship; the tests
  run on the `boto3` already in the dev env. moto conformance fixtures
  `s3_boto3_moto` (+ strict). Full Stage-1 conformance passes; a mid-stream-abort test proves the
  lane does **not** inherit the BUG-214 truncated-commit defect (abort by
  construction). Three-axis analysis and the disposition live in
  [research-s3-boto3-poc.md](research/research-s3-boto3-poc.md).
  - **Disposition: Park as test-only.** The lane is viable and correct, but for
    today's users `s3` / `s3-pyarrow` cover the same surface, so promoting a third
    install path now buys mostly choice-paralysis and a doubled per-backend
    maintenance footprint (`_S3Base`'s listing/metadata methods are s3fs-coupled,
    so the lane is ~625 standalone LOC). Interop loss is minimal: extensions ride
    the `Store` API, and `ext.arrow`'s native-PyArrow Tier-1 probe falls back
    gracefully (the `s3` lane lacks it too), so the boto3 lane is on par with `s3`.
  - **Revisit triggers** (would reopen as a Ship `BK-NNN`): s3fs upstream stalls on
    the >5 GB (#1936) or listing-cache (#324) issues, or the aiobotocore dep-pin
    cascade bites a real user. A Ship increment would add the `_S3Base` refactor,
    public wiring, an `AsyncS3Boto3Backend`, a backend guide, and a CHANGELOG entry.

- [x] **BK-248 — Confirm S3 403 / credential-failure error mapping over the wire (Stage 3)**
  spec: S3-016, S3-018 · effort: S · audience: library.maintainer, infra.test
  (Scoped as S3-016/S3-017 when opened; the verified surface is the
  PermissionDenied mapping (S3-016) and no-native-leakage (S3-018). The
  S3-017 connection-level/`BackendUnavailable` fallback was never the residual
  unknown and is not exercised here.)
  ID-200 verified rows (b) 403→`PermissionDenied` and (c) invalid-credentials→
  `PermissionDenied` only at the *mapping* boundary (moto enforces neither IAM
  nor credential validity). Confirmed the natural path over the wire against
  real AWS via a new Stage-3 file
  (`tests/backends/s3/test_live_error_mapping.py`, `RS_TEST_LIVE_S3=1`).
  - **Result — all paths map to `PermissionDenied`.** An `S3Backend` built with
    a bogus access key / secret produces a real 403
    (`InvalidAccessKeyId`/`SignatureDoesNotMatch`) on `read_bytes`, streaming
    `read`, and `write`; each maps to `PermissionDenied` (`backend == "s3"`).
    The "swallowed inside an aiobotocore streaming read" worry (ID-200) does
    **not** materialise: s3fs issues an eager HEAD/GET *inside* `_s3fs_errors`,
    so the 403 is caught and mapped before any stream is returned — it never
    reaches the `_ErrorMappingStream` wrapper.
  - **Empirical finding — `AccessDenied` vs 404.** A distinct `AccessDenied`
    (valid creds, forbidden resource) was *not* separately exercised: the
    single-credential `s3_live` IAM user cannot provision an
    existing-but-forbidden bucket, and targeting a bucket *outside* its
    `rs-conformance-*` grant returns **404 `NoSuchBucket`** (→ `NotFound`), not
    403 — S3 reports a non-existent bucket as 404 to a credentialed caller
    regardless of IAM. `s3fs.translate_boto_error` keys on the 403 code
    identically for `AccessDenied` and the invalid-credential codes, so the
    credential-failure 403 confirms the same boundary.
  - **No production-code change.** No row diverged, so no BUG was opened. The
    `# pragma: no cover` on `_s3_base.py`'s `PermissionError` branch is kept —
    the Stage-1 coverage gate never reaches it; only the live run does.
  Research note (§ 3(b)/(c), § 6) updated; trace
  `sdd/traces/bk-248-s3-error-mapping-over-the-wire.yml`. `backlogid.json`
  unchanged (BK max already 253 > 248).

- [x] **BK-249 — Parametrize the file-ancestor write conformance test over body type**
  spec: BE-008 · effort: S · audience: infra.test
  Surfaced in PR #708 (BK-235) review:
  `TestWriteErrorFidelity::test_write_under_file_ancestor_raises_invalid_path`
  (`conformance/test_errors.py` + async sibling in `test_async_extended.py`)
  passed only a `bytes` body. Azure HNS `write_atomic` keeps *separate*
  `except` blocks per body type, so the streaming `else:` branch's
  file-ancestor remap (sync `_azure.py:602`, async `aio/backends/_azure.py:662`)
  was unreachable by any recordable test and carried a
  `# pragma: no cover -- HNS only`.
  - **Resolution — parametrize over body type.** Added a `body_kind` axis
    (`bytes`, `stream`) to both tests; the stream body is an `io.BytesIO`
    (sync) / async generator (async). The streaming temp `create_file` under a
    file parent fails before the body is read, so an unread stream suffices.
  - **Scope note:** non-atomic `write` funnels both body types through *one*
    shared `except` (sync `_azure.py:508`), already covered by the bytes test —
    only `write_atomic` had the gap. The `write`-stream cell is therefore
    redundant for coverage but kept for the full `(method × body)` grid.
  - **Cassettes:** the 4 existing bytes cassettes were renamed in place
    (`[write-azure]` → `[write-bytes-azure]`, …) since the seed stays
    method-keyed; the 4 new stream cassettes were recorded against live HNS via
    targeted single-node `record_cassettes.py --node …[azure_live]` /
    `…[azure_live_async]` (no tree-wipe), scrub-verified clean, replay-confirmed.
  - **Pragmas dropped:** both `# pragma: no cover -- HNS only` removed; replay of
    the stream cassettes now executes sync `:602` / async `:662` (verified via
    coverage). No production-code change.

- [x] **BK-250 — Spec-traceability audit (audit-015): correctness gaps + spec defects**
  spec: STORE-018, HTTP-CON-003, HTTP-CON-004, S3-012, BATCH-023, SAW-015 · effort: M · audience: library.maintainer, user.api_docs, contributor.process, infra.test
  The "something is actually wrong or missing" slice of audit-015 (its
  [verified addendum](audits/audit-015-spec-traceability.md#verified-addendum-2026-06-01)).
  - **(a) 5 untested behaviors — tests added, all run green.** `S3-012` (S3 + S3-PyArrow
    non-recursive `delete_folder` on a non-empty folder raises `DirectoryNotEmpty`, in
    `tests/backends/s3/test_moto.py` — the cross-backend conformance test skips it via
    `_skip_flat_namespace`); `HTTP-CON-003` / `HTTP-CON-004` (`ReadOnlyHttpBackend` name +
    capability set, in `tests/backends/http/test_config.py`); `SAW-015` (`ext.otel` span
    over the `open_atomic` lifecycle, in `tests/ext/test_otel.py`); `BATCH-023` (sequential
    batch preserves input order, in `tests/ext/test_batch.py`). Each is a coverage gap, not a
    code bug — the behaviors already held, so the tests pass on first run.
  - **HTTP-CON-004 divergence resolved *toward the code*, not the spec (user-confirmed).**
    The audit hypothesised `LAZY_READ` was an accidental addition to the runtime constant and
    prescribed removing it. Verification falsified that: `read()` returns a live streamed
    response body on every transport (urllib; `requests`/`httpx` with `stream=True`), and
    `FEATURES.md` + the capability matrix + the HTTP guide all already declare `LAZY_READ`.
    The flag is truthful; the stale outliers were spec 032 (HTTP-CON-004) and the
    `ReadOnlyHttpBackend` docstring, both corrected to `{READ, METADATA, LAZY_READ}`. (Audit
    prescription is advisory; diverged per the re-verify-against-code convention.)
  - **(c) STORE-015 renumber.** Spec 001 declared `STORE-015` twice (native_path + glob).
    Kept `native_path` = `STORE-015` (its `NPR-022` test mark rides it); renumbered `glob()`
    → `STORE-018`. Updated the glob cross-refs (spec 018-glob.md, spec 029 ASYNC-053).
  - **BK-251 baseline ratchet.** Removed the 5 now-marked drift entries and the
    `(KIND_DUPLICATE, STORE-015)` entry from `check_spec_marks.py::_BASELINE`; added
    `(KIND_DRIFT, STORE-018)` — `glob()`'s GLOB-* coverage still owes a spec-file mark
    (BK-252). Gate green: `main() == 0`.
  The ~57 unbuilt-Graph IDs (`GR-*`, `ERR-013`) remain owned by ID-127.

- [x] **BK-253 — Disable Hypothesis per-example deadline in test profiles**
  spec: — · effort: S · audience: infra.test
  Surfaced during BK-244 verification: `test_pbt_properties.py::TestConfigFromDict::test_backend_types_preserved`
  failed once under `hatch run test-cov-s1` (pytest `-n auto` + coverage) yet
  passed on every isolated re-run, including 1000 examples — the signature of a
  Hypothesis wall-clock **deadline** flake, not a logic defect (the property is
  sound: `RegistryConfig.from_dict` samples `type` from the valid set and stores
  it verbatim). The `dev` profile (`tests/conftest.py`) set only
  `max_examples=50`, leaving the default 200 ms per-example deadline enabled; CPU
  contention under the standard parallel + coverage gate makes a trivial example
  exceed it and raise `DeadlineExceeded`. Fix: add `deadline=None` to all three
  profiles (`dev` / `ci` / `nightly`). PBTs here assert behaviour, not latency —
  performance is covered by `benchmarks/`. No production-code change.

- [x] **BK-244 — HNS open_atomic / write_atomic upload-failure cleanup: orphan-temp coverage**
  spec: SAW-005, SAW-011 · effort: S · audience: infra.test
  Discovered in PR #689 review of ID-188: the `test_open_atomic_exception_cleanup`
  orphan scan only bites the *caller-exception* path, leaving the Azure HNS
  upload-failure cleanup branch (`except Exception` → `tmp_fc.delete_file()` →
  `_raise_invalid_if_hns_file_ancestor`) without an asserted no-leak guarantee.
  - **Resolution — strengthen the existing real file-ancestor tests, no mocking.**
    The backlog sketch proposed a mock/patch-based failure-injection test, but
    that violates TESTING.md Rule 5/6 (don't mock third-party SDK internals).
    Investigation found the HNS cleanup branch is *already* driven against live
    HNS + replay by the file-ancestor conformance tests (azure inherits
    `rejects_write_under_file_ancestor=true` via `flat_namespace=false`); they
    only lacked the orphan scan.
  - **Sync:** added an orphan-`.~tmp.*` scan plus SAW-005/SAW-011 marks to
    `conformance/test_errors.py::TestWriteErrorFidelity::test_open_atomic_under_file_ancestor_raises_invalid_path`.
    Re-pointed the stale `test_atomic.py` comment that tracked this as BK-244.
  - **Async:** the async store exposes no `open_atomic`, so `write_atomic` is the
    analog; added the same scan + marks to
    `conformance/test_async_extended.py::TestWriteErrorFidelity::test_write_under_file_ancestor_raises_invalid_path`
    (covers `write` and `write_atomic`).
  - **Honest caveat:** the temp upload under a file parent fails *before* the temp
    is committed (temp and final share a parent), so the scan confirms the
    no-leak invariant rather than exercising removal of a committed orphan — the
    committed-temp-then-rename-fails path has no deterministic real-backend
    trigger. Documented in both test docstrings.
  - **Cassettes:** the new `list_files` request was recorded against live HNS via
    targeted single-node `record_cassettes.py --node …[azure_live]` /
    `…[azure_live_async]` (no tree-wipe), scrub-verified (299 cassettes clean),
    and confirmed on Stage-1 replay. All confirmed failing-first (cassette miss)
    then passing.
  - **Discovery:** the async `write_atomic` HNS cleanup unit test
    (`tests/backends/azure/aio/test_config.py::…test_write_atomic_hns_cleans_up_on_failure`)
    mocks `DataLakeFileClient` and asserts `delete_file.call_count` — a latent
    TESTING.md Rule 5 violation, noted for a separate decision (not fixed here).
- [x] **BK-251 — Spec-mark CI gate (`check_spec_marks.py`)**
  spec: — · effort: M · audience: library.maintainer, contributor.tooling
  Root-cause gate for the traceability drift audit-015 exposed. `scripts/check_spec_marks.py`
  maps every spec ID declared in `sdd/specs/` (headings + `ID`-column requirement tables) to
  its `@pytest.mark.spec(...)` usage across the whole `tests/` tree, and fails on three modes:
  **drift** (a shipped, non-allowlisted spec ID no mark cites), **stale** (a mark citing an ID
  no spec declares — the audit's `HTTP-001`), and **duplicate** (an ID declared twice — the
  `STORE-015` collision). Dual-wired into the `lint` script and the lint CI job.
  - **Baseline, not big-bang.** Mirrors `check_formal_trace.py`: a checked-in `_BASELINE` of
    the 166 violations known at landing (165 drift owed to BK-252, plus the `STORE-015`
    duplicate owed to BK-250). A violation outside the baseline fails (new drift); a stale
    baseline entry fails (the gap closed) — so the baseline self-prunes as BK-252/BK-250 land.
  - **Allowlist.** Two classes of declared ID are excused from drift: type-(d) design/meta/
    deferred IDs (seeded from the audit addendum's (d) rows — TLS Phase 2, ext.parquet
    Dagster-v2, async `read_seekable`/`open_atomic` deferrals, graph retry, doc-framework and
    testing-process principles), and implementation-pending Graph IDs (`GR-*`, `ERR-013`) owned
    by ID-127 and absent from `FEATURES.md`.
  - **Non-spec marker namespaces.** `@pytest.mark.spec(...)` is used repo-wide for backlog
    provenance (`BK-/BUG-/ID-/AF-/BL-/UC-NNN`) and docs-framework gate codes (`G-01..G-07`);
    both are excluded from the stale check (they cite real tracked artifacts, not spec
    sections). The extractor also splits comma-joined ID strings (`spec("DAG-002,DAG-003")`).
  - **One genuine stale fixed in-PR:** `tests/test_examples.py` cited a non-existent `HTTP-001`;
    repointed to `HTTP-CON-001`, the construction section the HTTP demo exercises.
  - Test-first guard at `tests/scripts/test_check_spec_marks.py` (extractors, drift/stale/dup,
    allowlist, comma-split, namespace exclusions, baseline shrink, repo-is-green).

- [x] **BUG-214 — S3 `write_atomic` commits a truncated object on mid-stream content failure**
  spec: S3-010, S3PA-013, AW-001, AW-007 · effort: S · audience: user.api
  Found by the ID-200 audit (see
  [research/research-s3-error-mapping-fidelity.md](research/research-s3-error-mapping-fidelity.md)
  § 3(d)). When the *content source* passed to a streaming `write` /
  `write_atomic` raised mid-stream, both S3 backends left a complete-looking
  but truncated object: `S3Backend` because s3fs's `S3File.__exit__` →
  `close()` flushes/completes the upload regardless of the in-flight
  exception; `S3PyArrowBackend` because PyArrow's output stream commits on
  `close()` and cannot be aborted.
  - **Fix (s3fs):** the streaming branch manages the handle explicitly and on
    any exception calls `discard()` (aborts the multipart upload / drops the
    buffer) and neutralises the handle so `__del__` cannot re-commit, then
    re-raises (S3-010). Covers `write` and the delegating `write_atomic`, both
    the single-PUT (≤50 MB) and completed-multipart regimes.
  - **Fix (s3-pyarrow):** PyArrow has no abort primitive, so `write_atomic`
    now buffers the content fully (a `SpooledTemporaryFile`, mirroring
    `open_atomic`) *before* opening the output stream — a content failure
    happens before any upload begins (S3PA-013). Plain `write` keeps streaming.
  - **Scope refinement — plain `write` truncation is a non-defect.** The audit
    framed the truncated object on plain `write` as part of the bug, but per
    AW-007 `write` is the non-atomic alternative and the local backend also
    leaves a partial file on a mid-stream failure. Only `write_atomic` owes
    AW-001 ("no partial content is ever visible"). So plain `write` was left
    streaming (s3fs cleans up for free via the shared `discard()` path;
    s3-pyarrow may leave a partial, like local). Documented on S3-010 /
    S3PA-013 / AW-007.
  - **Tests:** the mid-stream-failure-no-partial assertion landed as a
    cross-backend conformance test
    (`conformance/test_atomic.py::TestBackendWriteAtomic`,
    AW-001/S3-010) that rides every `ATOMIC_WRITE` fixture; an s3fs moto test
    (`test_moto.py::TestBug214MidStreamFailure`) pins the single-PUT +
    multipart + orphan-MPU mechanism; a pyarrow guard
    (`test_pyarrow.py::TestBug214WriteAtomicity`) pins the buffer-before-open
    mechanism without S3. All confirmed failing-first then passing.
  - **Confirmed on real AWS S3** (per CONTRIBUTING.md / TESTING.md Stage-3):
    added an `s3_pyarrow_live` fixture (the S3-PyArrow sibling of `s3_live`) so
    the conformance test runs against real AWS for *both* backends at
    `RS_TEST_LIVE_S3=1 ... --stage=3 -m live`. Both pass.
  - Azure coverage included in-PR: the new conformance test's one missing
    cassette was recorded via a **targeted** `pytest --stage=3 --record -m live`
    run against live HNS (not the all-or-nothing `record-azure` tree-wipe, which
    would churn ~298 cassettes), then scrub-verified
    (`record_cassettes.py --backend azure --verify-only`: 299 cassettes checked,
    account name absent) and confirmed on Stage-1 replay. Azure `write_atomic`
    buffers, so it satisfies AW-001 by construction.

- [x] **BK-235 — Record the Azure cassettes for new conformance tests**
  spec: — · audience: infra.test
  Sixteen conformance tests self-skipped on `azure_replay` for lack of a
  cassette, so the Azure backend was never exercised by those gates. With
  ID-213 (PR #706) closing the last error-class gap, all sixteen pass against
  live HNS, so the whole batch recorded in one
  `RS_TEST_LIVE_HNS=1 hatch run record-azure` run against the live ADLS Gen2
  account `remotestorehns` (2026-05-31).
  - **Pre-flight live dry-run (no `--record`) first**, because `record-azure`
    deletes the entire cassette tree at Step 1 (all-or-nothing): sync 197
    passed / async 95 passed / 0 failed against live HNS confirmed the
    destructive delete was safe to run.
  - The run refreshed the full conformance suite: 253 cassettes deleted →
    298 recorded (scrub-verified clean — no account name survived). Net 55
    new (the 16 target tests' sync/async/param variants, 10 param-id-reorder
    renames where the `azure_async` fixture id moved to the tail of the param
    id, and BK-243's regenerated cassette), 243 refreshed (volatile `ETag` /
    `Last-Modified` churn), 10 stale old-order names dropped.
  - Verified on replay (Stage 1): the 30 target instances pass — no longer
    self-skip; full `azure_replay` suite 292 passed / 6 legitimate semantic
    skips / 0 missing-cassette skips.
  - Removed 28 of ID-213's `# pragma: no cover -- HNS only` markers (15 sync /
    13 async) on the file-ancestor paths the new cassettes now exercise under
    `azure_replay`. Each removal was verified safe with a before/after coverage
    diff: every line its excluded clause re-exposes is executed by replay, so
    the strict (CI-only) 95% gate cannot regress. The remaining markers stay —
    they guard HNS branches replay still does not reach (`_datalake_service` /
    `_fs` client construction, partial `_hns_first_file_ancestor` walks, the
    `delete` / metadata edge clauses).

- [x] **BK-243 — Re-record stale Azure cassette for `test_open_atomic_exception_cleanup`**
  spec: SAW-004, SAW-005, TEST-007 · audience: infra.test
  Co-shipped with BK-235's full cassette refresh. ID-188 had extended
  `test_open_atomic_exception_cleanup` with a `list_files("", recursive=True)`
  orphan-temp scan that the old cassette did not cover, so the cassette was
  deleted and the test self-skipped under `azure_replay`. The BK-235
  `record-azure` run regenerated
  `TestBackendOpenAtomic.test_open_atomic_exception_cleanup[azure].yaml`; the
  test now passes on replay (Stage 1). No code change.

- [x] **ID-200 — Audit s3fs error-mapping fidelity in `_S3Base`**
  spec: — · audience: library.maintainer
  Audit of the s3fs → `_S3Base._s3fs_errors` → `_classify_error` boundary
  against the typed-error contract (S3-015..S3-018). Findings note:
  [`research/research-s3-error-mapping-fidelity.md`](research/research-s3-error-mapping-fidelity.md),
  with a re-runnable moto driver beside it. Five scenarios driven against a
  moto-backed `S3Backend` (Stage 1, in-process; no Docker/AWS):
  - **(a) missing key → `NotFound`** ✅; **(e) directory-marker ambiguity** ✅
    (deterministic exact-key precedence, no confused mix — `is_folder` shadowing
    the co-existing prefix recorded as a known flat-NS limitation, not a defect).
  - **(b) 403 forbidden → `PermissionDenied`** and **(c) expired/invalid
    credentials → `PermissionDenied`** ✅ at the mapping boundary: s3fs's
    `translate_boto_error` maps 403 `AccessDenied`, `ExpiredToken`,
    `InvalidAccessKeyId`, and `SignatureDoesNotMatch` all to `PermissionError`,
    which `_s3fs_errors` maps to `PermissionDenied`. moto enforces neither
    ACL/IAM nor credentials, so the *over-the-wire* path could not be exercised
    in-process — carved to **BK-248** for Stage-3 (MinIO / live `s3_live`).
  - **(d) mid-stream content failure → divergence → BUG-214.** `write` /
    `write_atomic` raise a typed error but **commit a truncated object** (6 MB
    delivered → 6 MB single-PUT object; 55 MB → 55 MB via a *completed*
    multipart upload), because s3fs's `S3File.__exit__`/`close()` commits the
    buffer regardless of the in-flight exception. Breaks the `ATOMIC_WRITE`
    contract; server-independent, so reproducible on moto. `open_atomic`'s
    caller-exception path is unaffected (object absent).
  Spawned: **BUG-214** (the (d) defect, with repro), **BK-248** (Stage-3
  natural-path confirmation of (b)/(c)). Informs **ID-202**'s boto3 error
  mapping. No code or test change in this item (report-only audit; the failing
  test lands with BUG-214 per the bug-fix protocol).

- [x] **ID-213 — Extend ID-209's `InvalidPath` translation to the HNS Azure backend**
  spec: BE-008, BE-012, BE-014, BE-015, BE-018, BE-019 · audience: user.api, library.maintainer, contributor.process, infra.test
  Follow-up to ID-209 (PR #680). ID-209 landed the cross-backend
  file-ancestor contract (write/move/copy under a file ancestor →
  `InvalidPath`; delete/read → `NotFound`; listing → `[]`) for the
  hierarchical backends via native-error translation, and deferred HNS
  Azure under the assumption "HNS has real directories so the gate passes
  once recorded." The BK-235 live-HNS run (account `remotestorehns`)
  falsified that: real ADLS Gen2 *does* error on these scenarios, but the
  Azure SDK raises `ResourceNotFoundError` / `ResourceExistsError` /
  `HttpResponseError(404|409)`, which `classify_azure_error` maps to
  `NotFound` / `AlreadyExists` — the wrong cross-backend class. 8 sync +
  7 async conformance tests failed against live HNS (the async set is one
  smaller: no async `open_atomic` sibling).
  - **Seam chosen: per-method error-path probe, not the classifier.** The
    backlog prescribed discriminating a file-ancestor `error_code` inside
    `classify_azure_error`. That seam cannot work: the same condition needs
    three different outcomes (`InvalidPath` for write/write_atomic/
    open_atomic/move-dst/copy-dst, `NotFound` for delete, `[]` for
    listing), which a pure `(exc, path) → error` classifier cannot pick;
    and the move/copy SDK error is keyed to **src** (live baseline:
    `mcua/move_src.txt` / `mcua/copy_src.txt`) during the DFS rename, so it
    carries no signal about the dst file-ancestor the contract names. The
    fix detects the file ancestor explicitly (mirroring SFTP's
    `_has_file_ancestor`) instead of trusting a native `error_code`.
  - New `_hns_first_file_ancestor` walks the slash-aligned ancestors on the
    *error* path (happy path pays nothing) and inspects `hdi_isfolder` so an
    HNS directory marker is not mistaken for a file. `write` / `write_atomic`
    / `open_atomic` / `move` / `copy` re-raise `InvalidPath` (keyed to dst
    for move/copy); `delete` re-raises `NotFound` (and `missing_ok=True`
    stays a quiet no-op); `list_files` / `list_folders` swallow → `[]`.
    Applied symmetrically to sync `_azure.py` and async
    `aio/backends/_azure.py`.
  - Verified against live HNS (`RS_TEST_LIVE_HNS=1`, no recording): the 8
    sync + 7 async blocked tests pass, the ready tests do not regress, and
    the Stage-1 / local / SFTP / replay suites are untouched (the change is
    confined to the two Azure backend files; `classify_azure_error` is
    unchanged). HNS-only paths carry `# pragma: no cover -- HNS only` until
    BK-235 records the cassettes that will exercise them.
  - Unblocks BK-235 for these eight tests. Parallel to ID-211 (flat-NS HEAD
    pre-check) and ID-212 (SFTP chroot-stat hardening) — all three are
    ID-209 follow-ups along different backends' error-translation paths.

- [x] **ID-212 — Harden SFTP file-ancestor detection against partial-stat-permission setups**
  spec: BE-006, BE-007 · audience: user.api, library.maintainer, infra.test
  Follow-up to ID-209 (PR #680). `SFTPBackend._has_file_ancestor` and
  `_ensure_parent_dirs` both walked the parent chain from the absolute
  SFTP root `/`, stat-ing every component above `self._base_path`. On a
  chrooted / partial-permission deployment where an ancestor above the
  chroot returns `SSH_FX_PERMISSION_DENIED`, the read walk aborted and
  mis-classified a genuine file-ancestor case as
  `RemoteStoreError("Failure")` instead of `NotFound` (diverging from
  BE-006/BE-007's `!PathExists ==> NotFound`), and the write walk
  re-raised the permission error as `PermissionDenied` so even ordinary
  nested writes failed.
  - Consolidated both helpers onto a shared `_base_relative_ancestor_dirs`
    generator whose walk root is `self._base_path`: components at or above
    the base are never probed, so the chroot boundary is never stat'd.
    Ancestors above `base_path` are assumed to exist (the connection-time
    root); base and below are walked exactly as before.
  - Added the `sftp_chroot_inproc` conformance fixture (a
    `ChrootStubSFTPServer` that denies stat at and above a boundary, with
    the backend's `base_path` set to a unique subdirectory below it) and
    wired the read-side `TestReadErrorFidelity` class to
    `include_strict_only=True` so the file-ancestor read / write / move /
    copy gates exercise the restricted-permission case. The fixture failed
    21 error-fidelity cells before the fix and passes after.
  - Dropped the chroot caveat from the `_has_file_ancestor` docstring and
    fixed the misleading "walk from base_path down" comment in
    `_ensure_parent_dirs`.
  - The optional `lstat`-on-immediate-parent second pass from the backlog
    note was not needed: the base-relative walk fully resolves the
    divergence. Discovered as ID-209 round-4 review follow-up.

- [x] **ID-214 — Sweep residual pre-reorg test-path references in non-authoritative docs**
  spec: — · audience: user.site
  Follow-up to ID-203, which realigned the authoritative surfaces but
  deliberately left the same pre-reorg path drift in non-authoritative
  places. The conformance suite was two flat files
  (`tests/backends/test_conformance.py` + `test_conformance_extended.py`)
  before BK-179/188/189/190 split it into per-topic files under
  `tests/backends/conformance/` (with "extended" cases now
  `@pytest.mark.extended_conformance` markers spread across them, plus
  `test_async_extended.py` for async), and backends moved from flat
  per-file homes (`test_azure.py`, `test_s3_shared.py`, …) into
  `tests/backends/<backend>/`.
  - **`docs-src/guides/custom-backend-guide.md` (user-facing).** Reworked the
    two tables structurally — not a 1:1 path swap. The "Conformance suite
    overview" now lists the eight per-topic files under
    `tests/backends/conformance/` (identity, io, listing, atomic, metadata,
    streaming, errors, check_health) with working GitHub links and per-file
    run commands, explains the `@pytest.mark.extended_conformance` marker
    mechanism (extended cases are spread across the topic files, not a
    separate file) and the async sibling `test_async_extended.py`, and the
    checklist table's Basic/Extended rows now point at the directory + marker.
    The two broken `blob/master/tests/backends/test_conformance*.py` links are
    gone.
  - **In-tree test docstrings/comments.** Fixed deleted-file / moved-path
    references in `tests/aio/test_async_cancellation.py`,
    `tests/aio/test_async_pbt_stateful.py` (×2),
    `tests/backends/azure/aio/test_live.py`,
    `tests/backends/azure/test_live_hns.py`,
    `tests/backends/conformance/test_async_extended.py` (×2),
    `tests/backends/conformance/test_identity.py`,
    `tests/backends/s3/test_config.py` (×4), `tests/backends/s3/test_moto.py`,
    `tests/backends/s3/test_pyarrow.py` (×4), `tests/test_pbt_write_result.py`,
    and `tests/test_snippets.py`. Each was verified by grepping the named
    class / test for its actual current home before rewriting (e.g.
    `TestWriteResultConformance` → `conformance/test_atomic.py`,
    `TestDeleteErrorFidelity` → `conformance/test_errors.py`,
    `TestAzureWriteOnHnsDirectory` → `azure/test_config.py`,
    `test_s3_shared.py` → `s3/test_shared.py`, `test_s3_options.py` →
    `s3/test_options.py`, `tests/aio/test_sync_adapter_conformance.py` →
    `tests/backends/conformance/test_sync_adapter_conformance.py`).
  - **`sdd/BACKLOG.md` item body.** The scope text attributed the
    `tests/backends/test_sqlblob.py:131` reference to **BK-235**, but it
    actually lives in **ID-140**'s "Ripple checks" list; corrected it there to
    `tests/backends/sqlblob/test_config.py:148` (the live LAZY_READ-absent
    assertion).
  - **Two discoveries while verifying-before-swapping** (per the "don't assume
    a path swap" rule): (1) the `test_sqlblob.py` ref was in ID-140, not BK-235
    as scoped; (2) `tests/aio/test_async_pbt_stateful.py` named a phantom
    `test_async_memory.py` that never existed — the dangling name was dropped
    and its example-based negative-path coverage pointed at the real home,
    `tests/aio/test_async_store.py` (PR #699 review corrected an initial mis-aim
    at the abstract-contract `test_async_backend.py`).
  - **CHANGELOG** — audience `user.site` (the guide is user-facing) ⇒ entry
    required (per `_schema.yml` derived rule), unlike ID-203 which was
    `infra.test`-only. Bare-name references to files that merely moved (e.g.
    `test_sync_adapter_conformance.py` in `dafny_oracle_async.py` /
    `test_registry.py`, the current path in `scripts/mutate_scopes.py`) were
    left as-is; CHANGELOG / `sdd/research/` / `sdd/rfcs/` / `sdd/audits/` /
    `sdd/traces/` / `BACKLOG-DONE.md` mentions are point-in-time history and stay.
  Trace: `sdd/traces/id-214-test-path-refs.yml`.

- [x] **ID-196 — `RemotePath.as_posix()` and pathlib parity audit**
  spec: PATH-016, PATH-017 · audience: user.api
  `RemotePath.__str__` already returned the POSIX-style key, but `.as_posix()`
  raised `AttributeError`, breaking pathlib muscle memory.
  - **`as_posix()` shipped as a method, not a property** (PATH-016). The
    backlog sketch said "one-line property", but `pathlib.PurePath.as_posix`
    is a *method* — the whole point is muscle memory, and a property would make
    `p.as_posix()` raise `TypeError` (calling the returned `str`). It returns
    `self._path` (always forward-slash); `RemotePath.ROOT.as_posix() == "."`.
  - **`__fspath__` deliberately NOT added** (PATH-017). The backlog flagged it
    as a parity gap, but `RemotePath` is a remote-store *key*, not a local
    path; making it `os.PathLike` would let it slip into `open()` / `os.path.*`
    and silently target the local filesystem. Pinned the non-goal as a testable
    invariant (`not isinstance(p, os.PathLike)`, `os.fspath(p)` raises).
  - **Spec correction.** The backlog cited `NPR-020`, which is
    `Backend.native_path` — unrelated. The contract lives in the path model;
    added `PATH-016` / `PATH-017` to `sdd/specs/004-path-model.md`.
  - **Parity audit → ID-215.** Catalogued the remaining `PurePath` members
    (`stem`, `suffixes`, `with_*`, `joinpath`, `parents`, `match`,
    `relative_to`, …) as deferred candidates; recorded informatively in spec
    004 and spun out as ID-215 rather than widening this S-sized item.
  Trace: `sdd/traces/id-196-as-posix-pathlib-parity.yml`.

- [x] **ID-203 — Align `tests/` folder structure with `src/` package layout**
  spec: TEST-002, TEST-003, TEST-010 · audience: infra.test
  Closed by realization plus a doc-drift sweep. An audit (this PR) found the
  substantive reorg had already landed incrementally — **BK-179** (Phase 1:
  fixture registry + reorganisation), **BK-188** (Phase A: backend-specific
  evictions), **BK-189** (Phase B: `tests/ext/` package), **BK-190** (Phase C:
  placement checks + spec 048 / TESTING.md). The current tree already
  mirrors `src/remote_store/` (`tests/aio/`, `tests/ext/`, `tests/scripts/`,
  `tests/e2e/`, `tests/backends/{conformance,fixtures,cassettes,<backend>}/`),
  `scripts/check_test_placement.py` (rules S, B, E) passes, and no top-level
  test imports a concrete cloud backend (only `test_examples.py`, permanently
  grandfathered). **No files moved**; behaviour unchanged.
  - **One structural clarification.** `tests/backends/test_flat_ns.py` is the
    lone bare `test_*.py` directly under `tests/backends/` — a white-box unit
    test of the shared helper `backends/_flat_ns.py` (imported by S3 /
    Azure-flat / SQLBlob), with no single per-backend home. Left in place and
    sanctioned by a new spec 048 TEST-010 "Shared backend helpers" clause (a
    backends-package-level shared module maps to `tests/backends/test_<f>.py`,
    the one place a bare test file is allowed there), restated in TESTING.md
    § Test Subpackage Placement.
  - **Doc-drift sweep** (refs to pre-reorg test paths the earlier phases left
    behind, per principle 3): `CONTRIBUTING.md` (§ Adding a Backend steps 3–4
    → `tests/backends/fixtures/` + `tests/backends/conformance/`; § Adding an
    Extension step 6 → `tests/ext/test_<name>.py`); specs `003` (→
    `conformance/test_identity.py`, `conformance/test_atomic.py`), `011` (→
    `s3/test_shared.py`), `022` (→ `conformance/test_atomic.py`), `045` (×5 →
    `conformance/test_atomic.py`); the `CAPABILITIES ClassVar` ripple-check row
    in `sdd/CLAUDE-REFERENCE.md` (→ `conformance/test_identity.py`); and a
    stale comment in `tests/conftest.py` naming two deleted files.
  - **No CHANGELOG** — audience `infra.test` only (per `_schema.yml` derived
    rule). Note: the BACKLOG entry's `library.maintainer` tag is not in the
    schema enum; corrected to `infra.test` (same kind of tag-correction
    ID-172 / ID-173 needed).
  - **Discovery follow-up (ID-214).** The same pre-reorg path drift survives in
    non-authoritative surfaces left out of this scope: the user-facing
    `docs-src/guides/custom-backend-guide.md` (broken GitHub links to
    `test_conformance.py` / `test_conformance_extended.py`, now a directory of
    per-topic files — needs structural rework, user-facing so CHANGELOG-bearing),
    several in-tree test docstrings/comments (e.g. `tests/aio/test_async_cancellation.py`,
    `tests/backends/s3/test_*.py`, `tests/test_pbt_write_result.py`), and an
    active `BACKLOG.md` item body. CHANGELOG / research / RFC mentions are
    point-in-time history and stay. Spun out as ID-214.
  Trace: `sdd/traces/id-203-tests-layout.yml`.

- [x] **BK-247 — Reconcile `check_formal_trace.py` baseline: migrate `ID-134` marker, close CAP-004 / DEPTH-001 / NPR-020, correct WR-008 / WR-010 comments**
  spec: BE-017, CAP-004, DEPTH-001, NPR-020 · audience: infra.test, contributor.tooling
  Leftover from ID-187. That item *added* `BE-017` / `ASYNC-017` spec
  markers to the `GetFolderInfo` aggregate tests but left the original
  `@pytest.mark.spec("ID-134")` backlog-ID citations in place (see the
  ID-187 trace, implement step: "spec markers BE-017 + ID-134"). A backlog
  ID is not a spec section, so `check_formal_trace.py` flagged each
  citation as an F2 (`conformance-cites-unknown-spec`); the violation was
  parked in `_BASELINE` with a note to "migrate to BE-017 when ID-187
  lands". ID-187 landed without the migration, so the F2 never went stale
  and the baseline comment rotted into the future tense about a shipped
  item. Reviewing the remaining F1 gaps surfaced three more that lacked
  only the marker, and two Store-layer clauses whose owner comments named
  already-shipped items (ID-185, ID-190).
  - **ID-134 migration.** Removed the 7 `@pytest.mark.spec("ID-134")`
    markers: 4 in `tests/backends/conformance/test_metadata.py`, 2 in
    `tests/backends/conformance/test_async_extended.py`, 1 in
    `tests/test_pbt_folder_info_aggregates.py`. Every site retained its
    `BE-017` / `ASYNC-017` spec-section marker, so coverage is unchanged
    (`BE-017` still reports `tested`). Provenance docstrings left intact.
    Removed `(KIND_TEST_BAD_ID, "ID-134")` and its F2 comment from `_BASELINE`.
  - **Closed three F1 gaps.** `CAP-004` → a new universal
    `test_identity.py::TestBackendCapabilityGate` that picks an undeclared
    capability and asserts `capabilities.require(missing)` raises
    `CapabilityNotSupported` with `exc.capability == missing.value` — the
    Dafny `RequireCapability` postcondition (error carries the capability
    name). The existing `unwrap` test was the wrong witness: it raises
    without going through `require()` and names `capability="unwrap"`.
    `DEPTH-001` → marked `test_listing.py::test_list_files_recursive_max_depth`
    (asserts `d <= max_depth` per returned file, the DEPTH-001 inclusive-boundary
    reference algorithm). `NPR-020` → marked
    `test_identity.py::test_native_path_round_trip` (asserts
    `to_key(native_path("some/key")) == "some/key"`). Removed all three from
    `_BASELINE`.
  - **Corrected two stale baseline comments (kept baselined).** `WR-008`
    (`Store.head()`) and `WR-010` (USER_METADATA strict gate) are both
    Store-layer clauses the conformance dir cannot drive: `head()` is a
    Store composition over `get_file_info` (spec 045 § WR-008), and the
    WR-010 gate fires once in the Store *before* delegating (ADR-0026), so a
    non-declaring backend never receives non-empty metadata and backends
    deliberately do not re-check it. Their real coverage lives in
    `tests/test_store.py::TestStoreHead` / `::TestMetadataGate`. Rewrote both
    comments to state they are structural F1s, not backfill gaps with a
    pending owner. Gate now reports **2 baselined gaps**, no new or stale
    violations.
  No CHANGELOG entry: audience is `infra.test` + `contributor.tooling`
  only (no `user.*`), per the trace-schema derived rule.
  Trace: `sdd/traces/bk-247-id134-marker-migration.yml`.

- [x] **ID-173 — `check_api_docs.py` Phase 4 — `__all__` ↔ `docs-src/reference/api/index.md`**
  spec: — · audience: contributor.tooling
  The staged rollout's final, deliberately-separate piece: a *different IR*
  from the method-caps checker — `{symbol_name: kind}` rather than
  `{method: caps}` — so it has its own extractor trio + compare run as a
  second pass in `main()`, untangled from the `PAGES` loop. Confirmed the
  design with the maintainer before coding (the backlog's stop-and-confirm).
  - **Symmetric three-source surface.** The maintainer's steer was symmetry:
    the Async section links a *third* namespace, so `remote_store.aio.__all__`
    is treated as a co-equal source alongside `remote_store.__all__` (primary)
    and `remote_store.backends.__all__`. `exports_symbols` walks all three.
  - **`ext.*` exclusion.** ~33 symbols re-exported from `remote_store.ext.*`
    are documented as *module* rows in the index Extensions section, not per
    symbol; excluded by `__module__` prefix (not a hardcoded list).
  - **Backend-companion exemption (explicit allowlist).** `ArrowSerializer`,
    `ResultSerializer` (on `sql-query.md`) and `AsyncAzureBackend` (on
    `aio.md`) are in their `__all__` but have no standalone index row — they
    "belong to their backend" in the docs. A first cut *derived* this from
    `:::` renders; review (PR #697) showed that masks dropped rows — ~every
    class is `:::`-rendered on its own page, and shared multi-class pages
    (`aio.md`, `errors.md`, `models.md`) make no robust derivation possible.
    Shipped instead: an explicit `_INDEX_EXEMPT` frozenset of the three
    companions, with `directive_symbols` repurposed to *police* it in `main()`
    via `allowlist_staleness_errors` — each entry must be public, `:::`-rendered,
    and absent from the index, so `gen-api-check` itself (not just
    `test_allowlist_is_not_stale`) fails on a stale allowlist.
  - **Bidirectional compare.** Unlike the coverage-only method-caps compare
    (over-claims tolerated), this is a true set diff: MISSING (public symbol
    with no index row and not on `_INDEX_EXEMPT`) and EXTRA (index link with
    no backing `__all__` symbol) are both errors. `kind` enriches messages
    only. Live surface (full extras): 53 public symbols, index green.
  - **No drift found** — `index.md` already mirrored the public surface once
    the `ext.*` and backend-companion rules were applied.
  - **Environment sensitivity (new vs the static graph IR).** The exports
    extractor imports the live packages, so optional-dependency symbols only
    appear under a full-extras env. Like the strict coverage gate, the check
    is correct under `hatch` / CI, not a bare-`python` sandbox; documented in
    the module docstring and the failure hint.
  - **Wiring:** no new wiring — the second pass rides the existing
    `gen-api-check` (already in `hatch run lint`, `preflight`, and CI).
    Updated the success line and split the failure hint into method-caps vs
    index-parity guidance. 22 new tests: the extractor trio, `compare_exports`
    (MISSING/EXTRA/exempt + the dropped-primary-row regression), and
    `allowlist_staleness_errors`, each in isolation, plus a `TestLiveIndex`
    round-trip.
  - **No CHANGELOG** — audience `contributor.tooling` only (per `_schema.yml`
    derived rule). Note: the BACKLOG entry's `platform.tooling` tag was not in
    the schema enum; corrected to `contributor.tooling` (same fix ID-172 needed).
  - Closes the `check_api_docs.py` staged rollout (ID-170 → ID-173). Unblocks
    ID-203 (tests/ folder reorg), which waited on the async API surface settling.

- [x] **ID-172 — `check_api_docs.py` Phase 3 — `AsyncStore`/`AsyncBackend` → `aio.md`**
  spec: ASYNC-045a · audience: contributor.tooling
  Spun off from ID-171; ID-192 (aio.md rework) and ID-194 (async gate
  extension) prerequisites had landed. The backlog framed this as "adding
  the [PAGES] entries is the only remaining step" — that under-estimated it.
  Two extractor gaps surfaced on first run against `aio.md`:
  - **Submodule public re-export.** The page uses `remote_store.aio.AsyncStore.*`,
    which matched neither `page_class_methods` prefix (internal qname, or the
    top-level `remote_store.<Class>` form). Replaced the hardcoded
    `remote_store.{short_class}.` prefix with a derived public path that
    drops `_`-prefixed module segments — sync-safe (`store.md`/`backend.md`
    stay green) and correct for the `aio.` submodule.
  - **Heading level.** Single-class pages put capability groups at `## H2`;
    the multi-class `aio.md` nests them at `### H3` under each class's `## H2`,
    so H2-only section splitting let a section-level `Requires` admonition
    bleed across the whole class. Now splits on H2 *or* H3.
  - **AsyncBackend was vacuous** (no async-backend gate edges in the graph).
    Per the in-scope override decision, added `_ASYNC_BACKEND_GATING` to
    `scripts/gen_graph.py` (mirrors `_BACKEND_GATING` minus
    `read_seekable` / `open_atomic`; 14 entries) plus an AsyncBackend
    method/req/gates/of emission loop. Graph: 142 → 170 nodes, 258 → 286 edges.
    Specced as **ASYNC-045a** (referencing BE-027's table); BE-027 cross-links back.
  - **Drift caught (the verifier earning its keep):** the `Requires
    Capability.GLOB` note in `aio.md`'s `AsyncBackend` section sat *before*
    `::: AsyncBackend.glob` (so it scoped to `iter_children`) — the same
    placement bug ID-170 caught in `store.md`. Moved it after the directive.
  - **Surprising ripple:** `docs-src/explanation/graph_viz.html` is generated
    from `graph.json`; the gate additions made it stale (caught by
    `test_graph_viz_html_is_up_to_date`). Regenerated via `hatch run gen-graph-viz`.
  - Added four `PAGES` entries (AsyncStore + AsyncBackend → `aio.md`), updated
    the error-hint to name all four gating dicts, and bumped the module
    docstring (Phase 3). `TestLivePages` auto-covers the new entries; added
    `test_real_graph_async_store_methods` / `test_real_graph_async_backend_methods`,
    `aio.`-prefix + H3-scoping page tests, and gen_graph tests for the new
    constant, its sync-mirror delta, node emission, and the METADATA-only
    `get_folder_info` (no async-backend dual gate, matching sync Backend).
  - **No CHANGELOG** — audience `contributor.tooling` only (per `_schema.yml`
    derived rule). Note: the BACKLOG entry's `platform.tooling` tag was not in
    the schema enum; corrected to `contributor.tooling`.
  - **Remaining:** `__all__` ↔ `index.md` → ID-173 (different IR; separate PR).

- [x] **ID-194 — gen_graph.py async gate extension (prereq for ID-172)**
  spec: — · audience: contributor.tooling
  Sibling of ID-171 (Backend gate extension). `gen_graph.py` already
  emitted method/req/gates/of edges for `Store` and `Backend`; AsyncStore
  had no edges, so any future PAGES entry for `aio.md` would have been
  vacuous and ID-172 was blocked.
  - Added `_GATING: dict[str, Capability]` (17 entries) to
    `src/remote_store/aio/_async_store.py`, mirroring sync `_store._GATING`
    minus `read_seekable` / `open_atomic` (no async equivalents).
    Placement matches sync `Store` — not the `_BACKEND_GATING` precedent —
    because AsyncStore is the close analogue of Store (concrete class with
    runtime enforcement), whereas Backend is an ABC with no runtime
    gating. Initial PR-694 push placed `_GATING` in `_async_store.py`
    without a runtime consumer and CodeQL flagged the unused global —
    fixed by adding an `AsyncStore._gate()` helper that consumes `_GATING`
    at runtime and refactoring every `self._backend.capabilities.require(
    Capability.X, ...)` site to `self._gate("method")`. Conditional
    `USER_METADATA` gates on `write` / `write_atomic` stay inline (not in
    `_GATING`).
  - Extended `scripts/gen_graph.py` with `_async_store_gating()` helper
    and an AsyncStore method/requirement-nodes loop mirroring the sync
    Store loop. Dual-gate special case for `AsyncStore.get_folder_info`
    (METADATA primary, LIST when `max_depth` is set). Graph grows
    107 → 142 nodes (+35), 222 → 258 edges (+36).
  - Added three new tests to `tests/scripts/test_gen_graph.py`:
    `test_async_store_gating_keys_match_async_store_members`,
    `test_async_store_method_nodes_emitted`,
    `test_async_store_get_folder_info_dual_gate`. Also closed an
    existing gap with `test_store_gating_keys_match_store_members` —
    the runtime drift guard in `build_graph()` covered the same case
    but a unit test fails earlier and closer to the dict.
  - Ripple: extended both the Pre-work index row and the Detailed-checklist
    entry for `_GATING` in `sdd/CLAUDE-REFERENCE.md` to record the
    two-constants split and call out `aio/_async_store.py` separately.
    No spec edit (BACKLOG `spec: —`); spec 001/029 do not contain a
    centralised gate table to mirror, so the spec ripple was a no-op.
  - **Remaining** (ID-194 brief): nothing — ID-194 ships the emitted
    edges. PAGES wiring for `aio.md` and the error-hint update in
    `check_api_docs.py` belong to ID-172 (now unblocked).
  Trace: `sdd/traces/id-194-gen-graph-async-gate.yml`.

- [x] **ID-210 — Async Dafny oracle: certify async conformance against the verified `MemoryBackend`**
  spec: ASYNC-004, ASYNC-005, ASYNC-006, ASYNC-007, ASYNC-008, ASYNC-010,
  ASYNC-012, ASYNC-013, ASYNC-014, ASYNC-015, ASYNC-016, ASYNC-017, ASYNC-018,
  ASYNC-019, ASYNC-020, ASYNC-024, ASYNC-029, ASYNC-047 · audience: infra.test
  Wave 1 (T) test-backfill. Closes the gap spun off from ID-193 close-out:
  the sync conformance suite has parametrised `dafny_oracle` as a peer
  backend since the oracle landed, but the async suite ran only against
  `memory_async_native`, `memory_async_adapted`, `local_async_adapted`, and
  the Azure async fixtures — never against the compiled, verified-by-
  construction `MemoryBackend` from `sdd/formal/MemoryBackend-py/`. The
  async-shaped contract was therefore cross-checked between two Python
  implementations (`AsyncMemoryBackend` and `SyncBackendAdapter(MemoryBackend())`)
  rather than against a verified oracle, weakening the (T) leg for
  async-only spec divergence.
  Added a `dafny_oracle_async` fixture composing
  `SyncBackendAdapter(DafnyOracleBackend())`, registered with
  `is_async=true` in `tests/backends/fixtures/fixtures.toml`. The
  registry-driven `pytest_generate_tests` hook in
  `tests/backends/conformance/conftest.py` picks it up automatically, so
  every test in `test_async_extended.py` (96 collected) now runs against
  the verified oracle alongside `memory_async_*` / `local_async_adapted`
  — 95 pass, 1 skips on capability grounds, identical to the
  `memory_async_adapted` baseline. `SyncBackendAdapter` is itself
  certified by `test_sync_adapter_conformance.py` (ASYNC-030..ASYNC-035),
  so the composition `verified-by-construction sync oracle ∘ certified
  adapter` is honest end-to-end without introducing a parallel
  `AsyncDafnyOracleBackend` class to maintain. No `.dfy` change and no
  re-translation: the contract is pure (T) wiring.
  **Out of scope** (deliberately not opened as a follow-up): native-
  `AsyncBackend` refinement in Dafny. Async-native semantics that the
  `to_thread`-bridged sync oracle cannot express (concurrency ordering,
  mid-await cancellation) are not currently observed in the conformance
  suite; revisit only if a divergence emerges that the bridge masks.
  Trace: `sdd/traces/id-210-async-dafny-oracle.yml`.

- [x] **ID-191 — Move atomicity: model the observable contract, then enforce it**
  spec: BE-018 · audience: infra.test
  Wave 1 (C)+(T) pair, sibling of ID-188 (PR #689). Closes BE-018 Gap 5
  at both the contract-definition and the contract-enforcement layers:
  a refinement that declares `CapAtomicMove` and exposes `CopyDone`
  (src gone, dst not yet written) as a "completed" move now fails to
  verify in Dafny.
  (C-definition) Added `sdd/formal/ResourceSafety.dfy` § 2.3
  "Observable contract for atomic-move-capable backends": a new
  `datatype MoveContract = ObservedDeleteDone | ObservedFailed(reason)`
  with no `CopyDone` variant by construction; predicate
  `ObservableForAtomicMove(phase) { phase != CopyDone && phase !=
  Initial }`; total `function Observe(phase): MoveContract` over the
  predicate's domain. Two structural bindings live at the
  runtime-state model: `method AtomicMoveIsObservable` actually calls
  `AtomicMove` and asserts the predicate on the returned phase (so
  postcondition drift on `AtomicMove` breaks verification);
  `CopyDeleteMove` itself gained the postcondition `srcExists &&
  (!dstExists || overwrite) && deleteFails ==>
  !ObservableForAtomicMove(phase)`, with the matching assert in the
  `deleteFails` branch, so the structural reason copy-then-delete is
  a strictly weaker contract is enforced on the method that produces
  the state. `ObservedFailedPreservesSource` formalises the BE-018
  "rollback, source preserved" clause: with `Initial` excluded from
  the predicate, a `Failed` observation is structurally bound to a
  `Failed(_,_)` runtime phase only.
  (C-enforcement) `sdd/formal/BackendContract.dfy` now `include`s
  `ResourceSafety.dfy` and `Backend.Move`'s signature carries a `ghost
  phase: MovePhase` output. Two new trait postconditions: `r.Ok? ==>
  phase == DeleteDone` (every successful Move terminates in
  src-gone-dst-present, regardless of capability) and `CapAtomicMove
  in capabilities ==> ObservableForAtomicMove(phase)` (the
  capability-gated atomicity clause — declaring CapAtomicMove obliges
  the refinement to expose a phase that excludes CopyDone and
  Initial). Both `MemoryBackend` and `MemoryBackendMinimal` assign
  `phase` in every branch of their Move body (`DeleteDone` on the
  happy path; specific `Failed("initial", ...)` reasons on each error
  path), discharging the new postcondition structurally. A future
  `S3Backend.Move` refinement that declared CapAtomicMove and assigned
  `phase := CopyDone` in any branch would fail verification — exactly
  the enforcement claim BE-018 Gap 5 names.
  Ghost outputs erase at compile time, but re-translating
  `sdd/formal/MemoryBackend-py/module_.py` via `dafny build -t py` (then
  `scripts/_dafny_classorder.py`) re-emits the now-visible
  ResourceSafety datatypes (`HandleState`, `Resource`, `WrapPipeline`,
  `MovePhase`, `MoveContract`, `ConnectionState`) and helper methods
  alongside `Backend` / `MemoryBackend` / `MemoryBackendMinimal`. The
  `Backend.Move` Python signature is unchanged (ghost erased); the
  `DafnyOracleBackend` adapter in `tests/backends/dafny/_helpers.py`
  needs no change. All `dafny_oracle` parametrisations of the move /
  copy conformance pass against the regenerated module.
  Verifier totals: 554 verified, 0 errors across BackendContract.dfy
  (51), MemoryBackend.dfy (478), ResourceSafety.dfy (16), and
  DepthCounting.dfy (9). Each new ResourceSafety / BackendContract
  clause carries `// @spec BE-018`.
  (T) Added `TestMoveCrashInjection::test_partial_move_preserves_at_least_one_copy`
  to `tests/backends/conformance/test_atomic.py`, parametrised over a
  `_CRASH_POINTS` matrix of two protocol shapes — `after_copy`
  (`inner.copy(src, dst); raise`) discharges the left disjunct of
  BE-018's OR (`src_present`); `after_delete` (`inner.copy(src, dst);
  inner.delete(src); raise`) discharges the right (`dst_present`). The
  single contract assertion `assert src_present or dst_present` is
  thereby non-trivially exercised from both directions — a buggy
  backend that left both gone (e.g. `delete(src); raise` without
  copying first) would fail it. Whichever side(s) survive, their
  content is verified intact (BE-018 forbids silent corruption
  alongside the non-loss invariant). The class is *not* parametrised
  over `fixture_params`: the contract is on the move *protocol*, not
  on any concrete backend. The `@pytest.mark.spec("BE-018")` marker is
  for traceability only; `check_formal_trace.py` sees no new F1 / F2
  (BE-018 was already in D and T).
  Trace: `sdd/traces/id-191-move-atomicity-observable-contract.yml`.

- [x] **ID-188 — Resource safety: prove the quality flags, then enforce cleanup**
  spec: SIO-001, SIO-008, SIO-009, SAW-004, SAW-005 · audience: infra.test
  Wave 1 (C)+(T) pair landed in one PR.
  (C) Introduced `datatype ReadStream = ReadStream(content, seekable)` in
  `sdd/formal/BackendContract.dfy` so `Backend.Read` returns a stream model
  rather than raw bytes; added the SIO-008 postcondition
  `r.Ok? && CapSeekableRead in capabilities ==> r.value.seekable`; both
  `MemoryBackend` and `MemoryBackendMinimal` refinements were updated to
  wrap content as `ReadStream(content, true)` and re-verified
  (`51 verified, 0 errors` on the contract; `478 verified, 0 errors` on the
  refinement). Added `CapLazyRead` as an advisory stub variant — Dafny
  Read materialises content, so "no I/O before first read" is a runtime
  protocol property over the BinaryIO wrapper that the model deliberately
  does not track; the Python conformance test `test_read_is_lazy`
  remains the load-bearing check for SIO-009. Re-translated
  `MemoryBackend-py/module_.py` via `dafny build -t py` and re-applied the
  class reorder; updated `tests/backends/dafny/_helpers.py` to unmarshal
  the new `ReadStream` shape. Added a new conformance test
  `TestStreamingConformance::test_read_returns_seekable_stream_when_declared`
  in `tests/backends/conformance/test_streaming.py` carrying
  `@pytest.mark.spec("SIO-008")`, which the DafnyOracleBackend certifies
  by construction (`io.BytesIO` is always seekable). The
  `check_formal_trace.py` matrix now reports SIO-008 as `tested`.
  (T) Extended `test_open_atomic_exception_cleanup` in
  `tests/backends/conformance/test_atomic.py` with a
  `list_files("", recursive=True)` scan after the forced failure: the
  fixture is function-scoped and writes nothing before the failed
  `open_atomic`, so any residual entry is an orphan temp artefact from a
  backend's per-strategy cleanup path (see spec 022 § Per-backend
  strategies). Added `@pytest.mark.spec("SAW-005")` alongside the
  existing SAW-004 marker (the new clause is exactly SAW-005's
  cleanup-on-failure obligation). The stale
  `TestBackendOpenAtomic.test_open_atomic_exception_cleanup[azure].yaml`
  cassette was deleted (new HTTP `list_files` request not recorded); the
  TEST-007 missing-cassette skip hook covers the gap until the next
  cassette refresh — tracked as BK-243.
  Gap-table row 6 in `sdd/formal/README.md` extended to cite SIO-008
  alongside SIO-001.
  Trace: `sdd/traces/id-188-quality-flags-cleanup.yml`.

- [x] **BK-246 — Strip internal tracker IDs from published docstrings and `docs-src/`; add lint gate**
  spec: — · audience: user.api_docs, contributor.process, contributor.tooling
  Audit on branch `claude/backlog-refs-api-docs-8o2Jq` found backlog
  and spec IDs leaking into prose users see — Python docstrings
  rendered onto `docs-src/reference/api/*.md` by mkdocstrings, plus a
  handful of `docs-src/` markdown pages, plus repo-root dual-classified
  pages. Discovered when the kwarg description for
  `S3Backend.__init__` was found to read "closing the ID-209
  cross-backend gap … See spec 003 § BE-008 and ID-211." Violates
  `sdd/CONTENT-RULES.md` Rule 1 (6-month test — tracker IDs are
  meaningless to package consumers and rot quickly) and Rule 5 (docs
  describe the pattern, not internal coordinates).
  Originally filed as BK-243; renumbered to BK-246 after PR #689
  (ID-188) took BK-243, BK-244, and BK-245 for unrelated work during
  this branch's review window.
  (T) New `scripts/check_no_tracker_refs.py` lint gate scans every
  docstring under `src/remote_store/` (via `ast.get_docstring`, so
  ``#`` comments inside source are out of scope) and every `.md` under
  `docs-src/` plus `README.md` / `FEATURES.md` / `CONTRIBUTING.md`.
  Matches any backlog or spec coordinate via a structural
  ``PREFIX-NNN`` pattern (so every present and future spec section
  prefix is caught without enumeration), plus `spec NNN` ordinals,
  internal SDD docs (`RFC-0NNN`, `ADR-0NNN` — leading-zero zero-pad,
  so IETF `RFC-3986`-style refs stay clean), and `PR #NNN`. External
  standards and codes (`HTTP-NNN`, `CVE-…`, `UTF-N`, `ISO-…`,
  `IEEE-…`, `PEP-…`, `SHA-…`, `MD5-…`, `SSH-N`) are exempt via
  `_EXTERNAL_PREFIXES`; the conda-forge staged-recipes PR reference is
  the only line-level allowlist. Wired into `hatch run lint` and the
  CI lint job. Out of scope: `sdd/**`, `CHANGELOG.md`,
  `DEVELOPMENT_STORY.md`, `CLAUDE.md`, `AGENTS.md`, `tests/`,
  `.claude/`, `docs-src/_data/`, and `#` comments inside Python
  sources.
  (C) Cleanup sweep — 178 leak sites across 24 files. Backend ABCs
  (`_backend.py`, `aio/_async_backend.py`) and Store/AsyncStore Raises
  rows rewritten to describe the file-ancestor `InvalidPath` rule
  directly. Flat-namespace backend constructors
  (`S3Backend`, `S3PyArrowBackend`, `AzureBackend`, `AsyncAzureBackend`,
  `SQLBlobBackend`) get the `reject_write_under_file_ancestor` kwarg
  prose rewritten as user-facing trade-off (per-HEAD cost, no-slash
  short-circuit, HNS deferred-contract caveat) without any tracker
  IDs. `AsyncBackendSyncAdapter` and its support classes
  (`_ChunkPullReader`, `_AsyncIteratorBridge`, `_SpoolAndFlush`) lose
  every `ASYNC-NNN` / `ADR-0025` / `spec 029` reference from module,
  class, and method docstrings. Internal `_maybe_check_no_file_ancestor`
  helpers on the four flat-NS backends, `_flat_ns.py` module +
  helpers, `_sftp.py::_has_file_ancestor` + `_ensure_parent_dirs`,
  `aio/backends/_memory.py`, `_capabilities.py`, `_proxy.py`,
  `ext/__init__.py`, `ext/cache.py`, and `ext/dagster.py` (29 leak
  sites across every Dagster serializer / IO manager / compute log
  manager docstring) all rewritten. `docs-src/` markdown:
  `explanation/architecture.md`, `explanation/graph-ir.md`,
  `guides/async-sync-bridges.md`, `guides/backends/azure-hns-setup.md`,
  `guides/extensions.md`, `guides/glob-pattern-matching.md`,
  `index.md`, `reference/api/aio.md`, `reference/api/proxy.md`, and
  `reference/migration.md` (12 BK/BUG/ID/ADR refs in section headers
  stripped). Repo-root `CONTRIBUTING.md` and `FEATURES.md` cleaned;
  `scripts/drift_check.py` template fixed so the generated
  `docs-src/reference/tested-versions.md` regenerates clean. Gate
  reports 0 violations after the sweep. `tests/scripts/
  test_check_no_tracker_refs.py` covers the regex set, the allowlist,
  Python/markdown scanners, the inline-comment carve-out, and includes
  an integration guard (`test_real_repo_is_clean`) so any future leak
  fails this test.
  Trace: `sdd/traces/bk-246-tracker-id-cleanup.yml`.

  Review (PR #690, in-PR): the original lint gate enumerated 24 spec
  prefixes and missed about 20 active prefixes used across
  `sdd/specs/` (S3-, AZ-, MEM-, GLOB-, CACHE-, BATCH-, RETRY-, HC-,
  ITER-, WT-, HTTP-, STREAM-, INTEG-, DIGEST-, SEEK-, TLS-, PARQ-,
  XW-, AW-, etc.) — the very regression class this PR was meant to
  police. The gate was rewritten around a structural
  ``[A-Z][A-Z0-9-]*-\d+`` pattern plus a compound-aware external-prefix
  carve-out (`HTTP-NNN` status codes external, `HTTP-CON-NNN` spec
  sections internal; `CVE-YYYY-NNNN` compound-aware; `RFC-`/`ADR-`
  leading-zero pad means internal). A new
  `test_every_spec_prefix_is_flagged` discovers prefixes from
  `sdd/specs/*.md` at test time and asserts each is flagged, so adding
  a new spec section without updating the regex fails the test
  instead of silently widening the leak surface. The sweep across the
  newly-caught prefixes added 9 fixes (S3-026 in `s3.md`, GLOB-014 in
  `sql-blob.md`, EW-001..EW-004 in sync + async `ext/write.py`,
  CACHE-001 in `ext/cache.py`). The `sdd/CLAUDE-REFERENCE.md`
  ripple-check row and the BACKLOG-DONE entry above were re-written
  in principle terms after the same enumeration concern surfaced in
  review.

- [x] **ID-211 — write-under-file HEAD pre-check for flat-namespace backends**
  spec: BE-008, BE-018, BE-019, ASYNC-008, ASYNC-010, ASYNC-018, ASYNC-019 · audience: user.api, library.maintainer, infra.test, contributor.process
  Follow-up to ID-209 (PR #680). ID-209 landed the cross-backend
  `InvalidPath` contract for write/move/copy under a file ancestor but
  carved out flat-namespace backends (S3, Azure non-HNS, SQLBlob) via
  `_skip_flat_namespace` on the conformance gate because detecting a
  file ancestor on those backends costs an extra HEAD round trip per
  slash-aligned ancestor. The user nominated an O(1) optimisation —
  skip the gate when the path has no slash — so the cost only applies
  to nested-path writes. ID-211 measures whether shipping the gate is
  worth it, and on what terms.
  (C) New shared helper module `src/remote_store/backends/_flat_ns.py`
  exports `_check_no_file_ancestor` (sync) and
  `_acheck_no_file_ancestor` (async). Both walk the slash-aligned
  ancestor chain via a caller-supplied `head_one` callable and
  short-circuit on no-slash paths (the user's optimisation). Each
  flat-namespace backend (`S3Backend`, `S3PyArrowBackend`,
  `AzureBackend`, `SQLBlobBackend`, and the async `AsyncAzureBackend`)
  gained a `reject_write_under_file_ancestor: bool = False`
  constructor kwarg (Decision 2 + 3 (b), asked via AskUserQuestion
  once the measurement was in hand). When the opt-in is set the
  backend constructs a backend-specific `head_one` closure
  (`head_object` on S3, `get_blob_properties` on Azure non-HNS,
  `SELECT 1` on SQLBlob) and threads it through `write` /
  `write_atomic` / `open_atomic` / `move` / `copy`. Azure HNS
  short-circuits the walk because `hdi_isfolder` rejects the operation
  on that path (ID-213 tracks an orthogonal HNS-side error-class
  translation gap that is independent of this opt-in). Spec 003 § BE-008
  / BE-018 / BE-019 and spec
  029 § ASYNC-008 / ASYNC-010 / ASYNC-018 / ASYNC-019 carry the new
  prose; the docstrings on every flat-NS backend list the kwarg.
  (T) Conformance: new per-fixture flag
  `BackendFixture.rejects_write_under_file_ancestor` (defaulting to
  `not flat_namespace` so hierarchical backends inherit native
  enforcement) keys the file-ancestor conformance gate. New strict
  fixtures `s3_moto_strict`, `s3_pyarrow_moto_strict`,
  `sqlblob_strict`, `azurite_strict`, `s3_pyarrow_minio_strict`, plus
  the async `azurite_async_strict` (all review follow-ups), construct
  their backends with the opt-in on and run the gate. Existing
  default-off fixtures
  continue to skip via the new `_skip_unless_rejects_file_ancestor`
  helper (replaces `_skip_flat_namespace` at the file-ancestor test
  sites). 10 new conformance test cases pass on the strict fixtures
  (write / write_atomic / open_atomic / move / copy under file
  ancestor, sync and async); the default fixtures continue to skip.
  Measurement: `sdd/research/research-id-211-flat-ns-file-ancestor-precheck.md`
  records the harness and the per-call cost numbers (S3-moto:
  +19 ms / +133% mean at depth 6; Azurite: +9.6 ms / +132% mean at
  depth 6; SQLBlob-sqlite: sub-ms but linear in depth). The default-off
  choice keeps that tax off hot paths.
  Trace: `sdd/traces/id-211-flat-ns-file-ancestor-precheck.yml`.

- [x] **ID-185 — Depth-boundary conformance gap**
  spec: DEPTH-003, BE-014 · audience: infra.test
  Wave 1 (T) test-backfill for an already-verified clause:
  `sdd/formal/DepthCounting.dfy` proves the four depth-filter properties
  (`ImmediateChildDepthIsZero`, `MaxDepthZeroIsImmediate`,
  `DepthFilterIsInclusive`, `DepthFilterExcludesDeeper`) and
  `sdd/formal/BackendContract.dfy` lines 705-709 pin the postcondition
  `recursive && max_depth >= 0 ==> forall fi :: Depth(path, fi.path) <= max_depth`,
  but the four `test_list_files_recursive_max_depth` variants in
  `tests/backends/conformance/test_listing.py` and the async sibling in
  `tests/backends/conformance/test_async_extended.py` asserted only the
  `.name` set. Names can repeat across depths, so a buggy implementation
  returning a too-deep file whose name coincides with an expected one
  (e.g. `pc/d1/a.txt` masquerading as a depth-0 child of `pc`) would
  slip past the name-set check. The new shared helper
  `tests/backends/conformance/_helpers.py::_depth(prefix, path)` mirrors
  the spec 037 reference formula
  (`len(parent.parts) - len(prefix_parts)`, with `prefix in {"", "."}`
  meaning root); the four variants in both sync and async now assert
  `_depth("pc", f.path) <= max_depth` for every returned file alongside
  the pre-existing name-set check. Bite verified by a direct
  construction during implementation (a wrong-depth file with a
  matching name fails the depth assertion). No Dafny edits, no oracle
  regeneration, no Docker; the variants already carry the `DEPTH-003`
  and `BE-014` (sync) / `ASYNC-014` (async) markers, so this is purely
  an added assertion.
  Trace: `sdd/traces/id-185-depth-boundary-conformance-gap.yml`.

- [x] **ID-187 — Property-based aggregate verification for `GetFolderInfo`**
  spec: BE-017, ID-134 · audience: infra.test
  An (O) item, Wave 0 of the Formal Verification queue. The existing
  `TestGetFolderInfoAggregates` spot-checks `file_count` / `total_size`
  against two hardcoded trees only; deterministic fixtures cannot reach
  the off-by-one paths in the recursive `ChildFiles` / `SumSizes` Dafny
  ghost functions. The new
  `tests/test_pbt_folder_info_aggregates.py::TestGetFolderInfoAggregatesOracle`
  generates random trees with `hypothesis` (nesting depth 0–4, 1–20
  files, 1–10000 byte payloads), seeds the Python `MemoryBackend` and
  the Dafny-compiled `DafnyOracleBackend` from the same `dict[str,
  bytes]` literal, and asserts every directory-prefix aggregate agrees
  — including root (`""`). The Dafny postcondition `file_count ==
  |ChildFiles(fs, path)|` / `total_size == SumSizes(fs, ChildFiles(fs,
  path))` supplies the expected aggregate that the random input forbids
  hardcoding. Disjoint vocabularies for directory names (`d0..d5`) and
  filenames (`f0..f5.bin`) make file-under-file conflicts structurally
  impossible, so the strategy needs no Hypothesis-side filter.
  Helper `build_oracle(tree: dict[str, bytes]) -> DafnyOracleBackend`
  ships in `tests/backends/dafny/_seed.py` and is re-exported from
  `tests/backends/dafny/__init__.py`. The seed is the source of truth;
  the oracle is never re-derived by enumerating a live backend
  (Safe/Unsafe-pair discipline, `sdd/formal/README.md`). Two
  `TestSeededBreakHarness` self-tests prove that divergent seeds yield
  divergent `total_size` and `file_count` respectively, guarding
  against a harness bug that would leave the PBT vacuously green.
  Surprising ripple: the existing `DafnyOracleBackend.get_folder_info`
  built `RemotePath(path)` directly, crashing on root listing (`""`)
  because `RemotePath` validation rejects the empty string; aligned the
  adapter with `MemoryBackend.get_folder_info` by switching to
  `RemotePath.from_backend_path(path)`. The pre-existing conformance
  tests never exercised root on the oracle, which is why the latent
  divergence reached master.
  Trace: `sdd/traces/id-187-folder-info-pbt.yml`.

- [x] **ID-209 — `fs` well-formedness as a `Backend` class invariant + write-under-file conformance gate**
  spec: BE-008, BE-014, BE-015, BE-018, BE-019 · audience: contributor.process, infra.test, library.maintainer, user.api
  Follow-up to ID-184 (PR #679). ID-184's new
  `!AllAncestorsTraversable(fs, path) ==> r.value == []` disjunct on
  `ListFiles` / `ListFolders` was a defensive postcondition over a state
  structurally unreachable from public `Backend` trait methods on a
  well-formed initial fs — every compliant refinement satisfied it
  vacuously. ID-209 makes the unreachability load-bearing on both
  layers.
  (C) Promoted well-formedness to a Dafny class invariant. The
  `Backend` trait now declares `predicate Valid()` reading
  `forall p :: p in fs ==> forall slash-aligned ancestor i :: IsDir(fs,
  p[..i])` — the *strong* form (every ancestor materialised as
  DirEntry) rather than the weak "absent OR DirEntry" form, because
  the weak form fails under a Write that inserts at a previously-absent
  slash-aligned ancestor of an existing key. The strong form rules
  that edge case out of `Valid()` directly and matches every real
  backend (Local's `parent.mkdir(parents=True)`, SFTP's mkdir-walk,
  Memory's `EnsureParents` all materialise the chain). `requires
  Valid() ensures Valid()` is now on every mutating method (`Write`,
  `Delete`, `DeleteFolder`, `Move`, `Copy`). The load-bearing case
  is the new `!AllAncestorsTraversable(old(fs), path) ==> r ==
  Err(InvalidPath(path, name))` clause on `Write` (Decision 1 (b) —
  asked via AskUserQuestion before any code): without it, a successful
  `Write` could insert a `FileEntry` under a file-ancestor, breaking
  `Valid()`. `Move` and `Copy` carry the same clause on their
  destination path. Both `MemoryBackend` and `MemoryBackendMinimal`
  prove maintenance via two factored ghost lemmas
  (`PreserveValidAfterFileInsert`, `PreserveValidAfterFileRemove`)
  that localise the quantifier reasoning — inline proofs timed out
  under Boogie's default budget due to the size of `Write` /
  `Move` / `Copy`'s combined postcondition piles. Spec 003 BE-008,
  BE-014, BE-015, BE-018, BE-019 carry the matching prose; the
  BE-014/015 Formal coverage paragraphs now frame the
  `!AllAncestorsTraversable` disjunct as a *logical consequence* of
  `Valid()` rather than a defensive postcondition.
  (T) Conformance gate: write-under-file raises `InvalidPath`
  (Decision 2 (a) — asked via AskUserQuestion before any code). On
  hierarchical backends Local / SFTP previously leaked native
  exceptions (`FileExistsError`, `NotADirectoryError`, SFTP-ENOTDIR)
  for this case — empirically confirmed by ad-hoc probes during the
  trace's orient phase, a BE-021 violation. Local's `write` /
  `write_atomic` / `open_atomic` / `move` / `copy` now catch
  `NotADirectoryError` / `FileExistsError` and map to `InvalidPath`;
  SFTP's `_map_exception` adds `errno.ENOTDIR → InvalidPath` to its
  OSError dispatch. Memory + AsyncMemory already raised `InvalidPath`
  via `_ensure_parents`. New
  `tests/backends/conformance/test_errors.py::TestWriteErrorFidelity::test_write_under_file_ancestor_raises_invalid_path`
  (sync, `BE-008`) and its async sibling
  `tests/backends/conformance/test_async_extended.py::TestWriteErrorFidelity::test_write_under_file_ancestor_raises_invalid_path`
  (`ASYNC-008` + `BE-008`) pin the cross-backend contract. The
  dafny_oracle fixture certifies the test through the new Dafny clause.
  Flat-namespace backends (S3, Azure non-HNS, SQLBlob, HTTP) skip via
  `_skip_flat_namespace` per the existing per-fixture record; ID-211
  tracks the optional HEAD-pre-check follow-up the user nominated
  during the Decision-(C) consult (most writes target the store root,
  so the overhead only applies to nested-path writes — worth
  measuring before shipping).
  Trace: `sdd/traces/id-209-fs-wellformedness.yml`.

## v0.26.0

- [x] **ID-193 — Async conformance extended: pattern research and implementation**
  spec: ASYNC-018, ASYNC-019 · audience: contributor.process, infra.test
  Closed by rollup: the three phases the original item named — document
  constraints, write a pattern doc or PoC, implement against the settled async
  API surface — landed incrementally across ID-155, BK-182, BK-228, and BK-229
  without citing ID-193, so the parent went stale rather than wrong. The
  realised pattern, tying the predecessor items into one place so the trail is
  not lost:
  - **Hypothesis 6.x stateful-test workaround** (the line the ID-193 description
    called out explicitly). `AsyncBackendModel` in
    `tests/aio/test_async_pbt_stateful.py` drives a `RuleBasedStateMachine`
    against `AsyncMemoryBackend` (native) and
    `SyncBackendAdapter(MemoryBackend())` (adapted) in lock-step against a
    shared `dict[str, bytes] + dirs` model. Rules dispatch through a
    per-instance event loop with `loop.run_until_complete` so `asyncio.Lock`
    state and `asyncio.to_thread` executor identity stay stable across the
    rule sequence — a per-rule `asyncio.run` would not. Landed under ID-155.
  - **Extended conformance suite.**
    `tests/backends/conformance/test_async_extended.py` (951 lines, 81
    `@pytest.mark.spec` markers across 18 ASYNC-* IDs: ASYNC-004 — ASYNC-008,
    ASYNC-010, ASYNC-012 — ASYNC-020, ASYNC-024, ASYNC-029, ASYNC-047) covers
    error-fidelity, listing completeness, move/copy postconditions (the
    ASYNC-018 / ASYNC-019 IDs the original item names — `TestMoveCopyErrorFidelity`,
    `TestMoveCopyOverwrite`, `TestMoveCopySelfOperation`, `TestMovePostState`,
    `TestCopyPostState`, `TestMoveCopyMetadataPreservation`), write-read
    round-trips, streaming-read consumption (ASYNC-020 analogue of SIO-001),
    operational consistency, and `iter_children`. Two structural gaps closed
    in the BK-182 PR: BK-228 added `TestAsyncIterChildren`, BK-229 added
    `TestAsyncWriteAtomic`.
  - **Registry-driven indirect fixture.** The `async_backend` fixture in
    `tests/backends/conformance/conftest.py` parametrises every conformance
    test that requests `async_backend` over the registry rows with
    `is_async=true` (currently `memory_async_native`, `memory_async_adapted`,
    `local_async_adapted`, `azure_live_async`, `azure_replay_async`).
    `pytest-asyncio` in `asyncio_mode = "auto"` (`pyproject.toml`) makes
    `async def` test/fixture functions first-class without decorators.
  Carve-out: the original phase-3 line "oracle integration with async
  backends" is genuinely undone — `DafnyOracleBackend`
  (`tests/backends/dafny/_helpers.py`) is sync-only with no async wrapper or
  `dafny_oracle_async` fixture, so the async suite cross-checks two Python
  implementations of the contract rather than the verified-by-construction
  oracle. Spun off as ID-210 (Formal Verification section) so the close-out
  reflects scope honestly; ID-203 (test folder restructure) and ID-161 / ID-198
  (downstream consumers that named ID-193 as a dependency) updated to drop the
  stale block.
  Trace: `sdd/traces/id-193-async-conformance-pattern.yml`.

- [x] **ID-184 — Listing traversability: prove the contract, then enforce it**
  spec: BE-013, BE-014, BE-015 · audience: contributor.process, infra.test
  A (C)+(T) pair, the first item of the Formal Verification Wave 1.
  (C) `AllAncestorsTraversable` was already used in `Exists`,
  `IsFileMethod`, and `IsFolderMethod`, but `ListFiles` and `ListFolders`
  were silent on it — a malformed-fs state where a file appeared
  mid-path satisfied the listing postconditions even though
  `Exists`/`IsFile`/`IsFolder` would all return false on the same path
  shape. The `BackendContract.dfy` listing postconditions now gate the
  empty-result early-return on
  `!PathExists(fs, path) || !AllAncestorsTraversable(fs, path)
  ==> r.value == []` and the completeness clause symmetrically widens
  its guard from `PathExists` to `PathExists && AllAncestorsTraversable`
  — relaxing the implementer obligation in the same malformed-fs slice,
  which is what keeps the two clauses jointly satisfiable.
  Honest scope: the new state is structurally unreachable through any
  public `Backend` trait method on a well-formed initial fs
  (`EnsureParents` inserts `DirEntry` for every slash-aligned prefix;
  `Write` to a path under a file is not in the reachable state-space),
  so this is a defensive postcondition against fs corruption rather
  than a behavioural gap any compliant refinement could exhibit. The
  two `MemoryBackend` classes call the existing
  `AncestorsTraversableCheck` helper before iterating, and the compiled
  oracle was regenerated. Spec 003 BE-014/BE-015 carry the matching
  prose invariant and a Formal coverage paragraph.
  (T) Two conformance additions: a new
  `TestDeleteFolderErrorFidelity::test_delete_folder_recursive_no_child_survives`
  (sync + async) pins the Dafny `forall p | IsChildOf(p, path) ::
  !PathExists(fs, p)` quantifier via a `list_files(prefix, recursive=True)`
  scan, separate from `test_delete_folder_recursive_removes_all` so its
  unrecorded `azure_replay` cassette self-skips without breaking the
  existing recording (BK-235 picks up the cassette refresh); and a
  paired `test_list_files_non_traversable_ancestor_yields_empty` /
  `test_list_folders_non_traversable_ancestor_yields_empty` (sync +
  async) added during review pins the adapter's exception-translation on
  Local/SFTP: seed `badanc.txt` as a file, then list under
  `badanc.txt/child` — the natural `NotADirectoryError` /
  `SFTPError` must be swallowed and surface as `[]`. Strict scope: the
  listed path is not in `fs`, so the existing `!PathExists` disjunct of
  the Dafny empty-result postcondition fires first; the new
  `!AllAncestorsTraversable` disjunct (unreachable from a well-formed
  initial fs through public trait methods) is verified by the Dafny
  refinement only. All new tests carry the matching `@pytest.mark.spec`
  markers (BE-013, BE-014, BE-015, plus the ASYNC-* mirrors); the
  formal-trace gate stays green without a baseline change.
  Trace: `sdd/traces/id-184-listing-traversability.yml`.

- [x] **ID-182 — Scheduled CI drift guard for unbounded extra-dependency floors**
  spec: — · audience: user.site, infra.ci, contributor.tooling
  Every `[<extra>]` in `pyproject.toml` declares a floor and deliberately no
  ceiling; PR 613 fixed two paramiko silent-upgrade breakages back-to-back
  (BUG-204, BK-198). The new `.github/workflows/drift-guard.yml` runs Mondays
  07:00 UTC, re-resolving each `remote-store[<extra>]` with
  `pip install --upgrade --pre`, diffing against `infra/drift-locks/<extra>.txt`,
  and running smoke targets from `scripts/drift_smoke_map.py` for any drifted
  extra. A single rolling GitHub issue is created / updated / auto-closed by
  `scripts/drift_report.py`. Pre-release resolutions surface in a distinct
  section of the report so RCs do not look like stable drift. Baselines ship
  as stubs; the first scheduled run advises maintainers to populate them via
  `hatch run drift-check refresh-baseline <extra>`. A new user-facing page —
  `docs-src/reference/tested-versions.md`, generated from the locks — records
  the upper-bound versions CI was last green against; `FEATURES.md` links to
  it. Workflow never edits `pyproject.toml` and never opens a pin-update PR.
  Trace: `sdd/traces/id-182-drift-guard.yml`.

- [x] **BK-236 — Docs-site link gate in `check-links` (DOCFRAME-009)**
  spec: DOCFRAME-009 · audience: contributor.tooling, user.site
  `check_links.py` validated relative on-disk links only (DOCFRAME-008);
  absolute `docs.remotestore.dev` links were exempt as external URLs, so
  two README links shipped to PyPI pointing at docs-site paths that never
  existed. `check_docs_site_links` now resolves every
  `https://docs.remotestore.dev/stable|latest/<path>` link against the
  page set derived from `build_source_map` — the same source→docs-URL map
  the mkdocs bridge uses — flagging a stale or mistyped path segment
  offline, with no docs build and no HTTP request. The new gate surfaced
  three more broken links (the data-lake-patterns guide and a research
  doc) and an unregistered example (`dagster_compute_log_manager` missing
  from `examples/_categories.yml`, an ID-208 ripple miss), all fixed in
  the same PR.
  Trace: `sdd/traces/bk-236-docs-site-link-check.yml`.

- [x] **ID-208 — `RemoteStoreComputeLogManager`: Dagster compute log manager (RFC-0014)**
  spec: DAG-021 -- DAG-033 · audience: user.api
  `ext.dagster` now covers Dagster's second storage extension point. The new
  `RemoteStoreComputeLogManager` is a Dagster *instance* component, configured
  in `dagster.yaml`, that captures op/step `stdout` / `stderr` and persists it
  to any remote-store backend — complementing the existing IO manager. It
  subclasses Dagster's `TruncatingCloudStorageComputeLogManager` and builds its
  own `Store` from `backend_type` + `backend_options` via the shared
  `_build_store`. RFC-0014 OQ6 resolved: `_build_store` now `Secret`-wraps
  credential-named options (DAG-033), which also retroactively masks
  credentials for the v2 `DagsterStoreResource` / `RemoteStoreIOManager`. The
  Dagster API paths were verified against the installed `dagster` 1.13.5; the
  RFC's assumed import paths were corrected.
  Trace: `sdd/traces/id-208-dagster-compute-log-manager.yml`.

- [x] **BK-195 — Conformance test: `copy()` preserves user metadata**
  spec: WR-013, BE-019, ASYNC-019 · audience: infra.test
  A (T) gap, paired with BK-196 (the contract side).
  `test_atomic.py::TestWriteResultConformance` covered the
  `write → get_file_info` user-metadata round-trip but nothing exercised
  `write → copy → get_file_info`; that gap let BK-192 (memory `copy()`
  dropping metadata) reach master with no cross-backend gate.
  `TestWriteResultConformance::test_metadata_round_trips_through_move_copy`
  now writes a file with a non-empty metadata mapping, copies it, and
  asserts `get_file_info(dst)` returns the mapping verbatim — parametrized
  over the backend registry, self-skipping backends without
  `USER_METADATA` (consistent with the sibling round-trip test), and gated
  by the compiled Dafny oracle (`dafny_oracle`), which is green because
  BK-196 pinned metadata in the `Copy` postcondition. The `copy`
  parameter is tagged `@pytest.mark.spec` WR-013 + BE-019; the async
  mirror `test_async_extended.py::TestMoveCopyMetadataPreservation`
  additionally carries ASYNC-019. Shipped with BK-233 as one PR — the
  items share `test_atomic.py`, which the wave execution-order note
  allows.
  Trace: `sdd/traces/bk-195-copy-move-metadata-conformance.yml`.

- [x] **BK-233 — Conformance test: `move()` preserves user metadata**
  spec: WR-013, BE-018, ASYNC-018 · audience: infra.test
  A (T) gap, the `move()` sibling of BK-195, paired with BK-232 (the
  contract side). A move is observationally copy-then-delete, so on a
  `USER_METADATA`-declaring backend the metadata mapping must survive it
  (the WR-013 round-trip). The parametrized test BK-195 added,
  `test_metadata_round_trips_through_move_copy`, carries a `move`
  parameter tagged `@pytest.mark.spec` WR-013 + BE-018; the async mirror
  carries ASYNC-018. The Dafny oracle is green because BK-232 pinned
  metadata in the `Move` postcondition. Shipped with BK-195 as one PR;
  the trace is rolled up under BK-195's via `co_shipped_items` rather
  than authored as a near-duplicate.
  Trace: `sdd/traces/bk-195-copy-move-metadata-conformance.yml`.

- [x] **BK-232 — Pin metadata in the Dafny `Move` postcondition**
  spec: WR-013, BE-018, ASYNC-018 · audience: library.maintainer
  A (C) gap, the `Move` sibling of BK-196. `MemoryBackend.dfy::Move`
  built the destination via `BasicFileInfo`, dropping user metadata, and
  the abstract `Move` postcondition pinned only content — so the model
  verified cleanly while encoding a metadata-losing move, the exact
  defect class BK-196 closed for `Copy`. The `Move` success
  postcondition in `BackendContract.dfy` now also pins
  `fs[dst].info.metadata == old(fs)[src].info.metadata`, and both
  `MemoryBackend.Move` and `MemoryBackendMinimal.Move` thread
  `srcEntry.info.metadata` onto the destination `FileInfo`. The metadata
  clause is folded into the existing content `ensures`; `BasicFileInfo`
  stays the rich-field-empty helper — `Move` constructs `FileInfo`
  directly rather than rippling a new parameter through its call sites.
  Spec 003 BE-018 gains the matching `Metadata` invariant and `Formal
  coverage` paragraph, mirroring what BK-196 added to BE-019. Compiled
  oracle regenerated; all four `.dfy` files verify. Surfaced during
  BK-196 review; the `write → move → get_file_info` conformance test is
  the distinct (T) gap BK-233.
  Trace: `sdd/traces/bk-232-move-metadata-postcondition.yml`.

- [x] **ID-190 — Formalize path well-formedness: `WellFormedPath` predicate**
  spec: PATH-002 -- PATH-008, NPR-020, NPR-010, STORE-012 · audience: library.maintainer
  A (C) gap. `BackendContract.dfy` treated paths as opaque non-empty
  strings; the PATH-002 -- PATH-008 normalisation rules (backslash
  conversion, `..` rejection, slash stripping and collapsing, dot-segment
  removal, null-byte and empty-path rejection) lived in Python alone, so
  the oracle could not certify a path-normalisation test. `WellFormedPath`
  is now a `ghost predicate` characterising a normalised path (a fixed
  point of `RemotePath._normalize` for non-root paths, plus the Root
  sentinel `"."` by fiat per PATH-015), declared as a `requires`
  precondition on all 13 contract methods and mirrored across both
  `MemoryBackend` classes. Second part: `NativePathRoundTrip` proves
  NPR-020's `to_key(native_path(k)) == k` identity over pure `NativePath`
  / `ToKey` string models for non-empty keys (and identity-default
  roots); the empty-key round-trip is backend-divergent — `to_key` of the
  bare root differs across backends — and is excluded, tracked as BK-234.
  Ghost-only: the `requires` clauses, the `ghost` predicate and functions,
  and the lemma erase at compile time, so the compiled oracle is
  unchanged; all four `.dfy` files verify (168 verified, 0 errors). The
  NPR-020 cross-backend conformance test is a (T) gap baselined in
  `check_formal_trace.py`.
  Trace: `sdd/traces/id-190-path-wellformedness.yml`.

- [x] **BK-196 — Pin metadata in the Dafny `Copy` postcondition**
  spec: WR-013, BE-019, ASYNC-019 · audience: library.maintainer
  A (C) gap, and the exemplar of benefit 1. `MemoryBackend.dfy::Copy`
  built the destination via `BasicFileInfo`, dropping user metadata, and
  the abstract `Copy` postcondition pinned only content — so the model
  verified cleanly while encoding the exact defect Python carried before
  BK-192. The `Copy` success postcondition in `BackendContract.dfy` now
  also pins `fs[dst].info.metadata == old(fs)[src].info.metadata`, and
  both `MemoryBackend.Copy` and `MemoryBackendMinimal.Copy` thread
  `srcEntry.info.metadata` onto the destination `FileInfo`. The metadata
  clause is folded into the existing content `ensures` so the shared
  `IsFile(fs, dst)` conjunct keeps `fs[dst]` well-defined. `BasicFileInfo`
  stays the rich-field-empty helper — `Copy` constructs `FileInfo`
  directly rather than rippling a new parameter through its call sites
  (a deliberate divergence from the item's advisory prescription).
  Compiled oracle regenerated; all four `.dfy` files verify. Surfaced
  during BK-192; pairs with BK-195 (the conformance-test side).
  Trace: `sdd/traces/bk-196-copy-metadata-postcondition.yml`.

- [x] **ID-206 — Mechanical spec ↔ Dafny ↔ test traceability gate**
  spec: — · audience: platform.tooling, infra.test
  The keystone of the Formal Verification wave: turns "Dafny ties tests
  to specs" from a slogan into a CI gate. `scripts/check_formal_trace.py`
  builds a coverage matrix across three sources — spec IDs with a
  verified Dafny postcondition (`// @spec <ID>` tags in
  `sdd/formal/*.dfy`), spec IDs cited by a conformance
  `@pytest.mark.spec` marker, and spec sections declared in `sdd/specs/`
  — and fails on a Dafny-backed clause with no conformance test, a test
  citing an absent spec ID, or a tag citing an absent spec ID.
  Structured `// @spec` tags were added above every contract
  postcondition in `BackendContract.dfy`, `DepthCounting.dfy`, and
  `ResourceSafety.dfy`; they are comments, so Dafny still verifies with
  0 errors. Landed behind a checked-in `_BASELINE` of the five gaps
  present at landing — it must shrink, never grow, so closing a gap
  forces its entry out in the same PR. Wired into `hatch run lint` and
  the CI lint job; tests under `tests/scripts/`. The printed matrix is
  the worklist for the (T)-backfill items (ID-184 / ID-185 / ID-188 /
  BK-195).
  Trace: `sdd/traces/id-206-traceability-gate.yml`.

- [x] **BK-231 — Fix stale paths in `sdd/formal/README.md`**
  spec: — · audience: library.maintainer
  The "Compiled oracle" section named the oracle adapter
  `tests/backends/dafny_oracle.py`; the adapter is
  `tests/backends/dafny/_helpers.py`. The oracle-test and conformance
  commands assumed a flat `tests/backends/test_conformance*.py` layout
  the suite no longer uses; corrected to `tests/backends/conformance/`.
  Co-shipped with ID-206.

- [x] **BK-230 — Silence persistent CI annotations: nested Node 20 in setup-dafny + uv cache reservation race**
  spec: — · audience: infra.ci
  Two CI annotations stayed visible after BK-206 and BK-219 closed; both
  are noise, not failures, but they masked real signal.
  (1) **Nested Node 20 actions in `verify-formal`.** BK-206 audited every
  direct `uses:` line and concluded all GitHub-org actions were on Node 24,
  but it scoped third-party actions out. The deprecation annotation kept
  firing on every `verify-formal` run because
  `dafny-lang/setup-dafny-action@v1.9.1` is composite and its `action.yml`
  pins `actions/setup-dotnet@v4` and `actions/setup-node@v4` internally,
  both Node 20. Latest upstream (`@main`) still pins the same versions, so
  this is not a "bump our pin" fix. Set
  `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"` at job level on
  `verify-formal` only, mirroring the BK-168 pattern that BK-206's
  follow-on cleanup removed from `mutation.yml` once direct actions were
  Node 24. Comment names the nested dependency so the flag is removable
  once upstream bumps.
  (2) **uv cache reservation race.** `test-primary` and `e2e` both emitted
  `Failed to save: Unable to reserve cache with key setup-uv-2-...-3.13.13-pruned-...`
  whenever they ran in parallel — two Linux jobs at the primary Python
  with caching enabled, racing to save the same content-hash key. (The
  `test` matrix shards do not enter the race today because line 63 of
  `ci.yml` computes `test-matrix = ALL_PYTHONS - [PRIMARY]`, leaving
  3.10/3.11/3.12/3.14 only.) The benign warning hid real failures in the
  annotations panel. Added per-job `cache-suffix` (`ci-test-primary`,
  `ci-e2e`) so the live race keys diverge, plus `ci-test-matrix` on the
  matrix `test` job as a forward-defensive entry — reintroducing 3.13 to
  the matrix would otherwise silently revive the race. Cross-platform job
  left alone — its OS axis already differentiates the key. Also corrected
  the stale "Node.js 20 → 22" wording in the BK-206 title and in the
  v0.25.0 CI/build-hygiene rollup line — the deprecation target was
  always Node.js 24; the title typo dated to the original BK-206 draft in
  commit 30f993deb. Audience: `infra.ci`.
  Trace: [`sdd/traces/BK-230-ci-node24-uv-cache-race.yml`](traces/BK-230-ci-node24-uv-cache-race.yml).

- [x] **ID-204 — Relocate `benchmarks/infra/` to top-level `infra/`, retune MinIO ports, single-source settings**
  spec: — · audience: infra.test, contributor.tooling
  Three coupled changes in one PR. (1) `git mv benchmarks/infra infra` — the
  compose stack is consumed primarily by the test suite (`sftp_docker` and
  `azurite` conformance fixtures, `test-cov-strict` second leg, every
  `tests/e2e/*` module), not by benchmarks; the old path misled
  contributors. (2) MinIO host ports moved from `9000:9000` /
  `9001:9001` to `19100:9000` / `19101:9001`. The container internal port
  stays 9000 (so MinIO's healthcheck and toxiproxy upstream are
  unchanged); only the host-side mapping moved off the VSCode Jupyter
  scan band. (3) Introduced `infra/.env` as the single source of truth
  for local-infra ports, hosts, and credentials. `infra/_settings.py`
  parses the file with stdlib only and exposes typed constants;
  `os.environ` wins over file values so ad-hoc per-test overrides keep
  working. Docker compose auto-loads `infra/.env` from its project dir;
  Python conftests import from `infra._settings`; CI workflows source the
  file and use `$VAR` in `-p` flag construction. `scripts/check_infra_settings.py`
  fails lint on any literal `-p N:M` outside `infra/.env`, dual-wired
  into `hatch run lint` and the lint CI job. Callers migrated:
  `tests/conftest.py`, `tests/e2e/conftest.py`, `benchmarks/conftest.py`,
  `benchmarks/_toxiproxy.py`, `benchmarks/bench_pyarrow_tier1.py`,
  `tests/backends/fixtures/s3_pyarrow_minio.py`, and the
  `_live_env._S3_EMULATOR_FRAGMENTS` guard (additive: `:19100` now
  alongside `:9000`). Three CI workflows updated to source the env
  file: `start-backends/action.yml`, `mutation.yml`, `publish.yml`.
  `benchmarks/_toxiproxy.py` collapsed onto the shared module and
  re-exports from `infra._settings` for back-compat. No CHANGELOG entry
  per `audience: infra.test, contributor.tooling` (schema-derived rule).
  Trace: [`sdd/traces/ID-204-infra-settings.yml`](traces/ID-204-infra-settings.yml).

- [x] **BK-182 — Shrink live HNS suites under `tests/backends/azure/` to HNS-unique cases**
  spec: TEST-003 · audience: infra.test
  After BK-179 (per-backend reorg), BK-180 (live `azure_live` /
  `azure_live_async` conformance fixtures), and BK-181 (Azure cassette /
  replay layer) all landed in v0.25.0, the per-backend live HNS suites at
  `tests/backends/azure/test_live_hns.py` and
  `tests/backends/azure/aio/test_live_hns.py` were duplicating happy-path
  coverage now exercised by the conformance suite against the same real
  ADLS Gen2 account. Trimmed both files to the cases conformance cannot
  express: directory-blob `hdi_isfolder` probes
  (`TestAzureLiveHnsDirectoryGuard`, `...GetFileInfoOnDirectory`,
  `...IsFolderIsFile`, `...FileApiOnDirectory` and async siblings),
  WriteResult etag normalisation cross-check on both SDK paths
  (`TestAzureLiveHnsWriteResult` + async sibling; both skip on the
  BUG-173/BUG-196 transient post-rename-read fallback), DFS AsyncIterator
  protocol (BUG-194 guard,
  `TestAsyncLiveHnsWriteAtomicAsyncIterator`), `write_atomic` streaming
  guard against BUG-202 (`TestAzureLiveHnsWriteAtomicStreaming`),
  `get_folder_info("")` HNS root carve-out (BUG-213, AZ-024), and the
  `_ensure_hns()` exists fallback on a real HNS directory. Sync went
  31 → 13 cases; async went 33 → 12 cases. Also deduped the inline
  `_require_live_env` validators in both files onto the shared
  `tests/backends/fixtures/_live_env.require_azure_live_connection_string`,
  refreshed stale `tests/backends/test_azure_live_hns.py` /
  `tests/aio/test_async_azure_live_hns.py` path references in
  `docs-src/guides/backends/azure-hns-setup.md`,
  `tests/backends/azure/aio/test_config.py`, and
  `tests/backends/azure/aio/test_live.py`. Discovery follow-ups BK-228 and
  BK-229 were ship-completed in the same PR (see entries below). No
  CHANGELOG entry (audience `infra.test`).
  Trace: [`sdd/traces/bk-182-shrink-live-hns.yml`](traces/bk-182-shrink-live-hns.yml).

- [x] **BK-228 — Async conformance gap: `iter_children` has no test in `test_async_extended.py`**
  spec: ASYNC-029, ITER-004, ITER-005 · audience: infra.test
  Surfaced during the BK-182 inventory: the per-backend
  `tests/backends/azure/aio/test_live_hns.py::TestAsyncLiveHnsIterChildren`
  was the only live coverage and was deleted as a duplicate, leaving the
  conformance gap exposed. Added `TestAsyncIterChildren` to
  `tests/backends/conformance/test_async_extended.py` mirroring the sync
  sibling in `test_listing.py::TestBackendIterChildren`: combined
  files-and-folders listing, empty/nonexistent path returns `[]`, and the
  files-only / folders-only parametrisation. Verified against
  `memory_async_native`, `memory_async_adapted`, `local_async_adapted`,
  and `azure_live_async` (real ADLS Gen2). `azure_replay_async` skips
  pending cassette refresh per TEST-009 (refresh is a normal PR diff).
  Closed in PR #658 alongside BK-182 per ship-complete (coverage
  regression window otherwise).

- [x] **BK-229 — Async conformance gap: `write_atomic` happy-path round-trip absent from `test_async_extended.py`**
  spec: ASYNC-010, WR-001a · audience: infra.test
  Surfaced during the BK-182 inventory: the per-backend
  `tests/backends/azure/aio/test_live_hns.py::TestAsyncLiveHnsContentRoundTrip`
  was the only async happy-path live coverage and was deleted as a
  duplicate. Added `TestAsyncWriteAtomic` to `test_async_extended.py`
  mirroring `test_atomic.py::TestBackendWriteAtomic`: creates-file, overwrite,
  and `AlreadyExists` guard. Verified against the same fixture set as
  BK-228; `azure_replay_async` skips pending cassette refresh. Closed in
  PR #658 alongside BK-182.

---

## v0.25.0

- [x] **BK-226 — Coalesce local `from azure.core.exceptions import ...` imports across the Azure backend (sync + async + `_azure_common`)**
  spec: — · audience: internal.style
  `src/remote_store/backends/_azure.py`,
  `src/remote_store/aio/backends/_azure.py`, and
  `src/remote_store/backends/_azure_common.py` repeated local
  `from azure.core.exceptions import ...` blocks inside ~8 methods each
  on the two `_azure.py` files plus the 7-symbol block in
  `classify_azure_error()` — a pattern that predated the consolidation
  work and entrenched further with the BUG-200/BUG-201 paths. Promoted
  to module-level imports in all three files; `azure.core` is a hard
  dependency of `azure-storage-blob` so no extras guard is required (the
  whole module surface already lives behind `try/except ImportError` in
  `backends/__init__.py`, and `_azure_common.py` is only imported by the
  two `_azure.py` files). Net line reduction across `src/`. Flagged by
  PR #650 review and folded in during PR #654 review.
  Trace: [`sdd/traces/bk-226-azure-exceptions-imports.yml`](traces/bk-226-azure-exceptions-imports.yml).

- [x] **BK-227 — `Store.move`/`copy` self-op short-circuit masks backend BUG-201 `InvalidPath` for HNS directories**
  spec: BE-018, BE-019, BE-021 · audience: user.api
  After BUG-203 fixed `AzureBackend.is_file(hns_dir)` to return `False`, the
  Store-layer self-op short-circuit (`if src == dst: if is_file: return; else
  raise NotFound`) fell into the `NotFound` branch for any directory source —
  the backend's BUG-201 `InvalidPath` contract was unreachable via the Store
  wrapper. Backend-agnostic fix: probe `is_file` first (1 RTT for the common
  file no-op case), then `is_folder` to raise `InvalidPath` for a directory
  source, then `NotFound` for a missing source. Applied to all four methods
  (`Store.move`, `Store.copy`, `AsyncStore.move`, `AsyncStore.copy`).
  Specs `STORE-008a`, `ASYNC-047`, and `BE-018`/`BE-019` prose updated to
  state the behavioural contract. Coverage: Store-layer regression tests in
  `tests/test_store.py` + `tests/aio/test_async_store.py`, plus parallel
  conformance cases in `tests/backends/conformance/test_atomic.py` +
  `test_async_extended.py` (gated on `self_op_supported` + `_skip_flat_namespace`)
  so a future backend SDK regression cannot pass at Memory while still
  failing at the wrapper. Shipped as PR #652 across 4 review rounds.
  Trace: [`sdd/traces/bk-227-store-self-op-invalidpath.yml`](traces/bk-227-store-self-op-invalidpath.yml).

- [x] **BK-224 — Refresh Stage 3 cassettes after PR #650; empty `_AZURE_HNS_KNOWN_FAILURE_FN_NAMES`**
  spec: — · audience: infra.test
  PR #650 fixed both BUG-202 (streaming `write_atomic`) and BUG-203 (`is_file`
  on HNS directory). Until the Stage 3 cassettes were re-recorded the fixes
  could not be replay-verified, so the originating xfail roster
  (`_AZURE_HNS_KNOWN_FAILURE_FN_NAMES` in `tests/backends/conformance/conftest.py`)
  still listed both names as known failures; left in place they would have
  flipped to xpass silently. Ran `RS_TEST_LIVE_HNS=1 hatch run record-azure`
  against the real ADLS Gen2 account (254 cassettes refreshed; sync 176
  passed + 2 xpassed, async 71 passed, replay smoke 247 passed + 2 xpassed —
  both BUG-202 and BUG-203 names xpass against the new cassette), then
  emptied the frozenset (kept the mechanism + `test_xfail_guard.py` as
  ready-to-use infrastructure for any future HNS-only conformance gap).
  Most cassette diffs are timestamp/request-ID drift; ~30 grew by ~60 lines
  because PR #650's other fixes (BUG-195/196/197/198/200/201) added HEAD
  probes on delete/read paths that the previous cassettes pre-dated.
  Scope expanded from "remove the BUG-202 entry only" to "remove both"
  after the xpassed signals confirmed BUG-203's fix was also reachable
  through the new cassettes.
  Trace: [`sdd/traces/bk-224-azure-cassette-refresh-xfail-removal.yml`](traces/bk-224-azure-cassette-refresh-xfail-removal.yml).

- [x] **BK-225 — Closed as no-defect: `TestAzureLiveHnsGetFolderInfoRoot` is live-only by design**
  spec: BE-017, ASYNC-017 · audience: infra.test
  The original framing — "cassettes must be recorded so `azure_replay` /
  `azure_replay_async` can replay these tests" — was based on a misread
  of `tests/backends/azure/test_live_hns.py`: that file is gated by
  `pytestmark = [pytest.mark.live, pytest.mark.skipif(RS_TEST_LIVE_HNS != "1")]`
  with no `@pytest.mark.vcr`, and `scripts/record_cassettes.py` only
  records the conformance suite (`_CONFORMANCE = "tests/backends/conformance/"`).
  The `azure_replay` / `azure_replay_async` fixtures are not registered for
  this file, so no cassette was ever going to materialise. Verified
  end-to-end against the real account that both
  `TestAzureLiveHnsGetFolderInfoRoot::test_get_folder_info_root_returns_valid_folder_info`
  (sync) and the async sibling pass with `RS_TEST_LIVE_HNS=1 -m live --stage=3`.
  No code or cassette change needed; closed to clear the dead item.
  Trace: [`sdd/traces/bk-225-live-hns-root-coverage-misframed.yml`](traces/bk-225-live-hns-root-coverage-misframed.yml).

- [x] **BUG-213 — `AzureBackend.get_folder_info("")` and async sibling fail on real ADLS Gen2 (sync + async)**
  spec: BE-017, ASYNC-017 · audience: library.maintainer
  The BUG-199 fix unconditionally called `self._fs.get_directory_client(azure_path)`
  followed by `dc.get_directory_properties()` in the HNS branch. When
  `path=""` (root), `azure_path` becomes `""` and real ADLS Gen2 rejects
  `get_directory_client("")` with `"Please specify a file system name and
  file path"`. Surfaced by `TestAzureLiveHnsGetFolderInfoRoot` (sync) and
  the async sibling against a real account — initially landed as
  mock-tests-only in PR #648, the code defect was confirmed during PR #650
  Stage 3 live verification.
  Fix: skip the per-path probe for the filesystem root in both sync
  (`src/remote_store/backends/_azure.py:851-863`) and async
  (`src/remote_store/aio/backends/_azure.py:921-934`). The root is always
  a folder, no `hdi_isfolder` probe is needed, and `get_paths(path="/")`
  alone is sufficient to enumerate children. Mock-level regression tests
  in both `TestAzureHNSPaths` and `TestAsyncAzureHNSPaths` now assert
  `get_directory_client.assert_not_called()` so any future drift fires.
  Spec: BE-017, ASYNC-017.
  Trace: [`sdd/traces/bug-213-azure-get-folder-info-root-path.yml`](traces/bug-213-azure-get-folder-info-root-path.yml).

- [x] **BUG-202 — `AzureBackend.write_atomic` streaming-input path raises `MissingRequiredQueryParameter` on real HNS**
  spec: BE-010, WR-001a · audience: library.maintainer
  Sync `AzureBackend.write_atomic` with a `BinaryIO` (streaming) input
  succeeded against Azurite but failed against a real HNS account with
  the Azure SDK error `MissingRequiredQueryParameter`. Root cause: the
  `_ByteCountingIO` wrapper around the caller's stream is not seekable,
  so the DataLake SDK could not infer the payload length and called
  `flush_data` with `position=None` — which real HNS rejects (Azurite
  forgives). Bytes-input path was already green.
  Fix: streaming `BinaryIO` input now drives the DataLake DFS append
  protocol directly — `create_file` → per-chunk
  `append_data(offset, length)` → `flush_data(position)` — instead of
  calling `upload_data` with an unseekable wrapper. Memory is bounded to
  `_AZURE_BLOCK_SIZE` per chunk; mirrors the async sibling at
  `aio/backends/_azure.py:562-576` introduced by BUG-194. Bytes input
  still uses `upload_data(content, length=len(content), ...)` (the SDK
  resolves length via `len()` for bytes; no protocol change needed).
  Mock-level regression test `test_write_atomic_hns_streaming_uses_dfs_append_protocol`
  in `tests/backends/azure/test_config.py` reconstructs the body from
  the `append_data` calls and pins both offset monotonicity and the
  final `flush_data(position)` byte count. Spec: BE-010, WR-001a.
  Trace: [`sdd/traces/bug-202-azure-write-atomic-streaming-missing-query-param.yml`](traces/bug-202-azure-write-atomic-streaming-missing-query-param.yml).

- [x] **BUG-203 — `AzureBackend.is_folder()` and `AsyncAzureBackend.is_folder()` return `True` for HNS file paths**
  spec: BE-005, ASYNC-005, BE-021 · audience: library.maintainer
  Both sync and async `is_folder('a.txt')` returned `True` when `a.txt`
  existed as an HNS file blob (no `hdi_isfolder=true` marker), because the
  HNS branch treated a successful `get_directory_properties()` response as
  proof of directoryness — but DataLake's
  `get_directory_client(path).get_directory_properties()` returns HTTP 200
  for any path entity, file or directory. The discriminator is the
  `hdi_isfolder` metadata marker. Sync was surfaced by the BK-180
  conformance run; async carried the same defect but `test_async_extended.py`
  has no `test_is_file` / `test_is_folder` mirror of `TestBackendFileFolder`,
  so the live async run was green not because the bug was absent but because
  no conformance test exercised it. Fix: extend the `hdi_isfolder` probe used
  by `write`/`write_atomic`/`open_atomic` to the `is_folder` HNS branch in
  `src/remote_store/backends/_azure.py` and `src/remote_store/aio/backends/_azure.py`
  (sibling fix landed in the same PR). Mock-level async regression test
  `test_is_folder_returns_false_for_file_path_on_hns` added in
  `tests/backends/azure/aio/test_config.py`.
  Trace: [`sdd/traces/bug-203-azure-is-file-hns-folder.yml`](traces/bug-203-azure-is-file-hns-folder.yml).

- [x] **BUG-195 — `get_file_info` on an HNS directory raises `NotFound` instead of `InvalidPath` (sync + async)**
  spec: BE-016, ASYNC-016, BE-021 · audience: library.maintainer
  BE-016 specifies "`InvalidPath` if the path names a directory (Dafny:
  `GetFileInfo: IsDir → InvalidPath`)" and ASYNC-016 inherits the same contract.
  Both `AzureBackend.get_file_info` and `AsyncAzureBackend.get_file_info` raised
  `NotFound` when the target was an HNS directory blob (marker `hdi_isfolder=true`).
  Same defect shape as BUG-190 (write on HNS directory) and BUG-192 (open_atomic
  on HNS directory): the `hdi_isfolder` probe was missing. Fix: detect
  `hdi_isfolder` in the `get_file_info` HNS branch and raise `InvalidPath`. Live
  tests in `TestAzureLiveHnsGetFileInfoOnDirectory` and the async sibling flipped
  from documenting the deviation to asserting `InvalidPath`.
  Trace: [`sdd/traces/bug-195-azure-get-file-info-on-hns-directory.yml`](traces/bug-195-azure-get-file-info-on-hns-directory.yml).

- [x] **BUG-197 — `read_bytes` and `delete` silently mishandle HNS directory paths (sync + async)** *(data-loss fix)*
  spec: BE-006, BE-007, BE-012, ASYNC-006, ASYNC-007, ASYNC-012, BE-021, ASYNC-024 · audience: library.maintainer
  BE-021 requires file-API operations on a directory path to raise `InvalidPath`.
  `write`/`write_atomic`/`open_atomic` enforce this via the `hdi_isfolder` probe
  (BUG-190/BUG-192); `read_bytes`, `read`, `read_seekable`, and `delete` did not.
  Live behaviour on a real ADLS Gen2 account: `read_bytes(hns_dir)` silently
  returned `b""`; `delete(hns_dir)` silently destroyed the directory marker.
  The `delete` regression was a data-loss defect — calling the file-API
  `delete()` on what the caller believed was a file but was actually a
  directory mutated account state without surfacing an error.
  Fix: extend the existing `hdi_isfolder` probe pattern to `read`, `read_bytes`,
  `read_seekable`, and `delete` on both `AzureBackend` and `AsyncAzureBackend`.
  Probe runs before any SDK mutation — detection raises `InvalidPath` without
  touching the directory marker. Live tests in `TestAzureLiveHnsFileApiOnDirectory`
  and the async sibling flipped from documenting the bad behaviour to asserting
  `InvalidPath`. Five cassettes hand-edited to remove the no-longer-issued
  GET/range calls and add the new HEAD probe; Stage 3 refresh via
  `RS_TEST_LIVE_HNS=1 hatch run record-azure` should re-record them to confirm
  wire fidelity.
  Trace: [`sdd/traces/bug-197-azure-read-delete-hns-directory.yml`](traces/bug-197-azure-read-delete-hns-directory.yml).

- [x] **BUG-201 — `AzureBackend` / `AsyncAzureBackend` `move`/`copy` self-op (src == dst) raises `AlreadyExists` instead of being a no-op (sync + async)**
  spec: BE-018, BE-019, BE-021, ASYNC-018, ASYNC-019 · audience: library.maintainer
  Conformance contract for `move(p, p)` and `copy(p, p)` is to be a no-op
  (data preserved, no error). Both `AzureBackend` and `AsyncAzureBackend`
  raised `AlreadyExists` instead. The original report scoped this as
  async-only because `_AZURE_HNS_KNOWN_FAILURE_FN_NAMES` gating hid the
  sync failure; PR #649 round-1 review confirmed the sync `move`/`copy`
  paths had no `src == dst` short-circuit either, so the fix landed on
  both sides.
  Fix: detect `src == dst` at the top of `move`/`copy` and short-circuit
  for files; for HNS directory paths the short-circuit still raises
  `InvalidPath` (BE-021) — mirrors the non-self-op directory check.
  `self_op_supported` flag in `tests/backends/fixtures/fixtures.toml`
  flipped to `true` for all four Azure fixtures (`azure_live`,
  `azure_live_async`, `azure_replay`, `azure_replay_async`); the family
  default in `backends.toml` stays `false` for any future Azure variant
  that has not been verified. Cassettes for the four
  `TestMoveCopySelfOperation.*[azure_async-*]` and matching `[azure]`
  tests were refreshed in the Stage 3 run (commit `bfb378c02`); a
  follow-up Stage 3 run will record the newly-enabled sync `[azure]`
  variants and the directory-guard cases.
  Trace: [`sdd/traces/bug-201-async-move-copy-self-op.yml`](traces/bug-201-async-move-copy-self-op.yml).

- [x] **BUG-200 — `AsyncAzureBackend.move`/`copy` directory checks raise wrong error / `InvalidInput` on real HNS**
  spec: BE-018, BE-019, BE-021, ASYNC-018, ASYNC-019, ASYNC-024 · audience: library.maintainer
  Conformance contract: `move`/`copy` with a directory source or directory
  destination raises `InvalidPath`. `AsyncAzureBackend` instead raised
  `RemoteStoreError(InvalidInput)` (source-is-directory) or `AlreadyExists`
  (destination-is-directory). Same defect family as BUG-195/BUG-197/BUG-190:
  missing `hdi_isfolder` probe before the SDK rename/copy call. Fix: after
  `get_blob_properties()` returns on src/dst, inspect metadata for
  `hdi_isfolder`; raise `InvalidPath` if present. Applied symmetrically to
  both sync and async paths; sync siblings exercised post BK-186 exhibit
  the same defect and receive the same fix.
  Trace: [`sdd/traces/bug-200-async-move-copy-directory-check.yml`](traces/bug-200-async-move-copy-directory-check.yml).

- [x] **BUG-198 — Folder-API on a file path raises wrong error type on `AsyncAzureBackend` (HNS)**
  spec: BE-014, BE-017, BE-021, ASYNC-013, ASYNC-017 · audience: library.maintainer
  Symmetric to BUG-197/BUG-195: `delete_folder` and `get_folder_info` on a
  *file* path should raise `InvalidPath`, but `AsyncAzureBackend` raised
  `DirectoryNotEmpty` (delete_folder) and `NotFound` (get_folder_info).
  Sync siblings were exercised post BK-186 `_skip_flat_namespace` lift and
  exhibited the same defect family. Fix: probe `get_directory_properties`
  metadata for absence of `hdi_isfolder=true` before invoking the folder-API
  SDK call; raise `InvalidPath` when the target is a file. Applied
  symmetrically to `delete_folder` and `get_folder_info` on both
  `AzureBackend` and `AsyncAzureBackend`.
  Trace: [`sdd/traces/bug-198-async-folder-api-on-file.yml`](traces/bug-198-async-folder-api-on-file.yml).

- [x] **BUG-196 — Async `write_atomic` HNS path lacks BUG-173 try/except fallback around `get_file_properties()`**
  spec: WR-001a, WR-004, AZ-034 · audience: library.maintainer
  `AsyncAzureBackend.write_atomic` HNS path called `get_file_properties()`
  *after* the rename committed but did not wrap it in try/except. The sync
  sibling (BUG-173) deliberately catches the exception, logs a warning, and
  returns `WriteResult(etag=None, last_modified=None)` — the rename has
  already committed, so a transient post-rename read failure must not
  surface as a write failure (WR-001a lists both fields as `Optional`).
  Fix: mirror the sync try/except + log + fallback shape on the async path;
  weaken the `TestAsyncLiveHnsWriteResult` assertion to allow `etag=None`.
  Trace: [`sdd/traces/bug-196-async-write-atomic-fallback.yml`](traces/bug-196-async-write-atomic-fallback.yml).

- [x] **BUG-212 — `scripts/record_cassettes.py` deletes cassettes before validating env**
  spec: — · audience: contributor.tooling
  Step 1 unlinks every cassette under `tests/backends/cassettes/<backend>/`
  before pytest validates the live opt-in flag (Step 2/3) and before
  `account_fn` validates the connection string (Step 4). A missing
  `RS_TEST_LIVE_HNS=1` or an empty / Azurite `AZURE_STORAGE_CONNECTION_STRING`
  therefore wipes the tree and only then fails. Recovery relied on the
  cassettes being checked into git. Surfaced during the BUG-199 recording
  attempt — first invocation hit the Windows cp1252 Unicode crash (fixed
  inline), second invocation surfaced this ordering bug and wiped 253
  cassettes; recovered via `git restore`.
  Fix: new `_preflight_env(cfg)` helper at the top of `main()` that
  loads `.env`, asserts the per-backend `live_opt_in_env` flag is `"1"`,
  and runs `cfg["account_fn"]()` to validate the cred string — all
  before any destructive step. Backend config gains a `live_opt_in_env`
  field (`"RS_TEST_LIVE_HNS"` for Azure). Two regression tests in
  `tests/scripts/test_record_cassettes.py::TestPreflightEnvGuard`:
  one pins `SystemExit` and cassette-tree intactness when the opt-in
  is missing; the other pins source order (`_preflight_env` before
  the Step 1 marker in `main()`) so a future edit cannot silently
  re-introduce the regression.
  Trace: [`sdd/traces/bug-212-record-cassettes-preflight.yml`](traces/bug-212-record-cassettes-preflight.yml).

- [x] **BUG-199 — `AzureBackend.get_folder_info` recursive `file_count` includes HNS directory blobs as files (sync + async)**
  spec: BE-017, ASYNC-017 · audience: user.api
  `FolderInfo.file_count` returned by `get_folder_info(path, recursive=True)`
  reported one extra "file" per HNS directory marker blob
  (`hdi_isfolder=true`). Surfaced by three live conformance tests
  (`test_get_folder_info_excludes_subdirs[azure_live]`,
  `test_get_folder_info_counts_recursive_children[azure_live]`, and
  `[azure_live_async]`).
  Fix: HNS branch of `get_folder_info` now walks `_fs.get_paths(recursive=True)`
  and filters `getattr(p, "is_directory", False)`, mirroring the pattern
  `list_files` already uses for HNS. Non-HNS branch unchanged (no marker
  blobs in flat namespace). Symmetric change in
  `aio/backends/_azure.py`. Three xfail entries removed from
  `_AZURE_HNS_KNOWN_FAILURE_FN_NAMES`; all three tests now pass cleanly
  against refreshed `azure_replay` / `azure_replay_async` cassettes (212
  passed, 25 xfailed for other HNS bugs, 0 failed). Workflow doc added
  in the same PR (`sdd/TESTING.md` § "Cassette-First Bug Investigation")
  codifies the replay-first → classify → fix → live-verify pattern;
  unrelated Unicode crash in `scripts/record_cassettes.py:115` and
  missing-prefix in `sdd/TESTING.md` § "Cassette Refresh" co-shipped.
  Trace: [`sdd/traces/bug-199-azure-folder-info-hns-dir-count.yml`](traces/bug-199-azure-folder-info-hns-dir-count.yml).

- [x] **BK-204 — SFTP-007 host-key resolution chain: config / env / STRICT-file tiers uncovered**
  spec: SFTP-007 · audience: infra.test
  `_resolve_host_keys` documents a four-tier precedence
  (direct > `config["known_host_keys"]` > `SFTP_KNOWN_HOST_KEYS` env >
  on-disk `host_keys_path`), but the lower three tiers carried
  `# pragma: no cover` markers (`_sftp.py:1270`, `:1300`, `:1302`)
  and no test ever reached them — the documented precedence had no
  regression guard either.
  Coverage: five tests added to `TestSFTPInlineHostKeysVerification`
  (`tests/backends/sftp/test_config.py`) — one positive STRICT-connect
  per tier (config-dict, env-var, file-fallback) plus a precedence test
  pinning `direct > config > env` (wrong keys in config + env, correct
  key direct → connect must still succeed) plus a negative file-fallback
  test (missing `host_keys_path` → `BackendUnavailable`). All three
  `# pragma: no cover` markers removed. Surfaced during BK-201 round-2
  review (user question: "where is the deleted test's logic covered
  now?"); STRICT file-fallback ripple surfaced during BUG-209 PR
  self-review.
  Trace: [`sdd/traces/bk-204-sftp-host-key-chain-coverage.yml`](traces/bk-204-sftp-host-key-chain-coverage.yml).

- [x] **BUG-211 — `SFTPBackend` existence probes swallow connect-time OSErrors as "not found"**
  spec: SFTP-007 · audience: user.api
  `exists()`, `is_file()`, and `is_folder()` wrapped their stat call in a
  catch-all `try: ... except OSError: return False`. The `self._sftp`
  property triggers `_connect()` → `_create_ssh_client()` on first use,
  so any `OSError` from that path was silently reported as "file does
  not exist". That swallow is what turned the BUG-209 Windows
  `PermissionError` into the apparent flakiness of
  `test_strict_rejects_mismatched_inline_key`.
  Fix: narrow each catch to `errno.ENOENT`; let every other `OSError`
  fall through to `_errors()` → `_map_exception` so `EACCES` surfaces as
  `PermissionDenied` and unknown codes surface as the generic
  `RemoteStoreError` carrying the original message. Co-shipped with
  BUG-209 because the swallow is what hid the BUG-209 failure mode.
  Regression: `TestSFTPExistsErrorFidelity::test_connect_time_oserror_propagates`
  parametrised over the three probes. Trace shares
  [`sdd/traces/bug-209-sftp-host-key-tempfile-lock.yml`](traces/bug-209-sftp-host-key-tempfile-lock.yml)
  (co_shipped_items).

- [x] **BUG-209 — SFTP STRICT verification silently bypassed on Windows by inline-key tempfile lock**
  spec: SFTP-007 · audience: user.api
  `_load_host_keys_from_string` wrote inline `known_host_keys` to
  `tempfile.NamedTemporaryFile(delete=True)`. On Windows that opens the
  file with `O_TEMPORARY`, which prevents paramiko's `load_host_keys`
  from re-opening the path — it raises `PermissionError`. The
  `OSError`-subclass error bubbled out of `_create_ssh_client` →
  `_connect()` → the `self._sftp` property, then got caught by the
  `except OSError: return False` in `exists()`. Net effect on Windows:
  inline known-host keys were never loaded, STRICT verification was
  silently skipped, and `test_strict_rejects_mismatched_inline_key`
  failed with "DID NOT RAISE". Cross-platform CI rotation made the
  failure look intermittent.
  Fix: switch the helper to `delete=False` with manual `os.unlink` in
  `finally`. Helper now exercises end-to-end on every OS, so the
  `# pragma: no cover` is dropped. Added a fixture-free regression
  `test_load_host_keys_from_string_reopenable` so future Windows-only
  failures fail in a unit test rather than only via the in-process
  SFTP server fixture.
  Trace: [`sdd/traces/bug-209-sftp-host-key-tempfile-lock.yml`](traces/bug-209-sftp-host-key-tempfile-lock.yml).

- [x] **ID-192 — aio.md rework: promote AsyncStore, fix empty member blocks**
  `docs-src/reference/api/aio.md` previously gave `AsyncBackend` the full
  per-category method-section treatment while `AsyncStore` carried only an
  `Interop (Backend-Specific)` subsection — the opposite of the
  Store-centric layout in `store.md`. Four classes
  (`SyncBackendAdapter`, `AsyncBackendSyncAdapter`, `AsyncMemoryBackend`,
  `AsyncAzureBackend`) used `members: false` with no follow-up directives,
  rendering as bare class-docstring stubs that suppressed the layer-4
  `Raises:` docstrings BK-173 had just added.
  Restructure: `## AsyncStore` now mirrors `store.md` with explicit
  `### Reading / Writing / Deleting / Listing and Iteration / File Operations /
  Metadata / Introspection / Lifecycle / Interop` subsections, each method
  carrying its own `:::` directive at `heading_level: 4` plus the matching
  `!!! note "Requires ..."` / `!!! info "Quality flag ..."` admonitions from
  the sync canonical. The `## AsyncBackend` section is unchanged. The four
  `members: false` directives are replaced with short framing-prose +
  `show_bases: false`, matching the precedent set by `backends/memory.md` and
  `backends/azure.md`. All `#asyncstore` / `#asyncbackend` / `#syncbackendadapter`
  / `#asyncbackendsyncadapter` / `#asyncmemorybackend` / `#asyncwritablecontent`
  anchors (cited from `reference/api/index.md`) are preserved.
  Unblocks ID-172 (`check_api_docs.py` async PAGES wiring) and ID-194
  (`gen_graph.py` async gate extension); the page surface is now stable
  enough for the verifier to lock onto.
  Audience: `user.api_docs`, `user.site`.
  Trace: [`sdd/traces/id-192-aio-md-rework.yml`](traces/id-192-aio-md-rework.yml).

- [x] **BK-223 — Tighten `match=` regex in `test_source_is_directory_raises_error` (sync + async)**
  spec: BE-018, BE-019, ASYNC-018, ASYNC-019 · audience: infra.test
  Symmetric fix to BK-177's `test_destination_is_directory_raises_error` tightening.
  Changed `match=f"mcds/{op}"` to `match=f"mcds/{op}(?!_dst)"` in both:
  - `tests/backends/conformance/test_errors.py::TestMoveCopyErrorFidelity::test_source_is_directory_raises_error`
  - `tests/backends/conformance/test_async_extended.py::TestMoveCopyErrorFidelity::test_source_is_directory_raises_error`
  The negative lookahead prevents the dst path `mcds/{op}_dst.txt` from satisfying
  the match, so a regression that flipped the error to be about dst would now be caught.
  No spec change; no CHANGELOG entry (infra.test only).

- [x] **BK-177 — Parametrize self-op tests + tighten `match=` regexes**
  spec: BE-018, BE-019 · audience: infra.test
  Two TESTING.md alignments on the sync side, mirroring PR #580 (async).
  1. `tests/backends/conformance/test_atomic.py::TestMoveCopySelfOperation`:
     collapsed five near-duplicate methods into two parametrized methods
     (`test_self_op_preserves_data` over `(op, cap)` × `overwrite` and
     `test_self_op_missing_raises_not_found` over `(op, cap)`), adding the
     previously-missing self-move-missing-NotFound case.
  2. `tests/backends/conformance/test_errors.py::TestMoveCopyErrorFidelity::test_destination_is_directory_raises_error`:
     tightened `match=f"mcdd/{op}"` to `match=f"mcdd/{op}_dstdir"` (the test
     was relocated here by BK-179's split, not in `test_atomic.py` as the
     original item stated). No spec change; no CHANGELOG entry (infra.test only).

- [x] **BUG-210 — `azure_replay` fixture omits `cleanup=`; ~133 `Unclosed AzureBackend` warnings per Stage-2 run**
  `tests/backends/fixtures/azure_replay.py` registered its `BackendFixture`
  without a `cleanup=` argument, so the conformance `backend` fixture had
  nothing to call at teardown. Every replay-fixture backend's `close()` was
  skipped, the lazy `_blob_service_instance` / `_cc_instance` clients stayed
  attached, and each instance's `__del__` later fired
  `ResourceWarning("Unclosed AzureBackend...")` at GC time. With
  `filterwarnings = error` in `pyproject.toml`, those warnings became
  exceptions in `__del__`, routed through `sys.unraisablehook` to
  pytest's hook, and were re-emitted as `PytestUnraisableExceptionWarning`
  attributed to whichever test was running when GC fired. On Linux CI
  (`-n auto = 4` workers) the GC timing rarely collided with a
  `pytest.warns(ResourceWarning, ...)` context; on a 20-worker Windows
  developer host the collision was intermittent (~1 in 5 sessions),
  surfacing as e.g. `TestSFTPLifecycle::test_del_closes_partial_clients`
  failing with an "Unclosed AzureBackend" message — a test that has no
  Azure code path. The sibling `azure_replay_async.py` already registered
  `aclose=_aclose`; only the sync slice was missed.
  Fix: one-line `cleanup=_cleanup` addition wrapping `backend.close()`.
  Verified on Windows: ResourceWarning count dropped from 133 → 0 per
  Stage-2 run; five consecutive `-n auto` runs of the full Stage-2 suite
  passed cleanly (previously 1/5 failed).
  **Structural guard**: new
  `tests/backends/fixtures/test_registry.py::TestFixtureCleanupContract`
  asserts that any sync fixture whose backend class overrides
  `Backend.close` declares `cleanup=`. Scope is deliberately narrow:
  sync only (`asyncio.run(f.aclose(...))` for an async fixture would
  leak the Linux `UnixSelectorEventLoop`'s self-pipe sockets and
  attribute the warning to a downstream test), and only fixtures
  whose `factory()` does not open a real network transport
  (`transport in {"fs", "memory", "sql"}` or `kind == "replay"`).
  Real-network and async fixtures are still covered indirectly: a
  missing `cleanup=` / `aclose=` there surfaces through the conformance
  suite as the same `ResourceWarning` leak that originally surfaced
  BUG-210. Stage-2 run with the fix reverted reproduces the assertion
  failure pointing at `azure_replay`.
  **Investigation note**: the residual `-n auto` Windows flake had been
  predicted to have host-resource roots (werkzeug `MemoryError`, Windows
  ephemeral-port exhaustion, Docker Desktop NAT); the actual cause was
  a single missing `cleanup=` kwarg made visible only because
  `filterwarnings=error` + 20 workers compresses the GC-timing window
  enough to hit a foreign `pytest.warns` block.
  Audience: `infra.test`.
  Trace: [`sdd/traces/BUG-210-azure-replay-fixture-leak.yml`](traces/BUG-210-azure-replay-fixture-leak.yml).

- [x] **BK-222 — Migrate `tests/test_coverage_gaps.py` (per-backend split) (BK-191 slice 6/6)**
  Sixth and final migration-pending slice from BK-191's audit.
  `tests/test_coverage_gaps.py` fired Rule B via function-local imports of `_s3`
  (lines 378, 384), `_s3_pyarrow` (390, 396), `_sftp` (402, 408), `_azure`
  (414, 427), plus `__import__` lambda forms (491–512) that were specifically
  crafted to evade the AST checker. Reframes audit-014's proposed "(b) conformance
  reshape (secret-masking)": the masking tests check backend-specific repr formats
  (`key='***'`) and internal attribute names (`_key`, `_secret`, `_password`,
  `_account_key`, etc.), making them per-backend implementation details rather than
  generic conformance invariants. The universal "no credential leakage" invariant
  is already covered by `TestBackendIdentity::test_repr_masks_secrets` in
  `tests/backends/conformance/test_identity.py`. The conformance approach would
  require naming concrete backend classes inside conformance files (violates the
  naming rule) or adding `secret_masking_spec` registry infrastructure (disproportionate).
  Disposition: **(a) per-backend split for all masking tests.**
  `TestS3CredentialMasking` (AF-008, SEC-004) added to `tests/backends/s3/test_config.py`;
  `TestS3PyArrowCredentialMasking` added to `tests/backends/s3/test_pyarrow.py`;
  `TestSFTPCredentialMasking` added to `tests/backends/sftp/test_config.py`;
  `TestAzureCredentialMasking` added to `tests/backends/azure/test_config.py`.
  Root `tests/test_coverage_gaps.py` retains all tests using only allowed backends
  (`LocalBackend`, `MemoryBackend`). `"test_coverage_gaps.py"` removed from
  `_BACKEND_AT_ROOT_GRANDFATHERED` in `scripts/check_test_placement.py`; the
  allow-list now contains only the permanently-justified `test_examples.py`.
  `test_grandfathered_files_skipped` in `tests/scripts/test_check_test_placement.py`
  updated to use `test_examples.py`. Audit-014 per-file section and summary
  table updated with rule-3 reframe note.
  Audience: `infra.test`, `contributor.process`. Spec: TEST-003, AF-008, SEC-004.
  Trace: [`sdd/traces/BK-222-test-coverage-gaps-per-backend-split.yml`](traces/BK-222-test-coverage-gaps-per-backend-split.yml).

- [x] **BK-191 — Audit `_BACKEND_AT_ROOT_GRANDFATHERED` allow-list (all six slices complete)**
  All six migration-pending slices from the 2026-05-13 audit landed across BK-216
  through BK-222. The `_BACKEND_AT_ROOT_GRANDFATHERED` set now contains only the
  permanently-justified `test_examples.py` (disposition (c), ID-044 example/test
  1:1 invariant). Closed by BK-222 (slice 6/6).
  Audience: `infra.test`. Spec: TEST-003, TEST-010.

- [x] **BK-181 — Implement Spec 048 Phase 3: HTTP cassette/replay layer**
  Shipped the Azure slice across two PRs and closed with S3 deferred as a
  documented exception. **PR 1a (#629):** `azure_replay` /
  `azure_replay_async` fixture wiring, `pytest-recording` dev dependency,
  `--record` flag, conformance conftest vcr hooks, scrubbing layer
  (`_cassettes.py`), cassette directory. **PR 1b (#630):** 253 Azure
  cassettes recorded from real ADLS Gen2; scrubbing additions
  (binary-safe body scrub, `_TMP_UUID_PATTERN` for `write_atomic`
  temp-file UUIDs, `x-ms-copy-source` request + response header scrub);
  `AsyncioRequestsTransport` gated on `_RS_CASSETTE_RECORDING` sentinel;
  `TESTING.md` cassette-refresh guide; 209 replay tests pass (28 HNS-bug
  failures faithfully reproduced). **S3 slice deferred:** the spike
  surfaced an upstream incompatibility between vcrpy's `aiohttp_stubs.py`
  and the `aiobotocore` request/response wrappers `s3fs` rides on, with
  no transport-injection workaround equivalent to Azure's
  `AsyncioRequestsTransport` shim. `s3_moto` already covers the Stage-1
  conformance surface for S3, so the user-facing impact is limited. Spec
  [TEST-008](specs/048-testing-architecture.md) amended to list S3 as a
  noted exception. Diagnosis in
  [`research-bk-181-s3-cassette-infeasibility.md`](research/research-bk-181-s3-cassette-infeasibility.md);
  spike preserved as evidence under
  [`sdd/research/bk-181-s3-spike/`](research/bk-181-s3-spike/).
  Audience: `infra.test`, `contributor.tooling`, `contributor.process`.
  Trace: [`sdd/traces/BK-181-cassette-replay-impl.yml`](traces/BK-181-cassette-replay-impl.yml).

- [x] **BUG-208 — `S3Backend.check_health()` silently no-ops (unawaited aiobotocore coroutine)**
  `check_health()` called `self._fs.s3.head_bucket(Bucket=...)` on the raw
  `aiobotocore` client, whose `head_bucket` returns a coroutine. The code
  never awaited it: the HEAD never reached the server, `check_health()`
  silently returned `None` regardless of bucket state, and the orphaned
  coroutine surfaced at GC as `RuntimeWarning: coroutine ... was never
  awaited` (escalated to an error by `filterwarnings = ["error"]`). Fixed
  by routing the probe through s3fs's synchronous `call_s3` wrapper —
  `self._fs.call_s3("head_bucket", Bucket=self._bucket)` — the same path
  `head_object` already uses; a missing bucket or invalid credentials now
  map through `_s3fs_errors` to `NotFound` / `PermissionDenied` /
  `BackendUnavailable` per PING-004 / PING-009. The mocked `test_ping.py`
  cases never exercised the `aiobotocore` path (they patched the s3fs
  client), so a real moto-backed regression class
  (`TestS3CheckHealthMoto`) was added and the `s3_moto` xfail removed from
  the conformance test. Spec PING-004 updated — its code block had
  codified the buggy raw-client call. Audit of every other
  `self._fs.s3.<method>` use in the S3 backend: none — `check_health` was
  the only direct raw-client call; all other operations already use
  `call_s3`. Audience: `user.api`.
  Trace: [`sdd/traces/BUG-208-s3-check-health-unawaited-coroutine.yml`](traces/BUG-208-s3-check-health-unawaited-coroutine.yml).

- [x] **ID-195 — Speed up `hatch run all` — pytest-xdist, preflight, SFTP-Docker carve-out**
  Add `pytest-xdist>=3.5` to dev extras; every `test*` script in `pyproject.toml`
  runs `pytest -n auto -p no:benchmark` (xdist on, benchmark plugin off so
  `filterwarnings=error` does not promote `PytestBenchmarkWarning` to
  INTERNALERROR; bench-* scripts re-enable it explicitly).
  `[tool.coverage.run] parallel = true` lets pytest-cov combine xdist worker
  partials into one `.coverage` data file. `hatch run all` wall time on a
  20-core dev machine, both runs stopping at the same pre-existing Windows
  flake in the test step: ~229 s → ~26 s. The bulk of the gain comes from
  `test-cov-s1` (Stage-1, xdist) replacing serial `test-cov-strict`; the
  preflight reorder contributes the rest.
  New `preflight` script ahead of `lint` in `hatch run all` runs the four
  artifact-drift `gen-*-check` calls (`gen_graph`, `gen_features`,
  `gen_graph_viz`, `check_api_docs`); drift surfaces in seconds rather than
  after the full lint/typecheck/test gauntlet. CI lint job runs the same
  checks inline so the win is dev-loop only.
  New `test-cov-s1` (`--stage=1`, no Docker probe, no floor) replaces
  `test-cov-strict` in `hatch run all` so the pre-commit gate never requires
  Docker services. `test-cov-strict` stays for CI and the publish workflow.
  CI `test` and `test-primary` jobs updated to the two-pass pattern.
  **SFTP-Docker carve-out**: `tests/backends/fixtures/registry.fixture_params`
  drops the `sftp_docker` fixture from parametrize whenever
  `PYTEST_XDIST_WORKER` is set. A second serial pytest invocation
  (`pytest -p no:benchmark -k sftp_docker tests/backends/conformance/`)
  picks them up. This replaces the prior approach (xdist_group + MaxStartups
  tuning + banner pre-checks + Transport.connect retry loops) — atmoz/sftp's
  OpenSSH daemon is unreliable under concurrent connections from multiple
  workers, and a serial pass is simpler than papering over instability with
  retries.
  Audience: `contributor.tooling`, `infra.ci`.
  Trace: [`sdd/traces/id-195-speed-up-hatch.yml`](traces/id-195-speed-up-hatch.yml).

- [x] **BK-219 — Centralise Python version config in CI; split primary-Python jobs**
  `ci.yml` carried ~12 hardcoded `"3.13"` literals and a fragile per-version
  coverage ternary (`matrix.python-version == '3.13' && '--cov...' || ''`).
  Shipped: (1) renamed `changes` job to `setup`; added a "Resolve Python
  versions" step whose `env:` block is the sole version source (`ALL_PYTHONS`,
  `PRIMARY_PYTHON`, `MIN_PYTHON`) and emits `primary`, `test-matrix` (all
  versions minus primary), and `typecheck-matrix` (min + primary) as job
  outputs via `jq`; (2) all 9 scalar jobs consume
  `${{ needs.setup.outputs.primary }}` — no more hardcoded `"3.13"`; (3) `test`
  matrix is `fromJSON(needs.setup.outputs.test-matrix)` with plain
  `pytest --ignore=tests/scripts` (no `--cov`); (4) `typecheck` matrix is
  `fromJSON(needs.setup.outputs.typecheck-matrix)`; (5) new `test-primary`
  job runs on primary Python only with `--cov-fail-under=95
  --ignore=tests/scripts` — coverage enforcement is now unconditional and
  version-independent; (6) new composite action
  `.github/actions/start-backends/action.yml` (boolean inputs `minio`,
  `azurite`, `sftp`) replaces duplicated service-startup boilerplate across
  `test`, `test-primary`, `e2e`, and `pyarrow24-check`; `CODE_PAT` extended
  with `^\.github/actions/`; `gate` updated. Bumping primary Python is now
  one line in `setup`. CI-only — no CHANGELOG entry.
  Audience: `infra.ci`.
  Trace: [`sdd/traces/BK-219-ci-python-version-config.yml`](traces/BK-219-ci-python-version-config.yml).

- [x] **BK-221 — Migrate `tests/test_pbt_write_result.py` (per-backend split) (BK-191 slice 5/6)**
  Fifth migration-pending slice from BK-191's audit. `tests/test_pbt_write_result.py`
  fired Rule B via two function-local concrete-cloud imports — `_s3` (inside the
  `s3_backend` fixture, line 267) and `_azure` (inside the `azure_backend` fixture,
  line 299); everything else in the file uses the allowed `MemoryBackend` and
  `LocalBackend`. Reframes audit-014's proposed "(b) conformance reshape (size
  regimes)": the PBT 1 tests are deliberately narrow (module docstring cites
  TESTING.md Rules 5 and 6); the BUG-168 boundary is `LocalBackend`-specific
  (real `BufferedWriter` path); running arbitrary-payload Hypothesis examples
  against the full conformance fixture registry (including SFTP and Azure network
  backends) would be slow and contrary to the documented rationale. Disposition:
  **(a) per-backend split only.** `TestMetadataRoundTripS3` (WR-012/WR-013)
  moved to `tests/backends/s3/test_write_result_pbt.py`; `TestMetadataRoundTripAzure`
  moved to `tests/backends/azure/test_write_result_pbt.py`. Root
  `tests/test_pbt_write_result.py` retains `TestWriteResultSizeSmall` and
  `TestWriteResultSizeBug168Regime` (WR-001a/WR-003) using only the allowed
  `MemoryBackend` and `LocalBackend`. `"test_pbt_write_result.py"` removed from
  `_BACKEND_AT_ROOT_GRANDFATHERED` in `scripts/check_test_placement.py`. One
  migration-pending entry remains (`test_coverage_gaps`) plus the
  permanently-justified `test_examples.py`. Audit-014 per-file section and summary
  table updated with rule-3 reframe note.
  Audience: `infra.test`, `contributor.process`. Spec: TEST-003, WR-012, WR-013.
  Trace: [`sdd/traces/BK-221-test-pbt-write-result-s3-azure-per-backend.yml`](traces/BK-221-test-pbt-write-result-s3-azure-per-backend.yml).

- [x] **BK-220 — Reshape `tests/test_seekable.py` (conformance reshape + Azure per-backend lift) (BK-191 slice 4/6)**
  Fourth migration-pending slice from BK-191's audit. `tests/test_seekable.py`
  fired Rule B via function-local imports of `_azure` (in
  `test_azure_does_not_declare` and the six `TestAzureRangeReader` methods) and
  `_http` (in `test_http_does_not_declare`); the string-form `pytest.param`
  parametrize table at lines 64–68 was AST-invisible to Rule B but logically
  part of the same SEEK-001 capability-declaration cluster. Disposition:
  **(b)** all of `TestCapabilityDeclaration` (SEEK-001) moved to
  `tests/backends/conformance/test_identity.py` as `TestSeekableCapability`;
  uses `BackendFixture.capabilities` from the fixture registry with
  `_DECLARES = {local, memory, s3, s3_pyarrow, sftp, sqlblob, dafny}` and
  `_DOES_NOT_DECLARE = {azure, http}` — no concrete backend class imports,
  covers all registered families including `dafny` and `sqlblob` which the
  original string-form table omitted. **(a)** `TestAzureRangeReader` plus
  `_FakeBlobClient` / `_FakeDownloader` helpers moved verbatim to a new
  `tests/backends/azure/test_seekable.py`. Root `tests/test_seekable.py`
  retains Store-API tests SEEK-002 through SEEK-012 (excluding SEEK-006) using
  only the allowed `MemoryBackend`; `"test_seekable.py"` removed from
  `_BACKEND_AT_ROOT_GRANDFATHERED` in `scripts/check_test_placement.py`. Two
  migration-pending entries remain (`test_coverage_gaps`, `test_pbt_write_result`)
  plus the permanently-justified `test_examples.py`. Audit-014 prescription
  confirmed accurate — `outcome: ok` on the audit read.
  Audience: `infra.test`, `contributor.process`. Spec: TEST-003, SEEK-001, SEEK-006.
  Trace: [`sdd/traces/BK-220-test-seekable-conformance-reshape-and-azure-per-backend.yml`](traces/BK-220-test-seekable-conformance-reshape-and-azure-per-backend.yml).

- [x] **BK-218 — Reshape `tests/test_depth_listing.py` (conformance marker + per-backend lift) (BK-191 slice 3/6)**
  Third migration-pending slice from BK-191's audit. `tests/test_depth_listing.py`
  fired Rule B via three function-local concrete-cloud imports — `_sftp`
  (`TestSFTPBackendNativeDepth`'s `sftp_stub` fixture), `_s3_base` and
  `_azure` (two `inspect.signature` checks in `TestS3AzureMaxDepthSignature`);
  everything else in the file uses the allowed in-process backends.
  Reframes audit-014's proposed "(b) move the file body to a new
  `tests/backends/conformance/test_depth_listing.py`": that prescription
  would have duplicated `conformance/test_listing.py::TestListFilesCompleteness`,
  which already parametrizes `list_files(max_depth=…)` over the full fixture
  registry, and it mis-modelled DEPTH-001 / DEPTH-002 as backend-conformance
  when spec 037 makes them Store-level ("No Backend ABC change"). Shipped
  disposition — **(a)** lift the three backend-specific snippets, each to a
  per-backend `test_depth_listing.py`: `TestSFTPBackendNativeDepth` (its
  `listdir_attr` call-count assertions verify SFTP's recursive-traversal
  *pruning*, not the result-correctness invariant) → `tests/backends/sftp/`,
  `test_s3_base_accepts_max_depth` → `tests/backends/s3/`, and
  `test_azure_accepts_max_depth` → `tests/backends/azure/` (`_s3_base` and
  `_azure` both import without their cloud SDKs, so these stay unguarded
  Stage-1 `inspect.signature` checks — symmetric Stage-1 coverage for both
  families). **(b)** Consolidate the cross-protocol DEPTH-003 *result*
  invariant onto pre-existing tests rather than a new conformance file:
  `@pytest.mark.spec("DEPTH-003")` was stacked onto the existing depth tests
  in `conformance/test_listing.py` and onto the pre-existing behavioural
  `tests/backends/azure/test_config.py::test_list_files_max_depth` (BUG-155)
  (multi-marker is an established pattern). Store-level DEPTH-001 /
  DEPTH-002 and the in-process-backend DEPTH-003 tests stay at root in
  `tests/test_depth_listing.py`, a TEST-010-compliant home once the
  concrete-cloud imports leave (unused `stat` / `MagicMock` imports
  removed). `"test_depth_listing.py"` removed from
  `_BACKEND_AT_ROOT_GRANDFATHERED` in `scripts/check_test_placement.py`; the
  allow-list now holds the three migration-pending entries (`test_coverage_gaps`,
  `test_pbt_write_result`, `test_seekable`) plus the permanently-justified
  `test_examples.py`. Three slices remain (BK-191 stays open as the umbrella).
  Reconsidered against CLAUDE.md § Audits rule 3 — diagnosis (the TEST-003
  violation at root) authoritative; original prescription (new conformance
  file) advisory. Audience: `infra.test`, `contributor.process`.
  Spec: TEST-003, TEST-010, DEPTH-001, DEPTH-002, DEPTH-003.
  Trace: [`sdd/traces/BK-218-test-depth-listing-conformance-marker-and-per-backend-lift.yml`](traces/BK-218-test-depth-listing-conformance-marker-and-per-backend-lift.yml).

- [x] **BK-217 — Split `tests/test_ping.py` (conformance + per-backend) (BK-191 slice 2/6)**
  Second migration-pending slice from BK-191's audit. Reframes the audit's
  proposed (a) per-backend disposition into a hybrid (b)+(a) split after
  re-reading the PING contract: `Backend.check_health()` is an ABC method
  (PING-002), not a capability, and PING-009 requires every failure to
  map to a `RemoteStoreError` subclass — combining the two yields a
  universal invariant ("outcome is either None or a `RemoteStoreError`
  subclass; native SDK exceptions never leak") that holds across the
  whole fixture registry regardless of fixture-precondition variance.
  New `tests/backends/conformance/test_check_health.py` parametrizes
  that invariant over every registered backend. The genuinely
  backend-specific parts — SDK-mocked probe identity
  (`head_bucket(Bucket=...)` / `stat(base_path)` /
  `get_container_properties()` / `get_file_info(bucket)`) and SDK
  error-mapping branches (PING-009) — moved to
  `tests/backends/{s3,sftp,azure,local}/test_ping.py`, with PING-005
  appended to `tests/backends/s3/test_pyarrow.py` (no
  `tests/backends/s3_pyarrow/` directory exists; mirrors BK-216).
  Root `tests/test_ping.py` keeps only `Store.ping()` delegation (PING-001)
  and observe `on_ping` / `on_error` integration (PING-010);
  `test_default_check_health_is_noop` (PING-002 via memory),
  `test_memory_backend_always_healthy` (PING-008), and `test_healthy_local`
  (PING-003 happy) were dropped as duplicates of the new conformance
  parametrize (memory and local fixtures cover those backends naturally).
  `"test_ping.py"` removed from `_BACKEND_AT_ROOT_GRANDFATHERED` in
  `scripts/check_test_placement.py`; the allow-list now holds the four
  migration-pending entries (`test_coverage_gaps`, `test_depth_listing`,
  `test_pbt_write_result`, `test_seekable`) plus the permanently-justified
  `test_examples.py`. Four slices remain (BK-191 stays open as the umbrella).
  Reconsidered against CLAUDE.md § Audits rule 3 (added in the same branch
  as the divergence from audit-014's original prescription) — diagnosis
  (the TEST-003 violation at root) authoritative; original prescription
  (pure (a) split) advisory. The first naive "`check_health()` is None"
  assertion surfaced three real signals: HTTP's check_health legitimately
  fails on a directory URL even when files are reachable (per PING-004
  spec note); SFTP's in-process fixture doesn't `mkdir base_path` at yield
  time; and **`S3Backend.check_health()` silently no-ops** because
  `self._fs.s3.head_bucket(...)` returns an aiobotocore coroutine the
  current code never awaits — filed as BUG-208 (discovery_followup) under
  a new `## S3 Correctness` section in BACKLOG.md; xfail-gated in the
  conformance test until the fix lands. Audience: `infra.test`,
  `contributor.process`. Spec: TEST-003, TEST-010, PING-002, PING-009.
  Trace: [`sdd/traces/BK-217-test-ping-conformance-and-per-backend-split.yml`](traces/BK-217-test-ping-conformance-and-per-backend-split.yml).

- [x] **BK-216 — Split `tests/test_config.py` per backend (BK-191 slice 1/6)**
  First migration-pending slice from BK-191's audit. The 13 concrete-backend
  tests in `tests/test_config.py` (SEC-005 SFTP enum coercion + RET-010..RET-013
  backend retry acceptance and SDK retry mapping) moved to their per-backend
  homes: `tests/backends/sftp/test_config.py`, `tests/backends/s3/test_config.py`,
  `tests/backends/azure/test_config.py`, and `tests/backends/s3/test_pyarrow.py`
  (no dedicated `tests/backends/s3_pyarrow/` directory exists — corrects the
  audit doc's pointer). Pure config-layer tests (CFG-*, Secret/`SecretRedactionFilter`,
  `RetryPolicy`, `TestFromToml*`, `TestResolveEnv*`) and the two cross-cutting
  RET-014 / RET-020 tests (which use only `_local` / `_memory` / the `remote_store`
  module) stay at root. With every banned-backend import gone from
  `tests/test_config.py`, `"test_config.py"` was removed from
  `_BACKEND_AT_ROOT_GRANDFATHERED` in `scripts/check_test_placement.py`; the
  allow-list now holds the five migration-pending entries plus the
  permanently-justified `test_examples.py`. Five slices remain (BK-191 stays
  open as the umbrella). Audience: `infra.test`, `contributor.process`.
  Spec: TEST-003, TEST-010.
  Trace: [`sdd/traces/BK-216-test-config-per-backend-split.yml`](traces/BK-216-test-config-per-backend-split.yml).

- [x] **BK-215 — `test_examples.py` allow-list justification documented (BK-191 slice 7/7)**
  First per-slice follow-up to BK-191, the only slice with disposition (c)
  "keep at root with documented justification". Updated the comment block
  above `_BACKEND_AT_ROOT_GRANDFATHERED` in `scripts/check_test_placement.py`
  to distinguish `test_examples.py` (justified permanently by the ID-044
  example/test 1:1 invariant — the HTTP read-only example demo binds the
  only banned-backend site) from the six migration-pending files. The
  allow-list entry stays in place. The remaining six slices (`test_config`,
  `test_coverage_gaps`, `test_depth_listing`, `test_pbt_write_result`,
  `test_ping`, `test_seekable`) are still tracked under BK-191; each retires
  its entry when its `(a)` / `(b)` refactor lands. Audience: `contributor.process`,
  `infra.test`. Spec: TEST-003.
  Trace: [`sdd/traces/BK-215-test-examples-justification.yml`](traces/BK-215-test-examples-justification.yml).

- [x] **BK-206 — Bump CI actions off Node.js 20 (audit: direct actions clear; nested actions tracked under BK-230)**
  Audited every `uses:` line across `.github/workflows/*.yml` against each
  action's published `action.yml` / release notes to determine the internal
  Node runtime. All Node-based GitHub-org actions are already pinned at
  versions whose runtime is Node 24, ahead of the June 2026 default-enforce
  and September 2026 removal of Node 20:
  - `actions/checkout@v6` — Node 24
  - `actions/setup-python@v6` — Node 24
  - `actions/setup-java@v5` — Node 24 (v5.0.0+ uses Node 24)
  - `actions/cache@v5` — Node 24
  - `actions/upload-artifact@v7` / `actions/download-artifact@v8` — Node 24
  - `actions/configure-pages@v6` — Node 24
  - `actions/deploy-pages@v5` — Node 24
  - `actions/upload-pages-artifact@v5` — composite (delegates to upload-artifact)
  - `actions/dependency-review-action@v5` — Node 24
  - `astral-sh/setup-uv@v8.1.0` — Node 24
  - `github/codeql-action/{init,analyze}@v4` — composite (no Node runtime)
  - `codecov/codecov-action@v6` — composite
  - `pypa/gh-action-pypi-publish@release/v1` — Docker (no Node runtime)
  Third-party JS actions used by single workflows (`prefix-dev/rattler-build-action@v0.2.37`
  in `conda-recipe.yml`, `dafny-lang/setup-dafny-action@v1.9.1` SHA-pinned in
  `ci.yml`) are out of scope for the GitHub-org Node 20 deprecation sweep;
  if they age into Node 20 enforcement they will be tracked under a new
  item with the specific finding. Audience: `infra.ci`.

  **Follow-on cleanup (PR #621 review):** dropped the
  `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"` env var at
  `.github/workflows/mutation.yml:17` (added by BK-168 / commit b6f2a34 to
  force then-Node-20 actions onto Node 24). The audit confirms every action
  in `mutation.yml` is already pinned at a Node-24-runtime version, so the
  flag is a no-op.

  **Audit gap surfaced post-merge (BK-230):** the third-party scope-out
  missed that `dafny-lang/setup-dafny-action@v1.9.1` (used by
  `verify-formal`) is *composite* and its internal steps pin
  `actions/setup-dotnet@v4` + `actions/setup-node@v4`, both still Node 20.
  The deprecation annotation kept firing on every `verify-formal` run.
  Reintroducing `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` on that one job
  silences it; tracked and fixed under BK-230.
  Trace: [`sdd/traces/BK-206-node-runtime-audit.yml`](traces/BK-206-node-runtime-audit.yml).

- [x] **BK-207 — Scope non-package tests to Python 3.13 in CI matrix**
  The `test` job ran a Python 3.10–3.14 matrix over the entire `tests/` tree,
  including `tests/scripts/` (230 collected items) which verifies contributor
  tooling in `scripts/` and does not exercise `remote_store` source. Added
  `--ignore=tests/scripts` to the matrix pytest invocation and introduced a
  single Python 3.13 `tooling-test` job that runs `pytest tests/scripts/ -q`.
  Coverage gates are unaffected — the matrix coverage target is `remote_store`,
  and the excluded tests do not exercise it (the few `from remote_store ...`
  occurrences in `tests/scripts/test_check_test_placement.py` are inside
  triple-quoted string fixtures fed to the placement checker, never imported).
  TEST-003 (test placement) is unchanged. Audience: `infra.ci`.
  Trace: [`sdd/traces/BK-207-tooling-test-job.yml`](traces/BK-207-tooling-test-job.yml).

- [x] **BK-205 — Wire `check_rst_roles` and `check_docs_framework` into CI lint job**
  `scripts/check_rst_roles.py` and `scripts/check_docs_framework.py` ran in the
  local `hatch run lint` script but were absent from the CI `lint` job in
  `.github/workflows/ci.yml` — `check_docs_framework.py` ran only in the `docs`
  job, and `check_rst_roles.py` had no CI invocation at all. Added both
  `python scripts/check_*.py` steps to the CI lint job alongside the other
  `check_*` scripts, applying the dual-wire principle uniformly. Mirror of
  BK-203 in the opposite direction (CI had what local lint lacked; this closes
  the local-has, CI-lacks gap). Surfaced during BK-203 review (PR #617).
  Trace: [`sdd/traces/BK-205-dual-wire-ci-checks.yml`](traces/BK-205-dual-wire-ci-checks.yml).

- [x] **BK-201 — SFTP test-hygiene: remove TESTING.md Rule 3 violations on `SFTPBackend` private state**
  Three pre-existing assertions on `SFTPBackend` private attributes in
  `tests/backends/sftp/test_config.py` lacked the
  `# internal: no public observable` exception tag that TESTING.md
  Rule 3 requires. Per-site disposition:
  - `test_resolve_host_keys_direct` (was L801, in `TestSFTPHelpers`):
    deleted the private-attribute test and replaced it with a new
    `TestSFTPInlineHostKeysVerification` class (SFTP-007) holding two
    straight-line live-fixture tests — STRICT + matching inline
    `known_host_keys` connects; STRICT + mismatched key (fresh
    `RSAKey.generate(2048)`) raises `BackendUnavailable` /
    `RemoteStoreError`. Bad-key backend uses
    `RetryPolicy(max_attempts=1, ...)` to skip the 3× connect retry.
    Proves the inline-key path is actually wired into the connection
    flow, which the deleted assertion only inferred indirectly.
  - `test_host_key_policy_string_coercion` (L882): tagged with
    `# internal: no public observable` plus a concrete reason —
    `__repr__` does not surface `_host_key_policy`, and downstream
    behavior (AUTO_ADD / TRUST_ON_FIRST_USE both call `AutoAddPolicy()`;
    STRICT defaults to `RejectPolicy`) is covered by
    `TestSFTPInlineHostKeysVerification` and `TestSFTPTofuPersistence`.
    The assertion pins the string→enum equivalence contract.
  - `test_tofu_inline_keys_not_persisted` (was L1721): replaced
    `assert backend._tofu_keys_path is None` with the mock pattern
    already used by `test_tofu_save_failure_suppressed` —
    `patch.object(backend._ssh_client, "save_host_keys") as save_mock`
    around `close()`, then `save_mock.assert_not_called()`. Touching
    `_ssh_client` to install the patch is consistent with the rest of
    the file (Rule 3 bans asserting on private attrs, not accessing
    them). Audience: `infra.test`, `contributor.process`.
  Trace: [`sdd/traces/bk-201-sftp-test-hygiene.yml`](traces/bk-201-sftp-test-hygiene.yml).

- [x] **BK-203 — Dual-wire gen-checks into `hatch run lint`**
  `gen_graph.py --check`, `gen_features.py --check`, `gen_graph_viz.py --check`, and
  `check_api_docs.py` ran in CI but not in `hatch run lint`, so generated-file
  staleness was only caught post-push. Added all four invocations to the `lint` array
  in `pyproject.toml` to close the local/CI gap. Surfaced during BK-202 work when the
  SFTPUtils refactor invalidated `graph.json` and `graph_viz.html` but lint did not
  flag it. Custom check scripts belong in lint AND CI, not CI alone.

- [x] **BK-202 — `SFTPUtils` helpers rendered as true `@staticmethod` on docs.remotestore.dev**
  The four `SFTPUtils` helpers (`load_private_key`, `scan_host_keys`,
  `scan_host_algorithms`, `enable_ssh_rsa_compat`) were exposed via the
  `name = staticmethod(name)` rebinding pattern, which griffe's static
  analysis cannot follow: the reference page rendered the methods with
  the `func` label, no signature, and the `_sftp` private module path
  leaking through the doc target. Moved the four function bodies inside
  the `SFTPUtils` class with `@staticmethod` decorators; removed the
  rebinding block. `HostKeyPolicy` stays at module level (preserves
  `from remote_store.backends._sftp import HostKeyPolicy` import sites
  in tests, benchmarks, and fixtures). `sftp-utils.md` now targets
  `SFTPUtils.<method>` with `show_root_heading: true`, matching
  `store.md`'s pattern; two cross-doc anchors in
  `troubleshooting.md` and `backends/sftp.md` updated to the new
  fully-qualified form. Verified by `mkdocs build --strict` (clean) and
  the SFTP test suites (no regressions). Audience: `user.site`,
  `user.api_docs`.

- [x] **BUG-207 — `Mutation Testing` matrix shard ran `python -m pytest` against a venv without pytest**
  Surfaced once BUG-206's setup-job fix let the matrix run for the first
  time since BK-186 PR 2. `.github/workflows/mutation.yml`'s mutate job
  was the only workflow that drove the venv through `hatch run …` (every
  other workflow in the repo does `uv pip install -e ".[dev]"`
  directly). Hatch 1.16.5 + `installer = "uv"` + `features = ["dev",
  "docs", "bench"]` silently produces a venv without the features
  installed; `scripts/run_mutate.py` then shells `subprocess.run([
  sys.executable, "-m", "pytest", ...])` and the venv answers
  `No module named pytest`. The hatch/uv interaction was confirmed
  locally by hatch failing to remove a partially-pruned `.venv` and the
  subsequent re-sync not restoring missing deps.
  Fix: replace the mutate step's `uv pip install hatch` +
  `hatch run mutate …` pair with the same uv-based pattern the rest of
  CI uses — `uv pip install -e ".[dev]" "pytest-gremlins>=1.5"` followed
  by `python scripts/run_mutate.py …`. `pytest-gremlins` is the only
  mutate-specific dep not in `[dev]`, so it lifts into the install
  command directly; the hatch shim was only an alias for the same
  script invocation, so nothing else moves. The setup job stays as-is —
  BUG-206's lazy fixture-package re-export already makes it run on bare
  `actions/setup-python` without project install.
  Audience: `infra.ci`.
  Trace: [`sdd/traces/BUG-207-mutation-shard-no-pytest.yml`](traces/BUG-207-mutation-shard-no-pytest.yml).

- [x] **BUG-206 — scheduled `Mutation Testing` cron failed at the setup job**
  The `mutation.yml` setup job runs `python scripts/run_mutate.py
  --list-scopes` (and `--container-needs <name>`) on a vanilla
  `actions/setup-python@v6` runner with no project install. Before
  BK-186 PR 2 the script was self-contained; after PR 2 it imports
  `tests.backends.fixtures._loader`, which triggers
  `tests/backends/fixtures/__init__.py`. The package init eagerly
  re-exported five names from `registry`, and `registry` imports both
  `pytest` and `remote_store._backend` at module scope. Neither is
  available in the setup job, so the first scheduled run after PR 2
  (2026-05-09) failed with `ModuleNotFoundError: No module named
  'pytest'` before any mutation matrix shard started.
  Fix: re-export the five public names lazily via `__getattr__` in
  `tests/backends/fixtures/__init__.py`. Importing the package no
  longer pulls `registry`, so the `_loader`-only path used by
  `mutate_scopes.py` runs with stdlib + `tomllib` alone; the lazy path
  is only exercised under pytest, where the deps are present.
  Regression guard: `tests/scripts/test_mutate_scopes.py::test_run_mutate_introspection_runs_without_pytest_or_remote_store`
  subprocess-runs every introspection command (`--list-scopes` and
  the three `--container-needs` variants) under a `sys.meta_path`
  finder that blocks `pytest` and `remote_store`, mirroring the bare
  CI environment.
  Audience: `infra.ci`, `infra.test`.
  Trace: [`sdd/traces/BUG-206-mutation-setup-bare-python.yml`](traces/BUG-206-mutation-setup-bare-python.yml).

- [x] **BK-199 — `SFTPUtils.scan_host_keys(host, port=22) -> str` preflight host-key discovery**
  Static helper that opens a `paramiko.Transport`, performs key exchange
  without authenticating, captures `transport.get_remote_server_key()`,
  and returns a single `known_hosts`-formatted line ready to commit into
  a `host.keys` file. Mirrors `ssh-keyscan`. The label follows OpenSSH
  convention: bare hostname for port 22, `[host]:port` otherwise.
  Network failures raise `OSError` cleanly (socket created via
  `socket.create_connection` to avoid paramiko's tuple-handling leak);
  KEX failures raise `paramiko.SSHException` so callers know to apply
  `enable_ssh_rsa_compat()` first for legacy servers. Tests cover the
  full-server flow (matches the in-process fixture's
  `host_key_entry`), bracket/no-bracket formatting via the small
  `_format_known_hosts_line` helper, and unreachable-port failure.
  Audience: `user.api`, `user.site`.
  Trace: [`sdd/traces/BK-199-scan-host-keys.yml`](traces/BK-199-scan-host-keys.yml).

- [x] **BK-200 — SFTP `scan_host_algorithms()` raw-socket KEXINIT diagnostic**
  Companion to `scan_host_keys()`, but returns the server's full RFC
  4253 § 7.1 algorithm advertisement (kex / host-key / cipher / MAC /
  compression name-lists) instead of the negotiated key. Pure socket
  + manual KEXINIT parse, so the result reflects exactly what the
  server advertises — independent of any process-global paramiko state
  mutated by `enable_ssh_rsa_compat()` or downstream code. Surfaces
  the diagnostic needed to triage `IncompatiblePeer` errors:
  `IncompatiblePeer` wraps four distinct negotiation failures (host
  key, KEX, cipher, MAC) and only the first is addressable by
  `enable_ssh_rsa_compat()`. Hooked into `SFTPBackend._map_exception`:
  the non-host-key `IncompatiblePeer` hint now points at
  `scan_host_algorithms()` and `connect_kwargs={"disabled_algorithms":
  ...}`. New "Diagnose first" subsection in the SFTP backend guide.
  Tests: `TestSFTPScanHostAlgorithms` (unit/integration against the
  infra sftp fixture, asserts the eleven documented entries
  and shape) and `TestSFTPScanHostAlgorithmsLegacy` in
  `tests/e2e/test_sftp_legacy_recovery.py` (asserts
  `server_host_key_algorithms == ["ssh-rsa"]` against the legacy-sftp
  container — the exact diagnostic that motivated the helper).
  `TestSFTPIncompatiblePeerHint::test_incompatible_peer_kex_hint_points_at_scan_host_algorithms`
  locks the new KEX-variant hint. Audience: `user.api`, `user.site`.
  Trace: [`sdd/traces/BK-200-scan-host-algorithms.yml`](traces/BK-200-scan-host-algorithms.yml).

- [x] **BK-198 — SFTP `enable_ssh_rsa_compat()` for paramiko 5+ legacy-server compatibility**
  Paramiko 5.0 removed `ssh-rsa` (SHA-1) from its host-key defaults
  across all four negotiation sites (`Transport._preferred_keys`,
  `Transport._preferred_pubkeys`, `Transport._key_info`,
  `RSAKey.HASHES`). Fresh `pip install remote-store[sftp]` resolves to
  paramiko 5+ today, so connecting to an `ssh-rsa`-only legacy SFTP
  server raises `IncompatiblePeer: no acceptable host key` during KEX
  on a default install. Empirical test against a Dockerized
  `ssh-rsa`-only server across paramiko 2.12 / 3.0 / 3.5 / 4.0 / 5.0
  (see [`sdd/research/research-bk-198-paramiko-ssh-rsa-empirical.md`](research/research-bk-198-paramiko-ssh-rsa-empirical.md))
  confirms: paramiko `< 5` ships `ssh-rsa` in defaults and connects
  out of the box; paramiko `>= 5` requires the helper. Ships three
  coordinated changes:
  (a) `SFTPUtils.enable_ssh_rsa_compat()` static method appending
  `ssh-rsa` to all four sites idempotently — required on paramiko 5+,
  no-op on `< 5`. Process-global; documented as a security reduction.
  (b) `SFTPBackend._map_exception` annotates
  `paramiko.ssh_exception.IncompatiblePeer` with a hint scoped to the
  `"host key"` substring (so KEX / cipher / MAC variants pass through
  as plain `BackendUnavailable`). (c) New "Legacy Servers (`ssh-rsa` /
  SHA-1)" guide section covering symptoms, remedy, security tradeoff,
  and the `paramiko<5` pin alternative with explicit cost. Tests in
  `TestSFTPEnableSshRsaCompat` (idempotency + four-site coverage with
  paramiko state restored after), `TestSFTPIncompatiblePeerHint` (hint
  present on host-key `IncompatiblePeer`, absent on KEX / other
  `SSHException`), and the e2e
  `tests/e2e/test_sftp_legacy_recovery.py` (parametrised on
  `paramiko.__version__` against a real Dockerized legacy server).
  Audience: `user.api`, `user.site`.
  Trace: [`sdd/traces/BK-198-ssh-rsa-compat.yml`](traces/BK-198-ssh-rsa-compat.yml).

- [x] **BK-197 — `HostKeyPolicy` accepts enum-name aliases**
  Value strings of `HostKeyPolicy` are `"strict"`, `"tofu"`, `"auto"`
  (`src/remote_store/backends/_sftp.py:68-70`); the latter two do not
  match their enum names (`TRUST_ON_FIRST_USE`, `AUTO_ADD`). Callers
  typing `"auto_add"` or `"trust_on_first_use"` hit
  `ValueError: 'auto_add' is not a valid HostKeyPolicy`. Added
  `_missing_` hook that maps the enum-name forms (case-insensitive)
  to canonical members; existing YAML configs using `"auto"` /
  `"tofu"` / `"strict"` continue to work unchanged. New test class
  `TestSFTPHostKeyPolicyAliases` covers the supported alias forms
  and confirms unknown values still raise.
  Audience: `user.api`.
  Trace: [`sdd/traces/BK-197-host-key-policy-aliases.yml`](traces/BK-197-host-key-policy-aliases.yml).

- [x] **BUG-204 — SFTP backend declared `paramiko>=2.2` but used paramiko 3.0+ API (`channel_timeout`)**
  `SFTPBackend._connect()` passes `channel_timeout=self._timeout` to
  `paramiko.SSHClient.connect()` (`src/remote_store/backends/_sftp.py:864`).
  The `channel_timeout` keyword was added in paramiko 3.0; paramiko 2.x
  raised `TypeError: SSHClient.connect() got an unexpected keyword
  argument 'channel_timeout'` at runtime. `pyproject.toml` `[sftp]`
  extra now requires `paramiko>=3.0`, matching what the code actually
  uses. Surfaced when a user pinned `paramiko<3` to recover ssh-rsa
  (SHA-1) host-key support for a legacy SFTP server (PSFTPd). New
  test `TestSFTPParamikoVersionSurface` asserts `channel_timeout` is in
  the installed paramiko's `SSHClient.connect` signature, guarding the
  lower bound against future drift.
  Audience: `user.api`.
  Trace: [`sdd/traces/BUG-204-paramiko-lower-bound.yml`](traces/BUG-204-paramiko-lower-bound.yml).

- [x] **BUG-205 — TOFU persistence through `Registry.get_store()` (withdrawn — not a bug)**
  Hypothesized that `SFTPBackend`'s TOFU flow did not persist newly
  accepted host keys to disk when the backend was constructed via the
  store registry; investigation under the failing-test-first protocol
  showed paramiko's `AutoAddPolicy.missing_host_key` already auto-saves
  to the path that `SFTPBackend.load_host_keys` sets on the client. No
  code change; recorded here so future contributors who form the same
  hypothesis can find the prior reasoning without re-filing the ID.
  Audience: `dev.process`.
  Discussion: [`sdd/traces/BK-198-ssh-rsa-compat.yml:25-26`](traces/BK-198-ssh-rsa-compat.yml).

- [x] **BK-192 — `copy()` metadata parity on `MemoryBackend` and `AsyncMemoryBackend`**
  Both backends constructed the destination `_FileEntry` in `copy()` without
  `metadata=src_node.metadata`, so `write(path, data, metadata={...}) → copy(path, dst) → get_file_info(dst)`
  returned `metadata=None`. Fix: pass `metadata=src_node.metadata` to the
  `_FileEntry(...)` constructor in `src/remote_store/backends/_memory.py::copy`
  and `src/remote_store/aio/backends/_memory.py::copy`. Regression coverage:
  `TestMemoryCopyMetadataRoundTrip` in `tests/backends/memory/test_coverage.py`
  and five new methods on `TestAsyncMemoryMetadataRoundTrip` in
  `tests/backends/memory/aio/test_basics.py`, covering `get_file_info`,
  `list_files` (recursive + non-recursive), the `None`-metadata control, and
  the `overwrite=True` path. Surfaced as a review note on PR #607 (BK-176).
  Audience: `user.api`. Spec: BE-019, ASYNC-019, WR-013.
  Trace: [`sdd/traces/bk-192-copy-metadata-parity.yml`](traces/bk-192-copy-metadata-parity.yml).

- [x] **BK-194 — Ripple-check rewrite: compact pre-work index + detailed verify checklist**
  `sdd/CLAUDE-REFERENCE.md` § Ripple-check table previously served only
  the verify-end purpose (a closing checklist after the diff was made).
  Trace research ([`research-agent-workflow-substrate.md`](research/research-agent-workflow-substrate.md)
  § 2.3) sampled 9 merged PRs and found 3 missed ripples (#604 `ci.yml`,
  #591 `graph.json` + `graph_viz.html`, #592 `_proxy.py` + extension
  wrappers) because agents consulted ripple-check only at the end. The
  section now carries two presentations of the same set of triggers:
  Pre-work index (one-liner per trigger, scanned before starting) and
  Detailed checklist (full ripples, verify-end + reviewer use). H2
  anchor `## Ripple-check table` preserved so the 30+ existing trace
  section strings (`Ripple-check table / <row>`) still resolve.
  CLAUDE.md principle 2 extended to mention both presentations.
  `.claude/skills/review-pr`, `release`, and `orchestrate` updated to
  point at the right H3 (Pre-work index at orient, Detailed checklist
  at verify-end). Consistency between the two tables is reviewer-enforced;
  if drift recurs, a check script can be promoted into BACKLOG. First
  live-authored trace under the BK-193 rule.
  Audience: `contributor.process`. CHANGELOG: — (process restructuring,
  not a new framework; matches BK-193 precedent).
  Trace: [`sdd/traces/bk-194-ripple-check-rewrite.yml`](traces/bk-194-ripple-check-rewrite.yml).

- [x] **BK-193 — Trace schema: `audience` field + post-hoc fields; re-tag unreleased traces**
  Cross-checking 9 sampled traces against their merged PRs surfaced
  five gaps the original schema could not represent: (1) which
  constituency a change is *for* (the `not_user_facing` boolean
  conflated context7-LLM presentation, lint tooling, test infra, and
  internal style); (2) discovery cascades during review (one fix
  surfaces another); (3) bundled scope (one PR closes several backlog
  items); (4) mechanical ripples authors do not cite (backlogid.json,
  graph.json, ci.yml); (5) review iteration count.
  `sdd/traces/_schema.yml` gains five fields: `audience` (required,
  priority-sorted list, 10 enum values: `user.api`, `user.api_docs`,
  `user.site`, `user.discoverability.{llm,human}`, `contributor.process`,
  `contributor.tooling`, `infra.test`, `infra.ci`, `internal.style`);
  `discovery_followups`, `co_shipped_items`, `expected_ripples` (optional
  lists); `review_rounds` (optional int). Derived rule: CHANGELOG
  required iff any `audience` entry starts with `user.`, or
  `contributor.process` introduces a new user-facing framework. All 39 unreleased
  traces under `sdd/traces/` re-tagged; 9 sampled traces additionally
  carry retrospective `discovery_followups` / `co_shipped_items` /
  `expected_ripples` / `review_rounds` filled from their merged PRs
  (#579, #582, #590, #591, #592, #597, #604, #606, #607). No validator
  wired — the `required` field acts as authoring convention; future
  traces failing to tag will fail visibly on the next aggregator run
  rather than at commit time.
  Research: [`sdd/research/research-agent-workflow-substrate.md`](research/research-agent-workflow-substrate.md)
  identifies the substrate the workflow-improvement programme needs;
  trace-vs-PR fidelity analysis (3 phases, 9-PR sample) was the empirical
  method that motivated the schema additions.
  Trace: [`sdd/traces/bk-193-trace-schema-audience.yml`](traces/bk-193-trace-schema-audience.yml)
  documents this work; declared retrospective in its `trigger` field
  because BK-193 itself ships the live-authoring rule that future
  traces (starting with BK-194) will follow.
  Schema-review iteration added two more fields and renamed one to close
  the "traces describe ideal, not actual" gap: optional step-level
  `outcome` (`ok` / `unclear` / `misleading`) for descriptive→diagnostic
  doc-failure signal; top-level `surprising_ripples` paired with
  `expected_ripples` (the latter introduced in the first review wave on
  this branch as `known_ripples`, then renamed before merge so the
  expected-vs-surprising distinction is load-bearing in the name).
  Six tagged traces carry `expected_ripples`; three of those
  (BK-178 / BK-179 / BK-187) additionally carry `surprising_ripples`
  for paths the ripple-check table did not anticipate (graph regen after
  docstring sweep; `ci.yml` after lint-scope or test-job change). Schema
  description prose tightened to instruct authors that traces record
  what actually happened, not what was supposed to happen.

- [x] **BK-176 — `AsyncMemoryBackend` metadata round-tripping parity with sync `MemoryBackend`**
  Added `metadata=node.metadata` to all four `FileInfo`-constructing sites in
  `src/remote_store/aio/backends/_memory.py`: `get_file_info`, `list_files`
  non-recursive, `iter_children`, and `_collect_files_from_snapshot`. Added a
  parametrized regression test class `TestAsyncMemoryMetadataRoundTrip` in
  `tests/backends/memory/aio/test_basics.py` covering all four sites plus a
  `None`-metadata control case. Spec: ASYNC-016.

- [x] **BK-190 — tests/ root cleanup phase C: enforce + document**
  Three CI-enforced placement rules in
  `scripts/check_test_placement.py`, all derived from spec 048:
  - **S** (existing): tests loading `scripts/` modules via `sys.path`
    must live in `tests/scripts/`.
  - **B** (new): top-level `tests/test_*.py` may import from
    `remote_store.backends._*` only the in-process backends (`_memory`,
    `_local`) and the shared `_fileinfo` helper. Concrete cloud /
    network classes imported via either the private module path or the
    public `remote_store.backends` namespace are TEST-003 violations.
    The banned class roster is computed at script import via
    `_discover_banned_backend_names`, a static AST scan over
    `src/remote_store/backends/_*.py` and
    `src/remote_store/aio/backends/_*.py` that excludes modules in
    `_ALLOWED_BACKEND_MODULES`; a new backend file added under either
    directory automatically extends the banned set with no
    hand-maintained list to drift. A grandfathered allow-list of
    cross-cutting legacy files (each also importing `MemoryBackend` or
    `LocalBackend`) lives in `_BACKEND_AT_ROOT_GRANDFATHERED`. Per-file
    migration tracked as **BK-191**. New top-level files are held to
    the strict standard.
  - **E** (new): top-level `tests/test_ext_*.py` is banned, and every
    `tests/ext/test_<x>.py` must have a matching
    `src/remote_store/ext/<x>.py`. The single namespace-wide contract
    (`tests/ext/test_contract.py`) is on a small allow-list inside the
    script.
  New scope-check classes under
  `tests/scripts/test_check_test_placement.py`
  (`TestBackendImportsAtRoot`, `TestRootExtNaming`, `TestExtOrphans`)
  cover positive and negative paths plus the grandfather skip and the
  contract allow-list. `sdd/TESTING.md` § Test Subpackage Placement
  table extended with `tests/ext/` and `tests/aio/ext/` rows and the
  new naming column; rule prose links to the script's
  `_BACKEND_AT_ROOT_GRANDFATHERED` and `_BANNED_BACKEND_NAMES` rather
  than enumerating. `sdd/specs/048-testing-architecture.md` TEST-010
  directory-layout snippet now shows `tests/ext/` and `tests/aio/ext/`.
  BK-182 and BK-177 re-scoped to current paths after BK-179's reorg
  (their original locations no longer exist). Spec: TEST-002, TEST-003,
  TEST-010.

- [x] **BK-189 — tests/ root cleanup phase B: `tests/ext/` package + ext-module moves**
  Mirrors `src/remote_store/ext/`'s layout (the async sibling at
  `tests/aio/ext/` already followed this shape). Created
  `tests/ext/__init__.py`. Migrated 15 ext-module tests plus the
  namespace-contract test under it, dropping the inconsistent
  `test_ext_` prefix in 5 of them:
  - bare-named (kept the name): `test_arrow.py`, `test_batch.py`,
    `test_cache.py`, `test_dagster.py`, `test_integrity.py`,
    `test_observe.py`, `test_otel.py`, `test_partition.py`,
    `test_streams.py`, `test_transfer.py`.
  - prefixed (renamed): `test_ext_parquet.py` →
    `tests/ext/test_parquet.py`; same for `pydantic`, `write`, `yaml`,
    `contract`.
  `tests/test_glob.py` split: core `_glob` helpers and
  `Store.glob`/`Backend.glob` (Tier 1 + Tier 2 + GLOB-012/013/014 helper
  tests) stay at root; `ext.glob.glob_files` Tier 3 (`TestGlobFiles`)
  moves to `tests/ext/test_glob.py` with its own minimal fixture set.
  `tests/ext/test_batch.py` and `tests/ext/test_transfer.py` switch
  `from .conftest import RestrictedBackend` to `from tests.conftest
  import RestrictedBackend` (matching the `tests/aio/ext/` absolute-
  import pattern). `tests/ext/test_contract.py`'s `_SRC =
  Path(__file__).resolve().parent.parent / "src" / "remote_store"` walks
  one level deeper now (`.parent.parent.parent`) to land on the repo
  root. `scripts/mutate_scopes.py` collapses the dual
  `test_<name>*.py` + `test_ext_<name>*.py` matching: `_matching_tests`
  is split into `_matching_core_tests(name)` and
  `_matching_ext_test(name)`, the `ext_prefix=True` knob is gone, and a
  new `ext-misc` orphan-catch covers `tests/ext/test_*.py` files with
  no matching `ext/<x>.py` source (today only `test_contract.py`). The
  per-module `ext-*` scopes still cover every ext source file, and
  `core-glob` and `ext-glob` are now cleanly separated. Spec: TEST-002,
  TEST-010.

- [x] **BK-188 — tests/ root cleanup phase A: backend-specific evictions + seekable rename**
  Three TEST-003 / TEST-010 placement fixes at `tests/` root, each a pure
  move with no behaviour change:
  - `tests/test_memory_coverage.py` → `tests/backends/memory/test_coverage.py`
    (covers `backends/_memory.py` MemoryBackend internals — TEST-003 home).
  - `tests/test_tls_ca_bundle.py` → `tests/backends/s3/test_tls_ca_bundle.py`
    (covers `backends/_s3_base.py` `_resolve_tls_ca_bundle` /
    `_validate_tls_ca_bundle` — S3-only).
  - `tests/test_ext_seekable.py` → `tests/test_seekable.py` (subject is
    `Store.read_seekable()` on the core `Store` API per spec 036
    SEEK-001..SEEK-012, not an ext module — drop misleading `ext_`
    prefix).
  `scripts/mutate_scopes.py`'s `core-memory` per-file scope folds away
  (no top-level test paired with `backends/_memory.py` after the move);
  the moved file is picked up by the existing `backends-memory` /
  `backends-http` transport scopes via the registry walk. Comment in
  `_add_per_file` updated to match. Phases B (`tests/ext/` package) and
  C (placement checks + TESTING.md / spec 048 update) follow under
  BK-189 / BK-190. Spec: TEST-003, TEST-010.

- [x] **BK-184 — `s3_live` Stage 3 conformance fixture**
  Per-call fresh bucket (`rs-conformance-<uuid>`), mirroring `azure_live.py` shape.
  Files: `fixtures.toml` `[fixture.s3_live]`, `_live_env.require_s3_live_credentials`,
  `TestRequireS3LiveCredentials` (10 cases), `s3_live.py`, spec 048 TEST-010 layout.
  Full sweep result: **162 passed, 18 skipped, 0 failed** (5 min, real AWS eu-central-1).
  All 18 skips are capability-gated: 13 flat-namespace folder tests, 2 WR-005, 1 WR-013,
  1 flat-namespace file/folder distinction, 1 virtual-folder deletion behaviour.

- [x] **BK-187 — Expand lint/format/typecheck scope to `scripts/` and `examples/`**
  `hatch run lint`, `format`, and `format-check` now cover `scripts/` alongside
  `src/`, `tests/`, `examples/`. `hatch run typecheck` adds `examples/` so that
  user-facing example code is held to the same `mypy --strict` bar as `src/`.
  Two scope carve-outs documented inline in `pyproject.toml`:
  `examples/medallion_dagster/` is excluded (its modules use sibling-relative
  imports that resolve only under the dagster launcher), and
  `examples/snippets/custom_backend_guide.py` carries `# mypy: ignore-errors`
  matching its existing `# ruff: noqa` (intentionally-incomplete tutorial
  fragments referenced by `--8<--` snippet markers in the Build Your Own
  Backend guide). `scripts/` was kept on the lint/format gate but deferred
  for typecheck — its 70+ `--strict` errors (untyped json/yaml dict literals,
  griffe API drift in `gen_graph.py`, stub gaps for `yaml`/`mkdocs_gen_files`)
  are queueable as a follow-up. The 26 example scripts under
  `hatch run examples` and the 31 demo-consuming tests in
  `tests/test_examples.py` + `tests/test_snippets.py` continue to pass; two
  snippet rewrites (`write_integrity{,_async}.py`) moved
  `assert result.digest is not None` *into* the rendered snippet block so the
  guide now demonstrates safe `Optional` access rather than relying on the
  post-snippet runtime assertion.

- [x] **BK-186 — Physical fixture/backend registry as single source of truth**
  Two-layer SSoT shipped across PR 1 (foundation) and PR 2 (consumers).
  PR 1 introduced `tests/backends/fixtures/backends.toml` + `fixtures.toml`
  + pure `_loader.py` with closed-enum validation; `BackendFixture` gained
  `flat_namespace`, `self_op_supported`, `transport`, `container` fields;
  the `_FLAT_NAMESPACE_BACKENDS` / `_NO_SELF_OP_BACKENDS` identity sets,
  the per-fixture import list in `_load_all`, and the `_VALID_KINDS` /
  `_VALID_STAGES` triples were folded into the loader. Closed BK-185.
  PR 2 made every scope derived. Non-backend scopes pair each
  `src/remote_store/_<x>.py` / `src/remote_store/ext/<x>.py` /
  `src/remote_store/backends/_<x>.py` with prefix-matching
  `tests/test_<x>*.py` files (per-file scopes); top-level test files
  matching no src by prefix roll into a single `core-misc` scope.
  Backend scopes come from `backends.toml` + `fixtures.toml`:
  `backends-local` / `backends-cloud` collapse into transport-derived
  `backends-{fs,memory,sql,http,ssh}`; the four split conformance topics
  (`io`, `atomic`, `errors`, `identity`) partition by transport instead
  of the hand-curated `LOCAL_STACK` / `CLOUD_STACK` literals. Mutation
  matrix grows from 20 to 60 scopes (12 per-file core + 15 per-file
  ext + core-memory + core-misc + 5 backends-* + 1 sync-adapter + 3
  unsplit conformance + 20 split conformance + 2 async-extended);
  `mutate_scopes.py` itself shrinks from 322 to 240 lines (-25%). `_BACKEND_LITERALS` in
  `test_registry.py::TestLayoutBoundary` derives fixture-path portions
  from `fixtures.toml`. `_live_env.py` exposes
  `require_live_credentials(descriptor, ...)` so BK-184's `s3_live`
  fixture can wrap the same emulator-signature core.
  `tests/conftest.py` reachability helpers route through one
  `_container_reachable(name)` keyed by a single `_CONTAINER_PORTS`
  map. Spec: TEST-001, TEST-004, TEST-005, TEST-006, TEST-008
  (transport-driven), TEST-010.

- [x] **BK-185 — Refactor flat-namespace gating from backend identity to capability/kind**
  Closed structurally by BK-186 PR 1: per-fixture `flat_namespace` /
  `self_op_supported` boolean fields on `BackendFixture` (sourced from
  `tests/backends/fixtures/backends.toml` + `fixtures.toml` via
  `_loader.py`) replace the `_FLAT_NAMESPACE_BACKENDS` /
  `_NO_SELF_OP_BACKENDS` identity sets keyed by `backend.name`. The
  Azurite emulator and live ADLS Gen2 now decide their namespace shape
  independently despite sharing `backend == "azure"`; the previously
  silent-skipped sync directory contracts in
  `tests/backends/conformance/test_errors.py` now exercise `azure_live`
  on Stage 3, surfacing the BUG-198/BUG-200/BUG-203 family that BK-180's
  sync sweep missed. The `HNS_AWARE` / `REAL_DIRECTORIES` capability
  alternatives are no longer needed: the per-fixture override is
  sufficient. Spec: TEST-005 (capability gating).

- [x] **BK-180 — Implement Spec 048 Phase 2: live Azure conformance fixtures**
  Adds `azure_live` and `azure_live_async` (Stage 3, kind `real-live`) to
  the registry per spec [TEST-001/004](specs/048-testing-architecture.md);
  conformance parametrize includes both when `--stage=3` and
  `RS_TEST_LIVE_HNS=1` are set. Each factory call provisions a fresh HNS
  filesystem (`conformance-<uuid>` / `conformance-async-<uuid>`) on the
  configured account and tears it down on cleanup; isolation matches the
  per-call shape used by `azurite` / `s3_moto`. The async cleanup channel
  is the new optional `BackendFixture.aclose:
  Callable[[AnyBackend], Awaitable[None]] | None` field — the conformance
  `async_backend` indirect fixture (now `async def`) awaits it before
  the synchronous `cleanup`. Spec TEST-004's dataclass example carries
  the additive field. The `_live_env.require_azure_live_connection_string`
  helper centralises the env-var validation (empty / Azurite-pointing
  values fail loud, not skip silent); the legacy live-HNS suite under
  `tests/backends/azure/test_live_hns.py` keeps its own inline copy
  pending BK-182's deletion.

  Verification: full conformance + extended sweep against a real ADLS
  Gen2 account in 2:45 — 208 passed, 24 skipped (capability gates), 20
  failed. The reds are real defects HNS surfaces that Azurite forgives;
  they are tracked as **BUG-198..BUG-203** plus addenda on **BUG-195**
  and **BUG-197**, not as BK-180 scope per the D4 decision (file
  follow-ups, ship the fixture wiring).

  Live S3 (`s3_live`) carved out to **BK-184** — `S3Backend` has no
  prefix support, so the bucket-isolation strategy needs a deliberate
  decision rather than copying the Azure shape.

- [x] **BK-183 — Per-topic `mutate-conformance-*` scopes (Windows-compatible)**
  Closes the conformance coverage gap noted during BK-179 review (PR #597,
  round 4): the per-backend `mutate-backends-{local,cloud}` scopes do not
  exercise `tests/backends/conformance/`, so a mutation in `_local.py` /
  `_s3.py` / etc. that kills only a conformance assertion is reported as a
  survivor. Adding the directory to either scope pushes pytest-gremlins'
  coverage subprocess past Windows' ~32 KiB command-line limit (WinError
  206). New scopes: `mutate-conformance-{listing,metadata,streaming,sync-adapter}`
  for topics that fit as one file, plus `-{io,atomic,errors,identity}-{local,cloud}`
  and `-async-extended-{local,memory}` for topics that exceed the limit
  (split by backend group via `-k`, with source-file targets matching the
  filter). Verified end-to-end on Windows by running
  `mutate-conformance-listing` (1184 mutations, 0 survivors).
  `.github/workflows/mutation.yml` is extended to include every new scope
  in the scheduled "all" list, the `workflow_dispatch` choices, and the
  summary aggregation; MinIO / Azurite / SFTP container startup conditions
  are widened to cover the new scopes that exercise the corresponding
  fixtures.

- [x] **ID-177 — Design and set up long-term docstring style enforcement**
  `scripts/check_rst_roles.py` scans `src/`, `tests/`, `scripts/`, and
  `examples/` for RST inline roles and fails with file:line output. Wired into
  `hatch run lint` and the `no-rst-roles` pre-commit pygrep hook.
  `sdd/DESIGN.md` § 4 documents the gate.

- [x] **BK-179 — Implement Spec 048 Phase 1: fixture registry + conformance reorganisation**
  Foundational refactor before any new fixtures or replay layer.
  Introduces `tests/backends/fixtures/registry.py` per spec
  [TEST-004](specs/048-testing-architecture.md) with the
  `BackendFixture` record (name, backend, factory, stage, kind,
  capabilities, is_async, cleanup, marks) and the `fixtures()` /
  `fixture_params()` helpers. Per-backend factory modules register
  every existing fixture: memory, local, http, s3_moto, sftp_inproc,
  sqlblob, dafny_oracle, azurite, s3_pyarrow_moto, s3_pyarrow_minio,
  sftp_docker, memory_async_native, memory_async_adapted,
  local_async_adapted. Stage 2 SFTP-Docker is wired into the CI
  `test` job. The `--stage=N` CLI flag (TEST-006) auto-detects via
  `docker info` (Stage 2 if reachable, Stage 1 otherwise). Conformance
  splits into seven topic files under `tests/backends/conformance/`
  with class-level capability-filtered parametrize replacing the
  `_require()` runtime-skip pattern (TEST-005). Backend-specific
  tests move into per-backend subtrees under `tests/backends/<x>/`
  with optional `aio/` siblings. Async conformance and sync-adapter
  conformance move under `tests/backends/conformance/`. TESTING.md
  placement table is updated to match. 14 spec-marker tests pin
  TEST-001/004/005/006/010 invariants. Spec: TEST-002, TEST-003,
  TEST-004, TEST-005, TEST-006, TEST-010.

- [x] **BK-175 — Live HNS test architecture: design phase**
  Original exit criterion was "RFC for the parametrize + cassette design".
  Delivered as a spec + ADR pair, exceeding the RFC scope: the design covers
  the whole testing tree, not just Azure HNS, with kind × stage axes, a
  conformance-as-spine layout, fixture registry, native pytest gating, and
  HTTP-only cassette/replay demotion. Implementation is split into four
  follow-up items (BK-179 Phase 1: fixture registry + reorganisation;
  BK-180 Phase 2: live conformance fixtures; BK-181 Phase 3: HTTP replay
  layer; BK-182: shrink legacy `test_azure_live_hns.py`). The
  HNS-specific bug fixes BUG-195, BUG-196, BUG-197 land into the new
  layout once BK-179/180 are green. Spec:
  `sdd/specs/048-testing-architecture.md`. ADR:
  `sdd/adrs/0028-testing-architecture-kind-stage-replay.md`.

- [x] **ID-178 — `list_folders(pattern=…)` — name-based glob filter**
  `Store.list_folders` and `AsyncStore.list_folders` accept an optional
  `pattern` keyword mirroring `list_files(pattern=…)` (STORE-014). When set,
  `FolderEntry` items whose `.name` does not match the pattern via
  `fnmatch.fnmatch` are excluded. Filtering is Store-level, applied after
  BFS traversal and path rebasing; `pattern=` does not prune traversal.
  Composes with `max_depth=`: depth governs which folders are visited,
  pattern governs what is yielded. `ProxyStore`, `ObservedStore`, and
  `CachedStore` forward the parameter (cache key extended from a 3-tuple to
  a 4-tuple — pre-upgrade entries become unreachable, no collision). No
  Backend ABC change. Originally filed as ID-175; renumbered after a
  collision with `ID-175 — Author templates folder` was caught by the
  `gen_backlogid.py --check` lint gate. Design: RFC-0013. Specs: STORE-017
  added in `sdd/specs/001-store-api.md`; DEPTH-002 amended in
  `sdd/specs/037-depth-limited-listing.md`.

- [x] **BK-178 — Fix all RST cross-reference roles in audit-013-touched files (docstring style)**
  Replaced RST role violations (`:class:`, `:meth:`, `:func:`, `:data:`, `:mod:`)
  with double-backtick inline code in the 10 files touched by audit-013.
  Initial pass fixed the 20 audit-flagged sites; PR review (#591) found audit-013
  was incomplete — the same files held additional RST roles in non-flagged
  docstrings (class/method/function bodies). Per CLAUDE.md principle 2
  ("verify beyond the diff"), widened the scope: also fixed
  `_async_to_sync_adapter.py` × 13 (class + helper docstrings),
  `_info.py:85`, `_config.py:313` (TOML loader, parallel to the audit-flagged
  YAML loader), `aio/_async_store.py` × 4 (sibling inner-generator docstrings),
  `tests/aio/_doubles.py` × 13 (class docstrings), and `scripts/docs/scan.py` × 6
  (function/class docstrings). Verified the touched files now contain zero
  `:role:`...`` patterns. No spec change; no CHANGELOG entry (internal
  style, not user-facing). Audit: `sdd/audits/audit-013-docstring-style.md`.
  Follow-up: ID-177 tracks the long-term enforcement gate; auditing the
  remaining repo files for RST roles is left for that gate to surface.

- [x] **BUG-194 — `AsyncAzureBackend.write_atomic` broken for all payloads on real ADLS Gen2**
  `_count_and_pass_hns` wrapped bytes in an async generator to count bytes while
  streaming. On the HNS code path, `upload_data` was called with that generator; the
  Azure SDK's `get_length()` returns `None` for async generators, so
  `flush_data(position=None)` omitted the required DFS query parameter and Azure returned
  `MissingRequiredQueryParameter`. The bug was latent since the HNS path was introduced:
  Azurite tolerates a missing `position` while real ADLS Gen2 does not, so no existing
  Azurite-backed test caught it. Isolated with `tmp/probe_dfs.py` (steps 1–7 rule out
  SDK issues; step 5 — `upload_data(async generator)` — reproduced the failure).

  **Initial fix** (during PR #590 development): `AsyncIterator` payloads were buffered to
  a `bytes` object so `upload_data` could receive a known-size argument. This resolved the
  `MissingRequiredQueryParameter` error but violated SIO-003/ASYNC-021 — the same
  streaming anti-pattern BUG-165 introduced and later fixed in the non-HNS path. Caught
  in PR review.

  **Final fix**: bytes input passes directly to `upload_data` (SDK's `get_length(bytes)`
  returns `len()`; no regression). `AsyncIterator` input drives the DFS append protocol
  directly: `create_file`, then `append_data(chunk, offset=position, length=chunk_len)`
  per chunk, then `flush_data(position)` with the final byte count. Memory is bounded to
  one chunk at a time (SIO-003, ASYNC-021 preserved). No current framework caller passes
  an `AsyncIterator` to async `write_atomic` for HNS, so the streaming regression was
  latent, not active.

  The async HNS live suite (`tests/aio/test_async_azure_live_hns.py`, added by BUG-193)
  confirmed the fix — all 9 live tests pass against a real ADLS Gen2 account.
  PR: #590. Spec: WR-001a, WR-004, AZ-034, ASYNC-010, SIO-003, ASYNC-021.

- [x] **BUG-193 — Async HNS live test suite missing; sync HNS live tests lacking `WriteResult` assertions**
  `TestAsyncAzureLiveHNS` in `tests/aio/test_async_azure_live.py` (added by BUG-182) used the
  Azurite-backed `async_azure_backend` fixture. Azurite does not emulate HNS, so `_ensure_hns()`
  returned `False` and `write_atomic` silently delegated to `write` — the temp-file + rename
  path was never exercised. The sole assertion (`isinstance(result, WriteResult)`) violated
  TESTING.md Rule 2. The class also inherited the module-level
  `skipif(not _azurite_reachable())` guard, blocking it in real-ADLS-Gen2-only CI even when
  `RS_TEST_LIVE_HNS=1` was set.

  Separately, the sync `test_write_atomic_metadata_survives_rename` (BUG-182) discarded the
  `write_atomic` return value entirely, missing WR-012 (metadata echo in
  `WriteResult.metadata`), WR-001a (size, source), and the uniquely-live cross-check that
  `WriteResult.etag` (from the post-rename `get_file_properties` call) matches
  `get_file_info().etag` (independent SDK read — the only assertion that surfaces normalisation
  drift between two distinct SDK paths on a real account).

  Fixed:
  1. Removed `TestAsyncAzureLiveHNS`; added `tests/aio/test_async_azure_live_hns.py` — a
     dedicated file with a real-ADLS-Gen2 fixture, no Azurite dependency, and explicit
     separation from the Azurite-gated module. Three classes: `TestAsyncLiveHnsWriteResult`
     (WR-001a, WR-004, AZ-034 — source, size, etag normalisation, last_modified, etag
     cross-check vs `get_file_info`), `TestAsyncLiveHnsMetadata` (WR-012, WR-013),
     `TestAsyncLiveHnsDirectoryGuard` (BE-021, BE-008, BE-010 — `write` and `write_atomic`;
     `open_atomic` absent from the async API, noted in docstring).
  2. Enhanced `TestAzureLiveHnsMetadataSurvivesRename` with `WriteResult` field assertions
     (WR-012 echo, WR-001a size/source).
  3. Added `TestAzureLiveHnsWriteResult` with the etag cross-check (WR-001a, WR-004, AZ-034).
  4. Updated `azure-hns-setup.md` guide: replaced stale "gap still open" paragraph with a
     positive description of the new file.
  Follow-up tracked as **BUG-196** in `sdd/BACKLOG.md`: the async `write_atomic` HNS path
  (`aio/backends/_azure.py:578`) calls `get_file_properties()` without the BUG-173 try/except
  fallback the sync path carries.
  PR: #590. Spec: WR-001a, WR-004, WR-012, WR-013, AZ-034, BE-008, BE-010, BE-021.

- [x] **BUG-182 — Verify HNS `write_atomic` user metadata survives the atomic rename in integration**
  `test_write_atomic_hns_metadata_preserved` (BUG-181) only verifies that `metadata=` is
  forwarded to `upload_data` on the temp file and that `WriteResult.metadata` echoes the
  caller's mapping by construction (WR-012). The harder property — ADLS Gen2's `rename_file`
  preserves user-defined metadata on the renamed final file — is a service-side semantics
  concern only a real account can answer. Added
  `tests/backends/test_azure_live_hns.py::TestAzureLiveHnsMetadataSurvivesRename` (one
  parametrized-free test, 1 KiB payload, sibling file under the existing module-scoped
  session prefix) that writes via `write_atomic(path, payload, metadata=...)` against a
  real ADLS Gen2 account and asserts the metadata round-trips via `get_file_info(path)`.
  Production code was already correct (the live test passed on first run, confirming
  BUG-181's docstring claim); this closes the verification gap rather than fixing a
  defect. Sync-only scope per BACKLOG-defined boundary; the `TestAsyncAzureLiveHNS` class
  in `tests/aio/test_async_azure_live.py` still uses the Azurite-backed fixture and is
  not re-wired here — the docs guide describes that gap factually instead of forwarding
  to a closed BUG. Spec: WR-013, BE-010.

- [x] **BUG-191 — Add live HNS test class for `write`/`write_atomic`/`open_atomic` directory-path guard**
  BUG-190 and BUG-192 added unit-mocked tests that fabricate `hdi_isfolder=true` on a mocked `BlobProperties` to verify the `InvalidPath` precondition. The mocks rely on the same probe assumption the code uses, so they verify code logic but not real-account behaviour. Added a focused live integration suite at `tests/backends/test_azure_live_hns.py::TestAzureLiveHnsDirectoryGuard` (three tests, 1 KiB payload, module-scoped fixture creating one HNS directory via `DataLakeServiceClient.create_directory`) that exercises the same three guards against a real ADLS Gen2 account. Gated on the new `live` pytest marker (excluded by default `addopts`) plus `RS_TEST_LIVE_HNS=1` plus a real-account `AZURE_STORAGE_CONNECTION_STRING` (Azurite-shaped values fail loud rather than silently skip). Setup guide updated to describe the new gating layer. Followed the BUG-170/175/176 verification intent (real backend, not mocks) but kept the scope narrow to the three guards rather than the full extended-conformance suite, since live cloud tests bear real cost. Spec: BE-021, BE-008, BE-010, SAW-001.

- [x] **BUG-192 — `AzureBackend.open_atomic` HNS branch missing `InvalidPath` guard for directory paths**
  Same pre-fix pattern as `write`/`write_atomic` before BUG-190: the HNS branch probed `get_blob_properties()` only under `overwrite=False` and never checked `hdi_isfolder`, causing `AlreadyExists` on `overwrite=False` or silent fall-through on `overwrite=True`. Fixed by applying the same unified probe pattern: check `hdi_isfolder` first and raise `InvalidPath`; fall through to the `AlreadyExists` guard only for regular files. Removed stale `# pragma: no cover` annotations from the now-covered HNS probe and yield/rename blocks. Added three HNS-mocked unit tests (`test_open_atomic_raises_invalid_path_on_hns_dir`, `test_open_atomic_regular_file_not_affected`, `test_open_atomic_path_not_found_proceeds`). Spec: BE-021.

- [x] **BUG-190 — Azure `write`/`write_atomic` on a directory path does not raise `InvalidPath` per BE-021/ASYNC-024**
  `AzureBackend` and `AsyncAzureBackend` violated BE-021/ASYNC-024 for `write` and `write_atomic` on HNS directory paths: `bc.get_blob_properties()` succeeded for HNS dirs (returning `hdi_isfolder=true` metadata), causing `AlreadyExists` on `overwrite=False` or a silent upload on `overwrite=True`. Fixed by unifying the blob-properties probe for both `overwrite` modes: check `hdi_isfolder` first and raise `InvalidPath`; fall through to the `AlreadyExists` guard only for regular files. Added HNS-mocked unit tests for sync and async (`TestAzureWriteOnHnsDirectory`, `TestAsyncAzureWriteOnHnsDirectory`). Spec: BE-008, BE-010, ASYNC-008, ASYNC-010, BE-021, ASYNC-024.

- [x] **BK-174 — Document `InvalidPath` on async `write`/`write_atomic` across the verified ripple layers**
  Follow-up to BK-173. The canonical error mapping
  ([BE-021](specs/003-backend-adapter-contract.md), cross-referenced from
  [ASYNC-024](specs/029-async-store-backend-api.md)) requires `write` and
  `write_atomic` to raise `InvalidPath` when ``path`` names a directory.
  `AsyncMemoryBackend.write` already documented it, but
  `AsyncMemoryBackend.write_atomic`, the `AsyncBackend` ABC, and
  `SyncBackendAdapter` only documented `AlreadyExists`.
  Aligned the docstrings on the layers where runtime is verified by tests:
  the `AsyncBackend` ABC (contract layer), `SyncBackendAdapter` (delegates
  to sync backends with verified `InvalidPath` semantics), and
  `AsyncMemoryBackend.write_atomic` (delegates to its own `write`, which
  raises `InvalidPath`). `AsyncStore` left unchanged: the sync `Store`
  documents only Store-layer validation (empty `path`) and lets
  backend-layer `InvalidPath` propagate; `AsyncStore` mirrors that
  convention. Added two conformance tests for `write_atomic(dir)`
  mirroring the existing `write(dir)` tests, traced to ASYNC-010. Also
  bundled the matching `--` → `—` (U+2014) swap in
  `AsyncBackend.delete_folder`'s `Raises:` clause that was deferred from
  BK-173 to keep the verbatim-mirror property between the ABC and
  `SyncBackendAdapter` holding character-for-character.
  `AsyncAzureBackend.write`/`write_atomic` were intentionally **not**
  updated: investigation surfaced that `classify_azure_error` does not
  map any Azure SDK error to `InvalidPath`, so the runtime does not
  uphold the canonical contract on HNS directories. Tracked as **BUG-190**
  for a follow-up that fixes the runtime (explicit `IsDir` check)
  together with HNS-mocked tests and the docstring claim.

- [x] **BK-173 — Complete the four-layer async docstring ripple at `SyncBackendAdapter`**
  PR #580 (BUG-189) review surfaced that the four-layer ripple chain
  (concrete backend → ABC → `AsyncStore` → `SyncBackendAdapter`) was applied
  through layer 3 but left the adapter's I/O methods silent. This item
  closes layer 4: nine previously silent methods (`read`, `read_bytes`,
  `delete_folder`, `get_file_info`, `get_folder_info`, `move`, `copy`,
  `write`, `write_atomic`) now carry `Raises:` clauses mirrored verbatim
  from the `AsyncBackend` ABC. User-facing via `help()` and IDE hover
  today; rendered docs site will surface them once the planned `aio.md`
  rework drops `members: false` (or adds explicit `:::` method blocks)
  on the four concrete async classes that currently render as empty
  headings (`SyncBackendAdapter`, `AsyncBackendSyncAdapter`,
  `AsyncMemoryBackend`, `AsyncAzureBackend`).

- [x] **BUG-189 — `AsyncMemoryBackend` did not mirror sync error fidelity for type-mismatched paths**
  The native `AsyncMemoryBackend` raised `NotFound` in several cases where
  the sync `MemoryBackend` (and the Dafny contract) require `InvalidPath`:
  `read`/`read_bytes`/`get_file_info` on a directory path,
  `get_folder_info` on a file path, `delete_folder` on a file path
  (including with `missing_ok=True` — type mismatch is not "missing"), and
  `move`/`copy` with a directory `src`. `copy(src, src, overwrite=False)`
  also incorrectly raised `AlreadyExists` instead of being a no-op like
  the sync backend (and like async `move(src, src)`). Discovered by
  porting the extended conformance suite from
  `tests/backends/test_conformance_extended.py` to the async side as
  classes mirroring BE-006..BE-021. Fix: align `_memory.py` branches with
  the canonical sync logic; document `InvalidPath` on the `AsyncBackend`
  ABC for `read`, `read_bytes`, `delete_folder`, `get_file_info`,
  `get_folder_info`, `move`, `copy`. Spec coverage added: ASYNC-004,
  ASYNC-005, ASYNC-006, ASYNC-007, ASYNC-008, ASYNC-013, ASYNC-014,
  ASYNC-015, ASYNC-016, ASYNC-017, ASYNC-018, ASYNC-019, ASYNC-020,
  ASYNC-024 (in addition to the existing ASYNC-012 stub).

- [x] **ID-176 — Wire stable docs site to context7**
  Added `docs-src/context7.json` to claim `https://docs.remotestore.dev/stable/`
  on context7 (`https://context7.com/websites/remotestore_dev_stable`). MkDocs
  copies non-Markdown files verbatim into the build output, so the file is
  present at the correct URL in every RTD stable build with no workflow changes.
  Includes `projectTitle`, `description`, and website-specific `rules` that
  guide LLMs toward the rendered Diataxis structure (tutorial/, guides/,
  reference/, explanation/) and key page URLs, rather than repeating source-code
  facts. Intentionally differs from the repo-level `context7.json`.

- [x] **BUG-188 — Benchmark SVG images broken on performance docs page**
  `build_source_map` indexed only `*.md` and `*.html` under `docs-src/`.
  The BK-171 `LinkResolver` hook rewrites every `](…)` token — including
  image syntax `![alt](path)` — so SVG assets fell through to the GitHub
  blob URL fallback and rendered as broken images. Fix: index every served
  file under `docs-src/` (excluding `_`-prefixed names, which are MkDocs
  infrastructure not served as pages) so no asset type can silently regress.
  Regression tests: `test_build_source_map_includes_docs_src_images`,
  `test_link_resolver_rewrites_image_syntax_to_in_site_path`.

- [x] **BK-171 — Reliable link validation for docs-only files in both repo and docs-site presentations**
  Universal on-disk link rule (DOCFRAME-008). `mkdocs_hooks.py` registers an
  `on_page_markdown` hook that applies `LinkResolver` to every `docs-src/`
  file at build time, so authors write on-disk repo paths everywhere — links
  resolve in the GitHub repo browser by construction and get rewritten to
  docs-site URLs at render time. The 76 docs-src class-3 links (virtual-URL
  form like `(../design/adrs/0002-…md)`) migrated to on-disk source form
  (`(../../sdd/adrs/0002-…md)`). `check-links` collapsed to a single mode
  that walks every git-tracked `.md`; `--mode repo`/`--mode site` interface
  removed; `check_site_links` deleted. SDD kind rules hoisted from
  hardcoded Python to [`docs-src/_path_rules.yml`](../docs-src/_path_rules.yml);
  `build_source_map` extended to include `examples/<subdir>/<stem>.py` →
  `tutorial/examples/<slug>.md` so docs-src files can link to runnable
  example sources. Closes audit-012 F-01 honestly (BK-167b's closure had
  exempted `docs-src/` from R1).
- [x] **BK-172 — Run S3-PyArrow tests against MinIO when pyarrow ≥ 24**
  On pyarrow ≥ 24, `S3PyArrowBackend` routes to MinIO instead of
  `ThreadedMotoServer` — which returns a `CompleteMultipartUpload` response
  shape that pyarrow 24's C++ S3 client rejects as `INTERNAL_FAILURE`.
  Changes: `minio_server` session fixture added to `tests/conftest.py`;
  `_s3_pyarrow_available()` in `tests/backends/conftest.py` checks MinIO
  reachability when pyarrow ≥ 24; `backend` fixture routes `s3-pyarrow` to
  MinIO on pyarrow ≥ 24; `test_s3_pyarrow.py` module-level skip removed,
  `s3pa_backend` fixture routes accordingly; `pyarrow<25` cap lifted on the
  `s3-pyarrow` extra; `test` CI job starts MinIO alongside Azurite;
  `pyarrow24-skip-check` job renamed to `pyarrow24-check` and now verifies
  the MinIO route runs end-to-end. Restores S3-PyArrow conformance coverage
  (96.36% → ~98%).

- [x] **BK-168 — Lift pyarrow `<24` pin; require moto `>=5.2.0`**
  Pin raised from `<24` to `<25` on the `s3-pyarrow`, `sql-query`, and `arrow`
  extras (matches dependabot #571). Dev dep `moto[server,s3]>=5.2.0` adopted —
  5.2.0's multipart-checksum + `CompleteMultipartUpload` response-shape fixes
  unblock pyarrow 23 against `ThreadedMotoServer` (E1 verified: 118/118 backend
  tests pass with the previous `_pyarrow_ge_23()` skip removed). Pyarrow 24 still
  hits `INTERNAL_FAILURE` on `CompleteMultipartUpload` against moto (E2); skip
  marker re-added but conditioned on `_pyarrow_ge_24()` instead, with reason
  pointing to BK-172 for the MinIO migration. Mypy `follow_imports = "skip"`
  override on `pyarrow.*` retained — re-evaluation under E3 surfaced 33
  attr-defined / name-defined errors (stubs still incomplete); comment updated
  with the verification trail.

- [x] **BUG-187 — EthicalAds floats over graph viz canvas on RTD**
  `graph_viz.html` is a standalone `<!DOCTYPE html>` document, so RTD's
  EthicalAds client had no MkDocs Material sidebar to anchor to and injected
  a `div.raised[data-ea-publisher]` at `<body>` level, floating it over the
  canvas. Fix in `scripts/gen_graph_viz.py`: add `<div id="ethical-ad-placement">`
  inside `#sidebar` (the official RTD custom-placement hook per
  docs.readthedocs.com), a `MutationObserver` fallback that reparents any
  body-level injection and strips the `raised` class, and a
  `#sidebar [data-ea-publisher]` CSS rule so the ad renders inline.

- [x] **BUG-186 — API graph visualization blank on iOS Safari**
  `docs-src/explanation/graph_viz.html` rendered briefly then went blank on
  iOS Safari refresh; zoom/pan unresponsive to touch. Four root causes in
  the `scripts/gen_graph_viz.py` template: missing `<meta name="viewport">`
  (Safari assumed 980px desktop width and reflowed after first paint);
  missing `touch-action: none` on the SVG (Safari hijacked touches as native
  pinch/scroll gestures, never reaching D3's pointer handlers); missing
  SVG `viewBox` combined with the simulation's `forceX`/`forceY` design
  constants (W0=1200, H0=800) — on the ~107px canvas left after the 268px
  sidebar, nodes were pulled past the right edge as the simulation ran,
  matching the "briefly seen then disappears" symptom; `100vh` on `body`
  was unstable under Safari's dynamic URL bar. Fix adds the viewport meta,
  `viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid meet"`,
  `touch-action: none` / `user-select: none` / `-webkit-user-select: none`
  on the SVG, and a `100dvh` fallback alongside `100vh`. Existing golden
  test (`tests/scripts/test_gen_graph_viz.py`) regenerated and passing;
  desktop layout unchanged because the viewBox dimensions equal the
  pre-existing simulation design constants.

- [x] **BK-170 — Host API graph visualization in docs Explanation section**
  `graph_viz.html` moved from `docs-src/_data/graph/` to `docs-src/explanation/`
  by updating `OUT` in `scripts/gen_graph_viz.py`. Companion page
  `docs-src/explanation/graph-ir.md` added and wired into `explanation/_nav.yml`
  after Architecture Overview. `docs-src/_data/` and `graph_viz.html` excluded
  from the Context7 index in `context7.json`.

- [x] **BK-169 — Add unit tests for DOCFRAME-004 gate (G-02 through G-06)**
  Five spec-traced pytest tests added in `tests/scripts/test_check_docs_framework.py`:
  `test_dest_collision_fails` (G-02), `test_jinja_in_dual_file_fails` (G-03),
  `test_include_markdown_in_docs_src_fails` (G-04), `test_broken_repo_link_in_dual_fails`
  (G-05), `test_url_nav_misalignment_fails` (G-06). Each test builds a minimal
  `tmp_path` fixture tree and asserts directly on the `_check_gXX` return value.

- [x] **ID-175 — Author templates folder (`sdd/templates/`)**
  `sdd/templates/` created with five starter templates: `rfc-template.md`
  (moved from `sdd/rfcs/`), `spec-template.md`, `adr-template.md`,
  `audit-template.md`, `research-template.md`. Directory default (repo-only)
  added to `scan.py` and documented in `AUTHORING.md`. Links in
  `CONTRIBUTING.md` and `CLAUDE-REFERENCE.md` updated.

- [x] **BK-167b — Apply documentation framework; close audit-012 findings**
  All `.md` files classified with `<!-- doc: dual dest=... -->`,
  `<!-- doc: repo-only -->`, or `<!-- doc: docs-only -->` markers (or
  covered by directory defaults). Bridge (DOCFRAME-005) live: gen_pages.py
  calls `scan_dual_files` + `render_dual_pages`; include-markdown wrappers,
  `_link_map.yml`, `render_sdd_wrappers`, and `render_link_rewritten` all
  removed. Nav restructured to Diataxis-pure top-level (Tutorial, Guides,
  Reference, Explanation); `explanation/design/` URL prefix aligned;
  Changelog moved under Reference; Further Reading section removed.
  `mkdocs build --strict` restored in CI; `check-links` wired into
  `hatch run all`. All 11 audit-012 findings and 1 warning closed as of
  2026-05-02. Supersedes the partial BK-167b entry below.

- [x] **BK-167a — Documentation framework tooling**
  Single bridge mechanism (`scan.scan_dual_files` + `render.render_dual_pages`)
  replacing include-markdown wrappers, `_link_map.yml`, and the legacy
  gen-files scan helpers. Inline HTML-comment classification markers with
  directory-default rules for SDD subdirs and `docs-src/`. `check_links.py`
  two-mode link checker. Spec 047 and ADR-0027 authored. DOCFRAME checks
  G-01 through G-07 implemented; G-01..G-06 pass as lint; unit tests for
  G-02..G-06 deferred to BK-169. `hatch run all` gate green.

- [x] **BK-167b (partial) — check_links.py link checker**
  `scripts/docs/check_links.py` — two-mode internal link checker (`--mode repo` for raw on-disk targets, `--mode site` for post-rewrite dual-file destinations). 11 spec-traced tests in `tests/scripts/test_check_links.py`. `hatch run check-links` script added. Remainder (classify all `.md`, wire gate, close audit-012 findings) continues in BK-167b.

- [x] **BK-167 — Documentation framework defined and wired in**
  Three-doc documentation framework (placement → structure → longevity)
  established and wired into the contributor and Claude-session entry
  points. The framework states the rules; tooling that enforces them is
  BK-167a; applying the framework and closing audit-012 findings is BK-167b.

  - [`sdd/AUTHORING.md`](AUTHORING.md) created (placement authority): file
    classification (repo-only / docs-only / dual; default dual), single
    home, plain Markdown for dual files, single bridge mechanism, PR-time
    gate enforcing every framework rule.
  - [`CLAUDE.md` § Documentation framework](../CLAUDE.md#documentation-framework)
    names the three docs and their application order; replaces the earlier
    two-pointer "Documentation conventions" stub.
  - [`CONTRIBUTING.md`](../CONTRIBUTING.md) gains a § Documentation
    framework pointer and adds `AUTHORING.md` to the Authoritative Document
    Format scope list with all named docs linked.
  - `sdd/DOCUMENTATION.md` and `sdd/CONTENT-RULES.md` Intent & Scope
    back-reference the framework so any entry node leads to the others.
  - `sdd/DOCUMENTATION.md` tightened: § 2 cross-references
    `sdd/000-process.md` § Document types (the canonical home for SDD
    artefact lifecycle/naming, including research-doc immutability that
    DOCUMENTATION.md no longer restates); duplicate Diataxis tables
    removed (Rule 1 + Rule 2 cover it); duplicate Cross-link example
    table removed (Rule 4 covers it); Rule 5 (PR documentation review)
    moved to Guides as a heuristic checklist (review-time aid, not a
    content-shape rule); Rule 3 prose moved to Guides as "Docstring style
    notes" (table stays as Rule). Net rules: 10 → 8.
  - `sdd/CONTENT-RULES.md` Rule 4 also points to `AUTHORING.md` Rule 1 for
    file-placement authority; typography aligned to `DOCUMENTATION.md` § 8.
  - All framework cross-references are real Markdown links, clickable in
    the GitHub repo browser and crawler-discoverable.
  - `sdd/CLAUDE-REFERENCE.md` ripple-check table gains a row for
    "new authoritative process doc in `sdd/`."
  - "Diataxis" spelling normalized in the framework trio and
    `sdd/CLAUDE-REFERENCE.md` (historical entries in `CHANGELOG`,
    `DEVELOPMENT_STORY`, older RFCs, and `BACKLOG` entries unchanged).

- [x] **BK-165 — Docs structure audit for the post-ID-174 layout (audit phase)**
  Established 13 audit rules covering the three-hierarchy vocabulary (repo
  path / nav position / URL path), link integrity, Diataxis nav purity,
  generation conventions, wrapper-pattern discipline, content coverage,
  duplication, and exclusion auditability. Ran report-only audit against
  `mkdocs.yml`, `scripts/gen_pages.py`, `docs-src/_nav.yml`,
  `docs-src/_link_map.yml`, all `docs-src/design/*.md`, and a full `.md`
  inventory across `sdd/`, `docs-src/`, root, and `examples/`. Delivered as
  `sdd/audits/audit-012-docs-structure.md`: 11 findings + 1 warning across
  7 rules; 4 rules passed cleanly. Authoring guide and simplification
  follow-up: BK-167.

- [x] **BK-166 — S3 control-path moto-backed lifecycle coverage**
  Adds `tests/backends/test_s3_moto.py`: drives a full backend lifecycle
  (`write` → `list_files` → `read` → `delete`) for both `S3Backend` and
  `S3PyArrowBackend` against a `ThreadedMotoServer`, with non-trivial
  `client_options` (`s3.addressing_style="path"`, `proxies={http: None,
  https: None}`, `connect_timeout`, `read_timeout`) and a parametrized
  `RetryPolicy` variant. Reuses the session-scoped `moto_server` fixture
  in `tests/conftest.py` (no duplicate server). Pins the s3fs ≥ 2024.x
  `set_session` contract: a future regression that re-introduces a
  `client_kwargs['config']` pop in the builder fails immediately because
  nothing in this test patches the production code path — a real
  `TypeError: got multiple values for keyword argument 'config'` from
  `aiobotocore` surfaces on first I/O.

  Failure-path coverage: `test_delete_missing_maps_to_notfound` verifies
  the s3fs control-path error pipeline (`_s3fs_errors` → real moto 404 →
  `NotFound`) under the tuned `client_options` for both backends. The
  existing error-mapping tests in `test_s3.py` inject exceptions via
  `patch.object(_s3fs, "cat_file", side_effect=Exception(...))` and
  never exercise the tuned `config_kwargs` end-to-end; conformance tests
  do, but only against Docker (not the default suite). Sanity-checked
  locally by reverting the BUG-185 fix; all six cases (4 lifecycle + 2
  failure-path) failed with that exact signature, then passed again on
  restore.

  Lives under `tests/backends/` (not `tests/e2e/`, which is excluded
  from the default suite via `addopts="--ignore=tests/e2e"`) so a
  regression is caught by `hatch run test` without remembering a
  separate command — the gap BUG-178 and BUG-185 fell through. The
  unit-level `TestAiobotocoreCreateClientBoundary` continues to pin the
  kwarg shape; the rejection assertion continues to live next to it in
  `TestConfigKwargsRetryCollision::test_client_kwargs_config_is_rejected`
  (it short-circuits before any HTTP and gains nothing from a moto
  fixture, so the moto file does not duplicate it). For S3-PyArrow the
  tuned `config_kwargs` flow through the s3fs control path; only the
  actual byte transfers in `write` / `read` run through PyArrow at
  default settings, while the surrounding s3fs calls (overwrite check
  via `_s3fs.exists`, post-upload `_s3fs.call_s3('head_object', ...)`,
  plus `list_files` / `exists` / `is_file` / `is_folder` / `delete` /
  `delete_folder` / `move` / `copy`) all use the tuned `config_kwargs`.
  Matches S3PA-026's delta against S3-026 (s3fs control path only).
  Specs: S3-026, S3PA-026.

## v0.24.1

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
  option through `opts["config_kwargs"]` (a dict);
  `client_kwargs["config"]` is never set, and any caller-supplied pre-built
  `Config` in `client_kwargs` is rejected with a `ValueError` pointing at
  the supported channel. Silent rewriting hid both prior bugs and is no
  longer permitted. Spec S3-026 / S3PA-026 rewritten to pin the new
  invariant. Tests added at the actual collision boundary
  (`TestAiobotocoreCreateClientBoundary` patches
  `aiobotocore.session.AioSession.create_client` and triggers
  `s3fs.connect()`), so a future variant of the same bug class fails the
  unit suite instead of escaping to a user. Follow-up e2e coverage
  against `moto` tracked as `BK-166` (prioritized). New "Botocore Client
  Tuning" section in `docs-src/how-to/backends/s3.md` documents proxies, retries,
  timeouts, and MinIO path-style addressing; runnable snippets in
  `examples/snippets/s3_botocore_tuning.py` are wired into
  `tests/test_snippets.py` and `tests/scripts/run_examples.py` so the
  examples gate (`hatch run examples`) catches drift. **Migration:**
  callers that passed a pre-built `botocore.config.Config` via
  `client_options={"client_kwargs": {"config": Config(...)}}` must switch
  to `client_options={"config_kwargs": {...}}` (a plain dict of the same
  `Config(...)` constructor kwargs). The old form raised `TypeError` at
  first I/O on s3fs ≥ 2024.x already; it now fails fast at backend
  construction with `ValueError` and a message naming the supported
  channel.

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
  echo is by construction per WR-012 (post-rename preservation on the live file covered by BUG-182); `overwrite=True`
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
  Item 6 (`check_error_handling.py` AST script) deferred; see BK-139d in BACKLOG.md.

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
  [Showcase architecture](research/research-medallion-dagster-showcase.md).

- [x] **ID-082 — Read-only HTTP backend (`ReadOnlyHttpBackend`)**
  7th backend: read-only access to HTTP/HTTPS URLs with `{READ, METADATA}`
  capabilities. [Spec 032](specs/032-http-backend.md), 3 transports
  (urllib/requests/httpx), streaming adapters (`_HttpxStreamAdapter`,
  `_Urllib3StreamAdapter`), conformance suite capability gates, 85 tests,
  [guide](../docs-src/guides/backends/http.md), [example](../examples/backends/http_backend.py),
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
  [ADR-0010](adrs/0010-observe-proxy-pattern.md),
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
  [Spec 025](specs/025-retry-policy.md), [ADR-0011](adrs/0011-retry-per-backend-native.md).
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
