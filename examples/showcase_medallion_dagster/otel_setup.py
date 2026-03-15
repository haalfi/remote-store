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
    """
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

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
