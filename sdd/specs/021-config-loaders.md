# Config Loaders Specification

## Overview

`RegistryConfig` gains two file-based loaders — `from_toml()` and `from_yaml()` —
that are thin translation layers over `from_dict()`. Both produce identical
`RegistryConfig` objects for equivalent input. The core config model does not change.

**Backlog items:** ID-005 (`from_toml`), ID-002 (`from_yaml`), ID-003 (Pydantic adapter)
**Research:** `sdd/research/research-store-config.md`
**Constraint:** ADR-0002 (no merging) — loaders are pre-processing steps that
produce a single immutable `RegistryConfig`.

---

## TOML Loader

### CFG-008: `from_toml()`

**Invariant:** `RegistryConfig.from_toml(path, *, table=())` reads a TOML file
and returns a `RegistryConfig`.

**Parameters:**
- `path: str | Path` — Path to the TOML file.
- `table: tuple[str, ...] = ()` — Dotted table path to extract. For
  `pyproject.toml`, use `table=("tool", "remote-store")`.

**Behavior:**
1. Parse the file via `tomllib` (3.11+) or `tomli` (3.10 backport).
2. If `table` is non-empty, traverse into the nested table.
3. Delegate to `from_dict()` (inherits Secret wrapping, validation).

**Raises:**
- `ModuleNotFoundError` if `tomllib` is unavailable and `tomli` is not installed.
  Message includes install instructions: `pip install 'remote-store[toml]'`.
- `KeyError` if a `table` key is not found in the parsed data.
- `FileNotFoundError` if `path` does not exist.
- `tomllib.TOMLDecodeError` if the file is not valid TOML.

**Postconditions:** The returned `RegistryConfig` is identical to calling
`from_dict()` on the parsed TOML dict (after table traversal).

### CFG-009: TOML Dependency Shim

**Invariant:** On Python 3.11+, `from_toml()` uses the stdlib `tomllib` with
zero runtime dependencies. On Python 3.10, the `tomli` backport is required
(available via the `toml` optional extra).

---

## YAML Loader

### CFG-010: `from_yaml()`

**Invariant:** `from_yaml(path)` (in `ext/yaml.py`) reads a YAML file and
returns a `RegistryConfig`.

**Location:** `remote_store/ext/yaml.py`

**Parameters:**
- `path: str | Path` — Path to the YAML file.

**Behavior:**
1. Parse the file via `yaml.safe_load` (pyyaml) or `ruamel.yaml` safe parser.
2. Validate the top-level value is a dict.
3. Delegate to `from_dict()` (inherits Secret wrapping, validation).

**Raises:**
- `ModuleNotFoundError` if neither `pyyaml` nor `ruamel.yaml` is installed.
  Message includes install instructions: `pip install 'remote-store[yaml]'`.
- `FileNotFoundError` if `path` does not exist.
- `TypeError` if the top-level YAML value is not a mapping.
- `yaml.YAMLError` (pyyaml) or `ruamel.yaml.YAMLError` (ruamel) if the file
  is not valid YAML.

**Design note:** No `key`/`table` parameter. YAML has no shared-file convention
like `pyproject.toml`. Users with nested YAML use
`yaml.safe_load(f)["key"] → from_dict()`. A `key` parameter can be added later
without breaking changes if demand emerges.

### CFG-011: YAML Library Precedence

**Invariant:** `from_yaml()` prefers `pyyaml` (`yaml.safe_load`). If `pyyaml`
is not installed, it falls back to `ruamel.yaml` (safe mode). If neither is
available, `ModuleNotFoundError` is raised.

**Rationale:** `pyyaml` is ubiquitous (~300M downloads/month) and simpler.
`ruamel.yaml` is a viable alternative but heavier. Accepting both avoids
forcing a specific library on users who already have one installed.

---

## Cross-Cutting

### CFG-012: Unknown Top-Level Keys Warning

**Invariant:** `from_dict()` emits a `UserWarning` for top-level keys other
than `"backends"` and `"stores"`. This catches typos like `"backend"` (singular)
or `"store"` that would otherwise silently produce an empty config.

**Behavior:** Uses `warnings.warn()` with `stacklevel` adjusted so the
warning source points to user code. Direct `from_dict()` calls use
`stacklevel=2`; indirect calls via `from_toml()`, `from_yaml()`, and
`pydantic_to_registry_config()` use `stacklevel=3`. Does not raise.

### CFG-013: Loader Equivalence

**Invariant:** `from_toml()`, `from_yaml()`, `from_dict()`, and
`pydantic_to_registry_config()` produce identical `RegistryConfig` objects for
semantically equivalent input. All Secret wrapping, type coercion, and
validation happens in `from_dict()` — the loaders/adapters are pure
format-to-dict translators.

