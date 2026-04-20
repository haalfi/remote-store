# Development Backlog

Active work items and ideas. Completed items live in
[BACKLOG-DONE.md](BACKLOG-DONE.md).

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

## How this file works

**Status legend:** `[ ]` pending · `[~]` in progress

**Ordering:** newest first within each section.

**Item scope:** idea + decision-relevant constraints + open questions.
Do not repeat process steps (those live in `sdd/000-process.md` and the ripple-check table).
Existing items may be more verbose — trim on next touch.

**Completing work:**

- Fully done → delete from here, add to `BACKLOG-DONE.md` as `[x]`
  (same commit as the code change).
- Partially done → split: ship the done part to `BACKLOG-DONE.md` as `[x]`
  under its original ID, create a new ID here for the remaining work, and
  link both.

**ID prefixes:**

| Prefix | Meaning |
|--------|---------|
| `BL-NNN` | Release blocker — must resolve before next PyPI publish. |
| `BK-NNN` | Committed backlog work, queued behind blockers. |
| `BUG-NNN` | Confirmed defect with reproduction steps. |
| `ID-NNN` | Idea — not evaluated, not committed to. |

---

## Release Blockers

*(none)*

---

## Bugs

- [ ] **BUG-177 — `S3Backend.write` does not surface the auto-CRC32 digest that `get_file_info` returns** (LOW)
  `_s3.py:171-184` vs `_s3.py:240-248`: the write path populates `WriteResult`
  from `self._fs.info(...)` (s3fs metadata, no checksum fields), so
  `result.digest is None`. `get_file_info()` issues a direct
  `head_object(..., ChecksumMode="ENABLED")` and `_head_to_fileinfo` converts
  any returned `ChecksumCRC32` / `ChecksumSHA256` / etc. into a
  `ContentDigest`. Since late 2022, Amazon S3 auto-computes and stores a
  CRC32 for every object uploaded without an explicit checksum algorithm, so
  for a declaring backend (`WRITE_RESULT_NATIVE`) a caller who reads back
  the object sees `info.digest == ContentDigest('crc32', ...)` while
  `result.digest` is `None` — a WR-001a divergence between `WriteResult` and
  `FileInfo` for the same just-written key.
  **Repro:** under `moto` (or any post-2022 S3 endpoint), call
  `S3Backend.write(key, data)`, then `S3Backend.get_file_info(key)`, and
  observe `info.digest is not None and result.digest is None`.
  Fix candidates: (a) in `write()`, call `head_object(..., ChecksumMode="ENABLED")`
  after the upload (same call `get_file_info` uses) and reuse
  `_digest_from_head_response` to populate `WriteResult.digest`; (b) accept
  the asymmetry as intentional (WR-007: "no v1 backend surfaces a
  server-verified digest on the default write path") and document that
  `WriteResult.digest is None` does not imply `FileInfo.digest is None`
  for the same key on the same backend. (a) is preferred because it keeps
  the two entry points consistent at no extra round-trip cost beyond what
  `get_file_info` already pays. Not yet surfaced in the conformance suite —
  `TestWriteResultConformance.test_native_file_info_matches_write_result`
  deliberately excludes `digest` from the equality check and carries a
  WR-007 comment explaining why. Wire up a strict S3 xfail alongside the
  fix.

- [ ] **BUG-176 — `SQLBlobBackend.copy(src, src, overwrite=True)` silently destroys data** (MEDIUM)
  `_sqlalchemy.py:673-721`: `copy()` has no `src == dst` early-return guard.
  The companion `move()` at `_sqlalchemy.py:649-655` does have the guard and
  behaves correctly. With `overwrite=True` and `src == dst`, `copy()`
  executes:
  1. `dst_exists` check passes (line 687 — it is the same row).
  2. `dst_exists and not overwrite` is false, so execution proceeds.
  3. `conn.execute(t.delete().where(t.c.key == dst))` deletes the row
     (line 692).
  4. The `INSERT ... SELECT` at lines 716-721 selects from the now-deleted
     row and inserts nothing. The file is silently destroyed.
  With `overwrite=False` the same pre-state check raises `AlreadyExists`
  instead of no-op'ing. Both are a spec violation per BE-019 (Dafny
  contract: `copy(x, x)` is a no-op).
  **Repro:**
  ```python
  b = SQLBlobBackend(url="sqlite:///:memory:")
  b.write("x.txt", b"data")
  b.copy("x.txt", "x.txt", overwrite=True)
  assert b.read_bytes("x.txt") == b"data"  # FAILS — NotFound or empty.
  ```
  Fix: mirror the `move()` guard at the top of `copy()` — verify source
  exists, then return. Currently skipped in `TestMoveCopySelfOperation`
  (`test_self_copy_preserves_data` and `test_self_copy_no_overwrite_preserves_data`)
  via `_NO_SELF_COPY_BACKENDS`.

