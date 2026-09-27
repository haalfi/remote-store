# BK-364 — `transfer-operations.md` documents partial files for `download` only, and the other direction is the one that can destroy data
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 3](../BACKLOG.md#users-succeed-unaided) by the ADR-0040 § 3
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

§ Error semantics carries one bullet on residue — *"Partial files on failed
download: if `download` fails mid-transfer a partial local file may remain …
When retrying, pass `overwrite=True`"* — and says nothing about `upload` or
`transfer`, which route through `store.write()` and so leave a partial file at
the **remote** destination on exactly the same fault. The asymmetry is
backwards: a partial local file is the caller's own disk and their own
`overwrite` flag, while a partial remote file may have replaced data they
cannot re-derive.
**Found by BK-360's review round 1, while checking whether that item's SFTP
rule rippled here.** It was left out of BK-360 deliberately: the SFTP rule is
measured for one backend, and this bullet is about a helper that works over
*any* `Store`, so stating it needs the residue question answered per backend
rather than borrowed from SFTP. That is the work — establish what
`upload`/`transfer` leave behind on the backends the helper is used with, then
state it once beside the `download` bullet.
BK-360 established the SFTP half and is the model: the governing fact there is
that a timeout reports a *lost reply*, so an operation reported as failed may
have been performed. Whether the flat-namespace backends share that shape is
the open question, not an assumption to carry over.

## Re-measured, 2026-09-27

The asymmetry holds.
`rg -n "Partial files on failed|\.write\(" docs-src/guides/transfer-operations.md src/remote_store/ext/transfer.py`
finds the page's one residue bullet at line 112, for `download` only, while `upload`
calls `store.write(...)` at `transfer.py:69` and `transfer` calls
`dst_store.write(...)` at `:149`. No residue sentence for either helper exists
on the page. BK-360's remote-residue text, in `guides/backends/sftp.md` and
`guides/troubleshooting.md` (lines 202-211), is SFTP-scoped and names neither
helper: `rg -n "upload|transfer\(|ext\.transfer"` over those two pages finds
only a store named `uploads` in a registry example. One more remote-residue
sentence is not BK-360's: `troubleshooting.md:288`, § "DatasetIncomplete error", where a
missing `_SUCCESS` marker means a partial dataset write. No search here was
exhaustive over `docs-src/`, so whoever states the rule reconciles with these
three sites and searches again. Found by the ADR-0040 § 3 conversion.
