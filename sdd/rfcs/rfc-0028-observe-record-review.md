# RFC-0028: An `/observe` record is checked before its spec

## Status

Draft, 2026-10-28. Tracked as **BK-499**. Amends
[RFC-0024](rfc-0024-spec-first-reset.md) D4, whose method is research
[§ 4](../research/research-spec-first-reset.md#4-the-design-method-working-name-observe),
and the flow of research
[§ 3](../research/research-spec-first-reset.md#3-the-flow-and-the-ground) with
step 5 of its [§ 9](../research/research-spec-first-reset.md#9-results-and-recommendation)
table: S4's End gains a whole-record pass (P1), and a review step joins the
flow between record and spec (P2, P3). Decisions taken in this RFC's session:
decision log `sdd/decisions/d32f7ee6-4e03-5d2b-8bc7-a4fd31fafb81.jsonl`.

## Summary

**A record leaves its session only after the session has re-checked it whole,
and reaches its spec only after a script, an unprimed reader and a primed
reviewer have checked it.** None of them decides: what they find becomes open
items in the record, and a reopen session decides them.

## Motivation

OP-01's record took thirteen open items after its session closed: `O14` to
`O16` from PR #1188's review, `O17` to `O26` from
[audit-025](../audits/audit-025-op-01-record-review.md). Audit-025 § 5 sorts
them into four classes, and nothing in the flow catches any of them:

1. A consistency check written once by the decision's author, naming a subset
   of the earlier decisions, and never re-run (C1, C2, G5).
2. Decision text that no dialog asked (`O14` to `O16`).
3. Backend, SDK and runtime behaviour, which S1 keeps out of the unprimed
   ground (C3 to C6).
4. Questions no axis raises (C7, G1 to G4).

## Proposal

### P1. The session's End re-checks the whole record

S4 is amended: a session ends when every axis is closed **and** a whole-record
pass has run. The pass re-runs each decision's consistency check against
every decision, later ones included, rather than the ones the check names:
every list, table or "only" claim against each decision that adds to it,
every reason against every outcome, and the option text a Decision adopts.
Each conflict is asked like any question, and its answer is a new decision
naming the one it amends. Class 1, inside the session, while the maintainer
is there to answer.

S5 is amended: each decision records an **Asked** line per dialog that
answered it, quoting the question's opening words and the answer. A claim in
the Decision that no dialog answered is asked first. Class 2, at the source.

### P2. The flow gains a review step between record and spec

Research § 3's flow becomes design, record, **review**, spec, compare; step 5
of § 9 runs it after the `/observe` session. `/observe-review <entry>` runs in
a fresh session after `/clear`, outside the hook's ground, in three parts:

- **Pairs** (class 2). `scripts/observe_dialogs.py` pairs every decision with
  its answered dialog in the session's decision logs. It fails a decision with
  no Asked line, a quote that starts no answered question or several, or an
  answer the log does not hold. Whether Decision text goes beyond its dialog
  is a judgement, so the script prints each pair, with the record's own text
  of each option the Decision adopts by label, for the readers.
- **Unprimed readers** (classes 1 and 2). Two fresh agents, whose findings
  are unioned, each read only the record, the pairs, the axes and the
  record's ground, with one fixed brief: decisions
  that cannot both hold, adopted option text included; claims of extent
  against every decision that adds a member; reasons another outcome makes
  false; Decision text its dialog does not cover. It is told nothing found
  before it ([ADR-0034](../adrs/0034-ship-panel-rounds-and-unprimed-exit.md)'s
  unprimed exit, applied to a record).
- **Primed review** (class 3). The session itself asks, per decision, whether
  a backend, its SDK or the Python runtime on a supported platform makes it
  false, two-valued or costly. Its ground: dependency source, Python and
  platform docs, vendor docs, and `src/remote_store/backends/` as evidence of
  what an SDK or the OS does, never as the expected answer, which keeps
  RFC-0024 § R1's rule that 0.33 is never ground for a decision.

### P3. What the review step may change

It never edits a decision, an Environment row or an axis's decided state,
and it decides nothing. Each finding that holds after a re-read becomes an
open item in the record, in the session's shapes (a reopen, a ground
conflict, a gap or a note), as audit-025 recorded `O17` to `O26`. The status
stays Complete, and a reopen session decides the items before the spec cites
the decisions they name.

### P4. Questions no axis raised

Class 4 is answered in the axes, not in a step: AX-1, AX-5 and AX-6 each gain
a question generalised from C7 and G1 to G4. F2's revision after the `read()`
flow still revisits the whole set.

## Evidence that the checks can fail

[ADR-0045](../adrs/0045-close-on-a-check-that-can-fail.md) asks of a check
offered as a close whether it could have come out the other way. The End
pass and the reader were run on OP-01's record at `c58ee74`, the commit
audit-025 read, without being told its findings; the reader's copy had
`O14` to `O16` removed and an Asked line per decision added. The primed
review was not run: it is audit-025's method, whose run is the audit.

| Target | End pass | Reader, run 1 | Reader, run 2 |
|---|---|---|---|
| C1 | missed | found | missed |
| C2 | judged consistent | missed | judged consistent |
| G5 | found | missed | missed |
| `O14`, `O15`, `O16` | — | found | found |

So the checks can fail, and did: no single run found C1 and G5, and none
found C2, which audit-025 itself carries as a note (`OP-01/O18`). Hence two
readers, unioned, beside the End pass; C2's class, an adopted option's
wording against an earlier decision, stays this step's known bound. Run 2
had the adopted option's text beside each Decision; run 1 did not. Every run
also raised candidates outside audit-025, listed unverified in the
[BK-499 trace](../traces/bk-499-observe-record-checks.yml) with the runs'
inputs.

## Alternatives Considered

Decided in the log above:

- **Class 1:** the End pass alone, which leaves the author re-reading what
  they are primed to skip; an unprimed reader alone, after the session,
  which turns every finding into a reopen; or a reader inside the session,
  which needs Agent admitted by the hook and a probe that subagent calls
  carry the parent's session id.
- **Class 2:** a reader pairing 44 decisions with their dialogs by hand; or a
  Decision split into the answer and a derived bullet, a check of form rather
  than content.
- **Class 3:** the same ground without 0.33's `src/`, which loses C3's
  evidence and audit-025 § 4's estimates; or an audit document per run, which
  splits the record's open items from the record.
- **Class 4:** one closing sweep instead of axis questions, which a session
  ticks without asking; or waiting for F2, which nothing orders before OP-02.

## Impact

- **Public API:** none.
- **Process:** `/observe` steps 3 and 5; a new skill `/observe-review`;
  `sdd/observe/axes.md`'s per-question shape and three questions; RFC-0024
  carries an "Amended by RFC-0028" line.
- **Testing:** `tests/scripts/test_observe_dialogs.py` pins the pairing and
  each way it fails; `tests/scripts/test_observe_ground.py` pins that
  `/observe-review` neither arms nor releases a session.
- **OP-01:** unchanged. Its D1 to D44 and its open items `O14` to `O26` stay
  as they are; deciding them is a separate session.

## Open Questions

None.

## References

- [RFC-0024](rfc-0024-spec-first-reset.md),
  [`research-spec-first-reset.md`](../research/research-spec-first-reset.md)
  §§ 3, 4 and 9.
- [Audit-025](../audits/audit-025-op-01-record-review.md) §§ 1 to 3 and 5.
- [ADR-0034](../adrs/0034-ship-panel-rounds-and-unprimed-exit.md),
  [ADR-0037](../adrs/0037-whole-file-gate-and-derived-figures.md),
  [ADR-0045](../adrs/0045-close-on-a-check-that-can-fail.md).
