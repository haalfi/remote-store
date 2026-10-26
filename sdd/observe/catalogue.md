# Operation catalogue

<!-- doc: repo-only -->

**The intents v1's core API serves through its store handles, one entry each,
with what each targets and the kind of result it gives; no signatures and no
semantics.**
[Spec 053](../specs/053-store-operations.md) binds this table: v1 offers exactly
these entries, each in a sync and an async form. The Offer column binds through
OP-18's spec, the one place that answers what a store supports. Each `/observe` session designs one entry, its
forms (bytes, text, stream) included; a session that finds the cut wrong
records a reopen ([RFC-0026](../rfcs/rfc-0026-operation-catalogue.md) C2).

## Needs

What a caller must be able to do, decided with the maintainer. An entry serves
one or more needs, and every need is served.

| ID | Group | Need |
|---|---|---|
| N‑01 | Data in and out | Read or write a whole small item in one call, as bytes or text |
| N‑02 | Data in and out | Read or write a large item chunk by chunk, without holding it in memory |
| N‑03 | Data in and out | Replace an item so readers see the old or the new content, never a partial one |
| N‑04 | Data in and out | Read parts of a large item at offsets |
| N‑05 | Discovery | See what is directly inside one folder |
| N‑06 | Discovery | See every item below a folder, at any depth or up to a depth |
| N‑07 | Discovery | Find the items whose keys match a pattern |
| N‑08 | Discovery | Tell whether a key exists, whether it is an item or a folder, its size and modification time, and, where the backend offers one, a token that changes when the item does |
| N‑09 | Organising | Remove one item |
| N‑10 | Organising | Remove a folder and everything below it |
| N‑11 | Organising | Give an item or a folder a new key |
| N‑12 | Organising | Duplicate an item or a folder under a new key in the same store |
| N‑13 | Integration | Move content between the store and a local file or folder |
| N‑14 | Integration | Copy items from one store to another |
| N‑15 | Integration | Work in a store rooted at one of its folders |
| N‑16 | Integration | Hand items to other libraries as files or a file system |
| N‑17 | Further | Write only if an item is absent, or unchanged since it was read |
| N‑18 | Further | Learn what a store supports and where it deviates |
| N‑19 | Further, optional | Make a folder that holds nothing yet |
| N‑20 | Further, optional | Attach key-value metadata and system properties (such as content type) to an item, and read them back, as far as the backend supports them |
| N‑21 | Omission check | Release a store's resources when done with it |
| N‑22 | Omission check, optional | Map a key to the backend's own address of it, and back |
| N‑23 | Omission check, optional | Reach the backend's own client, outside the library's guarantees |
| N‑24 | Omission check | Tell cheaply, without changing anything, whether the store is reachable |

N-21 to N-24 are no use case the maintainer chose; they were kept when the
draft entries were checked against 0.33's surface for omissions.

## Entries

