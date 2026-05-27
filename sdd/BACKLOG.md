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

## Formal Verification

The SDD chain is `Markdown spec → @pytest.mark.spec test`. The marker is
just a string: nothing proves a spec clause is self-consistent, and
nothing proves the test faithfully encodes it. The Dafny layer is the
machine-checked interlock in that chain. It earns its place three ways,
none of which is "run a second backend and diff the output":

1. **(C) A proven contract.** Dafny verifies that a clause's
   postcondition is internally consistent and *satisfiable*, discharged
   by the `MemoryBackend` refinement. A Markdown paragraph can silently
   contradict itself; a verified `.dfy` postcondition cannot. A contract
   clause that exists only in prose is unproven.
2. **(T) The oracle certifies the test, not the backend.** The compiled
   `MemoryBackend` is correct by construction and already runs the whole
   conformance suite as a parametrized fixture. A green oracle on a test
   proves the test demands nothing the verified contract does not, i.e.
   the test faithfully encodes the spec. Running the oracle as a peer
   backend to diff against would only test the oracle twice.
3. **(O) The oracle as ground truth.** A deterministic test hardcodes
   its expected value, and that literal is a better oracle than a second
   process: readable and dependency-free. Only property-based tests, with
   random inputs, need the verified oracle to *compute* the expected
   value.

**Execution order:**

| Wave | Items | Notes |
|---|---|---|
| 0 — property-based (O) | — | ID-187 landed; see BACKLOG-DONE.md |
| 1 — contract + test | ID-188, ID-191 | Each pairs a Dafny change with the conformance tests it makes certifiable |
| 1 — test backfill (T) | ID-210 | ID-185 landed; see BACKLOG-DONE.md |

Items stay granular for tracking, but a whole wave row may ship as one
PR where its items share a file or proof.

- [ ] **ID-188 — Resource safety: prove the quality flags, then enforce cleanup**
  spec: SIO-001, SIO-008, SIO-009, SAW-004 · effort: M · audience: infra.test
  A (C)+(T) pair.
  (C) Add quality-flag postconditions to `BackendContract.dfy`: if
  `CapSeekableRead` is declared, every stream `Read` returns satisfies
  `seekable()`; stub `CapLazyRead` as a no-I/O-before-first-read
  advisory. Re-verify the refinement.
  (T) One cleanup-coverage gap: `test_open_atomic_exception_cleanup` in
  `test_atomic.py` asserts only that the target path is absent after an
  `open_atomic` failure. Add a `list_files` scan asserting no orphan temp
  files remain anywhere under the test prefix.

- [ ] **ID-189 — Dafny `Error` variant for `ResourceLocked`**
  spec: ERR-013 · effort: S · audience: library.maintainer
  `ResourceLocked` (ERR-013, spec 005) is specified but not implemented:
  `src/remote_store/_errors.py` has no such class, the hierarchy ends at
  `BackendUnavailable`. The Dafny `Error` datatype omitting the variant is
  therefore correct for the current code, not a gap. The variant becomes
  warranted only when `ResourceLocked` is implemented, which the Graph
  backend (ID-127, ADR-0024) requires. That change adds three coupled
  pieces together: the `ResourceLocked` Python exception class (named
  `ResourceLocked`, per the flat error hierarchy and spec 005's own
  example), the Dafny `Error.ResourceLocked(path: Path)` variant, and its
  dispatch in `tests/backends/dafny/_helpers.py::_raise_if_err`. Track as
  a sub-task of ID-127, not standalone work today.

