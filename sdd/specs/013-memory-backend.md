# Memory Backend Specification

## Overview

`MemoryBackend` implements the `Backend` ABC using an in-process tree-indexed
data structure. Zero runtime dependencies, no filesystem access, no network.
Built-in (no optional extra).

**Primary use cases:** unit testing (no temp-dir setup/teardown, no OS-error
variability), interactive exploration, documentation examples, CI speed,
and large-scale in-process data structures on high-memory machines.

**Dependencies:** None (stdlib only).
**Optional extra:** None — always available.

---

## Data Structure

### MEM-DS-001: Why Not a Flat Dict

A `dict[str, bytes]` is the obvious starting point. It is wrong at scale.

| Operation | `dict[str, bytes]` | Tree-indexed |
|---|---|---|
| `read` / `read_bytes` | **O(1)** hash lookup | O(d) traversal, d = path depth |
| `write` | **O(1)** hash insert | O(d) traversal + insert |
| `exists` / `is_file` | **O(1)** | O(d) |
| `is_folder` | **O(n)** prefix scan | **O(d)** node lookup |
| `list_files(recursive=False)` | **O(n)** full scan, filter prefix | **O(k)** iterate children |
| `list_files(recursive=True)` | **O(n)** full scan | **O(subtree)** DFS |
| `list_folders` | **O(n)** full scan, deduplicate | **O(k)** iterate children |
| `get_folder_info` | **O(n)** scan + aggregate | **O(subtree)** DFS |
| `delete_folder(recursive=True)` | **O(n)** scan + delete each | **O(subtree)** walk + detach |

Where **n** = total files in the backend, **k** = direct children of the target
folder, **d** = depth of the path (typically 3–8, effectively constant).

For a backend holding 10M files, `list_files("data/images/", recursive=False)`
visits 10M keys with a flat dict. With a tree, it visits only the children of
that one directory node. The flat dict has a single O(1) advantage on point
lookups that evaporates the moment any hierarchical query is needed.

**Decision:** Tree-indexed storage with path-segment nodes.

### MEM-DS-002: Tree Structure

```
_root (_DirNode)
├── "data" (_DirNode)
│   ├── "images" (_DirNode)
│   │   ├── "cat.jpg" (_FileEntry: 2.1 MB)
│   │   └── "dog.jpg" (_FileEntry: 1.8 MB)
│   └── "config.yaml" (_FileEntry: 412 B)
└── "logs" (_DirNode)
    └── "2024" (_DirNode)
        └── "app.log" (_FileEntry: 50 KB)
```

Each internal **`_DirNode`** holds a `dict[str, _DirNode | _FileEntry]` mapping
segment names to children. Each leaf **`_FileEntry`** stores the file's content
and metadata.

Internal types (not public API):

```python
@dataclass(slots=True)
class _FileEntry:
    data: bytearray
    modified_at: datetime
    content_type: str | None = None

@dataclass(slots=True)
class _DirNode:
    children: dict[str, _DirNode | _FileEntry] = field(default_factory=dict)
```

`_DirNode` uses `field(default_factory=dict)` so that `_DirNode()` can be
called without arguments — this is the common case when creating intermediate
directories during `write()`, `move()`, and `copy()`.

### MEM-DS-003: Why `bytearray` Over `bytes`

`bytes` is immutable. Every overwrite creates a new object and the old one
becomes garbage. For large files written repeatedly (e.g. test fixtures that
reset state), this creates GC pressure proportional to file size × write count.

`bytearray` allows in-place mutation. Overwriting a 100 MB file reuses the
buffer allocation (via slice assignment or `clear()` + `extend()`) when the new
content fits within the existing capacity. CPython's `bytearray` uses a
geometric growth strategy, so repeated writes of similar-sized content amortize
to O(1) allocation cost.

`read_bytes()` returns `bytes(entry.data)` — a copy. Callers never hold a
mutable reference to the backend's buffer.

**Trade-off:** `bytearray` uses ~12.5% more memory than `bytes` for the same
content (overallocation headroom). Acceptable for an in-memory backend whose
entire dataset fits in RAM by definition.

