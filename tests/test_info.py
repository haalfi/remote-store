"""Tests for remote_store.info() runtime introspection."""

from __future__ import annotations

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
        result = remote_store.info()
        # Find any unavailable backend (extras-gated)
        for _name, info in result["backends"].items():
            if not info["available"]:
                assert info["class"] is None
                break

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
