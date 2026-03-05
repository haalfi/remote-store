# Audit 002 — Design & Spec Compliance Review

**Date:** 2026-03-05
**Scope:** Full codebase against all SDD specs (`sdd/specs/001`–`021`), BACKLOG, CHANGELOG, and DEVELOPMENT_STORY.md. Version 0.13.0 + unreleased work toward 0.13.1.
**Method:** Systematic cross-reference of source (`src/`), tests (`tests/`), and all documentation against the ripple-check table in `sdd/CLAUDE-REFERENCE.md`. No uncommitted changes present at audit time.

**Finding IDs assigned:** AF-016 through AF-021.

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 1 | Spec-vs-code conflict: capability sections in specs 008, 011, 012 stale after v0.12.0 GLOB landing |
| Moderate | 3 | CHANGELOG missing ID-043 entry; BACKLOG version annotations ahead of actual release; §11.6 method ordering violated across Store and all backends |
| Minor | 2 | DEVELOPMENT_STORY.md spec count wrong (20 vs 21); unlinked TODO in `ext/arrow.py` |

Items AF-016 through AF-018 are **documentation/spec fixes only** — no production code changes required. AF-020 and AF-021 are code style fixes with no behavioral impact.

---

## OK — verified consistent

| Area | Spec(s) | Result |
|------|---------|--------|
| Version sync | — | `pyproject.toml`, `src/remote_store/__init__.py`, `CITATION.cff` all `0.13.0` ✓ |
| `CITATION.cff` date-released | — | `2026-03-03` matches `[0.13.0]` CHANGELOG header ✓ |
| Error hierarchy — flat (ERR-008) | 005 | All 8 concrete types inherit directly from `RemoteStoreError`; all exported in `__all__` ✓ |
| `Capability` enum members (CAP-001) | 003 | `READ WRITE DELETE LIST MOVE COPY ATOMIC_WRITE METADATA GLOB` — 9 members ✓ |
| Backend ABC abstract interface | 003 | All required abstract methods present; `glob()` / `to_key()` / `close()` / `unwrap()` non-abstract defaults match BE-020/022/023/024 ✓ |
| LocalBackend capabilities | 003, 018 | `CapabilitySet(set(Capability))` — all 9, includes GLOB (GLOB-005) ✓ |
| SFTPBackend capabilities | 009 | `set(Capability) - {GLOB}` — no GLOB, matches SFTP-003 ✓ |
| MemoryBackend capabilities | 013 | `set(Capability) - {GLOB}` — no GLOB, matches MEM-003 ✓ |
| S3/S3PA/Azure `glob()` override | 018 | `glob()` methods present in all three backends (GLOB-018/019/020) ✓ |
| Store API surface (STORE-008) | 001 | All 23 public methods present in `_store.py` ✓ |
| STORE-008a same-path short-circuit (ID-040) | 001 | `src_path == dst_path` guard + `is_file()` check in `_store.py:363–366` / `384–387` ✓ |
| `Registry.get_store()` ownership (ID-041) | — | `store._owns_backend = False` set at `_registry.py:110` ✓ |
| `__init__.py` exports / `__all__` | 001 | All public types, extensions, and optional adapters exported correctly ✓ |
| `Secret` / credential hygiene | 020 | `Secret.__repr__` → `'***'`, `.reveal()`, auto-wrap in `from_dict()`, `SecretRedactionFilter` — SEC-001–SEC-008 ✓ |
| Config loaders `from_toml()` / `from_yaml()` | 021 | CFG-008/009/010/011 implemented and tested ✓ |
| Unknown-key warning in `from_dict()` (CFG-012) | 021 | `UserWarning` at correct stacklevel in `_from_dict()` ✓ |
| Pydantic adapter (CFG-015–017) | 021 | `ext/pydantic.py` calls only public `from_dict()` API ✓ |
| Glob three-tier design (BK-002) | 018 | Tier 1 `list_files(pattern=)`, Tier 2 `Store.glob()`, Tier 3 `ext.glob.glob_files()` ✓ |
| Spec test traceability | — | `@pytest.mark.spec` annotations present for STORE-008a, CFG-012, CFG-015–017, GLOB-002/005/018/019 ✓ |
| Registry auto-registration | — | All 6 backends registered in `_register_builtin_backends()` ✓ |

---

## Findings

---

### AF-016 — CRITICAL — Specs 008, 011, 012 capability sections stale post-GLOB landing

**Root cause:** When `Capability.GLOB` + native `glob()` was added to S3, S3-PyArrow, and Azure backends in v0.12.0 (BK-002), spec `018-glob.md` was written correctly (GLOB-018/019/020), but the capability sections inside each backend's own spec were never updated. They still say "Does not declare `GLOB`."

