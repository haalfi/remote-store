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
`from_pydantic()` use `stacklevel=3`. Does not raise.

### CFG-013: Loader Equivalence

**Invariant:** `from_toml()`, `from_yaml()`, `from_dict()`, and
`from_pydantic()` produce identical `RegistryConfig` objects for
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

### CFG-015: `from_pydantic()`

**Invariant:** `from_pydantic(model)` converts any Pydantic
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

**SecretStr handling:** Pydantic `SecretStr` fields in backend `options`
dicts are automatically unwrapped to plain strings before reaching
`from_dict()`, so `from_dict()`'s sensitive-key detection works correctly.
Users may use either `str` or `SecretStr` for credential values in their
models.

### CFG-016: ADR-0002 Compatibility

**Invariant:** The Pydantic adapter operates entirely on the user side.
Pydantic's source merging (env vars, `.env` files, config files) happens
*before* `from_pydantic()` is called. The resulting
`RegistryConfig` is immutable and subject to ADR-0002 (no further merging).

**Flow:**
```text
User's Pydantic model (merges env + .env + files)
    → from_pydantic() → from_dict()
        → RegistryConfig (immutable, ADR-0002 applies)
```

### CFG-017: Extension Contract

**Invariant:** `ext/pydantic.py` follows the extension architecture (ADR-0008):
- Defines `__all__`.
- Uses only the public `RegistryConfig.from_dict()` API.
- Imported directly from `remote_store.ext.pydantic` (ADR-0013).
- Import of `pydantic` is guarded at module level with a clear error message.

---

## Environment Variable Interpolation

**Backlog item:** ID-126
**Motivation:** Every backend that touches a remote system needs credentials.
Outside Pydantic, the dominant real-world pattern is env-var injection — but
`from_yaml()` and `from_toml()` offer no help, forcing users to write 10–15
lines of boilerplate (parse file → mutate dict → inject from `os.environ` →
call `from_dict()`). The Pydantic adapter solves this via `BaseSettings`, but
YAML/TOML users deserve the same ergonomics.

### CFG-018: `resolve_env()` Function

**Invariant:** `resolve_env(data, *, environ=None)` recursively resolves
`${VAR}` placeholders in a config dict and returns a new dict.

**Location:** `_config.py`, public export via `remote_store`.

**Parameters:**
- `data: dict[str, object]` — Config dict (typically parsed from YAML/TOML).
- `environ: Mapping[str, str] | None` — Variable source. Defaults to
  `os.environ`.

**Returns:** A deep copy of *data* with all placeholder strings resolved.
The original dict is never mutated.

**Raises:**
- `KeyError` if a placeholder references a variable that is not set and has
  no default. The error message includes the variable name and the config
  key path where it was found.

**Postconditions:**
- Non-string values (numbers, booleans, `None`, nested dicts, lists) are
  traversed but never modified.
- Keys are never interpolated — only values.
- The returned dict is suitable for `RegistryConfig.from_dict()`.

### CFG-019: Placeholder Syntax

**Invariant:** Two placeholder forms are supported:

| Form | Behavior |
|------|----------|
| `${VAR}` | Substitute the value of `VAR`; raise `KeyError` if unset |
| `${VAR:-default}` | Substitute the value of `VAR`; use `default` if unset |

**Rules:**
1. Placeholders may appear as the entire value (`${S3_KEY}`) or embedded in
   a larger string (`https://${HOST}:${PORT}/path`).
2. Multiple placeholders in one string are resolved left-to-right.
3. A full-value placeholder that resolves to a string remains a string — no
   type coercion. The YAML/TOML parser already determined the type by using
   the `${}` syntax (which is always a string).
4. Literal `${` that should not be interpolated can be escaped as `$${`
   (produces literal `${` in output).
5. Nested placeholders (`${${INNER}}`) are not supported.
6. Default values are literal strings — they do not undergo further
   interpolation.

**Syntax reference:** Follows the Docker Compose `${VAR}` / `${VAR:-default}`
convention — the de facto standard across Docker, Spring Boot, GitHub Actions,
and shell parameter expansion.

### CFG-020: Loader Integration

**Invariant:** `from_yaml()` and `from_toml()` accept an optional
`resolve_env: bool = False` keyword argument.

**Behavior:**
- When `resolve_env=False` (default): no change to current behavior.
- When `resolve_env=True`: the parsed dict is passed through `resolve_env()`
  before delegation to `from_dict()`.

**Flow (YAML example):**
```text
YAML file → yaml.safe_load() → resolve_env() → from_dict()
    → RegistryConfig (immutable, ADR-0002 applies)
```

**Design note:** `from_dict()` does **not** gain a `resolve_env` parameter.
It accepts already-constructed dicts where interpolation would be surprising.
Users who build dicts manually and want interpolation call `resolve_env()`
explicitly.

### CFG-021: ADR-0002 Compatibility

**Invariant:** `resolve_env()` is a pre-processing step that runs *before*
`RegistryConfig` construction. It occupies the same architectural position as
Pydantic's `BaseSettings` env-var resolution (CFG-016): user-side glue that
produces a single, final dict. Once the `RegistryConfig` is constructed,
ADR-0002 applies — no further merging or env-var lookups.

**Opt-in only:** The default is `resolve_env=False`. No loader reads
environment variables unless the caller explicitly opts in. This preserves
determinism, test safety, and the "same code = same behavior" guarantee.

**No `.env` loading:** `resolve_env()` reads from `os.environ` (or the
provided `environ` mapping). Loading `.env` files is the user's responsibility
(e.g. via `python-dotenv`). This keeps the function pure and predictable.

**No vault integration:** Secret managers (HashiCorp Vault, AWS Secrets
Manager, Azure Key Vault) populate env vars or provide their own SDKs.
`resolve_env()` consumes the result — it does not integrate with any
specific vault provider.

---

## File Placement

| Component | Location |
|-----------|----------|
| `from_toml()` | `_config.py` classmethod on `RegistryConfig` |
| `from_yaml()` | `ext/yaml.py` standalone function |
| `resolve_env()` | `_config.py` standalone function, public export |
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
from remote_store.ext.pydantic import from_pydantic

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
config = from_pydantic(settings)
```

## Example: YAML with Environment Variable Secrets

```yaml
# remote-store.yaml
backends:
  s3-prod:
    type: s3
    options:
      bucket: prod-data
      region_name: eu-central-1
      key: ${AWS_ACCESS_KEY_ID}
      secret: ${AWS_SECRET_ACCESS_KEY}
  sftp:
    type: sftp
    options:
      host: files.vendor.com
      username: ${SFTP_USER}
      password: ${SFTP_PASSWORD:-}

stores:
  raw-events:
    backend: s3-prod
    root_path: events/raw
```

```python
from remote_store.ext.yaml import from_yaml

# One line — env vars resolved, secrets wrapped, config immutable
config = from_yaml("remote-store.yaml", resolve_env=True)
```

## Example: TOML with Environment Variable Secrets

```toml
# remote-store.toml
[backends.s3-prod]
type = "s3"
options.bucket = "prod-data"
options.key = "${AWS_ACCESS_KEY_ID}"
options.secret = "${AWS_SECRET_ACCESS_KEY}"

[stores.raw-events]
backend = "s3-prod"
root_path = "events/raw"
```

```python
config = RegistryConfig.from_toml("remote-store.toml", resolve_env=True)
```

## Example: Standalone `resolve_env()` with Custom Loader

```python
import json
from remote_store import RegistryConfig, resolve_env

with open("config.json") as f:
    data = json.load(f)

config = RegistryConfig.from_dict(resolve_env(data))
```
