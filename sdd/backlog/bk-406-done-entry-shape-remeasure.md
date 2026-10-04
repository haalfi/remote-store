# BK-406 — ADR-0041's short done entry is measured on one release only
<!-- doc: repo-only -->

The index entry in [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead)
holds the current diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Why this item exists.** [BK-386](bk-386-done-entry-shape-measure.md) read
`hatch run report-done-length` at v0.33.0 and kept
[ADR-0041](../adrs/0041-done-register-links-dossiers.md)'s review-only rule:
11 dossier entries, all linked, median 100 words. It also kept the Phase 0 line
in [`CONTRIBUTING.md` § Release](../../CONTRIBUTING.md#release) for one more
release, because a single section written in the weeks after the rule landed
is one sample. This item is that second reading.

**Baseline**, from BK-386's close at `39059422c`: the v0.33.0 section (then
`Unreleased`) at 30 entries, 11 with a dossier at a median of 100 words, 0
unlinked, 19 without at a median of 529. BK-386's dossier lists the eleven by ID
and word count. **It does not reproduce from the released register.** The
release PR then added two close entries to that section, BK-386 and ID-259, each
linking its dossier, so `hatch run report-done-length` on the release branch
prints `v0.33.0 | 32 | 288.5 | 13 | 98 | 0 | 19 | 529`. Compare against the
recorded baseline, which excludes those two: re-run it at `39059422c` in a
worktree, or drop BK-386 and ID-259 from the eleven-plus-two.

**Read at the release, not before**, as BK-386 did: the *With dossier* median of
the section the release renames from `Unreleased`, its *Unlinked* count, and its
*Without* median, set against v0.33.0's row. The overall median mixes pre-rule
entries in. Dossiers are known by filename and links by text, so list the
entries counted as having a dossier, as BK-386 did.

**Decide one of** BK-386's three (keep, gate, reverse; definitions in its
dossier), and whether the Phase 0 line goes: two consistent readings are
enough to retire the scheduled measurement and leave `report-done-length` as an
on-demand script.

**Exit criteria:** the decision is recorded here, and the Phase 0 line is either
removed in the same change or handed to a named successor.
