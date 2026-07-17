# ADR-0007: Three-Tier Documentation Architecture with docs-src/ and Literate Nav

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
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

### Principle: three-tier content architecture

<!-- adr:decision -->
Supersedes ADR-0006's two-tier model.  Content lives in one of three places,
determined by its nature:

1. **Source directories** — content readable on GitHub without MkDocs
   (`README.md`, `guides/`, `sdd/`, `examples/`, `src/`).
2. **`docs-src/`** — site-specific authored content: landing pages, index
   pages, `include-markdown` wrappers, `mkdocstrings` directives, `.tmpl`
   templates for dynamic index pages, and per-section `_nav.yml` files.
   Checked into version control.
3. **Build hook (`scripts/gen_pages.py`)** — pure mechanics: filesystem
   scanning, template filling, link rewriting, navigation assembly.
   No authored prose.
<!-- /adr:decision -->

### Content homes by type

| Content type | Source location | Audience |
|---|---|---|
| Project introduction, installation, quick start | `README.md` | Both |
| User-facing guides (backends, streaming, patterns) | `guides/` | Package users |
| Runnable code examples | `examples/` | Package users |
| API docstrings | Python source (`src/`) | Both |
| Design specs | `sdd/specs/` | Developers |
| Architecture decision records | `sdd/adrs/` | Developers |
| Design process & overview | `sdd/` (root files) | Developers |
| Contributor workflow | `CONTRIBUTING.md` | Developers |
| Release history | `CHANGELOG.md` | Both |
| Development narrative | `DEVELOPMENT_STORY.md` | Developers |
| Site landing pages, section indexes, API ref layout | `docs-src/` | Site-specific |
| Dynamic index templates (specs, ADRs) | `docs-src/**/_index.tmpl` | Site-specific |
| Section navigation ordering | `docs-src/**/_nav.yml` | Site-specific |

### The `docs-src/` directory

MkDocs reads `docs-src/` as its `docs_dir`.  It contains:

- **Include wrappers** that pull content from source directories via
  `include-markdown` (e.g., `changelog.md` includes `../CHANGELOG.md`).
- **Directive pages** for `mkdocstrings` API reference and `pymdownx.snippets`
  example embeds.
- **Static authored pages** like `api/index.md` (API overview) and
  `examples/index.md` (examples overview) — curated site content that has
  no meaningful standalone existence on GitHub.
- **Templates** (`_index.tmpl`) whose static preamble is authored in Markdown;
  dynamic rows are injected by the build hook.
- **Navigation files** (`_nav.yml`) declaring the ordered list of pages in
  each section.  The build hook reads these recursively to assemble the
  site-wide `SUMMARY.md`.

### Build process

The MkDocs "literate" plugin stack replaces the monolithic build script:

- **`mkdocs-gen-files`** runs `scripts/gen_pages.py` during the build to
  create virtual pages (spec/ADR/RFC wrappers, filled templates, link-
  rewritten pages, copied assets) and assemble `SUMMARY.md` from the
  per-section `_nav.yml` files.
- **`mkdocs-literate-nav`** reads the generated `SUMMARY.md` for navigation,
  eliminating the static `nav:` block in `mkdocs.yml`.
- **`mkdocs-section-index`** maps section landing pages to their parent
  nav entry.

No pre-build step is required.  No `docs/` directory is generated on disk.

### Navigation convention

Each directory in `docs-src/` may contain a `_nav.yml` file:

```yaml
# docs-src/backends/_nav.yml
- Local: local.md
- S3: s3.md
- S3-PyArrow: s3-pyarrow.md
- SFTP: sftp.md
- Azure: azure.md
```

- Entries are `label: file.md` for leaf pages.
- Entries ending with `/` (e.g., `Specs: specs/`) are subsections — the build
  hook recurses into that directory's `_nav.yml`.
- Sections without a `_nav.yml` that match a scanned directory (`design/specs`,
  `design/adrs`) are populated automatically from the filesystem scan.
- Adding a page to a section means creating the `.md` file and adding one
  line to the section's `_nav.yml`.  No Python is touched.

### Where to put new content — decision rule

> If you can read it on GitHub and it makes sense without MkDocs, it belongs
> in a source directory.  If it is authored prose that only makes sense as
> part of the documentation site, it belongs in `docs-src/`.  If it is pure
> build mechanics (scanning, templating, link rewriting), it belongs in the
> build hook.

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
