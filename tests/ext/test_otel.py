"""Tests for remote_store.ext.otel -- OpenTelemetry bridge."""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from remote_store._errors import NotFound
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.observe import ObservedStore, observe
from remote_store.ext.otel import otel_hooks, otel_observe

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def otel_env() -> dict[str, Any]:
    """Return a dict with span_exporter, metric_reader, tracer, meter."""
    span_exporter = InMemorySpanExporter()
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(span_exporter))
    metric_reader = InMemoryMetricReader()
    mp = MeterProvider(metric_readers=[metric_reader])
    return {
        "span_exporter": span_exporter,
        "metric_reader": metric_reader,
        "tracer": tp.get_tracer("remote_store"),
        "meter": mp.get_meter("remote_store"),
    }


def _observed(env: dict[str, Any], *paths: str) -> tuple[ObservedStore, dict[str, Any]]:
    """Create an observed store, optionally pre-populated with files."""
    store = Store(backend=MemoryBackend())
    for p in paths:
        store.write(p, b"data")
    return otel_observe(store, tracer=env["tracer"], meter=env["meter"]), env


def _get_metrics(reader: InMemoryMetricReader) -> dict[str, Any]:
    """Collect metrics and return a name -> data mapping."""
    data = reader.get_metrics_data()
    result: dict[str, Any] = {}
    if data is None:
        return result
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                result[m.name] = m
    return result


# ---------------------------------------------------------------------------
# OBS-011: otel_hooks factory & otel_observe
# ---------------------------------------------------------------------------


class TestOtelSetup:
    @pytest.mark.spec("OBS-011")
    def test_hooks_returns_callable_around_and_on_any(self, otel_env: dict[str, Any]) -> None:
        hooks = otel_hooks(tracer=otel_env["tracer"], meter=otel_env["meter"])
        assert "around" in hooks
        assert "on_any" in hooks
        assert callable(hooks["around"])
        assert callable(hooks["on_any"])

    @pytest.mark.spec("OBS-011")
    def test_hooks_unpack_into_observe(self, otel_env: dict[str, Any]) -> None:
        observed = observe(
            Store(backend=MemoryBackend()), **otel_hooks(tracer=otel_env["tracer"], meter=otel_env["meter"])
        )
        assert isinstance(observed, ObservedStore)
        observed.write("probe.txt", b"ok")
        assert observed.read_bytes("probe.txt") == b"ok"

    @pytest.mark.spec("OBS-011")
    def test_custom_tracer_and_meter_names(self) -> None:
        hooks = otel_hooks(tracer_name="my.tracer", meter_name="my.meter")
        assert "around" in hooks
        assert "on_any" in hooks

    @pytest.mark.spec("OBS-011")
    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"tracer_name": "custom", "meter_name": "custom"}, id="custom-names"),
        ],
    )
    def test_otel_observe_returns_observed_store(self, kwargs: dict[str, str]) -> None:
        observed = otel_observe(Store(backend=MemoryBackend()), **kwargs)
        assert isinstance(observed, ObservedStore)
        assert isinstance(observed, Store)
        observed.write("probe.txt", b"ok")
        assert observed.read_bytes("probe.txt") == b"ok"

    @pytest.mark.spec("OBS-011")
    def test_otel_observe_with_env(self, otel_env: dict[str, Any]) -> None:
        observed = otel_observe(Store(backend=MemoryBackend()), tracer=otel_env["tracer"], meter=otel_env["meter"])
        assert isinstance(observed, ObservedStore)
        observed.write("probe.txt", b"ok")
        assert observed.read_bytes("probe.txt") == b"ok"
        spans = otel_env["span_exporter"].get_finished_spans()
        assert len(spans) >= 1


# ---------------------------------------------------------------------------
# OBS-012: Span conventions
# ---------------------------------------------------------------------------


class TestSpanConventions:
    @pytest.mark.spec("OBS-012")
    def test_span_name_and_kind(self, otel_env: dict[str, Any]) -> None:
        obs, env = _observed(otel_env, "a.txt")
        obs.read_bytes("a.txt")
        spans = env["span_exporter"].get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "store.read_bytes"
        assert spans[0].kind == SpanKind.CLIENT

    @pytest.mark.spec("OBS-012")
    def test_span_attributes(self, otel_env: dict[str, Any]) -> None:
        obs, env = _observed(otel_env, "data.csv")
        obs.read_bytes("data.csv")
        attrs = dict(env["span_exporter"].get_finished_spans()[0].attributes or {})
        assert attrs["remote_store.operation"] == "read_bytes"
        assert attrs["remote_store.backend"] == "memory"
        assert attrs["remote_store.path"] == "data.csv"

    @pytest.mark.spec("OBS-012")
    def test_span_error_status_and_exception(self, otel_env: dict[str, Any]) -> None:
        obs, env = _observed(otel_env)
        with pytest.raises(NotFound):
            obs.read("nonexistent.txt")
        span = env["span_exporter"].get_finished_spans()[0]
        assert span.status.status_code == StatusCode.ERROR
        assert span.attributes is not None
        assert span.attributes.get("error.type") == "NotFound"
        assert any(e.name == "exception" for e in span.events)

    @pytest.mark.spec("SAW-015")
    def test_open_atomic_span_covers_full_lifecycle(self, otel_env: dict[str, Any]) -> None:
        """SAW-015: a single ``store.open_atomic`` span wraps the open-write-promote lifecycle.

        The ``around`` hook opens the span on enter and closes it on context
        exit -- after the write is promoted to the final key -- so the whole
        atomic write is one span, not one-per-inner-op. Asserting the payload
        is readable afterwards confirms promotion happened inside the span's
        extent.
        """
        obs, env = _observed(otel_env)
        with obs.open_atomic("atomic.txt") as f:
            f.write(b"promote me")
        spans = env["span_exporter"].get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "store.open_atomic"
        assert spans[0].status.status_code != StatusCode.ERROR
        attrs = dict(spans[0].attributes or {})
        assert attrs["remote_store.operation"] == "open_atomic"
        assert obs.read_bytes("atomic.txt") == b"promote me"

    @pytest.mark.spec("OBS-012")
    def test_multiple_operations_create_multiple_spans(self, otel_env: dict[str, Any]) -> None:
        obs, env = _observed(otel_env)
        obs.write("a.txt", b"data")
        obs.exists("a.txt")
        obs.read_bytes("a.txt")
        spans = env["span_exporter"].get_finished_spans()
        assert len(spans) == 3
        assert [s.name for s in spans] == ["store.write", "store.exists", "store.read_bytes"]


