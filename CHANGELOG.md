# Changelog
<!-- doc: dual dest=reference/changelog.md -->

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor bumps may contain breaking changes.

## [Unreleased]

### Fixed

- BUG-182: live ADLS Gen2 (HNS) integration test confirming `AzureBackend.write_atomic` user metadata survives the atomic-rename commit (`tests/backends/test_azure_live_hns.py::TestAzureLiveHnsMetadataSurvivesRename`); closes the verification gap left by BUG-181's mock-only coverage (WR-013, BE-010).
- BUG-191: live ADLS Gen2 (HNS) integration test class covering the `write`/`write_atomic`/`open_atomic` directory-path guards on a real account, complementing the mock-only coverage from BUG-190/BUG-192. Gated by the new `live` pytest marker (excluded by default `addopts`), `RS_TEST_LIVE_HNS=1`, and a non-Azurite `AZURE_STORAGE_CONNECTION_STRING` (BE-021, BE-008, BE-010, SAW-001).
- BUG-192: `AzureBackend.open_atomic` now raises `InvalidPath` (not `AlreadyExists`) when the target is an HNS directory; both `overwrite=False` and `overwrite=True` are covered (BE-021).
- BUG-190: `AzureBackend` and `AsyncAzureBackend` now raise `InvalidPath` (not `AlreadyExists`) when `write` or `write_atomic` targets an HNS directory path; both `overwrite=False` and `overwrite=True` are covered (BE-008, BE-010, ASYNC-008, ASYNC-010, BE-021, ASYNC-024).
- BK-174: document `InvalidPath` on async `write`/`write_atomic` across the `AsyncBackend` ABC, `SyncBackendAdapter`, and `AsyncMemoryBackend.write_atomic`; bundle the matching `--` → `—` swap in `AsyncBackend.delete_folder` and add `write_atomic(dir)` regression coverage (ASYNC-010) to the async conformance suite. `AsyncAzureBackend` carved out as **BUG-190** — runtime does not uphold the canonical mapping on HNS directories.
- BK-173: complete the four-layer async docstring ripple by adding `Raises:` clauses to nine I/O methods on `SyncBackendAdapter`, mirrored from the `AsyncBackend` ABC; surfaces in `help()` and IDE hover today.
- BUG-189: `AsyncMemoryBackend` now mirrors the sync `MemoryBackend` error
  fidelity for type-mismatched paths. `read`, `read_bytes`, and
  `get_file_info` raise `InvalidPath` (not `NotFound`) when the path names
  an existing directory; `get_folder_info` raises `InvalidPath` when the
  path names an existing file; `delete_folder` raises `InvalidPath` when
  the path is a file (regardless of `missing_ok`); `move`/`copy` raise
  `InvalidPath` when the source is a directory; `copy(src, src,
  overwrite=False)` is now a no-op instead of raising `AlreadyExists`.
  Discovered by porting the extended conformance suite to async (see
  `tests/aio/test_async_conformance_extended.py`); `AsyncBackend` ABC
  docstrings updated to document the `InvalidPath` paths
  (ASYNC-006 / ASYNC-007 / ASYNC-013 / ASYNC-016 / ASYNC-017 / ASYNC-018 /
  ASYNC-019).
- BUG-188: benchmark SVG images no longer broken on the performance docs page
- BUG-187: EthicalAds ad no longer floats over graph viz canvas
- BUG-186: render API graph viz on iOS Safari

### Added

- Azure HNS account setup guide (`docs-src/guides/backends/azure-hns-setup.md`): step-by-step `az` CLI recipe for provisioning an ADLS Gen2 account suitable for the live HNS test suite, with cross-links from the Azure backend guide and `CONTRIBUTING.md`.
- ID-176: `docs-src/context7.json` — claims `https://docs.remotestore.dev/stable/` on context7 and supplies the full `rules` array so AI tools surface correct usage context from the rendered docs site.
- BK-171: Reliable link validation for docs-only files — universal on-disk
  link rule (DOCFRAME-008). `mkdocs_hooks.py` applies `LinkResolver` to
  every docs-src file at build time so authors write on-disk paths
  everywhere; `check-links` collapses to a single mode that walks every
  git-tracked `.md`. SDD kind rules hoisted to
  `docs-src/_path_rules.yml`. Closes audit-012 F-01 honestly.
- BK-172: route S3-PyArrow conformance tests to MinIO on pyarrow ≥ 24; lift `pyarrow<25` cap on `s3-pyarrow` extra
- BK-169: unit tests for DOCFRAME-004 gate — five spec-traced pytest tests in
  `tests/scripts/test_check_docs_framework.py` covering G-02 (dest collision),
  G-03 (Jinja syntax), G-04 (include-markdown), G-05 (broken relative link),
  G-06 (nav URL misalignment)
- BK-168: lift `pyarrow<24` to `<25` across all extras; require `moto[server,s3]>=5.2.0` for multipart compatibility under pyarrow 23
- BK-167b: docs framework bridge — `scan_dual_files` + `render_dual_pages`, `explanation/design/` URL alignment, nav restructure, `--strict` CI gate restored, audit-012 closed
- BK-167b: `check_links.py` — two-mode internal link checker (`--mode repo`/`--mode site`); `hatch run check-links`
- BK-167a (Step 1): `scan_dual_files`, `DualEntry`, `_parse_marker`, `_classify_file` in `scripts/docs/scan.py`; five spec-traced tests (DOCFRAME-001..003)
- BK-167a: ADR-0027, Spec 047 (docs framework tooling contracts), `sdd/AUTHORING.md`
- **End-to-end coverage for the S3 control path** (BK-166, S3-026, S3PA-026):
  `tests/backends/test_s3_moto.py` drives a full lifecycle
  (`write` / `list_files` / `read` / `delete`) for both `S3Backend` and
  `S3PyArrowBackend` against a `ThreadedMotoServer` with the same tuned
  `client_options` shape that triggered BUG-178 and BUG-185
  (`s3.addressing_style="path"`, cleared proxies, custom timeouts; with
  and without `RetryPolicy`). Nothing in the test patches the production
  code path, so a regression in the `config_kwargs` routing surfaces as a
  real `TypeError: got multiple values for keyword argument 'config'`
  from `aiobotocore`. Runs in the default suite (`hatch run test`) so a
  regression is caught without remembering a separate command — the gap
  BUG-178 and BUG-185 fell through. Complements the unit-level
  `TestAiobotocoreCreateClientBoundary` (kwarg shape) with wire-level
  behavior. `moto[server,s3]` was already pinned in `[dev]`; no new
  dependencies.

## [0.24.1] - 2026-04-30

### Added

- **`CAPABILITIES: ClassVar[CapabilitySet]` on every backend and ABC** (ID-159, BE-003):
  `Backend`, `AsyncBackend`, all built-in backends, and `SyncBackendAdapter` now declare a
  class-level `CAPABILITIES` attribute exposing the capability set without requiring
  instantiation. The `capabilities` property delegates to `self.CAPABILITIES` so the
  class view and the instance view always agree. Conformance tests enforce
  `instance.capabilities <= Cls.CAPABILITIES` for every backend; for `SQLBlobBackend`,
  `CAPABILITIES` is the upper bound and narrow-column schemas may yield a strictly
  smaller instance set. Custom backends should follow the same pattern (see
  `docs-src/guides/custom-backend-guide.md`).
- **`_GATING: dict[str, Capability]` in `_store.py`** (ID-159):
  Single source of truth for the method → capability mapping read by `Store._gate()`.
  Replaces the previous scattered gate logic; the new `_BACKEND_GATING: dict[str, str]`
  in `scripts/gen_graph.py` plays the same role for `Backend`.
- **`__mirror__: ClassVar[type[...]]` on async backends** (ID-159):
  `AsyncMemoryBackend` and `AsyncAzureBackend` now point at their sync peer via
  `__mirror__`, enabling static extraction of `mirrors` edges in the API graph.
- **RFC-0012 — Documentation Graph Model** (ID-159, accepted): graph schema, snapshot
  rules, and projection contract for the `graph.json` artifact and downstream
  generators.
- **Documentation API graph generator** (`scripts/gen_graph.py`, ID-159): emits
  `docs-src/_data/graph/graph.json` with capability/class/extra/method/requirement/package
  nodes and declares/gates/of/enables/mirrors/inherits edges. Method nodes carry
  `is_abstract`, `is_async`, `file`, `line` (schema 1.1, ID-164); `mirrors` edges
  carry `capability_delta: {async_only, sync_only}` so consumers can render sync↔async
  asymmetries — e.g. `AsyncMemoryBackend` declares `LAZY_READ`; `MemoryBackend` does
  not, so the edge reports `async_only: ["LAZY_READ"]` (schema 1.2, ID-162).
  `source_version` and `snapshot` are read from `pyproject.toml`, not hardcoded
  (ID-163). `gen-graph` / `gen-graph-check` hatch scripts.
- **`FEATURES.md` projection from API graph** (`scripts/gen_features.py`, ID-163):
  regenerates the mechanical sections (`backends_main`, `backends_flags`,
  `install_extras`) from `graph.json` between `<!-- BEGIN_GENERATED -->` /
  `<!-- END_GENERATED -->` markers; rows are sorted alphabetically (ID-169) instead
  of by source-file declaration order. `gen-features` / `gen-features-check` hatch
  scripts; release Phase 2 runs `gen-graph` then `gen-features` after
  `bump-my-version`.
- **API-docs verifier** (`scripts/check_api_docs.py`, ID-170, ID-171): walks
  `graph.json` and `docs-src/api/store.md` / `backend.md` in parallel through the
  same canonical mapping `{method: frozenset(required_capabilities)}` and flags missing
  `:::` directives or capability admonitions that drift from `_GATING` /
  `_BACKEND_GATING`. First catch: a `!!! note "Requires Capability.GLOB"` admonition
  placed before `::: Store.glob` in `store.md` — moved per the file's own
  placement-rule comment. `gen-api-check` hatch script wired into the CI lint job.
- **Interactive graph visualisation** (`scripts/gen_graph_viz.py`, ID-165):
  self-contained D3 v7 force-directed HTML rendered from `graph.json` and committed
  at `docs-src/_data/graph/graph_viz.html`. Nodes are colour-coded by kind; edges
  styled by type with directional arrowheads; abstract methods are dashed; async
  methods carry a small badge. Sidebar filter checkboxes, click-to-inspect detail
  panel, drag/zoom/pan. `gen-graph-viz` / `gen-graph-viz-check` hatch scripts.
- **`scripts/check_test_placement.py`** (ID-168): AST-based lint check enforcing the
  test subpackage placement rule formalised in `sdd/TESTING.md` § Test Subpackage
  Placement. Wired into the `lint` CI job and the `check-test-quality` hatch script.
- **`scripts/check_tla_no_emdash.py`**: CI guard rejecting non-ASCII em dashes in
  TLA+ and Dafny formal files; TLC's lexer treats U+2014 as a hard error.

### Fixed

- **`S3Backend(client_options={"client_kwargs": {"config": Config(...)}})` raised
  `TypeError: got multiple values for keyword argument 'config'`** (BUG-185):
  s3fs's `set_session()` always calls
  `aiobotocore.create_client("s3", config=AioConfig(**self.config_kwargs), **client_kwargs)`,
  so any `client_kwargs["config"]` injected by the BUG-178 fix duplicated `config=`.
  Reproduced on s3fs 2026.3.0 against an internal MinIO-style endpoint requiring
  `s3.addressing_style="path"` and `proxies={http: None, https: None}`. Fixed by
  routing every `botocore.config.Config` option through `opts["config_kwargs"]`
  (a plain dict of `Config(...)` constructor kwargs); `client_kwargs["config"]` is
  never set, and a caller-supplied pre-built `Config` in `client_kwargs` is rejected
  at backend construction with `ValueError` pointing at the supported channel.
  Silent rewriting hid both this bug and BUG-178 and is no longer permitted. Spec
  S3-026 / S3PA-026 rewritten. Tests added at the actual collision boundary
  (`TestAiobotocoreCreateClientBoundary` patches
  `aiobotocore.session.AioSession.create_client` and triggers `s3fs.connect()`),
  so a future variant of the same bug class fails the unit suite. New "Botocore
  Client Tuning" section in `docs-src/guides/backends/s3.md` documents proxies,
  retries, timeouts, and MinIO path-style addressing; runnable snippets in
  `examples/snippets/s3_botocore_tuning.py` are wired into `tests/test_snippets.py`
  and the examples gate. Follow-up moto-backed e2e coverage tracked as BK-166.
  **Migration:** callers that passed a pre-built `botocore.config.Config` via
  `client_options={"client_kwargs": {"config": Config(...)}}` must switch to
  `client_options={"config_kwargs": {...}}` (a plain dict of the same `Config(...)`
  constructor kwargs). The old form raised `TypeError` at first I/O on s3fs ≥ 2024.x
  already; it now fails fast with `ValueError` and a message naming the supported
  channel.

### Changed

- **Documentation filesystem reorganised along Diátaxis** (ID-174): All prose moved
  from `guides/` and the repo root into `docs-src/<bucket>/` (`how-to`,
  `explanation`, `reference`, `further`); the intermediate `docs/` layer was
  collapsed and removed in the same release. Cross-bucket links across
  `docs-src/api/` stubs, extension stubs, 26 example docstrings, and
  `scripts/docs/render.py` were updated; absolute GitHub URLs are now used for
  links to repo files outside `docs-src/` (sdd/, CONTRIBUTING.md). `mkdocs build
  --strict` passes with 0 warnings. **Bookmarks to specific guide URLs may need
  updating.**

### Internal

- **Async backends moved into `aio/backends/` subpackage** to mirror the sync
  `backends/` layout. Public imports through `remote_store.aio` and
  `remote_store.aio.backends` are unchanged; only direct imports of private modules
  (e.g. `remote_store._async_memory`) are affected.
- **Test subpackage consolidation** (ID-166, ID-167, ID-168): `tests/test_gen_graph.py`
  → `tests/scripts/test_gen_graph.py`, `tests/backends/test_dafny_classorder.py` →
  `tests/scripts/test_dafny_classorder.py`, `tests/test_gen_features.py` →
  `tests/scripts/test_gen_features.py`; `ROOT` anchors corrected for the new depth.
- **Context7 indexing** (ID-160): `context7.json` schema fixes; library registered
  at `/haalfi/remote-store` (691 snippets, source-reputation High, benchmark score
  91.3, version 0.24.0; verified 2026-04-29).
- **CodeQL `py/overly-complex-delete` alert #55**: `AsyncAzureBackend.__del__`
  refactored to delegate the open-clients check to a new private
  `_has_open_clients()` helper.
- **TLA+ toolchain pinning**: `tla2tools.jar` pinned to v1.7.4 in `ci.yml`,
  `tlc.Dockerfile`, and `scripts/tlc_check.sh` (v1.8.0 was a pre-release with
  inconsistent checksums); em dashes removed from TLA+ and Dafny formal files.

## [0.24.0] - 2026-04-26

### Added

