# BK-390 — RFC-0017's spec amendments after D3 step 1 have no owner once BK-387 closes
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** The remainder of BK-387 (partly done, per
[§ Completing work](../BACKLOG.md#how-this-file-works)). RFC-0017 § Impact
lists the amendment set. A spec describes behaviour that exists
(`CLAUDE.md` principle 3), so each amendment lands in the D3 step PR that makes
it true, not at acceptance. Everything that becomes true at D3 step 1 goes
with BK-389: specs 003, 005, 029 and 037, and the kernel half of 007 and 022.

**Amendment by step** (steps are RFC-0017 D3's table):

| Spec | Amendment (RFC-0017 § Impact) | Lands with |
|---|---|---|
| 007, 022, driver half | each driver's `put_is_atomic`, `open_write` and `rename` | that driver's step |
| 006 | SIO-008 against `get_range` | the first step whose driver has `get_range` (step 2, S3) |
| 036 | SEEK-004 and SEEK-006 against `get_range` | step 2 |
| 008 and S3-, S3PA- | s3fs-specific clauses retire with the lanes | step 2 |
| SQL-BLOB- | clauses describing class behaviour the kernel owns | step 3 |
| AZ- | the same, plus the generated sync driver | step 4 |
| 026 | `probe()` against PING-011 | each driver's step |
| 009 | SFTP-010's connection tiers become D5's `Session` | step 6 |
| 044 and GR- | GR-039 and `parents == "implicit"` | step 7 |

**Exit criteria:** every row landed in its step's PR. Close this item with
the last one; a row whose step is re-planned moves with it.
