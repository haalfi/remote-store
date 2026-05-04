# Audit-012: Documentation Structure — Post-ID-174 Layout

**Date:** 2026-04-30
**Scope:** Documentation structure, navigation, link integrity, and page-generation logic. No source code.
**Reference:** BK-165
**Closed:** 2026-05-02 (BK-167b). All findings resolved — see closure notes below each finding.

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

**R6 classification note:** "Navigation is purely Diataxis" is a project-internal design
decision, not a requirement derived from the Diataxis standard itself (which does not
prescribe how internal or process documentation should be navigated). Per project
agreement, SDD content (specs, ADRs, RFCs, research, audits, process documents) is
classified as Explanation for nav purposes — it deepens understanding of the system's
design and history. Findings against R6 report non-conformance with this project rule,
not violations of Diataxis as an external standard.

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
| R1 | Repo links must not be broken | CLOSED (BK-167b) |
| R2 | Rendered docs must not contain broken links | CLOSED (BK-167b) |
| R3 | Version switching must not produce 404s | CLOSED (BK-167b) |
| R4 | All authored Markdown reaches rendered docs | PASS |
| R5 | Anchored files stay at their repo path | PASS |
| R6 | Navigation is purely Diataxis | CLOSED (BK-167b) |
| R7 | URL paths correspond to navigation position | CLOSED (BK-167b) |
| R8 | Generation is convention-driven | CLOSED (BK-167b) |
| R9 | Mappings are minimal and bounded | CLOSED (BK-167b) |
| R10 | No duplicated content | PASS |
| R11 | Wrapper pattern is principled | CLOSED (BK-167b) |
| R12 | One mechanism controls nav order per section | PASS |
| R13 | Excluded files are auditable | CLOSED (BK-167b) |

**Totals (at close):** All 7 findings closed, warning closed. 5 passes/partials.

### Findings index

| ID | Rule | Severity | Description |
|----|------|----------|-------------|
| F-01 | R1 | Major | 4 links to virtual pages broken in GitHub repo browser: 3 in `architecture.md`, 1 in `security-model.md` |
| F-02 | R1 | Minor | Include-markdown wrapper files render as raw Jinja text on GitHub |
| F-03 | R2 | Major | Link validation set to `warn` — broken links do not fail the build |
| F-05 | R6 | Minor | Tutorial is a nav sub-item under "Getting Started", not a top-level section per project R6 rule |
| F-06 | R6 | Minor | Changelog listed under Reference; does not fit any Diataxis or project-defined nav category |
| F-07 | R6 | Minor | "Further Reading" is a fifth top-level nav section, contradicting the project's pure-Diataxis R6 rule |
| F-08 | R6, R7 | Major | Design nested under Explanation in nav but URL prefix is `design/`, not `explanation/...` |
| F-10 | R7 | Minor | Changelog renders at `/changelog/`, contradicting its nav position under Reference |
| F-11 | R9 | Minor | `_link_map.yml` comment says "repo-root files" but one entry points to `sdd/000-process.md` |
| F-12 | R11 | Major | Three distinct mechanisms render `sdd/` files into docs; no unifying rule |
| F-13 | R13 | Major | No central exclusion list; excluded files not auditable without reading four systems |
| W-01 | R3 | — | No build-time enforcement of cross-version link safety |

_F-04 and F-09 were withdrawn during review and their IDs retired: F-04 was a false
positive (the file exists on disk); F-09 duplicated F-08's consequence. Remaining IDs
are unchanged to preserve external references._

---

## Findings

### F-01: Virtual page links break in the GitHub repo browser (Major, R1)

A scan of all `docs-src/` files for links into `design/adrs/`, `design/specs/`,
`design/rfcs/`, `design/research/`, and `design/audits/` found **4 broken links across
2 files**:

| File | Line | Link |
|------|------|------|
| `docs-src/explanation/architecture.md` | 86 | `[ADR-0008](../design/adrs/0008-extension-architecture.md)` |
| `docs-src/explanation/architecture.md` | 104 | `[ADR-0002](../design/adrs/0002-config-resolution-no-merge.md)` |
| `docs-src/explanation/architecture.md` | 112 | `[ADRs](../design/adrs/index.md)` |
| `docs-src/explanation/security-model.md` | 78 | `[Spec 020: Credential Hygiene](../design/specs/020-credential-hygiene.md)` |

None of these target files exist on disk. `docs-src/design/adrs/` and
`docs-src/design/specs/` each contain only `_index.tmpl`. The links resolve to gen-files
virtual pages at MkDocs build time and work in the rendered docs, but when a crawler,
search engine, or agent navigates the GitHub repo and follows the link, GitHub returns 404.

**Closure (BK-167b → BK-171):** BK-167b updated the links to use the
`explanation/design/` URL prefix and exempted `docs-only` files from the
repo-mode link checker, deferring R1 enforcement on `docs-src/` to
`mkdocs build --strict`. That closure left R1 unverified for the GitHub
repo-browser presentation of every `docs-src/` file.

