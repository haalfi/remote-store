# Registry

## Registry

```
Registry(config: RegistryConfig | None = None)
```

Manages backend lifecycle and provides access to named stores.

Parameters:

- **`config`** (`RegistryConfig | None`, default: `None` ) – Optional configuration. Validates immediately.

Raises:

- `ValueError` – If config is invalid.

### get_store

```
get_store(name: str) -> Store
```

Get a store by its profile name.

Parameters:

- **`name`** (`str`) – The store profile name.

Raises:

- `KeyError` – If no store profile with this name exists.

### close

```
close() -> None
```

Close all instantiated backends.

If any backend raises during `close()`, the remaining backends are still closed. The first exception encountered is re-raised after all backends have been processed.

## register_backend

```
register_backend(
    type_name: str, cls: type[Backend]
) -> None
```

Register a backend class for a given type string.

Parameters:

- **`type_name`** (`str`) – The type identifier (e.g. "local").
- **`cls`** (`type[Backend]`) – The backend class to instantiate.

## See also

- [Choosing a Backend](https://docs.remotestore.dev/stable/guides/choosing-a-backend/index.md) — backend selection and registry usage
- [Configuration example](https://docs.remotestore.dev/stable/tutorial/examples/configuration/index.md) — registry-based store creation
