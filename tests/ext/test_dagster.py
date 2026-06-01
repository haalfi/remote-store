"""Tests for remote_store.ext.dagster -- Dagster IO manager and compute log manager."""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest import mock

import pytest
from dagster import AssetKey, InputContext, build_init_resource_context, build_input_context, build_output_context
from dagster._check import CheckError
from dagster._core.storage.compute_log_manager import ComputeIOType
from dagster._core.storage.local_compute_log_manager import IO_TYPE_EXTENSION, LocalComputeLogManager

from remote_store import Capability
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.dagster import (
    ParquetSerializer,
    RemoteStoreComputeLogManager,
    Serializer,
    dagster_io_manager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> Store:
    """Fresh MemoryBackend-backed Store for each test."""
    return Store(backend=MemoryBackend())


# ---------------------------------------------------------------------------
# Serializer roundtrips
# ---------------------------------------------------------------------------


class TestSerializerRoundtrips:
    """DAG-002, DAG-003: Pickle and JSON roundtrips."""

    @pytest.mark.spec("DAG-001")
    @pytest.mark.parametrize(
        "serializer",
        [
            pytest.param("pickle", id="pickle", marks=pytest.mark.spec("DAG-002")),
            pytest.param("json", id="json", marks=pytest.mark.spec("DAG-003")),
        ],
    )
    def test_roundtrip(self, store: Store, serializer: str) -> None:
        mgr = dagster_io_manager(store, serializer=serializer)
        obj = {"key": "value", "numbers": [1, 2, 3]}

        out_ctx = build_output_context(asset_key=AssetKey(["test", serializer]))
        mgr.handle_output(out_ctx, obj)

        in_ctx = build_input_context(
            asset_key=AssetKey(["test", serializer]),
            upstream_output=out_ctx,
        )
        assert mgr.load_input(in_ctx) == obj


class TestParquetSerializer:
    """DAG-004: Parquet roundtrip."""

    @pytest.mark.spec("DAG-004")
    def test_roundtrip_pandas(self, store: Store) -> None:
        """Roundtrip with a pandas DataFrame returns Arrow Table."""
        pa = pytest.importorskip("pyarrow")

        pandas = pytest.importorskip("pandas")
        mgr = dagster_io_manager(store, serializer="parquet")

        df = pandas.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})

        out_ctx = build_output_context(asset_key=AssetKey(["test", "parquet"]))
        mgr.handle_output(out_ctx, df)

        in_ctx = build_input_context(
            asset_key=AssetKey(["test", "parquet"]),
            upstream_output=out_ctx,
        )
        result = mgr.load_input(in_ctx)
        assert isinstance(result, pa.Table)
        pandas.testing.assert_frame_equal(result.to_pandas(), df)
        assert result.num_rows == 3

    @pytest.mark.spec("DAG-004")
    def test_roundtrip_arrow(self, store: Store) -> None:
        """Roundtrip with a PyArrow Table returns Arrow Table."""
        pa = pytest.importorskip("pyarrow")

        mgr = dagster_io_manager(store, serializer="parquet")

        table = pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"]})

        out_ctx = build_output_context(asset_key=AssetKey(["test", "parquet_arrow"]))
        mgr.handle_output(out_ctx, table)

        in_ctx = build_input_context(
            asset_key=AssetKey(["test", "parquet_arrow"]),
            upstream_output=out_ctx,
        )
        result = mgr.load_input(in_ctx)
        assert isinstance(result, pa.Table)
        assert result.equals(table)

    @pytest.mark.spec("DAG-004")
    def test_serialize_arrow_table(self) -> None:
        """Serialize a PyArrow Table directly."""
        pa = pytest.importorskip("pyarrow")
        pq = pytest.importorskip("pyarrow.parquet")

        serializer = ParquetSerializer()
        table = pa.table([pa.array([1, 2, 3]), pa.array(["x", "y", "z"])], names=["a", "b"])

        data = serializer.serialize(table)
        assert len(data) > 0

        # Verify it's valid parquet by reading back as Arrow
        import io

        roundtrip = pq.read_table(io.BytesIO(data))
        assert roundtrip.equals(table)

    @pytest.mark.spec("DAG-004")
    def test_serialize_polars_like(self) -> None:
        """Serialize an object with to_arrow() (Polars-like)."""
        pa = pytest.importorskip("pyarrow")
        pq = pytest.importorskip("pyarrow.parquet")

        table = pa.table([pa.array([10, 20])], names=["val"])

        # Mock a Polars-like DataFrame with to_arrow()
        pl = pytest.importorskip("polars")

        polars_like = mock.MagicMock(spec=pl.DataFrame)
        polars_like.to_arrow.return_value = table
        del polars_like.dtypes  # Ensure it doesn't match the pandas branch

        serializer = ParquetSerializer()
        data = serializer.serialize(polars_like)
        polars_like.to_arrow.assert_called_once()

        import io

        roundtrip = pq.read_table(io.BytesIO(data))
        assert roundtrip.equals(table)

    @pytest.mark.spec("DAG-004")
    def test_serialize_unsupported_type(self) -> None:
        """Serializing an unsupported type raises TypeError."""
        pytest.importorskip("pyarrow")
        serializer = ParquetSerializer()
        with pytest.raises(TypeError, match="ParquetSerializer expects a DataFrame, got str"):
            serializer.serialize("not a dataframe")

    @pytest.mark.spec("DAG-004")
    def test_deserialize_returns_arrow_table(self) -> None:
        """Deserialize returns a PyArrow Table (not pandas)."""
        import io

        pa = pytest.importorskip("pyarrow")
        pq = pytest.importorskip("pyarrow.parquet")

        table = pa.table([pa.array([1, 2, 3])], names=["col"])
        buf = io.BytesIO()
        pq.write_table(table, buf)
        parquet_bytes = buf.getvalue()

        serializer = ParquetSerializer()
        result = serializer.deserialize(parquet_bytes)
        assert isinstance(result, pa.Table)
        assert result.equals(table)


# ---------------------------------------------------------------------------
# Path generation
# ---------------------------------------------------------------------------


