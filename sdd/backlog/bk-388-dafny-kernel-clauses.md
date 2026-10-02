# BK-388 — The Dafny model lacks the root rule, the close posture and the absent container that RFC-0017's kernel encodes
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** Minted by BK-387 when RFC-0017's Open Question 7
was answered "extend all three"
([ADR-0042](../adrs/0042-contract-kernel-over-thin-drivers.md), Proposed).
RFC-0017 D7 carries the reasoning and the table; not restated here.

**Reach.** Of RFC-0017's 10 R1 (kernel-owned) items, D7 counts eight on clauses the
model omits. This item covers six of them: the root rule for BUG-259, 247,
254 and 260, and the absent container for BUG-246 and 243. The other two,
BUG-249 and 280, breach the never-leak invariant on listings, which D7 leaves
unmodelled, as it does the first-page bound. The close posture carries no R1
item; it is in scope because the kernel encodes it.

**What it owes, placed as the OQ7 answer states** (the root rule's placement
as the maintainer corrected it at BK-387's close):

| Clause | Where | Shape (D7's table) |
|---|---|---|
| Root rule, BE-029 | a pure predicate over the key upstream of the trait, in `BackendContract.dfy` or a file it includes the way it includes `ResourceSafety.dfy`, named by the trait's write-shaped preconditions; lemmas about it in a downstream module of `DepthCounting.dfy`'s shape (`include "BackendContract.dfy"`) | S |
| Close posture, BE-020 | a `closed` flag and a postcondition per operation, in `BackendContract.dfy` and the `MemoryBackend.dfy` refinement | S |
| Absent container, BE-021 § Reach | the store state becomes optional and the postconditions gain a branch, in both files | M |

**As landed (BK-388's PR).** The root rule is a *postcondition*, not a
precondition as the table's Root rule row prescribes: a precondition cannot
rank the closed guard ahead of it, as BE-029 requires, and it would stop the
contract certifying the oracle's `Write(".")` answer in the root-write
conformance cells. It ranks after the closed guard and ahead of every
observed check, and both refusals leave `fs` unchanged. The predicate sits
in `BackendContract.dfy` §5c and its lemmas in `RootPath.dfy`. The absent
container is a `containerPresent` flag that `Valid()` ties to `EmptyStore`,
not an optional store. `sdd/formal/README.md` gaps 9 to 11 record the
result.

PR review then closed three gaps in that first landing. First, `Valid()`
keeps `Root` a `DirEntry`, because a `DeleteFolder(Root)` the trait mandated
could otherwise remove it for good. Second, the trait's well-formed domain
holds a single root spelling, so `RootPath.dfy` §5 adds a raw-key entry
that folds every spelling of a write or `move`/`copy` destination onto
`Root`. Third, `Close()` no longer frames
`fs`, because BE-020 does not promise that contents survive a close.

**Spec change it forced.** Review found the model refusing a root
`move`/`copy` destination ahead of src-NotFound, which BE-018 § Precondition
order forbade. Every backend measured already takes the model's order
(`MemoryBackend`, `AsyncMemoryBackend`, `LocalBackend` on both root spellings;
`SFTPBackend` by its own test), so the maintainer amended BE-018 (BE-019 and
ASYNC-018/019 by reference) with a root-destination carve-out rather than
reorder the model, under `sdd/000-process.md` Rule 7. The conformance cell
`test_root_destination_outranks_a_missing_source`, sync and async, pins it.
The trace records the measurement.

**Gates.** `verify-formal` (a required CI job that runs only when
`sdd/formal` or `sdd/specs` change, `ci.yml`'s `FORMAL_PAT`) and
`check_dafny_twin_parity.py`, whose output at `0bf7fe6` is "17 member(s) in
lockstep, 2 declared divergence(s)"; new members are added on both sides.

**Ordering.** Lands before BK-389, because the kernel encodes one answer per
clause and a postcondition written afterwards would only ratify it (RFC-0017
D7). It also gives BK-345 and ID-244 the verified reference they lack.

**Exit criteria**, per row of the table:

- the close posture and the absent container verify in `BackendContract.dfy`
  and `MemoryBackend.dfy`;
- the root rule verifies in all three places: its predicate and the trait's
  preconditions in `BackendContract.dfy` (or the file it includes), their
  discharge in `MemoryBackend.dfy`, and the downstream lemma module;
- the twin-parity check is green with the new members;
- each new postcondition carries its `@spec` tag, so `check_formal_trace.py`
  lists it.

## Correction (2026-10-02, BK-389 planning PR)

The root rule's exit criterion above still reads "the trait's preconditions".
As landed (§ As landed) they are postconditions ranked after the closed guard,
and the criterion is read that way: its predicate in `BackendContract.dfy`
§5c and the trait's postconditions in its §6, their discharge in
`MemoryBackend.dfy`, and the lemmas in `RootPath.dfy`. Found by the read-only
audit of master `9caef6b` that preceded BK-389's split.
