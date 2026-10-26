# BK-493 — The v1 Store API has no agreed set of operations, so each design session would find its own scope
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** The maintainer, after spec 052 merged (2026-10-26):
besides what is in a store (spec 051) and how a key addresses it (spec 052),
the operations need an intended API surface, discussed, scoped and designed
before the first `/observe` session on `read()`. The first `/observe` run
(`exists`, [BK-485's dossier](bk-485-spec-first-reset.md)) had already found
that decisions binding every operation have no home.

## Decisions taken (2026-10-26)

From the dialogs in `sdd/decisions/3f9651c0-09db-5c69-8bbb-77ea5f97177e.jsonl`:

| Question | Decision |
| --- | --- |
| Depth | Inventory plus intent plus the decisions shared by every operation; no signatures, no semantics. |
| Input | Use cases first, 0.33's surface as an omission check only. |
| Granularity | One entry per intent; forms (bytes, text, stream) belong to the entry's session. |
| Async | A full async twin: every entry exists on `Store` and `AsyncStore`. |
| Use cases | All sixteen offered, in four groups: data in and out, discovery, organising, integration. |
| Optional | Create an empty folder and user metadata: offered only by a backend that declares support. |
| Required beyond the use cases | Conditional write; asking what a store supports. |
| From 0.33's surface | Store lifecycle, native address mapping, native handle escape hatch, health check. |
| Placement | Spec 053 binds; `sdd/observe/catalogue.md` holds one row per entry, ground for every session. The spec cites the table and never copies it. |
| Process | One PR: this item, RFC-0026 amending RFC-0024 § 9, spec 053 and the catalogue, revised once the deep research lands. |
| Research | The maintainer runs a deep research in their research repo from the brief below; its doc is filed under `sdd/research/` as background. |

## Status (2026-10-26)

Done on branch `bk-493-operation-catalogue` (from master at `e285319`), all
drafts: this item's index entry and dossier, the trace
`sdd/traces/bk-493-operation-catalogue.yml`,
[RFC-0026](../rfcs/rfc-0026-operation-catalogue.md),
[`sdd/observe/catalogue.md`](../observe/catalogue.md) and
[spec 053](../specs/053-store-operations.md), with the ground register's two
rows and D7 headers on specs 001 and 029. Three decisions of the second
session (`sdd/decisions/c886d81c-7d81-58f9-bc3d-f11dc7304e4a.jsonl`) changed the plan
above: the catalogue carries no 0.33 column, since it is ground (the table
below is the omission check's record); spec 053 supersedes STORE-008 and
ASYNC-046; its Tested against is `None.`, with the reason in its Notes.

The deep research landed the same day and is filed as
[`research-operation-catalogue.md`](../research/research-operation-catalogue.md);
its filing note records what the catalogue took from it (RFC-0026 C5). The
maintainer accepted RFC-0026 in PR #1184's review, which closes this item.

From an outside review on PR #1184 (the maintainer's dialog in
`sdd/decisions/c886d81c-7d81-58f9-bc3d-f11dc7304e4a.jsonl`): OP-22 and OP-23
are optional, since a backend may have no native client or address; OP-05
stays `v1`, and where a backend has no change token its profile refuses "if
unchanged" rather than check it apart from the write. That last decision is
semantics, so it is not in the ground: it is input the maintainer names at the
start of OP-05's session (research § 4, S3).

From review round 3 (same log): spec 053 keeps only OPS-001 and OPS-002, the
closed surface, which can be checked without a call. The Offer column binds
through OP-18's spec, the one place that answers what a store supports; the
retired OPS-003 and OPS-004 are input to OP-18's session. RFC-0026 amends
RFC-0024 § R4 for spec 053's missing test.

From the verification round (same log): every row of the research's Q1 table
now has a disposition in the catalogue's Not in v1 list, post-write metadata
update as a form of OP-20. An outside formal-definition table (Gemini) was not
adopted: it fixed signatures each entry's session decides, and its framing is
already how an entry's spec is written (SPEC-DESIGN Rules 2 and 4).

**Draft entries and the 0.33 omission check** (one per intent; 0.33
counterpart checked against `src/remote_store/_store.py` and `ext/` at
`e285319`; not ground, RFC-0026 C4):

| ID | Intent | 0.33 counterpart |
| --- | --- | --- |
| OP-01 | Read an item, whole or streamed | `read`, `read_bytes`, `read_text` |
| OP-02 | Read an item at offsets | `read_seekable` (SEEKABLE_READ) |
| OP-03 | Write an item, whole or streamed | `write`, `write_text` |
| OP-04 | Replace an item atomically | `write_atomic`, `open_atomic` |
| OP-05 | Write conditionally (if absent, if unchanged) | `write(overwrite=False)`, if absent only |
| OP-06 | List a folder's children | `iter_children`, `list_files`, `list_folders` |
| OP-07 | Walk a subtree, optionally depth-limited | `list_files(recursive, max_depth)`, `list_folders(max_depth)` |
| OP-08 | Match keys by pattern | `glob`, `list_files(pattern)`, `list_folders(pattern)` |
| OP-09 | Inspect: exists, kind, size, time | `exists`, `is_file`, `is_folder`, `get_file_info`, `get_folder_info`, `head` |
| OP-10 | Delete an item | `delete` |
| OP-11 | Delete a folder tree | `delete_folder` |
| OP-12 | Move or rename | `move` |
| OP-13 | Copy within a store | `copy` |
| OP-14 | Transfer to or from local disk | `ext.transfer.upload`, `download` |
| OP-15 | Transfer between stores | `ext.transfer.transfer` |
| OP-16 | Scope a store to a folder | `child` |
| OP-17 | Hand items to other libraries | `ext.arrow.pyarrow_fs` |
| OP-18 | Ask what a store supports | `supports` |
| OP-19 | Create an empty folder (optional, gated) | — |
| OP-20 | User metadata (optional, gated) | `write(metadata=)`, USER_METADATA |
| OP-21 | Store lifecycle (close, context manager) | `close`, `aclose` |
| OP-22 | Native address mapping | `native_path`, `to_key`, `resolve` |
| OP-23 | Native handle escape hatch | `unwrap` |
| OP-24 | Health check | `ping` |

Every public method of `Store` (`src/remote_store/_store.py`) and `AsyncStore`
(`src/remote_store/aio/_async_store.py`) at `e285319` appears in this column,
checked against each file's `def` lines (Grep
`^    (async )?def [a-z]`). So no 0.33 Store method is left without an entry.
Of `ext/`'s fifteen modules (Glob `src/remote_store/ext/*.py`, less
`__init__.py`), only `transfer` and `arrow` are mapped, for the use cases
N-13, N-14 and N-16. The other thirteen are not checked here: an extension
builds on the entries (spec 053, Notes).