class TestPathGeneration:
    """DAG-005, DAG-006: Asset path derivation."""

    @pytest.mark.spec("DAG-005")
    def test_partitioned_asset_path(self, store: Store) -> None:
        """Partitioned asset includes partition key in path."""
        mgr = dagster_io_manager(store, serializer="pickle")
        obj = {"data": True}

        out_ctx = build_output_context(
            asset_key=AssetKey(["foo", "bar"]),
            partition_key="2026-01",
        )
        mgr.handle_output(out_ctx, obj)

        # Verify the file was written at the expected path
        assert store.exists("foo/bar/2026-01.pkl")

        # Roundtrip through load_input with partitioned context
        in_ctx = build_input_context(
            asset_key=AssetKey(["foo", "bar"]),
            partition_key="2026-01",
            upstream_output=out_ctx,
        )
        assert mgr.load_input(in_ctx) == obj

    @pytest.mark.spec("DAG-005")
    def test_single_segment_asset_key(self, store: Store) -> None:
        """Single-segment asset key maps to flat path."""
        mgr = dagster_io_manager(store, serializer="json")
        obj = {"summary": True}

        out_ctx = build_output_context(asset_key=AssetKey(["report"]))
        mgr.handle_output(out_ctx, obj)

        assert store.exists("report.json")

    @pytest.mark.spec("DAG-006")
    def test_multi_segment_asset_key(self, store: Store) -> None:
        """Multi-segment asset key maps to nested path."""
        mgr = dagster_io_manager(store, serializer="json")
        obj = {"hello": "world"}

        out_ctx = build_output_context(
            asset_key=AssetKey(["ns", "group", "table"]),
        )
        mgr.handle_output(out_ctx, obj)

        assert store.exists("ns/group/table.json")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """DAG-008, DAG-010: Error scenarios."""

    @pytest.mark.spec("DAG-008")
    def test_missing_file_raises_not_found(self, store: Store) -> None:
        """Loading a non-existent asset raises NotFound."""
        from remote_store._errors import NotFound

        mgr = dagster_io_manager(store, serializer="pickle")

        out_ctx = build_output_context(asset_key=AssetKey(["missing", "asset"]))
        in_ctx = build_input_context(
            asset_key=AssetKey(["missing", "asset"]),
            upstream_output=out_ctx,
        )
        with pytest.raises(NotFound, match="missing/asset"):
            mgr.load_input(in_ctx)

    @pytest.mark.spec("DAG-010")
    def test_missing_pyarrow_error(self) -> None:
        """ParquetSerializer without PyArrow gives helpful error."""
        with (
            mock.patch.dict("sys.modules", {"pyarrow": None}),
            pytest.raises(ModuleNotFoundError, match="pip install 'remote-store\\[dagster,arrow\\]'"),
        ):
            ParquetSerializer()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    """DAG-007: handle_output adds metadata to context."""

    @pytest.mark.spec("DAG-007")
    def test_output_metadata(self, store: Store) -> None:
        mgr = dagster_io_manager(store, serializer="pickle")
        obj = {"key": "value"}

        out_ctx = build_output_context(asset_key=AssetKey(["meta", "test"]))
        mgr.handle_output(out_ctx, obj)

        metadata = out_ctx.get_logged_metadata()
        assert "path" in metadata
        assert "size" in metadata
        assert metadata["path"].text == "meta/test.pkl"
        assert metadata["size"].value > 0

    @pytest.mark.spec("DAG-007")
    def test_none_is_written(self, store: Store) -> None:
        """None is serialized and written (Dagster convention)."""
        mgr = dagster_io_manager(store, serializer="pickle")

        out_ctx = build_output_context(asset_key=AssetKey(["none", "asset"]))
        mgr.handle_output(out_ctx, None)

        assert store.exists("none/asset.pkl")

        in_ctx = build_input_context(
            asset_key=AssetKey(["none", "asset"]),
            upstream_output=out_ctx,
        )
        assert mgr.load_input(in_ctx) is None


# ---------------------------------------------------------------------------
# Custom serializer
# ---------------------------------------------------------------------------


class _ReverseSerializer:
    """Test serializer that reverses bytes."""

    extension: str = ".rev"

    def serialize(self, obj: Any) -> bytes:
        return bytes(reversed(obj.encode("utf-8")))

    def deserialize(self, data: bytes) -> Any:
        return bytes(reversed(data)).decode("utf-8")


class TestCustomSerializer:
    """DAG-009: Custom serializer protocol."""

    @pytest.mark.spec("DAG-009")
    def test_custom_serializer(self, store: Store) -> None:
        custom = _ReverseSerializer()
        assert isinstance(custom, Serializer)

        mgr = dagster_io_manager(store, serializer=custom)
        obj = "hello world"

        out_ctx = build_output_context(asset_key=AssetKey(["custom", "test"]))
        mgr.handle_output(out_ctx, obj)

        assert store.exists("custom/test.rev")

        in_ctx = build_input_context(
            asset_key=AssetKey(["custom", "test"]),
            upstream_output=out_ctx,
        )
        assert mgr.load_input(in_ctx) == obj

    @pytest.mark.spec("DAG-011")
    def test_unknown_serializer_raises(self, store: Store) -> None:
        """Unknown serializer string raises ValueError."""
        with pytest.raises(ValueError, match="Unknown serializer 'nope'"):
            dagster_io_manager(store, serializer="nope")


# ---------------------------------------------------------------------------
# v2: DagsterStoreResource
# ---------------------------------------------------------------------------


