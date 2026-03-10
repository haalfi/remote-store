"""OpenTelemetry bridge -- pre-built hooks emitting OTel spans and metrics.

Provides ready-made ``around`` and ``on_any`` hooks for :func:`observe` that
emit OpenTelemetry traces and metrics.  Depends only on ``opentelemetry-api``
(not the SDK); if no SDK is configured at runtime, all OTel calls become
zero-cost no-ops.

Usage:

```python
from remote_store import observe
from remote_store.ext.otel import otel_hooks

store = observe(store, **otel_hooks())
```

Or as a one-liner:

```python
from remote_store.ext.otel import otel_observe
observed = otel_observe(store)
```

Requires: ``pip install "remote-store[otel]"``
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

try:
    from opentelemetry import metrics, trace
    from opentelemetry.trace import SpanKind, StatusCode
except ModuleNotFoundError as _exc:
    raise ModuleNotFoundError(
        "OpenTelemetry API is required for the otel extension. Install it with: pip install 'remote-store[otel]'"
    ) from _exc

from remote_store.ext.observe import ObservedStore, StoreEvent, observe

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.metrics import Meter
    from opentelemetry.trace import Tracer

    from remote_store._store import Store

__all__ = [
    "otel_hooks",
    "otel_observe",
]


def otel_hooks(
    *,
    tracer_name: str = "remote_store",
    meter_name: str = "remote_store",
    tracer: Tracer | None = None,
    meter: Meter | None = None,
) -> dict[str, Any]:
    """Return hook kwargs for :func:`~remote_store.ext.observe.observe`.

    The returned dict contains an ``around`` context-manager hook (tracing)
    and an ``on_any`` callback (metrics).  Unpack it into ``observe()``:

    ```python
    observed = observe(store, **otel_hooks())
    ```

    :param tracer_name: OTel tracer name (default ``"remote_store"``).
        Ignored when *tracer* is provided.
    :param meter_name: OTel meter name (default ``"remote_store"``).
        Ignored when *meter* is provided.
    :param tracer: Explicit tracer instance. When ``None`` (default),
        obtained from the global ``TracerProvider`` via *tracer_name*.
    :param meter: Explicit meter instance. When ``None`` (default),
        obtained from the global ``MeterProvider`` via *meter_name*.
    :returns: A dict with ``around`` and ``on_any`` keys.
    """
    _tracer = tracer if tracer is not None else trace.get_tracer(tracer_name)
    _meter = meter if meter is not None else metrics.get_meter(meter_name)

    op_counter = _meter.create_counter(
        name="remote_store.operations",
        unit="1",
        description="Number of Store operations",
    )
    err_counter = _meter.create_counter(
        name="remote_store.errors",
        unit="1",
        description="Number of failed Store operations",
    )
    duration_hist = _meter.create_histogram(
        name="remote_store.operation.duration",
        unit="s",
        description="Duration of Store operations in seconds",
    )

    @contextlib.contextmanager
    def _around(operation: str, path: str, backend: str) -> Iterator[None]:
        with _tracer.start_as_current_span(
            f"store.{operation}",
            kind=SpanKind.CLIENT,
            attributes={
                "remote_store.operation": operation,
                "remote_store.backend": backend,
                "remote_store.path": path,
            },
        ) as span:
            try:
                yield
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                span.set_attribute("error.type", type(exc).__qualname__)
                raise

    def _on_any(event: StoreEvent) -> None:
        duration_s = event.duration_ms / 1000.0
        status = "error" if event.error is not None else "ok"
        base_attrs = {
            "operation": event.operation,
            "backend": event.backend,
        }

        # Operation counter
        op_counter.add(1, {**base_attrs, "status": status})

        if event.error is not None:
            error_type = type(event.error).__qualname__
            # Error counter
            err_counter.add(1, {**base_attrs, "error.type": error_type})
            # Duration with error.type
            duration_hist.record(duration_s, {**base_attrs, "error.type": error_type})
        else:
            # Duration without error.type
            duration_hist.record(duration_s, base_attrs)

    return {"around": _around, "on_any": _on_any}


def otel_observe(
    store: Store,
    *,
    tracer_name: str = "remote_store",
    meter_name: str = "remote_store",
    tracer: Tracer | None = None,
    meter: Meter | None = None,
) -> ObservedStore:
    """Convenience: wrap a Store with OTel tracing + metrics in one call.

    Equivalent to ``observe(store, **otel_hooks(...))``.

    :param store: The Store to observe.
    :param tracer_name: OTel tracer name (default ``"remote_store"``).
        Ignored when *tracer* is provided.
    :param meter_name: OTel meter name (default ``"remote_store"``).
        Ignored when *meter* is provided.
    :param tracer: Explicit tracer instance (see :func:`otel_hooks`).
    :param meter: Explicit meter instance (see :func:`otel_hooks`).
    :returns: An ``ObservedStore`` with OTel instrumentation.
    """
    return observe(
        store,
        **otel_hooks(tracer_name=tracer_name, meter_name=meter_name, tracer=tracer, meter=meter),
    )
