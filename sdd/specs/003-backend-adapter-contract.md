# Backend Adapter Contract Specification

## Overview

The `Backend` ABC defines the contract all storage backends must implement. It is the most critical spec in the system — every operation, error condition, and capability is defined here. Backends declare capabilities via a `Capability` enum and `CapabilitySet`.

---

## Capabilities

### CAP-001: Capability Enum Members

**Invariant:** `Capability` is an enum with members: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `ATOMIC_MOVE`, `METADATA`, `GLOB`, `SEEKABLE_READ`, `LAZY_READ`, `WRITE_RESULT_NATIVE`, `USER_METADATA`.
**See also:** [045-write-result.md](045-write-result.md) (WR-009, WR-010) for semantics of the two new members.

### CAP-002: CapabilitySet Construction

**Invariant:** `CapabilitySet` is constructed from a `set[Capability]`.
**Example:**
```python
cs = CapabilitySet({Capability.READ, Capability.WRITE})
```

### CAP-003: supports() Method

**Invariant:** `supports(cap)` returns `True` if `cap` is in the set, `False` otherwise.

### CAP-004: require() Method

**Invariant:** `require(cap)` raises `CapabilityNotSupported` if `cap` is not in the set.
**Raises:** `CapabilityNotSupported` with `capability` attribute set to the capability name.

### CAP-005: Iteration and Membership

**Invariant:** `CapabilitySet` supports `in` operator and `__iter__`.
**Example:**
```python
assert Capability.READ in cs
for cap in cs:
    print(cap)
```

### CAP-006: Immutability

**Invariant:** `CapabilitySet` is immutable after construction. The internal set cannot be modified.

### CAP-007: Quality-Flag Capabilities

**Invariant:** Some capabilities are *quality flags* — they describe a behavioural property of an existing method rather than gating access to a new one. Declaring a quality flag does **not** enable any additional method; omitting it does **not** disable any method.

**Current quality flags:**

- `ATOMIC_MOVE` — `move()` is guaranteed atomic under concurrent access (i.e. any reader observes either the pre-move or the post-move state, never a partial state). Backends that implement move as copy-then-delete do **not** declare this flag. Callers **must not** assume atomicity; they **should** check `Store.supports(Capability.ATOMIC_MOVE)` before relying on atomic rename semantics.
- `SEEKABLE_READ` — `read()` always returns a natively seekable stream (`stream.seekable()` is `True`) with zero overhead. Backends that omit this flag still support `Store.read_seekable()` via an optimized override or spool fallback, but `read()` itself may return a non-seekable stream. The flag describes a property of `read()` rather than gating any additional method.
- `LAZY_READ` — `read()` fetches data lazily on demand from the native source rather than loading the entire file into memory before returning. Backends that pre-load all file contents before returning a stream (e.g. in-memory backends, SQL blob stores) do **not** declare this flag. Callers can use `Store.supports(Capability.LAZY_READ)` to know whether partial reads avoid loading the entire file. This flag describes a property of `read()` rather than gating any additional method.
- `WRITE_RESULT_NATIVE` — `write*()` returns a `WriteResult` with `source == "native"` and each rich field (`etag`, `version_id`, `last_modified`, `digest`) populated from the backend's write response *when that response carries it* — which fields are filled depends on the backend, and a native backend whose write response carries no metadata (SFTP) populates none, leaving only `path`/`size`/`source`. Backends that omit this flag still return a `WriteResult`, but with `source == "basic"` (only `path` and `size` guaranteed). Does **not** gate any method. See [045-write-result.md](045-write-result.md) (WR-004, WR-009).

**Strict-gate capabilities** (raise `CapabilityNotSupported` before I/O when the backend lacks the capability and the caller passes the guarded kwarg):

- `USER_METADATA` — gates the `metadata=` kwarg on `write*()`. Passing `metadata=` to a backend without this capability raises `CapabilityNotSupported` before any I/O. See [045-write-result.md](045-write-result.md) (WR-010) and [ADR-0026](../adrs/0026-strict-gate-on-kwarg.md).

---

## Backend ABC

### BE-001: Abstract Base Class

**Invariant:** `Backend` is an ABC. Subclasses must implement all abstract methods.