**Conflict matrix:**

| Source | S3 GLOB | S3PA GLOB | Azure GLOB |
|--------|---------|-----------|-----------|
| `sdd/specs/008-s3-backend.md` § S3-003 | ✗ No | ✗ No | — |
| `sdd/specs/011-s3-pyarrow-backend.md` § S3PA-003 | — | ✗ No | — |
| `sdd/specs/012-azure-backend.md` § AZ-003 | — | — | ✗ No |
| `sdd/specs/018-glob.md` § GLOB-018/019/020 | ✓ Yes | ✓ Yes | ✓ Yes |
| `src/.../backends/_s3.py` | ✓ `set(Capability)` | — | — |
| `src/.../backends/_s3_pyarrow.py` | — | ✓ `set(Capability)` | — |
| `src/.../backends/_azure.py` | — | — | ✓ `set(Capability)` |
| `CHANGELOG.md` v0.12.0 | ✓ Yes | ✓ Yes | ✓ Yes |

The authoritative sources (spec 018, code, CHANGELOG) all agree: these backends declare GLOB. Specs 008/011/012 are stale.

**Fix required:** Update S3-003, S3PA-003, and AZ-003 capability lists to include `GLOB` and add a cross-reference to `018-glob.md`. Example for `008-s3-backend.md`:

```diff
-**Invariant:** `S3Backend` declares capabilities: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`. Does not declare `GLOB` (no native pattern matching; use `list_files(pattern=…)` or `ext.glob` for client-side fallback).
+**Invariant:** `S3Backend` declares capabilities: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`, `GLOB`. Native glob via prefix-optimized listing (see `018-glob.md` § GLOB-018).
```

Apply equivalent changes to `011-s3-pyarrow-backend.md` § S3PA-003 and `012-azure-backend.md` § AZ-003.

**Backlog entry:** AF-016

---

### AF-017 — MODERATE — ID-043 implemented but absent from `CHANGELOG.md [Unreleased]`

**Root cause:** BACKLOG marks ID-043 ("Remove `_stacklevel` from public `from_dict()` signature") as `[x]` done `*(unreleased)*`. The implementation is confirmed in `src/remote_store/_config.py`:
- `_from_dict(cls, data, *, stacklevel: int)` — private helper (line 159)
- `from_dict(cls, data)` — clean public signature, delegates to `_from_dict(data, stacklevel=3)` (line 208)

However, `CHANGELOG.md [Unreleased]` has entries for ID-040, ID-041, ID-042, ID-005, ID-002, CFG-012, and ID-003 but **no entry for ID-043**.

**Fix required:** Add an entry to `CHANGELOG.md` under `[Unreleased] → Changed`:

```markdown
### Changed

- **`RegistryConfig._from_dict()` extracted as private helper** (ID-043)
  `from_dict()` public signature no longer exposes a `_stacklevel` internal
  parameter. A private `_from_dict(data, *, stacklevel)` helper is shared by
  `from_dict()`, `from_toml()`, and `from_yaml()`, each passing the correct
  frame offset so `UserWarning` stacktraces point at user call sites.
```

**Backlog entry:** AF-017

---

### AF-018 — MODERATE — BACKLOG version tags `(v0.13.1)` ahead of actual release

**Root cause:** BACKLOG items ID-040, ID-041, ID-042 are annotated `(v0.13.1)`, but no v0.13.1 release has been cut. The three canonical version files and CHANGELOG all correctly reflect the current state:

| File | Current value |
|------|--------------|
| `pyproject.toml` | `0.13.0` |
| `src/remote_store/__init__.py` | `0.13.0` |
| `CITATION.cff` | `0.13.0` |
| `CHANGELOG.md` | ID-040/041/042 in `[Unreleased]` |
| `sdd/BACKLOG.md` | ID-040/041/042 annotated `(v0.13.1)` ← stale |

CLAUDE.md §3 requires the repo to describe reality at every commit. Aspirational version tags in the BACKLOG violate this.

**Fix required:** In `sdd/BACKLOG.md`, change the three item annotations:

```diff
-- [x] **ID-040 — …** (v0.13.1)
+- [x] **ID-040 — …** *(unreleased)*

-- [x] **ID-041 — …** (v0.13.1)
+- [x] **ID-041 — …** *(unreleased)*

-- [x] **ID-042 — …** (v0.13.1)
+- [x] **ID-042 — …** *(unreleased)*
```

Update all three to `(v0.13.1)` when the release commit is made.

**Backlog entry:** AF-018

---

### AF-019 — MINOR — `DEVELOPMENT_STORY.md` spec count wrong (20 vs 21)

