# Operation catalogue

<!-- doc: repo-only -->

**Every operation v1's Store offers, one entry per intent, with what it
targets and the kind of result it gives; no signatures and no semantics.**
[Spec 053](../specs/053-store-operations.md) binds this table: v1 offers exactly
these entries, each in a sync and an async form, and an optional entry only
where its backend declares it. Each `/observe` session designs one entry, its
forms (bytes, text, stream) included; a session that finds the cut wrong
records a reopen ([RFC-0026](../rfcs/rfc-0026-operation-catalogue.md) C2).

## Needs

What a caller must be able to do, decided with the maintainer. An entry serves
one or more needs, and every need is served.

| ID | Group | Need |
|---|---|---|
| N-01 | Data in and out | Read or write a whole small item in one call, as bytes or text |
| N-02 | Data in and out | Read or write a large item chunk by chunk, without holding it in memory |
| N-03 | Data in and out | Replace an item so readers see the old or the new content, never a partial one |
| N-04 | Data in and out | Read parts of a large item at offsets |
| N-05 | Discovery | See what is directly inside one folder |
| N-06 | Discovery | See every item below a folder, at any depth or up to a depth |
| N-07 | Discovery | Find the items whose keys match a pattern |
| N-08 | Discovery | Tell whether a key exists, whether it is an item or a folder, and its size and modification time |
| N-09 | Organising | Remove one item |
| N-10 | Organising | Remove a folder and everything below it |
| N-11 | Organising | Give an item or a folder a new key |
| N-12 | Organising | Duplicate an item or a folder under a new key in the same store |
| N-13 | Integration | Move content between the store and a local file |
| N-14 | Integration | Copy items from one store to another |
| N-15 | Integration | Work in a store rooted at one of its folders |
| N-16 | Integration | Hand items to other libraries as files or a file system |
| N-17 | Further | Write only if an item is absent, or unchanged since it was read |
| N-18 | Further | Learn what a store supports and where it deviates |
| N-19 | Further, optional | Make a folder that holds nothing yet |
| N-20 | Further, optional | Attach key-value metadata to an item and read it back |
| N-21 | Omission check | Release a store's resources when done with it |
| N-22 | Omission check | Map a key to the backend's own address of it, and back |
| N-23 | Omission check | Reach the backend's own client, outside the library's guarantees |
| N-24 | Omission check | Tell cheaply, without changing anything, whether the store is reachable |

N-21 to N-24 are no use case the maintainer chose; they were kept when the
draft entries were checked against 0.33's surface for omissions.

## Entries

**Columns.** *Target* is what the entry addresses: `item`, `folder`, `any`
(item or folder), `pattern`, `store`, `store pair`, or a pair of those with a
local path. *Result* is the kind of thing a caller gets: `content`, `reader`
(an object read from at offsets), `outcome` (whether and how the call took
effect), `listing`, `info`, `store`, `answer`, `address`, `adapter` (an object
another library reads the store through), `client` (the backend's own). *Offer* is
`v1` (every store) or `optional` (spec 053's gate). *Session* is the entry's
`/observe` status: `not started`, `designed` (its record is accepted) or
`specified` (its spec is ground).

| ID | Intent | Target | Result | Offer | Serves | Session |
|---|---|---|---|---|---|---|
| OP-01 | Read an item, whole or streamed | item | content | v1 | N-01, N-02 | not started |
| OP-02 | Read an item at offsets | item | reader | v1 | N-04 | not started |
| OP-03 | Write an item, whole or streamed | item | outcome | v1 | N-01, N-02 | not started |
| OP-04 | Replace an item atomically | item | outcome | v1 | N-03 | not started |
| OP-05 | Write an item conditionally: if absent, or if unchanged | item | outcome | v1 | N-17 | not started |
| OP-06 | List a folder's children | folder | listing | v1 | N-05 | not started |
| OP-07 | Walk a subtree, optionally to a depth | folder | listing | v1 | N-06 | not started |
| OP-08 | Match keys by pattern | pattern | listing | v1 | N-07 | not started |
| OP-09 | Inspect a key: whether it exists, its kind, size and time | any | info | v1 | N-08 | not started |
| OP-10 | Delete an item | item | outcome | v1 | N-09 | not started |
| OP-11 | Delete a folder tree | folder | outcome | v1 | N-10 | not started |
| OP-12 | Move or rename | any, to a key | outcome | v1 | N-11 | not started |
| OP-13 | Copy within a store | any, to a key | outcome | v1 | N-12 | not started |
| OP-14 | Transfer to or from a local file | any and local path | outcome | v1 | N-13 | not started |
| OP-15 | Transfer between stores | store pair | outcome | v1 | N-14 | not started |
| OP-16 | Scope a store to a folder | folder | store | v1 | N-15 | not started |
| OP-17 | Hand items to other libraries | store | adapter | v1 | N-16 | not started |
| OP-18 | Ask what a store supports | store | answer | v1 | N-18 | not started |
| OP-19 | Create an empty folder | folder | outcome | optional | N-19 | not started |
| OP-20 | Attach and read user metadata | item | info | optional | N-20 | not started |
| OP-21 | Close a store | store | outcome | v1 | N-21 | not started |
| OP-22 | Map a key to its native address, and back | any | address | v1 | N-22 | not started |
| OP-23 | Reach the native client | store | client | v1 | N-23 | not started |
| OP-24 | Check health | store | answer | v1 | N-24 | not started |

## Sources

The needs and entries are the maintainer's, from the dialogs in
`sdd/decisions/3f9651c0-09db-5c69-8bbb-77ea5f97177e.jsonl` (2026-10-26).
