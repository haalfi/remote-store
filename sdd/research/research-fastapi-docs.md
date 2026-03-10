# Research: FastAPI Documentation & CI/CD Patterns

**Item ID:** (none -- exploratory research)
**Date:** 2026-03-10
**Context:** Examining FastAPI docs toolchain for improvements applicable to remote-store.

---

## 1. Overview and Motivation

FastAPI's documentation is widely regarded as best-in-class for Python
libraries. This research examines how FastAPI achieves color-highlighted type
annotations in its API reference, its documentation toolchain, and its CI/CD
patterns — with the goal of identifying improvements applicable to
`remote-store`.

---

## 2. FastAPI Documentation Stack

### 2.1 Core Toolchain

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

### 2.2 How Color-Highlighted Type Annotations Work

The API reference pages (e.g. `/reference/apirouter/`) use a four-layer system.

**Layer 1 — Minimal markdown source.** Each reference page is just a few lines:

```markdown
# `APIRouter` class

::: fastapi.APIRouter
    options:
        members:
            - websocket
            - include_router
            ...
```

The `::: fastapi.APIRouter` directive tells mkdocstrings to introspect the
class and render its full signature, parameters, and docstrings.

**Layer 2 — mkdocstrings configuration.** The key options in `mkdocs.yml`:

```yaml
plugins:
  mkdocstrings:
    handlers:
      python:
        options:
          separate_signature: true      # Signature as highlighted code block
          signature_crossrefs: true     # Type names become clickable links
          show_symbol_type_heading: true # "class"/"method" badges
          show_symbol_type_toc: true    # Symbol types in TOC
          unwrap_annotated: true        # Shows base type, not Annotated[...]
          merge_init_into_class: true
          members_order: source
          extensions:
            - griffe_typingdoc
```

The two critical options for colored types:

- `separate_signature: true` — renders the signature as a **separate Pygments-
  highlighted Python code block** with CSS class `doc-signature`.
- `signature_crossrefs: true` — converts type names into clickable hyperlinks
  with distinct coloring.

**Layer 3 — Rendering pipeline** (inside `mkdocstrings-python`):

1. Format the signature string (line breaks, indentation)
2. Stash cross-references (replace `<autoref>` HTML with placeholder keys)
3. Pygments highlight with `language="python"`, `classes=["doc-signature"]`
4. Fix token classes (ensure function name gets CSS class `nf`)
5. Restore cross-references (replace placeholders back with `<a>` links)

This produces HTML like:

```html
<pre class="doc-signature highlight"><code>
<span class="nf">add_api_route</span><span class="p">(</span>
    <span class="n">path</span><span class="p">:</span>
    <span class="n"><a href="...">str</a></span>
<span class="p">)</span> <span class="o">-></span>
<span class="n"><a href="...">None</a></span>
</code></pre>
```

**Layer 4 — Theme CSS.** Material for MkDocs provides built-in Pygments CSS
that colors the token classes (`nf`, `n`, `nb`, `p`, `o`, etc.). No custom CSS
is needed for the colored types themselves. FastAPI adds Fira Code font and
terminal animation CSS, but these are cosmetic extras.

### 2.3 Build Scripts

FastAPI uses a Typer-based CLI (`scripts/docs.py`) for multi-language doc
builds with `multiprocessing.Pool` parallelism. Config inheritance via
`INHERIT:` in per-language `mkdocs.yml` files. Not relevant for remote-store
(single language).

---

## 3. FastAPI CI/CD Patterns

### 3.1 Docs Build & Deployment

- **Build:** `dorny/paths-filter` → language matrix → per-language MkDocs build
  → artifact upload
- **Deploy:** `workflow_run` trigger → download artifacts → Cloudflare Pages
  (production for master, preview URLs for PRs)
- **Gate:** `re-actors/alls-green` aggregation for branch protection

### 3.2 Testing

| Pattern | How |
|---|---|
| Path filtering | `dorny/paths-filter` skips tests when only docs changed |
| OS × Python matrix | Ubuntu/macOS/Windows × 3.10–3.14 × highest/lowest deps |
| Upstream testing | Tests against Starlette git main |
| uv caching | `astral-sh/setup-uv` with `enable-cache: true` |
| Coverage | Multi-platform merge, `--fail-under=100` |
| Redistribution | Builds sdist → extracts → runs tests |

### 3.3 Publishing

Triggered by GitHub Release. Uses `uv build` + `uv publish` with OIDC trusted
publishing (`id-token: write`, no stored API tokens).

---

## 4. Gap Analysis: remote-store vs FastAPI Patterns

Revalidated against remote-store `master` (v0.15.0, commit e1f25b3).

### 4.1 Already in Place (no action needed)

| Pattern | remote-store Status |
|---|---|
| mkdocstrings[python] | `>=0.27` in `[docs]` extra and hatch deps |
| mkdocs-material | `>=9.5` with light/dark toggle |
| `content.code.copy` | Enabled in `mkdocs.yml` |
| `navigation.instant`, `navigation.tabs`, `toc.follow` | Enabled |
| Minimal `:::` reference pages | Already used (e.g. `docs-src/api/store.md`) |
| Path filtering (`dorny/paths-filter`) | In `ci.yml` with `code`/`docs` filters |
| Gate job | Custom bash aggregation in `ci.yml` |
| uv in CI | `astral-sh/setup-uv@v6` + `uv pip install` everywhere |
| OIDC trusted publishing | In `publish.yml` |
| Cross-platform CI | Windows + macOS matrix |
| Versioned docs (mike) | Configured with deploy workflows |

### 4.2 Actionable Improvements

**Priority 1 — Colored type annotations (high impact, 4-line change).**
Add to existing mkdocstrings options in `mkdocs.yml`:

```yaml
separate_signature: true
signature_crossrefs: true
show_symbol_type_heading: true
show_symbol_type_toc: true
```

No dependency changes needed — already supported by `mkdocstrings >=0.27`.

**Priority 2 — Use `uv` in docs deployment (consistency, 2-line change).**
`docs.yml` still uses `pip install` while all other workflows use `uv`. Change
to `astral-sh/setup-uv@v6` + `uv pip install`.

**Priority 3 — Fira Code font (cosmetic).** Add `docs-src/css/custom.css`:

```css
@import url(https://cdn.jsdelivr.net/npm/firacode@6.2.0/distr/fira_code.css);
:root { --md-code-font: "Fira Code", monospace; }
```

Plus `extra_css: [css/custom.css]` in `mkdocs.yml`.

**Priority 4 — Additional Material features (minor).** Consider adding
`navigation.tabs.sticky`, `search.suggest`, `search.highlight`.

**Priority 5 — `griffe-typingdoc` (future).** Only relevant if remote-store
migrates from Sphinx-style docstrings to `Annotated[T, Doc("...")]` (PEP 727).
Not recommended as a near-term change.

**Priority 6 — PR preview deployments (infrastructure decision).** FastAPI
deploys PR previews to Cloudflare Pages. Could be added with Cloudflare,
Netlify, or GitHub Pages artifacts.

---

## 5. Conclusions

The biggest bang-for-buck improvement is adding `separate_signature: true` and
`signature_crossrefs: true` to the existing mkdocstrings config — a 4-line
change that produces FastAPI-quality colored, clickable type annotations in the
API reference with zero new dependencies.

Most of FastAPI's CI/CD patterns (path filtering, uv, OIDC publishing, gate
jobs, cross-platform testing) are already adopted by remote-store. The
remaining gaps are minor consistency fixes (`uv` in docs deploy) and
nice-to-haves (PR preview deployments).