- [ ] **ID-210 — Async Dafny oracle: certify async conformance against the verified `MemoryBackend`**
  spec: ASYNC-001 — ASYNC-029 · effort: M · audience: infra.test
  A (T) gap spun off from ID-193 close-out: the original "oracle integration
  with async backends" phase was not in fact delivered. The sync conformance
  suite parametrises `dafny_oracle` as a peer backend
  (`tests/backends/fixtures/dafny_oracle.py`, `is_async=false` in
  `tests/backends/fixtures/fixtures.toml`), so every sync conformance test the
  oracle passes proves the test faithfully encodes the verified contract.
  The async suite (`tests/backends/conformance/test_async_extended.py`) runs
  against `memory_async_native`, `memory_async_adapted`, `local_async_adapted`,
  and the Azure async fixtures — but never against the compiled `MemoryBackend`
  from `sdd/formal/MemoryBackend-py/`. The async-shaped contract is therefore
  cross-checked between two Python implementations (`AsyncMemoryBackend` and
  `SyncBackendAdapter(MemoryBackend())`) rather than against the
  verified-by-construction oracle, weakening the (T) leg for async-only spec
  divergence.
  Build `AsyncDafnyOracleBackend` as an `AsyncBackend` subclass that
  delegates each method to the existing `DafnyOracleBackend` via
  `asyncio.to_thread()` — same shape as `SyncBackendAdapter` (ASYNC-030 —
  ASYNC-037), scoped to the oracle so the correct-by-construction property
  the sync oracle has is preserved on the async side. Streaming methods
  (`read`, `list_files`, `list_folders`, `iter_children`) materialise the
  sync iterator inside the worker thread and re-yield from the async generator
  per ASYNC-032 / ASYNC-033. Register `dafny_oracle_async` in
  `tests/backends/fixtures/fixtures.toml` with `is_async=true` and a sibling
  `tests/backends/fixtures/dafny_oracle_async.py`; the registry-driven
  conformance hook in `tests/backends/conformance/conftest.py` then picks it
  up automatically. Spec markers covered by parametrisation: ASYNC-004,
  ASYNC-005, ASYNC-006, ASYNC-007, ASYNC-008, ASYNC-010, ASYNC-012, ASYNC-013,
  ASYNC-014, ASYNC-015, ASYNC-016, ASYNC-017, ASYNC-018, ASYNC-019, ASYNC-020,
  ASYNC-024, ASYNC-029, ASYNC-047 — the 18 the async extended conformance
  suite already exercises.
  **Open question:** whether to additionally model a native-`AsyncBackend`
  refinement in Dafny (closing the spec-side gap that the trait today only
  describes the sync `Backend`) or whether the `to_thread`-bridged sync
  oracle is sufficient for T-side certification. Recommendation: ship the
  bridged variant first; revisit the native-async refinement only if a
  divergence emerges that the bridge masks (analogous to how
  `SyncBackendAdapter` certifies the sync→async bridge in product code
  without a separate verified contract for it).

- [ ] **ID-191 — Move atomicity: model the observable contract, then enforce it**
  spec: BE-018, ASYNC-018 · effort: L · audience: infra.test
  A (C)+(T) pair. `ResourceSafety.dfy` § 2 models `AtomicMove` and
  `CopyDeleteMove` and proves `MoveFinalStateEquivalence`, but no contract
  pins the observable intermediate states.
  (C) Extend `ResourceSafety.dfy` with a `MoveContract` datatype encoding
  the states an atomic-move-capable backend may expose: `DeleteDone`
  (success) or `Failed` (rollback, source preserved), never `CopyDone`
  (source gone, destination not yet written).
  (T) Add a conformance test that injects a crash between copy and delete
  (a mock backend raising on the delete step) and asserts the source is
  intact or the destination is intact, never both gone. This test runs
  against a crash-injecting mock rather than the oracle, so the oracle
  does not certify it; the traceability gate still requires its
  `@pytest.mark.spec("BE-018")` marker. The abstract contract (BE-018,
  Gap 5) currently sidesteps intermediate states.

