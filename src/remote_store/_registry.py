"""Registry — backend lifecycle management and store access."""

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store._config import RegistryConfig
from remote_store._store import Store

if TYPE_CHECKING:
    from types import TracebackType

    from remote_store._backend import Backend

# Global backend factory registry: maps type strings to backend classes.
_BACKEND_FACTORIES: dict[str, type[Backend]] = {}


def register_backend(type_name: str, cls: type[Backend]) -> None:
    """Register a backend class for a given type string.

    :param type_name: The type identifier (e.g. ``"local"``).
    :param cls: The backend class to instantiate.
    """
    _BACKEND_FACTORIES[type_name] = cls


def _register_builtin_backends() -> None:
    """Register the built-in backends."""
    from remote_store.backends._local import LocalBackend

    if "local" not in _BACKEND_FACTORIES:
        register_backend("local", LocalBackend)


class Registry:
    """Manages backend lifecycle and provides access to named stores.

    :param config: Optional configuration. Validates immediately.
    :raises ValueError: If config is invalid.
    """

    def __init__(self, config: RegistryConfig | None = None) -> None:
        _register_builtin_backends()
        self._config = config or RegistryConfig()
        self._config.validate()
        self._backends: dict[str, Backend] = {}

    def __repr__(self) -> str:
        stores = sorted(self._config.stores.keys())
        return f"Registry(stores={stores!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Registry):
            return self._config == other._config
        return NotImplemented

    def __hash__(self) -> int:
        return id(self)

    def get_store(self, name: str) -> Store:
        """Get a store by its profile name.

        :param name: The store profile name.
        :raises KeyError: If no store profile with this name exists.
        """
        if name not in self._config.stores:
            available = sorted(self._config.stores.keys())
            raise KeyError(f"Unknown store '{name}'. Available stores: {available}")

        profile = self._config.stores[name]
        backend = self._get_backend(profile.backend)
        return Store(backend=backend, root_path=profile.root_path)

    def _get_backend(self, name: str) -> Backend:
        """Lazily instantiate and cache a backend."""
        if name not in self._backends:
            cfg = self._config.backends[name]
            if cfg.type not in _BACKEND_FACTORIES:
                raise ValueError(
                    f"Unknown backend type '{cfg.type}'. Registered types: {sorted(_BACKEND_FACTORIES.keys())}"
                )
            factory = _BACKEND_FACTORIES[cfg.type]
            try:
                self._backends[name] = factory(**cfg.options)
            except TypeError as exc:
                raise ValueError(
                    f"Invalid options for backend '{name}' (type={cfg.type!r}): {exc}. "
                    f"Provided options: {sorted(cfg.options.keys())}"
                ) from exc
        return self._backends[name]

    def close(self) -> None:
        """Close all instantiated backends."""
        for backend in self._backends.values():
            backend.close()
        self._backends.clear()

    def __enter__(self) -> Registry:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