- [ ] **BUG-175 — `SQLBlobBackend.glob` drops zero-segment `**/` matches on SQLite** (MEDIUM)
  `_sqlalchemy.py:734-745`: for SQLite dialects, `glob()` uses
  `t.c.key GLOB pattern` as an SQL-side pre-filter, then applies
  `pattern_to_regex` to the rows returned. SQLite's `GLOB` operator treats
  `**` as two independent `*`s and `/` as a literal separator — it cannot
  match the zero-directory case that `pattern_to_regex` and the spec
  (018 § "``**`` matches zero or more path segments") require. Rows that
  the regex would accept are silently dropped by the SQL filter before
  the regex runs.
  **Repro:**
  ```python
  b = SQLBlobBackend(url="sqlite:///:memory:")
  b.write("gr/a.txt", b"a")
  b.write("gr/sub/b.txt", b"b")
  # Pattern 'gr/**/*.txt' must match both files per spec 018.
  assert sorted(str(f.path) for f in b.glob("gr/**/*.txt")) == ["gr/a.txt", "gr/sub/b.txt"]
  # FAILS — returns only ['gr/sub/b.txt'].
  ```
  Fix candidates: (a) drop the SQLite pre-filter when the pattern contains
  `**` and rely on the regex alone; (b) follow the S3 `extract_prefix`
  approach and use the longest non-wildcard prefix as a `LIKE` narrowing,
  then regex-filter; (c) translate `**/` into a regex-equivalent SQL pattern
  directly (no obvious SQLite equivalent). Option (b) matches the pattern
  already used by S3/Azure glob implementations.
  Currently skipped in the conformance suite (recursive-glob case) pending
  a fix. Non-SQLite dialects use `LIKE` pre-filtering and are not affected.

- [ ] **BUG-173 — Azure HNS `write_atomic` leaks WriteResult-construction failures as write failures** (LOW)
  `_azure.py:488-494` (HNS-only, `# pragma: no cover`): after a successful
  `tmp_fc.rename_file()` commit, `dst_fc.get_file_properties()` is called to
  populate `etag`/`last_modified`. If that call raises (network blip,
  eventual consistency, permissions), the exception flows through
  `self._errors(path)` and surfaces as a write failure — but the file is
  already at the destination. Callers that retry will see `AlreadyExists`
  (when `overwrite=False`) or silently double-write.
  **Repro:** HNS backend, `write_atomic(path, data, overwrite=False)`; have
  `FileSystemClient.get_file_client(path).get_file_properties` raise
  `ResourceNotFoundError` (mock) after the rename succeeds. Expected: call
  returns a `WriteResult` (or, at worst, a `NotFound` that documents the
  committed-but-unreadable state). Actual: `NotFound` propagates; second
  invocation with the same args raises `AlreadyExists`.

