"""Tests for error hierarchy — derived from docs/specs/errors.md."""

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

# -- ERR-001: Base error --


@pytest.mark.spec("ERR-001")
def test_base_error_default_attributes() -> None:
    """RemoteStoreError carries optional path and backend (default None)."""
    e = RemoteStoreError("boom")
    assert e.path is None
    assert e.backend is None


@pytest.mark.spec("ERR-001")
def test_base_error_with_attributes() -> None:
    """RemoteStoreError accepts path and backend kwargs."""
    e = RemoteStoreError("boom", path="a/b.txt", backend="s3")
    assert e.path == "a/b.txt"
    assert e.backend == "s3"


# -- ERR-002: NotFound --


@pytest.mark.spec("ERR-002")
def test_not_found_is_remote_store_error() -> None:
    assert issubclass(NotFound, RemoteStoreError)


@pytest.mark.spec("ERR-002")
def test_not_found_path() -> None:
    e = NotFound("missing", path="data/file.txt")
    assert e.path == "data/file.txt"


# -- ERR-003: AlreadyExists --


@pytest.mark.spec("ERR-003")
def test_already_exists_is_remote_store_error() -> None:
    assert issubclass(AlreadyExists, RemoteStoreError)


@pytest.mark.spec("ERR-003")
def test_already_exists_path() -> None:
    e = AlreadyExists("exists", path="data/file.txt")
    assert e.path == "data/file.txt"


# -- ERR-004: PermissionDenied --


@pytest.mark.spec("ERR-004")
def test_permission_denied_is_remote_store_error() -> None:
    assert issubclass(PermissionDenied, RemoteStoreError)


@pytest.mark.spec("ERR-004")
def test_permission_denied_attributes() -> None:
    e = PermissionDenied("denied", path="secret", backend="s3")
    assert e.path == "secret"
    assert e.backend == "s3"


# -- ERR-005: InvalidPath --


@pytest.mark.spec("ERR-005")
def test_invalid_path_is_remote_store_error() -> None:
    assert issubclass(InvalidPath, RemoteStoreError)


@pytest.mark.spec("ERR-005")
def test_invalid_path_carries_path() -> None:
    e = InvalidPath("bad", path="foo/../bar")
    assert e.path == "foo/../bar"


# -- ERR-006: CapabilityNotSupported --


@pytest.mark.spec("ERR-006")
def test_capability_not_supported_is_remote_store_error() -> None:
    assert issubclass(CapabilityNotSupported, RemoteStoreError)


@pytest.mark.spec("ERR-006")
def test_capability_not_supported_extra_attribute() -> None:
    e = CapabilityNotSupported("no atomic", capability="atomic_write", backend="sftp")
    assert e.capability == "atomic_write"
    assert e.backend == "sftp"


# -- ERR-007: BackendUnavailable --


@pytest.mark.spec("ERR-007")
def test_backend_unavailable_is_remote_store_error() -> None:
    assert issubclass(BackendUnavailable, RemoteStoreError)


@pytest.mark.spec("ERR-007")
def test_backend_unavailable_backend() -> None:
    e = BackendUnavailable("down", backend="s3")
    assert e.backend == "s3"


# -- ERR-008: Flat hierarchy --


@pytest.mark.spec("ERR-008")
def test_all_errors_inherit_directly_from_base() -> None:
    """Concrete errors inherit from RemoteStoreError, not from each other."""
    concrete = [NotFound, AlreadyExists, PermissionDenied, InvalidPath, CapabilityNotSupported, BackendUnavailable]
    for cls in concrete:
        bases = cls.__mro__
        # Must have RemoteStoreError as direct parent (index 1 in MRO)
        assert bases[1] is RemoteStoreError, f"{cls.__name__} does not directly inherit RemoteStoreError"


# -- ERR-009: Meaningful str/repr --


@pytest.mark.spec("ERR-009")
def test_str_includes_context() -> None:
    e = NotFound("File not found", path="data/file.txt", backend="s3")
    s = str(e)
    assert "data/file.txt" in s
    assert "s3" in s


@pytest.mark.spec("ERR-009")
def test_repr_includes_class_name() -> None:
    e = NotFound("File not found", path="data/file.txt")
    r = repr(e)
    assert "NotFound" in r
    assert "data/file.txt" in r


@pytest.mark.spec("ERR-009")
def test_capability_str_includes_capability() -> None:
    e = CapabilityNotSupported("nope", capability="atomic_write")
    assert "atomic_write" in str(e)


@pytest.mark.spec("ERR-009")
def test_capability_repr_includes_capability() -> None:
    e = CapabilityNotSupported("nope", capability="atomic_write")
    assert "atomic_write" in repr(e)
