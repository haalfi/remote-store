# ReadOnlyHttpBackend

API reference for `ReadOnlyHttpBackend` — read-only access to files over
HTTP/HTTPS. Supports `READ` and `METADATA` capabilities only.

::: remote_store.backends.ReadOnlyHttpBackend
    options:
      show_bases: false

## Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    `unwrap`, `native_path`, and `to_key` expose backend internals. Using
    them ties your code to `ReadOnlyHttpBackend`. For portable alternatives,
    use the methods from [Store](../store.md).

## See also

- [HTTP Backend Guide](../../backends/http.md) — usage patterns, configuration, and examples
- [HTTP Backend example](../../examples/http-backend.md) — read-only HTTP access in action
