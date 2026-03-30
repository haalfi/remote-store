"""Runtime feature introspection for remote-store."""

from __future__ import annotations

import importlib.util
from typing import Any


def info() -> dict[str, Any]:
    """Return a structured summary of available backends and extensions.

    Populates the backend registry, then probes each backend and optional
    extension for availability in the current environment.

    Returns:
        A dict with keys ``version``, ``backends``, and ``extensions``.
    """
    from remote_store import __version__
    from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends

    _register_builtin_backends()

    # Backend metadata: type string → extras required to install.
    _BACKEND_EXTRAS: dict[str, str | None] = {
        "local": None,
        "memory": None,
        "http": None,
        "s3": "s3",
        "s3-pyarrow": "s3-pyarrow",
        "sftp": "sftp",
        "azure": "azure",
        "sql-blob": "sql",
        "sql-query": "sql-query",
    }

    backends: dict[str, dict[str, Any]] = {}
    for type_name, extras in _BACKEND_EXTRAS.items():
        available = type_name in _BACKEND_FACTORIES
        entry: dict[str, Any] = {
            "available": available,
            "extras": extras,
        }
        if available:
            cls = _BACKEND_FACTORIES[type_name]
            entry["class"] = f"{cls.__module__}.{cls.__qualname__}"
        backends[type_name] = entry

    # Extension metadata: module suffix → extras required.
    _EXTENSION_EXTRAS: dict[str, str | None] = {
        "batch": None,
        "cache": None,
        "glob": None,
        "integrity": None,
        "observe": None,
        "partition": None,
        "streams": None,
        "transfer": None,
        "arrow": "arrow",
        "parquet": "arrow",
        "otel": "otel",
        "pydantic": "pydantic",
        "yaml": "yaml",
        "dagster": "dagster",
    }

    extensions: dict[str, dict[str, Any]] = {}
    for name, extras in _EXTENSION_EXTRAS.items():
        module_name = f"remote_store.ext.{name}"
        available = importlib.util.find_spec(module_name) is not None
        extensions[name] = {
            "available": available,
            "extras": extras,
        }

    return {
        "version": __version__,
        "backends": backends,
        "extensions": extensions,
    }
