# Development Backlog
<!-- doc: repo-only -->

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

- [ ] **BUG-197 — `read_bytes` and `delete` silently mishandle HNS directory paths (sync + async)**
  BE-021 requires file-API operations on a directory path to raise `InvalidPath`.
  `write`/`write_atomic`/`open_atomic` enforce this via the `hdi_isfolder` probe
  (BUG-190/BUG-192). `read_bytes` and `delete` do not — neither path probes for the
  directory marker before invoking the SDK. Confirmed live on a real ADLS Gen2 account:
  - `AzureBackend.read_bytes(hns_dir)` and `AsyncAzureBackend.read_bytes(hns_dir)`:
    silently return `b""` (0 bytes) instead of raising `InvalidPath`.
  - `AzureBackend.delete(hns_dir)` and `AsyncAzureBackend.delete(hns_dir)`:
    silently delete the directory marker, leaving `exists()` returning `False`.
    **This is a data-loss defect**: calling the file-API `delete()` on what the
    caller believed was a file but is actually a directory destroys the directory
    silently. Stronger consequence than BUG-190/BUG-192 (which just chose the wrong
    error class) — this one mutates account state.
  Live tests freeze the actual behaviour in `tests/backends/test_azure_live_hns.py::
  TestAzureLiveHnsFileApiOnDirectory` and the async sibling; they must be flipped
  back to assert `InvalidPath` once the fix lands. Fix: extend the existing
  `hdi_isfolder` probe pattern from `write_atomic`/`open_atomic` to `read`,
  `read_bytes`, `read_seekable`, and `delete` on both sync and async backends.
  Spec: BE-021, BE-013, BE-014, ASYNC-013.

- [ ] **BUG-196 — Async `write_atomic` HNS path lacks BUG-173 try/except fallback around `get_file_properties()`**
  `src/remote_store/aio/backends/_azure.py:578` calls `await final_fc.get_file_properties()`
  *after* the rename has committed but does not wrap it in try/except. The sync sibling at
  `src/remote_store/backends/_azure.py:484-503` (BUG-173) deliberately catches an `Exception`,
  logs a warning, and returns `WriteResult(etag=None, last_modified=None)` — the rename
  already succeeded, so a transient post-rename read failure must not surface as a write
  failure. WR-001a lists both fields as `Optional`. Surfaced by the new
  `tests/aio/test_async_azure_live_hns.py::TestAsyncLiveHnsWriteResult` assertion
  `result.etag is not None` (only path the async backend supports today). Fix: mirror the
  sync try/except + log + `_build_azure_write_result(path, size, None, metadata)` shape, then
  weaken the live-test assertion to allow the fallback path. Spec: WR-001a, WR-004, AZ-034.

- [ ] **BUG-195 — `get_file_info` on an HNS directory raises `NotFound` instead of `InvalidPath` (sync + async)**
  BE-016 specifies "`InvalidPath` if the path names a directory (Dafny:
  `GetFileInfo: IsDir → InvalidPath`)" and ASYNC-016 inherits the same contract. Both
  `AzureBackend.get_file_info` and `AsyncAzureBackend.get_file_info` currently raise
  `NotFound` when the target is an HNS directory blob (marker `hdi_isfolder=true`). New live
  tests `tests/backends/test_azure_live_hns.py::TestAzureLiveHnsGetFileInfoOnDirectory` and
  `tests/aio/test_async_azure_live_hns.py::TestAsyncLiveHnsGetFileInfoOnDirectory` confirm
  the runtime behaviour and document the deviation. Same defect shape as BUG-190 (write on
  HNS directory) and BUG-192 (open_atomic on HNS directory): the `hdi_isfolder` probe is
  missing. Fix: detect `hdi_isfolder` in the `get_file_info` HNS branch and raise
  `InvalidPath`; update both live tests to assert `InvalidPath`. Spec: BE-016, ASYNC-016,
  BE-021.

---

## Backlog (Prioritized)

