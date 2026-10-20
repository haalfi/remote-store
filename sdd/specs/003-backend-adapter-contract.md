# Backend Adapter Contract Specification

## Overview

The `Backend` ABC defines the contract all storage backends must implement. It is the most critical spec in the system — every operation, error condition, and capability is defined here. Backends declare capabilities via a `Capability` enum and `CapabilitySet`.

The states between calls, the close posture (BE-020), the concurrent-use posture (BE-028) and the kernel's interaction protocol (BE-033), are [spec 052](052-backend-lifetime.md)'s. The contract kernel's single-call clauses (BE-030 to BE-032) are [spec 053](053-contract-kernel.md)'s.

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

**The MAY above is narrower than "the root is an addressable node".**
Reading the verdict off the SDK is sound only while the node is
*there*. A filesystem directory — the first example this clause offers — can be
removed underneath a live backend, and then the OS answers ENOENT rather than
`IsADirectoryError`: the verdict is not late, it is **wrong**, and every answer
in the table above flips. `LocalBackend` took the MAY, satisfied this clause for
years by observation, and breached it the moment its root was deleted. So the
MAY holds for a node whose absence the backend has already ruled out, and a
backend whose root can vanish under it decides root-ness from the key like any
flat namespace. `SFTPBackend` was already there for the neighbouring reason: its
`base_path` is created lazily, so the node is absent on an untouched store.

**One operation must still observe the root**, or the definitional answers
become unfalsifiable. If every probe answers from the key, nothing reports a
root that exists but is the wrong *type* — a regular file where the store root
belongs — and the store reports itself healthy while holding nothing. That
observation belongs in the health probe, which is off BE-021's roster and free
to make it: `LocalBackend.check_health` tests `is_dir()`, not mere existence,
for exactly this reason.

**Conformance pins the outcome, not the order.** A wrong order is visible to
the cells below only where the root's own answer is wrong, and a present root
often answers correctly by observation, so the order is unpinned there on every
row. It matters once the container is absent, which no conformance fixture
arranges (for a class on the kernel the fake-driver cells in
`tests/_kernel/` observe it, BE-020 ranked first); the
backends that can lose theirs pin it per backend.

**BE-020 outranks this check.** On a backend with `close_is_terminal = True`,
every operation in the table above except the addressing row raises
`BackendUnavailable` *after* `close()` — not `InvalidPath` from a file- or
write-shaped guard, not the row's definitional answer from a probe or aggregate,
and not a class the operation's own error handling substituted. A closed backend
is the more fundamental error, and a root pre-check is cheap and so naturally
wants to run first: a backend that has one MUST still run the closed guard ahead
of it, or the answer depends on which guard the implementer happened to write
first.

**The one carve-out is addressing, and it is named rather than derived.**
`native_path(path)` / `resolve(path).native_path` — the table's addressing row —
are pure key transformations that answer after `close()` exactly as they did
before, because BE-025's round-trip identity has nothing to do with a live
connection. (`to_key` is addressing's other half and is governed under § Round-trip
consequence rather than by a row here; it takes the same carve-out.)

**Do not restate that carve-out as "whatever reaches no client".** The
key-decided root answers — `exists`, `is_file`, `is_folder`, `get_folder_info`
— reach no client *either*, by construction: that is what deciding the root from
the key means, and it is precisely why each of them has to call the closed guard
explicitly rather than inherit it from a lazy accessor. A criterion phrased by
mechanism exempts the operations this clause exists to bind, which is the reading
that let five classes answer a closed store. The carve-out is the addressing row,
by name, and nothing else.

**Three pre-checks, and they need separate cells.** The rule reaches the root
three ways, and no one cell reaches another's path:

| Shape | What carries the pre-check | Conformance cell |
|---|---|---|
| File-shaped | `_reject_root_as_file` and its equivalents | `test_close_posture_outranks_root_rejection` |
| Write-shaped | a second, differently-worded write guard | `test_close_posture_outranks_root_write_rejection` |
| Probe and aggregate | the key-decided answer BE-029's table requires | `test_close_posture_outranks_the_root_probes` |

All three live in `tests/backends/conformance/test_close_posture.py`, each with
an `aio/` sibling. None is hypothetical. `GraphBackend` ordered its write guard
ahead of its closed check and answered a closed store with "cannot write to the
drive root", which the read cell had passed for years. In the third row's case,
five classes answered the root probes after `close()` — three of them for as long
as they had short-circuited the root from the key, and two more added in the
course of fixing them — and the two cells above stayed green throughout, because
neither drives a probe.

**The third row's cell enumerates its operations rather than listing them.** A
key-decided root answer can live in any operation the row governs, and patching
the ones an author thought of is what produced the second half of that five: the
probes were fixed from a reading of where the hazard was, and the next review
round found the same defect in `get_folder_info`, reached through an exception
handler that caught the guard's own error and re-classified it. An operation
added to the row is added to the cell's parametrisation.

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
"nothing has been written" is indistinguishable from "there is no root",
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
for every other canonical key. This is forced, not a concession — an inverse cannot
return two spellings from one input. A non-canonical key's address inverts to
its canonical key, as BE-025's non-canonical exception allows: `GraphBackend`
and both Memory classes fold `"d//f"`, `"d/./f"`, `"d/"` and `"./"` that way.

**A write *to* the root is refused before anything is transferred.**
`write`, `write_atomic` and `open_atomic` MUST raise `InvalidPath` naming the
root, under **every spelling that addresses it**, in both overwrite modes, and
**before** the request reaches the storage system. This clause used to place
writes out of scope on the grounds that the root is a malformed file path
"rejected by path validation" — true, and not sufficient. Validation downstream
of the write still rejects it, *after* the bytes have gone: on the two
hierarchical backends the write ran to completion against the container path
itself, leaving the store's container a regular file while every probe above kept
answering "folder" from the key. What the clause has to bind is therefore the
*order*, not merely the outcome.