- [ ] **BUG-172 — `_ChunkPullReader.read`/`readinto` return empty on closed stream instead of raising `ValueError`** (LOW)
  `_async_to_sync_adapter.py:613-614, 630-631`: both methods early-return
  `0` / `b""` when `self.closed`. Stdlib `io.IOBase` (which `io.RawIOBase`
  inherits from) raises `ValueError: I/O operation on closed file.` Callers
  using stream state checks against the standard contract silently get empty
  reads instead of the expected exception.
  **Repro:**
  ```python
  stream = adapter.read("path")          # returns _ChunkPullReader
  stream.close()
  assert stream.read() == b""            # currently passes
  # Expected: ValueError("I/O operation on closed file.") — matches io.BytesIO:
  b = io.BytesIO(b"x"); b.close()
  b.read()  # raises ValueError
  ```

- [ ] **BUG-170 — `SQLBlobBackend.write` omits `last_modified` from `WriteResult` under `WRITE_RESULT_NATIVE`** (MEDIUM)
  `_sqlalchemy.py:438-444`: when the `user_metadata` column is present the
  backend advertises `WRITE_RESULT_NATIVE` but returns
  `WriteResult(source="native", last_modified=None, ...)`. The `now`
  timestamp computed at line 411 is discarded. Quality gap — `source="native"`
  satisfies WR-004's textual invariant, but the Dafny refinement obligation
  under WR-004's formal-coverage clause ("rich fields on the returned
  WriteResult match the stored FileInfo") is not met.
  **Repro:**
  ```python
  backend = SQLBlobBackend(url="sqlite:///:memory:", table_name="blobs")
  # (default schema includes the user_metadata column)
  result = backend.write("a.txt", b"hi", overwrite=True)
  assert result.source == "native"              # passes
  assert result.last_modified is not None       # FAILS — is None
  ```

- [ ] **BUG-169 — `MemoryBackend.write` omits `last_modified` from `WriteResult` under `WRITE_RESULT_NATIVE`** (MEDIUM)
  `_memory.py:148-152`: backend declares `WRITE_RESULT_NATIVE` but returns
  `WriteResult(source="native", last_modified=None, ...)`. The `mtime`
  stored on the in-memory node (`datetime.now(timezone.utc)`) is available
  but not surfaced. Same quality gap as BUG-170 — WR-004's textual invariant
  (`source == "native"`) is satisfied, but the rich-field obligation from
  the formal-coverage clause is not.
  **Repro:**
  ```python
  backend = MemoryBackend()
  result = backend.write("a.txt", b"hi", overwrite=True)
  assert result.source == "native"              # passes
  assert result.last_modified is not None       # FAILS — is None
  ```

---

## Backlog (Prioritized)

*(none)*

---

## Ideas

### Streaming & Memory Optimization

