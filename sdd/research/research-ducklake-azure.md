# Research: DuckLake on Azure for remote-store users

**Item ID:** — (research only, no backlog item yet)
**Date:** 2026-07-02
**Status:** Research report — findings only, no code changes

---

## 1. Question

Can remote-store users whose data lives on Azure (the `azure` /
`AsyncAzureBackend` backends: Blob Storage or ADLS Gen2 via the Azure SDK)
adopt DuckLake, and to what extent do remote-store's features remain useful
alongside it? Should remote-store document or support a DuckLake-on-Azure
story?

## 2. Method and sources

Two research tracks, run 2026-07-02:

1. **Official documentation only** (duckdb.org, ducklake.select,
   learn.microsoft.com), via a fan-out search + adversarial-verification
   harness. Claims below labelled **[verified]** survived 3-vote adversarial
   verification against the cited page; **[unverified]** means the claim was
   extracted from an official page but its verification pass did not complete
   (session limits), so treat as plausible-but-unconfirmed.
2. **Source-level reading** of the current `main` branches of
   [duckdb/duckdb-azure](https://github.com/duckdb/duckdb-azure),
   [duckdb/ducklake](https://github.com/duckdb/ducklake), and
   [duckdb/duckdb-python](https://github.com/duckdb/duckdb-python), labelled
   **[code]** with file references.

Note: duckdb.org / ducklake.select pages were partially proxy-blocked in this
environment; where needed, the identical page sources were read from the
`duckdb/duckdb-web` and `duckdb/ducklake-web` repositories.

## 3. Verdict

**Yes.** DuckLake on Azure works today with no gaps, using DuckDB's own
`azure` extension for the data path. The recommended production shape for
multi-user access is: catalog on Azure Database for PostgreSQL, Parquet data
files on Azure Blob / ADLS Gen2. remote-store is not needed in DuckLake's
data path, but nearly all of its surrounding features remain useful, and a
thin fsspec adapter over `Store` could serve as DuckLake's data-path
filesystem with full operation coverage if we ever want remote-store in that
role.

One version caveat dominates everything else: **write support in the DuckDB
`azure` extension is recent** (landed between 2025-11 and 2026-02, see § 5).
Users on older DuckDB versions have a read-only Azure filesystem and DuckLake
cannot write data files through it.

## 4. DuckLake architecture on Azure

DuckLake = a SQL catalog database (all metadata, all file paths) + Parquet
data files at a `DATA_PATH`. "DuckLake manages files stored in a separate
storage location. The paths to the files are stored in the catalog server."
([paths](https://ducklake.select/docs/stable/duckdb/usage/paths)) **[verified]**

Catalog database options and their Azure fit:

| Catalog | Azure hosting | Fit |
|---|---|---|
| PostgreSQL | Azure Database for PostgreSQL | **Recommended.** "If you would like to operate a multi-user lakehouse with potentially remote clients, use PostgreSQL as the catalog database." **[verified]** |
| DuckDB file | any (file on disk) | Single client only: "if you are using DuckDB as your catalog database, you're limited to a single client." **[verified]** |
| SQLite file | any (file on disk) | Multi-process on one machine; no remote clients |
| MySQL | Azure Database for MySQL | **Not recommended** by DuckLake: "There are a number of known issues with MySQL as a catalog for DuckLake. … We therefore do not recommend to use MySQL as a catalog for DuckLake." **[verified]** |

Catalog and data are independently placeable: `DATA_PATH` is an `ATTACH`
option separate from the catalog connection string, e.g.
`ATTACH 'ducklake:postgres:…' AS lake (DATA_PATH 'az://container/lake/')`.
([choosing_a_catalog_database](https://ducklake.select/docs/stable/duckdb/usage/choosing_a_catalog_database))
**[verified]**

Supported data-path filesystems per DuckLake docs: "any file system backend
that DuckDB supports", explicitly listing Azure Blob Store and "Python fsspec
file systems".
([choosing_storage](https://ducklake.select/docs/stable/duckdb/usage/choosing_storage))
**[code]** (read from ducklake-web source)

Feature set relevant to storage behaviour:

- **ACID via the catalog.** Data files are written first, then become visible
  when the catalog transaction commits; concurrency control lives entirely in
  the catalog database. **[code]** (see § 6)
- **Data inlining.** Enabled by default with a row limit of 10: small
  inserts/deletes go into catalog tables instead of Parquet files.
  **[verified]** Inlined data is flushed to Parquet later
  (`ducklake_flush_inlined_data` / `CHECKPOINT`) **[unverified]** — so "small
  writes never touch Blob storage" is *not* a safe claim (a verifier refuted
  that phrasing 2-1); small writes touch Blob storage *eventually*.
- **Time travel / monotonic growth.** "DuckLake in normal operation never
  removes any data, even when tables are dropped or data is deleted."
  **[verified]** Physical removal is a two-step maintenance flow: data "can
  only be physically removed … by expiring snapshots"
  (`ducklake_expire_snapshots`) **[verified]**, and "expiring snapshots does
  not immediately delete files that are no longer referenced" — a separate
  `ducklake_cleanup_old_files` call deletes them. **[verified]** Without
  maintenance, the Azure container grows monotonically.

## 5. The load-bearing fact: Azure writes in DuckDB

**Official docs (current and LTS):** "You can write data directly to Azure
Blob or ADLSv2 Storage using the `COPY` statement." No read-only limitation
section exists any more. Schemes: `az://` / `azure://` (Blob), `abfss://`
(ADLS). Auth via DuckDB secrets: `CONFIG` (connection string, default),
`CREDENTIAL_CHAIN`, managed identity, `SERVICE_PRINCIPAL`. Read tuning:
`azure_read_transfer_concurrency`, `azure_read_transfer_chunk_size`,
`azure_read_buffer_size`.
([azure extension](https://duckdb.org/docs/stable/core_extensions/azure))

**Source level [code]:** any memory of "the azure extension is read-only" is
stale, but only barely:

- Blob writes merged 2025-11-26 (duckdb-azure PR #131), ADLS/DFS writes
  merged 2025-12 (PR #140), blob writes moved to the block API 2026-02-23
  (PR #151).
- Blob path (`azure_blob_filesystem.cpp`): sequential writes staged via
  `blob_client.StageBlock(...)`, committed atomically at close via
  `CommitBlockList` — a reader never sees a partial file.
- DFS path (`azure_dfs_filesystem.cpp`): sequential `file_client.Append(...)`
  plus `Flush`.
- Both throw `NotImplementedException` for append mode and read+write mode;
  neither implements `MoveFile` or `Truncate` (those fall through to DuckDB's
  base class, which throws "MoveFile is not implemented!").
- Blob filesystem's `CreateDirectory` is an explicit no-op; DFS implements it
  for real (directories exist under HNS).

Practical consequence: **document a DuckDB version floor** for any
DuckLake-on-Azure guidance (write support ships in current stable and LTS
docs as of 2026-07; verify the user's installed extension version rather than
assuming).

Azure-side note: `az://` uses the Blob API (works on flat and HNS accounts);
`abfss://` uses the Data Lake (DFS) API, i.e. presupposes an ADLS Gen2 /
HNS-enabled account **[unverified against learn.microsoft.com in this run]**.
This matches remote-store's own model: `AzureBackend` requires an explicit
`hns` flag and serves both account shapes through the Blob API.

## 6. What DuckLake actually does on the data path [code]

From `duckdb/ducklake` source, the complete filesystem contract:

| Operation | Where | Notes |
|---|---|---|
| Write-once Parquet files | `ducklake_insert.cpp` | Unique names `ducklake-{uuidv7}`; `use_tmp_file = false` — **no write-temp-then-rename, ever** |
| Random-access reads | Parquet reader | Footer + row-group range reads |
| Delete files | `ducklake_transaction.cpp`, `ducklake_cleanup_files.cpp` | Rollback cleanup, `cleanup_old_files`, `delete_orphaned_files`; `TryRemoveFile` semantics |
| Recursive glob `**` + `last_modified` | `ducklake_metadata_manager.cpp` | Only for `ducklake_delete_orphaned_files`; normal operation never lists the data path — paths come from the catalog |
| Create directory | `ducklake_util.cpp` | Local paths only; skipped for remote paths, failures swallowed |
| Rename / move / append / truncate / lock | — | **Never used.** "DuckLake as a concept will *never* change existing files, neither by changing existing content nor by appending to existing files." (choosing_storage) |

This write-once, catalog-committed design is why the azure extension's
restrictions (no move, no append, no read+write) are harmless: DuckLake
needs none of them.

## 7. remote-store fit

### 7.1 Where remote-store features genuinely complement DuckLake

DuckLake owns everything under `DATA_PATH`; remote-store must never write,
move, or delete files there (even "orphan-looking" ones — time travel keeps
old files referenced, and deletion is DuckLake maintenance's job, § 4).
Around that boundary, the existing feature set applies cleanly:

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
| `ext.partition` | Mostly superseded inside the data path — DuckLake tracks partition values in the catalog and its Hive-style layout is an internal default **[unverified]**; parsing paths for observability is fine, constructing them is not |

### 7.2 Could remote-store *be* the data path? (fsspec adapter analysis)

DuckDB Python officially registers fsspec filesystems:
`duckdb.register_filesystem(fsspec.AbstractFileSystem)` **[verified]**, with
protocol-based URL routing; the wrapper (`duckdb-python/src/pyfilesystem.cpp`)
implements the full write surface (`open("wb")`, `write`, `flush`, `close`,
`rm`, `glob`, `ls`, `isfile`, `size`, `modified`, `mv`, `mkdir`) **[code]**,
and the registered-fsspec path demonstrably supports SQL-driven `COPY TO`
writes in current stable DuckDB **[verified empirically against duckdb
1.5.4]**. DuckLake's docs explicitly list fsspec filesystems as supported
storage.

Mapping DuckLake's contract (§ 6) onto remote-store capabilities:

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

No hard gaps. Two honest caveats: (a) remote-store commits whole objects at
handle close rather than streaming staged blocks like duckdb-azure's
`StageBlock` path — a memory/temp-spool consideration for large Parquet
files, not a correctness issue given write-once semantics; (b) a Python
fsspec filesystem runs under the GIL and will not match the C++ extension's
parallel range reads (DuckDB's own docs carry this performance caveat).

**Missing piece:** remote-store ships a PyArrow filesystem adapter
(`ext.arrow`) but no fsspec `AbstractFileSystem` adapter. That adapter is the
one deliverable that would let *any* remote-store backend (not just Azure —
also SFTP, sql-blob, memory for tests) serve as a DuckLake data path.
Recommendation: worth a backlog item as an opt-in `ext.fsspec`; for Azure
specifically the native extension is the better default, so the adapter's
value is backend portability and test ergonomics (e.g. DuckLake integration
tests against `MemoryBackend`).

## 8. Recommended user story (if we document it)

```text
Azure Blob / ADLS Gen2 container
├── lake/          ← DuckLake DATA_PATH (DuckDB azure extension writes here;
│                     remote-store: read-only inspection at most)
├── raw/           ← remote-store Store (ingest, ext.transfer, ext.observe)
└── exports/       ← remote-store Store (app-owned outputs)
```

with the catalog on Azure Database for PostgreSQL (multi-user) or a local
DuckDB file (single client), DuckDB secret via `CREDENTIAL_CHAIN` (aligns
with remote-store's `DefaultAzureCredential` default), and a documented
DuckDB version floor for Azure write support.

## 9. Possible follow-ups (user decides)

1. Docs: a "DuckLake on Azure" section in `docs-src/guides/data-lake-patterns.md`
   (the guide already positions table formats above remote-store and shows the
   DuckDB read path via `pyarrow_fs`).
2. Backlog candidate: `ext.fsspec` adapter (§ 7.2), unlocking
   DuckLake-on-any-backend and in-memory DuckLake tests.
3. Backlog candidate: verify the flagged **[unverified]** claims (relative
   paths / relocatability, inlining flush semantics, partition layout) before
   committing any of them to user-facing docs.