### BE-002: Name Property

**Invariant:** `name` property returns a unique identifier string for the backend type (e.g. `"local"`, `"s3"`).

### BE-003: Capabilities

**Invariant:** Every concrete backend class must declare `CAPABILITIES: ClassVar[CapabilitySet]` as a class attribute assigning a non-empty `CapabilitySet`. This enables static capability extraction without instantiation (e.g. `gen_graph.py`). The `capabilities` property returns a `CapabilitySet` declaring all supported operations; for backends with a static capability set it delegates to `self.CAPABILITIES`. For backends that narrow capabilities at runtime (e.g. `SQLBlobBackend` with a narrow-column schema), `CAPABILITIES` is an upper bound and the instance `capabilities` may be a strict subset.

**Conformance invariant:** `set(instance.capabilities) ⊆ set(type(instance).CAPABILITIES)` for all backends. Enforced by `tests/backends/conformance/test_identity.py::TestBackendIdentity::test_capabilities_subset_of_class_var`.

### BE-004: exists()

**Invariant:** `exists(path)` returns `bool`. Returns `False` for missing paths — never raises `NotFound`. Also returns `False` for paths whose ancestors contain a file (file-as-directory-component), where traversal cannot proceed; these are treated as non-existent.

### BE-005: is_file() / is_folder()

**Invariant:** `is_file(path)` returns `True` only if `path` is a file. `is_folder(path)` returns `True` only if `path` is a folder. Both return `False` for non-existent paths and for paths whose ancestors contain a file (file-as-directory-component); in both cases, the path cannot be accessed, so `False` is the semantically correct response.

### BE-006: read()

**Invariant:** `read(path)` returns a `BinaryIO` stream for the file content.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if the path names a directory (type mismatch, not a missing file). See BE-021.
**See also:** [006-streaming-io.md](006-streaming-io.md)

### BE-007: read_bytes()

**Invariant:** `read_bytes(path)` returns the full file content as `bytes`.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if the path names a directory. Same preconditions as BE-006; see BE-021.

### BE-008: write()

