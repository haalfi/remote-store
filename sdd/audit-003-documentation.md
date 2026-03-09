# Audit 003 — Documentation Quality & Spec Compliance

**Date:** 2026-03-09
**Scope:** Full documentation site (`docs-src/`, `guides/`, `examples/`, API docstrings) audited against the authoritative `sdd/DOCUMENTATION.md` spec. Version 0.15.0, master branch.
**Method:** Built docs locally with `hatch run docs-build`. Systematic cross-reference of every section in `sdd/DOCUMENTATION.md` (§1–§13) against actual site structure, content, and source files. Guide cross-link compliance, docstring quality, README completeness, nav structure, and example coverage all checked.

**Finding IDs assigned:** AF-022 through AF-030.

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 1 | 7 example scripts have no docs-site page (invisible to users browsing the site) |
| Moderate | 4 | Proxy class docstrings missing; guide cross-link gaps; retry guide incomplete; `CacheBackend` protocol undocumented |
| Minor | 4 | `backends/index.md` sparse; `performance.md` guide-style violations; Research not a top-level Explanation entry; example imports use private modules |

---

## OK — verified consistent

| Area | Spec section | Result |
|------|-------------|--------|
| README content (§9) | §9 | All 14 required elements present: description, audience, scope boundaries, install, quick start, API overview, backend table, docs link, CHANGELOG link, CONTRIBUTING link, license, Python versions, project status, known limitations ✓ |
| Nav layout (§3) | §3 | All four Diataxis sections present: Getting Started, Guides, Reference, Explanation. Structure exceeds target ✓ |
| Content homes (§4) | §4 | Guides in `guides/`, examples in `examples/`, API in `src/`, specs/ADRs in `sdd/`, site-only in `docs-src/` ✓ |
| All nav pages build | §10 | `hatch run docs-build` succeeds — all 32 nav entries produce HTML pages, zero broken-link warnings ✓ |
| API reference pages | §2.3 | All 17 API pages present: Store, Registry, Backend, Config, Models, RemotePath, Capabilities, Errors, + 9 ext modules ✓ |
| Backend guides | §2.2 | All 6 backends have dedicated guides: local, memory, s3, s3-pyarrow, sftp, azure ✓ |
| Extension guides | §2.2 | All major extensions have guides: observe, cache, batch, transfer, glob, pyarrow-adapter, retry ✓ |
| Capabilities matrix | §2.3 | `docs-src/capabilities-matrix.md` present and built ✓ |
| Troubleshooting | §2.2 | `guides/troubleshooting.md` present ✓ |
| Migration guide | §2.2 | `guides/migration.md` present ✓ |
| Choosing a backend | §2.2 | `guides/choosing-a-backend.md` present ✓ |
| Explanation pages | §2.4 | Architecture, Performance, Concurrency, Security Model, Design all present ✓ |
| Further Reading | §13 | `docs-src/further-reading.md` links Development Story, SDD process, research docs, DESIGN.md ✓ |
| Contributing | §4 | `docs-src/contributing.md` wraps `CONTRIBUTING.md` ✓ |
| Docstring style | §5 | Sphinx-style (`:param:`, `:returns:`, `:raises:`) configured via mkdocstrings `docstring_style: sphinx` ✓ |
| `mkdocs.yml` validation | §10 | `validation.links.not_found: warn` (upgraded from `info` in audit-001 finding L-16) ✓ |
| Versioned docs | §10 | `mike` plugin configured for version selector ✓ |
| Store class docstrings | §5 | All 23 public methods fully documented: params, returns, raises, examples ✓ |
| Backend ABC docstrings | §5 | All 23 abstract + concrete methods fully documented ✓ |
| Error class docstrings | §5 | All 8 error classes document when raised and by which methods ✓ |
| Config class docstrings | §5 | `RegistryConfig`, `StoreProfile`, `BackendConfig`, `RetryPolicy`, `Secret` all documented ✓ |
| batch module docstrings | §5 | `batch_delete`, `batch_copy`, `batch_exists` fully documented ✓ |
| transfer module docstrings | §5 | `upload`, `download`, `transfer` documented (minor: `transfer()` missing `:returns:`) |
| Guide opening sentences | §7 | 21/21 guides open with a clear statement of purpose ✓ |

---

## Findings

---

### AF-022 — CRITICAL — 7 example scripts missing from docs-site examples nav

**Spec (§2.1, §4, §6):** Runnable examples live in `examples/` and should be discoverable on the docs site. Cross-linking rules (§6) require guides to link to matching example scripts, and the Examples section should surface all scripts.