**"Every spelling that addresses it" is wider than `is_root`, and this is the one
clause where that matters.** `is_root` is the two canonical spellings, `""` and
`"."` — the forms a backend key and a `RemotePath` use, and the right test
everywhere the question is *addressing*. It is the wrong test here. A caller
holding a `Backend` directly can pass `"./"`, which `RemotePath` normalises to the
root and `is_root` does not recognise; measured against a `LocalBackend` whose
root had been deleted, a guard written as `if is_root(path)` let `write("./")`
leave the root a regular file and `open_atomic("./")` return cleanly having done
it — the whole defect, one character from the spelling it caught. **So a backend
implementing this clause as `if is_root(path)` is not conformant**. The write
and `move`/`copy` destination cells below run all six spellings listed next,
and require only that the raised path name the root under some spelling, since
a backend may echo the raw key or fold it first (the verified oracle folds every
spelling onto `"."`). **They catch an `is_root` guard only where nothing
behind the guard refuses the key.** Whether something does depends on the
backend: a hierarchical store with its container present refuses `"./"` by its
own directory check, so there only the root destination against a missing
source sees the narrow guard, and a flat store's own key handling may or may
not refuse it. The case the order exists for, the absent-container write, is
reached by no conformance fixture, so it is pinned per backend.

Decide it instead on the key's addressable segments: drop empty and `"."`
segments, and refuse when nothing is left. That covers `""`, `"."`, `"./"`,
`".//"`, `"./."` and `"/"`.
`remote_store.backends._flat_ns._addressable_segments` is the shared
implementation; `GraphBackend` reaches it through its own `_key_segments`.

**The rule stops at the slash-and-dot spellings, and the bound is deliberate.**
`RemotePath._normalize` folds `\` to `/` before dropping segments, so it calls
`"\"` the root as well, and a draft of this clause required the same here. That
was withdrawn on measurement. The shared predicate is also how `GraphBackend`
builds every item address, so folding made `native_path("a\b")` address the same
node as `native_path("a/b")`: two distinct keys collided onto one address, and
`a\b` became unaddressable as itself.