**Invariant:** `write(path, content, *, overwrite=False, metadata=None) -> WriteResult` creates or overwrites a file and returns a `WriteResult`.
**Preconditions:** `content` is `bytes` or `BinaryIO`.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`. `InvalidPath` if an ancestor of `path` exists as a regular file (file-as-directory-component — see ID-209). `CapabilityNotSupported` if a non-`None`, non-empty `metadata` mapping is passed and the backend lacks `USER_METADATA` (per WR-010 empty-mapping carve-out — `metadata=None` and `metadata={}` are both no-ops with respect to this gate).
**See also:** [045-write-result.md](045-write-result.md) (WR-001 through WR-005, WR-010 through WR-012).
**Precondition evaluation order:** Backends MUST evaluate preconditions in this
order: (1) path validity — if `path` names an existing *directory* OR any
slash-aligned ancestor of `path` is a regular file (file-as-directory-component,
ID-209), raises `InvalidPath`; (2) overwrite conflict — if the file exists and
`overwrite=False`, raises `AlreadyExists`; (3) I/O. No later check may mask an
earlier one. This order applies to `write()`, `write_atomic()`, `move()`, and
`copy()` wherever analogous preconditions exist.
**Flat-namespace exemption:** Backends where the underlying storage has no
native directory concept (e.g. S3, Azure non-HNS, SQL) are exempt from step
(1): they cannot distinguish "path names a directory" from "path does not
exist", so they MUST skip the type-conflict check entirely. The file-ancestor
rejection added by ID-209 is similarly exempt on flat-namespace backends by
default — they cannot detect a file-ancestor in O(1) without an extra HEAD
round trip per slash-aligned ancestor. ID-211 ships the gate as an opt-in
client kwarg `reject_write_under_file_ancestor: bool = False` on each
flat-namespace backend constructor (`S3Backend`, `S3PyArrowBackend`,
`AzureBackend`, `SQLBlobBackend`, plus the async `AsyncAzureBackend`); when
the opt-in is set the backend walks slash-aligned ancestors, HEADing each
one, and raises `InvalidPath` on the first file ancestor. Paths with no
slash short-circuit (no walk, no extra round trips) so store-root writes
pay nothing. Measurement note:
`sdd/research/research-id-211-flat-ns-file-ancestor-precheck.md` records the
per-call cost vs depth on S3 (moto) and SQLBlob (sqlite); the gate is
linear in depth and the default-off choice keeps that tax off hot paths.
The conformance gate (`test_write_under_file_ancestor_raises_invalid_path`)
keys off the per-fixture `rejects_write_under_file_ancestor` flag rather
than `flat_namespace` — `s3_moto_strict` / `sqlblob_strict` /
`azurite_strict` / `s3_pyarrow_moto_strict` exercise the opt-in path,
while the default fixtures continue to skip the gate. The async sibling
`azurite_async_strict` covers `AsyncAzureBackend` end-to-end (the
non-HNS opt-in path through `_acheck_no_file_ancestor` and the SDK
`get_blob_properties` closure). For default-off flat-NS backends the
effective order is: existence check (non-existent target treated as
writable) → overwrite conflict → I/O.
**Azure HNS caveat.** On Azure HNS accounts the kwarg short-circuits the
walk because `hdi_isfolder` rejects the operation in the native write
path. The backend detects the file ancestor on that native rejection and
re-raises it as `InvalidPath`, so HNS delivers the cross-backend contract
this kwarg promises — with or without the kwarg set. Flat-NS Azure
(non-HNS, e.g. Azurite) and the other flat-NS backends deliver the
contract as described.
The opt-in gate is a **start-of-call** check, not an atomic guarantee: the
ancestor HEADs run once at entry, so a concurrent writer that creates a
file at one of the walked ancestor keys between the walk and the data-plane
operation can still produce the orphan-key shape the gate exists to
prevent. Callers needing atomicity must layer a backend-level lock or CAS
above the gate. The walk is also **fail-open** on transient probe errors
(503, throttling, network blip) — the closure swallows non-NotFound and
returns False so the data path proceeds; this is the documented contract
for all backends, including SQLBlob.
**Formal coverage:** `write()` is modelled in `sdd/formal/BackendContract.dfy`
as `Write` with postconditions covering the precondition evaluation order
(`IsDir → InvalidPath`, `!AllAncestorsTraversable → InvalidPath` (ID-209),
`IsFile ∧ !overwrite → AlreadyExists`), the WR-010
strict gate (`HasUserMetadata(metadata) ∧ CapUserMetadata !in capabilities →
CapabilityNotSupported`, with empty-mapping carve-out encoded by
`HasUserMetadata`), the WR-001a schema (`r.value.path == path ∧ r.value.size
== |content|`), WR-004 (source Native iff `CapWriteResultNative`), WR-005
(Basic source → rich fields None), WR-012 metadata echo, and WR-013
round-trip (`fs[path].info.metadata` reflects what was stored). ID-209
promotes well-formedness to a class invariant `predicate Valid()` on the
`Backend` trait, with `requires Valid() ensures Valid()` on every mutating
method (`Write`, `Delete`, `DeleteFolder`, `Move`, `Copy`); the file-ancestor
clause on Write is what closes the loophole that would let a successful
write break `Valid()`. Move / Copy carry the same file-ancestor clause on
their destination paths. Verified in `MemoryBackend.dfy`. Python backstop:
the WR-001a/004/005/012/013 postcondition chain is exercised against every
backend by `tests/backends/conformance/test_atomic.py::TestWriteResultConformance`;
the file-ancestor rejection is exercised by
`tests/backends/conformance/test_errors.py::TestWriteErrorFidelity::test_write_under_file_ancestor_raises_invalid_path`
(sync) and its async sibling in `test_async_extended.py`. See ID-151,
ID-184, ID-209.

### BE-009: write Creates Intermediate Directories

**Invariant:** `write` creates any intermediate directories automatically.

### BE-010: write_atomic()

**Invariant:** `write_atomic(path, content, *, overwrite=False, metadata=None) -> WriteResult` writes via a temporary file + atomic rename and returns a `WriteResult`.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`. `CapabilityNotSupported` if a non-`None`, non-empty `metadata` mapping is passed and the backend lacks `USER_METADATA` (per WR-010 empty-mapping carve-out).
**Precondition order:** Same as BE-008 — path validity (type conflict) → overwrite conflict → I/O. Flat-namespace exemption from BE-008 applies.
**See also:** [007-atomic-writes.md](007-atomic-writes.md); [045-write-result.md](045-write-result.md) (WR-001, WR-010).
**Formal coverage:** Delegates to BE-008 — at the Backend-contract level
`write_atomic` shares the `Write` postcondition model (return type, precondition
order, WR-010 gate, WR-001a/004/005/012/013 postcondition chain). Atomicity
itself is a frame-condition property outside Dafny's expressiveness (see
`sdd/formal/README.md` § Design decisions, "No error-path frame condition"). No
separate `WriteAtomic` method exists in `BackendContract.dfy`. Python backstop:
the Python conformance suite parametrizes `TestWriteResultConformance` over
both `write` and `write_atomic`, so `write_atomic` carries the same
postcondition-chain coverage as `write`. See ID-151.

