# ext.otel

## otel

[OpenTelemetry](https://opentelemetry.io/) bridge -- pre-built hooks emitting OTel spans and metrics.

Provides ready-made `around` and `on_any` hooks for `observe()` that emit OpenTelemetry traces and metrics. Depends only on `opentelemetry-api` (not the SDK); if no SDK is configured at runtime, all OTel calls become zero-cost no-ops.

Example

```
from remote_store import observe
from remote_store.ext.otel import otel_hooks

store = observe(store, **otel_hooks())
```

Or as a one-liner:

```
from remote_store.ext.otel import otel_observe
observed = otel_observe(store)
```

Requires: `pip install "remote-store[otel]"`

### otel_hooks

```
otel_hooks(
    *,
    tracer_name: str = "remote_store",
    meter_name: str = "remote_store",
    tracer: Tracer | None = None,
    meter: Meter | None = None,
) -> dict[str, Any]
```

Return hook kwargs for `observe()`.

The returned dict contains an `around` context-manager hook (tracing) and an `on_any` callback (metrics). Unpack it into `observe()`:

```
observed = observe(store, **otel_hooks())
```

Parameters:

- **`tracer_name`** (`str`, default: `'remote_store'` ) – OTel tracer name (default "remote_store"). Ignored when tracer is provided.
- **`meter_name`** (`str`, default: `'remote_store'` ) – OTel meter name (default "remote_store"). Ignored when meter is provided.
- **`tracer`** (`Tracer | None`, default: `None` ) – Explicit tracer instance. When None (default), obtained from the global TracerProvider via tracer_name.
- **`meter`** (`Meter | None`, default: `None` ) – Explicit meter instance. When None (default), obtained from the global MeterProvider via meter_name.

Returns:

- `dict[str, Any]` – A dict with around and on_any keys.

### otel_observe

```
otel_observe(
    store: Store,
    *,
    tracer_name: str = "remote_store",
    meter_name: str = "remote_store",
    tracer: Tracer | None = None,
    meter: Meter | None = None,
) -> ObservedStore
```

Convenience: wrap a Store with OTel tracing + metrics in one call.

Equivalent to `observe(store, **otel_hooks(...))`.

Parameters:

- **`store`** (`Store`) – The Store to observe.
- **`tracer_name`** (`str`, default: `'remote_store'` ) – OTel tracer name (default "remote_store"). Ignored when tracer is provided.
- **`meter_name`** (`str`, default: `'remote_store'` ) – OTel meter name (default "remote_store"). Ignored when meter is provided.
- **`tracer`** (`Tracer | None`, default: `None` ) – Explicit tracer instance (see otel_hooks()).
- **`meter`** (`Meter | None`, default: `None` ) – Explicit meter instance (see otel_hooks()).

Returns:

- `ObservedStore` – An ObservedStore with OTel instrumentation.

## See also

- [Observe](https://docs.remotestore.dev/stable/guides/observe/index.md) — guide to callback hooks and the OpenTelemetry bridge
- [OTel Tracing example](https://docs.remotestore.dev/stable/tutorial/examples/otel-tracing/index.md) — OpenTelemetry tracing in action
