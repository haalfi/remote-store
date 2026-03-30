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


@pytest.fixture
def registry():
    with tempfile.TemporaryDirectory() as tmp:
        yield Registry(_make_config(tmp)), tmp


class TestRegistryCore:
    """REG-001 through REG-007: Construction, get_store, lifecycle, context manager."""

    @pytest.mark.spec("REG-001")
    def test_validates_on_construction(self) -> None:
        bad_config = RegistryConfig(
            backends={},
            stores={"main": StoreProfile(backend="nonexistent")},
        )
        with pytest.raises(ValueError, match="nonexistent"):
            Registry(bad_config)

    @pytest.mark.spec("REG-001")
    def test_construction_ok(self, registry) -> None:
        reg, _ = registry
        assert reg is not None

    @pytest.mark.spec("REG-002")
    def test_returns_store(self, registry) -> None:
        reg, _ = registry
        store = reg.get_store("main")
        assert isinstance(store, Store)
        store.write("probe.txt", b"ok")
        assert store.read_bytes("probe.txt") == b"ok"

    @pytest.mark.spec("REG-003")
    def test_unknown_raises(self, registry) -> None:
        reg, _ = registry
        with pytest.raises(KeyError, match="unknown_store"):
            reg.get_store("unknown_store")

    @pytest.mark.spec("REG-004")
    def test_lazy_instantiation(self, registry) -> None:
        reg, _ = registry
        assert len(reg._backends) == 0
        reg.get_store("main")
        assert len(reg._backends) == 1

    @pytest.mark.spec("REG-005")
    def test_backend_shared_across_stores(self, registry) -> None:
        reg, _ = registry
        reg.get_store("main")
        reg.get_store("other")
        assert len(reg._backends) == 1

    @pytest.mark.spec("REG-006")
    def test_close_clears_backends(self, registry) -> None:
        reg, _ = registry
        reg.get_store("main")
        assert len(reg._backends) == 1
        reg.close()
        assert len(reg._backends) == 0

    @pytest.mark.spec("REG-007")
    def test_context_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with Registry(_make_config(tmp)) as reg:
                store = reg.get_store("main")
                assert isinstance(store, Store)
                store.write("probe.txt", b"ok")
                assert store.read_bytes("probe.txt") == b"ok"
            assert len(reg._backends) == 0


class TestRegistryStoreOwnership:
    """REG-005 / ID-041: Stores from get_store() must not own the shared backend."""

    @pytest.mark.spec("REG-005")
    def test_get_store_close_does_not_close_shared_backend(self, registry) -> None:
        reg, _ = registry
        s1 = reg.get_store("main")
        s2 = reg.get_store("other")
        s1.write("test.txt", b"hello")
        s1.close()
        assert s2.exists("test.txt") is False  # different root_path
        s2.write("test.txt", b"world")
        assert s2.read_bytes("test.txt") == b"world"
        reg.close()


class TestRegistryCloseOnError:
    """AF-009: close() must close all backends even when one raises."""

    @pytest.mark.parametrize(
        "use_lambda",
        [
            pytest.param(False, id="explicit_failing_close"),
            pytest.param(True, id="lambda_failing_close"),
        ],
    )
    def test_close_clears_on_error(self, registry, use_lambda: bool) -> None:
        reg, _ = registry
        reg.get_store("main")
        backend = next(iter(reg._backends.values()))
        if use_lambda:
            backend.close = lambda: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[assignment]
        else:
            original_close = backend.close
            close_calls: list[str] = []

            def failing_close() -> None:
                close_calls.append("called")
                original_close()
                raise RuntimeError("simulated close failure")

            backend.close = failing_close  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="boom|simulated close failure"):
            reg.close()
        if not use_lambda:
            assert len(close_calls) == 1
        assert len(reg._backends) == 0

    def test_close_multi_backend_continues_after_first_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            config = RegistryConfig(
                backends={
                    "local1": BackendConfig(type="local", options={"root": tmp1}),
                    "local2": BackendConfig(type="local", options={"root": tmp2}),
                },
                stores={
                    "s1": StoreProfile(backend="local1", root_path="a"),
                    "s2": StoreProfile(backend="local2", root_path="b"),
                },
            )
            reg = Registry(config)
            reg.get_store("s1")
            reg.get_store("s2")
            assert len(reg._backends) == 2

            close_order: list[str] = []
            b1, b2 = reg._backends["local1"], reg._backends["local2"]
            orig1, orig2 = b1.close, b2.close

            def failing_close1() -> None:
                close_order.append("local1")
                orig1()
                raise RuntimeError("backend1 failed")

            def tracking_close2() -> None:
                close_order.append("local2")
                orig2()

            b1.close = failing_close1  # type: ignore[assignment]
            b2.close = tracking_close2  # type: ignore[assignment]

            with pytest.raises(RuntimeError, match="backend1 failed"):
                reg.close()
            assert "local1" in close_order
            assert "local2" in close_order
            assert len(reg._backends) == 0


class TestRegistryBackendFactory:
    """REG-008: Backend factory registry."""

    @pytest.mark.spec("REG-008")
    def test_register_backend(self) -> None:
        from remote_store._registry import _BACKEND_FACTORIES

        assert "local" in _BACKEND_FACTORIES

    @pytest.mark.spec("REG-008")
    @pytest.mark.parametrize(
        ("import_path", "backend_key"),
        [
            pytest.param("s3fs", "s3", id="s3"),
            pytest.param("paramiko", "sftp", id="sftp"),
            pytest.param("azure.storage.filedatalake", "azure", id="azure"),
        ],
    )
    def test_optional_backend_registered_if_importable(self, import_path: str, backend_key: str) -> None:
        from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends

        _register_builtin_backends()
        try:
            __import__(import_path)
            assert backend_key in _BACKEND_FACTORIES
        except ImportError:
            pass

    @pytest.mark.spec("REG-008")
    def test_s3_pyarrow_registered_if_importable(self) -> None:
        from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends

        _register_builtin_backends()
        try:
            import pyarrow  # noqa: F401
            import s3fs  # noqa: F401

            assert "s3-pyarrow" in _BACKEND_FACTORIES
        except ImportError:
            pass
