# Configuration

## RegistryConfig

```
RegistryConfig(
    backends: dict[str, BackendConfig] = dict(),
    stores: dict[str, StoreProfile] = dict(),
)
```

Top-level configuration container.

Parameters:

- **`backends`** (`dict[str, BackendConfig]`, default: `dict()` ) – Mapping of backend names to their configs.
- **`stores`** (`dict[str, StoreProfile]`, default: `dict()` ) – Mapping of store names to their profiles.

### validate

```
validate() -> None
```

Validate that all store profiles reference existing backends.

Raises:

- `ValueError` – If a store references a non-existent backend.

### from_dict

```
from_dict(data: dict[str, object]) -> RegistryConfig
```

Construct from a plain dict (e.g. parsed TOML/JSON).

Parameters:

- **`data`** (`dict[str, object]`) – Dict with backends and stores keys.

### from_toml

```
from_toml(
    path: str | Path,
    *,
    table: tuple[str, ...] = (),
    resolve_env_vars: bool = False,
) -> RegistryConfig
```

Load config from a TOML file.

Parameters:

- **`path`** (`str | Path`) – Path to the TOML file.
- **`table`** (`tuple[str, ...]`, default: `()` ) – Dotted table path to extract config from. For pyproject.toml use table=("tool", "remote-store").
- **`resolve_env_vars`** (`bool`, default: `False` ) – When True, resolve ${VAR} placeholders via resolve_env before constructing the config.

Raises:

- `ModuleNotFoundError` – If tomllib is unavailable and tomli is not installed.
- `KeyError` – If a table key is not found, or if resolve_env_vars is True and a placeholder references an unset variable with no default.

## BackendConfig

```
BackendConfig(
    type: str,
    options: dict[str, object] = dict(),
    retry: RetryPolicy | None = None,
)
```

Describes a backend instance.

Parameters:

- **`type`** (`str`) – Backend type identifier (e.g. "local", "s3").
- **`options`** (`dict[str, object]`, default: `dict()` ) – Backend-specific configuration options.
- **`retry`** (`RetryPolicy | None`, default: `None` ) – Optional retry policy for transient errors.

Backend-conditional field: `options`

The `options` mapping contains backend-specific configuration. Keys and accepted values depend on the backend being configured.

## RetryPolicy

```
RetryPolicy(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 60.0,
    jitter: float = 1.0,
    timeout: float | None = None,
)
```

Retry configuration for transient backend errors.

Backends map these parameters to their native retry mechanisms. Backends that don't support a parameter silently ignore it.

Parameters:

- **`max_attempts`** (`int`, default: `3` ) – Maximum number of attempts (including the initial). Set to 1 to disable retry.
- **`backoff_base`** (`float`, default: `1.0` ) – Base delay in seconds for exponential backoff.
- **`backoff_max`** (`float`, default: `60.0` ) – Maximum delay between retries in seconds.
- **`jitter`** (`float`, default: `1.0` ) – Maximum random jitter added to each delay in seconds. Set to 0.0 to disable jitter.
- **`timeout`** (`float | None`, default: `None` ) – Total wall-clock timeout in seconds for all attempts combined. None means no total timeout.

### disabled

```
disabled() -> RetryPolicy
```

Return a policy that disables retry (single attempt, no backoff).

## StoreProfile

```
StoreProfile(
    backend: str,
    root_path: str = "",
    options: dict[str, object] = dict(),
)
```

Describes a named store.

Parameters:

- **`backend`** (`str`) – Name of the backend config to use.
- **`root_path`** (`str`, default: `''` ) – Path prefix for all operations.
- **`options`** (`dict[str, object]`, default: `dict()` ) – Store-specific options.

## Secret

```
Secret(value: str)
```

Immutable wrapper that prevents accidental exposure of credential strings.

`__repr__` and `__str__` always return a masked value. Call `.reveal()` to obtain the plain-text credential.

Parameters:

- **`value`** (`str`) – The secret string to protect.

Raises:

- `TypeError` – If value is not a str.

### reveal

```
reveal() -> str
```

Return the plain-text secret.

## SecretRedactionFilter

Bases: `Filter`

Logging filter that replaces `Secret` instances in log record args with `'***'`.

Attach to any handler or logger to prevent credential leakage through %-style formatting:

```
handler.addFilter(SecretRedactionFilter())
```

## resolve_env

```
resolve_env(
    data: dict[str, object],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]
```

Resolve `${VAR}` placeholders in a config dict.

Recursively walks *data* and replaces `${VAR}` with the value of the environment variable *VAR*. Use `${VAR:-default}` to provide a fallback when *VAR* is not set. Escape with `$${` to produce a literal `${`.

The original dict is never mutated; a deep copy with resolved values is returned.

Parameters:

- **`data`** (`dict[str, object]`) – Config dict (typically parsed from YAML/TOML).
- **`environ`** (`Mapping[str, str] | None`, default: `None` ) – Variable source. Defaults to os.environ.

Returns:

- `dict[str, object]` – A new dict with all placeholder strings resolved.

Raises:

- `KeyError` – If a placeholder references a variable that is not set and has no default. The message includes the variable name and the config key path where it was found.

## See also

- [Retry](https://docs.remotestore.dev/stable/guides/retry/index.md) — configuring retry policies
- [Security Model](https://docs.remotestore.dev/stable/explanation/security-model/index.md) — credential handling and secret redaction
- [Configuration example](https://docs.remotestore.dev/stable/tutorial/examples/configuration/index.md) — backend and store configuration
- [Retry Policy example](https://docs.remotestore.dev/stable/tutorial/examples/retry-policy/index.md) — retry policy in action
- [Config Loaders example](https://docs.remotestore.dev/stable/tutorial/examples/config-loaders/index.md) — TOML, YAML, Pydantic, and env-var interpolation
