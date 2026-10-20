# RFC-0021: The store is a tree, and each backend encodes it

## Status

Accepted, 2026-10-13, by the maintainer. Drafted 2026-10-12. Aligned with
[spec 051](../specs/051-store-tree.md) on 2026-10-15 (below). Tracked as
**BK-432**. PR #1127 (BK-389) was parked until this was decided, and resumes
against it: its open `delete_folder` findings are answered from it. Appendix A
landed as spec 003's
[BE-032](../specs/053-contract-kernel.md#be-032-the-store-tree-on-the-kernel)
with PR #1127, which is now the authority; the appendix stays as drafted.
Links (A.7) are stated there but not yet on the kernel.

## Summary

**The store is strictly a tree.** Backends map to it through a partial
`decode` function, and every operation is evaluated against that one logical
model, not against edge cases per operation or quirks of each backend's
geometry.

The tree is [spec 051](../specs/051-store-tree.md)'s (TREE-001 to TREE-012),
which states its structure. This RFC adds what that spec leaves out: what a
Key resolves to, how a backend encodes the tree, and what each operation
returns.

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
entry to be a directory, which is the tree's prefix closure (TREE-012).
Nothing maps a flat or implicit
encoding onto it, so the states the review kept hitting fall outside every
verified statement.

## Decisions

Each decision states what is decided. How it works is in
[Appendix A](#appendix-a), the draft of the spec section it becomes, and what
it costs is in [Impact](#impact).

### D0. Out of scope

How a caller's input string becomes a Key (spec 004's `RemotePath` and
BE-030's key rule), the root, the close posture, capability gating and
`glob`'s pattern rule are settled before the tree is consulted (BE-020,
BE-029, BE-030), and they are unchanged.

### D1. The store is a tree

The store is spec 051's tree, and its structure is stated there. A Key
resolves to an item, a folder or nothing. ([A.1](#a1-nodes-and-keys))

### D2. Each backend encodes the tree

A backend's raw state maps to the tree through a partial `decode` function.
Backends differ only in the properties of their encodings, which drivers
declare, and this RFC adds `links` to them. ([A.2](#a2-encodings))

### D3. A raw state that does not decode is not in the store

Listings omit such states, and an operation on a key that is an item answers
as the tree does. On a flat encoding, an operation on a key below an item
trusts the encoding instead of checking every ancestor. That is a stated
limit of the model. ([A.3](#a3-undecodable-states))

### D4. The library never writes a state that does not decode

Writing below an item, or writing an item over a folder, is `InvalidPath` on
every backend, within A.1's scope on name equality. The first replaces BE-008's
opt-in check. The second has no check today. Neither can stop another writer.
([A.4](#a4-writes))

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
for them a link that decodes is an item. A link that does not decode is
refused like an input the key rule refuses, and only `delete` removes it. The public
option comes later. ([A.7](#a7-links))

### D8. Refusals are observations of the encoding

After a refusal, the kernel probes only until the result for the operation's
family is decided, and replaces the refusal only with the result of a row
where the call must refuse, or with a listing's empty result on a row that
holds nothing. A probe that runs whether or not the call fails
fails closed. A probe that runs only because the call refused fails open, so
the refusal stands. Each driver obligation is stated once.
([A.8](#a8-observations))

### D9. Changes under an operation

A contradiction between one operation's observations is handled by BE-021's
first-page bound, applied once per operation. ([A.9](#a9-changes-under-an-operation))

### D10. Where the model lives

Spec 003 gains one section, drafted in Appendix A. The clauses it replaces
point to it. The model is also stated in Dafny, which checks the prose,
verified before this RFC is accepted: the tree, the flat encoding's `decode`
and its operations, and the refusal rule for both namespaces. Links and
changes under an operation are argued in prose only, and flat raw keys with
an empty segment are an open question.

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
| listing a link whose target is outside the root (D7) | Local | listed (read from `_local.py`: listings stat through links with no containment check; a dangling link and a loop are already skipped by `_listing_error`) | omitted and logged | none |
| a refused `get` or `delete` below an item, the refusal typed `InvalidPath` (A.8) | hierarchical | `InvalidPath` (measured on the kernel's fake with `FakeParentIsFile`) | `NotFound`, A.5's last row | one `stat` on that error path |
| a listing's first page refused with `NotFound` or `InvalidPath` on an existing folder (A.8 rule 4) | hierarchical | an empty listing (spec 003 BE-030's folder-key rule: a first-page `NotFound` or `InvalidPath` is empty) | the refusal stands, since `stat(k)` sees the folder | one `stat` on that error path |
| `delete_folder` refused with `PermissionDenied`, `AlreadyExists` or `InvalidPath` on an item, a non-empty folder or nothing (A.8) | hierarchical, folder objects | the refusal stands (`_probe_wanted` probes only `NotFound` and untyped; measured on the fake for `PermissionDenied` on an item and on nothing) | `InvalidPath`, `DirectoryNotEmpty` or `NotFound` | one `stat`, and for a folder one `list_page(limit=1)`, on that error path |
| recursive listing through a link to a folder in the root (D7) | Local | not descended (`os.walk(followlinks=False)`) | descended under `follow_within_root` | the linked subtree's listing |

Keyed calls on a link that does not decode keep today's Local answer,
`InvalidPath`. BE-021's cost table records the costs when the clauses land. A
stored key outside the addressable subset (`a\b`, A.2) is already omitted and
logged on the kernel, since BE-030 omits a listed key the rule would refuse or
rewrite. A recursive `delete_folder` over such a key already answers
`DirectoryNotEmpty` when it walks and removes the key when it runs
`delete_tree` (BE-030, BE-031), and A.3 keeps both routes, so that does not
change. A flat raw key with an empty segment is Open question 1 (BK-438),
which may change both.

- **Public API.** `reject_write_under_file_ancestor`, a constructor keyword on
  five flat backends (BE-008), loses its effect, since the check it enabled
  becomes unconditional. Each backend retires it when it moves onto the
  kernel. Until then BE-008's text keeps binding the backends not yet on the
  kernel, and spec 003 marks which clause binds which.
- **PR #1127** resumes against this model. `delete_folder` reads the shared
  resolver, which answers its first open spec finding. A.8 answers its second:
  a `PermissionDenied` is in the probe set, and drivers owe no rule about how
  a refusal is typed beyond A.8's two narrow ones (links, flat listings).
  The five open text findings are fixed against the new text.
- **Spec 003** gains Appendix A as one section. These texts are replaced by a
  pointer to it, for the backends on the kernel:
    - BE-030's *What is at a key*, with its list of determinants moved into A.8;
    - the folder and file-above rows of BE-008 and BE-021;
    - BE-008's flat exemption and its opt-in file-ancestor walk;
    - BE-031's probe rule, and its "a file and a prefix both" row.
- **Tests:** two generated suites (A.10) replace
  `tests/_kernel/test_condition_space.py`'s hand-assembled axes.
- **Formal model:** `Valid()` in `BackendContract.dfy` states the tree's
  prefix closure (TREE-012) over string paths, but not TREE-007's names: it
  admits an entry `a/` or `/a`, whose empty segment is no name. Only the
  paths its methods take are constrained, by the `WellFormedPath`
  precondition, which also excludes the names spec 004 refuses.
  `sdd/formal/StoreTree.dfy` states the model in Dafny and verifies with
  `bash scripts/dafny_verify.sh StoreTree.dfy`. CI's `verify-formal` job runs
  it. Mutants, each weakening one check or rule, fail verification; the
  trace's verify and align phases list each edit, the command and its count.
  It covers:
    - Dafny's `Key`, a sequence of spec 051's names (TREE-007) whose `Join`
      is TREE-009's Key, no two distinct sequences joining to the same
      string (TREE-010);
    - a valid tree is exactly a finite pair (L, K) meeting `Trie.WF`, the
      pairs that lemma L6 in `lean/StoreAxioms.lean` proves are, up to
      isomorphism, the models of spec 051's axioms (§12);
    - the tree and its resolution;
    - a flat encoding's partial `decode`, which yields a valid tree, for A.2's
      item-above-item state; a raw key with an empty segment is excluded by
      `Key`'s type and is Open question 1;
    - a flat lookup, a `list_page(k, limit=1)` and an ancestor `stat` agree
      with the tree's item, folder and through-an-item answers;
    - A.4's checks pass exactly where the tree's write does not answer
      `InvalidPath`, and a write they pass keeps the encoding decodable and
      agrees with the tree's write;
    - a flat listing of `k/` returns the tree's children of `k`;
    - a recursive `delete_folder` by walking deletes what its listings
      return, an omitted entry keeps the folder non-empty, and an item above
      the key hides nothing (A.3's limit);
    - a flat `move` or `copy` keeps the encoding decodable and moves or
      copies exactly its item;
    - a flat encoding holds no empty folder (A.6), raw keys with an empty
      segment aside;
    - A.8's refusal rule, for every call it names, each namespace and each
      row: the answer is the refusal or the A.5 result of the row actually
      there, and only a result rule 4 allows. Every row where the call must
      refuse is typed, and so is a listing's row that holds nothing, except a
      flat listing refused in a shape other than `NotFound` or `InvalidPath`,
      which stands. Enumerating it
      found a missing flat `delete_tree` row, which A.8 now has.

    Links (A.7), changes under an operation (A.9) and raw keys with an empty
    segment (open question below) are outside the sketch.
- **Local's and SFTP's links** decode by A.7's policy once each runs on the
  kernel. BUG-323, SFTP's recursive delete through a link at the key, is fixed
  independently of this RFC.
- **Follow-ups**, filed on acceptance: the public link option and a capability
  that exposes `links` (BK-433), and wiring the Dafny encodings into
  `BackendContract.dfy`'s operations (BK-434). Filed later: Open question 1
  (BK-438).

## Open Questions

A.8's tables and the Dafny sketch, owed before acceptance, are in. The sketch
covers what D10 names, and links and changes under an operation are argued in
prose only, as D10 states. One question is open:

1.  **Flat raw keys with an empty segment** (BK-438), on any flat encoding
    (S3, Azure without HNS, SQLAlchemy): a folder marker `a/`, and `a//b`,
    `a//` or `/a`, all written by another tool; the library writes none.
    On the kernel, BE-030 omits such a key from listings, so with only
    `a/`, `a//b` or `a//` stored the prefix `a/` makes `is_folder("a")` True
    while listings of `a` are empty: an empty folder, which A.6 rules out on
    a flat encoding. No flat driver runs on the kernel yet. Today's S3
    backends, measured on moto on 2026-10-15 (the server
    `infra._moto.start_moto_server` starts, one bucket per backend seeded with the
    one key by boto3 `put_object`, each call through the backend), answer
    as follows; all three agree unless a cell says otherwise:

    | Stored | `exists` / `is_folder` / `is_file("a")` | `list_folders("")` | `list_folders("a")` | `list_files("a")` |
    |---|---|---|---|---|
    | `a/` | T / T / F | `['a']` | `[]` | one file, name `""`, path `a` (s3fs, pyarrow); `[]` (boto3) |
    | `a//b`, `a//` | T / T / F | `['a']` | `['a']`, a phantom: `exists("a/a")` is F | `[]` |
    | `/a` | F / F / F | raises `InvalidPath` (empty after normalization) | `[]` | `[]` |

    With `a/` alone, s3fs and pyarrow also count the marker in
    `get_folder_info("a")`, and all three answer `DirectoryNotEmpty` for a
    non-recursive `delete_folder("a")`; only a recursive one removes it.
    Azure was not measured. How such keys decode is decided before any flat
    driver moves onto the kernel, checked against the services themselves.
    The maintainer's leaning: if the service holds a prefix with no object
    behind it, that prefix is an empty folder. Until then A.2 and A.6
    leave these keys out, A.3 keeps BE-030's omission on the kernel as the
    interim rule, and Impact claims no lasting behaviour for them.

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
  a refusal is typed (A.8). `delete_folder`'s narrower set goes. Narrowed
  later: two typing rules, for drivers with links and for flat listings
  (below).
- On a flat encoding, every operation on a key below an item trusts the
  encoding, folder operations included, so `delete("k/a.txt")` below an item
  removes the raw entry.
- After the closing round: A.8 is enumerated in Dafny, a probe replaces a
  refusal only on a row where the call must refuse (rule 4, widened by the
  next bullet for a listing's empty result), and a driver
  with links signals a link that does not decode with `InvalidPath`. A
  link that does not decode outranks the entry rule, so only `delete` removes
  it; a read of a link under `no_follow` is `InvalidPath`.
- A flat driver's `list_page` answers `NotFound` or `InvalidPath` only when
  nothing lies under the prefix (A.8), so a refused first page reads as empty
  without hiding entries. The verification pass after the closing round found
  the gap, and `StoreTree.dfy` §11 now models listings.
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

### Aligned with spec 051 (maintainer, 2026-10-15)

Spec 051 (TREE-001 to TREE-012) is the authority for the tree's structure,
and this RFC and `StoreTree.dfy` agree with it. A.1 points to it and separates
a Key from a caller's input (spec 004). `StoreTree.dfy`'s `Key` is a sequence
of names, taken from BK-434, with a lemma that two distinct Keys never join to
the same string. Flat raw keys with an empty segment, S3's folder markers
among them, are Open question 1 (BK-438), after two review rounds measured
that the three S3 backends treat a marker differently and that `a//b`, under
BE-030's omission on the kernel, would look the same to a caller. A stored `a\b` is a Key outside the addressable subset, not an
undecodable state. Resolution, and with it A.4 and every column of A.5,
holds where names compare exactly (A.1), and other equalities are left to
BK-436.

<a id="appendix-a"></a>
## Appendix A: draft of spec 003 § The store tree

This appendix becomes the spec section on acceptance. Until then it is the
proposal's detail, and the decisions above are what is being decided.

### A.1 Nodes and keys

- **The tree** is [spec 051](../specs/051-store-tree.md)'s: TREE-001 to
  TREE-012 state its folders and items, its names (TREE-007), its Keys
  (TREE-009) and that a Key names at most one entity (TREE-010). This section
  states none of them again. An item also has content and metadata, which
  that structure does not model. By TREE-001 and TREE-010, `is_file(k)` and `is_folder(k)`
  are never both true.
- **A Key is not a caller's input.** A caller passes an input string, and
  spec 004's `RemotePath` maps an accepted one onto a Key or rejects it (spec
  051 § Layering). BE-030's non-canonical rows (`d//f`, `d/./f`, `d/`) and
  root spellings (`./`) are inputs of that layer: each is mapped onto a Key,
  or refused, before the tree is consulted. A backend stores a
  *raw key*, its encoding's own spelling, which A.2 decodes. Below, "key"
  means a Key unless it says otherwise.
- A Key resolves to exactly one of `Item`, `Folder` or `Nothing`. Where an
  operation cares why there is nothing, the reason travels with the answer.
  The case that matters is a key whose path passes through an item, which
  makes a write `InvalidPath` (A.5).
- **Resolution assumes exact name equality**, as spec 051's names compare
  (§ Name equality), so A.4's checks and every column of A.5 hold where the
  encoding compares names exactly too. On a case-insensitive or normalizing
  encoding a Key can find an entry of another name (`read("A")` finds `a`);
  which backends compare names how, and how they then answer, is open under
  BK-436.
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
- under `follow_within_root`, a link whose target is outside the root, a
  dangling link, and a loop of links.

A flat raw key with an empty segment, such as a folder marker `a/` or `a//b`,
would give an empty name (TREE-007); how it decodes is Open question 1.

A stored key such as `a\b`, `..` or one holding NUL is not in that list. Spec
051's names forbid only `/`, so where its characters are in the spec's
alphabet Σ, which that spec leaves open, it decodes to a Key in the tree. That
Key lies outside the library's addressable subset: no input maps onto it, so no
keyed operation reaches it. Spec 004 refuses `..` (PATH-003) and NUL
(PATH-007), and folds `\` to `/` (PATH-002), so `a\b` as an input addresses
the Key `a/b` instead; BE-030's key rule refuses a stored `a\b`. Listings omit it and
log it, as BE-030 already does (BK-399's case), because no keyed operation
could act on what they returned. Addressing and `unwrap()` still reach it
(BE-030, BE-025).

### A.3 Undecodable states

- **Listings.** A listing of `k`'s parent that returns `k` as an item and `k/`
  as a prefix omits the prefix. A recursive listing omits every entry below an
  item it has listed. For that, a flat driver's `list_page` returns keys in
  byte-lexicographic order, so `k` arrives before every key below `k/`; that
  is a driver obligation, and hierarchical drivers stay unordered. A link
  that does not decode is omitted too. A raw key with an empty segment is
  omitted by BE-030's rule on the kernel until Open question 1 decides how it
  decodes. Each
  omission is logged. This extends BE-030's omission of a stored key outside
  the addressable subset (A.2), and the listing itself shows what to omit.
- **Folder operations on an item.** `list_files(k)` is empty and
  `delete_folder(k)` answers `InvalidPath` when `k` is an item. On a flat
  encoding, a listing of `k/` cannot see an item `k`, so a flat folder
  operation `stat`s `k` first, success included.
- **Keys below an item, on a flat encoding.** The probe, read-file and
  delete-file families do not walk their key's ancestors, and neither do the
  folder families: they `stat` the key alone. So `read("k/a.txt")` finds a raw
  entry another tool wrote below an item `k`, `delete("k/a.txt")` removes it,
  which is how such an entry is cleaned up, and `list_files("k/d")` lists
  `k/d/` as it stands. This is a stated limit of the model, where the tree
  would answer as A.5's last row. A.4 keeps the library's own writes from
  producing it.
- **A link that does not decode** is refused like an input the key rule refuses:
  every keyed operation answers `InvalidPath`, including a `move` from it,
  except `delete`, which removes the link (A.7). It never resolves to
  `Nothing`, so nothing is written through it. The driver signals it with
  `InvalidPath` from `stat` (A.8).
- **Omitted entries and `delete_folder`.** A recursive `delete_folder` that
  walks removes only what its listings return, so an omitted entry below the
  folder remains and the call answers `DirectoryNotEmpty`, as BE-030 already
  rules for a stored key outside the addressable subset. One that runs the driver's `delete_tree`
  removes the omitted entry with the rest, as BE-030 and BE-031 rule today;
  neither route changes. On a flat encoding, a recursive `delete_folder` of
  an item `k` answers `InvalidPath` and removes nothing, and a walk of `k`'s
  parent removes `k` and leaves `k/a.txt`, so it answers `DirectoryNotEmpty`.
- **`unwrap()`** reaches any raw entry.

### A.4 Writes

These writes are `InvalidPath` on every backend, within A.1's scope on name
equality:

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
| transfer | `move`, `copy`: the source as read-file, except that a `move` source names the entry at the key (A.7); the destination as write-file; in BE-018's order |

| Resolves to | probe `exists`/`is_file`/`is_folder` | read-file | write-file | delete-file | folder-read | delete-folder |
|---|---|---|---|---|---|---|
| `Item` | T / T / F | the item; a link under `no_follow` is `InvalidPath` (A.7) | replaced, or `AlreadyExists` without `overwrite`; a link under `no_follow` is `InvalidPath` (A.7) | removed | empty | `InvalidPath` |
| `Folder` | T / F / T | `InvalidPath` | `InvalidPath` | `InvalidPath` | its children | removed, or `DirectoryNotEmpty` |
| `Nothing` | F / F / F | `NotFound` | written, parents created | `NotFound` | empty | `NotFound` |
| `Nothing`, path through an item | F / F / F | `NotFound` | `InvalidPath` | `NotFound` | empty | `NotFound` |

The last row is what the tree answers. On a flat encoding the keyed families
and the folder families trust the encoding instead (A.3). For `delete`,
`delete_folder` and a `move` source, a link at the key that decodes resolves
to `Item` (A.7). A link that does not decode never reaches this table (A.3).
Every column holds where names compare exactly (A.1).
`missing_ok` turns a delete's `NotFound` into success. `get_folder_info`
types an empty aggregate as BE-017 states. The per-operation clauses keep what
is specific to them, such as `overwrite`, cursors, `max_depth` and the
synthesised write routes, and cite this table for the rest.

### A.6 Empty folders

The tree allows an empty folder. A folder becomes empty when its last child is
deleted or moved out. An encoding without folder objects cannot hold an empty
folder, so there it vanishes. With folder objects it stays. Whether a flat
raw key with an empty segment, such as a folder marker another tool wrote,
holds an empty folder is open (Open question 1).

### A.7 Links

- `links` is `none` for object stores and `present` where the wire has links:
  Local and SFTP.
- The store policy is `follow_within_root` (the default) or `no_follow`.
  Under `follow_within_root` a link decodes to its target's node, and a target
  outside the root does not decode. Under `no_follow` a link decodes to an
  item.
- **Entry operations.** `delete`, `delete_folder` and a `move` source name the
  entry at the key itself, so for them the last segment decodes under
  `no_follow` whatever the policy, and a link that decodes is an `Item`
  there. A.5's `Item`
  row then gives their answers: `delete` removes the link, never its target
  (BE-031's existing rule); `delete_folder` answers `InvalidPath`; `move` moves
  the link entry and leaves the target alone, as a rename does. Following a
  link there would delete or move its target's contents.
- **Every other operation** reads through a link under the store policy. Under
  `follow_within_root` a read or a `copy` from a link reads the target's
  content, and a write to a link goes to its target. Under `no_follow` a link
  has no content of its own, so read-file, a `copy` from it and a write to it
  are `InvalidPath`; replacing a link the store did not make would destroy it
  without a signal.
- **A link that does not decode** (its target outside the root, dangling, or
  in a loop) is refused like an input the key rule refuses (A.3). That outranks the
  entry rule: `move` of such a link is `InvalidPath`, and only `delete`
  removes it. The driver signals it (A.8's last obligation).

### A.8 Observations

A driver call observes the encoding, often only partly: a flat `stat` sees an
item but not a folder, and a `list_page(limit=1)` sees whether a folder is
empty. A refusal arrives as `NotFound`, `InvalidPath`, `AlreadyExists`,
`PermissionDenied`, an untyped `RemoteStoreError`, or another type.

**The probe set** is those first five shapes. Drivers owe no rule about which
of them a refusal takes, except the two typing rules at the end of this
section: a wire's ENOTDIR may arrive as any of them. Any other type
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
   the refusal stands (BE-021).
4. **A probe replaces the refusal only on a row where the call must refuse,
   or, for a listing, on a row that holds nothing.** A refusal in the probe
   set can meet any row, since a denial or a dead connection meets an
   existing item as well as a missing one. So when the probe concludes a row
   where A.5 gives the call success (an item for `get`, an empty folder for
   `remove_folder`, nothing for a write, a folder for a listing), the refusal
   stands. Otherwise that row's A.5 result replaces it.

The tables split by `namespace`, which decides what one `stat` sees; a
`parents="none"` driver on a hierarchical namespace takes the hierarchical
table, except that its `delete_folder` follows BE-031's `parents="none"`
sequence and so the flat `delete_tree` row, and it has no `remove_folder`.
`StoreTree.dfy` §11 enumerates every call these tables name (`get`,
`delete`, `put`, `ensure_parents`, `remove_folder`, `delete_tree`, the first
listing page; `move`, `copy` and `rename` as a source read and a destination
write), each namespace and each row, and proves rule 4: the answer is the
refusal, or the A.5 result of the row actually there where that row is one
on which the call must refuse or, for a listing, one that holds nothing.

**Flat namespace.** A `stat` sees an item or answers `None`; it cannot tell a
folder from nothing. Per call, after a refusal in the probe set:

| Call | Probe | Concludes |
|---|---|---|
| `get`, `delete` | `stat(k)`, then on `None` `list_page(k, limit=1)` | an item: the refusal stands; a non-empty listing: `InvalidPath`; an empty one: `NotFound` |
| `put`, `open_write`, commit | `stat(k)` (A.4's checks ran first, so the key is no folder and nothing above it is an item) | an item without `overwrite`: `AlreadyExists`; anything else: the refusal stands |
| `delete_tree` (BE-031's flat order) | `list_page(k, limit=1)` first, then `stat(k)` after an empty listing | a non-empty listing: the refusal stands; then an item: `InvalidPath`; `None`: `NotFound` |
| `list_page(k)`, first page | none: the only call that sees a flat folder is the listing that just failed, and A.3's `stat` ran first and found no item | a `NotFound` or `InvalidPath` is an empty listing, by the flat listing obligation below; any other shape stands |
| `move`, `copy` | the source as `get`, the destination as `put` | as those |

**Hierarchical namespace.** A `stat` sees an item or a folder. A miss is
`None`, or a `NotFound` or `InvalidPath`, since a POSIX `stat` below an item
raises ENOTDIR. Per call, after a refusal in the probe set:

| Call | Probe | Concludes |
|---|---|---|
| `get`, `delete`, a `move` or `copy` source | `stat(k)`, under `no_follow` for `delete` and a `move` source, which name the entry (A.7), and under the store policy for `get` and a `copy` source | an item: the refusal stands; a folder: `InvalidPath`; a miss: `NotFound` |
| write primitives (`put`, `open_write` and commit, `rename`, `copy`, `move` at the destination) | `stat(k)`, then on a miss the ancestors' `stat`s, shallowest first | a folder: `InvalidPath`; an item without `overwrite`: `AlreadyExists`; an item among the ancestors: `InvalidPath`; anything else: the refusal stands |
| `ensure_parents` | the ancestors' `stat`s | an item among them: `InvalidPath`, naming it; otherwise the refusal stands |
| `remove_folder` | `stat(k)` under `no_follow`, then for a folder `list_page(k, limit=1)` | an item: `InvalidPath`; a miss: `NotFound`; a non-empty folder: `DirectoryNotEmpty`; an empty folder: the refusal stands |
| `delete_tree`, with folder objects | `stat(k)` under `no_follow` | an item: `InvalidPath`; a miss: `NotFound`; a folder: the refusal stands |
| `list_page(k)`, first page | `stat(k)` | a folder: the refusal stands; anything else: an empty listing |

**What drivers owe instead**, each stated once here:

- A refusal changes nothing.
- `get` and `delete` refuse a key that is not an item, and every write
  primitive refuses a folder at its key or an item above it (hierarchical).
  `remove_folder` refuses anything but an empty folder, and `delete_tree`
  refuses an item, a link or nothing.
- A flat driver's `list_page` returns keys in byte-lexicographic order (A.3).
- `list_page` with `follow_links=False` never lists a link's target, and
  `delete` on a link removes the link (A.7).
- A driver declaring `links="present"` refuses a key whose link does not decode
  with `InvalidPath`, from `stat` and from every call, and types its own
  ENOTDIR as `NotFound`. So an `InvalidPath` from such a driver's `stat` means
  "does not decode", never a miss. This typing rule binds only drivers with
  links.
- A flat driver's `list_page` answers `NotFound` or `InvalidPath` only when
  nothing lies under the prefix, an absent container included (BE-021).
  Since the only call that sees a flat folder is the listing that just
  failed, this is what lets a refused first
  page read as empty without hiding entries. This typing rule binds only
  flat drivers' listings.

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
