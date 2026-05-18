# Development Backlog
<!-- doc: repo-only -->

Active work items and ideas. Completed items live in
[BACKLOG-DONE.md](BACKLOG-DONE.md).

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

## How this file works

**Status legend:** `[ ]` pending · `[~]` in progress

**Ordering:** within each topic group, higher-priority or blocking items come first.

**Item scope:** idea + decision-relevant constraints + open questions.
Do not repeat process steps (those live in `sdd/000-process.md` and the ripple-check table).
Existing items may be more verbose — trim on next touch.

**Item attributes:** each item carries a compact `spec: · effort: · audience:` line for quick scanning.
Effort: S = <1 day · M = 1–3 days · L = >3 days. `—` = not applicable.

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

## Azure HNS Correctness

Confirmed defects on real ADLS Gen2 accounts plus testing infrastructure for live coverage.
Bug fixes follow the `hdi_isfolder` probe pattern established by BUG-190/BUG-192.
BK-182 depends on live fixtures from BK-180 (landed) and on the Azure cassette/replay layer from BK-181 (landed).

- [~] **BK-227 — `Store.move`/`copy` self-op short-circuit masks backend BUG-201 `InvalidPath` for HNS directories**
  spec: BE-018, BE-019, BE-021 · effort: S · audience: library.maintainer
  `Store.move`/`copy` and `AsyncStore.move`/`copy` short-circuit `src == dst`
  by checking `self._backend.is_file(src_path)`; if False, raises
  `NotFound("Source not found: {src}")`. After BUG-203,
  `AzureBackend.is_file(hns_dir)` correctly returns `False`, so a Store-level
  self-move on an HNS directory now raises `NotFound` — but the path **does**
  exist, just as a directory. The backend's BUG-201 fix raises `InvalidPath`
  (BE-021) for the same input; that contract is unreachable via the Store
  wrapper. Pre-existing surface gap surfaced by PR #650 round-2 review.
  Fix: detect HNS-directory-source via `is_folder`/dir-probe before raising
  `NotFound`; raise `InvalidPath` to match the backend contract. Update or
  add a `Store`-layer regression test mirroring the backend
  `test_self_op_on_hns_directory_raises_invalid_path`.

- [ ] **BK-226 — Coalesce local `from azure.core.exceptions import ...` imports in `_azure.py` (sync + async)**
  spec: — · effort: S · audience: library.maintainer
  Both `src/remote_store/backends/_azure.py` and
  `src/remote_store/aio/backends/_azure.py` repeat local
  `from azure.core.exceptions import ResourceNotFoundError` /
  `HttpResponseError` inside ~8 methods each. The pattern predates the
  consolidation work (already imported at module level for the same
  `HttpResponseError` symbol elsewhere) and entrenched further with the
  BUG-200/BUG-201 paths. Promote the names to module-level imports — they
  are already in scope on import of `azure.core` (a hard dependency via
  the Azure SDK) so no extra extra-guard is needed. Flagged by
  PR #650 review; deferred to keep the consolidation PR
  scoped to the bug fixes themselves.

