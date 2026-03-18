# Development Backlog

Active work items and ideas. Completed items live in
[BACKLOG-DONE.md](BACKLOG-DONE.md).

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

## How this file works

**Status legend:** `[ ]` pending · `[~]` in progress · `[x]` done

**Ordering:** newest first within each section.

**Completing work:**

- Fully done → move to `BACKLOG-DONE.md` (same commit as the code change).
- Partially done → split: ship the done part to `BACKLOG-DONE.md` under its
  original ID, create a new ID here for the remaining work, and link both.

**ID prefixes:**

| Prefix | Meaning |
|--------|---------|
| `BL-NNN` | Release blocker — must resolve before next PyPI publish. |
| `BK-NNN` | Committed backlog work, queued behind blockers. |
| `BUG-NNN` | Confirmed defect with reproduction steps. |
| `ID-NNN` | Idea — not evaluated, not committed to. |

---

## Release Blockers

*(none)*

---

## Backlog (Prioritized)

---

## Known Bugs

*(none)*

---

## Ideas

### Integrations

- [~] **ID-018 — conda-forge publishing**
  Recipe, CI validation, release checklist steps all done.
  - Done: [recipe](../packaging/conda-forge/recipe.yaml),
    [conda-recipe workflow](../.github/workflows/conda-recipe.yml),
    staged-recipes PR `conda-forge/staged-recipes#32401` (CI green).
  - Blocked: waiting for conda-forge reviewer approval. When merged: add
    `conda install -c conda-forge remote-store` to README.

- [~] **ID-013 — Async Store / Backend API**
  Async version of Store and Backend for async frameworks (FastAPI, aiohttp).
  - Done: [research](research/research-async-store-api.md),
    [ADR-0012](adrs/0012-async-store-backend-api.md) draft,
    [spec 029](specs/029-async-store-backend-api.md) draft.
  - Remaining:
    - **Second research round** (required before implementation):
      sync API has evolved significantly since initial research; async
      would nearly double codebase, package surface, and docs; unclear
      if target audience (citizen developers) benefits; unclear if
      sync + async belong in the same package.
    - Spec 029 amendments: add `SyncBackendAdapter` streaming write
      conversion (materialize `AsyncIterator[bytes]` → `bytes`), add
      `AsyncMemoryBackend` section (ASYNC-060..063), add explicit
      `open_atomic` deferral note, add `check_health()` / `ping()`
      async equivalents.
    - Implementation Phase 1: core async surface.
    - Implementation Phase 2: native async backends.
    - Implementation Phase 3: async extensions.

- [ ] **ID-083 — Dagster extension v2: ConfigurableResource + IOManagerFactory**
  Follow-up to [ID-075](BACKLOG-DONE.md#post-v0170).
  Remaining features deferred from v1:
  - `DagsterStoreResource` (`ConfigurableResource`)
  - `RemoteStoreIOManager` (`ConfigurableIOManagerFactory`)
  - `teardown_after_execution()`

  [Research](research/research-dagster-extension.md),
  [showcase architecture](research/research-medallion-dagster-showcase.md).

### Documentation & Developer Experience

- [~] **ID-090 — Docs landing page (replace README include)**
  The docs homepage (`docs-src/index.md`) currently includes `README.md` 1:1.
  Replace it with a purpose-built landing page: concise orientation with a
  mermaid architecture diagram, the six key messages (Store-as-folder, zero
  deps, proven libs, backend-native API, extensions alongside, bring your own),
  and navigation links. Not a pitch, not a tutorial — an orientation for someone
  who already clicked through.
  - Done: [revised plan with complete draft](plans/plan-docs-landing-page.md)
    — open questions resolved, all link paths verified, full page content ready.
  - Next: apply draft to `docs-src/index.md`, verify mermaid + strict build.

- [ ] **ID-057 — Tested code snippets in docs (single-source snippets)**
  All code snippets in the docs site should come from real, tested Python
  source files — not hand-written markdown fences. One or more "snippet
  scripts" (e.g. `examples/snippets/`) contain named regions
  (`# snippet: quickstart-read` / `# end-snippet`). A mkdocs hook or
  `pymdownx.snippets` pulls regions into docs at build time. CI runs the
  snippet scripts as part of `hatch run all` to guarantee they stay valid.
  Inspired by Rust rustdoc, Go Example functions, Java `@snippet` tags.
  [Research](research/research-example-testing.md).

- [ ] **ID-058 — Auto-generate example docs wrappers via mkdocs-gen-files**
  Extend `docs-src/scripts/gen_pages.py` to scan `examples/*.py`, extract
  the module docstring, and generate `docs-src/examples/<name>.md` wrappers
  automatically. Eliminates the class of "forgot to add a wrapper" bugs
  (see AF-022).
  The existing API reference pages are already auto-generated this way.
  Each generated wrapper should also include links to relevant API reference
  pages at the bottom (e.g. caching example links to `ext.cache` reference).
  Also: add a CI/build-time check that every symbol in `__all__` has a
  matching `:::` directive in `docs-src/api/*.md` and a row in
  `docs-src/api/index.md`.

- [ ] **ID-066 — PR preview deployments**
  Deploy PR previews to Cloudflare Pages, Netlify, or GitHub Pages artifacts.
  Inspired by FastAPI's Cloudflare Pages pattern. Infrastructure decision needed.
  [Research](research/research-fastapi-docs.md) P6.

- [ ] **ID-067 — griffe-typingdoc for `Annotated[T, Doc("...")]` docstrings**
  Only relevant if migrating from Google-style docstrings to PEP 727
  `Annotated[T, Doc("...")]`. Not recommended near-term.
  [Research](research/research-fastapi-docs.md) P5.

### Core API
