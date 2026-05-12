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
| `BL-NNN` | Release blocker — must resolve before next PyPI publish. Monotonic, not reset per release. |
| `BK-NNN` | Committed backlog work, queued behind blockers. |
| `BUG-NNN` | Confirmed defect with reproduction steps. |
| `ID-NNN` | Idea — not evaluated, not committed to. |
| `AF-NNN` | Audit finding (retired — use `BUG` or `BK` for new items). |

**Assigning a new ID:** check `sdd/backlogid.json` (max per prefix from BACKLOG-DONE.md)
and the highest ID already in this file, then take the next integer. Run
`hatch run gen-backlogid` after moving items to BACKLOG-DONE.md to keep the JSON current.
`hatch run lint` flags drift and collisions.

---

## Release Blockers

*(none)*

---

## Bugs

- [ ] **BUG-203 — `AzureBackend.is_file()` returns `True` for HNS folder paths**
  Sync `AzureBackend.is_file('a.txt')` returns `True` when `a.txt` exists as
  an HNS directory blob (marker `hdi_isfolder=true`). Conformance contract
  requires `is_file()` to return `False` whenever the path is a directory,
  symmetric to `is_folder()` returning `False` on a file. Surfaced by the
  BK-180 conformance run against real ADLS Gen2:
  `tests/backends/conformance/test_io.py::TestBackendFileFolder::test_is_file[azure_live]`.
  Azurite-backed `azurite` fixture passes the same test because Azurite
  does not emulate HNS. Fix: extend the `hdi_isfolder` probe used by
  `write`/`write_atomic`/`open_atomic` to the `is_file` HNS branch in
  `src/remote_store/backends/_azure.py`. Async sibling apparently
  unaffected (no `[azure_live_async]` failure for this test). Spec:
  BE-005 (or whichever spec covers `is_file` semantics), BE-021.

- [ ] **BUG-202 — `AzureBackend.write_atomic` streaming-input path raises `MissingRequiredQueryParameter` on real HNS**
  Sync `AzureBackend.write_atomic` with a `BinaryIO` (streaming) input
  succeeds against Azurite but fails against a real HNS account with the
  Azure SDK error `MissingRequiredQueryParameter`. Surfaced by
  `tests/backends/conformance/test_atomic.py::TestWriteResultConformance::test_size_matches_written_bytes_for_streaming_input[azure_live]`.
  The bytes-input variant of the same test is green, so the defect is on
  the streaming code path (`src/remote_store/backends/_azure.py:~1027`).
  Likely a missing query parameter on the DataLake SDK call that real
  HNS validates and Azurite forgives. Async variant not exercised in
  this sweep (different test class). Fix: identify the SDK call,
  add the missing parameter, regression-cover with the conformance
  test once green. Spec: BE-010, WR-001a.

- [ ] **BUG-201 — `AsyncAzureBackend.move`/`copy` self-op (src == dst) raises `AlreadyExists` instead of being a no-op**
  Conformance contract for `move(p, p)` and `copy(p, p)` is to be a
  no-op (data preserved, no error). `AsyncAzureBackend` raises
  `AlreadyExists` instead. Surfaced by
  `tests/backends/conformance/test_async_extended.py::TestMoveCopySelfOperation::test_self_op_preserves_data[azure_live_async-overwrite-move]`,
  `[azure_live_async-no-overwrite-move]`, and `[azure_live_async-no-overwrite-copy]`.
  Errors fire at `src/remote_store/aio/backends/_azure.py:899` (copy
  destination check) and `:1068` (rename SDK call). Sync variant green
  in this sweep — the gap is async-only. Fix: detect src == dst at the
  top of `move`/`copy` and short-circuit. The conformance test is
  currently behind `_NO_SELF_OP_BACKENDS` in `test_async_extended.py`
  with key `"async-azure"`; the fix must also remove that key so the
  regression test runs against `azure_live_async`. Spec: BE-018, BE-019,
  ASYNC-018, ASYNC-019.

