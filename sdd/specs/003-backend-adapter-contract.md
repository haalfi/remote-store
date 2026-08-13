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
**Root:** the store root (`""` or `"."`) is always a folder — see BE-029.

### BE-029: Root Path

**Applies to:** backends declaring `Capability.LIST`. "The root is a folder"
presupposes a backend that *has* folders, and LIST is how a backend declares
that it enumerates them. A backend without LIST exposes a flat set of
addressable objects with no root to speak of, and its answers for `""` are
whatever its own contract says — `ReadOnlyHttpBackend`, for instance, resolves
the empty key to its base URL and reads that. The boundary is the declared
capability, never a named backend: naming one would reintroduce exactly the
undeclared divergence this clause removes, and a future LIST-less backend
would inherit the right treatment for free.

**Invariant:** Every LIST-capable backend accepts both spellings of the store
root — `""` and `"."` — and treats them as the same path: a folder that always
exists. For `path` in `{"", "."}`:

| Query | Answer |
|-------|--------|
| `exists(path)` | `True` |
| `is_folder(path)` | `True` |
| `is_file(path)` | `False` — and it does **not** raise |
| `get_folder_info(path)` | aggregates the whole store (never `NotFound`) |
| `list_files(path)` / `list_folders(path)` / `iter_children(path)` | enumerate from the root |
| `native_path(path)` / `resolve(path).native_path` | the backend's bare root |
| every file-shaped operation | `InvalidPath` — see below |

**A file-shaped operation on the root raises `InvalidPath`.** The root is a
folder, so BE-021's first row governs it exactly as it governs any other folder
path — the row's subject is a *file operation*, and its list is illustrative,
not the roster. In full: `read`, `read_bytes`, `read_seekable`,
`get_file_info`, `delete` (with or without `missing_ok`) and the `move`/`copy`
**source** all raise `InvalidPath`. The folder-shaped calls are not in that set;
they legitimately accept the root. That **outcome** binds every backend in
scope, whatever route it takes to get there.

**Where a backend has to decide it.** A backend whose native root is itself an
addressable node — a filesystem directory, a drive-root item — MAY hand the
root to its SDK and read the verdict off the answer: the store answers
*correctly*, merely later, and an `IsADirectoryError` or a `folder` facet is
the same verdict a string test would have produced. The MUST is for the
backends without that property: **a backend whose SDK cannot answer correctly
for its own native spelling of the root MUST decide root-ness from the key,
before the call.** The shape that fails is a flat namespace whose root key is
the empty string, and it fails in both directions — an SDK that rejects a
zero-length key at parameter validation turns a permanently wrong request into
a transport-shaped, retryable-looking error, while one that accepts it reads
the bare prefix back as a zero-length object and *succeeds*. Root-ness is
decidable from the string with no round trip, so neither outcome has to be
risked to learn it.

**Conformance pins the outcome, not the order** — and does not need to pin
both: a backend that gets the order wrong is observable as exactly the wrong
error class or a spurious success, which is what the cells below assert.

**BE-020 outranks this check.** On a backend with `close_is_terminal = True`,
a file-shaped call on the root *after* `close()` raises `BackendUnavailable`,
not `InvalidPath`: BE-020 states its guarantee without exception, and a closed
backend is the more fundamental error. A root pre-check is cheap and so
naturally wants to run first — a backend that has one MUST still run the closed
guard ahead of it, or the answer depends on which guard the implementer
happened to write first. Pinned by
`test_close_posture_outranks_root_rejection` in
`tests/backends/conformance/test_close_posture.py` and its `aio/` sibling.

**One predicate, both spellings.** `remote_store._path.is_root` is the shared
test; `strip_root` is its normalising form. A backend that asks `if path`
instead sends the dot spelling down the non-root arm, because `"."` is truthy —
which is how one backend came to answer `NotFound` for `delete("")` and
`InvalidPath` for `delete(".")` on the same store. Path concatenation is the
same trap from the other side: `"./"` is a real and permanently empty prefix on
a flat namespace, so a listing built by concatenation silently answers for
nothing and reports success.

**The root exists by definition, not by observation.** An empty store still
has a root: `is_folder("")` is `True` before anything is written. Backends that
would otherwise answer from a stat or a listing must short-circuit — otherwise
"nothing has been written yet" is indistinguishable from "there is no root",
a distinction no backend can act on and none of them exposes anywhere else.