class TestDagsterStoreResource:
    """DAG-012..014: DagsterStoreResource lifecycle and config."""

    @pytest.mark.spec("DAG-012")
    def test_get_store_builds_working_store(self) -> None:
        """Resource builds a functional Store from config."""
        from remote_store.ext.dagster import DagsterStoreResource

        resource = DagsterStoreResource(backend_type="memory", backend_options={})
        resource.setup_for_execution(context=build_init_resource_context())
        store = resource.get_store()

        store.write("test.txt", b"hello", overwrite=True)
        assert store.read_bytes("test.txt") == b"hello"

        resource.teardown_after_execution(context=build_init_resource_context())

    @pytest.mark.spec("DAG-013")
    def test_teardown_closes_store(self) -> None:
        """teardown_after_execution closes the Store."""
        from remote_store.ext.dagster import DagsterStoreResource

        resource = DagsterStoreResource(backend_type="memory", backend_options={})
        resource.setup_for_execution(context=build_init_resource_context())
        store = resource.get_store()
        assert store is not None

        resource.teardown_after_execution(context=build_init_resource_context())
        # After teardown, get_store should raise because the store is gone
        with pytest.raises(RuntimeError, match="setup_for_execution"):
            resource.get_store()

    @pytest.mark.spec("DAG-013")
    def test_teardown_before_setup_is_safe(self) -> None:
        """teardown_after_execution before setup_for_execution does not raise."""
        from remote_store.ext.dagster import DagsterStoreResource

        resource = DagsterStoreResource(backend_type="memory", backend_options={})
        # Must not raise; get_store should still report uninitialized after teardown
        resource.teardown_after_execution(context=build_init_resource_context())
        with pytest.raises(RuntimeError, match="setup_for_execution"):
            resource.get_store()

    @pytest.mark.spec("DAG-014")
    def test_unknown_backend_type_raises(self) -> None:
        """Unknown backend_type raises ValueError that includes the type name."""
        from remote_store.ext.dagster import DagsterStoreResource

        resource = DagsterStoreResource(backend_type="nonexistent", backend_options={})
        with pytest.raises(ValueError, match=r"nonexistent.*Registered types"):
            resource.setup_for_execution(context=build_init_resource_context())


# ---------------------------------------------------------------------------
# v2: RemoteStoreIOManager
# ---------------------------------------------------------------------------


class TestRemoteStoreIOManager:
    """DAG-015..016: RemoteStoreIOManager factory."""

    @pytest.mark.spec("DAG-015")
    def test_creates_working_io_manager(self) -> None:
        """Factory creates a working IO manager that round-trips objects."""
        from remote_store.ext.dagster import RemoteStoreIOManager

        factory = RemoteStoreIOManager(backend_type="memory", serializer="pickle")
        factory.setup_for_execution(context=build_init_resource_context())
        io_mgr = factory.create_io_manager(context=build_init_resource_context())

        obj = {"key": "value"}
        out_ctx = build_output_context(asset_key=AssetKey(["v2", "test"]))
        io_mgr.handle_output(out_ctx, obj)

        in_ctx = build_input_context(
            asset_key=AssetKey(["v2", "test"]),
            upstream_output=out_ctx,
        )
        assert io_mgr.load_input(in_ctx) == obj

        factory.teardown_after_execution(context=build_init_resource_context())

    @pytest.mark.spec("DAG-016")
    def test_json_serializer_through_factory(self) -> None:
        """JSON serializer round-trips a list through the factory."""
        from remote_store.ext.dagster import RemoteStoreIOManager

        factory = RemoteStoreIOManager(backend_type="memory", serializer="json")
        factory.setup_for_execution(context=build_init_resource_context())
        io_mgr = factory.create_io_manager(context=build_init_resource_context())

        obj = [1, 2, 3]
        out_ctx = build_output_context(asset_key=AssetKey(["v2", "json"]))
        io_mgr.handle_output(out_ctx, obj)

        in_ctx = build_input_context(
            asset_key=AssetKey(["v2", "json"]),
            upstream_output=out_ctx,
        )
        assert io_mgr.load_input(in_ctx) == obj

        factory.teardown_after_execution(context=build_init_resource_context())

    @pytest.mark.spec("DAG-015")
    def test_invalid_serializer_raises(self) -> None:
        """Invalid serializer string on factory raises ValueError."""
        from remote_store.ext.dagster import RemoteStoreIOManager

        factory = RemoteStoreIOManager(backend_type="memory", serializer="nope")
        factory.setup_for_execution(context=build_init_resource_context())
        with pytest.raises(ValueError, match="Unknown serializer 'nope'"):
            factory.create_io_manager(context=build_init_resource_context())

        factory.teardown_after_execution(context=build_init_resource_context())

    @pytest.mark.spec("DAG-015")
    def test_create_io_manager_before_setup_raises(self) -> None:
        """create_io_manager before setup_for_execution raises RuntimeError."""
        from remote_store.ext.dagster import RemoteStoreIOManager

        factory = RemoteStoreIOManager(backend_type="memory")
        with pytest.raises(RuntimeError, match="setup_for_execution"):
            factory.create_io_manager(context=build_init_resource_context())


# ---------------------------------------------------------------------------
# v2: Dataset IO Manager
# ---------------------------------------------------------------------------


class TestDatasetIOManager:
    """DAG-017..019: Dataset IO manager via ParquetDatasetStore."""

    @pytest.mark.spec("DAG-017")
    def test_dataset_roundtrip(self) -> None:
        """Dataset mode writes and reads an Arrow Table via ParquetDatasetStore."""
        pa = pytest.importorskip("pyarrow")

        from remote_store.ext.dagster import dagster_dataset_io_manager

        store = Store(backend=MemoryBackend())
        mgr = dagster_dataset_io_manager(store)

        table = pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"]})

        out_ctx = build_output_context(asset_key=AssetKey(["dataset", "test"]))
        mgr.handle_output(out_ctx, table)

        in_ctx = build_input_context(
            asset_key=AssetKey(["dataset", "test"]),
            upstream_output=out_ctx,
        )
        result = mgr.load_input(in_ctx)
        assert result.equals(table)

    @pytest.mark.spec("DAG-018")
    def test_dataset_partitioned(self) -> None:
        """Dataset mode incorporates the partition key into the dataset path."""
        pa = pytest.importorskip("pyarrow")

        from remote_store.ext.dagster import dagster_dataset_io_manager

        store = Store(backend=MemoryBackend())
        mgr = dagster_dataset_io_manager(store)

        table = pa.table({"val": [10, 20]})

        out_ctx = build_output_context(
            asset_key=AssetKey(["data", "monthly"]),
            partition_key="2026-01",
        )
        mgr.handle_output(out_ctx, table)

        in_ctx = build_input_context(
            asset_key=AssetKey(["data", "monthly"]),
            partition_key="2026-01",
            upstream_output=out_ctx,
        )
        result = mgr.load_input(in_ctx)
        assert result.equals(table)

    @pytest.mark.spec("DAG-019")
    def test_dataset_via_remote_store_io_manager(self) -> None:
        """RemoteStoreIOManager with serializer='parquet-dataset' uses ParquetDatasetStore."""
        pa = pytest.importorskip("pyarrow")

        from remote_store.ext.dagster import RemoteStoreIOManager

        factory = RemoteStoreIOManager(backend_type="memory", serializer="parquet-dataset")
        factory.setup_for_execution(context=build_init_resource_context())
        io_mgr = factory.create_io_manager(context=build_init_resource_context())

        table = pa.table({"x": [1, 2], "y": ["a", "b"]})

        out_ctx = build_output_context(asset_key=AssetKey(["v2", "dataset"]))
        io_mgr.handle_output(out_ctx, table)

        in_ctx = build_input_context(
            asset_key=AssetKey(["v2", "dataset"]),
            upstream_output=out_ctx,
        )
        result = io_mgr.load_input(in_ctx)
        assert result.equals(table)

        factory.teardown_after_execution(context=build_init_resource_context())

    @pytest.mark.spec("DAG-017")
    def test_dataset_unsupported_type_raises(self) -> None:
        """Dataset mode with an unsupported type raises TypeError."""
        pytest.importorskip("pyarrow")

        from remote_store.ext.dagster import dagster_dataset_io_manager

        store = Store(backend=MemoryBackend())
        mgr = dagster_dataset_io_manager(store)
        out_ctx = build_output_context(asset_key=AssetKey(["bad", "type"]))
        with pytest.raises(TypeError, match="Dataset mode expects a DataFrame"):
            mgr.handle_output(out_ctx, "not a dataframe")

    @pytest.mark.spec("DAG-019")
    def test_dataset_missing_pyarrow(self) -> None:
        """Dataset mode without the parquet extension gives a helpful error."""
        from remote_store.ext.dagster import dagster_dataset_io_manager

        store = Store(backend=MemoryBackend())
        with (
            mock.patch.dict("sys.modules", {"remote_store.ext.parquet": None}),
            pytest.raises(ModuleNotFoundError, match="pip install 'remote-store\\[dagster,arrow\\]'"),
        ):
            dagster_dataset_io_manager(store)