BK-171 closes F-01 honestly: every relative link in every git-tracked
`.md` (including `docs-src/**`) must resolve on disk. Authors write
on-disk paths everywhere; the mkdocs hook
([`scripts/mkdocs_hooks.py`](../../scripts/mkdocs_hooks.py)) rewrites them to docs-site
URLs at build time. The 76 docs-src links that previously pointed at
virtual destinations (e.g. `(../design/adrs/0002-...md)`) were migrated
to on-disk source paths (e.g. `(../../sdd/adrs/0002-...md)`). The
repo-mode/site-mode split in `check-links` is removed in favour of one
on-disk-only rule (DOCFRAME-008).

---

### F-02: Include-markdown wrapper files render as raw Jinja text on GitHub (Minor, R1)

**Affected files:** `docs-src/design/content-rules.md`, `docs-src/design/design.md`,
`docs-src/design/documentation.md`, `docs-src/design/testing.md`.

Each of these files contains only an `include-markdown` Jinja2 directive
that references the corresponding source file under `../../sdd/` (for
example, `docs-src/design/documentation.md` includes
`sdd/DOCUMENTATION.md`).

In the GitHub repo browser, Jinja2 directives are not processed — they render as literal
text. A reader navigating to these files on GitHub sees only the raw template syntax, not
the intended content. Per R1's rationale, agents and crawlers that navigate the repo
receive no information from these files.

Note: no `[text](path)` link is involved, so this is not a broken link in the strict
sense. It is a complete failure of the repo-navigation experience for these four pages.

**Closure (BK-167b):** All five include-markdown wrapper files deleted (DOCFRAME-005).
`sdd/AUTHORING.md`, `DOCUMENTATION.md`, `DESIGN.md`, `CONTENT-RULES.md`, `TESTING.md`
now carry explicit `dual` classification markers and are emitted directly by
`render_dual_pages` at `explanation/design/*.md`. The source files in `sdd/` render
correctly in both the repo browser and the docs site.

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

**Closure (BK-167b):** CI restores `mkdocs build --strict`, which promotes all warnings
(including `not_found: warn`) to hard failures — equivalent to `not_found: error` at the
build level. The installed MkDocs 1.x does not accept `error` as a literal config value,
but `--strict` achieves the same effect. Absorbs W-01: strict mode plus mike's
version-switch handling closes both.

---

### F-05: Tutorial is a nav sub-item, not a top-level section per project R6 rule (Minor, R6)

**Location:** `docs-src/_nav.yml`.

```yaml
- Getting Started:
    - Tutorial: getting-started.md
    - Examples: examples/
```

Per the project's R6 rule (top-level nav uses the four Diataxis quadrant labels), Tutorial
should be a top-level navigation section. Instead it is nested as a sub-item inside a
parent section labelled "Getting Started" — a label that is not a Diataxis term.

_Note: this is a non-conformance with the project's agreed nav structure, not a violation
of Diataxis as an external standard. Diataxis does not mandate specific nav labels._

**Closure (BK-167b):** `docs-src/_nav.yml` restructured: Tutorial is now a top-level
section containing Getting Started and Examples.

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

_Note: non-conformance with the project's R6 rule (no content placed in a Diataxis
section it doesn't belong to), not a violation of Diataxis itself._

**Closure (BK-167b):** Changelog moved to `reference/changelog.md` in the nav.
The Reference section is the standard home for changelogs in docs-as-code practice.
F-10 (URL mismatch) closed together: `CHANGELOG.md` now emits at `reference/changelog.md`.

---

### F-07: "Further Reading" is a fifth top-level section outside Diataxis (Minor, R6)

**Location:** `docs-src/_nav.yml`.

The nav contains five top-level sections: Getting Started, Guides, Reference,
Explanation, Further Reading. Per the project's R6 rule, no non-Diataxis top-level
sections are permitted. "Development Story" and "Contributing" (its two entries) have no
Diataxis home; their correct placement is a design decision for the authoring guide.

_Note: non-conformance with the project-internal R6 rule, not a violation of Diataxis
itself. Diataxis does not prohibit supplementary nav sections._

**Closure (BK-167b):** "Further Reading" section removed. Contributing and Development
Story moved under Explanation; both are context-providing background reading that fits
the Explanation quadrant.

---

### F-08: Design nav position and URL prefix are misaligned (Major, R6, R7)

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

_Design artifact: the `design/` URL structure and the `docs-src/` layout were
established by [ADR-0007](../adrs/0007-docs-src-literate-nav.md) (implemented in
ID-174)._

**Closure (BK-167b):** Design section moved from `design/` to `explanation/design/`.
Templates relocated to `docs-src/explanation/design/`; `render_sdd_indexes` and
`render_dual_pages` emit all content under the `explanation/design/` prefix. `_nav.yml`
updated: `Design: explanation/design/`.

