# BUG-267 — OBS-008 demands an `ERROR` level that nothing emits and nothing asserts
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

OBS-008's Levels bullet read "ERROR (before re-raise)" as an invariant over
"all library modules". No call site in `src/` logs at `error`, `exception`,
`critical` or `fatal` — verified by grep across the package — and none of the
four `@pytest.mark.spec("OBS-008")` tests in `tests/ext/test_observe.py`
asserts a level at all.
That is [`000-process.md` Rule 7](../000-process.md#intent-attribution)'s
**Unenforced** row: prose demanded it, nothing enforced it, so the claim is
undecided and **nothing moves yet**.
**BK-359 twice tried to resolve it in passing and both attempts were wrong.**
It first deleted the clause and wrote current behaviour into the spec — the
code made right by prose inside a review fix pass. Its round 4 caught that and
suspended the clause instead, which left the spec saying *undecided* while the
guide `docs-src/guides/observe.md`, rewritten in the same PR, still published
the withdrawal as settled — a split across two artifacts. Both edits are reverted;
OBS-008 and the guide are back at their pre-BK-359 text, so the divergence is
intact and undecided rather than half-resolved in two directions.
**The decision owed** is one of two: either the library should report before
re-raising, and the deliverable is that call site plus the level assertion
Rule 2 wants; or it should not, and the clause is withdrawn on the ordinary
path with the reason recorded. Either way it is decided once rather than
inherited.
