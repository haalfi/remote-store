"""Tests for remote_store.ext.dagster -- Dagster IO Manager adapter."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest
from dagster import AssetKey, build_init_resource_context, build_input_context, build_output_context

from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.dagster import (
    ParquetSerializer,
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


class TestPickleSerializer:
    """DAG-002: Pickle roundtrip."""

    @pytest.mark.spec("DAG-002")
    def test_roundtrip(self, store: Store) -> None:
        mgr = dagster_io_manager(store, serializer="pickle")
        obj = {"key": "value", "numbers": [1, 2, 3]}

        out_ctx = build_output_context(asset_key=AssetKey(["test", "pickle"]))
        mgr.handle_output(out_ctx, obj)

        in_ctx = build_input_context(
            asset_key=AssetKey(["test", "pickle"]),
            upstream_output=out_ctx,
        )
        assert mgr.load_input(in_ctx) == obj


class TestJsonSerializer:
    """DAG-003: JSON roundtrip."""

    @pytest.mark.spec("DAG-003")
    def test_roundtrip(self, store: Store) -> None:
        mgr = dagster_io_manager(store, serializer="json")
        obj = {"key": "value", "numbers": [1, 2, 3]}

        out_ctx = build_output_context(asset_key=AssetKey(["test", "json"]))
        mgr.handle_output(out_ctx, obj)

        in_ctx = build_input_context(
            asset_key=AssetKey(["test", "json"]),
            upstream_output=out_ctx,
        )
        assert mgr.load_input(in_ctx) == obj


class TestParquetSerializer:
    """DAG-004: Parquet roundtrip."""

    @pytest.mark.spec("DAG-004")
    def test_roundtrip_pandas(self, store: Store) -> None:
        """Roundtrip with a pandas DataFrame."""
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
        pandas.testing.assert_frame_equal(result, df)
        assert len(result) == 3

    @pytest.mark.spec("DAG-004")
    def test_serialize_arrow_table(self) -> None:
        """Serialize a PyArrow Table directly."""
        import pyarrow as pa
        import pyarrow.parquet as pq

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
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table([pa.array([10, 20])], names=["val"])

        # Mock a Polars-like DataFrame with to_arrow()
        import polars as pl

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
        serializer = ParquetSerializer()
        with pytest.raises(TypeError, match="ParquetSerializer expects a DataFrame, got str"):
            serializer.serialize("not a dataframe")

    @pytest.mark.spec("DAG-004")
    def test_deserialize_returns_to_pandas(self) -> None:
        """Deserialize reads parquet and calls to_pandas()."""
        import io

        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table([pa.array([1, 2, 3])], names=["col"])
        buf = io.BytesIO()
        pq.write_table(table, buf)
        parquet_bytes = buf.getvalue()

        serializer = ParquetSerializer()
        sentinel = object()
        mock_table = mock.MagicMock(spec=pa.Table)
        mock_table.to_pandas.return_value = sentinel
        with mock.patch("pyarrow.parquet.read_table", return_value=mock_table):
            result = serializer.deserialize(parquet_bytes)
        mock_table.to_pandas.assert_called_once()
        assert result is sentinel


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
        with pytest.raises(NotFound):
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
