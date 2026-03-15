"""Expectation tests wrapping example demos.

Each example exposes a ``demo(...)`` function with the scenario.
This module imports each demo and asserts on postconditions.
Examples stay print-based for users; tests add verification.

Design rationale (ID-044): examples are the single source of truth for
the scenario. This module adds the assertion layer — no duplicated setup.
"""

from __future__ import annotations

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


@pytest.fixture()
def memory_store():
    """Fresh MemoryBackend-backed Store for each test."""
    backend = MemoryBackend()
    store = Store(backend=backend)
    yield store
    store.close()


@pytest.fixture()
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
# Quickstart
# ---------------------------------------------------------------------------


class TestQuickstart:
    @pytest.mark.spec("STORE-008")
    def test_demo_direct(self, tmp_path):
        from examples.quickstart import demo_direct

        demo_direct(str(tmp_path / "direct"))

        from remote_store import Store
        from remote_store.backends import LocalBackend

        store = Store(LocalBackend(root=str(tmp_path / "direct")))
        assert store.exists("hello.txt")
        assert store.read_bytes("hello.txt") == b"Hello, world!"
        info = store.get_file_info("hello.txt")
        assert info.size == 13
        store.close()

    @pytest.mark.spec("STORE-008")
    def test_demo_registry(self, tmp_path):
        from examples.quickstart import demo_registry

        demo_registry(str(tmp_path / "registry"))

        from remote_store import Store
        from remote_store.backends import LocalBackend

        store = Store(LocalBackend(root=str(tmp_path / "registry")))
        assert store.exists("hello.txt")
        assert store.read_bytes("hello.txt") == b"Hello, world!"
        info = store.get_file_info("hello.txt")
        assert info.size == 13
        store.close()


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


class TestFileOperations:
    @pytest.mark.spec("STORE-008")
    def test_demo(self, memory_store):
        from examples.file_operations import demo

        demo(memory_store)

        # After the demo: readme_backup.txt deleted, tmp/ folder deleted,
        # changelog.txt moved to archive/.
        assert memory_store.exists("docs/readme.txt")
        assert not memory_store.exists("docs/changelog.txt")  # moved
        assert memory_store.exists("archive/changelog.txt")
        assert memory_store.exists("data/report.csv")
        assert not memory_store.exists("docs/readme_backup.txt")  # deleted
        assert not memory_store.exists("tmp/scratch.txt")  # folder deleted

        # Content integrity
        assert memory_store.read_bytes("data/report.csv") == b"col1,col2\n1,2\n3,4"

        # Metadata
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
        from examples.streaming_io import demo

        demo(memory_store)

        # Verify file contents
        assert memory_store.read_bytes("streamed.txt") == b"line1\nline2\nline3\nline4\nline5\n"
        assert memory_store.read_bytes("large.bin") == b"X" * 10_000
        assert memory_store.read_bytes("direct.txt") == b"Written as raw bytes"

        # Verify streaming read round-trip
        with memory_store.read("streamed.txt") as reader:
            content = reader.read()
        assert content == b"line1\nline2\nline3\nline4\nline5\n"


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


class TestAtomicWrites:
    @pytest.mark.spec("AW-001")
    @pytest.mark.spec("AW-003")
    def test_demo(self, memory_store):
        from examples.atomic_writes import demo

        results = demo(memory_store)

        # AlreadyExists raised on both atomic and regular write
        assert isinstance(results["atomic_already_exists"], AlreadyExists)
        assert isinstance(results["write_already_exists"], AlreadyExists)

        # Final content reflects the overwrite
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
        from examples.configuration import demo

        results = demo()

        # Secret masking
        assert results["secret_repr"] == "Secret('***')"
        assert results["secret_str"] == "***"
        assert results["secret_reveal"] == "my-secret-key"

        # Auto-wrapping of sensitive keys
        assert results["auto_key_repr"] == "Secret('***')"
        assert results["auto_secret_repr"] == "Secret('***')"
        assert results["bucket_value"] == "my-bucket"  # not wrapped

        # from_dict() produces usable config
        assert results["from_dict_data"] == b"a,b\n1,2\n"
        assert results["from_dict_logs"] == b"[INFO] started\n"

        # Validation catches unknown backend references
        assert isinstance(results["validation_error"], ValueError)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.spec("ERR-002")
    @pytest.mark.spec("ERR-003")
    @pytest.mark.spec("ERR-005")
    def test_demo(self, memory_store):
        from examples.error_handling import demo

        results = demo(memory_store)

        # NotFound with structured attributes
        nf = results["not_found"]
        assert isinstance(nf, NotFound)
        assert nf.path == "nonexistent.txt"
        assert nf.backend is not None

        # AlreadyExists with path attribute
        ae = results["already_exists"]
        assert isinstance(ae, AlreadyExists)
        assert ae.path == "existing.txt"

        # InvalidPath on traversal attempt
        ip = results["invalid_path"]
        assert isinstance(ip, InvalidPath)

        # Base class catches all remote-store errors
        assert len(results["base_class_errors"]) == 2

        # missing_ok succeeded
        assert results["missing_ok_succeeded"] is True


