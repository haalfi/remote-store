# Research: Azure PyArrow Optimization

**Date:** 2026-03-24
**Scope:** Evaluating native PyArrow filesystem integration for the Azure
backend to achieve Tier 1 read performance for analytical workloads
(Parquet, PyArrow datasets, Dagster, medallion architecture).

---

## 1. Problem Statement

The Azure backend (`AzureBackend`) currently lacks a native PyArrow filesystem
handle. When used through the `StoreFileSystemHandler` (spec 014), it falls to
**Tier 2** (full materialization via `read_bytes()` → `BufferReader`) for all
`open_input_file` calls. For files over the materialization threshold (64 MB),
a warning is emitted and the entire file is loaded into memory.

This has three consequences for analytical workloads:

1. **No column pruning.** Reading 3 columns from a 500 MB Parquet file
   downloads all 500 MB instead of ~30 MB of column chunks. The C++
   `ReadAt(offset, length)` → HTTP Range request pipeline is unavailable.
2. **No I/O coalescing.** PyArrow's `pre_buffer=True` optimization
   (ARROW-8562), which coalesces nearby byte ranges into fewer requests for
   4–6x speedups, cannot activate without a native filesystem.
3. **No streaming for large files.** Files > 64 MB trigger full
   materialization with a memory-cost warning. PR #259 (ID-100) adds
   `ext.seekable` with `SpooledTemporaryFile` fallback, but the file is still
   downloaded entirely before any byte is consumed.

The S3 backend solved this with `S3PyArrowBackend` (spec 011) — a hybrid that
uses PyArrow's C++ `S3FileSystem` for data-path operations and `s3fs` for
control-path operations. An analogous approach is needed for Azure.

---

## 2. Current Architecture

### 2.1 Azure Backend Data Path

```
AzureBackend.read(path)
  → BlobClient.download_blob(max_concurrency=N)
  → StorageStreamDownloader.chunks()     # forward-only iterator
  → _AzureBinaryIO(chunks_iter)          # io.RawIOBase adapter
  → BufferedReader(ErrorMappingStream)    # no seek(), no readat()
```

**Key limitation:** `_AzureBinaryIO` wraps a chunk iterator — there is no
`seek()`, no random access, and no way to request byte ranges. The Azure
Blob SDK's `download_blob(offset=, length=)` supports range requests, but
the current adapter does not expose them.

### 2.2 PyArrow Adapter Tier Mapping

| Tier | Condition | Azure Status |
|------|-----------|-------------|
| **Tier 1** | `store.unwrap(pyarrow.fs.FileSystem)` succeeds | Not available — `unwrap()` only supports `FileSystemClient` |
| **Tier 2** | File ≤ 64 MB | Used (full materialization) |
| **Tier 3** | File > 64 MB, seekable stream | Not applicable (non-seekable) |
| **Tier 2 fallback** | File > 64 MB, non-seekable | Used with memory warning |

### 2.3 S3PyArrow Pattern (Precedent)

`S3PyArrowBackend` (spec 011) demonstrates the dual-library approach:

| Path | Library | Operations |
|------|---------|-----------|
| **Data path** | `pyarrow.fs.S3FileSystem` (C++) | read, read_bytes, write, write_atomic, copy |
| **Control path** | `s3fs` (Python/botocore) | exists, is_file, list_files, delete, move |

Both libraries authenticate with the same credentials. The `unwrap()` method
returns the PyArrow filesystem, enabling Tier 1 reads through the
`StoreFileSystemHandler`.

---

## 3. Candidate Libraries

### 3.1 pyarrowfs-adlgen2

**Repository:** github.com/kaaveland/pyarrowfs-adlgen2
**PyPI:** pyarrowfs-adlgen2 (MIT license)
**Version:** 0.2.5 (June 2024)
**Downloads:** ~48,000/week

