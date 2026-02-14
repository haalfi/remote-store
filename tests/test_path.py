"""Tests for RemotePath — derived from docs/specs/path.md."""

from __future__ import annotations

import pytest

from remote_store._errors import InvalidPath
from remote_store._path import RemotePath

# -- PATH-001: Immutability --


@pytest.mark.spec("PATH-001")
def test_immutable_setattr() -> None:
    """RemotePath rejects attribute assignment."""
    p = RemotePath("a/b")
    with pytest.raises(AttributeError, match="immutable"):
        p.x = 1  # type: ignore[attr-defined]


# -- PATH-002: Backslash normalization --


@pytest.mark.spec("PATH-002")
def test_backslash_to_forward_slash() -> None:
    assert str(RemotePath("a\\b\\c")) == "a/b/c"


# -- PATH-003: Double-dot rejection --


@pytest.mark.spec("PATH-003")
def test_double_dot_rejected() -> None:
    with pytest.raises(InvalidPath):
        RemotePath("foo/../bar")


@pytest.mark.spec("PATH-003")
def test_double_dot_at_start() -> None:
    with pytest.raises(InvalidPath):
        RemotePath("../bar")


@pytest.mark.spec("PATH-003")
def test_double_dot_only() -> None:
    with pytest.raises(InvalidPath):
        RemotePath("..")


# -- PATH-004: Leading/trailing slash stripping --


@pytest.mark.spec("PATH-004")
def test_strip_leading_trailing_slashes() -> None:
    assert str(RemotePath("/a/b/")) == "a/b"


@pytest.mark.spec("PATH-004")
def test_strip_leading_slash() -> None:
    assert str(RemotePath("/file.txt")) == "file.txt"


# -- PATH-005: Consecutive slash collapsing --


@pytest.mark.spec("PATH-005")
def test_collapse_consecutive_slashes() -> None:
    assert str(RemotePath("a///b")) == "a/b"


# -- PATH-006: Dot segment removal --


@pytest.mark.spec("PATH-006")
def test_dot_segment_removal() -> None:
    assert str(RemotePath("a/./b")) == "a/b"


@pytest.mark.spec("PATH-006")
def test_multiple_dot_segments() -> None:
    assert str(RemotePath("./a/./b/.")) == "a/b"


# -- PATH-007: Null byte rejection --


@pytest.mark.spec("PATH-007")
def test_null_byte_rejected() -> None:
    with pytest.raises(InvalidPath):
        RemotePath("a/b\0c")


# -- PATH-008: Empty path rejection --


@pytest.mark.spec("PATH-008")
def test_empty_string_rejected() -> None:
    with pytest.raises(InvalidPath):
        RemotePath("")


@pytest.mark.spec("PATH-008")
def test_slash_only_rejected() -> None:
    with pytest.raises(InvalidPath):
        RemotePath("/")


@pytest.mark.spec("PATH-008")
def test_dot_only_rejected() -> None:
    with pytest.raises(InvalidPath):
        RemotePath(".")


# -- PATH-009: name property --


@pytest.mark.spec("PATH-009")
def test_name_returns_final_component() -> None:
    assert RemotePath("a/b/c.txt").name == "c.txt"


@pytest.mark.spec("PATH-009")
def test_name_single_component() -> None:
    assert RemotePath("file.txt").name == "file.txt"


# -- PATH-010: parent property --


@pytest.mark.spec("PATH-010")
def test_parent_returns_parent_path() -> None:
    assert RemotePath("a/b/c").parent == RemotePath("a/b")


@pytest.mark.spec("PATH-010")
def test_parent_none_for_single_component() -> None:
    assert RemotePath("file.txt").parent is None


# -- PATH-011: parts property --


@pytest.mark.spec("PATH-011")
def test_parts_tuple() -> None:
    assert RemotePath("a/b/c").parts == ("a", "b", "c")


@pytest.mark.spec("PATH-011")
def test_parts_single() -> None:
    assert RemotePath("file.txt").parts == ("file.txt",)


# -- PATH-012: Join operator --


@pytest.mark.spec("PATH-012")
def test_join_operator() -> None:
    assert RemotePath("a") / "b" == RemotePath("a/b")


@pytest.mark.spec("PATH-012")
def test_join_nested() -> None:
    assert RemotePath("a") / "b/c" == RemotePath("a/b/c")


# -- PATH-013: Equality and hashing --


@pytest.mark.spec("PATH-013")
def test_equality_normalized() -> None:
    assert RemotePath("a/b") == RemotePath("a//b")


@pytest.mark.spec("PATH-013")
def test_hash_normalized() -> None:
    assert hash(RemotePath("a/b")) == hash(RemotePath("a//b"))


@pytest.mark.spec("PATH-013")
def test_inequality_different_paths() -> None:
    assert RemotePath("a/b") != RemotePath("a/c")


@pytest.mark.spec("PATH-013")
def test_not_equal_to_string() -> None:
    assert RemotePath("a/b") != "a/b"


# -- PATH-014: Suffix property --


@pytest.mark.spec("PATH-014")
def test_suffix_with_extension() -> None:
    assert RemotePath("file.tar.gz").suffix == ".gz"


@pytest.mark.spec("PATH-014")
def test_suffix_no_extension() -> None:
    assert RemotePath("noext").suffix == ""


@pytest.mark.spec("PATH-014")
def test_suffix_single_extension() -> None:
    assert RemotePath("data.csv").suffix == ".csv"


@pytest.mark.spec("PATH-014")
def test_suffix_dotfile() -> None:
    assert RemotePath(".gitignore").suffix == ""
