# RFC-0030: An `/observe` record closes out instead of waiting for a review that finds nothing

## Status

Accepted, 2026-11-02, by the maintainer. Tracked as **BK-505**, which it
decides. Amends [RFC-0029](rfc-0029-faithfulness-before-spec.md) R2: what a
freeze needs beyond R1's check. Amends [RFC-0028](rfc-0028-observe-record-review.md)
P3: a review's items may be decided by a close-out instead of a reopen.
Decisions taken in this RFC's session: decision log
`sdd/decisions/debeb3f4-b39e-4b2c-8a57-33040e9119ec.jsonl` ("Close-out rule"),
and, after the pull request's review, log
`sdd/decisions/07bd66b7-51b6-5a03-b47e-dc2fedeeeae7.jsonl` ("Fix the rule":
one question per blocking item, C2).

## Summary

**A review finding blocks a freeze only when it leaves what a caller
observes false, two-valued or undecided; a finding about the record's own
text goes to the spec flow. After a review, one close-out decides the
blocking items by the close-out's recommendation, adopted in one dialog, and
the record freezes after a check scoped to what the close-out wrote, not
another full review.**

## Motivation

R2 freezes a record only after `/observe-review` has re-run on it as its
last reopen left it, and leaves the stopping rule to BK-505. On OP-01 that
loop does not end. Each review round's open items, from the record's "were
found by" lines: `O27` to `O44` (18), `O47` to `O64` (18), `O65` to `O72`
(8), `O73` to `O83` (11), `O84` to `O91` (8). Each reopen answers them with
decisions that restate the text they amend (D114 to D133, then D134 to
D150), and the next round finds the restatements disagreeing: each of `O84`
to `O91` cites a decision the reopen before wrote, D134 to D150 (`O84` D150,
`O85` D138, `O86` D137, `O87` D134, `O88` D135 and D137, `O89` D138, `O90`
D138 and D146, `O91` D145, read from each item's text), and four (`O88` to
`O91`) change nothing a caller observes.

No measured stopping rule exists to replace "a round finds nothing".
[`research-observe-record-quality.md`](../research/research-observe-record-quality.md)
§ 3's rule needs seeded defects per kind of reviewer, unbuilt and
unvalidated; capture-recapture at two readers erred by about half (§ 2, A),
and on OP-01 its estimate of 0.2 items left was followed by four more.

## Proposal

### C1. Blocking findings and notes

A review finding **blocks** a freeze when, left as it is, a spec clause
written from the record would state, for some backend or the runtime,
something false, two things, or nothing about what a caller observes: a
conflict between decisions on a behaviour, a case no decision covers, a
decision a backend, SDK or runtime makes false.

Every other finding is a **note**: a restated list or count, a Decided-by
cell, a reason, provenance, a Decision's fidelity to its dialog, where the
deciding decisions fix the behaviour. A note is routed to the entry's spec
flow, which writes each clause once from the deciding decisions and cites
the note it settles; it blocks nothing. `/observe-review` writes a finding
that does not block as a note, whatever its kind, so an item's shape is its
tag: a reopen, ground conflict or gap blocks, a note does not.

### C2. The close-out

After an `/observe-review`, the maintainer may close the record out instead
of reopening it. One dialog adopts the close-out's recommended answers: one
question per blocking item, its answer shown (four questions per call), and
one routing every note (C1). Each blocking item is then written as a
decision in `axes.md`'s reopen form, its Asked line quoting its own
question, and the notes are routed by one decision. No other question is
asked. A close-out runs once per review; the maintainer reads its decisions
in the pull request that carries them, and a disagreement there is a reopen.
OP-01's first close-out, D151 to D156, predates the per-item questions: the
dialog that chose the close-out adopted them unseen, so each quotes it, and
the maintainer accepted them on the pull request that carried them.

### C3. The freeze after a close-out

A close-out is followed by a check of what it wrote, not a full review:
`observe-dialogs` and `observe-tables` over the whole record, and a re-read
of each close-out decision against every decision it cites or amends. A
record may fail both scripts already (OP-01's D1 to D44 have no Asked line;
BK-509's table findings), so the check is a comparison: it fails
([ADR-0045](../adrs/0045-close-on-a-check-that-can-fail.md)) on a FAIL for
a close-out decision, or on a FAIL or table finding that the same script,
run on the record as the review's commit left it (`git show
<commit>:<record>`), did not report, line numbers aside. A finding on the close-out's own text is
corrected before its commit, or routed if it is a note. The record is then frozen as R2 states
(each item decided or routed, each naming what it blocks; the tag after the
merge). R2's full re-run is required after a reopen, not after a
close-out.

### C4. What catches the rest

The spec flow and its compare step (R2's flow), and R4's trial on the frozen
record. A defect they find reopens the record, as R2 already provides; the
next freeze takes `n + 1`.

### C5. The research report's proposals

Not adopted: § 3's slots, claim register, double extraction and seeded
stopping rule are neither built nor validated. R1's table check stays the
one mechanical gate beside the dialog pairing. They are revisited when R4's
trial reports.

## Alternatives Considered

Decided in the log above:

- **Freeze now, every item routed:** the same rule, but the four blocking
  OP-01 items routed undecided to the spec, which would then answer
  behaviour questions with no recorded decision.
- **Keep R2 as written:** another reopen and another full review per round,
  with no rule that ends it.

## Impact

- **Process:** RFC-0029 and RFC-0028 carry an "Amended by RFC-0030" line.
  `/observe-review` writes a finding that does not block as a note (its
  rules) and states the close-out (step 6).
- **Backlog:** BK-505 is decided by this RFC. OP-01's first close-out is
  BK-485's.
- **Public API, testing:** none.

## References

- [RFC-0029](rfc-0029-faithfulness-before-spec.md) R2, [RFC-0028](rfc-0028-observe-record-review.md) P3.
- [`research-observe-record-quality.md`](../research/research-observe-record-quality.md) § 2, § 3.
- OP-01's [record](../observe/records/OP-01.md), its open items `O27` to `O91`.
- [ADR-0045](../adrs/0045-close-on-a-check-that-can-fail.md).
