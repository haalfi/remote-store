"""OpenTelemetry tracing and metrics -- instrument any Store with OTel.

Requires: pip install "remote-store[otel]" opentelemetry-sdk

Demonstrates:
- Wrapping a Store with OTel spans and metrics
- Using otel_observe() one-liner
- Using otel_hooks() for custom composition
- Viewing collected spans and metrics
"""

from __future__ import annotations

try:
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
except ImportError as _exc:
    print("This example requires: pip install 'remote-store[otel]' opentelemetry-sdk")
    raise SystemExit(1) from _exc

from opentelemetry import metrics, trace

from remote_store import Store
from remote_store.backends import MemoryBackend
from remote_store.ext.otel import otel_observe


def main() -> None:
    # -- Set up OTel SDK with in-memory exporters (for demo) --------
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(_SimpleProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # -- Create and instrument a Store ------------------------------
    store = Store(backend=MemoryBackend())
    observed = otel_observe(store)
    print("Store instrumented with OpenTelemetry\n")

    # -- Perform some operations ------------------------------------
    observed.write("data/report.csv", b"id,value\n1,100\n2,200")
    print("Wrote data/report.csv")

    content = observed.read_bytes("data/report.csv")
    print(f"Read {len(content)} bytes from data/report.csv")

    observed.copy("data/report.csv", "data/report_backup.csv")
    print("Copied to data/report_backup.csv")

    observed.exists("data/report.csv")
    print("Checked existence")

    observed.delete("data/report_backup.csv")
    print("Deleted backup\n")

    # -- Inspect collected spans ------------------------------------
    spans = span_exporter.get_finished_spans()
    print(f"--- {len(spans)} spans collected ---")
    for span in spans:
        attrs = dict(span.attributes or {})
        status = "OK" if span.status.is_ok else "ERROR"
        print(f"  {span.name:24s}  status={status:5s}  backend={attrs.get('remote_store.backend', '?')}")

    # -- Inspect collected metrics ----------------------------------
    data = metric_reader.get_metrics_data()
    print("\n--- Metrics ---")
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                points = list(m.data.data_points)
                total = sum(getattr(p, "value", 0) or getattr(p, "count", 0) for p in points)
                print(f"  {m.name:40s}  unit={m.unit:3s}  data_points={len(points)}  total={total}")

    # -- Cleanup ----------------------------------------------------
    store.close()
    tracer_provider.shutdown()
    meter_provider.shutdown()
    print("\nDone!")


class _SimpleProcessor:
    """Minimal span processor for the example."""

    def __init__(self, exporter: InMemorySpanExporter) -> None:
        self._exporter = exporter

    def on_start(self, span, parent_context=None):  # type: ignore[no-untyped-def]
        pass

    def on_end(self, span):  # type: ignore[no-untyped-def]
        self._exporter.export([span])

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 0) -> bool:
        return True


if __name__ == "__main__":
    main()