**Actual:** 7 of 24 Python example scripts have no corresponding `docs-src/examples/*.md` wrapper and no entry in `docs-src/examples/_nav.yml`. Users browsing the site's Examples section cannot find them:

| Script | Topic | Has docs page? |
|--------|-------|:---:|
| `examples/caching.py` | Cache extension demo | ✗ |
| `examples/glob_pattern_matching.py` | Glob helper demo | ✗ |
| `examples/pyarrow_adapter.py` | PyArrow adapter demo | ✗ |
| `examples/observe_hooks.py` | Observability hooks demo | ✗ |
| `examples/otel_tracing.py` | OpenTelemetry tracing | ✗ |
| `examples/path_model.py` | RemotePath model demo | ✗ |
| `examples/capabilities_and_errors.py` | Capabilities & error handling | ✗ |

Contrast: the corresponding guides *do* link to these scripts — e.g., `guides/cache.md` links to `examples/caching.py`. But users navigating via Examples > nav won't find them.

**Fix required:** For each missing script, create a `docs-src/examples/<name>.md` wrapper (same pattern as existing entries) and add an entry to `docs-src/examples/_nav.yml`.

**Backlog entry:** AF-022

---

### AF-023 — MODERATE — `ObservedStore` proxy: 21 public method overrides have no docstrings

**Spec (§5):** "Every public symbol (class, method, function, property) must have a docstring that mkdocstrings can extract into useful reference docs."

**Actual:** `ObservedStore` in `src/remote_store/ext/observe.py` overrides 21 Store methods (exists, is_file, read, write, etc.). None of these overrides have docstrings — only `close()` and `child()` have one-line comments. The `__init__()` method also lacks a docstring.

Since mkdocstrings renders reference pages for `ObservedStore`, users see undocumented methods. While these are delegation-only overrides, the spec requires every public method to be documented.

**Mitigation note:** These are thin delegation wrappers. A class-level docstring stating "All public methods delegate to the inner Store and fire observation hooks. See `Store` for parameter/return documentation." would satisfy the spec without per-method docstrings on pure passthrough methods.

**Fix required:** Either (a) add a class-level docstring explaining the delegation pattern with a cross-reference to `Store`, or (b) add per-method docstrings. Option (a) is recommended.

**Backlog entry:** AF-023

---

### AF-024 — MODERATE — `CachedStore` proxy: 20+ public method overrides have no docstrings

**Spec (§5):** Same as AF-023.

**Actual:** `CachedStore` in `src/remote_store/ext/cache.py` overrides all Store methods for caching and delegation. None of the cached operations (exists, is_file, read_bytes, etc.), mutating operations (write, delete, move, etc.), or passthrough operations (to_key, unwrap, supports, etc.) have docstrings. Only `close()`, `child()`, and `ping()` have one-liners.

Same rendering issue as AF-023 — the `ext-cache.md` API page shows undocumented methods.

**Fix required:** Same approach as AF-023 — class-level docstring explaining the caching/delegation pattern.

**Backlog entry:** AF-024

---

### AF-025 — MODERATE — `CacheBackend` protocol: 6 methods completely undocumented

**Spec (§5):** "Every public symbol" must be documented.

**Actual:** The `CacheBackend` protocol class in `ext/cache.py` defines 6 public methods (`get`, `set`, `delete`, `clear`, `clear_prefix`, `size`) with zero docstrings. These are a public extension point — users implementing custom cache backends need to know the expected behavior.

**Fix required:** Add docstrings to each `CacheBackend` protocol method describing parameters, return types, and semantics.

**Backlog entry:** AF-025

---

### AF-026 — MODERATE — Guide cross-link gaps: 6 guides missing API reference links, 4 missing example links

**Spec (§6, §7):** Required cross-links: guides must link to API reference for classes/functions used and to matching example scripts.

**Actual:**

Missing API reference links:
- `guides/backends/index.md` — no API reference link
- `guides/choosing-a-backend.md` — no API reference link
- `guides/concurrency.md` — no API reference link
- `guides/extensions.md` — no centralized API reference link
- `guides/retry.md` — no link to API reference for `RetryPolicy`
- `guides/troubleshooting.md` — no API reference links

Missing example script links:
- `guides/choosing-a-backend.md` — no example link
- `guides/concurrency.md` — no example link
- `guides/extensions.md` — no example link
- `guides/retry.md` — no link to `examples/retry_policy.py`

**Fix required:** Add API reference and example cross-links to each guide per §6 minimum requirements.

