# Research: OP-01's behaviours classified, pilot on the stream lifecycle (BK-511)

<!-- doc: repo-only -->

**Date:** 2026-11-03; § 6 and § 7 2026-11-04
**Backlog items:** BK-511, BK-485
**Status:** Complete: pilot, whole record, the not-decided behaviours routed
(§ 6) and Local's gaps rerun at master as evidence, none filed (§ 7). A
point-in-time snapshot of the record tagged `observe/OP-01/freeze-1`
(`a7de4e31`).

---

## 1. Question and answer

Can OP-01's decisions, which mix happy and unhappy paths, read forms, sync and
async, and backends, be split into one entry per observable behaviour and
classified along fixed facets before spec work? On the stream lifecycle, yes:
45 decisions become 37 behaviour clauses, each checkable against a vocabulary,
covering every decision and every rule of the spike's freeze-1 oracle. The
split also shows what a decision-level reading hides: one behaviour needs up
to six decisions, 16 of the decisions the slice's clauses cite lie outside its
`Amends:` closure, and six behaviours are not decided. The whole record (§ 5) gives 123 clauses and
32 decisions with no behaviour of their own; 97 clauses are not a success
path, and seven behaviours are not decided, six of them the pilot's.

## 2. Method

- **Unit:** a behaviour clause, given (pre-state), when (call or trigger),
  then (outcome), stated as it holds after every amendment (`pilot.toml`).
- **Facets:** the record's axis; path and trigger; form, sync or async and
  stream state; backend scope; SPEC-DESIGN Rule 2's kind; status (decided,
  partly, implied, open); and two pieces of evidence: the spike's freeze-1
  rule and what 0.33 Local was observed to do (the spike's C1 to C8).
- **Pilot set:** the slice (D2, D6, D7, D15 to D18, D20, D36), every
  transitive amender of it from the record's `Amends:` lines (its closure,
  `check.py`), and five decisions found by reading to decide it without an
  amendment reaching it (`CITED_NOT_AMENDING`, which only widens the coverage
  scope; § 3 measures the full set).
- **Check:** `check.py --pilot` fails on a value outside a facet's vocabulary,
  a pilot decision no clause cites (and no `record_text` entry explains), or a
  freeze-1 rule no clause maps. It failed once while the pilot was written:
  rule G1 (collecting a Closed stream warns nothing) had no clause, now S37.

## 3. Pilot results

From `check.py --pilot` on the frozen record, with § 5's facet decisions
applied. The pilot as first classified (`596e79d87`) differs in four
fields only (a field-by-field comparison of the two `pilot.toml`): the
trigger of 9 clauses (S18, S19, S22 read `E8`, now D96's stream-read rows;
S16 `E8`, now those rows and E14; S24 `E8`, now E8 and E13; S27 to S29 `Runtime`, now E14; S30 `O2`,
now E1 and E2), the state of S01, S02 (`open-call`, now `none`) and S16 (`Exhausted`, now
`Open`, as its `given` states; F10 asks the rest), S33's gap (none, now
`OP-01/O5`), and `local` on S05, S16 and S32 (`pass`, now `untested`: Local
passed the spike's assumed rule, not a decided behaviour, which `check.py`
now refuses). Those first counts drove § 4.

| Facet | Counts over 37 clauses |
|---|---|
| Path | success 14, release 7, storage-failure 5, caller-error 3, cancellation 3, end 2, non-promise 2, lifetime-end 1 |
| Trigger | the caller or the runtime 28, an Environment row 9 |
| Form, api | stream 37; both forms 34, async only 3 |
| Scope | portable 35; a D43 variation point 2 (Cancelled close, Overlapping mutation) |
| Kind | lifetime 32, single call 3, environment 1, structure 1 |
| Status | decided 31, partly 2, implied 1, open 3 |
| Local | pass 13, untested 13, not offered 1, a gap 10 (C1 to C8) |

What the classification shows:

- **The unhappy paths are most of the slice, and Local's gaps sit there.**
  23 of 37 clauses are not a success; 4 of the 5 storage-failure clauses show
  a Local gap, against 3 of 14 success clauses.
- **A behaviour rarely has one decision.** S20 (a Failed stream raises
  again) needs D16, D52, D93, D95, D117 and D151; S13 needs five.
