# Extensions

API reference for all extension modules.
Extensions add optional capabilities to Store — install the relevant extra
to enable each one. For usage guides, see [Extensions](../../../guides/extensions.md).

| Module | Description |
|--------|-------------|
| [ext.arrow](arrow.md) | PyArrow `FileSystemHandler` adapter for Store |
| [ext.batch](batch.md) | Batch delete, copy, and exists operations |
| [ext.cache](cache.md) | Store-level caching middleware with TTL |
| [ext.dagster](dagster.md) | Dagster IO manager, config-driven Store resource, and compute log manager |
| [ext.glob](glob.md) | Portable glob pattern matching fallback |
| [ext.integrity](integrity.md) | Checksum computation and verification helpers |
| [ext.observe](observe.md) | Callback hooks for store operations |
| [ext.otel](otel.md) | OpenTelemetry bridge for ext.observe |
| [ext.parquet](parquet.md) | Managed Parquet datasets with manifests and completion markers |
| [ext.partition](partition.md) | Hive-style partition path helpers |
| [ext.pydantic](pydantic.md) | Pydantic model to RegistryConfig adapter |
| [ext.streams](streams.md) | Composable BinaryIO wrappers for progress and checksums |
| [ext.transfer](transfer.md) | Upload, download, and cross-store transfer |
| [ext.write](write.md) | Write helpers with guaranteed client-side content hashing |
| [aio.ext.write](aio-write.md) | Async write helpers with guaranteed client-side content hashing |
| [ext.yaml](yaml.md) | YAML config loader (PyYAML / ruamel.yaml) |

## See also

- [Extensions guide](../../../guides/extensions.md) — overview of all extensions with installation instructions
- [Choosing a Backend](../../../guides/choosing-a-backend.md) — backend selection guide
