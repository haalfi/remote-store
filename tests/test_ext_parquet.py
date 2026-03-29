"""Tests for ext.parquet -- derived from sdd/specs/042-ext-parquet.md (PDS-001 through PDS-012)."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pyarrow as pa
import pytest

from remote_store import AlreadyExists, CapabilityNotSupported, NotFound, Store
from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store.backends import LocalBackend, MemoryBackend
from remote_store.ext.parquet import DatasetIncomplete, DatasetManifest, ManifestCorrupted, ParquetDatasetStore

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(params=["memory", "local"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Store:
    """Store backed by MemoryBackend or LocalBackend."""
    if request.param == "memory":
        return Store(MemoryBackend())
    return Store(LocalBackend(str(tmp_path)))


@pytest.fixture
def memory_store() -> Store:
    """Store backed by MemoryBackend only."""
    return Store(MemoryBackend())


@pytest.fixture
def local_store(tmp_path: Path) -> Store:
    """Store backed by LocalBackend only."""
    return Store(LocalBackend(str(tmp_path)))


@pytest.fixture
def pds(store: Store) -> ParquetDatasetStore:
    """ParquetDatasetStore over the parametrized store."""
    return ParquetDatasetStore(store)


@pytest.fixture
def sample_table() -> pa.Table:
    """Small PyArrow table for testing."""
    return pa.table({"id": [1, 2, 3], "name": ["a", "b", "c"], "value": [1.0, 2.0, 3.0]})


# ---------------------------------------------------------------------------
# TestDatasetManifest -- PDS-004, PDS-008
# ---------------------------------------------------------------------------


class TestDatasetManifest:
    """PDS-004, PDS-008: DatasetManifest frozen dataclass with JSON serialization."""

    @pytest.mark.spec("PDS-004")
    def test_roundtrip_json(self) -> None:
        manifest = DatasetManifest(
            dataset_key="test/ds",
            parts=["data.parquet"],
            row_count=10,
            schema_hash="abcdef0123456789",
            compression="zstd",
            created_at_utc="2026-03-28T12:00:00Z",
            run_id="run-1",
            metadata={"source": "unit-test"},
        )
        text = manifest.to_json()
        restored = DatasetManifest.from_json(text)
        assert restored.dataset_key == manifest.dataset_key
        assert restored.parts == manifest.parts
        assert restored.row_count == manifest.row_count
        assert restored.schema_hash == manifest.schema_hash
        assert restored.compression == manifest.compression
        assert restored.created_at_utc == manifest.created_at_utc
        assert restored.run_id == manifest.run_id
        assert restored.metadata == manifest.metadata

    @pytest.mark.spec("PDS-008")
    def test_from_json_invalid_json(self) -> None:
        with pytest.raises(ManifestCorrupted, match="[Jj]son|[Pp]ars"):
            DatasetManifest.from_json("not valid json {{{")

    @pytest.mark.spec("PDS-008")
    def test_from_json_missing_field(self) -> None:
        partial = json.dumps({"dataset_key": "x", "parts": []})
        with pytest.raises(ManifestCorrupted, match="[Mm]issing|[Rr]equired|[Ff]ield"):
            DatasetManifest.from_json(partial)

    @pytest.mark.spec("PDS-004")
    def test_frozen(self) -> None:
        manifest = DatasetManifest(
            dataset_key="ds",
            parts=["data.parquet"],
            row_count=5,
            schema_hash="0000000000000000",
            compression="zstd",
            created_at_utc="2026-01-01T00:00:00Z",
        )
        with pytest.raises((AttributeError, TypeError), match="cannot|frozen|read.only"):
            manifest.dataset_key = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestWriteDataset -- PDS-001, PDS-002, PDS-005, PDS-011
# ---------------------------------------------------------------------------


class TestWriteDataset:
    """PDS-001, PDS-002, PDS-005, PDS-011: write_dataset behavior."""

    @pytest.mark.spec("PDS-001")
    def test_constructor_defaults(self, memory_store: Store) -> None:
        pds = ParquetDatasetStore(memory_store)
        assert pds.compression == "zstd"
        assert pds.max_rows_per_file is None
        assert pds.row_group_size is None

    @pytest.mark.spec("PDS-002", "PDS-005")
    def test_write_single_file(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/single")
        s = pds.store
        assert s.exists("ds/single/data.parquet")
        assert s.exists("ds/single/manifest.json")
        assert s.exists("ds/single/_SUCCESS")

    @pytest.mark.spec("PDS-002", "PDS-005")
    def test_write_multi_part(self, store: Store, sample_table: pa.Table) -> None:
        pds = ParquetDatasetStore(store, max_rows_per_file=1)
        pds.write_dataset(sample_table, "ds/multi")
        s = pds.store
        for i in range(3):
            assert s.exists(f"ds/multi/part-{i:05d}.parquet")
        assert s.exists("ds/multi/manifest.json")
        assert s.exists("ds/multi/_SUCCESS")

    @pytest.mark.spec("PDS-002", "PDS-004")
    def test_write_creates_manifest(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        manifest = pds.write_dataset(sample_table, "ds/manifest-check")
        assert isinstance(manifest, DatasetManifest)
        assert manifest.dataset_key == "ds/manifest-check"
        assert manifest.row_count == 3
        assert manifest.compression == pds.compression
        assert len(manifest.parts) >= 1
        assert manifest.schema_hash  # non-empty

    @pytest.mark.spec("PDS-002")
    def test_write_creates_success_marker(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/success")
        content = pds.store.read_bytes("ds/success/_SUCCESS")
        assert content == b""

    @pytest.mark.spec("PDS-002")
    def test_write_already_exists_raises(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/dup")
        with pytest.raises(AlreadyExists, match="ds/dup"):
            pds.write_dataset(sample_table, "ds/dup")

    @pytest.mark.spec("PDS-011")
    def test_write_overwrite_replaces(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/overwrite")
        bigger = pa.table({"id": [10, 20], "name": ["x", "y"], "value": [9.0, 8.0]})
        manifest = pds.write_dataset(bigger, "ds/overwrite", overwrite=True)
        assert manifest.row_count == 2
        roundtripped = pds.read_dataset("ds/overwrite")
        assert roundtripped.num_rows == 2

    @pytest.mark.spec("PDS-002")
    def test_write_run_id_in_manifest(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        manifest = pds.write_dataset(sample_table, "ds/run", run_id="run-42")
        assert manifest.run_id == "run-42"

    @pytest.mark.spec("PDS-002")
    def test_write_metadata_in_manifest(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        meta = {"pipeline": "etl", "version": "3"}
        manifest = pds.write_dataset(sample_table, "ds/meta", metadata=meta)
        assert manifest.metadata == meta

    @pytest.mark.spec("PDS-004")
    def test_write_schema_hash_deterministic(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        m1 = pds.write_dataset(sample_table, "ds/hash1")
        m2 = pds.write_dataset(sample_table, "ds/hash2")
        assert m1.schema_hash == m2.schema_hash

    @pytest.mark.spec("PDS-002")
    def test_write_requires_atomic_write(self, sample_table: pa.Table) -> None:
        mock_backend = MagicMock(spec=Backend)
        mock_backend.name = "mock"
        mock_backend.capabilities = CapabilitySet(
            {Capability.READ, Capability.WRITE, Capability.LIST, Capability.DELETE}
        )
        store = Store(mock_backend)
        pds = ParquetDatasetStore(store)
        with pytest.raises(CapabilityNotSupported, match="atomic_write"):
            pds.write_dataset(sample_table, "ds/nope")


# ---------------------------------------------------------------------------
# TestReadDataset -- PDS-003, PDS-006, PDS-012
# ---------------------------------------------------------------------------


class TestReadDataset:
    """PDS-003, PDS-006, PDS-012: read_dataset and read_manifest behavior."""

    @pytest.mark.spec("PDS-003")
    def test_read_roundtrip_single(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/rt")
        result = pds.read_dataset("ds/rt")
        assert result.num_rows == sample_table.num_rows
        assert result.schema.equals(sample_table.schema)
        assert result.to_pydict() == sample_table.to_pydict()

    @pytest.mark.spec("PDS-003")
    def test_read_roundtrip_multi_part(self, store: Store, sample_table: pa.Table) -> None:
        pds = ParquetDatasetStore(store, max_rows_per_file=2)
        pds.write_dataset(sample_table, "ds/rt-multi")
        result = pds.read_dataset("ds/rt-multi")
        assert result.num_rows == sample_table.num_rows
        assert result.to_pydict() == sample_table.to_pydict()

    @pytest.mark.spec("PDS-003")
    def test_read_missing_success_raises(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/no-success")
        pds.store.delete("ds/no-success/_SUCCESS")
        with pytest.raises(DatasetIncomplete, match="_SUCCESS"):
            pds.read_dataset("ds/no-success")

    @pytest.mark.spec("PDS-003")
    def test_read_missing_part_raises(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/missing-part")
        pds.store.delete("ds/missing-part/data.parquet")
        with pytest.raises(DatasetIncomplete, match="part|data.parquet"):
            pds.read_dataset("ds/missing-part")

    @pytest.mark.spec("PDS-006")
    def test_read_column_projection(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/proj")
        result = pds.read_dataset("ds/proj", columns=["id", "name"])
        assert result.column_names == ["id", "name"]
        assert result.num_rows == 3

    @pytest.mark.spec("PDS-012")
    def test_read_manifest_only(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/manifest-read")
        manifest = pds.read_manifest("ds/manifest-read")
        assert isinstance(manifest, DatasetManifest)
        assert manifest.dataset_key == "ds/manifest-read"
        assert manifest.row_count == 3

    @pytest.mark.spec("PDS-008")
    def test_read_corrupted_manifest(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/corrupt")
        pds.store.write("ds/corrupt/manifest.json", b"{{garbage", overwrite=True)
        with pytest.raises(ManifestCorrupted, match="[Jj]son|[Pp]ars|[Cc]orrupt"):
            pds.read_manifest("ds/corrupt")


# ---------------------------------------------------------------------------
# TestDatasetExists -- PDS-007
# ---------------------------------------------------------------------------


class TestDatasetExists:
    """PDS-007: dataset_exists checks for _SUCCESS marker."""

    @pytest.mark.spec("PDS-007")
    def test_exists_true_when_success(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/exists")
        assert pds.dataset_exists("ds/exists") is True

    @pytest.mark.spec("PDS-007")
    def test_exists_false_when_no_success(self, pds: ParquetDatasetStore) -> None:
        assert pds.dataset_exists("ds/nonexistent") is False


# ---------------------------------------------------------------------------
# TestDeleteDataset -- PDS-010
# ---------------------------------------------------------------------------


class TestDeleteDataset:
    """PDS-010: delete_dataset removes all dataset files."""

    @pytest.mark.spec("PDS-010")
    def test_delete_removes_all_files(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        pds.write_dataset(sample_table, "ds/del")
        pds.delete_dataset("ds/del")
        assert pds.dataset_exists("ds/del") is False
        assert not pds.store.exists("ds/del/data.parquet")
        assert not pds.store.exists("ds/del/manifest.json")

    @pytest.mark.spec("PDS-010")
    def test_delete_nonexistent_raises(self, pds: ParquetDatasetStore) -> None:
        with pytest.raises(NotFound, match="ds/ghost"):
            pds.delete_dataset("ds/ghost")


# ---------------------------------------------------------------------------
# TestEdgeCases -- PDS-002, PDS-005
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """PDS-002, PDS-005: edge cases for write/read."""

    @pytest.mark.spec("PDS-002")
    def test_nested_dataset_key(self, pds: ParquetDatasetStore, sample_table: pa.Table) -> None:
        key = "silver/orders/2026-03-28"
        pds.write_dataset(sample_table, key)
        result = pds.read_dataset(key)
        assert result.num_rows == 3

    @pytest.mark.spec("PDS-002")
    def test_empty_table(self, pds: ParquetDatasetStore) -> None:
        empty = pa.table({"id": pa.array([], type=pa.int64()), "name": pa.array([], type=pa.utf8())})
        pds.write_dataset(empty, "ds/empty")
        result = pds.read_dataset("ds/empty")
        assert result.num_rows == 0
        assert result.schema.equals(empty.schema)

    @pytest.mark.spec("PDS-005")
    def test_large_row_split(self, store: Store) -> None:
        table = pa.table({"x": list(range(100))})
        pds = ParquetDatasetStore(store, max_rows_per_file=7)
        manifest = pds.write_dataset(table, "ds/split")
        expected_parts = math.ceil(100 / 7)
        assert len(manifest.parts) == expected_parts

    @pytest.mark.spec("PDS-002")
    @pytest.mark.parametrize("compression", ["zstd", "snappy", "none"])
    def test_compression_roundtrip(self, store: Store, sample_table: pa.Table, compression: str) -> None:
        pds = ParquetDatasetStore(store, compression=compression)
        key = f"ds/compress-{compression}"
        manifest = pds.write_dataset(sample_table, key)
        assert manifest.compression == compression
        result = pds.read_dataset(key)
        assert result.to_pydict() == sample_table.to_pydict()
