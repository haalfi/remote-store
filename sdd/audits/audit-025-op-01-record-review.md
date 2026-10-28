# Audit 025 — The OP-01 record: one view of read()?

**Date:** 2026-10-28

**Motivation:** OP-01's record is the first output of `/observe` (BK-485,
RFC-0024 § 9 step 5), and step 5's spec clauses are written from it next. PR
#1188's review found three contradictions after the session had closed every
axis (`OP-01/O14` to `O16`). This audit asks whether more remain before the
spec is written, and what the misses say about the session itself.

**Scope:** `sdd/observe/records/OP-01.md` at `c58ee74`, read whole against
itself, spec 051 (TREE-001), spec 052 (KEY-013), and, for feasibility only,
`src/remote_store/backends/` and paramiko 5.1.0's source. Three questions:
does the record give one consistent view of a read, which requirements
contradict each other, and where implementation gets hard.

**Method:** one reader, one pass over the whole record, then each candidate
checked against the decisions it names. Findings marked ✓ were confirmed by
reading `src/` or a dependency's source in this session; the rest are readings
of the text or of backend behaviour not run here. Severity: blocks a spec
clause, should fix, optional. Prescriptions are advisory (CLAUDE.md § Audits).

**Verdict:** the core view is consistent. Classification (D9) feeds one
instant per whole read (D21) and one pinned content per stream (D22), and
failures are sticky (D16) and typed (D34). The stream state table (D18 with
D20's transition) is closed. Seven further tensions and five gaps remain; two
of the tensions (C3, C5) are missing design decisions, not wording.

## 1. Contradictions

Seven tensions that `O14` to `O16` do not cover. Each became a reopen in the
record's Open items (§ 5 maps them).

| # | Where | Tension | Sev. |
| --- | --- | --- | --- |
| C1 | D33 vs D34 | D33 justifies its typing by "`except` on the store's base never hides a bug in the caller's code". D34 puts key refused under that base, raised before any backend contact, though `read('../x')` is most often a caller's bug. Key refused, `UnicodeDecodeError` (D32), closed-stream reads (D15) and caller errors are all `ValueError`, so `except ValueError` cannot tell them apart. | should fix |
| C2 | D16 vs D39 | D16: recovery has one place, inside a read. D39's Decision: "the **next** read resumes". D6's `read(n)` returns min(n, r) bytes, so the resume happens inside the read that met the reset. The wording conflicts, not the intent, but the spec copies the wording. | should fix |
| C3 | D10, D21, D22, D25 vs Local on Windows | An open Local stream holds a handle. On Windows `os.replace` and `os.remove` fail with a sharing violation on a file open without `FILE_SHARE_DELETE`, which Python's `open()` does not set (not run here); Local's atomic write is `os.replace` (`_local.py:389`, `:453` ✓). An open stream then makes an O2 write or delete fail, an outcome another API call observes. D25's "an open file descriptor keeps the old file" holds on POSIX only. No variation point (D43) names it. | blocks, if Windows is a supported platform |
| C4 | D9 vs D21 on object stores | D9's folder check is a second request on the failure path (GET 404, then a listing). D21 takes classification and content from one instant. Most interleavings leave a valid instant between the two requests; one does not: with O3 creating an object `d` while `d/f` exists (C5), no instant has `d` a folder and not an item. D21 needs the argument for the composed classification, or a stated exception. | should fix |
| C5 | TREE-001 vs S3 | TREE-001: no entity is both a folder and an item. On S3, O3 can create the objects `a.txt` and `a.txt/b` together. KEY-013 then gives `a.txt/b` BlockedByItem, so D9 says not found, while a GET returns content. No Environment row (E1 to E15) names the state, and enforcing D9 on it costs an ancestor check on every successful read. | blocks |
| C6 | D33 vs D28, D38 | Descriptor exhaustion (E13) propagates as raised on Local (D33). On S3 the same condition surfaces through the SDK as a connection failure, which D28 reads as E7, D38 retries and D34 types unavailable. One cause, two categories by backend. | optional |
| C7 | D12 vs D20 | D12 leaves a whole-call deadline to a later extension, so a caller's own deadline is a cancellation (`asyncio.wait_for(stream.read(n), 5)`). D20 closes a stream whose read is cancelled, so that deadline destroys the stream. No contradiction in the text; a trap D12's reason does not name. | should fix |

## 2. Gaps

Five places where a spec clause would have no decision to cite.

- **G1, the async stream's shape** (D1, D2). D2's reason, a file object that
  `copyfileobj`, `TextIOWrapper` and pandas read, holds for the sync form only.
  For `AsyncStore` nothing says what `async for` yields (lines or chunks) or
  whether an async `readline` exists; D1's "both forms behave alike" cannot
  hold literally there.
- **G2, the file object's other methods** (D2, D6, D18). D18's table lists
  `readinto` and `readline`, which have no semantics as D6 gives `read(n)`.
  `read1` (which `TextIOWrapper` prefers when present), `readline(limit)`,
  `tell()`, `readable()` and `seekable()` are undecided.
- **G3, an unknown encoding** (D3, D33). `codecs.lookup` raises
  `LookupError`, neither `TypeError` nor `ValueError`, and D33's "before any
  backend contact" then means looking the codec up before the request.
- **G4, "the same failure again"** (D16). Re-raising one exception object
  appends to its traceback on every raise; the record does not say whether a
  Failed stream raises that object or a fresh, chained one.
- **G5, the open call's list** (D35). It names the classification failures
  only. That unavailable and timeout also surface from the open is implied by
  D28, not stated, and the list reads as complete.

## 3. Evidence for O14 to O16

`O14` asks whether to widen D35's read-phase list or narrow D19's s3 cells for
E6 and E15. Backend behaviour argues for widening. A mid-stream resume (D39) is
a new request: after E6 it meets a 403, permission denied. Moving an object to
an archive tier by lifecycle (S3) or Set Blob Tier (Azure) keeps its ETag as
far as this reader knows (not run here), so the resume passes its `If-Match`
pin and then fails with `InvalidObjectState` or `BlobArchived`: not readable
mid-stream, not changed, which also answers the category `O15` asks for. `O16`
gets no new evidence.

## 4. Where implementation gets hard

Estimates, ordered by expected cost; advisory, for step 5 and the
implementation that follows.

| Rank | Decisions | Why hard | Estimate |
| --- | --- | --- | --- |
| 1 | D12, D38, D39 | Retries are delegated to the SDKs today, mapping `max_attempts` alone and logging that backoff and jitter are ignored (`_s3_base.py:505`, `_s3_boto3.py:1066`, `_s3_pyarrow.py:604`, `_azure_common.py:392` ✓). D38 wants the library's own backoff with jitter, retry-after hints, E12 retried and a limit that restarts on progress (D39). That means disabling SDK retries, or attempts multiply (3 × 3 at the defaults), and one loop per backend in both forms. | very high |
| 2 | D20 | `KeyboardInterrupt` lands between any two bytecodes, cleanup included, so "Closed and released" is best effort in the sync form; a sync form running on a background loop must also carry the cancel across threads. | high |
| 3 | D22, D39, D43 | Every request after the open, prefetch and parallel ranges included (NP2, NP3), carries `If-Match`, a version or a generation. An S3-compatible endpoint that ignores `If-Match` breaks "never another content" silently, which D43's weaker default covers only if the declaration is right. s3fs's internal block fetching would have to be checked against it. | high |
| 4 | C5 | A design decision first (an extra request on success, an Environment row, or a declared non-promise), then code. | high, design |
| 5 | D40 on SFTP | paramiko's `prefetch` caps requests in flight, not data held: `_async_response` moves each answered extent into `_prefetch_data` and frees its slot, so a slow consumer accumulates the file in memory (paramiko 5.1.0 ✓). The current backend does not call it (`rg prefetch src/remote_store/backends` finds nothing ✓); an implementation of D40 needs its own bounded window. | medium |
| 6 | D17, async form | A finaliser cannot await, so releasing an aiohttp connection without a running loop is fragile, and aiohttp emits its own unclosed warnings beside D17's. | medium |
| 7 | D27 | `class NotFound(StoreError, FileNotFoundError)` works; the work is mapping each SDK's wrapped exceptions to the categories. | medium, wide |
| 8 | D24 on SFTP | One paramiko channel serialises requests, so overlapping calls need a connection pool per handle. | medium |
| 9 | C3 | A declared deviation, or a native open with `FILE_SHARE_DELETE` through `msvcrt` or `ctypes`. | low to medium |

## 5. What the misses say about `/observe`

Every finding above falls into one of two blind spots the session has by
design. Fixing them is filed as BK-499; this section is its diagnosis.

1. **The consistency check looks backwards only.** `/observe` step 3 checks
   each decision against earlier ones as it is written. A conflict that needs
   the whole record, a later decision against an earlier reason, passes: C1,
   C2, G4, G5, and PR #1188's own `O14` to `O16`. ADR-0037 records the same
   failure for review, which its whole-file gate answers.
2. **The session is unprimed, and backends are not on its ground.** S1 keeps
   code and specs 001 to 050 out, as it must. Backend physics then never
   enters: C3 (Windows sharing), C5 (S3 holding both shapes), § 3 (ETags
   surviving a tier change), and every row of § 4. Nothing between the record
   and the spec reads them.

The record carries the findings as reopens: C1 is `OP-01/O17`, C2 `O18`, C3
`O19`, C4 `O20`, C5 `O21`, C6 `O22`, C7 `O23`, G1 `O24`, G2 `O25`, and G3 to G5
together `O26`; § 3's evidence is appended to `O14` and `O15`.

## Appendix: derivations

- Line references to `src/`: `rg -n "prefetch|os\.replace|retries|max_attempts|retry_total" src/remote_store/backends` at `c58ee74`.
- paramiko: `inspect.getsource` of `SFTPFile._start_prefetch`,
  `_prefetch_thread` and `_async_response` in the default hatch environment,
  `paramiko.__version__` 5.1.0.
- The finding counts: the rows of § 1 (seven) and the bullets of § 2 (five),
  enumerated in this file.
