"""Tests for registry — derived from sdd/specs/002-registry-config.md (REG sections)."""

from __future__ import annotations

import tempfile

import pytest

from remote_store._config import BackendConfig, RegistryConfig, StoreProfile
from remote_store._registry import Registry
from remote_store._store import Store


def _make_config(root: str) -> RegistryConfig:
    return RegistryConfig(
        backends={"local": BackendConfig(type="local", options={"root": root})},
        stores={
            "main": StoreProfile(backend="local", root_path="data"),
            "other": StoreProfile(backend="local", root_path="other"),
        },
    )


class TestRegistryConstruction:
    """REG-001: Construction and validation."""

    @pytest.mark.spec("REG-001")
    def test_validates_on_construction(self) -> None:
        bad_config = RegistryConfig(
            backends={},
            stores={"main": StoreProfile(backend="nonexistent")},
        )
        with pytest.raises(ValueError, match="nonexistent"):
            Registry(bad_config)

    @pytest.mark.spec("REG-001")
    def test_construction_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg = Registry(_make_config(tmp))
            assert reg is not None


class TestRegistryGetStore:
    """REG-002 through REG-003: get_store behavior."""

    @pytest.mark.spec("REG-002")
    def test_returns_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg = Registry(_make_config(tmp))
            store = reg.get_store("main")
            assert isinstance(store, Store)

    @pytest.mark.spec("REG-003")
    def test_unknown_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg = Registry(_make_config(tmp))
            with pytest.raises(KeyError, match="unknown_store"):
                reg.get_store("unknown_store")


class TestRegistryBackendLifecycle:
    """REG-004 through REG-006: lazy instantiation, sharing, close."""

    @pytest.mark.spec("REG-004")
    def test_lazy_instantiation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg = Registry(_make_config(tmp))
            assert len(reg._backends) == 0
            reg.get_store("main")
            assert len(reg._backends) == 1

    @pytest.mark.spec("REG-005")
    def test_backend_shared_across_stores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg = Registry(_make_config(tmp))
            reg.get_store("main")
            reg.get_store("other")
            assert len(reg._backends) == 1

    @pytest.mark.spec("REG-006")
    def test_close_clears_backends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg = Registry(_make_config(tmp))
            reg.get_store("main")
            assert len(reg._backends) == 1
            reg.close()
            assert len(reg._backends) == 0


class TestRegistryContextManager:
    """REG-007: Context manager support."""

    @pytest.mark.spec("REG-007")
    def test_context_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with Registry(_make_config(tmp)) as reg:
                store = reg.get_store("main")
                assert isinstance(store, Store)
            assert len(reg._backends) == 0


class TestRegistryBackendFactory:
    """REG-008: Backend factory registry."""

    @pytest.mark.spec("REG-008")
    def test_register_backend(self) -> None:
        from remote_store._registry import _BACKEND_FACTORIES

        assert "local" in _BACKEND_FACTORIES