# ---------------------------------------------------------------------------
# Multi-partition loading (DAG-020)
# ---------------------------------------------------------------------------


def _multi_partition_input_context(
    asset_key: AssetKey,
    partition_keys: list[str],
) -> InputContext:
    """Build a mock InputContext with multiple partition keys.

    Dagster's ``build_input_context`` only accepts a single ``partition_key``.
    For multi-partition (time-window) scenarios we mock at our boundary
    (the context object passed to ``load_input``).
    """
    ctx = mock.MagicMock(spec=InputContext)
    ctx.asset_key = asset_key
    ctx.has_asset_partitions = True
    ctx.asset_partition_keys = partition_keys
    return ctx


class TestMultiPartitionLoading:
    """DAG-020: load_input with multiple partition keys."""

    @pytest.mark.spec("DAG-020")
    def test_multi_partition_returns_dict(self, store: Store) -> None:
        """Multiple partition keys return dict[str, Any]."""
        mgr = dagster_io_manager(store, serializer="json")

        # Write three partitions individually
        partitions = {"2026-01": {"month": 1}, "2026-02": {"month": 2}, "2026-03": {"month": 3}}
        for pk, obj in partitions.items():
            out_ctx = build_output_context(
                asset_key=AssetKey(["sales", "monthly"]),
                partition_key=pk,
            )
            mgr.handle_output(out_ctx, obj)

        # Load all three at once
        in_ctx = _multi_partition_input_context(
            asset_key=AssetKey(["sales", "monthly"]),
            partition_keys=["2026-01", "2026-02", "2026-03"],
        )
        result = mgr.load_input(in_ctx)

        assert result == {
            "2026-01": {"month": 1},
            "2026-02": {"month": 2},
            "2026-03": {"month": 3},
        }

    @pytest.mark.spec("DAG-020")
    def test_multi_partition_pickle(self, store: Store) -> None:
        """Multi-partition loading works with pickle serializer."""
        mgr = dagster_io_manager(store, serializer="pickle")

        for pk in ("a", "b"):
            out_ctx = build_output_context(
                asset_key=AssetKey(["data"]),
                partition_key=pk,
            )
            mgr.handle_output(out_ctx, {"pk": pk})

        in_ctx = _multi_partition_input_context(
            asset_key=AssetKey(["data"]),
            partition_keys=["a", "b"],
        )
        result = mgr.load_input(in_ctx)
        assert result == {"a": {"pk": "a"}, "b": {"pk": "b"}}

    @pytest.mark.spec("DAG-020")
    def test_single_partition_unchanged(self, store: Store) -> None:
        """Single partition still returns a single object (not a dict)."""
        mgr = dagster_io_manager(store, serializer="json")
        obj = {"val": 42}

        out_ctx = build_output_context(
            asset_key=AssetKey(["item"]),
            partition_key="only",
        )
        mgr.handle_output(out_ctx, obj)

        in_ctx = build_input_context(
            asset_key=AssetKey(["item"]),
            partition_key="only",
            upstream_output=out_ctx,
        )
        result = mgr.load_input(in_ctx)
        assert result == obj

    @pytest.mark.spec("DAG-020")
    def test_multi_partition_missing_raises(self, store: Store) -> None:
        """Missing partition raises NotFound immediately."""
        from remote_store._errors import NotFound

        mgr = dagster_io_manager(store, serializer="pickle")

        # Write only one of two partitions
        out_ctx = build_output_context(
            asset_key=AssetKey(["sparse"]),
            partition_key="exists",
        )
        mgr.handle_output(out_ctx, "ok")

        in_ctx = _multi_partition_input_context(
            asset_key=AssetKey(["sparse"]),
            partition_keys=["exists", "missing"],
        )
        with pytest.raises(NotFound, match="missing"):
            mgr.load_input(in_ctx)

    @pytest.mark.spec("DAG-020")
    def test_multi_partition_missing_first_raises(self, store: Store) -> None:
        """Fail-fast: missing *first* partition raises before reading the second."""
        from remote_store._errors import NotFound

        mgr = dagster_io_manager(store, serializer="pickle")

        out_ctx = build_output_context(
            asset_key=AssetKey(["sparse"]),
            partition_key="exists",
        )
        mgr.handle_output(out_ctx, "ok")

        # "missing" is first so it's encountered before "exists".  The code
        # iterates asset_partition_keys in list order; the mock preserves that
        # order.  If Dagster ever re-sorts partition keys internally this
        # assertion would need updating, but the mock gives us a stable contract.
        in_ctx = _multi_partition_input_context(
            asset_key=AssetKey(["sparse"]),
            partition_keys=["missing", "exists"],
        )
        with mock.patch.object(store, "read_bytes", wraps=store.read_bytes) as spy:
            with pytest.raises(NotFound, match="missing"):
                mgr.load_input(in_ctx)
            # Only one read attempted — the missing key; second key never read
            spy.assert_called_once()

    @pytest.mark.spec("DAG-020")
    def test_multi_partition_dataset(self) -> None:
        """Dataset IO manager returns dict for multiple partition keys."""
        pa = pytest.importorskip("pyarrow")

        from remote_store.ext.dagster import dagster_dataset_io_manager

        store = Store(backend=MemoryBackend())
        mgr = dagster_dataset_io_manager(store)

        tables = {
            "2026-01": pa.table({"val": [1, 2]}),
            "2026-02": pa.table({"val": [3, 4]}),
        }
        for pk, table in tables.items():
            out_ctx = build_output_context(
                asset_key=AssetKey(["ds", "monthly"]),
                partition_key=pk,
            )
            mgr.handle_output(out_ctx, table)

        in_ctx = _multi_partition_input_context(
            asset_key=AssetKey(["ds", "monthly"]),
            partition_keys=["2026-01", "2026-02"],
        )
        result = mgr.load_input(in_ctx)
        assert set(result.keys()) == {"2026-01", "2026-02"}
        assert result["2026-01"].equals(tables["2026-01"])
        assert result["2026-02"].equals(tables["2026-02"])

    @pytest.mark.spec("DAG-020")
    def test_multi_partition_dataset_missing_raises(self) -> None:
        """Dataset IO manager raises DatasetIncomplete for missing partition."""
        pa = pytest.importorskip("pyarrow")

        from remote_store.ext.dagster import dagster_dataset_io_manager
        from remote_store.ext.parquet import DatasetIncomplete

        store = Store(backend=MemoryBackend())
        mgr = dagster_dataset_io_manager(store)

        # Write only one of two partitions
        table = pa.table({"val": [1, 2]})
        out_ctx = build_output_context(
            asset_key=AssetKey(["ds", "sparse"]),
            partition_key="exists",
        )
        mgr.handle_output(out_ctx, table)

        in_ctx = _multi_partition_input_context(
            asset_key=AssetKey(["ds", "sparse"]),
            partition_keys=["exists", "missing"],
        )
        with pytest.raises(DatasetIncomplete, match="missing"):
            mgr.load_input(in_ctx)


