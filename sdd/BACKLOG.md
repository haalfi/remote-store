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

## S3 Client-Implementation Strategy

Three s3fs-inherited pain points (dep-conflict cascade, 5 GB multipart cliff,
listing-cache staleness) would not exist on a boto3-direct backend. Two
investigations and one PoC determine whether the answer is "live with it
and document," "tweak s3fs defaults," or "ship a third S3 lane."
ID-200 (error-mapping audit) is **done** — see
[BACKLOG-DONE.md](BACKLOG-DONE.md) and
[research/research-s3-error-mapping-fidelity.md](research/research-s3-error-mapping-fidelity.md);
it spawned BUG-214 and BK-248 (both done) and feeds ID-202's error mapping. All
three pains were surfaced as code-side flags in
[research](research/research-backend-setup-guides.md) § 6 and carved
out of [ID-199](#docs--discoverability) (backend setup-guides initiative).

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

  **Sequence — start after all of:**
  - ID-174 (docs reorg): final source URLs must be stable before the link list is written.
  - ID-172 + ID-173 (aio verifiers): `aio.md` and `index.md` must accurately
    reflect the async API before they are linked as authoritative reference.
  - ID-192 (aio.md rework): landed — `aio.md` structural rework is in place; required for ID-172 to close (see BACKLOG-DONE.md).
  - ID-193 (async conformance): landed — async extended conformance pattern is
    in place (see BACKLOG-DONE.md).

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
  spec: GR-001..GR-057, ERR-013 · effort: L · audience: user.api
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
  - **Bundled sub-task — `ResourceLocked` (ERR-013, ADR-0024):** Graph
    triggers the only need for this error class today. Three coupled
    pieces ship together with the backend, not separately: the
    `ResourceLocked` Python exception class in
    `src/remote_store/_errors.py` (named `ResourceLocked` per the flat
    error hierarchy and spec 005's example), the
    `Error.ResourceLocked(path: Path)` variant in
    `sdd/formal/BackendContract.dfy` (re-translate
    `MemoryBackend-py/module_.py`), and its dispatch in
    `tests/backends/dafny/_helpers.py::_raise_if_err`. Formerly tracked
    as the standalone ID-189; folded here because the Dafny variant
    cannot land in isolation — without the runtime class to raise,
    adding the variant alone would create a verified contract for
    behaviour the codebase cannot exhibit.
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

- [~] **BK-252 — Bulk spec-mark backfill (~127 type-(b) labels)**
  spec: — · effort: L · audience: library.maintainer
  The mechanical slice of audit-015: ~127 invariants whose behavior is already tested
  (largely via cross-backend conformance under sibling marks) but lack the
  spec-file-specific `@pytest.mark.spec(...)`. Backfill per spec-cluster — Azure (012)
  is the cleanest start (every `AZ-*` rides a `BE-*`/`GLOB-*` test). Both gates have landed
  (see BACKLOG-DONE.md): **BK-251** (the `check_spec_marks.py` gate, whose `_BASELINE` is the
  worklist and shrinks as marks land) and the **BK-250** `STORE-015` renumber (`glob()` is now
  `STORE-018`, an ordinary drift row this item backfills). Verify each mark against the named
  test before stamping; do not rubber-stamp. See the addendum's type-(b) caveats
  (`SQL-QUERY-061/063` ride shared-base coverage; `GLOB-019` depends on fixture liveness).
  Landing in grouped clusters on one branch (159 baselined → backfill per cluster). **All 5 clusters
  backfilled (groups 1-2 merged in #724; groups 3-4 in #726; group 5 in progress):** 102 marks landed
  (gate 159 → 57, 784 mark-cited IDs) across backend-restatement (AZ/S3/S3PA), core-API/paths
  (STORE/NPR/BE/CAP/MEM), text/stream/iter/pyarrow (SIO/RTXT/WTXT/ITER/SEEK/PA), extensions
  (BATCH/OBS/SAW/DAG/WR/GLOB), and HTTP/Async/SQL (HTTP-\*, ASYNC-\*, SQL-\*). The mechanical type-(b)
  backfill is **complete**; the remaining **57 baselined rows need a disposition decision** (NOT
  type-(b) backfills): 53 held-for-disposition across clusters + 4 `AW-002/005/006/007` (atomic-write
  IDs never clustered). They are design/meta/perf statements, protocol shapes, moved-`EW` stubs, or
  have no test asserting the specific clause — type-(d) allowlist / de-registration / new-test
  candidates. The held set:
  `AZ-007`/`S3-001`/`S3PA-001`/`MEM-001`/`MEM-005` (constructor/scope/registration, no canonical
  assertion); `AZ-010`/`S3PA-007`/`NPR-007` (sub-clause unasserted: non-HNS no-folder-marker /
  s3→pyarrow credential translation / S3 prefix-stripping); `STORE-007`/`STORE-010`/`CAP-007`/`BE-011`/`ITER-002`
  (thread-safety/immutability, equality, quality-flag principle, and the `write_atomic` /
  `iter_children` capability-gate raise-when-absent branches — no test exercises the clause);
  `NPR-009`/`017`/`018`/`019`, `RTXT-002`/`003`, `WTXT-002`/`003`, `ITER-003`
  (future-backends / no-Backend-ABC-change / STORE-008-surface / backward-compat — design/meta);
  `SEEK-007`/`PA-023`/`PA-026`/`CFG-007`/`CFG-014`/`GLOB-015`/`SAW-010`/`PING-009`/`RES-001`
  (azure-read-unchanged / optional-extra / no-backend-coupling / S3-buffer-mechanism /
  check_health-error-classification / resolution-opacity-problem-statement — design or no asserting
  test); `WR-014`/`015`/`016`/`017` (**moved** to spec 046 `EW-001..004` per ADR-0008 — the spec-045
  entries are cross-reference stubs; real coverage is under `EW-*` marks, so these need
  de-registration or allowlisting, not a `WR-*` mark);
  `MEM-026`/`030`/`031`/`032`/`040`/`041`/`042`/`DS-001`/`DS-003`/`DS-004`
  (atomicity-scope, conformance/fixture recommendations, perf tables, data-structure rationale);
  `HTTP-TR-001` (HttpTransport protocol shape — no structural assertion); `ASYNC-043`/`077`
  (delegation / shared-helpers code-org — design), `ASYNC-074` (non-HNS AsyncIterator materialization —
  untested); `SQL-BLOB-070`/`071`, `SQL-QUERY-090`/`091` (Performance-section blob-size / pooling /
  query-execution / serialization-overhead — perf/design); `AW-002`/`005`/`006`/`007` (atomic-write
  capability-gate / intermediate-dirs / mkstemp+replace / no-fallback — never clustered; verify before
  any backfill). **Next step is a maintainer call on this set, not more backfilling.**

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

- [ ] **BK-245 — Cross-source capability-parity check (Python ↔ Dafny)**
  spec: — · effort: S · audience: infra.test, contributor.tooling
  Discovered in PR #689 review of ID-188. The new `CapLazyRead`
  enum variant in `sdd/formal/BackendContract.dfy` is asserted to
  exist for Python-side parity with `Capability.LAZY_READ`, but no
  mechanical check enforces that claim — `check_formal_trace.py`
  matches @spec tags, not capability-enum membership, so a future
  drift between `Capability.<NAME>` in `_capabilities.py` and the
  `Capability` datatype + `CapabilityName` cases in
  `BackendContract.dfy` would silently slip through. Extend
  `scripts/check_formal_trace.py` (or add a sibling
  `scripts/check_capability_parity.py`) to assert
  `{Capability.<name>.value for name in Capability} ==
  {CapabilityName(c) for c in <dafny Capability enum>}`. The parity
  is per-name; ordering or grouping in the Dafny enum is out of
  scope.

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
