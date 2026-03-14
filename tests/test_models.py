"""Tests for models — derived from sdd/specs/001-store-api.md (MOD sections)."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from remote_store._models import FileInfo, FolderEntry, FolderInfo, PathEntry
from remote_store._path import RemotePath

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


class TestFileInfoImmutability:
    """MOD-001: FileInfo is a frozen dataclass."""

    @pytest.mark.spec("MOD-001")
    def test_fileinfo_frozen(self) -> None:
        fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=100, modified_at=NOW)
        with pytest.raises(dataclasses.FrozenInstanceError):
            fi.size = 200  # type: ignore[misc]


class TestFileInfoFields:
    """MOD-002 through MOD-003: FileInfo required and optional fields."""

    @pytest.mark.spec("MOD-002")
    def test_required_fields(self) -> None:
        fi = FileInfo(path=RemotePath("data/file.csv"), name="file.csv", size=42, modified_at=NOW)
        assert fi.path == RemotePath("data/file.csv")
        assert fi.name == "file.csv"
        assert fi.size == 42
        assert fi.modified_at == NOW

    @pytest.mark.spec("MOD-003")
    def test_defaults(self) -> None:
        fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=0, modified_at=NOW)
        assert fi.checksum is None
        assert fi.content_type is None
        assert fi.extra == {}

    @pytest.mark.spec("MOD-003")
    def test_optional_set(self) -> None:
        fi = FileInfo(
            path=RemotePath("a.txt"),
            name="a.txt",
            size=10,
            modified_at=NOW,
            checksum="abc123",
            content_type="text/plain",
            extra={"etag": "xyz"},
        )
        assert fi.checksum == "abc123"
        assert fi.content_type == "text/plain"
        assert fi.extra == {"etag": "xyz"}


class TestFolderInfoFields:
    """MOD-004 through MOD-005: FolderInfo required and optional fields."""

    @pytest.mark.spec("MOD-004")
    def test_frozen(self) -> None:
        fi = FolderInfo(path=RemotePath("data"), file_count=5, total_size=1000)
        with pytest.raises(dataclasses.FrozenInstanceError):
            fi.file_count = 10  # type: ignore[misc]

    @pytest.mark.spec("MOD-004")
    def test_required_fields(self) -> None:
        fi = FolderInfo(path=RemotePath("data"), file_count=5, total_size=1000)
        assert fi.path == RemotePath("data")
        assert fi.file_count == 5
        assert fi.total_size == 1000

    @pytest.mark.spec("MOD-005")
    def test_defaults(self) -> None:
        fi = FolderInfo(path=RemotePath("data"), file_count=0, total_size=0)
        assert fi.modified_at is None
        assert fi.extra == {}

    @pytest.mark.spec("MOD-005")
    def test_optional_set(self) -> None:
        fi = FolderInfo(path=RemotePath("data"), file_count=5, total_size=1000, modified_at=NOW, extra={"key": "val"})
        assert fi.modified_at == NOW
        assert fi.extra == {"key": "val"}

    @pytest.mark.spec("MOD-008")
    def test_name_property(self) -> None:
        fi = FolderInfo(path=RemotePath("a/b/c"), file_count=0, total_size=0)
        assert fi.name == "c"

    @pytest.mark.spec("MOD-008")
    def test_name_property_single_component(self) -> None:
        fi = FolderInfo(path=RemotePath("data"), file_count=0, total_size=0)
        assert fi.name == "data"


class TestModelEqualityHashing:
    """MOD-007: Equality and hashing based on path."""

    @pytest.mark.spec("MOD-007")
    def test_fileinfo_equality_by_path(self) -> None:
        a = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=10, modified_at=NOW)
        b = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=99, modified_at=NOW)
        assert a == b

    @pytest.mark.spec("MOD-007")
    def test_fileinfo_hash_by_path(self) -> None:
        a = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=10, modified_at=NOW)
        b = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=99, modified_at=NOW)
        assert hash(a) == hash(b)

    @pytest.mark.spec("MOD-007")
    def test_folderinfo_equality_by_path(self) -> None:
        a = FolderInfo(path=RemotePath("data"), file_count=1, total_size=10)
        b = FolderInfo(path=RemotePath("data"), file_count=9, total_size=99)
        assert a == b

    @pytest.mark.spec("MOD-007")
    def test_folderentry_equality_by_path(self) -> None:
        a = FolderEntry(path=RemotePath("data"), name="data")
        b = FolderEntry(path=RemotePath("data"), name="data")
        assert a == b

    @pytest.mark.spec("MOD-007")
    def test_folderentry_equality_ignores_name(self) -> None:
        a = FolderEntry(path=RemotePath("data"), name="data")
        b = FolderEntry(path=RemotePath("data"), name="other")
        assert a == b  # path-based equality ignores name

    @pytest.mark.spec("MOD-007")
    def test_folderentry_hash_by_path(self) -> None:
        a = FolderEntry(path=RemotePath("data"), name="data")
        b = FolderEntry(path=RemotePath("data"), name="data")
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    @pytest.mark.spec("MOD-007")
    def test_folderentry_inequality(self) -> None:
        a = FolderEntry(path=RemotePath("x"), name="x")
        b = FolderEntry(path=RemotePath("y"), name="y")
        assert a != b


class TestFolderEntry:
    """FolderEntry dataclass tests."""

    @pytest.mark.spec("MOD-006")
    def test_frozen(self) -> None:
        fe = FolderEntry(path=RemotePath("sub"), name="sub")
        with pytest.raises(dataclasses.FrozenInstanceError):
            fe.name = "other"  # type: ignore[misc]

    @pytest.mark.spec("MOD-006")
    def test_fields(self) -> None:
        fe = FolderEntry(path=RemotePath("a/b"), name="b")
        assert fe.path == RemotePath("a/b")
        assert fe.name == "b"

    @pytest.mark.spec("MOD-006")
    def test_not_equal_to_other_types(self) -> None:
        fe = FolderEntry(path=RemotePath("x"), name="x")
        assert fe != "x"
        assert fe.__eq__("x") is NotImplemented


class TestPathEntryProtocol:
    """PathEntry protocol structural subtyping tests."""

    @pytest.mark.spec("MOD-008")
    def test_fileinfo_satisfies_path_entry(self) -> None:
        fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=0, modified_at=NOW)
        assert isinstance(fi, PathEntry)

    @pytest.mark.spec("MOD-008")
    def test_folderentry_satisfies_path_entry(self) -> None:
        fe = FolderEntry(path=RemotePath("sub"), name="sub")
        assert isinstance(fe, PathEntry)

    @pytest.mark.spec("MOD-008")
    def test_folderinfo_satisfies_path_entry(self) -> None:
        fi = FolderInfo(path=RemotePath("a/b"), file_count=0, total_size=0)
        assert isinstance(fi, PathEntry)

    @pytest.mark.spec("MOD-008")
    def test_path_entry_uniform_iteration(self) -> None:
        entries: list[PathEntry] = [
            FileInfo(path=RemotePath("a.txt"), name="a.txt", size=0, modified_at=NOW),
            FolderEntry(path=RemotePath("sub"), name="sub"),
            FolderInfo(path=RemotePath("data"), file_count=3, total_size=500),
        ]
        names = [e.name for e in entries]
        paths = [str(e.path) for e in entries]
        assert names == ["a.txt", "sub", "data"]
        assert paths == ["a.txt", "sub", "data"]
