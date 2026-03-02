# Research: Configuration Loaders and Store Config Patterns

**Date:** 2026-03-02
**Backlog items:** ID-002 (YAML config support), ID-003 (Pydantic BaseSettings integration), ID-005 (Built-in `from_toml()` config loader)
**Status:** Research complete — awaiting design decisions

---

## 1. Executive Summary

This document researches how `remote-store` should extend its configuration
surface beyond the current `RegistryConfig.from_dict()`. The three backlog ideas
under review are:

| ID | Proposal | Dependency impact |
|----|----------|-------------------|
| **ID-002** | `RegistryConfig.from_yaml(path)` | Optional: `pyyaml` or `ruamel.yaml` |
| **ID-003** | Pydantic `BaseSettings` integration | Optional: `pydantic-settings` |
| **ID-005** | `RegistryConfig.from_toml(path)` | Zero on 3.11+; optional `tomli` on 3.10 |

A cross-cutting theme is that **a single backend technology often needs multiple
configurations** — the same S3 bucket accessed with different credentials, or
the same Azure account using account-key in production and connection-string in
CI. The config system must support this naturally without forcing users to
duplicate boilerplate.

**Headline findings:**

1. `from_toml()` (ID-005) is the lowest-friction, highest-value addition — zero
   runtime dependency on 3.11+, aligns with Python packaging conventions, and
   the TOML structure maps cleanly to the existing dict schema.
2. `from_yaml()` (ID-002) is straightforward but adds an optional dependency.
   `pyyaml` is the pragmatic choice (ubiquitous, simple); `ruamel.yaml` is
   technically superior but heavier.
3. Pydantic `BaseSettings` (ID-003) is the most complex but enables env-var
   binding, `.env` file loading, and type validation. It serves a different user
   segment (framework-heavy apps like FastAPI) and should be designed as an
   *adapter*, not a replacement for the core config model.
4. All three loaders are **thin translation layers** over `from_dict()`. The
   core config model (`BackendConfig`, `StoreProfile`, `RegistryConfig`) does
   not change.

---

## 2. Current State

### 2.1 Config model

Three frozen dataclasses in `src/remote_store/_config.py`:

```
RegistryConfig
├── backends: dict[str, BackendConfig]
│   └── BackendConfig(type: str, options: dict[str, object])
└── stores: dict[str, StoreProfile]
    └── StoreProfile(backend: str, root_path: str, options: dict[str, object])
```

### 2.2 Loading path

`RegistryConfig.from_dict(data)` is the only loader. It expects:

```python
{
    "backends": {
        "<name>": {"type": "<type>", "options": {<kwargs>}},
    },
    "stores": {
        "<name>": {"backend": "<backend-name>", "root_path": "<prefix>"},
    },
}
```

The Registry instantiates backends via `factory(**cfg.options)` — a direct
kwarg splat. This means `options` keys must exactly match constructor parameter
names.

### 2.3 ADR-0002: No merging

Config-as-code has absolute priority. No env-var merging, no layering. If
`RegistryConfig` is provided, it is used exclusively. This is a deliberate
design decision for determinism and test safety.

**Implication for this research:** All three loaders must produce a complete
`RegistryConfig`. We do not layer TOML + env vars + defaults. Users who want
env-var injection do it *before* constructing the config (or use the Pydantic
adapter which handles this in its own layer, yielding a final `RegistryConfig`
that is then used exclusively).

---

## 3. Backend Configuration Landscape

Understanding the full configuration surface per backend is essential for
evaluating how well each format and loader handles real-world configs.

### 3.1 Configuration options by backend

| Backend | Type | Required | Optional | Sensitive |
|---------|------|----------|----------|-----------|
| **Local** | `"local"` | `root` | — | — |
| **Memory** | `"memory"` | — | — | — |
| **S3** | `"s3"` | `bucket` | `key`, `secret`, `region_name`, `endpoint_url`, `client_options` | `key`, `secret` |
| **S3-PyArrow** | `"s3-pyarrow"` | `bucket` | `key`, `secret`, `region_name`, `endpoint_url`, `client_options` | `key`, `secret` |
| **SFTP** | `"sftp"` | `host` | `port`, `username`, `password`, `pkey`, `base_path`, `host_key_policy`, `known_host_keys`, `host_keys_path`, `config`, `timeout`, `connect_kwargs` | `password`, `pkey` |
| **Azure** | `"azure"` | `container` + one of (`account_name`, `account_url`, `connection_string`) | `account_key`, `sas_token`, `credential`, `client_options` | `account_key`, `sas_token`, `connection_string`, `credential` |

