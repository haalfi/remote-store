# Development Backlog

Active work items and ideas. Completed items live in
[BACKLOG-DONE.md](BACKLOG-DONE.md).

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

## How this file works

**Status legend:** `[ ]` pending · `[~]` in progress

**Ordering:** newest first within each section.

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

*(none)*

---

## Backlog (Prioritized)

- [~] **BK-142 — Harden CodeQL CI: scope, query suite, gating, dep review, annotations**
  Current `codeql.yml` runs with defaults and is not gated — findings post to the
  Security tab but don't block merges. Five concrete improvements:
  1. **Path filter** — skip CodeQL on doc-only PRs via GitHub's native `on.paths`
     trigger filter (distinct from `ci.yml`'s `changes` job approach).
  2. **Config file** (`.github/codeql/codeql-config.yml`) — scope analysis to
     `src/remote_store/`, upgrade query suite from default to `security-and-quality`.
  3. **Wire config into `codeql.yml`** — `config-file:` field on the init step.
  4. **Dependency review** — add `dependency-review-action` job (CVEs in deps on PRs).
  5. **Annotate intentional risks** — `ext/dagster.py` `pickle.loads` and
     `ext/yaml.py` ruamel path; add structured comments so real findings stay visible.
  Note: making CodeQL a required status check must be done in GitHub branch
  protection settings (not in YAML) — document this as a manual step.

- [~] **BK-139c — Dafny-Python bridge: unified oracle for backend conformance**
  POC completed (see `sdd/formal/POC/`). Proved two viable approaches to bridging
  formal Dafny specification and runtime Python testing.
  - **Direction 1: Handwritten oracle** (`sdd/formal/POC/oracle.py`)
    - 680 lines pure Python, no external deps
    - 32 passing conformance tests (25 self-validation + 7 backend comparison)
    - ✓ Practical for daily CI, proven correct
    - ✗ Manual transcription; must stay in sync with spec
  - **Direction 2: Compiled oracle** (`sdd/formal/MemoryBackend-py/`)
    - Direct `dafny translate py` output (41 verified proofs)
    - ✓ Mathematically verified, auto-generated from spec
    - ✗ Requires `_dafny` runtime; Dafny types need marshaling; class-ordering bug
  - **POC demonstrates feasibility**:
    - Unified strategy possible: run both oracles in differential conformance tests
    - Differential test fails if handwritten ≠ compiled → investigate why
    - Catches implementation-vs-spec drift at source
  - **Remaining (follow-up decision)**:
    - [ ] Review POC findings (`sdd/formal/POC/README.md`)
    - [ ] Assess effort vs. benefit for each direction
    - [ ] Decide: pursue unified bridge? which approach? when?
    - If yes: implement chosen approach + integrate into CI pipeline
  - **Related**: BK-139a, BK-139b, BK-140, BE-021

- [~] **BK-139b — Implement remaining bug prevention measures from research**
  Follow-up on [research-bug-prevention-beyond-testing.md](research/research-bug-prevention-beyond-testing.md).
  Items 1–3 shipped (see BK-139a in BACKLOG-DONE.md). Items 4, 5, 7 shipped.
  Remaining:
  6. `scripts/check_error_handling.py` AST script (~80 lines) — deferred until
     items 4–5 prove insufficient; conformance error fidelity tests may suffice.

---

## Ideas

### Testing & Verification

### Formal Verification

- [ ] **ID-133 — Regenerate `MemoryBackend-py/module_.py` after `CapAtomicMove` addition**
  `sdd/formal/MemoryBackend.dfy` was updated in ID-128 to include `CapAtomicMove`,
  but the Dafny-compiled Python output (`sdd/formal/MemoryBackend-py/module_.py`)
  was not regenerated (no Dafny toolchain available in CI). Run:
  `dafny translate py sdd/formal/MemoryBackend.dfy --include-runtime`
  with Dafny 4.11.0+ and commit the result. The file must not be hand-edited.
  Related: ID-128, BK-139c.

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
  - Capabilities: all 10 likely supportable (real folders, server-side
    copy/move, Range-header seeks, temp-file atomic writes).
  - Auth: OAuth 2.0 — client-credentials (daemon) and/or device-code
    (interactive).
  - SDK options: direct REST via `httpx` (minimal deps), `msgraph-sdk`
    (official), or `Office365-REST-Python-Client` (mature).
  - Reference: Azure backend (`_azure.py`) — closest architectural parallel.
  - Next: RFC scoping auth model, path mapping, and SDK choice.

- [ ] **ID-121 — CompositeStore (research complete)**
  `CompositeStore(Store)` — core Store subclass (not extension) that composes
  multiple stores into one. Deterministic fallthrough resolution for reads, union
  LIST (deduplicated), writes to primary tier only.
  - [Research](research/research-sqlalchemy-backend.md#52-compositestore-id-120)
    (anchor uses historical ID-120 from research doc; now ID-121 after swap)
  - Depends on: unified `resolve()` → `ResolutionPlan` (ID-120); at least two
    working backends to be useful; pairs well with ID-119
  - Next: design as separate spec — backend-agnostic, useful independently

### Integrations

- [~] **ID-018 — conda-forge publishing**
  Recipe, CI validation, release checklist steps all done.
  - Done: [recipe](../packaging/conda-forge/recipe.yaml),
    [conda-recipe workflow](../.github/workflows/conda-recipe.yml),
    staged-recipes PR `conda-forge/staged-recipes#32401` (CI green).
  - Blocked: waiting for conda-forge reviewer approval. When merged: add
    `conda install -c conda-forge remote-store` to README.

- [~] **ID-013b — Async Store API Phase 3: async extensions**
  Remainder of ID-013. Phase 1 (core primitives) and Phase 2 (native async
  backends) shipped — see [BACKLOG-DONE.md](BACKLOG-DONE.md).
  Spec 029 amended with round 2 §2.4 items + Phase 2 AsyncAzureBackend spec.
  Async guide updated with native backend docs.
  - Remaining:
    - Implementation Phase 3: async extensions. Note: Dagster 1.12.21 has no
      `AsyncIOManager`; `UPathIOManager.load_partitions_async` is internal only.
      Blocked until Dagster exposes a public async IO manager interface.

---

## Icebox

Deferred indefinitely — revisit only if demand or circumstances change.

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

