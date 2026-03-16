# Extensions

API reference for all extension modules.
Extensions add optional capabilities to Store — install the relevant extra
to enable each one. For usage guides, see [Extensions](../../extensions.md).

| Module | Description |
|--------|-------------|
| [ext.arrow](arrow.md) | PyArrow `FileSystemHandler` adapter for Store |
| [ext.batch](batch.md) | Batch delete, copy, and exists operations |
| [ext.cache](cache.md) | Store-level caching middleware with TTL |
| [ext.dagster](dagster.md) | Dagster IO Manager adapter for Store |
| [ext.glob](glob.md) | Portable glob pattern matching fallback |
| [ext.observe](observe.md) | Callback hooks for store operations |
| [ext.otel](otel.md) | OpenTelemetry bridge for ext.observe |
| [ext.partition](partition.md) | Hive-style partition path helpers |
| [ext.pydantic](pydantic.md) | Pydantic model to RegistryConfig adapter |
| [ext.transfer](transfer.md) | Upload, download, and cross-store transfer |
| [ext.yaml](yaml.md) | YAML config loader (PyYAML / ruamel.yaml) |