### BE-011: write_atomic Capability Gate

**Invariant:** `write_atomic` raises `CapabilityNotSupported` if the backend lacks `ATOMIC_WRITE`.

### BE-012: delete()

**Invariant:** `delete(path, missing_ok=False)` removes a file.
**Raises:** `NotFound` if the file is missing and `missing_ok=False`. `InvalidPath` if `path` names a directory, regardless of `missing_ok` — type errors are not silenced by missing-path tolerance (Dafny: `Delete: IsDir → InvalidPath` unconditionally). See BE-021.
**Postconditions:** If `missing_ok=True`, no error for missing files.

### BE-013: delete_folder()

**Invariant:** `delete_folder(path, recursive=False, missing_ok=False)` removes a folder.
**Raises:** `NotFound` if the path does not exist and `missing_ok=False`. `InvalidPath` if `path` names a file (use `delete` instead). `DirectoryNotEmpty` if the folder is non-empty and `recursive=False`. See BE-021.

### BE-014: list_files()

**Invariant:** `list_files(path, recursive=False)` returns `Iterator[FileInfo]`.
**Postconditions:** Returns only files, not folders. If `recursive=True`, includes files in all subdirectories.
**Missing-path behavior:** If `path` does not exist, does not name a folder,
or has a non-traversable ancestor (i.e. a file appears as a directory component
in the path), the iterator yields nothing. `list_files()` MUST NOT raise
`NotFound` for missing or non-existent paths. This matches the behavior already
guaranteed by BE-026 (`iter_children`) and ensures callers can safely iterate
over potentially absent paths without defensive guards.
**Formal coverage:** `list_files()` is modelled in
`sdd/formal/BackendContract.dfy` as `ListFiles`. The missing-path /
non-traversable-ancestor early-return is pinned by
`!PathExists(fs, path) || !AllAncestorsTraversable(fs, path) ==> r.value == []`;
the completeness postcondition's guard widened symmetrically from
`PathExists(fs, path)` to `PathExists(fs, path) && AllAncestorsTraversable(fs, path)`,
relaxing the implementer obligation in the same malformed-fs slice — both
changes together keep the model satisfiable. ID-209 promoted fs
well-formedness to a class invariant `predicate Valid()` on the `Backend`
trait, so the `!AllAncestorsTraversable` disjunct is now a **logical
consequence** of `Valid()` rather than a defensive postcondition against an
unreachable state: a successful `Write` (or `Move`/`Copy` to a non-existent
destination) that would otherwise insert a `FileEntry` under a file-ancestor
is rejected pre-I/O via the new `!AllAncestorsTraversable(old(fs), path)`
clause on those methods (see BE-008). Verified in `MemoryBackend.dfy`. See
ID-184, ID-209.

### BE-015: list_folders()

**Invariant:** `list_folders(path)` returns `Iterator[FolderEntry]` of immediate subfolders.
Each `FolderEntry` has `.name` (folder name) and `.path` (backend-relative `RemotePath`).
**Missing-path behavior:** If `path` does not exist, does not name a folder,
or has a non-traversable ancestor, the iterator yields nothing. `list_folders()`
MUST NOT raise `NotFound` for missing or non-existent paths.
**Formal coverage:** `list_folders()` is modelled in
`sdd/formal/BackendContract.dfy` as `ListFolders`, with the same
two-sided ancestor-traversability gating as BE-014 above (early-return
disjunct plus completeness conjunction). Under ID-209's `Valid()` class
invariant, the `!AllAncestorsTraversable` disjunct is a logical
consequence rather than a defensive postcondition (see BE-014). Verified
in `MemoryBackend.dfy`. See ID-184, ID-209.

