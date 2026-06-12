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

## Azure

- [ ] **ID-198 — Medallion Dagster + Azure HNS live showcase validation run**
  spec: — · effort: S · audience: library.maintainer, user.api
  The `examples/medallion_dagster/` showcase demonstrates a realistic user journey
  combining Dagster orchestration with an Azure HNS backend, but has never executed
  against a live ADLS Gen2 account. Run the full example end-to-end against real cloud
  infrastructure to surface testing gaps, implementation TODOs, or edge cases that
  conformance and unit tests miss. Async patterns are settled (ID-193 landed,
  see BACKLOG-DONE.md). Findings inform the next release scope; no code changes
  are produced by this item itself.

---

## Graph

ID-127 (Microsoft Graph / OneDrive / SharePoint) follow-ups, in execution order;
full findings in [audit-016](audits/audit-016-graph-backend-review.md).
**Order:** correctness + tests (BK-266/267) →
blocked or hygiene tail (BK-259/261/268/283). Each item's own rationale lives in
its body. (Security item BK-263 — the upload-session credential leak — the
load-bearing CI-coverage item BK-262 — replay-able cassettes — the spec/RFC
sync BK-264, and the guide/docstring sweep BK-265 shipped first; see
BACKLOG-DONE.md.)

- [ ] **BK-283 — Drive the Graph example snippet from replayed cassettes in CI**
  spec: GR-015, GR-019 · effort: S · audience: infra.test
  The replay-able cassettes BK-262 committed could also drive the env-gated
  `examples/backends/graph_backend.py` snippet, which today only runs under live
  credentials and is excluded from the `run_examples.py` CI sweep entirely. With
  the pre-signed-URL replay now solved (BK-262), a replayed variant could
  exercise the example in CI without creds — same `graph_replay` vcr config,
  second beneficiary. Sketch: record a cassette for the example's request
  sequence (or reuse the conformance ones if the call shapes line up) and wire a
  replayed path into `run_examples.py` so the snippet is covered without the
  live opt-in. Carried forward from BK-262 (the consolidated former BK-260);
  was gated on the cassette-replay core landing first, which it now has.

- [ ] **BK-266 — Graph backend correctness edges**
  spec: GR-031, GR-044 · effort: S · audience: user.api, library.maintainer
  Three small, independent fixes (split if preferred):
  - Scope the `resourceNotFound`→`BackendUnavailable` mapping to drive scope so it
    cannot escape `exists()` / `is_file()` / `is_folder()` when seen at item scope
    (`http.py:124`, GR-031).
  - Normalise paths before the self-op `src == dst` short-circuit, or document that
    GR-044 assumes Store-normalised input — direct-to-backend `copy("/a.txt",
    "a.txt")` skips the no-op today (`backend.py:_short_circuit_self_op`).
  - Decide whether the bundled `GraphAuth.get_token` should raise a
    `RemoteStoreError` subtype instead of stdlib `PermissionError` (`auth.py:184`),
    which currently propagates through `read` / `write` uncatchable by
    `except RemoteStoreError`.
  Audit-016 L1 / L3 / M7.

- [ ] **BK-267 — Graph test hardening**
  spec: GR-012, GR-040 · effort: S · audience: infra.test
  Close respx-tier gaps in the sole-coverage suite:
  - Pin `read()` first-iteration failure timing — assert no bytes are yielded
    before the `NotFound` / `InvalidPath` raise (the async-generator body defers;
    `test_read.py:207` does not catch this).
  - Add a direct `write_atomic` failure-path test (today only delegation is
    asserted).
  - Add at least one per-method `403`→`PermissionDenied` test, or document the
    centralised-mapping rationale.
  Audit-016 L7.

