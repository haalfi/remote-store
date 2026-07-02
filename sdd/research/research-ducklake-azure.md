# Research: DuckLake on Azure for remote-store users

**Date:** 2026-07-02
**Backlog items:** — (research only; backlog candidates proposed in § 4)
**Status:** Research complete — ready for design decisions

---

## 1. Problem Statement

remote-store users whose data lives on Azure (the `azure` /
`AsyncAzureBackend` backends: Blob Storage or ADLS Gen2 via the Azure SDK)
are starting to look at DuckLake, DuckDB's lakehouse format. The questions:

- Can they adopt DuckLake on Azure at all, and in which deployment shapes?
- To what extent do remote-store's features remain useful alongside it?
- Should remote-store document or support a DuckLake-on-Azure story, and
  could remote-store itself serve as DuckLake's storage layer?

Constraints:

- remote-store positions itself as the swappable I/O layer *underneath* table
  formats and query engines (`docs-src/guides/data-lake-patterns.md`): no
  table-format implementation, no query execution, no catalog integration.
  Any DuckLake story must respect that altitude.
- Research sources restricted to official documentation (duckdb.org,
  ducklake.select, learn.microsoft.com) plus primary source code of the
  DuckDB repositories. No blogs or third-party articles.

**Method and confidence labels.** Two tracks, run 2026-07-02: (1) official
docs via a fan-out search + adversarial-verification harness — claims
labelled **[verified]** survived a 3-vote verification against the cited
page; **[unverified]** means extracted from an official page but the
verification pass did not complete. (2) Source-level reading of the current
`main` branches of [duckdb/duckdb-azure](https://github.com/duckdb/duckdb-azure),
[duckdb/ducklake](https://github.com/duckdb/ducklake), and
[duckdb/duckdb-python](https://github.com/duckdb/duckdb-python), labelled
**[code]** and cited by file and line. **[code]** claims are primary-source
readings, not official-documentation statements: they are authoritative about
what the code does at the pinned date (2026-07-02, `main`), line numbers
drift with upstream changes, and behaviour may change without a docs update.
Where duckdb.org / ducklake.select pages were proxy-blocked, the
identical page sources were read from the `duckdb/duckdb-web` and
`duckdb/ducklake-web` repositories.

---

## 2. Survey: DuckLake-on-Azure landscape and integration options

### 2.1 Foundations: what DuckLake is and what it needs from Azure

**Architecture.** DuckLake = a SQL catalog database (all metadata, all file
paths) + Parquet data files at a `DATA_PATH`. "DuckLake manages files stored
in a separate storage location. The paths to the files are stored in the
catalog server."
([paths](https://ducklake.select/docs/stable/duckdb/usage/paths)) **[verified]**

**Paths are relative by default and the data tree is relocatable
[verified].** "By default, all paths written by DuckLake are relative paths",
layered file → table path → schema path → global data path (three-layer
relative paths since the DuckLake 0.2 standard), with a `path_is_relative`
flag stored per path in the spec tables. "The root data_path is specified
through the data_path parameter when creating a new DuckLake. When loading an
existing DuckLake, the data_path is loaded from the ducklake_metadata if not
provided." Data files are named `ducklake-⟨uuid⟩.parquet` relative to the
table path — now also docs-backed, matching the earlier code-level finding.
([paths](https://ducklake.select/docs/stable/duckdb/usage/paths),
[ducklake_data_file spec](https://ducklake.select/docs/stable/specification/tables/ducklake_data_file),
[DuckLake 0.2 announcement](https://ducklake.select/2025/07/04/ducklake-02/))
The 0.2 announcement also states the design intent of per-schema/table
subdirectories: "it is now possible to use prefix-based access control at the
object store level to grant users access to only specific schemas or tables"
— the same prefix-scoping model as remote-store's `child()`.

**Externally written Parquet can be registered [verified].** Since v0.2,
`ducklake_add_data_files` registers "existing Parquet files written through
other means or by other writers" into a DuckLake table via name mapping;
"All DuckLake operations are supported on added files, including schema
evolution and data change feeds."
([DuckLake 0.2 announcement](https://ducklake.select/2025/07/04/ducklake-02/))
This is the one sanctioned door for files produced outside DuckLake (e.g.
written with remote-store) to enter the lake — it does not change the rule
that DuckLake-managed files themselves must not be touched.
Catalog and data are independently placeable: `DATA_PATH` is an `ATTACH`
option separate from the catalog connection string, e.g.
`ATTACH 'ducklake:postgres:…' AS lake (DATA_PATH 'az://container/lake/')`.
([choosing_a_catalog_database](https://ducklake.select/docs/stable/duckdb/usage/choosing_a_catalog_database))
**[verified]**

**Catalog options and their Azure fit:**

| Catalog | Azure hosting | Fit |
|---|---|---|
| PostgreSQL | Azure Database for PostgreSQL | **Recommended.** "If you would like to operate a multi-user lakehouse with potentially remote clients, use PostgreSQL as the catalog database." **[verified]** |
| DuckDB file | any (file on disk) | Single client only: "if you are using DuckDB as your catalog database, you're limited to a single client." **[verified]** |
| SQLite file | any (file on disk) | Multi-process on one machine; no remote clients |
| MySQL | Azure Database for MySQL | **Not recommended** by DuckLake: "There are a number of known issues with MySQL as a catalog for DuckLake. … We therefore do not recommend to use MySQL as a catalog for DuckLake." **[verified]** |

**The load-bearing fact: Azure writes in DuckDB.** The Azure extension
supports reading and writing data directly via `COPY`. Official docs (current
and LTS): "You can write data directly to Azure Blob or ADLSv2 Storage using
the `COPY` statement."
Schemes: `az://` / `azure://` (Blob), `abfss://` (ADLS). Auth via DuckDB
secrets: `CONFIG` (connection string, default), `CREDENTIAL_CHAIN`, managed
identity, `SERVICE_PRINCIPAL`. Read tuning: `azure_read_transfer_concurrency`,
`azure_read_transfer_chunk_size`, `azure_read_buffer_size`.
([azure extension](https://duckdb.org/docs/stable/core_extensions/azure))

Implementation-history note **[code]** (from the duckdb-azure repository, not
the docs): write support is a recent addition to the extension —
blob writes merged 2025-11-26
([PR #131](https://github.com/duckdb/duckdb-azure/pull/131)), ADLS/DFS writes
merged 2025-12 ([PR #140](https://github.com/duckdb/duckdb-azure/pull/140)),
blob writes moved to the block API 2026-02-23
([PR #151](https://github.com/duckdb/duckdb-azure/pull/151)). Installations
pinned to older extension builds may therefore lack write support even though
current docs describe it.

How writes behave at source level **[code]** (duckdb-azure `main`,
2026-07-02):

- Blob path: sequential writes staged via `blob_client.StageBlock(...)`
  (`src/azure_blob_filesystem.cpp:415-444`), committed atomically at
  close/sync via `blob_client.CommitBlockList(...)`
  (`src/azure_blob_filesystem.cpp:81-101`) — a reader never sees a partial
  file.
- DFS path: sequential `file_client.Append(...)` plus `Flush`
  (`src/azure_dfs_filesystem.cpp:364-384`, sync at `:109-115`).
- Both throw `NotImplementedException` for append mode and read+write mode
  (`src/azure_blob_filesystem.cpp:117-122`,
  `src/azure_dfs_filesystem.cpp:131-136`); neither implements `MoveFile` or
  `Truncate` — those fall through to DuckDB's base class, which throws
  ("MoveFile is not implemented!", duckdb `src/common/file_system.cpp:579`;
  `Truncate` at `:492`).
- Blob filesystem's `CreateDirectory` is an explicit no-op
  (`src/include/azure_blob_filesystem.hpp:56-57`); DFS implements it for real
  (`src/azure_dfs_filesystem.cpp:159-167`).

Azure-side note: at code level, `az://` is served by the Blob API and
`abfss://` by the Data Lake (DFS) API **[code]**
(`src/azure_blob_filesystem.cpp:32-36`, `src/azure_dfs_filesystem.cpp:27-30`).
The initially plausible inference that the DFS endpoint presupposes an
HNS-enabled account is **refuted by Microsoft's docs [verified]**: "The Azure
Blob File System driver can be used with the Data Lake Storage endpoint of an
account even if that account does not have a hierarchical namespace enabled."
([Use the Azure Data Lake Storage URI](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-introduction-abfs-uri),
ms.date 2024-11-15)
Residual nuance **[unverified]**: that page addresses the Hadoop ABFS
driver's URI scheme; whether the specific DataLake SDK operations
duckdb-azure issues (directory create, `Append`/`Flush`) behave identically
on flat-namespace accounts is not established by it, so HNS-enabled accounts
remain the safe default recommendation for `abfss://` data paths.

Two further Microsoft facts frame the account-shape choice **[verified]**
([Azure Data Lake Storage introduction](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-introduction),
ms.date 2026-05-15): ADLS "isn't a dedicated service or account type" but a
capability set on Blob Storage unlocked "by enabling the hierarchical
namespace setting" (the DFS REST APIs surface at `dfs.core.windows.net`);
and HNS's headline benefit is that "renaming or deleting a directory become
single atomic metadata operations". Since DuckLake's data-path contract never
renames or moves files (§ table above), that benefit is irrelevant to
DuckLake — a flat Blob account addressed via `az://` is fully sufficient for
a DuckLake data path. This matches remote-store's own model: `AzureBackend`
requires an explicit `hns` flag and serves both account shapes through the
Blob API.

**What DuckLake actually does on the data path [code].** From
`duckdb/ducklake` source (`main`, 2026-07-02), the complete filesystem
contract:

| Operation | Where | Notes |
|---|---|---|
| Write-once Parquet files | `src/storage/ducklake_insert.cpp:479-584` | Unique names `ducklake-{uuidv7}` (`:571,576`); `use_tmp_file = false` (`:569`) — **no write-temp-then-rename, ever** |
| Random-access reads | Parquet reader | Footer + row-group range reads |
| Delete files | `src/storage/ducklake_transaction.cpp:596-617`, `src/functions/ducklake_cleanup_files.cpp:136-152` | Rollback cleanup, `cleanup_old_files`, `delete_orphaned_files`; `TryRemoveFile` semantics |
| Recursive glob `**` + `last_modified` | `src/storage/ducklake_metadata_manager.cpp:4830-4844` | Only for `ducklake_delete_orphaned_files`; normal operation never lists the data path — paths come from the catalog |
| Create directory | `src/common/ducklake_util.cpp:315-322` | Local paths only (`IsRemoteFile` guard); skipped for remote paths, failures swallowed |
| Rename / move / append / truncate / lock | — | **Never used** (no `MoveFile` call in ducklake `src/`; the only renames are catalog-level metadata operations). Docs: "DuckLake as a concept will *never* change existing files, neither by changing existing content nor by appending to existing files." ([choosing_storage](https://ducklake.select/docs/stable/duckdb/usage/choosing_storage)) |

This write-once, catalog-committed design is why the azure extension's
restrictions (no move, no append, no read+write) are harmless: DuckLake
needs none of them. Supported data-path filesystems per DuckLake docs: "any
file system backend that DuckDB supports", explicitly listing Azure Blob
Store and "Python fsspec file systems"
([choosing_storage](https://ducklake.select/docs/stable/duckdb/usage/choosing_storage);
confirmed against the published page in review, read via the ducklake-web
source in this run).

**Storage-behaviour features relevant to any integration:**

- **ACID via the catalog.** Data files are written first, then become visible
  when the catalog transaction commits; concurrency control lives entirely in
  the catalog database. **[code]**
- **Data inlining.** Enabled by default with a row limit of 10: small
  inserts/deletes go into catalog tables instead of Parquet files.
  **[verified]** Inlined data is flushed to Parquet later
  (`ducklake_flush_inlined_data` / `CHECKPOINT`) **[unverified]** — so "small
  writes never touch Blob storage" is *not* a safe claim (a verifier refuted
  that phrasing); small writes touch Blob storage *eventually*.
- **Time travel / monotonic growth.** "DuckLake in normal operation never
  removes any data, even when tables are dropped or data is deleted."
  **[verified]** Physical removal is a two-step maintenance flow: data "can
  only be physically removed … by expiring snapshots"
  (`ducklake_expire_snapshots`) **[verified]**, and "expiring snapshots does
  not immediately delete files that are no longer referenced" — a separate
  `ducklake_cleanup_old_files` call deletes them. **[verified]** Without
  maintenance, the Azure container grows monotonically.

### 2.2 Option A: DuckLake native, remote-store side-by-side

**Pattern:** DuckLake owns its `DATA_PATH` through DuckDB's C++ `azure`
extension; remote-store operates on the same container (or account) for
everything around it. No new remote-store code.

**How it works:** One container, prefix-partitioned:

```text
Azure Blob / ADLS Gen2 container
├── lake/          ← DuckLake DATA_PATH (DuckDB azure extension writes here;
│                     remote-store: read-only inspection at most)
├── raw/           ← remote-store Store (ingest, ext.transfer, ext.observe)
└── exports/       ← remote-store Store (app-owned outputs)
```

Catalog on Azure Database for PostgreSQL (multi-user) or a local DuckDB file
(single client). DuckDB secret via `CREDENTIAL_CHAIN`, which aligns with
remote-store's `DefaultAzureCredential` default.

remote-store features that genuinely complement DuckLake in this shape:

| remote-store feature | Role alongside DuckLake |
|---|---|
| `Registry` / config / `Secret` | Same container config for app files; env-var resolution and credential masking for the storage side of the stack (the DuckDB secret is configured separately in SQL) |
| `Store.child()` scoping | Keep app-owned prefixes (`raw/`, `exports/`, `uploads/`) cleanly separated from the DuckLake `DATA_PATH` prefix in one container |
| `ext.transfer`, `ext.batch` | Land source files into `raw/` for DuckLake to `COPY` from; ship exports out |
| `ext.observe` / `ext.otel` | Tracing/audit for all app-side storage I/O (DuckLake's own I/O bypasses remote-store and is not observable here) |
| `ext.cache` | Read-through caching for app-side reads, including read-only inspection of DuckLake-written Parquet |
| `ext.integrity`, `ext.write` | Checksums for files the app owns; Azure backend's native MD5/etag surfaces in `WriteResult` |
| `ext.arrow` (`pyarrow_fs`) + `ext.parquet` | Read-only analytics on DuckLake's Parquet files outside DuckDB (existing documented pattern in `docs-src/guides/data-lake-patterns.md`); write-side dataset management remains for non-DuckLake datasets |
| `glob()` (native on `AzureBackend` and `AsyncAzureBackend`) | Read-only enumeration of `**/*.parquet` under the data path, e.g. for monitoring size/growth; `ext.glob` remains the fallback for non-GLOB backends (sync-only) |
| `AsyncAzureBackend` | Same capability set as sync (zero delta), so async services can do all of the above |
| `ext.partition` | Mostly superseded inside the data path — "the files are by default written to directories in the Hive partitioning style. Writing data in this manner is not required as the partition values are tracked in the catalog server itself" ([paths](https://ducklake.select/docs/stable/duckdb/usage/paths)) **[verified]**; parsing paths for observability is fine, constructing them is not |
| `ext.parquet` + `ducklake_add_data_files` | Sanctioned ingest bridge: Parquet written via remote-store (any backend) can be registered into a DuckLake table with name mapping (v0.2+); all DuckLake operations then apply to the added files **[verified]** |

**Trade-offs:**

- Pro: works today; best I/O performance (C++ extension, parallel range
  reads, staged-block uploads); zero remote-store code to build or maintain.
- Pro: clean ownership boundary — DuckLake exclusively owns `DATA_PATH`;
  remote-store must never write, move, or delete files there (even
  "orphan-looking" ones: time travel keeps old files referenced, and deletion
  is DuckLake maintenance's job, § 2.1).
- Con: DuckLake's I/O bypasses remote-store entirely — no observe hooks, no
  cache, no typed errors for that traffic.
- Con: needs a current DuckDB/extension build. Write support is documented
  in current and LTS docs, but per the extension's code history it merged
  2025-11 to 2026-02 (§ 2.1), so installations pinned to older builds have a
  read-only Azure filesystem and DuckLake cannot write through them.

### 2.3 Option B: remote-store as the data path via an fsspec adapter

**Pattern:** A thin fsspec `AbstractFileSystem` over a remote-store `Store`,
registered with `duckdb.register_filesystem()`; DuckLake's `DATA_PATH` uses
the adapter's protocol scheme.

**How it works:** DuckDB Python officially registers fsspec filesystems:
`duckdb.register_filesystem(fsspec.AbstractFileSystem)` **[verified]**, with
protocol-based URL routing (duckdb-python `src/pyconnection.cpp:154,340-369`
**[code]**); the wrapper implements the full write surface (`open("wb")`,
`write`, `flush`, `close`, `rm`, `glob`, `ls`, `isfile`, `size`, `modified`,
`mv`, `mkdir` — duckdb-python `src/pyfilesystem.cpp:39-105,146-249`
**[code]**), and the registered-fsspec path demonstrably supports SQL-driven
`COPY TO` writes in current stable DuckDB **[verified empirically against
duckdb 1.5.4: COPY to a registered fsspec memory filesystem succeeded and
read back correctly]**. DuckLake's docs explicitly list fsspec filesystems as
supported storage (§ 2.1).

Mapping DuckLake's data-path contract (§ 2.1) onto remote-store capabilities:

| DuckLake need | remote-store surface | Covered |
|---|---|---|
| Write-once file handle | `write()` (bytes/stream), `open_atomic()`; adapter buffers and commits on close (fsspec `AbstractBufferedFile` pattern) | Yes |
| Random-access read | `read()` with `LAZY_READ` range reads, `read_seekable()` | Yes |
| size / mtime | `METADATA`: `head()`, `FileInfo.modified_at` | Yes |
| Delete (best-effort) | `delete(missing_ok=True)` | Yes |
| Recursive glob | `GLOB` (native on Azure) or `LIST` | Yes |
| exists / isfile / isdir | ungated `exists()` / `is_file()` / `is_folder()` | Yes |
| mkdir | no-op for remote paths (DuckLake skips it; duckdb-azure blob no-ops it too) | Yes |
| move / append / read+write / lock | not required by DuckLake; duckdb-azure itself doesn't implement them | — |

**Trade-offs:**

- Pro: no hard gaps — full operation coverage; remote-store's typed errors,
  observe hooks, and backend portability apply to DuckLake's own I/O.
- Pro: unlocks DuckLake on *any* remote-store backend (SFTP, sql-blob,
  memory), including in-memory DuckLake integration tests.
- Con: the adapter does not exist yet — remote-store ships a PyArrow
  filesystem adapter (`ext.arrow`) but no fsspec adapter. This is the one
  missing deliverable.
- Con: whole-object commit at handle close rather than streaming staged
  blocks like duckdb-azure's `StageBlock` path — a memory/temp-spool
  consideration for large Parquet files, not a correctness issue given
  write-once semantics.
- Con: a Python fsspec filesystem runs under the GIL and will not match the
  C++ extension's parallel range reads (DuckDB's own docs carry this
  performance caveat).
- Con: Python-only (the fsspec hook exists only in the DuckDB Python client).

### 2.4 Option C: status quo — plain Parquet via `ext.arrow`, no DuckLake

**Pattern:** What the docs already describe: remote-store as PyArrow
filesystem, DuckDB querying PyArrow datasets, table format optional
(`docs-src/guides/data-lake-patterns.md`).

**How it works:** `pyarrow_fs(store)` + `pyarrow.dataset` + `duckdb.sql`
over the dataset. All I/O flows through remote-store.

**Trade-offs:**

- Pro: zero new surface; full remote-store feature coverage of every byte.
- Con: no ACID, no time travel, no schema evolution, no multi-writer story —
  exactly the gaps DuckLake exists to fill.

---

## 3. Evaluation

| Criterion | A: native side-by-side | B: fsspec adapter | C: status quo |
|---|---|---|---|
| Works today | Yes (recent DuckDB) | No (`ext.fsspec` must be built) | Yes |
| DuckLake features (ACID, time travel, schema evolution) | Yes | Yes | — |
| I/O performance | Best (C++, parallel) | GIL-bound Python | GIL/Arrow-bound |
| remote-store coverage of lake I/O | — (bypassed) | Full (observe, errors, cache) | Full |
| Backend portability of the lake | Azure/S3/GCS/local only | Any remote-store backend | Any backend |
| Testability (in-memory lake) | — | Yes (`MemoryBackend`) | Yes |
| New remote-store surface to maintain | None | fsspec adapter + conformance | None |
| Client scope | Any DuckDB client | Python only | Python only |
| Version floor concern | DuckDB with Azure writes (2025-11+) | DuckDB Python with `register_filesystem` | None |

The options compose rather than compete: A is the deployment default, B adds
optional value on top of A (and is the only route for non-Azure/S3 backends),
C remains the right altitude for datasets that do not need a table format.

---

## 4. Recommendation

**Document Option A as the supported DuckLake-on-Azure story; treat Option B
as a backlog candidate, not a prerequisite.**

Key reasons: Option A works today with zero new code and the best I/O path,
and the ownership boundary (DuckLake owns `DATA_PATH`; remote-store owns the
prefixes around it) is compatible with remote-store's stated altitude — the
I/O layer, not a table format. Option B is genuinely feasible (full
operation-mapping coverage, § 2.3) but its value is portability and test
ergonomics, not the Azure story itself; for Azure specifically the native
extension is the better default.

Safest wording for user-facing docs (each statement backed by official
sources alone):

- Use PostgreSQL for the DuckLake catalog when you need a multi-user or
  remotely accessed lakehouse.
- Use the DuckDB or SQLite catalog options only when the deployment is local
  and the client model matches their limits (DuckDB: single client; SQLite:
  local multi-process).
- Store DuckLake data on Azure Blob or ADLS paths using DuckDB's Azure
  extension, which supports direct writes via `COPY` and documents both Blob
  (`az://` / `azure://`) and ADLS (`abfss://`) URI schemes.
- Emphasize that DuckLake treats data files as immutable and relies on
  catalog-driven visibility and maintenance rather than in-place mutation —
  hence the ownership rule: never write, move, or delete under `DATA_PATH`.

Preconditions / open questions before implementation:

1. **Docs:** add a "DuckLake on Azure" section to
   `docs-src/guides/data-lake-patterns.md` using the wording above, plus a
   version note grounded in the extension's code history (write support
   merged 2025-11 to 2026-02): advise users to verify their installed
   DuckDB/extension version supports Azure writes rather than assuming.
2. **Backlog candidate:** `ext.fsspec` adapter (Option B), unlocking
   DuckLake-on-any-backend and in-memory DuckLake tests.
3. **Verify before user-facing docs:** the remaining **[unverified]** claims
   flagged above (inlining flush semantics via
   `ducklake_flush_inlined_data` / `CHECKPOINT`, and whether the DataLake SDK
   operations duckdb-azure uses behave identically on flat-namespace
   accounts). Resolved since first draft: relative paths / relocatability,
   Hive-layout-as-default, and `ducklake-⟨uuid⟩.parquet` naming are now
   docs-verified (§ 2.1); the blanket "abfss requires HNS" claim is refuted
   by Microsoft docs (§ 2.1).
