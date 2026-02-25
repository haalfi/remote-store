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


class TestRegistryCloseOnError:
    """AF-009: close() must close all backends even when one raises."""

    def test_close_continues_after_error(self) -> None:
        """If a backend.close() raises, remaining backends are still closed."""
        with tempfile.TemporaryDirectory() as tmp:
            reg = Registry(_make_config(tmp))
            reg.get_store("main")

            # Patch the single backend's close() to raise
            backend = next(iter(reg._backends.values()))
            original_close = backend.close
            close_calls: list[str] = []

            def failing_close() -> None:
                close_calls.append("called")
                original_close()
                raise RuntimeError("simulated close failure")

            backend.close = failing_close  # type: ignore[assignment]

            with pytest.raises(RuntimeError, match="simulated close failure"):
                reg.close()

            assert len(close_calls) == 1
            assert len(reg._backends) == 0  # clear() ran despite error

    def test_close_clears_on_error(self) -> None:
        """_backends.clear() always runs, even when close() raises."""
        with tempfile.TemporaryDirectory() as tmp:
            reg = Registry(_make_config(tmp))
            reg.get_store("main")

            backend = next(iter(reg._backends.values()))
            backend.close = lambda: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[assignment,return-value]

            with pytest.raises(RuntimeError):
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

    @pytest.mark.spec("REG-008")
    def test_all_installed_backends_registered(self) -> None:
        """All backends whose dependencies are installed should be auto-registered."""
        from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends

        _register_builtin_backends()

        # local is always available (stdlib)
        assert "local" in _BACKEND_FACTORIES

        # Optional backends: registered if importable
        try:
            import s3fs  # noqa: F401

            assert "s3" in _BACKEND_FACTORIES
        except ImportError:
            pass

        try:
            import paramiko  # noqa: F401

            assert "sftp" in _BACKEND_FACTORIES
        except ImportError:
            pass

        try:
            import pyarrow  # noqa: F401
            import s3fs  # noqa: F401

            assert "s3-pyarrow" in _BACKEND_FACTORIES
        except ImportError:
            pass

        try:
            import azure.storage.filedatalake  # noqa: F401

            assert "azure" in _BACKEND_FACTORIES
        except ImportError:
            pass
