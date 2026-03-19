# Documentation Cross-Link Rules & Compliance Audit

**Date:** 2026-03-19
**Status:** Proposal — for discussion
**Supersedes:** Initial draft on branch `claude/add-doc-links-HqSzw`

---

## Motivation

`sdd/DOCUMENTATION.md` § 4 defines cross-linking requirements and minimums
per page. Audit 004 (AF-042) standardised the `## See also` format as
Pattern B. Despite these rules existing, compliance is inconsistent — most
API reference pages and all example pages violate the minimums.

This proposal does two things:

1. **Codifies four concrete cross-linking rules** (derived from the existing
   requirements in DOCUMENTATION.md § 4, lines 64–79).
2. **Audits current compliance** and proposes a phased fix plan.

---

## The Four Rules

These rules restate `DOCUMENTATION.md` § 4 "Required cross-links" and
"Minimum per page" as enforceable checklist items.

### Rule 1 — Guide → API reference

> If a guide references any code entity (class, function, error, extension
> module), its `## See also` section must link to the corresponding API
> reference page.

*Source: DOCUMENTATION.md line 68 ("Guide → API method it uses") and
line 77 ("Every how-to guide links to at least one API reference page").*

### Rule 2 — API reference → Guide

> If an API reference page documents something that has a corresponding
> guide, the page must link to that guide — either inline or in a
> `## See also` section.

*Source: DOCUMENTATION.md line 70 ("API method → guide that explains it")
and line 79 ("Every API class page links to its primary guide").*

### Rule 3 — Source link for examples & showcases

> If any example script, showcase folder, or notebook is mentioned anywhere
> in docs, a link to the source on GitHub must be present.

*Source: DOCUMENTATION.md lines 57–60 (two-site rule: source files link to
GitHub). Omitting the source link violates the content-type URL policy.*

### Rule 4 — Linked names in tables

> If table **header rows or key-column cells** contain names of backends,
> extensions, or other entities documented in the API reference or guides,
> those names should be links — not plain text.

**Scope clarification:** This applies to header rows and the first
(identifying) column of comparison tables — the cells where a name serves
as a label. It does **not** apply to every incidental mention of a backend
name in prose-style cells or footnotes, which would create link noise.

*Authority: This is a **new rule**, not a restatement of DOCUMENTATION.md.
Line 72 ("Backend guide → capabilities: link to matrix row") covers one
specific direction but does not generalise to all tables. If accepted, this
rule should be added to DOCUMENTATION.md § 4 "Required cross-links" table
as a new row.*

---

## Format Standard

All `## See also` sections use **Pattern B** (AF-042 decision):

```markdown
## See also

- [Guide name](../relative-path.md) — one-line description
- [Source: `examples/foo.py`](https://github.com/haalfi/remote-store/blob/master/examples/foo.py)
```

Within the docs site: **relative links**. To source files: **GitHub URLs**.
See DOCUMENTATION.md § 4 lines 57–62.

---

## Compliance Audit

### Rule 1 — Guide → API reference

