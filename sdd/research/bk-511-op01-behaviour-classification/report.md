# Research: OP-01's behaviours classified, pilot on the stream lifecycle (BK-511)

<!-- doc: repo-only -->

**Date:** 2026-11-03
**Backlog items:** BK-511, BK-485
**Status:** Pilot complete; the whole-record pass waits on § 4's facet
decisions. A point-in-time snapshot of the record tagged
`observe/OP-01/freeze-1` (`a7de4e31`).

---

## 1. Question and answer

Can OP-01's decisions, which mix happy and unhappy paths, read forms, sync and
async, and backends, be split into one entry per observable behaviour and
classified along fixed facets before spec work? On the stream lifecycle, yes:
45 decisions become 37 behaviour clauses, each checkable against a vocabulary,
covering every decision and every rule of the spike's freeze-1 oracle. The
split also shows what a decision-level reading hides: one behaviour needs up
to six decisions, five deciding decisions are reachable by citation only, and
six behaviours are not decided.

## 2. Method

- **Unit:** a behaviour clause, given (pre-state), when (call or trigger),
  then (outcome), stated as it holds after every amendment (`pilot.toml`).
- **Facets:** the record's axis; path and trigger; form, sync or async and
  stream state; backend scope; SPEC-DESIGN Rule 2's kind; status (decided,
  partly, implied, open); and two pieces of evidence: the spike's freeze-1
  rule and what 0.33 Local was observed to do (the spike's C1 to C8).
- **Pilot set:** the slice (D2, D6, D7, D15 to D18, D20, D36), every
  transitive amender of it from the record's `Amends:` lines (`effective.py`),
  and five decisions that decide it without an amendment reaching it.
- **Check:** `check_pilot.py` fails on a value outside a facet's vocabulary,
  a pilot decision no clause cites (and no `record_text` entry explains), or a
  freeze-1 rule no clause maps. It failed once while the pilot was written:
  rule G1 (collecting a Closed stream warns nothing) had no clause, now S37.

## 3. Results

From `check_pilot.py` on the frozen record.

| Facet | Counts over 37 clauses |
|---|---|
| Path | success 14, release 7, storage-failure 5, caller-error 3, cancellation 3, end 2, non-promise 2, lifetime-end 1 |
| Trigger | O1 25, a World row 5, Runtime 3, GC 3, O2 1 |
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
- **The amendment graph does not find every deciding decision.** D49, D94,
  D96, D118 and D138 decide the cancelled close and the failure phases with
  no `Amends:` line reaching the slice; eleven more decisions outside the
  closure are cited by clauses (D1, D9, D27, D28, D33, D40, D41, D71, D72,
  D133, D153). A citation graph is needed beside the amendment graph.
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

## 5. Limits

One author classified, the same who wrote the spike's rules; the clauses are
readings of the record, which governs. The pilot covers one slice of one
record: whole reads, text, concurrency (AX-8, AX-9) and the profile table are
untried. `local` is the spike's evidence, from Local with injected faults.
Derived from the record, so RFC-0029 R4 keeps it from BK-506's oracle
sessions.