**Shrink behavior:** Slice assignment (`entry.data[:] = new_content`) does not
shrink the underlying buffer when the new content is smaller. A file written
with 100 MB and then overwritten with 1 KB retains a ~100 MB allocation.
This is deliberate: the amortized-reuse benefit outweighs the temporary waste
in the typical pattern (repeated writes of similar size). If peak memory is a
concern, callers can `delete()` + `write()` instead of overwriting — this
creates a fresh `bytearray` sized to the new content.

### MEM-DS-004: `slots=True`

Both internal dataclasses use `slots=True`. Per-instance memory drops from
~168 bytes (dict-backed) to ~56 bytes (slot-backed). At 10M file entries,
this saves ~1 GB of pure object overhead.

### MEM-DS-005: Path Traversal

All operations share a single traversal primitive:

```python
def _traverse(self, path: str) -> _DirNode | _FileEntry | None:
    """Walk the tree by splitting path on '/' and following children dicts.
    Returns None if any segment is missing."""
```

This is O(d) dict lookups where d = path depth. Each lookup is an O(1) hash
operation on a short string (single path segment, not the full path).

**Path validation:** When `MemoryBackend` is used directly (without `Store`),
the backend validates paths before traversal. When used via `Store`, the
`RemotePath` constructor handles normalization upstream — but the backend must
not rely on this since direct use is a supported pattern.

Validation rules (applied by splitting on `'/'` and inspecting segments):

| Input | Behavior |
|---|---|
| `""` (empty string) | Valid for folder operations (resolves to root `_DirNode`). Rejected by file-targeted operations per existing `Store` convention. |
| `"/"` or absolute paths | Raise `InvalidPath`. Paths are always relative. |
| `"a/b/"` (trailing slash) | Trailing slash is stripped (normalize to `"a/b"`). |
| `"a//b"` (double slash) | Empty segments are skipped (normalize to `"a/b"`). |
| `"a/./b"` (dot segment) | `"."` segments are skipped (normalize to `"a/b"`). |
| `"a/../b"` (`..` segment) | Raise `InvalidPath`. Escape attempt. |
| `"a/b\x00c"` (null byte) | Raise `InvalidPath`. Unsafe character. |

This mirrors `LocalBackend._resolve()` semantics and `RemotePath` normalization
rules. The validation is a simple segment check — no filesystem interaction.

### MEM-DS-006: Folder Semantics

Folders are **explicit tree nodes**, not virtual prefixes. This matches
`LocalBackend` semantics:

- `write("a/b/c.txt", data)` creates `_DirNode` entries for `"a"` and `"a/b"`
  and a `_FileEntry` for `"c.txt"` under `"a/b"`.
- Deleting the last file in a directory does **not** auto-prune the parent
  `_DirNode`. The empty folder persists until explicitly removed via
  `delete_folder()`.
- `is_folder("a/b")` returns `True` if the `_DirNode` exists, regardless of
  whether it has children.
- `delete_folder("a/b", recursive=False)` on a non-empty folder raises
  `DirectoryNotEmpty`.

**Rationale:** This passes the full conformance suite without skips. Virtual
(prefix-based) semantics would require conformance test skips for empty-folder
operations, same as S3/Azure — defeating the purpose of a reference backend.

---

## Construction

### MEM-001: Constructor

**Signature:**
```python
MemoryBackend()
```

**Invariant:** No required parameters. The backend starts empty.
**Postconditions:** An empty root `_DirNode` is created. `_file_count = 0`,
`_folder_count = 0`. The root node is **not** counted in `_folder_count` — it
is an implicit container, not a user-created folder. A fresh
`MemoryBackend()` has `repr` `MemoryBackend(files=0, folders=0)`. No I/O, no
side effects.

### MEM-002: Backend Name

**Invariant:** `name` property returns `"memory"`.

### MEM-003: Capability Declaration

**Invariant:** `MemoryBackend` declares capabilities: `READ`, `WRITE`,
`DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`. Does not declare `GLOB` (use `ext.glob` for client-side pattern matching).

**Rationale:**
- `ATOMIC_WRITE`: In-memory writes are inherently atomic from the caller's
  perspective. `write_atomic()` behaves identically to `write()`.
- All other capabilities are naturally supported by the tree structure.

### MEM-004: Repr

**Invariant:** `repr(backend)` returns a string of the form:
```
MemoryBackend(files=42, folders=7)
```
No secrets to mask.

