# Development Backlog
<!-- doc: repo-only -->

Active work items and ideas. Completed items live in
[BACKLOG-DONE.md](BACKLOG-DONE.md).

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

<a id="how-this-file-works"></a>
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

- [ ] **ID-230 — Benchmark overhead story: reproducible run of record + user-facing framing**
  spec: — · effort: M · audience: user.site, library.maintainer
  Purpose-2 half of the benchmark-suite rework (purpose-1 governance shipped
  as BK-309). The suite can now answer "what is remote-store's overhead and is
  it acceptable?", but the published answer rests on a single stale run:
  `benchmarks/results/comparative.md` was generated 2026-04-12 on a Windows
  laptop, and the four SVG charts in `docs-src/explanation/performance.md`
  derive from `.benchmarks/` JSON that is **not committed** (so they cannot be
  reproduced or trusted). Scope when picked up:
  1. Regenerate `comparative.md` + charts from one documented Linux/Docker run
     (BK-309's scheduled workflow now produces exactly this artifact — wire the
     run of record to it rather than a laptop).
  2. Commit the source JSON alongside the rendered outputs so the charts are
     reproducible and diffable.
  3. Add a dated, one-glance "overhead verdict" the README's Performance
     section can cite with confidence (lead with the answer, per
     `research/research-benchmark-suite-v2.md` Phase 3).
  Keep the machinery (`bench-report-user` verdicts, chart generator) — this is
  a data-freshness + framing item, not new tooling. Surfaced during the
  benchmark-suite analysis that produced BUG-228 / BK-309.