- [ ] **BK-175 — Live HNS test architecture: parametrized conformance + record/replay layer**
  The hand-written `test_azure_live_hns.py` / `test_async_azure_live_hns.py` suites
  drifted into ~40% overlap with the conformance suite running against Azurite
  (`tests/backends/conftest.py` `azure` parametrize). The HNS suite hand-rolls
  contracts (NotFound family, copy/delete happy paths, exists True/False on files,
  move-existing-dst guards) where the production code has no `_ensure_hns()` branch
  — exercising the same lines as conformance, just on a different account. Going
  forward this duplication will grow with every new contract added to conformance.

  **Goal:** eliminate the duplication systematically and let conformance be the
  single source of truth for cross-backend behavioural contracts; live HNS files
  shrink to *only* HNS-unique tests (DataLake DFS protocol, `hdi_isfolder` directory
  semantics, etag normalisation across SDK paths, BUG-194/195/197 deviation guards).

  **Two pieces to design:**

  1. **Live conformance parametrize.** Add an `azure-live-hns` (and async equivalent)
     option to `tests/backends/conftest.py` that instantiates `AzureBackend` /
     `AsyncAzureBackend` against a real ADLS Gen2 connection string instead of
     Azurite. Gated by the existing `live` marker + `RS_TEST_LIVE_HNS=1` so default
     CI is unaffected. The full conformance + conformance-extended suite then runs
     against the real HNS account automatically — every future contract addition
     gets HNS coverage for free. Cost: ~140 conformance tests × HNS = ~5–10× current
     live transactions, still under $0.05/run.

  2. **Record/replay abstraction layer.** Wrap the SDK transport so
     live tests record real request/response pairs to YAML cassettes; replay mode
     reads from cassettes when no credentials are present. Implementation candidates:
     `pytest-recording` (vcrpy) for the HTTP layer, or a custom transport adapter
     in front of the Azure SDK pipeline policies. Per-test cassette files committed
     under `tests/cassettes/hns/`. Lets contributors run the full HNS conformance
     suite offline without credentials; CI runs in replay mode by default.

     Open design questions:
     - Cassette scrubbing for SAS tokens, account keys, request IDs.
     - Cassette invalidation policy when SDK request shapes change.
     - Whether to record per-test (simple, larger storage) or per-fixture (compact,
       harder to debug single-test failures).
     - Async-pipeline coverage — vcrpy supports it but needs validation against
       `azure.storage.filedatalake.aio`.

  **What stays as hand-written live tests:**
  - HNS-unique paths conformance can't reach: AsyncIterator DFS protocol (BUG-194
    regression guard), etag normalisation cross-check (`get_file_properties` vs
    `get_file_info` agreement), directory-blob `hdi_isfolder` probes.
  - Active deviation guards (BUG-195, BUG-197) until the underlying code is fixed.

  **Approach should not be designed in this PR** (PR #590, "improve HNS live tests")
  — that PR's scope was to extend coverage, and it succeeded (32 → 58 tests, surfaced
  BUG-194 / BUG-195 / BUG-196 / BUG-197). This BK is the follow-up to consolidate
  the architecture before the suite grows further.

  **Exit criteria:** RFC for the parametrize + cassette design; conformance runs
  against real HNS in a gated CI job; `tests/(aio/)test_azure_live_hns.py` shrinks
  to HNS-unique cases only; recording/replay procedure documented in
  `CONTRIBUTING.md` § Live tests.

- [ ] **BK-174 — `AsyncMemoryBackend` metadata round-tripping parity with sync `MemoryBackend`**
  `AsyncMemoryBackend.get_file_info` returns
  `FileInfo(... content_type=node.content_type)` without
  `metadata=node.metadata`, while sync `MemoryBackend.get_file_info`
  (`src/remote_store/backends/_memory.py:331`) passes it through. The same
  asymmetry exists at the other `FileInfo`-constructing sites in
  `src/remote_store/aio/backends/_memory.py`: `list_files` non-recursive
  (~L374), `iter_children` (~L427), `_collect_files_from_snapshot` (~L769).
  Out-of-scope from BUG-189 (which targeted error fidelity only). Add
  `metadata=node.metadata` to all four sites and a parametrized regression
  test that round-trips `metadata={"k": "v"}` through `write` →
  `get_file_info` and through `write` → `list_files` for the native async
  backend. Spec: ASYNC-016 § metadata round-trip.

- [ ] **BK-173 — Parametrize self-op tests + tighten `match=` regexes in `tests/backends/test_conformance_extended.py`**
  Two TESTING.md alignments to apply on the sync extended-conformance suite,
  mirroring fixes that landed in the async mirror via PR #580:
  1. **Parametrize `TestMoveCopySelfOperation`.** The sync class has five
     near-duplicate methods that differ only in `op ∈ {move, copy}` and
     `overwrite ∈ {True, False}` — a TESTING.md Rule 7 violation. The async
     side was parametrized over `(op, cap)` × `overwrite`, collapsing five
     tests into two and adding the previously-missing self-move-missing-NotFound
     case. Apply the same shape on the sync side.
  2. **Tighten `match=` in `test_destination_is_directory_raises_error`.** The
     current `match=f"mcdd/{op}"` matches both src and dst fragments because
     they share the prefix; pin to `match=f"mcdd/{op}_dstdir"` so a regression
     that flipped the error from dst to src would not silently pass. The
     async mirror was tightened in PR #580.
  No spec change; marker tags (`BE-018`, `BE-019`, the BE counterpart of
  `ASYNC-047`) stay on the parametrized methods. Verify behavior unchanged
  via `hatch run pytest tests/backends/test_conformance_extended.py -k SelfOperation`.

---

## Ideas

### Docs & Tooling