### CFG-014: Optional Extras

**Invariant:** `pyproject.toml` declares optional extras:
- `toml`: `["tomli>=1.1.0; python_version < '3.11'"]`
- `yaml`: `["pyyaml>=5.1"]`
- `pydantic`: `["pydantic-settings>=2.0.0"]`

---

## Pydantic Adapter

### CFG-015: `pydantic_to_registry_config()`

**Invariant:** `pydantic_to_registry_config(model)` converts any Pydantic
`BaseModel` instance to a `RegistryConfig`.

**Location:** `remote_store/ext/pydantic.py`

**Parameters:**
- `model: BaseModel` — A Pydantic model whose `model_dump()` output conforms
  to the `RegistryConfig` schema (i.e. has `backends` and `stores` keys).

**Behavior:**
1. Call `model.model_dump()` to produce a plain dict.
2. Delegate to `RegistryConfig.from_dict()` (inherits Secret wrapping,
   unknown-key warning, validation).

**Raises:**
- `ModuleNotFoundError` if `pydantic` is not installed. Message includes
  install instructions: `pip install 'remote-store[pydantic]'`.
- Any exception from `from_dict()` (e.g. `TypeError`, `KeyError`).

**Postconditions:** The returned `RegistryConfig` is identical to calling
`RegistryConfig.from_dict(model.model_dump())`.

**SecretStr note:** Pydantic `SecretStr` fields are **not** auto-unwrapped.
`model_dump()` returns `SecretStr` objects (not plain strings), which bypass
`from_dict()`'s `isinstance(v, str)` check and are **not** re-wrapped in
`Secret`. Users should use plain `str` for credential values in their
model's `options` dicts — `from_dict()` handles Secret wrapping at the
config→registry boundary.

### CFG-016: ADR-0002 Compatibility

**Invariant:** The Pydantic adapter operates entirely on the user side.
Pydantic's source merging (env vars, `.env` files, config files) happens
*before* `pydantic_to_registry_config()` is called. The resulting
`RegistryConfig` is immutable and subject to ADR-0002 (no further merging).

**Flow:**
```text
User's Pydantic model (merges env + .env + files)
    → pydantic_to_registry_config() → from_dict()
        → RegistryConfig (immutable, ADR-0002 applies)
```

### CFG-017: Extension Contract

**Invariant:** `ext/pydantic.py` follows the extension architecture (ADR-0008):
- Defines `__all__`.
- Uses only the public `RegistryConfig.from_dict()` API.
- Imported directly from `remote_store.ext.pydantic` (ADR-0013).
- Import of `pydantic` is guarded at module level with a clear error message.

---

## File Placement

| Component | Location |
|-----------|----------|
| `from_toml()` | `_config.py` classmethod on `RegistryConfig` |
| `from_yaml()` | `ext/yaml.py` standalone function |
| Unknown-key warning | `_config.py` inside `from_dict()` |
| Pydantic adapter | `ext/pydantic.py` |
| Optional extras | `pyproject.toml` `[project.optional-dependencies]` |

---

## Example TOML

```toml
# remote-store.toml
[backends.local]
type = "local"
options.root = "/data/store"

[backends.s3-prod]
type = "s3"
options.bucket = "prod-data"
options.region_name = "eu-central-1"

[stores.raw-events]
backend = "s3-prod"
root_path = "events/raw"

[stores.local-cache]
backend = "local"
root_path = "cache"
```

```python
config = RegistryConfig.from_toml("remote-store.toml")

# From pyproject.toml:
config = RegistryConfig.from_toml("pyproject.toml", table=("tool", "remote-store"))
```

## Example YAML

```yaml
# remote-store.yaml
backends:
  s3-prod:
    type: s3
    options:
      bucket: prod-data
      region_name: eu-central-1

stores:
  raw-events:
    backend: s3-prod
    root_path: events/raw
```

```python
from remote_store.ext.yaml import from_yaml

config = from_yaml("remote-store.yaml")
```

## Example Pydantic

```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from remote_store.ext.pydantic import pydantic_to_registry_config

class BackendEntry(BaseModel):
    type: str
    options: dict[str, object] = {}

class StoreEntry(BaseModel):
    backend: str
    root_path: str = ""
    options: dict[str, object] = {}

class RemoteStoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RS_",
        env_nested_delimiter="__",
    )

    backends: dict[str, BackendEntry] = {}
    stores: dict[str, StoreEntry] = {}

settings = RemoteStoreSettings()
config = pydantic_to_registry_config(settings)
```