- [ ] **BK-259 — Graph `_range_fallback_paths` flag: scope to operation, not backend lifetime**
  spec: GR-015 · effort: S · audience: user.api, library.maintainer
  `GraphBackend._range_fallback_paths` is a per-instance `set[str]`: a range
  read that falls back (a SharePoint drive ignored/rejected `Range`) records the
  path, and `get_file_info` then flags `extra["graph.read.range_fallback"] = True`
  on any `FileInfo` it returns for that path. The set only grows; nothing clears
  it. Two problems, surfaced in PR #760 review:
  - **Unbounded memory.** A long-lived backend that range-reads many distinct
    range-incapable paths holds one key per path for the instance lifetime.
    Bounded in practice by *distinct range-failing paths* (fallback is the rare
    misconfigured-SharePoint case), not by total reads — but unbounded in
    principle.
  - **Semantics vs spec.** GR-015 scopes the flag to "any `FileInfo` returned
    for the same item **within the operation context**." A per-backend set marks
    the path *permanently*: a later non-range `get_file_info`, or a read that did
    not fall back, still reports the stale flag. If range behaviour is
    per-request / tenant-config rather than a permanent drive property, this
    misleads.

  **Why it exists this way:** `read` / `_read_bytes` return bytes, and the
  backend has no `StoreEvent` / operation handle (the OBS-layering constraint
  GR-015 itself calls out — the proxy builds `StoreEvent` before the inner call,
  so the backend cannot inject into it). A per-backend set is the only channel
  that survives from a range read to a later `get_file_info`. The WARNING log
  (`graph.read.range_fallback` marker) is the always-reachable signal;
  `FileInfo.extra` is the spec-mandated but architecturally-awkward second one.

  **Solution space (decide when picked up):**
  1. **Self-healing flag (lean).** Clear the path from the set when a later
     ranged read on it succeeds (`206`), so the flag tracks the most-recent
     outcome instead of "ever failed." Small change; risk: flapping if a drive
     answers ranges inconsistently. Needs `stream_range` to signal range-success
     back (a second callback / return flag, mirroring `on_fallback`).
  2. **Bound the set.** A `TTLCache` / LRU caps memory and ages out stale marks,
     accepting staleness within the window. Fixes memory; only partly fixes the
     stale-semantics point.
  3. **Soften the spec.** If the marker is genuinely a backend-lifetime *hint*
     and not operation-scoped, amend GR-015's "within the operation context"
     wording to match reality and document the limitation. Pairs with (1).
  4. **Native-async observability.** Deliver the signal through the proper event
     channel once an async observe/otel surface exists — GR-015 already defers
     native-async observability as "a separate, unscheduled item"; the flag would
     then ride `StoreEvent.metadata` with true operation scope.

  Leaning **(1) + (3)**: self-heal on a successful ranged read and align the
  spec wording, with **(4)** as the eventual proper home. Touches
  `src/remote_store/aio/backends/_graph/{backend,transfer}.py`,
  `tests/backends/graph/aio/test_transfer.py`, and
  `sdd/specs/044-graph-backend.md` (GR-015). Discovered in PR #760 (ID-127
  GR-TRANSFER) review.

- [ ] **BK-261 — Graph small-write `overwrite=True`: replace-returns-409-for-files quirk**
  spec: GR-018 · effort: S · audience: user.api, library.maintainer
  On the small-file `PUT /content` path, `@microsoft.graph.conflictBehavior=replace`
  is expected to overwrite an existing file and return `200`. Graph issue reports
  describe some backing stores (SharePoint-backed drives) instead returning
  `409 nameAlreadyExists` for a *file* even with `replace`. The 409 discrimination
  in GR-018 would map that to `AlreadyExists` — a spurious failure for an intended
  overwrite. **Not reproduced**: the consumer OneDrive drive used for Stage-3 live
  verification honours `replace`, and our live path is consumer-only / device-code,
  so the SharePoint-backed edge cannot be live-verified today. No guard is taken in
  v1 because a speculative one (treating a `file`-faceted 409 on the `replace` path
  as success-equivalent) risks masking a genuine conflict and would guess at the
  body shape blind.
  **When picked up:** reproduce against a SharePoint-backed drive (needs app-only /
  SharePoint live testing, currently blocked — see the live-testing note), confirm
  the exact 409 body, then decide between a targeted guard on the `replace` path or
  documenting it as a hard backend limitation. Touches
  `src/remote_store/aio/backends/_graph/backend.py` (`_write_small`) and
  `sdd/specs/044-graph-backend.md` (GR-018). Discovered in ID-127 GR-WRITE review.

