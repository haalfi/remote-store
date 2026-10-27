# BK-497 — The input files carry only research § 4, so per-entry findings in § 2 reach no session
<!-- doc: repo-only -->

**Which input file carries which passage of `research-operation-catalogue.md` § 2 is fixed by one
literal rule, and the table below is that rule's output.** Q1 table rows go to the entry
`catalogue.md`'s Not in v1 table disposes them to, or whose entry-table intent names them. Every
other passage goes to each entry whose ID it names (a Q2 bullet's label and the Q3 heading count,
ranges expanded) or whose operation word below it contains; Q4 rows and note 7 also go to OP-01, the
first session. The rule decides, not a reading of relevance: review on PR #1187 refuted each
narrower reading in turn.

Excluded: note 1, a recommendation on the catalogue; Q4's key validation row and the `..` sentence,
spec 052's; Q4's async parity row, spec 053's (research § 3, BK-485's dossier).

## Operation words

Matched case-insensitively against the passage (for a Q2 bullet with its label, for Q3 with its
heading).

| Entry | Pattern |
|---|---|
| OP-01 | `\breads?\b\|\bget\b` |
| OP-02 | `\branges?\b\|multi-range\|\boffsets?\b` |
| OP-03 | `(?<![\w-])writes?\b\|\bput\b\|\buploads?\b` |
| OP-04 | `atomic(ally)? replace\|\breplace\b\|atomic put` |
| OP-05 | `\bconditions?\b\|\bconditional\b` |
| OP-06 | `(?<![\w-])list(s\|ing\|ings)?\b` |
| OP-07 | `\bwalk\b\|recursive listing\|\bdepth\b` |
| OP-08 | `\bglob\b\|\bpattern\b` |
| OP-09 | `\binspect\b\|identity (token\|field)s?\|\betag\b` |
| OP-10 | `(?<!tree )(?<!recursive )(?<![\w-])deletes?\b` |
| OP-11 | `tree delete\|recursive delete\|delete_dir` |
| OP-12 | `\brenam\w*\|\bmoves?\b\|\bmv\b` |
| OP-13 | `\bcop(y\|ies\|ying)\b` |
| OP-14 | `\btransfers?\b\|\blocal (file\|disk)\b` |
| OP-15 | `\btransfers?\b\|cross-store` |
| OP-16 | `prefix scope\|prefixstore\|prefixedbucket\|subtreefilesystem\|dirfilesystem` |
| OP-17 | `\bfspath\b\|io/fs\|\badapters?\b` |
| OP-18 | `capabilit\|\bgat(e\|es\|ed\|ing)\b\|\bflags?\b` |
| OP-19 | `create_dir\|\bmkdir\b\|empty folder` |
| OP-20 | `metadata\|system propert\|content type\|\btags?\b\|(?<![\w-])attributes?\b` |
| OP-21 | `\bclos(e\|ing)\b` |
| OP-22 | `native address\|\burls?\b\|\buris?\b` |
| OP-23 | `native client` |
| OP-24 | `\bhealth` |

## Routing

Generated with the files by a one-off script that asserts each passage against the research doc.

| Passage | Entries | Basis |
|---|---|---|
| Q1 Presigned or signed URL | — | catalogue disposition |
| Q1 System properties (content type, cache control) apart from user metadata | OP-20 | catalogue disposition |
| Q1 Batch delete | OP-10 | catalogue disposition |
| Q1 Versioned access | — | catalogue disposition |
| Q1 Integrity and identity tokens (checksums, unique keys, verified MD5) | OP-03, OP-09 | catalogue disposition |
| Q1 Append | — | catalogue disposition |
| Q1 Conditional read | — | catalogue disposition |
| Q1 Abort an in-flight write | OP-03 | catalogue disposition |
| Q1 Bucket or container create and delete | — | catalogue disposition |
| Q1 Server-side compose, restore or undelete | — | catalogue disposition |
| Q1 Multi-range read | OP-02 | catalogue disposition |
| Q1 Delete only a folder's contents, or only an empty folder | OP-11 | catalogue disposition |
| Q1 Storage class, retention or legal hold | — | catalogue disposition |
| Q1 Post-write metadata update | OP-20 | catalogue disposition |
| Q1 Local cache layer, transparent compression, `touch`, tags, query in place | OP-03 | catalogue disposition |
| Q1 Transaction, key-value view, FUSE mount, rsync, leases, snapshots, aborting an async copy, annotations | OP-15, OP-17 | catalogue disposition |
| Q1 closing | OP-07, OP-18, OP-24 | IDs and words |
| Q2 Write, atomic replace, conditional write (OP-03 to OP-05) | OP-01, OP-03, OP-04, OP-05, OP-10, OP-12, OP-13, OP-20 | IDs and words |
| Q2 List, walk, match (OP-06 to OP-08) | OP-06, OP-07, OP-08, OP-09 | IDs and words |
| Q2 Inspect (OP-09) | OP-09 | IDs and words |
| Q2 Delete (OP-10, OP-11) | OP-10, OP-11 | IDs and words |
| Q2 Copy and transfer (OP-13 to OP-15) | OP-13, OP-14, OP-15 | IDs and words |
| Q2 Read (OP-01, OP-02) | OP-01, OP-02 | IDs and words |
| Q3 Declared and checked before dispatch | OP-05, OP-18 | IDs and words |
| Q3 Configured per store, then an error at call time | OP-18, OP-20 | IDs and words |
| Q3 Error at call time only | OP-18 | IDs and words |
| Q3 Silent emulation or no-op | OP-10, OP-12, OP-13, OP-18, OP-19, OP-20 | IDs and words |
| Q3 Path-scoped probe | OP-18 | IDs and words |
| Q3 sentence: OpenDAL's gates | OP-05, OP-06, OP-07, OP-12, OP-13, OP-18, OP-19, OP-20 | IDs and words |
| Q3 sentence: Runtime gates | OP-11, OP-12, OP-18 | IDs and words |
| Q3 sentence: Effective flags | OP-18 | IDs and words |
| Q4 Error taxonomy | OP-01 | IDs and words; OP-01 as first session |
| Q4 Retries | OP-01, OP-10 | IDs and words; OP-01 as first session |
| Q4 Timeouts | OP-01 | IDs and words; OP-01 as first session |
| Q4 Consistency stated | OP-01, OP-03, OP-04, OP-06 | IDs and words; OP-01 as first session |
| Q4 Identity token | OP-01, OP-03, OP-09, OP-20 | IDs and words; OP-01 as first session |
| Q4 Closing | OP-01, OP-21 | IDs and words; OP-01 as first session |
| Q4 Prefix scope (OP-16) | OP-01, OP-16 | IDs and words; OP-01 as first session |
| note 2 | OP-03, OP-05 | IDs and words |
| note 3 | OP-07 | IDs and words |
| note 4 | OP-09, OP-14 | IDs and words |
| note 5 | OP-18 | IDs and words |
| note 6 | OP-24 | IDs and words |
| note 7 | OP-01, OP-03, OP-10 | IDs and words; OP-01 as first session |
