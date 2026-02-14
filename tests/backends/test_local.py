"""Local backend specific tests."""

from __future__ import annotations

import tempfile

import pytest

from remote_store._errors import InvalidPath
from remote_store.backends._local import LocalBackend


@pytest.fixture
def local_backend() -> LocalBackend:
    with tempfile.TemporaryDirectory() as tmp:
        yield LocalBackend(root=tmp)  # type: ignore[misc]


class TestLocalBackendErrorMapping:
    """BE-021: Backend-native exceptions never leak."""

    @pytest.mark.spec("BE-021")
    def test_path_traversal_rejected(self, local_backend: LocalBackend) -> None:
        """Resolved paths must stay within root."""
        with pytest.raises(InvalidPath):
            local_backend.read("../../etc/passwd")

    @pytest.mark.spec("BE-021")
    def test_native_errors_mapped(self, local_backend: LocalBackend) -> None:
        """FileNotFoundError maps to NotFound."""
        from remote_store._errors import NotFound

        with pytest.raises(NotFound):
            local_backend.read_bytes("nonexistent.txt")


class TestLocalBackendIdentity:
    """BE-002: Local backend name."""

    @pytest.mark.spec("BE-002")
    def test_name(self, local_backend: LocalBackend) -> None:
        assert local_backend.name == "local"
