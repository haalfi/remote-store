# Audit 004 -- Documentation Structural Consistency

**Date:** 2026-03-15
**Scope:** All files rendered to GH Pages / RTD (`docs-src/`, `guides/`), master branch at commit `526673c` (v0.17.0). Excludes `sdd/` internal docs.
**Method:** Five parallel AI agents audited the full doc surface for: (1) duplicated content within pages, (2) broken/missing links, (3) style/representation inconsistencies, (4) dash/em-dash handling, (5) table value representations. Human consolidated, spot-checked, and verified against a full `hatch run docs-build` (strict mode, zero warnings).
**Focus:** Structure, visual consistency, and link integrity. NOT content correctness or accuracy (covered by Audit 003).

**Finding IDs assigned:** AF-041 through AF-050, AF-052. (AF-051 was a false positive -- see below.)

---

## Executive Summary

| Category | Count | Severity |
|----------|-------|----------|
| Medium | 4 | Inconsistencies visible to readers across multiple pages |
| Low | 6 | Single-file style deviations or minor template drift |
| False positive | 1 | Verified non-issue after code review (AF-051) |
| None (informational) | 1 | Verified non-issue (AF-052) |

---

## Clean Areas (no issues found)

| Area | Status |
|------|--------|
| Duplicated content within pages | Clean -- include-markdown architecture prevents duplication |
| Links at build time | Clean -- all internal links resolve (`gen_pages.py` + `rewrite-relative-urls=false`) |
| Code block language tags | Consistent (`python`, `bash`, `toml`, `text`) |
| Installation commands | Consistent (`pip install "remote-store[extra]"` with quoted names) |
| API reference formatting | Consistent (`::: remote_store.Class` autodoc syntax) |
| Heading levels | Correct (all pages start at `#`, subsections at `##`) |

---

## Findings

### AF-041. Mixed dash convention: `--` vs `—` in prose -- *confirmed, Medium*

Six guide files use the Unicode em dash `—` (U+2014) while all `docs-src/` originals and ~15 other guide files use `--` (double hyphen). Both render acceptably, but the inconsistency is visible in source and some renderers leave `--` as two literal hyphens.

**Files using `—`:**

| File | Lines |
|------|-------|
| `guides/data-lake-patterns.md` | 4, 32, 49, 62, 69, 96, 215, 302-307 |
| `guides/dagster.md` | 12, 67, 123, 147, 149, 154 |
| `guides/batch-operations.md` | 8, 10, 37, 115, 120 |
| `guides/backends/sftp.md` | 108-110 |
| `guides/backends/memory.md` | 3, 43 |
| `guides/backends/s3-pyarrow.md` | 60 |

All other docs use `--`.

**Decision (2026-03-15):** Standardize on UTF-8 em dash `—` (U+2014). Tested on Windows cp1252 with MkDocs strict build — renders correctly. The earlier mojibake concern (see DEVELOPMENT_STORY.md) was environment-specific and no longer reproduces. `.editorconfig` and `.vscode/settings.json` now enforce `charset = utf-8`.

### AF-042. Two incompatible "See also" formats -- *confirmed, Medium*

End-of-page cross-reference sections use two incompatible patterns:

**Pattern A** (12 files): `**See also:**` bold paragraph after a `---` horizontal rule, links on continuation lines separated by ` -- `. Renders as a compact inline block. Used by: `transfer-operations`, `batch-operations`, `backends/sftp`, `backends/azure`, `backends/s3-pyarrow`, `pyarrow-adapter`, `backends/memory`, `backends/local`, `backends/s3`, `glob-pattern-matching`, `observe`, `cache`.

**Pattern B** (10 files): `## See also` heading with a bullet list. Renders as a full TOC entry with bulleted links. Used by: `data-lake-patterns`, `retry`, `dagster`, `backends/index`, `choosing-a-backend`, `troubleshooting`, `migration`, `docs-src/capabilities-matrix`, `docs-src/security-model`, `docs-src/architecture`.

**Missing entirely** (4 files): `guides/concurrency.md`, `guides/health-check.md`, `guides/performance.md`, `guides/extensions.md`.

### AF-043. Table boolean values: three representations -- *confirmed, Medium*

Tables expressing "supported / not supported" use three different styles:

1. **HTML entity checkmarks** (`&#x2705;` / `&#x274C;`) in `docs-src/capabilities-matrix.md` (lines 12-20)
2. **Plain text** `Yes` / `No` in backend capability tables (`guides/backends/sftp.md:116-125`, `guides/backends/azure.md:113-122`), the API store behavior matrix (`docs-src/api/store.md:224-230`), and `guides/concurrency.md:28-37`
3. **Bold `**No**`** mixed with plain `Yes` in `guides/cache.md` line 45

The capabilities matrix and backend capability tables describe the *same data* (which capabilities each backend supports) but look completely different.

