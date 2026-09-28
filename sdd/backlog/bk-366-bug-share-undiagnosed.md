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
