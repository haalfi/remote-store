# BK-366 — Bug share of shipped work rose 3% → 35% across five releases, undiagnosed
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Counting `BUG-` against all items in each `BACKLOG-DONE.md` release section:
**v0.27.0 3%, v0.28.0 12%, v0.29.0 21%, v0.29.1 23%, v0.30.0 35%**, with
`Unreleased` at 33% (16 of 49). Over the same window open `BUG-` items in
`BACKLOG.md` went 1 → 22 while `src/` grew 12.7%, so a larger codebase does not
explain it and the queue is growing rather than being worked down.
**Two readings fit these numbers and they need opposite responses.** Detection
improved — this repo added gates steadily, and a gate finds defects that
previously shipped silently, which would make the trend good news. Or quality
degraded. Nothing measured here distinguishes them, and that is the finding:
**the repo cannot currently tell whether its central promise is holding.**
**What would separate them**, none of it needing new tooling: whether each open
`BUG-` escaped to a released version or was caught pre-merge; which gate or
review caught it; and whether the classes cluster on the surfaces that grew. A
rise concentrated in pre-merge catches on new code is detection working; a rise
in escapes to released behaviour is not.
**Derivation:** `BUG-` versus total entry headers per `## vX.Y.Z` section of
`BACKLOG-DONE.md`; open counts and `src/` line totals from `git show <sha>:`
across the same window. Run before this entry was written.
**Exit criteria:** each open `BUG-` classified escaped/caught with the catching
mechanism named, and a recorded answer to which reading the data supports.

## Correction, 2026-09-28

The trend depends on its window. `BUG-` headers against all `[x]` headers per
section (scratch script over `BACKLOG-DONE.md`): v0.25.0 29/91 (32%), v0.26.0
0/17, v0.27.0 1/37 (3%), v0.28.0 6/50, v0.29.0 4/19, v0.29.1 3/13, v0.30.0
7/20 (35%), v0.31.0 24/59 (41%), v0.32.0 4/6, Unreleased 4/16. The five figures
above reproduce, but starting two releases earlier the share moves 32% → 41%,
not 3% → 35%. Open `BUG-` items now number 25 of 68
(`rg -c '^- \[[ ~]\] \*\*BUG-' sdd/BACKLOG.md`). Found by the ADR-0040 § 6 conversion.

## Note, 2026-09-28

[Audit-021](../audits/audit-021-contract-placement.md) classifies every
user-audience code defect from v0.28.0 to the current stub, open items
included, with the register's finder column per entry (57 of 71 caught
internally, 11 naming no finder, 2 user reports), and answers the reading
question: detection improved, and for the contract and SFTP-lifecycle
clusters what it detected was released behaviour found by audit rather than
by users; the eight Graph burn-in defects were fixed before release. Its
design conclusion is
[RFC-0017](../rfcs/rfc-0017-contract-kernel-over-thin-drivers.md). Whether
that meets this item's exit criteria is undecided here.