**Status: Compliant.** All guide pages have `## See also` sections linking
to at least one API reference page. This was achieved in BK-007 (PR #211).

No action required.

### Rule 2 — API reference → Guide

**Status: 23 pages have no guide link (Rule 2 violation); 7 pages have
guide links in ad-hoc format and are missing example/source links
(format + Rule 3 gap).**

32 API reference pages total. The 7 backend API pages have inline guide
links (e.g., "see the [S3 Backend Guide](../../backends/s3.md)") — so they
partially satisfy Rule 2 — but use an ad-hoc format, not the standard
`## See also` section, and lack example/source links (Rule 3). All other
25 non-exempt pages have no guide links at all (23 are non-compliant with
Rule 2; 2 are exempt).

| Category | Pages | Current state | Compliant? |
|---|---|---|---|
| Core API (`store`, `path`, `config`, `registry`, `models`, `errors`, `capabilities`, `sftp-utils`) | 8 | No guide links | No |
| Extension API (`batch`, `cache`, `glob`, `observe`, `transfer`, `arrow`, `dagster`, `otel`, `streams`, `partition`, `pydantic`, `yaml`, `integrity`) | 13 | Bare `:::` directives only | No |
| Extension index | 1 | No cross-links | No |
| Backend index | 1 | No cross-links | No |
| Backend API pages | 7 | Inline link to guide (ad-hoc format, no `## See also`, no example/source links) | No |
| API index (`api/index.md`) | 1 | Hub page with links to all sub-pages | Yes (exempt — navigation, not content) |
| Backend `backend.md` | 1 | Abstract base — no corresponding guide | Yes (exempt) |

Rule 2 non-compliant: 8 + 13 + 1 + 1 = **23 pages** (no guide link at all).
Format + Rule 3 gap: **7 backend pages** (have guide links in ad-hoc format,
need conversion to `## See also` and addition of example/source links).
Total needing work: **30 pages** (32 − 2 exempt).

**Fix plan:**

- **Core + Extension API + index pages (23 pages):** Add `## See also`
  section with guide link + example page link (where a corresponding
  guide/example exists).
- **Backend API pages (7 pages):** Convert inline links to `## See also`
  format for consistency. Add example page + GitHub source links where
  missing. This keeps all API pages structurally uniform — the whole point
  of a consistency proposal.

Mapping for core API pages:

| API page | Guide link | Example link |
|---|---|---|
| `api/store.md` | [Getting Started](getting-started.md), [Concurrency](concurrency.md) | [Quickstart](examples/quickstart.md) |
| `api/path.md` | [Getting Started](getting-started.md) | [Path Model](examples/path-model.md) |
| `api/config.md` | [Retry](retry.md), [Security](security-model.md) | [Configuration](examples/configuration.md), [Retry Policy](examples/retry-policy.md) |
| `api/registry.md` | [Choosing a Backend](choosing-a-backend.md) | [Configuration](examples/configuration.md) |
| `api/models.md` | [Getting Started](getting-started.md) | [File Operations](examples/file-operations.md) |
| `api/capabilities.md` | [Capabilities Matrix](capabilities-matrix.md) | [Capabilities & Errors](examples/capabilities-and-errors.md) |
| `api/errors.md` | [Troubleshooting](troubleshooting.md) | [Error Handling](examples/error-handling.md) |
| `api/sftp-utils.md` | [SFTP Backend](backends/sftp.md) | [SFTP Backend example](examples/sftp-backend.md) |

Mapping for extension API pages:

| API page | Guide link | Example link |
|---|---|---|
| `api/extensions/batch.md` | [Batch Operations](batch-operations.md) | [Batch Operations](examples/batch-operations.md) |
| `api/extensions/transfer.md` | [Transfer Operations](transfer-operations.md) | [Transfer Operations](examples/transfer-operations.md) |
| `api/extensions/glob.md` | [Glob Pattern Matching](glob-pattern-matching.md) | [Glob Pattern Matching](examples/glob-pattern-matching.md) |
| `api/extensions/cache.md` | [Cache](cache.md) | [Caching](examples/caching.md) |
| `api/extensions/observe.md` | [Observe](observe.md) | [Observe Hooks](examples/observe-hooks.md) |
| `api/extensions/otel.md` | [Observe](observe.md) | [OTel Tracing](examples/otel-tracing.md) |
| `api/extensions/arrow.md` | [PyArrow Adapter](pyarrow-adapter.md) | [PyArrow Adapter](examples/pyarrow-adapter.md) |
| `api/extensions/dagster.md` | [Dagster](dagster.md) | [Dagster IO Manager](examples/dagster-io-manager.md), [Medallion Dagster](examples/medallion-dagster.md) |
| `api/extensions/streams.md` | — (no dedicated guide) | [Streaming IO](examples/streaming-io.md) |
| `api/extensions/partition.md` | [Data Lake Patterns](data-lake-patterns.md) | — |
| `api/extensions/pydantic.md` | [Extensions](extensions.md) | [Config Loaders](examples/config-loaders.md) |
| `api/extensions/yaml.md` | [Extensions](extensions.md) | [Config Loaders](examples/config-loaders.md) |
| `api/extensions/integrity.md` | — (no dedicated guide) | — |

### Rule 3 — Source link for examples & showcases

**Status: Non-compliant in two areas.**

**Area A — Example doc pages (27 of 28 non-index pages):**
No example page links to its Python source on GitHub. Each page is a bare
snippet include with no `## See also` footer.

The 28th page, `docs-src/examples/index.md`, is a navigation hub listing
all examples with links to their doc pages and a GitHub link to the
notebooks folder. It is **exempt** — index pages are navigation, not
content, and already link outward.

Current pattern:
```markdown
# Quickstart

Minimal config, write, and read.

\`\`\`python
--8<-- "examples/quickstart.py"
\`\`\`
```

Required addition (per DOCUMENTATION.md line 73 "Example page → guide for
deeper reading" + two-site rule):

```markdown
## See also

- [Getting Started](../getting-started.md) — step-by-step guide
- [Source: `examples/quickstart.py`](https://github.com/haalfi/remote-store/blob/master/examples/quickstart.py)
```

**Area B — Showcase folder link (1 page):**
`docs-src/examples/medallion-dagster.md` links to the research doc but not
to the showcase source folder:

```
https://github.com/haalfi/remote-store/tree/master/examples/medallion_dagster/
```

Mapping for example pages:

| Example page | Guide link | Source path |
|---|---|---|
| `quickstart.md` | [Getting Started](getting-started.md) | `examples/quickstart.py` |
| `file-operations.md` | [Getting Started](getting-started.md) | `examples/file_operations.py` |
| `streaming-io.md` | — | `examples/streaming_io.py` |
| `atomic-writes.md` | [Concurrency](concurrency.md) | `examples/atomic_writes.py` |
| `configuration.md` | [Choosing a Backend](choosing-a-backend.md) | `examples/configuration.py` |
| `config-loaders.md` | [Extensions](extensions.md) | `examples/config_loaders.py` |
| `error-handling.md` | [Troubleshooting](troubleshooting.md) | `examples/error_handling.py` |
| `capabilities-and-errors.md` | [Capabilities Matrix](capabilities-matrix.md) | `examples/capabilities_and_errors.py` |
| `path-model.md` | — | `examples/path_model.py` |
| `store-child.md` | — | `examples/store_child.py` |
| `memory-backend.md` | [Memory Backend](backends/memory.md) | `examples/memory_backend.py` |
| `http-backend.md` | [HTTP Backend](backends/http.md) | `examples/http_backend.py` |
| `s3-backend.md` | [S3 Backend](backends/s3.md) | `examples/backends/s3_backend.py` |
| `s3-pyarrow-backend.md` | [S3-PyArrow Backend](backends/s3-pyarrow.md) | `examples/backends/s3_pyarrow_backend.py` |
| `sftp-backend.md` | [SFTP Backend](backends/sftp.md) | `examples/backends/sftp_backend.py` |
| `azure-backend.md` | [Azure Backend](backends/azure.md) | `examples/backends/azure_backend.py` |
| `batch-operations.md` | [Batch Operations](batch-operations.md) | `examples/batch_operations.py` |
| `transfer-operations.md` | [Transfer Operations](transfer-operations.md) | `examples/transfer_operations.py` |
| `glob-pattern-matching.md` | [Glob Pattern Matching](glob-pattern-matching.md) | `examples/glob_pattern_matching.py` |
| `caching.md` | [Cache](cache.md) | `examples/caching.py` |
| `observe-hooks.md` | [Observe](observe.md) | `examples/observe_hooks.py` |
| `otel-tracing.md` | [Observe](observe.md) | `examples/otel_tracing.py` |
| `pyarrow-adapter.md` | [PyArrow Adapter](pyarrow-adapter.md) | `examples/pyarrow_adapter.py` |
| `dagster-io-manager.md` | [Dagster](dagster.md) | `examples/dagster_io_manager.py` |
| `medallion-dagster.md` | [Dagster](dagster.md), [Data Lake Patterns](data-lake-patterns.md) | `examples/medallion_dagster/` (folder) |
| `retry-policy.md` | [Retry](retry.md) | `examples/retry_policy.py` |
| `health-check.md` | [Health Check](health-check.md) | `examples/health_check.py` |

### Rule 4 — Linked names in tables

**Status: Non-compliant in 6 files, 8+ tables.**

| File | Table | Location | Plain-text names |
|---|---|---|---|
| `capabilities-matrix.md` | Capability matrix | Header row | Local, Memory, HTTP, S3, S3-PyArrow, SFTP, Azure |
| `choosing-a-backend.md` | Trade-offs at a glance | First column (key) | Local, Memory, S3, S3-PyArrow, SFTP, Azure, HTTP |
| `concurrency.md` | move() atomicity, summary | First column (key) | Local, S3, S3-PyArrow, Azure (HNS), Azure (non-HNS), SFTP |
| `health-check.md` | Per-backend ping strategy | First column (key) | Local, S3, S3-PyArrow, SFTP, Azure, Memory |
| `performance.md` | Sample results | Header row | Local, S3 (MinIO), S3-PyArrow, SFTP, Azure (Azurite) |
| `api/store.md` | Backend Behavior Matrix | Header row | Local, S3, S3-PyArrow, SFTP, Azure, Memory |

Backend names should link to their guide page (e.g.,
`[Local](backends/local.md)`).

Note: `concurrency.md` has backend names in body cells (first column), not
headers. These are in scope because they serve as row keys — the identifying
label for each row. Incidental mentions of backend names in other columns or
prose are **not** in scope.

**Adjacent finding (not Rule 4):** `architecture.md` lists extension module
names (`ext.batch`, `ext.glob`, `ext.observe`, etc.) as code spans in prose
without linking to their API reference pages. This is a Rule 2 gap (API
entities mentioned without links), not a table issue. It can be addressed
alongside Phase 2 or as a separate follow-up.

---

## Implementation Plan

All phases are independently mergeable. Gate every PR with
`hatch run docs-build` (strict mode) — it catches broken relative links.

### Phase 1 — Example page See also sections (27 pages)

Add `## See also` footer to every example page with guide link(s) and
GitHub source link, per the mapping table above.

Split into up to 3 PRs for reviewability:

- **PR 1a:** Core examples (10 pages: quickstart through store-child)
- **PR 1b:** Backend examples (6 pages: memory-backend through azure-backend)
- **PR 1c:** Extension + showcase examples (11 pages: batch-operations
  through health-check, including medallion-dagster source link fix)

Low risk — purely additive.

### Phase 2 — API reference See also sections (30 pages)

Add `## See also` section to core API (8), extension API (13 + index),
and backend API (7 + index) pages, per the mapping tables above. Backend
pages: convert existing inline links to `## See also` format and add
example/source links.

Split into up to 2 PRs:

- **PR 2a:** Core API + extension API pages (23 pages)
- **PR 2b:** Backend API pages — format conversion (7 pages)

Low risk — purely additive.

### Phase 3 — Table header/cell links (6 files)

Replace plain-text backend names in table headers and key-column cells
with links to guide pages.

Single PR. Medium risk — widens markdown table lines. Review readability
of raw markdown before merging.

### Phase 4 — Add Rule 4 to DOCUMENTATION.md

If Phase 3 is accepted, add Rule 4 ("Linked names in tables") to
DOCUMENTATION.md § 4 "Required cross-links" table as a new row, making
it an official project convention.

---

## Scope Summary

| Phase | Files | PRs | Type of change |
|---|---|---|---|
| Phase 1 | 27 | 1a, 1b, 1c | Add `## See also` to example pages |
| Phase 2 | 30 | 2a, 2b | Add `## See also` to API ref pages |
| Phase 3 | 6 | 1 | Link plain-text names in tables |
| Phase 4 | 1 | 1 | Codify Rule 4 in DOCUMENTATION.md |
| **Total** | **64** | **up to 7** | |

All changes are additive (no code changes, no removals).

---

## Maintenance Cost

Adding ~57 `## See also` sections creates ~57 new link targets to maintain.

**Mitigations:**

- **Relative links within docs:** `hatch run docs-build` (strict mode)
  catches all broken relative links at build time. This is already in CI.
- **GitHub source URLs:** `mkdocs build --strict` does **not** validate
  external URLs. If an example file is renamed or moved, the GitHub link
  silently breaks. Options:
  - **Accept the risk** — example files rarely move, and the link text
    includes the filename, making stale links easy to spot.
  - **Follow-up: add a link checker** — e.g., `mkdocs-linkcheck` plugin or
    a CI step running `lychee` against the built site. This is out of scope
    for this proposal but would catch GitHub URL rot.
- **Ripple-check coverage:** `sdd/CLAUDE-REFERENCE.md` already requires
  checking example and guide pages when API symbols change. Adding "check
  See also links" to the ripple-check table would formalise this.

---

## What This Proposal Does NOT Include

- **Inline code-entity links in guide prose** (e.g., wrapping every
  `NotFound` in `[NotFound](api/errors.md#...)`). This creates maintenance
  overhead — anchor-based links depend on mkdocstrings' auto-generated IDs
  and break on renames. The See also footer pattern is sufficient for
  navigation.

- **Guide-level structural changes.** All guides already have compliant
  `## See also` sections (achieved in BK-007). No guide changes needed.

- **Docstring cross-links.** Adding "See also" or "Raised by" sections
  inside Python docstrings is a code change tracked separately.
