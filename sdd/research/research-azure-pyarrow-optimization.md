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
   (PARQUET-1820), which coalesces nearby byte ranges into fewer requests
   for significant speedups, cannot activate without a native filesystem.
3. **No streaming for large files.** Files > 64 MB trigger full
   materialization with a memory-cost warning. PR #259 (ID-100) adds
   `ext.seekable` with `SpooledTemporaryFile` fallback, which enables Tier 3
   (`PythonFile` streaming), but the entire file is still downloaded before
   any byte is consumed — there are no range requests.

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
| **Tier 3** | File > 64 MB, seekable stream | Available via `ext.seekable` (ID-100), but downloads entire file — no range requests |
| **Tier 2 fallback** | File > 64 MB, non-seekable | Used with memory warning (default without `ext.seekable`) |

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
- Native ADLS Gen2 directory listing — fewer round-trips vs Blob SDK's prefix scanning.
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

**Conclusion:** adlfs is a weaker fit than pyarrowfs-adlgen2 for HNS accounts.
Both share the same `PythonFile` GIL overhead (neither provides C++ native I/O),
but adlfs pulls in `fsspec` as a new transitive dependency (we don't use fsspec
anywhere else), and its Blob-endpoint listing is slower on HNS accounts.
(`azure-storage-blob` is NOT an incremental dep — it's already a transitive
dependency of `azure-storage-file-datalake`.) adlfs does support non-HNS
accounts, which pyarrowfs-adlgen2 does not — but this advantage is marginal
since our primary target (analytical workloads on data lakes) implies HNS.
RFC-0001 rejected adlfs for the base backend; the `fsspec` dependency-weight
and error-translation concerns carry over here.

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
- **Maturity.** `AzureFileSystem` was added in PyArrow 16.0.0 (Apr 2024) and
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

## 5. Simpler Path: Seekable Range Reader in Existing Backend

### 5.1 The Insight

The candidate evaluation in Section 3 focuses on `FileSystemHandler`
implementations and new backend classes. But `pyarrow.NativeFile` — the base
class for all Arrow streams — supports `read_at(nbytes, offset)` for
stateless random access. `pa.PythonFile` (which wraps Python file objects)
exposes this as `seek(offset) + read(nbytes)`. The existing Tier 3 path in
`ext/arrow.py` already wraps seekable streams in `PythonFile`:

```python
# ext/arrow.py, open_input_file — Tier 3
stream = self._store.read(path)
if hasattr(stream, "seekable") and stream.seekable():
    return pa.PythonFile(stream, mode="r")
```

If `AzureBackend.read()` returned a **seekable range-reader** — a `RawIOBase`
subclass that translates `seek()` + `readinto()` into
`download_blob(offset=, length=)` HTTP Range requests — the existing tier
machinery handles everything else:

1. PyArrow's Parquet reader calls `read_at(offset, length)` on the
   `PythonFile` for column-chunk access.
2. Each `read_at` becomes a single HTTP Range request via
   `download_blob(offset=, length=)`.
3. **Column pruning works**: 3 columns from a 500 MB Parquet file downloads
   ~30 MB instead of 500 MB.

No new backend class. No `FileSystemHandler`. No `unwrap()`. The core reader
is ~50 LOC; the dual-mode integration (keeping chunked streaming for
sequential callers, exposing seekable reads for PyArrow) adds ~100–150 LOC.

### 5.2 Implementation Sketch

```python
class _AzureRangeReader(io.RawIOBase):
    """Seekable reader using Azure Blob SDK range requests.

    Each readinto() issues a single HTTP Range request via
    download_blob(offset=, length=).  No data is downloaded until read.
    """

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
        # Note: download_blob().readall() double-buffers (allocates a
        # temporary bytes object then copies into b).  The real
        # implementation should use a _BufferWriter adapter whose
        # write() copies directly into the target memoryview at an
        # offset — avoiding the intermediate allocation.  Kept simple
        # here for sketch clarity.
        data = self._bc.download_blob(
            offset=self._pos, length=length,
            max_concurrency=self._max_concurrency,
        ).readall()
        n = len(data)
        b[:n] = data
        self._pos += n
        return n
```

**Error mapping:** The sketch omits `_ErrorMappingStream` wrapping. Currently
`read()` returns `BufferedReader(ErrorMappingStream(raw))` — Azure SDK
exceptions are translated to `RemoteStoreError`. The range reader would let
`azure.core.exceptions.*` propagate raw. The real implementation must wrap
`_AzureRangeReader` in `_ErrorMappingStream` (or integrate error mapping
directly). Notably, `ext/arrow.py` lines 298–303 already flag this concern:
subsequent reads from `PythonFile` bypass `_map_errors()`, so the range
reader's error mapping is the last translation boundary.