**Backlog entry:** AF-026

---

### AF-027 — MODERATE — `guides/retry.md` missing "See also" section and cross-links

**Spec (§7):** Guide checklist requires: links to API reference, links to matching example script, links to related guides ("See also"), and next steps at the end.

**Actual:** `guides/retry.md` ends at line 155 with the "Local and Memory" backend mapping section. No "See also" section, no link to `examples/retry_policy.py`, no link to the `RetryPolicy` API reference page, no next steps.

Compare: most other guides (observe, cache, glob, transfer, etc.) have a well-formed "See also" footer with API refs, examples, and related guides.

**Fix required:** Add a "See also" section at the end of `guides/retry.md` linking to the retry example, API reference, and related guides (config loaders, backend guides).

**Backlog entry:** AF-027

---

### AF-028 — MINOR — `guides/backends/index.md` sparse — missing API refs, examples, and next steps

**Spec (§7):** Guide checklist applies to all guide pages.

**Actual:** The backend index page lists backends and links to individual guides but has no API reference links, no example links, and no "See also" section. It scores 2/5 on the guide checklist.

**Fix required:** Add links to the Store API reference, the capabilities matrix, and an overall example (e.g., `examples/quickstart.md`). Add a brief "See also" footer.

**Backlog entry:** AF-028

---

### AF-029 — MINOR — `guides/performance.md` missing API refs, examples, and "See also" section

**Spec (§7):** Guide checklist applies.

**Actual:** Performance guide is well-written for methodology and results but reads more like Explanation than a How-To guide. It scores 2/5 on the guide checklist: no API reference links, no example script link, no "See also" section. The guide does link to the benchmark notebook, but only internally.

**Note:** This page might belong in the Explanation section (§2.4) rather than Guides. It explains *why* performance is what it is rather than answering *how do I achieve X*. Currently placed under Explanation in the nav (correct), but its content in `guides/` is still subject to guide standards.

**Fix required:** Either (a) add the missing cross-links to make it a proper guide, or (b) move the source file to `docs-src/` and reclassify as Explanation (no guide checklist required). Option (b) is recommended since it already lives under the Explanation nav section.

**Backlog entry:** AF-029

---

### AF-030 — MINOR — Research not a top-level Explanation entry

**Spec (§3 target layout):** Target nav shows `Research: research/` as a direct child of the Explanation section.

**Actual:** Research is nested under `Explanation > Design > Research` — three levels deep instead of two. Accessible but requires extra navigation.

**Impact:** Low — research documents are historical reference material, not frequently accessed.

**Fix required:** Optional. If desired, promote Research to a top-level Explanation entry per the target layout.

**Backlog entry:** AF-030

---

## Not Applicable / Out of Scope

| Item | Reason |
|------|--------|
| Hosted doc accessibility (§10) | RTD deployment not testable from local build; `mike` plugin configured correctly |
| ReadTheDocs vs GitHub Pages canonical (§6.1) | External hosting config, not auditable from source |
| PyPI README rendering (§11) | Requires actual PyPI upload to verify |
| Doc versioning with `mike` | Plugin configured in `mkdocs.yml`; deployment-time concern |

---

## Action Items

| ID | Priority | File(s) | Change |
|----|----------|---------|--------|
| AF-022 | Critical | `docs-src/examples/*.md`, `docs-src/examples/_nav.yml` | Add 7 missing example wrapper pages + nav entries (caching, glob, pyarrow-adapter, observe-hooks, otel-tracing, path-model, capabilities-and-errors) |
| AF-023 | Moderate | `src/remote_store/ext/observe.py` | Add class-level docstring to `ObservedStore` explaining delegation pattern |
| AF-024 | Moderate | `src/remote_store/ext/cache.py` | Add class-level docstring to `CachedStore` explaining caching/delegation pattern |
| AF-025 | Moderate | `src/remote_store/ext/cache.py` | Add docstrings to 6 `CacheBackend` protocol methods |
| AF-026 | Moderate | 6 guides (backends/index, choosing-a-backend, concurrency, extensions, retry, troubleshooting) | Add API reference and example cross-links |
| AF-027 | Moderate | `guides/retry.md` | Add "See also" section with API ref, example, and related guides |
| AF-028 | Minor | `guides/backends/index.md` | Add API reference, example, and "See also" links |
| AF-029 | Minor | `guides/performance.md` or `docs-src/performance.md` | Add cross-links or reclassify as Explanation |
| AF-030 | Minor | `docs-src/_nav.yml` | Optional: promote Research to top-level Explanation entry |
