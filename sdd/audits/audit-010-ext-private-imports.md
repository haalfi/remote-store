# Audit 010: Extension Private Module Imports

**Date:** 2026-04-23  
**Scope:** All extension modules in `src/remote_store/ext/` and `src/remote_store/aio/ext/`  
**Rule:** ADR-0008 § "Public API only" — Extensions MUST use only the public `Store` and `Backend` API.

**Interpretation note:** ADR-0008 illustrates the rule with runtime attribute access (`store._backend`). This audit extends the same principle to import-time access to private modules. That extension is not literal ADR text and may warrant a dedicated ADR to formalise.

**TYPE_CHECKING scope:** Imports inside `if TYPE_CHECKING:` blocks have no runtime effect and are out of scope. Only runtime imports — top-level and function-body deferred — are counted as violations.

---

## Findings

**11 of 16 extension modules have runtime violations** (12 distinct violations). Violations split into two categories with different remediation paths.

### Category 1: Truly private internals — no public API path

Fix requires a design decision: expose publicly, refactor, or add a public helper.

| Module | Import | Type |
|--------|--------|------|
| `ext/dagster.py` | `_registry._BACKEND_FACTORIES, _register_builtin_backends` | Private functions |
| `ext/glob.py` | `_glob` (module) | Private module |
| `ext/write.py` | `_store._validate_metadata` | Private function |

### Category 2: Already-public symbols imported via private path

Fix is a one-line import path change (`from remote_store._x import Y` → `from remote_store import Y`). All symbols are already in `remote_store.__all__`.

| Module | Import | Note |
|--------|--------|------|
| `ext/arrow.py` | `_errors.*` | Public error classes |
| `ext/batch.py` | `_errors.*` | Public error classes |
| `ext/cache.py` | `_models.FileInfo, FolderInfo`; `_proxy.ProxyStore` | Public classes |
| `ext/glob.py` | `_capabilities.Capability` | Public class |
| `ext/integrity.py` | `_models.ContentDigest` | Public class |
| `ext/observe.py` | `_proxy.ProxyStore` | Public class |
| `ext/parquet.py` | `_capabilities.Capability`; `_errors.*` | Public classes |
| `ext/pydantic.py` | `_config.RegistryConfig` | Public class |
| `ext/yaml.py` | `_config.RegistryConfig` (line 32); `_config.resolve_env` (line 95, deferred) | Public symbols |

**Compliant:** `aio/ext/write.py`, `ext/otel.py`, `ext/partition.py`, `ext/streams.py`, `ext/transfer.py` (5 modules; 11 + 5 = 16 total).

**Test gap:** `test_ext_contract.py::test_no_private_store_access` detects runtime attribute access (e.g., `store._backend`) but not import-time access to private modules. Both violate the same principle.

---

## Evidence

- ADR-0008 states: "Extensions MUST use only the public `Store` and `Backend` API. Direct access to private attributes (e.g., `store._backend`) is forbidden."
- All Category 2 symbols are confirmed present in `src/remote_store/__init__.py` `__all__`.
- `ext/yaml.py` line 95 is a deferred runtime import inside a function body (`resolve_env`), not a `TYPE_CHECKING` guard — the AST checker must handle this case.
- Grep of `src/remote_store/ext/` for `from remote_store._` with TYPE_CHECKING blocks excluded yields 12 violations across 11 modules.

---

## Recommended Actions

1. **Add import-time checker to test suite**  
   Extend `test_ext_contract.py` to flag `from remote_store._*` and `import remote_store._*` via AST analysis. Must exclude `if TYPE_CHECKING:` blocks but must catch function-body deferred imports (`ext/yaml.py` line 95 is the reference case).

2. **Fix Category 2 import paths**  
   Change `from remote_store._x import Y` to `from remote_store import Y` for all 9 Category 2 modules. Mechanical one-line fix per occurrence; no design decision required.

3. **Resolve Category 1 internals**  
   Three symbols have no public path and each requires a decision:
   - `_glob` utilities (`extract_prefix`, `needs_recursive`, `pattern_to_regex`) — expose as public or internalise inside `ext.glob`
   - `_registry._BACKEND_FACTORIES`, `_register_builtin_backends` — decide via ADR if these are stable API
   - `_store._validate_metadata` — expose as public helper or remove from extension use

---

## Non-Findings

- No extension imports directly from `backends/` or `aio/` modules.
- All extensions already define `__all__`.
