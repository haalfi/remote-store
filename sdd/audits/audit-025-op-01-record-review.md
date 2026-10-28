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

Seven tensions that `O14` to `O16` do not cover. Each became an open item in
the record, C2 and C7 as notes, C5 as a ground conflict and the rest as
reopens (§ 5 maps them).

| # | Where | Tension | Sev. |
| --- | --- | --- | --- |
| C1 | D33 vs D34 | D33 justifies its typing by "`except` on the store's base never hides a bug in the caller's code". D34 puts key refused under that base, raised before any backend contact, though `read('../x')` is most often a caller's bug. Key refused, `UnicodeDecodeError` (D32), closed-stream reads (D15) and caller errors are all `ValueError`, so `except ValueError` cannot tell them apart. | should fix |
| C2 | D16 vs D39 | D16: recovery has one place, inside a read. D39's option (a), which its Decision adopts by reference, says "the **next** read resumes", while D6's `read(n)` returns min(n, r) bytes, so the resume happens inside the read that met the reset. D39's Decision bullet itself ("a resume is a retry under D38's limit ... without a gap or a repeated byte") agrees with D16, and a spec copies that bullet, so only the adopted option's wording conflicts; the record carries it as a note. | optional |
| C3 | D10, D21, D22, D25 vs Local on Windows | An open Local stream holds a handle. On Windows `os.replace` and `os.remove` fail with a sharing violation on a file open without `FILE_SHARE_DELETE`, which Python's `open()` does not set (not run here); Local's atomic write is `os.replace` (`_local.py:389`, `:453` ✓). An open stream then makes an O2 write or delete fail, an outcome another API call observes. D25's "an open file descriptor keeps the old file" holds on POSIX only. No variation point (D43) names it. Windows is supported: `pyproject.toml:65` declares `Operating System :: OS Independent`, and the `os_sensitive` marker (`pyproject.toml:780`, "atomic writes, local filesystem") runs on the `windows-latest` lane (`.github/workflows/ci.yml:587` ✓). | blocks |
| C4 | D9 vs D21 on object stores | D9's folder check is a second request on the failure path (GET 404, then a listing). D21 takes classification and content from one instant. Most interleavings leave a valid instant between the two requests; one does not. `d` and `d/f` are absent at the GET, which answers 404; O3 then creates `d`, and only then `d/f`, before the listing, which finds `d/f`. The read reports not an item, yet `d` was absent, then an item, then both (C5's state), so no instant in the interval has it a folder and not an item. D21 needs the argument for the composed classification, or a stated exception. | should fix |
| C5 | TREE-001 vs S3 | TREE-001: no entity is both a folder and an item. On S3, O3 can create the objects `a.txt` and `a.txt/b` together. KEY-013 then gives `a.txt/b` BlockedByItem, so D9 says not found, while a GET returns content. No Environment row (E1 to E15) names the state, and enforcing D9 on it costs an ancestor check on every successful read. | blocks |
| C6 | D33 vs D28, D38 | Descriptor exhaustion (E13) propagates as raised on Local (D33). On S3 the same condition surfaces through the SDK as a connection failure, which D28 reads as E7, D38 retries and D34 types unavailable. One cause, two categories by backend. | optional |
| C7 | D12 vs D20 | D12 leaves a whole-call deadline to a later extension, so a caller's own deadline is a cancellation (`asyncio.wait_for(stream.read(n), 5)`). D20 closes a stream whose read is cancelled, so that deadline destroys the stream. No contradiction in the text; a trap D12's reason does not name, so the record carries it as a note, not a reopen. | optional |

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
  (key refused, not found, not an item) and the access and readability ones
  (permission denied, authentication failed, not readable), but not
  unavailable and timeout. That those also surface from the open is implied by
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
| 1 | D12, D38, D39 | S3 and Azure delegate retries to their SDKs, mapping `max_attempts` alone and logging that backoff and jitter are ignored (`_s3_base.py:505`, `_s3_boto3.py:1066`, `_s3_pyarrow.py:604`, `_azure_common.py:392` ✓). The library already owns one loop of D38's shape: HTTP's (`_http.py:552` to `:585` ✓), with equal-jitter backoff and a Retry-After floor from `remote_store._retry` (HTTP-RETRY-001). SFTP retries its connect only, through tenacity with exponential backoff and jitter (`_sftp.py:1834` to `:1848` ✓). The estimate starts from that loop. What remains is disabling the S3 and Azure SDK retries (or attempts multiply, 3 × 3 at the defaults), running the loop per request there and for SFTP's reads, retrying E12, restarting the limit on progress inside a stream (D39), and an async twin. | high |
| 2 | D20 | `KeyboardInterrupt` lands between any two bytecodes, cleanup included, so "Closed and released" is best effort in the sync form; a sync form running on a background loop must also carry the cancel across threads. | high |
| 3 | D22, D39, D43 | Every request after the open, prefetch and parallel ranges included (NP2, NP3), carries `If-Match`, a version or a generation. An S3-compatible endpoint that ignores `If-Match` breaks "never another content" silently, which D43's weaker default covers only if the declaration is right. s3fs's internal block fetching would have to be checked against it. | high |
| 4 | C5 | A design decision first (an extra request on success, an Environment row, or a declared non-promise), then code. | high, design |
| 5 | D40 on SFTP | paramiko's `prefetch` caps requests in flight, not data held: `_async_response` moves each answered extent into `_prefetch_data` and frees its slot, so a slow consumer accumulates the file in memory (paramiko 5.1.0 ✓). The whole read calls it (`read_bytes`, `_sftp.py:936` ✓), which NP8 permits, since a whole read holds the content anyway. No stream path calls it: `rg -n prefetch src/remote_store/backends` returns only that call and the docstring at `_sftp.py:2243` ✓. A stream under D40 cannot reuse it as is and needs its own bounded window. | medium |
| 6 | D17, async form | A finaliser cannot await, so releasing an aiohttp connection without a running loop is fragile, and aiohttp emits its own unclosed warnings beside D17's. | medium |
| 7 | D27 | `class NotFound(StoreError, FileNotFoundError)` works; the work is mapping each SDK's wrapped exceptions to the categories. | medium, wide |
| 8 | D24 on SFTP | One paramiko channel serialises requests, so overlapping calls need a connection pool per handle. | medium |
| 9 | C3 | A declared deviation, or a native open with `FILE_SHARE_DELETE` through `msvcrt` or `ctypes`. | low to medium |

