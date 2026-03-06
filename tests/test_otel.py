"""Tests for remote_store.ext.otel -- OpenTelemetry bridge."""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.observe import ObservedStore, observe
from remote_store.ext.otel import otel_hooks, otel_observe

# ---------------------------------------------------------------------------
# Fixtures — each test gets its own providers (no global state mutation)
# ---------------------------------------------------------------------------


@pytest.fixture()
def otel_env() -> dict[str, Any]:
    """Return a dict with span_exporter, metric_reader, tracer, meter."""
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    tracer = tracer_provider.get_tracer("remote_store")

    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    meter = meter_provider.get_meter("remote_store")

    return {
        "span_exporter": span_exporter,
        "metric_reader": metric_reader,
        "tracer": tracer,
        "meter": meter,
        "tracer_provider": tracer_provider,
        "meter_provider": meter_provider,
    }


def _make_store() -> Store:
    return Store(backend=MemoryBackend())


def _populated_store(*paths: str) -> Store:
    store = _make_store()
    for p in paths:
        store.write(p, b"data")
    return store


def _get_metrics(metric_reader: InMemoryMetricReader) -> dict[str, Any]:
    """Collect metrics and return a name -> data mapping."""
    data = metric_reader.get_metrics_data()
    result: dict[str, Any] = {}
    if data is None:
        return result
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                result[metric.name] = metric
    return result


# ---------------------------------------------------------------------------
# OBS-011: otel_hooks factory
# ---------------------------------------------------------------------------


class TestOtelHooksFactory:
    @pytest.mark.spec("OBS-011")
    def test_returns_dict_with_around_and_on_any(self, otel_env: dict[str, Any]) -> None:
        hooks = otel_hooks(tracer=otel_env["tracer"], meter=otel_env["meter"])
        assert "around" in hooks
        assert "on_any" in hooks
        assert callable(hooks["around"])
        assert callable(hooks["on_any"])

    @pytest.mark.spec("OBS-011")
    def test_hooks_unpack_into_observe(self, otel_env: dict[str, Any]) -> None:
        store = _make_store()
        observed = observe(store, **otel_hooks(tracer=otel_env["tracer"], meter=otel_env["meter"]))
        assert isinstance(observed, ObservedStore)

    @pytest.mark.spec("OBS-011")
    def test_custom_tracer_and_meter_names(self) -> None:
        hooks = otel_hooks(tracer_name="my.tracer", meter_name="my.meter")
        assert "around" in hooks
        assert "on_any" in hooks


class TestOtelObserve:
    @pytest.mark.spec("OBS-011")
    def test_otel_observe_returns_observed_store(self, otel_env: dict[str, Any]) -> None:
        store = _make_store()
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        assert isinstance(observed, ObservedStore)
        assert isinstance(observed, Store)

    @pytest.mark.spec("OBS-011")
    def test_otel_observe_with_custom_names(self) -> None:
        store = _make_store()
        observed = otel_observe(store, tracer_name="custom", meter_name="custom")
        assert isinstance(observed, ObservedStore)


# ---------------------------------------------------------------------------
# OBS-012: Span conventions
# ---------------------------------------------------------------------------


class TestSpanConventions:
    @pytest.mark.spec("OBS-012")
    def test_span_name_format(self, otel_env: dict[str, Any]) -> None:
        store = _populated_store("a.txt")
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        observed.read_bytes("a.txt")
        spans = otel_env["span_exporter"].get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "store.read_bytes"

    @pytest.mark.spec("OBS-012")
    def test_span_kind_client(self, otel_env: dict[str, Any]) -> None:
        from opentelemetry.trace import SpanKind

        store = _make_store()
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        observed.write("a.txt", b"hello")
        spans = otel_env["span_exporter"].get_finished_spans()
        assert spans[0].kind == SpanKind.CLIENT

    @pytest.mark.spec("OBS-012")
    def test_span_attributes(self, otel_env: dict[str, Any]) -> None:
        store = _populated_store("data.csv")
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        observed.read_bytes("data.csv")
        spans = otel_env["span_exporter"].get_finished_spans()
        attrs = dict(spans[0].attributes or {})
        assert attrs["remote_store.operation"] == "read_bytes"
        assert attrs["remote_store.backend"] == "memory"
        assert attrs["remote_store.path"] == "data.csv"

    @pytest.mark.spec("OBS-012")
    def test_span_error_status_and_exception(self, otel_env: dict[str, Any]) -> None:
        from opentelemetry.trace import StatusCode

        from remote_store._errors import NotFound

        store = _make_store()
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        with pytest.raises(NotFound):
            observed.read("nonexistent.txt")
        spans = otel_env["span_exporter"].get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.status.status_code == StatusCode.ERROR
        assert span.attributes is not None
        assert span.attributes.get("error.type") == "NotFound"
        assert any(e.name == "exception" for e in span.events)

    @pytest.mark.spec("OBS-012")
    def test_multiple_operations_create_multiple_spans(self, otel_env: dict[str, Any]) -> None:
        store = _make_store()
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        observed.write("a.txt", b"data")
        observed.exists("a.txt")
        observed.read_bytes("a.txt")
        spans = otel_env["span_exporter"].get_finished_spans()
        assert len(spans) == 3
        names = [s.name for s in spans]
        assert names == ["store.write", "store.exists", "store.read_bytes"]


