# Info

## info

```
info() -> InfoResult
```

Return a structured summary of available backends and extensions.

Populates the backend registry, then probes each backend and optional extension for availability in the current environment.

Returns:

- `InfoResult` – An InfoResult with keys version, backends, and
- `InfoResult` – extensions.

## InfoResult

Bases: `TypedDict`

Structured result of the `info` function.

## BackendInfo

```
BackendInfo = TypedDict(
    "BackendInfo",
    {
        "available": bool,
        "extras": str | None,
        "class": str | None,
    },
)
```

## ExtensionInfo

Bases: `TypedDict`

Information about a single extension.

## See also

- [Health Check](https://docs.remotestore.dev/stable/guides/health-check/index.md) — verifying backend reachability at runtime
- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — per-backend capability comparison
