"""Tests for remote_store.info() runtime introspection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import remote_store
from remote_store._info import _EXTENSION_GATE


@pytest.mark.spec("BK-136")
class TestInfo:
    """Verify info() returns correct structure and data."""

    def test_returns_version(self) -> None:
        result = remote_store.info()
        assert result["version"] == remote_store.__version__

    def test_top_level_keys(self) -> None:
        result = remote_store.info()
        assert set(result.keys()) == {"version", "backends", "extensions"}

    def test_always_available_backends_present(self) -> None:
        result = remote_store.info()
        for name in ("local", "memory", "http"):
            assert result["backends"][name]["available"] is True
            assert result["backends"][name]["extras"] is None

    def test_optional_backends_have_extras(self) -> None:
        result = remote_store.info()
        expected = {
            "s3": "s3",
            "sftp": "sftp",
            "azure": "azure",
            "sql-blob": "sql",
            "sql-query": "sql-query",
            "s3-pyarrow": "s3-pyarrow",
        }
        for name, extras in expected.items():
            assert result["backends"][name]["extras"] == extras

    def test_always_available_extensions(self) -> None:
        result = remote_store.info()
        for name in ("batch", "cache", "glob", "integrity", "observe", "partition", "streams", "transfer"):
            assert result["extensions"][name]["available"] is True
            assert result["extensions"][name]["extras"] is None

    def test_optional_extensions_have_extras(self) -> None:
        result = remote_store.info()
        expected = {
            "arrow": "arrow",
            "parquet": "arrow",
            "otel": "otel",
            "pydantic": "pydantic",
            "yaml": "yaml",
            "dagster": "dagster",
        }
        for name, extras in expected.items():
            assert result["extensions"][name]["extras"] == extras

    def test_available_backend_includes_class(self) -> None:
        result = remote_store.info()
        local = result["backends"]["local"]
        assert "class" in local
        assert "LocalBackend" in local["class"]  # type: ignore[operator]

    def test_unavailable_backend_class_is_none(self) -> None:
        from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends

        _register_builtin_backends()
        saved = _BACKEND_FACTORIES.pop("local")
        try:
            with patch("remote_store._registry._register_builtin_backends"):
                result = remote_store.info()
            assert result["backends"]["local"]["available"] is False
            assert result["backends"]["local"]["class"] is None
        finally:
            _BACKEND_FACTORIES["local"] = saved

    def test_extensions_discovered_dynamically(self) -> None:
        """All extension modules under remote_store.ext are discovered."""
        import pkgutil

        import remote_store.ext as _ext_pkg

        expected_modules = {m.name for m in pkgutil.iter_modules(_ext_pkg.__path__)}
        result = remote_store.info()
        assert set(result["extensions"].keys()) == expected_modules

    def test_return_type_exports(self) -> None:
        """TypedDict types are importable from the package."""
        assert hasattr(remote_store, "InfoResult")
        assert hasattr(remote_store, "BackendInfo")
        assert hasattr(remote_store, "ExtensionInfo")

    def test_optional_extension_unavailable_when_dep_missing(self) -> None:
        """Extensions with missing gating deps report available=False."""
        fake_gate = {**_EXTENSION_GATE, "arrow": ("nonexistent_pkg_xyz",)}
        with patch("remote_store._info._EXTENSION_GATE", fake_gate):
            result = remote_store.info()
            assert result["extensions"]["arrow"]["available"] is False
            # Parquet still gated by real pyarrow — unaffected.
            assert result["extensions"]["parquet"]["available"] is True
            # Base extensions always available.
            assert result["extensions"]["batch"]["available"] is True

    def test_user_registered_backend_appears_in_info(self) -> None:
        """Backends registered after _register_builtin_backends appear in info()."""
        from remote_store._backend import Backend
        from remote_store._registry import _BACKEND_FACTORIES

        class _FakeBackend(Backend):
            pass

        _BACKEND_FACTORIES["fake-test"] = _FakeBackend  # type: ignore[assignment]
        try:
            result = remote_store.info()
            assert "fake-test" in result["backends"]
            assert result["backends"]["fake-test"]["available"] is True
            assert result["backends"]["fake-test"]["extras"] is None
        finally:
            del _BACKEND_FACTORIES["fake-test"]
