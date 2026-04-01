"""Config loaders — from_toml(), from_yaml(), from_pydantic(), and resolve_env().

Demonstrates loading RegistryConfig from TOML files, YAML files, and Pydantic
models, plus env-var interpolation with resolve_env(). All loaders delegate to
from_dict() for Secret wrapping and validation.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from remote_store import Registry, RegistryConfig, resolve_env


def _posix(p: Path) -> str:
    """Return a forward-slash path string safe for TOML/YAML values."""
    return p.as_posix()


def demo() -> dict[str, object]:
    """Run config-loader examples and return results for test verification."""
    results: dict[str, object] = {}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # --- from_toml(): standalone TOML file ---
        toml_file = root / "remote-store.toml"
        toml_file.write_text(
            "[backends.local]\n"
            'type = "local"\n\n'
            "[backends.local.options]\n"
            f'root = "{_posix(root / "toml-data")}"\n\n'
            "[stores.docs]\n"
            'backend = "local"\n'
            'root_path = "docs"\n'
        )

        config = RegistryConfig.from_toml(toml_file)
        print(f"from_toml(): {len(config.backends)} backend(s), {len(config.stores)} store(s)")

        with Registry(config) as reg:
            docs = reg.get_store("docs")
            docs.write("readme.txt", b"Hello from TOML config!")
            results["toml_content"] = docs.read_bytes("readme.txt")
            print(f"  wrote: {results['toml_content'].decode()}")

        # --- from_toml(): pyproject.toml with table extraction ---
        pyproject = root / "pyproject.toml"
        pyproject.write_text(
            "[project]\n"
            'name = "my-app"\n\n'
            "[tool.remote-store.backends.local]\n"
            'type = "local"\n\n'
            "[tool.remote-store.backends.local.options]\n"
            f'root = "{_posix(root / "pyproject-data")}"\n\n'
            "[tool.remote-store.stores.cache]\n"
            'backend = "local"\n'
            'root_path = "cache"\n'
        )

        config = RegistryConfig.from_toml(pyproject, table=("tool", "remote-store"))
        print(f"\nfrom_toml(table=...): {len(config.stores)} store(s) from pyproject.toml")

        with Registry(config) as reg:
            cache = reg.get_store("cache")
            cache.write("data.bin", b"\x00\x01\x02")
            results["pyproject_bytes"] = len(cache.read_bytes("data.bin"))
            print(f"  wrote {results['pyproject_bytes']} bytes to cache")

        # --- from_yaml() (ext.yaml) ---
        yaml_file = root / "remote-store.yaml"
        yaml_file.write_text(
            "backends:\n"
            "  local:\n"
            "    type: local\n"
            "    options:\n"
            f"      root: '{_posix(root / 'yaml-data')}'\n"
            "stores:\n"
            "  logs:\n"
            "    backend: local\n"
            "    root_path: logs\n"
        )

        from remote_store.ext.yaml import from_yaml

        config = from_yaml(yaml_file)
        print(f"\nfrom_yaml(): {len(config.backends)} backend(s), {len(config.stores)} store(s)")

        with Registry(config) as reg:
            logs = reg.get_store("logs")
            logs.write("app.log", b"[INFO] started\n")
            results["yaml_content"] = logs.read_bytes("app.log")
            print(f"  wrote: {results['yaml_content'].decode().strip()}")

        # --- from_pydantic() ---
        try:
            from pydantic import BaseModel

            from remote_store.ext.pydantic import from_pydantic

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
                backends={
                    "local": BackendEntry(
                        type="local",
                        options={"root": _posix(root / "pydantic-data")},
                    )
                },
                stores={"notes": StoreEntry(backend="local", root_path="notes")},
            )
            config = from_pydantic(model)
            results["pydantic_stores"] = len(config.stores)
            print(f"\nfrom_pydantic(): {results['pydantic_stores']} store(s)")

            with Registry(config) as reg:
                notes = reg.get_store("notes")
                notes.write("todo.txt", b"Ship config loaders!")
                results["pydantic_content"] = notes.read_bytes("todo.txt")
                print(f"  wrote: {results['pydantic_content'].decode()}")

        except ImportError:
            print("\n(pydantic not installed -- skipping pydantic example)")
            results["pydantic_stores"] = None

        # --- resolve_env(): env-var interpolation for YAML ---
        os.environ["DEMO_STORE_ROOT"] = _posix(root / "env-data")

        yaml_env_file = root / "env-config.yaml"
        yaml_env_file.write_text(
            "backends:\n"
            "  local:\n"
            "    type: local\n"
            "    options:\n"
            "      root: ${DEMO_STORE_ROOT}\n"
            "stores:\n"
            "  data:\n"
            "    backend: local\n"
            "    root_path: resolved\n"
        )

        # Option A: resolve_env_vars=True on the loader
        config = from_yaml(yaml_env_file, resolve_env_vars=True)
        resolved_root = config.backends["local"].options["root"]
        results["resolved_root"] = resolved_root
        print(f"\nfrom_yaml(resolve_env_vars=True): root={resolved_root}")

        # Option B: standalone resolve_env() for any dict
        raw = json.loads('{"backends": {"mem": {"type": "memory"}}, "stores": {}}')
        resolved = resolve_env(raw)
        config2 = RegistryConfig.from_dict(resolved)
        results["resolve_env_backends"] = len(config2.backends)
        print(f"resolve_env() standalone: {results['resolve_env_backends']} backend(s)")

        # Default values: ${VAR:-fallback} syntax
        data_with_default: dict[str, object] = {"greeting": "${UNSET_VAR:-hello world}"}
        results["default_value"] = resolve_env(data_with_default)["greeting"]
        print(f"Default value: {results['default_value']}")

    print("\nDone!")
    return results


if __name__ == "__main__":
    demo()
