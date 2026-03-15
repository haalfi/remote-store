# Fix List: Documentation Structural Issues

Companion to **Audit 004** (`audit-004-docs-structural-consistency.md`).
**Remove this file after all items are resolved.**

---

## 1. Dash convention (AF-041, AF-045)

Pick one convention and apply globally.
`—` is typographically correct; `--` is ASCII-safe and matches docs-src originals.

- [ ] **T-01** `guides/data-lake-patterns.md` -- convert `—` to chosen convention (lines 4, 32, 49, 62, 69, 96, 215, 302-307)
- [ ] **T-02** `guides/dagster.md` -- convert `—` (lines 12, 67, 123, 147, 149, 154)
- [ ] **T-03** `guides/batch-operations.md` -- convert `—` (lines 8, 10, 37, 115, 120)
- [ ] **T-04** `guides/backends/sftp.md` -- convert `—` (lines 108-110)
- [ ] **T-05** `guides/backends/memory.md` -- convert `—` (lines 3, 43)
- [ ] **T-06** `guides/backends/s3-pyarrow.md` -- convert `—` (line 60)

---

## 2. "See also" format (AF-042)

Pick Pattern A (`**See also:**` bold + inline links) or Pattern B (`## See also` heading + bullet list). Convert all to the winner. Add to the 4 files that lack it.

- [ ] **T-07** `guides/concurrency.md` -- add See also section
- [ ] **T-08** `guides/health-check.md` -- add See also section
- [ ] **T-09** `guides/performance.md` -- add See also section
- [ ] **T-10** `guides/extensions.md` -- add See also section
- [ ] **T-11** Convert all 22 existing "See also" sections to the chosen format

---

## 3. Table boolean values (AF-043)

Project convention: `Yes` / `--` (dash), never `Yes` / `No`.

- [ ] **T-12** `docs-src/capabilities-matrix.md` lines 12-20 -- replace HTML entity checkmarks with `Yes` / `--`
- [ ] **T-13** `guides/cache.md` line 45 -- replace bold `**No**` with `--`
- [ ] **T-14** Normalize all 6 files to `Yes` / `--` convention

---

## 4. Blockquotes to admonitions (AF-044)

- [ ] **T-15** `guides/backends/sftp.md` lines 127-131 -- convert three `>` blockquotes to `!!! warning` or `!!! note` admonitions

---

## 5. Extensions table (AF-046)

- [ ] **T-16** `guides/extensions.md` lines 10-19 -- replace `--` cell values with "none", empty cell, or a distinct glyph

---

## 6. Backend page structure (AF-047, AF-048, AF-050)

- [ ] **T-17** `guides/backends/local.md` -- add `## Installation` stub ("Built-in -- no extra dependencies")
- [ ] **T-18** `guides/backends/memory.md` -- add `## Installation` stub; review whether extra sections should follow standard ones
- [ ] **T-19** Audit all 6 backend pages: ensure core sections (Installation, Usage, Options, Capabilities, Caveats, See also) appear in consistent order

---

## 7. Admonition type (AF-049)

- [ ] **T-20** `docs-src/api/models.md` line 3 -- convert lone `!!! tip` to `!!! note`, or accept as intentional

---

## Summary

| # | Item | Files | AF-ID |
|---|------|-------|-------|
| T-01..T-06 | Normalize dash convention | 6 | AF-041 |
| T-07..T-10 | Add missing "See also" sections | 4 | AF-042 |
| T-11 | Unify "See also" format | 22 | AF-042 |
| T-12..T-14 | Unify table boolean style | 6 | AF-043 |
| T-15 | Convert blockquotes to admonitions | 1 | AF-044 |
| T-16 | Clarify `--` in extensions table | 1 | AF-046 |
| T-17..T-19 | Harmonize backend page structure | 6 | AF-047 |
| T-20 | Lone `!!! tip` admonition | 1 | AF-049 |

**Total: 20 items across 10 actionable findings.** (AF-051 was a false positive; AF-052 is a non-issue.)
