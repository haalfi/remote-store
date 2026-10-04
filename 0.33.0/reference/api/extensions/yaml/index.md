# ext.yaml

## yaml

YAML config loader — load RegistryConfig from a YAML file.

Install with `pip install "remote-store[yaml]"`.

Example

```
from remote_store.ext.yaml import from_yaml

config = from_yaml("remote-store.yaml")
```

Accepts either [pyyaml](https://pyyaml.org/) or [ruamel.yaml](https://yaml.readthedocs.io/) as the parser.

### from_yaml

```
from_yaml(
    path: str | Path, *, resolve_env_vars: bool = False
) -> RegistryConfig
```

Load config from a YAML file.

Accepts either `pyyaml` or `ruamel.yaml` as the parser.

Parameters:

- **`path`** (`str | Path`) – Path to the YAML file.
- **`resolve_env_vars`** (`bool`, default: `False` ) – When True, resolve ${VAR} placeholders via resolve_env before constructing the config.

Returns:

- `RegistryConfig` – An immutable RegistryConfig.

Raises:

- `ModuleNotFoundError` – If neither pyyaml nor ruamel.yaml is installed.
- `FileNotFoundError` – If path does not exist.
- `TypeError` – If the top-level YAML value is not a mapping.
- `KeyError` – If resolve_env_vars is True and a placeholder references an unset variable with no default.

## See also

- [Extensions](https://docs.remotestore.dev/stable/guides/extensions/index.md) — overview of all extension modules
- [Config Loaders example](https://docs.remotestore.dev/stable/tutorial/examples/config-loaders/index.md) — YAML config loader in action