A thin `pyarrow.fs.FileSystemHandler` implementation for ADLS Gen2. Uses the
same `azure-storage-file-datalake` SDK that our `AzureBackend` already uses.

**API:**

```python
import pyarrowfs_adlgen2
import azure.identity
import pyarrow.fs

# Single-container access
handler = pyarrowfs_adlgen2.FilesystemHandler.from_account_name(
    "mystorageacct", "mycontainer",
    credential=azure.identity.DefaultAzureCredential(),
    timeouts=pyarrowfs_adlgen2.Timeouts(
        file_client_timeout=30,
        file_system_timeout=15,
    ),
)
fs = pyarrow.fs.PyFileSystem(handler)

# Whole-account access (paths: "container/path/file")
handler = pyarrowfs_adlgen2.AccountHandler.from_account_name(
    "mystorageacct",
    credential=azure.identity.DefaultAzureCredential(),
)
fs = pyarrow.fs.PyFileSystem(handler)
```

**Strengths:**
- Uses `azure-storage-file-datalake` (DFS endpoint) — same SDK as our backend.
- Native ADLS Gen2 directory listing — O(1) vs Blob SDK's prefix scanning.
- `FileSystemHandler` interface — direct PyArrow integration without fsspec.
- `FilesystemHandler` constructor accepts a raw `FileSystemClient`, which our
  backend already creates lazily (`_fs` property).
- Lightweight: ~1k LOC, MIT license, minimal dependencies.

**Weaknesses:**
- **HNS-only.** Does not work with plain Blob Storage accounts. Uses the
  DFS SDK exclusively — no fallback to Blob SDK.
