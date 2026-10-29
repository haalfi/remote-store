# RFC-0029: A record is checked and frozen before its spec, and the first one tests whether its own oracles add anything

## Status

Accepted, 2026-10-29, by the maintainer. Drafted 2026-10-29. Tracked as
**BK-503**. Amends [RFC-0024](rfc-0024-spec-first-reset.md) § 9 steps 5 and 6
of [`research-spec-first-reset.md`](../research/research-spec-first-reset.md#9-results-and-recommendation),
as [RFC-0028](rfc-0028-observe-record-review.md) left them: step 5 gains a
table check on the record and a freeze before its spec (R1, R2), its reference
model gains two test rules (R3), and step 6 runs a trial before its bake-off
(R4, R5). Background: [`research-spec-faithfulness.md`](../research/research-spec-faithfulness.md).
Decisions taken in this RFC's session: decision log
`sdd/decisions/7d282f9d-8eb6-48be-8d6c-9fc7641121cf.jsonl`.

## Summary

**A record reaches its spec only once a table check has run on it and its
open items are decided or explicitly scoped out, at a commit hash that fixes
it. OP-01's frozen record is then also the subject of a single-rater pilot
trial measuring whether oracles derived from the record catch spec
misreadings that every spec-derived check misses, before step 6's bake-off.**
Nothing here gates on that claim until the trial reports.

## Motivation

[`research-spec-faithfulness.md`](../research/research-spec-faithfulness.md)
§ 2 found no published pipeline from prose records to spec, models and
reference model with faithfulness gates, and no measurement of the claim the
step-5 flow rests on: that checking against the record, not only against the
spec, catches what the spec got wrong. RFC-0024 step 5 builds the reference
model "fresh from the spec", so every oracle it carries inherits the spec's
reading.

Three gaps follow, each shown on OP-01 (research § 3):

1. **The record itself carries the failure modes.** OP-01's review found
   decision text no dialog asked, tables in one decision that another
   contradicts, and a consistency check that passed and was wrong. RFC-0028's
   readers found them by judgement; no mechanical check looks at the record's
   tables.
2. **No state says a record is ready for its spec.** OP-01 is Complete, yet
   many of its open items block a spec clause (`OP-01/O14` blocks "the spec
   clause for a stream read's failures"), and BK-501's reopen can leave a
   ground conflict routed and open.
3. **Step 6 scores its bake-off on mutants killed by oracles nobody has
   checked against the record.**

## Proposal

### R1. The record's tables are checked before its reopen

`/observe-review` gains a deterministic check (G3) over the record's tables:
each case table complete and disjoint over its declared domain (D9's
partition, D34's categories), each state table with a cell per state and
event (D18), and each row a decision cites present in it. A finding becomes
an open item, as RFC-0028 P3 has the step's other findings. The same script
checks the spec's tables when the spec exists. BK-504 builds it and runs it
on OP-01 before the reopen, recording what it found and whether it could
have found nothing ([ADR-0045](../adrs/0045-close-on-a-check-that-can-fail.md)).

### R2. A record is frozen before its spec

Step 5's flow becomes design, record, review, **reopen, freeze**, spec,
compare. A record is **frozen** at the commit where each of its open items is
either decided (`Decided by`), or of a kind no reopen of this record decides,
each named with what it blocks:

- routed to a ground artifact's flow and awaiting `Flow done` (BK-501,
  `axes.md` § Per-question loop), such as `OP-01/O21`;
- for another entry's session, or tagged `shared:`.

A spec clause blocked by such an item is not written until the item is
decided. The freeze is that commit's hash, named in the record's Session
section; a later reopen ends it, and the spec then cites the amending
decisions. RFC-0024 R1 holds: no freeze settles ground on the side.

### R3. Two test rules bind every v1 reference model now

- **Membership, not equality, where a clause leaves the outcome open.** An
  assertion on a value the record leaves unspecified, not promised or
  profile-declared checks that the value is in the allowed set, never that it
  equals the one value the reference model happens to produce.
- **A relaxed comparison is also run unrelaxed.** Wherever a test weakens a
  comparison (a projection, a "has failed" flag, a tolerance), the same run
  also compares strictly and reports the difference, so the relaxation cannot
  hide a defect.

Held until the trial reports (R4): wheat and chaff screening as a gate (G2),
the per-family kill as a gate (G8), and any LLM judge as a gate. G0's typed
non-commitment lint waits for the format RFC, which owns F3's terms
(RFC-0024 § R4).

### R4. OP-01's frozen record is the subject of a faithfulness trial

**The claim.** Oracles written from the record alone (E) catch seeded spec
misreadings that every check never consulting the record (S⁺) misses.

**The design** is the research's trial protocol (research § 2.3), at its core
tier, with these choices:

| Point | Choice |
|---|---|
| Pipeline | A only; B and C′ later as descriptive extensions |
| Raters | One, the maintainer: a single-rater pilot. Every label-dependent measure (realism rating, judge precision, register auto-labels) is reported as unvalidated |
| Toolchain | The reference model and its gates in Python (Hypothesis state machine, runtime contracts, CrossHair advisory only); history checks by Porcupine in Docker, as `scripts/dafny_verify.sh` runs Dafny. The Dafny and TLA+ layers stay under `SPEC-DESIGN.md`, outside the trial |
| Home | `sdd/research/bk-506-faithfulness-trial/`: harness, seeds, labels, analysis scripts and the pre-registration, every script committed, none scratchpad-only |
| Order | Stage 0, a dry run on a toy operation that claims nothing and replaces the protocol's unsourced cost assumptions with measured hours, minutes per label and tokens; then the pre-registration commit; then the run on the frozen record |

**Information flow.** Every session writing E runs under a read scope that
admits the frozen record and its ground and nothing derived from it, enforced
as `/observe`'s hook enforces its ground. That makes the repository's own
OP-01 spec, written in parallel after the freeze (R2), invisible to it.

**Not done:** the verified edition's 10 to 20 seed variant, which can neither
support nor refute the claim; auto-classifying a surviving mutant that maps to
the non-promise register as intended, which would hide a wrongly typed
non-commitment; counting two sessions of one model provider as independent
lineages.

### R5. Step 6 runs the trial first

Step 6 becomes: the trial (R4), then the bake-off as research § 9 states it,
on the same frozen record and scored with the trial's harness, mutants and
validated E oracles, then the format RFC with both results in hand.

## Alternatives Considered

Decided in the log above:

- **Next step after OP-01's record:** reopen OP-01 first and leave the process
  open; write a records-only check set now, before any RFC; or write the spec
  as step 5 stands, which gives up a spec-blind check set for OP-01.
- **Scope:** the same RFC under BK-485 with no new item; or the ordering and
  gates only, with the trial's decisions in a second RFC after Stage 0.
- **The spec against the trial:** the spec only after the trial reports,
  which holds spec work for the trial's whole run; or clauses no open item
  blocks now, before any record-derived check set exists.
- **Step 6:** the bake-off first, scored on unvalidated oracles; or one run
  varying form and oracle source together, two factors at n = 60.
- **Tier:** all three pipelines, which n = 60 cannot rank; or Stage 0 only,
  the tier left to an amendment.
- **Toolchain:** pure Python, with a young, unbenchmarked history checker; or
  the repository's Dafny-to-Python path as literal Pipeline C, larger and
  exposed to back-end soundness bugs.
- **Record checks:** a research brief first, holding the reopen; or a manual
  pass on OP-01 with no check for the next record.
- **Adopted now:** also G0's typed lint, ahead of the format RFC; or also G4a
  per edit, an SMT encoding of an unsettled spec.
- **Raters:** an external second rater; or the question left open, blocking
  the pre-registration.
- **Home:** a top-level `trials/` folder; or the harness under `tests/`.
- **Status:** Proposed, leaving step 5's order unbinding meanwhile.

## Impact

- **Public API:** none.
- **Process:** RFC-0024 carries an "Amended by RFC-0029" line. `/observe-review`
  gains R1's check (BK-504). Step 5's freeze (R2) is written into the
  `/observe` and `/observe-review` skills by BK-504, which first touches them.
- **Backlog:** BK-504 (R1's check, run on OP-01), BK-505 (a research brief on
  record completeness and consistency, RFC-0028 and R1's check as its
  baseline, started without waiting for BK-504),
  BK-506 (R4's trial: Stage 0, pre-registration, run). OP-01's reopen is
  BK-501's tool under BK-485.
- **Testing:** none now; R3 binds the first v1 reference model, OP-01's.
- **Cost:** the protocol's own estimate rests on assumptions it labels
  unsourced; Stage 0 measures the cost before the pre-registration commits to
  it.

## Open Questions

1. **Lineages.** The protocol wants four model providers in distinct roles
   (spec writer, E author, seeder, judge). Which are available is decided in
   the pre-registration (BK-506); with fewer, each shared role is reported as
   such.

## References

- [`research-spec-faithfulness.md`](../research/research-spec-faithfulness.md)
  and its reports in `haalfi/research` at `fc762e6`.
- [RFC-0024](rfc-0024-spec-first-reset.md), [RFC-0028](rfc-0028-observe-record-review.md),
  [`research-spec-first-reset.md`](../research/research-spec-first-reset.md) § 9.
- [`sdd/observe/axes.md`](../observe/axes.md) § Per-question loop, OP-01's
  [record](../observe/records/OP-01.md).
- [ADR-0045](../adrs/0045-close-on-a-check-that-can-fail.md).
