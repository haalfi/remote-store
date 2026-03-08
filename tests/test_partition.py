"""Tests for remote_store.ext.partition -- Hive-style partition path helpers."""

from __future__ import annotations

import copy

import pytest

from remote_store.ext.partition import ParsedPartition, parse_partition, partition_path

# ===========================================================================
# PART-001 / PART-002 / PART-003: partition_path() basics
# ===========================================================================


class TestPartitionPath:
    @pytest.mark.spec("PART-001")
    def test_single_partition(self) -> None:
        assert partition_path("data.parquet", year="2026") == "year=2026/data.parquet"

    @pytest.mark.spec("PART-002")
    def test_multiple_partitions_ordered(self) -> None:
        result = partition_path("f.csv", year="2026", month="03", day="01")
        assert result == "year=2026/month=03/day=01/f.csv"

    @pytest.mark.spec("PART-003")
    def test_int_value_coercion(self) -> None:
        assert partition_path("f.parquet", year=2026, month=3) == "year=2026/month=3/f.parquet"

    @pytest.mark.spec("PART-004")
    def test_no_partitions_returns_filename(self) -> None:
        assert partition_path("data.parquet") == "data.parquet"

    @pytest.mark.spec("PART-005")
    def test_empty_filename_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            partition_path("")

    @pytest.mark.spec("PART-005")
    def test_filename_with_slash_raises(self) -> None:
        with pytest.raises(ValueError, match="/"):
            partition_path("dir/file.parquet")

    @pytest.mark.spec("PART-006")
    def test_empty_value_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            partition_path("f.parquet", year="")

    @pytest.mark.spec("PART-006")
    def test_empty_key_in_kwargs_impossible(self) -> None:
        # Python syntax prevents empty-string kwargs, but we guard anyway.
        # Use **dict to bypass syntax restriction.
        with pytest.raises(ValueError, match="key must be non-empty"):
            partition_path("f.parquet", **{"": "val"})  # type: ignore[arg-type]


# ===========================================================================
# PART-007 / PART-008 / PART-009: parse_partition()
# ===========================================================================


class TestParsePartition:
    @pytest.mark.spec("PART-007")
    def test_basic_parse(self) -> None:
        parsed = parse_partition("year=2026/month=03/data.parquet")
        assert parsed.partitions == {"year": "2026", "month": "03"}
        assert parsed.filename == "data.parquet"

    @pytest.mark.spec("PART-008")
    def test_segment_with_multiple_equals_is_filename(self) -> None:
        # "a=b=c" has two '=' -- not a partition segment
        parsed = parse_partition("a=b=c")
        assert parsed.partitions == {}
        assert parsed.filename == "a=b=c"

    @pytest.mark.spec("PART-008")
    def test_segment_with_empty_key_is_filename(self) -> None:
        # "=value" has empty key portion
        parsed = parse_partition("=value/data.csv")
        assert parsed.partitions == {}
        assert parsed.filename == "=value/data.csv"

    @pytest.mark.spec("PART-009")
    def test_kv_after_non_partition_is_filename(self) -> None:
        parsed = parse_partition("year=2026/subdir/region=us/data.csv")
        assert parsed.partitions == {"year": "2026"}
        assert parsed.filename == "subdir/region=us/data.csv"

    @pytest.mark.spec("PART-009")
    def test_no_partitions(self) -> None:
        parsed = parse_partition("just-a-file.txt")
        assert parsed.partitions == {}
        assert parsed.filename == "just-a-file.txt"

    @pytest.mark.spec("PART-009")
    def test_all_partitions_no_filename(self) -> None:
        parsed = parse_partition("year=2026/month=03")
        assert parsed.partitions == {"year": "2026", "month": "03"}
        assert parsed.filename == ""

    @pytest.mark.spec("PART-010")
    def test_empty_path_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            parse_partition("")


# ===========================================================================
# PART-011: Round-trip
# ===========================================================================


class TestRoundTrip:
    @pytest.mark.spec("PART-011")
    def test_round_trip_single(self) -> None:
        path = partition_path("data.parquet", year="2026")
        parsed = parse_partition(path)
        assert parsed.partitions == {"year": "2026"}
        assert parsed.filename == "data.parquet"

    @pytest.mark.spec("PART-011")
    def test_round_trip_multiple(self) -> None:
        path = partition_path("f.csv", region="eu", year="2026", month="03")
        parsed = parse_partition(path)
        assert parsed.partitions == {"region": "eu", "year": "2026", "month": "03"}
        assert parsed.filename == "f.csv"

    @pytest.mark.spec("PART-011")
    def test_round_trip_int_values(self) -> None:
        path = partition_path("f.parquet", year=2026, month=3)
        parsed = parse_partition(path)
        assert parsed.partitions == {"year": "2026", "month": "3"}
        assert parsed.filename == "f.parquet"


# ===========================================================================
# PART-012: ParsedPartition dataclass
# ===========================================================================


class TestParsedPartition:
    @pytest.mark.spec("PART-012")
    def test_frozen(self) -> None:
        p = ParsedPartition(partitions={"a": "1"}, filename="f.txt")
        with pytest.raises(AttributeError):
            p.filename = "other.txt"  # type: ignore[misc]

    @pytest.mark.spec("PART-012")
    def test_dict_is_independent_copy(self) -> None:
        p = parse_partition("year=2026/f.txt")
        p.partitions["extra"] = "added"
        # Re-parse to confirm original is unaffected
        p2 = parse_partition("year=2026/f.txt")
        assert "extra" not in p2.partitions

    @pytest.mark.spec("PART-012")
    def test_deepcopy(self) -> None:
        p = ParsedPartition(partitions={"a": "1"}, filename="f.txt")
        p2 = copy.deepcopy(p)
        assert p == p2
        assert p is not p2


# ===========================================================================
# PART-013: Module exports
# ===========================================================================


class TestExports:
    @pytest.mark.spec("PART-013")
    def test_all_exports(self) -> None:
        from remote_store.ext import partition

        assert set(partition.__all__) == {"ParsedPartition", "parse_partition", "partition_path"}

    @pytest.mark.spec("PART-013")
    def test_top_level_reexport(self) -> None:
        import remote_store

        assert hasattr(remote_store, "partition_path")
        assert hasattr(remote_store, "parse_partition")
        assert hasattr(remote_store, "ParsedPartition")