**Columns.** IDs in both tables are written with a non-breaking hyphen
(U+2011) so they never wrap; search them as `OP.NN` or `N.NN`. *Target* is
what the entry addresses: `item`, `folder`, `any` (item or folder), `pattern`
or `store`; an entry with a destination names the source with it: `any, to a
key`, `any, to a store` or `any and local path`. *Result* is the kind of thing a caller gets: `content`, `reader`
(an object read from at offsets), `outcome` (whether and how the call took
effect), `listing`, `info`, `store`, `answer`, `address`, `adapter` (an object
another library reads the store through), `client` (the backend's own). *Offer* is
`v1` (every store) or `optional` (only where the backend declares it).

| ID | Intent | Target | Result | Offer | Serves |
|---|---|---|---|---|---|
| OP‑01 | Read an item, whole or streamed | item | content | v1 | N‑01, N‑02 |
| OP‑02 | Read an item at offsets | item | reader | v1 | N‑04 |
| OP‑03 | Write an item, whole or streamed | item | outcome | v1 | N‑01, N‑02 |
| OP‑04 | Replace an item atomically | item | outcome | v1 | N‑03 |
| OP‑05 | Write an item conditionally: if absent, or if unchanged | item | outcome | v1 | N‑17 |
| OP‑06 | List a folder's children | folder | listing | v1 | N‑05 |
| OP‑07 | Walk a subtree, optionally to a depth | folder | listing | v1 | N‑06 |
| OP‑08 | Match keys by pattern | pattern | listing | v1 | N‑07 |
| OP‑09 | Inspect a key: whether it exists, its kind, size and time | any | info | v1 | N‑08 |
| OP‑10 | Delete an item | item | outcome | v1 | N‑09 |
| OP‑11 | Delete a folder tree | folder | outcome | v1 | N‑10 |
| OP‑12 | Move or rename | any, to a key | outcome | v1 | N‑11 |
| OP‑13 | Copy within a store | any, to a key | outcome | v1 | N‑12 |
| OP‑14 | Transfer to or from a local file or folder | any and local path | outcome | v1 | N‑13 |
| OP‑15 | Transfer between stores | any, to a store | outcome | v1 | N‑14 |
| OP‑16 | Scope a store to a folder | folder | store | v1 | N‑15 |
| OP‑17 | Hand items to other libraries | store | adapter | v1 | N‑16 |
| OP‑18 | Ask what a store supports | store | answer | v1 | N‑18 |
| OP‑19 | Create an empty folder | folder | outcome | optional | N‑19 |
| OP‑20 | Attach and read item metadata: user metadata and system properties | item | info | optional | N‑20 |
| OP‑21 | Close a store | store | outcome | v1 | N‑21 |
| OP‑22 | Map a key to its native address, and back | any | address | optional | N‑22 |
| OP‑23 | Reach the native client | store | client | optional | N‑23 |
| OP‑24 | Check health | store | answer | v1 | N‑24 |

**What `v1` promises.** Every store offers a `v1` entry under the one contract
its spec states. Where part of it depends on the backend, such as OP-09's
token, the entry stays `v1` and its session declares the variation as a
profile of that contract (spec 053, Notes;
[RFC-0024](../rfcs/rfc-0024-spec-first-reset.md) D6).

## Not in v1

Operations comparable libraries offer that no entry names, from the deep
research ([`research-operation-catalogue.md`](../research/research-operation-catalogue.md),
Q1). *Form of OP-NN* is undecided: that entry's session decides whether v1
offers it as a form of the entry. *Not in v1* is out of v1's core; an
extension may add it on top of the entries, as it may add content hashing.

| Operation | Disposition |
|---|---|
| Batch delete | Form of OP-10 |
| Abort an in-flight write | Form of OP-03 |
| Multi-range read | Form of OP-02 |
| Delete only a folder's contents, or only an empty folder | Form of OP-11 |
| Update metadata or system properties after the write | Form of OP-20 |
| Backend-verified checksum on upload (Content-MD5, a checksum algorithm) | Form of OP-03 |
| Touch (write an empty item) | Form of OP-03 |
| Conditions on read, delete, copy or move | Not in v1; OP-05 conditions writes only |
| Presigned URL | Not in v1 |
| Append | Not in v1 |
| Versioned access, restore | Not in v1 |
| Server-side compose, storage class, retention, legal hold, tags apart from metadata, query in place | Not in v1 |
| Bucket or container create and delete | Not in v1 |
| Local cache layer, transparent compression, transactions | Not in v1 |
| Key-value mapping view | Form of OP-17 |
| Rsync-style mirroring | Form of OP-15 |
| FUSE mount | Not in v1 |
| Leases, snapshots, aborting a server-side copy | Not in v1 |
| Annotations (large attached payloads) | Not in v1 |

## Sources

The needs and entries are the maintainer's, from the dialogs in
`sdd/decisions/3f9651c0-09db-5c69-8bbb-77ea5f97177e.jsonl` (2026-10-26), revised
against the deep research in
`sdd/decisions/c886d81c-7d81-58f9-bc3d-f11dc7304e4a.jsonl`.