- [ ] **BUG-200 — `AsyncAzureBackend.move`/`copy` directory checks raise wrong error / `InvalidInput` on real HNS**
  Conformance contract: `move`/`copy` with a directory source or
  directory destination raises `InvalidPath`. `AsyncAzureBackend`
  instead raises `RemoteStoreError(InvalidInput)` (when source is a
  directory) or `AlreadyExists` (when destination is a directory).
  Surfaced by
  `tests/backends/conformance/test_async_extended.py::TestMoveCopyErrorFidelity::test_source_is_directory_raises_error[azure_live_async-move]`,
  `[azure_live_async-copy]`,
  `test_destination_is_directory_raises_error[azure_live_async-move]`,
  and `[azure_live_async-copy]`. Errors at
  `src/remote_store/aio/backends/_azure.py:899/937/1068`. Same defect
  family as BUG-195/BUG-197/BUG-190: missing `hdi_isfolder` probe before
  the SDK call. **Sync variant now exercised:** BK-186 PR 1 lifted the
  identity-based gate — `_skip_flat_namespace` now reads the per-fixture
  `flat_namespace` flag (false for `azure_live` HNS), so the sync siblings
  in `test_errors.py::TestMoveCopyErrorFidelity` no longer silent-skip on
  Stage 3. Re-verify the sync side on the next Stage 3 run; the same fix
  shape likely applies. Fix: add the directory probe to the async
  `move`/`copy` paths.
  Spec: BE-018, BE-019, BE-021, ASYNC-018, ASYNC-019, ASYNC-024.

- [ ] **BUG-199 — `AzureBackend.get_folder_info` recursive `file_count` includes HNS directory blobs as files (sync + async)**
  `FolderInfo.file_count` returned by `get_folder_info(path, recursive=True)`
  reports `3` where conformance expects `2`. The extra "file" is an HNS
  directory blob (marker `hdi_isfolder=true`) that the recursive walk
  fails to filter out. Surfaced by three live conformance tests:
  `tests/backends/conformance/test_async_extended.py::TestGetFolderInfoAggregates::test_get_folder_info_counts_recursive_children[azure_live_async]`,
  `tests/backends/conformance/test_metadata.py::TestGetFolderInfoAggregates::test_get_folder_info_counts_recursive_children[azure_live]`,
  and `tests/backends/conformance/test_metadata.py::TestBackendMetadata::test_get_folder_info_excludes_subdirs[azure_live]`.
  Both sync and async hit it, so the miscount lives in the shared
  recursive-walk logic (or in the per-iteration filter) used by both
  backends. Fix: filter `hdi_isfolder=true` entries from the recursive
  file aggregation in `get_folder_info`. Spec: BE-017, ASYNC-017.

- [ ] **BUG-198 — Folder-API on a file path raises wrong error type on `AsyncAzureBackend` (HNS)**
  Symmetric to BUG-197/BUG-195: `delete_folder` and `get_folder_info`
  on a *file* path should raise `InvalidPath`, but `AsyncAzureBackend`
  raises `DirectoryNotEmpty` (delete_folder) and `NotFound`
  (get_folder_info) instead. Surfaced by
  `tests/backends/conformance/test_async_extended.py::TestDeleteFolderErrorFidelity::test_delete_folder_on_file_raises_error[azure_live_async]`,
  `test_delete_folder_on_file_missing_ok_still_raises[azure_live_async]`,
  and `tests/backends/conformance/test_async_extended.py::TestGetFolderInfoErrorFidelity::test_get_folder_info_on_file_raises_error[azure_live_async]`.
  Errors at `src/remote_store/aio/backends/_azure.py:640` (delete_folder)
  and `:829` (get_folder_info). **Sync variant now exercised:** BK-186
  PR 1 lifted the identity-based gate — `_skip_flat_namespace` now reads
  the per-fixture `flat_namespace` flag (false for `azure_live` HNS), so
  the sync siblings in `test_errors.py::TestDeleteFolderErrorFidelity`
  and `TestGetFolderInfoErrorFidelity` no longer silent-skip on Stage 3.
  Re-verify the sync side on the next Stage 3 run; the same defect likely
  surfaces.
  Same fix shape as BUG-195/BUG-197: detect the type mismatch before
  the SDK call and raise `InvalidPath`.
  Spec: BE-014, BE-017, BE-021, ASYNC-013, ASYNC-017.

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
  Live tests freeze the actual behaviour in `tests/backends/azure/test_live_hns.py::
  TestAzureLiveHnsFileApiOnDirectory` and the async sibling at
  `tests/backends/azure/aio/test_live_hns.py`; they must be flipped
  back to assert `InvalidPath` once the fix lands. The BK-180 conformance run
  against `azure_live_async` reproduces the async halves at
  `tests/backends/conformance/test_async_extended.py::TestReadErrorFidelity::test_read_on_directory_raises_error`,
  `test_read_bytes_on_directory_raises_error`,
  `TestDeleteErrorFidelity::test_delete_on_directory_raises_invalid_path`, and
  `test_delete_on_directory_missing_ok_still_raises`. Fix: extend the existing
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
  `tests/backends/azure/aio/test_live_hns.py::TestAsyncLiveHnsWriteResult` assertion
  `result.etag is not None` (only path the async backend supports today). Fix: mirror the
  sync try/except + log + `_build_azure_write_result(path, size, None, metadata)` shape, then
  weaken the live-test assertion to allow the fallback path. Spec: WR-001a, WR-004, AZ-034.

