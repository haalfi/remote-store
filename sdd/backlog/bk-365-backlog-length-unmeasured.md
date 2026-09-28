# BK-365 — Both backlog files grew past what a maintainer can read, and nothing measures it
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

**In progress: [RFC-0016](../rfcs/rfc-0016-backlog-as-index.md) is accepted as
[ADR-0040](../adrs/0040-backlog-as-index.md)** for the `BACKLOG.md` half — an
index with per-item dossiers. Shipped: the rules header, R1–R4, the § 1
pilot (16 items to `sdd/backlog/`), § 2 (9 items), § 3 (8 items), § 4
(5 items) and § 5 (14 items), per `sdd/rfcs/rfc-0016-measure.py`; what
remains is the exit criteria below.
**`sdd/BACKLOG.md` is 20,097 words at `6cec225`.** That is the file a maintainer
reads to decide what to work on, and it is now roughly eighty pages of prose. Two
independent multipliers got it there over seven weeks (2026-07-18 → 2026-09-05):
the item count doubled, 28 → 57, and the median words per item doubled too,
145 → 290. Total 4,823 → 20,097 words — 4.2× against 12.7% growth in `src/`
over the same window. `BACKLOG-DONE.md` shows the same shape at 104,328 words
over 651 items, and its per-release medians run from **10 words per completed
item at v0.3.0 to 649 under `Unreleased`** — 65×, of which 2.8× arrived in the
current cycle alone (v0.30.0 sat at 234). **Pinned because both files change on
every merge**: re-derive rather than quote, and read the ratios, which are stable,
rather than the totals, which are not.
**Measured, not felt.** Derivation: for each entry, the words between its
`- [x] **ID-NNN` header and the next header or heading, over
`git show <sha>:sdd/BACKLOG.md` across the file's history; per-release figures
from `BACKLOG-DONE.md`'s own `## vX.Y.Z` sections. Both were run before this
entry was written.
**Why this is not simply Rule 7's job.**
[`CONTENT-RULES.md` Rule 7](../CONTENT-RULES.md#kernsatz) binds `sdd/`, so it
formally reaches both files, but it tests whether a *section* opens with its
core claim and a backlog entry is not a section. Nothing tests whether an entry
has outgrown its next reader, and the release step
([`CONTRIBUTING.md` § Release](../../CONTRIBUTING.md#release)) renames
`## Unreleased` to `## vX.Y.Z` without condensing, so nothing shortens an entry
after it is written.
**Answered for `BACKLOG.md` by ADR-0040:** whether a 290-word median is a
defect or the price of [principle 9](../../CLAUDE.md#principles)'s derivations.
Length moves to a dossier rather than being cut, which is what
[research](../research/research-appropriate-level-of-detail.md) § 9.2 permits,
and the caps are a recorded departure from its § 9.1. The question stays open
for `BACKLOG-DONE.md`.
**Exit criteria:** § 6 converted (dropping its `unconverted` marker, so
R2/R3 then gate it), and a recorded decision on the
`BACKLOG-DONE.md` half with any mechanism's bound stated per
[`DRIFT-RULES.md`](../DRIFT-RULES.md#rules).

## Re-measured, 2026-09-28

§ 6 is converted, so every section of `BACKLOG.md` is in the index shape
(`python sdd/rfcs/rfc-0016-measure.py`: 68 items, none over 8 content lines);
§ 2 holds 8 items today, since BUG-241 left it as BL-011. Two figures above are
imprecise. The 20,097 words at `6cec225` is not reachable in this shallow clone;
at `203c7caa8`, the commit that filed this item, the item text alone counts
20,125 words over 57 items and the whole file 24,671 (a scratch script,
`str.split()` over `git show 203c7caa8:sdd/BACKLOG.md`), so the figure is item
text. And
`git show 203c7caa8:sdd/BACKLOG-DONE.md | rg -c '^- \[x\] \*\*'` gives 659
entries, not 651. Current per-release medians of words per `BACKLOG-DONE.md`
entry (words from each `- [x] **ID` header to the next header or heading):
9.5 at v0.3.0, 235 at v0.30.0, 646 at v0.31.0, 403 at v0.32.0 (6 entries) and
599.5 under Unreleased (16 entries). Found by the ADR-0040 § 6 conversion.
