# BK-489 — The frozen kernel line has no decision: revive it, rewrite it or drop it
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** [RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md)
D7, which makes this item the host of RFC-0024 D10 ("when, and whether, the
frozen kernel line is revived or rewritten") and of the open class P items of
RFC-0024 § R3 whose whole subject is the kernel, a driver, the `Session` or the
migration. The work is on the branch `frozen/kernel-driver` at `814c1f6`
(RFC-0025 D1): the kernel, both Memory drivers, `remote_store.drivers`, specs
052 and 053, `StoreTree.dfy`, `KernelProtocol.dfy` and `tests/_kernel/`. Its
completed entries are in
[`BACKLOG-DONE.md` § Frozen](../BACKLOG-DONE.md#frozen).

## Absorbed items

Each row is the item's index diagnosis as it stood when absorbed, shortened;
the dossiers stay where they are. Every row is `(was <ID>, absorbed here)`.

| ID | Diagnosis | Dossier |
|---|---|---|
| BK-390 | RFC-0017's spec amendments after D3 step 1 (specs 006, 008, 009, 026, 036, 044, the later drivers' half of 007 and 022, the per-backend specs) have no owner; each lands in its step's PR. | [bk-390](bk-390-rfc-0017-spec-amendments.md) |
| BK-439 | The kernel's flat `glob` neither `stat`s its literal prefix (BE-032 A.3) nor omits a match below a matched item; open: an ordering obligation for `glob`, or a buffered omission. | — |
| BK-446 | No driver exercises the kernel's `glob`: `MemoryDriver` declares no `GLOB`, so only the fake driver in `tests/_kernel/` runs it. | — |
| BK-455 | The `Session` has obligations in BE-033 (`invalidate`, cancel, `unwrap` through `run`, a `close` racing in-flight calls) but no state set, and its close/run race no model. | — |
| BK-434 | RFC-0021's encodings are verified in `StoreTree.dfy` alone; `BackendContract.dfy`'s operations never see an encoding, and the model drifts from the kernel (audit-023 T3, T12, T13, T14). Its drift findings on `BackendContract.dfy` are re-checked against the model master keeps (RFC-0025 D7). | [bk-434](bk-434-trait-refinement-against-storetree.md) |
| BK-450 | The driver boundary has no single enforcement point: keys and declarations unchecked (audit-023 T2, T9, T10), one stream fault mapped three ways (T4, T5), flags meaning different things per runtime (T6), checks owned by both `Store` and kernel (P6). Its T1 is BUG-341, kept on master. | [bk-450](bk-450-driver-boundary-enforcement.md) |
| BK-467 | Rule 4 cannot let the Dafny lifetime model (`KernelProtocol.dfy`) or kernel-cell marks govern a clause: `check_formal_trace.py` counts only `tests/backends/conformance/` marks. No Dafny lifetime model or BE-03x mark is left on master for Rule 4 to admit. | — |
| BK-435 | Spec 051's store tree is not tied to the store's operations: `StoreTree.dfy` §12 carries no `@spec` tags, and research § 10 step 3's Dafny operations wait on BK-434. Its open work is on `StoreTree.dfy`, parked with that model. | — |

**BK-450's record.** The decision log
`sdd/decisions/062e5181-cc50-5b17-963f-e9da78bad8ee.jsonl` holds the
constraint the maintainer filed on BK-450 from PR #1159's review: a stream's
close-failure rule must not swallow an integrity failure (its dossier, the
stream-adapter part).

## Split in from BK-452

BK-452's flat reference driver (audit-023 P4): both Memory drivers are
hierarchical, so flat decoding, the `list_page` byte-order obligation, BE-032
A.3's shadow omission and A.4's ancestor checks run only against the kernel's
test fake. Open: the reference set's members and the cells each runs.
BK-452 keeps Memory's pins on master
([its dossier](bk-452-template-reference-set.md)).

## Candidate breaks for their operations' flows (RFC-0025 D2, RFC-0024 § R5)

Both are **Breaking**, shipped on the kernel line and frozen with it; their
done entries are in [`BACKLOG-DONE.md` § Frozen](../BACKLOG-DONE.md#frozen).
Each returns through the flow of its operation as a candidate break record, not
through this item's decision.

| ID | Break | Flow | Dossier |
|---|---|---|---|
| BK-405 | `glob` reads a pattern as a path: a leading `/`, `//` and `.` mean the canonical spelling, `..` or a null byte is `InvalidPath`. The tier split it fixed is back on master. | `glob()` | [bk-405](bk-405-ext-glob-fallback-tier-split.md) |
| BUG-329 | `metadata` must be `None` or a `Mapping`, else `ValueError` before any I/O. | `write()` | — |

## Parked pull requests

PR #1172 (BK-456 stage three, branch `bk-456-prune-052`) is parked as a draft
with the frozen line, revisited with D10; it answers RFC-0025 Open Question 2.
Its base is #1170's branch, so it retargets to master if #1170 merges.

## Kernel-only finding: BK-448

BK-448 (the async kernel leaves a caller's content iterator suspended when it
refuses a chunk or the write fails) was absorbed into BK-449, which closed it
on the kernel; BK-449 is frozen. v0.33.0 has no kernel content proxy, so the
finding exists only on the frozen line
([BK-449's dossier](bk-449-interaction-protocol-states.md)).
