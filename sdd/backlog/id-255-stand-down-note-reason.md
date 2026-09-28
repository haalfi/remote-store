# ID-255 — The stand-down note gives a reason that is false in the state the release checklist prescribes
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`_release_window_note` in `scripts/check_changelog_unreleased.py` prints: "The
stray-line rule, the audience rule and the unknown-ID note all key on entries
leading with an ID, **which condensed prose does not**, so all three stood
down." That reason is true at the *end* of Phase 1 and false at its
*beginning* — and the beginning is the state
[`CONTRIBUTING.md` § Release Phase 1](../../CONTRIBUTING.md#release) mandates,
since it says to add the `###` groupings **before** condensing any bullet.
**Reproduce it:** put a bare `### Fixed` *inside* an untouched `[Unreleased]`,
above its entries — `parse_unreleased` scans forward from the `## [Unreleased]`
heading, so a grouping placed above that heading sets nothing and the symptom
never appears.
The note claims the entries do not lead with an ID, then reports "over the 25
line(s) that still parse as entries" — counting the ones that do.
What actually switches the three off is the `###` itself: `grouped` is a bare
`startswith("### ")` and `collect` branches on it alone, never on whether any
line still parses. The reason describes a *consequence* of finishing the
condense, not the *trigger*.
**What it decides.** Whether to state the trigger instead ("a `###` grouping,
not the absence of IDs, is what switches these off") or to state both. It is a
message-string change; no existing assertion pins the reason clause — the
tests key on `_STOOD_DOWN` and on the surviving-entry count, deliberately, per
the comment at that assertion — so whoever takes it should add one, or the
corrected reason is unpinned in exactly the way the wrong one was.
**A second half worth deciding at the same time**, being the same paragraph's
blind spot: the docstring's "The cost, stated in full" costs out uniqueness
and the prose budget but never costs out the **audience rule**, which is what
the groupings-first ordering trades away earliest.
**Filed rather than fixed by ID-253**, which found it: that PR's whole diff to
`scripts/check_changelog_unreleased.py` is inside the module docstring —
verified by AST, base and head byte-identical with the docstring stripped —
and it declined to trade that property for a one-sentence message fix.
