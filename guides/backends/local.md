# Local Backend

The local backend stores files on the local filesystem. It is built-in and requires no extra dependencies.

## Usage

```python
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={"local": BackendConfig(type="local", options={"root": "/data"})},
    stores={"files": StoreProfile(backend="local", root_path="files")},
)

with Registry(config) as registry:
    store = registry.get_store("files")
    store.write("readme.txt", b"Hello!")
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `root` | `str` | Root directory for file storage (required) |
