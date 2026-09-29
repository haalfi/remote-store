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

**What it owes, placed as the OQ7 answer states:**

| Clause | Where | Shape (D7's table) |
|---|---|---|
| Root rule, BE-029 | a pure predicate over the key in an included lemma module of `DepthCounting.dfy`'s shape (`include "BackendContract.dfy"`), with its preconditions on the trait's write-shaped operations | S |
| Close posture, BE-020 | a `closed` flag and a postcondition per operation, in `BackendContract.dfy` and the `MemoryBackend.dfy` refinement | S |
| Absent container, BE-021 § Reach | the store state becomes optional and the postconditions gain a branch, in both files | M |

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
- the root rule's lemma module verifies, and its preconditions on the trait
  hold in `MemoryBackend.dfy`;
- the twin-parity check is green with the new members;
- each new postcondition carries its `@spec` tag, so `check_formal_trace.py`
  lists it.
