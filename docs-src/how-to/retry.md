# Retry Policy

`RetryPolicy` provides unified retry configuration across backends.
Each backend maps the policy to its native retry mechanism, avoiding
retry multiplication.

## Quick Start

```python
from remote_store import RetryPolicy, Store
from remote_store.backends import SFTPBackend

# Custom retry: 5 attempts, 2s base backoff, 30s max, 0.5s jitter
policy = RetryPolicy(
    max_attempts=5,
    backoff_base=2.0,
    backoff_max=30.0,
    jitter=0.5,
)

backend = SFTPBackend(host="sftp.example.com", retry=policy)
store = Store(backend)
```

## RetryPolicy Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_attempts` | `int` | `3` | Total attempts (including the initial one). Must be >= 1. |
| `backoff_base` | `float` | `1.0` | Minimum delay in seconds between retries. |
| `backoff_max` | `float` | `60.0` | Maximum delay in seconds between retries. |
| `jitter` | `float` | `1.0` | Random jitter added to each delay (0 to `jitter` seconds). |
| `timeout` | `float \| None` | `None` | Overall timeout in seconds. `None` means no timeout. |

All fields are validated at construction time:

- `max_attempts >= 1`
- `backoff_base >= 0`
- `backoff_max >= 0`
- `jitter >= 0`
- `timeout > 0` or `None`

## Disabling Retries

Use the `disabled()` factory to create a single-attempt (no retry) policy:

```python
from remote_store import RetryPolicy

no_retry = RetryPolicy.disabled()
# Equivalent to: RetryPolicy(max_attempts=1)
```

## TOML / YAML Configuration

Retry can be configured per-backend in config files:

```toml
[backends.production]
type = "sftp"

[backends.production.options]
host = "sftp.example.com"

[backends.production.retry]
max_attempts = 5
backoff_base = 2.0
backoff_max = 30.0
jitter = 0.5
```

```yaml
backends:
  production:
    type: sftp
    options:
      host: sftp.example.com
    retry:
      max_attempts: 5
      backoff_base: 2.0
      backoff_max: 30.0
      jitter: 0.5
```

Load with the standard config loaders:

```python
from remote_store import RegistryConfig, Registry

config = RegistryConfig.from_toml("config.toml")
registry = Registry(config)
store = registry.get_store("my-store")
```

## Per-Backend Mapping

Each backend translates `RetryPolicy` to its native retry mechanism.
Not all fields are mappable to every backend — unmappable fields are
logged at debug level.

### SFTP

Full mapping via tenacity:

| RetryPolicy field | Tenacity equivalent |
|-------------------|---------------------|
| `max_attempts` | `stop_after_attempt(N)` |
| `backoff_base` | `wait_exponential(min=N)` |
| `backoff_max` | `wait_exponential(max=N)` |
| `jitter` | `+ wait_random(0, N)` |
| `timeout` | `\| stop_after_delay(N)` |

Retry scope: **connection only** (not per-operation).

### S3

Only `max_attempts` is mappable to botocore:

```
botocore.config.Config(retries={"max_attempts": N, "mode": "standard"})
```

`backoff_base`, `backoff_max`, `jitter`, and `timeout` are managed by
botocore internally and cannot be overridden.

### S3-PyArrow

Dual mapping:

- **PyArrow C++ side:** `AwsStandardS3RetryStrategy(max_attempts=N)`
- **s3fs side:** Same botocore config as S3.

Only `max_attempts` is mappable on both sides.

### Azure

Three fields are mappable to `ExponentialRetry`:

| RetryPolicy field | Azure equivalent |
|-------------------|------------------|
| `max_attempts` | `retry_total = max_attempts - 1` |
| `backoff_base` | `initial_backoff = max(1, round(backoff_base))` |
| `jitter` | `random_jitter_range = round(jitter)` |

Azure expects integer seconds, so fractional values are rounded (with
a minimum of 1 for `initial_backoff`).

`backoff_max` and `timeout` are not mappable.

### Local and Memory

These backends do not accept a `retry` parameter — passing one raises
`TypeError`. Local filesystem and in-memory operations do not have
transient failures that benefit from retry.

## See also

- [Retry policy example](../examples/retry-policy.md) — runnable script
- [Backend guides](backends/index.md) — per-backend configuration details
