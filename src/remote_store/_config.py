"""Configuration model — immutable data containers describing backends and stores."""

from __future__ import annotations

import dataclasses
import logging
import os
import re
import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
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

    Args:
        value: The secret string to protect.

    Raises:
        TypeError: If *value* is not a ``str``.
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
    %-style formatting:

    ```python
    handler.addFilter(SecretRedactionFilter())
    ```
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = {k: "***" if isinstance(v, Secret) else v for k, v in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple("***" if isinstance(a, Secret) else a for a in record.args)
        return True


# endregion


# region: retry policy


@dataclasses.dataclass(frozen=True)
class RetryPolicy:
    """Retry configuration for transient backend errors.

    Backends map these parameters to their native retry mechanisms.
    Backends that don't support a parameter silently ignore it.

    Args:
        max_attempts: Maximum number of attempts (including the initial).
            Set to 1 to disable retry.
        backoff_base: Base delay in seconds for exponential backoff.
        backoff_max: Maximum delay between retries in seconds.
        jitter: Maximum random jitter added to each delay in seconds.
            Set to 0.0 to disable jitter.
        timeout: Total wall-clock timeout in seconds for all attempts
            combined. ``None`` means no total timeout.
    """

    max_attempts: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 60.0
    jitter: float = 1.0
    timeout: float | None = None

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.backoff_base < 0:
            raise ValueError("backoff_base must be >= 0")
        if self.backoff_max < 0:
            raise ValueError("backoff_max must be >= 0")
        if self.jitter < 0:
            raise ValueError("jitter must be >= 0")
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError("timeout must be > 0 or None")

    @classmethod
    def disabled(cls) -> RetryPolicy:
        """Return a policy that disables retry (single attempt, no backoff)."""
        return cls(max_attempts=1)


# endregion


@dataclasses.dataclass(frozen=True)
class BackendConfig:
    """Describes a backend instance.

    Args:
        type: Backend type identifier (e.g. ``"local"``, ``"s3"``).
        options: Backend-specific configuration options.
        retry: Optional retry policy for transient errors.
    """

    type: str
    options: dict[str, object] = dataclasses.field(default_factory=dict)
    retry: RetryPolicy | None = None


@dataclasses.dataclass(frozen=True)
class StoreProfile:
    """Describes a named store.

    Args:
        backend: Name of the backend config to use.
        root_path: Path prefix for all operations.
        options: Store-specific options.
    """

    backend: str
    root_path: str = ""
    options: dict[str, object] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class RegistryConfig:
    """Top-level configuration container.

    Args:
        backends: Mapping of backend names to their configs.
        stores: Mapping of store names to their profiles.
    """

    backends: dict[str, BackendConfig] = dataclasses.field(default_factory=dict)
    stores: dict[str, StoreProfile] = dataclasses.field(default_factory=dict)

    def validate(self) -> None:
        """Validate that all store profiles reference existing backends.

        Raises:
            ValueError: If a store references a non-existent backend.
        """
        for store_name, profile in self.stores.items():
            if profile.backend not in self.backends:
                raise ValueError(
                    f"Store '{store_name}' references unknown backend '{profile.backend}'. "
                    f"Available backends: {sorted(self.backends.keys())}"
                )

    @classmethod
    def _from_dict(cls, data: dict[str, object], *, stacklevel: int) -> RegistryConfig:
        """Private implementation shared by all loaders.

        *stacklevel* is passed directly to ``warnings.warn()`` so that the
        warning points at the correct frame in each calling context.
        """
        _KNOWN_KEYS = {"backends", "stores"}
        unknown = set(data.keys()) - _KNOWN_KEYS
        if unknown:
            warnings.warn(
                f"Unknown top-level config keys ignored: {sorted(unknown)}. Expected keys: {sorted(_KNOWN_KEYS)}",
                UserWarning,
                stacklevel=stacklevel,
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
            options = dict(cfg.get("options") or {})
            for k in _SENSITIVE_KEYS:
                if k in options and isinstance(options[k], str):
                    options[k] = Secret(options[k])
            raw_retry = cfg.get("retry")
            retry: RetryPolicy | None = None
            if isinstance(raw_retry, dict):
                retry = RetryPolicy(**raw_retry)
            elif isinstance(raw_retry, RetryPolicy):
                retry = raw_retry
            backend_type = cfg["type"]
            if not isinstance(backend_type, str):
                msg = f"Backend '{name}' type must be a string, got {type(backend_type).__name__}"
                raise TypeError(msg)
            backends[str(name)] = BackendConfig(
                type=backend_type,
                options=options,
                retry=retry,
            )

        stores: dict[str, StoreProfile] = {}
        for name, prof in raw_stores.items():
            if not isinstance(prof, dict):
                msg = f"Store profile for '{name}' must be a dict"
                raise TypeError(msg)
            store_backend = prof["backend"]
            if not isinstance(store_backend, str):
                msg = f"Store '{name}' backend must be a string, got {type(store_backend).__name__}"
                raise TypeError(msg)
            raw_root = prof.get("root_path", "")
            if raw_root is None:
                raw_root = ""
            if not isinstance(raw_root, str):
                msg = f"Store '{name}' root_path must be a string, got {type(raw_root).__name__}"
                raise TypeError(msg)
            stores[str(name)] = StoreProfile(
                backend=store_backend,
                root_path=raw_root,
                options=dict(prof.get("options") or {}),
            )

        return cls(backends=backends, stores=stores)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RegistryConfig:
        """Construct from a plain dict (e.g. parsed TOML/JSON).

        Args:
            data: Dict with ``backends`` and ``stores`` keys.
        """
        return cls._from_dict(data, stacklevel=3)

    @classmethod
    def from_toml(
        cls,
        path: str | Path,
        *,
        table: tuple[str, ...] = (),
        resolve_env_vars: bool = False,
    ) -> RegistryConfig:
        """Load config from a TOML file.

        Args:
            path: Path to the TOML file.
            table: Dotted table path to extract config from.
                For ``pyproject.toml`` use ``table=("tool", "remote-store")``.
            resolve_env_vars: When ``True``, resolve ``${VAR}`` placeholders
                via :func:`resolve_env` before constructing the config.

        Raises:
            ModuleNotFoundError: If ``tomllib`` is unavailable and
                ``tomli`` is not installed.
            KeyError: If a *table* key is not found, or if
                *resolve_env_vars* is ``True`` and a placeholder
                references an unset variable with no default.
        """
        try:
            import tomllib
        except ModuleNotFoundError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
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

        if resolve_env_vars:
            data = resolve_env(data)

        return cls._from_dict(data, stacklevel=3)


# region: env-var interpolation

_PLACEHOLDER_RE = re.compile(r"\$\$\{|\$\{([^}]+)\}")


def _resolve_placeholder(
    match: re.Match[str],
    env: Mapping[str, str],
    path: str,
) -> str:
    """Replace a single placeholder match."""
    full = match.group(0)
    if full == "$${":
        return "${"
    expr = match.group(1)
    if ":-" in expr:
        var, default = expr.split(":-", 1)
        return env.get(var, default)
    if expr not in env:
        raise KeyError(f"Environment variable {expr!r} is not set (referenced at config path {path!r})")
    return env[expr]


def _resolve_value(
    value: object,
    env: Mapping[str, str],
    path: str,
) -> object:
    """Recursively resolve placeholders in a config value."""
    if isinstance(value, str):
        return _PLACEHOLDER_RE.sub(lambda m: _resolve_placeholder(m, env, path), value)
    if isinstance(value, dict):
        return {k: _resolve_value(v, env, f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, env, f"{path}[{i}]") for i, item in enumerate(value)]
    return value


def resolve_env(
    data: dict[str, object],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Resolve ``${VAR}`` placeholders in a config dict.

    Recursively walks *data* and replaces ``${VAR}`` with the value of
    the environment variable *VAR*. Use ``${VAR:-default}`` to provide a
    fallback when *VAR* is not set. Escape with ``$${`` to produce a
    literal ``${``.

    The original dict is never mutated; a deep copy with resolved values
    is returned.

    Args:
        data: Config dict (typically parsed from YAML/TOML).
        environ: Variable source. Defaults to ``os.environ``.

    Returns:
        A new dict with all placeholder strings resolved.

    Raises:
        KeyError: If a placeholder references a variable that is not set
            and has no default. The message includes the variable name
            and the config key path where it was found.
    """
    env: Mapping[str, str] = environ if environ is not None else os.environ
    result = _resolve_value(data, env, "$")
    assert isinstance(result, dict)  # noqa: S101 — guaranteed by input type
    return result  # type: ignore[return-value]


# endregion