### 3.2 Multiple configs per backend technology

A single project commonly needs multiple backend configs of the **same type**
with different credentials or endpoints. Examples:

```
# Same S3 technology, different access patterns
backends:
  s3-prod:       {type: s3, options: {bucket: prod-data, region_name: eu-central-1}}
  s3-analytics:  {type: s3, options: {bucket: analytics, key: AKIA..., secret: ...}}
  s3-minio-dev:  {type: s3, options: {bucket: dev, endpoint_url: http://localhost:9000, key: minioadmin, secret: minioadmin}}

# Same Azure technology, different auth methods
backends:
  az-prod:       {type: azure, options: {container: prod, account_name: acme}}          # DefaultAzureCredential
  az-ci:         {type: azure, options: {container: test, connection_string: "..."}}     # Connection string
  az-readonly:   {type: azure, options: {container: prod, account_name: acme, sas_token: "sv=..."}}

# SFTP to different hosts
backends:
  sftp-vendor-a: {type: sftp, options: {host: files.vendor-a.com, username: upload, password: "..."}}
  sftp-vendor-b: {type: sftp, options: {host: sftp.vendor-b.io, username: etl, pkey: <PKey>}}
```

Multiple stores then map to these backends:

```
stores:
  raw-events:    {backend: s3-prod,       root_path: events/raw}
  aggregates:    {backend: s3-analytics,   root_path: agg/v2}
  dev-scratch:   {backend: s3-minio-dev,  root_path: scratch}
  invoices:      {backend: az-prod,        root_path: invoices/2026}
  test-fixtures: {backend: az-ci,          root_path: fixtures}
  vendor-a-drop: {backend: sftp-vendor-a,  root_path: /incoming}
  vendor-b-drop: {backend: sftp-vendor-b,  root_path: /data/drop}
```

**Key design requirement:** The config format must allow an arbitrary number of
backend entries of the same type, each with its own credential set. This is
already supported by the current dict schema (backends are keyed by user-chosen
names, not by type), and all three file formats handle this naturally.

### 3.3 Sensitive values and the secrets problem

The most common pain points in configuration:

| Problem | Frequency | Affected backends |
|---------|-----------|-------------------|
| Secrets in config files (committed to VCS) | Very common | S3, SFTP, Azure |
| Different secrets per environment (dev/staging/prod) | Very common | All cloud |
| Non-string credentials (`pkey` is a `paramiko.PKey` object) | SFTP only | SFTP |
| Credential objects (`DefaultAzureCredential()`) | Azure only | Azure |

**Observation:** TOML and YAML can express all *string-serializable* options,
but `pkey` (a `paramiko.PKey` instance) and `credential` (an Azure credential
object) cannot be represented in any config file format. These always require
code-level construction. This is acceptable — the `from_dict()` / `from_toml()`
/ `from_yaml()` path is for the common case; complex credentials use the
Python-object constructor.

Possible mitigations for file-based configs:

1. **`pkey` from PEM string:** SFTP's `load_private_key()` can load from a PEM
   string. A TOML/YAML config could store `pkey_pem: "-----BEGIN RSA..."` and a
   thin post-processing step converts it. However, this is *outside* the scope
   of `from_toml()` / `from_yaml()` — those are pure dict loaders.
2. **Secrets via env vars:** The Pydantic adapter (ID-003) handles this
   natively. For TOML/YAML, users inject secrets before calling `from_dict()`.
3. **Recommendation:** Document the pattern of loading TOML/YAML for structure,
   then overriding `options` with secrets from env vars / vault before
   constructing the `RegistryConfig`. Do *not* build env-var resolution into
   `from_toml()` / `from_yaml()` (ADR-0002).

---

## 4. ID-005: `from_toml()` — TOML Config Loader

