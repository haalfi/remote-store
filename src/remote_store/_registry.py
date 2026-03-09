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
    from remote_store.backends._memory import MemoryBackend

    if "local" not in _BACKEND_FACTORIES:
        register_backend("local", LocalBackend)

    if "memory" not in _BACKEND_FACTORIES:
        register_backend("memory", MemoryBackend)

    if "azure" not in _BACKEND_FACTORIES:
        try:
            from remote_store.backends._azure import AzureBackend

            register_backend("azure", AzureBackend)
        except ImportError:  # pragma: no cover
            pass

    if "s3" not in _BACKEND_FACTORIES:
        try:
            from remote_store.backends._s3 import S3Backend

            register_backend("s3", S3Backend)
        except ImportError:  # pragma: no cover
            pass

    if "sftp" not in _BACKEND_FACTORIES:
        try:
            from remote_store.backends._sftp import SFTPBackend

            register_backend("sftp", SFTPBackend)
        except ImportError:  # pragma: no cover
            pass

    if "s3-pyarrow" not in _BACKEND_FACTORIES:
        try:
            from remote_store.backends._s3_pyarrow import S3PyArrowBackend

            register_backend("s3-pyarrow", S3PyArrowBackend)
        except ImportError:  # pragma: no cover
            pass


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
        store = Store(backend=backend, root_path=profile.root_path)
        store._owns_backend = False
        return store

    def _get_backend(self, name: str) -> Backend:
        """Lazily instantiate and cache a backend."""
        if name not in self._backends:
            cfg = self._config.backends[name]
            if cfg.type not in _BACKEND_FACTORIES:
                raise ValueError(
                    f"Unknown backend type '{cfg.type}'. Registered types: {sorted(_BACKEND_FACTORIES.keys())}"
                )
            factory = _BACKEND_FACTORIES[cfg.type]
            kwargs = dict(cfg.options)
            if cfg.retry is not None:
                kwargs["retry"] = cfg.retry
            try:
                self._backends[name] = factory(**kwargs)
            except TypeError as exc:
                raise ValueError(
                    f"Invalid options for backend '{name}' (type={cfg.type!r}): {exc}. "
                    f"Provided options: {sorted(kwargs.keys())}"
                ) from exc
        return self._backends[name]

    def close(self) -> None:
        """Close all instantiated backends.

        If any backend raises during ``close()``, the remaining backends are
        still closed.  The first exception encountered is re-raised after all
        backends have been processed.
        """
        first_error: Exception | None = None
        try:
            for backend in self._backends.values():
                try:
                    backend.close()
                except Exception as exc:  # noqa: BLE001
                    if first_error is None:
                        first_error = exc
        finally:
            self._backends.clear()
        if first_error is not None:
            raise first_error

    def __enter__(self) -> Registry:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