# ---------------------------------------------------------------------------
# OBS-013: Metric instruments
# ---------------------------------------------------------------------------


class TestMetricInstruments:
    @pytest.mark.spec("OBS-013")
    def test_operations_counter_on_success(self, otel_env: dict[str, Any]) -> None:
        store = _make_store()
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        observed.write("a.txt", b"data")
        m = _get_metrics(otel_env["metric_reader"])
        assert "remote_store.operations" in m
        counter = m["remote_store.operations"]
        points = list(counter.data.data_points)
        assert len(points) == 1
        assert points[0].value == 1
        attrs = dict(points[0].attributes)
        assert attrs["operation"] == "write"
        assert attrs["backend"] == "memory"
        assert attrs["status"] == "ok"

    @pytest.mark.spec("OBS-013")
    def test_error_metrics(self, otel_env: dict[str, Any]) -> None:
        """operations counter status=error + errors counter + error.type attr."""
        from remote_store._errors import NotFound

        store = _make_store()
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        with pytest.raises(NotFound):
            observed.read("missing.txt")
        m = _get_metrics(otel_env["metric_reader"])
        # operations counter records status=error
        ops_points = list(m["remote_store.operations"].data.data_points)
        assert len(ops_points) == 1
        assert dict(ops_points[0].attributes)["status"] == "error"
        # errors counter records error.type
        assert "remote_store.errors" in m
        err_points = list(m["remote_store.errors"].data.data_points)
        assert len(err_points) == 1
        assert err_points[0].value == 1
        assert dict(err_points[0].attributes)["error.type"] == "NotFound"

    @pytest.mark.spec("OBS-013")
    def test_duration_histogram(self, otel_env: dict[str, Any]) -> None:
        store = _populated_store("a.txt")
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        observed.read_bytes("a.txt")
        m = _get_metrics(otel_env["metric_reader"])
        assert "remote_store.operation.duration" in m
        hist = m["remote_store.operation.duration"]
        points = list(hist.data.data_points)
        assert len(points) == 1
        assert points[0].count == 1
        assert points[0].sum >= 0.0
        attrs = dict(points[0].attributes)
        assert attrs["operation"] == "read_bytes"
        assert attrs["backend"] == "memory"
        # High-cardinality path must NOT appear in any metric attributes
        for metric_data in m.values():
            for pt in metric_data.data.data_points:
                pt_attrs = dict(pt.attributes)
                assert "path" not in pt_attrs
                assert "remote_store.path" not in pt_attrs

    @pytest.mark.spec("OBS-013")
    def test_duration_histogram_error_includes_error_type(self, otel_env: dict[str, Any]) -> None:
        from remote_store._errors import NotFound

        store = _make_store()
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        with pytest.raises(NotFound):
            observed.read("missing.txt")
        m = _get_metrics(otel_env["metric_reader"])
        hist = m["remote_store.operation.duration"]
        points = list(hist.data.data_points)
        assert len(points) == 1
        attrs = dict(points[0].attributes)
        assert attrs["error.type"] == "NotFound"


# ---------------------------------------------------------------------------
# OBS-014: Import gating
# ---------------------------------------------------------------------------


class TestImportGating:
    @pytest.mark.spec("OBS-014")
    @pytest.mark.parametrize("name", ["otel_hooks", "otel_observe"])
    def test_exports(self, name: str) -> None:
        """Public API available from top-level and ext.otel.__all__."""
        import remote_store
        from remote_store.ext import otel

        assert hasattr(remote_store, name)
        assert name in otel.__all__


# ---------------------------------------------------------------------------
# Integration: full round-trip
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_round_trip(self, otel_env: dict[str, Any]) -> None:
        """Write, read, delete -- verify spans and metrics for all three."""
        store = _make_store()
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        observed.write("test.txt", b"hello")
        observed.read_bytes("test.txt")
        observed.delete("test.txt")

        spans = otel_env["span_exporter"].get_finished_spans()
        assert len(spans) == 3
        span_names = [s.name for s in spans]
        assert span_names == ["store.write", "store.read_bytes", "store.delete"]

        m = _get_metrics(otel_env["metric_reader"])
        assert "remote_store.operations" in m
        assert "remote_store.operation.duration" in m

    def test_error_does_not_break_observation(self, otel_env: dict[str, Any]) -> None:
        """Errors propagate correctly through the OTel-instrumented store."""
        from opentelemetry.trace import StatusCode

        from remote_store._errors import NotFound

        store = _make_store()
        observed = otel_observe(store, tracer=otel_env["tracer"], meter=otel_env["meter"])
        with pytest.raises(NotFound):
            observed.read("no-such-file.txt")
        # Span was still created and finished
        spans = otel_env["span_exporter"].get_finished_spans()
        assert len(spans) == 1
        assert spans[0].status.status_code == StatusCode.ERROR