### 4.1 Why TOML

- **stdlib on 3.11+:** `tomllib` is built-in since Python 3.11 (PEP 680).
  `tomli` is the compatible backport for 3.10.
- **Python ecosystem alignment:** `pyproject.toml` is the standard for project
  config. Tools like `pytest`, `mypy`, `ruff`, `black` all use TOML.
- **Strict typing:** TOML distinguishes strings, integers, booleans, arrays,
  and tables — unlike YAML, there are no ambiguous value types.
- **Read-only is fine:** `tomllib` is read-only by design. We only need to
  *read* config.

### 4.2 Dependency strategy

```python
# Compatibility shim (standard pattern)
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]
```

| Python version | Module | Dependency |
|----------------|--------|------------|
| 3.11+ | `tomllib` (stdlib) | None |
| 3.10 | `tomli` (backport) | Optional extra |

Since remote-store targets `>=3.10`, the optional extra would be:

```toml
[project.optional-dependencies]
toml = ["tomli>=1.1.0; python_version < '3.11'"]
```

Alternatively, since `tomli` is tiny (~3 KB) and pure Python, it could be a
hard dependency for 3.10 users without an extra. But the extra approach is
more consistent with our "zero core dependencies" philosophy.

### 4.3 TOML schema

Natural mapping from the existing dict schema:

```toml
# remote-store.toml (standalone) or [tool.remote-store] in pyproject.toml

[backends.local]
type = "local"
options.root = "/data/store"

[backends.s3-prod]
type = "s3"

[backends.s3-prod.options]
bucket = "prod-data"
region_name = "eu-central-1"
# key and secret intentionally omitted — use IAM role or inject at runtime

[backends.s3-dev]
type = "s3"

[backends.s3-dev.options]
bucket = "dev-data"
endpoint_url = "http://localhost:9000"
key = "minioadmin"
secret = "minioadmin"

[backends.azure]
type = "azure"

[backends.azure.options]
container = "my-container"
account_name = "mystorageaccount"

[stores.raw-events]
backend = "s3-prod"
root_path = "events/raw"

[stores.scratch]
backend = "s3-dev"
root_path = "scratch"

[stores.documents]
backend = "azure"
root_path = "documents"

[stores.local-cache]
backend = "local"
root_path = "cache"
```

This maps 1:1 to the dict that `from_dict()` already accepts.

### 4.4 Proposed API

```python
@classmethod
def from_toml(
    cls,
    path: str | Path,
    *,
    table: tuple[str, ...] = (),
) -> RegistryConfig:
    """Load config from a TOML file.

    :param path: Path to the TOML file.
    :param table: Dotted table path to extract config from.
        For pyproject.toml use ``table=("tool", "remote-store")``.
    """
```

The `table` parameter enables reading from a nested table, which is essential
for `pyproject.toml` usage:

```python
# Standalone file
config = RegistryConfig.from_toml("remote-store.toml")

# From pyproject.toml
config = RegistryConfig.from_toml("pyproject.toml", table=("tool", "remote-store"))
```

### 4.5 Implementation sketch

```python
@classmethod
def from_toml(cls, path: str | Path, *, table: tuple[str, ...] = ()) -> RegistryConfig:
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "TOML support requires tomli on Python < 3.11. "
                "Install it with: pip install 'remote-store[toml]'"
            ) from None

    with open(path, "rb") as f:
        data = tomllib.load(f)

    for key in table:
        if not isinstance(data, dict) or key not in data:
            raise KeyError(f"Table key {key!r} not found in {path}")
        data = data[key]

    return cls.from_dict(data)
```

~15 lines of logic. Delegates entirely to `from_dict()`.

### 4.6 Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Implementation effort | Very low | ~15 lines wrapping `from_dict()` |
| Dependency cost | Zero on 3.11+; `tomli` on 3.10 | Aligns with zero-dep philosophy |
| User demand | High | TOML is the standard Python config format |
| Risk | Very low | Pure translation layer, no new semantics |
| Multi-backend support | Natural | TOML tables map cleanly to nested dicts |

---

## 5. ID-002: `from_yaml()` — YAML Config Loader

### 5.1 Why YAML

