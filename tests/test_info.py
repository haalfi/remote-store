"""Tests for remote_store.info() runtime introspection."""

from __future__ import annotations

import importlib.util
from unittest.mock import patch

import remote_store


class TestInfo:
    """Verify info() returns correct structure and data."""

    def test_returns_version(self) -> None:
        result = remote_store.info()
        assert result["version"] == remote_store.__version__

    def test_backends_section_is_dict(self) -> None:
        result = remote_store.info()
        assert isinstance(result["backends"], dict)

    def test_extensions_section_is_dict(self) -> None:
        result = remote_store.info()
        assert isinstance(result["extensions"], dict)

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

        # Ensure backends are registered, then temporarily remove 'local'.
        _register_builtin_backends()
        saved = _BACKEND_FACTORIES.pop("local")
        try:
            # Prevent info() from re-registering local.
            with patch("remote_store._registry._register_builtin_backends"):
                result = remote_store.info()
            assert result["backends"]["local"]["available"] is False
            assert result["backends"]["local"]["class"] is None
        finally:
            _BACKEND_FACTORIES["local"] = saved

    def test_top_level_keys(self) -> None:
        result = remote_store.info()
        assert set(result.keys()) == {"version", "backends", "extensions"}

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
        """Extensions with missing third-party deps report available=False."""
        original_find_spec = importlib.util.find_spec

        def _fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
            # Block pyarrow to make arrow/parquet unavailable.
            if name == "pyarrow":
                return None
            return original_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

        with patch("importlib.util.find_spec", side_effect=_fake_find_spec):
            result = remote_store.info()
            assert result["extensions"]["arrow"]["available"] is False
            assert result["extensions"]["parquet"]["available"] is False
            # Base extensions unaffected.
            assert result["extensions"]["batch"]["available"] is True
