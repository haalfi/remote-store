# Memory Backend Specification

## Overview

`MemoryBackend` implements the `Backend` ABC using an in-process tree-indexed
data structure. Zero runtime dependencies, no filesystem access, no network.
Built-in (no optional extra). `open_atomic` holds its temporary in memory too,
through the driver's `open_write` (SAW-012).

`MemoryBackend` is a class on the contract kernel
([003 § Contract kernel](003-backend-adapter-contract.md#contract-kernel)):
`class MemoryBackend(DriverBackend)`, whose zero-argument constructor builds a
`MemoryDriver`. `AsyncMemoryBackend(AsyncDriverBackend)` builds an
`AsyncMemoryDriver` the same way. Both drivers hold a `MemoryTree`
(`remote_store/backends/_memory_tree.py`), the tree this spec describes, and
call the same primitives on it. They differ in their lock (`threading.Lock`,
`asyncio.Lock`), their stream shape, their `name` (MEM-002) and their
capabilities (MEM-003, `LAZY_READ`). The clauses below state Memory's
behaviour once for both classes, except where a clause names one.

**Placement.** Each clause is discharged by the kernel, by the driver, or
forwarded through the public class; IDs and prose are kept. The table places
each `### MEM-` heading once, except MEM-DS-005 and MEM-014, which split, so
31 headings give 33 placements (headings counted by
`rg -n '^### MEM-' sdd/specs/013-memory-backend.md`).

| Owner | Clauses |
|---|---|
| kernel (5) | MEM-DS-005's validation table (BE-030: the driver receives a canonical key), MEM-014's `recursive` dispatch (BE-031: `remove_folder` or `delete_tree`, the root refused first), MEM-013 (`write_atomic` is `put`, from `put_is_atomic = True`; AW-001), MEM-018 (`close`, through `close_is_terminal = False`; BE-020), MEM-020 (the choke point; the tree raises only typed errors, the kernel refusing non-mapping metadata before it, and the kernel converts or refuses content `put` could not read and marks what the content raises as `put` reads it, so nothing the caller's content raises reaches `classify`) |
| driver (15) | MEM-DS-001, MEM-DS-002, MEM-DS-003, MEM-DS-004, MEM-DS-005's traversal (`MemoryTree.traverse`, O(d) over a canonical key), MEM-DS-006, MEM-010, MEM-011, MEM-012, MEM-014's two primitives (`delete_tree` for the recursive case, `remove_folder` for the other, each under the one lock), MEM-015 (`folder_stats`, one walk under the one lock), MEM-016 (`move`, one lock), MEM-016b (`copy`), MEM-025 (each `list_page` one locked collect with no cursor, and the kernel lists a recursive call as one `delimiter=None` request, so a listing stays one snapshot), MEM-026 |
| forwarded or declared (7) | MEM-001 (constructor), MEM-002 (`name`, the driver's), MEM-003 (capabilities, the class's `CAPABILITIES` handed to the driver), MEM-004 (`repr` on the public class, reading the driver's counters), MEM-005 (registration), MEM-017 (`to_key`), MEM-019 (`unwrap`) |
| unchanged (6) | MEM-030, MEM-031, MEM-032 (testing), MEM-040, MEM-041, MEM-042 (performance) |

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

```text
root (DirNode)
├── "data" (DirNode)
│   ├── "images" (DirNode)
│   │   ├── "cat.jpg" (FileEntry: 2.1 MB)
│   │   └── "dog.jpg" (FileEntry: 1.8 MB)
│   └── "config.yaml" (FileEntry: 412 B)
└── "logs" (DirNode)
    └── "2024" (DirNode)
        └── "app.log" (FileEntry: 50 KB)
```

Each internal **`DirNode`** holds a `dict[str, DirNode | FileEntry]` mapping
segment names to children. Each leaf **`FileEntry`** stores the file's content
and metadata.

Internal types (not public API), in `remote_store/backends/_memory_tree.py`,
where `MemoryTree` holds the `root` node and the two counters:

```python
@dataclass(slots=True)
class FileEntry:
    data: bytearray
    modified_at: datetime
    content_type: str | None = None
    metadata: dict[str, str] | None = None

@dataclass(slots=True)
class DirNode:
    children: dict[str, DirNode | FileEntry] = field(default_factory=dict)
```

`DirNode` uses `field(default_factory=dict)` so that `DirNode()` can be
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

All operations share a single traversal primitive, the driver's:

```python
def traverse(self, key: str) -> DirNode | FileEntry | None:  # MemoryTree
    """The node at *key*, or None when absent or under a file. O(d)."""
```

This is O(d) dict lookups where d = path depth. Each lookup is an O(1) hash
operation on a short string (single path segment, not the full path). The key
it receives is canonical, so the split is a plain split on `'/'`, with `""`
the root.

**Path validation:** When `MemoryBackend` is used directly (without `Store`),
the backend validates paths before traversal. When used via `Store`, the
`RemotePath` constructor handles normalization upstream — but the backend must
not rely on this since direct use is a supported pattern. On the kernel the
validation is the kernel's, by
[BE-030](003-backend-adapter-contract.md#be-030-key-rule-on-the-kernel)'s key
rule, ahead of every driver call; every row below is that rule's answer.

Validation rules (applied by splitting on `'/'` and inspecting segments):

| Input | Behavior |
|---|---|
| `""` (empty string) | Valid for folder operations (resolves to root `DirNode`), except `delete_folder`, which raises `InvalidPath` ("Cannot delete the store root", BE-031). Rejected by file-targeted operations per existing `Store` convention. |
| `"/"` or absolute paths | Raise `InvalidPath`. Paths are always relative. |
| `"a/b/"` (trailing slash) | Trailing slash is stripped (normalize to `"a/b"`). |
| `"a//b"` (double slash) | Empty segments are skipped (normalize to `"a/b"`). |
| `"a/./b"` (dot segment) | `"."` segments are skipped (normalize to `"a/b"`). |
| `"a/../b"` (`..` segment) | Raise `InvalidPath`. Escape attempt. |
| `"a/b\x00c"` (null byte) | Raise `InvalidPath`. Unsafe character. |
| `"a\\b"`, `"\\"` (backslash) | Raise `InvalidPath`, on every operation, and store nothing. |

This table is BE-030's rule as Memory meets it. It is neither `RemotePath`
normalization nor `LocalBackend._resolve()`; the rows where those differ are
recorded in [BK-389's dossier](../backlog/bk-389-kernel-step-1-memory.md),
decision 6. The validation is a simple segment check — no filesystem
interaction. The non-canonical rows reach addressing too: `native_path` of
`"a//b"`, `"a/./b"` or `"a/"` is the canonical key, and of `"./"` is `""`
(BE-025).

### MEM-DS-006: Folder Semantics

Folders are **explicit tree nodes**, not virtual prefixes. This matches
`LocalBackend` semantics:

- `write("a/b/c.txt", data)` creates `DirNode` entries for `"a"` and `"a/b"`
  and a `FileEntry` for `"c.txt"` under `"a/b"`.
- Deleting the last file in a directory does **not** auto-prune the parent
  `DirNode`. The empty folder persists until explicitly removed via
  `delete_folder()`.
- `is_folder("a/b")` returns `True` if the `DirNode` exists, regardless of
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
**Postconditions:** An empty root `DirNode` is created. `file_count = 0`,
`folder_count = 0`. The root node is **not** counted in `folder_count` — it
is an implicit container, not a user-created folder. A fresh
`MemoryBackend()` has `repr` `MemoryBackend(files=0, folders=0)`. No I/O, no
side effects.

### MEM-002: Backend Name

**Invariant:** `name` property returns `"memory"`. It is the driver's `name`,
forwarded by the kernel; `AsyncMemoryBackend`'s is `"async-memory"`.

### MEM-003: Capability Declaration

**Invariant:** `MemoryBackend` declares every capability except `GLOB` and
`LAZY_READ` (`set(Capability) - {GLOB, LAZY_READ}`, `_ALL_CAPABILITIES` in
`backends/_memory.py`); `AsyncMemoryBackend` every capability except `GLOB`,
its one-chunk read stream being lazy. Neither declares `GLOB` (use
`list_files(pattern=…)` or `ext.glob` for client-side pattern matching). The
declared set is the class's `CAPABILITIES`, which the constructor hands to the
driver: a subclass narrowing it narrows what the store allows, and one
declaring a `COPY`, `MOVE`, `ATOMIC_MOVE`, `ATOMIC_WRITE` or `GLOB` the driver
cannot back is refused with `ValueError` at construction. The other
capabilities are taken as declared, and a `capabilities` property override
never reaches construction. Pinned by `TestMemoryCapabilityOverride` in
`tests/backends/memory/test_coverage.py`.

**Rationale:**
- `ATOMIC_WRITE`: In-memory writes are inherently atomic from the caller's
  perspective. `write_atomic()` behaves identically to `write()`.
- All other capabilities are naturally supported by the tree structure.

### MEM-004: Repr

**Invariant:** `repr(backend)` returns a string of the form:
```text
MemoryBackend(files=42, folders=7)
```
No secrets to mask.

**Implementation:** The driver's `MemoryTree` maintains two running counters
(`file_count`, `folder_count`) incremented/decremented on mutations. The public
class's `__repr__` reads these through the driver's `counts` in O(1) — no tree
traversal — and without the driver's lock, which is not reentrant, so `repr`
from a thread paused inside a locked step does not deadlock (pinned by
`test_repr_does_not_wait_for_the_lock`). `AsyncMemoryBackend`'s `repr` has the same form under its own name. This avoids O(n) surprise on large trees (e.g.
debugger tooltip triggering `repr` on a 10M-file backend).

### MEM-005: Registration

**Invariant:** The `"memory"` backend type is registered in
`_register_builtin_backends()` unconditionally (no optional dependency gate).

---

## Operations

All operations follow the `Backend` ABC contract (spec 003). This section
documents memory-specific behavior only.

### MEM-010: read() — Stream Type

**Invariant:** `read(path)` returns a `BinaryIO` that is a seekable, closable
stream over an `io.BytesIO` wrapping an independent copy of the file content.

**Implementation:** the driver's `get`:
```python
def get(self, key: str) -> BinaryIO:
    with self._lock:
        data = bytes(self._tree.file(key).data)  # copy happens inside the lock
    return io.BytesIO(data)
```
`bytes(node.data)` copies the buffer before the lock is released. The returned
`BytesIO` therefore holds an independent snapshot: a concurrent `write()` that
mutates the `bytearray` after the lock releases cannot affect the caller's
copy. The lock is held only for the traversal and the copy; the caller reads
from the returned stream without holding the lock. The kernel's `read` wraps
that `BytesIO` in its error-mapping stream, which delegates seeking to it, so
the caller's stream is seekable but is not a plain `io.BytesIO`.

**Allocation rationale:** the copy is made under the lock, from the
`bytearray`, and the `BytesIO` is built over it after the lock is released.

**Note:** Here the copy is always made, so the stream never exposes a live
internal buffer.

### MEM-011: read_bytes() — Copy Semantics

**Invariant:** `read_bytes(path)` returns `bytes(entry.data)`.

The caller receives an immutable copy. Mutations to the returned bytes cannot
corrupt the backend's state. This is a deliberate safety boundary.

### MEM-012: write() — Full Operation

**Preconditions:** Path must pass validation (MEM-DS-005). If the path resolves
to an existing `FileEntry` and `overwrite=False`, raise `AlreadyExists`.

**Behavior:**
1. Validate path (the kernel's, BE-030; the driver's `put` receives the canonical key).
2. Traverse the tree, creating intermediate `DirNode` entries for any missing
   path segments (same as BE-009). Each new `DirNode` uses
   `DirNode(children={})` and increments `folder_count`.
3. If the leaf already exists as a `FileEntry`:
   - If `overwrite=False`: raise `AlreadyExists`.
   - If `overwrite=True`: update content in-place via slice assignment.
4. If the leaf does not exist: create a new `FileEntry`, insert into parent's
   `children`, and increment `file_count`.
5. Set `modified_at` to `datetime.now(timezone.utc)`.

**Content handling:** the driver's `put` buffers the body before it takes the
lock, then stores it under the lock:
```python
raw = bytearray(content) if isinstance(content, bytes) else _drain(content)
# _drain: BinaryIO read from current position, 64 KiB at a time
with self._lock:
    ...  # an existing entry: entry.data[:] = raw (in-place slice assignment)
```

### MEM-013: write_atomic() — Identical to write()

**Invariant:** `write_atomic()` has the same behavior as `write()`.

In-memory operations are inherently atomic — no temp file, no rename, no
partial-write window. Implementing a fake temp-file dance would add complexity
and slow down writes for no correctness benefit. On the kernel this is the
first of AW-001's routes: the driver declares `put_is_atomic = True`, so the
kernel's `write_atomic` is the driver's `put`.

### MEM-014: delete_folder() — Subtree Removal

**Invariant:** `delete_folder(path, recursive=True)` walks the subtree to
count files and folders being removed, decrements `file_count` and
`folder_count` accordingly, then detaches the `DirNode` from its parent's
`children` dict. Descendants become unreachable and are collected by GC.

This is O(subtree) — the walk is required to maintain the running counters
(MEM-004). The alternative (O(1) detach + lazy counter recomputation) was
rejected because it makes `__repr__` either O(n) or stale, and the subtree
walk is pure dict iteration without I/O.

`delete_folder(path, recursive=False)` is O(d): traverse to the node, verify
it has no children (else `DirectoryNotEmpty`), remove from parent, decrement
`folder_count` by 1.

On the kernel the `recursive` dispatch is the kernel's
([BE-031](003-backend-adapter-contract.md#be-031-delete_folder-on-the-kernel)):
the recursive case calls the driver's `delete_tree`, the other its
`remove_folder`, each one locked step over `MemoryTree`. The root is refused
with `InvalidPath` before either is called.

### MEM-015: get_folder_info() — Subtree Walk

**Invariant:** `get_folder_info(path)` traverses the subtree rooted at the
target node, aggregating `file_count`, `total_size`, and `modified_at`.

**Aggregation semantics:**
- `file_count`: Total `FileEntry` nodes in the subtree.
- `total_size`: Sum of `len(entry.data)` across all files.
- `modified_at`: `max(entry.modified_at)` across all files, or `None` if the
  folder contains no files. This matches `LocalBackend` which uses
  `max(st_mtime)` across `rglob("*")` results.

This is O(subtree) — same as `LocalBackend`, but without I/O. For very large
directories, this is CPU-bound on dict iteration, not I/O-bound.

### MEM-016: move() — Detach and Reattach

**Preconditions:** `src` must resolve to an existing `FileEntry` (else
`NotFound`). If `dst` resolves to an existing `FileEntry` and
`overwrite=False`, raise `AlreadyExists`.

**Behavior:** Detach the `FileEntry` from the source parent's `children` dict
and insert it into the destination parent. Intermediate `DirNode` entries for
`dst` are created as needed (same as `write()`, per BE-009). The `data` buffer
is not copied — the same `bytearray` is reattached. `modified_at` is preserved
from the source. `file_count` is unchanged (no net add/remove).
`folder_count` increments for any new intermediate directories created for
`dst`; the source parent directory is **not** auto-pruned even if now empty
(consistent with MEM-DS-006).

This is O(d_src + d_dst) — two tree traversals. File content is not touched.

### MEM-016b: copy() — Deep Copy Content

**Preconditions:** `src` must resolve to an existing `FileEntry` (else
`NotFound`). If `dst` resolves to an existing `FileEntry` and
`overwrite=False`, raise `AlreadyExists`.

**Behavior:** Traverse to the source `FileEntry`, create a new `FileEntry`
with `bytearray(entry.data)` (deep copy of content buffer), and insert it into
the destination parent. Intermediate `DirNode` entries for `dst` are created
as needed (per BE-009). `modified_at` is set to `datetime.now(timezone.utc)`
(it is a new file, not a preservation of the source timestamp). `content_type`
is copied from the source. `file_count` increments by 1. `folder_count`
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
also acquire the lock for the duration of their tree traversal. The lock is the
driver's, one per `MemoryDriver` instance, taken by each driver primitive for
one step over `MemoryTree`, which takes no lock itself; `AsyncMemoryDriver`
holds one `asyncio.Lock` the same way.

**Rationale:** `Store` is documented as "safe to share across threads" (DESIGN
§3.1). A single coarse lock is the simplest correct approach. Fine-grained
per-node locking would improve concurrent throughput on disjoint subtrees but
adds substantial complexity for a backend whose primary use case is testing —
where contention is rare.

**Postconditions:** The lock is never held during caller consumption of returned
data. Specifically:

- `read()` copies the buffer with `bytes(node.data)` under the lock, then
  releases the lock and returns a `BytesIO` over the copy (MEM-010). The caller
  reads from an independent copy without holding the lock.
- `list_files()` and `list_folders()` **eagerly collect** all results under the
  lock: the driver's `list_page` answers one `Page` with no cursor, and the
  kernel iterates it after the lock is released. This avoids
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

**Invariant:** Every error a `MemoryBackend` operation itself produces is a
`remote_store` error type. There are no native exceptions to map — no
`OSError`, no `botocore`, no `paramiko`. Metadata that is not a mapping never
reaches the tree: the kernel refuses it with `ValueError` first (BE-030). The
streams it hands out are `io`
objects and raise the `io` protocol's own errors where that protocol does: the
write-only file `open_atomic` yields answers `seek()` with
`io.UnsupportedOperation`, `read()` with `NotImplementedError`, a
non-buffer `write()` with `TypeError` and a `write()` of a `memoryview` that is
not C-contiguous with `BufferError`. One native exception reaches the driver
from the caller's content, and it is not the tree's: an error the content
raises passes the choke point verbatim, still the caller's type (ASYNC-091). A `bytearray` or `memoryview` is stored as its bytes, since the
kernel hands the driver a `bytes` copy, and content that is no bytes source is
the kernel's `TypeError` before the tree is touched (BE-030 § Content).
The drivers touch the caller's content only through `read` (sync) and
`async for` (async), and the kernel marks whatever either raises as the
caller's, a buffer that cannot be read as `bytes` and an `__aiter__` that
fails included (`tests/backends/memory/test_buffer_content.py`). So nothing the
caller's content raises reaches `classify`, which stays as the protocol
requires and answers a base `RemoteStoreError`.

Error conditions are detected by tree inspection:

| Condition | Error raised |
|---|---|
| Path not found (file or folder) | `NotFound` |
| File exists and `overwrite=False` | `AlreadyExists` |
| Non-empty folder with `recursive=False` | `DirectoryNotEmpty` |
| Invalid path (null byte, `..`, etc.) | `InvalidPath` |

On the kernel the invalid-path row is the kernel's (BE-030), raised before the
driver is called. The driver raises the other rows already typed and without
`backend`, which the kernel's choke point fills from the driver's `name`
(ERR-001); the kernel's own probes may raise them too (BE-032 A.8). The error messages are the kernel's and the tree's.

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
| `FileEntry` (slots, no data) | ~56 |
| `DirNode` (slots, empty children dict) | ~120 |
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
