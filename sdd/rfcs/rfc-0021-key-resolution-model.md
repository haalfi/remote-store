# RFC-0021: The store is a tree, and each backend encodes it

## Status

Draft, 2026-10-12. Tracked as **BK-432**. PR #1127 (BK-389) is parked until
this is decided, and its open `delete_folder` findings are answered from it.

## Summary

**The store is strictly a tree.** Backends map to it through a partial
`decode` function, and every operation is evaluated against that one logical
model, not against edge cases per operation or quirks of each backend's
geometry.

A store is a tree. The root is a folder, a folder holds named folders and
items, and an item is a leaf. A key is a path of names from the root and names
at most one node, so a key that names an item can never name a folder.

A backend does not hold that tree directly. It holds an *encoding*: paths on a
disk, keys in a bucket, rows in a table. An *abstraction function* decodes the
encoding to the tree. The function is partial: some raw states, such as a
bucket holding both `k` and `k/a.txt`, decode to no tree, and those raw states
are not in the store.

Every keyed operation is specified once against the tree. The kernel's job is
to answer as the tree would, from lossy observations of the encoding. How much
that costs, and what it can see, depends on the encoding and never on the
model.

## Motivation

**The spec has no single statement of what a key names, and its statements
disagree.** BE-030's *What is at a key* (spec 003) gives one answer and lists
the calls that read it. BE-031 states its own probe rule for `delete_folder`.
BE-008, BE-014, BE-017 and BE-021 each carry rows for a folder, an absent key,
a key under a file and a shadowed prefix. The kernel mirrors the split.
`_state` reads a `stat` that raises `NotFound` or `InvalidPath` as a miss and
probes four refusal types (`_may_be_a_folder`). `delete_folder`'s `_df_kind`
treats no `stat` error as a miss, and its `_probe_wanted` probes two refusal
types. PR #1127's closing round over `a630ef5` found exactly that: with folder
objects, an untyped refusal of `delete_folder("f/x")`, where `f` is a file,
answers untyped where BE-031's table says `NotFound`.

