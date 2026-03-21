"""Tests for RemotePath — derived from sdd/specs/004-path-model.md."""

from __future__ import annotations

import pytest

from remote_store._errors import InvalidPath
from remote_store._path import RemotePath

pytestmark = pytest.mark.os_sensitive


class TestRemotePathImmutability:
    """PATH-001: immutability."""

    @pytest.mark.spec("PATH-001")
    def test_immutable_setattr(self) -> None:
        p = RemotePath("a/b")
        with pytest.raises(AttributeError, match="immutable"):
            p.x = 1  # type: ignore[attr-defined]


class TestRemotePathNormalization:
    """PATH-002 through PATH-006: normalization rules."""

    @pytest.mark.spec("PATH-002")
    def test_backslash_to_forward_slash(self) -> None:
        assert str(RemotePath("a\\b\\c")) == "a/b/c"

    @pytest.mark.spec("PATH-003")
    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("foo/../bar", id="mid"),
            pytest.param("../bar", id="start"),
            pytest.param("..", id="bare"),
        ],
    )
    def test_double_dot_rejected(self, raw: str) -> None:
        with pytest.raises(InvalidPath):
            RemotePath(raw)

    @pytest.mark.spec("PATH-004")
    @pytest.mark.parametrize(
        "raw, expected",
        [
            pytest.param("/a/b/", "a/b", id="both"),
            pytest.param("/file.txt", "file.txt", id="leading"),
        ],
    )
    def test_strip_slashes(self, raw: str, expected: str) -> None:
        assert str(RemotePath(raw)) == expected

    @pytest.mark.spec("PATH-005")
    def test_collapse_consecutive_slashes(self) -> None:
        assert str(RemotePath("a///b")) == "a/b"

    @pytest.mark.spec("PATH-006")
    @pytest.mark.parametrize(
        "raw, expected",
        [
            pytest.param("a/./b", "a/b", id="single-dot"),
            pytest.param("./a/./b/.", "a/b", id="multiple-dots"),
        ],
    )
    def test_dot_segment_removal(self, raw: str, expected: str) -> None:
        assert str(RemotePath(raw)) == expected


class TestRemotePathValidation:
    """PATH-007 through PATH-008: input validation."""

    @pytest.mark.spec("PATH-007")
    def test_null_byte_rejected(self) -> None:
        with pytest.raises(InvalidPath):
            RemotePath("a/b\0c")

    @pytest.mark.spec("PATH-008")
    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("", id="empty"),
            pytest.param("/", id="slash-only"),
            pytest.param(".", id="dot-only"),
        ],
    )
    def test_empty_like_rejected(self, raw: str) -> None:
        with pytest.raises(InvalidPath):
            RemotePath(raw)


class TestRemotePathProperties:
    """PATH-009 through PATH-011, PATH-014: name, parent, parts, suffix."""

    @pytest.mark.spec("PATH-009")
    @pytest.mark.parametrize(
        "raw, expected",
        [
            pytest.param("a/b/c.txt", "c.txt", id="nested"),
            pytest.param("file.txt", "file.txt", id="single"),
        ],
    )
    def test_name(self, raw: str, expected: str) -> None:
        assert RemotePath(raw).name == expected

    @pytest.mark.spec("PATH-010")
    @pytest.mark.parametrize(
        "raw, expected",
        [
            pytest.param("a/b/c", RemotePath("a/b"), id="nested-parent"),
            pytest.param("file.txt", None, id="single-no-parent"),
        ],
    )
    def test_parent(self, raw: str, expected: RemotePath | None) -> None:
        assert RemotePath(raw).parent == expected

    @pytest.mark.spec("PATH-011")
    @pytest.mark.parametrize(
        "raw, expected",
        [
            pytest.param("a/b/c", ("a", "b", "c"), id="multi"),
            pytest.param("file.txt", ("file.txt",), id="single"),
        ],
    )
    def test_parts(self, raw: str, expected: tuple[str, ...]) -> None:
        assert RemotePath(raw).parts == expected

    @pytest.mark.spec("PATH-014")
    @pytest.mark.parametrize(
        "raw, expected",
        [
            pytest.param("file.tar.gz", ".gz", id="multi-ext"),
            pytest.param("noext", "", id="no-ext"),
            pytest.param("data.csv", ".csv", id="single-ext"),
            pytest.param(".gitignore", "", id="dotfile"),
        ],
    )
    def test_suffix(self, raw: str, expected: str) -> None:
        assert RemotePath(raw).suffix == expected