**Implementation:** The backend maintains two running counters (`_file_count`,
`_folder_count`) incremented/decremented on mutations. `__repr__` reads these
in O(1) — no tree traversal. This avoids O(n) surprise on large trees (e.g.
debugger tooltip triggering `repr` on a 10M-file backend).

### MEM-005: Registration

**Invariant:** The `"memory"` backend type is registered in
`_register_builtin_backends()` unconditionally (no optional dependency gate).

---

## Operations

All operations follow the `Backend` ABC contract (spec 003). This section
documents memory-specific behavior only.

### MEM-010: read() — Stream Type

**Invariant:** `read(path)` returns a `BinaryIO` that is **not** `io.BytesIO`.

**Implementation:**
```python
def read(self, path: str) -> BinaryIO:
    with self._lock:
        entry = ...  # traverse to _FileEntry, raise NotFound if missing
        snapshot = bytes(entry.data)  # immutable copy under lock
    return io.BufferedReader(io.BytesIO(snapshot))
```
The `bytes()` copy is taken under the lock so that a concurrent `write()` cannot
mutate the `bytearray` while the snapshot is being created. The lock is released
before the `BufferedReader` wrapper is returned — the caller reads from an
immutable copy without holding the lock. The returned stream is seekable and
closable.

**Contract note:** `io.BufferedReader` officially wraps `io.RawIOBase`, and
`io.BytesIO` extends `io.BufferedIOBase`, not `RawIOBase`. However, CPython
(and all known implementations) accepts `BytesIO` as a `BufferedReader`
argument because `BytesIO` implements the required `readinto()` / `read()`
protocol. This works on CPython 3.10–3.14 and PyPy. If a future runtime
rejects this, the fallback is a thin `io.RawIOBase` subclass that delegates
`readinto()` to a `memoryview` over the content bytes — trivial to implement.

**Rationale:** The conformance test `test_read_returns_true_stream_not_bytesio`
exists because `BytesIO` is a sign that a backend loaded everything into memory
instead of streaming. For a memory backend that distinction is moot — the data
*is* memory — but the wrapping is trivial and maintains conformance.

### MEM-011: read_bytes() — Copy Semantics

**Invariant:** `read_bytes(path)` returns `bytes(entry.data)`.

The caller receives an immutable copy. Mutations to the returned bytes cannot
corrupt the backend's state. This is a deliberate safety boundary.

### MEM-012: write() — Full Operation

**Preconditions:** Path must pass validation (MEM-DS-005). If the path resolves
to an existing `_FileEntry` and `overwrite=False`, raise `AlreadyExists`.

**Behavior:**
1. Validate path.
2. Traverse the tree, creating intermediate `_DirNode` entries for any missing
   path segments (same as BE-009). Each new `_DirNode` uses
   `_DirNode(children={})` and increments `_folder_count`.
3. If the leaf already exists as a `_FileEntry`:
   - If `overwrite=False`: raise `AlreadyExists`.
   - If `overwrite=True`: update content in-place via slice assignment.
4. If the leaf does not exist: create a new `_FileEntry`, insert into parent's
   `children`, and increment `_file_count`.
5. Set `modified_at` to `datetime.now(timezone.utc)`.

**Content handling:**
```python
if isinstance(content, bytes):
    entry.data[:] = content      # in-place slice assignment
else:
    entry.data[:] = content.read()  # BinaryIO: read from current position
```

### MEM-013: write_atomic() — Identical to write()

**Invariant:** `write_atomic()` has the same behavior as `write()`.

In-memory operations are inherently atomic — no temp file, no rename, no
partial-write window. Implementing a fake temp-file dance would add complexity
and slow down writes for no correctness benefit.

### MEM-014: delete_folder() — Subtree Removal

**Invariant:** `delete_folder(path, recursive=True)` walks the subtree to
count files and folders being removed, decrements `_file_count` and
`_folder_count` accordingly, then detaches the `_DirNode` from its parent's
`children` dict. Descendants become unreachable and are collected by GC.

This is O(subtree) — the walk is required to maintain the running counters
(MEM-004). The alternative (O(1) detach + lazy counter recomputation) was
rejected because it makes `__repr__` either O(n) or stale, and the subtree
walk is pure dict iteration without I/O.

`delete_folder(path, recursive=False)` is O(d): traverse to the node, verify
it has no children (else `DirectoryNotEmpty`), remove from parent, decrement
`_folder_count` by 1.