- [ ] **ID-173 — `check_api_docs.py` — `__all__` ↔ `docs-src/reference/api/index.md`**
  Spun off from ID-171 (Backend sub-task done, see BACKLOG-DONE.md).
  Different IR from the method-caps checker: `{symbol_name: kind}` rather
  than `{method: caps}`; separate extractor pair, same compare pattern.
  Sources of truth: `remote_store.__all__` (primary public API) and
  `remote_store.backends.__all__` (secondary; e.g. `SFTPUtils`). Page side:
  parse `[Name](page.md)` link rows in the existing tables under `## Core`,
  `## Backends`, etc. Compare = set diff with missing/extra symbol messages.
  Stop and confirm before implementing — this is a genuinely different IR
  (per the Phase 1 reviewers' staged-rollout preference).
  Page target: `docs-src/reference/api/index.md`.

- [ ] **ID-172 — `check_api_docs.py` — `AsyncStore`/`AsyncBackend` ↔ `docs-src/reference/api/aio.md`**
  Spun off from ID-171 (Backend sub-task done, see BACKLOG-DONE.md).
  Blocked on aio rework: the `aio.md` page and `AsyncStore`/`AsyncBackend`
  classes need rework before the verifier can be wired in meaningfully.
  Wire up after that rework lands: add `_ASYNC_STORE_GATING` (or equivalent)
  to `_async_store.py`, extend gen_graph.py for async gates, add both
  classes to `PAGES` pointing at `aio.md`.
  Griffe traversal path (for the implementer):
  `pkg.members["aio"].members["_async_store"].members["AsyncStore"]`

- [ ] **ID-161 — Publish `llms.txt` to the docs site**
  Add a machine-readable discovery file at `docs-src/llms.txt` (served as
  `https://docs.remotestore.dev/llms.txt`) per the
  [llmstxt.org](https://llmstxt.org/) open standard. The file gives LLM
  tools a single, stable entry point — a curated H1 title, a one-paragraph
  summary, and a short link list — without relying on any specific platform.

  **Format** (llmstxt.org §2):
  ```
  # remote-store

  > Unified file-storage API for Python — one `Store` interface across
  > Local, S3, SFTP, Azure, SQL, and more.

  ## Docs
  - [Getting started](https://docs.remotestore.dev/getting-started/)
  - [Backends & capabilities](https://docs.remotestore.dev/reference/capabilities-matrix/)
  - [API reference](https://docs.remotestore.dev/api/)
  - [Migration guide](https://docs.remotestore.dev/reference/migration/)
  - [FEATURES (authoritative)](https://github.com/haalfi/remote-store/blob/master/FEATURES.md)

  ## Source
  - [GitHub](https://github.com/haalfi/remote-store)
  - [PyPI](https://pypi.org/project/remote-store/)
  ```

  **Why this adds value over `context7.json`:** `context7.json`
  targets one proprietary index; `llms.txt` is an open, client-agnostic
  standard. Tools that resolve `/llms.txt` at a domain root (e.g. Cursor,
  OpenAI's URL tools, or any future LLM IDE plugin) will discover the file
  without prior registration.

  **MkDocs note:** `docs_dir: docs-src` is set in `mkdocs.yml`. MkDocs
  copies non-Markdown files verbatim, so `docs-src/llms.txt` will appear
  at the site root automatically. No plugin or hook needed.

  **Maintenance:** the link list should be reviewed when major new guides
  land, not on every release. The file has no version number — it describes
  the current stable docs, not a specific release.

  **Optional follow-on (not in scope here):** `llms-full.txt` —
  concatenated full prose of all guides, for tools that prefer a single
  large context file. Worth a separate ID if demand appears.

  **Sequence — start after all of:**
  - ID-174 (docs reorg): final source URLs must be stable before the link list is written.
  - ID-172 + ID-173 (aio verifiers): `aio.md` and `index.md` must accurately
    reflect the async API before they are linked as authoritative reference.
  - aio.md rework (memory): `aio.md` structural rework must land before ID-172 can close.
  - Async conformance test (memory): async extended conformance pattern must be
    designed and implemented before the aio API surface is considered settled.

  **Exit criteria:** `docs-src/llms.txt` committed; `GET
  https://docs.remotestore.dev/llms.txt` returns the file after next deploy.


- [~] **ID-018 — conda-forge publishing**
  Recipe, CI validation, release checklist steps all done.
  - Done: [recipe](../packaging/conda-forge/recipe.yaml),
    [conda-recipe workflow](../.github/workflows/conda-recipe.yml),
    staged-recipes PR `conda-forge/staged-recipes#32401` (CI green).
  - Blocked: waiting for conda-forge reviewer approval. When merged: add
    `conda install -c conda-forge remote-store` to README.

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
  - `tests/backends/test_sqlblob.py:131` asserts LAZY_READ is NOT declared —
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

