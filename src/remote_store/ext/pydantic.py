"""Pydantic adapter — convert any Pydantic model to a RegistryConfig.

Install with ``pip install "remote-store[pydantic]"``.

Usage::

    from pydantic_settings import BaseSettings, SettingsConfigDict
    from remote_store.ext.pydantic import pydantic_to_registry_config

    class MySettings(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="RS_", env_nested_delimiter="__")
        backends: dict = {}
        stores: dict = {}

    config = pydantic_to_registry_config(MySettings())
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import pydantic  # noqa: F401
except ModuleNotFoundError as _exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "Pydantic is required for the pydantic extension. Install it with: pip install 'remote-store[pydantic]'"
    ) from _exc

from remote_store._config import RegistryConfig

if TYPE_CHECKING:
    from pydantic import BaseModel

__all__ = [
    "pydantic_to_registry_config",
]


def pydantic_to_registry_config(model: BaseModel) -> RegistryConfig:
    """Convert a Pydantic model to a :class:`RegistryConfig`.

    Calls ``model.model_dump()`` to produce a plain dict, then delegates to
    :meth:`RegistryConfig.from_dict`. Secret wrapping, unknown-key warnings,
    and validation all happen in ``from_dict()``.

    If the Pydantic model uses ``pydantic.SecretStr`` for credential fields,
    ``model_dump()`` exposes them as plain strings. This is intentional —
    ``from_dict()`` re-wraps sensitive keys in :class:`Secret` at the
    config→registry boundary.

    :param model: A Pydantic model whose ``model_dump()`` output has
        ``backends`` and ``stores`` keys matching the RegistryConfig schema.
    :returns: An immutable ``RegistryConfig``.
    :raises TypeError: If the model dump does not conform to the expected schema.
    """
    return RegistryConfig.from_dict(model.model_dump())
