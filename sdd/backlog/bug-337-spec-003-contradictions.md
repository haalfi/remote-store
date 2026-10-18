# BUG-337 — Spec 003 contradicts itself on a move onto an existing file and on the write precondition order
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** A read of spec 003 against RFC-0022 for a
maintainer summary, 2026-10-18 (BK-457's work, PR #1160). An agent flagged
five contradictions; the four below were confirmed by reading the lines named,
the fifth was not one (below).

**Evidence, line numbers at master `32a5653`.**

1. **Move or copy onto an existing file.** `sdd/specs/003-backend-adapter-contract.md`
   line 737 (BE-021 table): "Directory operation (e.g. `delete_folder`,
   `move`/`copy` dst) on a path that is a file | `InvalidPath`". Line 669
   (BE-018): "`AlreadyExists` if `dst` names an existing file, `overwrite=False`".
   Line 1817 (BE-032 A.5): an `Item` under write-file is "replaced, or
   `AlreadyExists` without `overwrite`". `sdd/formal/BackendContract.dfy` line
   1154 (`@spec BE-018`): `IsFile(old(fs), dst) && !overwrite && src != dst ==>
   r == Err(AlreadyExists(dst, name))`. The verified model and two sections agree;
   BE-021's row is the odd one out.
2. **BE-008's order is incomplete.** Lines 445 to 452 number the order (0) root,
   (1) path validity, (2) overwrite conflict, (3) I/O, and add "No later check
   may mask an earlier one". The same section's Formal coverage, lines 536 to
   543, puts the closed guard (BE-020) and the WR-010 metadata gate before
   path validity, as `BackendContract.dfy`'s `Write` does.
3. **BE-010 drops the root step.** Line 570: "Same as BE-008 — path validity
   (type conflict) → overwrite conflict → I/O", without BE-008's step (0),
   which line 456 calls "the one step no backend is exempt from".
4. **BE-018's destination-directory rule is unqualified.** Line 669 raises
   `InvalidPath` "if `dst` names an existing directory" for every backend;
   BE-021, lines 745 to 753, binds the destination half to hierarchical
   backends only, off the kernel.

**Not a contradiction.** BE-028 (line 1364) says `LocalBackend` is
"serialised by the kernel" while A.7 (line 1841) says Local is not yet on the
contract kernel. "Kernel" in BE-028 is the operating-system kernel serialising
`os` calls. It is a wording hazard in a spec where "the kernel" is a defined
term, not a disagreement.

**Prescription** (advisory):

- Item 1: BE-021's row names the destination case it means (an ancestor of
  `dst` that is a file, `InvalidPath`), or drops `move`/`copy` dst; BE-018 and
  the model stand.
- Items 2 and 3: state the order once, in BE-008, with the closed guard and
  the WR-010 gate, as the model has it; BE-010 and BE-018 link to it instead
  of restating it.
- Item 4: BE-018 adds BE-021's binding, or links to it.
- Reword "serialised by the kernel" to "serialised by the operating system".
- Bug-fix protocol (`000-process.md` Rule 6): a failing test first where a
  conformance cell can witness the corrected row; the spec-only fixes need no
  CHANGELOG entry (audience `library.maintainer`).