- **Alpha status** on PyPI despite being described as "stable."
- Single maintainer, low activity (28 stars, last release June 2024).
- `copy_file` uses download-then-upload (no server-side copy).
- No CI/CD, no published docs, still uses `setup.py`.
- Hard-coded `*.dfs.core.windows.net` endpoint validation — no OneLake
  support (issue #27).
- No version pin on `azure-storage-file-datalake`.
- `open_input_file` is identical to `open_input_stream` — same `PythonFile`
  wrapping, same GIL overhead. **Does NOT provide true C++ range requests.**

**Critical finding:** pyarrowfs-adlgen2 wraps Python file objects in
`PythonFile`, which means every `ReadAt` call acquires the GIL and goes through
Python dispatch. This is the **same overhead** that spec 014 criticizes in
PyArrow's `FSSpecHandler`. It does NOT provide C++ native I/O — the performance
benefit comes primarily from faster directory listing via the DFS SDK, not from
the I/O path itself.

### 3.2 adlfs (fsspec-based)

**Repository:** github.com/fsspec/adlfs
**PyPI:** adlfs (~1.3M downloads/week)
**Status:** Actively maintained by multiple contributors.

**Strengths:**
- Wide adoption, active maintenance.
- Works with both HNS and non-HNS accounts.
- Broad ecosystem support (Dask, xarray, pandas).
- PyArrow can wrap it via `FSSpecHandler`.

**Weaknesses:**
- Uses `azure-storage-blob` (Blob endpoint), not the DFS SDK.
- Directory listing is prefix-based — O(n) for deep hierarchies.
- `FSSpecHandler` wrapping has the same `PythonFile` GIL overhead.
- Fragile error translation (string matching on exception messages).
- Transitive dependency weight (fsspec + azure-storage-blob).
- Already rejected in RFC-0001 for the base Azure backend.

**Conclusion:** adlfs is worse than pyarrowfs-adlgen2 for our use case. It
provides no PyArrow-native I/O, adds the Blob SDK endpoint (slower listing),
and was already rejected for the base backend.

### 3.3 obstore (object-store-python)

**Repository:** github.com/developmentseed/obstore
**PyPI:** obstore
**Status:** Active development, backed by Rust `object_store` crate (same
crate used by DataFusion, Polars, InfluxDB, Delta-rs).

A Rust-backed `pyarrow.fs.FileSystemHandler` via PyO3. Implements I/O
entirely in Rust — no `PythonFile`, no GIL contention on the read path.

**Strengths:**
- **True C++-equivalent I/O.** Rust native code issues HTTP Range requests
  without GIL overhead. This is the performance ceiling for
  `FileSystemHandler` implementations.
- Multi-cloud: S3, GCS, Azure (Blob + ADLS Gen2), local.
- Active maintenance, growing community.
- Server-side copy, multipart uploads.
- Supports `pyarrow.fs.FileSystem` interface directly.

**Weaknesses:**
- Rust binary dependency — more complex build, platform-specific wheels.
- Young project, API may still evolve.
- Adds a non-trivial transitive dependency (`object_store` crate).
- Azure support may not use the DFS endpoint natively in all operations
  (the `object_store` crate treats Azure as flat blob storage).
- Less control over Azure-specific features (HNS detection, atomic
  rename) — the Rust crate abstracts these away.

### 3.4 pyarrow.fs.AzureFileSystem (Built-in C++ Filesystem)

**Source:** PyArrow ships a C++ `AzureFileSystem` backed by the Azure SDK for
C++, directly analogous to `S3FileSystem` used by `S3PyArrowBackend`.

**API:**

```python
from pyarrow.fs import AzureFileSystem

# Account-key auth
fs = AzureFileSystem(account_name="mystorageacct", account_key="...")

# DefaultAzureCredential-style (via C++ Azure SDK)
fs = AzureFileSystem(account_name="mystorageacct")
```

**Strengths:**
- **True Tier 1 — zero GIL overhead.** All I/O happens in C++ with no
  `PythonFile` bridge. `ReadAt` maps directly to HTTP Range requests via the
  C++ Azure SDK, with `ReadRangeCache` coalescing and connection pooling.
- Direct analog of the `S3PyArrowBackend` pattern — `unwrap()` returns this
  filesystem, `StoreFileSystemHandler` gets native C++ performance.
- No new Python dependency — ships with PyArrow itself.
- Supports Blob Storage and ADLS Gen2.

**Weaknesses:**
- **Auth limitations.** The C++ Azure SDK's credential support is narrower than
  the Python `azure-identity` package. `DefaultAzureCredential`, managed
  identity, and environment-based auth are supported, but interactive browser
  auth, `AzureCliCredential`, and custom token providers require investigation.
  Our backend supports `connection_string`, `account_key`,
  `DefaultAzureCredential`, and `ClientSecretCredential` — each needs
  validation against the C++ SDK.
- **Maturity.** `AzureFileSystem` was added in PyArrow 15.0.0 (Jan 2024) and
  is still marked as experimental. The S3 and GCS C++ filesystems are
  significantly more mature.
- **HNS handling unclear.** Whether the C++ SDK correctly handles hierarchical
  namespace operations (atomic rename, directory-level ACLs) on ADLS Gen2
  needs investigation.
- **Limited control-path operations.** Like `S3FileSystem`, it may lack some
  control-path features we need (HNS detection, soft-delete, last-modified
  filtering). We would still need the Python Azure SDK for the control path.

**Critical assessment:** If `AzureFileSystem` supports our required auth
methods and handles both HNS and non-HNS accounts, it is the strongest
candidate — providing the same true-Tier-1 benefits that `S3FileSystem` gives
`S3PyArrowBackend`. However, its experimental status and auth coverage gaps
must be validated before committing to it. A spike is needed: test the four
auth methods against both HNS and non-HNS accounts, verify `ReadRangeCache`
activates, and benchmark against `download_blob(offset=, length=)`.

### 3.5 Build Our Own FileSystemHandler

Rather than depending on a third-party library, we could implement a
`pyarrow.fs.FileSystemHandler` directly in the `AzureBackend`, analogous to
how `StoreFileSystemHandler` works but using the Azure SDK's range-request
capabilities directly.

**Approach:**

```python
# In AzureBackend or a new AzurePyArrowBackend:
def unwrap(self, type_hint):
    if type_hint is pyarrow.fs.FileSystem:
        return pyarrow.fs.PyFileSystem(self._build_handler())
    ...

def _build_handler(self):
    # Return a FileSystemHandler that uses:
    # - download_blob(offset=, length=) for range reads
    # - DataLake SDK for listing
    # - Existing error mapping
    ...
```

**Strengths:**
- Full control over credential bridging, error mapping, HNS detection.
- Can use `download_blob(offset=, length=)` for byte-range requests.
- No new dependency.
- Consistent with the codebase's "direct SDK" philosophy (RFC-0001).
- Can fall back gracefully for non-HNS accounts.

**Weaknesses:**
- Still `PythonFile` wrapping — GIL overhead on every `ReadAt`.
- More code to write and maintain (~300–500 LOC).
- `download_blob(offset=, length=)` issues a fresh HTTP request per range,
  unlike C++ implementations that use connection pooling and HTTP/2.

**Critical insight:** Even with our own `FileSystemHandler`, the `PythonFile`
bridge is unavoidable for any Python-based implementation. The GIL overhead
from `ReadAt → GIL acquire → Python seek + read → GIL release` is inherent
to `pyarrow.fs.PyFileSystem`. Only Rust/C++ implementations (obstore,
PyArrow's built-in S3/GCS) avoid this.

---

## 4. Performance Analysis

### 4.1 Where Does the Performance Actually Come From?

Breaking down the performance layers:

| Layer | C++ native (S3FileSystem) | PythonFile (pyarrowfs/adlfs/custom) | Tier 2 (current Azure) |
|-------|--------------------------|--------------------------------------|------------------------|
| Column pruning | Yes (range reads) | Yes (range reads via Python) | No (full file) |
| I/O coalescing | Yes (C++ ReadRangeCache) | No (Python dispatch per range) | No |
| GIL-free reads | Yes | No | N/A |
| Connection pooling | Yes (C++ HTTP client) | Per-request (Azure SDK) | N/A |
| Directory listing | S3 ListObjectsV2 | Varies by SDK | Blob prefix scan |

**Key takeaway:** The biggest win is **column pruning** — reading only the byte
ranges needed instead of the full file. This is achievable with any
`FileSystemHandler` that supports range reads, even with `PythonFile` overhead.
I/O coalescing and GIL-free reads are secondary optimizations that matter at
high concurrency.

### 4.2 Estimated Impact by Workload

| Workload | Current (Tier 2) | With range-read handler | Improvement |
|----------|------------------|------------------------|-------------|
| Single Parquet file, 3/50 columns, 500 MB | Download 500 MB | Download ~30 MB | **~17x less data** |
| Dataset scan, 100 files × 200 MB, filter pushdown | 20 GB into memory | ~2 GB range reads | **~10x less data** |
| Directory listing, 1000 files on HNS | Blob prefix scan | DFS native listing | **~3x faster** |
| Small Parquet file (< 64 MB) | Full materialization (fast enough) | Range reads (marginal gain) | Minimal |

### 4.3 pyarrowfs-adlgen2 vs Custom Handler

Both use `PythonFile` wrapping, so I/O performance should be similar. The
differences are:

| Aspect | pyarrowfs-adlgen2 | Custom handler |
|--------|-------------------|---------------|
| Credential bridging | Factory method or raw `FileSystemClient` | Reuse existing backend credentials |
| HNS fallback | None (HNS-only) | Full (reuse existing `_hns` detection) |
| Error mapping | Azure exceptions propagate raw | Mapped to `RemoteStoreError` hierarchy |
| Listing performance | Native DFS directory listing | Same (we already use DFS on HNS) |
| Server-side copy | Not supported (download + upload) | Supported (existing `copy()` method) |
| Maintenance | External dependency | Internal code |

---

## 5. Recommendation

### 5.1 Preferred Approach: AzurePyArrowBackend (Custom Handler)

Build an `AzurePyArrowBackend` that follows the `S3PyArrowBackend` pattern:

| Path | Implementation | Operations |
|------|---------------|-----------|
| **Data path** | Custom `FileSystemHandler` using `download_blob(offset=, length=)` for range reads, `upload_blob()` for writes | `read`, `read_bytes`, `write`, `write_atomic`, `open_atomic` |
| **Control path** | Inherit from `AzureBackend` (or shared base) | `exists`, `is_file`, `list_files`, `delete`, `move`, `copy` |
| **PyArrow bridge** | `unwrap(pyarrow.fs.FileSystem)` → `PyFileSystem(handler)` | Tier 1 reads in `StoreFileSystemHandler` |

**Why not pyarrowfs-adlgen2:**
1. HNS-only — breaks for non-HNS users.
2. No error mapping — Azure exceptions propagate raw.
3. Alpha status, single maintainer.
4. No server-side copy.
5. We'd need to bridge credentials anyway.
6. ~80% of what we need, but the remaining 20% (HNS fallback, error mapping,
   credential bridging) requires enough glue code that we might as well own
   the handler.

**Why not obstore:**
1. Rust binary dependency — heavier than the Azure SDK we already use.
2. Less control over Azure-specific features (HNS detection, atomic rename).
3. Would replace our carefully designed error mapping and capability system.
4. Overkill for a single-cloud optimization when we already have the SDK.

**Why not adlfs:**
1. Already rejected in RFC-0001. Same weaknesses still apply.

### 5.2 Implementation Outline

```python
class _AzureRangeReader(io.RawIOBase):
    """Seekable reader using Azure Blob SDK range requests."""

    def __init__(self, blob_client, file_size: int, max_concurrency: int = 1):
        self._bc = blob_client
        self._size = file_size
        self._pos = 0
        self._max_concurrency = max_concurrency

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._size + offset
        self._pos = max(0, min(self._pos, self._size))
        return self._pos

    def tell(self) -> int:
        return self._pos

    def readinto(self, b: bytearray | memoryview) -> int:
        remaining = self._size - self._pos
        if remaining <= 0:
            return 0
        length = min(len(b), remaining)
        stream = self._bc.download_blob(
            offset=self._pos, length=length,
            max_concurrency=self._max_concurrency,
        )
        # Stream directly into caller's buffer to avoid a temporary
        # copy.  writable_buf adapts memoryview/bytearray for readinto.
        writable_buf = memoryview(b)[:length]
        n = stream.readinto(writable_buf)
        self._pos += n
        return n
```

This gives PyArrow's Parquet reader the `seek()` + `read()` interface it needs
for column-chunk access. Each `ReadAt(offset, length)` translates to a single
HTTP Range request via `download_blob(offset=, length=)`.

### 5.3 Scope and Phasing

**Phase 0: Spike — evaluate `pyarrow.fs.AzureFileSystem`**
- Test `AzureFileSystem` with: `connection_string`, `account_key`,
  `DefaultAzureCredential`, `ClientSecretCredential`.
- Verify against both HNS and non-HNS accounts.
- Confirm `ReadRangeCache` activates (I/O coalescing for Parquet).
- Benchmark vs `download_blob(offset=, length=)` for range-read throughput.
- **If viable:** use as data-path filesystem (true C++ Tier 1, same as
  `S3PyArrowBackend`). **If not:** proceed with custom `FileSystemHandler`.

**Phase 1: Core handler + Tier 1 reads** (this item)
- `_AzureRangeReader` — seekable reader via range requests.
- `_AzureFileSystemHandler` — `pyarrow.fs.FileSystemHandler` impl.
- `AzurePyArrowBackend` — hybrid backend with `unwrap(pyarrow.fs.FileSystem)`.
- Spec: `sdd/specs/0XX-azure-pyarrow-backend.md`.
- Works with HNS accounts only (DFS listing); non-HNS falls back to base
  `AzureBackend` behavior (Tier 2 in adapter).

**Phase 2: Benchmarks and validation**
- Benchmark against Tier 2 on real Parquet datasets.
- Quantify: column pruning savings, listing speedup, memory reduction.
- Compare with pyarrowfs-adlgen2 to validate our handler matches its
  listing performance.

**Phase 3: Polish**
- Dagster integration testing (medallion pipeline with Azure + PyArrow).
- Documentation: guide update, example script.
- Optional: support non-HNS accounts with Blob SDK range reads (no DFS
  listing benefit, but still gets column pruning).

### 5.4 Dependencies

No new PyPI dependencies. The handler uses:
- `azure-storage-file-datalake` (already required by `azure` extra).
- `pyarrow` (already required by `arrow` extra).

A new combined extra would be convenient:
```toml
azure-pyarrow = ["azure-storage-file-datalake>=12.16.0", "azure-identity>=1.0.0", "pyarrow>=12.0.0"]
```

### 5.5 Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| `download_blob(offset=, length=)` per range is too slow (HTTP overhead per call) | Medium | Batch small ranges into larger requests; profile first |
| Non-HNS accounts get no benefit | Low (HNS is standard for analytics) | Document clearly; non-HNS users keep base `AzureBackend` |
| `PythonFile` GIL overhead limits concurrency | Low for typical use | Acceptable trade-off; only obstore avoids this |
| Maintenance burden of custom handler | Low | ~300–500 LOC, thin wrapper over Azure SDK we already use |

---

## 6. Decision

**Proceed with Phase 0 spike first** — evaluate `pyarrow.fs.AzureFileSystem`
(Section 3.4) against our four auth methods and both HNS/non-HNS accounts.
If viable, it replaces the custom handler as the data-path implementation
(true C++ Tier 1). If not viable (auth gaps, experimental instability), fall
back to Phase 1 with the custom `PythonFile`-based handler.

**Phase 1** — create `AzurePyArrowBackend` with the chosen data-path
implementation. This provides:

1. **Column pruning** for Parquet reads (the single biggest win — up to 17x
   less data transfer per Section 4.2).
2. **Tier 1 dispatch** with `StoreFileSystemHandler` — `unwrap()` returns a
   `pyarrow.fs.FileSystem`, enabling range-read column access. Note: this is
   a `PythonFile` bridge, not true C++ Tier 1; I/O coalescing and GIL-free
   reads require `pyarrow.fs.AzureFileSystem` (see Section 3.4 and Phase 0).
3. **No new dependencies** beyond what the `azure` and `arrow` extras already provide.
4. **Consistent error mapping** and credential handling.
5. **HNS-aware listing** via the DFS SDK (already implemented in `AzureBackend`).

Backlog item: **ID-102**.

---

## 7. References

- Spec 014: PyArrow FileSystem Adapter (`sdd/specs/014-pyarrow-filesystem-adapter.md`)
- Spec 011: S3-PyArrow Hybrid Backend (`sdd/specs/011-s3-pyarrow-backend.md`)
- Spec 012: Azure Backend (`sdd/specs/012-azure-backend.md`)
- RFC-0001: Azure Backend via Direct ADLS Gen2 SDK (`sdd/rfcs/rfc-0001-azure-backend.md`)
- PR #259: ID-100 Seekable read capability + extension
- pyarrowfs-adlgen2: github.com/kaaveland/pyarrowfs-adlgen2 (v0.2.5)
- adlfs: github.com/fsspec/adlfs
- obstore: github.com/developmentseed/obstore
- ARROW-8562: I/O coalescing for Parquet (github.com/apache/arrow/pull/7022)
- Azure SDK: `download_blob(offset=, length=)` range request support
- PyArrow AzureFileSystem: arrow.apache.org/docs/python/generated/pyarrow.fs.AzureFileSystem.html
