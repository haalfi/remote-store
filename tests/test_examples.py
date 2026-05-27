"""Expectation tests wrapping example demos.

Each example exposes a ``demo(...)`` function with the scenario.
This module imports each demo and asserts on postconditions.
Examples stay print-based for users; tests add verification.

Design rationale (ID-044): examples are the single source of truth for
the scenario. This module adds the assertion layer — no duplicated setup.
"""

from __future__ import annotations

import sys

import pytest

from remote_store import (
    AlreadyExists,
    BackendConfig,
    InvalidPath,
    NotFound,
    Registry,
    RegistryConfig,
    Store,
    StoreProfile,
)
from remote_store.backends import MemoryBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_store():
    """Fresh MemoryBackend-backed Store for each test."""
    backend = MemoryBackend()
    store = Store(backend=backend)
    yield store
    store.close()


@pytest.fixture
def two_stores():
    """Two isolated memory stores sharing one backend (for transfer tests)."""
    config = RegistryConfig(
        backends={"mem": BackendConfig(type="memory", options={})},
        stores={
            "primary": StoreProfile(backend="mem", root_path="primary"),
            "archive": StoreProfile(backend="mem", root_path="archive"),
        },
    )
    with Registry(config) as registry:
        yield registry.get_store("primary"), registry.get_store("archive")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_hello_store(tmp_path, subdir):
    """Verify quickstart demo wrote hello.txt correctly."""
    from remote_store import Store
    from remote_store.backends import LocalBackend

    store = Store(LocalBackend(root=str(tmp_path / subdir)))
    assert store.exists("hello.txt")
    assert store.read_bytes("hello.txt") == b"Hello, world!"
    assert store.get_file_info("hello.txt").size == 13
    store.close()


# ---------------------------------------------------------------------------
# Quickstart (parametrized)
# ---------------------------------------------------------------------------


class TestQuickstart:
    @pytest.mark.spec("STORE-008")
    @pytest.mark.parametrize(
        ("demo_func", "subdir"),
        [
            pytest.param("demo_direct", "direct", id="direct"),
            pytest.param("demo_registry", "registry", id="registry"),
        ],
    )
    def test_demo(self, tmp_path, demo_func, subdir):
        import examples.getting_started.quickstart as qs

        getattr(qs, demo_func)(str(tmp_path / subdir))
        _verify_hello_store(tmp_path, subdir)
        assert (tmp_path / subdir).exists()


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


class TestFileOperations:
    @pytest.mark.spec("STORE-008")
    def test_demo(self, memory_store):
        from examples.getting_started.file_operations import demo

        demo(memory_store)

        assert memory_store.exists("docs/readme.txt")
        assert not memory_store.exists("docs/changelog.txt")
        assert memory_store.exists("archive/changelog.txt")
        assert memory_store.exists("data/report.csv")
        assert not memory_store.exists("docs/readme_backup.txt")
        assert not memory_store.exists("tmp/scratch.txt")
        assert memory_store.read_bytes("data/report.csv") == b"col1,col2\n1,2\n3,4"
        assert memory_store.is_file("docs/readme.txt")
        assert memory_store.is_folder("docs")
        assert not memory_store.is_file("docs")
        assert not memory_store.is_folder("docs/readme.txt")


# ---------------------------------------------------------------------------
# Streaming I/O
# ---------------------------------------------------------------------------


class TestStreamingIO:
    @pytest.mark.spec("SIO-001")
    @pytest.mark.spec("SIO-002")
    @pytest.mark.spec("SIO-003")
    def test_demo(self, memory_store):
        from examples.getting_started.streaming_io import demo

        demo(memory_store)

        assert memory_store.read_bytes("streamed.txt") == b"line1\nline2\nline3\nline4\nline5\n"
        assert memory_store.read_bytes("large.bin") == b"X" * 10_000
        assert memory_store.read_bytes("direct.txt") == b"Written as raw bytes"

        with memory_store.read("streamed.txt") as reader:
            assert reader.read() == b"line1\nline2\nline3\nline4\nline5\n"


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