**Project convention** (not yet applied anywhere): `Yes` / `--` (dash), never `Yes` / `No`.

### AF-044. Blockquotes used as admonitions in SFTP guide -- *confirmed, Medium*

`guides/backends/sftp.md` lines 127-131 uses three `>` blockquotes for caveats ("Atomic write caveat", "Move fallback", "TOCTOU on `overwrite=False`"). All other behavioral notes in the docs use MkDocs admonitions (`!!! note`, `!!! warning`). The visual difference is jarring because this guide is included into `docs-src/backends/sftp.md` which also renders API admonitions below it.

### AF-045. "See also" link-description dashes mixed -- *confirmed, Low*

Within Pattern B "See also" sections, `guides/data-lake-patterns.md` (lines 302-307) and `guides/dagster.md` (lines 147-149) use `—` for link descriptions, while all other Pattern B files use `--`. This compounds AF-041.

### AF-046. Extensions table overloads `--` for two meanings -- *confirmed, Low*

`guides/extensions.md` lines 10-19: the "Extra" column uses `--` to mean "no extra dependency", and the "Guide" / "Example" columns use `--` to mean "not available". Two distinct semantics, same glyph, also collides with the em-dash punctuation convention.

### AF-047. Backend page template drift -- *confirmed, Low*

Backend guide pages follow a common template but each has drifted:
- Local and Memory omit `## Installation` (built-in).
- Memory adds `## Folder Semantics`, `## Thread Safety`, `## Testing with MemoryBackend`.
- SFTP adds `## Connection Behaviour`, `## Escape Hatch`.
- Azure adds `## Authentication`, `## HNS vs Non-HNS`, `## Streaming`, `## Escape Hatch`, `## Local Development with Azurite`.
- S3/S3-PyArrow have `## When to use S3-PyArrow vs S3`, `## Escape Hatch`.

Core sections (Installation, Usage, Options, Capabilities, Caveats, See also) should appear in the same order with the same names; extra sections after.

### AF-048. Local backend missing `## Installation` -- *confirmed, Low*

`guides/backends/local.md` has no `## Installation` section. Other built-in backends (`memory.md`) also lack it. Add "Built-in -- no extra dependencies" stub for structural consistency with remote backend pages.

### AF-049. Lone `!!! tip` admonition -- *confirmed, Low*

`docs-src/api/models.md` line 3 is the only `!!! tip` in the entire documentation. All other admonitions are `!!! note` (8 instances) or `!!! warning` (1 instance).

### AF-050. `memory.md` has unique extra sections -- *confirmed, Low*

`guides/backends/memory.md` has `## Folder Semantics`, `## Thread Safety`, and `## Testing with MemoryBackend` -- sections no other backend page has. Consider folding into standard sections or accepting as intentional.

### AF-051. Orphan page: `rfc-template.md` not in nav -- *false positive*

Initially reported as an orphan page. On review, `rfc-template.md` is intentionally
published by `scripts/gen_pages.py` (lines 153-155) and linked from `CONTRIBUTING.md`.
It is excluded from auto-generated nav by `skip_stems={"rfc-template"}` (line 76)
because it is a reference template, not an actual RFC. **No action needed.**

### AF-052. Code-comment `#` in sftp.md code block -- *verified non-issue, None*

`guides/backends/sftp.md` line 96: `# Development / testing` appears inside a ` ```python ` code block. Renders correctly as a Python comment. No action needed.

---

## Action Items

| ID | Severity | File(s) | Issue |
|----|----------|---------|-------|
| AF-041 | Medium | 6 guide files | Mixed `--` vs `—` dash convention in prose |
| AF-042 | Medium | 22 guide + docs-src files | Two "See also" formats; 4 files missing it entirely |
| AF-043 | Medium | `capabilities-matrix.md`, 4 backend guides, `cache.md` | Three boolean table-value representations |
| AF-044 | Medium | `guides/backends/sftp.md` | Blockquotes instead of admonitions for caveats |
| AF-045 | Low | `guides/data-lake-patterns.md`, `guides/dagster.md` | `—` in "See also" link descriptions (compounds AF-041) |
| AF-046 | Low | `guides/extensions.md` | `--` overloaded for "no dep" and "not available" in table |
| AF-047 | Low | 6 backend guide files | Backend page template drift (section order/naming) |
| AF-048 | Low | `guides/backends/local.md`, `guides/backends/memory.md` | Missing `## Installation` stub |
| AF-049 | Low | `docs-src/api/models.md` | Lone `!!! tip` admonition |
| AF-050 | Low | `guides/backends/memory.md` | Unique extra sections not in other backend pages |
| AF-051 | -- | -- | False positive (template page, intentionally published) |
| AF-052 | None | `guides/backends/sftp.md` | Code-comment `#` in code block (non-issue) |
