# Research: ID-200 — s3fs error-mapping fidelity in `_S3Base`

**Item ID:** ID-200
**Date:** 2026-05-31
**Method:** moto-backed `S3Backend` (Stage 1, in-process `ThreadedMotoServer`); no Docker, no live AWS.
**Probe:** [`research-s3-error-mapping-fidelity.py`](research-s3-error-mapping-fidelity.py) (throwaway driver, re-runnable via `hatch run python sdd/research/research-s3-error-mapping-fidelity.py`).
**Status:** Audit complete. moto-reproducible surface verified; one divergence → **BUG-214** (fixed). Over-the-wire confirmation of rows (b)/(c) completed under **BK-248** against real AWS S3 (`tests/backends/s3/test_live_error_mapping.py`, `RS_TEST_LIVE_S3=1`) — see § 3(b)/(c) "Over the wire" and § 6.

---

## 1. Question

Does the s3fs → `_S3Base._s3fs_errors` → `_classify_error` boundary in
`src/remote_store/backends/_s3_base.py` preserve enough signal from
`botocore.ClientError` to meet our typed-error contract (spec S3-015..S3-018),
or does s3fs swallow / collapse cases the docs claim we surface?

ID-200 names five scenarios. Drive each against a moto-backed `S3Backend`,
record the target typed error, the observed typed error, and the underlying
s3fs/botocore exception. A divergence opens a BUG; otherwise the note is the
closing evidence.

## 2. Findings (one row per scenario)

| # | Scenario | Target | Observed (moto) | Underlying exception | Verdict |
|---|---|---|---|---|---|
| a | `GetObject` missing key | `NotFound` | `NotFound` | `FileNotFoundError` from `s3fs` | ✅ pass |
| b | `GetObject` forbidden (403) | `PermissionDenied` | `PermissionDenied` | botocore 403 `AccessDenied` → s3fs `PermissionError` | ✅ pass (mapping); natural-path deferred |
| c | `PutObject` expired/invalid token | `BackendUnavailable` \| `PermissionDenied` | `PermissionDenied` (all three credential failures) | `ExpiredToken`/`InvalidAccessKeyId`/`SignatureDoesNotMatch` → s3fs `PermissionError` | ✅ pass (mapping); natural-path deferred |
| d | Multipart abort mid-stream (>5 MB) | typed error **and no partial object** | typed error raised (`BackendUnavailable`) **but a truncated object is committed** | content-stream `ConnectionResetError`; s3fs `close()` commits on `__exit__` | ❌ **diverges → BUG-214** |
| e | `HeadObject` directory-marker ambiguity | `InvalidPath` \| `NotFound`, not a confused mix | no error; deterministic exact-key precedence | none (exact-key HEAD succeeds) | ✅ pass (no confusion); minor note |

## 3. Detail

### (a) Missing key → `NotFound`
`read()` on an absent key: s3fs raises `FileNotFoundError`, caught by
`_s3fs_errors` and re-raised as `NotFound` with `path` and `backend` set.
No surprise; matches S3-015.

### (b) Forbidden 403 → `PermissionDenied`
**moto does not enforce ACL/IAM by default, so a genuine 403 is not
reproducible in-process.** To audit the *mapping* faithfully we constructed
the real `botocore.ClientError` a 403 `GetObject` produces and ran it through
s3fs's own translator and our real `_s3fs_errors`:

- `s3fs.errors.translate_boto_error(403 AccessDenied)` → `PermissionError`.
- `_s3fs_errors` catches `PermissionError` → `_permission_denied` →
  `PermissionDenied`.

So the boundary is correct *when a 403 propagates as an s3fs `PermissionError`*.
The residual unknown is over-the-wire: that a live S3 403 on the `GetObject`
read path actually routes through `translate_boto_error` (rather than being
swallowed inside an aiobotocore streaming read) — see BK-248.