### MEM-015: get_folder_info() — Subtree Walk

**Invariant:** `get_folder_info(path)` traverses the subtree rooted at the
target node, aggregating `file_count`, `total_size`, and `modified_at`.

**Aggregation semantics:**
- `file_count`: Total `_FileEntry` nodes in the subtree.
- `total_size`: Sum of `len(entry.data)` across all files.
- `modified_at`: `max(entry.modified_at)` across all files, or `None` if the
  folder contains no files. This matches `LocalBackend` which uses
  `max(st_mtime)` across `rglob("*")` results.

This is O(subtree) — same as `LocalBackend`, but without I/O. For very large
directories, this is CPU-bound on dict iteration, not I/O-bound.

### MEM-016: move() — Detach and Reattach

**Preconditions:** `src` must resolve to an existing `_FileEntry` (else
`NotFound`). If `dst` resolves to an existing `_FileEntry` and
`overwrite=False`, raise `AlreadyExists`.

**Behavior:** Detach the `_FileEntry` from the source parent's `children` dict
and insert it into the destination parent. Intermediate `_DirNode` entries for
`dst` are created as needed (same as `write()`, per BE-009). The `data` buffer
is not copied — the same `bytearray` is reattached. `modified_at` is preserved
from the source. `_file_count` is unchanged (no net add/remove).
`_folder_count` increments for any new intermediate directories created for
`dst`; the source parent directory is **not** auto-pruned even if now empty
(consistent with MEM-DS-006).

This is O(d_src + d_dst) — two tree traversals. File content is not touched.

### MEM-016b: copy() — Deep Copy Content

**Preconditions:** `src` must resolve to an existing `_FileEntry` (else
`NotFound`). If `dst` resolves to an existing `_FileEntry` and
`overwrite=False`, raise `AlreadyExists`.

**Behavior:** Traverse to the source `_FileEntry`, create a new `_FileEntry`
with `bytearray(entry.data)` (deep copy of content buffer), and insert it into
the destination parent. Intermediate `_DirNode` entries for `dst` are created
as needed (per BE-009). `modified_at` is set to `datetime.now(timezone.utc)`
(it is a new file, not a preservation of the source timestamp). `content_type`
is copied from the source. `_file_count` increments by 1. `_folder_count`
increments for any new intermediate directories.

This is O(d_src + d_dst + content) — two tree traversals plus a buffer copy.
Unlike `move()`, the source entry is unchanged.

### MEM-017: to_key() — Identity

**Invariant:** `to_key(path)` returns `path` unchanged. The memory backend has
no native root prefix to strip.

### MEM-018: close() — No-op

**Invariant:** `close()` is a no-op. There are no resources to release. The
tree is garbage-collected when the backend object is collected.

### MEM-019: unwrap() — Default

**Invariant:** `unwrap()` raises `CapabilityNotSupported`. There is no native
handle to expose.

---

## Thread Safety

### MEM-025: Single-Lock Serialization

**Invariant:** All mutating operations (`write`, `write_atomic`, `delete`,
`delete_folder`, `move`, `copy`) acquire a single `threading.Lock` before
modifying the tree. Read operations (`read`, `read_bytes`, `exists`, `is_file`,
`is_folder`, `list_files`, `list_folders`, `get_file_info`, `get_folder_info`)
also acquire the lock for the duration of their tree traversal.

**Rationale:** `Store` is documented as "safe to share across threads" (DESIGN
§3.1). A single coarse lock is the simplest correct approach. Fine-grained
per-node locking would improve concurrent throughput on disjoint subtrees but
adds substantial complexity for a backend whose primary use case is testing —
where contention is rare.

**Postconditions:** The lock is never held during caller consumption of returned
data. Specifically:

- `read()` snapshots `bytes(entry.data)` under the lock, wraps in
  `BufferedReader`, releases the lock, then returns the wrapper. The caller
  reads from the wrapper without holding the lock.
- `list_files()` and `list_folders()` **eagerly collect** all results into a
  list under the lock, release it, then return `iter(list)`. This avoids
  holding the lock during caller iteration (which would deadlock if the caller
  calls another backend method mid-iteration, since `threading.Lock` is not
  reentrant). The trade-off is O(k) up-front memory instead of O(1) per yield.