---

### F-10: Changelog URL contradicts its nav position under Reference (Minor, R7)

**Location:** `docs-src/changelog.md` → renders at `/changelog/`. Nav position: Reference.

`docs-src/changelog.md` renders at `/changelog/` (top-level URL), not
`/reference/changelog/`. The nav position (under Reference) and the URL (top-level) are
inconsistent.

**Closure (BK-167b):** Closed together with F-06. `CHANGELOG.md` now carries
`<!-- doc: dual dest=reference/changelog.md -->` and is emitted by the bridge at
`/reference/changelog/`. The old `docs-src/changelog.md` wrapper is deleted.

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

**Closure (BK-167b):** `docs-src/_link_map.yml` deleted (DOCFRAME-005). Both
`CONTRIBUTING.md` and `sdd/000-process.md` now carry explicit dual markers and are
emitted by `render_dual_pages` instead.

---

### F-12: Three distinct mechanisms render `sdd/` files into docs; no unifying rule (Major, R11)

| File(s) | Mechanism | Layer |
|---------|-----------|-------|
| `sdd/DESIGN.md`, `sdd/DOCUMENTATION.md`, `sdd/TESTING.md`, `sdd/CONTENT-RULES.md` | Static authored `docs-src/design/*.md` files using the `include-markdown` MkDocs plugin. `gen_pages.py` does not write these files — `scan_include_wrappers` only detects them to populate the `LinkResolver` source map. | MkDocs plugin |
| `sdd/000-process.md` | `_link_map.yml` entry read by `render_link_rewritten` in `gen_pages.py`, which writes a virtual page at `design/process.md`. | gen-files |
| `sdd/specs/`, `sdd/adrs/`, `sdd/rfcs/`, `sdd/research/`, `sdd/audits/` | `gen_pages.py` `render_sdd_wrappers` filesystem scan, which writes virtual pages at `design/{kind}/{slug}.md`. | gen-files |

Three mechanisms, spanning two architectural layers (MkDocs plugin vs. gen-files), render
`sdd/` content into the docs. The rule for which mechanism applies to which file is not
derivable from file location or metadata alone — a contributor must understand all three
systems to place a new `sdd/` file correctly. This contradicts R11 (the wrapper pattern
must be a principled bridge, not an ad-hoc collection of approaches).

_Design artifact: the gen-files scan approach for `sdd/` kinds was specified in
[ADR-0007](../adrs/0007-docs-src-literate-nav.md) (implemented in ID-174). The
include-markdown wrapper approach for `sdd/` top-level files and the `_link_map.yml`
entry for `sdd/000-process.md` post-date that ADR and were added without a unifying
rule._

**Closure (BK-167b):** Single bridge: `scan_dual_files` + `render_dual_pages`
(DOCFRAME-001, DOCFRAME-005). All three legacy mechanisms removed. The rule is now
derivable from the file alone: every `.md` carries an explicit or directory-default
classification marker that determines whether and where it appears on the docs site.

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

_Design artifact: [ADR-0007](../adrs/0007-docs-src-literate-nav.md) documents the
scan-based discovery approach but does not define an explicit exclusion list._

**Closure (BK-167b):** Every `.md` in the repo now carries an explicit
`<!-- doc: repo-only -->`, `<!-- doc: docs-only -->`, or `<!-- doc: dual dest=... -->`
marker (or has a directory-default classification). The classification is readable from
the file itself. The PR-time gate (G-01) fails on any unclassified file, so the
boundary between intentionally excluded and accidentally missed is always auditable.

---

### W-01: No build-time enforcement of cross-version link safety (R3)

Mike version management is configured correctly (`version_selector: true`,
`extra.version.provider: mike`). However, because link validation is set to `warn`
(F-03), cross-version broken links are not caught at build time. The combination of
versioned docs and silent link warnings means that a page removed in a newer version
could leave dangling references in older versioned builds with no CI signal.

**Closure (BK-167b):** Closed by F-03 fix (`mkdocs build --strict`). `--strict` promotes `not_found: warn` to a build failure; MkDocs 1.x rejects `error` as a literal config value.
Mike's version-switch handling prevents cross-version navigation from hitting dead pages.

---

## Rules with no findings

| Rule | Evidence |
|------|---------|
| R4 — All authored Markdown reaches rendered docs | All `docs-src/` files have a rendering path. Root-level files (`CONTRIBUTING.md`, `DEVELOPMENT_STORY.md`, `CHANGELOG.md`) reach the site via `_link_map.yml` entries or `include-markdown` wrappers. Excluded files (`sdd/BACKLOG.md`, `sdd/CLAUDE-REFERENCE.md`, `CLAUDE.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`) are internal/agent tooling files, not authored user-facing documentation. |
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