# ---------------------------------------------------------------------------
# OBS-013: Metric instruments
# ---------------------------------------------------------------------------


class TestMetricInstruments:
    @pytest.mark.spec("OBS-013")
    def test_operations_counter_on_success(self, otel_env: dict[str, Any]) -> None:
        obs, env = _observed(otel_env)
        obs.write("a.txt", b"data")
        m = _get_metrics(env["metric_reader"])
        assert "remote_store.operations" in m
        points = list(m["remote_store.operations"].data.data_points)
        assert len(points) == 1
        assert points[0].value == 1
        attrs = dict(points[0].attributes)
        assert (attrs["operation"], attrs["backend"], attrs["status"]) == ("write", "memory", "ok")

    @pytest.mark.spec("OBS-013")
    def test_error_metrics(self, otel_env: dict[str, Any]) -> None:
        """operations counter status=error + errors counter + error.type attr."""
        obs, env = _observed(otel_env)
        with pytest.raises(NotFound):
            obs.read("missing.txt")
        m = _get_metrics(env["metric_reader"])
        ops_points = list(m["remote_store.operations"].data.data_points)
        assert dict(ops_points[0].attributes)["status"] == "error"
        assert "remote_store.errors" in m
        err_points = list(m["remote_store.errors"].data.data_points)
        assert err_points[0].value == 1
        assert dict(err_points[0].attributes)["error.type"] == "NotFound"

    @pytest.mark.spec("OBS-013")
    def test_duration_histogram(self, otel_env: dict[str, Any]) -> None:
        obs, env = _observed(otel_env, "a.txt")
        obs.read_bytes("a.txt")
        m = _get_metrics(env["metric_reader"])
        assert "remote_store.operation.duration" in m
        points = list(m["remote_store.operation.duration"].data.data_points)
        assert len(points) == 1
        assert points[0].count == 1
        assert points[0].sum >= 0.0
        attrs = dict(points[0].attributes)
        assert (attrs["operation"], attrs["backend"]) == ("read_bytes", "memory")
        for metric_data in m.values():
            for pt in metric_data.data.data_points:
                assert "path" not in dict(pt.attributes)
                assert "remote_store.path" not in dict(pt.attributes)

    @pytest.mark.spec("OBS-013")
    def test_duration_histogram_error_includes_error_type(self, otel_env: dict[str, Any]) -> None:
        obs, env = _observed(otel_env)
        with pytest.raises(NotFound):
            obs.read("missing.txt")
        points = list(_get_metrics(env["metric_reader"])["remote_store.operation.duration"].data.data_points)
        assert dict(points[0].attributes)["error.type"] == "NotFound"


# ---------------------------------------------------------------------------
# OBS-014: Import gating
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-014")
@pytest.mark.parametrize("name", ["otel_hooks", "otel_observe"])
def test_exports(name: str) -> None:
    """Public API available from ext.otel.__all__ (not top-level, ADR-0013)."""
    import remote_store
    from remote_store.ext import otel

    assert not hasattr(remote_store, name)
    assert name in otel.__all__


# ---------------------------------------------------------------------------
# Integration: full round-trip
# ---------------------------------------------------------------------------


def test_full_round_trip(otel_env: dict[str, Any]) -> None:
    """Write, read, delete -- verify spans and metrics for all three."""
    obs, env = _observed(otel_env)
    obs.write("test.txt", b"hello")
    obs.read_bytes("test.txt")
    obs.delete("test.txt")
    spans = env["span_exporter"].get_finished_spans()
    assert len(spans) == 3
    assert [s.name for s in spans] == ["store.write", "store.read_bytes", "store.delete"]
    m = _get_metrics(env["metric_reader"])
    assert "remote_store.operations" in m
    assert "remote_store.operation.duration" in m


def test_error_does_not_break_observation(otel_env: dict[str, Any]) -> None:
    """Errors propagate correctly through the OTel-instrumented store."""
    obs, env = _observed(otel_env)
    with pytest.raises(NotFound):
        obs.read("no-such-file.txt")
    spans = env["span_exporter"].get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code == StatusCode.ERROR