### BE-016: get_file_info()

**Invariant:** `get_file_info(path)` returns `FileInfo`.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if the path names a directory (Dafny: `GetFileInfo: IsDir → InvalidPath`). See BE-021.
**Formal coverage:** `get_file_info()` is modelled in
`sdd/formal/BackendContract.dfy` as `GetFileInfo` with postcondition
`IsFile → r.Ok? ∧ r.value == fs[path].info`. The extended `FileInfo`
datatype carries the optional `digest`, `etag`, `last_modified`, and
`metadata` fields (no `version_id` — only `WriteResult` does in v1), so
the WR-013 round-trip (metadata survives `write → get_file_info`) and
the WR-008 field mapping to `head()`-produced `WriteResult` are
discharged structurally. Verified in `MemoryBackend.dfy`. See ID-151.

### BE-017: get_folder_info()

**Invariant:** `get_folder_info(path)` returns `FolderInfo`.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if the path names a file (wrong type — use `get_file_info` instead). See BE-021.
**Formal coverage:** `get_folder_info()` is modelled in `sdd/formal/BackendContract.dfy` as `GetFolderInfo` with postconditions `IsFile → InvalidPath`, `!PathExists → NotFound`, `IsDir → Ok`, `file_count == |ChildFiles(fs, path)|`, and `total_size == SumSizes(fs, ChildFiles(fs, path))`. Verified in `MemoryBackend.dfy`. Property-based aggregate coverage against the compiled Dafny oracle lives in `tests/test_pbt_folder_info_aggregates.py`. See ID-130, ID-134, ID-187.

### BE-018: move()

**Invariant:** `move(src, dst, overwrite=False)` renames/moves a file.
**Raises:** `NotFound` if `src` does not exist. `InvalidPath` if `src` names a directory, if `dst` names an existing directory (cannot overwrite a directory with a file), or if an ancestor of `dst` exists as a regular file (file-as-directory-component on dst, ID-209 — flat-namespace backends opt in to the dst-side ancestor walk via the `reject_write_under_file_ancestor` kwarg, same shape as BE-008 / ID-211). `AlreadyExists` if `dst` names an existing file, `overwrite=False`, and `src != dst` — self-move on a file is a no-op (Dafny: `Move: src == dst → Ok`); self-move on a directory still raises `InvalidPath` per the precondition ordering in BE-008. See BE-021 and BE-008 for precondition evaluation order.
**Precondition order:** `src`-NotFound takes priority over dst-side preconditions; specifically `move(missing_src, blocked_dst)` MUST raise `NotFound(src)` rather than `InvalidPath(dst)`. `LocalBackend.move` enforces this naturally (the `mkdir_parents` walk that catches the file-ancestor case runs after the src-exists check); flat-namespace backends running the ID-211 opt-in MUST defer the `_check_no_file_ancestor(dst)` walk until after the src-NotFound probe to match. Surfaced by the ID-211 review; pinned to remove the cross-backend ambiguity that existed under BE-018 alone.
**Metadata:** `move()` preserves the source file's user metadata: after a
successful move, `get_file_info(dst)` MUST return the same `metadata`
mapping the source file carried before the move — the WR-013 user-metadata
round-trip, applied to the move path. A backend that rebuilds the
destination `FileInfo` without carrying `metadata` across violates this
invariant.
**Atomicity:** Backends SHOULD implement `move()` atomically where the
underlying storage supports it (e.g. Local via `os.rename`, Memory under lock,
SQL in a transaction). Backends that cannot provide atomicity (e.g. S3 and
Azure non-HNS, which use copy-then-delete) MUST document this in their class
docstring. The caller MUST NOT assume atomicity. On partial failure in a
copy-then-delete implementation, the source file may still exist alongside the
destination; the backend MUST NOT silently swallow the error.
**Formal coverage:** `move()` is modelled in
`sdd/formal/BackendContract.dfy` as `Move`; the success postcondition pins
both `fs[dst].content == old(fs)[src].content` and
`fs[dst].info.metadata == old(fs)[src].info.metadata`, so a refinement that
drops metadata fails to verify. Verified in `MemoryBackend.dfy`. See BK-232.