- [ ] **ID-140 — SQLBlob lazy reads for SQLite & PostgreSQL**
  The current blanket claim that `SQLBlobBackend` cannot do lazy reads is too
  strong (see spec 040 SQL-BLOB-020, `_sqlalchemy.py:47` excluding
  `Capability.LAZY_READ`). Both primary dialects have a path to honest
  `LAZY_READ`; MySQL does not. This item captures the direction — **no
  implementation yet**.

  **SQLite (Py 3.11+):** `sqlite3.Connection.blobopen(table, col, rowid)`
  returns a seekable, chunked `Blob` handle. Reachable through SQLAlchemy via
  `sa_conn.connection.driver_connection`. Requires a `SELECT rowid FROM t
  WHERE key = :key` lookup first, and only works when the user-supplied table
  has an implicit rowid (i.e. not `WITHOUT ROWID`). Genuine streaming.

  **PostgreSQL (`bytea`, our current schema):** no native blob handle API.
  Pseudo-stream via repeated `SELECT substring(data FROM :off FOR :len) FROM
  t WHERE key = :k`. Client memory stays bounded (satisfies LAZY_READ
  semantics per spec 006 line 70-73), but each chunk is a round trip, and on
  compressed TOAST (`EXTENDED`, the default) the server must decompress per
  call. `ALTER COLUMN data SET STORAGE EXTERNAL` makes substring cheap at
  the cost of disk space — caller-controlled tradeoff.

  **PostgreSQL Large Objects (`lo_*`):** genuine streaming via
  `psycopg.connection.lobject()`, but requires an `oid` column and manual
  lifecycle (`lo_unlink` on delete/overwrite/move, otherwise we leak).
  Different storage model — belongs in a separate backend variant
  (e.g. `sql-largeobject`), not a retrofit to `SQLBlobBackend`.

  **MySQL:** no streaming story. Same `SUBSTRING()` pseudo-stream is
  possible but out of scope here (not a primary target).

  **Constraints & gotchas:**
  - `requires-python = ">=3.10"` (`pyproject.toml:11`) stays. SQLite
    `blobopen` is 3.11+ → runtime check, fall back to current eager path on
    3.10.
  - Capability becomes **per-instance, dialect-conditional** — new pattern
    in this codebase; no other backend varies capabilities at runtime.
    Consider whether `Capability` set should be computed in `__init__` and
    cached, and how `store.supports()` interacts with it.
  - Connection lifetime: streaming handle must keep the DBAPI connection
    checked out until the returned `BinaryIO.close()`. Needs a wrapper that
    owns both.
  - Custom tables (`create_table=False`): rowid may not exist; substring
    path is schema-agnostic and works as a universal fallback.

  **Ripple checks when picked up** (per `sdd/CLAUDE-REFERENCE.md`):
  - Spec 040 SQL-BLOB-003 (capabilities list) and SQL-BLOB-020 (`read()`).
  - Spec 006 streaming-io — capability semantics already fit.
  - `FEATURES.md` capability matrix.
  - `tests/test_backend_sqlblob.py:131` asserts LAZY_READ is NOT declared —
    must split into dialect-conditional assertions.
  - Behavioral test: large blob (e.g. 50 MiB) read in 4 KiB chunks with
    bounded RSS.
  - CHANGELOG, this file.

  **Open decisions for whoever picks this up:**
  1. SQLite-only first, or SQLite + PG `bytea` substring together?
  2. Declare `LAZY_READ` for PG substring path given the per-chunk
     round-trip cost, or reserve LAZY_READ for "true" lazy and add a
     separate `CHUNKED_READ` quality flag?
  3. PG Large Objects as a follow-up backend — separate idea, own ID.

  Related: ID-136 (non-lazy **write** is by-design; this item is about
  **reads** only — writes remain eager).

### Testing & Verification

- [ ] **ID-153 — Consolidate moto / Azurite fixtures at `tests/conftest.py`**
  `tests/test_pbt_write_result.py::_moto_endpoint` spins up a second
  `ThreadedMotoServer` alongside the session-scope `moto_server` in
  `tests/backends/conftest.py` because conftest scope does not cross the
  `tests/` vs `tests/backends/` boundary. Promote `moto_server`, `_free_port`,
  and `_AZURITE_CONN_STR` to `tests/conftest.py` so both test trees share one
  server. Non-blocking — flagged in PR #478 review.

- [ ] **ID-152 — Dafny `last_modified` spec-opacity follow-up (unblocks oracle xfail)**
  `MemoryBackend.dfy:Write` currently hardcodes `Option_None()` for
  `last_modified` in the returned `WriteResult` — a deliberate opacity choice
  (`// last_modified: opaque`).  This means the `dafny-oracle` branch of the
  `test_native_populates_last_modified` xfail carries `strict=False` and will
  never self-flip when BUG-169 (`_memory.py`) is fixed.

  When BUG-169 is resolved, also:
  1. Update `BackendContract.dfy` / `MemoryBackend.dfy` to populate
     `last_modified` in the `WriteResult` under `CapWriteResultNative`
     (e.g. by threading a timestamp through `EnsureParents` or by using
     a spec-level ghost value).
  2. Regenerate `MemoryBackend-py/module_.py` via `scripts/dafny_translate.sh`.
  3. Drop the `"dafny-oracle"` entry from `_LAST_MODIFIED_XFAIL` in
     `tests/backends/test_conformance.py`.

  **Exit criteria:** `test_native_populates_last_modified[dafny-oracle-*]`
  passes without xfail.  `bash scripts/dafny_verify.sh` still green.

  Related: BUG-169, ID-151 (done).

