# Research: The v1 operation catalogue against comparable libraries (BK-493)

**Date:** 2026-10-26
**Backlog items:** BK-493 (The v1 Store API has no agreed set of operations, so each design session would find its own scope)
**Status:** Research complete. Background to [RFC-0026](../rfcs/rfc-0026-operation-catalogue.md); it decides nothing. Not ground: its per-entry notes are for each entry's own session (RFC-0026 C4).

---

**Ten comparable libraries cut the catalogue's operations in different ways,
and the most widely offered operation with no draft entry, a presigned URL, is
in 8 of them.** The cut stands, OP-20 and OP-09 widen, and every other
operation found gets a disposition in the catalogue's Not in v1 list (§ 3). What the comparables most often had to
retrofit is input to each entry's session, not to the catalogue.

## 1. Question and method

The maintainer tested the draft catalogue against what comparable libraries
offer, from the brief in [BK-493's dossier](../backlog/bk-493-operation-catalogue.md):
completeness (Q1), the cut (Q2), which entries are gated and how a caller
learns it (Q3), what is decided once for every operation (Q4), and pitfalls
per entry (Q5). The full report, with a citation per claim, is
[`reports/remote-store v1 operation catalogue verified.md`](https://github.com/haalfi/research/blob/b0e426f875c6de42730cd5fa15b3daf6ca4185b6/reports/remote-store%20v1%20operation%20catalogue%20verified.md)
in the `haalfi/research` repository at `b0e426f`. This document keeps
its results and their consequences for the Store API.

**Comparables (10, the denominator for every "n/10"):** fsspec, pyarrow.fs,
Apache OpenDAL (Rust core and Python binding, counted as one), Rust
`object_store`, Go `gocloud.dev/blob`, smart_open, cloudpathlib, and the AWS
S3 (boto3), Azure Blob and Google Cloud Storage SDKs. Hadoop FileSystem,
paramiko/SFTP and obstore are cited where needed but not counted. Versions are
in § Sources; all were read on 2026-10-26.

**Evidence.** Claims rest on documentation or released source unless marked.
*Inference* marks the researcher's own reading. *Observed* marks a claim seen
by running pyarrow, smart_open and cloudpathlib against local disk and the
moto S3 emulator; *observed on MinIO* marks the user's run against a MinIO
server of unstated version. Nothing was run against real AWS, Azure or GCS. Counts are lower bounds: an operation counts only where found in a
full text.

---

## 2. Results

### Q1. Completeness: operations no draft entry covered

| Operation | Use case | Count |
|---|---|---|
| Presigned or signed URL | Time-limited access without credentials | 8/10 |
| System properties (content type, cache control) apart from user metadata | HTTP serving | 7/10 |
| Batch delete | Many keys in few requests | 6/10 |
| Versioned access | History, recovery, pinned reads | 6/10 |
| Integrity and identity tokens (checksums, unique keys, verified MD5) | Verify transfers, detect change without reading | 6/10 |
| Append | Logs | 6/10, always gated, sometimes emulated |
| Conditional read | Skip the transfer if unchanged | 5/10 |
| Abort an in-flight write | Drop a streamed or multipart upload | 5/10 |
| Bucket or container create and delete | Provisioning | 5/10 |
| Server-side compose, restore or undelete | Concatenation, recovery | 4/10 each |
| Multi-range read | Columnar formats | 3/10 |
| Delete only a folder's contents, or only an empty folder | Guardrails | 3/10 |
| Storage class, retention or legal hold | Cost, compliance | 3/10 each |
| Post-write metadata update | Fix a content type after upload | 2/10 native (Azure, GCS); S3 rewrites the object |
| Local cache layer, transparent compression, `touch`, tags, query in place | Various | 2/10 each |
| Transaction, key-value view, FUSE mount, rsync, leases, snapshots, aborting an async copy, annotations | Various | 1/10 each |

Absent almost everywhere: OP-07's depth limit (fsspec only), OP-18's
capability query (OpenDAL only) and OP-24's health check (OpenDAL and gocloud
only; the vendor SDKs' calls in § 5's row 24 check that a bucket or container
exists, and are not counted as health checks, inference).

### Q2. The cut

- **Write, atomic replace, conditional write (OP-03 to OP-05).** The
  comparables merge them: a condition is a mode of put (object_store
  `PutMode::{Overwrite, Create, Update}`, every put atomic), and the vendor
  stores attach conditions to read, delete, copy, rename and metadata update
  as well. OpenDAL publishes a conditional-operations specification: a
  condition is never silently ignored, a mutation condition is advertised only
  if it is evaluated atomically with the visible commit (stat-then-mutate
  emulation is forbidden), staged writes evaluate it at the final commit, and
  where the error surfaces is unspecified. fsspec's `mode="create"` is exactly
  that forbidden emulation (inference). Atomic replace is a separate operation only on
  filesystems (`os.replace`, SFTP `posix_rename`); on object stores every PUT
  is atomic.
- **List, walk, match (OP-06 to OP-08).** The least agreed cut. gocloud has
  one prefix-and-delimiter listing; object_store separates a recursive listing
  from a delimited one; pyarrow merges inspect, list and walk into one call;
  fsspec and cloudpathlib keep separate calls. Depth and pattern are emulated
  client-side at O(subtree) cost (inference); only GCS matches a glob
  server-side.
- **Inspect (OP-09).** The comparables lean to one rich inspect call with
  derived probes; Hadoop deprecated single-attribute probes. The identity
  fields it returns are opaque tokens, not content hashes (Q4).
- **Delete (OP-10, OP-11).** Tree delete is one call where it exists (fsspec,
  pyarrow, cloudpathlib, OpenDAL); object_store and gocloud have none.
- **Copy and transfer (OP-13 to OP-15).** fsspec splits by locality; pyarrow's
  `copy_files` merges local and cross-store transfer; object_store copies
  within one store only.
- **Read (OP-01, OP-02).** pyarrow splits sequential from random reads;
  object_store folds ranges into one get with options.

### Q3. Gating and how a caller learns it

| Strategy | Who |
|---|---|
| Declared and checked before dispatch | OpenDAL: `capability()` with about 90 to 100 flags, a pre-dispatch check, and for conditions "never silently ignored" |
| Configured per store, then an error at call time | object_store, which also ignores unsupported tags but errors on unsupported attributes |
| Error at call time only | gocloud, pyarrow, cloudpathlib, smart_open |
| Silent emulation or no-op | fsspec `mkdir` does nothing and `mv` is copy plus delete; cloudpathlib `mkdir` does nothing; pyarrow drops metadata keys; smart_open ignores unknown parameters |
| Path-scoped probe | Hadoop `hasPathCapability`, where False may mean unknown |

OpenDAL gates create_dir, rename, copy, recursive listing, user metadata,
append, presign and the conditional and versioned variants, which matches the
catalogue's optional OP-19 and OP-20. Several gates depend on bucket or
account type and are only found at runtime: Azure rename and recursive delete
need a hierarchical namespace, S3 `RenameObject` needs Express One Zone.
OpenDAL's flags are the effective set, simulations included, and were missed
and fixed piecemeal.

### Q4. Decided once for every operation

| Decision | What the comparables do |
|---|---|
| Key validation | object_store rejects or encodes `.`/`..` and empty segments; OpenDAL passes `..` through; gocloud escapes per driver; pyarrow, smart_open and cloudpathlib normalise none of `..`, `.` or `//` (observed). Vendor limits: S3 and GCS 1024 bytes, Azure 1024 characters and 254 segments |
| Error taxonomy | object_store `Error` enum and OpenDAL `ErrorKind`, each with NotFound, AlreadyExists, a precondition kind and an unsupported kind; gocloud `ErrorCode`; fsspec and pyarrow builtins |
| Retries | object_store built in, retrying a timeout only if the request is idempotent; OpenDAL opt-in, temporary errors only; s3fs an allow-list; gocloud not portable (inference); GCS retries deletes by default |
| Timeouts | per instance or per call: object_store 30 s, OpenDAL 60 s (opt-in), botocore 60 s, Azure 20 s to connect and 60 s to read, GCS 60 s; gocloud per call |
| Consistency stated | atomic put (object_store); strong read-after-write including list (S3, Azure, GCS); gocloud's list may miss recent writes |
| Identity token | ETag and version are opaque. An S3 ETag is an MD5 only for a single-part plaintext or SSE-S3 upload; multipart, SSE-C/KMS and directory buckets give no MD5, and a metadata-only change leaves the ETag alone |
| Closing | gocloud `Bucket.Close`; vendor `close()`; OpenDAL `Operator`, fsspec and pyarrow have none; object_store relies on Drop (inference) |
| Async parity | OpenDAL Python is not at parity (presign is async-only); fsspec and Azure offer both; boto3 and GCS are sync only |
| Prefix scope (OP-16) | object_store `PrefixStore`, OpenDAL `root`, gocloud `PrefixedBucket`, fsspec `DirFileSystem`, pyarrow `SubTreeFileSystem` |

`..` containment was retrofitted in three libraries in 2026 (fsspec
DirFileSystem, OpenDAL fs, cloudpathlib).

### Advisory notes (the report's, not decisions)

1. **Additions or explicit exclusions:** presign (8/10), system properties next
   to OP-20 (7/10), batch delete, versioned access, integrity and identity
   tokens (6/10 each), append (6/10), conditional read and abort (5/10 each),
   multi-range read (3/10), delete guardrails (3/10), post-write metadata
   update (2/10 native).
2. **OP-05's scope.** The vendor stores and OpenDAL attach conditions to more
   than writes; OpenDAL's specification defines them once: no silent drop,
   atomic with the commit, the error point unspecified, status codes alone not
   deciding the error kind.
3. **OP-07's depth limit** has one precedent (fsspec) and costs O(subtree) on
   object stores.
4. **OP-09 and OP-14:** ETag and version are opaque identity tokens; an S3 ETag
   cannot double as an integrity check.
5. **OP-18:** OpenDAL's effective flags with a pre-dispatch check, Hadoop's
   "False means unknown", gates that depend on bucket type; object_store mixes
   silently ignoring one option with erroring on another.
6. **OP-24:** a thin precedent (2/10), and the two disagree on whether a
   missing root is healthy.
7. **Shared decisions most often retrofitted:** `..` containment, missing-key
   delete, exception typing in Python bindings, sync and async parity in
   bindings, retry coupled to idempotency, behaviour on an exception during a
   streamed write.

---

## 3. Consequences for the Store API

What the catalogue and spec 053 took from the results (decision log
`sdd/decisions/c886d81c-7d81-58f9-bc3d-f11dc7304e4a.jsonl`):

| Result | Consequence |
|---|---|
| Conditions attach to read, delete, copy and rename too (Q2, note 2) | OP-05 stays a conditional write; conditions on other entries are not in v1 |
| List, walk and match is the least agreed cut; one precedent for a depth limit (Q2, note 3) | OP-06 to OP-08 stay three entries; OP-07 keeps its depth limit |
| System properties (7/10) and identity tokens (6/10) have no entry (Q1) | OP-20 holds user metadata and system properties; OP-09's info holds an identity token where the backend offers one |
| pyarrow and OpenDAL expose no native handle, boto3 no address mapping (§ 5, rows 22 and 23); an outside review on PR #1184 raised it | OP-22 and OP-23 are optional |
| Batch delete, abort, multi-range read, delete guardrails, post-write metadata update, checksum verification, `touch`, a key-value mapping view, rsync-style mirroring (Q1, § 5) | Forms of OP-10, OP-03, OP-02, OP-11, OP-20, OP-03, OP-03, OP-17 and OP-15, for those entries' sessions |
| Every other Q1 operation | Not in v1; an extension may add one on top of the entries |
| Gates are found at call time or silently ignored almost everywhere (Q3) | One place answers what a store supports, OP-18, whose spec binds the catalogue's Offer column |
| Shared decisions most often retrofitted (note 7) | `..` containment is spec 052's and async parity spec 053's; the rest is input to `read()`'s session and each later one (RFC-0026 Open Question 1) |

The Q1 table's dispositions are in the catalogue's
[Not in v1](../observe/catalogue.md#not-in-v1) list.

---

## 4. Notes for each entry's session

The pitfalls the comparables met, per entry, as input for that entry's
session, none proposing semantics. Each entry's notes are in its input file,
`sdd/observe/inputs/OP-NN.md` (for example
[`OP-01.md`](../observe/inputs/OP-01.md)), which the hook admits to that
entry's session alone
([RFC-0027](../rfcs/rfc-0027-observe-playground.md)); this doc, admitted
whole, would hand every session all of them.

---

## 5. Entry × comparable

`—` means none found, (g) gated, (e) emulated or composite, n/c not checked.

| OP | fsspec | pyarrow.fs | OpenDAL (Rust / Py) | object_store | gocloud | smart_open | cloudpathlib | boto3 (S3) | Azure Blob | GCS |
|---|---|---|---|---|---|---|---|---|---|---|
| 01 read | `open`, `cat_file` | `open_input_stream` | `read`, `reader` | `get`, `get_opts` | `NewReader`, `ReadAll` | `open('rb')` | `read_bytes`, `open` (via cache) | `get_object` | `download_blob` | `download_as_bytes`, `Blob.open` |
| 02 read at offsets | `seek`, `cat_file(start,end)`, `cat_ranges` | `open_input_file`, `read_at` | `read_with(range)`, `Reader::fetch`; Py `read(offset,size)` | `get_range`, `get_ranges` | `NewRangeReader` | `seek` (per transport) | `seek` on cache copy | `Range=` | `offset`/`length` | `start`/`end` |
| 03 write | `open('wb')`, `pipe_file`, `put_file` | `open_output_stream` | `write`, `writer` | `put`, `put_multipart` | `NewWriter`, `WriteAll`, `Upload` | `open('wb')` | `write_bytes`, `open('w')` | `put_object`, `upload_fileobj` | `upload_blob` | `upload_from_*`, `Blob.open('wb')` |
| 04 atomic replace | — (`transaction`, semi-atomic) | — (exception commits partial) | n/c (staged writes: conditions at final commit) | `put` (atomic) | `Writer.Close` | — | — | PUT atomic | Put Blob / commit (inference) | write (inference) |
| 05 conditional write | `mode="create"`/`xb` (g) | — | `write_with(if_*)` (g) | `PutMode::Create/Update` (g) | `IfNotExist` (absent only) | — | `open('x')` (e) | `IfNoneMatch`/`IfMatch` | `overwrite=False`, `etag`+`match_condition` | `if_generation_match` |
| 06 list children | `ls` | `get_file_info(FileSelector)` | `list` | `list_with_delimiter` | `List(Delimiter="/")` | — (`iter_bucket`) | `iterdir` | `list_objects_v2(Delimiter)` | `walk_blobs` | `list_blobs(delimiter)` |
| 07 walk (+depth) | `find`/`walk(maxdepth)` | `FileSelector(recursive)`, no depth | `list_with(recursive)` (g); Py `scan` | `list`, no depth | `List` flat | — | `walk(lazy)`, `rglob` | flat prefix | `list_blobs`; HNS `get_paths` | flat prefix |
| 08 pattern | `glob` | — | — | — | — | — | `glob`, `rglob` | — | — | `match_glob` |
| 09 inspect | `info`, `exists`, `isdir`, `isfile`; `ukey`, `checksum` | `get_file_info` | `stat` | `head` | `Attributes` (`ETag`, `MD5`), `Exists` | — (`to_boto3`) | `exists`, `is_*`, `stat`, `info` | `head_object` | `get_blob_properties` | `reload`, `exists` |
| 10 delete | `rm_file`, `rm` | `delete_file` | `delete` (missing = no-op) | `delete`, `delete_stream` | `Delete` | — | `unlink` | `delete_object(s)` | `delete_blob` | `Blob.delete` |
| 11 delete tree | `rm(recursive)`; `rmdir` | `delete_dir`, `delete_dir_contents` | Rust `delete_with(recursive)` (g); Py `remove_all` | — (list + `delete_stream`) | — | — | `rmtree`; `rmdir` | — (list + `delete_objects`) | HNS `delete_directory` (g) | — (list + batch) |
| 12 move | `mv` (e) | `move` (g: S3 files e; Azure HNS) | `rename` (g; S3 unsupported) | `rename_opts` (e) | — | — | `rename`/`replace`/`move` (e) | `rename_object` (g: Express) | DataLake `rename_*` (g: HNS) | `move_blob` (atomic, same bucket); `rename_blob` (e) |
| 13 copy | `copy`, `cp_file` | `copy_file` (≤5 GB on S3) | `copy` (g) | `copy_opts` | `Copy` | — | `copy`, `copytree` | `copy_object` (≤5 GB), `copy` | `start_copy_from_url` | `copy_blob`, `rewrite` |
| 14 to/from local | `get`, `put` | `copy_files` | n/c | — | `Download`, `Upload` (io streams) | — (stream copy) | `download_to`, `upload_from` | `upload_file`, `download_file` | `upload_blob`, `download_blob` | `*_filename` |
| 15 between stores | generic copy, `rsync` | `copy_files(src_fs, dst_fs)` | n/c | — | — | `open` both ends | `copy` across clients | `copy(SourceClient=)` | `start_copy_from_url` | `copy_blob(destination_bucket)` |
| 16 scope | `DirFileSystem` | `SubTreeFileSystem` | `root` | `PrefixStore` | `PrefixedBucket`; `io/fs.SubFS` | — | — | — | `ContainerClient` (partial) | `Bucket` |
| 17 hand to libs | `ArrowFSWrapper`, `get_mapper`, file objects | `PyFileSystem(FSSpecHandler)`, `filesystem=` | `object_store_opendal` | (obstore fsspec) | `io/fs.FS` | file-like | `fspath` (cache copy) | file-like body | `StorageStreamDownloader` | `BlobReader`/`BlobWriter` |
| 18 capability query | — | — | `info().capability()` / Py `capability()` | — (`NotImplemented`/`NotSupported`; tags ignored) | — (`Unimplemented`) | — | — | — | — | — |
| 19 create folder (g) | `mkdir`/`makedirs` (no-op or bucket) | `create_dir` (marker) | `create_dir` (g, simulated on S3) | — | — | — | `mkdir` (silent no-op) | — (`key/` convention) | DataLake `create_directory` (g) | `storage_control` folders (g) |
| 20 user metadata (g) | — generic (s3fs `setxattr`) | `metadata=` (S3 drops user keys) | `write_with(user_metadata)` (g) | `Attributes` (local NotImplemented) | `WriterOptions.Metadata` | per transport | client `extra_args` | `Metadata=` | `metadata=`, `set_blob_metadata` | `metadata`, `patch` |
| 21 lifecycle | — (file `close` only; instance cache) | — (global `finalize_s3`) | — (Writer close/abort) | — (Drop) | `Bucket.Close` | file `close` | — (cache via GC) | `client.close()` | `close()`, context manager | `Client.close()` |
| 22 address mapping | `unstrip_protocol`, `url_to_fs` | `from_uri` | `from_uri`, `info().root()` | `parse_url`, `Path::from_url_path` | `OpenBucket(url)` | `parse_uri` | `as_uri`, `from_uri` | — | `BlobClient.url` | `Blob.from_uri` (n/c) |
| 23 native handle | `.s3`, `.service_client` | — | — | concrete store types | `As`, `ErrorAs`, `Before*` | `to_boto3`; inject | `S3Client.client` | (native) | (native) | (native) |
| 24 health check | — | — | `check()` (missing root = healthy) | — | `IsAccessible` (missing root = false) | — | — | `head_bucket` (existence probe) | `ContainerClient.exists` (existence probe) | `lookup_bucket`, `Bucket.exists` (existence probes) |

The column headers use the comparables' names; the row labels are the draft
entries' short names, matched to the catalogue by ID.

---

## 6. Limits

- Nothing was run against real AWS, Azure or GCS. The MinIO observations under
  OP-02 and OP-10 match RFC 9110 and the AWS documentation but do not verify
  AWS itself.
- OpenDAL's conditional-operations specification is a moving page ("Last
  updated on Aug 31, 2026"), not pinned to a release. The pre-1.0 crates
  (object_store, OpenDAL) and the S3 conditional-operation matrix change often.
- Some fsspec, OpenDAL and object_store source was read on main, possibly
  slightly ahead of the release in § Sources; smart_open's docs come from its
  development branch.
- Unverified: the content of fsspec 2023.9.0's glob change, and reports that
  botocore 1.36 broke S3-compatible servers.

## Sources

Read on 2026-10-26. Per-claim citations are in the full report linked in § 1.

| Library | Version | Where |
|---|---|---|
| fsspec, s3fs, gcsfs, adlfs, sshfs | fsspec 2026.9.0, s3fs 2026.9.0, gcsfs 2026.10.1, adlfs 2026.8.0, sshfs 2026.8.0 | https://filesystem-spec.readthedocs.io/en/latest/ ; fsspec and s3fs source at their tags, gcsfs, adlfs and sshfs on `main` |
| pyarrow.fs | Apache Arrow 26.0.0 | https://arrow.apache.org/docs/python/api/filesystems.html |
| Apache OpenDAL | opendal_core 0.59.5, Python binding 0.47.12 | https://opendal.apache.org/docs/rust/opendal_core/struct.Capability.html ; https://opendal.apache.org/docs/specifications/conditional-operations/ |
| object_store, obstore | object_store 0.14.2, obstore 0.12.0 | https://docs.rs/object_store/0.14.2 ; https://developmentseed.org/obstore/v0.12.0/ |
| gocloud.dev/blob | v0.47.0 | https://pkg.go.dev/gocloud.dev/blob@v0.47.0 |
| smart_open | 8.0.4 | https://github.com/piskvorky/smart_open |
| cloudpathlib | 0.26.0 | https://cloudpathlib.drivendata.org/stable/ |
| AWS S3, boto3 | boto3/botocore 1.43.118, s3transfer 0.19.3; S3 docs "latest" | https://docs.aws.amazon.com/AmazonS3/latest/userguide/ ; https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html |
| Azure Blob | azure-storage-blob 12.31.0, datalake 12.26.0 | https://learn.microsoft.com/en-us/rest/api/storageservices/ ; https://learn.microsoft.com/en-us/python/api/azure-storage-blob/ |
| Google Cloud Storage | google-cloud-storage 3.17.1 | https://cloud.google.com/storage/docs/ |
| Hadoop FileSystem | 3.5.0 and 3.3.5 | https://hadoop.apache.org/docs/current/hadoop-project-dist/hadoop-common/filesystem/ |
| Python, paramiko, SFTP | Python 3.15, paramiko 5.1.0, draft-ietf-secsh-filexfer-02 | https://docs.python.org/3.15/ ; https://docs.paramiko.org/en/latest/api/sftp.html |