### MEM-026: Atomicity Scope

**Invariant:** Individual operations are atomic with respect to concurrent
threads. There is no multi-operation transaction support — a `read()` followed
by `write()` is not atomic as a pair. This matches all other backends.

---

## Error Mapping

### MEM-020: No Native Exceptions

**Invariant:** `MemoryBackend` raises only `remote_store` error types. There
are no native exceptions to map — no `OSError`, no `botocore`, no `paramiko`.

Error conditions are detected by tree inspection:

| Condition | Error raised |
|---|---|
| Path not found (file or folder) | `NotFound` |
| File exists and `overwrite=False` | `AlreadyExists` |
| Non-empty folder with `recursive=False` | `DirectoryNotEmpty` |
| Invalid path (null byte, `..`, etc.) | `InvalidPath` |

`PermissionDenied` and `BackendUnavailable` are never raised — memory is always
accessible and there are no permission checks.

---

## Testing Impact

### MEM-030: Conformance Suite

**Requirement:** `MemoryBackend` must pass the full 56-test conformance suite
with zero skips.

Unlike S3/Azure (which skip virtual-folder edge cases), the memory backend's
explicit folder semantics match `LocalBackend` behavior exactly. This makes it
the cleanest conformance reference.

### MEM-031: Store Test Fixture Replacement

**Recommendation:** Replace `LocalBackend` + `tempfile.TemporaryDirectory` in
`test_store.py` and coverage-gap Store tests with `MemoryBackend()`. This:

- Eliminates filesystem side effects from Store-level tests.
- Isolates Store logic tests from backend implementation details.
- Reduces test setup/teardown to a constructor call.
- Separates LocalBackend's dedicated integration tests (OS error mapping,
  atomicity, path resolution) from Store logic tests.

### MEM-032: Dedicated LocalBackend Testing

**Recommendation:** Keep all LocalBackend-specific tests (`test_local.py`,
permission-error injection in `test_coverage_gaps.py`) as a dedicated
integration suite. These test filesystem behavior that only LocalBackend needs
to verify.

---

## Performance Characteristics

### MEM-040: Complexity Summary

| Operation | Time | Space |
|---|---|---|
| `read` / `read_bytes` | O(d) | O(content) for copy |
| `write` / `write_atomic` | O(d + content) | Amortized O(1) with `bytearray` reuse |
| `exists` / `is_file` / `is_folder` | O(d) | O(1) |
| `delete` | O(d) | O(1) |
| `delete_folder(recursive=True)` | O(d + subtree) | O(1) after walk |
| `list_files(recursive=False)` | O(d + k) | O(k) eager collect |
| `list_files(recursive=True)` | O(d + subtree) | O(subtree) eager collect |
| `list_folders` | O(d + k) | O(k) eager collect |
| `get_file_info` | O(d) | O(1) |
| `get_folder_info` | O(d + subtree) | O(1) |
| `move` | O(d_src + d_dst) | O(1) — no data copy |
| `copy` | O(d_src + d_dst + content) | O(content) |

Where: **d** = path depth (typically 3–8), **k** = direct children count,
**subtree** = total descendants, **content** = file size in bytes.

### MEM-041: Memory Overhead Per Entry

| Component | Bytes (CPython 3.12, 64-bit) |
|---|---|
| `_FileEntry` (slots, no data) | ~56 |
| `_DirNode` (slots, empty children dict) | ~120 |
| `bytearray` overhead (empty) | ~57 |
| `str` key per segment (avg 10 chars) | ~75 |
| **Total per file (excl. content)** | **~190** |
| **Total per directory** | **~195** |

At 10M files + 1M directories: ~2.1 GB structural overhead (excluding file
content). A flat `dict[str, bytes]` at 10M entries would use ~1.5 GB structural
overhead but pay O(n) on every listing query — a poor trade.

### MEM-042: Scaling Envelope

Intended to work well within these ranges:

| Dimension | Comfortable | Tested |
|---|---|---|
| File count | 10M+ | Conformance + stress |
| Directory count | 1M+ | Conformance + stress |
| Single file size | 1 GB+ | Limited by RAM |
| Tree depth | 100+ | Conformance |
| Total data size | Limited by machine RAM | - |

Beyond these ranges, consider a real backend. The memory backend is not a
database.
