"""Configuration model — immutable data containers describing backends and stores."""

from __future__ import annotations

import dataclasses
import logging
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# region: Secret wrapper

_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "key",
        "secret",
        "password",
        "account_key",
        "sas_token",
        "connection_string",
    }
)


class Secret:
    """Immutable wrapper that prevents accidental exposure of credential strings.

    ``__repr__`` and ``__str__`` always return a masked value.
    Call ``.reveal()`` to obtain the plain-text credential.

    :param value: The secret string to protect.
    :raises TypeError: If *value* is not a ``str``.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"Secret value must be a str, got {type(value).__name__}")
        object.__setattr__(self, "_value", value)

    def reveal(self) -> str:
        """Return the plain-text secret."""
        return self._value  # type: ignore[attr-defined,no-any-return]  # __setattr__ hides slot

    def __repr__(self) -> str:
        return "Secret('***')"

    def __str__(self) -> str:
        return "***"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Secret):
            return bool(self._value == other._value)  # type: ignore[attr-defined]
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)  # type: ignore[attr-defined]

    def __bool__(self) -> bool:
        return bool(self._value)  # type: ignore[attr-defined]

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Secret instances are immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Secret instances are immutable")

    def __reduce__(self) -> tuple[type[Secret], tuple[str]]:
        return (Secret, (self._value,))  # type: ignore[attr-defined]


def _reveal(value: str | Secret | None) -> str | None:
    """Unwrap a ``Secret`` to a plain string, passing through ``str`` and ``None``."""
    if isinstance(value, Secret):
        return value.reveal()
    return value


# endregion


# region: log redaction filter


class SecretRedactionFilter(logging.Filter):
    """Logging filter that replaces ``Secret`` instances in log record args with ``'***'``.

    Attach to any handler or logger to prevent credential leakage through
    %-style formatting::

        handler.addFilter(SecretRedactionFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = {k: "***" if isinstance(v, Secret) else v for k, v in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple("***" if isinstance(a, Secret) else a for a in record.args)
        return True


# endregion


@dataclasses.dataclass(frozen=True)
class BackendConfig:
    """Describes a backend instance.

    :param type: Backend type identifier (e.g. ``"local"``, ``"s3"``).
    :param options: Backend-specific configuration options.
    """

    type: str
    options: dict[str, object] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class StoreProfile:
    """Describes a named store.

    :param backend: Name of the backend config to use.
    :param root_path: Path prefix for all operations.
    :param options: Store-specific options.
    """

    backend: str
    root_path: str = ""
    options: dict[str, object] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class RegistryConfig:
    """Top-level configuration container.

    :param backends: Mapping of backend names to their configs.
    :param stores: Mapping of store names to their profiles.
    """

    backends: dict[str, BackendConfig] = dataclasses.field(default_factory=dict)
    stores: dict[str, StoreProfile] = dataclasses.field(default_factory=dict)

    def validate(self) -> None:
        """Validate that all store profiles reference existing backends.

        :raises ValueError: If a store references a non-existent backend.
        """
        for store_name, profile in self.stores.items():
            if profile.backend not in self.backends:
                raise ValueError(
                    f"Store '{store_name}' references unknown backend '{profile.backend}'. "
                    f"Available backends: {sorted(self.backends.keys())}"
                )

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
        *,
        _stacklevel: int = 2,
    ) -> RegistryConfig:
        """Construct from a plain dict (e.g. parsed TOML/JSON).

        :param data: Dict with ``backends`` and ``stores`` keys.
        """
        _KNOWN_KEYS = {"backends", "stores"}
        unknown = set(data.keys()) - _KNOWN_KEYS
        if unknown:
            warnings.warn(
                f"Unknown top-level config keys ignored: {sorted(unknown)}. Expected keys: {sorted(_KNOWN_KEYS)}",
                UserWarning,
                stacklevel=_stacklevel,
            )

        raw_backends = data.get("backends", {})
        raw_stores = data.get("stores", {})
        if not isinstance(raw_backends, dict) or not isinstance(raw_stores, dict):
            msg = "Expected 'backends' and 'stores' to be dicts"
            raise TypeError(msg)

        backends: dict[str, BackendConfig] = {}
        for name, cfg in raw_backends.items():
            if not isinstance(cfg, dict):
                msg = f"Backend config for '{name}' must be a dict"
                raise TypeError(msg)
            options = dict(cfg.get("options", {}))
            for k in _SENSITIVE_KEYS:
                if k in options and isinstance(options[k], str):
                    options[k] = Secret(options[k])
            backends[str(name)] = BackendConfig(
                type=str(cfg["type"]),
                options=options,
            )

        stores: dict[str, StoreProfile] = {}
        for name, prof in raw_stores.items():
            if not isinstance(prof, dict):
                msg = f"Store profile for '{name}' must be a dict"
                raise TypeError(msg)
            stores[str(name)] = StoreProfile(
                backend=str(prof["backend"]),
                root_path=str(prof.get("root_path", "")),
                options=dict(prof.get("options", {})),
            )

        return cls(backends=backends, stores=stores)

    @classmethod
    def from_toml(
        cls,
        path: str | Path,
        *,
        table: tuple[str, ...] = (),
    ) -> RegistryConfig:
        """Load config from a TOML file.

        :param path: Path to the TOML file.
        :param table: Dotted table path to extract config from.
            For ``pyproject.toml`` use ``table=("tool", "remote-store")``.
        :raises ModuleNotFoundError: If ``tomllib`` is unavailable and
            ``tomli`` is not installed.
        :raises KeyError: If a *table* key is not found.
        """
        try:
            import tomllib
        except ModuleNotFoundError:
            try:
                import tomli as tomllib  # type: ignore[no-redef,import-not-found]
            except ModuleNotFoundError:
                raise ModuleNotFoundError(
                    "TOML support requires tomli on Python < 3.11. Install it with: pip install 'remote-store[toml]'"
                ) from None

        with open(path, "rb") as f:
            data: dict[str, object] = tomllib.load(f)

        for key in table:
            if not isinstance(data, dict) or key not in data:
                raise KeyError(f"Table key {key!r} not found in {path}")
            data = data[key]  # type: ignore[assignment]

        if not isinstance(data, dict):
            msg = f"Expected a TOML table, got {type(data).__name__}"
            raise TypeError(msg)

        return cls.from_dict(data, _stacklevel=3)

    @classmethod
    def from_yaml(cls, path: str | Path) -> RegistryConfig:
        """Load config from a YAML file.

        Accepts either ``pyyaml`` or ``ruamel.yaml`` as the parser.

        :param path: Path to the YAML file.
        :raises ModuleNotFoundError: If neither ``pyyaml`` nor ``ruamel.yaml``
            is installed.
        """
        safe_load = _get_yaml_loader()

        with open(path, encoding="utf-8") as f:
            data = safe_load(f)

        if not isinstance(data, dict):
            msg = f"Expected YAML mapping at top level, got {type(data).__name__}"
            raise TypeError(msg)

        return cls.from_dict(data, _stacklevel=3)


def _get_yaml_loader() -> Callable[..., Any]:
    """Return a safe YAML load function, preferring pyyaml over ruamel.yaml."""
    try:
        from yaml import safe_load  # type: ignore[import-untyped]

        return safe_load  # type: ignore[no-any-return]
    except ImportError:
        pass
    try:
        from ruamel.yaml import YAML  # type: ignore[import-not-found]

        _yaml = YAML(typ="safe")
        return _yaml.load  # type: ignore[no-any-return]
    except ImportError:
        pass
    raise ModuleNotFoundError(
        "YAML support requires pyyaml or ruamel.yaml. Install with: pip install 'remote-store[yaml]'"
    )
