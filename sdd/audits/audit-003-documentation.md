# Audit 003 — Documentation Quality & Spec Compliance

**Date:** 2026-03-09
**Scope:** Full documentation site (`docs-src/`, `guides/`, `examples/`, API docstrings) audited against `sdd/DOCUMENTATION.md` spec. Version 0.15.0, commit `62ecb61` (master HEAD at audit time).
**Method:** Built docs locally with `hatch run docs-build`. Systematic cross-reference of every section in `sdd/DOCUMENTATION.md` (S1-S13) against actual site structure, content, and source files. Assessed against the 5 Documentation Goals from S1.

**Finding IDs assigned:** AF-022 through AF-040.

---

## Executive Summary

| Goal | Score | Verdict | Key Findings |
|------|-------|---------|--------------|
| 1. New user: install + run <10 min | 9/10 | PASS | 3-step quickstart, standalone code, no missing imports |
| 2. Returning user: "How do I X?" in 1 click | 8/10 | PASS with gaps | All tasks discoverable; cross-feature linking sparse |
| 3. Advanced user: API lookup without source | 7/10 | PASS with gaps | 17 API ref pages; proxy class docstrings missing |
| 4. Contributor: design decisions & content placement | 7/10 | PASS with staleness | CONTRIBUTING.md counts stale; CLAUDE-REF wrong path |
| 5. Accuracy at every commit | 5/10 | MULTIPLE ISSUES | 7 accuracy findings across guides, docs, and config |

---

## Goal 1: New User — Install + Run in <10 min

**Checked:** README quickstart, `docs-src/getting-started.md`, `examples/quickstart.py`, tutorial notebooks.

**Verdict: PASS (9/10)**

- 3-step install-configure-run path works end-to-end
- Quickstart code is standalone (no temp-file boilerplate, minimal imports)
- No missing imports or broken examples in the getting-started flow
- Tutorial notebooks execute successfully via `hatch run notebooks`

**No new findings.**

---

## Goal 2: Returning User — "How do I X?" in One Click

**Checked:** Nav structure, guide inventory, cross-linking density, example discoverability.

**Verdict: PASS (8/10)**

**Strong:** All common tasks (configure backend, read/write files, use extensions) are discoverable in 1-2 clicks from the nav. 21 guides cover the full feature set.

**Weak:** Cross-feature linking is sparse — batch, transfer, and observe guides don't link to each other despite natural workflows that combine them. 6 guides missing API reference links. 7 example scripts invisible on docs site.

**Findings:**

- AF-022 — 7 example scripts missing from docs-site nav (Critical)
- AF-026 — 6 guides missing API reference links, 4 missing example links
- AF-027 — `guides/retry.md` missing "See also" section and cross-links
- AF-028 — `guides/backends/index.md` sparse

---

## Goal 3: Advanced User — API Lookup Without Source

**Checked:** 17 API reference pages, docstring compliance for Store, Backend, extensions, models, errors.

**Verdict: PASS with gaps (7/10)**

**Strong:** Store (23 methods), Backend ABC (23 methods), all 8 error classes, all config classes, batch/glob/transfer extensions — all fully documented with params, returns, raises.

**Weak:** Proxy classes (`ObservedStore`, `CachedStore`) and the `CacheBackend` protocol have missing or incomplete docstrings.

**Findings:**

- AF-023 — `ObservedStore`: 24 method overrides, 0 per-method docstrings. Class-level docstring exists ("Proxy Store that fires observation hooks") but is terse — does not explain delegation pattern or refer users to `Store` for parameter docs. mkdocstrings renders 24 undocumented methods on the API page.
- AF-024 — `CachedStore`: same pattern, 20+ method overrides without per-method docstrings
- AF-025 — `CacheBackend` protocol: 6 methods (`get`, `set`, `delete`, `clear`, `clear_prefix`, `size`) completely undocumented. Public extension point for custom cache backends.
- AF-031 — `transfer()` in `ext/transfer.py` missing `:returns:` docstring (returns `None` but undocumented)

---

## Goal 4: Contributor — Design Decisions & Content Placement

**Checked:** `CONTRIBUTING.md`, `sdd/CLAUDE-REFERENCE.md`, `sdd/DOCUMENTATION.md` S4 content homes.

**Verdict: PASS with staleness (7/10)**

**Strong:** DOCUMENTATION.md is comprehensive (S1-S13), content homes are clear, ADR/RFC process well documented.

**Weak:** Stale counts and wrong paths create confusion for new contributors.

**Findings:**

- AF-038 — `CONTRIBUTING.md` states "9 ADRs" (actual: 11) and "3 RFCs" (actual: 4)
- AF-039 — `sdd/CLAUDE-REFERENCE.md` line 77 references `docs/` directory, should be `docs-src/`

---

## Goal 5: Accuracy at Every Commit

**Checked:** Code examples in guides, import paths, hook tables, version references, counts in contributor docs.

**Verdict: MULTIPLE ISSUES (5/10)**

This is the weakest area. Several guides contain import paths to private modules, the observe guide's hook table is incomplete, and `migration.md` documents an unreleased version.

**Findings:**