### BE-019: copy()

**Invariant:** `copy(src, dst, overwrite=False)` duplicates a file.
**Raises:** `NotFound` if `src` does not exist. `InvalidPath` if `src` names a directory, if `dst` names an existing directory, or if an ancestor of `dst` exists as a regular file (file-as-directory-component on dst, ID-209 — flat-namespace backends opt in to the dst-side ancestor walk via the `reject_write_under_file_ancestor` kwarg, same shape as BE-008 / ID-211). `AlreadyExists` if `dst` names an existing file, `overwrite=False`, and `src != dst` — self-copy on a file is a no-op, not an error (Dafny: "Self-copy (src == dst) is a no-op, not AlreadyExists"); self-copy on a directory still raises `InvalidPath` per the precondition ordering in BE-008. See BE-021.
**Precondition order:** Same as BE-018 — `src`-NotFound takes priority over dst-side preconditions, so `copy(missing_src, blocked_dst)` MUST raise `NotFound(src)` rather than `InvalidPath(dst)`.
**Metadata:** `copy()` preserves the source file's user metadata: after a
successful copy, `get_file_info(dst)` MUST return the same `metadata`
mapping as `get_file_info(src)` — the WR-013 user-metadata round-trip,
applied to the copy path. A backend that rebuilds the destination
`FileInfo` without carrying `metadata` across violates this invariant.
**Partial failure:** Unlike `move()`, `copy()` has no delete-after phase, so it
cannot create a duplicate of the source. However, a backend that writes `dst`
incrementally (e.g. multi-part upload) can leave a corrupt or incomplete
destination if the transfer fails mid-way. Backends MUST NOT silently return
success on a failed copy — the caller should assume `dst` is corrupt if an
error is raised mid-operation.
**Formal coverage:** `copy()` is modelled in
`sdd/formal/BackendContract.dfy` as `Copy`; the success postcondition pins
both `fs[dst].content == old(fs)[src].content` and
`fs[dst].info.metadata == old(fs)[src].info.metadata`, so a refinement that
drops metadata fails to verify. Verified in `MemoryBackend.dfy`. See BK-196.

### BE-020: close()

**Invariant:** `close()` is optional (default no-op). Called for resource cleanup.
**Postconditions:** Whether the instance is reusable after `close()` is the backend's **close posture**, declared by the `close_is_terminal` class attribute (BK-298):

- `close_is_terminal = False` (the default — a backend need not restate it): the backend re-initialises its clients lazily and remains usable after `close()`. The posture of `LocalBackend`, `MemoryBackend`, `SFTPBackend`, `ReadOnlyHttpBackend`, and the SQL backends.
- `close_is_terminal = True`: `close()` / `aclose()` is **terminal** — the flag flips at the *start* of `close()` and every lazy client accessor guards on it, so a subsequent operation raises `BackendUnavailable` rather than silently re-opening resources the caller cannot observe. The posture of `AzureBackend` (AZ-029), the three S3 backends (S3-019), and `GraphBackend` (GR-051).

The use-after-close conformance lane (`tests/backends/conformance/test_close_posture.py` and its `aio/` sibling) gates on this attribute, asserting the terminal error for terminal backends and re-initialisation for the rest.
**Rationale:** A terminal close turns a use-after-close (a likely bug) into a clear typed error instead of a silent resource reopen, while leaving stateless/cheap backends freely reusable.

### BE-021: Error Mapping

**Invariant:** Backend-native exceptions never leak. All exceptions are mapped to `remote_store` error types.

**Canonical error mapping table:** The following cross-cutting scenarios MUST
map to the specified error type regardless of backend:

| Scenario | Required error type |
|----------|---------------------|
| File operation (`read`, `write`, `delete`, `get_file_info`, `move`/`copy` src) on a path that is a directory | `InvalidPath` |
| Directory operation (`delete_folder`, `move`/`copy` dst) on a path that is a file | `InvalidPath` |
| Operation on a non-existent path | `NotFound` |
| Operation denied by credentials or ACL | `PermissionDenied` |
| Parent directory creation fails (permissions) | `PermissionDenied` |
| Parent directory creation fails (path conflict) | `InvalidPath` |

The type-mismatch rule (`InvalidPath`) takes precedence over the existence rule (`NotFound`) — a directory path is not "missing", it is the wrong type. This is machine-verified in `sdd/formal/BackendContract.dfy` (`Read`, `Delete`, `DeleteFolder`, `GetFileInfo`, `GetFolderInfo`, `Move`, `Copy` postconditions).

**Scope note:** This table covers *cross-cutting* scenarios that apply to multiple operations. Method-specific errors (e.g. `DirectoryNotEmpty` from `delete_folder`, `CapabilityNotSupported` from capability-gated operations) are documented per-method and intentionally omitted here.

**Broad exception handler rule:** Backends MUST NOT use bare `except OSError`
or `except Exception` handlers that map all errors to a single type. Handlers
MUST discriminate by `errno`, exception type, or HTTP status code before
choosing the mapped error. Silent returns (swallowing exceptions without
re-raising a `RemoteStoreError`) are permitted ONLY for `exists()`,
`is_file()`, and `is_folder()` — these three methods return `False` on any
traversal error, including file-as-directory-component conflicts, rather than
raising `InvalidPath`. All other operations MUST raise appropriate errors.

### BE-022: unwrap()

**Invariant:** `unwrap(type_hint)` returns the native backend handle if it matches the requested type.
**Raises:** `CapabilityNotSupported` if the backend cannot provide the requested type.
**Rationale:** See [ADR-0003](../adrs/0003-fsspec-is-implementation-detail.md).

### BE-023: to_key()

**Invariant:** `to_key(native_path)` converts a backend-native or absolute path to a backend-relative key by stripping the backend's own root/prefix. The default implementation is the identity function.
**Postconditions:** Pure, deterministic, total (never raises). If the input path does not start with the backend's root, it is returned unchanged.
**See also:** [010-native-path-resolution.md](010-native-path-resolution.md) (NPR-003 through NPR-009), [ADR-0005](../adrs/0005-native-path-resolution.md).

### BE-025: native_path()

**Invariant:** `native_path(path)` converts a backend-relative key to the backend-native path. The inverse of `to_key()`: `backend.to_key(backend.native_path(key)) == key`. The default implementation is the identity function — backends with a native root **must** override.
**Postconditions:** Pure, deterministic, total (never raises). The returned path is usable with the native handle from `unwrap()`.
**Overrides:** `LocalBackend` (prepends root dir), `S3Backend` (prepends bucket), `S3PyArrowBackend` (prepends bucket), `SFTPBackend` (prepends base_path), `AzureBackend` (prepends container).
**Example:** `S3PyArrowBackend(bucket="lake").native_path("data/file.parquet")` returns `"lake/data/file.parquet"`.
**See also:** [001-store-api.md](001-store-api.md) (STORE-015), [014-pyarrow-filesystem-adapter.md](014-pyarrow-filesystem-adapter.md) (PA-010 Tier 1).

### BE-026: iter_children()

**Invariant:** `iter_children(path)` returns `Iterator[FileInfo | FolderEntry]` — files as `FileInfo`, folders as `FolderEntry`. Concrete method with a default implementation that chains `list_files(path)` and `list_folders(path)`. Backends that can fetch both in a single I/O call override for efficiency.
**Postconditions:** Non-recursive (immediate children only). Non-existent paths yield nothing.
**See also:** [027-iter-children.md](027-iter-children.md) (ITER-004, ITER-005).

### BE-024: glob()

**Invariant:** `glob(pattern)` matches files against a glob pattern. Non-abstract — the default implementation raises `CapabilityNotSupported`. Backends with native glob support override this and declare `Capability.GLOB`.
**Postconditions:** Returns only files (not folders). Paths in returned `FileInfo` objects are backend-relative (same convention as `list_files`).
**Raises:** `CapabilityNotSupported` if the backend lacks `GLOB`.
**See also:** [018-glob.md](018-glob.md) (GLOB-003 through GLOB-005), [ADR-0009](../adrs/0009-glob-three-tier-design.md).

