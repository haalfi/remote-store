# Research: OP-01's behaviours classified, pilot on the stream lifecycle (BK-511)

<!-- doc: repo-only -->

**Date:** 2026-11-03
**Backlog items:** BK-511, BK-485
**Status:** Pilot and whole-record pass complete; routing the not-decided
behaviours and filing Local's gaps follow. A point-in-time snapshot of the record tagged
`observe/OP-01/freeze-1` (`a7de4e31`).

---

## 1. Question and answer

Can OP-01's decisions, which mix happy and unhappy paths, read forms, sync and
async, and backends, be split into one entry per observable behaviour and
classified along fixed facets before spec work? On the stream lifecycle, yes:
45 decisions become 37 behaviour clauses, each checkable against a vocabulary,
covering every decision and every rule of the spike's freeze-1 oracle. The
split also shows what a decision-level reading hides: one behaviour needs up
to six decisions, 16 of the decisions the slice's clauses cite lie outside its
`Amends:` closure, and six behaviours are not decided. The whole record (§ 5) gives 127 clauses and
32 decisions with no behaviour of their own; 101 clauses are not a success
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
applied. The pilot as first classified (`596e79d87`) differs in three
fields only (a field-by-field comparison of the two `pilot.toml`): the
trigger of 9 clauses (S16, S18, S19, S22 read `E8`, now D96's stream-read
rows; S24 `E8`, now E8 and E13; S27 to S29 `Runtime`, now E14; S30 `O2`,
now E1 and E2), the state of S01 and S02 (`open-call`, now `none`), and S33's
gap (none, now `OP-01/O5`). Those first counts drove § 4.

| Facet | Counts over 37 clauses |
|---|---|
| Path | success 14, release 7, storage-failure 5, caller-error 3, cancellation 3, end 2, non-promise 2, lifetime-end 1 |
| Trigger | the caller or the runtime 28, an Environment row 9 |
| Form, api | stream 37; both forms 34, async only 3 |
| Scope | portable 35; a D43 variation point 2 (Cancelled close, Overlapping mutation) |
| Kind | lifetime 32, single call 3, environment 1, structure 1 |
| Status | decided 31, partly 2, implied 1, open 3 |
| Local | pass 16, untested 10, not offered 1, a gap 10 (C1 to C8) |

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

| Facet | Counts over 127 clauses (`check.py`) |
|---|---|
| Path | success 26, storage-failure 26, concurrent 25, caller-error 10, configuration 9, release 7, non-promise 7, cancellation 6, absent 6, end 2, content-failure 2, lifetime-end 1 |
| Form | stream 61, all three 51, text 5, whole 4, handle 3, whole and stream 3 |
| Scope | portable 101, a D43 variation point 22, one backend 4 |
| Kind | lifetime 57, single call 41, environment 12, function 11, structure 5, liveness 1 |
| Status | decided 120, open 3, partly 2, implied 2 |
| Trigger | an Environment row 66, the caller or the runtime 61 |

What the whole record adds to the pilot:

- **Nine clauses duplicated another group's and were dropped** (the `DROP`
  set of the merge, nine ids). The same behaviour was
  classified from different deciding decisions in two groups (A03 and X25,
  A06 and X05, A09 and C24, C08 with B18 and X11, C10 to C13 with X10 and
  X17 to X19); the survivor holds the union of both citations and triggers.
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
- **`environment` stays narrow:** 11 of its 12 clauses are a D43 variation
  point's deviation; C19 is the one portable assumption.

## 6. Limits

The pilot had one author, the same who wrote the spike's rules; the whole
record's four groups had one each, normalised and deduplicated by the pilot's
author. The clauses are readings of the record, which governs; no second
reader has checked them. `local` is the spike's evidence, from Local with injected faults.
Derived from the record, so RFC-0029 R4 keeps it from BK-506's oracle
sessions.