**Not a drop-in replacement for `read()`:** `_AzureRangeReader.readinto()`
issues a fresh HTTP Range request per call. When wrapped in `BufferedReader`
(as the current `read()` does), each call uses the buffer size (default 8 KB)
— meaning a 100 MB sequential read would issue ~12,800 individual HTTP
requests instead of the current chunked streaming. This is unacceptable for
`Store.read()` general-purpose callers.

The implementation needs a **dual-mode approach**:
- `read()` keeps the current chunked streaming (`_AzureBinaryIO`) for
  sequential callers — no behavior change.
- A separate path exposes `_AzureRangeReader` for the PyArrow adapter.
  Options: (a) a new capability flag (e.g., `RANGE_READ` — NOT
  `SEEKABLE_READ`, which already exists with the meaning "read() always
  returns a seekable stream"), (b) a backend-internal method like
  `_open_seekable(path)`, or (c) the `ext.seekable` composition point
  with a range-read implementation.

This raises the complexity estimate from ~50–100 LOC to ~150–200 LOC and
requires spec-level design for how the seekable path is exposed. The PoC
(Phase 1) should validate the range-read performance before committing to
the integration approach.

### 5.3 What This Does NOT Solve

The seekable range reader delivers column pruning — the single biggest win
(Section 4.2). But it has inherent limitations:

| Capability | Seekable range reader (Tier 3) | C++ native filesystem (Tier 1) |
|-----------|-------------------------------|-------------------------------|
| Column pruning | Yes — range reads via Python | Yes — range reads via C++ |
| I/O coalescing | No — one HTTP request per `read_at` | Yes — `ReadRangeCache` batches nearby ranges |
| GIL-free reads | No — `PythonFile` acquires GIL per call | Yes — all I/O in C++ |
| Connection pooling | Per-request (Azure SDK) | C++ HTTP client with keep-alive |
| Concurrent reads | Serialized (GIL + seek/read pair) | Parallel (C++ thread pool) |

For most workloads (single-user, moderate concurrency), the `PythonFile`
overhead is acceptable. I/O coalescing and GIL-free reads matter at high
concurrency or when reading many small column chunks — a measurable but
secondary optimization.

---

## 6. Full Tier 1 Path (If Needed)

If benchmarks show that the `PythonFile` overhead from Section 5 is a
bottleneck (likely only at high concurrency or with many small range reads),
the next step is true C++ Tier 1 via `pyarrow.fs.AzureFileSystem`.

### 6.1 Why AzureFileSystem Over the Other Candidates

**pyarrowfs-adlgen2, adlfs, custom FileSystemHandler:** All use `PythonFile`
wrapping — they do NOT eliminate the GIL overhead that motivates moving beyond
Section 5. Building a `FileSystemHandler` adds ~300–500 LOC of complexity for
zero I/O performance gain over the seekable range reader.

**obstore:** True Rust-native I/O (no GIL), but adds a heavy Rust binary
dependency and abstracts away Azure-specific features we need (HNS detection,
error mapping). Overkill when PyArrow ships its own C++ Azure filesystem.

**`pyarrow.fs.AzureFileSystem`:** The only option that provides true C++ Tier 1
(zero GIL, I/O coalescing, connection pooling) without a new dependency. Direct
analog of the `S3PyArrowBackend` pattern. The right choice if we need to go
beyond `PythonFile`.

### 6.2 AzurePyArrowBackend (S3PyArrow Pattern)

If `AzureFileSystem` proves viable, build an `AzurePyArrowBackend`:

| Path | Implementation | Operations |
|------|---------------|-----------|
| **Data path** | `pyarrow.fs.AzureFileSystem` (C++) | read, read_bytes, write, write_atomic, copy |
| **Control path** | Existing `AzureBackend` (Python SDK) | exists, is_file, list_files, delete, move |
| **PyArrow bridge** | `unwrap(pyarrow.fs.FileSystem)` → native C++ FS | True Tier 1 in `StoreFileSystemHandler` |

**Open questions** (require spike):
- Auth coverage: does `AzureFileSystem` support `connection_string`,
  `account_key`, `DefaultAzureCredential`, `ClientSecretCredential`?
- HNS handling: does the C++ SDK handle both HNS and non-HNS accounts?
- Maturity: `AzureFileSystem` is experimental (added PyArrow 16.0.0, Apr 2024).
  Stability for production workloads needs validation.

### 6.3 Dependencies

No new PyPI dependencies for either path. The seekable range reader uses
`azure-storage-blob` (transitively via `azure-storage-file-datalake` in the
`azure` extra). The `AzurePyArrowBackend` would additionally use
`pyarrow.fs.AzureFileSystem` (ships with `pyarrow`).

A combined extra would be convenient for the Tier 1 path:
```toml
azure-pyarrow = ["azure-storage-file-datalake>=12.16.0", "azure-identity>=1.0.0", "pyarrow>=16.0.0"]
```

---

## 7. Recommendation

### 7.1 Phasing

**Phase 1: Seekable range reader + PoC** (moderate effort, high value)
- Add `_AzureRangeReader` with dual-mode integration (~150–200 LOC):
  `read()` keeps chunked streaming for sequential callers; a separate
  seekable path exposes range reads for the PyArrow adapter.
- Build a PoC that reads a multi-column Parquet file from Azure via the
  `StoreFileSystemHandler` and measures: bytes transferred, time, memory.
- Compare against current Tier 2 (full materialization) baseline.
- Expected result: ~10–17x less data transfer for selective column reads.

**Phase 2: Benchmark and decide** (data-driven gate)
- Run the PoC against real workloads: Parquet column pruning, dataset scans,
  Dagster medallion pipeline.
- Measure whether `PythonFile` GIL overhead or missing I/O coalescing is a
  practical bottleneck.
- **If Phase 1 is sufficient:** ship it, close ID-102. The seekable range
  reader gives Azure users best-in-class column pruning with zero new
  complexity.
- **If not:** proceed to Phase 3.

**Phase 3: Spike `pyarrow.fs.AzureFileSystem`** (only if Phase 2 shows need)
- Test auth methods, HNS/non-HNS, `ReadRangeCache` activation.
- Benchmark against Phase 1 range reader for throughput delta.
- **If viable:** proceed to Phase 4. **If not:** the seekable range reader
  from Phase 1 is the final answer — document the ceiling.

**Phase 4: `AzurePyArrowBackend`** (only if Phase 3 succeeds)
- Build the hybrid backend following the `S3PyArrowBackend` pattern.
- Spec, tests, Dagster integration, docs, example.

### 7.2 Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| `download_blob(offset=, length=)` per range is too slow (HTTP overhead per call) | Medium | PoC will measure this directly in Phase 1 |
| `PythonFile` GIL overhead limits concurrency | Low for typical use | Phase 2 benchmarks; only proceed to Tier 1 if measured |
| `AzureFileSystem` auth gaps block Tier 1 | Medium | Phase 1 delivers value regardless; Tier 1 is optional |
| Non-HNS accounts get no listing benefit | Low (HNS standard for analytics) | Column pruning works on any account type |

### 7.3 What This Gives Azure Users

For analytical workloads (Parquet, PyArrow datasets, Dagster):

| Capability | Before | After Phase 1 | After Phase 4 (if needed) |
|-----------|--------|--------------|--------------------------|
| Column pruning | No (full file download) | Yes (range reads via `PythonFile`) | Yes (range reads via C++) |
| I/O coalescing | No | No | Yes (`ReadRangeCache`) |
| Large file handling | Tier 2 fallback with warning | Tier 3 streaming | Tier 1 native |
| New dependencies | — | None | None (ships with PyArrow) |
| Code complexity | — | ~150–200 LOC (dual-mode reader) | New backend class (~300–500 LOC) |

Backlog item: **ID-102**.

---

## 8. References

- Spec 014: PyArrow FileSystem Adapter (`sdd/specs/014-pyarrow-filesystem-adapter.md`)
- Spec 011: S3-PyArrow Hybrid Backend (`sdd/specs/011-s3-pyarrow-backend.md`)
- Spec 012: Azure Backend (`sdd/specs/012-azure-backend.md`)
- RFC-0001: Azure Backend via Direct ADLS Gen2 SDK (`sdd/rfcs/rfc-0001-azure-backend.md`)
- PR #259: ID-100 Seekable read capability + extension
- pyarrowfs-adlgen2: github.com/kaaveland/pyarrowfs-adlgen2 (v0.2.5)
- adlfs: github.com/fsspec/adlfs
- obstore: github.com/developmentseed/obstore
- PARQUET-1820: pre_buffer / read coalescing for Parquet (github.com/apache/arrow/pull/6744)
- ARROW-8562: I/O coalescing parameterization (github.com/apache/arrow/pull/7022)
- Azure SDK: `download_blob(offset=, length=)` range request support
- PyArrow AzureFileSystem: arrow.apache.org/docs/python/generated/pyarrow.fs.AzureFileSystem.html
- PyArrow NativeFile: arrow.apache.org/docs/python/generated/pyarrow.NativeFile.html
