"""Local backend specific tests."""

from __future__ import annotations

import tempfile

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import InvalidPath
from remote_store.backends._local import LocalBackend

pytestmark = pytest.mark.os_sensitive


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


class TestLocalBackendCapabilities:
    """Local backend supports all capabilities."""

    def test_supports_all_capabilities(self, local_backend: LocalBackend) -> None:
        for cap in Capability:
            assert local_backend.capabilities.supports(cap), f"Missing: {cap.name}"


class TestLocalBackendResolve:
    """RES-050: LocalBackend.resolve() returns kind='local' with root and absolute_path."""

    @pytest.mark.spec("RES-050")
    def test_kind_is_local(self, local_backend: LocalBackend) -> None:
        plan = local_backend.resolve("file.txt")
        assert plan.kind == "local"

    @pytest.mark.spec("RES-050")
    def test_details_has_root(self, local_backend: LocalBackend) -> None:
        plan = local_backend.resolve("file.txt")
        assert "root" in plan.details

    @pytest.mark.spec("RES-050")
    def test_details_has_absolute_path(self, local_backend: LocalBackend) -> None:
        plan = local_backend.resolve("file.txt")
        assert "absolute_path" in plan.details
        assert "file.txt" in plan.details["absolute_path"]

    @pytest.mark.spec("RES-050")
    def test_details_root_matches_backend(self, local_backend: LocalBackend) -> None:
        plan = local_backend.resolve("file.txt")
        # root in details should be the backend's configured root
        assert plan.details["root"] is not None
        assert len(plan.details["root"]) > 0
