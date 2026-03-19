# Naming Inconsistency Analysis

**Date:** 2025-03-19
**Status:** Proposal — for discussion

---

## 1. Config Loader Naming (most inconsistent)

The core config module (`_config.py`) establishes a clear `from_*` classmethod
pattern on `RegistryConfig`:

| Location | Function / Method | Style |
|---|---|---|
| `_config.py` | `RegistryConfig.from_dict(data)` | classmethod, `from_<format>` |
| `_config.py` | `RegistryConfig.from_toml(path)` | classmethod, `from_<format>` |
| `ext/yaml.py` | `from_yaml(path)` | standalone function, `from_<format>` |
| `ext/pydantic.py` | `pydantic_to_registry_config(model)` | standalone function, `<source>_to_<target>` |

**Problems:**

- `pydantic_to_registry_config` uses a completely different naming style
  (`source_to_target`) vs the established `from_*` pattern. It's also the most
  verbose name in the entire public API.
- `from_yaml` matches the `from_*` verb pattern but is a standalone function
  while `from_dict`/`from_toml` are classmethods. This is defensible (YAML
  requires an optional dependency, so it can't live on the class), but the
  asymmetry is visible to users.

**Proposed rename:**

| Current | Proposed | Rationale |
|---|---|---|
| `pydantic_to_registry_config(model)` | `from_pydantic(model)` | Matches `from_yaml`, `from_dict`, `from_toml` |

`from_yaml` is fine as-is — it already matches the `from_*` verb. The
standalone-vs-classmethod split is documented (ADR-0013: optional deps aren't
re-exported or placed on core classes).

---

## 2. Integration Factory Naming (pyarrow, dagster, otel)

Each optional-dependency extension exposes a factory function to wrap a `Store`.
Their naming is inconsistent with each other and with the pure-Python ext
factories:

| Module | Factory | Style | What it wraps |
|---|---|---|---|
| `ext/cache.py` | `cached_store(store)` | `<adjective>_store` | Store → CachedStore |
| `ext/observe.py` | `observe(store)` | bare verb | Store → ObservedStore |
| `ext/arrow.py` | `pyarrow_fs(store)` | `<library>_<concept>` | Store → PyFileSystem |
| `ext/dagster.py` | `remote_store_io_manager(store)` | `<our_library>_<concept>` | Store → IOManager |
| `ext/otel.py` | `otel_observe(store)` | `<library>_<verb>` | Store → ObservedStore |
| `ext/otel.py` | `otel_hooks()` | `<library>_<noun>` | → hook kwargs dict |

**Problems:**

- `remote_store_io_manager` — includes our own library name (`remote_store`)
  which is redundant since you're already importing from
  `remote_store.ext.dagster`. Every other factory omits the library name.
- `pyarrow_fs` — prefixes the external library name (`pyarrow`), which no other
  pure-Python ext factory does. The cache ext doesn't call its factory
  `lru_cached_store`; the observe ext doesn't call its factory
  `callback_observe`.
- The otel names (`otel_observe`, `otel_hooks`) do prefix the library name, but
  this is more defensible: `otel_observe` is a specialization of the existing
  `observe()` function, so the prefix disambiguates.

**Proposed renames:**

| Current | Proposed | Rationale |
|---|---|---|
| `remote_store_io_manager(store)` | `dagster_io_manager(store)` | Drop redundant `remote_store_` prefix; the external library name (`dagster`) is appropriate here since the return type is a Dagster `IOManager` — like `pyarrow_fs` returning a PyArrow `FileSystem` |
| `pyarrow_fs(store)` | (keep) | On reflection, the prefix is appropriate: the return type is `pyarrow.fs.PyFileSystem`, not a Store wrapper. Users need to know which ecosystem's object they're getting. |
| `otel_observe(store)` | (keep) | Prefix disambiguates from the existing `observe()` |
| `otel_hooks()` | (keep) | Prefix is natural for a hook-bag factory |

---

## 3. Class Naming in Extensions (pyarrow, dagster)

| Module | Class | Style |
|---|---|---|
| `ext/arrow.py` | `StoreFileSystemHandler` | `Store` + concept |
| `ext/dagster.py` | `_RemoteStoreIOManagerImpl` | `RemoteStore` + concept (private) |

- The private dagster class uses `RemoteStore` (two words) while the public
  arrow class uses just `Store`. Minor since `_RemoteStoreIOManagerImpl` is
  private, but worth noting.

**Proposed:** No rename needed — `_RemoteStoreIOManagerImpl` is private. If it
ever becomes public, prefer `StoreIOManager` to match `StoreFileSystemHandler`.

---

## 4. Summary of Recommended Changes

### Must fix (style clash):

1. **`pydantic_to_registry_config` → `from_pydantic`** — the `source_to_target`
   pattern is used nowhere else in the codebase.

2. **`remote_store_io_manager` → `dagster_io_manager`** — redundant
   `remote_store_` prefix; matches the `pyarrow_fs` pattern of
   `<external_lib>_<concept>`.

### Consider (minor asymmetries):

3. Pure-Python ext factories use bare verbs/adjectives (`observe`,
   `cached_store`) while optional-dep ext factories prefix the library name
   (`pyarrow_fs`, `otel_observe`). This is actually a useful convention — it
   signals "this returns a foreign type" vs "this returns a Store subtype". If
   adopted as a rule, document it.

### No action needed:

4. `from_yaml` — matches `from_*` pattern, standalone function is justified by
   ADR-0013.
5. `otel_observe`, `otel_hooks` — prefix disambiguates from core `observe()`.
6. `pyarrow_fs` — prefix matches the external-type-factory convention.

---

## 5. Migration Notes

Both renames (#1 and #2) would need:

- Deprecation alias in the old name (emit `DeprecationWarning`, remove in next
  minor/major)
- Update `__all__`, docstrings, tutorials, and CHANGELOG
- Spec updates (PYDANTIC spec, DAG spec)
- Backlog item for execution
