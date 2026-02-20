# ADR-0006: Documentation Architecture — Source of Truth and Audiences

## Status

Accepted

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

## Decision

### Principle: `docs/` is a representation, never the source

All publishable content lives in source directories. The `docs/` directory
is **fully generated** — every file is either a wrapper directive or produced
by the build script. `docs/` is gitignored.

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
The build script wraps them into `docs/` for the published site.

### Build process

A build script (or MkDocs hook) generates the entire `docs/` tree:

1. Creates wrapper files with `include-markdown` directives pointing to
   source locations (`README.md`, `guides/`, `sdd/`, `examples/`).
2. Generates navigation index pages from `mkdocs.yml` structure.
3. Copies or symlinks assets as needed.

The generated `docs/` directory is excluded from version control via
`.gitignore`.

### Where to put new content — decision rule

> If you can read it on GitHub and it makes sense without MkDocs, it belongs
> in a source directory. If it only makes sense as part of the site build,
> it belongs in the build script.

## Consequences

- **Single source of truth.** Every piece of content has exactly one home.
  No drift between source and `docs/` copies.
- **`docs/` is gitignored.** Eliminates an entire class of "forgot to update
  the wrapper" bugs and keeps the repo clean.
- **GitHub-readable.** All guides, specs, and examples render correctly on
  GitHub without a docs build.
- **Clear contributor guidance.** New content goes into the appropriate source
  directory; the build script handles presentation.
- **`guides/` grows organically.** New topics (streaming patterns, error
  handling, migration guides) are added as standalone files without touching
  build infrastructure.
- **Build script becomes load-bearing.** The script that generates `docs/`
  must be maintained and tested. A broken script means a broken docs site.
