# BK-390 — RFC-0017's spec amendments after D3 step 1 have no owner once BK-387 closes
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** The remainder of BK-387 (partly done, per
[§ Completing work](../BACKLOG.md#how-this-file-works)). RFC-0017 § Impact
lists the amendment set. A spec describes behaviour that exists
(`CLAUDE.md` principle 3), so each amendment lands in the D3 step PR that makes
it true, not at acceptance. Everything that becomes true at D3 step 1 goes
with BK-394, the Memory half of step 1 split from BK-389 on 2026-10-02: specs
003, 005, 013, 029 and 037, the kernel half of 007 and 022, and spec 026's
PING-002 and PING-008 plus the Memory drivers' rows of 007 and 022, and any
clause outside spec 003 that BK-395's answers contradict. BK-389's kernel PR
is private and touches spec 003 only: the clauses its kernel cells trace to,
and any spec 003 clause BK-395's answers contradict (its dossier, item 8,
the authority for the split; corrected after PR #1055 merged, which said it
amended no spec). This item owns steps 2 to 8.

**Amendment by step** (steps are RFC-0017 D3's table):

| Spec | Amendment (RFC-0017 § Impact) | Lands with |
|---|---|---|
| 007, 022, driver half | each driver's `put_is_atomic`, `open_write` and `rename` | that driver's step, 2 to 8 |
| 006 | SIO-008 against `get_range` | the first step whose driver has `get_range` (step 2, S3) |
| 036 | SEEK-004 (the S3 lane's passthrough) against `get_range` | step 2 |
| 036 | SEEK-006 (`AzureBackend`'s range-reader override) against `get_range` | step 4, when that class is replaced |
| 008 and S3-, S3PA- | s3fs-specific clauses retire with the lanes | step 2 |
| SQL-BLOB-, SQL-QUERY- | clauses describing class behaviour the kernel owns | step 3 |
| AZ- | the same, plus the generated sync driver | step 4 |
| 026 | each driver's own health-check row against its `probe()`: PING-004 and PING-005 retire and an S3 driver row is added (step 2), a SQL row is added (step 3), PING-007 Azure (step 4), PING-003 Local (step 5), PING-006 SFTP (step 6), PING-011 Graph (step 7), an HTTP row is added (step 8) | that driver's step, 2 to 8 |
| 009 | SFTP-010's connection tiers become D5's `Session` | step 6 |
| each remote driver's own spec (S3B-, created at step 2 per RFC-0017 D4; SQL-BLOB-, SQL-QUERY-, AZ-, 009, GR-, HTTP- in 032) | its connection lifecycle stated as its `Session` (RFC-0017 D5: every remote driver has one) | that driver's step: 2, 3, 4, 6, 7, 8 |
| 044 and GR- | GR-039 and `parents == "implicit"`; Graph's folder `modified_at` meeting the kernel's rule (RFC-0017 D3) | step 7 |

**Exit criteria:** every row landed in its step's PR. Close this item with
the last one; a row whose step is re-planned moves with it.
