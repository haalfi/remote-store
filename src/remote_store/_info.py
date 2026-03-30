"""Runtime feature introspection for remote-store."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
from typing import TypedDict

# TypedDict with "class" key requires functional syntax (reserved word).
BackendInfo = TypedDict(
    "BackendInfo",
    {
        "available": bool,
        "extras": str | None,
        "class": str | None,
    },
)


class ExtensionInfo(TypedDict):
    """Information about a single extension."""

    available: bool
    extras: str | None


class InfoResult(TypedDict):
    """Structured result of :func:`info`."""

    version: str
    backends: dict[str, BackendInfo]
    extensions: dict[str, ExtensionInfo]


# Extras mapping: type string → pip extra name (None = always available).
# This is the only piece that cannot be discovered at runtime.
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

_EXTENSION_EXTRAS: dict[str, str | None] = {
    "arrow": "arrow",
    "parquet": "arrow",
    "otel": "otel",
    "pydantic": "pydantic",
    "yaml": "yaml",
    "dagster": "dagster",
}

# Third-party package(s) that gate each optional extension.
# If ANY listed package is importable, the extension is available.
# Base extensions (extras=None) are always available.
_EXTENSION_GATE: dict[str, tuple[str, ...]] = {
    "arrow": ("pyarrow",),
    "parquet": ("pyarrow",),
    "otel": ("opentelemetry",),
    "pydantic": ("pydantic",),
    "yaml": ("yaml", "ruamel.yaml"),
    "dagster": ("dagster",),
}


def info() -> InfoResult:
    """Return a structured summary of available backends and extensions.

    Populates the backend registry, then probes each backend and optional
    extension for availability in the current environment.

    Returns:
        A :class:`InfoResult` with keys ``version``, ``backends``, and
        ``extensions``.
    """
    from remote_store import __version__
    from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends

    _register_builtin_backends()

    # --- Backends: registry is source of truth for availability ----------
    backends: dict[str, BackendInfo] = {}
    # Include all known backends (extras mapping) plus any extra registered
    # backends not in the mapping (e.g. user-registered backends).
    all_backend_keys = dict.fromkeys([*_BACKEND_EXTRAS, *_BACKEND_FACTORIES])
    for type_name in all_backend_keys:
        available = type_name in _BACKEND_FACTORIES
        cls_name: str | None = None
        if available:
            cls = _BACKEND_FACTORIES[type_name]
            cls_name = f"{cls.__module__}.{cls.__qualname__}"
        backends[type_name] = {
            "available": available,
            "extras": _BACKEND_EXTRAS.get(type_name),
            "class": cls_name,
        }

    # --- Extensions: discover modules dynamically via pkgutil ------------
    import remote_store.ext as _ext_pkg

    extensions: dict[str, ExtensionInfo] = {}
    for module_info in pkgutil.iter_modules(_ext_pkg.__path__):
        name = module_info.name
        gate_pkgs = _EXTENSION_GATE.get(name)
        available = True if gate_pkgs is None else any(importlib.util.find_spec(pkg) is not None for pkg in gate_pkgs)
        extensions[name] = {
            "available": available,
            "extras": _EXTENSION_EXTRAS.get(name),
        }

    return {
        "version": __version__,
        "backends": backends,
        "extensions": extensions,
    }