- [ ] **BK-268 — File the deferred Graph async-ext follow-ups (backlog hygiene)**
  spec: GR-003 · effort: S · audience: library.maintainer
  Two promised follow-ups have no tracked owner: GR-003 says async callers compose
  pattern matching themselves "until an async equivalent of `ext.glob` lands as a
  separate backlog item" (no such item exists), and ADR-0025 § Risks says the cache
  extension "should learn to warn when wrapped over a bridged backend (tracked
  separately)" (not filed). File or explicitly decline each so the deferred
  async-ext surface (glob / observe / otel / cache / integrity) has owners.
  Audit-016 L10.

---

## Lint / CI Completeness

- [ ] **ID-179 — Trace schema validator: wire `audience` field check into `hatch run lint`**
  spec: — · effort: S · audience: library.maintainer
  `sdd/traces/_schema.yml` declares `audience` as `required`, but BK-193
  deliberately left that field as an authoring convention — enforced "on the
  next aggregator run," not at commit time — rather than wiring a gate (no
  aggregator exists yet, so nothing validates it today). Add
  `scripts/check_traces.py` that jsonschema-validates every
  `sdd/traces/[!_]*.yml` against the schema. Wire into the existing
  `hatch run lint` script list and into the lint CI job. Per
  `feedback_check_scripts_dual_wire`. Promotes BK-193's convention to
  mechanical enforcement. No priority while trace authoring is still
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
  large context file. Worth a separate ID if demand appears. **Tooling
  decision:** if pursued, generate it from the **built** site with a
  MkDocs-native plugin (`mkdocs-llmstxt`, by the `mkdocstrings` author —
  `full_output:` emits `llms-full.txt`), not an external source bundler. A
  raw-source bundler would miss the `gen-files`-generated API pages and the
  BK-171 URL rewrites, and ignore `literate-nav` order. See
  [`research/research-lx-llms-context-tooling.md`](research/research-lx-llms-context-tooling.md).
  The orthogonal "bundle repo source for a coding agent" use-case is ID-216,
  not this file.

  **Content checklist when starting:** streaming reads (`with store.read(path) as f:`),
  `MemoryBackend` for unit testing, `store.child()` scoping, and
  `ext.integrity`/`ext.partition`/`ext.transfer` use-case examples are the
  known gaps in how external tools currently discover remote-store.

  **Sequence — prerequisites met (all landed, see BACKLOG-DONE.md):**
  ID-174 (docs reorg, stable source URLs), ID-172 + ID-173 (aio verifiers:
  `aio.md` and `index.md` now reflect the async API), ID-192 (aio.md rework),
  and ID-193 (async conformance) have all shipped. Nothing gates this item;
  the link list can be written against the current stable docs.

  **Exit criteria:** `docs-src/llms.txt` committed; `GET
  https://docs.remotestore.dev/llms.txt` returns the file after next deploy.

- [ ] **ID-216 — Evaluate `lx` as an ad-hoc repo-context bundler for coding agents**
  spec: — · effort: S · audience: library.maintainer
  [`rasros/lx`](https://github.com/rasros/lx) (Go, MIT) bundles a directory
  tree into one LLM-ready blob (XML/Claude format, token estimation,
  `.gitignore`-aware, tree/skeleton views). This is a **developer-convenience**
  tool for handing a coding agent whole-codebase or whole-subtree **source**
  context on demand — distinct from the docs-site `llms.txt`/`llms-full.txt`
  lineage (ID-161), which targets *published docs prose*, not source. Nothing
  here is committed or deployed, so the pipeline and supply-chain-in-CI concerns
  that rule `lx` out for `llms-full.txt` do not apply.
  **Scope:** timeboxed local trial — does `lx` beat a plain `git archive` /
  bespoke script for our layout? Settle on an invocation (likely an `.lxignore`
  plus a documented one-liner), and decide whether it earns a mention in
  CONTRIBUTING / dev docs. Do **not** wire it into CI or the docs build.
  **Why ID, not BK:** unevaluated DX convenience, no committed outcome.
  Background and the full lx-vs-MkDocs-plugin analysis:
  [`research/research-lx-llms-context-tooling.md`](research/research-lx-llms-context-tooling.md).
  **Exit criteria:** trial run recorded; keep/drop decision noted on this item;
  if kept, a documented invocation lands in dev docs.

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
