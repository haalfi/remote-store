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
        """RemotePath rejects attribute assignment."""
        p = RemotePath("a/b")
        with pytest.raises(AttributeError, match="immutable"):
            p.x = 1  # type: ignore[attr-defined]


class TestRemotePathNormalization:
    """PATH-002 through PATH-006: normalization rules."""

    @pytest.mark.spec("PATH-002")
    def test_backslash_to_forward_slash(self) -> None:
        assert str(RemotePath("a\\b\\c")) == "a/b/c"

    @pytest.mark.spec("PATH-003")
    def test_double_dot_rejected(self) -> None:
        with pytest.raises(InvalidPath):
            RemotePath("foo/../bar")

    @pytest.mark.spec("PATH-003")
    def test_double_dot_at_start(self) -> None:
        with pytest.raises(InvalidPath):
            RemotePath("../bar")

    @pytest.mark.spec("PATH-003")
    def test_double_dot_only(self) -> None:
        with pytest.raises(InvalidPath):
            RemotePath("..")

    @pytest.mark.spec("PATH-004")
    def test_strip_leading_trailing_slashes(self) -> None:
        assert str(RemotePath("/a/b/")) == "a/b"

    @pytest.mark.spec("PATH-004")
    def test_strip_leading_slash(self) -> None:
        assert str(RemotePath("/file.txt")) == "file.txt"

    @pytest.mark.spec("PATH-005")
    def test_collapse_consecutive_slashes(self) -> None:
        assert str(RemotePath("a///b")) == "a/b"

    @pytest.mark.spec("PATH-006")
    def test_dot_segment_removal(self) -> None:
        assert str(RemotePath("a/./b")) == "a/b"

    @pytest.mark.spec("PATH-006")
    def test_multiple_dot_segments(self) -> None:
        assert str(RemotePath("./a/./b/.")) == "a/b"


class TestRemotePathValidation:
    """PATH-007 through PATH-008: input validation."""

    @pytest.mark.spec("PATH-007")
    def test_null_byte_rejected(self) -> None:
        with pytest.raises(InvalidPath):
            RemotePath("a/b\0c")

    @pytest.mark.spec("PATH-008")
    def test_empty_string_rejected(self) -> None:
        with pytest.raises(InvalidPath):
            RemotePath("")

    @pytest.mark.spec("PATH-008")
    def test_slash_only_rejected(self) -> None:
        with pytest.raises(InvalidPath):
            RemotePath("/")

    @pytest.mark.spec("PATH-008")
    def test_dot_only_rejected(self) -> None:
        with pytest.raises(InvalidPath):
            RemotePath(".")


class TestRemotePathProperties:
    """PATH-009 through PATH-011, PATH-014: name, parent, parts, suffix."""

    @pytest.mark.spec("PATH-009")
    def test_name_returns_final_component(self) -> None:
        assert RemotePath("a/b/c.txt").name == "c.txt"

    @pytest.mark.spec("PATH-009")
    def test_name_single_component(self) -> None:
        assert RemotePath("file.txt").name == "file.txt"

    @pytest.mark.spec("PATH-010")
    def test_parent_returns_parent_path(self) -> None:
        assert RemotePath("a/b/c").parent == RemotePath("a/b")

    @pytest.mark.spec("PATH-010")
    def test_parent_none_for_single_component(self) -> None:
        assert RemotePath("file.txt").parent is None

    @pytest.mark.spec("PATH-011")
    def test_parts_tuple(self) -> None:
        assert RemotePath("a/b/c").parts == ("a", "b", "c")

    @pytest.mark.spec("PATH-011")
    def test_parts_single(self) -> None:
        assert RemotePath("file.txt").parts == ("file.txt",)

    @pytest.mark.spec("PATH-014")
    def test_suffix_with_extension(self) -> None:
        assert RemotePath("file.tar.gz").suffix == ".gz"

    @pytest.mark.spec("PATH-014")
    def test_suffix_no_extension(self) -> None:
        assert RemotePath("noext").suffix == ""

    @pytest.mark.spec("PATH-014")
    def test_suffix_single_extension(self) -> None:
        assert RemotePath("data.csv").suffix == ".csv"

    @pytest.mark.spec("PATH-014")
    def test_suffix_dotfile(self) -> None:
        assert RemotePath(".gitignore").suffix == ""


