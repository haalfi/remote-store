"""Configuration model — immutable data containers describing backends and stores."""

from __future__ import annotations

import dataclasses


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
    def from_dict(cls, data: dict[str, object]) -> RegistryConfig:
        """Construct from a plain dict (e.g. parsed TOML/JSON).

        :param data: Dict with ``backends`` and ``stores`` keys.
        """
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
            backends[str(name)] = BackendConfig(
                type=str(cfg["type"]),
                options=dict(cfg.get("options", {})),
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