- **Familiar:** Widely used for application config (Kubernetes, Ansible,
  Docker Compose, etc.).
- **Readable:** More compact than TOML for deeply nested structures.
- **Comments:** YAML supports inline comments (like TOML, unlike JSON).

### 5.2 Library comparison

| Feature | PyYAML | ruamel.yaml |
|---------|--------|-------------|
| YAML spec | 1.1 | **1.2** |
| Comment preservation | No | Yes |
| Round-trip editing | No | Yes |
| Safety defaults | Unsafe `yaml.load()` by default | Safer |
| Install size | Small | Larger |
| PyPI downloads | ~300M/month | ~2.5M/month |
| API simplicity | Simple | More complex |

**Recommendation: `pyyaml`.** We only need read-only parsing of config files.
We do not need comment preservation or round-trip editing. `pyyaml` is
ubiquitous (likely already installed in most environments), simpler, and
well-tested. The YAML 1.1 vs 1.2 differences (`yes`/`no` as booleans) are
irrelevant for our config schema — all our option values are explicit strings,
numbers, or dicts.

However, we should accept *either* library — users who have `ruamel.yaml`
installed should be able to use it. The import strategy:

```python
try:
    from yaml import safe_load  # pyyaml
except ImportError:
    try:
        from ruamel.yaml import YAML
        _yaml = YAML(typ="safe")
        safe_load = _yaml.load  # ruamel.yaml
    except ImportError:
        safe_load = None
```

### 5.3 YAML schema

```yaml
# remote-store.yaml
backends:
  s3-prod:
    type: s3
    options:
      bucket: prod-data
      region_name: eu-central-1

  s3-dev:
    type: s3
    options:
      bucket: dev-data
      endpoint_url: "http://localhost:9000"
      key: minioadmin
      secret: minioadmin

  azure:
    type: azure
    options:
      container: my-container
      account_name: mystorageaccount

  sftp-vendor:
    type: sftp
    options:
      host: files.vendor.com
      port: 22
      username: etl
      password: "${VENDOR_PASSWORD}"  # user resolves before loading
      base_path: /incoming
      timeout: 30

stores:
  raw-events:
    backend: s3-prod
    root_path: events/raw

  scratch:
    backend: s3-dev
    root_path: scratch

  documents:
    backend: azure
    root_path: documents

  vendor-drop:
    backend: sftp-vendor
    root_path: incoming
```

Again, maps 1:1 to the dict schema.

### 5.4 Proposed API

```python
@classmethod
def from_yaml(
    cls,
    path: str | Path,
) -> RegistryConfig:
    """Load config from a YAML file.

    :param path: Path to the YAML file.
    :raises ModuleNotFoundError: If neither pyyaml nor ruamel.yaml is installed.
    """
```

Simpler than TOML — no `table` parameter needed because YAML files are
typically standalone (no `pyproject.yaml` convention).

### 5.5 Implementation sketch

```python
@classmethod
def from_yaml(cls, path: str | Path) -> RegistryConfig:
    try:
        from yaml import safe_load
    except ImportError:
        try:
            from ruamel.yaml import YAML
            _yaml = YAML(typ="safe")
            safe_load = _yaml.load
        except ImportError:
            raise ModuleNotFoundError(
                "YAML support requires pyyaml or ruamel.yaml. "
                "Install with: pip install pyyaml"
            ) from None

    with open(path) as f:
        data = safe_load(f)

    if not isinstance(data, dict):
        raise TypeError(f"Expected YAML mapping at top level, got {type(data).__name__}")

    return cls.from_dict(data)
```

~20 lines. Delegates to `from_dict()`.

### 5.6 YAML pitfalls for config files

| Pitfall | Impact on remote-store | Mitigation |
|---------|----------------------|------------|
| `yes`/`no`/`on`/`off` parsed as booleans (YAML 1.1) | Port numbers like `port: 22` are fine; but `host_key_policy: "STRICT"` needs quoting if a future option name collides | Document: always quote string values that could be ambiguous |
| Indentation errors silently change structure | Could produce malformed config | `from_dict()` validation catches invalid structures |
| No native type distinction (everything is a string without explicit tags) | Numbers and booleans auto-convert, which is actually desirable for our schema | Non-issue |
| `yaml.load()` is unsafe | Remote code execution if using untrusted input | Always use `safe_load()` — enforced in our implementation |

