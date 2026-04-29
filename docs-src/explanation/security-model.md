# Security Model

How `remote-store` handles credentials, trust boundaries, and security
policies.

## Credential hygiene

All credentials are wrapped in `Secret` objects at the configuration layer.
The `Secret` class provides:

- **Masked output** — `repr()` and `str()` return `***`, never plain text
- **Explicit reveal** — `secret.reveal()` is the only way to access the
  plain-text value, making credential access auditable
- **Immutability** — `Secret` uses `__slots__` with `__setattr__` and
  `__delattr__` overrides to prevent modification after creation

### Automatic wrapping

`RegistryConfig.from_dict()`, `from_toml()`, and `ext.yaml.from_yaml()`
automatically wrap values for these config keys in `Secret`:

- `key`, `secret`, `password`
- `account_key`, `sas_token`, `connection_string`

You never need to create `Secret` instances manually in configuration code.

### Log redaction

The `SecretRedactionFilter` logging filter replaces `Secret` instances with
`***` in log records. Attach it to your logging handlers to prevent credential
leakage:

```python
import logging
from remote_store import SecretRedactionFilter

handler = logging.StreamHandler()
handler.addFilter(SecretRedactionFilter())
logging.getLogger("remote_store").addHandler(handler)
```

## Trust boundaries

### Backend isolation

- User code interacts with `Store` only — backend instances are internal
- Backend-specific exceptions are mapped to `remote-store` error types and
  **never leak** to user code
- `Store.unwrap()` is the explicit escape hatch for direct backend access;
  using it crosses the trust boundary intentionally

### Path validation

- All paths are validated via `RemotePath` before reaching a backend
- Path traversal (`..`) is rejected at the Store layer
- Each backend applies additional provider-specific validation

### Configuration isolation

- Config-as-code has absolute priority — no environment variable overrides
  unless explicitly opted in
- No config merging prevents accidental credential exposure from layered
  sources

## Vulnerability reporting

Report security issues via
[GitHub Security Advisories](https://github.com/haalfi/remote-store/security/advisories/new),
not public issues.

See [SECURITY.md](https://github.com/haalfi/remote-store/blob/master/SECURITY.md)
for response timelines, scope, and the fix policy.

## See also

- [Architecture Overview](architecture.md) — system design and error model
- [API Reference: Secret](../api/config.md#remote_store.Secret)
- [Spec 020: Credential Hygiene](../design/specs/020-credential-hygiene.md)
