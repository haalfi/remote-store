# Audit-012: Documentation Structure — Post-ID-174 Layout

**Date:** 2026-04-30
**Scope:** Documentation structure, navigation, link integrity, and page-generation logic. No source code.
**Reference:** BK-165

---

## Scope & Methodology

Audit basis: thirteen rules established and agreed before the audit began. They derive
from the post-ID-174 three-layer page-emission system: static `docs-src/` Markdown,
gen-files virtual pages, and include-markdown wrappers.

### Vocabulary: the three hierarchies

Every docs page has three independent identifiers that need not match:

| Hierarchy | Definition | Example |
|-----------|------------|---------|
| **Repo path** | Where content originates on disk | `sdd/specs/batch.md` |
| **Nav position** | Label and place in the navigation tree | Explanation > Design > Specs > Batch |
| **URL path** | Rendered address on the docs site | `/design/specs/batch/` |

Changes to any one layer must be traceable through all three. Discrepancies between
them are defects.

### Audit rules

| ID | Rule | MUST / SHOULD |
|----|------|---------------|
| R1 | All `.md` files in the repo must have no broken relative links | MUST |
| R2 | Rendered docs must not contain broken links | MUST |
| R3 | Version switching must not produce 404s | MUST |
| R4 | All authored Markdown reaches rendered docs | SHOULD |
| R5 | Anchored files stay at their repo path | MUST |
| R6 | Navigation is purely Diataxis | MUST |
| R7 | URL paths correspond to navigation position | MUST |
| R8 | Generation is convention-driven, not mapping-driven | MUST |
| R9 | Mappings are minimal and bounded | MUST |
| R10 | No duplicated content | MUST |
| R11 | Wrapper pattern is principled | MUST |
| R12 | One mechanism controls nav order per section | MUST |
| R13 | Excluded files are auditable | MUST |

**R6 classification note:** SDD content (specs, ADRs, RFCs, research, audits, process
documents) is classified as Explanation under Diataxis — it deepens and broadens
understanding of the system's design and history. No non-Diataxis top-level nav sections
are permitted.

Files inspected: `mkdocs.yml`, `scripts/gen_pages.py`, `docs-src/_nav.yml`,
`docs-src/_link_map.yml`, `docs-src/api/_nav.yml`, `docs-src/design/_nav.yml`,
all `docs-src/design/*.md`, `docs-src/changelog.md`, `docs-src/index.md`,
`docs-src/explanation/architecture.md`. Full `.md` inventory across `sdd/`,
`docs-src/`, root, and `examples/` cross-referenced against gen-files scan
and nav entries.

---

## Summary

| Rule | Title | Status |
|------|-------|--------|
| R1 | Repo links must not be broken | **FINDING** |
| R2 | Rendered docs must not contain broken links | **FINDING** |
| R3 | Version switching must not produce 404s | **WARNING** |
| R4 | All authored Markdown reaches rendered docs | **FINDING** |
| R5 | Anchored files stay at their repo path | PASS |
| R6 | Navigation is purely Diataxis | **FINDING** |
| R7 | URL paths correspond to navigation position | **FINDING** |
| R8 | Generation is convention-driven | PARTIAL |
| R9 | Mappings are minimal and bounded | **FINDING** |
| R10 | No duplicated content | PASS |
| R11 | Wrapper pattern is principled | **FINDING** |
| R12 | One mechanism controls nav order per section | PASS |
| R13 | Excluded files are auditable | **FINDING** |

**Totals:** 7 rules with findings, 1 warning, 1 partial, 4 passes.

### Findings index

| ID | Rule | Severity | Description |
|----|------|----------|-------------|
| F-01 | R1 | Major | Links to virtual pages (`design/adrs/*`, `design/specs/*`, etc.) broken in GitHub repo browser — systemic |
| F-02 | R1 | Minor | Include-markdown wrapper files render as raw Jinja text on GitHub |
| F-03 | R2 | Major | Link validation set to `warn` — broken links do not fail the build |
| F-04 | R2, R4 | Major | `development-story.md` referenced in nav but has no source file or `_link_map.yml` entry |
| F-05 | R6 | Minor | Tutorial is a nav sub-item under "Getting Started", not a top-level Diataxis quadrant |
| F-06 | R6 | Minor | Changelog listed under Reference section |
| F-07 | R6 | Minor | "Further Reading" is a fifth top-level nav section outside Diataxis |
| F-08 | R6, R7 | Major | Design nested under Explanation in nav but URL prefix is `design/`, not `explanation/...` |
| F-09 | R7 | Major | Design section URL `design/` contradicts its nav position under Explanation (duplicates F-08 consequence) |
| F-10 | R7 | Minor | Changelog renders at `/changelog/`, contradicting its nav position under Reference |
| F-11 | R9 | Minor | `_link_map.yml` comment says "repo-root files" but one entry points to `sdd/000-process.md` |
| F-12 | R11 | Major | Three distinct mechanisms render `sdd/` files into docs; no unifying rule |
| F-13 | R13 | Major | No central exclusion list; excluded files not auditable without reading four systems |
| W-01 | R3 | — | No build-time enforcement of cross-version link safety |

