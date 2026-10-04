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

**Baseline**, from `hatch run report-done-length` over the register at
`8fa22d6` (the merge of ADR-0041), which this PR leaves unchanged; median words
per entry:

| Section | Entries | Median | With dossier | Median | Unlinked | Without | Median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Unreleased | 17 | 558 | 1 | 67 | 0 | 16 | 599.5 |
| v0.32.0 | 6 | 403 | 0 | — | 0 | 6 | 403 |
| v0.31.0 | 59 | 646 | 0 | — | 0 | 59 | 646 |
| v0.30.0 | 20 | 235 | 0 | — | 0 | 20 | 235 |

Unreleased's one dossier entry is BK-365's close; the only other in the
register is BUG-241's under Absorbed, which holds retired IDs, not releases. The 16 without were written before
the rule, and none of their items has a dossier file under `sdd/backlog/`; they
stay as they are, since ADR-0041 does not condense them.

**Read at the release, not before.** The figure that answers the question is
the *With dossier* median of the section the release renames from
`Unreleased`, set against its *Without* median and v0.32.0's, together with
its *Unlinked* count: dossier entries that omit the link the rule requires.
The overall median mixes pre-rule entries in, so it is not the figure to read.

**Record at the revisit:** the report's rows for the new release section and
the previous one; the entries counted as having a dossier, since dossiers are
known by filename and links by text (the script's bound); and one of:

- **keep**: dossier entries are short and linked without a gate, so review holds the rule;
- **gate**: dossier entries drift long or unlinked, so propose a mechanism, with its bound
  stated per [DRIFT-RULES](../DRIFT-RULES.md#rules) and without a word cap,
  which ADR-0041 declined;
- **reverse**: the short entry cost readers something the dossier did not
  give back, which takes a new ADR amending ADR-0041.

**Exit criteria:** the decision is recorded here, and the Phase 0 checklist line
either goes or gets a successor: if the line stays, open the item it will close
at the following release and name it in the close note; otherwise remove it in
the same change.

## Decision at v0.33.0, 2026-10-04: keep

Read at the release base `39059422c`, before Phase 2 renames the section, so
the section is still `Unreleased`; v0.32.0's row is unchanged from the
baseline above.

| Section | Entries | Median | With dossier | Median | Unlinked | Without | Median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Unreleased (v0.33.0) | 30 | 290.5 | 11 | 100 | 0 | 19 | 529 |
| v0.32.0 | 6 | 403 | 0 | — | 0 | 6 | 403 |

**Entries counted as having a dossier**, by re-running the script's own
`parse()` with the item ID kept (words in parentheses): ID-257 (134), BK-395
(125), BK-387 (109), BK-396 (107), ID-251 (103), BL-011 (100), BK-388 (98),
BK-380 (89), BK-385 (87), BUG-240 (70), BK-365 (67). All eleven link their own
dossier.

**Keep.** Dossier entries came out short and linked under review alone: a
median of 100 words against 529 for entries without a dossier, and none
unlinked. Nothing drifted that a gate would catch, and nothing here shows a
short entry costing a reader what the dossier failed to give back, which is
ADR-0041's reversal condition.

**The Phase 0 line stays for one more release.** One release is one sample,
and this one's eleven entries were written in the weeks right after the
rule landed. Successor: **BK-406**, which repeats the reading at the next
release and decides whether the line then goes.