# ---------------------------------------------------------------------------
# v3: RemoteStoreComputeLogManager (DAG-021 .. DAG-033)
# ---------------------------------------------------------------------------

_OUT = ComputeIOType.STDOUT
_ERR = ComputeIOType.STDERR


@pytest.fixture
def clm(tmp_path):
    """A RemoteStoreComputeLogManager backed by a fresh in-memory Store."""
    mgr = RemoteStoreComputeLogManager(
        backend_type="memory",
        local_dir=str(tmp_path / "local"),
    )
    yield mgr
    mgr.dispose()


def _seed_local_capture(mgr, log_key, io_type, content):
    """Write a local capture file the way Dagster's LocalComputeLogManager would."""
    path = mgr.local_manager.get_captured_local_path(log_key, IO_TYPE_EXTENSION[io_type])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def _upload(mgr, log_key, io_type, content, *, partial=False):
    """Seed a local capture file, then drive the cloud-upload hook."""
    path = _seed_local_capture(mgr, log_key, io_type, content)
    with open(path, "rb") as fh:
        mgr._upload_file_obj(fh, log_key, io_type, partial)


def _read_cloud(mgr, log_key, io_type, *, partial=False):
    """Read uploaded content back through the cloud-download hook."""
    mgr.download_from_cloud_storage(log_key, io_type, partial)
    local_path = mgr.local_manager.get_captured_local_path(log_key, IO_TYPE_EXTENSION[io_type], partial=partial)
    with open(local_path, "rb") as fh:
        return fh.read()


class TestComputeLogManagerConfig:
    """DAG-021, DAG-022, DAG-023: ConfigurableClass plumbing, construction, properties."""

    pytestmark = pytest.mark.os_sensitive

    @pytest.mark.spec("DAG-021")
    def test_config_type_fields(self) -> None:
        """config_type() exposes exactly the documented config fields."""
        cfg = RemoteStoreComputeLogManager.config_type()
        assert set(cfg.keys()) == {
            "backend_type",
            "backend_options",
            "root_path",
            "local_dir",
            "prefix",
            "skip_empty_files",
            "upload_interval",
        }

    @pytest.mark.spec("DAG-021")
    def test_from_config_value_builds_instance(self, tmp_path) -> None:
        """from_config_value() constructs a working manager from a config dict."""
        mgr = RemoteStoreComputeLogManager.from_config_value(
            None,
            {"backend_type": "memory", "local_dir": str(tmp_path / "local")},
        )
        try:
            assert isinstance(mgr, RemoteStoreComputeLogManager)
            _upload(mgr, ["run", "step"], _OUT, b"ok")
            assert mgr.cloud_storage_has_logs(["run", "step"], _OUT)
        finally:
            mgr.dispose()

    @pytest.mark.spec("DAG-021")
    def test_inst_data_default_none(self, clm) -> None:
        """inst_data is None when the manager is constructed directly."""
        assert clm.inst_data is None

    @pytest.mark.spec("DAG-021")
    def test_inst_data_roundtrip(self, tmp_path) -> None:
        """inst_data returns the ConfigurableClassData passed to the constructor."""
        from dagster._serdes import ConfigurableClassData

        data = ConfigurableClassData("remote_store.ext.dagster", "RemoteStoreComputeLogManager", "{}")
        mgr = RemoteStoreComputeLogManager(backend_type="memory", local_dir=str(tmp_path / "local"), inst_data=data)
        try:
            assert mgr.inst_data is data
        finally:
            mgr.dispose()

    @pytest.mark.spec("DAG-022")
    def test_unknown_backend_type_raises(self, tmp_path) -> None:
        """An unregistered backend_type raises ValueError naming the type."""
        with pytest.raises(ValueError, match="nonexistent"):
            RemoteStoreComputeLogManager(backend_type="nonexistent", local_dir=str(tmp_path / "local"))

    @pytest.mark.spec("DAG-022")
    def test_missing_capability_raises_and_closes_store(self, tmp_path) -> None:
        """A backend missing a required capability raises ValueError and the Store is closed."""
        fake_store = mock.MagicMock(spec=Store)
        fake_store.supports.side_effect = lambda cap: cap is not Capability.LIST

        with (
            mock.patch("remote_store.ext.dagster._build_store", return_value=fake_store),
            pytest.raises(ValueError, match="LIST"),
        ):
            RemoteStoreComputeLogManager(backend_type="memory", local_dir=str(tmp_path / "local"))
        fake_store.close.assert_called_once()

    @pytest.mark.spec("DAG-023")
    def test_local_manager_rooted_at_local_dir(self, tmp_path) -> None:
        """local_manager is a LocalComputeLogManager staging under the configured local_dir."""
        local_dir = tmp_path / "local"
        mgr = RemoteStoreComputeLogManager(backend_type="memory", local_dir=str(local_dir))
        try:
            assert isinstance(mgr.local_manager, LocalComputeLogManager)
            captured = mgr.local_manager.get_captured_local_path(["run", "step"], "out")
            assert captured.startswith(str(local_dir))
        finally:
            mgr.dispose()

    @pytest.mark.spec("DAG-023")
    def test_upload_interval_default_none(self, clm) -> None:
        """upload_interval is None by default — partial-upload polling disabled."""
        assert clm.upload_interval is None

    @pytest.mark.spec("DAG-023")
    def test_upload_interval_configured(self, tmp_path) -> None:
        """A configured upload_interval is returned; zero collapses to None."""
        mgr = RemoteStoreComputeLogManager(backend_type="memory", local_dir=str(tmp_path / "a"), upload_interval=30)
        zero = RemoteStoreComputeLogManager(backend_type="memory", local_dir=str(tmp_path / "b"), upload_interval=0)
        try:
            assert mgr.upload_interval == 30
            assert zero.upload_interval is None
        finally:
            mgr.dispose()
            zero.dispose()


