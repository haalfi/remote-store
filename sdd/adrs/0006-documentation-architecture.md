# ADR-0006: Documentation Architecture — Source of Truth and Audiences

## Status

Accepted (amended)

## Context

The project serves two distinct audiences:

1. **Package users** — install `remote-store`, need to configure backends, use
   the API, follow guides.
2. **Developers / contributors** — need to understand design decisions, specs,
   and repo structure as a precondition for contribution.

Content was accumulating in `docs/` with mixed provenance: some files were
thin `include-markdown` wrappers pointing to source files elsewhere, while
others contained original content found nowhere else in the repo. This
created a contradiction — `docs/` was treated as a build artifact in some
places and as the source of truth in others.

The `docs/` directory is consumed by MkDocs to produce the published
documentation site. MkDocs requires a specific directory layout, navigation
structure, and directive syntax (`include-markdown`, `mkdocstrings`,
`pymdownx.snippets`). These are **presentation concerns**, not content
concerns.

### Problems with original content living in `docs/`

- **Redundancy risk.** Content drifts between the "real" source (`README.md`,
  `sdd/`, `examples/`) and the `docs/` copy.
- **Wrong abstraction level.** Detailed backend guides, getting-started
  tutorials, and design specs are valuable independently of MkDocs — they
  should be readable on GitHub, in editors, and offline.
- **Unclear ownership.** Contributors don't know whether to edit `docs/s3.md`
  or create a source file and wrap it.

### Problems with site-specific content living in the build script

The original decision placed all presentation logic in a monolithic build
script (`scripts/generate_docs.py`, 574 lines).  This created a new problem:
**site-specific authored content** — API reference overviews, example index
pages, section landing pages — was embedded as Python string literals.  These
pages are curated prose that a human writes, but they only make sense in the
context of the published documentation site.  Storing them inside Python
strings made them hard to discover, edit, and review.

The build script was also responsible for navigation mapping, link rewriting,
template rendering, and asset copying — mixing content with mechanics.

## Decision

### Principle: three-tier content architecture

Content lives in one of three places, determined by its nature:

1. **Source directories** — content readable on GitHub without MkDocs
   (`README.md`, `guides/`, `sdd/`, `examples/`, `src/`).
2. **`docs-src/`** — site-specific authored content: landing pages, index
   pages, `include-markdown` wrappers, `mkdocstrings` directives, and
   `.tmpl` templates for dynamic index pages. Checked into version control.
3. **Build hook (`scripts/gen_pages.py`)** — pure mechanics: filesystem
   scanning, template filling, link rewriting, navigation generation.
   No authored prose.

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

### The `docs-src/` directory

MkDocs reads `docs-src/` as its `docs_dir`. It contains:

- **Include wrappers** that pull content from source directories via
  `include-markdown` (e.g., `changelog.md` includes `../CHANGELOG.md`).
- **Directive pages** for `mkdocstrings` API reference and `pymdownx.snippets`
  example embeds.
- **Static authored pages** like `api/index.md` (API overview) and
  `examples/index.md` (examples overview) — curated site content that has
  no meaningful standalone existence on GitHub.
- **Templates** (`_index.tmpl`) whose static preamble is authored in Markdown;
  dynamic rows are injected by the build hook.

### Audience entry points

- **Package users** enter through `README.md` (also the PyPI landing page).
  It links to `guides/` for deeper topics and `examples/` for runnable code.
- **Developers** enter through `README.md` for orientation, then navigate to
  `sdd/` for design context and `CONTRIBUTING.md` for workflow.

### The `guides/` directory

Top-level directory for all user-facing guide content — any topic that helps
a package user accomplish something. Organized by subject:

```
guides/
  backends/
    index.md          # comparison table, pluggable architecture
    local.md
    s3.md
    s3-pyarrow.md
    sftp.md
  # future topics added as needed
```

Guides are written as standalone Markdown, readable on GitHub without MkDocs.
The build hook includes them into the site via `docs-src/` wrappers.

### Build process

The MkDocs "literate" plugin stack replaces the monolithic build script:

- **`mkdocs-gen-files`** runs `scripts/gen_pages.py` during the build to
  create virtual pages (spec/ADR/RFC wrappers, filled templates, link-
  rewritten pages, copied assets).
- **`mkdocs-literate-nav`** reads a generated `SUMMARY.md` for navigation,
  eliminating the static `nav:` block in `mkdocs.yml`.
- **`mkdocs-section-index`** maps section landing pages to their parent
  nav entry.

No pre-build step is required. No `docs/` directory is generated on disk.

### Where to put new content — decision rule

> If you can read it on GitHub and it makes sense without MkDocs, it belongs
> in a source directory. If it is authored prose that only makes sense as
> part of the documentation site, it belongs in `docs-src/`. If it is pure
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
- **`guides/` grows organically.** New topics (streaming patterns, error
  handling, migration guides) are added as standalone files without touching
  build infrastructure.
- **Minimal build hook.** `scripts/gen_pages.py` handles only filesystem
  scanning, template rendering, link rewriting, and navigation generation —
  no authored content.
- **Navigation is auto-maintained.** Adding a new spec or ADR file to `sdd/`
  automatically adds it to the site navigation via the build hook's scan.