class TestAtomicWrites:
    @pytest.mark.spec("AW-001")
    @pytest.mark.spec("AW-003")
    def test_demo(self, memory_store):
        from examples.getting_started.atomic_writes import demo

        results = demo(memory_store)

        assert isinstance(results["atomic_already_exists"], AlreadyExists)
        assert isinstance(results["write_already_exists"], AlreadyExists)
        assert memory_store.read_bytes("config.json") == b'{"version": 2}'
        assert memory_store.read_bytes("data.txt") == b"updated"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestConfiguration:
    @pytest.mark.spec("CFG-003")
    @pytest.mark.spec("CFG-005")
    @pytest.mark.spec("SEC-001")
    @pytest.mark.spec("SEC-003")
    def test_demo(self):
        from examples.configuration.configuration import demo

        results = demo()

        assert results["secret_repr"] == "Secret('***')"
        assert results["secret_str"] == "***"
        assert results["secret_reveal"] == "my-secret-key"
        assert results["auto_key_repr"] == "Secret('***')"
        assert results["auto_secret_repr"] == "Secret('***')"
        assert results["bucket_value"] == "my-bucket"
        assert results["from_dict_data"] == b"a,b\n1,2\n"
        assert results["from_dict_logs"] == b"[INFO] started\n"
        assert isinstance(results["validation_error"], ValueError)


class TestConfigLoaders:
    @pytest.mark.spec("CFG-018")
    def test_demo(self):
        pytest.importorskip("yaml", reason="PyYAML not installed")

        from examples.configuration.config_loaders import demo

        results = demo()

        # TOML loaders
        assert results["toml_content"] == b"Hello from TOML config!"
        assert results["pyproject_bytes"] == 3
        # YAML loader
        assert results["yaml_content"] == b"[INFO] started\n"
        # Pydantic loader (optional dep)
        if results["pydantic_stores"] is not None:
            assert results["pydantic_stores"] == 1
            assert results["pydantic_content"] == b"Ship config loaders!"
        # resolve_env()
        assert results["resolve_env_backends"] == 1
        assert results["default_value"] == "hello world"
        assert isinstance(results["resolved_root"], str)
        assert len(results["resolved_root"]) > 0

    @pytest.mark.os_sensitive
    def test_posix_paths_in_generated_config(self):
        """BUG-136 regression: generated TOML/YAML must use forward slashes."""
        from pathlib import PureWindowsPath

        from examples.configuration.config_loaders import _posix

        # Simulate a Windows path — should produce forward slashes
        win_path = PureWindowsPath("C:/Users/test/data")
        assert "\\" not in _posix(win_path)
        assert _posix(win_path) == "C:/Users/test/data"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.spec("ERR-002")
    @pytest.mark.spec("ERR-003")
    @pytest.mark.spec("ERR-005")
    def test_demo(self, memory_store):
        from examples.errors.error_handling import demo

        results = demo(memory_store)

        nf = results["not_found"]
        assert isinstance(nf, NotFound)
        assert nf.path == "nonexistent.txt"
        assert nf.backend is not None

        ae = results["already_exists"]
        assert isinstance(ae, AlreadyExists)
        assert ae.path == "existing.txt"

        assert isinstance(results["invalid_path"], InvalidPath)
        assert len(results["base_class_errors"]) == 2
        assert results["missing_ok_succeeded"] is True


# ---------------------------------------------------------------------------
# Memory backend
# ---------------------------------------------------------------------------


class TestMemoryBackend:
    @pytest.mark.spec("MEM-DS-002")
    def test_demo(self, memory_store):
        from examples.advanced.memory_backend import demo

        demo(memory_store)

        assert memory_store.exists("hello.txt")
        assert memory_store.read_bytes("hello.txt") == b"Hello from memory!"
        assert memory_store.exists("reports/q1.csv")
        assert not memory_store.exists("reports/q2.csv")
        assert memory_store.exists("archive/q1.csv")
        assert memory_store.exists("archive/q2.csv")