class TestComputeLogManagerPaths:
    """DAG-024: remote path scheme."""

    pytestmark = pytest.mark.os_sensitive

    @pytest.mark.spec("DAG-024")
    def test_path_scheme_nested_log_key(self, clm) -> None:
        """A multi-segment log key maps to {prefix}/storage/<namespace>/<base>.<ext>."""
        log_key = ["run1", "compute_logs", "step_a"]
        _upload(clm, log_key, _ERR, b"e")  # capture is complete once the store has stderr
        assert clm.display_path_for_type(log_key, _OUT) == "dagster/storage/run1/compute_logs/step_a.out"
        assert clm.display_path_for_type(log_key, _ERR) == "dagster/storage/run1/compute_logs/step_a.err"

    @pytest.mark.spec("DAG-024")
    def test_path_scheme_single_segment_log_key(self, clm) -> None:
        """A single-segment log key maps directly under {prefix}/storage."""
        log_key = ["report"]
        _upload(clm, log_key, _ERR, b"e")
        assert clm.display_path_for_type(log_key, _OUT) == "dagster/storage/report.out"

    @pytest.mark.spec("DAG-024")
    def test_partial_and_final_paths_are_distinct(self, clm) -> None:
        """The .partial suffix gives partial uploads a path of their own."""
        log_key = ["run1", "compute_logs", "step_a"]
        _upload(clm, log_key, _OUT, b"streaming", partial=True)
        assert clm.cloud_storage_has_logs(log_key, _OUT, partial=True)
        assert not clm.cloud_storage_has_logs(log_key, _OUT, partial=False)

    @pytest.mark.spec("DAG-024")
    def test_custom_prefix(self, tmp_path) -> None:
        """A multi-segment prefix is honoured verbatim."""
        mgr = RemoteStoreComputeLogManager(backend_type="memory", local_dir=str(tmp_path / "local"), prefix="logs/dag")
        try:
            log_key = ["run1", "step"]
            _upload(mgr, log_key, _ERR, b"e")
            assert mgr.display_path_for_type(log_key, _OUT) == "logs/dag/storage/run1/step.out"
        finally:
            mgr.dispose()

    @pytest.mark.spec("DAG-024")
    def test_empty_prefix_drops_segment(self, tmp_path) -> None:
        """An empty prefix produces no leading slash and no empty segment."""
        mgr = RemoteStoreComputeLogManager(backend_type="memory", local_dir=str(tmp_path / "local"), prefix="")
        try:
            log_key = ["run1", "step"]
            _upload(mgr, log_key, _ERR, b"e")
            path = mgr.display_path_for_type(log_key, _OUT)
            assert path == "storage/run1/step.out"
            assert not path.startswith("/")
        finally:
            mgr.dispose()

    @pytest.mark.spec("DAG-024")
    def test_root_path_is_namespace_prefix_not_embedded(self, tmp_path) -> None:
        """The Store's root_path is an outer namespace prefix, not woven into the derivation."""
        mgr = RemoteStoreComputeLogManager(backend_type="memory", local_dir=str(tmp_path / "local"), root_path="ns")
        try:
            log_key = ["run1", "step"]
            _upload(mgr, log_key, _ERR, b"e")
            # root_path is applied once by the Store as an outer prefix; the
            # compute-log derivation (dagster/storage/...) is identical to the
            # root_path="" case in test_path_scheme_* above.
            assert mgr.display_path_for_type(log_key, _OUT) == "ns/dagster/storage/run1/step.out"
        finally:
            mgr.dispose()