---

## Findings

### F-01: Virtual page links break in the GitHub repo browser (Major, R1)

**Affected files:** `docs-src/explanation/architecture.md` (lines 86, 104, 112) and
likely other `docs-src/` files that cross-link into the design section.

`docs-src/explanation/architecture.md` contains links of the form:

```
[ADR 0008](../design/adrs/0008-extension-architecture.md)
```

The file `docs-src/design/adrs/0008-extension-architecture.md` does not exist on disk.
`docs-src/design/adrs/` contains only `_index.tmpl`. The link resolves to a gen-files
virtual page at MkDocs build time and works in the rendered docs, but when a crawler,
search engine, or agent navigates the GitHub repo and follows the link, GitHub returns 404.

This is systemic: any `docs-src/` file that links to `design/adrs/*`, `design/specs/*`,
`design/rfcs/*`, `design/research/*`, or `design/audits/*` has the same problem. The
full extent requires a link scan across all `docs-src/` files.

---

### F-02: Include-markdown wrapper files render as raw Jinja text on GitHub (Minor, R1)

**Affected files:** `docs-src/design/content-rules.md`, `docs-src/design/design.md`,
`docs-src/design/documentation.md`, `docs-src/design/testing.md`.

Each of these files contains only a Jinja2 directive:

```
{%
   include-markdown "../../sdd/DOCUMENTATION.md"
%}
```

In the GitHub repo browser, Jinja2 directives are not processed — they render as literal
text. A reader navigating to these files on GitHub sees only the raw template syntax, not
the intended content. Per R1's rationale, agents and crawlers that navigate the repo
receive no information from these files.

Note: no `[text](path)` link is involved, so this is not a broken link in the strict
sense. It is a complete failure of the repo-navigation experience for these four pages.

---

### F-03: Link validation is `warn`, not `error` — broken links do not fail the build (Major, R2)

**Location:** `mkdocs.yml`.

```yaml
validation:
  links:
    not_found: warn
```

With this setting, broken links in the rendered docs produce build warnings but do not
cause the build to fail. Broken links can silently ship through CI undetected. Setting
`not_found: error` would make any unresolved internal link a hard build failure.

---

### F-04: `development-story.md` referenced in nav but has no source (Major, R2, R4)

**Location:** `docs-src/_nav.yml`, Further Reading section.

```yaml
- Further Reading:
    - Overview: further/further-reading.md
    - Development Story: development-story.md
    - Contributing: contributing.md
```

`development-story.md` is listed in the nav but:

- `docs-src/development-story.md` does not exist on disk.
- No `_link_map.yml` entry maps `DEVELOPMENT_STORY.md` to this path.
- No `gen_pages.py` render function is visibly responsible for generating it.

If this page is not produced by `gen_pages.py`, the nav entry produces a broken link in
the rendered site. Confirmation requires a full read of the gen-files render functions.

---

### F-05: Tutorial appears as a sub-item, not a top-level Diataxis quadrant (Minor, R6)

**Location:** `docs-src/_nav.yml`.

```yaml
- Getting Started:
    - Tutorial: getting-started.md
    - Examples: examples/
```

Tutorial is a Diataxis quadrant and should be a top-level navigation section. Instead it
is nested as a sub-item inside a parent section labelled "Getting Started" — a label that
is not a Diataxis term. This makes the nav structure depart from Diataxis at the first
entry.

---

### F-06: Changelog listed under Reference (Minor, R6)

**Location:** `docs-src/_nav.yml`.

```yaml
- Reference:
    - API: api/
    - Features: reference/FEATURES.md
    - Capabilities Matrix: reference/capabilities-matrix.md
    - Migration: reference/migration.md
    - Changelog: changelog.md
```

Changelog is not Reference content by any Diataxis definition. A changelog is a
historical record of changes, not a description of the system's machinery.

---

### F-07: "Further Reading" is a fifth top-level section outside Diataxis (Minor, R6)

**Location:** `docs-src/_nav.yml`.

The nav contains five top-level sections: Getting Started, Guides, Reference,
Explanation, Further Reading. "Further Reading" is not a Diataxis quadrant. Per R6 no
non-Diataxis top-level sections are permitted. "Development Story" and "Contributing"
(its two entries) have no Diataxis home; their correct placement is a design decision for
the authoring guide.

---

### F-08 & F-09: Design nav position and URL prefix are misaligned (Major, R6, R7)

**Location:** `docs-src/_nav.yml` and the `design/` URL structure.

```yaml
- Explanation:
    - Architecture Overview: explanation/architecture.md
    - Performance: explanation/performance.md
    - Concurrency: explanation/concurrency.md
    - Security Model: explanation/security-model.md
    - Design: design/
```

