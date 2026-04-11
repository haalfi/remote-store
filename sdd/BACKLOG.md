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

- [ ] **BUG-163 — `_ensure_known_hosts_file` 0o600 not enforced on Windows**
  `SFTPBackend._ensure_known_hosts_file()` creates the file with
  `os.open(path, O_CREAT | O_WRONLY, 0o600)` but NTFS ignores POSIX mode
  bits -- the file is created with `0o666`. The test
  `test_ensure_known_hosts_file_creates_with_mode_600` correctly catches
  this. Fix either the code (Windows ACL or accept NTFS limitation) or
  the test (skip on Windows where POSIX permissions are meaningless).

---

## Backlog (Prioritized)

- [ ] **BK-139b — Implement remaining bug prevention measures from research**
  Follow-up on [research-bug-prevention-beyond-testing.md](research/research-bug-prevention-beyond-testing.md).
  Items 1–3 shipped (see BK-139a in BACKLOG-DONE.md). Items 4, 5, 7 shipped.
  Remaining:
  6. `scripts/check_error_handling.py` AST script (~80 lines) — deferred until
     items 4–5 prove insufficient; conformance error fidelity tests may suffice.

---

## Ideas

### Streaming & Memory Optimization

- [ ] **ID-137 — Reduce per-backend streaming overhead**
  E2e streaming integrity test (8+ runs, 7--14 MiB, random order) identified
  four optimization opportunities:
  1. **PyArrow S3 upload buffer ~4 MiB constant** (HIGH): `open_output_stream()`
     allocates ~4 MiB regardless of file size. Investigate buffer-size options
     on `pyarrow.fs.S3FileSystem` (`background_writes`, etc.).
  2. **Memory backend zero-copy read** (MEDIUM): `read()` does `bytes(node.data)`
     + `BytesIO()`, copying the full file. A `memoryview`-based approach could
     eliminate one copy (must consider thread-safety under `_lock`).
  3. **SFTP 32 KiB chunk size** (LOW): `_CHUNK_SIZE = 32768` produces 250--400
     chunks for 10 MiB. Increasing to 256 KiB could reduce syscall overhead
     without affecting correctness.
  4. **Non-lazy -> memory ~10% overhead** (LOW): `sftp -> memory` and
     `azure -> memory` consistently show total ≈ file_size × 1.1. Understand
     the source of the extra ~10%.
  5. **Decouple Azure `max_block_size` from `_COPY_BUFSIZE`** (MEDIUM):
     Currently both are 256 KiB. `_COPY_BUFSIZE` controls Python-level
     `shutil.copyfileobj` chunking (memory), while `max_block_size` controls
     HTTP PUT request size (network I/O). A larger `max_block_size` (e.g.
     4 MiB) would reduce HTTP overhead (~16x fewer requests) but empirical
     testing showed 8 MiB pipe cost with 4 MiB blocks (SDK holds 2 blocks).
     Needs careful tuning with `min_large_block_upload_threshold`.

### Testing & Verification

- [ ] **ID-136 — Document SQL backend non-lazy write as by-design**
  `SQLBlobBackend.write()` materializes the full stream into memory because
  SQL BLOB columns require complete data for INSERT/UPDATE. This is inherent
  to SQL storage and cannot be streamed. Add a code comment and note in
  backend docs.

### Formal Verification

- [ ] **ID-134 — Verify `GetFolderInfo` aggregate fields (`file_count`, `total_size`) in Dafny postcondition**
  The `GetFolderInfo` counting loop in `MemoryBackend.dfy` computes `file_count`
  and `total_size` but the postcondition only asserts `r.Ok? && r.value.path == path`.
  Adding `ensures r.value.file_count == |set k | k in fs && fs[k].FileEntry? && IsChildOf(k, path)|`
  (and a sum-based postcondition for `total_size`) would make these fields verified
  by construction.  Requires loop invariants tracking partial counts/sums against
  a ghost set — non-trivial Dafny proof work.

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