- **The amendment graph does not find every deciding decision.** 16
  decisions the clauses cite lie outside the slice's `Amends:` closure
  (`check.py --pilot`, "deciding, outside the slice's Amends closure"): D1,
  D9, D27, D28, D33, D40, D41, D49, D71, D72, D94, D96, D118, D133, D138,
  D153. A citation graph is needed beside the amendment graph. Measured on the
  slice only.
- **Six behaviours are not decided:** S05 `read(0)` mid-stream (F1, partly),
  S16 a failure at the last byte (F10), S17 `chunks(0)` raised at the call or
  at `next()` (F5, partly), S19 a failed read delivers no bytes (F7, implied
  only), S32 a warning for an unclosed Exhausted or Failed stream (F3), S33 a
  stream when its handle's lifetime ends (`OP-01/O5`).
- **Four decisions state no behaviour** of their own (D2's shape, D100,
  D131, D149): they move where the record says something.

## 4. What the pilot asks of the facets

Three facets need a decision before the whole-record pass:

1. **Kind barely separates inside a lifetime.** 32 of 37 clauses are
   `lifetime`, as a stream's clauses should be; the facet will separate only
   across the record. Rule 2 also leaves a choice open: a failure response
   whose witness needs a World row (E8) may be `environment` ("a witness that
   needs a behaviour outside the library's control") or `lifetime` (the
   library's response to it, which is what a test checks). The pilot chose
   `lifetime`.
2. **Trigger names one World row for many.** E8 stands for any storage
   failure the library cannot mend; the whole record will need the row set
   (E7 to E13, E15 to E19) or a category per clause.
3. **State mixes single states and sets** (`not-Closed`, `any`); a clause per
   state would multiply clauses without new behaviour.

## 5. The whole record

The facets as decided on 2026-11-03 (`whole/SCHEMA.md`): kind with the trigger
apart, the trigger a set of Environment rows (a cancellation is E14), state
sets allowed and `none` for a call before any stream, status measuring the
behaviour (OP-01/O9's working names are a gap, not a partial decision), and
`content-failure` for a strict decode. Four groups by axis were classified in
parallel against that schema (`whole/a.toml` to `d.toml`); `check.py` then
covers all 156 decisions.

| Facet | Counts over 123 clauses (`check.py`) |
|---|---|
| Path | success 26, storage-failure 26, concurrent 23, caller-error 10, configuration 9, release 7, non-promise 7, cancellation 6, absent 4, end 2, content-failure 2, lifetime-end 1 |
| Form | stream 60, all three 48, text 5, whole 4, handle 3, whole and stream 3 |
| Scope | portable 98, a D43 variation point 21, one backend 4 |
| Kind | lifetime 56, single call 39, environment 11, function 11, structure 5, liveness 1 |
| Status | decided 116, open 3, partly 2, implied 2 |
| Trigger | an Environment row 66, the caller or the runtime 57 |

What the whole record adds to the pilot:

- **Thirteen clauses duplicated another file's and were dropped.** The same
  behaviour was classified from different deciding decisions in two files
  (A03 and X25, A06 and X05, A09 with C24 and X21, C08 with B18 and X11, C10
  to C13 with X10 and X17 to X19, A05 and X03, X04 and A04, X16 and B17); the
  survivor holds the union of both citations and triggers. The first merge
  found nine by a decided-by overlap of at least a half with the same path; a
  review found X21, and a second pass over every pair from two files sharing
  two deciding decisions and a scope (47 pairs, each read) found X21's pair
  again and three more. The other 43 pairs share only D34 and D96, the
  category and phase tables nearly every failure clause cites.
  A behaviour has no single home decision, so a spec written decision by
  decision would state these twice. One survivor's scope was corrected from
  the record: D62's metadata deviation sits in D43's Pinned resume point, not
  portable.
- **One more behaviour not decided:** C06, that an open descriptor keeps the
  old file across an O3 replace, is stated only in D25's reason, which D64
  limits to one host (`implied`).
- **Behaviours the record states only outside a Decision field:** D119's
  consistency check carries S3's outcome for E15 mid-stream (C10); D61, not
  D34's changed row, says a stream without resume fails unavailable for
  E1 to E5 (C08); D84 and D139 agree on S3 only through an inference the
  record never writes (a passing resume on an archived object still fails
  not readable).
- **Original wording a later decision contradicts**, read as amended: D12's
  check ("AX-13 bounds the call's total") against D97 and D128 (no total
  deadline); D4 calls E17's success path a failure, which D67 and D88 fix;
  D76 changes D43's normal value's wording while D110 calls it a
  restatement.
- **`environment` stays narrow:** 10 of its 11 clauses are a D43 variation
  point's deviation; C19 is the one portable assumption.

## 6. The not-decided behaviours, routed

Under RFC-0030 C1, two of the seven behaviours block a freeze, four are
notes for OP-01's spec flow, and one is an open item the record already
routes. The record is frozen and not edited here: a blocking finding waits
for a reopen, whose freeze takes the next number (C4), and BK-485's entry
names it. Each verdict was read from the decisions in the table.

| Clause | Behaviour | Verdict | Goes to | Deciding decisions |
|---|---|---|---|---|
| S05 | `read(0)` with bytes remaining | blocking: two things | a reopen | D6's Decision gives min(n, r), so `b''`, and says the bytes returned are "the whole content once `b''` is returned", so after `read(0)` a clause states that more bytes follow, or that none do. D155 settled the same question for `read1(0)` and an empty `readinto` and amends D78, D132 and D134 only, not D6 |
| S16 | a read at the last byte, the end not yet observed, meets a storage failure or a cancellation | blocking: nothing | a reopen | D18's Exhausted is "at end"; D132, D148 and D155 set that cell's values, none says when a stream enters it. A stream that learns the end from a read returning nothing makes that read a transfer, which D16 and D51 (Failed) or D20 and D50 (Closed) govern; a stream that knows the size returns `b''`. The record does not say which a caller observes |
| S17 | `chunks(0)` raises at the call, not at the first `next()` | note | the spec flow | D7 (a non-positive size is a caller error), D92 (argument checks first, in every state) and D117 ("`chunks(0)` on a Failed stream raises `ValueError`"): the call raises. A valid `chunks(n)` on a Closed or Failed stream raises at the call by D117 and D93's list |
| S19 | a failed data read delivers no bytes; `tell()` is unchanged | note | the spec flow | D72 (the read "returns its full count (D6) or fails"), D93 (`tell()` is the bytes delivered) and D16 (no bytes after a gap) admit one reading. Local breaks it through C8 (BUG-346) |
| S32 | an unclosed Exhausted or Failed stream warns when collected | note | the spec flow | D18: "dropping it unclosed releases it when collected (D17)" covers every state but Closed, and D17's adopted option releases with a `ResourceWarning`, as its source, CPython's file objects, does for any unclosed file |
| S33 | a stream once its handle's lifetime ends | routed | OP-21's flow | `OP-01/O5`, `shared: Lifetime`; D108 has it block only the clause for D18's last column |
| C06 | an open Local stream across a replace or delete on the same host delivers the old content | note | the spec flow's Local profile cell | D22 fails a read only when the backend can no longer serve the pinned content, D25 gives O3's E3 and E5 O2's rights, D64 limits the open descriptor to one host, D65 declares Windows' deviation. That a descriptor keeps the file is a backend fact: `local_pin.py`, Linux, Python 3.13.18, delivered all 16384 old bytes after `os.replace` and after `os.remove` |

S17, S19 and S32 were `partly`, `implied` and `open` in `pilot.toml`. Each
is a note because one reading of the deciding decisions fixes what a caller
observes; the spec flow writes that clause and cites the spike's F5, F7 or
F3. The classification files stay as classified.

## 7. Local's gaps at master, and the other `read()` chains

`conform.py` (freeze-1), rerun on master at `94a5bec` with Python 3.13.18,
one run of 400 examples per mode, reproduces C1 to C7: plain Local RF4, RF7,
Z1, S1; faults strict RF2, RF6, K1, K3, G1, Z2; faults protocol only RF2,
RF3, K1, K3, G1, Z2. T1, C8's rule, did not diverge in this run (two of
three in `rerun.md`). The faults are injected below the library
(`../bk-485-op01-stream-spike/report.md` § 5). The 0.33 line is frozen, so
none of these is filed as an item (the maintainer, 2026-11-04): each is
evidence for BK-485 step 5's 0.33 comparison, which cites this section.

`chains.py` runs each gap's call on `read()`'s other chains offline:
S3 boto3's real `_S3RangeReader` with a fake client, Azure's real
`_AzureBinaryIO` over a fake chunk iterator, and a seekable fake standing in
for SFTP's `SFTPFile`, each under its `_ErrorMappingStream` and
`io.BufferedReader`, faults injected in the fake.

| # | Local at master (rule: shortest trace) | Decisions | Clauses | S3 boto3, Azure, SFTP chains |
|---|---|---|---|---|
| C1 | a cancelled read leaves the stream open (RF2: `read(-1) !cancel`, then `readline() !cancel` raised the cancel, not `ValueError`) | D20, D50 | S27 | the same on all three: `KeyboardInterrupt`, stream not closed |
| C2 | Failed is not sticky (RF3: after `read(-1) !fail`, `read1(5)` returned 5 bytes) | D16, D51, D52, D93, D117 | S20 | S3 boto3 and SFTP the same, the next read reaching the raw stream; Azure below |
| C3 | an injected `OSError(EIO)` surfaces as `OSError` (RF6: `read(4) !fail`) | D27, D33, D34 (E13 disk I/O: the base category) | S18, S22 | an injected `OSError` is mapped on all three: S3 boto3's classifier gives `RemoteStoreError`, the stub mapper `BackendUnavailable`. Azure's own failure shape is not: azure-core's `ServiceResponseError` leaves `read()` unmapped (part 2), since `_AzureBinaryIO` converts nothing to `OSError` and Azure's wrapper has no `also_catch` (`_azure.py`'s `read()`) |
| C4 | `close()` raises a release failure (K3: `close() !release_fail`) | D36 | S24 | SFTP's chain: `close()` returns, the wrapper suppressing the failure; S3 boto3's and Azure's raw close cannot fail here, not run |
| C5 | `read(-2)` raises `ValueError` (RF4, RF7) | D6, D70 | S04 | `ValueError` on all three: CPython's `BufferedReader` |
| C6, C7 | `seekable()` is `True` (Z1), `seek(0)` returns 0 (S1) | D70, D93, D153 | S13, S14 | S3 boto3 and SFTP as Local; Azure already as decided, `False` and `io.UnsupportedOperation` |

C6 and C7 share one row: D70 decides both, and one cause, a seekable raw
file, produces both. The strict mode counts the injected `EIO` as unavailable,
the spike's E8 analogue; D34 types E13's disk I/O as the base category, so
C3 is the same gap either way: no library category. For the comparison's
reading of 0.33: SIO-001 disclaims seekability as a Store API contract, and
SIO-008 is the exception, a seekable `read()` stream on a backend that
declares `SEEKABLE_READ`, as Local, SFTP and S3 boto3 do (C6, C7); BE-021 promises that no native exception leaks, and SIO-012 maps only
the shapes a backend's wrapper catches (C3 and C4 on Local, and Azure's
`ServiceResponseError` mid-stream, below); no 0.33 clause speaks to C1, C2 or
C5.

**A gap on Azure.** `chains.py`'s second part runs azure-storage-blob
12.31.1's own `_ChunkIterator` under Azure's chain, its second chunk
download raising once (injected): that read raises, mapped for an `OSError`
and unmapped for azure-core 1.41.0's `ServiceResponseError`, which the
wrapper does not catch, and the next reads deliver the chunks after it: 16
of 20 bytes, not a prefix of the content, with no error. D16 and D51 make
that stream Failed, and D22 never delivers bytes after a gap; the unmapped
raise is against D27 and, in 0.33, BE-021, which Azure's caught set under
SIO-012 does not reach. The gap is the symptom BUG-346 records, bytes lost
after a mid-stream failure, by another mechanism BUG-346 does not cover: the
SDK's iterator has already taken the failed chunk's offset, so any failed
read, not only `readline`, is followed by reads past the gap. With 0.33
frozen it is recorded here only; a per-backend fix of BUG-346's `readline`
loss would leave it, and a Failed state that holds on every `read()` would
not. The first
part's Azure C2, `b''` after the failure, is its fake generator ending at
its raise, not the SDK.

## 8. Limits

The pilot had one author, the same who wrote the spike's rules; the whole
record's four groups had one each, normalised and deduplicated by the pilot's
author. The clauses are readings of the record, which governs. PR #1204's
second review checked the counts and the dropped ids against the files, not
each clause against the record. `local` is the spike's evidence, from Local with injected faults.
§ 6's verdicts have the same author; § 7's other chains use the real
wrappers and raw classes around fakes, with no network, and SFTP's
`SFTPFile` is a stand-in.
Derived from the record, so RFC-0029 R4 keeps it from BK-506's oracle
sessions.
