"""Pydantic adapter — convert any Pydantic model to a RegistryConfig.

Install with ``pip install "remote-store[pydantic]"``.

!!! example

    ```python
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from remote_store.ext.pydantic import from_pydantic

    class MySettings(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="RS_", env_nested_delimiter="__")
        backends: dict = {}
        stores: dict = {}

    config = from_pydantic(MySettings())
    ```
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from pydantic import SecretStr
except ModuleNotFoundError as _exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "Pydantic is required for the pydantic extension. Install it with: pip install 'remote-store[pydantic]'"
    ) from _exc

from remote_store import RegistryConfig

if TYPE_CHECKING:
    from pydantic import BaseModel

__all__ = [
    "from_pydantic",
]


def _unwrap_secret_strs(d: dict[str, Any]) -> dict[str, Any]:
    """Unwrap ``SecretStr`` values to plain ``str`` so ``from_dict()`` can wrap them as ``Secret``."""
    return {k: v.get_secret_value() if isinstance(v, SecretStr) else v for k, v in d.items()}


def from_pydantic(model: BaseModel) -> RegistryConfig:
    """Convert a Pydantic model to a ``RegistryConfig``.

    Calls ``model.model_dump()`` to produce a plain dict, then delegates to
    ``RegistryConfig.from_dict()``. Secret wrapping, unknown-key warnings,
    and validation all happen in ``from_dict()``.

    Pydantic ``SecretStr`` fields in backend ``options`` dicts are
    automatically unwrapped to plain strings before reaching ``from_dict()``,
    so ``from_dict()``'s sensitive-key detection works correctly. Users may
    use either ``str`` or ``SecretStr`` for credential values in their models.

    Args:
        model: A Pydantic model whose ``model_dump()`` output has
            ``backends`` and ``stores`` keys matching the RegistryConfig schema.

    Returns:
        An immutable ``RegistryConfig``.

    Raises:
        TypeError: If the model dump does not conform to the expected schema.
    """
    data = model.model_dump()
    backends = data.get("backends", {})
    if isinstance(backends, dict):
        for cfg in backends.values():
            if isinstance(cfg, dict) and "options" in cfg and isinstance(cfg["options"], dict):
                cfg["options"] = _unwrap_secret_strs(cfg["options"])
    return RegistryConfig.from_dict(data)
