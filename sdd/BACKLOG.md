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

*(none)*

---

## Backlog (Prioritized)

- [ ] **BK-156 — Refactor per-backend test files to remove conformance duplication**
  Per-backend test files (`test_s3.py`, `test_s3_pyarrow.py`, `test_sftp.py`,
  `test_azure.py`, etc.) still contain tests that duplicate what the conformance
  and extended-conformance suites already cover (e.g. `plan.kind`, category-1
  operations). These should be deleted and, where specs reference specific test
  files, the spec body updated to point to the conformance test instead.
  Requires a pass over each backend spec to update traceability references.

- [ ] **BK-152 — Single conformance test for WriteResult/FileInfo consistency + fix violating backends**
  The contract "write a file, then fetch its info — shared fields must agree" has no
  single test and the existing partial coverage is gated on `WRITE_RESULT_NATIVE`,
  which lets backends that declare `source="basic"` escape the check even when their
  `get_file_info()` returns richer data than their `write()`.

  **Test change:** add one `test_write_result_rich_fields_match_file_info` gated on
  `WRITE + METADATA` only: after `write()` / `write_atomic()`, assert
  `result.etag == info.etag`, `result.digest == info.digest`, and
  `result.last_modified == info.modified_at` (when `last_modified is not None`).
  The new test should carry a single `_RICH_FIELDS_XFAIL` escape-hatch table,
  consolidating the two separate `_LAST_MODIFIED_XFAIL` and `_DIGEST_XFAIL` tables
  from the removed tests (both empty today, but the wider gate makes temporary lags
  more likely during future backend additions).
  Remove the two tests it supersedes:
  - `test_native_file_info_matches_write_result` (covers `etag`+`last_modified`,
    gated on `WRITE_RESULT_NATIVE`) — strict subset of the new test
  - `test_digest_matches_file_info` (covers `digest`, gated on `WRITE_RESULT_NATIVE`,
    added in PR #482) — strict subset of the new test
  Keep `test_metadata_round_trips_via_get_file_info` (WR-013 round-trip, different
  spec obligation).

  **`Store.head()` note:** `head()` returns `source="sidecar"` by constructing its
  `WriteResult` directly from `get_file_info()`, so `head()` vs `get_file_info()` is
  consistent by construction. However, `head()` is also used to *enrich* a prior
  `write()` result — that enrichment is only unambiguous once write and info agree on
  the fields write populated. Fixing this item closes that ambiguity too; no separate
  item is needed for `head()`.

  **Formal layer:** `BackendContract.dfy:413-416` already encodes WR-001a correctly
  for `WRITE_RESULT_NATIVE` backends; the comment at lines 410-412 explicitly defers
  "absence of rich-field population" to empirical testing. No Dafny amendment is
  needed — once violating backends are fixed to declare `WRITE_RESULT_NATIVE`, the
  existing postcondition binds them automatically.

  **Backends that currently fail this test:**
  - `S3PyArrowBackend` (`_s3_pyarrow.py:243`): `write()` returns `source="basic"` with
    all optional fields `None`, but `get_file_info()` calls
    `head_object(ChecksumMode="ENABLED")` and returns `etag`, `digest`, and
    `modified_at`. Fix: add the same `head_object` call after the PyArrow upload, set
    `source="native"`, declare `WRITE_RESULT_NATIVE`.
  - `LocalBackend` (`_local.py:178`): `write()` already calls `full.stat()` for
    `st_size` and discards `st_mtime`; `get_file_info()` returns that mtime as
    `modified_at`. Fix: reuse the existing `stat()` result for `last_modified`, set
    `source="native"`, declare `WRITE_RESULT_NATIVE`.
  - `SFTPBackend` (`_sftp.py:367`, `418`): `write()` returns `last_modified=None`;
    `get_file_info()` returns `modified_at` from `sftp.stat()`. The write path already
    calls `self._sftp.stat()` pre-write at `_sftp.py:346` (for the AlreadyExists
    check). Fix: add a second `sftp.stat()` call *after* the upload — one new
    post-write round-trip on top of the existing pre-write one — then populate
    `last_modified` and declare `WRITE_RESULT_NATIVE`.
  - `SQLAlchemyBackend` (`_sqlalchemy.py:439-450`): `write()` gates `last_modified` on
    `user_metadata` column presence; `get_file_info()` always reads `modified_at` from
    the row when the `modified_at` column exists. Fix: decouple the `last_modified`
    gate from the `user_metadata` check — set it whenever `modified_at` is in
    `self._optional_columns`, regardless of `user_metadata`.

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

