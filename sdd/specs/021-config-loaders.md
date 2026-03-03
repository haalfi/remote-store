# Config Loaders Specification

## Overview

`RegistryConfig` gains two file-based loaders — `from_toml()` and `from_yaml()` —
that are thin translation layers over `from_dict()`. Both produce identical
`RegistryConfig` objects for equivalent input. The core config model does not change.

**Backlog items:** ID-005 (`from_toml`), ID-002 (`from_yaml`)
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

**Invariant:** `RegistryConfig.from_yaml(path)` reads a YAML file and returns
a `RegistryConfig`.

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
- `yaml.YAMLError` if the file is not valid YAML.

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

**Behavior:** Uses `warnings.warn()` with `stacklevel=2`. Does not raise.

### CFG-013: Loader Equivalence

**Invariant:** `from_toml()`, `from_yaml()`, and `from_dict()` produce identical
`RegistryConfig` objects for semantically equivalent input. All Secret wrapping,
type coercion, and validation happens in `from_dict()` — the file loaders are
pure format-to-dict translators.

### CFG-014: Optional Extras

**Invariant:** `pyproject.toml` declares optional extras:
- `toml`: `["tomli>=1.1.0; python_version < '3.11'"]`
- `yaml`: `["pyyaml>=5.1"]`

---

## File Placement

| Component | Location |
|-----------|----------|
| `from_toml()` | `_config.py` classmethod on `RegistryConfig` |
| `from_yaml()` | `_config.py` classmethod on `RegistryConfig` |
| Unknown-key warning | `_config.py` inside `from_dict()` |
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
config = RegistryConfig.from_yaml("remote-store.yaml")
```