- AF-032 — `guides/observe.md`: `on_write` hook table lists `write`, `write_atomic` but omits `open_atomic` (which triggers `on_write` per `observe.py` line 109)
- AF-033 — `guides/observe.md`: `on_ping` hook row missing entirely (the `ping()` method fires `on_ping` per `observe.py` line 107)
- AF-034 — `ext/observe.py`: `observe()` function docstring says "Fires after write/write_atomic" for `on_write` param but omits `open_atomic`
- AF-035 — `guides/cache.md`: imports from `remote_store.backends._memory` (private module)
- AF-036 — `guides/health-check.md`: imports from `remote_store.backends._local` (private module)
- AF-037 — `guides/backends/sftp.md`: imports from `remote_store.backends._sftp` (private module, no disclaimer that this is internal API)
- AF-040 — `guides/migration.md`: documents v0.15.0-to-v0.16.0 migration for an unreleased version

---

## Structural Checks (retained from initial audit)

### Verified consistent

| Area | Spec section | Status |
|------|-------------|--------|
| README content (S9) | S9 | All 14 required elements present |
| Nav layout (S3) | S3 | All four Diataxis sections present |
| Content homes (S4) | S4 | Guides, examples, API, specs all in correct locations |
| All nav pages build (S10) | S10 | `hatch run docs-build` succeeds, zero broken-link warnings |
| API reference pages (S2.3) | S2.3 | All 17 API pages present |
| Backend guides (S2.2) | S2.2 | All 6 backends have dedicated guides |
| Extension guides (S2.2) | S2.2 | All major extensions have guides |
| Capabilities matrix (S2.3) | S2.3 | Present and built |
| Docstring style (S5) | S5 | Sphinx-style configured via mkdocstrings |
| Versioned docs (S10) | S10 | `mike` plugin configured |
| Store class docstrings (S5) | S5 | All 23 public methods fully documented |
| Backend ABC docstrings (S5) | S5 | All 23 abstract + concrete methods fully documented |
| Error class docstrings (S5) | S5 | All 8 error classes documented |
| Config class docstrings (S5) | S5 | All 5 config classes documented |
| Guide opening sentences (S7) | S7 | 21/21 guides open with clear purpose statement |

### Additional structural findings

- AF-029 — `guides/performance.md` reads as Explanation, not How-To. Missing API refs, examples, "See also". Consider reclassifying.
- AF-030 — Research docs nested 3 levels deep (Explanation > Design > Research) instead of 2. Low impact.

---

## Not Applicable / Out of Scope

| Item | Reason |
|------|--------|
| Hosted doc accessibility (S10) | RTD deployment not testable from local build |
| ReadTheDocs vs GitHub Pages canonical (S6.1) | External hosting config |
| PyPI README rendering (S11) | Requires actual PyPI upload |
| Doc versioning with `mike` | Deployment-time concern |

---

## Action Items

| ID | Severity | Goal | File(s) | Issue |
|----|----------|------|---------|-------|
| AF-022 | Critical | 2 | `docs-src/examples/*.md`, `_nav.yml` | 7 example scripts missing from docs-site nav |
| AF-023 | Moderate | 3 | `src/remote_store/ext/observe.py` | ObservedStore: 24 method overrides lack per-method docstrings |
| AF-024 | Moderate | 3 | `src/remote_store/ext/cache.py` | CachedStore: 20+ method overrides lack per-method docstrings |
| AF-025 | Moderate | 3 | `src/remote_store/ext/cache.py` | CacheBackend protocol: 6 methods undocumented |
| AF-026 | Moderate | 2 | 6 guides | Missing API reference and example cross-links |
| AF-027 | Moderate | 2 | `guides/retry.md` | Missing "See also" section and cross-links |
| AF-028 | Minor | 2 | `guides/backends/index.md` | Sparse — missing API refs, examples, next steps |
| AF-029 | Minor | — | `guides/performance.md` | Guide-style violations; consider reclassifying as Explanation |
| AF-030 | Minor | — | `docs-src/_nav.yml` | Research nested 3 levels deep instead of 2 |
| AF-031 | Low | 3 | `src/remote_store/ext/transfer.py` | `transfer()` missing `:returns:` docstring |
| AF-032 | Medium | 5 | `guides/observe.md` | on_write hook table omits `open_atomic` |
| AF-033 | Medium | 5 | `guides/observe.md` | on_ping hook row missing entirely |
| AF-034 | Low | 5 | `src/remote_store/ext/observe.py` | `observe()` docstring on_write omits `open_atomic` |
| AF-035 | Low | 5 | `guides/cache.md` | Private import `backends._memory` |
| AF-036 | Low | 5 | `guides/health-check.md` | Private import `backends._local` |
| AF-037 | Medium | 5 | `guides/backends/sftp.md` | Private imports `backends._sftp` without disclaimer |
| AF-038 | High | 4 | `CONTRIBUTING.md` | Stale counts: 9 ADRs (actual 11), 3 RFCs (actual 4) |
| AF-039 | High | 4 | `sdd/CLAUDE-REFERENCE.md` | `docs/` should be `docs-src/` |
| AF-040 | Medium | 5 | `guides/migration.md` | Documents unreleased v0.16.0 migration |