# ---------------------------------------------------------------------------
# Memory backend
# ---------------------------------------------------------------------------


class TestMemoryBackend:
    @pytest.mark.spec("MEM-DS-002")
    def test_demo(self, memory_store):
        from examples.memory_backend import demo

        demo(memory_store)

        # Final state after copy + move
        assert memory_store.exists("hello.txt")
        assert memory_store.read_bytes("hello.txt") == b"Hello from memory!"

        # q1 copied to archive, q2 moved to archive
        assert memory_store.exists("reports/q1.csv")  # original still exists (copy)
        assert not memory_store.exists("reports/q2.csv")  # moved away
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
        from examples.store_child import demo

        demo(memory_store)

        # Path isolation: children wrote under their subpaths
        assert memory_store.exists("reports/q1.csv")
        assert memory_store.exists("reports/q2.csv")
        assert memory_store.exists("archive/2024/summary.txt")

        # Content integrity
        assert memory_store.read_bytes("reports/q1.csv") == b"revenue,100\n"
        assert memory_store.read_bytes("archive/2024/summary.txt") == b"Year-end summary"

        # Chained child equivalence
        deep = memory_store.child("archive").child("2024")
        direct = memory_store.child("archive/2024")
        assert deep == direct

        # Parent survives child close
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
        from examples.batch_operations import demo

        results = demo(memory_store)

        # batch_exists
        assert results["exists"]["a.txt"] is True
        assert results["exists"]["b.txt"] is True
        assert results["exists"]["missing.txt"] is False

        # batch_copy success
        assert results["copy_ok"].all_succeeded is True
        assert results["copy_ok"].total == 2

        # batch_copy partial failure
        assert not results["copy_partial"].all_succeeded
        assert "c.txt" in results["copy_partial"].failed
        assert isinstance(results["copy_partial"].failed["c.txt"], AlreadyExists)

        # batch_delete success
        assert results["delete_ok"].all_succeeded is True

        # batch_delete with missing_ok
        assert results["delete_missing_ok"].all_succeeded is True

        # batch_delete with stop_on_error: first succeeds, second fails, third skipped
        assert "gone.txt" in results["delete_stop_on_error"].failed


# ---------------------------------------------------------------------------
# Glob pattern matching
# ---------------------------------------------------------------------------


class TestGlobPatternMatching:
    @pytest.mark.spec("GLOB-001")
    @pytest.mark.spec("GLOB-009")
    def test_demo(self, memory_store):
        from examples.glob_pattern_matching import demo

        results = demo(memory_store)

        # Tier 1: list_files(pattern=...)
        assert results["tier1_csvs"] == ["report.csv"]
        assert results["tier1_reports"] == ["report.csv", "report.txt"]
        assert results["tier1_md"] == ["docs/guide.md", "docs/readme.md"]
        assert "logs/app.log" in results["tier1_logs_recursive"]
        assert "logs/error.log" in results["tier1_logs_recursive"]
        assert "logs/archive/old.log" in results["tier1_logs_recursive"]
        assert len(results["tier1_logs_recursive"]) == 3

        # Tier 3: glob_files()
        assert len(results["tier3_deep_logs"]) == 3
        assert results["tier3_doc_mds"] == ["docs/guide.md", "docs/readme.md"]
        assert len(results["tier3_everything"]) == 8  # all 8 files

        # Child-scoped glob
        assert len(results["child_tier1"]) == 2  # app.log, error.log (not archive/)
        assert len(results["child_tier3"]) == 3  # all .log files including archive/


# ---------------------------------------------------------------------------
# Transfer operations
# ---------------------------------------------------------------------------


