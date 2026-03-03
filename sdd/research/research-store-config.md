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

**12-Factor framing.** The three proposed loaders map cleanly onto the
file-vs-environment spectrum from [The Twelve-Factor App, Factor III](https://12factor.net/config)
("Store config in the environment"):

| Loader | 12-Factor alignment | Primary audience |
|--------|-------------------|------------------|
| `from_toml()` / `from_yaml()` | Low (file-based) | Libraries, scripts, local dev |
| Pydantic `BaseSettings` adapter | High (env-var native) | Services, containers, 12-factor apps |
| Code-level `RegistryConfig()` | N/A (explicit code) | Complex credentials, tests, notebooks |

This tension between file-based configuration (developer ergonomics, VCS-friendly)
and environment-variable configuration (deploy-time flexibility, secret safety) is
the central design question. ADR-0002 resolves it by keeping all three as
*pre-processing* steps that produce a single, immutable `RegistryConfig` — the
Registry never merges sources at runtime.

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

## 3. External Landscape Survey

Before proposing solutions, we survey how existing Python libraries and
frameworks handle configuration for storage and application settings. This
establishes prior art and justifies where remote-store should align with,
diverge from, or defer to ecosystem conventions.

### 3.1 fsspec — the closest analog

[fsspec](https://filesystem-spec.readthedocs.io/) is the Python ecosystem's
abstract filesystem interface. It is the closest analog to remote-store:
multiple backends, credential management, used by pandas, dask, and xarray.

**fsspec's config approach:**

- **`fsspec.config.conf`** — A global nested dict keyed by protocol (`s3`,
  `gcs`, `abfs`) that supplies default kwargs to any filesystem constructor.
  This is the "config-as-defaults" pattern.
- **`storage_options` pass-through** — Every `fsspec.filesystem("s3", **opts)`
  call accepts kwargs that override global config. This two-tier design
  (global defaults + per-call overrides) was adopted by pandas
  `read_parquet(storage_options=...)`, dask, xarray, and PyArrow.
- **`set_conf_files()` / `set_conf_env()`** — Reads `~/.config/fsspec/conf.json`
  and env vars like `FSSPEC_S3_KEY`.
- **No TOML/YAML loader** — fsspec only supports JSON for config files.

**Key differences from remote-store:**

| Aspect | fsspec | remote-store |
|--------|--------|--------------|
| Config model | Global mutable dict | Immutable frozen dataclasses |
| Layering | Global defaults + per-call overrides | No merging (ADR-0002) |
| Backend identity | Protocol string (`"s3"`) | User-chosen name (`"s3-prod"`) |
| Multiple configs per protocol | Not supported natively | First-class (§4.2) |
| File format | JSON only | TOML, YAML, Pydantic (proposed) |

**Relevance to remote-store:** fsspec's `storage_options` convention is table
stakes for interoperability with the data ecosystem. Even though remote-store
uses a different config model, we should document how users can bridge between
`storage_options` dicts and `BackendConfig.options`. This is a documentation
concern, not a code change — `BackendConfig.options` already *is* a dict of
kwargs, so `storage_options` dicts are often directly usable as `options`.
See §8 (Cross-Cutting Concerns) for the compatibility note.

### 3.2 Competing storage abstraction libraries

| Library | Config approach | Credential handling | File-based config |
|---------|----------------|--------------------|--------------------|
| **Apache libcloud** | Provider-specific drivers with explicit credential passing. Connection objects constructed in code. | Explicit kwargs only | No |
| **cloudpathlib** | `Client` objects wrapping cloud SDK clients. | Delegated entirely to underlying SDK (boto3, google-cloud-storage) | No |
| **smart_open** | `transport_params` dicts (analogous to `storage_options`) | Delegated to underlying SDK | No |

**Pattern across all:** Storage abstraction libraries delegate credential
management to the underlying SDK and focus on clean pass-through configuration.
None provide their own config file format — they all accept dicts/kwargs and
let users construct them however they wish.

**Implication for remote-store:** This validates the "thin translation layer"
design. `from_toml()` and `from_yaml()` are file-to-dict loaders that feed
into `from_dict()` — exactly the pattern the ecosystem expects. We are *not*
building a config management framework; we are providing format-specific
convenience for dict construction.

### 3.3 Hydra / OmegaConf — state-of-the-art config

Meta's [Hydra](https://hydra.cc/) + [OmegaConf](https://omegaconf.readthedocs.io/)
is the most sophisticated config system in the Python ML ecosystem:

- **Config groups** — Organizing configs by concern (db, server, logging) and
  composing via command-line overrides.
- **Variable interpolation** — `${backend.bucket}` references within configs.
- **Structured configs** — Pydantic-like validation via dataclasses.
- **Override grammar** — `+backend=s3` to select, `~backend` to remove.

Hydra's config groups are directly analogous to remote-store's backends/stores
split. However, Hydra targets ML experiment management with complex composition
needs. remote-store's config is structurally simple (two flat dicts of typed
entries) and doesn't need interpolation, overrides, or config groups.

**Why we don't adopt Hydra's approach:** The complexity budget doesn't justify
it. Hydra adds `omegaconf`, `hydra-core`, and a CLI framework. remote-store's
config is a two-level nested dict — TOML/YAML handle this natively. Users who
*do* use Hydra can trivially convert OmegaConf dicts to plain dicts via
`OmegaConf.to_container()` and pass them to `from_dict()`.

### 3.4 dynaconf — Python settings management

[dynaconf](https://www.dynaconf.com/) is a mature library specifically for
settings management:

- **Multiple file formats** — TOML, YAML, JSON, INI, `.env`
- **Layered environments** — `[default]`, `[development]`, `[production]`
- **Env-var overrides** — `DYNACONF_` prefix convention
- **Vault integration** — HashiCorp Vault, Redis
- **Framework extensions** — Django and Flask

dynaconf solves much of what the Pydantic adapter (ID-003) addresses: env-var
binding, multi-format file loading, and secrets integration. The question is
whether remote-store should recommend dynaconf as an integration pattern rather
than building a bespoke Pydantic adapter.

**Assessment:** dynaconf is powerful but opinionated — it manages settings
*globally*, uses its own merge semantics, and has a learning curve. The Pydantic
adapter approach is lighter: users who already use `pydantic-settings` (common
in FastAPI/Django) get integration for free via `model_dump() → from_dict()`.
Users who prefer dynaconf can use it the same way:
`settings.as_dict() → from_dict()`. We should document dynaconf as a supported
integration path in the Pydantic adapter docs, not build a dedicated adapter.

### 3.5 Airflow's env-var override convention

Apache Airflow uses a `.cfg` (INI) file with a widely-copied env-var override
convention:

```
AIRFLOW__CORE__SQL_ALCHEMY_CONN=postgresql://...
AIRFLOW__SMTP__SMTP_HOST=smtp.example.com
```

The double-underscore convention (`SECTION__KEY`) maps directly to the INI
section/key hierarchy. This pattern was adopted by Prefect, Dagster, and dbt.

**Comparison with the Pydantic adapter proposal (§7.4):** The Pydantic adapter
proposes `RS_BACKENDS__S3_PROD__OPTIONS__BUCKET=prod-data` — triple-nested and
verbose. Airflow's convention works because its config is two levels deep
(section + key). remote-store's config is three levels deep
(backends/stores → name → options), making flat env vars inherently unwieldy.

**Implication:** For env-var-heavy deployments, the Pydantic adapter should
document a *flatter* alternative pattern:

```bash
# Instead of deeply nested env vars:
RS_BACKENDS__S3_PROD__OPTIONS__BUCKET=prod-data

# Consider per-backend env prefix pattern:
RS_S3_PROD_BUCKET=prod-data
RS_S3_PROD_REGION=eu-central-1
```

This requires a custom Pydantic model per deployment but is far more ergonomic.
We should document both approaches with trade-offs.

### 3.6 Django and Flask configuration lessons

The two most popular Python web frameworks have decades of configuration
experience worth studying:

**Django:**
- `settings.py`-as-Python-module was deliberate: config IS code.
- The ecosystem split into three camps: `django-environ` (12-factor, env vars),
  `django-configurations` (class-based inheritance), `django-split-settings`
  (modular files).
- Key lesson: the community never converged on one approach. Different deployment
  models need different config patterns.

**Flask:**
- `app.config` offers five explicit loading methods: `from_envvar()`,
  `from_pyfile()`, `from_object()`, `from_file()` (TOML/JSON with loader
  callable), `from_mapping()`.
- Flask 2.0+ added `from_file()` with a `load` parameter — exactly the
  "thin translation layer" pattern this research proposes.
- Key lesson: every successful framework supports multiple config sources but
  does NOT merge automatically. The user explicitly chains load calls.

**Validation for ADR-0002:** Flask's approach — explicit, user-controlled loading
with no automatic merging — is precisely what ADR-0002 mandates and what our
proposed `from_toml()` / `from_yaml()` / Pydantic adapter implements. This is
not a novel design; it is the proven pattern in battle-tested frameworks.

---

## 4. Backend Configuration Landscape

Understanding the full configuration surface per backend is essential for
evaluating how well each format and loader handles real-world configs.

### 4.1 Configuration options by backend

| Backend | Type | Required | Optional | Sensitive |
|---------|------|----------|----------|-----------|
| **Local** | `"local"` | `root` | — | — |
| **Memory** | `"memory"` | — | — | — |
| **S3** | `"s3"` | `bucket` | `key`, `secret`, `region_name`, `endpoint_url`, `client_options` | `key`, `secret` |
| **S3-PyArrow** | `"s3-pyarrow"` | `bucket` | `key`, `secret`, `region_name`, `endpoint_url`, `client_options` | `key`, `secret` |
| **SFTP** | `"sftp"` | `host` | `port`, `username`, `password`, `pkey`, `base_path`, `host_key_policy`, `known_host_keys`, `host_keys_path`, `config`, `timeout`, `connect_kwargs` | `password`, `pkey` |
| **Azure** | `"azure"` | `container` + one of (`account_name`, `account_url`, `connection_string`) | `account_key`, `sas_token`, `credential`, `client_options` | `account_key`, `sas_token`, `connection_string`, `credential` |

### 4.2 Multiple configs per backend technology

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

### 4.3 Credential chain patterns in cloud SDKs

All three major cloud SDKs implement a credential resolution chain with
well-defined priority ordering. This is the most important configuration
pattern in production cloud systems and directly affects how remote-store
users will manage credentials.

**AWS (boto3/botocore) credential chain:**

1. Explicit kwargs (`aws_access_key_id`, `aws_secret_access_key`)
2. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
3. Shared credential file (`~/.aws/credentials`)
4. AWS config file (`~/.aws/config`)
5. Assume role provider
6. Boto2 config file (`/etc/boto.cfg`, `~/.boto`)
7. Instance metadata service (IMDS) on EC2
8. Container credential provider (ECS)

**Azure `DefaultAzureCredential` chain:**

1. `EnvironmentCredential`
2. `WorkloadIdentityCredential`
3. `ManagedIdentityCredential`
4. `AzureCliCredential`
5. `AzurePowerShellCredential`
6. `AzureDeveloperCliCredential`

**GCP Application Default Credentials:**

1. `GOOGLE_APPLICATION_CREDENTIALS` env var (service account JSON path)
2. User credentials via `gcloud auth application-default login`
3. Attached service account (GCE, GKE, Cloud Run)

**Implications for remote-store:**

The credential chain pattern means that in many production deployments,
*no credentials appear in config at all*. The backend's underlying SDK
resolves credentials automatically via IAM roles, managed identity, or
workload identity. This is the ideal state.

remote-store already supports this: if `key`/`secret` are omitted from S3
options, the underlying credential chain resolves automatically (`S3Backend`
uses `s3fs`, which uses `aiobotocore`, which delegates to `botocore`'s
credential provider chain — not `boto3` directly, though the chain behavior
is identical). If `credential` is omitted
from Azure options, `DefaultAzureCredential()` is used. The config loaders
should *not* attempt to replicate or interfere with these chains.

**Recommendation:** Document the credential chain pattern explicitly in the
config loader guide. Show that a minimal TOML config with no secrets is the
recommended production pattern:

```toml
# Production config — credentials resolved by cloud SDK chain
[backends.s3-prod]
type = "s3"
options.bucket = "prod-data"
options.region_name = "eu-central-1"
# No key/secret — IAM role resolves automatically
```

Users who *must* put credentials in config (dev, CI, on-prem) should use the
Pydantic adapter with env-var binding or the TOML/YAML + env-var injection
pattern documented in §8.1.

### 4.4 Sensitive values and the secrets problem

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

Additionally, `host_key_policy` (`HostKeyPolicy` Enum with values `"strict"`,
`"tofu"`, `"auto"`) is *string-representable* but requires coercion: TOML/YAML
will produce a raw string like `"strict"`, but `SFTPBackend.__init__` expects
a `HostKeyPolicy` instance. Without coercion, `factory(**cfg.options)` passes
the raw string through, and comparisons in `_create_ssh_client()` silently fail
(`"strict" != HostKeyPolicy.STRICT` — Python Enum equality is identity-based).
The implementation should add string→Enum coercion in `SFTPBackend.__init__`:

```python
if isinstance(host_key_policy, str):
    host_key_policy = HostKeyPolicy(host_key_policy)
```

This is a pre-existing gap in `SFTPBackend`, not specific to config loaders,
but config loaders make it a practical problem. Tracked as part of ID-039
(credential hygiene), item 4.

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

## 5. ID-005: `from_toml()` — TOML Config Loader

### 5.1 Why TOML

- **stdlib on 3.11+:** `tomllib` is built-in since Python 3.11 (PEP 680).
  `tomli` is the compatible backport for 3.10.
- **Python ecosystem alignment:** `pyproject.toml` is the standard for project
  config. Tools like `pytest`, `mypy`, `ruff`, `black` all use TOML.
- **Strict typing:** TOML distinguishes strings, integers, booleans, arrays,
  and tables — unlike YAML, there are no ambiguous value types.
- **Read-only is fine:** `tomllib` is read-only by design. We only need to
  *read* config.

### 5.2 Dependency strategy

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

### 5.3 TOML schema

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

### 5.4 Proposed API

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

### 5.5 Implementation sketch

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

### 5.6 Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Implementation effort | Very low | ~15 lines wrapping `from_dict()` |
| Dependency cost | Zero on 3.11+; `tomli` on 3.10 | Aligns with zero-dep philosophy |
| User demand | High | TOML is the standard Python config format |
| Risk | Very low | Pure translation layer, no new semantics |
| Multi-backend support | Natural | TOML tables map cleanly to nested dicts |

---

## 6. ID-002: `from_yaml()` — YAML Config Loader

### 6.1 Why YAML

- **Familiar:** Widely used for application config (Kubernetes, Ansible,
  Docker Compose, etc.).
- **Readable:** More compact than TOML for deeply nested structures.
- **Comments:** YAML supports inline comments (like TOML, unlike JSON).

### 6.2 Library comparison

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

### 6.3 YAML schema

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

### 6.4 Proposed API

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

### 6.5 Implementation sketch

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

### 6.6 YAML pitfalls for config files

| Pitfall | Impact on remote-store | Mitigation |
|---------|----------------------|------------|
| `yes`/`no`/`on`/`off` parsed as booleans (YAML 1.1) | Port numbers like `port: 22` are fine; string values that happen to match YAML boolean literals would be silently coerced | Document: always quote string values that could be ambiguous |
| Enum values loaded as raw strings | `host_key_policy: "strict"` loads as a Python `str`, but `SFTPBackend` expects a `HostKeyPolicy` Enum. The `from_dict()` → `factory(**options)` pipeline passes strings through without coercion, causing silent failures (see §4.4). | Implement string→Enum coercion in `SFTPBackend.__init__` |
| **The Norway problem** — bare `NO` is parsed as `false` in YAML 1.1 | Country codes, region names, or any short string matching YAML 1.1 boolean literals (`NO`, `YES`, `ON`, `OFF`) silently become booleans. This caused real bugs in npm package country-code lists and GitHub Actions workflows. | Always quote string values. This is a concrete argument for TOML's stricter typing — TOML has no implicit boolean coercion, making it the safer default for config files. |
| Indentation errors silently change structure | Could produce malformed config | `from_dict()` validation catches invalid structures |
| No native type distinction (everything is a string without explicit tags) | Numbers and booleans auto-convert, which is actually desirable for our schema | Non-issue |
| `yaml.load()` is unsafe | Remote code execution if using untrusted input | Always use `safe_load()` — enforced in our implementation |

### 6.7 Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Implementation effort | Very low | ~20 lines wrapping `from_dict()` |
| Dependency cost | Optional `pyyaml` | Ubiquitous, likely already installed |
| User demand | Medium | YAML is common but less so in Python-native tooling |
| Risk | Low | `safe_load()` mitigates security; `from_dict()` validates |
| Multi-backend support | Natural | YAML mappings are dicts |

---

## 7. ID-003: Pydantic `BaseSettings` Integration

### 7.1 Why Pydantic

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

### 7.2 Design challenge: ADR-0002 tension

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

### 7.3 Proposed design: adapter, not replacement

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

**SecretStr for credential awareness.** Documented Pydantic example models
should use `pydantic.SecretStr` for sensitive fields (`key`, `secret`,
`password`, `account_key`, `sas_token`, `connection_string`). `SecretStr`
provides no real security boundary — the plain value is accessible via
`.get_secret_value()` — but it prevents accidental exposure in logs, `repr()`,
and serialization output. More importantly, it signals to users that these
fields contain secrets and should be treated with care. The
`to_registry_config()` method would call `.get_secret_value()` when building
the options dict.

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

### 7.4 Multi-backend configs with Pydantic

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

### 7.5 Pydantic's built-in file sources

As of `pydantic-settings` 2.13+, users can combine env vars with TOML, YAML,
and JSON files in a single `BaseSettings` class. This means the Pydantic
adapter partially subsumes ID-002 and ID-005 for users who adopt it — but only
for those users. The standalone `from_toml()` and `from_yaml()` remain
valuable for users who don't want Pydantic.

### 7.6 Assessment

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Implementation effort | Medium | Adapter + documentation + examples |
| Dependency cost | Optional `pydantic-settings` (+ `pydantic`) | Heavy; ~5 MB |
| User demand | Medium-high | Strong in FastAPI/Django ecosystem |
| Risk | Medium | Must not violate ADR-0002 semantics |
| Multi-backend support | Works but verbose | `env_nested_delimiter` handles it |
| ADR-0002 compatibility | Compatible | Pydantic merges *then* produces RegistryConfig |

---

## 8. Cross-Cutting Concerns

### 8.1 Secrets in config files

None of the three loaders should resolve secrets from env vars or vaults.
This is the user's responsibility (per ADR-0002). However, we should document
the common patterns with concrete examples:

| Pattern | When to use | How |
|---------|-------------|-----|
| Inject before `from_dict()` | Simple scripts | Load TOML/YAML, replace secrets from `os.environ`, call `from_dict()` |
| Pydantic env-var binding | Framework apps | Pydantic resolves env vars, produces `RegistryConfig` |
| Config-as-code | Prod deployments | Secrets in vault, injected into Python code at app startup |
| `.env` + Pydantic | Local dev | `.env` file with secrets, loaded by `BaseSettings` |
| SOPS / sealed secrets | GitOps workflows | Encrypted config files committed to VCS, decrypted at deploy |
| Kubernetes Secrets | Container orchestration | Mounted as files or env vars in pods |

#### Concrete example 1: TOML + env-var injection

```python
import os
import tomllib
from remote_store import RegistryConfig

# Load structure from TOML
with open("remote-store.toml", "rb") as f:
    data = tomllib.load(f)

# Inject secrets from environment
s3_opts = data["backends"]["s3-prod"]["options"]
s3_opts["key"] = os.environ["AWS_ACCESS_KEY_ID"]
s3_opts["secret"] = os.environ["AWS_SECRET_ACCESS_KEY"]

config = RegistryConfig.from_dict(data)
```

#### Concrete example 2: HashiCorp Vault integration

```python
import hvac
import tomllib
from remote_store import RegistryConfig

# Load structure from TOML
with open("remote-store.toml", "rb") as f:
    data = tomllib.load(f)

# Fetch secrets from Vault
client = hvac.Client(url="https://vault.example.com")
secret = client.secrets.kv.v2.read_secret_version(path="remote-store/s3-prod")
s3_creds = secret["data"]["data"]

data["backends"]["s3-prod"]["options"]["key"] = s3_creds["access_key"]
data["backends"]["s3-prod"]["options"]["secret"] = s3_creds["secret_key"]

config = RegistryConfig.from_dict(data)
```

#### Concrete example 3: SOPS-encrypted config

[SOPS](https://github.com/getsops/sops) (Secrets OPerationS) by Mozilla
encrypts config files so they can be committed to VCS. At deploy time, the
file is decrypted and loaded:

```bash
# Encrypt a config file (one-time)
sops --encrypt remote-store.toml > remote-store.enc.toml

# At deploy time, decrypt and load
sops --decrypt remote-store.enc.toml > /tmp/remote-store.toml
```

```python
# In application code — identical to normal TOML loading
config = RegistryConfig.from_toml("/tmp/remote-store.toml")
```

#### Real-world secrets infrastructure

| Tool | How it works | Integration with remote-store |
|------|-------------|-------------------------------|
| **HashiCorp Vault** | API-based secret storage. `hvac` Python client. Vault Agent sidecar for automatic injection. | Fetch secrets via `hvac`, inject into dict, call `from_dict()` |
| **SOPS (Mozilla)** | Encrypts YAML/JSON/TOML files in-place. Committed to VCS encrypted. | Decrypt at deploy time, load normally via `from_toml()` / `from_yaml()` |
| **AWS Secrets Manager / SSM** | `boto3` calls at startup. Often used with IAM role authentication. | Fetch via `boto3`, inject into config dict |
| **Kubernetes Secrets** | Mounted as files (`/run/secrets/`) or env vars in pods. | Use mounted file paths in config, or env vars via Pydantic adapter |
| **Docker Secrets** | Mounted at `/run/secrets/<name>`. Available in Swarm mode. | Pydantic adapter: `secrets_dir='/run/secrets'` |

### 8.2 Non-serializable options (`pkey`, `credential`)

SFTP's `pkey` (a `paramiko.PKey` instance) and Azure's `credential` (e.g.,
`DefaultAzureCredential()`) cannot be represented in TOML, YAML, or JSON.
File-based configs work for all *string-serializable* options; complex
credential objects require code-level construction.

**Acceptable trade-off:** Users with complex credentials use `RegistryConfig()`
directly or use the Pydantic adapter with a custom validator that constructs the
credential object. Document both paths.

### 8.3 Validation and error messages

All three loaders delegate to `from_dict()`, which validates structure. The
Registry constructor calls `validate()`, which checks backend references.
Backend construction catches `TypeError` from invalid options and re-raises
with a clear message including the provided option keys. This validation chain
is sufficient — no need to add format-specific validation.

### 8.4 Where to put the code

| Loader | Location | Rationale |
|--------|----------|-----------|
| `from_toml()` | `_config.py` (classmethod on `RegistryConfig`) | Zero-dep on 3.11+, core workflow |
| `from_yaml()` | `_config.py` (classmethod on `RegistryConfig`) | Parallel to `from_toml()`, import-guarded |
| Pydantic adapter | `ext/pydantic.py` | Optional dependency, adapter pattern |

`from_toml()` and `from_yaml()` belong on `RegistryConfig` because they are
simple format loaders (like `from_dict()`). The Pydantic adapter is more
complex and involves a separate settings model, so it fits the `ext/` pattern.

### 8.5 fsspec `storage_options` compatibility

fsspec's `storage_options` convention is the de facto standard for passing
backend configuration in the data ecosystem (pandas, dask, xarray, PyArrow).
A `storage_options` dict for S3 looks like:

```python
storage_options = {
    "key": "AKIA...",
    "secret": "...",
    "client_kwargs": {"endpoint_url": "http://localhost:9000"},
}
```

remote-store's `BackendConfig.options` is already a dict of kwargs splatted
into the backend constructor. For S3, the constructor accepts `key`, `secret`,
`region_name`, `endpoint_url`, and `client_options` — which overlap
significantly with fsspec's `storage_options` but the mapping is hierarchical,
not a simple rename. `S3Backend`'s `client_options` is a pass-through dict for
*all* `s3fs.S3FileSystem` kwargs, while fsspec's `client_kwargs` is a *nested
key within* that dict. In `_s3.py`, `region_name` is placed into
`opts.setdefault("client_kwargs", {})`, so
`client_options={"client_kwargs": {"region_name": "us-east-1"}}` is valid.
Similarly, fsspec puts `endpoint_url` inside `client_kwargs`, while
remote-store accepts it as a top-level constructor option (which then gets
placed into `client_kwargs` internally).

**Recommendation:** Do not attempt to auto-translate `storage_options` dicts.
Instead, document the mapping between fsspec's `storage_options` keys and
remote-store's `BackendConfig.options` keys for each backend. Users who work
with both ecosystems (e.g., using remote-store for writes and PyArrow datasets
for reads) can maintain a shared config and translate as needed.

This is a documentation concern for the config loader guide, not a code change.
If demand emerges for a `from_storage_options()` helper, it can be added later
as a thin key-mapping utility.

### 8.6 Optional extras

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

## 9. Priority and Sequencing

### 9.1 Recommended order

| Priority | Item | Rationale |
|----------|------|-----------|
| 1 | **ID-005 `from_toml()`** | Lowest cost, highest value. Zero dep on 3.11+. Natural for Python projects. |
| 2 | **ID-002 `from_yaml()`** | Low cost. Parallel implementation to `from_toml()`. |
| 3 | **ID-003 Pydantic adapter** | Higher cost, narrower audience. Can be done independently. |

ID-005 and ID-002 can ship together in a single release. ID-003 is
independent and can ship later.

### 9.2 Spec requirements

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

## 10. Open Questions

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

## 11. References

- ADR-0002: Configuration Resolution — No Merging
- Spec 002: Registry & Configuration
- PEP 680: `tomllib` — Support for Parsing TOML in the Standard Library
- `pydantic-settings` documentation: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- `tomllib` documentation: https://docs.python.org/3/library/tomllib.html
- PyYAML: https://pyyaml.org/
- `ruamel.yaml`: https://yaml.dev/doc/ruamel.yaml/
- The Twelve-Factor App, Factor III (Config): https://12factor.net/config
- fsspec documentation: https://filesystem-spec.readthedocs.io/
- Hydra documentation: https://hydra.cc/
- OmegaConf documentation: https://omegaconf.readthedocs.io/
- dynaconf documentation: https://www.dynaconf.com/
- Apache libcloud: https://libcloud.apache.org/
- cloudpathlib: https://cloudpathlib.drivendata.org/
- smart_open: https://github.com/piskvorky/smart_open
- SOPS (Secrets OPerationS): https://github.com/getsops/sops
- HashiCorp Vault hvac client: https://hvac.readthedocs.io/
- boto3 credential configuration: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
- Azure Identity DefaultAzureCredential: https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential
- GCP Application Default Credentials: https://cloud.google.com/docs/authentication/application-default-credentials
- Flask configuration handling: https://flask.palletsprojects.com/en/stable/config/
- The YAML Norway problem: https://hitchdev.com/strictyaml/why/implicit-typing-removed/