class TestComputeLogManagerUploadDownload:
    """DAG-025, DAG-026, DAG-027, DAG-028: upload, download, existence, UI metadata."""

    pytestmark = pytest.mark.os_sensitive

    @pytest.mark.spec("DAG-025")
    def test_upload_writes_content_to_store(self, clm) -> None:
        """_upload_file_obj persists the captured bytes to the Store."""
        log_key = ["run1", "compute_logs", "step_a"]
        _upload(clm, log_key, _OUT, b"hello stdout")
        assert clm.cloud_storage_has_logs(log_key, _OUT)
        assert _read_cloud(clm, log_key, _OUT) == b"hello stdout"

    @pytest.mark.spec("DAG-025")
    def test_upload_skips_empty_when_configured(self, tmp_path) -> None:
        """skip_empty_files=True suppresses upload of a zero-byte log."""
        mgr = RemoteStoreComputeLogManager(
            backend_type="memory",
            local_dir=str(tmp_path / "local"),
            skip_empty_files=True,
        )
        try:
            log_key = ["run1", "step"]
            _upload(mgr, log_key, _OUT, b"")
            assert not mgr.cloud_storage_has_logs(log_key, _OUT)
        finally:
            mgr.dispose()

    @pytest.mark.spec("DAG-025")
    def test_upload_skips_empty_partial(self, clm) -> None:
        """A zero-byte partial upload is skipped even with skip_empty_files off."""
        log_key = ["run1", "step"]
        _upload(clm, log_key, _OUT, b"", partial=True)
        assert not clm.cloud_storage_has_logs(log_key, _OUT, partial=True)

    @pytest.mark.spec("DAG-025")
    def test_upload_empty_final_is_kept(self, clm) -> None:
        """A zero-byte final upload is kept when skip_empty_files is off (the default)."""
        log_key = ["run1", "step"]
        _upload(clm, log_key, _OUT, b"")
        assert clm.cloud_storage_has_logs(log_key, _OUT)

    @pytest.mark.spec("DAG-026")
    def test_download_streams_store_to_local(self, clm) -> None:
        """download_from_cloud_storage fetches a Store object back to the local stage."""
        log_key = ["run1", "compute_logs", "step_a"]
        _upload(clm, log_key, _OUT, b"captured output")
        # Drop the local capture file so the read must come from the Store.
        local_path = clm.local_manager.get_captured_local_path(log_key, IO_TYPE_EXTENSION[_OUT])
        os.remove(local_path)
        clm.download_from_cloud_storage(log_key, _OUT)
        with open(local_path, "rb") as fh:
            assert fh.read() == b"captured output"

    @pytest.mark.spec("DAG-027")
    def test_cloud_storage_has_logs(self, clm) -> None:
        """cloud_storage_has_logs reports presence per log key and io_type."""
        log_key = ["run1", "step"]
        assert not clm.cloud_storage_has_logs(log_key, _OUT)
        _upload(clm, log_key, _OUT, b"x")
        assert clm.cloud_storage_has_logs(log_key, _OUT)
        assert not clm.cloud_storage_has_logs(log_key, _ERR)

    @pytest.mark.spec("DAG-028")
    def test_download_url_is_none(self, clm) -> None:
        """download_url_for_type returns None — v1 has no signed-URL primitive."""
        log_key = ["run1", "step"]
        _upload(clm, log_key, _OUT, b"x")
        assert clm.download_url_for_type(log_key, _OUT) is None

    @pytest.mark.spec("DAG-028")
    def test_display_path_gated_on_capture_completeness(self, clm) -> None:
        """display_path_for_type is None until capture completes, then a real location."""
        log_key = ["run1", "compute_logs", "step_a"]
        assert clm.display_path_for_type(log_key, _OUT) is None
        _upload(clm, log_key, _ERR, b"e")
        assert clm.display_path_for_type(log_key, _OUT) is not None


class TestComputeLogManagerDeleteAndListing:
    """DAG-029, DAG-031: delete_logs and get_log_keys_for_log_key_prefix."""

    pytestmark = pytest.mark.os_sensitive

    @pytest.mark.spec("DAG-029")
    def test_delete_logs_by_log_key(self, clm) -> None:
        """delete_logs(log_key=...) removes every io_type x partial variant from the Store."""
        log_key = ["run1", "compute_logs", "step_a"]
        _upload(clm, log_key, _OUT, b"o")
        _upload(clm, log_key, _ERR, b"e")
        _upload(clm, log_key, _OUT, b"op", partial=True)
        _upload(clm, log_key, _ERR, b"ep", partial=True)

        clm.delete_logs(log_key=log_key)

        for io_type in (_OUT, _ERR):
            for partial in (False, True):
                assert not clm.cloud_storage_has_logs(log_key, io_type, partial=partial)

    @pytest.mark.spec("DAG-029")
    def test_delete_logs_by_prefix(self, clm) -> None:
        """delete_logs(prefix=...) removes the whole run's log folder from the Store."""
        prefix = ["run1", "compute_logs"]
        key_a = [*prefix, "step_a"]
        key_b = [*prefix, "step_b"]
        _upload(clm, key_a, _OUT, b"a")
        _upload(clm, key_b, _OUT, b"b")

        clm.delete_logs(prefix=prefix)

        assert not clm.cloud_storage_has_logs(key_a, _OUT)
        assert not clm.cloud_storage_has_logs(key_b, _OUT)

    @pytest.mark.spec("DAG-029")
    def test_delete_logs_requires_an_argument(self, clm) -> None:
        """delete_logs() with neither log_key nor prefix raises a Dagster check failure."""
        with pytest.raises(CheckError):
            clm.delete_logs()

    @pytest.mark.spec("DAG-031")
    def test_get_log_keys_for_prefix(self, clm) -> None:
        """get_log_keys_for_log_key_prefix enumerates one key per stored step log."""
        prefix = ["run1", "compute_logs"]
        _upload(clm, [*prefix, "step_a"], _OUT, b"a")
        _upload(clm, [*prefix, "step_b"], _OUT, b"b")
        _upload(clm, [*prefix, "step_a"], _ERR, b"ae")

        keys = clm.get_log_keys_for_log_key_prefix(prefix, _OUT)

        assert sorted("/".join(k) for k in keys) == [
            "run1/compute_logs/step_a",
            "run1/compute_logs/step_b",
        ]

    @pytest.mark.spec("DAG-031")
    def test_get_log_keys_excludes_partial_uploads(self, clm) -> None:
        """Partial-upload files are not surfaced as log keys."""
        prefix = ["run1", "compute_logs"]
        _upload(clm, [*prefix, "step_a"], _OUT, b"a")
        _upload(clm, [*prefix, "step_a"], _OUT, b"ap", partial=True)

        keys = clm.get_log_keys_for_log_key_prefix(prefix, _OUT)

        assert [list(k) for k in keys] == [["run1", "compute_logs", "step_a"]]

    @pytest.mark.spec("DAG-031")
    def test_get_log_keys_empty_prefix(self, clm) -> None:
        """An unknown prefix yields no log keys rather than raising."""
        assert list(clm.get_log_keys_for_log_key_prefix(["no", "such", "run"], _OUT)) == []