class TestTransferOperations:
    @pytest.mark.spec("XFER-001")
    @pytest.mark.spec("XFER-006")
    @pytest.mark.spec("XFER-011")
    def test_demo(self, two_stores, tmp_path):
        from examples.transfer_operations import demo

        primary, archive = two_stores
        results = demo(primary, archive, str(tmp_path))

        # Upload round-trip
        assert results["uploaded_content"] == b"Hello from local filesystem!"
        assert results["upload_bytes"] == 100_000

        # Download round-trip
        assert results["downloaded_content"] == b"Hello from local filesystem!"
        assert results["download_bytes"] == 100_000

        # Download overwrite guard
        assert isinstance(results["download_overwrite_guard"], FileExistsError)

        # Transfer round-trip
        assert results["transferred_content"] == b"Hello from local filesystem!"
        assert results["transfer_bytes"] == 100_000

        # Final state: both stores have their files
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
        from examples.observe_hooks import demo

        results = demo(memory_store)

        # Per-operation hooks fired
        assert len(results["write_events"]) == 2  # two writes
        assert results["write_events"][0].operation == "write_text"
        assert len(results["read_events"]) == 1  # one read_bytes
        assert results["read_events"][0].operation == "read_bytes"

        # Catch-all hook fired for exists, copy, delete
        assert len(results["any_events"]) == 3
        ops = [e.operation for e in results["any_events"]]
        assert "exists" in ops
        assert "copy" in ops
        assert "delete" in ops

        # Around hook fired
        assert "is_file" in results["around_ops"]

        # Buffered observer collected events
        assert len(results["buffered_events"]) == 3  # 2 writes + 1 exists

        # All events have timing info
        for event in results["write_events"] + results["read_events"] + results["any_events"]:
            assert event.duration_ms >= 0
            assert event.error is None


# ---------------------------------------------------------------------------
# OTel tracing (optional dependency)
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

        from examples.otel_tracing import demo
        from remote_store.ext.otel import otel_observe

        # Set up OTel with in-memory exporters
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

        # Verify spans
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 5  # write, read_bytes, copy, exists, delete
        span_names = {s.name for s in spans}
        assert "store.write" in span_names
        assert "store.read_bytes" in span_names

        # Verify metrics exist
        data = metric_reader.get_metrics_data()
        metric_names = set()
        for rm in data.resource_metrics:
            for sm in rm.scope_metrics:
                for m in sm.metrics:
                    metric_names.add(m.name)
        assert "remote_store.operations" in metric_names

        tracer_provider.shutdown()
        meter_provider.shutdown()


# ---------------------------------------------------------------------------
# PyArrow adapter (optional dependency)
# ---------------------------------------------------------------------------


class TestPyArrowAdapter:
    @pytest.mark.spec("PA-002")
    def test_demo(self, memory_store):
        pytest.importorskip("pyarrow")

        from examples.pyarrow_adapter import demo

        results = demo(memory_store)

        # Parquet round-trip
        assert results["people_rows"] == 3
        assert results["people_data"]["id"] == [1, 2, 3]
        assert results["people_data"]["name"] == ["Alice", "Bob", "Charlie"]

        # File was actually written
        assert results["file_size"] > 0

        # Dataset discovery
        assert results["dataset_rows"] == 15  # 3 partitions * 5 rows
        assert results["dataset_files"] == 3


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    @pytest.mark.spec("RET-001")
    def test_demo(self):
        from examples.retry_policy import demo

        # Smoke test -- demo prints output and exercises validation
        demo()


class TestHealthCheck:
    @pytest.mark.spec("PING-001")
    def test_demo(self, memory_store: Store):
        from examples.health_check import demo

        demo(memory_store)


# ---------------------------------------------------------------------------
# Dagster IO Manager (optional dependency)
# ---------------------------------------------------------------------------


class TestHttpBackend:
    @pytest.mark.spec("HTTP-001")
    def test_demo(self):
        from examples.http_backend import demo
        from remote_store.backends import ReadOnlyHttpBackend

        # Use a memory-backed HTTP-like test: create backend pointed at nothing,
        # just verify the capability check and error handling paths.
        backend = ReadOnlyHttpBackend(base_url="http://127.0.0.1:1/", timeout=0.1)
        store = Store(backend=backend)
        results = demo(store)
        store.close()

        assert results["supports_read"] is True
        assert results["supports_write"] is False
        assert "write" in results["write_error"]


class TestDagsterIOManager:
    @pytest.mark.spec("DAG-002,DAG-003,DAG-005")
    def test_demo(self):
        pytest.importorskip("dagster")

        from examples.dagster_io_manager import demo

        results = demo()

        assert results["pickle_roundtrip"] is True
        assert results["partition_path_exists"] is True
        assert results["json_roundtrip"] is True
