# ADR-0007: Three-Tier Documentation Architecture with docs-src/ and Literate Nav

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | ADR-0006 |
| Superseded by | —        |
| Amends        | —        |

## Context

ADR-0006 established that `docs/` is a representation, never the source.
All publishable content lives in source directories (`README.md`, `guides/`,
`sdd/`, `examples/`, `src/`), and a build script generates the `docs/` tree.

This created an unintended consequence: **site-specific authored content** —
API reference overviews, example index pages, section landing pages — had no
home in the source directories (they don't make sense on GitHub without
MkDocs) and so were embedded as Python string literals inside the build
script (`scripts/generate_docs.py`, 574 lines).

ADR-0006's decision rule was binary: source directory or build script.  It
did not account for a third category of content — curated prose that only
makes sense in the context of the published documentation site but is still
*authored* content that a human writes and reviews.

### Problems with the ADR-0006 implementation

- **Content trapped in Python.** ~100 lines of authored prose (API Reference
  overview, Examples index, Design index, Getting Started) lived as string
  literals, making them hard to discover, edit, and diff-review.
- **Navigation in two places.** The sidebar structure was duplicated: once as
  page definitions in the Python script, once as a static 57-line `nav:`
  block in `mkdocs.yml`.
- **Mixed concerns.** The build script handled content generation, navigation
  mapping, link rewriting, template rendering, and asset copying in one
  monolithic file.
- **Manual nav maintenance.** Adding a spec or ADR required no script change
  (auto-scanned) but required a manual `mkdocs.yml` update.

## Decision

### A third content tier (supersedes ADR-0006)

Content lives in one of **three** tiers, chosen by its nature, replacing
ADR-0006's binary "source directory or build script" rule:

- **Source directories** (`README.md`, `guides/`, `sdd/`, `examples/`, `src/`):
  anything readable on GitHub without MkDocs.
- **`docs-src/`**: site-only authored prose with no standalone existence on
  GitHub, such as API-reference overviews, section landing pages, and example
  indexes. Version-controlled.
- **Build hook**: pure mechanics (scanning, template filling, link rewriting,
  nav assembly). No authored prose.

**Why the third tier:** ADR-0006's two-way rule left authored prose that only
makes sense inside the published site with no home, so ~100 lines of it were
trapped as Python string literals in the build script: undiscoverable, hard to
edit, hard to review. The tier exists to house exactly that category.

*Reverse if* site-only authored prose stops being a distinct category
(everything becomes either GitHub-readable source or pure mechanics),
collapsing back to ADR-0006's two tiers.

### The placement rule

> Readable on GitHub without MkDocs goes in a **source directory**. Authored
> prose meaningful only as part of the docs site goes in **`docs-src/`**. Pure
> build mechanics go in the **build hook**.

The full content-type-to-location map is reference material owned by the
placement authority, [`AUTHORING.md`](../AUTHORING.md); this rule applies it
rather than restating it.

### The build hook tier holds mechanism, never prose

The build hook replaced ADR-0006's monolithic script with a literate MkDocs
plugin stack that carries no authored content and no hand-maintained
navigation: section ordering lives beside the content in `_nav.yml`, not in a
central `nav:` block. The mechanism itself (plugin choices,
`_nav.yml`-to-`SUMMARY.md` assembly, link rewriting) is specified in
[spec 047](../specs/047-docs-framework-tooling.md) (DOCFRAME-001, DOCFRAME-007)
and pinned in `pyproject.toml`. This ADR fixes only the tier's boundary:
mechanics carry no authored prose.

*Reverse if* the "mechanics tier carries no authored content" boundary is
itself abandoned. The concrete mechanism is spec 047's to evolve; ADR-0027 has
since narrowed it to a single bridge.

## Consequences

- **Single source of truth.** Every piece of content has exactly one home.
  No drift between source and site copies.
- **No generated artifact in version control.** The `docs/` directory no
  longer exists; MkDocs builds directly from `docs-src/` plus virtual files.
- **GitHub-readable.** All guides, specs, and examples render correctly on
  GitHub without a docs build.
- **Clear contributor guidance.** New content goes into the appropriate source
  directory or `docs-src/`; the build hook handles only mechanics.
- **`guides/` grows organically.** New topics are added as standalone files
  without touching build infrastructure.
- **Minimal build hook.** `scripts/gen_pages.py` handles only filesystem
  scanning, template rendering, link rewriting, and navigation assembly —
  no authored content, no navigation metadata.
- **Navigation is co-located.** Each section's page ordering lives in its
  own `_nav.yml`, next to the content it describes.  Adding a new spec or
  ADR to `sdd/` automatically adds it to the site navigation.
- **ADR-0006's core insight is preserved.** Source content still lives in
  source directories.  The new `docs-src/` tier fills the gap ADR-0006
  left for site-specific authored content.
