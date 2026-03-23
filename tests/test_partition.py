"""Tests for remote_store.ext.partition -- Hive-style partition path helpers."""

from __future__ import annotations

import copy

import pytest

from remote_store.ext.partition import ParsedPartition, parse_partition, partition_path

# ===========================================================================
# PART-001 through PART-006: partition_path() basics and validation
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
    @pytest.mark.parametrize(
        "filename,match",
        [
            pytest.param("", "non-empty", id="empty"),
            pytest.param("dir/file.parquet", "/", id="slash"),
        ],
    )
    def test_invalid_filename_raises(self, filename: str, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            partition_path(filename)

    @pytest.mark.spec("PART-006")
    @pytest.mark.parametrize(
        "kwargs,match",
        [
            pytest.param({"year": ""}, "non-empty", id="empty_value"),
            pytest.param({"key": "a=b"}, "must not contain '='", id="equals_in_value"),
            pytest.param({"": "val"}, "key must be non-empty", id="empty_key"),
        ],
    )
    def test_invalid_partition_raises(self, kwargs: dict, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            partition_path("f.parquet", **kwargs)


# ===========================================================================
# PART-007 through PART-010: parse_partition()
# ===========================================================================


class TestParsePartition:
    @pytest.mark.spec("PART-007")
    def test_basic_parse(self) -> None:
        parsed = parse_partition("year=2026/month=03/data.parquet")
        assert parsed.partitions == {"year": "2026", "month": "03"}
        assert parsed.filename == "data.parquet"

    @pytest.mark.spec("PART-008")
    @pytest.mark.parametrize(
        "path,expected_parts,expected_file",
        [
            pytest.param("a=b=c", {}, "a=b=c", id="multiple_equals_is_filename"),
            pytest.param("=value/data.csv", {}, "=value/data.csv", id="empty_key_is_filename"),
            pytest.param("key=/data.csv", {"key": ""}, "data.csv", id="empty_value_is_valid"),
        ],
    )
    def test_edge_case_segments(self, path: str, expected_parts: dict, expected_file: str) -> None:
        parsed = parse_partition(path)
        assert parsed.partitions == expected_parts
        assert parsed.filename == expected_file

    @pytest.mark.spec("PART-009")
    @pytest.mark.parametrize(
        "path,expected_parts,expected_file",
        [
            pytest.param(
                "year=2026/subdir/region=us/data.csv",
                {"year": "2026"},
                "subdir/region=us/data.csv",
                id="kv_after_non_partition",
            ),
            pytest.param("just-a-file.txt", {}, "just-a-file.txt", id="no_partitions"),
            pytest.param("year=2026/month=03", {"year": "2026", "month": "03"}, "", id="all_partitions_no_filename"),
        ],
    )
    def test_parse_variants(self, path: str, expected_parts: dict, expected_file: str) -> None:
        parsed = parse_partition(path)
        assert parsed.partitions == expected_parts
        assert parsed.filename == expected_file

    @pytest.mark.spec("PART-010")
    def test_empty_path_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            parse_partition("")


# ===========================================================================
# PART-011: Round-trip
# ===========================================================================


class TestRoundTrip:
    @pytest.mark.spec("PART-011")
    @pytest.mark.parametrize(
        "filename,kwargs,expected_parts",
        [
            pytest.param("data.parquet", {"year": "2026"}, {"year": "2026"}, id="single"),
            pytest.param(
                "f.csv",
                {"region": "eu", "year": "2026", "month": "03"},
                {"region": "eu", "year": "2026", "month": "03"},
                id="multiple",
            ),
            pytest.param("f.parquet", {"year": 2026, "month": 3}, {"year": "2026", "month": "3"}, id="int_values"),
        ],
    )
    def test_round_trip(self, filename: str, kwargs: dict, expected_parts: dict) -> None:
        path = partition_path(filename, **kwargs)
        parsed = parse_partition(path)
        assert parsed.partitions == expected_parts
        assert parsed.filename == filename


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
    @pytest.mark.parametrize("name", ["partition_path", "parse_partition", "ParsedPartition"])
    def test_top_level_reexport(self, name: str) -> None:
        import remote_store

        assert hasattr(remote_store, name)
