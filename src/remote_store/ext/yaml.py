"""YAML config loader — load RegistryConfig from a YAML file.

Install with ``pip install "remote-store[yaml]"``.

!!! example

    ```python
    from remote_store.ext.yaml import from_yaml

    config = from_yaml("remote-store.yaml")
    ```

Accepts either [pyyaml](https://pyyaml.org/) or [ruamel.yaml](https://yaml.readthedocs.io/) as the parser.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# Fail-fast: raise at import time if neither yaml library is installed,
# consistent with all other optional-dep extensions (arrow, parquet, …).
if importlib.util.find_spec("yaml") is None and importlib.util.find_spec("ruamel.yaml") is None:
    raise ModuleNotFoundError(  # pragma: no cover
        "YAML support requires pyyaml or ruamel.yaml. Install with: pip install 'remote-store[yaml]'"
    )

from remote_store import RegistryConfig

__all__ = [
    "from_yaml",
]


def _get_yaml_loader() -> Callable[..., Any]:
    """Return a safe YAML load function, preferring pyyaml over ruamel.yaml."""
    try:
        from yaml import safe_load  # type: ignore[import-untyped]

        return safe_load  # type: ignore[no-any-return]
    except ImportError:
        pass
    try:
        from ruamel.yaml import YAML

        _yaml = YAML(typ="safe")
        return _yaml.load  # type: ignore[no-any-return]  # CodeQL: safe — YAML(typ="safe") disables arbitrary tag execution, equivalent to pyyaml safe_load
    except ImportError:
        pass
    raise ModuleNotFoundError(  # pragma: no cover
        "YAML support requires pyyaml or ruamel.yaml. Install with: pip install 'remote-store[yaml]'"
    )


def from_yaml(
    path: str | Path,
    *,
    resolve_env_vars: bool = False,
) -> RegistryConfig:
    """Load config from a YAML file.

    Accepts either ``pyyaml`` or ``ruamel.yaml`` as the parser.

    Args:
        path: Path to the YAML file.
        resolve_env_vars: When ``True``, resolve ``${VAR}`` placeholders
            via ``resolve_env`` before constructing
            the config.

    Returns:
        An immutable ``RegistryConfig``.

    Raises:
        ModuleNotFoundError: If neither ``pyyaml`` nor ``ruamel.yaml``
            is installed.
        FileNotFoundError: If *path* does not exist.
        TypeError: If the top-level YAML value is not a mapping.
        KeyError: If *resolve_env_vars* is ``True`` and a placeholder
            references an unset variable with no default.
    """
    safe_load = _get_yaml_loader()

    with open(path, encoding="utf-8") as f:
        data = safe_load(f)

    if not isinstance(data, dict):
        msg = f"Expected YAML mapping at top level, got {type(data).__name__}"
        raise TypeError(msg)

    if resolve_env_vars:
        from remote_store import resolve_env

        data = resolve_env(data)

    return RegistryConfig._from_dict(data, stacklevel=3)
