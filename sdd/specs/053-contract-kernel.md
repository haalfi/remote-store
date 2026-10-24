# 053: Contract Kernel Specification

## Overview

What a class on the contract kernel answers that the Backend contract leaves to
the backend: how it validates and normalises a key, how it removes a folder,
and how it gives the store tree's answer from what its driver observes. These
are single-call clauses ([`SPEC-DESIGN.md` Rule 2](../SPEC-DESIGN.md#kind-of-truth))
at two interfaces: most state what a caller of a class on the kernel observes,
and the driver duties state what the kernel requires of its driver.

Scope: BE-030 to BE-032, binding a class on the kernel and the driver beneath
it. Out of scope: the Backend contract every backend meets, which is
[spec 003](003-backend-adapter-contract.md)'s; the states between calls,
including the kernel's interaction protocol (BE-033), which are
[spec 052](052-backend-lifetime.md)'s; and the store tree itself, which is
[spec 051](051-store-tree.md)'s.

## Terms

- **Class on the kernel**, **driver**: as § Contract kernel below defines them.
- **Store tree**, **Key**, **Item**, **Folder**: [spec 051](051-store-tree.md)'s,
  as BE-032's A.1 uses them.
- **Encoding**, **raw key**, **determinant**, **probe set**: as BE-032's A.1,
  A.2 and A.8 define them.

---

## Contract kernel

The clauses below bind a **class on the kernel**: a backend implemented as the
contract kernel (`DriverBackend` / `AsyncDriverBackend`, public in
`remote_store.drivers` with the driver protocols) over a driver of wire
primitives, per
[RFC-0017](../rfcs/rfc-0017-contract-kernel-over-thin-drivers.md) D1 and D2 and
[ADR-0042](../adrs/0042-contract-kernel-over-thin-drivers.md). `MemoryBackend`
and `AsyncMemoryBackend` are the first such classes. Each clause states, once,
an answer the clauses of [spec 003](003-backend-adapter-contract.md) leave to the backend. A backend not on
the kernel is unaffected by them. The decisions behind what a key resolves to
and how a refusal is typed are recorded in [RFC-0021](../rfcs/rfc-0021-key-resolution-model.md), which BE-032 lands.

### BE-030: Key Rule on the Kernel

**Invariant:** a class on the kernel validates and normalises every key an
operation names before its driver sees it, and decides the root on the result.
An operation's driver call receives only canonical keys: no leading `/`, no
empty, `.` or `..` segment, no null byte, no backslash, and `""` for the root.
The addressing members are the one exception, stated under **Addressing stays
total** below.

**Pipeline, per operation**, in this order:

1. The closed guard (BE-020), when the driver declares `close_is_terminal`. The
   class's own `close_is_terminal` must be the driver's; the kernel refuses to
   construct over one that differs. `unwrap` takes it too, and the states
   around it are [BE-033](052-backend-lifetime.md#be-033-interaction-protocol-on-the-kernel)'s.
2. Refusals, raising `InvalidPath`: a key starting with `/`, a `..` segment, a
   null byte, a backslash.
3. Normalisation: empty and `.` segments are dropped, so `//`, `/./` and a
   trailing `/` fold and every root spelling becomes `""`.
4. The root check on the canonical key, where `""` is the root.
5. The driver, with the canonical key. For a write the result's path is built
   from that key **before** the driver commits, so no key the kernel accepts can
   fail after the bytes land.

**Gates around the pipeline.** A declared-capability gate comes before step 1,
closed or not, since capability data is not a live operation: `GLOB` for
`glob` (the pattern rule below), `ATOMIC_WRITE` for `write_atomic` and
`open_atomic` (BE-011), `MOVE` for `move` and `COPY` for `copy`, a
self-operation included, each refused with `CapabilityNotSupported` by the
declaration, whatever protocols the driver presents. The kernel refuses to
construct over a declaration its protocols cannot back, and over a driver that
leaves a primitive out or inherits the protocol's own body for one, which would
answer `None` instead of acting. `probe`'s inherited body is the one exception,
being the exemption from probing (PING-008); a `probe` left out is refused like
any other. WR-010's metadata gate
on `write` and `write_atomic` comes after step 4 and before step 5, where
BE-008's order puts it: after the root refusal and ahead of any I/O.
Shape comes first within it, as WR-011 orders it: `metadata` that is neither
`None` nor a `Mapping`, a falsy one included, is refused with `ValueError`
whatever the class declares, and only then is a non-empty mapping refused for
want of `USER_METADATA`.
That ranks it ahead of BE-008's type, ancestor and overwrite checks: on a class
without `USER_METADATA`, a write carrying metadata answers
`CapabilityNotSupported` with a folder at the key, a file above it, or an
existing file and `overwrite=False`, on both namespaces. Ranking it after those
checks instead would cost every such write a `stat` on a hierarchical namespace, and on
a flat one would put I/O ahead of the gate. `BackendContract.dfy`'s `Write`
states the same order.

**Content.** A driver receives only the types its `put` declares. A
`bytearray` or `memoryview` passed to `write` or `write_atomic` reaches it as
a `bytes` copy, and so does a buffer a content stream (or, async, its iterator)
yields. Content that is no bytes source, neither a buffer nor a readable stream
(async: an async iterator), is refused with `TypeError` after WR-010's gate and
before any I/O, on `write` and `write_atomic` alike; a buffer that cannot be
read as `bytes` (a released `memoryview`) fails at the same rank with its own
error, and so does content whose `read` (async: `__aiter__`) cannot even be
looked up. A stream that yields something not binary, `None` included (a
non-blocking stream's "no data available"), or whose `readinto` answers anything but
a count or `readlines` anything but a list, raises `TypeError` when read; one
that yields a buffer that cannot be read as `bytes` raises that buffer's error.
Either is the caller's own error, passed through verbatim like ASYNC-091's and
never classified. Async content is checked chunk by chunk whatever the driver
does. On sync the stream a driver receives answers an unsized `read` (no size,
`None` or a negative one) and `readall` by sized reads of the caller's stream,
each checked, so a driver that reads its content in full sees the `None` a raw
stream's own `readall` would stop at. Line reads (`readline`, `readlines`,
iteration) loop inside the caller's stream, where the kernel cannot see a
`None`, and are not covered. A check on the target made before the stream is
read answers first, such as `write_atomic`'s `stat` by temp and rename without
`overwrite`. The stream `open_atomic` yields takes a write as Python's binary
files do, on the wire temporary's route and the spool's alike: a buffer that is
not C-contiguous is refused with its exporter's own error, `BufferError` for a
`memoryview`.

**What a key resolves to** is [BE-032](#be-032-the-store-tree-on-the-kernel)'s
answer, for every call below: the tree's `Item`, `Folder` or `Nothing` (A.1),
each family's result (A.5), the determinants a call runs whether or not it
fails, and the error-path probes that type a driver refusal (A.8). On the
kernel, BE-008's "no native directory concept" is the flat namespace, and the
kernel refuses to construct over a flat driver with folder objects (`parents`
other than `"none"`), whose `stat` could not see them, and over an
explicit-parents driver without `ensure_parents`, which could not create a
write's parents (BE-009). What stays here is what is specific to one call:

- *A write target* (`write`, `write_atomic`, `open_atomic`, the `move`/`copy`
  destination). Where the kernel stats the target first (`write_atomic` by temp
  and rename without `overwrite`, `move` by rename) that `stat` is a
  determinant: a file is `AlreadyExists` without `overwrite`, a folder or a
  file above `InvalidPath`, and a miss goes on to the wire. With `overwrite`, a
  file that check missed is replaced, or displaced and restored by a rename
  that cannot replace, never answered `AlreadyExists`, and one gone before it
  is displaced leaves the destination free for the move.
- *Two keys* (`move`, `copy`), in BE-018's order. The kernel checks the source
  first on a flat namespace, with explicit parents, on a rename route and for
  a self-operation, so the source's `NotFound` outranks BE-032 A.4's checks and
  parent creation for the destination. A refusal is answered for the source
  first, then the destination, by A.8's rows; when it stands, it names the
  destination if it is an `AlreadyExists`, or a `NotFound` or `InvalidPath`
  with the source confirmed a file.
- *An empty aggregate* (`get_folder_info`): typed as BE-017 states, by a
  determinant `stat` with folder objects and fail-open without them; on a flat
  namespace A.3's `stat` has already answered for an item.

For a key passing step 2, a canonical `""` is exactly BE-029's "addresses the
root" predicate, so every operation gets the wide predicate: the write side and
the `move`/`copy` destination as BE-029 requires, and the read side and the
source as BE-008 permits.

| Key class (examples) | Probes: `exists`, `is_file`, `is_folder` | File-shaped: `read`, `read_bytes`, `read_seekable`, `get_file_info`, `delete`, `move`/`copy` source | Write-shaped: `write`, `write_atomic`, `open_atomic`, `move`/`copy` destination | Folder-shaped: `list_files`, `list_folders`, `iter_children`, `get_folder_info` | `delete_folder` |
|---|---|---|---|---|---|
| root (`""`, `"."`, `"./"`, `".//"`, `"./."`) | the root's answer (BE-029) | `InvalidPath` | `InvalidPath` | the root folder | `InvalidPath`, refused before the driver |
| `/`-led (`"/"`, `"/./"`, `"/f"`) | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` |
| `..` segment (`"d/../f"`) | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` |
| null byte | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` |
| backslash (`"d\\f"`, `"\\"`) | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` |
| non-canonical (`"d//f"`, `"d/./f"`, `"d/"`) | the canonical key's answer | the canonical key's answer | the canonical key's answer | the canonical key's answer | the canonical key's answer |
| canonical (`"f"`, `"d/f"`) | passed through | passed through | passed through | passed through | passed through |

The `InvalidPath` of a refused probe is a refusal of the key, not a traversal
answer, so BE-004's "never raises `NotFound`" is unaffected.

**Addressing stays total** (BE-025). `native_path(key)` and `resolve(key)` run
no closed guard and never raise for the key: a key passing step 2 is normalised
and the driver receives the canonical key; a key step 2 refuses reaches the
driver raw. `resolve(key).key` is the caller's `key`, and its `native_path` is
the kernel's `native_path(key)`. `to_key` is forwarded unchanged.

**A listing never presents a key the rule would refuse or rewrite.** An entry or
common prefix a driver lists whose key is not canonical (one another tool stored,
such as `a\b`) is omitted from `list_files`, `list_folders`, `iter_children`,
`glob` and the `get_folder_info` aggregate, and the omission is logged. A driver
that aggregates natively computes that aggregate itself, so it owes the same
omission (BE-017: it returns the value the kernel would). Folding it
would name another node (`a\b` as `a/b`), which is BE-029's withdrawn fold;
raising would make every sibling unlistable. The entry stays reachable through
addressing and `unwrap()`. Since the kernel never hands such a key to its driver,
a recursive `delete_folder` that walks the tree cannot empty a folder holding
one and answers `DirectoryNotEmpty`; one the driver's `delete_tree` performs
removes it with the rest of the tree (BE-031).

**`glob(pattern)` takes the rule segment-wise over the whole pattern.** Order:
the capability first (a driver without native glob declares no `GLOB`, so
`CapabilityNotSupported`, closed or not, since capability data is not a live
operation); then the closed guard; then step 2's refusals over the raw pattern;
then step 3 for every segment, wildcard characters untouched inside their
segments, with one addition: a raw pattern ending in `/` keeps that trailing `/`
when anything remains, since in a pattern it selects directories only. A
canonical `""` names the root, a folder, and yields nothing. Worked examples:
`"./d/*.csv"`, `"d//*.csv"` and `"d/./*.csv"` reach the driver as `"d/*.csv"`;
`"d/*//"` as `"d/*/"`; `"d/*/."` as `"d/*"`; `"/d/*.csv"`, `"*/../x"` and
`"d\\*.csv"` raise `InvalidPath`.

**Conformance:** fake-driver kernel cells in `tests/_kernel/`, run against both
runtimes. Memory's cells are in `tests/backends/memory/test_kernel_cells.py`,
both classes: the root spellings' `FolderInfo`, addressing's fold of a
non-canonical key, and the backslash refusal storing nothing; and in
`tests/backends/memory/test_metadata_shape.py`, both classes: metadata that is
not a mapping refused with no parent folder made. What a key resolves to is
BE-032's two generated suites (its A.10); `glob`, the capability gates and
construction are generated over axes of their own.

### BE-031: `delete_folder` on the Kernel

**Invariant:** a class on the kernel removes folders through two driver
primitives with refusal obligations of their own, and sequences them, with its
error-path probes, in one place.

**Primitives.**

- `remove_folder(key)` removes an empty folder and refuses anything else (a
  non-empty folder, a file, an absent key) **without removing it**, in one step
  where the wire has one (`rmdir`, a lock). A driver whose `parents` is
  `"explicit"` or `"implicit"`, which has folder objects, MUST provide it; the
  kernel refuses to construct over one that does not. It is never called when
  `parents == "none"`. A folder object persists until `remove_folder` or
  `delete_tree` removes it: emptying a folder does not remove it.
- `delete_tree(key)`, optional, removes a folder's whole tree. Where folder
  objects exist it refuses a file, a link (never traversed) or an absent key
  without removing anything, removes a link below `key` as an entry without
  following it, and a wire whose tree delete also removes a file item checks
  first and documents that race. The kernel calls it with no probe before it,
  so the link refusal is the driver's: it is what keeps the table's link row
  true on this route. With `parents == "none"` it removes what lies under the
  prefix and leaves a file named by the key itself.

**`stat` and `list_page` take `follow_links`**, default `True`; `False` is a view
in which a link (dangling or not, or a Windows junction) is a non-folder entry.
`stat` is called with `False` by the three calls that name the entry at their
key: `delete`, a `move` source and `delete_folder` (BE-032 A.7);
`list_page` by `delete_folder` alone. So a link at `key` answers
`InvalidPath`, and a link below it is deleted as an entry, never traversed.
The walk lists `key` with no `stat` first, so the view is a driver obligation:
`list_page` with `follow_links=False` refuses a link at `prefix` or lists
nothing, never its target's entries, and `delete` on a link removes the link,
never its target.

**The probe rule** is BE-032's A.8: a refusal in the probe set (`NotFound`,
`InvalidPath`, `AlreadyExists`, `PermissionDenied`, untyped) gets the rows of
the call that refused, `remove_folder`, `delete_tree` (hierarchical with folder
objects, or the flat row without them) or the walk's first listing of `key`,
and every other type passes through unprobed. A probe that cannot answer leaves
the refusal standing (fail-open), and `missing_ok` applies to the answer,
replaced or standing, when it is a `NotFound`.

**The sequence.**

- *Folder objects, `recursive=False`:* `remove_folder(key)`, with no probe
  before it.
- *Folder objects, `recursive=True`, with `delete_tree`:* `delete_tree(key)`.
- *Folder objects, `recursive=True`, without it (the walk):* `list_page(prefix,
  delimiter="/")` down the tree, then every file deleted, then `remove_folder`
  deepest first and `key` last. A refusal of the first page of `key`'s
  listing is the operation's first page and gets A.8's rows; a refusal of a
  later page of `key`'s listing propagates, `missing_ok` not applying (A.9). On
  the way, a typed `NotFound` from any call below `key` (a subfolder's listing,
  a file's `delete`, a subfolder's `remove_folder`) is tolerated, the entry
  being already gone, and any other refusal propagates unprobed (A.9). Only
  the calls on `key` itself apply `missing_ok`.
- *`parents == "none"`:* on a flat namespace one `stat(key)` first, since a
  listing of `key/` cannot see an item `key` (A.3): an item answers
  `InvalidPath` and nothing is removed. Then list first, `stat` only after an
  empty listing on a hierarchical namespace. A non-recursive call lists
  `limit=1` with `delimiter="/"`; a recursive one lists with `delimiter=None`,
  `limit=1` before `delete_tree`, or paged without `delete_tree`, deleting each
  listed file and tolerating a `NotFound` on one; a listed key the listing
  omits (one BE-030 refuses, or one below a listed item, A.3) is left, and the
  call then answers `DirectoryNotEmpty`. The listing is the determinant and
  fails closed, except that a refusal of its first page is an empty listing
  where A.8's first-page row reads it so; on a later page a refusal propagates
  (A.9). After an empty listing: an item → `InvalidPath`, anything else →
  `NotFound`, to which `missing_ok` applies; a `stat` that cannot answer leaves
  `NotFound` (fail-open). A `delete_tree` refusal after a non-empty listing
  gets A.8's flat `delete_tree` row.

| Key state, folder objects | `recursive=False` | `recursive=True` |
|---|---|---|
| empty folder | removed | removed |
| folder holding files, or only an empty folder | `DirectoryNotEmpty` | removed |
| file, or a link | `InvalidPath` | `InvalidPath`, nothing removed |
| absent, or under a file (`f/x`) | `NotFound` | `NotFound` |

| Key state, `parents == "none"` | `recursive=False` | `recursive=True` |
|---|---|---|
| files under the prefix | `DirectoryNotEmpty` | removed |
| file `f`, nothing under it | `InvalidPath` | `InvalidPath` |
| a file and a prefix both (flat; decodes to no tree, A.3) | `InvalidPath`, nothing removed | `InvalidPath`, nothing removed |
| absent, or under a file (`f/x`) | `NotFound` | `NotFound` |

**A recursive delete may answer `DirectoryNotEmpty`** on a walk (either
`parents` case), when a writer adds under the tree mid-walk, or when an entry
the listing omits (BE-030, BE-032 A.3) stays behind. BE-013's prose lists the error for
`recursive=False` only, but `BackendContract.dfy`'s `DeleteFolder` (tagged
BE-013) requires a recursive delete of a present folder to succeed and remove
every child. A concurrent writer lies outside that sequential model. A stored
key BE-030 omits lies inside it, and the model now covers that state: its
recursive-success and emptiness postconditions are guarded by a
canonical-subtree predicate, `CanonicalUnder`, so the walk's `DirectoryNotEmpty` over an omitted stored key is a state the model
admits rather than a departure from it.

**The root.** `delete_folder` on any root spelling raises `InvalidPath` before
the driver is called (BE-030's table), never reaching `remove_folder`,
`delete_tree` or the walk. BE-029 leaves the root `delete_folder` undefined for
backends in general; for a class on the kernel this clause defines it.

**Conformance:** fake-driver kernel cells in `tests/_kernel/`, which enumerate the
probe rule's condition space (refusal × `stat` outcome × listing outcome ×
`missing_ok`, per context).

### BE-032: The Store Tree on the Kernel

**Invariant:** a class on the kernel answers every keyed operation as the store
tree would. The tree is [spec 051](051-store-tree.md)'s. A backend holds an
*encoding* of it, which a partial `decode` maps onto the tree; a raw state that
decodes to no tree is not in the store. The kernel's job is to give the tree's
answer from what the driver can observe of the encoding, and how much that
costs depends on the encoding, never on the answer. The decision and its
alternatives are [RFC-0021](../rfcs/rfc-0021-key-resolution-model.md);
`sdd/formal/StoreTree.dfy` states the model and verifies the flat encoding's
`decode`, its operations and the refusal rule (A.8).

The parts below are labelled A.1 to A.10, as in the RFC's Appendix A, which
this section lands; code and tests cite them by those labels.

**A.1 Nodes and keys.**

- **The tree** is spec 051's: TREE-001 to TREE-012 state its folders and
  items, its names (TREE-007), its Keys (TREE-009) and that a Key names at most
  one entity (TREE-010). This section states none of them again. An item also
  has content and metadata, which that structure does not model. By TREE-001
  and TREE-010, `is_file(k)` and `is_folder(k)` are never both true.
- **A Key is not a caller's input.** Spec 004's `RemotePath` maps an accepted
  input onto a Key or rejects it (spec 051 § Layering). BE-030's non-canonical
  rows (`d//f`, `d/./f`, `d/`) and root spellings (`./`) are inputs of that
  layer: each is mapped onto a Key, or refused, before the tree is consulted. A
  backend stores a *raw key*, its encoding's own spelling, which A.2 decodes.
  Below, "key" means a Key unless it says otherwise.
- A Key resolves to exactly one of `Item`, `Folder` or `Nothing`. Where an
  operation cares why there is nothing, the reason travels with the answer: a
  key whose path passes through an item makes a write `InvalidPath` (A.5).
- **Resolution assumes exact name equality**, as spec 051's names compare
  (§ Name equality), so A.4's checks and every column of A.5 hold where the
  encoding compares names exactly too. On a case-insensitive or normalizing
  encoding a Key can find an entry of another name (`read("A")` finds `a`);
  which backends compare names how, and how they then answer, is not
  decided here.
- Resolutions carry no depth. `ensure_parents(key)` creates every missing
  folder from the key alone, so no result depends on where absence starts.
  The item a path passes through travels with the answer only for the error
  message.

**A.2 Encodings.** Each driver declares its encoding's properties:

| Property | Meaning for the encoding | Declaration |
|---|---|---|
| refuses non-tree writes | the wire refuses a write below an item, or of an item over a folder | `namespace="hierarchical"` |
| folder objects | a folder is a raw entry, so it can exist with no children | `parents` other than `"none"` |
| one lookup sees a folder | a single `stat` answers for a folder too | `namespace="hierarchical"` |
| links | a raw entry can be a link | `links` (A.7) |

The kernel refuses to construct over a flat driver with folder objects.

These raw states decode to no tree:

- an item at `k` together with entries below `k/`, on a flat encoding;
- under `follow_within_root`, a link whose target is outside the root, a
  dangling link, and a loop of links (A.7).

A flat raw key with an empty segment, such as a folder marker `a/` or `a//b`,
would give an empty name (TREE-007); how it decodes is not decided here, and
A.3 keeps BE-030's omission of such a key.

A stored key such as `a\b`, `..` or one holding NUL is not in that list. Spec
051's names forbid only `/`, so where its characters are in the spec's alphabet
Σ, it decodes to a Key in the tree. That Key lies outside the library's
addressable subset: no input maps onto it, so no keyed operation reaches it.
Spec 004 refuses `..` (PATH-003) and NUL (PATH-007), and folds `\` to `/`
(PATH-002), so `a\b` as an input addresses the Key `a/b` instead. Listings omit
such a key and log it, as BE-030 rules, because no keyed operation could act on
what they returned. Addressing and `unwrap()` still reach it (BE-030, BE-025).

**A.3 Undecodable states.**

- **Listings.** A listing of `k`'s parent that returns `k` as an item and `k/`
  as a prefix omits the prefix. A recursive listing omits every entry below an
  item it has listed. For that, a flat driver's `list_page` returns keys in
  byte-lexicographic order, a prefix `p` ordered as `p/`, so `k` arrives before
  every key below `k/`; that is a driver obligation, and it lets the kernel
  track the omission with a stack of open items rather than a buffer of the
  listing. Hierarchical drivers stay unordered. A link that does not decode is
  omitted too (A.7). Each omission is logged, in the one record per listing
  BE-030 already writes.
- **Folder operations on an item.** `list_files(k)`, `list_folders(k)` and
  `iter_children(k)` are empty, and `get_folder_info(k)` and `delete_folder(k)`
  answer `InvalidPath`, when `k` is an item. On a flat encoding a listing of
  `k/` cannot see an item `k`, so a flat folder operation `stat`s `k` first,
  success included, whatever raw entries lie below it.
- **Keys below an item, on a flat encoding.** The probe, read-file and
  delete-file families do not walk their key's ancestors, and neither do the
  folder families: they `stat` the key alone. So `read("k/a.txt")` finds a raw
  entry another tool wrote below an item `k`, `delete("k/a.txt")` removes it,
  which is how such an entry is cleaned up, and `list_files("k/d")` lists `k/d/`
  as it stands. This is a stated limit, where the tree would answer as A.5's
  last row. A.4 keeps the library's own writes from producing it.
- **A link that does not decode** is refused like an input the key rule
  refuses: every keyed operation answers `InvalidPath`, a `move` from it
  included, except `delete`, which removes the link (A.7).
- **Omitted entries and `delete_folder`.** A recursive `delete_folder` that
  walks removes only what its listings return, so an omitted entry below the
  folder remains and the call answers `DirectoryNotEmpty`. One that runs the
  driver's `delete_tree` removes the omitted entry with the rest (BE-031). On a
  flat encoding, a recursive `delete_folder` of an item `k` answers
  `InvalidPath` and removes nothing, and a walk of `k`'s parent removes `k`,
  leaves `k/a.txt` and answers `DirectoryNotEmpty`.
- **`unwrap()`** reaches any raw entry.

**A.4 Writes.** These writes are `InvalidPath` on every class on the kernel,
within A.1's scope on name equality:

- writing below an item (`k/a.txt` while `k` is an item);
- writing an item over a folder (`k` while `k` is a folder, including a flat
  `k/` that holds entries).

A write is `write`, `write_atomic`, `open_atomic` and the `move`/`copy`
destination. An encoding that refuses non-tree writes needs no check, because
the kernel types the wire's refusal (A.8). A flat encoding checks with one
`stat` per ancestor, shallowest first, and one `list_page(k, limit=1)`, before
the write and after the transfer source check. These checks decide the result,
so they fail closed: a `stat` miss (`None`,
`NotFound`, `InvalidPath`) is no item, a listing's `NotFound` or `InvalidPath`
is an empty listing by the flat listing obligation (A.8), and any other failure
is the write's. Neither check is race-free on a flat wire: another writer can
act between the check and the write.

**A.5 Families and results.**

| Family | Operations |
|---|---|
| probe | `exists`, `is_file`, `is_folder` |
| read-file | `read`, `read_bytes`, `read_seekable`, `get_file_info` |
| write-file | `write`, `write_atomic`, `open_atomic` |
| delete-file | `delete` |
| folder-read | `list_files`, `list_folders`, `iter_children`, `get_folder_info`, and `glob` over its pattern's literal prefix |
| delete-folder | `delete_folder` |
| transfer | `move`, `copy`: the source as read-file, except that a `move` source names the entry at the key (A.7); the destination as write-file; in BE-018's order |

| Resolves to | probe `exists`/`is_file`/`is_folder` | read-file | write-file | delete-file | folder-read | delete-folder |
|---|---|---|---|---|---|---|
| `Item` | T / T / F | the item; a link under `no_follow` is `InvalidPath` (A.7) | replaced, or `AlreadyExists` without `overwrite`; a link under `no_follow` is `InvalidPath` (A.7) | removed | empty | `InvalidPath` |
| `Folder` | T / F / T | `InvalidPath` | `InvalidPath` | `InvalidPath` | its children | removed, or `DirectoryNotEmpty` |
| `Nothing` | F / F / F | `NotFound` | written, parents created | `NotFound` | empty | `NotFound` |
| `Nothing`, path through an item | F / F / F | `NotFound` | `InvalidPath` | `NotFound` | empty | `NotFound` |

The last row is what the tree answers. On a flat encoding the keyed families
and the folder families trust the encoding instead (A.3). For `delete`,
`delete_folder` and a `move` source, a link at the key that decodes resolves to
`Item` (A.7). A link that does not decode never reaches this table (A.3). Every
column holds where names compare exactly (A.1). `missing_ok` turns a delete's
`NotFound` into success. `get_folder_info` types an empty aggregate as BE-017
states. The per-operation clauses keep what is specific to them, such as
`overwrite`, cursors, `max_depth` and the synthesised write routes, and cite
this table for the rest.

**A.6 Empty folders.** The tree allows an empty folder. A folder becomes empty
when its last child is deleted or moved out. An encoding without folder objects
cannot hold an empty folder, so there it vanishes. With folder objects it stays
until `remove_folder` or `delete_tree` removes it (BE-031). Whether a flat raw
key with an empty segment, such as a folder marker another tool wrote, holds an
empty folder is not decided here.

**A.7 Links.** The rule below binds a driver that declares `links="present"`.
Whatever its driver declares, a class on the kernel has `delete` and a `move`
source probe their key without following a link, and `delete_folder` keeps
BE-031's `follow_links=False` view.

- `links` is `none` for object stores and `present` where the wire has links:
  Local and SFTP.
- The store policy is `follow_within_root` (the default) or `no_follow`. Under
  `follow_within_root` a link decodes to its target's node, and a target
  outside the root does not decode. Under `no_follow` a link decodes to an
  item.
- **Entry operations.** `delete`, `delete_folder` and a `move` source name the
  entry at the key itself, so for them the last segment decodes under
  `no_follow` whatever the policy, and a link that decodes is an `Item` there.
  A.5's `Item` row then gives their answers: `delete` removes the link, never
  its target (BE-031's existing rule); `delete_folder` answers `InvalidPath`;
  `move` moves the link entry and leaves the target alone, as a rename does.
- **Every other operation** reads through a link under the store policy. Under
  `follow_within_root` a read or a `copy` from a link reads the target's
  content, and a write to a link goes to its target. Under `no_follow` a link
  has no content of its own, so read-file, a `copy` from it and a write to it
  are `InvalidPath`; replacing a link the store did not make would destroy it
  without a signal.
- **A link that does not decode** (its target outside the root, dangling, or in
  a loop) is refused like an input the key rule refuses (A.3). That outranks
  the entry rule: `move` of such a link is `InvalidPath`, and only `delete`
  removes it. The driver signals it (A.8's typing rule for drivers with links).

**A.8 Observations.** A driver call observes the encoding, often only partly: a
flat `stat` sees an item but not a folder, and a `list_page(limit=1)` sees
whether a folder is empty. A refusal arrives as `NotFound`, `InvalidPath`,
`AlreadyExists`, `PermissionDenied`, an untyped `RemoteStoreError`, or another
type.

**The probe set** is those first five shapes. Drivers owe no rule about which
of them a refusal takes, except the two typing rules at the end of this part: a
wire's ENOTDIR may arrive as any of them. Any other type (`BackendUnavailable`,
`ResourceLocked`, `DirectoryNotEmpty`, ...) says nothing about the key and
passes through unprobed. Then:

1. A call that succeeds runs only its *determinants*: the probes that run
   whether or not it fails. They are A.3's `stat` before a flat folder
   operation; A.4's write checks; the probes `exists`, `is_file` and
   `is_folder`; `get_file_info` and a ranged `read_seekable`; the transfer
   source check, which runs on a flat namespace, with explicit parents, on a
   rename route and for a self-operation; the destination `stat` where the
   kernel stats a write target first (`write_atomic` by temp and rename without
   `overwrite`, `move` by rename); `get_folder_info`'s empty-aggregate `stat`
   with folder objects; and, without folder objects, `delete_folder`'s listing.
   A call that succeeds without a determinant probes nothing.
2. On a refusal whose compatible rows give more than one result for the family,
   the kernel probes, cheapest call first. For example, delete-folder answers
   `NotFound` in both `Nothing` rows, so it never tells them apart.
3. A determinant fails closed: its failure is the operation's failure. A probe
   that runs only because the call refused fails open: if it cannot answer,
   the refusal stands (BE-021).
4. **A probe replaces the refusal only on a row where the call must refuse,
   or, for a listing, on a row that holds nothing.** A refusal in the probe set
   can meet any row, since a denial or a dead connection meets an existing item
   as well as a missing one. So when the probe concludes a row where A.5 gives
   the call success (an item for `get`, an empty folder for `remove_folder`,
   nothing for a write, a folder for a listing), the refusal stands. Otherwise
   that row's A.5 result replaces it, chaining the refusal as its cause.

What a `stat` says. A miss is `None`, or a raised `NotFound` or `InvalidPath`,
since a POSIX `stat` below an item raises ENOTDIR. On a hierarchical namespace a
key's `stat` that raises another refusal in the probe set is followed by its
ancestors' `stat`s, shallowest first: an item among them puts the key's path
through an item, an absent one makes the key absent, and an ancestor that
cannot answer is skipped; if none decides, the `stat`'s own error is the
answer, which a determinant raises and an error-path probe reads as no answer.
A flat namespace never walks ancestors (A.3's stated limit).

The tables split by `namespace`, which decides what one `stat` sees; a
`parents="none"` driver on a hierarchical namespace takes the hierarchical
table, except that its `delete_folder` follows BE-031's `parents="none"`
sequence and so the flat `delete_tree` row, and it has no `remove_folder`.
`StoreTree.dfy` §11 enumerates every call these tables name (`get`, `delete`,
`put`, `ensure_parents`, `remove_folder`, `delete_tree`, the first listing
page; `move`, `copy` and `rename` as a source read and a destination write),
each namespace and each row, and proves rule 4.

**Flat namespace.** A `stat` sees an item or answers a miss; it cannot tell a
folder from nothing. Per call, after a refusal in the probe set:

| Call | Probe | Concludes |
|---|---|---|
| `get`, `delete` | `stat(k)`, then on a miss `list_page(k, limit=1)` | an item: the refusal stands; a non-empty listing: `InvalidPath`; an empty one: `NotFound` |
| `put`, `open_write`, commit, `rename` (A.4's checks ran first, so the key is no folder and nothing above it is an item) | `stat(k)` | an item without `overwrite`: `AlreadyExists`; anything else: the refusal stands |
| `delete_tree` (BE-031's `parents="none"` order) | `list_page(k, limit=1)` first, then `stat(k)` after an empty listing | a non-empty listing: the refusal stands; then an item: `InvalidPath`; a miss: `NotFound` |
| `list_page(k)`, first page | none: the only call that sees a flat folder is the listing that just failed, and A.3's `stat` ran first and found no item | a `NotFound` or `InvalidPath` is an empty listing, by the flat listing obligation below; any other shape stands |
| `move`, `copy` | the source as `get`, the destination as `put` | as those |

**Hierarchical namespace.** A `stat` sees an item or a folder. Per call, after
a refusal in the probe set:

| Call | Probe | Concludes |
|---|---|---|
| `get`, `delete`, a `move` or `copy` source | `stat(k)`, without following a link for `delete` and a `move` source, which name the entry (A.7) | an item: the refusal stands; a folder: `InvalidPath`; a miss or a path through an item: `NotFound` |
| write primitives (`put`, `open_write` and commit, `rename`, `copy`, `move` at the destination) | `stat(k)`, then on a miss the ancestors' `stat`s, shallowest first | a folder: `InvalidPath`; an item without `overwrite`: `AlreadyExists`; an item among the ancestors: `InvalidPath`; anything else: the refusal stands |
| `ensure_parents` | the ancestors' `stat`s | an item among them: `InvalidPath`, naming it; otherwise the refusal stands |
| `remove_folder` | `stat(k)` without following a link, then for a folder `list_page(k, limit=1)` | an item: `InvalidPath`; a miss: `NotFound`; a non-empty folder: `DirectoryNotEmpty`; an empty folder: the refusal stands |
| `delete_tree`, with folder objects, and the walk's first listing of `k` | `stat(k)` without following a link | an item: `InvalidPath`; a miss: `NotFound`; a folder: the refusal stands |
| `list_page(k)`, first page | `stat(k)` | a folder: the refusal stands; anything else: an empty listing |

A listing's first page and a `folder_stats` push-down answer alike, and on the
root `""`, always a folder, only a `NotFound` or `InvalidPath`, an absent
container's, is an empty listing (BE-021); no `stat` is asked. A two-key
refusal is answered for the source first, both keys being probed only when the
source is an item; the refusal then names the destination when only the
destination's state can explain it (BE-030).

**What drivers owe instead**, each stated once here:

- A refusal changes nothing.
- `get` and `delete` refuse a key that is not an item, and every write
  primitive refuses a folder at its key or an item above it (hierarchical).
  `remove_folder` refuses anything but an empty folder, and `delete_tree`
  refuses an item, a link or nothing.
- A flat driver's `list_page` returns keys in byte-lexicographic order (A.3).
- A driver's `folder_stats` returns the aggregate the kernel would compute over
  its own listing, so it omits what that listing omits: the keys BE-030's
  listing rule omits (one the key rule refuses or rewrites, an empty-segment
  key among them), and on a flat namespace every key below an item it lists
  (A.3). BE-030 states the first half for native aggregates; this adds A.3's.
- `list_page` with `follow_links=False` never lists a link's target, and
  `delete` on a link removes the link (A.7).
- A driver declaring `links="present"` refuses a key whose link does not decode
  with `InvalidPath`, from `stat` and from every call, and types its own
  ENOTDIR as `NotFound`. So an `InvalidPath` from such a driver's `stat` means
  "does not decode", never a miss. This typing rule binds only drivers with
  links.
- A flat driver's `list_page` answers `NotFound` or `InvalidPath` only when
  nothing lies under the prefix, an absent container included (BE-021). Since
  the only call that sees a flat folder is the listing that just failed, this
  is what lets a refused first page read as empty without hiding entries. This
  typing rule binds only flat drivers' listings.

**A.9 Changes under an operation.** A refusal before the operation's first page
is read through A.5. A refusal after it propagates. The bound is kept once per
operation, not per request. In `delete_folder`'s walk, a refusal of an entry
below the key propagates unprobed, except a `NotFound`, an entry already gone,
which is tolerated; `DirectoryNotEmpty` when a writer adds under the tree
mid-walk is the same rule.

**A.10 Conformance:** two generated suites in `tests/_kernel/`, run against both
runtimes. `test_tree_results.py` crosses tree state with key, for the results
in A.5. `test_encoding_observations.py` crosses encoding property, raw state,
refusal shape and what the error-path probes do, for A.3, A.4, A.8 and A.9.
Its fake driver returns an item and a prefix of the same name on one flat
listing page, in byte-lexicographic order, as a real flat wire does.

**Costs**, on the kernel, against a class not on it (BE-021's cost table
measures the error-path probes; these are the determinants this section adds):

| Call | Encoding | Added on every call | Added on the error path |
|---|---|---|---|
| a write or a `move`/`copy` destination (A.4) | flat | one `stat` per ancestor and one `list_page(limit=1)`; on a transfer, also the source check | one `stat` |
| a folder operation on a non-root key (A.3) | flat | one `stat` | — |
| `get`, `delete`, a source, refused | flat | — | one `stat`, then on a miss one `list_page(limit=1)` |
| `delete(path, missing_ok=True)` on an absent key | flat | — | one `stat` and one `list_page(limit=1)`, where a class not on the kernel spends the listing alone (BE-021) |
| a listing's first page refused in the probe set | hierarchical | — | one `stat` |

---

## Assumptions

None lifted out of the sections: BE-032's A.1, A.4 and A.8 and BE-030's
**Content** paragraph state, in their own text, what they rely on from
encodings, wires and caller streams.

## Notes

The sections carry their derived claims in place: BE-030's equivalence of a
canonical `""` with BE-029's root predicate, and that a refused probe's
`InvalidPath` leaves BE-004 unaffected; BE-032 A.1's exclusivity of `is_file`
and `is_folder`, from TREE-001 and TREE-010; and the model notes in BE-031
(`CanonicalUnder`) and BE-032 A.8 (`StoreTree.dfy` §11's proof of rule 4).

## Tested against

- The Dafny models `sdd/formal/StoreTree.dfy`, `RootPath.dfy`, and
  `BackendContract.dfy` verified in `MemoryBackend.dfy`:
  `bash scripts/dafny_verify.sh StoreTree.dfy RootPath.dfy BackendContract.dfy MemoryBackend.dfy`.
- Every test file carrying a BE-030, BE-031 or BE-032 mark, both runtimes:
  `python scripts/run_tests.py $(rg -l 'mark\.spec\([^)]*"BE-03[0-2]"' tests)`.

Which test checks which section derives from the tests' spec marks.