### 5.7 Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Implementation effort | Very low | ~20 lines wrapping `from_dict()` |
| Dependency cost | Optional `pyyaml` | Ubiquitous, likely already installed |
| User demand | Medium | YAML is common but less so in Python-native tooling |
| Risk | Low | `safe_load()` mitigates security; `from_dict()` validates |
| Multi-backend support | Natural | YAML mappings are dicts |

---

## 6. ID-003: Pydantic `BaseSettings` Integration

### 6.1 Why Pydantic

Pydantic `BaseSettings` (from `pydantic-settings`) provides:

- **Env-var binding:** Fields automatically populate from environment variables.
- **`.env` file support:** Load from `.env` files.
- **Type validation:** Constructor-time validation with clear error messages.
- **Nested model support:** `env_nested_delimiter` for `APP__DB__HOST=...`.
- **Built-in file sources:** `TomlConfigSettingsSource`, `YamlConfigSettingsSource`,
  `JsonConfigSettingsSource`.
- **Source priority customization:** Init > CLI > env > `.env` > file > secrets > defaults.
- **Docker secrets:** `secrets_dir='/run/secrets'`.

This is the go-to configuration approach for FastAPI, Django, and other
framework-heavy Python applications. As of March 2026, `pydantic-settings`
v2.13+ supports Python 3.10–3.14.

### 6.2 Design challenge: ADR-0002 tension

ADR-0002 says "no merging, no env var overrides." Pydantic `BaseSettings` is
*built for* merging and env var overrides. These appear to conflict.

**Resolution:** The Pydantic adapter operates in its *own* layer. It merges
env vars, `.env` files, and config files to produce a *final* `RegistryConfig`.
Once that `RegistryConfig` is constructed, ADR-0002 applies — the Registry uses
it exclusively with no further merging. The Pydantic layer is user-side glue,
not core library behavior.

```
User's Pydantic model (merges env + .env + files)
    ↓ produces
RegistryConfig (immutable, no further merging)
    ↓ used by
Registry (ADR-0002 applies here)
```

This is consistent with ADR-0002's note: "those users can build their own
config loader and pass `RegistryConfig`." The Pydantic adapter is exactly that
— a pre-built config loader that users opt into.

### 6.3 Proposed design: adapter, not replacement

The Pydantic integration should be an **adapter module** (e.g.,
`remote_store.ext.pydantic` or a top-level helper), not a modification to the
core config model. The core remains pure dataclasses with zero dependencies.

#### Option A: Pydantic models that produce RegistryConfig

```python
# remote_store/ext/pydantic.py (or remote_store/_pydantic.py)
from pydantic_settings import BaseSettings
from pydantic import Field

class S3Options(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RS_S3_")

    bucket: str
    key: str | None = None
    secret: str | None = None
    region_name: str | None = None
    endpoint_url: str | None = None

class AzureOptions(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RS_AZURE_")

    container: str
    account_name: str | None = None
    account_key: str | None = None
    sas_token: str | None = None
    connection_string: str | None = None

class SFTPOptions(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RS_SFTP_")

    host: str
    port: int = 22
    username: str | None = None
    password: str | None = None
    base_path: str = "/"
    timeout: int = 10

class RemoteStoreSettings(BaseSettings):
    """Pydantic settings that produces a RegistryConfig."""

    def to_registry_config(self) -> RegistryConfig:
        ...
```

#### Option B: Generic converter from any Pydantic model

```python
def pydantic_to_registry_config(settings: BaseModel) -> RegistryConfig:
    """Convert a Pydantic model to RegistryConfig.

    Expects the model to have 'backends' and 'stores' fields
    matching the RegistryConfig schema.
    """
    return RegistryConfig.from_dict(settings.model_dump())
```

#### Recommendation: Option B with documented patterns

Option A is opinionated and hard to maintain — it pre-defines env var prefixes
and field structures that may not match every user's deployment. Option B is a
thin utility that users combine with their own Pydantic models. We provide
*documented example patterns*, not rigid pre-built models.