**Why `is_file("")` may not raise.** BE-021 already forbids `exists()`,
`is_file()` and `is_folder()` from raising on an inaccessible path; the root is
the same rule at the boundary. A backend whose SDK rejects a zero-length key at
parameter validation must answer `False` itself rather than let the rejection
surface as `BackendUnavailable`.

**Layering.** `Store` normalises `"."` and refuses a root delete (STORE-002 in
[001-store-api.md](001-store-api.md)), so an application going through `Store`
never depends on this clause. It binds the layer below, which has its own
callers: the adapter surface, `unwrap()` consumers, anything round-tripping a
`FolderInfo.path` (rendered `"."` by `RemotePath.ROOT`) back into a query, and
the conformance suite itself.

**Round-trip consequence.** Because both spellings share one native path,
BE-025's `to_key(native_path(k)) == k` identity returns the *canonical* root
key: `to_key(native_path("."))` is `""`, not `"."`. The identity holds verbatim
for every other key. This is forced, not a concession — an inverse cannot
return two spellings from one input.

**Out of scope:** `delete_folder("")` and writes *to* the root. `delete_folder`
on the root is governed at the `Store` layer (STORE-002); backend behaviour for
it is undefined by this clause. Writing to the root path is a malformed file
path, rejected by path validation. Note `delete("")` is **not** out of scope —
it is a file-shaped operation on a folder, and the row above governs it.

**Conformance:** `tests/backends/conformance/test_io.py::TestBackendRootPath`
and its async sibling in `test_async_extended.py`, both gated on
`Capability.LIST` and parametrised over both spellings; addressing is covered by
`test_identity.py::TestBackendNativePath` (sync) and
`test_async_extended.py::TestAsyncBackendNativePath` (async).

**Coverage note.** Two LIST-capable backends reach these cells only in part, and
what they do reach is measured rather than assumed:

| Backend | Reached by the conformance cells | Pinned only in its per-backend home | Pinned nowhere |
|---------|----------------------------------|--------------------------------------|----------------|
| `SQLQueryBackend` — fixture `sqlquery` | the query rows on the empty store (`exists` / `is_folder` / `is_file`, both spellings); addressing (`native_path` / `resolve` agreeing on both spellings, `to_key` returning the canonical root key); and the **read half** of the file-shaped-operation row — `read`, `read_bytes`, `read_seekable`, `get_file_info`, both spellings | the populated-store rows (`get_folder_info` aggregating a non-empty store), because the conformance fixture registers an empty query mapping and the suite seeds through `write` (ID-244) | — |
| Graph — fixture `graph_replay` | addressing, under the fixture's `base_path`: `native_path` / `resolve` agreeing on both spellings, `to_key` returning the canonical root key | in `tests/backends/graph/aio/test_backend.py`: every root spelling refused by `_require_writable_key`, and the same addressing agreement with **no** `base_path` — the conformance fixture is always rooted under one, and the bare-root arm is where both defects this clause was written from lived | the query rows and the file-shaped-operation row |

The file-shaped-operation row is seven operations (`_ROOT_FILE_OPS`): the four
reads above plus `delete`, `move` and `copy`. `SQLQueryBackend` declares no
capability for those three, so they are gated out rather than missed — nothing
to pin, which is why its "pinned nowhere" cell is empty rather than listing them.

