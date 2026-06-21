"""Minimal OpenTelemetry setup with console exporters (no external services)."""

from __future__ import annotations

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)


def configure_otel() -> None:
    """Set up OTel with console exporters (no Jaeger/Grafana needed).

    Spans print to stderr as JSON lines; metrics export every 10 seconds.
    For production, swap ConsoleSpanExporter for OTLPSpanExporter.

    Idempotent and non-clobbering: if a real (SDK) provider is already
    installed — because this ran once, or the host application configured
    OTel itself, or a test pre-installed its own providers — this is a
    no-op for that signal. OpenTelemetry pins the first ``set_*_provider()``
    per process and warns-and-ignores later sets, so re-setting would be
    both ineffective and noisy; skipping respects an existing setup.
    """
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)

    if not isinstance(metrics.get_meter_provider(), MeterProvider):
        metrics.set_meter_provider(
            MeterProvider(
                metric_readers=[
                    PeriodicExportingMetricReader(
                        ConsoleMetricExporter(),
                        export_interval_millis=10_000,
                    )
                ]
            )
        )
