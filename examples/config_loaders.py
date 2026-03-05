"""Config loaders — from_toml(), from_yaml(), and pydantic_to_registry_config().

Demonstrates loading RegistryConfig from TOML files, YAML files, and Pydantic
models. All loaders delegate to from_dict() for Secret wrapping and validation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from remote_store import Registry, RegistryConfig

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # --- from_toml(): standalone TOML file ---
        toml_file = root / "remote-store.toml"
        toml_file.write_text(
            "[backends.local]\n"
            'type = "local"\n\n'
            "[backends.local.options]\n"
            f'root = "{root / "toml-data"}"\n\n'
            "[stores.docs]\n"
            'backend = "local"\n'
            'root_path = "docs"\n'
        )

        config = RegistryConfig.from_toml(toml_file)
        print(f"from_toml(): {len(config.backends)} backend(s), {len(config.stores)} store(s)")

        with Registry(config) as reg:
            docs = reg.get_store("docs")
            docs.write("readme.txt", b"Hello from TOML config!")
            print(f"  wrote: {docs.read_bytes('readme.txt').decode()}")

        # --- from_toml(): pyproject.toml with table extraction ---
        pyproject = root / "pyproject.toml"
        pyproject.write_text(
            "[project]\n"
            'name = "my-app"\n\n'
            "[tool.remote-store.backends.local]\n"
            'type = "local"\n\n'
            "[tool.remote-store.backends.local.options]\n"
            f'root = "{root / "pyproject-data"}"\n\n'
            "[tool.remote-store.stores.cache]\n"
            'backend = "local"\n'
            'root_path = "cache"\n'
        )

        config = RegistryConfig.from_toml(pyproject, table=("tool", "remote-store"))
        print(f"\nfrom_toml(table=...): {len(config.stores)} store(s) from pyproject.toml")

        with Registry(config) as reg:
            cache = reg.get_store("cache")
            cache.write("data.bin", b"\x00\x01\x02")
            print(f"  wrote {len(cache.read_bytes('data.bin'))} bytes to cache")

        # --- from_yaml() ---
        yaml_file = root / "remote-store.yaml"
        yaml_file.write_text(
            "backends:\n"
            "  local:\n"
            "    type: local\n"
            "    options:\n"
            f"      root: '{root / 'yaml-data'}'\n"
            "stores:\n"
            "  logs:\n"
            "    backend: local\n"
            "    root_path: logs\n"
        )

        config = RegistryConfig.from_yaml(yaml_file)
        print(f"\nfrom_yaml(): {len(config.backends)} backend(s), {len(config.stores)} store(s)")

        with Registry(config) as reg:
            logs = reg.get_store("logs")
            logs.write("app.log", b"[INFO] started\n")
            print(f"  wrote: {logs.read_bytes('app.log').decode().strip()}")

        # --- pydantic_to_registry_config() ---
        try:
            from pydantic import BaseModel

            from remote_store.ext.pydantic import pydantic_to_registry_config

            class BackendEntry(BaseModel):
                type: str
                options: dict[str, object] = {}

            class StoreEntry(BaseModel):
                backend: str
                root_path: str = ""

            class MyConfig(BaseModel):
                backends: dict[str, BackendEntry] = {}
                stores: dict[str, StoreEntry] = {}

            model = MyConfig(
                backends={"local": BackendEntry(type="local", options={"root": str(root / "pydantic-data")})},
                stores={"notes": StoreEntry(backend="local", root_path="notes")},
            )
            config = pydantic_to_registry_config(model)
            print(f"\npydantic_to_registry_config(): {len(config.stores)} store(s)")

            with Registry(config) as reg:
                notes = reg.get_store("notes")
                notes.write("todo.txt", b"Ship config loaders!")
                print(f"  wrote: {notes.read_bytes('todo.txt').decode()}")

        except ImportError:
            print("\n(pydantic not installed -- skipping pydantic example)")

    print("\nDone!")