**Root cause:** `DEVELOPMENT_STORY.md` line 11 says `20 specs`. The `sdd/specs/` directory contains 21 files (`001-store-api.md` through `021-config-loaders.md`). Spec 021 was added in v0.14.0 work (ID-002/003/005) and the table was not updated.

**Fix required:**

```diff
-| Specs & docs | 20 specs, 10 ADRs, 3 RFCs |
+| Specs & docs | 21 specs, 10 ADRs, 3 RFCs |
```

**Backlog entry:** AF-019

---

## Not Applicable

| Item | Reason |
|------|--------|
| `guides/backends/` prerequisites | No dependency changes since last verified |
| `mkdocs.yml` nav / `_nav.yml` sync | No new backends or docs sections since v0.13.0 |
| `CONTRIBUTING.md` repo structure | No new directories or structural changes |
| `examples/configuration.py` | Updated for ID-042 (credential hygiene) — in CHANGELOG |
| CITATION.cff sha256 (conda-forge) | ID-018 conda-forge submission still pending externally |
| Error model tests per-backend | All backends tested via conformance suite; ERR-* coverage confirmed |

---

---

### AF-020 — MODERATE — DESIGN.md §11.6 method ordering violated across Store and all backends

**Rule (DESIGN.md §11.6):**

> Within a class, methods are ordered: (1) class variables, (2) `__init__`, (3) properties, (4) public methods, (5) dunder methods (`__eq__`, `__hash__`, `__repr__`), (6) private helpers.

**Violations found:**

| File | Issue |
|------|-------|
| `src/remote_store/_store.py` | `__repr__` (line 42), `__eq__` (45), `__hash__` (50) placed immediately after `__init__` — before properties and public methods. Per §11.6 they belong at position 5, after all public methods. |
| `src/remote_store/_store.py` | Private helpers `_full_path` (91), `_require_file_path` (106), `_strip_root` (112), `_rebase_file_info` (130), `_rebase_folder_info` (137) inserted before public methods `to_key` (145), `unwrap` (158), `supports` (168), etc. Per §11.6 private helpers belong after all public methods. |
| `src/remote_store/backends/_s3.py` | `__repr__` (71) before `name` property (81) and all public methods |
| `src/remote_store/backends/_s3_pyarrow.py` | Same `__repr__`-first pattern |
| `src/remote_store/backends/_local.py` | Same `__repr__`-first pattern |
| `src/remote_store/backends/_memory.py` | Same `__repr__`-first pattern |
| `src/remote_store/backends/_sftp.py` | Same `__repr__`-first pattern (expected, not checked individually) |
| `src/remote_store/backends/_azure.py` | Same `__repr__`-first pattern (expected, not checked individually) |

**Fix required:** Reorder methods in `_store.py` and all 6 backend files so that dunder methods (`__repr__`, `__eq__`, `__hash__`) and private helpers appear after all public methods, per §11.6. No behavior changes.

**Backlog entry:** AF-020

---

### AF-021 — MINOR — Unlinked TODO in `ext/arrow.py` violates DESIGN.md §11.7

**Rule (DESIGN.md §11.7):** "No TODO comments without a linked issue."

**Violation:** `src/remote_store/ext/arrow.py:277`:

```python
# TODO(Phase 2): Subsequent reads from PythonFile bypass _map_errors(), …
```

"Phase 2" references a known backlog item (ID-037 — PyArrow adapter Phase 2), but the comment does not cite the ID. DESIGN.md §11.7 requires a linked issue.

**Fix required:** Amend the comment to reference the backlog item:

```python
# TODO(ID-037 Phase 2): Subsequent reads from PythonFile bypass _map_errors(), …
```

**Backlog entry:** AF-021

---

## Action Items

| ID | Priority | File(s) | Change |
|----|----------|---------|--------|
| AF-016 | Critical | `sdd/specs/008-s3-backend.md` § S3-003, `sdd/specs/011-s3-pyarrow-backend.md` § S3PA-003, `sdd/specs/012-azure-backend.md` § AZ-003 | Add `GLOB` to capability list, add cross-ref to 018-glob.md |
| AF-017 | Moderate | `CHANGELOG.md` `[Unreleased]` | Add `### Changed` entry for ID-043 |
| AF-018 | Moderate | `sdd/BACKLOG.md` | Change `(v0.13.1)` to `*(unreleased)*` for ID-040/041/042 |
| AF-020 | Moderate | `_store.py`, all 6 backend files | Reorder methods per DESIGN.md §11.6 |
| AF-019 | Minor | `DEVELOPMENT_STORY.md` line 11 | Change `20 specs` to `21 specs` |
| AF-021 | Minor | `src/remote_store/ext/arrow.py:277` | Add `ID-037` to TODO comment |
