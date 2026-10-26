# Research: The v1 operation catalogue against comparable libraries (BK-493)

**Date:** 2026-10-26
**Backlog items:** BK-493 (The v1 Store API has no agreed set of operations, so each design session would find its own scope)
**Status:** Research complete. Background to [RFC-0026](../rfcs/rfc-0026-operation-catalogue.md); it decides nothing. Not ground: its per-entry pitfalls are notes for each entry's own session (RFC-0026 C4).

---

## Filing note

**Where it comes from.** The maintainer ran the brief in
[BK-493's dossier](../backlog/bk-493-operation-catalogue.md) in their research
repository, on the draft entries. The report below is
`reports/remote-store v1 operation catalogue verified.md` of `haalfi/research`,
branch `research/remote-store-v1-operation-catalogue-verified`, commit
[`b0e426f`](https://github.com/haalfi/research/blob/b0e426f875c6de42730cd5fa15b3daf6ca4185b6/reports/remote-store%20v1%20operation%20catalogue%20verified.md),
copied unchanged except that its headings sit one level lower, its nested
lists are indented four spaces, and its one relative link points at that
commit. Its notes, its brief and the first,
unverified report stay in that repository.

**What the catalogue took from it** (decision log
`sdd/decisions/c886d81c-7d81-58f9-bc3d-f11dc7304e4a.jsonl`):

| Finding | Catalogue |
|---|---|
| Conditions attach to read, delete, copy and rename too (Q2) | OP-05 stays a conditional write; conditions on other entries are not in v1 |
| List, walk and match is the least agreed cut; a depth limit has one precedent (Q2) | OP-06 to OP-08 stay three entries, OP-07 keeps its depth limit |
| System properties (7/10) and identity tokens (6/10) have no entry (Q1) | OP-20 holds user metadata and system properties; OP-09's info holds an identity token where the backend offers one |
| Presign, append, versioned access, conditional read and the rest of Q1 | Not in v1; an extension may add a feature, such as a simulated append |
| Batch delete, abort, multi-range read, delete guardrails (Q1) | Forms of OP-10, OP-03, OP-02 and OP-11, for their sessions |
| Shared decisions most often retrofitted (advisory note 7) | Not in spec 053; input to `read()`'s session and each later one (RFC-0026 Open Question 2) |

---

## Report

- **Date:** 2026-10-26. All sources read on this date.
- **Brief:** [`briefs/remote-store v1 operation catalogue verified.md`](https://github.com/haalfi/research/blob/b0e426f875c6de42730cd5fa15b3daf6ca4185b6/briefs/remote-store%20v1%20operation%20catalogue%20verified.md).
- **Base:** the first report, `reports/remote-store v1 operation catalogue.md` on branch `research/remote-store-v1-operation-catalogue`, and its notes 01–06 on that branch. Neither was edited, so the two reports can be diffed.
- **New evidence:** `research_notes/remote-store v1 operation catalogue verified/01-verification.md`.
- **Inputs to this run:**
    - a ChatGPT run on the identical brief, read critically;
    - a Perplexity answer on S3 ETag vs MD5;
    - the open caveats of the first report.
- **Rule for those inputs:** nothing from them was used unless the lead researcher checked it against a primary full text.
- **Status:** informs the catalogue and decides nothing. Recommendations are marked **advisory**.
- **Not an authority:** remote-store's own stable code and specs.

**Labels.**
- **[doc]**: stated in the cited docs, docstring, changelog, spec or issue.
- **[src]**: read in released source at the cited tag.
- **[obs]**: seen by running code on 2026-10-26, using pyarrow 26.0.0, smart_open 8.0.4 and cloudpathlib 0.26.0 against local disk and the **moto 5.2.4 S3 emulator**. Nothing was run against real AWS, Azure or GCS.
- **[inf]**: inference by the researcher.
- **unreachable**: the source could not be fetched.

Keys like `[OS]` refer to the source table. "Notes 0x" means the first run's notes. "V01" means this run's verification notes.

**Comparables (10, the denominator for every "n/10"):**
1. fsspec
2. pyarrow.fs
3. OpenDAL (Rust core and Python binding, counted as one)
4. object_store
5. gocloud blob
6. smart_open
7. cloudpathlib
8. boto3 (S3)
9. azure-storage-blob
10. google-cloud-storage

Hadoop FileSystem, paramiko/SFTP and obstore are cited where needed but not counted.

### What changed against the first report

| # | Change | Evidence |
|---|---|---|
| 1 | **OpenDAL Python ≠ Rust.** Python 0.47.12 still has `remove_all` and `scan`. `presign_*` exists only on `AsyncOperator`. `check()` is on both. Matrix cells OP-07, OP-11 and OP-24 updated; Q3 notes the Python presign gap | V01 A1 [src OD-PYI] |
| 2 | **OpenDAL conditional-operations specification** added as the strongest precedent for OP-05 and OP-18: no silent dropping of conditions; atomic with visible commit; no stat-then-mutate emulation; where the error surfaces is unspecified; status codes alone do not decide the error kind | V01 A2 [doc OD-SPEC] |
| 3 | **object_store has two policies for unsupported options:** `tags` are ignored, `attributes` must error | V01 A3 [src OS-SRC] |
| 4 | **fsspec append and identity:** the base file accepts `ab` (s3fs emulates it by download/re-upload or part copy); `checksum` and `ukey`. Append goes 5/10 → 6/10; new integrity/identity row | V01 A4 [src FS-SRC, S3FS] |
| 5 | **gocloud `Bucket` implements `io/fs.FS` and `io/fs.SubFS`** (OP-17; the first report had "—") | V01 A5 [doc GC] |
| 6 | **New Q1 rows:** conditional read (5/10), post-write metadata/property update (2/10 native), integrity/identity tokens (6/10), delete-contents / empty-only delete guardrails (3/10), cache invalidation (2/10) | V01 A6; notes 02–05 |
| 7 | **S3 ETag ≠ MD5** with the documented cases, including multipart `-N` construction, directory buckets, and checksum change on copy (OP-09, OP-14) | V01 C [doc AWS-OBJ, AWS-INTEG] |
| 8 | **Caveats resolved:** Azure default `retry_total` = 3 (`ExponentialRetry`); pyarrow S3 copy is single-request `CopyObject` (5 GB limit applies) | V01 D [src AZ-SRC, PA-SRC] |
| 9 | **The ChatGPT run's matrix positions that conflict with this report were rechecked; this report's positions stand** (GCS `move_blob`, pyarrow move gating, cloudpathlib `mkdir`, pyarrow S3 metadata drop, presign 8/10, `PrefixStore`, fsspec FS close, GCS retries). Its SDK version pins were stale (azure-storage-blob 12.30.2 and GCS 3.14.1 vs PyPI 12.31.0 and 3.17.1) | V01 B |

---

### Sources and versions

All rows of the first report's source table apply unchanged. Their keys are repeated here with the link and version; the full file lists per key are in the first report.

| Key | Source (link) | Version / date |
|---|---|---|
| FS-API / FS-FEAT / FS-COPY / FS-CL | https://filesystem-spec.readthedocs.io/en/latest/api.html , …/features.html , …/async.html , …/changelog.html ; raw `docs/source/copying.rst` (master) | fsspec 2026.9.0 (page build 2026.9.0.post2) |
| FS-SRC | https://raw.githubusercontent.com/fsspec/filesystem_spec/2026.9.0/fsspec/spec.py (also `asyn.py`, `exceptions.py`, `transaction.py`, `mapping.py`, `generic.py`, `implementations/dirfs.py`, `implementations/arrow.py`) | tag 2026.9.0 |
| FS-CL-2023 | https://raw.githubusercontent.com/fsspec/filesystem_spec/2023.9.0/docs/source/changelog.rst | tag 2023.9.0 |
| S3FS | https://raw.githubusercontent.com/fsspec/s3fs/2026.9.0/s3fs/core.py , `errors.py`, `docs/source/changelog.rst` | s3fs 2026.9.0 |
| GCSFS / ADLFS / SSHFS | raw.githubusercontent.com `fsspec/{gcsfs,adlfs,sshfs}` main | gcsfs 2026.10.1, adlfs 2026.8.0, sshfs 2026.8.0 |
| PA / PA-CPP | https://arrow.apache.org/docs/python/api/filesystems.html , `generated/pyarrow.fs.*.html`; https://arrow.apache.org/docs/cpp/api/filesystem.html | Apache Arrow v26.0.0 |
| PA-SRC | https://raw.githubusercontent.com/apache/arrow/apache-arrow-26.0.0/cpp/src/arrow/filesystem/s3fs.cc (+ `azurefs.*`, `gcsfs.cc`, `python/pyarrow/_fs.pyx`, `fs.py`) | tag apache-arrow-26.0.0 |
| OD-CAP | https://opendal.apache.org/docs/rust/opendal_core/struct.Capability.html | opendal_core 0.59.5 |
| OD-SRC | https://raw.githubusercontent.com/apache/opendal/v0.59.5/core/core/src/ (`types/operator/*`, `types/capability.rs`, `types/error.rs`, `raw/path.rs`, `layers/*`), `core/layers/*`, `services/{s3,fs,sftp}` | tag v0.59.5 |
| **OD-PYI** | https://raw.githubusercontent.com/apache/opendal/v0.59.5/bindings/python/python/opendal/operator.pyi | Python binding 0.47.12 (tag v0.59.5) |
| **OD-SPEC** | https://opendal.apache.org/docs/specifications/conditional-operations/ | "Last updated on Aug 31, 2026" |
| OD-PY / OD-CL | https://opendal.apache.org/docs/python/api/capability/ ; https://raw.githubusercontent.com/apache/opendal/main/CHANGELOG.md | 0.47.12; to v0.59.1 entry |
| OS / OS-SRC / OS-CL / OS-423 | https://docs.rs/object_store/0.14.2 ; https://raw.githubusercontent.com/apache/arrow-rs-object-store/v0.14.2/src/lib.rs (and `path/mod.rs`, `client/*`, `aws/*`, `local.rs`, `memory.rs`, `prefix.rs`, `attributes.rs`, `parse.rs`); `CHANGELOG.md`; https://github.com/apache/arrow-rs-object-store/issues/423 | object_store 0.14.2 |
| OBS | https://developmentseed.org/obstore/v0.12.0/ | obstore 0.12.0 |
| GC / GC-SRC | https://pkg.go.dev/gocloud.dev/blob@v0.47.0 ; https://gocloud.dev/howto/blob/ ; https://raw.githubusercontent.com/google/go-cloud/v0.47.0/blob/blob.go , `gcerrors/errors.go`, drivers | gocloud.dev v0.47.0 |
| SO | https://raw.githubusercontent.com/piskvorky/smart_open/develop/README.md , `HOWTO.md`, `help.txt`, `CHANGELOG.md`; 8.0.4 wheel | smart_open 8.0.4 |
| CP | https://cloudpathlib.drivendata.org/stable/ ; raw `HISTORY.md`, `cloudpath.py`, `s3/s3client.py` | cloudpathlib 0.26.0 |
| AWS-* | https://docs.aws.amazon.com/AmazonS3/latest/userguide/ (`conditional-writes`, `conditional-deletes`, `UsingMetadata`, `object-keys`, `Welcome`, `s3-express-differences`, `using-folders`, `copy-object`, `mpuoverview`) and …/API/ (`API_PutObject`, `API_GetObject`, `API_HeadObject`, `API_DeleteObject`, `API_DeleteObjects`, `API_CopyObject`, `API_RenameObject`, `API_ListObjectsV2`, `API_HeadBucket`) | "latest", 2026-10-26 |
| **AWS-OBJ** | https://docs.aws.amazon.com/AmazonS3/latest/API/API_Object.html | 2026-10-26 |
| **AWS-INTEG** | https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html , …/checking-object-integrity-upload.html (WebFetch) | 2026-10-26 |
| B3 | https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html , `guide/retries.html`, `guide/error-handling.html`; botocore config; botocore `CHANGELOG.rst` 1.36.0 | boto3/botocore 1.43.118, s3transfer 0.19.3 |
| AZ-* | https://learn.microsoft.com/en-us/rest/api/storageservices/ (conditional headers, naming, properties-and-metadata, copy-blob, list-blobs, blob-batch, get-blob, put-block, error codes, datalake path create/delete); https://learn.microsoft.com/en-us/python/api/azure-storage-blob/ ; …/azure/storage/blobs/ (retry policy, concurrency, HNS) | azure-storage-blob 12.31.0 (PyPI 2026-09-30), datalake 12.26.0 |
| **AZ-SRC** | https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-storage-blob_12.31.0/sdk/storage/azure-storage-blob/azure/storage/blob/_shared/policies.py , `_shared/base_client.py` | tag azure-storage-blob_12.31.0 |
| GCS-* | https://cloud.google.com/storage/docs/ (`request-preconditions`, `objects`, `consistency`, `retry-strategy`, `quotas`, `copying-renaming-moving-objects`, `rename-hns-folders`, `folders-overview`, `composing-objects`, `listing-objects`, `batch`); https://cloud.google.com/python/docs/reference/storage/latest/ ; api-core exceptions | google-cloud-storage 3.17.1 (PyPI 2026-10-15) |
| **GCS-CL** | https://raw.githubusercontent.com/googleapis/python-storage/main/CHANGELOG.md | main, 2026-10-26 |
| H-* | https://hadoop.apache.org/docs/current/hadoop-project-dist/hadoop-common/filesystem/ (introduction, filesystem, fsdatainputstream, fsdatainputstreambuilder, outputstream, pathcapabilities); hadoop-aws `directory_markers.html`, `index.html` | Hadoop 3.5.0 / 3.3.5 |
| PY / PARAMIKO / SFTP | docs.python.org 3.15 (`os`, `pathlib`); https://docs.paramiko.org/en/latest/api/sftp.html ; OpenSSH `PROTOCOL`; draft-ietf-secsh-filexfer-02 | Python 3.15, paramiko 5.1.0 |

---

### Summary

1. **Completeness (Q1).** The most widely offered operations with no catalogue entry, in order:
    - presigned/signed URLs (8/10)
    - system properties such as content type, apart from user metadata (7/10)
    - batch delete (6/10)
    - versioned access (6/10)
    - integrity/identity tokens (6/10)
    - append (6/10, always gated, sometimes emulated)
    - conditional read (5/10)
    - abort of an in-flight write (5/10)
    - multi-range read (3/10)

    Post-write metadata update is native in only 2/10 (Azure, GCS). S3 rewrites the object to change user metadata.
2. **The cut (Q2).**
    - Comparables merge write, atomic replace and conditional write. A condition is a mode or option of put, and also attaches to read, delete, copy, rename and metadata update.
    - OpenDAL now publishes a specification for that cross-cutting condition model.
    - List, walk and match is the least agreed cut. Nobody but fsspec has a depth limit; pyarrow merges inspect, list and walk.
3. **Gating (Q3).**
    - Only OpenDAL (and Hadoop) offers a capability query. OpenDAL's flags are the effective set, simulations included, and its spec forbids silently dropping a condition.
    - The others signal at call time with errors, or not at all. Even object_store mixes "ignore" (tags) and "error" (attributes).
    - Some gates depend on bucket or account type.
4. **Shared decisions (Q4).**
    - Path rules, error taxonomy, retry/timeout, concurrency and scope are fixed once per instance, with divergent choices.
    - The ETag is an opaque identity token, not a content hash (AWS documents when it is not MD5).
5. **Pitfalls (Q5)** are listed per entry. Recurring themes:
    - Bucket or account type decides move, folder and tree-delete semantics.
    - Conditional variants were folded into option structs in 2025–26.
    - `..` containment was retrofitted in 2026.
    - Behaviour on exception during a streamed write is split three ways.

---

### Q1. Completeness: operations no catalogue entry covers

Counts are lower bounds; an operation counts only where found in a full text. "(g)" = gated per backend or bucket type, "(e)" = emulated.

| Operation | Use case | Offered by (name) | Count |
|---|---|---|---|
| **Presigned / signed URL** | Time-limited delegated access without credentials | fsspec `sign` (base raises `NotImplementedError`) [src FS-SRC]; OpenDAL `presign_*` (g; Python only on `AsyncOperator` [src OD-PYI]) [doc OD-CAP]; object_store `Signer` (#738/#739) [doc OS-CL]; gocloud `SignedURL` (g, `Unimplemented`) [doc GC]; cloudpathlib `as_url(presign=True)` [doc CP; obs]; boto3 `generate_presigned_url` [doc B3]; Azure `generate_blob_sas` [doc AZ]; GCS `generate_signed_url` [doc GCS] | 8/10 |
| **System properties** (content-type, cache-control, encoding) apart from user metadata | HTTP serving, MIME | object_store `Attribute::{ContentType, CacheControl, …}` [doc OS-SRC]; OpenDAL `write_with_content_type` etc. (g) [doc OD-CAP]; pyarrow `metadata=` (S3 honours only 6 system keys) [src PA-SRC]; cloudpathlib `content_type_method` [doc CP]; boto3 `ContentType`/`CacheControl` [doc AWS-META]; Azure `ContentSettings` [doc AZ]; GCS `content_type`/`cache_control` [doc GCS] | 7/10 |
| **Batch / bulk delete** | Many keys in few requests; partial-failure reporting | object_store `delete_stream` [doc OS]; OpenDAL `Deleter`, `delete_max_size` [doc OD-CAP]; fsspec `rm(list)` (s3fs bulk) [doc S3FS]; boto3 `delete_objects` (≤1000); Azure `delete_blobs` (≤256); GCS `batch()` (≤100) [doc] | 6/10 |
| **Versioned access** | History, recovery, pinned reads | OpenDAL `*_with_version`, `list_with_versions` (g) [doc OD-CAP]; object_store `GetOptions.version` [doc OS]; smart_open `version_id` [doc SO]; boto3 `VersionId`; Azure `version_id=`; GCS `generation=` [doc] | 6/10 |
| **Integrity / identity tokens** (checksums, unique keys, verified MD5) | Verify transfers, detect change without reading content | fsspec `checksum`, `ukey` [src FS-SRC L766, L1453]; gocloud `WriterOptions.ContentMD5` (verified on Close), `Attributes.MD5` [src GC-SRC blob.go]; object_store CRC64NVME support (#633) [doc OS-CL]; boto3 `ChecksumAlgorithm` [doc B3]; Azure `validate_content`/`content_md5` [doc AZ]; GCS `checksum=`, `crc32c` [doc GCS] | 6/10 |
| **Append** | Logs, row appends | pyarrow `open_append_stream` (g: S3 raises) [doc PA; obs]; fsspec mode `ab` (base accepts; s3fs **emulates** by HEAD then download/re-upload below 5 MiB, else part copy) [src FS-SRC L1984, S3FS L127, L2597+]; smart_open `ab` (g: Azure append blobs) [doc SO]; OpenDAL `write_can_append` (g) [doc OD-CAP]; boto3 `WriteOffsetBytes` (g: directory buckets) [doc B3]; Azure append blob [doc AZ]. cloudpathlib mode `a` acts on the cache copy [inf] | 6/10 (+1 e) |
| **Conditional read** (If-Match / If-None-Match / If-(Un)Modified-Since / version) | Avoid transfer if unchanged; read a pinned state | OpenDAL `read_with_if_match` etc. (g) [doc OD-CAP]; object_store `GetOptions{if_match, if_none_match, if_modified_since, version}` [doc OS]; boto3 GetObject/HeadObject conditions [doc AWS-GetObject]; Azure Get Blob conditions [doc AZ cond.]; GCS generation/metageneration [doc GCS-PRE] | 5/10 |
| **Abort an in-flight write** | Drop a streamed or multipart upload | object_store `MultipartUpload::abort`; OpenDAL `Writer::abort`; gocloud cancel `ctx`; smart_open `terminate()`; boto3 `abort_multipart_upload` [doc/src] | 5/10 |
| **Server-side compose / block list** | Concatenation, parallel upload | OpenDAL `compose` (g); boto3 `upload_part_copy`; Azure `commit_block_list`; GCS `compose` [doc] | 4/10 |
| **Restore / undelete** | Archive retrieval, soft-delete recovery | OpenDAL `restore` (g); boto3 `restore_object`; Azure `undelete_blob`; GCS `restore_blob` [doc] | 4/10 |
| **Multi-range (vectored) read** | Columnar formats | object_store `get_ranges`; OpenDAL `Reader::fetch`; fsspec `cat_ranges` [doc] | 3/10 |
| **Delete-contents / delete-empty-only guardrails** | Clean a folder but keep it; refuse a non-empty delete | pyarrow `delete_dir_contents(accept_root_dir, missing_dir_ok)` [doc PA]; fsspec `rmdir` [doc FS-API]; cloudpathlib `rmdir` (empty only, `DirectoryNotEmptyError`) [src CP; obs] | 3/10 |
| **Post-write metadata / property update** | Fix content type or metadata after upload | Azure `set_blob_metadata` (replaces all), `set_http_headers`, `set_blob_tags` [doc AZ]; GCS `Blob.patch` (in place) [doc GCS]. S3 changes tags in place, but user metadata only by copy-replace [doc AWS-META]; s3fs `setxattr` = copy [src S3FS] | 2/10 native (3/10 incl. S3 tags) |
| **Local cache layer and its control** (caching, invalidation, materialisation) | Repeated reads, offline edit, freshness, reclaiming cache state | fsspec caching filesystems, `open_local`, `invalidate_cache`, `use_listings_cache` [doc FS-API, FS-FEAT]; cloudpathlib cache modes, `clear_cache`, `file_cache_mode` [doc CP] | 2/10 |
| Storage class / tier change | Cost | boto3, Azure, GCS [doc] | 3/10 |
| Retention / legal hold / object lock | WORM compliance | boto3, Azure, GCS [doc] | 3/10 |
| Bucket / container create and delete | Provisioning | pyarrow `allow_bucket_*`; s3fs `mkdir`; the three SDKs [doc/src] | 5/10 |
| Transparent compression | `.gz`/`.bz2` | pyarrow, smart_open [doc] | 2/10 |
| `touch` | Sentinels | cloudpathlib, fsspec [src] | 2/10 |
| Tags (separate from metadata) | Indexing, lifecycle filters | boto3, Azure [doc] | 2/10 |
| Query in place | Server-side CSV/JSON filter | boto3, Azure [doc] | 2/10 |
| Transaction (deferred multi-file commit; "semi-atomic") | Commit or discard writes together | fsspec [doc FS-FEAT] | 1/10 |
| Key-value mapping view / FUSE mount / rsync | Zarr stores, mounts, mirroring | fsspec `get_mapper`, `fuse.run`, `generic.rsync` (experimental) [doc FS-API] | 1/10 each |
| Leases, snapshots, abort async copy | Pessimistic lock, point-in-time copy | Azure only [doc AZ] | 1/10 |
| Annotations (≤1 MB) | Large attached payloads | S3 only [doc AWS-META] | 1/10 |

**Absent almost everywhere:**
- OP-07's depth limit: fsspec only (`find/walk(maxdepth)`). Arrow C++ `max_recursion` is not exposed in Python [doc; obs].
- OP-18: OpenDAL only.
- OP-24: OpenDAL `check()` and gocloud `IsAccessible` only [src].

**Advisory.**
- Strongest candidates for an entry, a gated entry, or an explicit "out of scope" note: presign (8/10), system properties (7/10), batch delete, versioned access and integrity tokens (6/10 each), conditional read and abort (5/10 each).
- Batch delete and abort can also be read as parts of OP-10/11 and OP-03.
- Conditional read overlaps the OP-05 cut question (Q2).
- Integrity tokens overlap OP-09.

---

### Q2. The cut: where comparables split or merge differently

#### Write vs atomic replace vs conditional write (OP-03 / OP-04 / OP-05)

**object_store** merges all three. Every `put` is atomic ("No clients should be able to observe a partially written object"), and `PutMode::{Overwrite (default), Create, Update}` selects the precondition [doc OS]. The streamed `put_multipart_opts` is separate, and the atomic wording is not stated for it [doc OS; inf].

**gocloud** supports if-absent only, via `WriterOptions.IfNotExist` [doc GC]. The docs name a non-existent `gcerrors.PreconditionFailed`; drivers return `FailedPrecondition` [src GC-SRC L1516].

**OpenDAL** expresses conditions as options with separate capability flags [doc OD-CAP]. **Its conditional-operations spec makes them a cross-cutting contract** [doc OD-SPEC]:
- **Scope:** the same conditions (`if_match`, `if_none_match`, `if_version_match`, `if_not_exists`, `if_(un)modified_since`, `if_not_changed`) apply to read, stat, write, copy, rename, delete and restore.
- **No silent dropping:** "OpenDAL never silently ignores a condition". An unsupported combination returns `Unsupported`.
- **Atomic with commit:** a mutation condition is advertised only if it "can evaluate the condition atomically with the mutation's visible commit". Stat-then-mutate emulation is forbidden.
- **Staged and multipart writes:** the condition is evaluated "at the final commit"; on failure the previous file stays.
- **Where the error appears:** unspecified (handle construction, I/O, or close).
- **Error kind:** status codes alone do not decide it. A 412 or 304 maps to `ConditionNotMatch` only in response to an explicit condition.
- **Missing key:** deleting it "remains a successful no-op", even under a condition. A conditional batch delete evaluates each entry independently.
- **Origin:** RFCs 5485 Conditional Reader, 7818 Rename If Not Exists, 8145 Conflict Error Kind, 8147 Write If Not Changed.

**The vendor stores:**
- **GCS:** `ifGenerationMatch=0` means absent; `=<gen>` means unchanged [doc GCS-PRE].
- **S3:** `If-None-Match: *` / `If-Match` on PutObject, CopyObject and CompleteMultipartUpload [doc AWS-CW].

**fsspec** `mode="create"`/`xb` is "implementation-dependent", "trial basis" [doc FS-FEAT]. The base does `exists()` then write [src FS-SRC]. Note that this is exactly the emulation the OpenDAL spec forbids [inf].

**No conditional write:** pyarrow, smart_open, cloudpathlib (`open('x')` is check-then-act) [doc/src; obs].

**Atomic replace is a separate operation only on filesystems:** `os.rename` vs `os.replace` [doc PY]; paramiko `rename` vs `posix_rename` [doc PARAMIKO]. On object stores, PUT already is atomic [doc AWS-CONS, OS, GC].

**Abort** is its own verb in object_store, OpenDAL, gocloud and smart_open. On exception, pyarrow S3 commits the partial object and cloudpathlib uploads it [obs; src].

**Trend:** object_store 0.13.0 `rename_opts`/`copy_opts` (#555, #548); OpenDAL 0.58.0 `rename_with_if_not_exists` [doc OS-CL, OD-CL].

**Conditions beyond write, in the vendor stores:**
- S3: conditional GET/HEAD, copy, rename, delete [doc AWS-CD, AWS-DEL, AWS-REN].
- Azure: get, delete, copy, metadata set [doc AZ].
- GCS: read, delete, compose, move [doc GCS-PRE].

**Cost to a caller.**
- Separate entries make each guarantee visible but multiply entry points.
- A mode on one call hides that the streamed or multipart path differs. On S3, a 409 on CompleteMultipartUpload restarts the whole upload [doc AWS-CW].
- If OP-05 stays write-only, conditional read, delete, copy and rename have no home [inf].
- OpenDAL's spec shows one coherent way to define conditions once and attach them to many entries [doc OD-SPEC].

#### List vs walk vs pattern (OP-06 / OP-07 / OP-08)

| Comparable | Shape |
|---|---|
| gocloud | One `List(ListOptions{Prefix, Delimiter})`. An empty delimiter gives a flat recursive listing. No glob, no depth [doc GC] |
| object_store | `list` (recursive) vs `list_with_delimiter`; `list_with_offset`. No glob, no depth [doc OS] |
| OpenDAL | Rust `list` + `list_with(...).recursive(true)` (gated, simulated by default); **Python also `scan`** (recursive) [src OD-PYI]. No glob found |
| pyarrow | One call for inspect, list and walk: `get_file_info(path \| [paths] \| FileSelector(...))`. No glob; no depth in Python [doc PA; obs] |
| fsspec | Separate `ls`, `find(maxdepth, withdirs)`, `walk(maxdepth, topdown)`, `glob(maxdepth)`, `expand_path`; copy/get/put accept globs and `recursive=`/`maxdepth=` [doc FS-API, FS-COPY] |
| cloudpathlib | `iterdir`, `walk(lazy=)`, `glob`, `rglob` [doc CP] |
| Vendor SDKs | Prefix + delimiter; only GCS has a server-side glob (`match_glob`) [doc GCS] |

**Cost to a caller.**
- One call with options: depth and pattern are emulated client-side at O(subtree) cost [doc H-INTRO; inf].
- Separate calls allow pruning: cloudpathlib added `walk(lazy=True)` for this [doc CP-HIST].
- Glob semantics drift with the reference implementation [doc FS-CL, PY].

#### Inspect (OP-09)

The comparables lean towards one rich inspect call with derived probes:
- Hadoop deprecated single-attribute probes in favour of one `getFileStatus` [doc H-FS].
- gocloud `Exists` is a shortcut [doc GC].
- pyarrow returns `FileType.NotFound` without raising [doc PA].

The identity fields such a call returns (ETag, version) are opaque tokens, not content hashes (see Q4, OP-09).

#### Delete (OP-10 / OP-11)

| Comparable | Shape |
|---|---|
| OpenDAL Rust | `delete_with(recursive(true))`; `remove_all` deprecated in 0.55.0 [doc OD-SRC] |
| OpenDAL Python 0.47.12 | **still exposes `remove_all`** [src OD-PYI] |
| fsspec | `rm(recursive, maxdepth)` + `rmdir` |
| pyarrow | `delete_file`, `delete_dir`, `delete_dir_contents` |
| cloudpathlib | `unlink`, `rmdir`, `rmtree` |
| object_store, gocloud | No tree delete [doc] |

#### Copy and transfer (OP-13 / OP-14 / OP-15)

- **fsspec** splits by locality: `copy`/`get`/`put` [doc FS-COPY].
- **pyarrow** has `copy_file` within a filesystem and `copy_files` between any two (merging OP-14 and OP-15) [doc PA].
- **cloudpathlib** `copy` covers all of them, via the cache across clients [src CP].
- **object_store** copies within one store only [doc OS].
- **gocloud** `Upload`/`Download` take `io.Reader`/`io.Writer` streams, not local paths [doc GC].

#### Read (OP-01 / OP-02)

- pyarrow splits sequential and random reads [doc PA]; Hadoop uses one `openFile()` with a read policy [doc H-OPEN].
- object_store folds ranges into `get_opts`; `get_ranges` (coalesced) takes no options [doc OS].
- OpenDAL Python `read(offset, size)` [src OD-PYI].

**Advisory.** The draft's cut matches fsspec and cloudpathlib. Two open cut questions:
- conditions as a cross-cutting modifier (OpenDAL spec precedent) versus OP-05;
- OP-06/07/08 as one listing with options versus three entries.

---

### Q3. Optional entries: what is gated and how a caller learns

| Strategy | Who | Mechanism |
|---|---|---|
| **Declared and pre-checked** | OpenDAL | `capability()` (~90–100 fields) [doc OD-CAP]. `CorrectnessCheckLayer` raises `Unsupported` before dispatch [src OD-SRC]. For conditions, the spec adds: never silently ignored, combinations must hold as a conjunction or `Unsupported`, and a flag may be advertised only after the service passes the portable behaviour tests [doc OD-SPEC] |
| **Configured per store + call-time error** | object_store | `S3ConditionalPut`, `S3CopyIfNotExists` config. Errors are `NotImplemented` or `NotSupported`, with no rule for which [src OS-SRC]. **Unsupported options get two policies: `tags` are ignored, `attributes` must error** [src OS-SRC L1946–1952] |
| **Call-time error only** | gocloud, pyarrow, cloudpathlib, smart_open | `gcerrors.Unimplemented`; `ArrowNotImplementedError` or a generic `OSError`; `CloudPathNotImplementedError`; `NotImplementedError` [doc/obs] |
| **Silent emulation or no-op** | fsspec, cloudpathlib, pyarrow, smart_open | fsspec `mkdir` = `pass`, `mv` = copy + rm, `mode="create"` = exists then write, and s3fs `ab` = download/re-upload [src]; cloudpathlib `mkdir` no-op [obs]; pyarrow drops metadata keys [doc; obs]; smart_open ignores unknown `transport_params` [doc; obs] |
| (Path-scoped probe) | Hadoop | `hasPathCapability(path, cap)`. It "MUST NOT return True … unless it is known to be supported". False may mean unknown; must be cheap and side-effect free [doc H-PCAP] |

**What OpenDAL gates** [doc OD-CAP]:
- create_dir, rename, copy, `list_with_recursive`
- `write_with_user_metadata`, append, presign
- conditional and versioned variants of read, write, stat, delete and copy
- multipart limits `write_multi_{min,max}_size`, `delete_max_size`
- `shared`

The catalogue's gated OP-19 and OP-20 match OpenDAL's `create_dir` and `write_with_user_metadata`. OpenDAL also gates OP-07, OP-12 and OP-13, and its S3 service reports `rename` and `create_dir` as Unsupported natively [doc OD-CAP; src OD-SRC].

**Python binding gaps** relative to the effective capability: presign exists only on `AsyncOperator`, so a sync Python caller cannot reach it whatever `capability().presign_read` says [src OD-PYI; inf].

**Bucket- or account-type gates**, found at runtime:
- pyarrow Azure move (HNS) [doc PA-CPP]
- gcsfs `_is_bucket_hns_enabled` [src]
- OpenDAL S3 `!is_s3_express` [src]
- S3 `RenameObject` (Express One Zone) [doc AWS-REN]
- Azure rename and recursive delete (HNS) [doc AZ]

**Pitfalls of a capability query:**
- OpenDAL removed `native_capability`/`full_capability` in 0.58.0 [doc OD-CL]. Simulations set the flags [src].
- Flags were missed and fixed piecemeal (#7204, #7349, #7320) [doc OD-CL].
- obstore re-types the two "unsupported" variants into unrelated Python types [src OBS].

**Advisory.**
- A query alone does not settle the gate anywhere. OpenDAL pairs it with a pre-dispatch check and a no-silent-drop rule; Hadoop defines False as "unknown".
- Silent drops (pyarrow metadata, object_store tags, smart_open params) and silent no-ops (fsspec, cloudpathlib `mkdir`) leave a caller unable to tell "unsupported" from "done".

---

### Q4. Shared decisions (decided once, not per operation)

| Decision | object_store 0.14.2 | OpenDAL 0.59.5 / Py 0.47.12 | gocloud v0.47.0 | fsspec 2026.9.0 | pyarrow / smart_open / cloudpathlib | Vendor SDKs |
|---|---|---|---|---|---|---|
| **Key validation** | `Path`: no leading or trailing `/`, no empty segments, no `.`/`..`, no control chars; `parse` rejects, `from` percent-encodes (`foo/../bar` → `foo/%2E%2E/bar`); no length check [doc OS-SRC] | normalised on every call; trailing `/` = dir; `..` passed through [src] | non-UTF-8 → `InvalidArgument`; per-driver `__0x<hex>__` escaping [doc/src] | `_strip_protocol`, `root_marker` [src] | pyarrow rejects a scheme; others need a URI; none normalise `..` or `//` [obs] | S3 ≤1024 B; Azure ≤1024 chars, ≤254 segments; GCS ≤1024 B, no CR/LF, not `.`/`..` [doc] |
| **Error taxonomy** | `Error` enum (NotFound, AlreadyExists, Precondition, NotModified, NotSupported, NotImplemented, PermissionDenied, Unauthenticated, InvalidPath, Generic, …) [doc] | `ErrorKind` (Unsupported, NotFound, AlreadyExists, ConditionNotMatch, RangeNotSatisfied, IsADirectory, RateLimited, …) + Permanent/Temporary/Persistent [doc]; conditional errors defined by spec: `ConditionNotMatch` only for explicit conditions, `Conflict` for unrelated service conflicts [doc OD-SPEC]; Python classes not builtins [src] | `gcerrors.ErrorCode` + `ErrorAs` [doc] | builtins; implementations translate [src] | builtins + `ArrowInvalid`; smart_open S3 → `OSError`; cloudpathlib own hierarchy [obs] | botocore `ClientError`; Azure `Resource*Error`; api-core `PreconditionFailed`… [doc] |
| **Retries** | built in, `RetryConfig` 10 retries / 3 min; timeouts retried only if idempotent or safe; S3 Overwrite put/copy marked idempotent [doc+src] | opt-in `RetryLayer`, retries only Temporary errors, then marks them Persistent [doc] | not portable [inf] | per implementation (s3fs 5 retries, allow-list + string match) [src] | pyarrow S3 3 attempts; others via boto3 [doc] | botocore legacy/standard/adaptive; **Azure default `ExponentialRetry` `retry_total=3`** (the README's 10 is the `StorageRetryPolicy` base default) [src AZ-SRC]; GCS idempotency-aware policies but uploads and deletes retry by default [doc GCS-RETRY] |
| **Timeouts** | `ClientOptions` 30 s / 5 s [doc] | opt-in `TimeoutLayer` 60 s / 10 s [doc] | per call `ctx` [doc] | `FSTimeoutError`; per implementation [src] | pyarrow `request_timeout` ignored on Linux [doc] | botocore 60/60 s; Azure 20/60 s; GCS 60 s [doc] |
| **Consistency stated** | atomic put; list order not guaranteed; keep ETag and version [doc] | none general; conditional metadata contract: advertised ETag/version must be populated and reusable as a condition [doc OD-SPEC] | List may miss recent writes; not readable until Close [doc] | none; `DirCache` may be stale [doc] | — | S3, Azure, GCS strong read-after-write incl. list [doc] |
| **Identity token (ETag)** | `e_tag` and `version`; "Stores will use differing combinations…" [doc OS] | `if_not_changed` lowers to a version match, else an ETag match [doc OD-SPEC] | `Attributes.ETag`, `MD5` [src] | `ukey`, `checksum` [src] | — | **S3: ETag is an MD5 only for single-part plaintext/SSE-S3. SSE-C/SSE-KMS → not MD5. Multipart/UploadPartCopy → MD5 of the part MD5s + `-N`. Directory buckets: no MD5. ETag ignores metadata changes** [doc AWS-OBJ, AWS-INTEG] |
| **Closing** | none (Drop) [inf] | no `Operator.close`; Writer close/abort or "data could be lost" [doc] | `Bucket.Close`, later calls → `FailedPrecondition`; "always check the error of Close" [doc; src] | instances cached by args and pinned against GC until `clear_instance_cache`; s3fs `weakref.finalize` [doc; src] | pyarrow global `finalize_s3`; cloudpathlib GC [doc] | `close()`; Azure context managers [doc] |
| **Async parity** | async-only; obstore `_async` twins [doc] | async + blocking; Python `AsyncOperator`/`Operator`, **not at parity (presign async-only)** [src OD-PYI] | sync + `ctx` [doc] | `AsyncFileSystem` + sync wrappers [doc] | none | Azure `aio`; boto3 none; GCS none [doc] |
| **Concurrency / instrumentation** | `LimitStore`, `ThrottledStore` | `ConcurrentLimitLayer`, ~20 layers | OpenTelemetry | `batch_size`, callbacks | — | — |
| **Prefix scope (OP-16)** | `PrefixStore` | `root` | `PrefixedBucket`, `SingleKeyBucket` | `DirFileSystem` | `SubTreeFileSystem` | — |

**Observations [inf unless cited].**
- `..` handling differs in all four abstractions: object_store rejects or encodes it; gocloud escapes the `/` of `../`; OpenDAL passes it through generically; fsspec DirFileSystem guards it only on local disk.
- Retry safety is tied to idempotency (object_store), error status (OpenDAL), an allow-list (s3fs), or not decided (gocloud).
- GCS retries deletes by default [doc GCS-RETRY], so a retried delete that already succeeded can surface as NotFound [inf].
- Python bindings diverge from their Rust cores in exception typing and in API surface: obstore, and OpenDAL Python `remove_all`, `scan`, async-only presign [src].

---

### Q5. Pitfalls per entry (notes for each entry's later session; no semantics proposed)

Full citations are in the first run's notes 02–06 and in V01. Lines marked **(new)** come from this run.

#### OP-01 Read
- The view during a streamed read is undefined unless pinned [doc H-FSDIS]. s3fs added ETag expiry checks (#1008) [doc S3FS-CL].
- gcsfs read-ahead defaults changed memory (170→600 MB), then were reverted for `cat_file` [doc GCSFS-CL].
- object_store returns NotFound on a directory path (0.6.0, #4231) [doc OS-CL].
- pyarrow S3 streams are unbuffered; `allow_delayed_open` defers open errors to close [doc PA].
- cloudpathlib downloads the whole object; a locally edited cache blocks reads [doc CP; obs].
- **(new)** OpenDAL: under a condition, a missing file still returns `NotFound` for stat and read [doc OD-SPEC].

#### OP-02 Read at offsets
- Ranges past EOF were fixed separately in object_store, fsspec, adlfs, smart_open and s3fs [doc *-CL].
- Azure has no suffix range; S3 serves one range per GET [doc].
- Multi-range reads are split out with coalescing; pinned ranges need `get_opts` [doc OS].
- Hadoop `readVectored`: mixed old and new data if the file changes [doc H-FSDIS].
- fsspec block-cache bugs [doc FS-CL].
- cloudpathlib makes no remote range request [doc CP].
- **(new)** OpenDAL Python `read(offset, size)` [src OD-PYI].

#### OP-03 Write
- Visible only on close, and close can fail [doc H-OUT, GC, PARAMIKO].
- Abort is explicit; S3 and GCS can't clean up on drop; smart_open 7.0.0 fixed orphaned multipart parts [doc OS, SO-MIG].
- On exception, pyarrow commits, cloudpathlib uploads and smart_open aborts [obs; src].
- Part-size floor: 5 MiB–5 GiB, ≤10,000 parts, R2 equal sizes [doc AWS, OS].
- Empty files take a separate path [doc S3FS-CL, OD-CAP].
- object_store `with_fsync` [doc OS-CL].
- fsspec reverted `auto_mkdir` [doc FS-CL].
- Azure defaults to `overwrite=False`; append blobs append [doc AZ].
- botocore 1.36.0 changed the default checksums [doc B3-CL].
- **(new)** S3 attaches a full-object CRC64NVME checksum when none is supplied. "AWS SDKs do not automatically calculate MD5 checksums" [doc AWS-INTEG].

#### OP-04 Replace atomically
- Object-store PUT is atomic. object_store's local temp files `…#<n>` leak into the key space [doc AWS-CONS, OS].
- Windows `os.rename` vs `os.replace`; SFTP `rename` vs `posix_rename` [doc PY, PARAMIKO, SSH-PROTO].
- Durable replace needs a directory fsync (#758) [doc OS-CL].
- object_store local copy was not atomic until #4759 [doc OS-CL].
- fsspec transactions are "semi-atomic" [doc FS-FEAT].
- S3: "latest timestamp wins" [doc AWS-CONS].

#### OP-05 Conditional write
- object_store's history: DynamoDB lock → native (0.11.2) → on by default (0.12.0) [doc OS-CL].
- Conflicts surface as 412, 409 or 404 (concurrent delete) [doc AWS-CW].
- A delete marker counts as absent; GCS `ifGenerationMatch=0` ignores noncurrent versions [doc AWS-CW, GCS-PRE].
- If-Match needs `s3:GetObject`; no GCS preconditions with XML multipart [doc].
- The local filesystem can't do "if unchanged" (object_store #423); "if absent" maps to `O_EXCL` [doc OS-423, PARAMIKO].
- When the check runs is undefined in fsspec; Hadoop calls S3A no-overwrite create an unsafe lock [doc FS-FEAT, H-FS].
- object_store separates `AlreadyExists` from `Precondition`; the gocloud docs name a non-existent code [doc OS; src GC-SRC].
- obstore's fsspec adapter ignores `mode=` [src OBS].
- **(new)** OpenDAL spec:
    - forbids stat-then-mutate emulation
    - evaluates staged writes at the final commit, leaving the old file intact on failure
    - leaves the point where the error surfaces unspecified
    - says a wildcard ETag "has no portable meaning" unless the operation defines one
    - lists `if_version_not_match` on a missing file as having "no portable behavior" [doc OD-SPEC]

#### OP-06 List children
- Directory markers: Hadoop S3A policy changes (3.3.1/3.4.0/3.5.0) [doc H-MARK]; cloudpathlib #148 [doc].
- A missing folder: an error in Hadoop, optional in pyarrow, tolerated in OpenDAL [doc].
- object_store prefixes match per path segment [doc OS].
- Ordering: not guaranteed in Hadoop or object_store; not lexicographic in S3 directory buckets; Azure upper case first and `/` lowest on HNS; gocloud lexicographic [doc].
- Short or empty pages; s3fs per-page retries [doc].
- Stale listing caches [doc S3FS-CL, FS-FEAT].

#### OP-07 Walk subtree
- Flat vs per-level listing is a real split; pruning needs per-level listing [doc OS-CL, H-FS, CP-HIST].
- Depth limits: fsspec only [doc; obs].
- `withdirs` / base exclusion differ [doc].
- Cost is O(entries) [doc H-INTRO, FS-CL, GCSFS-CL].
- HNS differences [doc].
- gocloud listing may miss recent writes [doc GC].
- **(new)** OpenDAL Python `scan` vs Rust `list_with(recursive)` [src OD-PYI].

#### OP-08 Match by pattern
- fsspec 2023.9.0 glob change: **still unverified**. Its changelog section lists no glob item; adlfs's compatibility note is the only evidence [doc FS-CL-2023, ADLFS-CL].
- Later fsspec fixes (#1825, #2084, #2038, #2112) [doc].
- fsspec rules: `**` must be a whole component, `maxdepth` applies to the first `**`, trailing `/` = folders, no braces [doc FS-API].
- pathlib 3.13 changes; cloudpathlib #154 [doc].
- Metacharacters in keys [doc PY; inf].
- Bucket-level globbing refused [doc]; cloudpathlib rejects `..` [obs].
- Only GCS matches server-side [doc].

#### OP-09 Inspect
- "Is it a directory" is ambiguous (object_store #4231, gocloud `IsDir`) [doc].
- Directory probes are costly and were repeatedly retuned (s3fs, adlfs) [doc].
- S3 HEAD on a missing key returns 403 without `s3:ListBucket` [doc AWS-HEAD].
- mtime: multipart initiation time; ~1 s granularity; SFTP minimal stat [doc].
- ETag format bugs (unquoted, missing, empty) [doc].
- cloudpathlib `NoStatError`; pyarrow never raises [obs; doc].
- **(new) ETag is not a content hash** [doc AWS-OBJ, AWS-INTEG]:
    - S3 ETag = MD5 only for single-part plaintext or SSE-S3 uploads.
    - Not MD5 for SSE-C/SSE-KMS, multipart or UploadPartCopy.
    - Multipart ETag = MD5 of the concatenated part MD5s + `-<parts>`.
    - The Console uses multipart above 16 MB.
    - Directory buckets do not support MD5.
    - "The ETag only reflects changes to the content of an object, not changes to its metadata."
- **(new)** fsspec offers `ukey` and `checksum` as identity probes [src FS-SRC].

#### OP-10 Delete item
- Missing key:
    - succeeds in S3 (DeleteObjects), OpenDAL, and object_store S3 and memory;
    - errors in object_store local/GCP/Azure, gocloud, fsspec (MemoryFS aligned in #2140), Azure (`BlobNotFound`) and GCS;
    - Hadoop returns False;
    - cloudpathlib defaults to `missing_ok=True` [doc].
- **(new)** In OpenDAL this holds even under a condition: "Deleting a file that does not exist remains a successful no-op" [doc OD-SPEC].
- Bulk limits 1000/256/100; object_store #731/#734 [doc].
- Partial batch failures [doc].
- Versioned buckets insert delete markers [doc AWS-DEL, AWS-CD].
- Azure `delete_snapshots` [doc].
- **(new)** OpenDAL: a conditional batch delete evaluates each entry independently [doc OD-SPEC].

#### OP-11 Delete folder tree
- Not atomic and O(n) [doc H-INTRO, H-FS]. Azure HNS gives atomic directory operations [doc AZ-HNS].
- Root and bucket special cases [doc].
- **pyarrow S3 `delete_dir("bucket")` without `allow_bucket_deletion` empties the bucket, then raises** [src; obs].
- Markers must be deleted too; S3 directory buckets auto-delete empty parents [doc].
- OpenDAL Rust merged tree delete into `delete_with(recursive)`. **(new)** Python 0.47.12 still offers `remove_all` [src OD-PYI].
- fsspec async `maxdepth` bug [doc].
- Azure HNS paginated delete; flat-namespace partial deletes; cloudpathlib >256 blobs (#509) [doc].

#### OP-12 Move / rename
- Copy + delete: not atomic, O(data) [doc H-FS, H-S3A, OS].
- Atomic only on certain bucket or account types:
    - Azure HNS (pyarrow move is HNS-only)
    - GCS `move_blob`/`moveTo` in the same bucket; gcsfs changed `mv` three times
    - S3 `RenameObject` (Express One Zone)
    - OpenDAL S3 `Unsupported` [doc/src]
- **(new)** GCS `move_blob` exists well before 3.14 (python-storage changelog, "Add Bucket.move_blob() for HNS-enabled buckets (#1431)") [doc GCS-CL].
- SFTP v3 RENAME fails if the target exists; Hadoop is inconsistent [doc].
- sshfs fallback deletes the source in `finally:` [src; inf].
- cloudpathlib unlinks the target first [src].
- Directory moves are refused by several [doc/src]; fsspec `maxdepth` bug [doc].
- Same-path moves differ [doc/src].
- GCS early-deletion charges on copy-based moves [doc].
- **(new)** OpenDAL rename accepts conditions under the spec (RFC 7818). Rename "may still fail because [its] source … does not exist" even when the condition succeeds [doc OD-SPEC].

#### OP-13 Copy within a store
- S3 CopyObject ≤5 GB atomic; s3fs `_copy_basic`/`_copy_managed` [doc; src].
- **(new, resolved)** pyarrow S3 copy is a single `CopyObjectRequest` with no `UploadPartCopy`, so the 5 GB limit applies to pyarrow `copy_file` and `move` on S3 [src PA-SRC L2394–2416, L3468; inf for the failure mode].
- S3 errors inside a 200; Azure `pending` copies; adlfs does not poll [doc; src].
- object_store copy-if-not-exists config; the multipart mode drops tags and attributes [doc].
- Local hard link; sshfs shell `cp` [doc; src].
- Metadata directive and SSE-C forwarding [doc].
- fsspec trailing-slash spec (#1225) [doc].
- **(new)** Copying a multipart S3 object with CopyObject changes its checksum (and so its ETag form) "even though the data doesn't" [doc AWS-INTEG].

#### OP-14 Transfer to or from local disk
- Temp-file strategies differ: s3transfer temp + rename; fsspec writes `lpath` directly; gocloud fileblob cross-device rename (`NoTempDir`) [src; doc].
- Callbacks and concurrency knobs [doc].
- botocore 1.36.0 CRC32 default; breakage of S3-compatible servers unverified; GCS `DataCorruption` [doc].
- cloudpathlib GHSA-r4f8-3xc4-c8vw `..` escape [doc].
- fsspec `put_file(mode="create")` is check-then-write [src].
- **(new)** Verifying a download by comparing ETag with a local MD5 fails for multipart, SSE-C/SSE-KMS and directory-bucket objects. Full-object checksums for multipart uploads exist only for CRC64NVME/CRC32/CRC32C [doc AWS-OBJ, AWS-INTEG]. gocloud verifies `ContentMD5` on `Writer.Close` [src GC-SRC].

#### OP-15 Transfer between stores
- Data goes through the client and often local disk (fsspec temp dir, cloudpathlib cache) [src; doc].
- fsspec `copy_file_op` defaults to ignoring errors; mixed backends rejected late (#2302) [src; doc].
- Same provider across buckets is a third case (obstore "Bucket mismatch", object_store same-store only, S3 cross-Region restrictions, Azure copy from URL) [src; doc].
- pyarrow `copy_files` destination semantics vs fsspec trailing slash [doc; inf].
- **(new)** ETags are not comparable across stores or upload methods [doc AWS-INTEG; inf].

#### OP-16 Scope to a folder
- `..` escapes fixed in 2026: fsspec DirFS 2026.7.0 (local only), OpenDAL fs 0.58.0 (#7684), cloudpathlib 0.25.0 (GHSA) [src; doc].
- pyarrow `SubTreeFileSystem` "makes no security guarantee"; object_store local follows symlinks out of the root [doc; obs].
- Prefix-stripping bugs (#664/#686, DirFS fixes) [doc].
- Every method must be forwarded [doc].
- gocloud `PrefixedBucket` closes the parent [doc].
- **(new)** gocloud `Bucket` also implements `io/fs.SubFS`, a second scoping route [doc GC].

#### OP-17 Hand items to other libraries
- Bridges drop data: pyarrow `FSSpecHandler` TODO, object_store_opendal unknown attributes, obstore `mode` [src].
- Path conventions break (#2072, `root_marker`) [doc/src].
- Adapters break when the wrapped library changes [doc].
- obstore's fsspec adapter is "best effort" [doc].
- cloudpathlib `fspath` is a read-only cache copy [doc].
- **(new)** gocloud `*blob.Bucket` "implements io/fs.FS and io/fs.SubFS, so it can be used with functions in those packages" [doc GC].

#### OP-18 Capability query
- Coverage: OpenDAL `capability()`, Hadoop `hasPathCapability`; nobody else [doc].
- OpenDAL removed native/full in 0.58.0; simulations set flags [doc; src].
- Capabilities depend on path or bucket [src].
- Hadoop semantics [doc H-PCAP].
- Missed flags [doc OD-CL].
- **(new)** OpenDAL spec:
    - "Separate capability fields do not imply support for combinations of those conditions."
    - Unsupported combinations return `Unsupported`.
    - A flag may be advertised only after the service passes the portable behaviour tests [doc OD-SPEC].
- **(new)** object_store ignores unsupported tags but errors on attributes [src OS-SRC].
- **(new)** OpenDAL Python presign is async-only [src OD-PYI].

#### OP-19 Create an empty folder
- Coverage: OpenDAL `create_dir` (S3 simulated), pyarrow `create_dir`, fsspec `mkdir`/`makedirs`, Hadoop `mkdirs`; none in object_store or gocloud [doc/src].
- Zero-byte `key/` marker; Hadoop policy changes [doc].
- Same intent, different results: pyarrow markers, cloudpathlib no-op, s3fs/gcsfs/adlfs "create bucket", gcsfs HNS real folders [src/doc; obs].
- OpenDAL trailing `/` [doc].
- gocloud escapes a trailing `/` [doc].
- pyarrow rate-limit option [doc].
- Hadoop atomic probe+create [doc; inf].

#### OP-20 User metadata
- Limits:
    - S3: 2 KB, keys stored lowercase, US-ASCII; non-ASCII values RFC 2047-encoded; immutable except by copy.
    - Azure: C# identifiers, case-insensitive, 8 KB.
    - GCS: 8 KiB, patchable [doc].
- gocloud lowercases keys and escapes [doc].
- On S3 an update is a copy [src S3FS].
- Support is uneven: object_store local `NotImplemented`, pyarrow S3 silent drop, Attributes not returned by list [src; obs; doc].
- object_store mixes system and user metadata in `Attribute` [doc].
- **(new)** object_store tags (separate from attributes) are silently ignored where unsupported [src OS-SRC].
- **(new)** S3 ETag does not change on a metadata-only change [doc AWS-INTEG]. Azure `set_blob_metadata` replaces the whole set [doc AZ].

#### OP-21 Store lifecycle
- Coverage: gocloud `Bucket.Close`; vendor `close()`; no close in object_store, OpenDAL `Operator`, fsspec `AbstractFileSystem` (only file objects have `close`, `spec.py` L2270 [src]) or pyarrow [doc/src].
- fsspec instance cache hazard (#1002) [doc].
- Fragile GC-time async close [src; doc].
- pyarrow global `finalize_s3` [doc; src].
- Derived handles take over the lifecycle [doc].

#### OP-22 Native address mapping
- Coverage: fsspec `unstrip_protocol`/`url_to_fs`, pyarrow `from_uri`, OpenDAL `from_uri`/`info().root()`, object_store `parse_url`, gocloud `OpenBucket(url)`, smart_open `parse_uri`, cloudpathlib `as_uri`, Azure `BlobClient.url` [doc/src].
- The native path may be a cache copy (cloudpathlib) [src].
- pyarrow `MakeUri` embeds credentials; smart_open accepts them in URIs [src; doc].
- Many URL forms map to one store [doc].
- The logical key is not always the native key (percent-encoding, `__0x__` escaping) [doc].
- None of pyarrow, smart_open and cloudpathlib normalises `..`, `.` or `//` [obs].

#### OP-23 Native handle escape hatch
- Coverage: gocloud `As`/`ErrorAs`/`Before*`; s3fs `.s3`; adlfs `.service_client`; cloudpathlib `S3Client.client`; smart_open (injected client); object_store concrete types; none in OpenDAL or pyarrow Python [doc/src].
- `As` "implies that the resulting code is no longer portable" [doc GC].
- The handle may be uninitialised or bound to a loop (s3fs) [src].
- Errors are the most-used escape hatch [doc].

#### OP-24 Health check
- Coverage: OpenDAL `check()` (Rust; Python on both `Operator` and `AsyncOperator` [src OD-PYI]) and gocloud `IsAccessible`; nobody else [src].
- **They disagree on NotFound:** OpenDAL OK, gocloud false [src].
- "Healthy" means list permission; S3 HeadBucket also needs `s3:ListBucket` and answers 400/403/404 with no body [doc AWS-HB].
- OpenDAL checks relative to its root [src].

---

### Catalogue entry × comparable

Legend:
- **name**: the comparable's counterpart
- **(g)**: gated
- **(e)**: emulated or composite
- **—**: none found
- **n/c**: not checked

Cells changed against the first report are marked **Δ**.

| OP | fsspec | pyarrow.fs | OpenDAL (Rust / Py) | object_store | gocloud | smart_open | cloudpathlib | boto3 (S3) | Azure Blob | GCS |
|---|---|---|---|---|---|---|---|---|---|---|
| 01 read | `open`, `cat_file` | `open_input_stream` | `read`, `reader` | `get`, `get_opts` | `NewReader`, `ReadAll` | `open('rb')` | `read_bytes`, `open` (via cache) | `get_object` | `download_blob` | `download_as_bytes`, `Blob.open` |
| 02 read at offsets | `seek`, `cat_file(start,end)`, `cat_ranges` | `open_input_file`, `read_at` | `read_with(range)`, `Reader::fetch`; Py `read(offset,size)` Δ | `get_range`, `get_ranges` | `NewRangeReader` | `seek` (per transport) | `seek` on cache copy | `Range=` | `offset`/`length` | `start`/`end` |
| 03 write | `open('wb')`, `pipe_file`, `put_file` | `open_output_stream` | `write`, `writer` | `put`, `put_multipart` | `NewWriter`, `WriteAll`, `Upload` | `open('wb')` | `write_bytes`, `open('w')` | `put_object`, `upload_fileobj` | `upload_blob` | `upload_from_*`, `Blob.open('wb')` |
| 04 atomic replace | — (`transaction`, semi-atomic) | — (exception commits partial) | n/c (staged writes: conditions at final commit Δ) | `put` (atomic) | `Writer.Close` | — | — | PUT atomic | Put Blob / commit (inf) | write (inf) |
| 05 conditional write | `mode="create"`/`xb` (g) | — | `write_with(if_*)` (g, spec-bound Δ) | `PutMode::Create/Update` (g) | `IfNotExist` (absent only) | — | `open('x')` (e) | `IfNoneMatch`/`IfMatch` | `overwrite=False`, `etag`+`match_condition` | `if_generation_match` |
| 06 list children | `ls` | `get_file_info(FileSelector)` | `list` | `list_with_delimiter` | `List(Delimiter="/")` | — (`iter_bucket`) | `iterdir` | `list_objects_v2(Delimiter)` | `walk_blobs` | `list_blobs(delimiter)` |
| 07 walk (+depth) | `find`/`walk(maxdepth)` | `FileSelector(recursive)`, no depth | `list_with(recursive)` (g); Py `scan` Δ | `list`, no depth | `List` flat | — | `walk(lazy)`, `rglob` | flat prefix | `list_blobs`; HNS `get_paths` | flat prefix |
| 08 pattern | `glob` | — | — (none found) | — | — | — | `glob`, `rglob` | — | — | `match_glob` |
| 09 inspect | `info`, `exists`, `isdir`, `isfile`; `ukey`, `checksum` Δ | `get_file_info` | `stat` | `head` | `Attributes` (`ETag`, `MD5`) Δ, `Exists` | — (`to_boto3`) | `exists`, `is_*`, `stat`, `info` | `head_object` (ETag ≠ MD5 in general Δ) | `get_blob_properties` | `reload`, `exists` |
| 10 delete | `rm_file`, `rm` | `delete_file` | `delete` (missing = no-op) | `delete`, `delete_stream` | `Delete` | — | `unlink` | `delete_object(s)` | `delete_blob` | `Blob.delete` |
| 11 delete tree | `rm(recursive)`; `rmdir` Δ | `delete_dir`, `delete_dir_contents` | Rust `delete_with(recursive)` (g); Py `remove_all` Δ | — (list + `delete_stream`) | — | — | `rmtree`; `rmdir` Δ | — (list + `delete_objects`) | HNS `delete_directory` (g) | — (list + batch) |
| 12 move | `mv` (e) | `move` (g: S3 files e; Azure HNS) | `rename` (g; S3 unsupported) | `rename_opts` (e) | — | — | `rename`/`replace`/`move` (e) | `rename_object` (g: Express) | DataLake `rename_*` (g: HNS) | `move_blob` (atomic, same bucket); `rename_blob` (e) |
| 13 copy | `copy`, `cp_file` | `copy_file` (≤5 GB on S3 Δ) | `copy` (g) | `copy_opts` | `Copy` | — | `copy`, `copytree` | `copy_object` (≤5 GB), `copy` | `start_copy_from_url` | `copy_blob`, `rewrite` |
| 14 to/from local | `get`, `put` | `copy_files` | n/c | — | `Download`, `Upload` (io streams) | — (stream copy) | `download_to`, `upload_from` | `upload_file`, `download_file` | `upload_blob`, `download_blob` | `*_filename` |
| 15 between stores | generic copy, `rsync` | `copy_files(src_fs, dst_fs)` | n/c | — | — | `open` both ends | `copy` across clients | `copy(SourceClient=)` | `start_copy_from_url` | `copy_blob(destination_bucket)` |
| 16 scope | `DirFileSystem` | `SubTreeFileSystem` | `root` | `PrefixStore` | `PrefixedBucket`; `io/fs.SubFS` Δ | — | — | — | `ContainerClient` (partial) | `Bucket` |
| 17 hand to libs | `ArrowFSWrapper`, `get_mapper`, file objects | `PyFileSystem(FSSpecHandler)`, `filesystem=` | `object_store_opendal` | (obstore fsspec) | `io/fs.FS` Δ | file-like | `fspath` (cache copy) | file-like body | `StorageStreamDownloader` | `BlobReader`/`BlobWriter` |
| 18 capability query | — | — | `info().capability()` / Py `capability()` | — (`NotImplemented`/`NotSupported`; tags ignored Δ) | — (`Unimplemented`) | — | — | — | — | — |
| 19 create folder (g) | `mkdir`/`makedirs` (no-op or bucket) | `create_dir` (marker) | `create_dir` (g, simulated on S3) | — | — | — | `mkdir` (silent no-op) | — (`key/` convention) | DataLake `create_directory` (g) | `storage_control` folders (g) |
| 20 user metadata (g) | — generic (s3fs `setxattr`) | `metadata=` (S3 drops user keys) | `write_with(user_metadata)` (g) | `Attributes` (Local NotImplemented) | `WriterOptions.Metadata` | per transport | client `extra_args` | `Metadata=` | `metadata=`, `set_blob_metadata` | `metadata`, `patch` |
| 21 lifecycle | — (file `close` only; instance cache) | — (global `finalize_s3`) | — (Writer close/abort) | — (Drop) | `Bucket.Close` | file `close` | — (cache via GC) | `client.close()` | `close()`, CM | `Client.close()` |
| 22 address mapping | `unstrip_protocol`, `url_to_fs` | `from_uri` | `from_uri`, `info().root()` | `parse_url`, `Path::from_url_path` | `OpenBucket(url)` | `parse_uri` | `as_uri`, `from_uri` | — | `BlobClient.url` | `Blob.from_uri` (n/c) |
| 23 native handle | `.s3`, `.service_client` | — | — | concrete store types | `As`, `ErrorAs`, `Before*` | `to_boto3`; inject | `S3Client.client` | (native) | (native) | (native) |
| 24 health check | — | — | `check()` (Rust; Py sync + async Δ; NotFound = OK) | — | `IsAccessible` (NotFound = false) | — | — | `head_bucket` | `ContainerClient.exists` | `lookup_bucket`, `Bucket.exists` |

---

### Advisory notes for the catalogue (not decisions)

1. **Possible additions or explicit exclusions:**
    - presign (8/10)
    - system properties next to OP-20 (7/10)
    - batch delete, versioned access, integrity/identity tokens (6/10 each)
    - append (6/10, gated or emulated)
    - conditional read and abort (5/10 each)
    - multi-range read (3/10)
    - delete-contents / empty-only guardrails (3/10)
    - post-write metadata update (2/10 native)
2. **OP-05's scope.** The vendor stores and OpenDAL attach conditions to read, delete, copy, rename and metadata update. OpenDAL's spec is a worked precedent for defining conditions once:
    - no silent drop
    - atomic with commit
    - unspecified error point
    - status codes don't decide the error kind
3. **OP-07's depth limit** has one precedent (fsspec), and its cost on object stores is O(subtree).
4. **OP-09 / OP-14:** the comparables treat ETag and version as opaque identity tokens. AWS documents when an S3 ETag is not an MD5, so it cannot double as an integrity check.
5. **OP-18:** OpenDAL's effective flags plus pre-dispatch check, Hadoop's "False = unknown", and gates that depend on bucket type. Comparables also mix silent ignore with error (object_store tags vs attributes), which is a precedent to decide against or for explicitly [inf].
6. **OP-24:** a thin precedent (2/10), and the two disagree on NotFound.
7. **Shared decisions most often retrofitted, to decide once:**
    - `..` containment (three libraries in 2026)
    - missing-key delete (split across comparables)
    - exception typing in Python bindings
    - sync/async API parity in bindings (OpenDAL presign)
    - retry coupled to idempotency
    - behaviour on exception during a streamed write

### Caveats

- **Runs:** nothing was run against real AWS, Azure or GCS. [obs] items are from the moto S3 emulator and local disk (first run).
- **Issue pages:** GitHub issue pages are unreachable; issue numbers come from changelogs.
- **Still unverified on AWS, observed on MinIO** (run by the user; server version not stated; details in V02 `02-minio-probe.md`):
    - **Range reads:** a range starting at or past the size gives 416 `InvalidRange`. An end past EOF is clamped (206). A suffix larger than the object returns the whole object.
    - **Missing-key deletes:** `delete_object` on a missing key gives 204; `delete_objects` lists the key under `Deleted`.
    - **Error codes:** `NoSuchKey` (404), `InvalidRange` (416), `PreconditionFailed` (412 for both `If-None-Match: *` and a wrong `If-Match`). `head_object` on a missing key carries only status `'404'`, no code string.
    - These match RFC 9110, object_store's `GetRange` docs and AWS DeleteObjects docs. They do not verify AWS itself.
- **Still unverified:**
    - the content of the fsspec 2023.9.0 glob change
    - reports that botocore 1.36 broke S3-compatible servers
- **Resolved here:** the Azure `retry_total` default (3) and pyarrow S3 copies over 5 GB (single CopyObject).
- **Versions:**
    - Hadoop pages were read at both 3.3.5 ("stable") and 3.5.0 ("current").
    - smart_open docs come from `develop`, which may be ahead of 8.0.4.
    - Some fsspec, OpenDAL and object_store source was read on main or master, possibly slightly ahead of the release.
- **Corrections carried over from the first run's workflow track (its notes 01):**
    - A 1–2 vote refuted a bundled claim about gocloud `SignedURL`/`Unimplemented`. The v0.47.0 source and docs confirm `SignedURL` → `Unimplemented`, and that is what this report uses.
    - Its statement that gocloud returns `PreconditionFailed` is superseded: the code is `FailedPrecondition` (verified in source).
- **External inputs:** the ChatGPT and Perplexity texts were leads only. MinIO claims from the Perplexity answer rest on vendor marketing and are not used.
- **This run's own limits:**
    - The OpenDAL conditional spec page is undated except for "Last updated on Aug 31, 2026". It is a moving reference, not pinned to 0.59.5.
    - The S3 integrity pages were read through WebFetch (rendered to markdown), not raw HTML.
- **Version-sensitive areas:** the pre-1.0 crates (object_store, OpenDAL) and the S3 conditional-operation matrix change often.