- [ ] **BUG-195 — `get_file_info` on an HNS directory raises `NotFound` instead of `InvalidPath` (sync + async)**
  BE-016 specifies "`InvalidPath` if the path names a directory (Dafny:
  `GetFileInfo: IsDir → InvalidPath`)" and ASYNC-016 inherits the same contract. Both
  `AzureBackend.get_file_info` and `AsyncAzureBackend.get_file_info` currently raise
  `NotFound` when the target is an HNS directory blob (marker `hdi_isfolder=true`). New live
  tests `tests/backends/azure/test_live_hns.py::TestAzureLiveHnsGetFileInfoOnDirectory` and
  `tests/backends/azure/aio/test_live_hns.py::TestAsyncLiveHnsGetFileInfoOnDirectory` confirm
  the runtime behaviour and document the deviation. The BK-180 conformance run against
  `azure_live_async` reproduces the async half at
  `tests/backends/conformance/test_async_extended.py::TestGetFileInfoErrorFidelity::test_get_file_info_on_directory_raises_error`.
  Same defect shape as BUG-190 (write on HNS directory) and BUG-192 (open_atomic on HNS
  directory): the `hdi_isfolder` probe is missing. Fix: detect `hdi_isfolder` in the
  `get_file_info` HNS branch and raise `InvalidPath`; update both live tests to assert
  `InvalidPath`. Spec: BE-016, ASYNC-016, BE-021.

---

## Backlog (Prioritized)