### 6.4 Multi-backend configs with Pydantic

The key challenge with Pydantic is mapping *multiple* backend instances of the
same type to *different* env var prefixes:

```bash
# How does the user configure two S3 backends via env vars?
RS_BACKENDS__S3_PROD__TYPE=s3
RS_BACKENDS__S3_PROD__OPTIONS__BUCKET=prod-data
RS_BACKENDS__S3_PROD__OPTIONS__KEY=AKIA...
RS_BACKENDS__S3_DEV__TYPE=s3
RS_BACKENDS__S3_DEV__OPTIONS__BUCKET=dev-data
RS_BACKENDS__S3_DEV__OPTIONS__KEY=AKIA...
```

This works with `env_nested_delimiter="__"` but is verbose. The Pydantic
settings model:

```python
class BackendEntry(BaseModel):
    type: str
    options: dict[str, Any] = {}

class StoreEntry(BaseModel):
    backend: str
    root_path: str = ""
    options: dict[str, Any] = {}

class RemoteStoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RS_",
        env_nested_delimiter="__",
    )

    backends: dict[str, BackendEntry] = {}
    stores: dict[str, StoreEntry] = {}

    def to_registry_config(self) -> RegistryConfig:
        return RegistryConfig.from_dict(self.model_dump())
```

Then env vars `RS_BACKENDS__S3_PROD__OPTIONS__BUCKET=prod-data` resolve
correctly. This is *documented pattern*, not library code.

### 6.5 Pydantic's built-in file sources

As of `pydantic-settings` 2.13+, users can combine env vars with TOML, YAML,
and JSON files in a single `BaseSettings` class. This means the Pydantic
adapter partially subsumes ID-002 and ID-005 for users who adopt it — but only
for those users. The standalone `from_toml()` and `from_yaml()` remain
valuable for users who don't want Pydantic.

### 6.6 Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Implementation effort | Medium | Adapter + documentation + examples |
| Dependency cost | Optional `pydantic-settings` (+ `pydantic`) | Heavy; ~5 MB |
| User demand | Medium-high | Strong in FastAPI/Django ecosystem |
| Risk | Medium | Must not violate ADR-0002 semantics |
| Multi-backend support | Works but verbose | `env_nested_delimiter` handles it |
| ADR-0002 compatibility | Compatible | Pydantic merges *then* produces RegistryConfig |

---

## 7. Cross-Cutting Concerns

### 7.1 Secrets in config files

None of the three loaders should resolve secrets from env vars or vaults.
This is the user's responsibility (per ADR-0002). However, we should document
the common patterns:

| Pattern | When to use | How |
|---------|-------------|-----|
| Inject before `from_dict()` | Simple scripts | Load TOML/YAML, replace secrets from `os.environ`, call `from_dict()` |
| Pydantic env-var binding | Framework apps | Pydantic resolves env vars, produces `RegistryConfig` |
| Config-as-code | Prod deployments | Secrets in vault, injected into Python code at app startup |
| `.env` + Pydantic | Local dev | `.env` file with secrets, loaded by `BaseSettings` |

### 7.2 Non-serializable options (`pkey`, `credential`)

SFTP's `pkey` (a `paramiko.PKey` instance) and Azure's `credential` (e.g.,
`DefaultAzureCredential()`) cannot be represented in TOML, YAML, or JSON.
File-based configs work for all *string-serializable* options; complex
credential objects require code-level construction.

**Acceptable trade-off:** Users with complex credentials use `RegistryConfig()`
directly or use the Pydantic adapter with a custom validator that constructs the
credential object. Document both paths.

### 7.3 Validation and error messages

All three loaders delegate to `from_dict()`, which validates structure. The
Registry constructor calls `validate()`, which checks backend references.
Backend construction catches `TypeError` from invalid options and re-raises
with a clear message including the provided option keys. This validation chain
is sufficient — no need to add format-specific validation.

### 7.4 Where to put the code

