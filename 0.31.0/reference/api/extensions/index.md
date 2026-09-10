# Extensions

API reference for all extension modules. Extensions add optional capabilities to Store — install the relevant extra to enable each one. For usage guides, see [Extensions](https://docs.remotestore.dev/stable/guides/extensions/index.md).

| Module                                                                                           | Description                                                               |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| [ext.arrow](https://docs.remotestore.dev/stable/reference/api/extensions/arrow/index.md)         | PyArrow `FileSystemHandler` adapter for Store                             |
| [ext.batch](https://docs.remotestore.dev/stable/reference/api/extensions/batch/index.md)         | Batch delete, copy, and exists operations                                 |
| [ext.cache](https://docs.remotestore.dev/stable/reference/api/extensions/cache/index.md)         | Store-level caching middleware with TTL                                   |
| [ext.dagster](https://docs.remotestore.dev/stable/reference/api/extensions/dagster/index.md)     | Dagster IO manager, config-driven Store resource, and compute log manager |
| [ext.glob](https://docs.remotestore.dev/stable/reference/api/extensions/glob/index.md)           | Portable glob pattern matching fallback                                   |
| [ext.integrity](https://docs.remotestore.dev/stable/reference/api/extensions/integrity/index.md) | Checksum computation and verification helpers                             |
| [ext.observe](https://docs.remotestore.dev/stable/reference/api/extensions/observe/index.md)     | Callback hooks for store operations                                       |
| [ext.otel](https://docs.remotestore.dev/stable/reference/api/extensions/otel/index.md)           | OpenTelemetry bridge for ext.observe                                      |
| [ext.parquet](https://docs.remotestore.dev/stable/reference/api/extensions/parquet/index.md)     | Managed Parquet datasets with manifests and completion markers            |
| [ext.partition](https://docs.remotestore.dev/stable/reference/api/extensions/partition/index.md) | Hive-style partition path helpers                                         |
| [ext.pydantic](https://docs.remotestore.dev/stable/reference/api/extensions/pydantic/index.md)   | Pydantic model to RegistryConfig adapter                                  |
| [ext.streams](https://docs.remotestore.dev/stable/reference/api/extensions/streams/index.md)     | Composable BinaryIO wrappers for progress and checksums                   |
| [ext.transfer](https://docs.remotestore.dev/stable/reference/api/extensions/transfer/index.md)   | Upload, download, and cross-store transfer                                |
| [ext.write](https://docs.remotestore.dev/stable/reference/api/extensions/write/index.md)         | Write helpers with guaranteed client-side content hashing                 |
| [ext.yaml](https://docs.remotestore.dev/stable/reference/api/extensions/yaml/index.md)           | YAML config loader (PyYAML / ruamel.yaml)                                 |

The async-native extensions live under [Async › Extensions](https://docs.remotestore.dev/stable/reference/api/aio/extensions/index.md):

| Module                                                                                           | Description                                                     |
| ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| [aio.ext.write](https://docs.remotestore.dev/stable/reference/api/aio/extensions/write/index.md) | Async write helpers with guaranteed client-side content hashing |

## See also

- [Extensions guide](https://docs.remotestore.dev/stable/guides/extensions/index.md) — overview of all extensions with installation instructions
- [Async extensions](https://docs.remotestore.dev/stable/reference/api/aio/extensions/index.md) — native async extension surface
- [Choosing a Backend](https://docs.remotestore.dev/stable/guides/choosing-a-backend/index.md) — backend selection guide