- **`WriteResult`: write methods return rich metadata; `Store.head()`; user metadata; hashing helpers; async parity** (ID-146, ID-148, ID-013b):
  The entire write surface now returns a structured result and accepts optional user metadata.

  - **`WriteResult` dataclass** — every `write*()` call returns `WriteResult(path, size, source,
    digest, etag, version_id, last_modified, metadata)`. `source` signals origin:
    `NativeSource` (from the backend's write response), `BasicSource` (from a post-write stat),
    or `SidecarSource` (from `ext.write`). Two new capabilities gate the rich fields:
    `WRITE_RESULT_NATIVE` (backend populates `etag`, `digest`, `version_id`, `last_modified`
    from its own response) and `USER_METADATA` (caller-supplied `metadata=` is persisted).
  - **`Store.head(path)`** — retrieves file metadata as a `WriteResult` without reading content;
    gated on `Capability.METADATA`.
  - **`ext.write`** — `write_with_hash` and `open_atomic_with_hash` guarantee a client-side
    SHA-256 digest in `WriteResult.digest` regardless of whether the backend declares
    `WRITE_RESULT_NATIVE`; suitable for integrity-critical pipelines.
  - **Async parity** — `AsyncStore.write*()` and `AsyncBackend.write` / `write_atomic`
    return `WriteResult` and accept `metadata=`; `Capability.USER_METADATA` enforced at the
    `AsyncStore` layer; `aio.ext.write.write_with_hash` mirrors the sync helper.
  - **Proxy forwarding** — `ProxyStore`, `ObservedStore`, and `CachedStore` all forward
    `WriteResult` and `head()`; `StoreEvent.metadata["write_result"]` is populated on
    successful writes.
  - Docs: Write Integrity guide; RFC-0011 (Implemented).

- **`AsyncBackendSyncAdapter`** (ID-141–143c): new public class wrapping any
  `AsyncBackend` as a synchronous `Backend` via a private event loop on a
  dedicated daemon thread. Design in ADR-0025; spec 029 § AsyncBackendSyncAdapter
  (ASYNC-080…093) covers streaming read/list pumps, write bridging, `open_atomic`
  synthesis, capability translation, fail-fast guard for running-loop callers,
  bounded shutdown, and GC-path cleanup (`_ChunkPullReader` as `io.RawIOBase`;
  best-effort `__del__` on `_AsyncIteratorBridge`). Full unit suite in
  `tests/aio/` (every test traced to spec IDs), Azurite-backed integration suite
  for the full sync `Backend` contract, and bridged-Azure variant in the e2e
  streaming chain. Decision guide: `guides/async-sync-bridges.md`. Unblocks
  ID-127 (Graph backend).

### Fixed

- **`AsyncMemoryBackend.delete` raises `InvalidPath` for directory paths** (BUG-184):
  When a directory path was passed with `missing_ok=True`, the backend silently returned
  instead of raising `InvalidPath` — diverging from sync `MemoryBackend` (BE-012) and
  spec `ASYNC-012`. Fixed by inserting the `isinstance(existing, _DirNode)` guard mirrored
  from `_memory.py:204-205`; spec `ASYNC-012` tightened to pin the outcome; the PBT guard
  that previously suppressed the directory-path case is removed.

- **s3fs lazy init raises `got multiple values for keyword argument 'config'`** (BUG-178):
  When `client_options={"config_kwargs": {...}}` and `retry=RetryPolicy(...)` were both supplied,
  `aiobotocore.create_client()` received two `config=` arguments. Fixed by extracting
  `_S3Base._build_s3fs_kwargs()`, which merges `config_kwargs` into a single
  `botocore.config.Config` before the retry-derived config is applied; both `S3Backend` and
  `S3PyArrowBackend` delegate to the shared builder.

- **`SQLBlobBackend.glob` drops zero-segment `**/` matches on SQLite** (BUG-175):
  SQLite's `GLOB` operator treated `**` as two independent `*`s and required a literal `/`
  between them, dropping zero-directory-depth matches. Replaced with `extract_prefix` +
  `LIKE` narrowing; the existing Python regex handles final filtering.

- **`SQLBlobBackend.copy(src, src)` no longer silently destroys data** (BUG-176):
  `copy()` lacked the `src == dst` early-return guard that `move()` has. With
  `overwrite=True` the single row was deleted before the `INSERT ... SELECT`
  ran, destroying the file; with `overwrite=False` the method incorrectly
  raised `AlreadyExists`. Fixed by mirroring `move()`'s guard at the top of
  `copy()`: verify source exists, then return immediately.

- **`AsyncAzureBackend.write` streaming** (BUG-165): `write` and
  `write_atomic` materialized any `AsyncIterable[bytes]` payload into a
  single `bytes` buffer before calling `upload_blob` / `upload_data`,
  holding the entire file in memory and breaking the streaming contract
  (SIO-003, ASYNC-021). The async iterator is now passed through — the
  Azure SDK accepts `AsyncIterable[bytes]` directly and streams it in
  bounded memory.

- **Docs pages deployment on release tags** (BUG-164): `pages` job moved to a
  dedicated `gh-pages-deploy.yml` workflow triggered by `workflow_run` on `Docs`
  completion. Eliminates the `github-pages` environment protection rule failure
  when `docs.yml` ran in a tag ref context on release events.

### Changed

- **pyarrow 24.x mypy compatibility** (BK-154): pyarrow 24.0.0 shipped partial
  type stubs that surfaced `attr-defined`, `name-defined`, and `no-untyped-call`
  errors under mypy strict mode. Added `follow_imports = "skip"` for
  `pyarrow`/`pyarrow.*` in `pyproject.toml`, restoring pre-24 behaviour where
  all `pa.*` resolves as `Any`. Removed the now-redundant
  `# type: ignore[import-untyped]` annotations on pyarrow imports in
  `ext/arrow.py`, `ext/parquet.py`, `backends/_s3_pyarrow.py`, and
  `backends/_sqlalchemy.py`.

### Documentation

- **Documentation gaps from Audit-011 resolved** (BK-162): Fixed 16 findings across four areas —
  custom-backend guide and snippet updated for `WriteResult` return type, `metadata=` kwarg, and
  new capability descriptions (`USER_METADATA`, `WRITE_RESULT_NATIVE`, `LAZY_READ`); `async.md`
  gained a Write Results section, `aio.ext.write` prose, and an Async-Sync Bridges cross-reference;
  `extensions.md` added the `aio.ext.write` table row and import stubs; `s3.md`, `azure.md`, and
  `local.md` received Write Results sections and corrected `USER_METADATA` claims. Audit report:
  `sdd/audits/audit-011-docs-v023-gaps.md`.

- **SFTPGo compatibility note in README and SFTP guide**: documents SFTPGo as a zero-dependency
  SFTP server for local development and CI, with a comparison table against OpenSSH-server.

- **Backend-specifics visibility in API reference** (BK-153): added a three-tier admonition
  vocabulary (info/note/warning) across all `docs-src/api/` pages — capability-gate notes on
  B-series methods, backend-conditional argument notes on `metadata=` and `max_depth=`, conditional
  field notes on `FileInfo`, `WriteResult`, `FolderInfo`, and `BackendConfig.options`, and
  interop-section warnings on `Backend`, `AsyncBackend`, `AsyncStore`, `ProxyStore`,
  `ReadOnlyHttpBackend`, and `SFTPUtils`. Vocabulary documented in `sdd/DOCUMENTATION.md`.
  Closed all 20 findings from audit-009.

- **Docs site spacing and typography** (BK-157): custom CSS reduces whitespace across all pages —
  table cell padding halved, headings follow the classic generous-above/tight-below asymmetry,
  parameter/returns blocks and bullet lists are compact, adjacent heading-before-method gaps
  collapsed.

- **Content rule 6 — code examples are sourced, not written** (ID-144):
  codifies the existing `examples/snippets/` practice (ID-057, ID-106) in
  `sdd/CONTENT-RULES.md` so future doc PRs pull tested snippets rather than
  hand-writing fences.

- **Formal-layer principles: Dafny vs TLA+** (ID-147): rewrites
  `sdd/formal/README.md` around the repo's stance — Dafny for
  per-operation contracts, TLA+ for cross-layer protocol properties,
  decoupled rather than embedded. Adds the spec-decomposition
  authoring rule (write the TLA+ invariant first on multi-conjunction
  spec items) and four authoring rules (stand-alone modules,
  demonstrated bundling, CI-informational with cadence-based revisit,
  promotion gated on a real regression catch).

- **OBS-003 step 6 outcome clarification** (ID-147): spec 019 step 6/7
  now state explicitly that `on_<op>` and `on_any` fire regardless of
  outcome, cross-referencing OBS-004. Matches existing code and tests;
  removes a drift surfaced by the OBS-003 hand-decomposition exercise
  (`sdd/research/research-id-147-obs003-decomposition.md` § 2).

- **`Observer.tla` and informational `verify-tla` CI** (ID-147): starts
  the live informal TLA+ layer under `sdd/formal/tla/` with
  `Observer.tla` — six invariants covering OBS-003 step 6/7 and
  OBS-003a dispatch routing, each paired with a break-and-catch row
  confirming orthogonality of the seeded mutations (the module is an
  *authoring* artefact per `sdd/formal/README.md` rule 3 — TLC on MC3
  holds vacuously on the unmutated spec, so the CI job catches future
  edits to the model, not regressions in `observe.py`; see module
  header *Scope caveat* for the OBS-009 gap). The
  `sdd/research/tla-poc/` tree stays as the frozen 2026-04 PoC
  artefact. `.github/workflows/ci.yml` gains a non-blocking
  `verify-tla` job (pinned `tla2tools.jar@v1.8.0`, SHA-256 verified)
  that runs MC3 from the live layer. Status revisit tracked as
  ID-150 for 2026-10-19.

### Internal

- **`test_streaming_integrity` SFTP→Azure pipe-threshold adjusted** (BUG-174):
  `PIPE_THRESHOLD` raised 1.5 MiB → 2.25 MiB. Root cause is a tracemalloc attribution
  artifact — Azure SDK's staged-block uploader holds two 1 MiB chunks live simultaneously
  when the source is wrapped in `io.BufferedReader`; revised ceiling reflects the two-chunk
  hold plus headroom. No production-code change.

- **Async test coverage expansion** (ID-155, ID-156, ID-157, BK-164): four new modules under
  `tests/aio/` targeting async-specific concerns absent from the existing suite.
  `test_async_pbt_stateful.py` (ID-155) — `RuleBasedStateMachine` driving `AsyncMemoryBackend`
  and `SyncBackendAdapter(MemoryBackend())` in lock-step against a shared model; surfaced BUG-184.
  `test_sync_adapter_conformance.py` extended with live `S3/moto`, `SFTP`, and `Azurite` fixtures
  (ID-156) so `AsyncBackendSyncAdapter` is exercised against real SDKs and connection pools.
  `test_async_azure_live.py` (ID-157) — 17 Azurite-backed tests covering ETag/`last_modified`
  propagation, chunked download, `USER_METADATA` round-trip, and HNS `write_atomic`.
  `test_async_drift.py`, `test_async_adapter_unit.py`, `test_async_error.py` (BK-164) — API-parity
  guard against the sync surface, executor-boundary unit tests, and error-passthrough assertions.

- **Async e2e streaming integrity test** (ID-138): `tests/e2e/test_async_streaming_integrity.py`
  validates a five-hop async chain (`AsyncMemoryBackend` → `AsyncAzureBackend` (Azurite) →
  `AsyncMemoryBackend` → `SyncBackendAdapter(LocalBackend)` → `AsyncMemoryBackend`) with per-hop
  SHA-256 verification. Falls back to a no-Azurite chain when the service is unavailable.

- **HNS `write_atomic` WriteResult parity tests** (BUG-181): four mock tests added to
  `TestAsyncAzureHNSPaths` covering rich-field population from `get_file_properties()`;
  `version_id`/`digest` confirmed `None` on HNS (ADLS Gen2 `PathProperties` does not surface
  these); `metadata=` forwarding to pre-rename `upload_data`; `overwrite` mode guards.

- **pytest-asyncio event-loop leak and `ResourceWarning` fixes** (ID-158, BUG-180):
  session-scoped `_close_leaked_event_loops` fixture closes orphaned loops before GC at teardown,
  eliminating the `ResourceWarning` promoted to error by BK-158. Companion fix:
  `UrllibTransport._request()` wraps the caught `HTTPError` in `contextlib.closing()` so the
  file descriptor is released before GC on Python 3.14.

- **PBT `BackendModel` tracks empty directory nodes** (BUG-183): `BackendModel` in
  `test_pbt_stateful.py` derived implicit dirs from the live-file map, forgetting nodes after the
  last file was deleted and diverging from `MemoryBackend`'s MEM-DS-006 dir-retention semantics.
  Fixed with a separate `self.dirs` set; `delete_folder` rule added. No production-code change.

- **Test fixture and duplication consolidation** (ID-153, BK-156, BK-163): `_free_port`,
  `moto_server`, `azurite_server`, and availability helpers promoted to root `tests/conftest.py`,
  eliminating cross-boundary imports. ~110 duplicate conformance tests removed from `test_sftp.py`,
  `test_azure.py`, and `test_sqlblob.py`. Five shared S3/S3-PyArrow invariants extracted to
  `test_s3_shared.py`.

- **Extension import-path contract** (BK-160, BK-161): Rule 12 added to `sdd/DESIGN.md` requiring
  extensions to use public import paths when one exists. `test_no_private_module_imports` AST
  checker enforces it; 10 private-path imports fixed across 10 modules; 3 justified exceptions
  documented with inline comments.

- **`filterwarnings = error` in pytest** (BK-158): unhandled warnings now fail the suite;
  existing SQLAlchemy suppressors retained with inline justification.

- **S3 and S3-PyArrow test and spec consolidation** (BK-155): shared invariants extracted to
  `tests/backends/test_s3_shared.py`, parametrized over both backends with per-param
  `pytest.mark.spec(...)` marks preserving `S3-NNN` and `S3PA-NNN` traceability;
  Category-1 conformance duplicates removed from `test_s3.py` and `test_s3_pyarrow.py`.

- **Dafny `WriteResult` — `last_modified` spec-opacity closed** (ID-152):
  `MemoryBackend.dfy:Write` returns a capability-conditional timestamp witness (`Some(0)` when
  `CapWriteResultNative in capabilities`) instead of the hardcoded `Option_None()`. Adapter at
  `tests/backends/dafny_oracle.py` lifts `Some(n)` to `datetime.fromtimestamp(n, tz=timezone.utc)`.

- **Hypothesis property coverage for `WriteResult`** (ID-151c): adds
  `tests/test_pbt_write_result.py` with two property tests on top of
  `TestWriteResultConformance`.  The first exercises
  `WriteResult.size == len(payload)` on `MemoryBackend` (small regime) and
  `LocalBackend` (256 KiB – 1 MiB BUG-168 buffer boundary — the only v1
  backend whose write path runs through a real `BufferedWriter`) across
  `bytes` / `BinaryIO` inputs and `overwrite=True` / `overwrite=False`.  The
  second exercises WR-012 echo + WR-013 `get_file_info` round-trip on the two
  backends that go through a real SDK serialisation layer (S3 via `moto`
  server mode; Azure via Azurite when reachable).  Strategies are
  module-scope and WR-011-compliant; profiles inherit from
  `tests/conftest.py` (dev 50 / ci 100 / nightly 1000).

- **Retired per-backend `WriteResult` test duplication** (ID-151b): removed
  `TestLocalWriteResult`, `TestSFTPWriteResult`, `TestS3PyArrowWriteResult`,
  and the generic `write` / `write_atomic` / size / metadata-echo methods from
  `TestS3WriteResult`, `TestAzureWriteResult`, and
  `TestAzureWriteResultIntegration`. All removed cases are now covered by
  `TestWriteResultConformance`. Azure- and S3-specific SDK-level assertions
  (etag stripping, version_id, digest, metadata-passed-to-SDK, HNS atomic
  path, capability declarations, Azurite etag / last_modified wire checks)
  are retained.

- **Dependabot auto-merge workflow hardening**: restores the
  `github.repository == 'haalfi/remote-store'` guard, removes the unused
  `dependabot/fetch-metadata` step, switches the merge command to
  `--squash --delete-branch`, adds a per-PR `concurrency` group, and
  guards on `pull_request.state == 'open'`. Header comment documents the
  intentional `pull_request_review` trigger and the recovery path for
  PRs that miss the workflow window.

- **`MemoryBackendMinimal` satisfiability witness** (ID-151, part 4): adds a
  sibling refinement class to `sdd/formal/MemoryBackend.dfy` that declares
  neither `CapWriteResultNative` nor `CapUserMetadata`. This makes the
  WR-010 `CapabilityNotSupported` gate live code (not dead code as in
  `MemoryBackend`) and forces `wr_source` to `BasicSource` on every
  successful write — closing the refinement coverage gap flagged in the
  part-1 review. `bash scripts/dafny_verify.sh MemoryBackend.dfy` passes
  with 98 verified, 0 errors.

- **`DafnyOracleBackend` adapter widening** (ID-151, part 5): `write()` and
  `write_atomic()` in `tests/backends/dafny_oracle.py` now accept a
  `metadata=` kwarg and return `WriteResult`, matching the Part-1 ABC.
  `get_file_info()` and `list_files()` now marshal the Dafny `FileInfo.metadata`
  field. All `TestWriteResultConformance` skips on `dafny-oracle` are removed;
  `test_native_populates_last_modified` is xfailed (BUG-169 parity — the Dafny
  `MemoryBackend.Write` hardcodes `Option_None()` for `last_modified`).

- **Python WR-* conformance assertions** (ID-151, part 3): adds
  `TestWriteResultConformance` in `tests/backends/test_conformance.py`,
  exercising every backend's `write` / `write_atomic` return value against
  the Dafny `Write` postconditions in `sdd/formal/BackendContract.dfy`
  (spec 045 WR-001a, WR-004, WR-005, WR-012, WR-013). Rich-field checks
  are gated on `Capability.WRITE_RESULT_NATIVE`; metadata checks are gated
  on `Capability.USER_METADATA`. The new fixture-level assertions surface
  two pre-existing backend defects as strict `xfail`s — BUG-169
  (`MemoryBackend` drops `last_modified`) and BUG-170 (`SQLBlobBackend`
  drops `last_modified`) — so fixing each bug flips the xfail and forces
  the `xfail` marker off in the same commit.

- **Dependabot auto-merge workflow**: adds
  `.github/workflows/dependabot-auto-merge.yml`. On approval of a
  Dependabot PR by the repo owner, enables GitHub auto-merge (squash);
  GitHub merges automatically once the `gate` check passes.

- **Dafny `WriteResult` oracle regeneration + adapter update** (ID-151,
  part 2): `scripts/dafny_translate.sh` Docker wrapper (analogous to
  `scripts/dafny_verify.sh`) translates Dafny specs to Python using
  `dafny build -t py` without a native Dafny install. Companion
  `scripts/_dafny_classorder.py` automates the previously manual class
  reorder (ADT types → `Backend` → `default__` → `MemoryBackend`) so
  `module_.py` imports cleanly. Regenerates `MemoryBackend-py/` under
  the Part 1 contract (Dafny 4.11.0, matching the verify pin), and
  `DafnyOracleBackend` now passes `Option_None()` for the new fourth
  `metadata` parameter on `Write`. Oracle-gated conformance run green
  (154 passed, 5 skipped). Follow-up remainder in `BACKLOG.md`:
  `MemoryBackendMinimal` satisfiability witness for the
  `CapabilityNotSupported` / `BasicSource` branches.

- **Dafny `WriteResult` extension** (ID-151, part 1): widens the Backend
  trait `Write` to return `Result<WriteResult>` with a fourth `metadata`
  parameter, adds `FileInfo`/`WriteResult`/`ContentDigest`/`WriteSource`
  data models, `CapWriteResultNative` and `CapUserMetadata` capabilities,
  and the `WriteResultFromFileInfo` function plus the `WR008FieldMapping`
  lemma. Encodes WR-001a, WR-004, WR-005, WR-010 (with the
  empty-mapping carve-out via `HasUserMetadata`), WR-012, and WR-013 as
  Write postconditions; the WR-006 negative direction (Write never
  produces `SidecarSource`) is enforced structurally by the `Write`
  postcondition restricting `source` to `NativeSource | BasicSource`.
  `MemoryBackend` refines the widened contract.

- **`scripts/gen_pages.py` refactor**: split the 840-line mkdocs-gen-files hook
  into `scripts/docs/{scan,render,nav,link}.py` plus a 70-line orchestrator;
  example metadata and link rewrites are now data-driven via `SddKind`,
  self-describing example docstrings, and `LinkResolver`.

- **Microsoft Graph backend — SDD artifacts** (ID-127): accepted
  `sdd/rfcs/rfc-0010-graph-backend.md`, ADRs `sdd/adrs/0021-graph-sdk-choice.md`
  (SDK choice), `sdd/adrs/0022-graph-auth-model.md` (auth model),
  `sdd/adrs/0023-async-monitor-polling.md` (async monitor polling), and
  `sdd/adrs/0024-resource-locked-error.md` (`ResourceLocked` error), plus
  `sdd/specs/044-graph-backend.md` (GR-001..GR-057). Amends
  `sdd/specs/005-error-model.md` with ERR-013 (`ResourceLocked`) and
  `sdd/specs/025-retry-policy.md` with RET-015 (Graph retry mapping).
  No runtime changes.

- **Test-quality cleanup on coverage PR** (BK-151): cross-platform-safe tests,
  real assertions on previously mock-only checks, `spec=` on every `MagicMock()`.

## [0.23.0] - 2026-04-12

### Added

- **`Capability.LAZY_READ`** (BK-146): New quality flag that indicates `read()`
  fetches data lazily on demand from the native source. Backends that pre-load
  the full file into memory before returning a stream (Memory, SQLBlob, SQLQuery)
  do not declare it. Declared by Local, HTTP, S3, S3-PyArrow, SFTP, and Azure.
  Spec SIO-009 added; conformance tests added; capabilities matrix, backend
  guides, and `FEATURES.md` updated.

### Fixed

- **Azure chunked upload** (BUG-161): `AzureBackend.write()` now uses
  staged-block upload instead of buffering the entire stream into memory.
  Sets `max_single_put_size` and `max_block_size` defaults (256 KiB) on
  both `BlobServiceClient` and `DataLakeServiceClient`. Users can override
  via `client_options` for throughput tuning on large files.

- **Transfer pipe memory overhead** (BUG-162): Backends that relied on the
  platform-default `shutil.copyfileobj` buffer (1 MiB on Windows) now use
  an explicit 256 KiB copy buffer. This keeps peak pipe-layer memory (two
  live chunks: current read + previous write) well under the streaming
  threshold. SFTP was unaffected (already used 32 KiB chunks).

- **`known_hosts` mode test skipped on Windows** (BUG-163): NTFS ignores POSIX
  mode bits; mode-assertion test now skipped on Windows. File-creation check
  retained on all platforms.

- **`cast()` string-literal removal** (BK-146): All `cast("TypeName", value)`
  patterns replaced with `cast(TypeName, value) # noqa: TC006`. Removed redundant
  `BufferedReader`-over-`BytesIO` wrappers in Memory and SQL backends (`BytesIO`
  is `BufferedIOBase` and needs no extra buffering). Removed `BufferedReader` from
  S3 backend — s3fs `AbstractBufferedFile` already provides internal buffering.
  `FileInfo`/`FolderInfo` promoted to runtime imports in `cache.py`.

- **Pages deployment failure** (BUG-144): Batch mike pushes into one and
  replace built-in deployment with explicit `deploy-pages@v4` (Node 20) job,
  fixing "Multiple artifacts" error and `DEP0040` punycode warning.

### Documentation

- **Documentation content longevity rules** (BK-148): New `sdd/CONTENT-RULES.md`
  keeps prose from drifting out of sync with code and generated artefacts.
  `DOCUMENTATION.md` and `CLAUDE.md` updated to reference it.

- **Documentation: remove stale enumerations, unify API references** (BK-149):
  Removed hardcoded counts from guides and docstrings. Reordered Capability enum
  logically; updated all references consistently. Standardized ext module docstrings
  to MkDocs admonition syntax.

- **Documentation: apply content-longevity rules to Guides, Explanation, and Examples** (BK-149b):
  Pseudo-precise values, exhaustive enumerations, and stale counts removed from
  Guides, Explanation, Getting Started, README, and example docstrings. Completes BK-149.

- **SQL blob non-lazy write** (ID-136): Backend guide, capabilities matrix,
  and docstring updated.

- **Design index and Further Reading reshaped** (BK-150): `design/` now
  surfaces every `sdd/` process document — Design, Testing, Documentation
  Standards, Content Rules, Process — plus a new Audits section generated
  from `sdd/audits/`. `further-reading.md` stops duplicating
  the SDD trail and points at `design/` instead; it keeps only
  documentation-convention and community/policy links (Contributing,
  Dev Story, Changelog, Security, Code of Conduct, Citation).
  Contributing and Development Story dropped from the top nav.

- **Azure backend guide** (ID-137): Updated `max_block_size` and
  `max_single_put_size` library defaults from 256 KiB to 1 MiB.

### Internal

- **Streaming overhead reduction** (ID-137): Reduced per-hop allocations
  across Memory, SFTP, Azure, and S3-PyArrow backends. Azure block size
  decoupled from the pipe-layer copy buffer; streaming integrity thresholds
  recalibrated from e2e measurements.

- **Streaming integrity test hardened** (BUG-161, BUG-162): Memory and chunk
  violations are now hard failures instead of warnings. Non-lazy destinations
  (SQL BLOB) are exempt from chunk-count checks (by-design, ID-136).

- **Dafny upgraded to 4.11.0** (ID-134c): Removed `SumSizesAddOneLocal` workaround
  — Boogie cross-file lemma bug fixed in 4.11.0. Toolchain updated throughout
  (CI, `session-init.sh`, `dafny_verify.sh`, README); ubuntu-22.04 zip used
  (20.04 not published for 4.11.0).

- **Dafny ghost infrastructure for `GetFolderInfo` aggregate verification**
  (ID-134, part 1): Added `ChildFiles`, `SumSizes`, and `SumSizesAddOne`
  to `BackendContract.dfy`. Pure additions — no existing postconditions changed.

- **Verified `GetFolderInfo` aggregate postcondition** (ID-134, part 2):
  Strengthened `GetFolderInfo` postcondition to assert `file_count ==
  |ChildFiles(fs, path)|` and `total_size == SumSizes(fs, ChildFiles(fs,
  path))`. `MemoryBackend.dfy` refinement proves the loop computes these
  correctly via ghost set tracking and `SumSizesAddOne` induction.

- **SDD Expert in orchestrate skill** (BK-147): Added a 5th domain expert
  focused on spec-code consistency, ADR coverage, and process guide accuracy.
  Scoped to `sdd/` (specs, ADRs, RFCs, formal, process guides).

- **Mutation testing CI workflow** (BK-145): Added `.github/workflows/mutation.yml`
  with manual (`workflow_dispatch`) and weekly scheduled (`cron`, Saturdays 05:00
  UTC) triggers. Runs all 6 scoped mutation targets in parallel via matrix
  strategy, uploads HTML reports as artifacts, and writes job summaries.
  Cloud-backend scope starts MinIO/Azurite/SFTP services. Gremlins cache
  persisted across runs via `actions/cache`.

- **E2e streaming integrity test** (ID-135): Proves the streaming contract --
  round-robin SHA-256 verification and `tracemalloc` memory profiling across
  all backends.

- **Codecov upload moved to publish workflow**: Coverage is now uploaded to
  Codecov on `release: published` (in `publish.yml`) rather than on every CI
  run. Ensures Codecov reflects released versions only, matching PyPI. The
  `coverage` job runs after a successful `publish` (`needs: publish`), starts
  Azurite, runs the full suite at the 95% threshold, and uploads `coverage.xml`.

## [0.22.1] - 2026-04-10

### Fixed

- **CodeQL alerts** (BK-143): Resolved all 31 open CodeQL security/quality
  alerts — SFTP `known_hosts` permissions (`0o644` → `0o600`), resource
  cleanup, unused imports, and type-stub no-ops. Follow-up: kept `BinaryIO`
  as a runtime import (suppressing `TCH003`/`TC006`) so `cast(BinaryIO, ...)`
  call sites remain genuinely used at runtime and are not flagged by CodeQL.

## [0.22.0] - 2026-04-09

### Added

- **Dafny-compiled oracle as conformance gate** (BK-139c, ID-133): The
  mathematically verified `MemoryBackend.dfy` (53 proofs, 0 errors) is now
  compiled to Python and runs through the full conformance suite as
  `DafnyOracleBackend`. Validates the conformance suite: if the oracle
  passes a test, the test is known-correct. Handwritten POC oracle removed.
  Compiled with Dafny 4.9.1 (downgraded from POC's 4.11.0 — 4.9.1 is the
  version available in the CI environment).
- **`Capability.ATOMIC_MOVE`** (ID-128): New capability flag indicating
  `move()` is guaranteed atomic under concurrent access. Declared by
  Local, Memory, and SQLBlob backends. S3, S3-PyArrow, Azure, and SFTP
  omit it (copy-then-delete semantics). Query with
  `store.supports(Capability.ATOMIC_MOVE)`.
- **Extended conformance suite** (BK-139b): 42 test functions (~53 parameterized
  cases per backend) derived from Dafny `BackendContract.dfy` postconditions.
  Covers error fidelity, precondition ordering, listing completeness, depth
  filtering, move/copy semantics, resource cleanup, and operational consistency.
  Marked `@pytest.mark.extended_conformance` for CI isolation.
- **`ResourceWarning` safety net** (BK-139b): `__del__` methods on
  `SFTPBackend`, `AzureBackend`, and `AsyncAzureBackend` emit
  `ResourceWarning` if `.close()` / `.aclose()` was not called.
  Sync backends also clean up connections; async backend warns only
  (cannot `await` in `__del__`).
- **Ruff `BLE` rule set** (BK-139b): Enabled `BLE001` (blind exception)
  linter rule. All 44 existing intentional broad catches annotated with
  `# noqa: BLE001` (37 in `src/`, 7 in `tests/`).
- **Property-based tests** (BK-139a): Hypothesis PBT suite covering
  partition roundtrip (P1), config `from_dict` corruption (P2), path
  normalization idempotence (P3), and stateful MemoryBackend model (P4).
  Three profiles: `dev` (50 examples), `ci` (100), `nightly` (1000).
- **PBT testing rules** in `sdd/TESTING.md`: Rules 9–11 covering the
  `@given` assertion requirement, profile discipline, and strategy scope.
- **`_safe_wrap()` helper** in `_stream.py`: Safely wraps a stream through
  one or more wrapper layers, closing all acquired resources if any wrapper
  constructor raises.
- **Dafny formal verification layer** (`sdd/formal/`): Machine-checkable
  backend contract specification covering the six BK-140 gaps —
  precondition ordering (BE-008), error mapping (BE-021), listing
  semantics (BE-014/015), depth counting (DEPTH-001), move atomicity
  (BE-018), and resource safety (SIO-001). Includes `MemoryBackend`
  reference refinement, verified depth algorithm, and `_safe_wrap`
  leak-freedom proof.
- **Dafny `GetFolderInfo` method** (ID-130): Added `GetFolderInfo` to
  `BackendContract.dfy` with postconditions `IsFile → InvalidPath`,
  `!PathExists → NotFound`, `IsDir → Ok`. Verified in `MemoryBackend.dfy`.
  Closes the BE-017 formal coverage gap.
- **CI: Dafny verification gate** in `ci.yml`: Runs `dafny verify` on
  all formal specs when `sdd/formal/` or `sdd/specs/` files change.
  Skipped for code-only PRs.
- **DafnyOracle POC** (BK-139c): Proof-of-concept reference oracle implementation
  derived from `MemoryBackend.dfy` formal specification. Two approaches validated:
  handwritten oracle (680 lines, 32 passing tests) and compiled oracle (Dafny
  4.11.0, 41 verified proofs). Demonstrates feasibility of spec-based conformance
  testing. See `sdd/formal/POC/` for implementation and roadmap. Not production-ready.
- **BK-140a backend contract spec amendments** (`sdd/specs/`): Six spec
  amendments tightening the backend ABC behavioral contract — precondition
  evaluation order with flat-namespace exemption (BE-008), canonical error
  mapping table aligned with Dafny postconditions (BE-021), missing-path
  listing semantics (BE-014/015), reference depth algorithm (DEPTH-001),
  move/copy atomicity documentation (BE-018/019), and acquire-then-wrap
  resource safety invariant (SIO-001). Per-method Raises clauses updated
  for BE-006 through BE-019 to be consistent with the canonical table.
- **Query method behavior under file-as-directory-component** (ID-129):
  Codified behavior for `exists()`, `is_file()`, `is_folder()` when paths
  contain file-as-directory-component ancestors (e.g., querying `a/b/c` when
  `a/b` is a file). All three query methods return `False` rather than raising
  `InvalidPath`. Spec amendments to BE-004, BE-005, BE-021 document this
  "accidental consensus" behavior. Dafny formal methods `IsFileMethod()` and
  `IsFolderMethod()` with `AllAncestorsTraversable` predicate verify the
  contract in `MemoryBackend.dfy`. Extended conformance tests cover all
  backends (Local, S3, Azure, SFTP, etc.).

### Fixed

- **PBT stateful model: `read_bytes` on implicit directory** (BUG-160): The
  `BackendModel.read_bytes` rule did not skip paths that are implicit directories
  (created as a side-effect of writing a nested file). Calling `read_bytes('d')`
  after `write_new('d/0')` raised `InvalidPath` instead of `NotFound`, causing
  the `pytest.raises(NotFound)` guard to fail. Added an early-return guard for
  directory paths.
- **ADR-0008 conformance: `ext.arrow` Tier 1 probe** (BK-141): Updated
  `StoreFileSystemHandler.__init__` to narrow exception catch from `Exception`
  to `(CapabilityNotSupported, TypeError, OSError)` and documented the
  capability-probe pattern in ADR-0008 as an explicit exception to the
  "CapabilityNotSupported must propagate" rule. OSError catch handles cloud
  backend initialization failures (e.g., S3 endpoint unreachable). Added test
  `test_tier1_unexpected_exception_propagates` to verify unexpected exceptions
  are not silently caught. The pattern is now ADR-endorsed for optional feature
  detection during extension initialization.
- **Type-mismatch errors now raise `InvalidPath` per spec** (ID-131):
  `read()`, `read_bytes()`, `delete()`, `get_file_info()`, `get_folder_info()`,
  `delete_folder()` on the wrong path type (directory vs file) now raise
  `InvalidPath` instead of `NotFound` in LocalBackend, MemoryBackend, and
  SFTPBackend — matching the Dafny `BackendContract.dfy` postconditions and
  BE-021 canonical error mapping. `move()`/`copy()` now check source and
  destination types across all three backends. Self-move and self-copy
  (`src == dst`) are no-ops in Local, Memory, S3, S3-PyArrow, and SFTP
  backends (previously leaked `SameFileError` or lost data).
- **S3 `read()` leaks file handle if stream wrapping fails** (BUG-159):
  Both `S3Backend.read()` and `S3PyArrowBackend.read()` now use the new
  `_safe_wrap()` helper to close raw handles if wrapping constructors raise.

### Documentation

- **Custom backend guide: conformance suite integration** (ID-132): The
  "Testing your backend" section now explains how to register a new backend in
  `tests/backends/conftest.py` to run the full conformance suite automatically,
  how `_require()` / capability gating causes tests to self-skip (not fail) for
  partial-capability backends, and the flat-namespace vs. hierarchical backend
  distinction (`_FLAT_NAMESPACE_BACKENDS`). Added a conformance checklist table
  (basic, extended, error mapping, repr safety). Corrected spec coverage range
  (BE-001–BE-025 + ancillary specs) and test count (50 Dafny-derived tests).
- Added "Quality & Testing" section to README explaining testing dimensions (spec-driven development, unit tests, PBT, formal verification, mutation testing, benchmarks, examples).

### Internal

- **CodeQL hardening** (BK-142): Scoped CodeQL analysis to `src/remote_store/`
  via `.github/codeql/codeql-config.yml`; upgraded query suite from default to
  `security-and-quality`; added `on.paths` trigger filter on push to skip
  doc-only merges; removed `paths` filter from `pull_request` trigger so the
  "Analyze (Python)" status check is always posted (prevents branch-protection
  merge blocks on non-code PRs); added `dependency-review` job to catch CVEs
  in dependency changes on PRs; annotated intentional `pickle.loads` (dagster
  ext) and `ruamel.yaml` safe-mode loader (yaml ext) with CodeQL justification
  comments.

## [0.21.1] - 2026-04-03

### Fixed

- **Azure `list_files` ignores `max_depth`** (BUG-155): Both
  `AzureBackend.list_files` and `AsyncAzureBackend.list_files` now implement
  depth limiting when `recursive=True` and `max_depth` is specified,
  consistent with S3 and Local backends.
- **Sync `AzureBackend.close()` doesn't close `DefaultAzureCredential`**
  (BUG-156): Sync backend now caches the credential and closes it in
  `close()`, matching the async backend's `aclose()` pattern.
- **Sync `AzureBackend.delete_folder` non-HNS materializes all blobs**
  (BUG-157): Existence check now stops after the first blob instead of
  eagerly fetching all blobs into memory.
- **Sync `AzureBackend.read()` doesn't protect downloader on stream-wrapping
  failure** (BUG-158): The downloader is now cleaned up if
  `_ErrorMappingStream` or `BufferedReader` construction fails.
- **`LocalBackend` leaks `IsADirectoryError` for directory paths**
  (BUG-153, BUG-154): `read()`, `read_bytes()`, `delete()`, `write()`,
  `write_atomic()`, and `open_atomic()` now catch `IsADirectoryError` and
  raise `NotFound` (read/delete) or `InvalidPath` (write), consistent with
  MemoryBackend.  `delete(missing_ok=True)` on a directory is now silenced,
  matching MemoryBackend's behavior.
- **S3 `client_options` shallow copy mutates caller's nested dicts** (BUG-148):
  Lazy filesystem init now deep-copies `client_options` so that adding
  `region_name`, `config`, or `verify` to `client_kwargs` does not modify
  the caller's original dict. Affects both `S3Backend` and `S3PyArrowBackend`.
- **S3PyArrow `get_file_info` returns no ETag and no digest** (BUG-150):
  `get_file_info` now uses `call_s3("head_object", ChecksumMode="ENABLED")`
  like `S3Backend`, returning both ETag and digest when available.
- **S3PyArrow `_extract_etag` scope too broad** (BUG-151): `_extract_etag`
  override now only affects listing paths; `get_file_info` extracts ETag
  from the HeadObject response.
- **S3 `list_files` ignores `max_depth`** (BUG-152): `_S3Base.list_files`
  now implements native depth limiting during BFS traversal, consistent
  with all other backends.
- **SFTP `delete_folder` masks `listdir` permission errors** (BUG-147):
  Non-recursive `delete_folder` now re-raises non-ENOENT errors from
  `listdir` instead of silently treating them as empty.
- **SFTP listing methods silently swallow non-ENOENT errors** (BUG-146):
  `list_files`, `list_folders`, and `iter_children` now only suppress
  ENOENT from `listdir_attr`; other errors propagate as `RemoteStoreError`.
- **SFTP `_ensure_parent_dirs` swallows permission errors** (BUG-145):
  Parent directory creation now only catches ENOENT on `stat` and EEXIST
  on `mkdir`; other errors propagate.
- **SFTP SSH client leaked on connection failure** (BUG-144): `_connect()`
  now closes the `SSHClient` if the retry-wrapped connect exhausts attempts.
- **SFTP `st_mode` None causes TypeError** (BUG-143): Entries with
  `st_mode is None` are now skipped in listing, traversal, and stats methods.
- **SFTP `read()` leaks file handle if stream wrapping fails** (BUG-142):
  The paramiko file handle is now closed if `_ErrorMappingStream` or
  `BufferedReader` construction raises.
- **`config_loaders.py` example crashes on Windows** (BUG-136): Path
  interpolation into TOML/YAML strings produced backslashes which are
  invalid escape sequences. Now uses forward slashes on all platforms.
- **CachedStore write doesn't invalidate parent directory metadata** (BUG-137):
  Writing a nested path (e.g. `dir/file.txt`) now also invalidates cached
  `exists()` / `is_folder()` / `is_file()` entries for all ancestor
  directories, not just the leaf path.
- **CachedStore.child() creates isolated cache** (BUG-138): `_wrap_child()`
  now passes the parent's cache backend to the child and tracks the child's
  path prefix so mutations through a child store correctly invalidate
  the parent's cached entries.
- **RegistryConfig.from_dict crashes on null options** (BUG-139): YAML/TOML
  `options:` with no value (`None`) now treated as empty dict instead of
  raising `TypeError`.
- **RegistryConfig.from_dict converts null to string "None"** (BUG-140):
  Null `type` or `backend` now raises `TypeError` with a clear message
  instead of silently producing the string `"None"`. Null `root_path`
  is treated as empty string (same as omitted).
- **partition_path allows `=` in key** (BUG-141): Partition keys containing
  `=` now raise `ValueError`, preventing round-trip failures with
  `parse_partition`.

### Changed

- **Examples reorganized into topical subdirectories** — examples are now
  grouped into `getting_started/`, `configuration/`, `errors/`, `advanced/`,
  `backends/`, `extensions/`, and `integrations/` for easier navigation.
  The docs index page reflects the new 7-section layout. All import paths,
  CI workflows, and docs references updated accordingly.

### Internal

- **Remove Pygments `<2.21` upper-bound pin**: pymdown-extensions 10.21.2
  fixed the `filename=None` highlight bug. Pygments is now unpinned above 2.18.
- **Deduplicate `pyproject.toml` dependency lists** (BK-138): Hatch env uses
  `features = ["dev", "docs", "bench"]` instead of re-listing 43 packages.
  `bench`, `docs`, and `dev` extras compose from user-facing backend/extension
  extras via self-referential dependencies. Removed cargo-culted `s3fs` from
  `docs` extra (all backends use lazy imports).

## [0.21.0] - 2026-04-01

### Added

- **`resolve_env()` env-var interpolation** (ID-126): `resolve_env(data)`
  resolves `${VAR}` and `${VAR:-default}` placeholders in config dicts.
  `from_toml()` and `from_yaml()` gain an opt-in `resolve_env_vars=True`
  parameter. Standalone function exported from `remote_store` for custom
  loaders. Spec: CFG-018..CFG-021.
- **Async Store API (`remote_store.aio`)** (ID-013): `AsyncStore` --
  async counterpart to `Store` with coroutine methods for all operations.
  `AsyncBackend` abstract base class for native async backends.
  `SyncBackendAdapter` wraps any synchronous backend for async use
  (delegates to a thread-pool executor). `AsyncMemoryBackend` for
  async testing. Phase 1 — core primitives.
- **`AsyncAzureBackend` native async backend** (ID-013 Phase 2): First native
  async backend for `remote_store.aio`. Uses Azure SDK async clients
  (`azure.storage.blob.aio`, `azure.storage.filedatalake.aio`) for true
  non-blocking I/O. Shared helpers extracted to `_azure_common.py` for
  sync/async code reuse. Zero new dependencies.
- `FEATURES.md` at repo root — versioned snapshot of backends, extensions,
  capabilities, and install extras for agent and human discoverability (BK-136).
- `remote_store.info()` public function — runtime introspection of available
  backends and extensions in the current environment (BK-136).
- `CLAUDE.md` now references `FEATURES.md` for cold-start agent sessions (BK-136).
- Release checklist in `CONTRIBUTING.md` now includes `FEATURES.md` update (BK-136).
- **Dagster multi-partition loading** — `load_input` now returns
  `dict[str, Any]` when the input context carries multiple partition keys
  (time-window aggregation). Applies to both the bytes-serializer IO manager
  and the dataset IO manager (ID-124, spec DAG-020).

### Changed

- **`ParquetSerializer.deserialize()` now returns a PyArrow Table** instead of
  a pandas DataFrame (BUG-135). Removes the hidden hard dependency on pandas
  for users installing `remote-store[dagster,arrow]` without pandas. Callers
  that need pandas call `table.to_pandas()` on the result. See
  [Migration Guide](https://docs.remotestore.dev/stable/reference/migration/#v0200-to-v0210).

### Documentation

- **Spec 029 amendments** (ID-013b): add round 2 §2.4 items (ASYNC-036/037,
  ASYNC-052a–e, ASYNC-057/058, ASYNC-061/062) and Phase 2 `AsyncAzureBackend`
  spec (ASYNC-070–079). Update `max_depth` on ASYNC-014/015/017, `resolve()`
  in ASYNC-034 passthrough list, and ASYNC-046 enumeration.
- Expand async guide with native backend section (`AsyncAzureBackend`),
  health check (`ping()`), and updated limitations.
- Fix CHANGELOG migration-guide link for GitHub (move `guides/migration.md`
  to repo root so `migration.md#…` resolves in both GitHub and docs).
- Fix stale pandas reference in Dagster guide — Parquet serializer
  deserializes to a PyArrow Table, not a pandas DataFrame.

### Internal

- **Test quality: TESTING.md compliance** (BK-137): Fixed Rule 2 (sole
  `isinstance` → behavioral assertions) and Rule 7 (copy-paste → parametrize)
  violations in post-v0.20.0 async and dagster tests. Improved coverage for
  `_azure_common` (69→100%), `_async_azure` (89→95%), `_sync_adapter` (93→98%),
  `_async_store` (96→98%).
- Fix 72 `ResourceWarning: unclosed database` in SQL backend tests by adding
  proper fixture teardown and `close()` calls. Filter residual SQLAlchemy pool
  warning on Python 3.13+ (BK-135).
- Replace `isinstance`-only assertions (12 tests) and private attribute
  assertions (~15 instances) with behavioral checks (BK-134).
- Upgrade `setup-uv` from v7 to v8.0.0 (immutable tags) across all workflows.
- Disable uv caching on lightweight CI jobs to eliminate cache-contention warnings.

## [0.20.0] - 2026-03-30

### Added

- **Dagster extension v2 (`ext.dagster`)** (ID-083): `DagsterStoreResource`
  (`ConfigurableResource`) for direct Store access in assets, and
  `RemoteStoreIOManager` (`ConfigurableIOManagerFactory`) for config-driven
  IO management with automatic Store lifecycle. Dataset mode via
  `dagster_dataset_io_manager()` or `serializer="parquet-dataset"` writes
  Parquet datasets through `ParquetDatasetStore`. Spec 031 (DAG-012 -- DAG-019).

- **Parquet Dataset Storage extension (`ext.parquet`)** (ID-122):
  `ParquetDatasetStore` — high-level Parquet dataset read/write with manifest
  metadata, `_SUCCESS` completion markers, and atomic-commit semantics. Supports
  single-file and multi-part layouts, column projection on read, and
  overwrite semantics. Extension-specific errors: `DatasetIncomplete`,
  `ManifestCorrupted` (import from `remote_store.ext.parquet`). Spec 042.

- **`resolve()` introspection API** (ID-120): `Store.resolve(key)` returns a
  frozen `ResolutionPlan` dataclass describing how a key maps to its storage
  location, backend identity, and backend-specific context. Available on all
  backends with no I/O. Enables debugging ("which backend handled this key?"),
  principled cache key derivation, and future composite store composition.
  Spec 043.

- **`max_listing_size` parameter for `cache()`** (BK-123 M-1): Skips caching
  listing results (`list_files`, `list_folders`, `iter_children`, `glob`) that
  exceed the given item count. Complements the existing `max_content_size` guard
  for `read_bytes`.

- **`SQLQueryBackend` — read-only SQL query materializer** (ID-119 v2): Maps
  path keys to SQL queries and serializes results to Parquet, CSV, or Arrow
  IPC based on the key's file extension. Explicit query mappings via `queries`
  dict; `strict=True` default (view/convention discovery deferred).
  `ResultSerializer` protocol with built-in `ArrowSerializer`. New optional
  extra: `pip install remote-store[sql-query]`. Spec 041.

- **SQLBlobBackend — SQL key-value blob storage** (ID-119 v1): New
  `SQLBlobBackend` backed by SQLAlchemy. Uses a SQL table as key-value store
  with full Backend contract (all 10 capabilities). SQLite optimizations:
  WAL mode, `PRAGMA synchronous=NORMAL`. Supports owned or borrowed
  engines, custom table names, existing
  table introspection (`create_table=False`), and `max_blob_size` guard.
  Optional extra: `pip install remote-store[sql]`. Spec 040.

- **TLS CA bundle support for S3 backends** (ID-118): New `tls_ca_bundle`
  parameter on `S3Backend` and `S3PyArrowBackend` replaces nested
  `client_options={"client_kwargs": {"verify": path}}`. Falls back to
  `AWS_CA_BUNDLE` / `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` env vars.
  Early path validation at construction time. Spec 039.

- **S3 endpoint URL normalization** (ID-117): `S3Backend` and
  `S3PyArrowBackend` now accept bare `host:port` values for `endpoint_url`
  and auto-prefix them with `https://`. Reduces migration friction from
  PyArrow's `endpoint_override` which accepted bare endpoints. URLs with
  existing schemes are unchanged. Spec S3-025 / S3PA-023.

- **Non-recursive `get_folder_info`** (ID-112):
  `Store.get_folder_info(path, max_depth=N)` controls traversal depth for
  folder statistics. `max_depth=0` aggregates only direct children;
  `max_depth=N` includes files up to N levels deep. `None` (default) preserves
  the existing full-recursive backend delegation. Store-level computation
  using `list_files()`; no Backend ABC change. `CachedStore` and
  `ObservedStore` forward the parameter. Spec 038.

- **Depth-limited listing** (ID-107, ID-108): `Store.list_files(max_depth=N)`
  and `Store.list_folders(max_depth=N)` control traversal depth without
  fetching the full recursive tree. When `max_depth` is set on `list_files`,
  `recursive` is ignored. Client-side filtering at the Store level; no
  Backend ABC change. Spec 037.

- **Backend-native `max_depth` optimization** (ID-107b):
  `Backend.list_files()` now accepts optional `max_depth` kwarg. Local, SFTP,
  and Memory backends prune traversal natively, reducing filesystem and network
  I/O. S3/Azure accept the parameter but defer to Store-level client-side
  filtering. Spec 037 (DEPTH-003).

- **Azure range reader** (ID-102): `AzureBackend.read_seekable()` returns
  a seekable stream backed by `download_blob(offset=, length=)`. Each
  `read()` issues a single HTTP Range request — no full-file download.
  Enables PyArrow Tier 3 column pruning for Parquet on Azure.

- **S3-PyArrow in comparative benchmarks** (ID-104): S3-PyArrow now appears
  in overhead charts, comparative reports, and user-facing verdicts with boto3
  as its raw SDK baseline. New S3 vs S3-PyArrow comparison chart.

- **Overhead-vs-RTT chart** (ID-104): Replaces the placeholder with a real
  line chart showing how overhead % changes across network latency profiles
  (clean, rtt20, rtt50, rtt100). Raw SDK targets added for latency backends
  for apples-to-apples comparison. Network profile metadata saved in
  benchmark JSON.

- **`--file` flag for benchmark tools** (ID-104): `report.py` and `charts.py`
  accept `--file PATH` to load a specific JSON file instead of auto-detecting
  the latest.

- **Latency matrix benchmark command** (ID-104):
  `hatch run bench-latency-matrix` runs rtt20/rtt50/rtt100 profiles
  sequentially. Cross-platform Python script with configurable `--profiles`,
  `--pool-size`, `--bench-timeout`.

- **Seekable read and cache benchmarks** (ID-103 Phase 4):
  `test_seekable.py` measures `read_seekable()` cost (open+read, sequential
  chunks, random seeks) across backends with different seek strategies.
  `test_cache.py` measures CachedStore cold read (miss) vs warm read (hit)
  vs uncached baseline.

- **Benchmark charts and user-facing report** (ID-103 Phases 2--3):
  SVG chart generation (`hatch run bench-charts`) for overhead %, overhead
  vs RTT, and throughput by file size. User-facing verdict report
  (`hatch run bench-report-user`) classifying overhead as
  Negligible/Moderate/Visible/Favorable. Performance guide reframed to
  lead with the answer. README gains a Performance section.

- **Toxiproxy latency simulation for all backends** (ID-103 Phase 1):
  Toxiproxy now proxies all three network backends (MinIO, Azurite, SFTP).
  New `--network-profile` flag with named profiles (`clean`, `rtt20`,
  `rtt50`, `rtt100`). New `s3-latency` and `sftp-latency` backend params
  alongside the existing `azure-latency`.

- **ProxyStore added to API reference** (ID-101): `ProxyStore` is now exported
  from `remote_store` and documented. It remains an internal delegation base by
  design (ADR-0014) but is visible in the inheritance chain of `ObservedStore`
  and `CachedStore`, and useful for building custom Store extensions.

### Fixed

- **Publish workflow no longer runs full CI suite** (BK-132): Removed redundant
  lint/typecheck/test jobs from `publish.yml` — master branch protection already
  gates these. Publish now only builds, checks, and uploads. Fixes Python 3.10
  dependency resolution failure caused by `pytest-gremlins>=1.5` (requires 3.11+).

- **`MemoryCache.size()` no longer rebuilds dict** (BK-127 L-1): Replaced dict
  comprehension with `sum()` generator — avoids transient 2× memory spike on
  large caches. Trade-off: `size()` no longer evicts expired entries as a
  side-effect; they remain in `_data` until the next `get()`, `clear_prefix()`,
  or `clear_prefixes()` call.

- **Replaced mypy `ignore_missing_imports` overrides with proper type stubs**
  (BK-015): Removed 8 `[[tool.mypy.overrides]]` entries that suppressed
  import errors for packages shipping `py.typed` or having PyPI stubs
  (`pydantic`, `pydantic_settings`, `tomli`, `tomllib`, `ruamel.yaml`,
  `requests`, `urllib3`, `httpx`). Added `types-requests` to dev
  dependencies. Cleaned up now-unnecessary `# type: ignore` comments in
  `_http_requests.py` and `_http_httpx.py`. Mypy now sees real types
  instead of `Any` for these imports.

- **SFTP TOFU host key persistence** (BUG-005): `TRUST_ON_FIRST_USE` now
  persists accepted host keys to disk on disconnect, creating the known_hosts
  file and parent directories if absent. Inline keys (code/config/env) are
  never persisted. Spec SFTP-028.

- **Cache coherency in move/copy operations** (BUG-006): `CachedStore.move()`
  and `CachedStore.copy()` now clear the entire cache (instead of selective
  invalidation) to prevent stale cached entries for nested paths that are
  relocated or overwritten. Consistent with `delete_folder()` safety strategy.
  Spec CACHE-010 updated.

- **Snippet indentation in docs code blocks** (BUG-004): named snippet
  regions inside function bodies rendered with extra leading whitespace.
  Fixed via pymdownx.snippets `dedent_subsections` option.

### Changed

- **S3 recursive listing memory optimization** (BK-123 H-1/H-2):
  `list_files(recursive=True)` and `get_folder_info` now use paginated
  per-directory `ls()` calls instead of `find()`, reducing peak memory from
  O(total objects) to O(widest directory).

- **MemoryBackend listing lock reduction** (BK-123 M-3/M-4/M-5): `list_files`,
  `list_folders`, and `iter_children` now snapshot state under lock and build
  results lazily outside it, reducing lock contention during long iterations.

- **MemoryBackend write memory optimization** (BK-123 M-6): Stream writes
  accumulate directly into a `bytearray` via chunked reads, halving peak memory.

- **CachedStore pre-flight size check** (BK-123 M-2): `read_bytes` checks
  cached `get_file_info` size before reading to skip caching oversized files
  earlier. Zero extra backend calls.

- **Performance messaging rewrite** (ID-104): README and performance guide now
  present overhead as measured values in ms (with percentages in brackets)
  instead of judgmental language. Users see the numbers and decide for
  themselves.

- **Seekable read promoted to Store API** (ID-100, ID-102): New
  `Store.read_seekable()` method — always returns a seekable stream,
  backend-optimized. On seekable backends (Local, S3, SFTP) it's
  zero-overhead passthrough. On Azure it returns `_AzureRangeReader`
  (HTTP Range requests per read — ideal for PyArrow column pruning).
  On HTTP it spools to `SpooledTemporaryFile`. Replaces
  `ext.seekable.seekable_read()` (removed, never released).
  ADR-0017 supersedes ADR-0016. Spec 036 revised.

### Removed

- **Deprecated function aliases removed** (BK-130): `cached_store()`,
  `remote_store_io_manager()`, and `pydantic_to_registry_config()` are removed.
  Use `cache()`, `dagster_io_manager()`, and `from_pydantic()` respectively.
  The `_deprecated_alias()` helper in `ext/_helpers.py` is also removed.
  Pre-v1 — no deprecation shim needed.

### Documentation

- **Fix docs list completeness findings** (BK-129): Add SQLBlob and SQLQuery
  backends to all backend lists, tables, and matrices across 14 doc files.
  Remove ghost "Seekable read" entries from extension lists. Add missing
  extensions to architecture.md. Add `read_seekable()` directive to Store API
  reference. Add `sql` and `sql-query` extras to README installation section.

- **RFC-0008: Parquet Dataset Storage extension** (ID-122): Draft RFC proposing
  `ParquetDatasetStore` — high-level Parquet dataset read/write with manifests,
  `_SUCCESS` markers, and atomic-commit semantics on top of existing Store
  primitives.

- **S3 listing strategies and performance** (ID-113): New comprehensive guide in
  `guides/backends/s3.md` explaining shallow vs. recursive listing, why flat
  `ListObjectsV2` streams beat delimiter-based folder iteration, and why
  parallelization is wrong for large buckets. Includes performance data and
  examples showing when to use each approach. New example file
  `examples/backends/s3_listing_strategies.py` demonstrates shallow, recursive,
  and filtered listing patterns.

### Internal

- **CI test quality gates** (BK-126): AST-based assertion checker
  (`scripts/check_test_assertions.py`) and MagicMock spec checker
  (`scripts/check_mock_spec.py`) now run in CI lint job. Rules 1 and 4 from
  `sdd/TESTING.md` are machine-enforced.

- **MagicMock `spec=` migration** (BK-126): All 67 unconstrained
  `MagicMock()` calls now use `spec=` with the correct class, preventing
  mocks from silently accepting invalid attribute access.

- **Assertion migration** (BK-126): 87 test functions that lacked explicit
  `assert` or `pytest.raises` now have meaningful post-condition assertions.

- **pytest-gremlins integration** (BK-126): Added `pytest-gremlins>=1.5` for
  mutation testing. New hatch scripts: `check-test-quality`,
  `test-cov-branch` (branch coverage diagnostic). No CI threshold yet.

- **Fix mutation testing scripts** (BK-131): Replaced broken `mutate` /
  `mutate-report` scripts with 6 scoped scripts (`mutate-core-api`,
  `mutate-core-infra`, `mutate-ext-proxy`, `mutate-ext-format`,
  `mutate-backends-local`, `mutate-backends-cloud`). Original scripts passed
  source dir as positional arg instead of `--gremlin-targets`. Scoped runs
  avoid Windows command-line length limits. Added `[tool.pytest-gremlins]`
  config with incremental caching enabled.

- **Eliminate avoidable `type: ignore` comments** (BK-016): Replaced 9
  `no-any-return` suppressions with `cast()` in `ext/cache.py` (6) and
  `_stream.py` (3). 1 `misc` in `_path.py` kept (mypy `Final` on `__slots__`
  limitation).

- Document `list()` materialisation in concurrent batch helpers (BK-127 L-2).
- Clarify module-level sqlalchemy import rationale (BK-127 L-3).

- **Ruff PT rules enabled** (BK-124b): `flake8-pytest-style` enforced in
  `pyproject.toml`. 152 auto-fixed, 13 `match=` added to `pytest.raises`,
  9 intentional PT012 suppressed. Ruff PT section in TESTING.md marked enabled.

- **Multi-agent orchestration skill** (BK-125): `/orchestrate` skill delegating
  to 4 domain experts (Store & Backend, Extension, Testing, Documentation) via
  Claude Code Agent tool. Two modes: implementation and review. ADR-0019
  documents the architecture decision.

- **Orchestrate v2: iterative convergence model** (BK-128): Redesigned
  `/orchestrate` from single-pass parallel to iterative convergence with three
  complexity modes (Simple, Standard, Complex). Adds plan refinement with
  experts (1 round), consolidation step, review loop (max 2 rounds), and
  user as tie-breaker. ADR-0020 supersedes ADR-0019.

- **Testing standards guide** (BK-124a): New `sdd/TESTING.md` codifying 8 test
  quality rules from research-testing-best-practices. Companion to DESIGN.md
  § 11 (style). Includes Testing Expert quick reference for BK-125.

- **RFC-0009: Multi-agent orchestration** (BK-125): Draft RFC proposing
  orchestrator + 4 subject matter experts for complex multi-concern tasks.
  Claude Code native (Agent tool) approach. No code change — process only.

- **Test coverage and ResourceWarning fixes**: SQLBlob test fixtures now
  dispose engines on teardown (ResourceWarning eliminated). ProxyStore
  delegation coverage 68% → 100% (new `test_proxy.py`). SQLAlchemy backend
  coverage 90% → 99% (`_glob_to_like`, optional columns, health check).
  `/pr` skill now gates on `hatch run test-cov` (95% threshold) before
  creating PRs.

## [0.19.0] - 2026-03-23

### Changed

- **Renamed ext factory functions for naming consistency** (BK-010):
  - `pydantic_to_registry_config()` → `from_pydantic()` — matches the `from_*`
    pattern used by `from_yaml`, `from_dict`, `from_toml`.
  - `remote_store_io_manager()` → `dagster_io_manager()` — drops redundant
    `remote_store_` prefix, matches `pyarrow_fs` pattern.
  - `cached_store()` → `cache()` — bare verb, matches `observe()`.
  - Old names remain as deprecated aliases emitting `DeprecationWarning`.

### Documentation

- **Single-source code snippets for docs** (ID-057): docs code blocks are now
  pulled from tested Python files in `examples/snippets/` via pymdownx.snippets
  named regions. CI runs snippet scripts to guarantee they stay valid.

- **Auto-generated example doc wrappers** (ID-058): `scripts/gen_pages.py` now
  scans `examples/*.py`, extracts the module docstring, and generates wrapper
  pages + index + nav entries automatically. Eliminates the class of "forgot to
  add a wrapper" bugs. Added `tests/test_api_coverage.py` to verify every
  `__all__` symbol has API documentation.

- **Cross-link compliance pass** (BK-013): `## See also` sections added to all
  27 example pages and all API reference pages. Backend names in capability
  matrices, choosing-a-backend, concurrency, health-check, performance, and API
  reference tables now link to their respective guide pages. Added Rule 4
  ("Table header/key-column → documented entity") to `DOCUMENTATION.md` § 4.

- **Docstring and API doc fixes**: replaced private-module imports with public
  API paths in docs, completed extensions table, fixed Sphinx-style remnants.

### Internal

- **S3 backend code deduplication** (BK-011): extracted `_S3Base` base class,
  `_fileinfo` helpers, and error factories from the two S3 backends. Net −94
  lines, single maintenance point for 155 previously duplicated lines.

- **Extension code deduplication** (BK-012): `_StreamWrapper` base class in
  `ext/streams.py`, generic `_run_batch()` executor in `ext/batch.py`,
  `_deprecated_alias()` helper in `ext/_helpers.py`.

- **Test suite deduplication and parametrization** (BK-014): refactored 30 of 40
  test files (~17,800 → ~16,300 lines, −8.6%) while preserving identical
  coverage. Parametrized similar tests, extracted shared fixtures, merged
  single-method classes, and consolidated repeated assertion patterns.

- **SDD document category consolidation** (ID-099): merged `proposals/` →
  `rfcs/` and `plans/` → `research/`, reducing SDD categories from 7 to 5.
  Added Document Types table to `000-process.md`.

- **Fixed compound-command PreToolUse hook**: replaced `jq` (not installed) with
  Python for JSON parsing. Also blocks `git -C` pattern.

## [0.18.0] - 2026-03-18

### Added

- **S3 backend now populates `FileInfo.digest` from `x-amz-checksum-*`** —
  `get_file_info` calls `HeadObject` with `ChecksumMode: ENABLED` unconditionally,
  returning both metadata and any checksum headers in a single request. The
  base64-encoded checksum is converted to a hex `ContentDigest`. Listing paths
  (`list_files`, `iter_children`) still return `digest=None` to avoid per-file
  overhead. (ID-098, S3-024)
- **S3 backend now populates `FileInfo.etag`** — `_info_to_fileinfo` strips
  the double-quoted S3 ETag and stores it as a lowercase string.
  (ID-096, S3-023)
- **Azure backend now populates `FileInfo.etag` and `FileInfo.digest`** —
  `_props_to_fileinfo` strips and lowercases the Azure blob ETag (`etag`), and
  converts `content_settings.content_md5` bytes to a `ContentDigest("md5", hex)`
  when the blob was uploaded with Content-MD5 set. (ID-097, AZ-034)

- **`ContentDigest` frozen dataclass** — immutable model with `algorithm: str`
  and `value: str` (both lowercase-normalized, validated). Convenience
  `content_digest()` function in `ext.integrity`. (ID-095, CDG-001–CDG-003)
- **`FileInfo.digest` and `FileInfo.etag` fields** — `digest: ContentDigest | None`
  for verified checksums, `etag: str | None` for opaque server tags.
  `FileInfo.checksum` is removed (pre-1.0, no deprecation shim).
  (ID-095, CDG-004)
- **`ext.streams` module** — composable `BinaryIO` wrappers for progress
  tracking and checksum computation: `ProgressReader`, `ProgressWriter`,
  `ChecksumReader`, `ChecksumWriter`, `read_with_progress()`. Stream-level
  primitives that compose with any `BinaryIO`, including from `open_atomic()`.
  (ID-092)
- **`ext.integrity` module** — pure functions for checksum verification over
  Store's public API: `checksum()`, `verify()`, `verify_hex()`. (ID-093)
- **`ProxyStore` base class** — shared delegation base for `ObservedStore`
  and `CachedStore`. Centralizes private-attribute coupling, provides default
  delegation for all Store methods, and enables `child()` propagation.
  Internal only — not part of the public API. (ID-094, ADR-0014)
- **HTTP backend: HEAD fallback for CDN-blocked servers** — when `HEAD` returns
  401/403, `exists()`, `get_file_info()`, and `check_health()` retry with
  `GET` + `Range: bytes=0-0`. The result is cached for the backend's lifetime.
  Discovered during live testing against CDN-fronted endpoints. (ID-085)
- **`@pytest.mark.os_sensitive` CI marker** — macOS and Windows CI jobs now run
  only tests that exercise OS-specific behaviour (path separators, atomic writes
  via `os.replace`, local filesystem operations). Network-protocol backends
  (HTTP, S3, SFTP) are Linux-only. Reduces cross-platform CI time significantly.
  (ID-087)
- **Medallion + Dagster showcase** (`examples/medallion_dagster/`) —
  self-contained Dagster project demonstrating 4 extensions composing over live
  MeteoSwiss weather data in a Bronze/Silver/Gold medallion architecture.
  Uses `ReadOnlyHttpBackend`, `ext.cache`, `ext.otel`,
  and `ext.dagster`. (BK-008)
- **Read-only HTTP backend** (`ReadOnlyHttpBackend`) — read files from
  HTTP/HTTPS URLs. Capabilities: `{READ, METADATA}`. Zero runtime dependencies
  (uses stdlib `urllib`); optional `requests` and `httpx` transports via extras
  for connection pooling. Install with `pip install "remote-store[requests]"` or
  `pip install "remote-store[httpx]"`. (ID-082)
- **Conformance suite capability gates** — WRITE, DELETE, LIST, MOVE, COPY
  capabilities are now gated in the backend conformance suite, enabling testing
  of partial-capability backends.
- **`ext.dagster` — Dagster IO Manager adapter** (ID-075 v1) — wraps any
  existing `Store` as a Dagster `IOManager` via `remote_store_io_manager()`.
  Pluggable serialization (pickle, JSON, Parquet). Install with
  `pip install "remote-store[dagster]"`. Spec `031-ext-dagster.md`
  (DAG-001 through DAG-011).

### Changed

- **`ext.transfer.download()` now uses `ProgressReader` wrapper** — progress
  tracking in `download()` is now consistent with `upload()` and `transfer()`,
  using the `ProgressReader` stream wrapper instead of an inline callback.
  (ID-006, XFER-009)
- **`ext.transfer` now uses public `ProgressReader`** from `ext.streams`
  instead of its private `_ProgressReader`. No public API change. (ID-091)
- **`ObservedStore` and `CachedStore` now extend `ProxyStore`** — reduces
  boilerplate, centralizes delegation, and removes duplicated init coupling.

### Fixed

- **`child()` now propagates proxy behavior** in `ObservedStore` and
  `CachedStore`. Previously, `cached_store(s).child("sub")` returned a plain
  `Store`, silently losing caching/observation. (BUG-003)
- **`pydantic_to_registry_config()` now unwraps `SecretStr` fields** —
  Pydantic `SecretStr` values in backend `options` dicts are automatically
  converted to plain strings before reaching `from_dict()`, so sensitive-key
  detection wraps them in `Secret` correctly. Previously, `SecretStr` objects
  bypassed the `isinstance(v, str)` check and were not wrapped.

### Documentation

- **Backend API reference pages** (ID-088) — added class documentation for all
  7 backends (Local, Memory, HTTP, S3, S3-PyArrow, SFTP, Azure) under a new
  "Backends" section in the API reference. Each page links to the corresponding
  backend guide.
- **Extensions API reference section** (ID-089) — moved all 11 extension API
  pages into a nested "Extensions" section with an index page, matching the
  Backends section structure.
- **Docs landing page** (ID-090) — replaced the 1:1 README include with a
  purpose-built orientation page: architecture diagram, six key messages,
  quick start, and navigation links.

### Removed

- **Top-level re-exports of optional-dependency extensions** (ADR-0013) —
  `from remote_store import pyarrow_fs` and similar shortcuts for arrow, otel,
  pydantic, and yaml extensions are removed.
  Use the canonical import path instead:
  `from remote_store.ext.arrow import pyarrow_fs`.  Pure-Python extensions
  (batch, cache, glob, observe, partition, transfer) are unchanged.

## [0.17.0] - 2026-03-14

### Added

- **`AzureBackend(max_concurrency=)` parameter** (ID-076) — controls parallel
  connections for blob uploads and downloads. Default `1` (sequential, matching
  prior behavior). Set higher for improved throughput on large files.

- **`FolderInfo.name` property** (ID-079) — derived `@property` returning the
  final path component (`self.path.name`). `FolderInfo` now satisfies the
  `PathEntry` protocol alongside `FileInfo` and `FolderEntry`.

- **`FolderEntry` dataclass and `PathEntry` protocol** (ID-072) — `FolderEntry`
  is an immutable identity object returned by listing operations with `.name`
  and `.path` attributes. `PathEntry` is a runtime-checkable protocol satisfied
  by both `FileInfo` and `FolderEntry`, enabling uniform iteration.

- **`Store.write_text()` convenience method** (ID-074) — writes a string to a
  file with configurable encoding. Wraps `write()` with `encoding` and
  `overwrite` parameters matching `pathlib.Path.write_text()`. Store-level only
  (no backend changes). `ext.observe` `on_write` hook, `ext.cache` routes through
  `write`. Spec `030-write-text.md` (WTXT-001 through WTXT-006).

### Changed

- **Docstrings migrated from Sphinx to Google style** (ID-080) — all 367
  Sphinx-style markers (`:param:`, `:returns:`, `:raises:`) across 25 source
  files converted to Google-style sections (`Args:`, `Returns:`, `Raises:`).
  `mkdocs.yml` updated to `docstring_style: google`. `sdd/DESIGN.md` §4
  updated with the new convention. Unlocks inline admonitions and markdown
  cross-references inside docstrings.

- **S3 listing methods no longer call `exists()` before listing** (ID-062) —
  removes a redundant API round-trip from `list_files`, `list_folders`, and
  `iter_children` in `S3Backend` and `S3PyArrowBackend`. The existing
  `FileNotFoundError` handler already covers non-existent paths.

- **`list_folders()` returns `Iterator[FolderEntry]`** (ID-072) — was
  `Iterator[str]`. Use `.name` for the folder name, `.path` for the full path.

- **`iter_children()` returns `Iterator[FileInfo | FolderEntry]`** (ID-072) —
  was `Iterator[FileInfo | str]`. Use `isinstance(entry, FolderEntry)` instead
  of `isinstance(entry, str)` to distinguish folders from files.

- **Store docstring rewrite** (ID-074) — rewrote all Store method docstrings for
  accuracy and consistency. Fixed `write`/`write_atomic` str claim, corrected
  `read_text` errors reference.

- **`store.md` restructured with per-method `:::` directives** (ID-074) —
  individual method headings, admonitions for ordering, atomicity, metadata, and
  thread-safety. Added backend behavior matrix verified against backend source.

### Docs

- **README medium pass** (ID-081) — streamlined onboarding flow, added backend
  behavior matrix, restored correct extras and library names, fixed method count
  (27).

- **Docs site polish** (ID-064) — property return types now visible
  (`show_signature_annotations`), Fira Code font for code blocks,
  sticky navigation tabs, search suggest/highlight, tighter parameter
  list spacing, capability matrix icons.

## [0.16.0] - 2026-03-10

### Added

- **`Store.read_text()` convenience method** (ID-056) — reads a file and
  decodes to string. Wraps `read_bytes()` with `encoding` and `errors`
  parameters matching `pathlib.Path.read_text()`. Store-level only (no backend
  changes). `ext.observe` `on_read` hook, `ext.cache` routes through cached
  `read_bytes`. Spec `028-read-text.md` (RTXT-001 through RTXT-006).

- **`Store.iter_children()` combined listing** (ID-055) — yields both files
  (`FileInfo`) and folders (`str`) in a single pass, avoiding two round-trips.
  All 6 backends override with single-call implementations. `ext.observe`
  `on_list` hook, `ext.cache` caching and invalidation. Spec
  `027-iter-children.md` (ITER-001 through ITER-008).

- **`Store.ping()` health check** (ID-054) — lightweight, non-destructive
  backend connectivity verification. Delegates to `Backend.check_health()`.
  Per-backend strategies: Local (`exists` + `os.access`), S3 (`head_bucket`),
  S3-PyArrow (`get_file_info`), SFTP (`stat`), Azure
  (`get_container_properties`), Memory (no-op). `ext.observe` `on_ping` hook.
  Spec `026-health-check.md` (PING-001 through PING-010).

- **`RetryPolicy` dataclass** (ID-010) — unified retry configuration for transient
  backend errors. Frozen dataclass with `max_attempts`, `backoff_base`, `backoff_max`,
  `jitter`, and `timeout` fields. Each backend maps the policy to its native retry
  mechanism: SFTP (tenacity), S3 (botocore), Azure (ExponentialRetry), S3-PyArrow
  (PyArrow C++ + botocore). `RetryPolicy.disabled()` factory for single-attempt
  mode. Configurable via constructor (`retry=RetryPolicy(...)`) or dict config
  (`"retry": {"max_attempts": 5}`). ADR-0011, spec `025-retry-policy.md`.

- **`SFTPUtils` utility class** — groups `load_private_key` and `HostKeyPolicy`
  into a public re-export (`from remote_store.backends import SFTPUtils`).
  Replaces private `backends._sftp` imports in user-facing code.

### Changed

- **Authoritative docs restructured to ADF standard** (ID-059) — `sdd/DESIGN.md`
  trimmed to code style conventions only (sections 1-10 removed, duplicated specs).
  `sdd/DOCUMENTATION.md` condensed to rules + guides (~130 lines from ~456).
  `sdd/000-process.md` restructured to Intent/Rules/Guides (~75 lines from ~152).
  Audit files moved to `sdd/audits/`. `CONTRIBUTING.md` spec format section
  replaced with cross-ref to `000-process.md`. `CLAUDE.md` environment note removed,
  gh CLI `Forbidden operations` denylist replaced with ask-gated confirmation.

- **`from_yaml()` moved from `RegistryConfig` classmethod to `ext/yaml.py`** (ID-002)
  YAML config loading requires an optional dependency (`pyyaml` or `ruamel.yaml`),
  same as the Pydantic adapter. Moved to `ext.yaml` for consistency with the
  extension architecture (ADR-0008). Import changes:
  `from remote_store.ext.yaml import from_yaml`.

### Docs

- **RTD docs now default to stable release** — changed all docs deep links in
  user-facing files (README, guides) from `/en/latest/` to `/stable/`, dropping
  the `/en/` language prefix (single-language project) and pointing to the most
  recent PyPI release instead of unreleased master. Updated DOCUMENTATION.md
  canonical URL policy and CONTRIBUTING.md release checklist. Requires RTD admin:
  default version = `stable`, URL versioning scheme = `/version/path/`.

- **README API table audit** — added missing `iter_children()` to Browse &
  Inspect section, added 5 missing example scripts to Examples table
  (`caching`, `config_loaders`, `capabilities_and_errors`, `path_model`,
  `retry_policy`), added `ext.yaml` to Extensions table, updated method count
  from 23 to 26 in comparison table, fixed stale PyArrow `native_path()`
  limitation note. Added `ext-yaml.md` API reference page and nav entry.

- **Audit 003 fixes** (AF-022 through AF-040) — documentation quality audit
  follow-up. 16 findings fixed, 3 closed as non-defects. Key changes:
  7 missing example doc pages added, observe hook table completed (`on_ping`,
  `open_atomic`), private imports replaced with public API in 4 guides,
  `CacheBackend` protocol docstrings added, CONTRIBUTING.md spec listing
  simplified (no longer goes stale), mkdocstrings `show_if_no_docstring: false`
  for proxy class overrides.

## [0.15.0] - 2026-03-08

### Added

- **`hatch run notebooks` smoke-test runner** (ID-048) — lightweight script (`tests/scripts/run_notebooks.py`) that executes tutorial notebook code cells via `exec()` without requiring Jupyter. Wired into `hatch run all` and CI `examples` job. Skips `benchmark_analysis.ipynb` (needs pre-generated data).
- **`Store.open_atomic(path, overwrite=False)`** — context manager for streaming atomic writes (ID-026, SAW-001 through SAW-015). Yields a writable file object backed by a temporary location; on successful exit the file is atomically promoted to the target path, on exception the temporary artifact is cleaned up. Eliminates the memory-buffering requirement of `write_atomic()` for large files. All 6 backends supported.
- **`Backend.open_atomic(path, overwrite=False)`** — new abstract method on the Backend ABC. Per-backend temp-path strategies: `mkstemp`+`os.replace` (Local), `.~tmp.*`+`posix_rename` (SFTP), `SpooledTemporaryFile`+PUT (S3, S3-PyArrow, Azure non-HNS), temp blob+DFS rename (Azure HNS), `BytesIO` buffer (Memory).
- **Data lake medallion notebook** (`examples/notebooks/04_data_lake_medallion.ipynb`) — end-to-end Bronze/Silver/Gold pipeline using `Store.child()`, PyArrow, Polars, and DuckDB. Generates ~3,500 sensor readings with realistic quality issues, cleans through medallion layers, and runs analytical queries on gold. Runs entirely on `MemoryBackend`.
- **`Store.native_path(key)`** — converts a store-relative key to the backend-native path (STORE-015). Inverse of `to_key()`. Used by the PyArrow adapter for Tier 1 fast-path reads.
- **`Backend.native_path(path)`** — converts a backend-relative key to the backend-native path (BE-025). Default is identity; `S3PyArrowBackend` prepends bucket prefix.
- **PyArrow adapter Tier 1 native fast-path reads** (ID-037, PA-010) — `StoreFileSystemHandler` now probes for a native PyArrow filesystem at construction via `store.unwrap(pyarrow.fs.FileSystem)`. When available (e.g., `S3PyArrowBackend`), `open_input_file` delegates directly to the native FS, bypassing Python I/O for zero GIL overhead with C++ range requests and I/O coalescing.
- **`S3PyArrowBackend.unwrap()`** now accepts `pyarrow.fs.FileSystem` base class in addition to `pyarrow.fs.S3FileSystem`.
- **Parallel batch operations** (ID-035) — `batch_delete`, `batch_copy`, and `batch_exists` now accept `concurrent=True` and `max_workers=N` keyword arguments for parallel execution via `ThreadPoolExecutor`. Cloud backends benefit significantly from concurrent I/O over sequential execution. `stop_on_error` is incompatible with `concurrent=True` (raises `ValueError`). Spec: BATCH-020 through BATCH-025.
- **`ext.cache` — store-level caching middleware** (ID-025) — `cached_store(store, ttl=300)` wraps a Store in a proxy that caches read-only operations (`exists`, `is_file`, `is_folder`, `read_bytes`, `get_file_info`, `get_folder_info`, `list_files`, `list_folders`, `glob`) with TTL-based expiration. All mutating operations automatically invalidate affected entries. `max_content_size` limits memory for large files. Thread-safe. Spec: CACHE-001 through CACHE-015.
- **`ext.partition` — Hive-style partition path helpers** (ID-036) — `partition_path(filename, **partitions)` builds paths like `year=2026/month=03/data.parquet`, `parse_partition(path)` extracts the partition dict and filename. Pure Python, zero dependencies. Spec: PART-001 through PART-013.

### Documentation

- **Documentation overhaul** (DOC-001) — Diataxis nav restructure (Getting Started / Guides / Reference / Explanation), extension API reference pages for all 9 ext modules, 7 new content pages (capabilities matrix, choosing a backend, troubleshooting, migration, architecture overview, security model, further reading), research docs surfaced on site, docstring audit for Store/Backend/errors with complete `:param:`/`:returns:`/`:raises:` and examples, cross-links between guides and API reference pages.

## [0.14.0] - 2026-03-07

### Changed

- **`_stacklevel` removed from public `from_dict()` signature** (ID-043)
  Internal `_stacklevel` parameter no longer leaks into the public
  `RegistryConfig.from_dict()` API. Warning stack-level control is now handled
  via a private `_from_dict()` helper.

### Fixed

- **`Registry.get_store()` no longer owns the shared backend** (ID-041)
  Stores returned by `get_store()` now set `_owns_backend = False`, preventing
  a store's `close()` from shutting down the cached backend and breaking sibling
  stores. `Registry.close()` remains the lifecycle owner.

- **`Store.move()` and `Store.copy()` short-circuit when `src == dst`** (ID-040)
  Moving or copying a file to itself is now a uniform no-op across all backends.
  Source existence is verified via `is_file()` (not `exists()`), so folders at
  the source path correctly raise `NotFound`. Spec: STORE-008a.

### Added

- **Data lake patterns guide** (ID-034)
  New guide (`guides/data-lake-patterns.md`) documenting Bronze/Silver/Gold
  medallion architecture using `Store.child()` + `ext.arrow` + `ext.transfer`.
  Covers PyArrow, Polars, DuckDB, Delta Lake integration, batch partition
  operations, cross-backend transfer, and testing without cloud credentials.
  Includes honest assessment of where remote-store fits vs. Databricks/Spark.

- **Credential hygiene documentation** (ID-042)
  Added "Credential hygiene" section to README and updated `examples/configuration.py`
  with `Secret` wrapping, `from_dict()` auto-wrapping, and `.reveal()` usage.

- **`RegistryConfig.from_toml()` — TOML config loader** (ID-005)
  Load config from a standalone `.toml` file or from `pyproject.toml` via
  `table=("tool", "remote-store")`. Zero dependencies on Python 3.11+;
  optional `tomli` backport for 3.10. Spec: CFG-008, CFG-009.

- **`RegistryConfig.from_yaml()` — YAML config loader** (ID-002)
  Load config from a YAML file. Accepts `pyyaml` (primary) or `ruamel.yaml`
  (fallback). Spec: CFG-010, CFG-011.

- **Unknown top-level key warning in `from_dict()`** (CFG-012)
  `from_dict()` now emits `UserWarning` for unrecognized keys like `"backend"`
  (typo for `"backends"`), preventing silently empty configs.

- **`pydantic_to_registry_config()` — Pydantic adapter** (ID-003)
  Convert any Pydantic `BaseModel` or `BaseSettings` instance to a
  `RegistryConfig` via `model_dump() → from_dict()`. Supports env-var binding,
  `.env` file loading, and validation via `pydantic-settings`. Optional
  `pydantic` extra. Spec: CFG-015, CFG-016, CFG-017.

## [0.13.0] - 2026-03-03

### Added

- **`Secret` wrapper and credential hygiene** (ID-039, SEC-001 through SEC-008)
  `Secret` type in `_config.py` wraps sensitive credential strings: `repr()`
  and `str()` return `'***'`, `.reveal()` returns the plain value.
  `RegistryConfig.from_dict()` auto-wraps known sensitive keys (`key`, `secret`,
  `password`, `account_key`, `sas_token`, `connection_string`). All backends
  accept `str | Secret` for credential params via `_reveal()`. SFTP coerces
  `host_key_policy` strings to `HostKeyPolicy` enum. `SecretRedactionFilter`
  logging filter scrubs `Secret` instances from log record args.
  Spec: `sdd/specs/020-credential-hygiene.md`.

- **Intrinsic stdlib logging** (ID-004, OBS-008)
  Core modules and extensions now use `log = logging.getLogger(__name__)` with `NullHandler`
  on the `"remote_store"` root logger. DEBUG for method entry, INFO for
  write/delete/move/copy completion. Structured `extra={}` with `op`, `path`,
  `backend` keys. Existing logger names standardised (`_log` -> `log`,
  `logger` -> `log`).

- **`ext.observe` — observability hooks** (ID-024, ADR-0010, OBS-001 through OBS-010)
  `observe(store, on_read=..., on_write=..., on_any=..., around=...)` wraps a
  Store in an `ObservedStore` proxy that fires callbacks after each operation.
  `StoreEvent` frozen dataclass carries operation, path, backend, timing, error,
  and metadata. `BufferedObserver` queues events for batched delivery on a
  background thread. Drift-protection test ensures new Store methods cannot
  silently bypass observation. Spec: `sdd/specs/019-ext-observe.md`.

- **`ext.otel` — OpenTelemetry bridge** (ID-024, OBS-011 through OBS-014)
  Pre-built hooks that emit OpenTelemetry spans and metrics. `otel_observe(store)`
  wraps a Store with distributed tracing (`store.{op}` spans with `CLIENT` kind)
  and three metric instruments (operations counter, errors counter, duration
  histogram). Depends only on `opentelemetry-api` (zero-cost no-ops without SDK).
  New optional extra: `pip install "remote-store[otel]"`.
  Spec: `sdd/specs/019-ext-observe.md` (OBS-011--OBS-014).

### Fixed

- **`get_folder_info("")` crashed with `InvalidPath` for root folders** (BUG-001)
  Added `RemotePath.ROOT` class-level sentinel that bypasses `__init__` validation
  (`str(ROOT) == "."`). Fixed all 6 backends and `_rebase_folder_info` to return
  `RemotePath.ROOT` for root-level queries. Store methods now accept `"."` as a
  root alias so that `str(folder_info.path)` round-trips correctly.
  Spec: `sdd/specs/004-path-model.md` (PATH-015).

## [0.12.0] - 2026-03-01

### Added

- **S3, S3-PyArrow, and Azure native glob** (BK-002, ID-007, GLOB-018/019/020)
  All cloud backends now override `Backend.glob()` with prefix-optimized listing
  and client-side regex filtering. Local, S3, S3-PyArrow, and Azure backends
  now declare `Capability.GLOB`.
  Shared glob helpers extracted to internal `_glob.py` module.

## [0.11.0] - 2026-03-01

### Added

- **Glob pattern matching — three-tier design (ADR-0009)** (BK-002, ID-007)
  - **Tier 1:** `list_files(pattern=…)` — universal `fnmatch` name filtering, works with every backend (needs only `LIST`)
  - **Tier 2:** `Store.glob()` / `Capability.GLOB` — native backend glob, capability-gated (like `unwrap()`). `LocalBackend` implements via `pathlib`
  - **Tier 3:** `ext.glob.glob_files()` — portable full-glob fallback with `**` recursive patterns and `[abc]`/`[!abc]` character classes; delegates to native glob when available, otherwise `list_files` + client-side regex
### Changed

- **Beta status.** Project classifier changed from Alpha to Beta. Core API
  (Store, Registry, Backend, models, errors) is now considered stable.
  See CONTRIBUTING.md § Stability tiers.

## [0.10.0] - 2026-02-28

### Added

- **Extension namespace contract (ADR-0008)** — formalized the `ext.*` namespace contract: public API only, no lifecycle ownership, `CapabilityNotSupported` propagation, export rules for pure-Python vs optional-dependency extensions, development lifecycle, and third-party naming convention. Added extensions guide, expanded CONTRIBUTING.md checklist, contract enforcement tests, updated CLAUDE-REFERENCE.md ripple-check table (ID-027)

### Changed

- **S3-PyArrow read path optimization** — removed `BufferedReader` from `S3PyArrowBackend.read()`, added `read()` + chunked `readline()` to `_PyArrowBinaryIO`, eliminating double-copy overhead on streaming reads (ID-031, RFC-0003)
- **Benchmark tiered modes, backend filtering, and comparative docs** — replaced binary `slow`/not-slow split with three tiers (quick/standard/full), added `--backend` filter for single-backend runs (deselects instead of skipping to avoid fixture setup), added `--bench-timeout` watchdog (Windows-compatible), added `--comparative` and `--markdown` modes to `report.py` for remote-store vs raw SDK vs fsspec comparison tables, updated hatch scripts. Comparative results and performance guide now populated with measured Docker benchmark data across 4 backends (ID-020)
- **Release CI: GitHub Release as single trigger** — `publish.yml` now triggers on `release: types: [published]` instead of `push: tags: ["v*"]`. The GitHub Release becomes the single event that triggers PyPI publish (ID-028)
- **Versioned documentation with mike** — `docs.yml` split into two jobs: `deploy-dev` (master push deploys "dev" alias) and `deploy-release` (release published deploys versioned docs with "latest" alias). Version switcher dropdown added to docs site. Requires changing GitHub Pages source to "Deploy from a branch" (`gh-pages`) (ID-029)

## [0.9.0] - 2026-02-28

### Added

- **Transfer operations (`ext.transfer`)** — `upload`, `download`, and `transfer` functions for moving data between local files and Stores or between two Stores. All streaming (never loads full file into memory), with optional `on_progress` callback per chunk. `upload` streams a local file to a Store, `download` reads in 1 MiB chunks to a local file, `transfer` pipes between any two Stores. Supports `overwrite` flag. Pure Python, no extra dependencies, unconditional top-level export (ID-023, unifies ID-001 + ID-009)
- **Batch operations (`ext.batch`)** — `batch_delete`, `batch_copy`, and `batch_exists` convenience functions for operating on collections of paths. Sequential execution with error aggregation via `BatchResult` (succeeded/failed split). Supports `stop_on_error`, `missing_ok`, and `overwrite` options. Pure Python, no extra dependencies, unconditional top-level export (ID-022)
- **PyArrow FileSystem adapter (Phase 1)** — `StoreFileSystemHandler` wraps any `Store` into a `pyarrow.fs.PyFileSystem`, enabling seamless interop with PyArrow datasets, Pandas, Polars, DuckDB, PyIceberg, and Delta Lake. Includes `pyarrow_fs()` convenience factory, `_StoreSink` write buffer with spill-to-disk, tiered read strategy (Tier 2 BufferReader for small files, Tier 3 PythonFile for large seekable files), complete error mapping (PA-019/020), and conditional top-level export. Install with `pip install "remote-store[arrow]"`. Tier 1 native fast-path deferred to Phase 2 (ID-016)
- **`Store.unwrap(type_hint)`** — delegates to `Backend.unwrap()`, exposing the backend's native handle through the public Store surface. Used by the PyArrow adapter and available to all callers (STORE-013)
- **Concurrency and atomicity guide** — new `guides/concurrency.md` documenting TOCTOU race on `overwrite=False` (all backends) and non-atomic `move()` (S3, S3-PyArrow, Azure non-HNS, SFTP fallback), with per-backend summary table and practical workarounds. Cross-referenced from all backend guides (AF-010)
- **Capability gating tests** — 14 tests verifying all 12 Store methods that require a capability raise `CapabilityNotSupported` when the backend lacks it, with correct `.capability` attribute value and backend name propagation (AF-012, STORE-006)
- **S3 and SFTP error path tests** — mock-based tests for `PermissionDenied` (S3-016: HTTP 403/accessdenied, SFTP-021: `errno.EACCES`), `AlreadyExists` (SFTP-022: `errno.EEXIST`), and `BackendUnavailable` (S3-017: endpoint/connect/timeout/dns errors, SFTP-023: `paramiko.SSHException`). Removed `pragma: no cover` from now-tested `_classify_error`/`_map_exception` branches (AF-013)
- **CI gate in publish workflow** — `publish.yml` now runs lint, typecheck, and tests (Python 3.10 + 3.13) before building and publishing to PyPI, preventing broken tags from reaching the registry (AF-014)

## [0.8.0] - 2026-02-27

### Added

- **`Store.child(subpath)` — runtime sub-scoping** — returns a new Store scoped to a subfolder, sharing the parent's backend instance (no new connections). Child stores do not close the shared backend on `close()` or context manager exit. Validated via `RemotePath`, chainable (`store.child("a").child("b")`), equality-transparent with directly constructed stores. Spec: `015-store-child.md` (ID-021)
- **Cloud backend examples** — 5 new example scripts (`s3_backend.py`, `s3_pyarrow_backend.py`, `sftp_backend.py`, `azure_backend.py`, `store_child.py`) demonstrating each backend with self-contained env-var configuration and graceful failure messages. All Store API methods now have example coverage
- **Claude Code reusable skills** — 6 slash-command skills in `.claude/commands/` codifying recurring workflows: `/ripple-check` (cross-reference validation), `/release` (6-phase release checklist), `/add-backend` (12-step scaffolding), `/backlog-sync` (backlog update helper), `/pr-preflight` (11-check pre-submission validation), `/add-spec` (SDD spec + test scaffolding) (ID-030)

### Changed

- **Release checklist expanded** — replaced the 5-item release checklist in CONTRIBUTING.md with a 6-phase process covering pre-flight, content freeze, version bump, validation, ship with PR review gate, and post-release verification. GitHub Release is the intended single trigger for PyPI publish and docs deploy (ID-028, ID-029 track the CI changes)

### Fixed

- **`streaming_io.py` example leaked file handles on Windows** — `store.read()` streams were not closed before `TemporaryDirectory` cleanup, causing `PermissionError` on Windows due to file locking. Streams are now used as context managers

## [0.7.0] - 2026-02-27

### Added

- **`MemoryBackend` — in-memory backend** — tree-indexed, zero dependencies, no filesystem access. Supports all 8 capabilities with zero conformance test skips. Primary use cases: unit testing, interactive exploration, documentation examples, CI speed. Registered as `"memory"` backend type, always available (no optional extra). Store test fixtures migrated from `LocalBackend` + `tempfile` to `MemoryBackend` (ID-017)
- **PyArrow FileSystemHandler adapter spec** — drafted `sdd/specs/014-pyarrow-filesystem-adapter.md` for `StoreFileSystemHandler` wrapping any `Store` into a `pyarrow.fs.PyFileSystem`. Tiered read strategy (native fast path / BufferReader / PythonFile), spill-to-disk writes, complete error mapping (ID-016)
- **Backend `__repr__` with credential masking** — all 6 backends now implement `__repr__()`. Secrets display as `'***'` when set and `None` when unset; identifiers (bucket, host, container) are shown in clear text (AF-008)

### Changed

- **S3/S3-PyArrow `get_folder_info()` on empty folders** — no longer raises `NotFound`; the `exists()` check already gates non-existent paths. Azure non-HNS retains current behavior since virtual folders can't be empty (AF-004)
- **`Registry.close()` error handling** — now closes all backends even if one raises, always clears the cache, and re-raises the first error (AF-009)

### Removed

- **`RemoteFile` / `RemoteFolder` model classes** — removed dead code from models, `__all__`, tests, docs, and specs (AF-011)

### Fixed

- **README Azure SDK name** — corrected from wrong package name to `azure-storage-file-datalake` (AF-015)
- **CONTRIBUTING.md** — added spec 012 reference (AF-015)
- **Azure configuration example** — added to `examples/configuration.py` (AF-015)

## [0.6.0] - 2026-02-25

### Added

- **`DirectoryNotEmpty` error type** — new `RemoteStoreError` subclass raised when a non-recursive folder delete targets a non-empty folder. Replaces generic `NotFound` with a descriptive error (AF-005)
- **`_ErrorMappingStream`** — `io.RawIOBase` proxy that wraps streams returned by `Backend.read()`, catching `OSError` during lazy reads and mapping them through each backend's error classifier. Prevents native exceptions from leaking after `_errors()` context manager exits (AF-006)
- **Auto-registration of all backends** — `_register_builtin_backends()` now registers S3, SFTP, and S3-PyArrow backends (in addition to local and Azure) when their dependencies are installed (AF-001)
- **SFTP `_map_exception()` method** — single source of truth for SFTP error classification, used by both `_errors()` and `_ErrorMappingStream` (AF-006)
- **SFTP empty folder support** — `get_folder_info()` on an empty SFTP directory now returns `FolderInfo(file_count=0)` instead of raising `NotFound` (AF-004)

### Changed

- **BREAKING**: Removed `Capability.GLOB` and `Capability.RECURSIVE_LIST` enum members that had no corresponding backend methods (AF-002)
- **S3/S3-PyArrow `close()`** — no longer calls `clear_instance_cache()`, which was a global side-effect affecting all s3fs instances in the process (AF-003)
- **Azure/S3-PyArrow `read()`** — eliminated double-buffering by wrapping `_ErrorMappingStream` directly in `BufferedReader` instead of nesting two `BufferedReader` layers

### Fixed

- **Lazy stream error mapping** — `OSError` raised during `stream.read()` after `Backend.read()` returns is now properly mapped to `RemoteStoreError` subtypes instead of leaking as raw exceptions (AF-006)
- **Exception chaining** — stream error mapping uses `from exc` to preserve original traceback for debugging

---

## [0.5.0] - 2026-02-23

### Added

- **Azure backend** (`AzureBackend`) — new built-in backend for Azure Blob Storage and ADLS Gen2 using `azure-storage-file-datalake` directly. Adapts at runtime to Hierarchical Namespace (HNS) accounts for atomic rename and real directories, while remaining fully functional on plain Blob Storage. Install with `pip install "remote-store[azure]"`. (BK-001, spec 012)
- **Streaming reads for Azure** — `read()` returns a forward-only streaming `BinaryIO` via `_AzureBinaryIO` adapter wrapping `StorageStreamDownloader.chunks()`, consistent with other backends
- **Azurite CI integration** — Azure backend tests run against Azurite Docker emulator in CI
- **Azure backend guide** — `guides/backends/azure.md` with installation, auth options, HNS vs non-HNS behavior, and Azurite local development

### Changed

- **SIO-001 seekability clarification** — `read()` streams are not guaranteed to be seekable; seekability is a backend-level property. Callers needing seekability should use `read_bytes()` + `BytesIO`
- **AZ-020 spec updated** — changed from BytesIO wrapper to streaming adapter

---

## [0.4.4] - 2026-02-23

### Added

- **Community standards** — CODE_OF_CONDUCT.md (Contributor Covenant v2.1), SECURITY.md (vulnerability reporting policy), issue templates (bug report + feature request), PR template, and CODEOWNERS
- **Dependabot** — automated dependency updates for pip and GitHub Actions (weekly, Mondays)
- **CodeQL** — GitHub code scanning workflow for Python on push/PR and weekly schedule
- Security section in README linking to vulnerability reporting
- **Streaming conformance tests** — 5 tests (x4 backends) that prevent regression of v0.4.3 streaming fixes: not-BytesIO assertion, chunked reads, stream position, BinaryIO write, and write-from-current-position (SIO-001, SIO-003)

---

## [0.4.3] - 2026-02-19

### Fixed

- **Streaming read/write loaded entire files into memory** — all four backends (Local, S3, S3-PyArrow, SFTP) now use true streaming for `read()` and `write()` with `BinaryIO` content, matching the spec's streaming-first intent
- **SFTP copy/move buffered entire files** — `copy()` and `move()` fallback now stream chunks using `_CHUNK_SIZE` instead of loading source into memory
- **Broken API reference link in README** — ReadTheDocs URL was missing `/en/latest/` prefix, causing 404 on PyPI

### Changed

- **Versioning docs consolidated** — removed outdated duplicate from `sdd/000-process.md`, canonical source is now `CONTRIBUTING.md`

---

## [0.4.2] - 2026-02-19

### Fixed

- **PyPI relative links broken** — README example scripts, notebooks, and CONTRIBUTING.md links used relative paths (`examples/quickstart.py`, `CONTRIBUTING.md`, etc.) which resolve to 404 on PyPI; converted all to absolute GitHub URLs

---

## [0.4.1] - 2026-02-19

### Fixed

- **PyPI logo broken** — README image used relative path (`assets/logo.png`) which doesn't resolve on PyPI's CDN; changed to absolute raw GitHub URL
- **Documentation site out of date** — specs 010 (native path resolution) and 011 (S3-PyArrow backend) and ADR-0005 were missing from the MkDocs site and navigation
- **Navigation on RTD** — added `navigation.instant` to MkDocs Material config so sidebar stays visible across page loads

### Added

- PyPI version, Python versions, Read the Docs, and license badges in README
- Read the Docs publishing (`remote-store.readthedocs.io`)
- "Going Public" section in DEVELOPMENT_STORY.md

### Changed

- `Documentation` URL in `pyproject.toml` now points to Read the Docs instead of GitHub Pages
- `CITATION.cff` URL updated to Read the Docs
- `.readthedocs.yaml` build OS bumped to ubuntu-24.04

---

## [0.4.0] - 2026-02-19

### Added

- **S3-PyArrow hybrid backend** — uses PyArrow's C++ S3 filesystem for reads/writes/copies (higher throughput for large files) and s3fs for listing/metadata/deletion. Drop-in alternative to `S3Backend` with the same constructor signature.
  - Install via `pip install "remote-store[s3-pyarrow]"`
  - Spec: `sdd/specs/011-s3-pyarrow-backend.md`
- New optional extra: `s3-pyarrow` (requires `s3fs>=2024.2.0` and `pyarrow>=14.0.0`)
- Dual `unwrap()` support: returns either `pyarrow.fs.S3FileSystem` or `s3fs.S3FileSystem`

---

## [0.3.0] - 2026-02-18

### Added

- **`Store.to_key(path)`** — public method to convert backend-native paths to store-relative keys
- **`Backend.to_key()`** — backend-level native-path-to-key conversion
- Python 3.14 support — added to CI test matrix and PyPI classifiers
- **PyPI publish workflow** — trusted publishing (OIDC) via GitHub Actions on `v*` tags (BL-001)
- **SFTP backend documentation** — `docs/backends/sftp.md` with installation, usage, and API reference (BL-002)
- **CITATION.cff** — enables GitHub's "Cite this repository" button (BL-005)
- **Development backlog** — `sdd/BACKLOG.md` for tracking release blockers, prioritized work, and ideas
- Versioning policy added to SDD process doc (`sdd/000-process.md`)
- Set up GitHub Pages docs hosting via `actions/deploy-pages` (BL-008)

### Fixed

- Store round-trip bug: `list()` returned backend-relative paths that included `root_path`, breaking re-use as input to `read()`/`delete()`
- CI: fixed cross-platform `type: ignore` comments for S3 backend

### Changed

- **README rewritten** — approachable, dev-friendly tone with scannable layout (BL-003, BL-004)
- Pinned minimum versions on public extras: `s3fs>=2024.2.0`, `paramiko>=2.2`, `tenacity>=4.0`
- Removed `typing-extensions` from core dependencies (unused — Python 3.10+ covers all needs)
- Removed `azure` extra (`adlfs`) — no Azure backend exists yet; will be re-added with the backend

---

## [0.2.0] - 2026-02-17

### Added

- **SFTP backend** via pure paramiko with host key policies (STRICT / TOFU / AUTO_ADD), PEM key sanitization, and tenacity retry on transient SSH errors
- Simulated atomic writes (temp file + rename) with documented orphan-file caveat
- `HostKeyPolicy` enum and `load_private_key()` utility for key management
- `_sanitize_pem()` for Azure Key Vault PEM compatibility

### Changed

- `sftp` optional dependency changed from `paramiko + sshfs` to `paramiko + tenacity`
- Version bumped to 0.2.0

---

## [0.1.0] - 2026-02-14

### Added

- **Store** — primary user-facing abstraction for folder-scoped file operations
- **Registry** — backend lifecycle management with lazy instantiation and context manager support
- **RegistryConfig / BackendConfig / StoreProfile** — declarative, immutable configuration with `from_dict()` for TOML/JSON parsing
- **RemotePath** — immutable, validated path value object with normalization and safety checks
- **Local backend** — stdlib-only reference implementation with full capability support
- **Capability system** — backends declare supported features; unsupported operations fail explicitly
- **Normalized error hierarchy** — `NotFound`, `AlreadyExists`, `InvalidPath`, `PermissionDenied`, `CapabilityNotSupported`, `BackendUnavailable`
- **Streaming-first I/O** — `read()` returns `BinaryIO`, `write()` accepts `bytes | BinaryIO`
- **Atomic writes** — `write_atomic()` via temp-file-and-rename
- **Empty path support** — `""` resolves to store root for folder/query operations (see ADR-0004)
- **Full type safety** — mypy strict mode, `py.typed` marker
- **Spec-driven development** — 7 specifications, 4 ADRs, full test traceability with `@pytest.mark.spec`
- **Examples** — 6 runnable Python scripts and 3 Jupyter notebooks
- **CI** — ruff, mypy, pytest (Python 3.10–3.13), example validation

### Known Limitations

- Only the local filesystem backend is implemented. S3, Azure, and SFTP backends are planned.
- No glob/pattern matching support yet (`Capability.GLOB` is declared but unused).
- No async API (sync-only by design; compatible with structured concurrency).
