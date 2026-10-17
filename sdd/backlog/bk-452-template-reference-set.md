# BK-452 — The template is Memory alone: no flat reference driver, unpinned Memory clauses, a stale checklist
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** [Audit 023](../audits/audit-023-kernel-migration-readiness.md),
proposal P4 and findings T17, T18 and T19, at `52448e0`.

**Parts** (advisory; untracked sub-bullets, no IDs):

- **A flat reference driver** (P4). Both Memory drivers are hierarchical with
  implicit parents (`backends/_memory.py:43-44`, `aio/backends/_memory.py:39-40`)
  and hold the tree directly, so flat decoding, the `list_page` byte-order
  obligation, A.3's shadow omission and `stat`, and A.4's ancestor checks run
  only against the kernel's test fake (`tests/_kernel/_cells.py`, shape
  `flat-none`). Decide the reference set's members and the kernel and
  conformance cells each runs. Due before D3 step 2, whose S3 is the first flat
  driver.
- **Memory's pins** (T18, T19's test half). The counter clauses (MEM-004,
  MEM-014, MEM-016, MEM-016b) have no assertion after a `delete`, a
  `delete_folder` or a replacing move or copy, and MEM-016 and MEM-016b misstate
  the overwrite case; the mtime clauses (MEM-015, MEM-016, MEM-016b) are
  asserted only as `is not None`. A counters-against-walk invariant in the
  stateful property test, mtime pins, both runtimes. Due before step 8.
- **CONTRIBUTING's checklist** (T17). Its intro (`CONTRIBUTING.md:84-85`) and
  step 2 (`:88`) send new backends to the `Backend` ABC; the guide calls a
  driver the documented route. Rewrite both as a driver plus a `DriverBackend`
  subclass; step 3 (the fixture) stays. Due before step 8.

T19's model half (the Dafny copy setting `last_modified` to `None`) is BK-434's.

**Overlaps:** BK-446 (Memory presents `SupportsGlob`) is P4's glob member and
stays its own item; BK-450's decode step and declaration record are what the
flat reference driver is checked against.