### BE-027: Capability-Gated Methods (Graph IR Metadata)

**Invariant:** The mapping from Backend method names to required capability names used in the graph IR is maintained in `_BACKEND_GATING` in `scripts/gen_graph.py`. This is static metadata for documentation and tooling — Backend has no runtime `_gate()` equivalent (unlike `Store`). The per-method capability associations are:

| Method(s) | Required capability |
|-----------|---------------------|
| `read`, `read_bytes`, `read_seekable` | `READ` |
| `write` | `WRITE` |
| `write_atomic`, `open_atomic` | `ATOMIC_WRITE` |
| `delete`, `delete_folder` | `DELETE` |
| `list_files`, `list_folders`, `iter_children` | `LIST` |
| `glob` | `GLOB` |
| `get_file_info`, `get_folder_info` | `METADATA` |
| `move` | `MOVE` |
| `copy` | `COPY` |

**Enforcement:** Runtime capability enforcement for these methods is performed by `Store._gate()`, not by `Backend` directly. `_BACKEND_GATING` is the authoritative source for graph-IR generation only; keeping it in sync with the Backend ABC is enforced by `tests/scripts/test_gen_graph.py::test_backend_gating_keys_match_backend_members`.
**Async counterpart:** `AsyncBackend` carries the same table minus `read_seekable` / `open_atomic` in `_ASYNC_BACKEND_GATING` — see [ASYNC-045a](029-async-store-backend-api.md).
**See also:** `sdd/CLAUDE-REFERENCE.md` ripple-check row for `_BACKEND_GATING`.

---

## Concurrency

### BE-028: Concurrent-Use Posture

**Invariant:** Every concrete `Backend` declares a **concurrent-use posture**,
one of two values:

- **`thread_safe`** (the default — a backend spec need not restate it): a single
  instance is safe to share across threads, and each `Backend` operation is
  atomic with respect to other operations on the same instance.
- **`single_connection`**: a single instance is **not** safe under concurrent
  use — it wraps a non-thread-safe native client (e.g. one SFTP channel, or a
  `urllib` opener whose redirect counter is shared). Such a backend MUST document
  the posture in its spec **and** class docstring, and MUST state the remedy: one
  instance per thread, or an external serializing wrapper.

No backend provides multi-operation transactionality: atomicity is per-operation
only (MEM-026), and ordering between concurrent callers is not guaranteed.

**Postconditions:**
- `thread_safe` is the posture of `LocalBackend` (stateless; delegates to
  `os`/`shutil`, serialised by the kernel), `MemoryBackend` (a single
  `threading.Lock`, MEM-025), the cloud and SQL backends (their native clients —
  the boto3/s3fs client, the Azure SDK service clients, the SQLAlchemy
  engine/pool — are documented thread-safe for concurrent per-instance use), and
  `GraphBackend` on the async axis (GR-059).
- `single_connection` is the posture of `SFTPBackend` (SFTP-029) and
  `ReadOnlyHttpBackend` on its default `urllib` transport (HTTP-CONC-001).
- An **undeclared** posture is a contract violation, not a silent default: every
  concrete backend states its posture, or inherits the `thread_safe` default by
  the terms of this clause (`LocalBackend`, which has no numbered spec, is
  `thread_safe` by this paragraph).

**Rationale:** STORE-007 promises a `Store` is "safe to share across threads,"
but a `Store` is immutable and merely delegates — the guarantee bottoms out in
the backend. This clause turns "thread-safe" from an unstated assumption into an
explicit per-backend obligation a caller can read from the spec without reading
source. Like CAP-007's quality flags, declaring the posture gates no method; it
documents a property every method has. The posture is the authoritative source
for the machine-readable `concurrency` registry field the cross-backend
concurrency conformance lane tests against.

**See also:** [001-store-api.md](001-store-api.md) (STORE-007),
[013-memory-backend.md](013-memory-backend.md) (MEM-025/026),
[029-async-store-backend-api.md](029-async-store-backend-api.md) (ASYNC-094).