A clause that binds every LIST-capable backend needs its coverage checked per
backend, not per source site — both defects this clause was written from
survived a source-wide sweep because no cell executed against them. Each column
here is a distinct gate, and the two that were structural have been closed
structurally: BK-340 registered the missing `sqlquery` fixture, and ID-241 made
the missing-cassette skip fire per unplayable request rather than per test name,
which is what let Graph's addressing cells — pure string work, no HTTP — move
into the first column. What remains in Graph's last column is not a gate but an
absence: the Graph data-plane cassettes those rows need have not been recorded.
The middle column is the gate still open, and it is a second one underneath
capability filtering rather than a residue of the first: a read-only backend
cannot reach any cell that seeds through `write` (ID-244).

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
**Absent container:** A missing bucket, container or table counts as a missing file, so `missing_ok=True` returns cleanly and `missing_ok=False` raises `NotFound` — see [BE-021](#be-021-error-mapping) § "An absent container reads as an absent path" for the rule, its stated reach, and its cost model. It binds every backend in scope, with no carve-out. Outside the Dafny model's frame: `BackendContract.dfy` models the store as a map that always exists, so the absent-container case has no representation to verify against and is pinned in Python only (BUG-243).

### BE-013: delete_folder()

**Invariant:** `delete_folder(path, recursive=False, missing_ok=False)` removes a folder.
**Raises:** `NotFound` if the path does not exist and `missing_ok=False`. `InvalidPath` if `path` names a file (use `delete` instead). `DirectoryNotEmpty` if the folder is non-empty and `recursive=False`. See BE-021.
**Absent container:** A missing bucket, container or table counts as a missing folder, on the same terms as BE-012 — see [BE-021](#be-021-error-mapping) § "An absent container reads as an absent path". This is the half the wire shape got wrong: an absent prefix is an empty listing, so the container's 404 is the only one a prefix listing can raise, and a backend MUST read it as "no children" rather than letting it escape past the `missing_ok` check.

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
**Flat-namespace backends are not exempt** (BK-324): when the prefix listing comes back empty they probe the exact key and raise `InvalidPath` rather than `NotFound`. See [BE-021](#be-021-error-mapping) for the shared error-path rule and its cost model.
**Root:** `get_folder_info("")` aggregates over the whole store rather than raising — see BE-029.
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
| File operation (e.g. `read`, `write`, `delete`, `get_file_info`, `move`/`copy` src) on a path that is a directory | `InvalidPath` |
| Directory operation (e.g. `delete_folder`, `move`/`copy` dst) on a path that is a file | `InvalidPath` |
| Operation on a non-existent path | `NotFound` |
| Operation denied by credentials or ACL | `PermissionDenied` |
| Parent directory creation fails (permissions) | `PermissionDenied` |
| Parent directory creation fails (path conflict) | `InvalidPath` |

The type-mismatch rule (`InvalidPath`) takes precedence over the existence rule (`NotFound`) — a directory path is not "missing", it is the wrong type. This is machine-verified in `sdd/formal/BackendContract.dfy` (`Read`, `Delete`, `DeleteFolder`, `GetFileInfo`, `GetFolderInfo`, `Move`, `Copy` postconditions).

**Backend scope of the two type-mismatch rows.** They bind every backend on the
operations that can *fail* on a wrong-typed path: `read`, `read_bytes`,
`read_seekable`, `delete`, `get_file_info`, `delete_folder`,
`get_folder_info`, and the `move`/`copy` **source**. Their write half —
`write`, `write_atomic`, `open_atomic`, and the `move`/`copy` **destination** —
binds hierarchical backends only. On a flat namespace a write to a key that
shadows a prefix succeeds, so there is no error to reclassify; BE-008's
flat-namespace exemption governs there instead, unchanged. This is the single
roster for both halves; the clauses below explain the mechanism behind the
split and what it costs, and do not restate it.

**Scope note:** This table covers *cross-cutting* scenarios that apply to multiple operations. Method-specific errors (e.g. `DirectoryNotEmpty` from `delete_folder`, `CapabilityNotSupported` from capability-gated operations) are documented per-method and intentionally omitted here.

**Flat-namespace backends: no exemption, but an error-path obligation.** A
flat namespace stores keys, not nodes, so "this path is a directory" is not an
answer the store returns — it has to be derived from a prefix listing. That
made the two type-mismatch rows above quietly optional on S3, Azure non-HNS
and SQL for a long time: those backends answered `NotFound`, or worse
succeeded (a bare prefix read as a zero-length object, a `delete` that no-oped,
a `get_folder_info` that counted the file as its own content). BK-324 settled
it in favour of the contract: **the two rows hold on every backend wherever an
operation can fail on a wrong-typed path** — the scope stated with the rows
above — and the divergence is a defect rather than a declared variation.

The obligation is discharged on the **error path only**. A backend derives the
type verdict when the operation has already failed to find what it needed — one
`MaxKeys=1` prefix listing for "is this a folder?", one HEAD / exact-key lookup
for "is this a file?" — and converts the miss into `InvalidPath`. A call that
*finds its target* never runs the probe, so the guarantee costs nothing on the
hot path.

**Two cases both fail and succeed**, and both are the idempotent-delete idiom.
They cost different things, because each spends the probe its own type verdict
needs:

| Call | Miss that triggers the probe | Probe spent |
|------|------------------------------|-------------|
| `delete(path, missing_ok=True)` on an absent key | the exact-key lookup finds no object | one `MaxKeys=1` prefix listing — "is this a folder?" |
| `delete_folder(path, missing_ok=True)` on an absent prefix | the prefix listing comes back empty | one HEAD / exact-key lookup — "is this a file?" |

In both the probe runs and the call then returns cleanly, because `missing_ok`
tolerates the miss; in a delete loop that is one extra round trip per absent
path. Neither is avoidable by testing `missing_ok` first: `delete(folder,
missing_ok=True)` and `delete_folder(file, missing_ok=True)` must still raise
`InvalidPath` (see "Type mismatch outranks `missing_ok`" below), and after a
miss the probe is the only thing separating *this is the wrong type* from *this
is genuinely absent*. Skipping it would restore the silent success this clause
exists to remove, so the cost is the price of the verdict, not an oversight.
The probe is **fail-open**: if it errors (503, throttling, network blip) the
operation's original error stands rather than being replaced by a transport
error, the same posture the file-ancestor walk takes (see BE-008 / ID-211).

**Fail-open is a property of that call site, not of the probe as a mechanism.**
The same HEAD or prefix listing usually also serves as the plain *existence*
check at the head of `delete`, `delete_folder`, the `move`/`copy` source and
`get_folder_info`. There it is the **determinant**, and there it MUST fail
closed: an error-path probe that cannot answer still has the operation's own
error to preserve, but a determinant that cannot answer has nothing — swallowing
its failure does not keep a truthful verdict, it invents one. A denied HEAD
reported as `NotFound` both contradicts the ACL row above and tells the caller an
object is absent when it exists and they may not see it. A backend that shares
one helper across the two roles therefore wraps it *at the error-path call site*
rather than widening the helper itself.

The probe firing on failure is *why* the roster splits where it does: the
obligation reaches exactly the operations that *can* fail on a wrong-type path
— the list stated with the rows above — and the write half offers it no failure
to reclassify.

`read_seekable` is in the list, not exempt from it. `SEEKABLE_READ` is a
CAP-007 *quality flag*: it describes the stream `read()` hands back, not a
different contract, and the ABC default implementation delegates to `read()`.
Only a backend that overrides `read_seekable` for an optimised range reader
could diverge — so excluding it would make the error contract depend on whether
a backend optimised its seekable path, which is exactly the undeclared
divergence this clause exists to remove.

Type mismatch outranks `missing_ok`: `delete(folder, missing_ok=True)` and
`delete_folder(file, missing_ok=True)` raise `InvalidPath`, because the
tolerance is for a *missing* path, not a wrong-typed one. This is the same rule
BE-012 already states for hierarchical backends, now uniform.

**An absent container reads as an absent path.** The bucket, container or table
holding a path is part of the path's existence: a container that is not there
holds no path either. `delete(path, missing_ok=True)` and `delete_folder(path,
missing_ok=True)` MUST return cleanly against an absent container; with
`missing_ok=False` both MUST raise `NotFound`. This binds **every** backend in
scope — there is no carve-out, and a backend whose native error for an absent
container is not already a `NotFound` owes the reclassification like any other.

**The rule is free on the miss path, and MUST stay so.** Backends MUST NOT spend
an extra round trip to tell an absent container from an absent path: the two
answers are the same, so the discrimination has no buyer. Where a backend needs
a probe to recognise the absent container at all, that probe belongs on the
*error* path — charged only to an operation that has already failed — under the
error-path-only rule above. An ordinary miss must not pay for it.

**Reach: these two calls, and no others by implication.** The clause decides
what `missing_ok` tolerates; it does not silently re-decide operations that have
no `missing_ok`. Every other operation already had an answer for an absent
container before this clause, and keeps it: `get_folder_info`, `read`,
`get_file_info` and the `move`/`copy` source take the canonical table's
`NotFound` row; `list_files` and `list_folders` return an empty listing, since an
absent container holds nothing; `exists()`, `is_file()` and `is_folder()` MUST
answer `False`, which BE-004 / BE-005 and this section's own rule already forbid
them from breaching. `write` is the one operation *on the roster* that no clause
of this spec decides, and this one does not decide it either — which leaves it
the one roster operation a backend spec may decide, as
[GR-031](044-graph-backend.md#gr-031-404-discrimination-item-vs-drive) does for
`GraphBackend` ([ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md)).
That is a gap being filled, not a divergence: a backend answering `write` its own
way contradicts nothing here. Anything *off* the roster — a health probe, a
credential or container-identity lookup — is not an operation this section
reaches at all, so it needs no such permission and is not counted against this
one. All of these obligations are pre-existing — this
clause neither creates nor relaxes them, and that is why those operations are
absent from the roster above rather than exempt from it.

**The root is decided by BE-029, not here, and BE-029 wins.** This paragraph
assigns answers per *operation*; it says nothing about the store root within
them, and reading a root answer off it is a mistake this spec has already
produced once. [BE-029](#be-029-root-path) states the root case directly and
without qualifying it by whether the container exists: the root is a folder that
always exists, so `exists("")` and `is_folder("")` answer `True`, and
`get_folder_info("")` aggregates the whole store and never raises `NotFound` —
an empty store rather than a missing path. Where that meets the `NotFound` row
above, **BE-029 governs**: against an absent container the root of a compliant
backend answers as it would for an empty one.

Stated here because this is where a reader looking for per-operation answers
lands, and following it alone yields the wrong answer for one path in every
operation it names.

**Most backends do not meet the root row yet, and the list below does not record
it.** § Known divergences holds one bullet, `LocalBackend`, whose breach is
whole-backend rather than root-specific. The root breaches are measured and
tracked as **BUG-254**: `exists("")` and `is_folder("")` answer `False` on
`S3Backend` and `S3PyArrowBackend`, and `get_folder_info("")` raises `NotFound`
on `S3Boto3Backend`, `AzureBackend` and `AsyncAzureBackend` — five classes,
seven class-cells (two operations on two classes, plus one on three), in two
opposite directions. `SQLBlobBackend` is the one that complies.
They are absent from the list below because that list is organised by the
absent-container *clause* and these are breaches of BE-029's root row; the
pointer is here so a reader does not read the one-bullet list as meaning the root
is settled.

**§ Reach's roster is twelve operations, and its siblings are not silently
included.** The twelve are the two tolerant deletes plus the ten this paragraph
names, counting the `move`/`copy` source as one. (The Graph paragraph below says
GR-031 reached "eleven of the ones named above" and kept `write`; eleven plus
`write` is the same twelve.)

`read_bytes`, `read_seekable`, `iter_children` and `glob` are not among them.
Each is a thin variant of one that is — `read`, `list_files`, `list_folders` —
and a backend that answers a named operation one way and its variant another has
a defect rather than a permission. But that is a *reading*, and it is the reading
this section elsewhere makes explicit when it counts Graph's divergence as
"eleven of the ones named above, plus `read_bytes` and `iter_children`". A
backend spec relying on the reading should say so, as
[SQL-BLOB-050](040-sql-blob-backend.md#sql-blob-050-exception-translation) does.

**"Roster" is used twice in this section and the two sets differ.** The
type-mismatch rows above have their own roster — the one their scope paragraph
calls "the single roster for both halves", which *does* name `read_bytes` and
`read_seekable`, and which the "`read_seekable` is in the list" paragraph is
about. This paragraph is about § Reach's roster only. Neither is wrong; a reader
meeting the word in one place and the membership claim from the other is.

**Known divergences, stated rather than implied.** These are what ships today,
recorded so a reader does not mistake an obligation for a description, and
tracked in the backlog. They are scoped to the whole absent-container question
rather than to the two deletes alone: the Reach paragraph rules that the other
operations keep obligations this clause did not write, and a divergence from one
of *those* is no less real for having been written down elsewhere. Listing them
here is what makes the container case answerable from one place.

- `LocalBackend` answers **every** operation with
  `InvalidPath("Path escapes root directory")` once its root directory is
  deleted, including both tolerant deletes. The containment check walks up to
  the deepest existing ancestor, which is above the root once the root is gone,
  so absence is misreported as an escape. This is the furthest from the clause
  any backend currently sits, and the only one where the error type actively
  misleads.

Three bullets have left this list and are recorded rather than deleted, because
each was a *measured* divergence and the measurement is what a later reader
needs in order to trust the list's remaining entry:

- `exists()` and `is_folder()` raised `NotFound` against an absent container on
  `S3Boto3Backend`, `AzureBackend` and `AsyncAzureBackend`, where the strict
  prefix probe was reached after the tolerant HEAD came back empty. All three now
  answer `False`, as `S3Backend` and `S3PyArrowBackend` already did (BUG-246).
- `S3Boto3Backend`'s `list_files`, `list_folders` and `iter_children` raised a
  raw `botocore.exceptions.ClientError`, breaching the never-leak invariant at
  the top of this section rather than the mapping row: they were the only methods
  on that class whose wire call was not wrapped in its error mapper, against
  fifteen methods that do wrap. All three now return an empty listing, as the two s3fs-backed
  lanes already did against the identical response (BUG-249).
- On `SQLBlobBackend`, **every operation except the two deletes** answered an
  absent table with `BackendUnavailable` (or the base error, by dialect), because
  they mapped the driver's complaint without asking whether the table was still
  there. It was the widest divergence this list ever held by operation count —
  fourteen operations, measured against a dropped SQLite table, of which thirteen
  owed a different answer. Each of the thirteen now takes the answer § Reach
  gives it or its named sibling: `exists`, `is_file` and `is_folder` answer
  `False`; `read`, `read_bytes`, `get_file_info`, the `move`/`copy` source and
  `get_folder_info` **below the root** raise `NotFound`, while the root
  aggregates to an empty store under BE-029; `list_files`, `list_folders`,
  `iter_children` and `glob` come back empty. Three of those thirteen —
  `read_bytes`, `iter_children` and `glob` — are siblings § Reach does not name,
  per the roster paragraph above. `read_seekable` is not among them: this backend
  does not override it, so it is not a distinct operation here. The same split showed on a disposed in-memory engine, where disposal
  destroys the database rather than releasing a connection to it — one divergence
  with two ways in, closed by the same change, and the reclassification
  deliberately does not try to tell them apart; see
  [SQL-BLOB-050](040-sql-blob-backend.md#sql-blob-050-exception-translation).
  **`write` keeps `BackendUnavailable`** and is not a residue: it is the one
  roster operation § Reach declines to decide, so a backend answering it its own
  way contradicts nothing here (BUG-246).

`GraphBackend` was a bullet too, adjudicated by
[ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md). Counting
bullets rather than backend classes — one of the two frames `sdd/BACKLOG.md` § 1
uses, and the one it counts this list in — this list held five and now holds
one.
[GR-031](044-graph-backend.md#gr-031-404-discrimination-item-vs-drive) mapped
`404 resourceNotFound` to `BackendUnavailable` for every error-raising
operation, deliberately, on the grounds that a deleted drive is a backend
identity failure rather than a per-item condition — and a drive is a container,
so two clauses of this repository's own specs gave opposite answers for the same
call. The divergence was recorded as reaching the two tolerant deletes; measured
across every operation it reached **eleven** of the ones named above, plus
`read_bytes` and `iter_children`.
[ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md) adjudicated
it in favour of this clause for every operation this clause decides. GR-031 keeps
what it does not: `write`, the one roster operation § Reach declines; and, off
the roster entirely, `check_health`, Graph's drive-id resolution and its
copy/move monitor poller.

The rule exists because leaving it unstated let each backend answer from
whatever its wire protocol happened to reveal. `HeadObject` answers a bodyless
404, so a missing bucket is indistinguishable from a missing key and `delete`
tolerated it without being asked to; `ListObjectsV2` answers an absent prefix
with `200 KeyCount=0`, so the only 404 it can raise is the container's, and
`delete_folder` raised where its sibling returned — against the same absent
bucket, in the same store. Tolerating is the cheaper way to end that
disagreement on the backends whose wire shape produced it: making the pair
strict would have cost `delete` a second `HeadBucket` on every miss, against the
one-probe-per-miss budget above, to buy an answer no caller asked to
distinguish.

**Two earlier premises for the rule were false, and both are recorded rather
than quietly dropped** — each was asserted from a reading and disproved by a
run, which is the argument for the rule being stated as an obligation rather
than inferred from what backends happened to do.

The first was that the hierarchical backends had already settled it, because on
Local an absent store root is just an absent path. With its root deleted,
`LocalBackend` raises `InvalidPath("Path escapes root directory")` from the
containment check, before either delete's `missing_ok` branch is reached. It is
a divergence from this clause, not evidence for it, and it went unnoticed
because both deletes look correct in isolation — the guard that fires is two
lines upstream in `_resolve`.

The second was that the rule merely ratified what `delete` already did on every
flat-namespace backend, correcting only its sibling. That holds for the S3 and
Azure family, whose bodyless `HeadObject` 404 cannot name the bucket, and it is
where the reported symptom came from. It does not hold for `SQLBlobBackend`,
which is flat-namespace by this spec's own classification and whose `delete` was
measured raising `BackendUnavailable` against a dropped table before this
change, exactly as its sibling did — that is the state *before BUG-243*, which
is the change this paragraph is about, and not the state the departed bullet
above describes, which is after it. The rule therefore changes `delete` on one
backend rather than ratifying it everywhere. Both are recorded above — Local as
this list's one remaining bullet, SQLBlob among the three that have left it; the
premise survived six review rounds because "the S3 family" and "the
flat-namespace backends" were used interchangeably by a clause whose whole
purpose is to bind the second set.

Reading the container's 404 as "no children" does not shortcut the rest of the
operation: the wrong-type probe still runs and `missing_ok=False` still raises.
The catch MUST stay narrow to the one shape that means "the container is not
there" — a denial stays `PermissionDenied` and a 503 stays
`BackendUnavailable`, per the determinant rule above.

**What each backend's absent container looks like**, since the shape differs and
the answer must not. S3 and Azure already map it into `NotFound` — the family
`missing_ok` swallows — so the work is only to stop the error escaping past the
tolerance check out of a `delete_folder` determinant. `SQLBlobBackend`'s
container is its table, and a dropped one arrives as a driver failure rather
than a missing row (`OperationalError` on SQLite, `ProgrammingError` on
PostgreSQL and MySQL), so it reclassifies: one inspector call, hung off
`SQLAlchemyError` so it is charged to a statement that already failed and never
to a miss.

**What "every backend" leaves out, named rather than left to be re-derived.**
The clause reaches every backend that can delete and whose container can be
absent. That is `S3Backend`, `S3PyArrowBackend`, `S3Boto3Backend`,
`AzureBackend`, `AsyncAzureBackend`, `SQLBlobBackend`, `LocalBackend`,
`SFTPBackend`, `GraphBackend` and its sync adapter. Four are out of scope, for
two different reasons: `MemoryBackend` and `AsyncMemoryBackend` delete, but
their container is an in-process dict that cannot be absent while the backend
exists; `SQLQueryBackend` and `ReadOnlyHttpBackend` do not declare `DELETE`, so
there is no tolerant delete to bind. Writing the roster out is cheap insurance
— `GraphBackend` sat unexamined through six review rounds of this clause
because nobody had enumerated which backends the words picked out.

**Why "every backend" and not a scoped subset.** Three criteria for narrowing
the clause's reach were tried and every one was either circular or false — the
last keyed on whether a backend's mapping already produces `NotFound`, which the
canonical table above requires of every backend anyway. Compliance turned out to
cost less than any of the justifications for exemption, which is the argument
against a carve-out here rather than for one. It binds all of them.

**The store root is decided before the probe, not by it.** A probe answer about
the root is meaningless — it is a folder whether or not it has children — so
every file-shaped operation rejects it up front (BE-029) and the probes below
exempt it. That pre-check is also the only one that costs nothing, which is why
it is the single exception to the error-path-only rule above.

**Conformance:** `tests/backends/conformance/test_errors.py` and its async
sibling `test_async_extended.py` carry no flat-namespace skip on these cells.

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
**Root spellings:** `native_path("")` and `native_path(".")` return the same value, the bare backend root (BE-029). The round-trip identity therefore returns the canonical root key — `to_key(native_path("."))` is `""` — since one native path cannot invert to two spellings. Every non-root key round-trips verbatim. The identity-default implementation normalises both spellings for the same reason.
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
