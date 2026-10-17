# BK-434 — RFC-0021's encodings are verified in `StoreTree.dfy` alone, so the trait's operations are not refined against them
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** Filed by BK-432 (RFC-0021 D10 names the wiring as a
follow-up). This dossier was added when [audit 023](../audits/audit-023-kernel-migration-readiness.md)
(proposal P3, at `52448e0`) widened the scope.

**Original scope.** `StoreTree.dfy` proves a flat encoding's `decode` and
RFC-0021's refusal rule (A.8) on its own types; `BackendContract.dfy`'s
operations still range over `map<Path, Entry>` and never see an encoding. Open
decision: refinement lemmas per encoding, or one encoding-parametric trait.

**Added by audit-023 P3** (advisory; untracked sub-bullets, no IDs):

- **The model's role.** Triage recommended that the formal model gate driver
  acceptance; the refinement is what makes that sound. If it is to gate D3
  step 2's own acceptance, this item moves before step 2.
- **Drift the refinement must remove:** `ListFolders` lists every nested folder
  (T3, `IsChildOf` any depth, BE-015 says immediate); `Move` and `Copy` answer
  `BackendUnavailable` ahead of the kernel's capability gate (T12's model half);
  no `Canonical` guard outside `DeleteFolder` (T13's model half); copy sets
  `last_modified` to `None` (T19's model half); `StoreTree` names admit `.`,
  `..`, `\` and NUL; a negative `max_depth` reads as unlimited.
- **The key rule inside the domain.** The oracle adapter passes non-canonical
  keys the trait was never proven for (T14); route it through a verified
  raw-key entry, as `RootPath.dfy` § 5 does for root spellings.
- **Missing operations.** The trait has no `read_bytes`, `read_seekable`,
  `write_atomic`, `open_atomic`, `iter_children`, `glob` or `check_health`
  (T12); `glob`'s exclusion premise (`BackendContract.dfy:89-92`, "delegates to
  ListFiles") no longer holds on the kernel, and BK-451 redefines it.
- **Traceability.** BE-030 and BE-031 cannot carry an `@spec` tag, because
  `check_formal_trace.py` counts only `tests/backends/conformance/` markers.

**Order:** after BK-432; before RFC-0017 D3 step 8, or step 2 as above.