- [ ] **ID-212 — Harden SFTP file-ancestor detection against partial-stat-permission setups**
  spec: BE-006, BE-007 · effort: S · audience: library.maintainer
  Follow-up to ID-209 (PR #680).  The new
  `SFTPBackend._has_file_ancestor(sftp_path)` walks `sftp_path`'s parent
  chain from the absolute SFTP root `/` rather than from
  `self._base_path`, and returns `False` conservatively on any
  non-ENOENT stat error.  In a chrooted SFTP deployment where stat on
  an ancestor above the chroot returns `SSH_FX_PERMISSION_DENIED`, the
  walk aborts on that ancestor and a genuine file-ancestor case under
  the chroot is mis-classified as a generic `RemoteStoreError("Failure")`
  rather than `NotFound` — diverging from BE-006/BE-007's
  `!PathExists ==> NotFound` postcondition on those servers.  The
  in-process `sftp_inproc` conformance fixture does not exercise this
  because it grants unrestricted local-FS access.

  `_ensure_parent_dirs` shares the same walk-from-root pattern (its own
  comment says "Walk from base_path down" but the code walks from `/`),
  so a clean fix consolidates both helpers onto `self._base_path` as
  the walk root.  Optional second-pass: a targeted `lstat` on the
  immediate parent only as a single-round-trip mitigation when the full
  walk returns False on an opaque error.

  Output: refactor both walks onto `self._base_path`, add a conformance
  fixture variant (e.g. `sftp_chroot_inproc`) that exercises the
  restricted-permission case, and tighten the `_has_file_ancestor`
  docstring to drop the chroot caveat.  Promote to BK-prefix once a
  user reports the divergence on a real chroot deployment.

- [ ] **ID-213 — Extend ID-209's `InvalidPath` translation to the HNS Azure backend**
  spec: BE-008, BE-012, BE-014, BE-015, BE-018, BE-019 · effort: M · audience: contributor.process, infra.test, library.maintainer, user.api
  Follow-up to ID-209 (PR #680). Decision 2(a) — write/move/copy under
  a file ancestor MUST raise `InvalidPath` cross-backend — was
  implemented for Local and SFTP via native-error translation in
  `_classify` / per-method handlers. HNS Azure was deferred under the
  assumption that "HNS has real directories, so the gate should pass
  once recorded"; the BK-235 cassette-recording run against live ADLS
  Gen2 (account `remotestorehns`, 2026-05-27) live-verified that
  assumption and falsified it. Real HNS Azure *does* error on these
  scenarios — no HEAD pre-check needed, which is what distinguishes
  this from ID-211's flat-NS scope — but the SDK raises
  `ResourceNotFoundError` / `ResourceExistsError` /
  `HttpResponseError(404|409)`, which
  `_azure_common.classify_azure_error` currently maps to `NotFound` /
  `AlreadyExists` rather than `InvalidPath`. The eight failing sync
  conformance tests:
    - `TestWriteErrorFidelity::test_write_under_file_ancestor_raises_invalid_path` (`write`, `write_atomic`)
    - `TestWriteErrorFidelity::test_open_atomic_under_file_ancestor_raises_invalid_path`
    - `TestDeleteErrorFidelity::test_delete_under_file_ancestor_raises_not_found` (expects `NotFound`, gets `AlreadyExists`)
    - `TestMoveCopyErrorFidelity::test_destination_under_file_ancestor_raises_invalid_path` (`move`, `copy`)
    - `TestListFilesCompleteness::test_list_files_non_traversable_ancestor_yields_empty`
    - `TestListFoldersCompleteness::test_list_folders_non_traversable_ancestor_yields_empty`
  Fix shape parallels ID-209's Local/SFTP patch: distinguish the
  ancestor-is-a-file case from generic 404/409 in
  `classify_azure_error` (ADLS Gen2 returns a specific `error_code`
  on the response — `PathConflict` / similar — for the
  ancestor-as-file case), then re-raise as `InvalidPath`. For the two
  listing tests the catch site is the per-method handler, not
  `_classify` — the natural Azure error must be swallowed so the
  empty-list postcondition fires (mirrors Local/SFTP's
  `NotADirectoryError` → `[]` swallow added in ID-209). Async siblings
  in `tests/backends/conformance/test_async_extended.py` expected to
  mirror; verify against `azure_live_async` once the sync fix lands
  (the BK-235 recording aborted before Step 3 so the async behaviour
  is not yet observed). Unblocks BK-235 for these eight tests; the
  other eight self-skipping cassettes BK-235 covers record cleanly
  today against live HNS. Parallel to ID-211 (flat-NS HEAD pre-check)
  and ID-212 (SFTP chroot-stat hardening) — all three are ID-209
  follow-ups along different backends' error-translation paths.
  Discovered: BK-235 sync recording run, 2026-05-27.

---

## Async API Verification

Async API surface, conformance, and tooling. ID-192 (aio.md rework) and ID-193
(async conformance pattern) have landed (see BACKLOG-DONE.md); the verifier
(ID-194) can now be made authoritative against the stabilised page.

**Sequence:** ID-194 → ID-172 → ID-173

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

- [ ] **ID-203 — Align `tests/` folder structure with `src/` package layout**
  spec: — · effort: M · audience: library.maintainer
  `tests/` does not mirror the `src/remote_store/` package tree; as the `aio`
  subtree and other packages grow, test file placement becomes ambiguous.
  Mirror `src/` layout (e.g. `tests/aio/`, `tests/backends/`) and carve out
  `tests/scripts/` for script-level tests.
  **Blocked on:** ID-194 (gen_graph async gate) + ID-172 + ID-173 — the async
  API surface must be settled before reorganising the tests that cover it.
  ID-193 (async conformance pattern) is no longer a blocker — landed (see
  BACKLOG-DONE.md).

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

## S3 Client-Implementation Strategy

Three s3fs-inherited pain points (dep-conflict cascade, 5 GB multipart cliff,
listing-cache staleness) would not exist on a boto3-direct backend. Two
investigations and one PoC determine whether the answer is "live with it
and document," "tweak s3fs defaults," or "ship a third S3 lane."
Execute in order: ID-200 informs whether ID-202 needs to also cover
error-mapping wins. All three were surfaced as code-side flags in
[research](research/research-backend-setup-guides.md) § 6 and carved
out of [ID-199](#docs--discoverability) (backend setup-guides initiative).

- [ ] **ID-200 — Audit s3fs error-mapping fidelity in `_S3Base`**
  spec: — · effort: S · audience: library.maintainer
  Establish whether the s3fs → `_ErrorMappingStream` boundary in
  `src/remote_store/backends/_s3_base.py` preserves enough signal from
  `botocore.ClientError` to meet our typed-error contract, or whether
  s3fs swallows / collapses cases the docs claim we surface.
  Concretely, drive these scenarios against a moto-backed `S3Backend`
  and record which `RemoteStoreError` subclass is raised:
  (a) `GetObject` on a missing key → `NotFound`.
  (b) `GetObject` on a forbidden key (403) → `PermissionDenied`, not
      `NotFound`. This is the one most likely lost across s3fs.
  (c) `PutObject` with an expired/invalid session token →
      `BackendUnavailable` or `PermissionDenied`, not silent success.
  (d) Multipart upload abort mid-stream (e.g. connection reset during
      `write_atomic` on a >5 MB file) → typed error, not a partial
      object left in the bucket.
  (e) `HeadObject` on a path whose parent is a key with the same name
      (the directory-marker ambiguity) → `InvalidPath` or `NotFound`,
      not a confused mix.
  Output: a short findings note pinned in `sdd/research/`, with one
  row per scenario (target typed error, observed typed error, the
  underlying s3fs/botocore exception). If any row diverges, open a
  BUG-NNN; otherwise close ID-200 with the note as evidence.
  No spec change; no new tests in this item (failing tests come from
  the BUGs it spawns, per the bug-fix protocol).

- [ ] **ID-201 — Spike: default `S3Backend` to `use_listings_cache=False`?**
  spec: — · effort: S · audience: user.api
  `s3fs` keeps a directory-listing cache whose invalidation is
  undocumented upstream (fsspec/filesystem_spec #324). For `Store`-shape
  workloads this surfaces as stale `list_files` / `iter_children`
  results after writes from another process. Spike whether disabling
  the cache by default is the right trade.
  Measure on a moto bucket and on a real S3 bucket if creds available:
  (1) `list_files` latency with cache on vs off at 100 / 1 000 /
      10 000 keys per prefix, hot vs cold;
  (2) `iter_children` latency at the same sizes;
  (3) frequency of stale results in a write-then-list loop across two
      `Store` instances pointed at the same bucket.
  Output one of three recommendations:
  (a) flip default to `use_listings_cache=False`, document the perf
      delta, expose a `client_options` override for users who need the
      cache;
  (b) keep current default, add a docs section in
      `guides/backends/s3.md` explaining the cache and the override;
  (c) expose a first-class `Store`-level `refresh()` / invalidation
      API if the measurements show the cache is too valuable to drop
      but staleness is too costly to leave silent.
  No code change in this item beyond throwaway measurement scripts;
  the chosen path becomes a new BK-NNN.

- [ ] **ID-202 — PoC: `s3-boto3` backend lane alongside `s3` and `s3-pyarrow`**
  spec: — · effort: L · audience: user.api
  Three of the s3fs-inherited pains we cannot fix from our side are
  (1) the aiobotocore-driven dep-pin cascade against user-installed
  `boto3`, (2) the >5 GB multipart-restart bug (s3fs-fuse #1936), and
  (3) the fsspec listing-cache staleness handled by ID-201. A boto3-
  direct backend has none of these. Build a PoC to decide whether the
  maintenance cost justifies a third S3 lane.
  Scope of the PoC:
  - New backend class `S3Boto3Backend` under
    `src/remote_store/backends/_s3_boto3.py`, sharing `_S3Base` where
    sensible (path normalisation, endpoint URL handling, TLS bundle
    resolution) and diverging where s3fs-specific assumptions leak
    (filesystem-shape walks, cache invalidation calls).
  - New extra `s3-boto3 = ["boto3>=1.34"]`, no `aiobotocore`.
  - Capability parity with `S3Backend` (all caps except
    `ATOMIC_MOVE`), verified by running the conformance suite against
    `S3Boto3Backend` under moto.
  - Multipart upload via `boto3.s3.transfer.TransferConfig`, with an
    explicit smoke test at 5 GB + 1 byte to prove the cliff is gone.
    Run only in `bench` / `live` gates, not in `hatch run all`.
  - Typed-error mapping built from `ClientError.response['Error']
    ['Code']` directly, citing the findings from ID-200.
  Decide on three axes and record the answer in
  `sdd/research/`:
  (a) **User value**: do the three retired pains justify a second
      install path? Net new users gained vs choice-paralysis cost.
  (b) **Maintenance cost**: lines of code in `_s3_boto3.py` beyond
      what `_S3Base` factors out, plus test matrix expansion under
      `hatch run test` and conformance runtime.
  (c) **Interop loss**: which downstream extensions
      (`ext.arrow`, `ext.parquet`, `ext.dagster`) break or degrade
      without the fsspec-shaped backend underneath, and whether they
      can be bridged.
  Three exit dispositions:
  - **Ship**: promote PoC to `BK-NNN` for hardening, docs, and
    inclusion in `FEATURES.md`. Mark `s3` and `s3-boto3` as peers,
    not default-and-alternate.
  - **Park**: keep PoC branch alive but do not merge; revisit if
    s3fs upstream stalls on the 5 GB / listing-cache issues.
  - **Reject**: archive findings as the rationale for not splitting
    the S3 surface; document the boto3 escape hatch via
    `Store.unwrap()` and `s3-pyarrow` instead.
  Out of scope: an async variant (`AsyncS3Boto3Backend`) — folded
  into a follow-up if ID-202 ships.

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

- [ ] **ID-207 — Strengthen `check_formal_trace.py` from citation hygiene to clause enforcement**
  spec: — · effort: L · audience: platform.tooling
  ID-206 shipped `scripts/check_formal_trace.py`; a PR #663 review
  confirmed it certifies *citation hygiene at spec-ID granularity*, not
  clause-level enforcement (its docstring was narrowed to say so). Four
  independent hardening steps would close the gap:
  1. **Derive D mechanically.** D is built from author-typed `// @spec`
     tags, so deleting a tag silently drops an F1 and a new untagged
     `ensures` never enters D. Parse every contract `ensures` and fail on
     an untagged one — needs an exemption marker for proof-helper lemma
     `ensures` (e.g. `SlashCountZero`, the Safe/Unsafe pairs) that encode
     no spec clause.
  2. **Clause granularity, not ID granularity.** D/T/S key on spec ID, so
     one marker clears F1 for every `ensures` sharing that ID (~10 share
     `BE-014`). Per-clause sub-IDs, or a tag→test-name link, would gate
     each postcondition individually.
  3. **Push T past citation.** A marker only cites an ID; it does not
     prove the test asserts the clause, is enabled, or cites the *right*
     ID — a wrong-but-real ID passes F2 and even satisfies F1.
  4. **Bar baseline growth mechanically.** `_BASELINE` shrink-only is a
     review convention; a new violation can be parked by editing the
     frozenset. A committed count/hash pinned by a separate check would
     make it mechanical.
  Surfaced in the PR #663 review. Steps are independent and may split
  into separate IDs. No priority until the gate is shown to miss a real
  regression; promote to BK-prefix at that point.

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
  - ID-193 (async conformance): landed — async extended conformance pattern is
    in place (see BACKLOG-DONE.md).

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

- [ ] **ID-199 — Backend setup & configuration guides expansion**
  spec: — · effort: L · audience: user.site, library.maintainer
  Expand the backend-related guide set in `docs-src/guides/` based on user
  pain mined from two sources: in-repo signal (traces, BACKLOG, CHANGELOG,
  PRs) and an external survey of GitHub issues across `boto3`/`s3fs`/
  `azure-storage-blob`/`paramiko`/`fsspec`, Stack Overflow, Reddit, and
  vendor forums. Seven candidate guides identified; full pain mapping,
  scope boundaries, sequencing, and code-side flags are in
  [research](research/research-backend-setup-guides.md). The two existing
  guides (`azure-hns-setup.md`, `sftp.md`) are the proof-of-value pattern.

  **Authoring contract (binding — see research § 2.2):** every guide
  under this initiative must be self-validated (maintainer-walked
  end-to-end against a real target), practicable (copy-pasteable steps),
  proven (dogfood trace or artifact in the PR), down to the point
  (recipe + outcome + caveat, no marketing), and link only reliable
  external references (vendor docs, RFCs, library docs — not Stack
  Overflow, Reddit, blogs, or GitHub-issue threads). Candidates that
  cannot meet the contract are deferred or scope-reduced, never
  weakened to fit.

  **Tier-1 standalone guides (per-guide PR + dedicated backlog ID when
  each is picked up):**
  1. S3-compatible providers cookbook — greenlit; AWS S3 + MinIO + R2 + B2 tested scope
  2. Large-object & streaming tuning — **split-ship**: SFTP half greenlit; S3 5 GB cliff deferred until AWS dogfood budget
  3. Local-dev emulators — greenlit; already dogfooded via CI
  4. SFTP reliability — greenlit
  5. Azure keyless auth & private endpoints — **conditional** on Azure subscription with elevated RBAC + vNet rights
  6. Credential & secret rotation — greenlit per-backend; Azure half tied to #5
  7. SQLite operational notes — greenlit; sidebar in `sql-blob.md`

  **Tier-2 sidebars** for `s3.md`, `sftp.md`, `azure.md`,
  `azure-hns-setup.md` — see research doc § 4. Fold into adjacent
  Tier-1 PRs where scope overlaps.

  **Out of scope (Tier-3):** AWS root-email governance, MinIO operator
  UX, `s3fs-fuse` FUSE-only concerns, generic DB pool tuning,
  hypothetical Azure-Blob-like self-hosts. Redirect to vendor docs.

  **Three code-side flags surfaced** (NOT guide work) — see research doc
  § 6: `s3fs` typed-error mapping fidelity; `S3Backend`
  `use_listings_cache` default; third S3 lane (`s3-boto3` direct)
  viability. Now tracked as **ID-200 / ID-201 / ID-202** in the
  S3 Client-Implementation Strategy section.

  **Sequencing (dogfood-cost ordered, see research § 7):**
  Phase 1 (zero new setup) = §3.3 + §3.7 + §3.4;
  Phase 2 (free-tier accounts) = §3.1 + §3.6 non-Azure halves + §3.2 SFTP half;
  Phase 3 (budgeted dogfood — gated on the access decision in research § 8 Q5) = §3.2 S3 half + §3.5 + §3.6 Azure half;
  Tier-2 sidebars mop up alongside Phase 1/2.

  Effort `L` reflects the parent scope; each individual guide is M-sized.

- [ ] **ID-205 — Migrate complex ASCII diagrams to Mermaid**
  spec: — · effort: M · audience: library.maintainer
  ASCII art diagrams in `sdd/`, `guides/`, and `docs-src/` are hard to
  maintain and render poorly. Mermaid renders natively on GitHub and in
  MkDocs via `pymdownx.superfences` (already used in `docs-src/index.md`
  and several `sdd/` research docs). Convert all non-trivial ASCII diagrams; leave simple
  inline flows (single arrows, short sequences) as text.

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

- [ ] **BK-234 — Reconcile `to_key` empty-key / bare-root behaviour across backends**
  spec: NPR-005, NPR-020, NPR-021 · effort: M · audience: library.maintainer
  NPR-020 states the round-trip `to_key(native_path(k)) == k` holds "for
  all valid keys", but for the empty key it contradicts NPR-005. For
  `k == ""`, `native_path("")` returns the bare root (NPR-021); NPR-005
  then says `to_key` returns a path that does not start with `root + "/"`
  unchanged, so `to_key(root) == root`, not `""`. The backends split:
  `S3Backend.to_key` (`_s3_base.py`) and `AzureBackend.to_key`
  (`_azure.py`) follow NPR-005 and return the bare bucket/container;
  `LocalBackend.to_key` and `SFTPBackend.to_key` special-case the bare
  root to `""`. So `to_key(native_path("")) == ""` on Local/SFTP but
  `== root` on S3/Azure — the NPR-001 round-trip invariant fails on
  S3/Azure for the empty key. Decide the contract (amend NPR-005 / NPR-020
  so they agree, then align the four backends) or rule the empty key out
  of the round-trip's domain. ID-190's `NativePathRoundTrip` lemma
  excludes the empty-key / non-empty-root case for this reason. Surfaced
  during ID-190 review.

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

- [ ] **ID-198 — Medallion Dagster + Azure HNS live showcase validation run**
  spec: — · effort: S · audience: library.maintainer, user.api
  The `examples/medallion_dagster/` showcase demonstrates a realistic user journey
  combining Dagster orchestration with an Azure HNS backend, but has never executed
  against a live ADLS Gen2 account. Run the full example end-to-end against real cloud
  infrastructure to surface testing gaps, implementation TODOs, or edge cases that
  conformance and unit tests miss. Async patterns are settled (ID-193 landed,
  see BACKLOG-DONE.md). Findings inform the next release scope; no code changes
  are produced by this item itself.

- [ ] **BK-235 — Record the Azure cassettes for new conformance tests**
  spec: — · effort: S · audience: infra.test
  Sixteen conformance tests self-skip on `azure_replay` because no
  cassette exists yet, so the Azure backend is not actually exercised by
  these gates. Record via `RS_TEST_LIVE_HNS=1 hatch run record-azure`
  against a live ADLS Gen2 account (Stage-3 credentials; per TEST-009
  CI does not auto-record). The recording run on 2026-05-27 (account
  `remotestorehns`) split the worklist into two halves:

  **Record-ready (8 tests, pass against live HNS):**
  - `TestWriteResultConformance::test_metadata_round_trips_through_move_copy` (`move`, `copy`) — BK-195/BK-233
  - `TestDeleteFolderErrorFidelity::test_delete_folder_recursive_no_child_survives` (sync) — ID-184
  - `TestReadErrorFidelity::test_read_under_file_ancestor_raises_not_found` (`read`, `read_bytes`)
  - `TestGetFileInfoErrorFidelity::test_get_file_info_under_file_ancestor_raises_not_found`
  - `TestMoveCopySelfOperation::test_self_op_on_directory_raises_invalid_path` (`move`, `copy`)

  **Blocked on ID-213 (8 tests, fail against live HNS — error class mismatch):**
  - `TestWriteErrorFidelity::test_write_under_file_ancestor_raises_invalid_path` (`write`, `write_atomic`)
  - `TestWriteErrorFidelity::test_open_atomic_under_file_ancestor_raises_invalid_path`
  - `TestDeleteErrorFidelity::test_delete_under_file_ancestor_raises_not_found`
  - `TestMoveCopyErrorFidelity::test_destination_under_file_ancestor_raises_invalid_path` (`move`, `copy`)
  - `TestListFilesCompleteness::test_list_files_non_traversable_ancestor_yields_empty`
  - `TestListFoldersCompleteness::test_list_folders_non_traversable_ancestor_yields_empty`

  Plus async siblings for both halves (the recording aborted before
  Step 3, so async behaviour is unobserved; expected to mirror sync).
  Surfaced during BK-195/BK-233 → ID-184 → ID-209 (each item extended
  the worklist as new self-skipping tests landed); the 2026-05-27 run
  revealed the worklist was bigger than the originating items
  enumerated, and that the ID-209 assumption "HNS has real directories
  so the gate should pass once recorded" only holds for the
  read/get_file_info paths — not write/delete/move/copy/list under a
  file ancestor (ID-213 tracks the fix). The `record-azure` script
  deletes the entire cassette tree before re-recording, so the
  record-ready half cannot ship without the blocked half also
  recording cleanly: BK-235 lands as a single PR once ID-213 closes.

- [ ] **BK-237 — Feature-type DoD checklists in `sdd/000-process.md`**
  spec: — · effort: S · audience: contributor.process
  Codify two complementary feature-DoD checklists in `sdd/000-process.md`,
  derived from the v0.23.0→v0.24.0 post-release retrospective lessons:
  - **Contract-expanding feature** (next: any new `Capability.X`): spec/RFC
    update, capability-declaration review covering over- *and*
    under-declaration, conformance test + xfail registry landed *before*
    first backend implementation, wrapper forwarding check (`ProxyStore`,
    `ObservedStore`, `CachedStore`, sync adapter, oracle adapter), docs
    ripple (`guides/`, `examples/snippets/`, `FEATURES.md`, capabilities
    matrix). The RFC scope must enumerate the conformance / PBT / Dafny
    extensions the feature will need up front, rather than discovering
    them as follow-ups (`feedback_estimation.md` 2-3x rule applied at RFC
    time, not after the fact). ID-146 → ID-151c (eight sub-IDs over two
    weeks for a single feature line) is the cautionary precedent.
  - **Bridge / adapter feature** (next: any future cross-layer wrapper):
    API parity test against wrapped layer, event-loop / resource lifecycle
    test, cancellation invariant test, live backend coverage (not just
    doubles), `filterwarnings = error` clean.
  Closes the pattern-drift risk before ID-127 Graph backend repeats the
  conformance-lag and doc-ripple issues from ID-146. Also surfaces the
  audit-PR pattern (PR #465) as a recommended gate.

- [ ] **BK-238 — Promote `filterwarnings = error` and audit-PR to feature-DoD**
  spec: — · effort: S · audience: contributor.process
  `filterwarnings = error` is enabled globally (PR #495, BK-158) and the
  audit-PR pattern (PR #465) filed 6 pre-release bugs against unreleased
  work. Both proved high-yield in the v0.23.0→v0.24.0 cycle. Codify each
  as a checked step in the feature-DoD landed by BK-237 — no behavior
  change, just process-documentation alignment. Folds into BK-237 if
  both ship in the same PR.

- [ ] **BK-239 — Generic field-vs-capability symmetry check for `WriteResult`**
  spec: — · effort: S · audience: infra.test
  Per-pair under-declaration guards already exist:
  `tests/backends/conformance/test_atomic.py::test_basic_source_leaves_rich_fields_none`
  (lines 157-168) asserts that a backend NOT declaring
  `WRITE_RESULT_NATIVE` leaves `digest` / `etag` / `version_id` /
  `last_modified` as `None`, and
  `test_file_info_metadata_none_when_capability_absent` (lines 252-258)
  does the same for `USER_METADATA`. The gap is that these checks do not
  scale — a new field/capability pair (the next contract-expanding
  feature) can land without a guard. Add a generic conformance assertion
  that iterates every `WriteResult` field and verifies any populated
  value is matched by a declared capability, so future
  field/capability pairs inherit the symmetry automatically (post-v0.23.0
  lessons §4 Pattern 7). Lands before ID-127 to keep the guard generic
  when a new backend joins.

- [ ] **BK-240 — Streaming-iteration counting wrapper for write paths**
  spec: SIO-003 · effort: S · audience: infra.test
  BUG-165 (Azure async materialized payloads), BUG-181 (HNS size
  counting), and `gotcha_async_materialize_antipattern.md` are three
  instances of the same defect: an `AsyncIterable[bytes]` (or
  `Iterable[bytes]`) collected into a single `bytes` before the SDK call.
  The type signature tolerates it, so the bug recurs. Add a conformance
  test that wraps the iterable in a counting iterator and asserts the
  SDK call observes >1 chunk for inputs larger than one chunk —
  failing if the backend materialized. `test_streaming.py:120-125`
  (SIO-003) checks BinaryIO support; this extends to the iterable
  contract on both sync and async write paths.

- [ ] **BK-241 — `tests/aio/README.md` orientation for next async backend**
  spec: — · effort: S · audience: contributor.process, infra.test
  Async test infra is now mature (ID-153, BK-164, ID-155, ID-156, ID-157,
  ID-158, ID-193). The next async backend (ID-127 Graph) needs a single
  landing page that names the conftest layout, doubles in `tests/aio/_doubles.py`,
  the `AsyncBackendSyncAdapter` parametrization, and the live-vs-doubles
  layering — so it does not repeat the conftest sprawl that BK-164 and
  ID-156 cleaned up. One short README (or an addendum to `sdd/TESTING.md`,
  whichever fits the docs framework better) is enough.

- [ ] **BK-242 — Flat-NS file-ancestor pre-check perf (SQLBlob IN-list, memoisation)**
  spec: — · effort: S · audience: infra.test, library.maintainer
  ID-211 review surfaced two perf optimisations the disposition (b)
  opt-in didn't ship. Bundle here so they don't get lost:
  - **SQLBlob `WHERE key IN (ancestors)`**: today `_head_one` issues one
    `SELECT 1` per ancestor — N round trips for a depth-N path. The
    research note (`sdd/research/research-id-211-flat-ns-file-ancestor-precheck.md`
    § 5.4) already flagged this; a single `SELECT key FROM table WHERE
    key IN (:ancestors)` collapses the walk to one RTT. On in-memory
    SQLite the win is sub-ms; on PostgreSQL/MySQL over the network at
    depth 6 it is 6 RTTs → 1 RTT (~10-50 ms each).
  - **`head_one` memoisation**: bulk-write workloads (`a/b/c/file-{i}.bin`
    for i in 1..N) re-HEAD the same `a`, `a/b`, `a/b/c` ancestors N
    times. A bounded per-instance `TTLCache(maxsize=…, ttl=…)` on the
    closure collapses O(N×D) HEADs to ~O(D) per distinct prefix without
    changing the contract (the TTL accepts staleness within its window).
    Applies to S3, S3PyArrow, Azure non-HNS, and SQLBlob.
  Both are perf optimisations that don't change the gate's contract —
  ship behind the existing `reject_write_under_file_ancestor=True`
  opt-in only. Includes refreshing `§ 4` / `§ 5.4` in the research note
  with measured before/after numbers. Touches
  `src/remote_store/backends/_flat_ns.py`,
  `src/remote_store/backends/_sqlalchemy.py`,
  `src/remote_store/backends/_s3.py`,
  `src/remote_store/backends/_s3_pyarrow.py`,
  `src/remote_store/backends/_azure.py`,
  `src/remote_store/aio/backends/_azure.py`. Discovered in PR #686 review.

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
