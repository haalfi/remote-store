# Configuration

::: remote_store.RegistryConfig

::: remote_store.BackendConfig

!!! note "Backend-conditional field: `options`"
    The `options` mapping contains backend-specific configuration. Keys and
    accepted values depend on the backend being configured.

::: remote_store.RetryPolicy

::: remote_store.StoreProfile

::: remote_store.Secret

::: remote_store.SecretRedactionFilter

::: remote_store.resolve_env

## See also

- [Retry](../../guides/retry.md) — configuring retry policies
- [Security Model](../../explanation/security-model.md) — credential handling and secret redaction
- [Configuration example](../../../examples/configuration/configuration.py) — backend and store configuration
- [Retry Policy example](../../../examples/advanced/retry_policy.py) — retry policy in action
- [Config Loaders example](../../../examples/configuration/config_loaders.py) — TOML, YAML, Pydantic, and env-var interpolation