## 5. What the misses say about `/observe`

Each finding, together with `O14` to `O16`, falls into one of four classes,
assigned below one by one. Fixing them is filed as BK-499; this section is its
diagnosis.

1. **A consistency check its author writes once and nobody re-runs: C1, C2,
   G5.** Each conflict pairs a later decision with an earlier one, which
   `/observe` step 3's check against earlier decisions covers, and the check
   was written. It names a subset its author picked: D34's names D9 but not
   D33 (C1), and D35's names D22 and D34 but not D28 (G5). Or it checks only
   part of the decision: D39's names D16 and holds for D39's Decision bullet,
   but not for the option (a) text the Decision adopts (C2). Nothing re-reads
   a check. ADR-0034 answers the same failure in review with
   an unprimed reader.
2. **Decision text beyond its dialog: `O14` to `O16`.** Each is text that no
   dialog asked, as the record's entries state: D35's read-phase list, E15 in
   D25, and D19's exposure table and its sentence on s4.
3. **Implementation behaviour outside the unprimed ground: C3 to C6, § 3,
   § 4.** S1 keeps code and specs 001 to 050 out, as it must, so what
   backends, their SDKs and the Python runtime do never enters. That covers
   Windows sharing (C3), S3's two requests and both shapes (C4, C5), an SDK's
   mapping of descriptor exhaustion (C6), ETags surviving a tier change (§ 3),
   and § 4's rows, `KeyboardInterrupt` and aiohttp's finaliser included.
   Nothing between the record and the spec reads them.
4. **Questions no axis raises: C7, G1 to G4.** A caller's own deadline (C7),
   the async stream's shape (G1), the file object's other methods (G2), an
   unknown encoding (G3) and an exception re-raised (G4) are none of the
   axes' questions, so the loop never asked them. The skill's Rules already
   route such a question to the axes' F2 revision after `read()`.

The record carries the findings as open items: C1 is `OP-01/O17`, C2 the note `O18`, C3
`O19`, C4 `O20`, C5 `O21`, C6 `O22`, C7 the note `O23`, G1 `O24`, G2 `O25`, and
G3 to G5 together `O26`; § 3's evidence is appended to `O14` and `O15`.

## Appendix: derivations

- Line references to `src/`: `rg -n "prefetch|os\.replace|retries|max_attempts|retry_total" src/remote_store/backends`
  and `rg -n "equal_jitter|retry_after|wait_exponential|wait_random" src/remote_store/backends`
  at `c58ee74`, read uncapped: a run capped at 25 lines hides `_http.py`'s and
  `_sftp.py`'s hits.
- § 5's class 1: each decision's Consistency check line in the record, read
  for the decisions it names.
- C3's platform: `rg -n "OS Independent|os_sensitive|windows-latest" pyproject.toml .github/workflows/ci.yml`.
- paramiko: `inspect.getsource` of `SFTPFile._start_prefetch`,
  `_prefetch_thread` and `_async_response` in the default hatch environment,
  `paramiko.__version__` 5.1.0.
- The finding counts: the rows of § 1 (seven) and the bullets of § 2 (five),
  enumerated in this file.
