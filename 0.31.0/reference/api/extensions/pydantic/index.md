# ext.pydantic

## pydantic

Pydantic adapter — convert any Pydantic model to a RegistryConfig.

Install with `pip install "remote-store[pydantic]"`.

Example

```
from pydantic_settings import BaseSettings, SettingsConfigDict
from remote_store.ext.pydantic import from_pydantic

class MySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RS_", env_nested_delimiter="__")
    backends: dict = {}
    stores: dict = {}

config = from_pydantic(MySettings())
```

### from_pydantic

```
from_pydantic(model: BaseModel) -> RegistryConfig
```

Convert a Pydantic model to a `RegistryConfig`.

Calls `model.model_dump()` to produce a plain dict, then delegates to `RegistryConfig.from_dict()`. Secret wrapping, unknown-key warnings, and validation all happen in `from_dict()`.

Pydantic `SecretStr` fields in backend `options` dicts are automatically unwrapped to plain strings before reaching `from_dict()`, so `from_dict()`'s sensitive-key detection works correctly. Users may use either `str` or `SecretStr` for credential values in their models.

Parameters:

- **`model`** (`BaseModel`) – A Pydantic model whose model_dump() output has backends and stores keys matching the RegistryConfig schema.

Returns:

- `RegistryConfig` – An immutable RegistryConfig.

Raises:

- `TypeError` – If the model dump does not conform to the expected schema.

## See also

- [Extensions](https://docs.remotestore.dev/stable/guides/extensions/index.md) — overview of all extension modules
- [Config Loaders example](https://docs.remotestore.dev/stable/tutorial/examples/config-loaders/index.md) — Pydantic config loader in action