class TestComputeLogManagerSubscriptionsAndLifecycle:
    """DAG-030, DAG-032: subscription delegation and dispose."""

    pytestmark = pytest.mark.os_sensitive

    @pytest.mark.spec("DAG-030")
    def test_subscribe_completes_when_capture_done(self, clm) -> None:
        """on_subscribe delegates to the polling manager, which completes a finished capture."""
        log_key = ["run1", "step"]
        _upload(clm, log_key, _ERR, b"e")  # capture complete: the Store has stderr
        subscription = clm.subscribe(log_key)
        try:
            assert subscription.is_complete
        finally:
            clm.unsubscribe(subscription)

    @pytest.mark.spec("DAG-030")
    def test_unsubscribe_completes_a_pending_subscription(self, clm) -> None:
        """on_unsubscribe delegates removal; the pending subscription is then completed."""
        log_key = ["run1", "step"]  # nothing uploaded: capture is not complete
        subscription = clm.subscribe(log_key)
        assert not subscription.is_complete
        clm.unsubscribe(subscription)
        assert subscription.is_complete

    @pytest.mark.spec("DAG-032")
    def test_dispose_disposes_managers_and_closes_store(self, tmp_path) -> None:
        """dispose() disposes the subscription + local managers and closes the Store."""
        fake_store = mock.MagicMock(spec=Store)
        fake_store.supports.return_value = True
        with mock.patch("remote_store.ext.dagster._build_store", return_value=fake_store):
            mgr = RemoteStoreComputeLogManager(backend_type="memory", local_dir=str(tmp_path / "local"))

        with (
            # internal: no public observable for the subscription manager
            mock.patch.object(mgr._subscription_manager, "dispose") as sub_dispose,
            mock.patch.object(mgr.local_manager, "dispose") as local_dispose,
        ):
            mgr.dispose()

        sub_dispose.assert_called_once()
        local_dispose.assert_called_once()
        assert fake_store.close.call_count == 1


class TestBuildStoreCredentialMasking:
    """DAG-033: _build_store wraps sensitive backend_options in Secret (RFC-0014 OQ6)."""

    @pytest.mark.spec("DAG-033")
    def test_build_store_masks_sensitive_keys(self, monkeypatch) -> None:
        """Credential-named options reach the backend constructor wrapped in Secret."""
        from remote_store._config import Secret
        from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends
        from remote_store.ext.dagster import _build_store

        captured: dict[str, object] = {}

        def recording_factory(**kwargs):
            captured.update(kwargs)
            return MemoryBackend()

        _register_builtin_backends()
        monkeypatch.setitem(_BACKEND_FACTORIES, "_recording_backend", recording_factory)

        options = {
            "secret": "s3cr3t",
            "password": "hunter2",
            "bucket": "public-bucket",
            "region": "eu-central-1",
        }
        store = _build_store("_recording_backend", options, "")
        store.close()

        assert isinstance(captured["secret"], Secret)
        assert captured["secret"].reveal() == "s3cr3t"
        assert isinstance(captured["password"], Secret)
        assert captured["bucket"] == "public-bucket"
        assert captured["region"] == "eu-central-1"
        # The caller's mapping is copied, never mutated.
        assert options["secret"] == "s3cr3t"

    @pytest.mark.spec("DAG-033")
    def test_unknown_backend_type_raises(self) -> None:
        """_build_store raises ValueError listing registered types for an unknown backend."""
        from remote_store.ext.dagster import _build_store

        with pytest.raises(ValueError, match="Unknown backend type"):
            _build_store("definitely-not-registered", {}, "")

    @pytest.mark.spec("DAG-033")
    def test_rejected_options_rewrapped_as_valueerror(self) -> None:
        """A backend ctor TypeError becomes a ValueError naming the type and options."""
        from remote_store.ext.dagster import _build_store

        with pytest.raises(ValueError, match="'memory' rejected the provided options") as exc_info:
            _build_store("memory", {"bogus_option": 1}, "")

        assert "bogus_option" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, TypeError)


class TestComputeLogManagerEndToEnd:
    """DAG-021, DAG-022: a real Dagster run captures stdout/stderr into a Store."""

    pytestmark = pytest.mark.os_sensitive

    @pytest.mark.spec("DAG-021")
    @pytest.mark.spec("DAG-022")
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Dagster's FD-level compute-log capture yields empty files on Windows under execute_in_process",
    )
    def test_end_to_end_capture_and_read_back(self, tmp_path) -> None:
        """A job configured via dagster.yaml-style overrides persists and serves its logs."""
        from dagster import DagsterInstance, job, op

        @op
        def chatty() -> None:
            print("STDOUT-MARKER-12345")  # noqa: T201 -- exercising compute-log capture
            print("STDERR-MARKER-67890", file=sys.stderr)  # noqa: T201

        @job
        def chatty_job() -> None:
            chatty()

        dagster_home = tmp_path / "dagster_home"
        dagster_home.mkdir()
        instance = DagsterInstance.local_temp(
            str(dagster_home),
            overrides={
                "compute_logs": {
                    "module": "remote_store.ext.dagster",
                    "class": "RemoteStoreComputeLogManager",
                    "config": {
                        "backend_type": "local",
                        "backend_options": {"root": str(tmp_path / "store")},
                        "local_dir": str(tmp_path / "local"),
                    },
                }
            },
        )
        try:
            result = chatty_job.execute_in_process(instance=instance)
            assert result.success

            manager = instance.compute_log_manager
            assert isinstance(manager, RemoteStoreComputeLogManager)

            # The run's compute logs were captured and uploaded to the Store;
            # discover the actual log key via the enumeration hook (DAG-031).
            keys = manager.get_log_keys_for_log_key_prefix([result.run_id, "compute_logs"], _OUT)
            assert keys, "the run's captured stdout should be persisted to the Store"

            log_key = list(keys[0])
            assert manager.cloud_storage_has_logs(log_key, _OUT)
            # Logs are read back from the Store (the local capture is gone).
            stdout, _ = manager.get_log_data_for_type(log_key, _OUT, offset=0, max_bytes=None)
            stderr, _ = manager.get_log_data_for_type(log_key, _ERR, offset=0, max_bytes=None)
            assert b"STDOUT-MARKER-12345" in stdout
            assert b"STDERR-MARKER-67890" in stderr
        finally:
            instance.dispose()