**The review kept narrowing one condition.** Rounds 7 to 10 of PR #1127's
review "had one shape: each fix added a probe to one call family, and the next
round found a family or an axis nobody had crossed"
([BK-389's dossier](../backlog/bk-389-kernel-step-1-memory.md), § Re-plan
after round 10). The re-plan merged six helpers into one classifier. The
closing round over `a630ef5` then found the same question, "what does a
refusal of shape X say about the key", in `delete_folder`'s own probe rule. No
artifact held the question above the call families, so each round answered it
for one family.

**Backend quirks were written into the model itself.** A first draft of this
RFC made geometry a parameter of the model. Its outcomes included a flat
`Prefix` and a `FileAndPrefix` beside `File` and `Folder`, so the model
inherited every encoding's oddities. The maintainer's objection is the reason
for this version: in a store, a key that names an item is a leaf and cannot be
a folder. A state where it is one is a fact about an encoding, not about the
store.

**The formal spec already holds the logical model. What it lacks is the
decoding step.** `BackendContract.dfy` models the store as `map<Path, Entry>`
and its class invariant `Valid()` (line 536) requires every ancestor of an
entry to be a directory, which is the tree. Nothing maps a flat or implicit
encoding onto it, so the states the review kept hitting fall outside every
verified statement.

## Decisions

Each decision states what is decided. How it works is in
[Appendix A](#appendix-a), the draft of the spec section it becomes, and what
it costs is in [Impact](#impact).

### D0. Out of scope

The key rule, the root, the close posture, capability gating and `glob`'s
pattern rule are settled before the tree is consulted (BE-020, BE-029,
BE-030), and they are unchanged.

### D1. The store is a tree

The root is a folder, folders hold named folders and items, and an item is a
leaf. A key names at most one node, and resolves to an item, a folder or
nothing. ([A.1](#a1-nodes-and-keys))

### D2. Each backend encodes the tree

A backend's raw state maps to the tree through a partial `decode` function.
Backends differ only in the properties of their encodings, which drivers
declare, and this RFC adds `links` to them. ([A.2](#a2-encodings))

### D3. A raw state that does not decode is not in the store

Listings omit such states, and folder operations answer as the tree does. On a
flat encoding, a keyed lookup trusts the encoding instead of checking every
ancestor. That is a stated limit of the model. ([A.3](#a3-undecodable-states))

### D4. The library never writes a state that does not decode

Writing below an item, or writing an item over a folder, is `InvalidPath` on
every backend. The first replaces BE-008's opt-in check. The second has no
check today. Neither can stop another writer. ([A.4](#a4-writes))

### D5. One result table

Each keyed operation belongs to one of seven families. Its result is the cell
where its family meets what the key resolves to.
([A.5](#a5-families-and-results))

### D6. Empty folders depend on the encoding

Whether a folder still exists after its last child is deleted is a property of
the encoding, stated once. ([A.6](#a6-empty-folders))

### D7. Links follow one store-wide policy

How a link decodes is one policy for the whole store, never a per-call option.
`delete`, `delete_folder` and a `move` source name the entry at the key, so
for them a link is always an item. A link that does not decode is refused like
a key the rule refuses. The public option comes later. ([A.7](#a7-links))

### D8. Refusals are observations of the encoding

After a refusal, the kernel probes only until the result for the operation's
family is decided. A probe that runs whether or not the call fails fails
closed. A probe that runs only because the call refused fails open, so the
refusal stands. Each driver obligation is stated once.
([A.8](#a8-observations))

### D9. Changes under an operation

A contradiction between one operation's observations is handled by BE-021's
first-page bound, applied once per operation. ([A.9](#a9-changes-under-an-operation))

### D10. Where the model lives

Spec 003 gains one section, drafted in Appendix A. The clauses it replaces
point to it. The model is also stated in Dafny, which checks the prose: a
`decode` per encoding and the lemmas that each operation keeps the encoding
decodable and agrees with the tree, verified before this RFC is accepted.

## Alternatives

- **A semantic model with geometry as its parameter**, this RFC's first
  draft. Rejected: its outcome set grew a flat `Prefix` and a `FileAndPrefix`,
  so the model carried encoding quirks and stopped being the abstraction a
  caller reasons about.
- **Keep the per-operation rules and state the missing driver obligation**,
  the cheaper answer to PR #1127's second finding. Rejected: it leaves two
  rules for one `stat` answer.
- **Undecodable entries stay reachable by their own key.** Rejected: it puts
  nodes outside the tree.
- **Enforce the tree on every keyed lookup.** Rejected: one `stat` per
  ancestor on every flat call, success included, to answer for states only a
  foreign writer creates.
- **Keep BE-008's guard opt-in.** Rejected: with the default, the library
  itself creates states that do not decode.
- **A per-call `follow_links`.** Rejected: one key would resolve two ways.

<a id="impact"></a>
## Impact

**Behaviour changes and costs**, on the kernel. They land through BK-389's
resume, then BK-394 onward, as each backend moves onto the kernel, each with a
CHANGELOG entry and a migration note:

| Change | Encoding | Today | Under this RFC | Cost |
|---|---|---|---|---|
| write below an item (D4) | flat | written, unless `reject_write_under_file_ancestor` is on | `InvalidPath` | one `stat` per ancestor, per write |
| write an item over a folder (D4) | flat | written, whether or not the opt-in is on | `InvalidPath` | one `list_page(limit=1)` per write |
| listing an item `k` and a prefix `k/` together (D3) | flat | both listed | the prefix omitted and logged | none; flat drivers list in byte-lexicographic order (A.3) |
| folder operation on a key that is an item with raw entries below it (D3) | flat | `list_files`, `get_folder_info` and `delete_folder` act on `k/` | empty, `InvalidPath` for `get_folder_info` and `delete_folder` | one `stat` per folder operation |
| listing a link (D7) | SFTP | hidden | listed per the store's link policy; a link that does not decode is omitted | none |
| listing a link that does not decode (D7) | Local | listed (read from `_local.py`: listings stat through links with no containment check) | omitted and logged | none |
| recursive listing through a link to a folder in the root (D7) | Local | not descended (`os.walk(followlinks=False)`) | descended under `follow_within_root` | the linked subtree's listing |

Keyed calls on a link that does not decode keep today's Local answer,
`InvalidPath`. BE-021's cost table records the costs when the clauses land. A
stored key the key rule refuses (`a\b`) is already omitted and logged today
(BE-030), and a recursive `delete_folder` over it already answers
`DirectoryNotEmpty` (BE-031). A.3 makes that the rule for every omitted entry,
so it does not change.

- **Public API.** `reject_write_under_file_ancestor`, a constructor keyword on
  five flat backends (BE-008), loses its effect, since the check it enabled
  becomes unconditional. Each backend retires it when it moves onto the
  kernel. Until then BE-008's text keeps binding the backends not yet on the
  kernel, and spec 003 marks which clause binds which.
- **PR #1127** resumes against this model. `delete_folder` reads the shared
  resolver, which answers its first open spec finding. A.8 answers its second:
  a `PermissionDenied` is in the probe set, and drivers owe no typing rule.
  The five open text findings are fixed against the new text.
- **Spec 003** gains Appendix A as one section. These texts are replaced by a
  pointer to it, for the backends on the kernel:
    - BE-030's *What is at a key*, with its list of determinants moved into A.8;
    - the folder and file-above rows of BE-008 and BE-021;
    - BE-008's flat exemption and its opt-in file-ancestor walk;
    - BE-031's probe rule, and its "a file and a prefix both" row.
- **Tests:** two generated suites (A.10) replace
  `tests/_kernel/test_condition_space.py`'s hand-assembled axes.
- **Formal model:** `Valid()` in `BackendContract.dfy` already is A.1's tree.
  `sdd/formal/StoreTree.dfy` states the model in Dafny and verifies with
  `bash scripts/dafny_verify.sh StoreTree.dfy` (28 verified, 0 errors). CI's
  `verify-formal` job runs it. Six mutants, each weakening one check or rule,
  fail verification. It covers:
    - the tree and its resolution;
    - a flat encoding's partial `decode`, which yields a valid tree;
    - a flat lookup, a `list_page(k, limit=1)` and an ancestor `stat` agree
      with the tree's item, folder and through-an-item answers;
    - A.4's checks pass exactly where the tree's write does not answer
      `InvalidPath`, and a write they pass keeps the encoding decodable and
      agrees with the tree's write;
    - a flat listing of `k/` returns the tree's children of `k`;
    - a recursive `delete_folder` deletes the visible subtree, and an omitted
      entry keeps the folder non-empty;
    - a flat `move` or `copy` keeps the encoding decodable and moves or
      copies exactly its item;
    - a flat encoding holds no empty folder (A.6).

    Links (A.7), the refusal tables (A.8) and changes under an operation
    (A.9) are outside the sketch.
- **Local's and SFTP's links** decode by A.7's policy once each runs on the
  kernel. BUG-323, SFTP's recursive delete through a link at the key, is fixed
  independently of this RFC.
- **Follow-ups**, filed when this RFC is accepted: the public link option and a
  capability that exposes `links`, and wiring the Dafny encodings into
  `BackendContract.dfy`'s operations.

## Open Questions

None. The two items owed before acceptance are done: A.8's tables, and the
Dafny sketch described under Impact.

### Decided while drafting (maintainer, 2026-10-12)

- Park PR #1127 and settle the model first. It is tracked as a new item with
  this RFC as its record. The RFC's PR stacks on `bk-389-kernel`.
- The model is also stated in Dafny, verified before acceptance. The first
  draft had left Dafny out to keep its scope small, and the maintainer
  reversed that once the model became a tree with a `decode` per encoding,
  which is a refinement statement.
- The model is one tree with a partial abstraction function per backend
  encoding, not a semantic model with geometry as its parameter.
- A raw state that does not decode is not in the store. Listings omit it.
  Keyed lookups trust the encoding, as a stated limit.
- Writes that would make the encoding undecodable are always `InvalidPath`.
- An emptied folder's existence depends on the encoding, stated once.
- Links: a `links` property, a store-level policy, and `InvalidPath` for a
  write to a link under `no_follow`. Only the model is in scope; the public
  option comes later.
- After the divergence check fired on links (round 2 found a write through an
  escaping link): a link that does not decode is refused like a key the rule
  refuses (`InvalidPath` on keyed calls, omitted from listings), and `delete`,
  `delete_folder` and a `move` source name the entry at the key, so for them a
  link is always an item.
- An omitted raw entry keeps its folder non-empty, so a recursive
  `delete_folder` that cannot remove it answers `DirectoryNotEmpty`.
- One probe set (`NotFound`, `InvalidPath`, `AlreadyExists`,
  `PermissionDenied`, untyped) for every call, and no driver obligation on how
  a refusal is typed (A.8). `delete_folder`'s narrower set goes.
- On a flat encoding, the probe, read-file and delete-file families trust the
  encoding, so `delete("k/a.txt")` below an item removes the raw entry.
- A flat driver's `list_page` returns keys in byte-lexicographic order, a
  driver obligation, so the kernel needs no buffer for the recursive omission.
- A link as a transfer source: `move` moves the link, and `copy` copies the
  target's content (`InvalidPath` under `no_follow`).
- Local and SFTP have links. SFTP's were measured (below); Local's are read
  from `_local.py`.
- SFTP has links (`links="present"`), measured on the `atmoz/sftp` container
  with `SFTPBackend` as on master. Today it follows a link on keyed calls,
  hides it in listings, and lists or reads through it at its own key, which
  is the inconsistent decoding A.7's policy replaces. The same run found
  BUG-323: a recursive `delete_folder` on a link to a folder deletes the
  target's files.
- Outcomes carry no depth.
- `glob` is a folder-read over its pattern's literal prefix.
- The model lives in one new section of spec 003. The RFC keeps decisions to
  their claims and drafts that section as Appendix A.

<a id="appendix-a"></a>
## Appendix A: draft of spec 003 § The store tree

This appendix becomes the spec section on acceptance. Until then it is the
proposal's detail, and the decisions above are what is being decided.

### A.1 Nodes and keys

- The root is a folder. A folder holds named children, each either a folder or
  an item. An item has content and metadata, and no children.
- A key is the sequence of names from the root to a node. It names at most one
  node, so `is_file(k)` and `is_folder(k)` are never both true.
- A key resolves to exactly one of `Item`, `Folder` or `Nothing`. Where an
  operation cares why there is nothing, the reason travels with the answer.
  The case that matters is a key whose path passes through an item, which
  makes a write `InvalidPath` (A.5).
- Resolutions carry no depth. `ensure_parents(key)` creates every missing
  folder from the key alone, so no result depends on where absence starts.
  The item a path passes through travels with the answer only for the error
  message.

### A.2 Encodings

Each driver declares its encoding's properties:

| Property | Meaning for the encoding | Declaration |
|---|---|---|
| refuses non-tree writes | the wire refuses a write below an item, or of an item over a folder | `namespace="hierarchical"` |
| folder objects | a folder is a raw entry, so it can exist with no children | `parents` other than `"none"` |
| one lookup sees a folder | a single `stat` answers for a folder too | `namespace="hierarchical"` |
| links | a raw entry can be a link | `links`, new |

The kernel refuses to construct over a flat driver with folder objects.

These raw states decode to no tree:

- an item at `k` together with entries below `k/`, on a flat encoding;
- a stored key the key rule refuses, such as `a\b` (BK-399's case);
- under `follow_within_root`, a link whose target is outside the root, a
  dangling link, and a loop of links.

### A.3 Undecodable states

- **Listings.** A listing of `k`'s parent that returns `k` as an item and `k/`
  as a prefix omits the prefix. A recursive listing omits every entry below an
  item it has listed. For that, a flat driver's `list_page` returns keys in
  byte-lexicographic order, so `k` arrives before every key below `k/`; that
  is a driver obligation, and hierarchical drivers stay unordered. A link that
  does not decode is omitted too. Each omission is logged. This extends BE-030's omission of a key the rule
  refuses, and the listing itself shows what to omit.
- **Folder operations on an item.** `list_files(k)` is empty and
  `delete_folder(k)` answers `InvalidPath` when `k` is an item. On a flat
  encoding, a listing of `k/` cannot see an item `k`, so a flat folder
  operation `stat`s `k` first, success included.
- **Keyed lookups.** On a flat encoding, the probe, read-file and
  delete-file families do not walk their key's ancestors. So `read("k/a.txt")`
  finds a raw entry another tool wrote below an item `k`, and
  `delete("k/a.txt")` removes it, which is how such an entry is cleaned up.
  This is a limit of the model. A.4 keeps the library's own writes from
  producing it.
- **A link that does not decode** is refused like a key the rule refuses:
  every keyed operation answers `InvalidPath`, except `delete`, which removes
  the link (A.7). It never resolves to `Nothing`, so nothing is written
  through it.
- **Omitted entries keep a folder non-empty.** A recursive `delete_folder`
  removes only what it can list, so an omitted entry below the folder remains
  and the call answers `DirectoryNotEmpty`, as BE-031 already rules for a key
  the rule refuses. On a flat encoding, a recursive `delete_folder` of an
  item `k` answers `InvalidPath` and removes nothing. One of `k`'s parent
  removes `k` and leaves `k/a.txt`, so it answers `DirectoryNotEmpty`.
- **`unwrap()`** reaches any raw entry.

### A.4 Writes

These writes are `InvalidPath` on every backend:

- writing below an item (`k/a.txt` while `k` is an item);
- writing an item over a folder (`k` while `k` is a folder, including a flat
  `k/` that holds entries).

An encoding that refuses non-tree writes needs no check, because the kernel
types the wire's refusal (A.8). A flat encoding checks with one `stat` per
ancestor and one `list_page(k, limit=1)`. These checks decide the result, so
they fail closed (BUG-292's decided policy). Neither check is race-free on a
flat wire: another writer can act between the check and the write.

### A.5 Families and results

| Family | Operations |
|---|---|
| probe | `exists`, `is_file`, `is_folder` |
| read-file | `read`, `read_bytes`, `read_seekable`, `get_file_info` |
| write-file | `write`, `write_atomic`, `open_atomic` |
| delete-file | `delete` |
| folder-read | `list_files`, `list_folders`, `iter_children`, `get_folder_info`, and `glob` over its pattern's literal prefix |
| delete-folder | `delete_folder` |
| transfer | `move`, `copy`: the source as read-file, the destination as write-file, in BE-018's order |

| Resolves to | probe `exists`/`is_file`/`is_folder` | read-file | write-file | delete-file | folder-read | delete-folder |
|---|---|---|---|---|---|---|
| `Item` | T / T / F | the item | replaced, or `AlreadyExists` without `overwrite`; a link under `no_follow` is `InvalidPath` (A.7) | removed | empty | `InvalidPath` |
| `Folder` | T / F / T | `InvalidPath` | `InvalidPath` | `InvalidPath` | its children | removed, or `DirectoryNotEmpty` |
| `Nothing` | F / F / F | `NotFound` | written, parents created | `NotFound` | empty | `NotFound` |
| `Nothing`, path through an item | F / F / F | `NotFound` | `InvalidPath` | `NotFound` | empty | `NotFound` |

The last row is what the tree answers. On a flat encoding the probe, read-file
and delete-file families trust the encoding instead (A.3). For `delete`,
`delete_folder` and a `move` source, a link at the key resolves to `Item`
(A.7). A link that does not decode never reaches this table (A.3).
`missing_ok` turns a delete's `NotFound` into success. `get_folder_info`
types an empty aggregate as BE-017 states. The per-operation clauses keep what
is specific to them, such as `overwrite`, cursors, `max_depth` and the
synthesised write routes, and cite this table for the rest.

### A.6 Empty folders

The tree allows an empty folder. A folder becomes empty when its last child is
deleted or moved out. An encoding without folder objects cannot hold an empty
folder, so there it vanishes. With folder objects it stays.

### A.7 Links

- `links` is `none` for object stores and `present` where the wire has links:
  Local and SFTP.
- The store policy is `follow_within_root` (the default) or `no_follow`.
  Under `follow_within_root` a link decodes to its target's node, and a target
  outside the root does not decode. Under `no_follow` a link decodes to an
  item.
- **Entry operations.** `delete`, `delete_folder` and a `move` source name the
  entry at the key itself, so for them the last segment decodes under
  `no_follow` whatever the policy, and a link there is an `Item`. A.5's `Item`
  row then gives their answers: `delete` removes the link, never its target
  (BE-031's existing rule); `delete_folder` answers `InvalidPath`; `move` moves
  the link entry and leaves the target alone, as a rename does. Following a
  link there would delete or move its target's contents.
- **Every other operation** reads through a link under the store policy. Under
  `follow_within_root` a `copy` from a link writes a regular item with the
  target's content, and a write to a link goes to its target. Under
  `no_follow` both are `InvalidPath`, since replacing a link the store did not
  make would destroy it without a signal.
- **A link that does not decode** (its target outside the root, dangling, or
  in a loop) is refused like a key the rule refuses (A.3).

### A.8 Observations

A driver call observes the encoding, often only partly: a flat `stat` sees an
item but not a folder, and a `list_page(limit=1)` sees whether a folder is
empty. A refusal arrives as `NotFound`, `InvalidPath`, `AlreadyExists`,
`PermissionDenied`, an untyped `RemoteStoreError`, or another type.

**The probe set** is those first five shapes. Drivers owe no rule about which
of them a refusal takes: a wire's ENOTDIR may arrive as any of them, so each
is compatible with every A.5 row the call can refuse on. Any other type
(`BackendUnavailable`, `ResourceLocked`, `DirectoryNotEmpty`, ...) says
nothing about the key and passes through unprobed. Then:

1. A call that succeeds runs only its *determinants*: the probes that run
   whether or not it fails. They are A.3's `stat` before a flat folder
   operation, A.4's write checks, and those BE-030 lists today: the probes
   `exists`, `is_file` and `is_folder`; `get_file_info` and a ranged
   `read_seekable`; the transfer source check; the destination `stat` where
   the kernel stats a write target first (`write_atomic` by temp and rename
   without `overwrite`, `move` by rename); and `get_folder_info`'s
   empty-aggregate `stat` with folder objects.
2. On a refusal whose compatible rows give more than one result for the
   family, the kernel probes, cheapest call first. For example, delete-folder
   answers `NotFound` in both `Nothing` rows, so it never tells them apart.
3. A determinant fails closed: its failure is the operation's failure. A probe
   that runs only because the call refused fails open: if it cannot answer,
   the refusal stands (BE-021). When it answers, the row's A.5 result
   replaces the refusal.

**Flat encoding** (`parents="none"`). A `stat` sees an item or answers
`None`; it cannot tell a folder from nothing. Per call, after a refusal in
the probe set:

| Call | Rows it can refuse on | Results differ? | Probe |
|---|---|---|---|
| `get`, `delete` | `Folder`, `Nothing` | yes: `InvalidPath` against `NotFound` | `list_page(k, limit=1)`: non-empty is `Folder` |
| `put`, `open_write`, commit | none: A.4's checks ran first, so the key is `Item` or `Nothing` | no | none; the refusal stands |
| `list_page(k)`, first page | `Item`, `Nothing` (A.3's `stat` ran first) | no: both are empty | none; a `NotFound` or `InvalidPath` reads as empty, any other shape stands |
| `move`, `copy` | the source as `get`, the destination as `put` | as those | as those |

**Hierarchical encoding** (folder objects, `parents` other than `"none"`). A
`stat` sees an item or a folder. A miss is `None`, or a `NotFound` or
`InvalidPath`, since a POSIX `stat` below an item raises ENOTDIR. Per call,
after a refusal in the probe set:

| Call | Rows it can refuse on | Results differ? | Probe |
|---|---|---|---|
| `get`, `delete` | `Folder`, `Nothing`, through an item | yes: `InvalidPath` against `NotFound` | `stat(k)`: a folder is `InvalidPath`, a miss `NotFound` |
| write primitives (`put`, `open_write` and commit, `rename`, `copy`, `move` at the destination) | `Folder`, through an item; `Item` without `overwrite` | yes | `stat(k)`: a folder is `InvalidPath`, an item `AlreadyExists`; on a miss, the ancestors' `stat`s, shallowest first: an item among them is `InvalidPath` |
| `ensure_parents` | through an item | no: `InvalidPath` | the ancestors' `stat`s, which name the item for the message |
| `remove_folder` | `Item`, `Nothing`, through an item, a non-empty `Folder` | yes | `stat(k)` under `no_follow`: an item is `InvalidPath`, a miss `NotFound`; a folder then `list_page(k, limit=1)`: non-empty is `DirectoryNotEmpty` |
| `delete_tree` | `Item`, `Nothing`, through an item | yes | `stat(k)` under `no_follow` |
| `list_page(k)`, first page | `Item`, `Nothing`, through an item, an unreadable `Folder` | yes: empty against the refusal | `stat(k)`: a folder keeps the refusal, anything else is empty |

**What drivers owe instead**, each stated once here:

- A refusal changes nothing.
- `get` and `delete` refuse a key that is not an item, and every write
  primitive refuses a folder at its key or an item above it (hierarchical).
  `remove_folder` refuses anything but an empty folder, and `delete_tree`
  refuses an item, a link or nothing.
- A flat driver's `list_page` returns keys in byte-lexicographic order (A.3).
- `list_page` with `follow_links=False` never lists a link's target, and
  `delete` on a link removes the link (A.7).

### A.9 Changes under an operation

A refusal before the operation's first page is read through A.5. A refusal
after it propagates. The bound is kept once per operation, not per request.
`delete_folder`'s `DirectoryNotEmpty`, when a writer adds under the tree
mid-walk, is the same rule.

### A.10 Conformance

Two generated suites. One crosses tree state with key, for the results in A.5.
The other crosses encoding property, raw state and refusal shape, for A.3, A.4
and A.8. Its fake driver must be able to return an item and a prefix of the
same name on one listing page, as a real flat wire does. Today's
`tests/_kernel/_fake.py` cannot, so it would pass A.3's omission rule without
exercising it.