**The cost is the collision, not a BE-025 breach**, and the distinction is worth
stating because the first version of this paragraph got it wrong. `\` is
excluded from `WellFormedPath` by PATH-002, so a backslash key is not canonical
and [BE-025](#be-025-native_path)'s round-trip identity never covered it —
`LocalBackend.to_key` folds `\` to `/`, for that reason, and is conformant.
What the fold broke is the rule this clause is about: a predicate deciding
*refusal* and a predicate deciding *addressing* were made one function, and
widening it moved the addressing. The reach is narrower than "any POSIX key with
a backslash" and the class of error is the one that matters here.

So a backslash-only key is **not** refused by this clause. It is the milder
failure of the two — on a POSIX namespace it lands a file named `\` inside the
container rather than occupying it — and it is stated here rather than closed,
because closing it costs the addressing contract. A backend wanting to refuse it
must do so without widening the predicate its addressing depends on. A class on
the kernel does exactly that: [BE-030](053-contract-kernel.md#be-030-key-rule-on-the-kernel) refuses a
backslash on every operation, as a validation rule rather than a root rule, while
its addressing passes the key raw.

**The obligation this leaves is a normative one: within a backend, whether a key
names a node and *which* node it names are decided by one predicate.** Both ways
of breaking that were measured on `GraphBackend` in the change that added this
clause. Widening the shared predicate for the guard's sake moved its addressing,
which is the withdrawal above. Narrowing it for addressing's sake is the same
defect mirrored: its `move`/`copy` destination address split on a predicate that
kept `"."`, so `"./x"` passed the destination guard and then named a folder
literally called `.` while `write("./x")` wrote to the root. A backend free to
split a key two ways will eventually accept a spelling at one predicate and
misplace it at the other.

`is_root` itself is deliberately **not** widened, and § "One predicate, both
spellings" above still holds for every other use of it: it has call sites in
`native_path` / `to_key`, where the addressing round-trip is defined in terms of
the canonical pair, and in the prefix construction every flat-namespace listing
uses. On the read side an unrecognised root spelling costs a wrong error class.
Here it costs the container, and the asymmetry in the rule follows the asymmetry
in the damage.

The rejection is definitional, like the root's other answers, and for the same
reason: an observational is-a-directory check answers `False` in exactly the
state — an absent container — where the guard has to hold. Where the container
cannot be occupied because the SDK refuses a zero-length key, the requirement
still bites: reaching the SDK produced a retryable class for a permanent
condition on one backend and a bare SDK message on another, both of which the
clause's opening paragraphs already forbid.

**The `move`/`copy` destination is covered too**, and the rule is the same one:
a destination that is the root is a write to the root, refused before the
transport. It is stated rather than left to follow, because the argument that it
follows is exactly what failed. On the hierarchical backends the destination was
once refused by observation: the destination probe reports a directory, but
only once the source has been found. With a missing source the source check
answers `NotFound(src)` first, whether or not the container is present, and so
breaches [BE-018](#be-018-move)'s root-destination carve-out. And that
reasoning does not survive the move to a flat namespace, where nothing is
observed: measured, `move(src, ".")` on the direct-boto3 lane **returned cleanly
and deleted the source**, and the s3fs lane answered `AlreadyExists` for a
destination that does not exist. A clause whose scope depends on a per-namespace
reachability argument is a clause that is wrong on the namespace nobody checked.

**Out of scope:** `delete_folder("")`, which is governed at the `Store` layer
(STORE-002) — backend behaviour for it is undefined by this clause, except on a
class on the kernel, where [BE-031](053-contract-kernel.md#be-031-delete_folder-on-the-kernel) refuses
it with `InvalidPath`. Note
`delete("")` is **not** out of scope — it is a file-shaped operation on a folder,
and the row above governs it.

**On the kernel:** this clause's answers are the kernel's, not the driver's.
The kernel decides the root on the canonical key, after the closed guard
([BE-030](053-contract-kernel.md#be-030-key-rule-on-the-kernel), steps 1 and 4), so every spelling
that addresses the root reaches the driver as `""`, and only for a
folder-shaped call or addressing; the probes answer the root from the key
without a driver call. The driver owes a listing of `""` (`list_page`, and
`folder_stats` where it aggregates natively) and its bare root from
`native_path("")`.

**Conformance:** `tests/backends/conformance/test_io.py::TestBackendRootPath`
and its async sibling in `test_async_extended.py`, both gated on
`Capability.LIST` and parametrised over both spellings, except the write and
`move`/`copy` destination cells, which run all six; addressing is covered by
`test_identity.py::TestBackendNativePath` (sync) and
`test_async_extended.py::TestAsyncBackendNativePath` (async).

The file-shaped-operation row is seven operations (`_ROOT_FILE_OPS`): the four
reads above plus `delete`, `move` and `copy`. `SQLQueryBackend` declares no
capability for those three, so they are gated out rather than missed.

**The write row is a second roster and deliberately not folded into that one.**
`_ROOT_WRITE_OPS` is `write`, `write_atomic` and `open_atomic` (two in the async
mirror, which declares no `open_atomic`, as it declares no `read_seekable`), plus
a companion roster for the `move`/`copy` **destination**. Separate because it is
a separate *rule*, not because its members share a gate: like the seven above,
each is paired with its own capability — `write` under `WRITE`, `write_atomic`
and `open_atomic` under `ATOMIC_WRITE`, the destination pair under `MOVE` and
`COPY`. What distinguishes the rows is what they owe. The type-mismatch row owes
an error class; these owe an error class **and the absence of a side effect**.
Their conformance cells seed a file and read it back afterwards, which is the
strongest form the "before anything is transferred" clause takes from outside a
backend — the container's own state is not observable through the `Backend` API,
and the absent-container case no fixture arranges. A backend whose
container can go absent pins that half in its per-backend home. No roster here
reaches `SQLQueryBackend`, which is read-only.

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
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`. `InvalidPath` if an ancestor of `path` exists as a regular file (file-as-directory-component). `CapabilityNotSupported` if a non-`None`, non-empty `metadata` mapping is passed and the backend lacks `USER_METADATA` (per WR-010 empty-mapping carve-out — `metadata=None` and `metadata={}` are both no-ops with respect to this gate), on a class that runs the gate itself; the order below says which do.
**See also:** [045-write-result.md](045-write-result.md) (WR-001 through WR-005, WR-010 through WR-012).
**Precondition evaluation order:** Backends MUST evaluate preconditions in this
order: the closed guard — after a terminal close the call raises
`BackendUnavailable`, ahead of every step below ([BE-020](052-backend-lifetime.md#be-020-close));
(0) the root — if `path` is the store root, raises `InvalidPath`, decided
from the key and before any request is issued ([BE-029](#be-029-root-path));
the metadata gate — a non-empty `metadata` on a class without `USER_METADATA`
raises `CapabilityNotSupported` (WR-010). A class that runs the gate itself runs
it here, as every class on the kernel does
([BE-030](053-contract-kernel.md#be-030-key-rule-on-the-kernel)). A class that leaves the gate to
`Store` (e.g. `LocalBackend`) does not raise it, and `Store` runs it before the
backend is called;
(1) path validity — if `path` names an
existing *directory* OR any slash-aligned ancestor of `path` is a regular file
(file-as-directory-component), raises `InvalidPath`; (2) overwrite
conflict — if the file exists and `overwrite=False`, raises `AlreadyExists`;
(3) I/O. No later check may mask an earlier one. This order applies to `write()`,
`write_atomic()`, `move()`, and `copy()` wherever analogous preconditions exist.
For `move`/`copy`, step (0) binds **both** ends: the source as the file-shaped
operation it is, and the destination as the write it is.
Step (0) is numbered rather than folded into (1) because it is the one step no
backend is exempt from: the flat-namespace exemption below releases (1), and a
backend taking it still owes the root refusal, which needs no round trip and no
namespace concept to decide.
**The two ends owe different predicates, and the asymmetry is deliberate.** The
write end — the three writers and the `move`/`copy` destination — must refuse
**every spelling that addresses the root**, which is wider than `is_root`; see
[BE-029](#be-029-root-path), which states why a guard written as
`if is_root(path)` is not conformant there. The source end is required only to
refuse `is_root`. Seven of the eleven `WRITE`-capable classes meet that through
the shared `_reject_root_as_file`, which is exactly `is_root`; the other four
refuse the source under the **wider** predicate: `GraphBackend` and
`SQLBlobBackend` as a by-product of their own key splitters, and
`MemoryBackend` and `AsyncMemoryBackend` by the kernel's key rule
([BE-030](053-contract-kernel.md#be-030-key-rule-on-the-kernel)), so `move("./", dst)` raises there
and not on the seven. That
divergence is permitted: the floor is `is_root` and a backend MAY exceed it.

**What an unrecognised root spelling costs on the read side, stated rather than
assumed.** The usual summary is "a wrong error class". That is not the whole of
it, and the difference matters because this summary is the justification for
leaving `is_root` unwidened. Measured over `exists` / `is_folder` /
`list_files(recursive=True)` on a root holding two files: `LocalBackend` and
`MemoryBackend` answer `True / True / 2` under all three of `""`, `"."` and
`"./"`; `SQLBlobBackend` answers `True / True / 2` for the first two and
**`True / True / 0`** for `"./"` — the probes agree the folder is there and the
listing comes back empty. So the read side can cost a silently wrong *value*.
It remains the milder failure — the write side cost a container — and
the reason not to widen `is_root` here is its blast radius, not the harmlessness
of the read side: it is also how addressing, `to_key` and every flat-namespace
listing prefix decide the root.
**Flat-namespace exemption:** Backends where the underlying storage has no
native directory concept (e.g. S3, Azure non-HNS, SQL) are exempt from step
(1): they cannot distinguish "path names a directory" from "path does not
exist", so they MUST skip the type-conflict check entirely. The file-ancestor
rejection is similarly exempt on flat-namespace backends by
default — they cannot detect a file-ancestor in O(1) without an extra HEAD
round trip per slash-aligned ancestor. The gate ships as an opt-in
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
effective order is the order above with step (1) skipped.
**On the kernel no backend takes this exemption.** A class on the kernel
refuses a write below a file and a write of a file over a folder on every
namespace, unconditionally ([BE-032](053-contract-kernel.md#be-032-the-store-tree-on-the-kernel)'s
A.4), so the opt-in walk and its fail-open sentence below bind only the
classes not on the kernel.
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
(the closed guard `!Live() → BackendUnavailable` (BE-020) and the
root refusal `AddressesRoot(path) → InvalidPath` (BE-029) first, then the
WR-010 strict gate (`HasUserMetadata(metadata) ∧ CapUserMetadata !in
capabilities → CapabilityNotSupported`, with empty-mapping carve-out encoded
by `HasUserMetadata`, and an unchanged-state frame; BE-030 holds it ahead of
any I/O), then `IsDir → InvalidPath`, `!AllAncestorsTraversable → InvalidPath`,
`IsFile ∧ !overwrite → AlreadyExists`), the WR-001a schema (`r.value.path == path ∧ r.value.size
== |content|`), WR-004 (source Native iff `CapWriteResultNative`), WR-005
(Basic source → rich fields None), WR-012 metadata echo, and WR-013
round-trip (`fs[path].info.metadata` reflects what was stored). The model
promotes well-formedness to a class invariant `predicate Valid()` on the
`Backend` trait, with `requires Valid() ensures Valid()` on every mutating
method (`Write`, `Delete`, `DeleteFolder`, `Move`, `Copy`, `Close` and
`DropContainer`; the read-only methods `require Valid()` too); the file-ancestor
clause on Write is what closes the loophole that would let a successful
write break `Valid()`. Move / Copy carry the same file-ancestor clause on
their destination paths. Verified in `MemoryBackend.dfy`. The model states
the WR-010 gate for every `Backend`, so for a class that leaves the gate to
`Store` it is stricter than the order above, which binds the gate only where a
class runs it. Python backstop:
the WR-001a/004/005/012/013 postcondition chain is exercised against every
backend by `tests/backends/conformance/test_atomic.py::TestWriteResultConformance`;
the file-ancestor rejection is exercised by
`tests/backends/conformance/test_errors.py::TestWriteErrorFidelity::test_write_under_file_ancestor_raises_invalid_path`
(sync) and its async sibling in `test_async_extended.py`.

### BE-009: write Creates Intermediate Directories

**Invariant:** `write` creates any intermediate directories automatically.

### BE-010: write_atomic()

**Invariant:** `write_atomic(path, content, *, overwrite=False, metadata=None) -> WriteResult` writes via a temporary file + atomic rename and returns a `WriteResult`.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`. `CapabilityNotSupported` if a non-`None`, non-empty `metadata` mapping is passed and the backend lacks `USER_METADATA` (per WR-010 empty-mapping carve-out), on a class that runs the gate itself, as BE-008 scopes it.
**Precondition order:** [BE-008](#be-008-write)'s, every step of it, from the closed guard and the root through I/O. Flat-namespace exemption from BE-008 applies, except on the kernel, where no backend takes it ([BE-032](053-contract-kernel.md#be-032-the-store-tree-on-the-kernel), A.4).
**See also:** [007-atomic-writes.md](007-atomic-writes.md); [045-write-result.md](045-write-result.md) (WR-001, WR-010).
**Formal coverage:** Delegates to BE-008 — at the Backend-contract level
`write_atomic` shares the `Write` postcondition model (return type, precondition
order, WR-010 gate, WR-001a/004/005/012/013 postcondition chain). Atomicity
itself is a frame-condition property outside Dafny's expressiveness (see
`sdd/formal/README.md` § Design decisions, "No error-path frame condition"). No
separate `WriteAtomic` method exists in `BackendContract.dfy`. Python backstop:
the Python conformance suite parametrizes `TestWriteResultConformance` over
both `write` and `write_atomic`, so `write_atomic` carries the same
postcondition-chain coverage as `write`.

### BE-011: write_atomic Capability Gate

**Invariant:** `write_atomic` raises `CapabilityNotSupported` if the backend lacks `ATOMIC_WRITE`.

### BE-012: delete()

**Invariant:** `delete(path, missing_ok=False)` removes a file.
**Raises:** `NotFound` if the file is missing and `missing_ok=False`. `InvalidPath` if `path` names a directory, regardless of `missing_ok` — type errors are not silenced by missing-path tolerance (Dafny: `Delete: IsDir → InvalidPath` whatever `missing_ok` is). See BE-021.
**Postconditions:** If `missing_ok=True`, no error for missing files.
**Absent container:** A missing bucket, container or table counts as a missing file, so `missing_ok=True` returns cleanly and `missing_ok=False` raises `NotFound` — see [BE-021](#be-021-error-mapping) § "An absent container reads as an absent path" for the rule, its stated reach, and its cost model. It binds every backend in scope, with no carve-out. Modelled in `sdd/formal/BackendContract.dfy`: `containerPresent` with `DropContainer`, and a `Delete` postcondition for the absent state, verified in `MemoryBackend.dfy`; the per-backend absent states are pinned in Python.

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
`Live() && (!PathExists(fs, path) || !AllAncestorsTraversable(fs, path)) ==> r == Ok([])`
(the `Live()` guard is BE-020's; the model also has
`Live() && !containerPresent ==> r == Ok([])` for BE-021 § Reach);
the completeness postcondition's guard widened symmetrically from
`PathExists(fs, path)` to `PathExists(fs, path) && AllAncestorsTraversable(fs, path)`,
relaxing the implementer obligation in the same malformed-fs slice — both
changes together keep the model satisfiable. The model promotes fs
well-formedness to a class invariant `predicate Valid()` on the `Backend`
trait, so the `!AllAncestorsTraversable` disjunct is a **logical
consequence** of `Valid()` rather than a defensive postcondition against an
unreachable state: a successful `Write` (or `Move`/`Copy` to a non-existent
destination) that would otherwise insert a `FileEntry` under a file-ancestor
is rejected pre-I/O via the `!AllAncestorsTraversable(old(fs), path)`
clause on those methods (see BE-008). Verified in `MemoryBackend.dfy`.

### BE-015: list_folders()

**Invariant:** `list_folders(path)` returns `Iterator[FolderEntry]` of immediate subfolders.
Each `FolderEntry` has `.name` (folder name) and `.path` (backend-relative `RemotePath`).
**Missing-path behavior:** If `path` does not exist, does not name a folder,
or has a non-traversable ancestor, the iterator yields nothing. `list_folders()`
MUST NOT raise `NotFound` for missing or non-existent paths.
**Formal coverage:** `list_folders()` is modelled in
`sdd/formal/BackendContract.dfy` as `ListFolders`, with the same
two-sided ancestor-traversability gating as BE-014 above (early-return
disjunct plus completeness conjunction). Under the `Valid()` class
invariant, the `!AllAncestorsTraversable` disjunct is a logical
consequence rather than a defensive postcondition (see BE-014). Verified
in `MemoryBackend.dfy`.

### BE-016: get_file_info()

**Invariant:** `get_file_info(path)` returns `FileInfo`.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if the path names a directory (Dafny: `GetFileInfo: IsDir → InvalidPath`). See BE-021.
**Formal coverage:** `get_file_info()` is modelled in
`sdd/formal/BackendContract.dfy` as `GetFileInfo` with postcondition
`IsFile → r.Ok? ∧ r.value == fs[path].info` (under BE-020's `Live()`
guard, see there). The extended `FileInfo`
datatype carries the optional `digest`, `etag`, `last_modified`, and
`metadata` fields (no `version_id` — only `WriteResult` does in v1), so
the WR-013 round-trip (metadata survives `write → get_file_info`) and
the WR-008 field mapping to `head()`-produced `WriteResult` are
discharged structurally. Verified in `MemoryBackend.dfy`.

### BE-017: get_folder_info()

**Invariant:** `get_folder_info(path)` returns `FolderInfo`.
**Raises:** `NotFound` if the path does not exist. `InvalidPath` if the path names a file (wrong type — use `get_file_info` instead). See BE-021.
**Flat-namespace backends are not exempt**: when the prefix listing comes back empty they probe the exact key and raise `InvalidPath` rather than `NotFound`. See [BE-021](#be-021-error-mapping) for the shared error-path rule and its cost model.
**Root:** `get_folder_info("")` aggregates over the whole store rather than raising — see BE-029.
**`modified_at` on a class on the kernel:** the latest known modification time of any file under the folder, recursively. A file whose time is the unknown sentinel (`datetime.min` in UTC, `FileInfo.modified_at`'s "cannot know") is skipped, and a folder with no known time answers `None`. The kernel computes it over a listing; a driver that aggregates natively returns the same value. Backends not on the kernel are outside this sentence.
**Formal coverage:** `get_folder_info()` is modelled in `sdd/formal/BackendContract.dfy` as `GetFolderInfo` with postconditions `IsFile → InvalidPath`, `!PathExists → NotFound`, `IsDir → Ok`, `file_count == |ChildFiles(fs, path)|`, and `total_size == SumSizes(fs, ChildFiles(fs, path))`, each under BE-020's `Live()` guard; also an absent-container clause (BE-021 § Reach): the root aggregates to zero, any other path is `NotFound`. Verified in `MemoryBackend.dfy`. Property-based aggregate coverage against the compiled Dafny oracle lives in `tests/test_pbt_folder_info_aggregates.py`.

### BE-018: move()

**Invariant:** `move(src, dst, overwrite=False)` renames/moves a file.
**Raises:** `NotFound` if `src` does not exist. `InvalidPath` if `src` names a directory, if `dst` names an existing directory (cannot overwrite a directory with a file; binds hierarchical backends and every class on the kernel, per [BE-021](#be-021-error-mapping)'s backend scope of the type-mismatch rows), or if an ancestor of `dst` exists as a regular file (file-as-directory-component on dst — flat-namespace backends opt in to the dst-side ancestor walk via the `reject_write_under_file_ancestor` kwarg, same shape as BE-008). `AlreadyExists` if `dst` names an existing file, `overwrite=False`, and `src != dst` — self-move on a file is a no-op (Dafny: `Move: src == dst → Ok`); self-move on a directory still raises `InvalidPath` per the precondition ordering in BE-008. See BE-021 and BE-008 for precondition evaluation order.
**Precondition order:** `src`-NotFound takes priority over dst-side preconditions; specifically `move(missing_src, blocked_dst)` MUST raise `NotFound(src)` rather than `InvalidPath(dst)`. `LocalBackend.move` enforces this naturally (the `mkdir_parents` walk that catches the file-ancestor case runs after the src-exists check); flat-namespace backends running the opt-in MUST defer the `_check_no_file_ancestor(dst)` walk until after the src-NotFound probe to match. This order is pinned to remove the cross-backend ambiguity that existed under BE-018 alone. **One dst-side check outranks src-NotFound: a `dst` that addresses the store root.** [BE-029](#be-029-root-path) decides it from the key before any request, so `move(missing_src, "")` MUST raise `InvalidPath(dst)`; a `src` that is the root is refused first, as `InvalidPath(src)`. "Is the root" there is `is_root`, the source end's floor: [BE-008](#be-008-write)'s two-predicate paragraph lets a backend refuse a wider source spelling first, and does not require it. That is the order the backends measured for it already take (`MemoryBackend`, `AsyncMemoryBackend` and `LocalBackend`, both root spellings, `move` and `copy`; `SFTPBackend`'s is pinned by `test_move_and_copy_destination_cannot_reach_the_corruption`), and the one `sdd/formal/BackendContract.dfy` verifies.
**On the kernel:** the flat-namespace opt-in walk named here does not exist. A class on the kernel refuses a destination below a file or over a folder on every namespace, unconditionally, in BE-018's order: on a flat namespace by its own checks after the source check, on a hierarchical one by typing the wire's refusal ([BE-032](053-contract-kernel.md#be-032-the-store-tree-on-the-kernel), A.4 and A.8).
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
drops metadata fails to verify. Verified in `MemoryBackend.dfy`.

### BE-019: copy()

**Invariant:** `copy(src, dst, overwrite=False)` duplicates a file.
**Raises:** `NotFound` if `src` does not exist. `InvalidPath` if `src` names a directory, if `dst` names an existing directory (on the backends BE-018 names), or if an ancestor of `dst` exists as a regular file (file-as-directory-component on dst — flat-namespace backends opt in to the dst-side ancestor walk via the `reject_write_under_file_ancestor` kwarg, same shape as BE-008). `AlreadyExists` if `dst` names an existing file, `overwrite=False`, and `src != dst` — self-copy on a file is a no-op, not an error (Dafny: "Self-copy (src == dst) is a no-op, not AlreadyExists"); self-copy on a directory still raises `InvalidPath` per the precondition ordering in BE-008. See BE-021.
**Precondition order:** Same as BE-018 — `src`-NotFound takes priority over dst-side preconditions, so `copy(missing_src, blocked_dst)` MUST raise `NotFound(src)` rather than `InvalidPath(dst)`, except for a `dst` that addresses the store root, which BE-018 ranks ahead of it.
**On the kernel:** the flat-namespace opt-in walk named here does not exist. A class on the kernel refuses a destination below a file or over a folder on every namespace, unconditionally, in BE-018's order: on a flat namespace by its own checks after the source check, on a hierarchical one by typing the wire's refusal ([BE-032](053-contract-kernel.md#be-032-the-store-tree-on-the-kernel), A.4 and A.8).
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
drops metadata fails to verify. Verified in `MemoryBackend.dfy`.

### BE-021: Error Mapping

**Invariant:** Backend-native exceptions never leak. All exceptions are mapped to `remote_store` error types.

**Canonical error mapping table:** The following cross-cutting scenarios MUST
map to the specified error type regardless of backend:

| Scenario | Required error type |
|----------|---------------------|
| File operation (e.g. `read`, `write`, `delete`, `get_file_info`, `move`/`copy` src or dst) on a path that is a directory | `InvalidPath` |
| Directory operation (e.g. `delete_folder`, `get_folder_info`) on a path that is a file | `InvalidPath` |
| Operation on a non-existent path | `NotFound` |
| Operation denied by credentials or ACL | `PermissionDenied` |
| Parent directory creation fails (permissions) | `PermissionDenied` |
| Parent directory creation fails (path conflict) | `InvalidPath` |

A `move`/`copy` destination that is a file is not a type mismatch: it is the overwrite conflict of [BE-018](#be-018-move) and BE-019, `AlreadyExists` without `overwrite`. A destination below a file is the path-conflict row.

The type-mismatch rule (`InvalidPath`) takes precedence over the existence rule (`NotFound`) — a directory path is not "missing", it is the wrong type. This is machine-verified in `sdd/formal/BackendContract.dfy` (`Read`, `Delete`, `DeleteFolder`, `GetFileInfo`, `GetFolderInfo`, `Move`, `Copy` postconditions).

**Backend scope of the two type-mismatch rows.** They bind every backend on the
operations that can *fail* on a wrong-typed path: `read`, `read_bytes`,
`read_seekable`, `delete`, `get_file_info`, `delete_folder`,
`get_folder_info`, and the `move`/`copy` **source**. Their write half —
`write`, `write_atomic`, `open_atomic`, and the `move`/`copy` **destination** —
binds hierarchical backends only. On a flat namespace a write to a key that
shadows a prefix succeeds, so there is no error to reclassify; BE-008's
flat-namespace exemption governs there instead, unchanged. On the kernel the
write half binds every namespace too
([BE-032](053-contract-kernel.md#be-032-the-store-tree-on-the-kernel), A.4). This is the single
roster for both halves; the clauses below explain the mechanism behind the
split and what it costs, and do not restate it.

**Scope note:** This table covers *cross-cutting* scenarios that apply to multiple operations. Method-specific errors (e.g. `DirectoryNotEmpty` from `delete_folder`, `CapabilityNotSupported` from capability-gated operations) are documented per-method and intentionally omitted here.

**On the kernel, each obligation has two halves.** For a class on the kernel the
table below assigns each obligation of this clause to the kernel or to its
driver; the obligations themselves, and the prose stating them, are unchanged.
A class not on the kernel discharges both halves itself.

| Obligation | Kernel | Driver |
|---|---|---|
| Native exceptions never leak (the invariant) | the choke point: a `RemoteStoreError` passes, any other `Exception` goes to `classify`, and a classifier that raises or answers a non-error still yields a `RemoteStoreError` ([ERR-001](005-error-model.md#err-001-base-error), [ERR-009](005-error-model.md#err-009-meaningful-string-representations)). An error raised by the caller's own content passes verbatim ([ASYNC-091](029-async-store-backend-api.md#async-091-write-side-binaryio-failure-mid-write)) | `classify` maps its wire's exceptions |
| The type-mismatch and `NotFound` rows, and type mismatch outranking `missing_ok` | decided from the driver's observations by [BE-032](053-contract-kernel.md#be-032-the-store-tree-on-the-kernel)'s A.5 and A.8 | `stat` and `list_page` observe, and refusals keep A.8's "What drivers owe instead" |
| The `PermissionDenied` rows | passes the driver's type through | `classify` types a denial |
| Parent creation fails on a path conflict | A.8's write and `ensure_parents` rows type a refusal | a write primitive or `ensure_parents` refuses an item above the key |
| Flat namespaces' error-path obligation, fail-open probes, fail-closed determinants | A.3 and A.8 | — |
| An absent container reads as an absent path | the choke point maps a refusal `container_absent` recognises to `NotFound`, which `missing_ok` and A.8's listing rows read | `container_absent` recognises its wire's shape |
| § Reach's first-page bound | A.9, kept once per operation | `list_page` answers one `Page` per wire request |
| The root decided before the probe | BE-030's step 4 | — |
| The broad exception handler rule | `exists`, `is_file` and `is_folder` answer from `stat` | `classify` discriminates by type, `errno` or status |
| A listing's denial is about the folder it lists | — (A.7) | `list_page` raises the denial of the folder it lists |

**Flat-namespace backends: no exemption, but an error-path obligation.** A
flat namespace stores keys, not nodes, so "this path is a directory" is not an
answer the store returns — it has to be derived from a prefix listing. That
made the two type-mismatch rows above quietly optional on S3, Azure non-HNS
and SQL for a long time: those backends answered `NotFound`, or worse
succeeded (a bare prefix read as a zero-length object, a `delete` that no-oped,
a `get_folder_info` that counted the file as its own content). This clause
settles it in favour of the contract: **the two rows hold on every backend wherever an
operation can fail on a wrong-typed path** — the scope stated with the rows
above — and the divergence is a defect rather than a declared variation.

The obligation is discharged on the **error path only**. A backend derives the
type verdict when the operation has already failed to find what it needed — one
`MaxKeys=1` prefix listing for "is this a folder?", one HEAD / exact-key lookup
for "is this a file?" — and converts the miss into `InvalidPath`. A call that
*finds its target* never runs the probe, so the guarantee costs nothing on the
hot path. A class on the kernel with a flat namespace departs from that: it
also refuses the states a flat store can hold and no tree gives, so every
non-root folder operation calls `stat` on its key and every write checks the
key's ancestors and its prefix, success included
([BE-032](053-contract-kernel.md#be-032-the-store-tree-on-the-kernel), A.3 and A.4, whose cost table
lists each).

**Two cases both fail and succeed**, and both are the idempotent-delete idiom.
They cost different things, because each spends the probe its own type verdict
needs:

| Call | Miss that triggers the probe | Probe spent |
|------|------------------------------|-------------|
| `delete(path, missing_ok=True)` on an absent key | the exact-key lookup finds no object | one `MaxKeys=1` prefix listing — "is this a folder?" |
| `delete_folder(path, missing_ok=True)` on an absent prefix | the prefix listing comes back empty | one HEAD / exact-key lookup — "is this a file?" |

In both the probe runs and the call then returns cleanly, because `missing_ok`
tolerates the miss; in a delete loop that is one extra round trip per absent
path. A class on the kernel departs from the first row: its flat `delete`
error path asks `stat` before the listing, two round trips, since a refusal
may meet an existing file as well as a missing one; its costs are in
[BE-032](053-contract-kernel.md#be-032-the-store-tree-on-the-kernel)'s cost table. Neither is avoidable by testing `missing_ok` first: `delete(folder,
missing_ok=True)` and `delete_folder(file, missing_ok=True)` must still raise
`InvalidPath` (see "Type mismatch outranks `missing_ok`" below), and after a
miss the probe is the only thing separating *this is the wrong type* from *this
is genuinely absent*. Skipping it would restore the silent success this clause
exists to remove, so the cost is the price of the verdict, not an oversight.
The probe is **fail-open**: if it errors (503, throttling, network blip) the
operation's original error stands rather than being replaced by a transport
error, the same posture the file-ancestor walk takes (see BE-008).

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
them from breaching. `write` is the one operation *on the roster* this clause
does not decide, and the permission that leaves is now narrower than it was: a
backend spec may decide what `write` does against an absent container, as
[GR-031](044-graph-backend.md#gr-031-404-discrimination-item-vs-drive) does for
`GraphBackend` ([ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md)),
but **not what it does when the target is the root** — [BE-029](#be-029-root-path)
decides that, for every backend, and decides it specifically for the
absent-container state. So the sentence divides: a backend answering `write` its
own way for a key *under* the container contradicts nothing here; one answering
the root key its own way contradicts BE-029. Anything *off* the roster — a health probe, a
credential or container-identity lookup — is not an operation this section
reaches at all, so it needs no such permission and is not counted against this
one. All of these obligations are pre-existing — this
clause neither creates nor relaxes them, and that is why those operations are
absent from the roster above rather than exempt from it.

**The empty listing is an answer about a container that was absent when the
listing began.** A listing that has already received a page has been told the
container exists; a container 404 arriving on a *later* page therefore reports a
deletion that happened underneath the scan, not an absence, and a backend MUST
let it propagate rather than end the iteration. Returning early there hands the
caller a short listing indistinguishable from a complete one — the caller most
harmed being the one diffing a listing against local state and deleting the
difference, which is a data-loss shape rather than an error-reporting one.

The bound is on the **page**, not on what the operation yielded from it. Every
listing discards part of a page — `list_files` drops common prefixes, directory
markers and anything past `max_depth`; `list_folders` drops keys; `glob` drops
non-matches — so a backend keying the bound on a yielded item goes blind exactly
where a page's contents are all filtered away, and those are ordinary page
shapes: a container organised into folders returns a first page of nothing but
prefixes.

Backends whose listing API exposes no page boundary may satisfy this by marking
each item the service returned *before* its own filters run; the residue is a
truncated page carrying no items at all, which MUST then be stated in that
backend's spec as a declared variation rather than left implied. That licence
is for a class not on the kernel: a driver answers the kernel in `Page`s, so a
migrated class has no unmarked page, and the kernel keeps the bound (BE-032's A.9).

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

That extends to the two operations this paragraph leaves to a backend or counts
only as a source. **`write` on the root** is decided by BE-029 rather than left
open, and the `move`/`copy` **destination** — which § Reach's roster counts only
as a source — is decided there too: both raise `InvalidPath` from the key, before
the request, whether or not the container exists. A backend spec may still decide
what `write` does against an absent container for a key *under* it; the root key
is not its to decide.

Stated here because this is where a reader looking for per-operation answers
lands, and following it alone yields the wrong answer for one path in every
operation it names.

**§ Reach's roster is twelve operations, and its siblings are not silently
included.** The twelve are the two tolerant deletes plus the ten § Reach
names, counting the `move`/`copy` source as one.

`read_bytes`, `read_seekable`, `iter_children` and `glob` are not among them.
Each is a thin variant of one that is — `read`, `list_files`, `list_folders` —
and a backend that answers a named operation one way and its variant another has
a defect rather than a permission. But that is a *reading*. A
backend spec relying on the reading should say so, as
[SQL-BLOB-050](040-sql-blob-backend.md#sql-blob-050-exception-translation) does.

**"Roster" is used twice in this section and the two sets differ.** The
type-mismatch rows above have their own roster — the one their scope paragraph
calls "the single roster for both halves", which *does* name `read_bytes` and
`read_seekable`, and which the "`read_seekable` is in the list" paragraph is
about. This paragraph is about § Reach's roster only. Neither is wrong; a reader
meeting the word in one place and the membership claim from the other is.

The absent-container rule exists because leaving it unstated let each backend answer from
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
raising `InvalidPath` — and for the listing entries the next paragraph names.
All other operations MUST raise appropriate errors.

**A listing's denial is about the folder it lists, not about an entry's link
target.** `list_files`, `list_folders` and `iter_children` raise
`PermissionDenied` when the backend is refused the folder they list, a subfolder
a recursive listing descends into, or the metadata of an entry. They skip an
entry gone before its metadata was read, a dangling link, a link loop, and a
link (a symlink, or on Windows a directory junction) whose target the backend
is refused: the link is present and readable as a link, and only its target is
refused, so the listed folder was not. The folder a listing is asked for is not
an entry: asked for such a link itself, the listing is refused the folder it
lists, and raises. The clause decides links only where a backend's listings
follow them, as `LocalBackend`'s do.

### BE-022: unwrap()

**Invariant:** `unwrap(type_hint)` returns the native backend handle if it matches the requested type.
**Raises:** `CapabilityNotSupported` if the backend cannot provide the requested type.
**On the kernel:** `unwrap` takes the closed guard, so after a terminal close it raises `BackendUnavailable` ([BE-033](052-backend-lifetime.md#be-033-interaction-protocol-on-the-kernel)).
**Rationale:** See [ADR-0003](../adrs/0003-fsspec-is-implementation-detail.md).

### BE-023: to_key()

**Invariant:** `to_key(native_path)` converts a backend-native or absolute path to a backend-relative key by stripping the backend's own root/prefix. The default implementation is the identity function.
**Postconditions:** Pure, deterministic, total (never raises). If the input path does not start with the backend's root, it is returned unchanged.
**See also:** [010-native-path-resolution.md](010-native-path-resolution.md) (NPR-003 through NPR-009), [ADR-0005](../adrs/0005-native-path-resolution.md).

### BE-025: native_path()

**Invariant:** `native_path(path)` converts a backend-relative key to the backend-native path. The inverse of `to_key()`: `backend.to_key(backend.native_path(key)) == key`. The default implementation is the identity function — backends with a native root **must** override.
**Root spellings:** `native_path("")` and `native_path(".")` return the same value, the bare backend root (BE-029). The round-trip identity therefore returns the canonical root key — `to_key(native_path("."))` is `""` — since one native path cannot invert to two spellings. Every non-root key **in canonical form** round-trips verbatim; a non-canonical one need not, and for the same reason — `native_path` normalises, and one address cannot invert to the several keys that produced it. Every lossy class is one `WellFormedPath` (PATH-002 through PATH-008) already excludes, though not every exclusion is lossy — `".."` segments and null bytes are excluded and do round-trip verbatim. The lossy ones are: a redundant `"."` segment, an empty segment (leading, trailing or doubled slash), and on backends that fold it, a backslash. Measured on `GraphBackend`, `native_path("a/./b")`, `native_path("dir/")`, `native_path("a//b")` and `native_path("/a")` each invert to the canonical key rather than the caller's spelling. So the identity is exact over the keys `to_key` produces and over every canonical key, and lossy over the wider set a caller holding a `Backend` directly may hand `native_path`. The identity-default implementation normalises both root spellings for the same reason.
**Postconditions:** Pure, deterministic, total (never raises). The returned path is usable with the native handle from `unwrap()`.
**On the kernel:** a class on the kernel normalises a key before its driver addresses it and passes a refused key raw, so a non-canonical key inverts to its canonical form and a `..` or null-byte key round-trips verbatim; the rule is [BE-030](053-contract-kernel.md#be-030-key-rule-on-the-kernel)'s **Addressing stays total**.
**Overrides:** `LocalBackend` (prepends root dir), `S3Backend` (prepends bucket), `S3PyArrowBackend` (prepends bucket), `SFTPBackend` (prepends base_path), `AzureBackend` (prepends container), `MemoryBackend` and `AsyncMemoryBackend` (the kernel's normalisation, over a driver whose `native_path` is the identity on a canonical key).
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
**On the kernel:** a class on the kernel refuses and normalises the pattern by the rule and order [BE-030](053-contract-kernel.md#be-030-key-rule-on-the-kernel) states, so the driver receives a canonical pattern.
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
