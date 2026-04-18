"""Tests for models — derived from sdd/specs/001-store-api.md (MOD sections)."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from remote_store._models import ContentDigest, FileInfo, FolderEntry, FolderInfo, PathEntry, WriteResult
from remote_store._path import RemotePath

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def file_info() -> FileInfo:
    return FileInfo(path=RemotePath("a.txt"), name="a.txt", size=100, modified_at=NOW)


@pytest.fixture
def folder_info() -> FolderInfo:
    return FolderInfo(path=RemotePath("data"), file_count=5, total_size=1000)


class TestFrozenModels:
    """MOD-001 / MOD-004 / MOD-006 / CDG-001: All models are frozen dataclasses."""

    @pytest.mark.spec("MOD-001")
    def test_fileinfo_frozen(self, file_info: FileInfo) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            file_info.size = 200  # type: ignore[misc]

    @pytest.mark.spec("MOD-004")
    def test_folderinfo_frozen(self, folder_info: FolderInfo) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            folder_info.file_count = 10  # type: ignore[misc]

    @pytest.mark.spec("MOD-006")
    def test_folderentry_frozen(self) -> None:
        fe = FolderEntry(path=RemotePath("sub"), name="sub")
        with pytest.raises(dataclasses.FrozenInstanceError):
            fe.name = "other"  # type: ignore[misc]

    @pytest.mark.spec("CDG-001")
    def test_contentdigest_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            ContentDigest("sha256", "abcd1234").algorithm = "md5"  # type: ignore[misc]


class TestFileInfoFields:
    """MOD-002 through MOD-003: FileInfo required and optional fields."""

    @pytest.mark.spec("MOD-002")
    def test_required_fields(self) -> None:
        fi = FileInfo(path=RemotePath("data/file.csv"), name="file.csv", size=42, modified_at=NOW)
        assert (fi.path, fi.name, fi.size, fi.modified_at) == (
            RemotePath("data/file.csv"),
            "file.csv",
            42,
            NOW,
        )

    @pytest.mark.spec("MOD-003")
    @pytest.mark.spec("CDG-004")
    def test_defaults(self) -> None:
        fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=0, modified_at=NOW)
        assert (fi.digest, fi.etag, fi.content_type, fi.extra) == (None, None, None, {})

    @pytest.mark.spec("MOD-003")
    @pytest.mark.spec("CDG-004")
    def test_optional_set(self) -> None:
        fi = FileInfo(
            path=RemotePath("a.txt"),
            name="a.txt",
            size=10,
            modified_at=NOW,
            digest=ContentDigest("sha256", "abcdef0123456789"),
            etag='"abc123"',
            content_type="text/plain",
            extra={"key": "val"},
        )
        assert fi.digest == ContentDigest("sha256", "abcdef0123456789")
        assert (fi.etag, fi.content_type, fi.extra) == ('"abc123"', "text/plain", {"key": "val"})


class TestFolderInfoFields:
    """MOD-004 / MOD-005 / MOD-008: FolderInfo fields and properties."""

    @pytest.mark.spec("MOD-004")
    def test_required_fields(self, folder_info: FolderInfo) -> None:
        assert (folder_info.path, folder_info.file_count, folder_info.total_size) == (
            RemotePath("data"),
            5,
            1000,
        )

    @pytest.mark.spec("MOD-005")
    def test_defaults(self) -> None:
        fi = FolderInfo(path=RemotePath("data"), file_count=0, total_size=0)
        assert (fi.modified_at, fi.extra) == (None, {})

    @pytest.mark.spec("MOD-005")
    def test_optional_set(self) -> None:
        fi = FolderInfo(path=RemotePath("data"), file_count=5, total_size=1000, modified_at=NOW, extra={"key": "val"})
        assert (fi.modified_at, fi.extra) == (NOW, {"key": "val"})

    @pytest.mark.spec("MOD-008")
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            pytest.param("a/b/c", "c", id="nested"),
            pytest.param("data", "data", id="single-component"),
        ],
    )
    def test_name_property(self, path: str, expected: str) -> None:
        assert FolderInfo(path=RemotePath(path), file_count=0, total_size=0).name == expected

    @pytest.mark.spec("MOD-008")
    def test_name_property_root(self) -> None:
        assert FolderInfo(path=RemotePath.ROOT, file_count=0, total_size=0).name == "."


class TestModelEqualityHashing:
    """MOD-007: Equality and hashing based on path."""

    @pytest.mark.spec("MOD-007")
    def test_fileinfo_equality_and_hash(self) -> None:
        a = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=10, modified_at=NOW)
        b = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=99, modified_at=NOW)
        assert a == b
        assert hash(a) == hash(b)

    @pytest.mark.spec("MOD-007")
    def test_folderinfo_equality_by_path(self) -> None:
        a = FolderInfo(path=RemotePath("data"), file_count=1, total_size=10)
        b = FolderInfo(path=RemotePath("data"), file_count=9, total_size=99)
        assert a == b

    @pytest.mark.spec("MOD-007")
    def test_folderentry_equality_hash_and_set(self) -> None:
        a = FolderEntry(path=RemotePath("data"), name="data")
        b = FolderEntry(path=RemotePath("data"), name="data")
        assert a == b
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    @pytest.mark.spec("MOD-007")
    def test_folderentry_equality_ignores_name(self) -> None:
        assert FolderEntry(path=RemotePath("data"), name="data") == FolderEntry(path=RemotePath("data"), name="other")

    @pytest.mark.spec("MOD-007")
    def test_folderentry_inequality(self) -> None:
        assert FolderEntry(path=RemotePath("x"), name="x") != FolderEntry(path=RemotePath("y"), name="y")


class TestFolderEntryFields:
    """MOD-006: FolderEntry dataclass tests."""

    @pytest.mark.spec("MOD-006")
    def test_fields(self) -> None:
        fe = FolderEntry(path=RemotePath("a/b"), name="b")
        assert (fe.path, fe.name) == (RemotePath("a/b"), "b")

    @pytest.mark.spec("MOD-006")
    def test_not_equal_to_other_types(self) -> None:
        fe = FolderEntry(path=RemotePath("x"), name="x")
        assert fe != "x"
        assert fe.__eq__("x") is NotImplemented


class TestPathEntryProtocol:
    """MOD-008: PathEntry protocol structural subtyping tests."""

    @pytest.mark.spec("MOD-008")
    @pytest.mark.parametrize(
        "instance",
        [
            pytest.param(FileInfo(path=RemotePath("a.txt"), name="a.txt", size=0, modified_at=NOW), id="FileInfo"),
            pytest.param(FolderEntry(path=RemotePath("sub"), name="sub"), id="FolderEntry"),
            pytest.param(FolderInfo(path=RemotePath("a/b"), file_count=0, total_size=0), id="FolderInfo"),
        ],
    )
    def test_satisfies_path_entry(self, instance: PathEntry) -> None:
        assert isinstance(instance, PathEntry)

    @pytest.mark.spec("MOD-008")
    def test_path_entry_uniform_iteration(self) -> None:
        entries: list[PathEntry] = [
            FileInfo(path=RemotePath("a.txt"), name="a.txt", size=0, modified_at=NOW),
            FolderEntry(path=RemotePath("sub"), name="sub"),
            FolderInfo(path=RemotePath("data"), file_count=3, total_size=500),
        ]
        assert [e.name for e in entries] == ["a.txt", "sub", "data"]
        assert [str(e.path) for e in entries] == ["a.txt", "sub", "data"]


class TestContentDigest:
    """CDG-001 through CDG-005: ContentDigest dataclass."""

    @pytest.mark.spec("CDG-001")
    @pytest.mark.parametrize(
        ("algo_in", "val_in", "algo_out", "val_out"),
        [
            pytest.param("SHA256", "ABCD1234", "sha256", "abcd1234", id="lowercase"),
            pytest.param(" sha256 ", " abcd1234 ", "sha256", "abcd1234", id="whitespace"),
        ],
    )
    def test_normalization(self, algo_in: str, val_in: str, algo_out: str, val_out: str) -> None:
        d = ContentDigest(algo_in, val_in)
        assert (d.algorithm, d.value) == (algo_out, val_out)

    @pytest.mark.spec("CDG-002")
    def test_equality_and_hash(self) -> None:
        a, b = ContentDigest("sha256", "abcd1234"), ContentDigest("SHA256", "ABCD1234")
        assert a == b
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    @pytest.mark.spec("CDG-003")
    @pytest.mark.parametrize(
        ("algo", "val", "match"),
        [
            pytest.param("", "abcd1234", "algorithm must not be empty", id="empty-algo"),
            pytest.param("   ", "abcd1234", "algorithm must not be empty", id="ws-algo"),
            pytest.param("sha256", "", "value must not be empty", id="empty-val"),
            pytest.param("sha256", "   ", "value must not be empty", id="ws-val"),
            pytest.param("sha256", "not-hex!", "value must be hexadecimal", id="non-hex"),
        ],
    )
    def test_validation_errors(self, algo: str, val: str, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            ContentDigest(algo, val)

    @pytest.mark.spec("CDG-005")
    def test_top_level_export(self) -> None:
        import remote_store

        assert hasattr(remote_store, "ContentDigest")
        assert remote_store.ContentDigest is ContentDigest


class TestWriteResultFields:
    """WR-001a: WriteResult frozen dataclass with required and optional fields."""

    @pytest.mark.spec("WR-001a")
    def test_required_fields(self) -> None:
        wr = WriteResult(path=RemotePath("data/file.csv"), size=42)
        assert wr.path == RemotePath("data/file.csv")
        assert wr.size == 42

    @pytest.mark.spec("WR-001a")
    def test_source_defaults_to_basic(self) -> None:
        wr = WriteResult(path=RemotePath("a.bin"), size=0)
        assert wr.source == "basic"

    @pytest.mark.spec("WR-001a")
    @pytest.mark.parametrize("source", ["native", "basic", "sidecar"])
    def test_source_values(self, source: str) -> None:
        wr = WriteResult(path=RemotePath("a.bin"), size=0, source=source)  # type: ignore[arg-type]
        assert wr.source == source

    @pytest.mark.spec("WR-001a")
    def test_optional_defaults_none(self) -> None:
        wr = WriteResult(path=RemotePath("a.bin"), size=0)
        assert wr.digest is None
        assert wr.etag is None
        assert wr.version_id is None
        assert wr.last_modified is None
        assert wr.content_md5 is None
        assert wr.metadata is None

    @pytest.mark.spec("WR-001a")
    def test_frozen(self) -> None:
        wr = WriteResult(path=RemotePath("a.bin"), size=10)
        with pytest.raises(dataclasses.FrozenInstanceError):
            wr.size = 99  # type: ignore[misc]

    @pytest.mark.spec("WR-001a")
    def test_equality_field_wise(self) -> None:
        a = WriteResult(path=RemotePath("a.bin"), size=10, etag='"abc"')
        b = WriteResult(path=RemotePath("a.bin"), size=10, etag='"abc"')
        c = WriteResult(path=RemotePath("a.bin"), size=99, etag='"abc"')
        assert a == b
        assert a != c

    @pytest.mark.spec("WR-001a")
    def test_top_level_export(self) -> None:
        import remote_store

        assert hasattr(remote_store, "WriteResult")
        assert remote_store.WriteResult is WriteResult


class TestFileInfoMetadata:
    """WR-012: FileInfo.metadata field."""

    @pytest.mark.spec("WR-012")
    def test_metadata_defaults_none(self) -> None:
        fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=0, modified_at=NOW)
        assert fi.metadata is None

    @pytest.mark.spec("WR-012")
    def test_metadata_accepted(self) -> None:
        fi = FileInfo(
            path=RemotePath("a.txt"),
            name="a.txt",
            size=0,
            modified_at=NOW,
            metadata={"x-custom": "value"},
        )
        assert fi.metadata == {"x-custom": "value"}

    @pytest.mark.spec("WR-012")
    def test_metadata_frozen(self) -> None:
        fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=0, modified_at=NOW, metadata={"k": "v"})
        with pytest.raises(dataclasses.FrozenInstanceError):
            fi.metadata = None  # type: ignore[misc]