class TestRemotePathJoin:
    """PATH-012: ``/`` operator."""

    @pytest.mark.spec("PATH-012")
    @pytest.mark.parametrize(
        "right, expected",
        [
            pytest.param("b", "a/b", id="simple"),
            pytest.param("b/c", "a/b/c", id="nested"),
        ],
    )
    def test_join(self, right: str, expected: str) -> None:
        assert RemotePath("a") / right == RemotePath(expected)


class TestRemotePathEqualityHashing:
    """PATH-013: equality and hashing based on normalized path."""

    @pytest.mark.spec("PATH-013")
    def test_equality_and_hash_normalized(self) -> None:
        assert RemotePath("a/b") == RemotePath("a//b")
        assert hash(RemotePath("a/b")) == hash(RemotePath("a//b"))

    @pytest.mark.spec("PATH-013")
    def test_inequality_different_paths(self) -> None:
        assert RemotePath("a/b") != RemotePath("a/c")

    @pytest.mark.spec("PATH-013")
    def test_not_equal_to_string(self) -> None:
        assert RemotePath("a/b") != "a/b"


class TestRemotePathRoot:
    """PATH-015: RemotePath.ROOT — class-level sentinel for root folder."""

    @pytest.mark.spec("PATH-015")
    def test_str_and_repr(self) -> None:
        assert str(RemotePath.ROOT) == "."
        assert repr(RemotePath.ROOT) == "RemotePath('.')"

    @pytest.mark.spec("PATH-015")
    def test_properties(self) -> None:
        assert RemotePath.ROOT.name == "."
        assert RemotePath.ROOT.parent is None
        assert RemotePath.ROOT.parts == (".",)
        assert RemotePath.ROOT.suffix == ""

    @pytest.mark.spec("PATH-015")
    @pytest.mark.parametrize(
        "right, expected",
        [
            pytest.param("a", RemotePath("a"), id="simple"),
            pytest.param("a/b", RemotePath("a/b"), id="nested"),
        ],
    )
    def test_join_produces_normal_path(self, right: str, expected: RemotePath) -> None:
        assert RemotePath.ROOT / right == expected

    @pytest.mark.spec("PATH-015")
    def test_equality_hash_and_identity(self) -> None:
        assert RemotePath.ROOT == RemotePath.ROOT
        assert hash(RemotePath.ROOT) == hash(RemotePath.ROOT)
        assert RemotePath.ROOT is RemotePath.ROOT

    @pytest.mark.spec("PATH-015")
    def test_immutable(self) -> None:
        with pytest.raises(AttributeError, match="immutable"):
            RemotePath.ROOT.x = 1  # type: ignore[attr-defined]
        with pytest.raises(AttributeError, match="immutable"):
            del RemotePath.ROOT._path  # type: ignore[misc]

    @pytest.mark.spec("PATH-015")
    @pytest.mark.parametrize(
        "raw, expected",
        [
            pytest.param("", RemotePath.ROOT, id="empty-returns-root"),
            pytest.param("a/b", RemotePath("a/b"), id="nonempty-returns-path"),
        ],
    )
    def test_from_backend_path(self, raw: str, expected: RemotePath) -> None:
        result = RemotePath.from_backend_path(raw)
        assert result == expected
        if raw == "":
            assert result is RemotePath.ROOT

    @pytest.mark.spec("PATH-008")
    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("", id="empty"),
            pytest.param(".", id="dot"),
        ],
    )
    def test_constructor_still_rejects(self, raw: str) -> None:
        """PATH-008 must still reject empty/dot — ROOT is a separate sentinel."""
        with pytest.raises(InvalidPath):
            RemotePath(raw)
