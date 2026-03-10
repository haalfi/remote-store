# FastAPI Documentation & CI/CD Research

Research into how [FastAPI](https://github.com/fastapi/fastapi) builds beautiful
docs and optimizes its GitHub workflows. Findings applicable to `remote-store`.

---

## 1. Documentation Stack

### Core Toolchain

| Tool | Version | Purpose |
|------|---------|---------|
| **mkdocs-material** | `>=9.7.0` | Theme — Material for MkDocs |
| **mkdocstrings[python]** | `>=0.30.1` | Auto-generates API reference from docstrings + type hints |
| **griffe-typingdoc** | `>=0.3.0` | Griffe extension — extracts `Annotated[T, Doc("...")]` docs |
| **griffe-warnings-deprecated** | `>=1.1.0` | Shows deprecation warnings in generated docs |
| **pymdownx** (via Material) | bundled | Syntax highlighting, tabs, admonitions, code copy |
| **mkdocs-macros-plugin** | `>=1.5.0` | Template variables (sponsors, people YAML data) |
| **mkdocs-redirects** | `>=1.2.1` | URL redirects for moved pages |
| **cairosvg + pillow** | latest | Social card image generation |

### Additional Docs Dependencies

| Tool | Purpose |
|------|---------|
| **markdown-include-variants** | `>=0.0.8` — include external files/code snippets |
| **mdx-include** | `>=1.4.1` — extended markdown includes |
| **black** | `>=25.1.0` — used by mkdocstrings to format signatures |
| **jieba** | `>=0.42.1` — Chinese text segmentation for CJK search |
| **python-slugify** | `>=0.8.0` — custom slug generation for header permalinks |
| **typer** | `>=0.21.1` — CLI framework for `scripts/docs.py` |

### How the Color-Highlighted Type Annotations Work

The beautiful API reference pages (e.g. `/reference/apirouter/`) are produced by
a **four-layer system**:

#### Layer 1: Markdown Source (minimal)

The actual markdown for an API reference page is just a few lines:

```markdown
# `APIRouter` class

::: fastapi.APIRouter
    options:
        members:
            - websocket
            - include_router
            - get
            - put
            ...
```

The `::: fastapi.APIRouter` directive tells **mkdocstrings** to introspect
the class and render its full signature, parameters, and docstrings.

#### Layer 2: mkdocstrings Configuration

The magic configuration in `mkdocs.yml`:

```yaml
plugins:
  mkdocstrings:
    handlers:
      python:
        options:
          extensions:
            - griffe_typingdoc          # Reads Doc() from Annotated types
          show_root_heading: true       # Shows class name as heading
          show_if_no_docstring: true    # Renders even undocumented members
          preload_modules:
            - httpx                     # Pre-load for cross-reference resolution
            - starlette
          inherited_members: true       # Shows inherited methods
          members_order: source         # Preserves source-code ordering
          separate_signature: true      # Signature on its own line (KEY!)
          unwrap_annotated: true        # Unwraps Annotated[X, ...] to show X
          filters:
            - '!^_'                     # Hide private members
          merge_init_into_class: true   # __init__ params shown on class
          docstring_section_style: spacy  # Compact docstring sections
          signature_crossrefs: true     # Type names become clickable links (KEY!)
          show_symbol_type_heading: true  # Shows "class", "method" badges
          show_symbol_type_toc: true      # Symbol types in table of contents
```

**Key options for the colored types:**

- `separate_signature: true` — puts the full signature on its own styled line,
  making parameter types visually prominent.
- `signature_crossrefs: true` — makes type annotations into hyperlinks with
  distinct coloring (the source of the "colored types" effect).
- `unwrap_annotated: true` — cleans up `Annotated[str, ...]` to show just `str`.
- `show_symbol_type_heading: true` — adds "class"/"method"/"attribute" badges.

#### Layer 3: Theme + Syntax Highlighting

```yaml
theme:
  name: material
  palette:
    - scheme: default        # Light mode
      primary: teal
      accent: amber
    - scheme: slate          # Dark mode
      primary: teal
      accent: amber
  features:
    - content.code.annotate  # Inline code annotations
    - content.code.copy      # Copy button on code blocks
    - navigation.instant     # SPA-like navigation
    - navigation.tabs        # Top-level tabs
    - navigation.tabs.sticky
    - search.highlight
    - search.suggest

markdown_extensions:
  pymdownx.highlight:
    line_spans: __span       # Enables per-line highlighting
  pymdownx.inlinehilite: null  # Inline code highlighting
  pymdownx.superfences:
    custom_fences:
      - name: mermaid        # Mermaid diagram support
        class: mermaid
        format: !!python/name:pymdownx.superfences.fence_code_format ''
```

#### Layer 4: Custom CSS

```css
/* Fira Code for all code blocks */
@import url(https://cdn.jsdelivr.net/npm/firacode@6.2.0/distr/fira_code.css);
@import url(https://fonts.googleapis.com/css2?family=Noto+Color+Emoji&display=swap);

:root {
    --md-code-font: "Fira Code", monospace, "Noto Color Emoji";
    --md-text-font: "Roboto", "Noto Color Emoji";
}
```

Plus custom terminal animation CSS (`termynal.css`) for the interactive
terminal demos on the landing page.

### Custom JavaScript

- **`termynal.js`** — animated terminal output on landing page
- **`custom.js`** — external link detection (adds arrow icons), announcement
  bar rotation
- **`init_kapa_widget.js`** — AI-powered docs search widget (Kapa.ai)

### MkDocs Lifecycle Hooks (`scripts/mkdocs_hooks.py`)

Custom hooks plugged into MkDocs build lifecycle:

- **`on_config`**: Sets Material theme language from docs directory name
- **`on_files`**: Resolves missing translations by falling back to English
  source (`EnFile` class)
- **`on_nav`**: Renames navigation sections based on `index.md` page titles
- **`on_page_markdown`**: Injects "missing translation" banners for
  untranslated pages

---

## 2. Build Scripts & Process

### `scripts/docs.py` — Typer CLI

A Typer-based CLI that orchestrates multi-language doc builds:

| Command | Purpose |
|---------|---------|
| `build-lang <lang>` | Build docs for one language via `mkdocs build` |
| `build-all` | Build all languages in parallel (`multiprocessing.Pool`, 4x CPU cores) |
| `live [lang]` | Live-reload dev server (`mkdocs serve` on port 8008) |
| `serve` | Simple HTTP server to preview full multi-language build |
| `langs-json` | Output language codes as JSON (used by CI matrix) |
| `new-lang <lang>` | Scaffold a new translation directory |
| `update-languages` | Update `mkdocs.yml` with all language alternatives |
| `generate-readme` | Generate README.md from `docs/en/docs/index.md` |
| `add-permalinks` | Add/update header permalink slugs in markdown |
| `generate-docs-src-versions` | Auto-generate Python 3.9/3.10 code variants using Ruff |

### Build Chain

```
pyproject.toml (dependency groups)
    └─> hatch / uv install docs group
        └─> scripts/docs.py build-lang en
            └─> mkdocs build (reads docs/en/mkdocs.yml)
                ├─> mkdocstrings introspects Python source
                ├─> griffe_typingdoc reads Annotated[T, Doc()]
                ├─> pymdownx.highlight does syntax coloring
                ├─> social plugin generates OG images
                └─> outputs to site/
```

### Config Inheritance

```
docs/en/mkdocs.env.yml    # Base/shared config (env-level)
docs/en/mkdocs.yml        # English config (INHERIT: ../en/mkdocs.env.yml)
docs/de/mkdocs.yml        # German (inherits same base, overrides language)
docs/es/mkdocs.yml        # Spanish ...
```

---

## 3. CI/CD Workflows

### 3.1 Docs Build (`build-docs.yml`)

**Triggers:** Push to master, PR open/sync.

**4-job pipeline:**

1. **`changes`** — `dorny/paths-filter` checks if docs-related files changed.
   Skips the entire pipeline if nothing relevant changed.
2. **`langs`** — Runs `scripts/docs.py langs-json` to get language list.
3. **`build-docs`** — **Matrix job across all languages** (each language builds
   in parallel as a separate CI job):
   - MkDocs card cache per language (`actions/cache` with key
     `mkdocs-cards-{lang}-{ref}`)
   - uv dependency caching via `astral-sh/setup-uv` with `enable-cache: true`
   - Each language's built site uploaded as artifact `docs-site-{lang}`
4. **`docs-all-green`** — `re-actors/alls-green` aggregation for branch
   protection.

### 3.2 Docs Deployment (`deploy-docs.yml`)

**Trigger:** `workflow_run` — fires after Build Docs completes.

**Target: Cloudflare Pages** (not GitHub Pages).

- Downloads all `docs-site-*` artifacts from triggering build
- Deploys via `cloudflare/wrangler-action@v3`
- Master branch → production; PRs → preview deployments with unique URL
- Posts deployment status on PR with preview URL

### 3.3 Publishing (`publish.yml`)

Remarkably simple — 6 steps:

1. Triggered by **GitHub Release creation**
2. `uv build` creates sdist + wheel
3. `uv publish` uploads to PyPI
4. Auth via **OIDC trusted publishing** (no stored API tokens!)

```yaml
permissions:
  id-token: write  # For OIDC trusted publishing
```

### 3.4 Test Workflow (`test.yml`)

**Key optimizations:**

| Optimization | How |
|---|---|
| **Path filtering** | `dorny/paths-filter` skips tests when only docs changed |
| **Matrix strategy** | OS (Ubuntu/macOS/Windows) x Python (3.10-3.14) x resolution (highest/lowest) |
| **Dual resolution** | Tests with newest AND oldest compatible deps |
| **Upstream testing** | Tests against Starlette git main (catches upstream breaks) |
| **uv caching** | `astral-sh/setup-uv` with `enable-cache: true` |
| **100% coverage** | Multi-platform coverage merge, `--fail-under=100` |
| **Branch gate** | `alls-green` aggregates all job statuses into one check |
| **Benchmarks** | CodSpeed runs on Ubuntu/Python 3.13 |
| **Redistribution test** | Separate workflow builds sdist → extracts → runs tests |

### 3.5 Other Workflows

| Workflow | Purpose |
|---|---|
| `latest-changes.yml` | Auto-updates release notes on PR merge |
| `smokeshow.yml` | Uploads coverage HTML to Smokeshow |
| `test-redistribute.yml` | Validates built packages work when installed |
| `pre-commit.yml` | Runs pre-commit with fork-safe two-path logic |

---

## 4. Key Takeaways for remote-store

### Docs Improvements

1. **Use `mkdocstrings` with `signature_crossrefs: true` and
   `separate_signature: true`** — this is the #1 thing that makes FastAPI's
   API reference look professional. Type annotations become colored, clickable
   cross-references.

2. **Use `griffe_typingdoc`** — if we adopt `Annotated[T, Doc("...")]` pattern
   (PEP 727 style), parameter docs live right next to the type hints in code.

3. **Add Fira Code font** — small CSS change, big visual improvement for code.

4. **Enable Material features** — `content.code.copy`, `navigation.instant`,
   `search.suggest`, `navigation.tabs.sticky`.

5. **Minimal reference markdown** — just `::: remote_store.RemoteStore` with
   member filters. The plugin does all the heavy lifting.

### CI/CD Improvements

1. **Path filtering with `dorny/paths-filter`** — skip docs build when only
   code changed, skip tests when only docs changed. Saves CI minutes.

2. **`alls-green` aggregation** — single branch protection check that handles
   skipped jobs cleanly.

3. **OIDC trusted publishing** — eliminates PyPI API token secrets.

4. **uv for everything** — FastAPI moved from pip to uv for install, lock,
   build, and publish. Significantly faster CI.

5. **Cloudflare Pages for docs** — PR preview deployments with unique URLs.

6. **`workflow_run` chaining** — decouples build from deploy, keeps workflows
   focused.

### Minimal Adoption Path

To get FastAPI-quality API reference docs with colored types, the minimum
changes are:

```toml
# pyproject.toml additions
"mkdocstrings[python] >=0.30.1"
"griffe-typingdoc >=0.3.0"
```

```yaml
# mkdocs.yml additions
plugins:
  mkdocstrings:
    handlers:
      python:
        options:
          separate_signature: true
          signature_crossrefs: true
          show_root_heading: true
          show_if_no_docstring: true
          merge_init_into_class: true
          members_order: source
          show_symbol_type_heading: true
          show_symbol_type_toc: true
```

```css
/* docs/css/custom.css */
@import url(https://cdn.jsdelivr.net/npm/firacode@6.2.0/distr/fira_code.css);
:root { --md-code-font: "Fira Code", monospace; }
```

```markdown
<!-- docs/reference/remote-store.md -->
# `RemoteStore`

::: remote_store.RemoteStore
```

---

*Research conducted 2026-03-10 from FastAPI repository at
github.com/fastapi/fastapi (master branch).*