# ---------------------------------------------------------------------------
# Store.child()
# ---------------------------------------------------------------------------


class TestStoreChild:
    @pytest.mark.spec("CHILD-001")
    @pytest.mark.spec("CHILD-002")
    @pytest.mark.spec("CHILD-004")
    @pytest.mark.spec("CHILD-005")
    @pytest.mark.spec("CHILD-006")
    def test_demo(self, memory_store):
        from examples.advanced.store_child import demo

        demo(memory_store)

        assert memory_store.exists("reports/q1.csv")
        assert memory_store.exists("reports/q2.csv")
        assert memory_store.exists("archive/2024/summary.txt")
        assert memory_store.read_bytes("reports/q1.csv") == b"revenue,100\n"
        assert memory_store.read_bytes("archive/2024/summary.txt") == b"Year-end summary"
        assert memory_store.child("archive").child("2024") == memory_store.child("archive/2024")

        child = memory_store.child("reports")
        child.close()
        assert memory_store.read_bytes("reports/q1.csv") == b"revenue,100\n"


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------


class TestBatchOperations:
    @pytest.mark.spec("BATCH-001")
    @pytest.mark.spec("BATCH-002")
    @pytest.mark.spec("BATCH-008")
    @pytest.mark.spec("BATCH-014")
    def test_demo(self, memory_store):
        from examples.extensions.batch_operations import demo

        results = demo(memory_store)

        assert results["exists"]["a.txt"] is True
        assert results["exists"]["b.txt"] is True
        assert results["exists"]["missing.txt"] is False
        assert results["copy_ok"].all_succeeded is True
        assert results["copy_ok"].total == 2
        assert not results["copy_partial"].all_succeeded
        assert "c.txt" in results["copy_partial"].failed
        assert isinstance(results["copy_partial"].failed["c.txt"], AlreadyExists)
        assert results["delete_ok"].all_succeeded is True
        assert results["delete_missing_ok"].all_succeeded is True
        assert "gone.txt" in results["delete_stop_on_error"].failed


# ---------------------------------------------------------------------------
# Glob pattern matching
# ---------------------------------------------------------------------------


class TestGlobPatternMatching:
    @pytest.mark.spec("GLOB-001")
    @pytest.mark.spec("GLOB-009")
    def test_demo(self, memory_store):
        from examples.extensions.glob_pattern_matching import demo

        results = demo(memory_store)

        assert results["tier1_csvs"] == ["report.csv"]
        assert results["tier1_reports"] == ["report.csv", "report.txt"]
        assert results["tier1_md"] == ["docs/guide.md", "docs/readme.md"]
        assert set(results["tier1_logs_recursive"]) == {
            "logs/app.log",
            "logs/error.log",
            "logs/archive/old.log",
        }
        assert len(results["tier1_logs_recursive"]) == 3
        assert len(results["tier3_deep_logs"]) == 3
        assert results["tier3_doc_mds"] == ["docs/guide.md", "docs/readme.md"]
        assert len(results["tier3_everything"]) == 8
        assert len(results["child_tier1"]) == 2
        assert len(results["child_tier3"]) == 3


# ---------------------------------------------------------------------------
# Transfer operations
# ---------------------------------------------------------------------------