- [ ] **ID-150 — Revisit informational `verify-tla` CI status (2026-10-19)**
  First revisit ticket for the informational `verify-tla` job landed under
  ID-147 on 2026-04-19. Per `sdd/formal/README.md` § Authoring rules (3),
  the status is revisited every 6 months or every 10 spec amendments touching
  TLA-backed sections (whichever first). At the revisit, record one of:
  **promote** (check caught a real regression — add to the gate's `needs`),
  **remove** (no catches, no active modules — drop the job), or **re-defer**
  (still useful but no catch yet — open the next revisit ticket). A calendar
  without a ticket is the same as no calendar, which is why this item exists.

  **Exit criteria:** decision logged in the ticket's close note; if re-deferred,
  the successor ticket is linked here; if promoted, `verify-tla` joins the
  `gate.needs` list in `.github/workflows/ci.yml` and the caveat in
  `sdd/formal/README.md` is updated.

- [ ] **ID-147 — TLA+ augmentation: Observer dispatch module + informational CI**
  Follow-up to the ID-147b PoC (WriteResult) and the formal-layer principles
  landed in PR 458. Picks one concrete target that satisfies the "demonstrated
  bundling" authoring rule in `sdd/formal/README.md`, and turns the principle
  from doc-only into enforcement by adding an informational TLC check to CI.

  **Scope (rescoped 2026-04-19):** The earlier draft proposed three modules
  (`Backend.tla`, `Store.tla`, `Observer.tla`) with abstract-layer targets.
  The authoring rules landed in PR 458 now flag "capability gate ordering in
  the abstract" as *not* a valid target — formal artefacts must target
  demonstrated bundling, not speculative layer properties. `Backend.tla` and
  `Store.tla` are dropped; `Observer.tla` remains because OBS-003 demonstrably
  bundles multiple independently-falsifiable claims (see decomposition note
  below).

  **Deliverable 1 — `Observer.tla`** (under `sdd/formal/tla/`, the live
  informal TLA+ layer — physical location is decoupled from CI gate
  status, see `sdd/formal/README.md` rules 3 and 4):
  - Shadows spec 019 § OBS-003 + OBS-003a + OBS-009.
  - Six independent invariants (`EventPerCompletedOp`, `RoutingByOpClass`,
    `ClassHookOutcomeIndependent`, `ErrorHookFiresOnErrorOnly`,
    `ErrorAlwaysReraise`, `AfterHookExceptionIsolated`). The shortlist grew
    from five to six under break-and-catch: the original `HookOutcomeContract`
    bundled two independently-falsifiable claims and was split into I3a / I3b.
  - Full break-and-catch matrix (one mutation per invariant, each triggering
    exactly the target invariant and no others) — if rows collapse, the
    invariants were not orthogonal and the decomposition needs another pass.
  - Scoping rationale + invariant derivation:
    [`sdd/research/research-id-147-obs003-decomposition.md`](research/research-id-147-obs003-decomposition.md).

  **Deliverable 2 — informational `verify-tla` CI job:**
  - Mirrors `verify-formal` (Dafny) pattern in `.github/workflows/ci.yml`.
  - Triggers on `sdd/formal/tla/**` changes (the live informal TLA+ layer).
  - Informational (non-blocking) per the authoring rules until a real
    regression catch promotes it to blocking.
  - Same PR opens the first 6-month revisit BACKLOG ticket (per the authoring
    rules: "a calendar without a ticket is the same as no calendar").

  **Explicitly deferred to follow-up items (if justified):**
  - `Backend.tla` / `Store.tla`: only if a concrete bundled target appears.
  - OBS-005 around-semantics: separate module if invariants prove useful.
  - OBS-015 / WR-019 proxy forwarding: already modelled by the PoC's
    `WR018ProxyForwarding.tla`; do not duplicate.

  **Workflow note:** The hand-decomposition (~30 min) surfaced a latent OBS-003
  step 6 drift before any TLA+ was written. Decomposition belongs *before*
  mechanical translation (Specula or hand-authoring). See the decomposition
  note § 2 and § 7.

  **Relation to existing formal layer:** additive. Dafny (`sdd/formal/`) stays
  as the per-operation contract and oracle layer. TLA+ sits above it, covering
  protocol composition across layers that Dafny cannot express.

- [ ] **ID-138 — Async streaming integrity e2e test**
  The e2e streaming test only covers sync backends. Add an async variant
  using `AsyncAzureBackend` to verify the block-size defaults work for
  async uploads too. Requires an async `transfer()` equivalent or direct
  `store.write()` loop.
  ID-143 covered the bridged-async case via `AsyncBackendSyncAdapter`
  (sync `transfer()` driving `AsyncAzureBackend` through the bridge — landed).
  The native `AsyncStore.transfer()` variant remains the residual scope
  of this item.

### API Surface Enhancements


- [ ] **ID-123 — Cache key derivation from `ResolutionPlan` (Phase 2)**
  `ext.cache` derives cache keys from `ResolutionPlan` fields instead of
  ad-hoc `(operation, path)` tuples. Only valuable once `CompositeStore`
  (ID-121) exists — single-backend cache keys are already correct.
  - Spec: RES-100 (proposed in [043](specs/043-resolution-plan.md))
  - Depends on: ID-121 (CompositeStore)

### New Backends

- [ ] **ID-127 — OneDrive / SharePoint backend (Microsoft Graph)**
  Unified backend covering OneDrive (personal & business) and SharePoint
  document libraries via the Microsoft Graph REST API. Single `drive_id`
  parameter selects the target drive.
  - Design: [RFC-0010](rfcs/rfc-0010-graph-backend.md),
    [ADR-0021](adrs/0021-graph-sdk-choice.md) (SDK),
    [ADR-0022](adrs/0022-graph-auth-model.md) (auth),
    [ADR-0023](adrs/0023-async-monitor-polling.md) (async polling),
    [ADR-0024](adrs/0024-resource-locked-error.md) (ResourceLocked error).
  - Spec: [044-graph-backend.md](specs/044-graph-backend.md)
    (GR-001..GR-057; RET-015 in [spec 025](specs/025-retry-policy.md);
    ERR-013 in [spec 005](specs/005-error-model.md)).
  - Reference: Azure backend (`_azure.py`) — closest architectural parallel.
  - Spec foundation: ID-141 (ADR-0025), ID-142 (spec 029
    § AsyncBackendSyncAdapter + `tests/aio/_doubles.py`), and ID-143
    (`AsyncBackendSyncAdapter` implementation + integration suite) — all landed.
  - Next: implementation per spec 044.

- [ ] **ID-121 — CompositeStore (research complete)**
  `CompositeStore(Store)` — core Store subclass (not extension) that composes
  multiple stores into one. Deterministic fallthrough resolution for reads, union
  LIST (deduplicated), writes to primary tier only.
  - [Research](research/research-sqlalchemy-backend.md#52-compositestore-id-120)
    (anchor uses historical ID-120 from research doc; now ID-121 after swap)
  - Depends on: unified `resolve()` → `ResolutionPlan` (ID-120); at least two
    working backends to be useful; pairs well with ID-119
  - Next: design as separate spec — backend-agnostic, useful independently

### Integrations

- [~] **ID-018 — conda-forge publishing**
  Recipe, CI validation, release checklist steps all done.
  - Done: [recipe](../packaging/conda-forge/recipe.yaml),
    [conda-recipe workflow](../.github/workflows/conda-recipe.yml),
    staged-recipes PR `conda-forge/staged-recipes#32401` (CI green).
  - Blocked: waiting for conda-forge reviewer approval. When merged: add
    `conda install -c conda-forge remote-store` to README.

- [~] **ID-013b — Async Store API Phase 3: async extensions**
  Remainder of ID-013. Phase 1 (core primitives) and Phase 2 (native async
  backends) shipped — see [BACKLOG-DONE.md](BACKLOG-DONE.md).
  Spec 029 amended with round 2 §2.4 items + Phase 2 AsyncAzureBackend spec.
  Async guide updated with native backend docs.
  - Remaining:
    - Implementation Phase 3: async extensions. Note: Dagster 1.12.21 has no
      `AsyncIOManager`; `UPathIOManager.load_partitions_async` is internal only.
      Blocked until Dagster exposes a public async IO manager interface.

---

## Icebox

Deferred indefinitely — revisit only if demand or circumstances change.

- [ ] **BK-139b — Implement remaining bug prevention measures from research**
  Items 1–3 shipped as BK-139a; items 4, 5, 7 shipped as BK-139b (see
  BACKLOG-DONE.md). Only item 6 remains: `scripts/check_error_handling.py`
  (~80 lines) — an AST script flagging broad exception handlers that silently
  return without checking `errno`. Deferred because BLE rules (item 4) and the
  extended conformance error-fidelity category (item 5) cover the same
  error-swallowing bug class with less maintenance overhead. Reactivate if a
  new error-swallowing bug escapes those nets.
  Related: [research](research/research-bug-prevention-beyond-testing.md).

- [ ] **ID-114 — PyArrow-style bucket path support (research)**
  PyArrow convention: `"bucket/prefix"` embeds bucket in path. Current
  `S3Backend` requires split (`bucket=...`, `path=...`). Research feasibility
  of factory method or native convention for easier PyArrow→remote-store
  migration.
  - Deliverable: RFC only — low commitment, no code change guaranteed

- [ ] **ID-118b — TLS CA bundle for Azure (Phase 2)**
  Extend `tls_ca_bundle` to `AzureBackend` if demand materializes.
  Primarily benefits Azure Stack Hub / on-premises deployments.
  Wrap `ClientOptions(ca_cert=...)`, check `AZURE_CA_CERTIFICATE_PATH`.
  S3 Phase 1 shipped — see BACKLOG-DONE.md.

- [ ] **ID-105 — AzurePyArrowBackend (C++ Tier 1)**
  Optional upgrade from the Tier 3 range reader shipped in
  [ID-102](BACKLOG-DONE.md#streaming--io). Only worth pursuing if real-Azure
  benchmarks show GIL overhead or missing I/O coalescing matters for target
  workloads. Approach: `pyarrow.fs.AzureFileSystem` (C++, ships with PyArrow)
  following the `S3PyArrowBackend` dual-library pattern.
  [Research § 6](research/research-azure-pyarrow-optimization.md#6-full-tier-1-path-if-needed).
  - Spike: validate auth methods, HNS/non-HNS, `ReadRangeCache` activation.
  - If viable: `AzurePyArrowBackend` — spec, tests, docs.

- [ ] **ID-125 — Update medallion showcase to Dagster v2 resource pattern**
  Replace `dagster_io_manager(store)` calls in `examples/medallion_dagster/`
  with `RemoteStoreIOManager`. Demonstrates the config-driven pattern.

- [ ] **ID-066 — PR preview deployments**
  Deploy PR previews to Cloudflare Pages, Netlify, or GitHub Pages artifacts.
  Inspired by FastAPI's Cloudflare Pages pattern. Infrastructure decision needed.
  [Research](research/research-fastapi-docs.md) P6.

- [ ] **ID-067 — griffe-typingdoc for `Annotated[T, Doc("...")]` docstrings**
  Only relevant if migrating from Google-style docstrings to PEP 727
  `Annotated[T, Doc("...")]`. Not recommended near-term.
  [Research](research/research-fastapi-docs.md) P5.

