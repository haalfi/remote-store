# BK-386 — ADR-0041's short done entry is unmeasured until the next release
<!-- doc: repo-only -->

The index entry in [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead)
holds the current diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Why this item exists.** [ADR-0041](../adrs/0041-done-register-links-dossiers.md)
decides that a completed `BACKLOG-DONE.md` entry for an item with a dossier is
short, says what shipped and where, and links the dossier. It is enforced by
review alone, with no length rule, and its Neutral consequence says the only
evidence is the next release section's median, which nothing schedules. This
item schedules it, and `scripts/report_done_length.py` produces the figure. The
checklist line in [`CONTRIBUTING.md` § Release](../../CONTRIBUTING.md#release)
Phase 0 makes it findable without naming this ID, the split ID-259 uses.

**Baseline**, from `hatch run report-done-length` at `8fa22d6` (the merge of
ADR-0041), median words per entry:

| Section | Entries | Median | With dossier | Median | Without | Median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Unreleased | 17 | 558 | 1 | 67 | 16 | 599.5 |
| v0.32.0 | 6 | 403 | 0 | — | 6 | 403 |
| v0.31.0 | 59 | 646 | 0 | — | 59 | 646 |
| v0.30.0 | 20 | 235 | 0 | — | 20 | 235 |

The one linked entry is BK-365's close. The 16 without a link were written
before the rule and stay as they are, since ADR-0041 does not condense them.

**Read at the release, not before.** The figure that answers the question is
the *With dossier* median of the section the release renames from
`Unreleased`, set against its *Without* median and v0.32.0's. The overall median
mixes pre-rule entries in, so it is not the figure to read.

**Record at the revisit:** the report's rows for the new release section and
the previous one; the entries counted as linked, since the link is detected
textually and a citation of another item's dossier also counts (the script's
bound); and one of:

- **keep**: linked entries are short without a gate, so review holds the rule;
- **gate**: linked entries drift long, so propose a mechanism, with its bound
  stated per [DRIFT-RULES](../DRIFT-RULES.md#rules) and without a word cap,
  which ADR-0041 declined;
- **reverse**: the short entry cost readers something the dossier did not
  give back, which takes a new ADR amending ADR-0041.

**Exit criteria:** the decision is recorded here, the Phase 0 checklist line is
removed or kept to match it, and any successor is named in the close note.