class TestTransferOperations:
    @pytest.mark.spec("XFER-001")
    @pytest.mark.spec("XFER-006")
    @pytest.mark.spec("XFER-011")
    def test_demo(self, two_stores, tmp_path):
        from examples.extensions.transfer_operations import demo

        primary, archive = two_stores
        results = demo(primary, archive, str(tmp_path))

        expected_content = b"Hello from local filesystem!"
        for key in ("uploaded_content", "downloaded_content", "transferred_content"):
            assert results[key] == expected_content
        for key in ("upload_bytes", "download_bytes", "transfer_bytes"):
            assert results[key] == 100_000
        assert isinstance(results["download_overwrite_guard"], FileExistsError)

        assert primary.exists("hello.txt")
        assert primary.exists("large.bin")
        assert archive.exists("hello_archived.txt")
        assert archive.exists("large_archived.bin")


# ---------------------------------------------------------------------------
# Observe hooks
# ---------------------------------------------------------------------------


class TestObserveHooks:
    @pytest.mark.spec("OBS-001")
    @pytest.mark.spec("OBS-002")
    @pytest.mark.spec("OBS-003")
    @pytest.mark.spec("OBS-005")
    @pytest.mark.spec("OBS-006")
    def test_demo(self, memory_store):
        from examples.extensions.observe_hooks import demo

        results = demo(memory_store)

        assert len(results["write_events"]) == 2
        assert results["write_events"][0].operation == "write_text"
        assert len(results["read_events"]) == 1
        assert results["read_events"][0].operation == "read_bytes"

        assert len(results["any_events"]) == 3
        ops = {e.operation for e in results["any_events"]}
        assert ops == {"exists", "copy", "delete"}

        assert "is_file" in results["around_ops"]
        assert len(results["buffered_events"]) == 3

        for event in results["write_events"] + results["read_events"] + results["any_events"]:
            assert event.duration_ms >= 0
            assert event.error is None


# ---------------------------------------------------------------------------
# Smoke tests (demos with no/minimal assertions)
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    @pytest.mark.spec("RET-001")
    def test_demo(self):
        from examples.advanced.retry_policy import demo

        result = demo()
        assert result is None


class TestHealthCheck:
    @pytest.mark.spec("PING-001")
    def test_demo(self, memory_store: Store):
        from examples.advanced.health_check import demo

        result = demo(memory_store)
        assert result is None


# ---------------------------------------------------------------------------
# Optional-dependency examples
# ---------------------------------------------------------------------------


class TestOtelTracing:
    @pytest.mark.spec("OBS-011")
    def test_demo(self, memory_store):
        pytest.importorskip("opentelemetry")

        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        from examples.extensions.otel_tracing import demo
        from remote_store.ext.otel import otel_observe

        span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
        metric_reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[metric_reader])

        observed = otel_observe(
            memory_store,
            tracer=tracer_provider.get_tracer("test"),
            meter=meter_provider.get_meter("test"),
        )
        demo(observed)

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 5
        span_names = {s.name for s in spans}
        assert {"store.write", "store.read_bytes"} <= span_names

        data = metric_reader.get_metrics_data()
        metric_names = {m.name for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics}
        assert "remote_store.operations" in metric_names

        tracer_provider.shutdown()
        meter_provider.shutdown()


class TestPyArrowAdapter:
    @pytest.mark.spec("PA-002")
    def test_demo(self, memory_store):
        pytest.importorskip("pyarrow")

        from examples.integrations.pyarrow_adapter import demo

        results = demo(memory_store)

        assert results["people_rows"] == 3
        assert results["people_data"]["id"] == [1, 2, 3]
        assert results["people_data"]["name"] == ["Alice", "Bob", "Charlie"]
        assert results["file_size"] > 0
        assert results["dataset_rows"] == 15
        assert results["dataset_files"] == 3


class TestParquetDataset:
    @pytest.mark.spec("PDS-002,PDS-003,PDS-006")
    def test_demo(self, memory_store):
        pytest.importorskip("pyarrow")

        from examples.integrations.parquet_dataset import demo

        results = demo(memory_store)

        assert results["single_parts"] == ["data.parquet"]
        assert results["single_rows"] == 3
        assert results["read_rows"] == 3
        assert results["projected_columns"] == ["id", "name"]
        assert results["multi_parts"] == 2
        assert results["overwrite_rows"] == 2
        assert results["compression"] == "zstd"
        assert results["exists"] is True
        assert results["missing"] is False