**Over the wire (BK-248).** Confirmed against real AWS S3. A read with a
bogus access key / secret yields a genuine 403 (`InvalidAccessKeyId` /
`SignatureDoesNotMatch`), and both `read_bytes` (→ `cat_file`) and `read`
(→ `open` + stream) raise `PermissionDenied` with `backend == "s3"`. The
"swallowed inside an aiobotocore streaming read" worry does **not**
materialise: s3fs issues an eager HEAD/GET *inside* the `_s3fs_errors`
context (both `cat_file` and `open`), so the 403 is caught by the context
manager and mapped before any stream is handed back — it never reaches the
`_ErrorMappingStream` wrapper. The streaming-read classifier
(`_classify_by_message`, used by `_ErrorMappingStream`) is therefore not on
the auth-failure path at all.

A distinct `AccessDenied` (valid credentials, forbidden resource) was *not*
separately exercised. The single-credential `s3_live` IAM user has full
access within its `rs-conformance-*` grant, and targeting a bucket *outside*
the grant returns **404 `NoSuchBucket`** (→ `NotFound`), not 403 — S3 reports
a non-existent bucket as 404 to a credentialed caller regardless of IAM
(empirically confirmed during BK-248). Because `translate_boto_error` keys on
the 403 error *code* identically for `AccessDenied` and the invalid-credential
codes, the credential-failure 403 confirms the same mapping boundary the
`AccessDenied` row would. Provisioning an existing-but-forbidden bucket
(second restricted credential, or a bucket policy `Deny`) is the only way to
exercise the `AccessDenied` code itself and is out of scope for the current
`s3_live` setup.

### (c) Expired / invalid credentials → `PermissionDenied`
**moto accepts any credentials, so this too is not naturally reproducible.**
Running the three realistic botocore `ClientError`s through the same real
path:

| Credential failure | HTTP | s3fs translate | mapped |
|---|---|---|---|
| `ExpiredToken` | 400 | `PermissionError` | `PermissionDenied` |
| `InvalidAccessKeyId` | 403 | `PermissionError` | `PermissionDenied` |
| `SignatureDoesNotMatch` | 403 | `PermissionError` | `PermissionDenied` |

All three satisfy the target (`BackendUnavailable` **or** `PermissionDenied`);
none is a silent success. Note `ExpiredToken` is HTTP **400**, yet s3fs keys on
the *error code* and still yields `PermissionError` — so our earlier worry that
it would fall through to a bare `RemoteStoreError` via the message heuristic was
wrong (the heuristic never runs; s3fs translates first).

**Over the wire (BK-248).** Confirmed: a `PutObject` (`write` →
`pipe_file`) with invalid credentials raises a real 403 over the wire and
maps to `PermissionDenied` with `backend == "s3"`, matching the read-path
result in § 3(b).

### (d) Mid-stream failure → typed error **but truncated object committed**  ❌
This is the divergence. When the *content source* raises mid-stream during
`write()` / `write_atomic()`, a typed error **is** raised, but a **truncated
object is left in the bucket**:

| Entry point | Bytes delivered before failure | Left behind |
|---|---|---|
| `write()` | 6 MB | object **present, 6 291 456 B** (single PUT) |
| `write()` | 55 MB | object **present, 57 671 680 B** (completed multipart: parts 1+2 + CompleteMultipartUpload) |
| `write_atomic()` | 6 MB / 55 MB | same as `write()` (S3 `write_atomic` delegates to `write`) |
| `open_atomic()` (caller raises *inside* the `with`) | 6 MB buffered | object **ABSENT** — safe |

Root cause: `write()`'s streaming branch does
`with self._fs.open(path, "wb") as f: ... f.write(chunk)`. When
`content.read()` raises, s3fs's `S3File.__exit__` calls `close()`, which
flushes the buffer / completes the in-flight multipart upload **regardless of
whether the `with` body raised**. The result is a *complete-looking but
truncated* object — arguably worse than an orphaned multipart upload, because
it passes a later `HeadObject`/`exists` check.

This breaks the `ATOMIC_WRITE` contract for `write_atomic` ("no reader ever
sees a partial file") and leaves plain `write` in an inconsistent state (caller
gets `BackendUnavailable`, yet a truncated object exists). It is **server-
independent** (s3fs `close()` semantics), so moto reproduces it faithfully and
the fix is verifiable in the default Stage-1 suite — no Docker/AWS needed.

