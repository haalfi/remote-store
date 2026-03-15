# Fix List: Documentation Structural Issues

Companion to **Audit 004** (`audit-004-docs-structural-consistency.md`).
**Remove this file after all items are resolved.**

---

## 1. Dash convention (AF-041, AF-045)

**Decision:** Standardize on UTF-8 em dash `—` (U+2014). Typographically correct, and the earlier MkDocs/cp1252 mojibake concern no longer reproduces. `.editorconfig` enforces `charset = utf-8`.

The 6 files below already use `—` — they are *correct*. The remaining `docs-src/` and guide files that use `--` need converting to `—`.

- [x] **T-01** `guides/data-lake-patterns.md` — already uses `—` ✓
- [x] **T-02** `guides/dagster.md` — already uses `—` ✓
- [x] **T-03** `guides/batch-operations.md` — already uses `—` ✓
- [x] **T-04** `guides/backends/sftp.md` — already uses `—` ✓
- [x] **T-05** `guides/backends/memory.md` — already uses `—` ✓
- [x] **T-06** `guides/backends/s3-pyarrow.md` — already uses `—` ✓
- [x] **T-01b** Converted remaining `--` → `—` across 33 files (319 replacements)

---

## 2. "See also" format (AF-042)

**Decision:** Pattern B (`## See also` heading + bullet list). Shows in page TOC, easier to extend.

- [x] **T-07** `guides/concurrency.md` — added See also section
- [x] **T-08** `guides/health-check.md` — added See also section
- [x] **T-09** `guides/performance.md` — added See also section
- [x] **T-10** `guides/extensions.md` — added See also section
- [x] **T-11** Converted all 12 Pattern A files to Pattern B; 9 existing Pattern B files already consistent

---

## 3. Table boolean values (AF-043)

Project convention: `Yes` / `—` (em dash), never `Yes` / `No`.

- [x] **T-12** `docs-src/capabilities-matrix.md` — replaced HTML entity checkmarks with `Yes` / `—`
- [x] **T-13** `guides/cache.md` — replaced bold `**No**` with `—`
- [x] **T-14** Normalized all tables: `docs-src/api/store.md`, `guides/concurrency.md`, `README.md`

---

## 4. Blockquotes to admonitions (AF-044)

- [x] **T-15** `guides/backends/sftp.md` — converted three `>` blockquotes to `!!! warning` / `!!! note` admonitions

---

## 5. Extensions table (AF-046)

- [x] **T-16** `guides/extensions.md` — Extra column uses `*(none)*` for built-in, `—` for not available

---

## 6. Backend page structure (AF-047, AF-048, AF-050)

- [x] **T-17** `guides/backends/local.md` — added `## Installation` stub
- [x] **T-18** `guides/backends/memory.md` — added `## Installation` stub
- [x] **T-19** Audited all 6 backend pages — core sections (Installation, Usage, Options, ..., See also) consistent; backend-specific sections vary appropriately

---

## 7. Admonition type (AF-049)

- [x] **T-20** `docs-src/api/models.md` — removed (content already in `_models.py` module docstring and each class docstring; triple redundancy on rendered page). AF-049 admonition type was correct (`!!! tip`)

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
