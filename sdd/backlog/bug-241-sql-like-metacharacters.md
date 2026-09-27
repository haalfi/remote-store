# BUG-241 — `SQLBlobBackend` builds prefix `LIKE` patterns without escaping `_` and `%`, so listings and folder deletes reach sibling keys
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 2](../BACKLOG.md#correct-and-proven) by the ADR-0040 § 2
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`SQLBlobBackend._reject_folder` builds `LIKE key + "/%"`, and every other
prefix probe in `_sqlalchemy.py` follows the same convention. In SQL `LIKE`,
`_` matches any single character and `%` matches any sequence, so a key
containing either over-matches: probing `a_b` also matches `axb/...`, and a
key containing `%` matches far more.
**Consequence:** the wrong-type probe can report a folder that does not
exist, turning a `NotFound` into an `InvalidPath` for a sibling key whose
name merely resembles the target. Underscores in object keys are common, so
this is a wrong answer on ordinary data rather than a wrong error type.
The convention is file-wide, so fixing one site without the rest would be the
inconsistency this section exists to remove. Fix them together with
`ESCAPE`, or a dialect-appropriate equivalent.
**Test shape:** seed sibling keys that differ only in a `LIKE` metacharacter
position and assert the probe does not confuse them.

## Correction, 2026-09-27

The body above scopes the defect to probes and their error type. It also
reaches listings and a delete. `rg -n '\.like\(' src` finds eleven sites, all
in `_sqlalchemy.py`: nine build `key + "/%"` or `prefix + "%"` unescaped (lines
460, 537, 588, 900, 913, 948, 991, 1029, 1116 at this commit), and two are the
glob path, which escapes. Line 913 is `delete_folder`'s `DELETE`, not a probe.
Measured on `SQLBlobBackend` over in-memory SQLite (`StaticPool`), seeded with
`a_b/x.txt`, `axb/y.txt`, `a%/z.txt`, `aQQ/w.txt`:

| call | answer |
|---|---|
| `list_files("a_b", recursive=True)` | `a_b/x.txt`, `axb/y.txt` |
| `delete_folder("a_b", recursive=True)` | deletes `axb/y.txt` too |
| then `delete_folder("a%", recursive=True)` | deletes `aQQ/w.txt` too; nothing remains |

So the consequence is wrong listings and data loss on ordinary keys, not only a
wrong error type. Whether that meets the `BL-` bar is the maintainer's call.
Found by the ADR-0040 § 2 conversion, which re-derived the item before writing
its index diagnosis; the index title changed with it.

## Absorbed, 2026-09-27

Absorbed into [BL-011](bl-011-sql-like-sibling-deletion.md), a release
blocker, by maintainer decision after the correction above. BL-011's index
entry holds the current diagnosis.