`open_atomic` is **not** affected by a *caller* exception, because it buffers to
a `SpooledTemporaryFile` and only calls `write()` after the `yield`; a caller
exception skips the upload entirely. The exposure is specifically the
streaming-content path of `write` / `write_atomic`.

Notes for the fix (BUG-214, not done here per audit/bug-fix protocol):
- The fix likely wraps the s3fs file so an exception aborts the upload (e.g.
  `S3File.discard()` / `_abort_mpu`) instead of letting `__exit__` commit.
- The "5 MB" in the scenario title is a red herring for s3fs: its write block
  size defaults to **50 MB** (`S3FileSystem.default_block_size = 52428800`), so
  true multipart only engages above 50 MB. Below it the truncated commit is a
  single PUT. Both sizes are covered above.

### (e) Directory-marker ambiguity → deterministic, not confused
With both a file `conf` and a key `conf/app.txt` present:

- `is_file("conf")` → `True`
- `is_folder("conf")` → `False`
- `get_file_info("conf")` → returns the file's `FileInfo`
- `read("conf")` → returns the file bytes

The feared "confused mix" does not materialise: an exact-key `HeadObject` on
`conf` resolves deterministically to the file and the same-named prefix is
ignored. No `InvalidPath`/`NotFound` is raised — but none is needed, because
there is no ambiguity in the operations tested. The one debatable point is that
`is_folder("conf")` returns `False` even though the prefix `conf/` exists and is
listable; the file shadows the prefix. This is a known flat-namespace limitation,
not a typed-error defect — recorded here, not escalated.

## 4. Disposition

- **(d)** opens **BUG-214** — `write`/`write_atomic` commit a truncated object
  when the content source fails mid-stream. Reproducible on moto; failing test +
  fix belong to BUG-214 per the bug-fix protocol.
- **(b)/(c)** pass at the mapping boundary, and the natural path is now
  confirmed over the wire against real AWS by **BK-248**
  (`tests/backends/s3/test_live_error_mapping.py`): an invalid-credential 403
  maps to `PermissionDenied` on `read_bytes`, streaming `read`, and `write`.
  The streaming-read swallow risk does not materialise — s3fs's eager HEAD/GET
  inside `_s3fs_errors` catches the 403 before any stream is returned. A
  distinct `AccessDenied` error code (valid creds, forbidden resource) is not
  exercised because the `s3_live` IAM user cannot provision an
  existing-but-forbidden bucket; an out-of-scope bucket returns 404, not 403.
  s3fs translates `AccessDenied` and the invalid-credential codes identically,
  so the boundary is the same.
- **(a)/(e)** pass; no action.
- **ID-202** (boto3-direct lane) should reuse this note: its `ClientError`
  → typed-error mapping must (i) preserve the 403/credential → `PermissionDenied`
  rows verified here, and (ii) **not** inherit the (d) truncated-commit defect —
  a boto3 `upload_fileobj` that fails mid-stream must abort, not complete.

## 5. Reproduction

```
hatch run python sdd/research/research-s3-error-mapping-fidelity.py
```

Drives all five scenarios against a fresh in-process moto server and prints,
per scenario, the observed typed error and the underlying exception. The (d)
rows additionally report the committed object size and any orphaned multipart
uploads.

## 6. Over-the-wire confirmation (BK-248)

The credential/permission rows (b)/(c) are confirmed against real AWS S3 by
`tests/backends/s3/test_live_error_mapping.py` (Stage 3, opt-in):

```
RS_TEST_LIVE_S3=1 hatch run pytest -m live tests/backends/s3/test_live_error_mapping.py
```

The suite constructs an `S3Backend` with a bogus access key / secret and
asserts that the resulting live 403 maps to `PermissionDenied` on the read
(`read_bytes` and streaming `read`) and write (`write`) paths, with
`backend == "s3"`. Result: all paths pass — the live 403 routes through
`s3fs.translate_boto_error` → `_s3fs_errors`, and the eager HEAD/GET means the
streaming-read wrapper is never on the auth-failure path. No production-code
change was needed. See § 3(b)/(c) "Over the wire" for the `AccessDenied`-vs-404
caveat.
