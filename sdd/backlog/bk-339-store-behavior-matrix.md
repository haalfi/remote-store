# BK-339 — Decide what replaces `store.md`'s hand-maintained Backend Behavior Matrix
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 3](../BACKLOG.md#users-succeed-unaided) by the ADR-0040 § 3
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`docs-src/reference/api/store.md` § Backend Behavior Matrix hand-maintains five
behavioural rows across ten backends, and carries the line *"Verify against
actual code before relying on these in production"* — a reference page telling
readers not to trust it, which is the admission that it drifts. Users read this
table to choose a backend.
**One measured error, not a suspicion.** The `copy()` preserves metadata` row
says `—` for Memory, but `MemoryBackend.copy` constructs the destination with
`metadata=src_node.metadata` (`src/remote_store/backends/_memory.py`), so user
metadata survives a copy. The row is also **ambiguous in a way that hides the
error**: Local's cell reads "Yes (`copy2`)", which is filesystem metadata,
while Memory's concerns user metadata — one row conflating two different
properties, which is why a reader cannot tell a wrong cell from an
out-of-scope one. Fixing the cell without splitting the row re-hides it.
**The disposition is the work.** Rows divide three ways: derivable from
capability declarations (`Native glob()` duplicates the capabilities matrix's
GLOB row — the two currently agree, so this is duplication rather than
contradiction); genuinely useful user information available nowhere else
(`move()` atomicity, `write_atomic()` mechanism); and under-specified
(`list_files()` ordering, which the specs do not guarantee — publishing
per-backend orderings invites reliance on an unguaranteed property). Deleting
outright would remove real value; deriving needs declarations that do not exist
for the middle group.
**Check `capabilities-matrix.md` at the same time** — it is the neighbouring
ten-backend table and a candidate home for the derivable rows, but whether it
is generated or hand-maintained was not established.

**RFC-0017 D3 placement (BK-394, 2026-10-15).** RFC-0017 § Impact assigned this item's re-homing to BK-394, at D3 step 1. Placement: no step absorbs it; the rows it decides on are Store behaviour, unchanged by a class moving onto the kernel.

*Frozen 2026-10-25: [RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md) froze RFC-0017's D3 steps on `frozen/kernel-driver`, so the placement above no longer applies; the item stands as framed.*