SDD content is correctly nested under Explanation in the nav tree, consistent with the
agreed R6 classification. However, the URL prefix is `design/`, not `explanation/design/`
or `explanation/`. This creates a permanent mismatch between the two layers:

- Nav position: Explanation > Design > Specs > …
- URL: `/design/specs/batch/` (not `/explanation/specs/batch/`)

The URL implies a distinct top-level section outside Diataxis, which contradicts R6.
The nav position and URL path are misaligned, violating R7. Any internal cross-link to
SDD content uses the `design/` prefix, anchoring the inconsistency into every such link.

---

### F-10: Changelog URL contradicts its nav position under Reference (Minor, R7)

**Location:** `docs-src/changelog.md` → renders at `/changelog/`. Nav position: Reference.

`docs-src/changelog.md` renders at `/changelog/` (top-level URL), not
`/reference/changelog/`. The nav position (under Reference) and the URL (top-level) are
inconsistent.

---

### F-11: `_link_map.yml` comment contradicts its content (Minor, R9)

**Location:** `docs-src/_link_map.yml`.

The file comment:
```yaml
# Repo-root markdown files served into the docs tree.
```

The two entries:
```yaml
contributing.md:
  source: CONTRIBUTING.md       # repo-root ✓

design/process.md:
  source: sdd/000-process.md    # NOT repo-root ✗
```

`sdd/000-process.md` is not a repo-root file. The documented scope does not match one of
the two entries, making the boundary of what belongs in this file unclear.

---

### F-12: Three distinct mechanisms render `sdd/` files into docs; no unifying rule (Major, R11)

| File(s) | Mechanism |
|---------|-----------|
| `sdd/DESIGN.md`, `sdd/DOCUMENTATION.md`, `sdd/TESTING.md`, `sdd/CONTENT-RULES.md` | Static `include-markdown` wrapper in `docs-src/design/*.md` |
| `sdd/000-process.md` | `_link_map.yml` entry → `design/process.md` |
| `sdd/specs/`, `sdd/adrs/`, `sdd/rfcs/`, `sdd/research/`, `sdd/audits/` | `gen_pages.py` `render_sdd_wrappers` scan |

Three different mechanisms render `sdd/` files into the docs. The rule for which
mechanism applies to which file is not derivable from the file's location or metadata
alone — a contributor must understand all three systems to place a new `sdd/` file
correctly. This directly contradicts R11 (the wrapper pattern must be a principled
bridge, not an ad-hoc collection of approaches).

---

### F-13: No central exclusion list; excluded files not auditable (Major, R13)

Files confirmed as having no rendering path:

| File | Apparent reason |
|------|-----------------|
| `sdd/BACKLOG.md` | Internal process file |
| `sdd/BACKLOG-DONE.md` | Internal process file |
| `sdd/CLAUDE-REFERENCE.md` | Claude-specific tooling file |
| `sdd/formal/README.md` | Unknown — no rendering path found |
| `CODE_OF_CONDUCT.md` | Not rendered; not documented as excluded |
| `SECURITY.md` | Not rendered; not documented as excluded |
| `CLAUDE.md` | Not rendered; not documented as excluded |

To determine which `.md` files are intentionally excluded, a reader must
cross-reference: the `gen_pages.py` scan logic, `_link_map.yml`, all `docs-src/`
include-markdown wrappers, and `docs-src/_nav.yml`. No single location enumerates
excluded files or states the exclusion criteria. The boundary between "intentionally
excluded" and "accidentally missed" is not auditable.

---

### W-01: No build-time enforcement of cross-version link safety (R3)

Mike version management is configured correctly (`version_selector: true`,
`extra.version.provider: mike`). However, because link validation is set to `warn`
(F-03), cross-version broken links are not caught at build time. The combination of
versioned docs and silent link warnings means that a page removed in a newer version
could leave dangling references in older versioned builds with no CI signal.

---

## Rules with no findings

| Rule | Evidence |
|------|---------|
| R5 — Anchored files stay at their repo path | `sdd/`, `CHANGELOG.md`, `CONTRIBUTING.md` confirmed at canonical paths. The docs pipeline adapts to them via wrappers; no anchored file has been moved. |
| R10 — No duplicated content | All `docs-src/design/*.md` files are pure `include-markdown` wrappers — one directive each, no copied text. `docs-src/changelog.md` similarly wraps `CHANGELOG.md`. Single source of truth intact across all checked pairs. |
| R12 — One mechanism controls nav order | Nav authority chain is linear: `_nav.yml` files → `gen_pages.py nav_mod.build_summary()` → `SUMMARY.md` → literate-nav plugin. `SUMMARY.md` is the single source consumed by the plugin. No competing nav authority found. |

---

## Partial compliance

**R8 — Generation is convention-driven:** Mostly convention-based — file-system scanning
for the five SDD kinds, location-based routing for `docs-src/` files, `_link_map.yml`
with only two entries. Partially violated because three distinct mechanisms cover
`sdd/` top-level files (see F-12) without a rule derivable from file location or
metadata.