- [ ] **BK-182 — Shrink live HNS suites under `tests/backends/azure/`**
  spec: TEST-002, TEST-003 · effort: M · audience: infra.test
  Originally targeted the now-removed top-level
  `tests/backends/test_azure_live_hns.py` /
  `tests/aio/test_async_azure_live_hns.py` pair; BK-179's reorg moved them
  to `tests/backends/azure/test_live_hns.py` and
  `tests/backends/azure/aio/test_live_hns.py`. BK-180 added live `azure_live`
  / `azure_live_async` conformance fixtures, so most happy-path coverage
  in the moved files is now duplicated against a real ADLS Gen2 account.
  Now that BK-181 has landed the Azure cassette/replay layer (PRs #629/#630),
  delete the duplicated cases and keep only HNS-unique tests at the new
  paths: DFS AsyncIterator protocol
  (BUG-194 regression guard), etag normalisation cross-check
  (`get_file_properties` vs `get_file_info`), directory-blob `hdi_isfolder`
  probes, and any remaining deviation guards. Async equivalents stay under
  `tests/backends/azure/aio/test_live_hns.py` only where sync / async
  behaviour differs. Spec: TEST-002, TEST-003.

---

## Formal Verification

Goal: Dafny spec as authoritative contract, compiled oracle as reference backend,
conformance tests as proof obligations — tightly coupled and machine-verifiable.
Two patterns: **A** (oracle differential — run op on target + `DafnyOracleBackend`,
assert outputs match) and **B** (inline postcondition assertions citing spec ID and
line number).

**Execution order:**

| Wave | Items | Notes |
|---|---|---|
| 0 — no prereqs | ID-183, ID-184, ID-188, ID-189, BK-195 + BK-196 | Start in parallel; ID-183 is infrastructure; ID-188 is Tier 1 + Pattern B only |
| 1 — after ID-183 | ID-185, ID-187 | Pattern A work; needs oracle helper |
| 2 — long-horizon | ID-190, ID-191 | No blocker; pick up when scope allows |

- [ ] **ID-183 — Oracle differential testing infrastructure (Pattern A foundation)**
  spec: — · effort: M · audience: infra.test
  The `DafnyOracleBackend` already participates in every conformance test as
  a parametrized backend, but no utility exists to run an operation on *both*
  a target backend and the oracle within the same test and compare outputs.
  This item adds that infrastructure as the shared foundation for ID-185
  and ID-187 (the Pattern A consumers). Concretely: a
  `assert_oracle_match(backend, method, *args,
  **kwargs)` helper (or fixture variant) that (1) constructs a fresh
  `DafnyOracleBackend`, (2) seeds it with the same state as `backend` via a
  minimal write sequence, (3) calls `method` on both, (4) asserts results are
  equal with a structured diff on mismatch. Also: document the Pattern A/B
  conventions — which Dafny spec ID to cite in assertion comments, how to
  reference postcondition line numbers — so all subsequent items follow the
  same style. The helper lives in
  `tests/backends/dafny/` alongside `_helpers.py`.
  No spec change; no new tests. Prerequisite for ID-185 and ID-187.

- [ ] **ID-184 — Error contract verification: precondition ordering and completeness**
  spec: BE-004, BE-005, BE-008, BE-014, BE-015, BE-021 · effort: M · audience: infra.test
  Paired Tier-1 Dafny change and Tier-3 test gaps; ship together.
  (a) **Dafny (Tier 1):** `AllAncestorsTraversable` is already defined in
  `BackendContract.dfy` (L230) and used in the abstract postconditions of
  `Exists`, `IsFileMethod`, and `IsFolderMethod` (L303, L312, L321), but
  `ListFiles` (L469) and `ListFolders` (L496) postconditions are silent on
  it — a backend that succeeds even when an ancestor is a file would satisfy
  the contract today. Add the traversability requirement to both listing
  methods (BE-014, BE-015) so the abstract contract matches what the
  Memory refinement already proves.
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

- [ ] **ID-188 — Resource safety verification: `SafeWrapInvariant` and `open_atomic` cleanup**
  spec: SIO-001, SIO-008, SIO-009, SAW-004 · effort: M · audience: infra.test
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

- [ ] **ID-189 — Dafny spec completeness sweep: `ResourceLocked` error variant**
  spec: ERR-013 · effort: S · audience: infra.test
  `ResourceLocked` (ERR-013, spec 005) is absent from the `Error` datatype in
  `BackendContract.dfy` even though the Python `RemoteStoreResourceLockedError`
  is a first-class exception. Add the `ResourceLocked(path: Path)` variant
  and update `tests/backends/dafny/_helpers.py::_raise_if_err` to dispatch
  it to the Python error class. Without the variant, an oracle run on a
  backend that surfaces `ResourceLocked` (e.g. the future Graph backend,
  ID-127) would crash the differential helper rather than report a clean
  mismatch.
  Spec: ERR-013.

- [ ] **BK-195 — Conformance test: `copy()` preserves user metadata**
  spec: WR-013, BE-019, ASYNC-019 · effort: M · audience: infra.test
  `tests/backends/conformance/test_atomic.py::TestWriteResultConformance`
  covers `write → get_file_info` metadata round-trip but no test exercises
  `write → copy → get_file_info` metadata for any backend. The gap is why
  BK-192 shipped to master: only memory backends had targeted tests, and
  no cross-backend gate caught the same omission. Add a conformance test
  that runs against every backend declaring `USER_METADATA` capability
  (Local, S3, SFTP via metadata files, Azure, memory, async-memory).
  Surfaced during BK-192 work. Spec: WR-013, BE-019, ASYNC-019.
  Trace: `sdd/traces/bk-192-copy-metadata-parity.yml`.

- [ ] **BK-196 — Dafny formal-spec gap: `Copy` postcondition does not pin metadata**
  spec: WR-013, BE-019, ASYNC-019 · effort: S · audience: library.maintainer
  `sdd/formal/MemoryBackend.dfy::Copy` builds the destination via
  `BasicFileInfo(dst, dst, srcEntry.info.size)`, which drops user metadata.
  The `Copy` postcondition does not pin metadata, so the model verifies
  cleanly today but encodes the same defect the Python code had before
  BK-192. Two fix shapes: (a) tighten the postcondition to require
  `dstEntry.info.userMetadata == srcEntry.info.userMetadata` and adjust
  `BasicFileInfo` / the constructor to carry it; (b) extend `Copy` to
  thread metadata through explicitly. Surfaced during BK-192 work. Spec:
  WR-013, BE-019, ASYNC-019. Trace: `sdd/traces/bk-192-copy-metadata-parity.yml`.

- [ ] **ID-185 — Listing completeness and depth verification**
  spec: DEPTH-001, BackendContract.ListFiles · effort: M · audience: infra.test
  Two gap families in `tests/backends/conformance/test_listing.py`, both
  resolvable without Dafny spec changes (`DepthCounting.dfy` is already
  complete). (a) **Depth boundary (Pattern B):** the four
  `test_list_files_recursive_max_depth` variants check name-sets only; add
  `assert all(path.count("/") - prefix.count("/") - 1 <= max_depth for f in
  files)` (or a shared `_depth(prefix, path)` helper) so a buggy backend
  that ignores `max_depth` would fail, not silently pass. Cite
  `DepthCounting.dfy` Properties 1–4 in the assertion comment. (b)
  **Completeness (Pattern A):** `test_list_folders_completeness` and
  `test_list_files_unlimited_depth` verify expected name-sets but not the
  `forall` quantifier ("every matching path appears in the result"). Run
  the same listing on `DafnyOracleBackend` via ID-183 and assert
  `{f.path for f in python_result} == {f.path for f in oracle_result}`,
  catching backends that silently truncate results. Depends on ID-183.
  Spec: DEPTH-001, BackendContract.ListFiles completeness postcondition,
  BackendContract.ListFolders completeness postcondition.

- [ ] **ID-187 — Aggregate verification: oracle differential and property-based tests for `GetFolderInfo`**
  spec: BE-017, BackendContract.GetFolderInfo · effort: M · audience: infra.test
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
  BackendContract.GetFolderInfo, BackendContract.SumSizesAddOne lemma.

- [ ] **ID-190 — Path formalization: `WellFormedPath` predicate and round-trip invariant**
  spec: PATH-002–008, NPR-020, NPR-010, STORE-012 · effort: L · audience: library.maintainer
  Two related gaps in the Dafny model. First: `BackendContract.dfy` treats
  paths as opaque strings and assumes well-formedness without verifying how
  it is produced. PATH-002..008 (normalization rules: backslash → slash, `..`
  rejection, slash stripping, slash collapsing, dot-segment removal, null-byte
  rejection, empty-path rejection) are Python-only today. Add a
  `WellFormedPath(s: string): bool` predicate to `BackendContract.dfy`
  encoding these rules, and declare it as a precondition assumption on all
  contract methods. Update `MemoryBackend.dfy` to carry the assumption
  through. Second: no formal guarantee that `to_key(native_path(k)) == k`
  for all backend-relative keys (NPR-020's stated identity). Add a
  `NativePathRoundTrip` lemma (or axiom, if the full proof is out of scope
  for now) to the contract. This enables future composition reasoning across
  Store ↔ Backend layers. Spec: PATH-002–008, NPR-020, NPR-010, STORE-012.

- [ ] **ID-191 — Move atomicity formal model in `ResourceSafety.dfy`**
  spec: BE-018, ASYNC-018 · effort: L · audience: infra.test
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

---

## Async API Verification

Async API surface, conformance, and tooling. ID-192 (aio.md rework) has landed
(see BACKLOG-DONE.md); the verifier (ID-194) can now be made authoritative and
the conformance pattern (ID-193) can lock in the test shape against the
stabilised page.

**Sequence:** ID-194 (in parallel with ID-193) → ID-172 → ID-173

- [ ] **ID-193 — Async conformance extended: pattern research and implementation**
  spec: ASYNC-018, ASYNC-019 · effort: L · audience: infra.test, library.maintainer
  The sync extended conformance chain is complete (spec → Dafny MemoryBackend oracle →
  conformance test), but the async variant has no pattern yet. Research event-loop
  per-test management, Hypothesis 6.x stateful-test workarounds (per-instance loop +
  `run_until_complete`), and oracle integration with async backends. Three phases:
  (1) document constraints and open questions; (2) write pattern doc or PoC;
  (3) implement against settled async API surface. Do not port sync tests line-for-line.
  ID-192 (aio.md rework) prerequisite has landed.

- [ ] **ID-194 — gen_graph.py async gate extension (prereq for ID-172)**
  spec: — · effort: M · audience: platform.tooling, library.maintainer
  `gen_graph.py` emits gating edges for `Store` and `Backend` but lacks async equivalents.
  Without a `_GATING` constant in `aio/_async_store.py` and async graph emission,
  `check_api_docs.py` has nothing to compare against for the async page.
  Add `_GATING` to `src/remote_store/aio/_async_store.py` (mirroring the sync
  `_GATING` constant in `_store.py`), then extend `gen_graph.py` to emit async gates
  via Griffe traversal of `pkg.members["aio"].members["_async_store"].members["AsyncStore"]`.
  ID-192 prerequisite has landed. Unblocks ID-172 (PAGES wiring).

- [ ] **ID-172 — `check_api_docs.py` — `AsyncStore`/`AsyncBackend` ↔ `docs-src/reference/api/aio.md`**
  spec: — · effort: M · audience: platform.tooling
  Spun off from ID-171 (Backend sub-task done, see BACKLOG-DONE.md).
  ID-192 (aio.md rework) prerequisite has landed; still blocked on ID-194
  (gen_graph async gate extension).
  Once both land: add `AsyncStore` and `AsyncBackend` to `PAGES` in
  `check_api_docs.py` pointing at `docs-src/reference/api/aio.md`.
  `check_api_docs.py` is already wired into the `hatch run lint` script and the
  CI lint job (landed via BK-203); adding the entries is the only remaining step.
  Griffe traversal path (for the implementer):
  `pkg.members["aio"].members["_async_store"].members["AsyncStore"]`

- [ ] **ID-173 — `check_api_docs.py` — `__all__` ↔ `docs-src/reference/api/index.md`**
  spec: — · effort: M · audience: platform.tooling
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

---

## SFTP

- [ ] **ID-181 — Per-backend `ssh-rsa` opt-in via `paramiko.Transport` subclass**
  spec: SFTP-007 · effort: M · audience: user.api
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
  Surfaced during BK-198 (PR 613) review.

---

## Lint / CI Completeness


- [ ] **ID-179 — Trace schema validator: wire `audience` field check into `hatch run lint`**
  spec: — · effort: S · audience: library.maintainer
  `sdd/traces/_schema.yml` declares `audience` as `required` but no
  validator runs it. Add `scripts/check_traces.py` that jsonschema-validates
  every `sdd/traces/[!_]*.yml` against the schema. Wire into the existing
  `hatch run lint` script list and into the lint CI job. Per
  `feedback_check_scripts_dual_wire`. Closes the convention-vs-enforcement
  gap left open by BK-193. No priority while trace authoring is still
  ad-hoc; promote to BK-prefix when trace volume justifies enforcement.

---

## Docs & Discoverability

- [ ] **ID-161 — Publish `llms.txt` to the docs site**
  spec: — · effort: S · audience: user.api, library.maintainer
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

  **Content checklist when starting:** streaming reads (`with store.read(path) as f:`),
  `MemoryBackend` for unit testing, `store.child()` scoping, and
  `ext.integrity`/`ext.partition`/`ext.transfer` use-case examples are the
  known gaps in how external tools currently discover remote-store.

  **Sequence — start after all of:**
  - ID-174 (docs reorg): final source URLs must be stable before the link list is written.
  - ID-172 + ID-173 (aio verifiers): `aio.md` and `index.md` must accurately
    reflect the async API before they are linked as authoritative reference.
  - ID-192 (aio.md rework): landed — `aio.md` structural rework is in place; required for ID-172 to close (see BACKLOG-DONE.md).
  - ID-193 (async conformance): async extended conformance pattern must be
    designed and implemented before the aio API surface is considered settled.

  **Exit criteria:** `docs-src/llms.txt` committed; `GET
  https://docs.remotestore.dev/llms.txt` returns the file after next deploy.

- [ ] **ID-180 — Stable HTML-anchor IDs across non-spec docs under `sdd/`**
  spec: — · effort: M · audience: library.maintainer
  Specs already have stable IDs (`ASYNC-016`, `WR-013`); non-spec docs
  (CLAUDE.md "Principles", CLAUDE-REFERENCE row pointers, AUTHORING /
  DOCUMENTATION / CONTENT-RULES rules) do not. Trace `section:` fields
  reference these by heading text, which rots when sections are renamed.
  Add HTML-anchor comments (`<!-- id: ripple-bug-fix -->`) to stable
  reference points in seven `sdd/` framework docs plus `CLAUDE.md`. No
  priority until trace aggregation exists or first heading-text drift
  breaks a trace reference; promote to BK-prefix at that point.

- [ ] **ID-197 — Review context7.com docs page for framing and content gaps**
  spec: — · effort: S · audience: library.maintainer
  The context7 docs proxy surfaces how external tools and readers discover the
  project; framing found there (e.g. "one consistent interface across environments")
  may sharpen our own Getting Started, README, or guides. Walk the page, compare
  framing and structure against `docs-src/`, note strong angles and coverage gaps,
  then assess whether our source docs already cover them or could adopt the same
  framing. Findings feed the next docs-improvement session or ID-161 content checklist.

---

## API Ergonomics

- [ ] **ID-196 — RemotePath.as_posix() and pathlib parity audit**
  spec: NPR-020 · effort: S · audience: user.api
  `RemotePath.__str__` returns the POSIX-style key, but `.as_posix()` raises
  `AttributeError`, breaking pathlib muscle memory. `pathlib.PurePath.as_posix()`
  is the documented, canonical way to get a forward-slash string regardless of
  platform. Add `as_posix()` as a one-line property returning `str(self)` in
  `src/remote_store/_path.py`, then audit `RemotePath` against the `PurePath`
  API surface (`__fspath__`, `fspath`, etc.) to close remaining parity gaps.
  Discovered during HNS listing test authoring; workaround was explicit `str()` conversion.

- [ ] **ID-123 — Cache key derivation from `ResolutionPlan` (Phase 2)**
  spec: RES-100 · effort: M · audience: user.api
  `ext.cache` derives cache keys from `ResolutionPlan` fields instead of
  ad-hoc `(operation, path)` tuples. Only valuable once `CompositeStore`
  (ID-121) exists — single-backend cache keys are already correct.
  - Spec: RES-100 (proposed in [043](specs/043-resolution-plan.md))
  - Depends on: ID-121 (CompositeStore)

---

## New Backends

- [ ] **ID-127 — OneDrive / SharePoint backend (Microsoft Graph)**
  spec: GR-001..GR-057 · effort: L · audience: user.api
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
  spec: — · effort: L · audience: user.api
  `CompositeStore(Store)` — core Store subclass (not extension) that composes
  multiple stores into one. Deterministic fallthrough resolution for reads, union
  LIST (deduplicated), writes to primary tier only.
  - [Research](research/research-sqlalchemy-backend.md#52-compositestore-id-120)
    (anchor uses historical ID-120 from research doc; now ID-121 after swap)
  - Depends on: unified `resolve()` → `ResolutionPlan` (ID-120); at least two
    working backends to be useful; pairs well with ID-119
  - Next: design as separate spec — backend-agnostic, useful independently

- [ ] **ID-140 — SQLBlob lazy reads for SQLite & PostgreSQL**
  spec: SQL-BLOB-003, SQL-BLOB-020 · effort: L · audience: user.api
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

---

## Long-horizon / Maintenance

- [ ] **ID-150 — Revisit informational `verify-tla` CI status (2026-10-19)**
  spec: — · effort: S · audience: library.maintainer
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

- [ ] **ID-182 — Scheduled CI drift guard for unbounded extra-dependency floors**
  spec: — · effort: M · audience: library.maintainer
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
  early warning, not automated remediation. Surfaced during BK-198 (PR 613) review.

- [ ] **ID-198 — Medallion Dagster + Azure HNS live showcase validation run**
  spec: — · effort: S · audience: library.maintainer, user.api
  The `examples/medallion_dagster/` showcase demonstrates a realistic user journey
  combining Dagster orchestration with an Azure HNS backend, but has never executed
  against a live ADLS Gen2 account. Run the full example end-to-end against real cloud
  infrastructure to surface testing gaps, implementation TODOs, or edge cases that
  conformance and unit tests miss. Schedule after async conformance (ID-193) completes
  so async patterns are settled. Findings inform the next release scope; no code changes
  are produced by this item itself.

- [ ] **BK-208 — Triage post-v0.23.0 lessons-learned into backlog items**
  spec: — · effort: M · audience: library.maintainer
  A post-v0.23.0 retrospective covers the v0.23.0→master cycle (~100 PRs, two
  headline features: WriteResult and AsyncBackendSyncAdapter). Eight concrete
  recommendations were deferred before v0.24.0 to avoid scope creep. Triage them
  into proper backlog items or close each with reasoning: (a) feature-type DoD
  checklists in `sdd/000-process.md`; (b) `guides/` and `examples/snippets/` rows
  in the ripple-check table; (c) `filterwarnings = error` to feature-DoD; (d)
  symmetric capability-declaration test; (e) streaming-iteration assertion;
  (f) `tests/aio/README.md` update. Closes the pattern-drift risk before ID-127
  Graph backend repeats conformance-lag and doc-ripple issues.

- [~] **ID-018 — conda-forge publishing**
  spec: — · effort: — · audience: library.maintainer
  Recipe, CI validation, release checklist steps all done.
  - Done: [recipe](../packaging/conda-forge/recipe.yaml),
    [conda-recipe workflow](../.github/workflows/conda-recipe.yml),
    staged-recipes PR `conda-forge/staged-recipes#32401` (CI green).
  - Blocked: waiting for conda-forge reviewer approval. When merged: add
    `conda install -c conda-forge remote-store` to README.

---

## Icebox

Deferred indefinitely — revisit only if demand or circumstances change.

- [ ] **BK-139d — Implement remaining bug prevention measures from research**
  spec: — · effort: M · audience: library.maintainer
  Items 1–3 shipped as BK-139a; items 4, 5, 7 shipped as BK-139b (see
  BACKLOG-DONE.md). Only item 6 remains: `scripts/check_error_handling.py`
  (~80 lines) — an AST script flagging broad exception handlers that silently
  return without checking `errno`. Deferred because BLE rules (item 4) and the
  extended conformance error-fidelity category (item 5) cover the same
  error-swallowing bug class with less maintenance overhead. Reactivate if a
  new error-swallowing bug escapes those nets.
  Related: [research](research/research-bug-prevention-beyond-testing.md).

- [ ] **ID-114 — PyArrow-style bucket path support (research)**
  spec: — · effort: S · audience: user.api
  PyArrow convention: `"bucket/prefix"` embeds bucket in path. Current
  `S3Backend` requires split (`bucket=...`, `path=...`). Research feasibility
  of factory method or native convention for easier PyArrow→remote-store
  migration.
  - Deliverable: RFC only — low commitment, no code change guaranteed

- [ ] **ID-118b — TLS CA bundle for Azure (Phase 2)**
  spec: — · effort: M · audience: user.api
  Extend `tls_ca_bundle` to `AzureBackend` if demand materializes.
  Primarily benefits Azure Stack Hub / on-premises deployments.
  Wrap `ClientOptions(ca_cert=...)`, check `AZURE_CA_CERTIFICATE_PATH`.
  S3 Phase 1 shipped — see BACKLOG-DONE.md.

- [ ] **ID-105 — AzurePyArrowBackend (C++ Tier 1)**
  spec: — · effort: L · audience: user.api
  Optional upgrade from the Tier 3 range reader shipped in
  [ID-102](BACKLOG-DONE.md#streaming--io). Only worth pursuing if real-Azure
  benchmarks show GIL overhead or missing I/O coalescing matters for target
  workloads. Approach: `pyarrow.fs.AzureFileSystem` (C++, ships with PyArrow)
  following the `S3PyArrowBackend` dual-library pattern.
  [Research § 6](research/research-azure-pyarrow-optimization.md#6-full-tier-1-path-if-needed).
  - Spike: validate auth methods, HNS/non-HNS, `ReadRangeCache` activation.
  - If viable: `AzurePyArrowBackend` — spec, tests, docs.

- [ ] **ID-125 — Update medallion showcase to Dagster v2 resource pattern**
  spec: — · effort: S · audience: user.api
  Replace `dagster_io_manager(store)` calls in `examples/medallion_dagster/`
  with `RemoteStoreIOManager`. Demonstrates the config-driven pattern.

- [ ] **ID-066 — PR preview deployments**
  spec: — · effort: L · audience: library.maintainer
  Deploy PR previews to Cloudflare Pages, Netlify, or GitHub Pages artifacts.
  Inspired by FastAPI's Cloudflare Pages pattern. Infrastructure decision needed.
  [Research](research/research-fastapi-docs.md) P6.

- [ ] **ID-067 — griffe-typingdoc for `Annotated[T, Doc("...")]` docstrings**
  spec: — · effort: S · audience: library.maintainer
  Only relevant if migrating from Google-style docstrings to PEP 727
  `Annotated[T, Doc("...")]`. Not recommended near-term.
  [Research](research/research-fastapi-docs.md) P5.
