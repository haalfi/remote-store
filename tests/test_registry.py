"""Tests for registry — derived from docs/specs/registry.md."""

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


# -- REG-001: Construction and validation --


@pytest.mark.spec("REG-001")
def test_registry_validates_on_construction() -> None:
    bad_config = RegistryConfig(
        backends={},
        stores={"main": StoreProfile(backend="nonexistent")},
    )
    with pytest.raises(ValueError, match="nonexistent"):
        Registry(bad_config)


@pytest.mark.spec("REG-001")
def test_registry_construction_ok() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(_make_config(tmp))
        assert reg is not None


# -- REG-002: get_store --


@pytest.mark.spec("REG-002")
def test_get_store_returns_store() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(_make_config(tmp))
        store = reg.get_store("main")
        assert isinstance(store, Store)


# -- REG-003: Unknown store --


@pytest.mark.spec("REG-003")
def test_get_store_unknown_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(_make_config(tmp))
        with pytest.raises(KeyError, match="unknown_store"):
            reg.get_store("unknown_store")


# -- REG-004: Lazy instantiation --


@pytest.mark.spec("REG-004")
def test_lazy_instantiation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(_make_config(tmp))
        assert len(reg._backends) == 0
        reg.get_store("main")
        assert len(reg._backends) == 1


# -- REG-005: Backend sharing --


@pytest.mark.spec("REG-005")
def test_backend_shared_across_stores() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(_make_config(tmp))
        reg.get_store("main")
        reg.get_store("other")
        # Both stores reference "local" backend — should be the same instance
        assert len(reg._backends) == 1


# -- REG-006: close --


@pytest.mark.spec("REG-006")
def test_close_clears_backends() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(_make_config(tmp))
        reg.get_store("main")
        assert len(reg._backends) == 1
        reg.close()
        assert len(reg._backends) == 0


# -- REG-007: Context manager --


@pytest.mark.spec("REG-007")
def test_context_manager() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with Registry(_make_config(tmp)) as reg:
            store = reg.get_store("main")
            assert isinstance(store, Store)
        # After exiting, backends should be cleared
        assert len(reg._backends) == 0


# -- REG-008: Backend factory registry --


@pytest.mark.spec("REG-008")
def test_register_backend() -> None:
    from remote_store._registry import _BACKEND_FACTORIES

    # "local" should already be registered
    assert "local" in _BACKEND_FACTORIES