| Loader | Location | Rationale |
|--------|----------|-----------|
| `from_toml()` | `_config.py` (classmethod on `RegistryConfig`) | Zero-dep on 3.11+, core workflow |
| `from_yaml()` | `_config.py` (classmethod on `RegistryConfig`) | Parallel to `from_toml()`, import-guarded |
| Pydantic adapter | `ext/pydantic.py` | Optional dependency, adapter pattern |

`from_toml()` and `from_yaml()` belong on `RegistryConfig` because they are
simple format loaders (like `from_dict()`). The Pydantic adapter is more
complex and involves a separate settings model, so it fits the `ext/` pattern.

### 7.5 Optional extras

```toml
[project.optional-dependencies]
# Existing
s3 = [...]
sftp = [...]
azure = [...]
arrow = [...]
otel = [...]

# New
toml = ["tomli>=1.1.0; python_version < '3.11'"]
yaml = ["pyyaml>=5.1"]
pydantic = ["pydantic-settings>=2.0.0"]
```

---

## 8. Priority and Sequencing

### 8.1 Recommended order

| Priority | Item | Rationale |
|----------|------|-----------|
| 1 | **ID-005 `from_toml()`** | Lowest cost, highest value. Zero dep on 3.11+. Natural for Python projects. |
| 2 | **ID-002 `from_yaml()`** | Low cost. Parallel implementation to `from_toml()`. |
| 3 | **ID-003 Pydantic adapter** | Higher cost, narrower audience. Can be done independently. |

ID-005 and ID-002 can ship together in a single release. ID-003 is
independent and can ship later.

### 8.2 Spec requirements

Per project conventions, new features require a spec in `sdd/specs/`. A single
spec covering all three config loaders would be appropriate since they share
the same config model and validation chain. Suggested invariants:

- `CFG-008`: `from_toml(path, table=())` loads config from a TOML file.
- `CFG-009`: `from_yaml(path)` loads config from a YAML file.
- `CFG-010`: Pydantic adapter converts `BaseSettings` to `RegistryConfig`.
- `CFG-011`: All loaders produce identical `RegistryConfig` for equivalent input.
- `CFG-012`: Missing optional dependency raises `ModuleNotFoundError` with
  install instructions.

---

## 9. Open Questions

| # | Question | Candidates | Recommendation |
|---|----------|------------|----------------|
| Q1 | Should `from_toml()` support reading from a `pyproject.toml` `[tool.remote-store]` table? | Yes (via `table` parameter) / No (only standalone files) | **Yes** — TOML's primary Python use is `pyproject.toml`. The `table` kwarg costs nothing and enables this. |
| Q2 | Should we accept both `pyyaml` and `ruamel.yaml`? | Accept both / Only `pyyaml` / Only `ruamel.yaml` | **Accept both** with `pyyaml` as primary and `ruamel.yaml` as fallback. |
| Q3 | Should the Pydantic adapter live in `ext/pydantic.py` or `_pydantic.py`? | `ext/` / top-level private | **`ext/pydantic.py`** — follows extension architecture (ADR-0008). |
| Q4 | Should the Pydantic adapter provide pre-built `S3Options` etc., or just a generic converter? | Pre-built models / Generic converter + docs | **Generic converter + documented patterns.** Pre-built models are opinionated and maintenance-heavy. |
| Q5 | Should `from_toml()` accept `str`, `Path`, or both? | `str` only / `Path` only / Both | **Both** (`str | Path`) — consistent with Python stdlib conventions. |
| Q6 | Should `from_yaml()` accept a `key` parameter (like `table` for TOML)? | Yes / No | **No** — YAML has no equivalent of `pyproject.toml` shared-file convention. If needed later, add it then. |
| Q7 | Should we add `from_json()` while we're at it? | Yes / No | **No** — JSON has no comments, is less readable, and `from_dict(json.load(f))` is a one-liner. Not worth a dedicated method. |

---

## 10. References

- ADR-0002: Configuration Resolution — No Merging
- Spec 002: Registry & Configuration
- PEP 680: `tomllib` — Support for Parsing TOML in the Standard Library
- `pydantic-settings` documentation: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- `tomllib` documentation: https://docs.python.org/3/library/tomllib.html
- PyYAML: https://pyyaml.org/
- `ruamel.yaml`: https://yaml.dev/doc/ruamel.yaml/
