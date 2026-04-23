# Audit 010: Extension Private Module Imports

**Date:** 2026-04-23  
**Scope:** All extension modules in `src/remote_store/ext/` and `src/remote_store/aio/ext/`  
**Rule:** ADR-0008 § "Public API only" — Extensions MUST use only the public `Store` and `Backend` API.

---

## Findings

**11 of 16 extension modules violate the rule by importing from private modules** (`_*` prefixed), resulting in **12 distinct violations**:

| Module | Import | Type | Severity |
|--------|--------|------|----------|
| `ext/dagster.py` | `_registry._BACKEND_FACTORIES, _register_builtin_backends` | Private functions | High |
| `ext/glob.py` | `_glob` (module) | Private module | High |
| `ext/write.py` | `_store._validate_metadata` | Private function | High |
| `ext/arrow.py` | `_errors.*` | Private classes | Medium |
| `ext/batch.py` | `_errors.*` | Private classes | Medium |
| `ext/cache.py` | `_models.FileInfo, FolderInfo`, `_proxy.ProxyStore` | Private classes | Medium |
| `ext/glob.py` | `_capabilities.Capability` | Private class | Medium |
| `ext/integrity.py` | `_models.ContentDigest` | Private class | Medium |
| `ext/observe.py` | `_proxy.ProxyStore`, `_models.*`, `_resolution.ResolutionPlan` | Private classes | Medium |
| `ext/parquet.py` | `_capabilities.Capability`, `_errors.*` | Private classes | Medium |
| `ext/pydantic.py` | `_config.RegistryConfig` | Private class | Medium |
| `ext/yaml.py` | `_config.RegistryConfig` | Private class | Medium |

**Compliant:** `aio/ext/write.py`, `ext/streams.py`, `ext/transfer.py`, `ext/partition.py`, `ext/otel.py` (5 modules total: 11 violating + 5 compliant = 16 extensions).

**Test gap:** `test_ext_contract.py::test_no_private_store_access` only detects *runtime* attribute access (e.g., `store._backend`), not *import-time* access to private modules. Both violations contradict ADR-0008.

---

## Evidence

- ADR-0008 explicitly states: "Extensions MUST use only the public `Store` and `Backend` API. Direct access to private attributes (e.g., `store._backend`) is forbidden."
- Current test enforces one direction (runtime access) but not the other (imports).
- Grep and semantic index search confirm 14 distinct private imports across ext modules.

---

## Recommended Actions

1. **Add import-time checker to test suite**  
   Extend `test_ext_contract.py::test_no_private_store_access` to also detect imports of private modules/functions via AST analysis. Should fail on `from remote_store._*` and `import remote_store._*` (excluding TYPE_CHECKING blocks for type hints). Create backlog item to track enforcement.

2. **Re-export violating symbols from public API**  
   Move the following to `src/remote_store/__init__.py` or a new public module:
   - `ContentDigest, FileInfo, FolderInfo, FolderEntry, WriteResult` (from `_models`)
   - `Capability` (from `_capabilities`)
   - Error classes (from `_errors`)
   - `RegistryConfig` (from `_config`)
   - `ProxyStore` (from `_proxy`)
   - `ResolutionPlan` (from `_resolution`)
   - `_validate_metadata` → public helper in `_store`
   - Glob utilities: `extract_prefix, needs_recursive, pattern_to_regex` → public submodule or helpers
   - Registry internals: `_BACKEND_FACTORIES, _register_builtin_backends` → decide via ADR if part of stable API

3. **Update violating extension modules**  
   Fix each of the 11 modules to use only public API. Create backlog item to track fixing.

---

## Non-Findings

- No extension imports directly from `backends/` or `aio/` modules (good).
- All extensions already define `__all__` (rule is enforced).
