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

- [~] **BK-167a — Documentation framework tooling**
  Builds the build-time infrastructure that enforces the framework defined
  in BK-167. Author-facing rules (marker syntax, classification,
  directory defaults) are normative in
  [`AUTHORING.md`](AUTHORING.md); the tooling that enforces them is
  specified in [spec 047](specs/047-docs-framework-tooling.md). Decision
  rationale in [ADR-0027](adrs/0027-docs-bridge-single-mechanism.md).

  **Deliverables:**
  - **Bridge implementation**: single `scan.scan_dual_files` +
    `render.render_dual_pages` mechanism replacing include-markdown
    wrappers, `_link_map.yml`, and the legacy gen-files scan helpers.
    Resolves audit-012 F-01, F-02, F-11, F-12.
  - **File classification storage**: inline HTML-comment marker
    (`<!-- doc: dual dest=... -->`) with directory-default rules for
    SDD subdirs and `docs-src/`. Resolves Q4 (inline) and F-13.
  - **PR-time gate script** (`scripts/check_docs_framework.py`): seven
    checks G-01 through G-07 covering AUTHORING and DOCUMENTATION rules.
    Wired into `hatch run all`. Closes F-03, W-01.
  - **Nav/URL fixes** (folded in per design review): Diataxis-pure
    top-level nav, `explanation/design/` URL prefix, Changelog URL under
    Reference. Closes F-05, F-06, F-07, F-08, F-10. Verified by G-06.

  **Resolved questions:**
  - Q2 (move `sdd/`?) — no. `sdd/` paths are referenced by skills,
    agents, and ripple-check; the bridge adapts to the canonical path.
  - Q3 (single declarative file?) — no. Directory convention for SDD
    subdirs plus inline markers is one declarative system without a
    drift surface.
  - Q4 (manifest vs inline?) — inline. Central manifest reintroduces
    F-13's audit problem in a different location.

  **Ripple coverage for spec 047 / ADR-0027:**
  As SDD artefacts under `sdd/specs/` and `sdd/adrs/`, both files are
  rendered by the existing `gen_pages.py` filesystem scan
  (`render.render_sdd_wrappers`) at `design/specs/047-*.md` and
  `design/adrs/0027-*.md`. The `sdd/CLAUDE-REFERENCE.md` ripple-check
  row "A new authoritative process doc in `sdd/`" applies to trio-level
  process docs (AUTHORING / DOCUMENTATION / CONTENT-RULES / DESIGN /
  TESTING / 000-process), not SDD artefacts; its targets (CLAUDE.md
  framework section, sibling authority back-references,
  `docs-src/further/further-reading.md`) do not apply here. The new
  tooling-spec category is a content distinction recorded in
  [`000-process.md`](000-process.md) § Spec format; it does not require
  a structural ripple-check entry. Post-bridge (DOCFRAME-005), the
  unified scanner replaces the auto-render path; semantics unchanged.

  **Progress:** Step 1 landed — `_parse_marker`, `_classify_file`, `DualEntry`, `scan_dual_files` in `scripts/docs/scan.py` with five spec-traced tests (DOCFRAME-001..003).

  **Depends on:** BK-167 (framework defined and wired in).

- [ ] **BK-167b — Apply documentation framework; close audit-012 findings**
  Once the framework (BK-167) and its tooling (BK-167a) are in place,
  classify every existing `.md`, run the gate, and close the open
  audit-012 findings. Exit criterion: framework "up & running, tested &
  proven, documented & correct."

  **Audit-012 findings to close:**
  - F-03: raise link validation from `warn` to `error` in `mkdocs.yml`
    AND restore `mkdocs build --strict` in `.github/workflows/ci.yml`
    (currently relaxed so cross-presentation links from the trio do not
    block PRs before the bridge in BK-167a rewrites them). Absorbs W-01
    (no build-time enforcement of cross-version link safety): `not_found:
    error` plus mike's version-switch handling closes both.
  - F-01/F-02: include-markdown wrappers fail in the GitHub repo browser;
    resolved by the bridge chosen in BK-167a. The new
    `docs-src/design/authoring.md` wrapper introduced by BK-167 is removed
    as part of this transition.
  - F-05/F-06/F-07/F-08: align nav structure to pure Diataxis and fix the
    `design/` URL prefix to match its nav position under Explanation.
  - F-10: Changelog URL `/changelog/` contradicts nav position under
    Reference. Closed by enforcing `sdd/DOCUMENTATION.md` Rule 9 (URL
    alignment).
  - F-11: `_link_map.yml` comment says "repo-root files" but lists
    `sdd/000-process.md`. Closed when the bridge unification (BK-167a)
    replaces `_link_map.yml`.
  - F-13: excluded files auditable (closed by the classification system
    from BK-167 + BK-167a).

  **Other follow-up (from BK-167 self-review):**
  - F-S-6: `sdd/DOCUMENTATION.md` "API page building blocks" placement.
    Currently under Guides per the Authoritative Document Format, but the
    templates carry "Required" / "Optional" columns. Decide: restore as a
    Rule, extract to a separate doc, or soften the wording.

  **Open question:**
  - Q1: Should the docstring-driven examples chain stay (single source of
    truth, hidden machinery) or be replaced with static stubs
    (discoverability, duplication)?

  **Exit criteria:**
  - All `.md` files classified.
  - PR-time gate green on master.
  - All audit-012 findings closed (or explicitly deferred with rationale).

  **Depends on:** BK-167a (tooling).

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

