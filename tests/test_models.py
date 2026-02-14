"""Tests for models — derived from docs/specs/models.md."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from remote_store._models import FileInfo, FolderInfo, RemoteFile, RemoteFolder
from remote_store._path import RemotePath

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


# -- MOD-001: FileInfo immutability --


@pytest.mark.spec("MOD-001")
def test_fileinfo_frozen() -> None:
    fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=100, modified_at=NOW)
    with pytest.raises(dataclasses.FrozenInstanceError):
        fi.size = 200  # type: ignore[misc]


# -- MOD-002: FileInfo required fields --


@pytest.mark.spec("MOD-002")
def test_fileinfo_required_fields() -> None:
    fi = FileInfo(path=RemotePath("data/file.csv"), name="file.csv", size=42, modified_at=NOW)
    assert fi.path == RemotePath("data/file.csv")
    assert fi.name == "file.csv"
    assert fi.size == 42
    assert fi.modified_at == NOW


# -- MOD-003: FileInfo optional fields --


@pytest.mark.spec("MOD-003")
def test_fileinfo_defaults() -> None:
    fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=0, modified_at=NOW)
    assert fi.checksum is None
    assert fi.content_type is None
    assert fi.extra == {}


@pytest.mark.spec("MOD-003")
def test_fileinfo_optional_set() -> None:
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


# -- MOD-004: FolderInfo required fields --


@pytest.mark.spec("MOD-004")
def test_folderinfo_frozen() -> None:
    fi = FolderInfo(path=RemotePath("data"), file_count=5, total_size=1000)
    with pytest.raises(dataclasses.FrozenInstanceError):
        fi.file_count = 10  # type: ignore[misc]


@pytest.mark.spec("MOD-004")
def test_folderinfo_required_fields() -> None:
    fi = FolderInfo(path=RemotePath("data"), file_count=5, total_size=1000)
    assert fi.path == RemotePath("data")
    assert fi.file_count == 5
    assert fi.total_size == 1000


# -- MOD-005: FolderInfo optional fields --


@pytest.mark.spec("MOD-005")
def test_folderinfo_defaults() -> None:
    fi = FolderInfo(path=RemotePath("data"), file_count=0, total_size=0)
    assert fi.modified_at is None
    assert fi.extra == {}


@pytest.mark.spec("MOD-005")
def test_folderinfo_optional_set() -> None:
    fi = FolderInfo(path=RemotePath("data"), file_count=5, total_size=1000, modified_at=NOW, extra={"key": "val"})
    assert fi.modified_at == NOW
    assert fi.extra == {"key": "val"}


# -- MOD-006: RemoteFile and RemoteFolder --


@pytest.mark.spec("MOD-006")
def test_remotefile_holds_path() -> None:
    rf = RemoteFile(path=RemotePath("a/b.txt"))
    assert rf.path == RemotePath("a/b.txt")


@pytest.mark.spec("MOD-006")
def test_remotefile_frozen() -> None:
    rf = RemoteFile(path=RemotePath("a.txt"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        rf.path = RemotePath("b.txt")  # type: ignore[misc]


@pytest.mark.spec("MOD-006")
def test_remotefolder_holds_path() -> None:
    rf = RemoteFolder(path=RemotePath("data"))
    assert rf.path == RemotePath("data")


@pytest.mark.spec("MOD-006")
def test_remotefolder_frozen() -> None:
    rf = RemoteFolder(path=RemotePath("data"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        rf.path = RemotePath("other")  # type: ignore[misc]


# -- MOD-007: Equality and hashing --


@pytest.mark.spec("MOD-007")
def test_fileinfo_equality_by_path() -> None:
    a = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=10, modified_at=NOW)
    b = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=99, modified_at=NOW)
    assert a == b


@pytest.mark.spec("MOD-007")
def test_fileinfo_hash_by_path() -> None:
    a = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=10, modified_at=NOW)
    b = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=99, modified_at=NOW)
    assert hash(a) == hash(b)


@pytest.mark.spec("MOD-007")
def test_folderinfo_equality_by_path() -> None:
    a = FolderInfo(path=RemotePath("data"), file_count=1, total_size=10)
    b = FolderInfo(path=RemotePath("data"), file_count=9, total_size=99)
    assert a == b


@pytest.mark.spec("MOD-007")
def test_remotefile_equality() -> None:
    assert RemoteFile(path=RemotePath("a.txt")) == RemoteFile(path=RemotePath("a.txt"))


@pytest.mark.spec("MOD-007")
def test_remotefolder_equality() -> None:
    assert RemoteFolder(path=RemotePath("data")) == RemoteFolder(path=RemotePath("data"))


@pytest.mark.spec("MOD-007")
def test_remotefile_not_equal_to_remotefolder() -> None:
    assert RemoteFile(path=RemotePath("a")) != RemoteFolder(path=RemotePath("a"))
