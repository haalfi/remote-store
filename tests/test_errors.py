"""Tests for error hierarchy — derived from sdd/specs/005-error-model.md."""

from __future__ import annotations

import pytest

from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)


class TestBaseError:
    """ERR-001: RemoteStoreError carries optional path and backend."""

    @pytest.mark.spec("ERR-001")
    def test_default_attributes(self) -> None:
        """RemoteStoreError carries optional path and backend (default None)."""
        e = RemoteStoreError("boom")
        assert e.path is None
        assert e.backend is None

    @pytest.mark.spec("ERR-001")
    def test_with_attributes(self) -> None:
        """RemoteStoreError accepts path and backend kwargs."""
        e = RemoteStoreError("boom", path="a/b.txt", backend="s3")
        assert e.path == "a/b.txt"
        assert e.backend == "s3"


class TestNotFound:
    """ERR-002: NotFound."""

    @pytest.mark.spec("ERR-002")
    def test_is_remote_store_error(self) -> None:
        assert issubclass(NotFound, RemoteStoreError)

    @pytest.mark.spec("ERR-002")
    def test_path(self) -> None:
        e = NotFound("missing", path="data/file.txt")
        assert e.path == "data/file.txt"


class TestAlreadyExists:
    """ERR-003: AlreadyExists."""

    @pytest.mark.spec("ERR-003")
    def test_is_remote_store_error(self) -> None:
        assert issubclass(AlreadyExists, RemoteStoreError)

    @pytest.mark.spec("ERR-003")
    def test_path(self) -> None:
        e = AlreadyExists("exists", path="data/file.txt")
        assert e.path == "data/file.txt"


class TestPermissionDenied:
    """ERR-004: PermissionDenied."""

    @pytest.mark.spec("ERR-004")
    def test_is_remote_store_error(self) -> None:
        assert issubclass(PermissionDenied, RemoteStoreError)

    @pytest.mark.spec("ERR-004")
    def test_attributes(self) -> None:
        e = PermissionDenied("denied", path="secret", backend="s3")
        assert e.path == "secret"
        assert e.backend == "s3"


class TestInvalidPath:
    """ERR-005: InvalidPath."""

    @pytest.mark.spec("ERR-005")
    def test_is_remote_store_error(self) -> None:
        assert issubclass(InvalidPath, RemoteStoreError)

    @pytest.mark.spec("ERR-005")
    def test_carries_path(self) -> None:
        e = InvalidPath("bad", path="foo/../bar")
        assert e.path == "foo/../bar"


class TestCapabilityNotSupported:
    """ERR-006: CapabilityNotSupported."""

    @pytest.mark.spec("ERR-006")
    def test_is_remote_store_error(self) -> None:
        assert issubclass(CapabilityNotSupported, RemoteStoreError)

    @pytest.mark.spec("ERR-006")
    def test_extra_attribute(self) -> None:
        e = CapabilityNotSupported("no atomic", capability="atomic_write", backend="sftp")
        assert e.capability == "atomic_write"
        assert e.backend == "sftp"


class TestBackendUnavailable:
    """ERR-007: BackendUnavailable."""

    @pytest.mark.spec("ERR-007")
    def test_is_remote_store_error(self) -> None:
        assert issubclass(BackendUnavailable, RemoteStoreError)

    @pytest.mark.spec("ERR-007")
    def test_backend(self) -> None:
        e = BackendUnavailable("down", backend="s3")
        assert e.backend == "s3"


class TestFlatHierarchy:
    """ERR-008: All errors inherit directly from RemoteStoreError."""

    @pytest.mark.spec("ERR-008")
    def test_all_errors_inherit_directly_from_base(self) -> None:
        """Concrete errors inherit from RemoteStoreError, not from each other."""
        concrete = [NotFound, AlreadyExists, PermissionDenied, InvalidPath, CapabilityNotSupported, BackendUnavailable]
        for cls in concrete:
            bases = cls.__mro__
            assert bases[1] is RemoteStoreError, f"{cls.__name__} does not directly inherit RemoteStoreError"


class TestStrRepr:
    """ERR-009: Meaningful str/repr output."""

    @pytest.mark.spec("ERR-009")
    def test_str_includes_context(self) -> None:
        e = NotFound("File not found", path="data/file.txt", backend="s3")
        s = str(e)
        assert "data/file.txt" in s
        assert "s3" in s

    @pytest.mark.spec("ERR-009")
    def test_repr_includes_class_name(self) -> None:
        e = NotFound("File not found", path="data/file.txt")
        r = repr(e)
        assert "NotFound" in r
        assert "data/file.txt" in r

    @pytest.mark.spec("ERR-009")
    def test_capability_str_includes_capability(self) -> None:
        e = CapabilityNotSupported("nope", capability="atomic_write")
        assert "atomic_write" in str(e)

    @pytest.mark.spec("ERR-009")
    def test_capability_repr_includes_capability(self) -> None:
        e = CapabilityNotSupported("nope", capability="atomic_write")
        assert "atomic_write" in repr(e)
