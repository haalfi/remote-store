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

- [ ] **BUG-182 — (Candidate) Verify HNS `write_atomic` metadata survives rename in integration**
  `test_write_atomic_hns_metadata_preserved` (BUG-181) only verifies that `metadata=` is
  forwarded to `upload_data` on the temp file and that `WriteResult.metadata` echoes the
  caller's mapping by construction (WR-012). It cannot verify that ADLS Gen2 atomic rename
  preserves user-defined metadata on the live file (a filesystem-level semantics concern).
  When HNS integration tests are available: add `test_write_atomic_hns_metadata_survives_rename`
  — write with `metadata={"k": "v"}`; assert `get_file_properties()` on the final path
  returns `metadata["k"] == "v"`.
  Spec: WR-013, ASYNC-010.

---

## Backlog (Prioritized)

- [ ] **BK-167 — audit-012 simplifications (post-framework)**
  Follows BK-165 (audit phase complete, `sdd/audits/audit-012-docs-structure.md`).
  Authoring guide and framework wiring shipped — see BK-167 (partial) in
  `BACKLOG-DONE.md`. Framework cleanup: BK-167a.

  **Simplifications to evaluate (per audit-012 findings):**
  - F-03: raise link validation from `warn` to `error` in `mkdocs.yml`.
  - F-12: unify the three mechanisms for rendering `sdd/` top-level files
    (include-markdown wrappers vs. `_link_map.yml` vs. gen-files scan).
  - F-01/F-02: evaluate whether include-markdown wrappers should be replaced
    with gen-files virtual pages so repo-browser links resolve correctly, or
    whether `sdd/` top-level files move into `docs-src/design/` (removes the
    wrapper layer entirely but conflicts with R5 for process docs).
  - F-05/F-06/F-07/F-08: align nav structure to pure Diataxis and fix the
    `design/` URL prefix to match its nav position under Explanation.

  **Open questions from BK-165:**
  1. Should the docstring-driven examples chain stay (single source of truth,
     hidden machinery) or be replaced with static stubs (discoverability,
     duplication)?
  2. Should `sdd/` move under `docs-src/design/` to remove the wrapper layer?
     Tradeoff: cleaner build vs. moving authoritative artifacts off the
     established `sdd/` path that tooling and skills already reference.
  3. Is there a single declarative file describing every virtual page that
     would replace the four current generation mechanisms?

  **Depends on:** BK-165 (audit phase done).

- [~] **BK-167a — Documentation framework cleanup (spin-off from BK-167)**
  The framework first cut shipped under BK-167 (partial). This item bundles
  the cleanup findings from the self-review (Documentation expert and SDD
  expert) so the framework holds together as a system. Decisions already
  taken: no CHANGELOG entry (SDD-only, no user-facing behavior); no ADR
  (the framework rationale lives in audit-012 and the trio's Intent &
  Scope sections).

  **Convergent findings (both experts):**
  - C-1: `sdd/AUTHORING.md` Rule 1 asserts "Classes are recorded centrally"
    while open question Q4 (below) flags this as undecided. Either resolve
    Q4 or soften Rule 1.
  - C-2: Rule 4 names "the bridge" without defining or linking it; a reader
    of the file in isolation cannot act on it.
  - C-3: BK-167 entry was mixed-state without an `[~]` marker; this split
    resolves it.
  - C-4: "Source for the gate categories" subsection is meta-commentary
    (format Exclusion 3) and asserts a category↔R-id mapping without
    enumerating it.

  **Documentation expert findings:**
  - F-D-1: trio not surfaced from `README` or `CONTRIBUTING.md` beyond bare
    scope list — non-Claude contributors miss it.
  - F-D-4: "Diataxis" vs "Diátaxis" spelling drift across `DOCUMENTATION.md`
    and `AUTHORING.md`.
  - F-D-5: cross-link at `DOCUMENTATION.md:73` lacks an anchor.
  - F-D-6: `CONTENT-RULES.md` Rule 4 still names `DOCUMENTATION.md § 2` as
    placement authority — should also point to `AUTHORING.md` Rule 1.
  - F-D-7: `CONTRIBUTING.md` scope list does not link the trio docs.

  **SDD expert findings:**
  - F-S-1: `AUTHORING.md` Intent & Scope blends "where files belong" with
    "which constraints apply" — overlaps `DOCUMENTATION.md` /
    `CONTENT-RULES.md` scope. Tighten to placement only.
  - F-S-2: Rule 5's five gate categories each pass the Cross-check test
    independently. Promote to Rules 5–9 (or restructure as Rule 5 with
    sub-rules carrying clear normative force).
  - F-S-4: Guides "If unsure, assume dual" is a binding tiebreaker, belongs
    in Rule 1.
  - F-S-5: URL alignment is duplicated (`DOCUMENTATION.md` Rule 9 +
    `AUTHORING.md` Rule 5 gate category). Pick one home.
  - F-S-6: "API page building blocks" (~130 lines of "Required" templates)
    sits under Guides which the format says is non-binding. Either restore
    as Rules or extract to its own doc.
  - F-S-8: ripple-check table missing a row for "new authoritative process
    doc added."

  **Open question (carried from BK-167):**
  Q4. File classification mechanism — central manifest vs. inline per-file
  metadata (HTML comment markers, still plain Markdown). Inline keeps the
  class next to the file; central preserves a single auditable boundary.
  `sdd/AUTHORING.md` Rule 1 currently mandates central; adopting inline
  would amend that rule. Evaluate against F-13 (auditable boundary) and
  F-12 (one mechanism — currently in BK-167).

  **Depends on:** BK-167 (partial) shipped.

---

## Ideas

### Docs & Tooling

- [ ] **ID-173 — `check_api_docs.py` — `__all__` ↔ `docs-src/api/index.md`**
  Spun off from ID-171 (Backend sub-task done, see BACKLOG-DONE.md).
  Different IR from the method-caps checker: `{symbol_name: kind}` rather
  than `{method: caps}`; separate extractor pair, same compare pattern.
  Sources of truth: `remote_store.__all__` (primary public API) and
  `remote_store.backends.__all__` (secondary; e.g. `SFTPUtils`). Page side:
  parse `[Name](page.md)` link rows in the existing tables under `## Core`,
  `## Backends`, etc. Compare = set diff with missing/extra symbol messages.
  Stop and confirm before implementing — this is a genuinely different IR
  (per the Phase 1 reviewers' staged-rollout preference).

- [ ] **ID-172 — `check_api_docs.py` — `AsyncStore`/`AsyncBackend` ↔ `docs-src/api/aio.md`**
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
  - [FEATURES (authoritative)](https://github.com/haalfi/remote-store/blob/master/docs-src/reference/FEATURES.md)

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
  - `docs-src/reference/FEATURES.md` capability matrix.
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