- [ ] **ID-225 — Evaluate migrating the docs stack from Material for MkDocs to Zensical**
  spec: — · effort: L · audience: user.site, library.maintainer, contributor.tooling
  Our docs foundation is entering maintenance mode as its authors converge on a
  successor. [Material for MkDocs is feature-frozen](https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/)
  (critical bug/security fixes for ~12 months, no new features), MkDocs 1.x is
  itself being forked (a `properdocs` MkDocs-1.x continuation now surfaces as a
  transitive docs dep, and a build-time banner warns MkDocs 2.0 will break all
  plugins/themes), and `mkdocs-llmstxt` (adopted in ID-220) is in maintenance
  mode for the same reason. The whole ecosystem is pointing at
  [**Zensical**](https://github.com/zensical/zensical) — a new MIT static site
  generator (Rust core, reads `mkdocs.yml` natively, with a migration path) built
  by the Material team. Crucially, `mkdocstrings`' author is rebuilding
  API-reference-from-docstrings *inside* Zensical — the exact capability our docs
  depend on `mkdocstrings` for.
  **Not prioritized:** Zensical is pre-1.0 and does **not** yet ship the
  API-reference feature we require, so "not yet — revisit when Zensical reaches
  API-reference parity" is a legitimate outcome. Kept visible here as the
  strategic anchor, not queued work.
  **Scope when picked up:** trial `zensical build` against our `mkdocs.yml`;
  confirm parity for the pieces we rely on (gen-files pages, mkdocstrings API
  reference, literate-nav order, BK-171 link rewrites, mike/RTD versioning); and
  fold in native `llms.txt` / `llms-full.txt` generation if Zensical ships it
  (its roadmap already speaks of LLM/agent consumption). This item is the
  **sunset trigger for the interim `mkdocs-llmstxt` adoption (ID-220)**: when the
  migration lands, the HTML→Markdown plugin is a prime candidate for replacement
  by a native feature.
  Background: [research](research/research-llms-full-txt-tooling.md).
  **Why ID, not BK:** unevaluated framework migration against a pre-1.0 upstream,
  no committed outcome.

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
  viability. Tracked as **ID-200 / ID-201 / ID-202** — all complete;
  see [BACKLOG-DONE.md](BACKLOG-DONE.md) (ID-201's disposition shipped
  as BK-257).

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

- [ ] **ID-123 — Cache key derivation from `ResolutionPlan` (Phase 2)**
  spec: RES-100 · effort: M · audience: user.api
  `ext.cache` derives cache keys from `ResolutionPlan` fields instead of
  ad-hoc `(operation, path)` tuples. Only valuable once `CompositeStore`
  (ID-121) exists — single-backend cache keys are already correct *for the
  default per-store cache*. The exception (audit-016 L8): a **shared**
  `cache_backend=` across two top-level stores at different backends/drives
  collides on `(op, path)` and serves one store's bytes for another's — not
  Graph-specific (same for two Local roots or S3 buckets), opt-in, but exactly
  the case identity-derived keys would close.
  - Spec: RES-100 (proposed in [043](specs/043-resolution-plan.md))
  - Depends on: ID-121 (CompositeStore)

---

## New Backends

- [ ] **ID-121 — CompositeStore (research complete)**
  spec: — · effort: L · audience: user.api
  `CompositeStore(Store)` — core Store subclass (not extension) that composes
  multiple stores into one. Deterministic fallthrough resolution for reads, union
  LIST (deduplicated), writes to primary tier only.
  - [Research](research/research-sqlalchemy-backend.md#52-compositestore-id-120)
    (anchor uses historical ID-120 from research doc; now ID-121 after swap)
  - Depends on: unified `resolve()` → `ResolutionPlan` (ID-120) — **satisfied**:
    `Store.resolve()` ships and returns a `ResolutionPlan` (see BACKLOG-DONE.md).
    Remaining: at least two working backends to be useful; pairs well with
    ID-119 (landed) — so both conditions are already met.
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
  - `tests/backends/sqlblob/test_config.py:148` asserts LAZY_READ is NOT
    declared — must split into dialect-conditional assertions.
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

## New Extensions

- [ ] **ID-217 — Async-native extension surface (owner for the deferred async `ext.*`)**
  spec: GR-003 · effort: L · audience: user.api
  `src/remote_store/aio/ext/` ships only `write.py` (`write_with_hash`); there is
  no async equivalent of `ext.glob`, `ext.observe`, `ext.otel`, or `ext.integrity`
  (audit-016 M6). A native `AsyncStore` consumer — the natural audience for an
  async-native backend such as Graph — reaches the full `ext.*` surface only by
  dropping to `AsyncBackendSyncAdapter` (ADR-0025), which forfeits the async
  streaming the backend exists to provide. GR-003 calls this out for `GLOB`
  specifically: async callers compose pattern matching over `list_files`
  themselves "until an async equivalent of `ext.glob` lands as a separate backlog
  item" — this is that item, and it owns the surface as a whole, not just glob.
  **Decision pending:** build per-extension async equivalents (glob first, as the
  smallest and the one a spec promises), or formally decline the ecosystem and
  document the sync-adapter route as the supported path for extension features
  over async backends. The `ext.cache`-over-bridged-backend guard is tracked
  separately as ID-218. Filed (not yet scoped) per audit-016 L10 / BK-268.

- [ ] **ID-218 — `ext.cache`: warn when wrapping a bridged (async-native) backend**
  spec: — · effort: S · audience: user.api
  `CachedStore` with an unset `max_content_size` materialises whatever the wrapped
  backend yields (`ext/cache.py`). Over a sync REST backend that is merely
  inconvenient; over an async-native backend reached through
  `AsyncBackendSyncAdapter` (ADR-0025) — a backend that exists precisely to
  *avoid* materialisation — it silently defeats the streaming the user chose the
  backend for. ADR-0025 § Risks flags this and promises the cache extension
  "should learn to warn when wrapped over a bridged backend (tracked separately)";
  this is that owner. Scope: emit a warning (or require an explicit
  `max_content_size`) when `cache()` wraps a `Store` whose backend is an
  `AsyncBackendSyncAdapter` and `max_content_size` is unset. Sibling of ID-217
  (async-native `ext.*`). Filed per audit-016 L10 / BK-268.

---

## Formal Verification

Dafny-section work earns its slot one of three ways: **(C)** prove a
spec clause is internally consistent and satisfiable, **(T)** certify
that a conformance test demands nothing the verified contract does not
(via the compiled `MemoryBackend` oracle), or **(O)** supply an
oracle-computed expected value for a property-based test. Runtime
backend gaps downstream of a Dafny-backed clause — a backend not
honouring a verified postcondition — are spec-conformance work, not
Dafny-section work; file those under the relevant backend section
(SFTP, Azure, S3, etc.).

Full doctrine and intake rules: [`sdd/formal/README.md`](formal/README.md)
§ "Three shapes of Dafny-section work: (C), (T), (O)".

*(none)*

---

## Maintenance / Long-horizon

- [ ] **ID-229 — Evaluate porting to httpx 1.0 (lift the `<1.0` cap)**
  spec: GR-033 · effort: M · audience: user.api
  BUG-225 capped the `graph` and `httpx` extras at `httpx>=0.24.0,<1.0`
  after the drift guard's `--pre` re-resolution pulled `httpx==1.0.dev3`
  and the async graph backend failed to import. That pre-release turned
  out to be a **wholesale API rewrite**, not the exception-hierarchy
  reorg the BUG-225 diagnosis first assumed: `1.0.dev3` drops
  `httpx.AsyncClient`, `httpx.TransportError`, `httpx.DecodingError`,
  `httpx.HTTPStatusError`, `Timeout`, `Limits` — essentially the entire
  client surface the graph backend (`AsyncClient` in ~30 sites) and the
  `[httpx]` HTTP adapter are built on. Coding around a single missing
  symbol would only convert an honest import failure into a falsely-green
  import that then explodes at runtime on `httpx.AsyncClient(...)`, so the
  cap is the honest interim posture.
  **Upstream context:** the cap matches the maintainers' own guidance.
  httpx 0.28.x is still a pre-1.0 line; the "1.0.dev" / "httpx2" threads
  are about the project's next major API *direction*, not a released
  stable 1.x series. In the late-2024 V1 discussion the maintainers said
  httpx was not yet at a 1.0 SemVer release and recommended **pinning to
  0.28 while reviewing deprecations** — which is exactly what `<1.0` does.
  So `<1.0` is not a defensive over-cap; it tracks the current usable
  branch until a real stable 1.x ships.
  Ref: [encode/httpx#3344](https://github.com/encode/httpx/discussions/3344).
  **When picked up:** real httpx 1.0 stable is out and pins install
  cleanly against it. Diff the actual 1.0 public API against 0.28
  (`AsyncClient`, `Response`, `Timeout`/`Limits`, the transport-error and
  decoding-error bases, `respx` compatibility); decide port-vs-hold; if
  porting, update `_graph/*.py` + the `[httpx]` backend, raise the cap,
  and refresh the `graph` / `httpx` drift baselines. The `graph` drift
  smoke wired in BUG-225 (`scripts/drift_smoke_map.py`) now imports the
  async graph module directly, so a future 1.0 break fails the graph leg
  loudly instead of riding green on the top-level fallback.
  **Why ID, not BK:** unevaluated migration against an upstream whose 1.0
  shape is not yet stable — the same posture as ID-225. Mirrors the
  revisit discipline of ID-150.

- [ ] **ID-150 — Revisit informational `verify-tla` CI status (2026-10-19)**
  spec: — · effort: S · audience: library.maintainer
  First revisit ticket for the informational `verify-tla` job landed under
  ID-147 on 2026-04-19. Per [`sdd/formal/README.md` § Authoring rules](formal/README.md#authoring-rules) (3),
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

- [ ] **ID-215 — `RemotePath` deferred pathlib-parity members**
  spec: PATH-016, PATH-017 · effort: S · audience: user.api
  Follow-up from ID-196. That item shipped `as_posix()` (PATH-016) and pinned
  the deliberate non-goal that `RemotePath` is **not** `os.PathLike`
  (PATH-017). The accompanying parity audit catalogued the `pathlib.PurePath`
  members still absent from `RemotePath`:
  - **Cheap, safe read accessors** complementing the existing `name` / `suffix`:
    `stem` (name without final suffix) and `suffixes` (list of all suffixes).
  - **Copy-with mutators:** `with_name`, `with_suffix`, `with_stem`. Each must
    re-run normalisation/validation and reject empty results per PATH-008.
  - **Other:** `joinpath` (n-ary `/`), `parents` (ancestor sequence),
    `match` (glob), `relative_to` / `is_relative_to`, `is_absolute`.
  Out of scope (meaningless for a rootless remote key): `drive`, `root`,
  `anchor`, `as_uri`. No demand for any of these yet — `as_posix()` covered the
  one concrete need. Reactivate per-member if a user hits a specific gap; each
  would need a `PATH-NNN` clause + spec-tagged test.
  Surfaced during the ID-196 parity audit.

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
