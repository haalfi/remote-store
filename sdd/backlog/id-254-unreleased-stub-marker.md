# ID-254 — The `[Unreleased]` stub's section marker means one thing on half the entries and nothing on the other half
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Twelve of the 25 entries under CHANGELOG `[Unreleased]` open with a bolded
marker and thirteen open with none (`- <ID>: **<marker>** —` against
`- <ID>: <text>`, tallied over the section as of this item's filing; re-tally
rather than reading the split, which every merged PR moves). Four of the twelve are
`**Breaking**`, which is a real obligation the ripple-check's **Breaking
change** row states and `check_breaking_migration_link.py` half-enforces. The
other eight are decoration nobody wrote down: `**Fix**` (5), `**Docs**` (1),
`**Added**` (1), `**Change**` (1).
**Three of those four names are not section names.** The canonical names are
[`CONTRIBUTING.md` § CHANGELOG section order](../../CONTRIBUTING.md#changelog-section-order),
which ID-253 gave its one home; against that list `**Fix**`, `**Change**` and
`**Docs**` each look like they name the section the entry will land in
(`Fixed`, `Changed`, `Documentation`) and each names something else. A reader
cannot tell whether the marker is a section assignment the author made or an
emphasis they chose, and the release step reassigns sections from the item
regardless — which is what ID-253 recorded the v0.30.0 release doing to eight
unmarked stubs.
**What it decides.** Either the marker becomes a section assignment the PR
author owes — spelled with the canonical names and gateable in
`check_changelog_unreleased.py` alongside the three rules already there, which
would move section assignment off the release manager and onto the author who
knows the change — or it stays free-form emphasis and says so, in which case
`**Breaking**` is documented as the one marker that means anything and the
other eight are normalised or dropped. **Do not split the difference**: a
marker that is a section name on some entries and a mood on others is the
state this item exists to leave.
**Section assignment is this item's either way.** ID-253 wrote the expansion
step's sources, its per-entry shape and the section order, but not the rule for
*which* section a given entry lands in — and that is the one decision the step
makes per entry. If the marker becomes an obligation, the author assigns and
the rule is the marker's definition; if it stays emphasis, the release manager
assigns and the rule has to be written for them. Either resolution owes it, so
it does not fall between the two.
**Not urgent, and the reason bounds it:** nothing downstream reads the
marker except the breaking-change gate, which keys on `**Breaking**` alone, so
the cost today is a reader's confusion rather than a wrong release. Found by
ID-253 while deriving the section order, and deliberately left out of its
scope.
