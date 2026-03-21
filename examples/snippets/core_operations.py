"""Core operations snippets — tested source for guides and README.

Named regions can be included in any docs page via pymdownx.snippets:

    ```python
    ;--8<-- "examples/snippets/core_operations.py:registry-config"
    ```

Run directly or via ``hatch run examples`` to verify all snippets.
"""

from __future__ import annotations

import tempfile

from remote_store import Store
from remote_store.backends import MemoryBackend


def demo() -> None:
    """Execute all core-operations snippets."""
    with tempfile.TemporaryDirectory() as tmp:
        _direct_store(f"{tmp}/direct")
        _registry_config(f"{tmp}/registry")
        _store_api()


def _direct_store(tmp: str) -> None:
    # --8<-- [start:direct-store]
    from remote_store import Store  # noqa: F811
    from remote_store.backends import LocalBackend  # noqa: F811

    store = Store(LocalBackend(root=tmp))
    store.write_text("hello.txt", "Hello, world!")
    print(store.read_text("hello.txt"))  # 'Hello, world!'
    # --8<-- [end:direct-store]


def _registry_config(tmp: str) -> None:
    # --8<-- [start:registry-config]
    from remote_store import Registry, RegistryConfig  # noqa: F811

    config = RegistryConfig.from_dict({
        "backends": {"main": {"type": "local", "options": {"root": tmp}}},
        "stores": {"data": {"backend": "main", "root_path": ""}},
    })

    with Registry(config) as registry:
        store = registry.get_store("data")
        store.write_text("hello.txt", "Hello, world!")
        print(store.read_text("hello.txt"))  # 'Hello, world!'
    # --8<-- [end:registry-config]


def _store_api() -> None:
    store = Store(MemoryBackend())
    store.write_text("path/to/file.txt", "content")
    store.write_text("path/to/file.csv", "a,b")
    store.write("path/to/data.bin", b"\x00")
    store.write_text("reports/q1.csv", "data")

    # --8<-- [start:store-api]
    store.read_text("path/to/file.txt")                          # -> str
    store.write_text("path/to/file.txt", "content", overwrite=True)  # write string
    store.read_bytes("path/to/file.csv")                         # -> bytes
    store.write("path/to/data.bin", b"\x00", overwrite=True)     # streaming write

    store.list_files("reports/", pattern="*.csv")   # iterate FileInfo
    store.exists("path/to/file.txt")                # -> bool

    store.copy("path/to/file.txt", "path/to/copy.txt")
    store.delete("path/to/copy.txt")
    # --8<-- [end:store-api]


if __name__ == "__main__":
    demo()
    print("\nAll core-operations snippets OK.")
