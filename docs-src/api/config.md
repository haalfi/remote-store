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

- [Retry](../how-to/retry.md) — configuring retry policies
- [Security Model](../explanation/security-model.md) — credential handling and secret redaction
- [Configuration example](../examples/configuration.md) — backend and store configuration
- [Retry Policy example](../examples/retry-policy.md) — retry policy in action
- [Config Loaders example](../examples/config-loaders.md) — TOML, YAML, Pydantic, and env-var interpolation