- [ ] **BK-204 — SFTP-007 host-key resolution chain: config / env tiers uncovered**
  `_resolve_host_keys` in `src/remote_store/backends/_sftp.py` documents a
  four-tier precedence (direct param > `config["known_host_keys"]` >
  `SFTP_KNOWN_HOST_KEYS` env > on-disk `host_keys_path` fallback). BK-201's
  `TestSFTPInlineHostKeysVerification` exercises the "direct" tier end to
  end (load + STRICT verify), but the config-dict and env-var branches
  still carry `# pragma: no cover` at `_sftp.py:1285-1288` — no test ever
  reaches them. The precedence claim (direct > config > env) is also
  untested: today nothing would catch a regression that silently flipped
  the order. Two shapes: (a) targeted unit tests on `_resolve_host_keys`
  parametrised over (direct, config, env) combinations, asserting the
  selected source via behavior (STRICT verifies against the expected key
  using `sftp_server`'s entry, swapped through each tier) or via the
  `_load_host_keys_from_string` boundary; (b) extend
  `TestSFTPInlineHostKeysVerification` with a third pair of tests that
  populate the config dict and env var with the live server's key, drop
  the `direct` parameter, and assert STRICT connect succeeds — then
  remove the two `pragma: no cover` markers. Spec: SFTP-007. Surfaced
  during BK-201 round-2 review (user question: "where is the deleted
  test's logic covered now?"). Audience: `infra.test`.

- [ ] **BK-196 — Dafny formal-spec gap: `Copy` postcondition does not pin metadata**
  `sdd/formal/MemoryBackend.dfy::Copy` builds the destination via
  `BasicFileInfo(dst, dst, srcEntry.info.size)`, which drops user metadata.
  The `Copy` postcondition does not pin metadata, so the model verifies
  cleanly today but encodes the same defect the Python code had before
  BK-192. Two fix shapes: (a) tighten the postcondition to require
  `dstEntry.info.userMetadata == srcEntry.info.userMetadata` and adjust
  `BasicFileInfo` / the constructor to carry it; (b) extend `Copy` to
  thread metadata through explicitly. Surfaced during BK-192 work. Spec:
  WR-013, BE-019, ASYNC-019. Trace: `sdd/traces/bk-192-copy-metadata-parity.yml`.

- [ ] **BK-195 — Conformance test: `copy()` preserves user metadata**
  `tests/backends/conformance/test_atomic.py::TestWriteResultConformance`
  covers `write → get_file_info` metadata round-trip but no test exercises
  `write → copy → get_file_info` metadata for any backend. The gap is why
  BK-192 shipped to master: only memory backends had targeted tests, and
  no cross-backend gate caught the same omission. Add a conformance test
  that runs against every backend declaring `USER_METADATA` capability
  (Local, S3, SFTP via metadata files, Azure, memory, async-memory).
  Surfaced during BK-192 work. Spec: WR-013, BE-019, ASYNC-019.
  Trace: `sdd/traces/bk-192-copy-metadata-parity.yml`.

- [ ] **BK-191 — Audit `_BACKEND_AT_ROOT_GRANDFATHERED` allow-list**
  BK-190 enforces TEST-003 (no concrete cloud / network backend imports at
  `tests/` root) but grandfathers a set of legacy cross-cutting files
  that each import multiple cloud backends to verify cross-protocol
  features (config loaders, depth-limited listing, example demos, PBT
  oracles, ping / health checks, seekable reads, coverage padding). The
  authoritative roster lives in
  `scripts/check_test_placement.py::_BACKEND_AT_ROOT_GRANDFATHERED`. For
  each entry, decide: (a) move backend-specific assertions to
  `tests/backends/<backend>/`, (b) reshape into conformance parametrize
  (`tests/backends/conformance/`), or (c) keep at root and document why.
  Coverage-padding tests are the most obvious candidates for split.
  Each entry removed from the allow-list closes part of this item.
  Spec: TEST-003, TEST-010.

- [ ] **BK-182 — Shrink live HNS suites under `tests/backends/azure/`**
  Originally targeted the now-removed top-level
  `tests/backends/test_azure_live_hns.py` /
  `tests/aio/test_async_azure_live_hns.py` pair; BK-179's reorg moved them
  to `tests/backends/azure/test_live_hns.py` and
  `tests/backends/azure/aio/test_live_hns.py`. BK-180 added live `azure_live`
  / `azure_live_async` conformance fixtures, so most happy-path coverage
  in the moved files is now duplicated against a real ADLS Gen2 account.
  Once BK-181 lands HTTP cassette/replay, delete the duplicated cases and
  keep only HNS-unique tests at the new paths: DFS AsyncIterator protocol
  (BUG-194 regression guard), etag normalisation cross-check
  (`get_file_properties` vs `get_file_info`), directory-blob `hdi_isfolder`
  probes, and any remaining deviation guards. Async equivalents stay under
  `tests/backends/azure/aio/test_live_hns.py` only where sync / async
  behaviour differs. Spec: TEST-002, TEST-003.

- [ ] **BK-181 — Implement Spec 048 Phase 3: HTTP cassette/replay layer**
  Add `<backend>_replay` Stage 1 fixtures for HTTP-transport backends
  (Azure first, S3 follows) per spec [TEST-007](specs/048-testing-architecture.md).
  Choose the recording mechanism (`pytest-recording`/vcrpy or a custom Azure
  pipeline-policy adapter; benchmark against async-pipeline coverage and
  scrubbing complexity). Implement scrubbing for credentials, SAS tokens,
  account keys, and per-run request IDs. Wire `--record` mode for
  `pytest --stage=3 --record` and document the refresh procedure. Cassettes
  live under `tests/backends/cassettes/<backend>/`. Missing cassette ⇒ replay-fixture
  skip (TEST-007). Sequencing: depends on BK-179 (registry) and
  BK-180 (live fixtures the recording mode runs against). Spec: TEST-007,
  TEST-008, TEST-009.

- [ ] **BK-177 — Parametrize self-op tests + tighten `match=` regexes in `tests/backends/conformance/test_atomic.py`**
  Two TESTING.md alignments to apply on the sync side of
  `TestMoveCopySelfOperation`, mirroring fixes that landed in the async
  mirror (`tests/backends/conformance/test_async_extended.py`) via PR #580.
  Originally referenced the now-removed
  `tests/backends/test_conformance_extended.py`; BK-179's split moved the
  self-op tests into
  `tests/backends/conformance/test_atomic.py::TestMoveCopySelfOperation`.
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
  via `hatch run pytest tests/backends/conformance/test_atomic.py -k SelfOperation`.

---

## Ideas

### Docs & Tooling

- [ ] **ID-179 — Trace schema validator: wire `audience` field check into `hatch run lint`**
  `sdd/traces/_schema.yml` declares `audience` as `required` but no
  validator runs it. Add `scripts/check_traces.py` that jsonschema-validates
  every `sdd/traces/[!_]*.yml` against the schema. Wire into the existing
  `hatch run lint` script list and into the lint CI job. Per
  `feedback_check_scripts_dual_wire`. Closes the convention-vs-enforcement
  gap left open by BK-193. No priority while trace authoring is still
  ad-hoc; promote to BK-prefix when trace volume justifies enforcement.

- [ ] **ID-180 — Stable HTML-anchor IDs across non-spec docs under `sdd/`**
  Specs already have stable IDs (`ASYNC-016`, `WR-013`); non-spec docs
  (CLAUDE.md "Principles", CLAUDE-REFERENCE row pointers, AUTHORING /
  DOCUMENTATION / CONTENT-RULES rules) do not. Trace `section:` fields
  reference these by heading text, which rots when sections are renamed.
  Add HTML-anchor comments (`<!-- id: ripple-bug-fix -->`) to stable
  reference points in seven `sdd/` framework docs plus `CLAUDE.md`. No
  priority until trace aggregation exists or first heading-text drift
  breaks a trace reference; promote to BK-prefix at that point.

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

- [ ] **ID-182 — Scheduled CI drift guard for unbounded extra-dependency floors**
  Applies library-wide, not to `[sftp]` alone. Every `[<extra>]` in
  `pyproject.toml` declares a floor and (today) no ceiling — `[s3]`,
  `[azure]`, `[sftp]`, `[sql]`, `[arrow]`, etc. A silent transitive
  upgrade on day N+3 can break a working pin set on day N. PR 613
  addressed two such incidents in the same shape: `paramiko` 2.x → 3.x
  (BUG-204, `channel_timeout`) and 4.x → 5.x (BK-198, `ssh-rsa`).
  Without a guard, the next one is just a matter of time. Shape that
  would catch this class of drift before users do: scheduled job
  (weekly), resolve each `remote-store[<extra>]` against
  `pip install --upgrade --pre` with no consumer-side pins, diff
  resolved versions against a committed observed-lock, and for each
  delta run the most-likely-to-break smoke tests against deterministic
  fixtures (the `benchmarks/infra/legacy-sftp` e2e is the model). Open
  an issue on drift; do not auto-merge a pin update — the point is
  early warning, not automated remediation. Audience:
  `library.maintainer`. Surfaced during BK-198 (PR 613) review.

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

### Formal Verification

- [ ] **ID-191 — Move atomicity formal model in `ResourceSafety.dfy`**
  `ResourceSafety.dfy` § 2 models `AtomicMove` and `CopyDeleteMove` as state
  machines and proves `MoveFinalStateEquivalence` (both reach `DeleteDone`).
  What is missing is a contract that conformance tests can enforce: no test
  today verifies that backends declaring `CapAtomicMove` do not expose the
  `CopyDone` intermediate state (source gone, destination not yet written).
  Two parts: (a) extend `ResourceSafety.dfy` to define a `MoveContract`
  datatype that encodes the allowed observable states — either `DeleteDone`
  (success) or `Failed` (rollback, src preserved), never `CopyDone`; (b) add
  a conformance test that simulates a crash between copy and delete (via a
  mock backend that raises on the delete step) and asserts the source path
  is either intact or the destination is intact, never both gone.  The
  abstract backend contract (BE-018, Gap 5) currently sidesteps intermediate
  states; this item formalizes the contract for atomic-move-capable backends.
  Spec: BE-018, ASYNC-018, ResourceSafety.dfy § 2.

- [ ] **ID-190 — Path formalization: `WellFormedPath` predicate and round-trip invariant**
  Two related gaps in the Dafny model. First: `BackendContract.dfy` treats
  paths as opaque strings and assumes well-formedness without verifying how
  it is produced. PATH-001..015 (normalization rules: backslash → slash, `..`
  rejection, null-byte rejection, slash collapsing, empty-component removal)
  are Python-only today. Add a `WellFormedPath(s: string): bool` predicate to
  `BackendContract.dfy` encoding these rules, and declare it as a precondition
  assumption on all contract methods. Update `MemoryBackend.dfy` to carry the
  assumption through. Second: no formal guarantee that
  `to_key(native_path(k)) == k` for all backend-relative keys. Add a
  `NativePathRoundTrip` lemma (or axiom, if the full proof is out of scope for
  now) to the contract. This enables future composition reasoning across
  Store ↔ Backend layers. Spec: PATH-001–015, NPR-001, NPR-010, STORE-012.

- [ ] **ID-189 — Dafny spec completeness sweep: missing error variant and field axioms**
  Three small gaps with no current Tier-3 consumer but required for oracle
  accuracy. (a) `ResourceLocked` (ERR-013, spec 005) is absent from the
  `Error` datatype in `BackendContract.dfy`; add the variant and update
  `_helpers.py::_raise_if_err` to dispatch it to the Python error class.
  (b) WR-007 ("no default hashing"): add a postcondition to the abstract
  `Write` contract stating `source == BasicSource ==> r.value.digest.None?`,
  closing the gap where a non-native backend could silently populate `digest`.
  (c) `FileInfo.name` consistency: add an axiom to the `GetFileInfo`
  postcondition requiring `info.name == LastPathComponent(info.path)`,
  preventing backends from returning a mismatched name field.
  Spec: ERR-013, WR-007, MOD-001.

- [ ] **ID-188 — Resource safety verification: `SafeWrapInvariant` and `open_atomic` cleanup**
  Two test-gap closures plus one small Dafny extension.
  (a) **Dafny (Tier 1):** add quality-flag postcondition axioms to
  `BackendContract.dfy`: if `CapSeekableRead in capabilities` then every
  stream returned by `Read` satisfies `stream.seekable()`; stub the
  `CapLazyRead` flag analogously as a no-I/O-before-first-read advisory.
  (b) **Pattern B — `test_streaming.py`:** add `assert stream.closed` after
  every context-manager exit and after every explicit `.close()` call,
  citing `ResourceSafety.dfy::SafeWrapInvariant` in the comment. The
  `SafeWrapImpliesNoLeaks` lemma guarantees no handle is left in `Open`
  state after a safe-wrap sequence; these assertions make that guarantee
  visible in the test suite.
  (c) **Pattern B — `test_atomic.py`:** after the exception-cleanup test for
  `open_atomic`, add a `list_files` scan asserting no orphan temp files
  remain anywhere under the test prefix, not just that the target path does
  not exist.
  Spec: SIO-001, SIO-008, SIO-009, SAW-004, ResourceSafety.dfy § 1.

- [ ] **ID-187 — Aggregate verification: oracle differential and property-based tests for `GetFolderInfo`**
  `TestGetFolderInfoAggregates` spot-checks `file_count` and `total_size`
  against hardcoded expected values. Two upgrades: (a) **Pattern A:** run
  each existing aggregate test against both the target backend and
  `DafnyOracleBackend` within the same test body using the ID-183
  infrastructure; assert `python_fi.file_count == oracle_fi.file_count` and
  `python_fi.total_size == oracle_fi.total_size`. The oracle is the
  ground-truth implementation of the `GetFolderInfo` postcondition
  (`file_count == |ChildFiles(fs, path)|`, `total_size == SumSizes(fs,
  ChildFiles(fs, path))`). (b) **Property-based:** add a
  `hypothesis`-parametrized test that generates random file trees (varying
  nesting depth 0–4, file count 1–20, size 1–10000 bytes) and compares
  Python `MemoryBackend` vs oracle on `get_folder_info` — catches off-by-one
  errors in recursive `ChildFiles` or `SumSizes` computation that deterministic
  fixtures cannot reach. Depends on ID-183. Spec: BE-017, ID-134,
  BackendContract.GetFolderInfo, MemoryBackend.SumSizesAddOne lemma.

- [ ] **ID-185 — Listing completeness and depth verification**
  Two gap families in `tests/backends/conformance/test_listing.py`, both
  resolvable without Dafny spec changes (`DepthCounting.dfy` is already
  complete). (a) **Depth boundary (Pattern B):** the four
  `test_list_files_recursive_max_depth` variants check name-sets only; add
  `assert all(path.count("/") - prefix.count("/") - 1 <= max_depth for f in
  files)` (or a shared `_depth(prefix, path)` helper) so a buggy backend
  that ignores `max_depth` would fail, not silently pass. Cite
  `DepthCounting.dfy` Properties 1–4 in the assertion comment. (b)
  **Completeness (Pattern A):** `test_list_folders_completeness` and
  `test_list_files_recursive` verify expected name-sets but not the
  `forall` quantifier ("every matching path appears in the result"). Run
  the same listing on `DafnyOracleBackend` via ID-183 and assert
  `{f.path for f in python_result} == {f.path for f in oracle_result}`,
  catching backends that silently truncate results. Depends on ID-183.
  Spec: DEPTH-001, BackendContract.ListFiles completeness postcondition,
  BackendContract.ListFolders completeness postcondition.

- [ ] **ID-184 — Error contract verification: precondition ordering and completeness**
  Paired Tier-1 Dafny change and Tier-3 test gaps; ship together.
  (a) **Dafny (Tier 1):** lift `AllAncestorsTraversable` from
  `MemoryBackend.dfy` into the abstract `BackendContract.dfy` postconditions
  for `Exists`, `IsFileMethod`, `IsFolderMethod`, `ListFiles`, and
  `ListFolders` — currently the predicate is only in the refinement, leaving
  the abstract contract silent on file-as-directory-component behaviour
  (BE-004, BE-005, BE-014, BE-015).
  (b) **Pattern B — BE-008 ordering:** in `test_errors.py`, add inline
  assertions confirming that `IsDir` fires *before* the `overwrite` and
  `missing_ok` flags are evaluated — specifically
  `test_write_on_directory_overwrite_still_raises_error` and
  `test_delete_on_directory_missing_ok_still_raises`. The Dafny Write
  postcondition chain (L359–372) encodes this ordering; the tests today
  only check the error type, not the ordering invariant.
  (c) **Pattern B — `delete_folder` completeness:** `test_delete_folder_recursive_removes_all`
  asserts two specific paths are gone; add a scan asserting no path under
  the deleted prefix exists, matching the Dafny quantifier
  `forall p | IsChildOf(p, path) :: !PathExists(fs, p)`.
  For move/copy destination-path discrimination in `test_destination_is_directory_raises_error`,
  see BK-177 which already tracks that `match=` tightening with a concrete fix recipe.
  Spec: BE-004, BE-005, BE-008, BE-014, BE-015, BE-021.

- [ ] **ID-183 — Oracle differential testing infrastructure (Pattern A foundation)**
  The `DafnyOracleBackend` already participates in every conformance test as
  a parametrized backend, but no utility exists to run an operation on *both*
  a target backend and the oracle within the same test and compare outputs.
  This item adds that infrastructure as the shared foundation for ID-184
  through ID-188. Concretely: a `assert_oracle_match(backend, method, *args,
  **kwargs)` helper (or fixture variant) that (1) constructs a fresh
  `DafnyOracleBackend`, (2) seeds it with the same state as `backend` via a
  minimal write sequence, (3) calls `method` on both, (4) asserts results are
  equal with a structured diff on mismatch. Also: document the Pattern A/B
  conventions — which Dafny spec ID to cite in assertion comments, how to
  reference postcondition line numbers — so all subsequent items follow the
  same style. The helper lives in
  `tests/backends/dafny/` alongside `_helpers.py`.
  No spec change; no new tests. Prerequisite for ID-185, ID-187, ID-188.

### API Surface Enhancements

- [ ] **ID-181 — Per-backend `ssh-rsa` opt-in via `paramiko.Transport` subclass**
  `SFTPUtils.enable_ssh_rsa_compat()` mutates paramiko's class attributes
  so every `Transport` instance in the process accepts SHA-1 host keys
  thereafter. For single-server use cases this is fine and documented as
  a security tradeoff. For processes that talk to a mix of modern and
  legacy SFTP backends (e.g. a Dagster job, a multi-tenant pipeline),
  the shim leaks SHA-1 acceptance into every other transport. A
  per-backend escape hatch would scope the tradeoff to one backend.
  Sketch: `BackendConfig(type="sftp", options={..., "allow_legacy_ssh_rsa": True})`
  constructs a `Transport` subclass whose instance-level `_preferred_keys`
  / `_preferred_pubkeys` include `ssh-rsa`, leaving `paramiko.Transport`
  class attrs untouched. `Transport._key_info` and `RSAKey.HASHES` are
  read at class scope so they still need a module-level patch — but
  those are algorithm-name → impl lookup tables, not security policy.
  Audience: `user.api`. Surfaced during BK-198 (PR 613) review.

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

- [ ] **BK-139d — Implement remaining bug prevention measures from research**
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