## Research brief

Hand this section to the deep-research run with the draft entries above, or
with `sdd/observe/catalogue.md` and `sdd/specs/053-store-operations.md` once a
commit carries them.

**Goal.** Test the drafted operation catalogue of `remote-store` v1, a Python
library that gives one API over local disk, in-memory, S3, SFTP and Azure
storage, against what comparable libraries offer. The catalogue lists *what*
v1 offers, one entry per intent; *how* each entry behaves is designed later,
one entry per session. The research informs the catalogue; it decides nothing.

**Questions.**

1. **Completeness.** Which operations do the comparable libraries offer that
   no catalogue entry covers? For each, the use case it serves and how many of
   the libraries offer it.
2. **The cut.** Where would the comparables split or merge entries
   differently, for example write against atomic replace against conditional
   write, or list against walk against pattern match? What each choice costs a
   caller.
3. **Optional entries.** Which operations do the comparables gate on a
   backend's capability, and how does a caller learn of the gate (a query, an
   error, documentation)?
4. **Shared decisions.** What do the comparables decide once for every
   operation rather than per operation: key validation, error taxonomy,
   timeouts and retries, consistency, closing, async parity?
5. **Pitfalls.** Per entry, the object-store or filesystem behaviours that
   made comparables change or split an operation, cited, as notes for the
   entry's later session. No proposal of semantics.

**Comparables.** fsspec, `pyarrow.fs`, Apache OpenDAL (Rust core and its
Python binding), Rust `object_store` (arrow-rs), Go `gocloud.dev/blob`,
`smart_open`, `cloudpathlib`, and the AWS S3, Azure Blob and Google Cloud
Storage SDKs. Others where a question needs them.

**Rules.** Cite every claim with a link and the version or date read. Tell
documented behaviour apart from observed. Do not read `remote-store`'s 0.33
code or specs as an authority; the catalogue's 0.33 column is only an
omission check.

**Output.** One Markdown doc: a dated header, the sources with versions, one
section per question, and a table of catalogue entry against comparable (who
offers it, under which name, gated or not). Recommendations are marked
advisory.