class TestHttpBackend:
    @pytest.mark.spec("HTTP-001")
    def test_demo(self):
        pytest.importorskip("pytest_httpserver", reason="pytest-httpserver not installed")

        from pytest_httpserver import HTTPServer
        from werkzeug.wrappers import Response as WerkzeugResponse

        from examples.backends.http_backend import demo
        from remote_store.backends import ReadOnlyHttpBackend

        server = HTTPServer(host="127.0.0.1")
        server.expect_request("/files/hello.txt", method="GET").respond_with_data(
            b"Hello, HTTP world!",
            content_type="text/plain",
            headers={"Content-Length": "18"},
        )
        head_resp = WerkzeugResponse(b"", status=200, content_type="text/plain")
        head_resp.content_length = 18
        server.expect_request("/files/hello.txt", method="HEAD").respond_with_response(head_resp)
        server.start()

        try:
            backend = ReadOnlyHttpBackend(
                base_url=server.url_for("/files/"),
                http_client="urllib",
            )
            store = Store(backend=backend)
            results = demo(store)
            store.close()
        finally:
            server.clear()
            if server.is_running():
                server.stop()

        assert results["supports_read"] is True
        assert results["supports_write"] is False
        assert results["read_content"] == b"Hello, HTTP world!"
        assert results["read_text"] == "Hello, HTTP world!"
        assert results["content_type"] == "text/plain"
        assert results["size"] == 18
        assert "write" in results["write_error"]


class TestDagsterIOManager:
    @pytest.mark.spec("DAG-002,DAG-003,DAG-005")
    def test_demo(self):
        pytest.importorskip("dagster")

        from examples.integrations.dagster_io_manager import demo

        results = demo()

        assert results["pickle_roundtrip"] is True
        assert results["partition_path_exists"] is True
        assert results["json_roundtrip"] is True


class TestDagsterV2Resource:
    @pytest.mark.spec("DAG-012,DAG-013")
    def test_demo(self):
        pytest.importorskip("dagster")

        from examples.integrations.dagster_v2_resource import demo

        results = demo()

        assert results["pickle_roundtrip"] is True
        assert results["teardown_ok"] is True


class TestDagsterComputeLogManager:
    pytestmark = pytest.mark.os_sensitive

    # Mirrors the skipif on tests/ext/test_dagster.py::TestComputeLogManagerEndToEnd.
    # Upstream dagster-io/dagster#24043 closed as not-planned, so the empty-files
    # behaviour on Windows is settled, not a transient bug.
    @pytest.mark.spec("DAG-021,DAG-022,DAG-025")
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Dagster's FD-level compute-log capture yields empty files on Windows under execute_in_process",
    )
    def test_demo(self):
        pytest.importorskip("dagster")

        from examples.integrations.dagster_compute_log_manager import demo

        results = demo()

        assert results["manager_is_remote_store"] is True
        assert results["job_succeeded"] is True
        assert results["stdout_captured"] is True
        assert results["stderr_captured"] is True


# ---------------------------------------------------------------------------
# Async Store
# ---------------------------------------------------------------------------


class TestAsyncStore:
    @pytest.mark.spec("ASYNC-040")
    async def test_demo(self):
        from examples.advanced.async_store import demo
        from remote_store.aio import AsyncMemoryBackend, AsyncStore

        async with AsyncStore(AsyncMemoryBackend(), root_path="data") as store:
            await demo(store)

            assert await store.exists("hello.txt")
            assert await store.read_text("hello.txt") == "Hello, async world!"
            assert await store.exists("data.csv")
            assert await store.exists("reports/q1.txt")
            info = await store.get_file_info("hello.txt")
            assert info.size == len(b"Hello, async world!")