class TestRemotePathJoin:
    """PATH-012: ``/`` operator."""

    @pytest.mark.spec("PATH-012")
    def test_join_operator(self) -> None:
        assert RemotePath("a") / "b" == RemotePath("a/b")

    @pytest.mark.spec("PATH-012")
    def test_join_nested(self) -> None:
        assert RemotePath("a") / "b/c" == RemotePath("a/b/c")


class TestRemotePathEqualityHashing:
    """PATH-013: equality and hashing based on normalized path."""

    @pytest.mark.spec("PATH-013")
    def test_equality_normalized(self) -> None:
        assert RemotePath("a/b") == RemotePath("a//b")

    @pytest.mark.spec("PATH-013")
    def test_hash_normalized(self) -> None:
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
    def test_str_is_dot(self) -> None:
        assert str(RemotePath.ROOT) == "."

    @pytest.mark.spec("PATH-015")
    def test_repr(self) -> None:
        assert repr(RemotePath.ROOT) == "RemotePath('.')"

    @pytest.mark.spec("PATH-015")
    def test_name_is_dot(self) -> None:
        assert RemotePath.ROOT.name == "."

    @pytest.mark.spec("PATH-015")
    def test_parent_is_none(self) -> None:
        assert RemotePath.ROOT.parent is None

    @pytest.mark.spec("PATH-015")
    def test_parts(self) -> None:
        assert RemotePath.ROOT.parts == (".",)

    @pytest.mark.spec("PATH-015")
    def test_suffix_is_empty(self) -> None:
        assert RemotePath.ROOT.suffix == ""

    @pytest.mark.spec("PATH-015")
    def test_join_produces_normal_path(self) -> None:
        assert RemotePath("a") == RemotePath.ROOT / "a"

    @pytest.mark.spec("PATH-015")
    def test_join_nested(self) -> None:
        assert RemotePath("a/b") == RemotePath.ROOT / "a/b"

    @pytest.mark.spec("PATH-015")
    def test_equality(self) -> None:
        assert RemotePath.ROOT == RemotePath.ROOT

    @pytest.mark.spec("PATH-015")
    def test_hash(self) -> None:
        assert hash(RemotePath.ROOT) == hash(RemotePath.ROOT)

    @pytest.mark.spec("PATH-015")
    def test_singleton_identity(self) -> None:
        assert RemotePath.ROOT is RemotePath.ROOT

    @pytest.mark.spec("PATH-015")
    def test_immutable_setattr(self) -> None:
        with pytest.raises(AttributeError, match="immutable"):
            RemotePath.ROOT.x = 1  # type: ignore[attr-defined]

    @pytest.mark.spec("PATH-015")
    def test_immutable_delattr(self) -> None:
        with pytest.raises(AttributeError, match="immutable"):
            del RemotePath.ROOT._path  # type: ignore[misc]

    @pytest.mark.spec("PATH-015")
    def test_from_backend_path_empty(self) -> None:
        """from_backend_path('') returns ROOT."""
        assert RemotePath.from_backend_path("") is RemotePath.ROOT

    @pytest.mark.spec("PATH-015")
    def test_from_backend_path_nonempty(self) -> None:
        """from_backend_path('a/b') returns RemotePath('a/b')."""
        assert RemotePath.from_backend_path("a/b") == RemotePath("a/b")

    @pytest.mark.spec("PATH-008")
    def test_empty_string_still_rejected(self) -> None:
        """PATH-008 must still reject empty string — ROOT is a separate sentinel."""
        with pytest.raises(InvalidPath):
            RemotePath("")

    @pytest.mark.spec("PATH-008")
    def test_dot_still_rejected(self) -> None:
        """PATH-008 must still reject '.' via constructor."""
        with pytest.raises(InvalidPath):
            RemotePath(".")
