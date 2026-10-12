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
every backend. This retires BE-008's opt-in check. It cannot stop another
writer. ([A.4](#a4-writes))

### D5. One result table

Each keyed operation belongs to one of seven families. Its result is the cell
where its family meets what the key resolves to.
([A.5](#a5-families-and-results))

### D6. Empty folders depend on the encoding

Whether a folder still exists after its last child is deleted is a property of
the encoding, stated once. ([A.6](#a6-empty-folders))

### D7. Links follow one store-wide policy

How a link decodes is one policy for the whole store, never a per-call option.
Destructive tree operations never follow a link, whatever the policy. The
public option comes later. ([A.7](#a7-links))

### D8. Refusals are observations of the encoding

The kernel probes only until the result for the operation's family is
decided. A probe that decides the result fails closed. A probe that only types
a refusal fails open, so the refusal stands. Each driver obligation is stated
once. ([A.8](#a8-observations))

### D9. Changes under an operation

A contradiction between one operation's observations is handled by BE-021's
first-page bound, applied once per operation. ([A.9](#a9-changes-under-an-operation))

### D10. Where the model lives

Spec 003 gains one section, drafted in Appendix A. The clauses it replaces
point to it. The formal `decode` functions are a follow-up.

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

**Behaviour changes and costs**, all on flat encodings and all on the kernel.
They land through BK-389's resume, then BK-394 onward, each with a CHANGELOG
entry and a migration note:

| Change | Today | Under this RFC | Cost |
|---|---|---|---|
| write below an item, or an item over a folder (D4) | written, unless the opt-in is on | `InvalidPath`; BE-008's opt-in retired | one `stat` per ancestor, plus one `list_page(limit=1)`, per write |
| listing a raw state that does not decode (D3) | listed | omitted and logged | none |
| folder operation on a key that is an item (D3) | acts on `k/` | empty, or `InvalidPath` for `delete_folder` | one `stat` per folder operation |

BE-021's cost table records both costs when the clauses land.

- **PR #1127** resumes against this model. `delete_folder` reads the shared
  resolver, which answers both open spec findings (A.8 settles the second).
  The five open text findings are fixed against the new text.
- **Spec 003** gains Appendix A as one section. These texts are replaced by a
  pointer to it:
    - BE-030's *What is at a key*;
    - the folder and file-above rows of BE-008 and BE-021;
    - BE-008's flat exemption and its opt-in file-ancestor walk;
    - BE-031's probe rule, and its "a file and a prefix both" row.
- **Tests:** two generated suites (A.10) replace
  `tests/_kernel/test_condition_space.py`'s hand-assembled axes.
- **Formal model:** `Valid()` in `BackendContract.dfy` already is A.1's tree. A
  follow-up adds a `decode` function for each encoding, with refinement lemmas
  showing that each encoding's operations commute with `decode`.
- **SFTP's links** decode by A.7's policy once SFTP runs on the kernel. Today
  it follows a link on keyed calls and hides it in listings. BUG-323, its
  recursive delete through a link at the key, is fixed independently of this
  RFC.
- **No public API change in this RFC.** The link option and a capability that
  exposes `links` are a follow-up item, filed when this RFC is accepted.

## Open Questions

1. **Listing order.** A.3's recursive omission needs an item `k` to be listed
   before the entries below `k/`. That holds for a lexicographic listing,
   because `k` sorts before `k/`. Is that order a driver obligation, or does
   the kernel buffer?

### Decided while drafting (maintainer, 2026-10-12)

- Park PR #1127 and settle the model first. It is tracked as a new item with
  this RFC as its record, in prose and tables, with no Dafny. The RFC's PR
  stacks on `bk-389-kernel`.
- The model is one tree with a partial abstraction function per backend
  encoding, not a semantic model with geometry as its parameter.
- A raw state that does not decode is not in the store. Listings omit it.
  Keyed lookups trust the encoding, as a stated limit.
- Writes that would make the encoding undecodable are always `InvalidPath`.
- An emptied folder's existence depends on the encoding, stated once.
- Links: a `links` property, a store-level policy, `no_follow` for destructive
  tree operations, and `InvalidPath` for a write to a link under `no_follow`.
  Only the model is in scope; the public option comes later.
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
- a loop of links.

### A.3 Undecodable states

- **Listings.** A listing of `k`'s parent that returns `k` as an item and `k/`
  as a prefix omits the prefix. A recursive listing omits every entry below an
  item it has listed. Each omission is logged. This extends BE-030's omission
  of a key the rule refuses, and the listing itself shows what to omit.
- **Folder operations on an item.** `list_files(k)` is empty and
  `delete_folder(k)` answers `InvalidPath` when `k` is an item. On a flat
  encoding, a listing of `k/` cannot see an item `k`, so a flat folder
  operation `stat`s `k` first, success included.
- **Keyed lookups.** On a flat encoding, a lookup does not walk its key's
  ancestors, so `read("k/a.txt")` finds a raw entry another tool wrote below
  an item `k`. This is a limit of the model. A.4 keeps the library's own
  writes from producing it.
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
| `Item` | T / T / F | the item | replaced, or `AlreadyExists` without `overwrite` | removed | empty | `InvalidPath` |
| `Folder` | T / F / T | `InvalidPath` | `InvalidPath` | `InvalidPath` | its children | removed, or `DirectoryNotEmpty` |
| `Nothing` | F / F / F | `NotFound` | written, parents created | `NotFound` | empty | `NotFound` |
| `Nothing`, path through an item | F / F / F | `NotFound` | `InvalidPath` | `NotFound` | empty | `NotFound` |

`missing_ok` turns a delete's `NotFound` into success. `get_folder_info`
types an empty aggregate as BE-017 states. The per-operation clauses keep what
is specific to them, such as `overwrite`, cursors, `max_depth` and the
synthesised write routes, and cite this table for the rest.

### A.6 Empty folders

The tree allows an empty folder. An encoding without folder objects cannot
hold one, so a folder whose last child is deleted there vanishes. With folder
objects it stays. No operation creates an empty folder, but deletes produce
one.

### A.7 Links

- `links` is `none` for object stores and `present` where the wire has links:
  Local and SFTP.
- The store policy is `follow_within_root` (the default) or `no_follow`.
  Under `follow_within_root` a link decodes to its target's node, and a target
  outside the root does not decode. Under `no_follow` a link decodes to an
  item.
- Destructive tree operations decode under `no_follow` whatever the policy,
  since following a link would delete its target's contents.
- A write to a link goes to the target under `follow_within_root`. Under
  `no_follow` it is `InvalidPath`, since replacing a link the store did not
  make would destroy it without a signal.

### A.8 Observations

A driver call observes the encoding, often only partly: a flat `stat` sees an
item but not a folder, and a `list_page(limit=1)` sees whether a folder is
empty. A refusal arrives as `NotFound`, `InvalidPath`, `AlreadyExists`,
`PermissionDenied`, an untyped `RemoteStoreError`, or another type. For each
encoding property one table gives **(call, shape) → the A.5 rows it is
compatible with**. Then:

1. On success, a call probes nothing beyond A.3 and A.4.
2. On a refusal whose compatible rows give more than one result for the
   family, the kernel probes, cheapest call first. For example, delete-folder
   answers `NotFound` in both `Nothing` rows, so it never tells them apart.
3. A probe that decides whether the operation proceeds, or what it returns,
   fails closed: its failure is the operation's failure. A probe that only
   types a refusal that already happened fails open: the refusal stands
   (BE-021).

A driver obligation removes rows from a shape's compatible set, and the table
states it once. For example, "an encoding that refuses non-tree writes types
ENOTDIR as `NotFound`, never `PermissionDenied`" removes the
path-through-an-item row from `PermissionDenied`'s set. Without it the kernel
probes a `PermissionDenied`.

### A.9 Changes under an operation

A refusal before the operation's first page is read through A.5. A refusal
after it propagates. The bound is kept once per operation, not per request.
`delete_folder`'s `DirectoryNotEmpty`, when a writer adds under the tree
mid-walk, is the same rule.

### A.10 Conformance

Two generated suites. One crosses tree state with key, for the results in A.5.
The other crosses encoding property, raw state and refusal shape, for A.3, A.4
and A.8.
