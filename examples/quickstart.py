"""Quickstart — minimal usage of remote-store.

Demonstrates three ways to get started:
1. Direct construction — three lines, no config
2. Registry with declarative config — for multi-backend applications
3. Store at a new root — the root path need not exist beforehand
"""

from __future__ import annotations

import tempfile

from remote_store import Registry, RegistryConfig, Store
from remote_store.backends import LocalBackend


def demo_direct(root: str) -> None:
    """Simplest usage: construct a Store directly."""
    store = Store(LocalBackend(root=root))
    store.write_text("hello.txt", "Hello, world!")
    print(store.read_text("hello.txt"))  # 'Hello, world!'


def demo_registry(root: str) -> None:
    """Registry usage: declarative config, multiple stores."""
    config = RegistryConfig.from_dict(
        {
            "backends": {"main": {"type": "local", "options": {"root": root}}},
            "stores": {"data": {"backend": "main", "root_path": ""}},
        }
    )

    with Registry(config) as registry:
        store = registry.get_store("data")
        store.write_text("hello.txt", "Hello, world!")
        print(store.read_text("hello.txt"))  # 'Hello, world!'


def demo_new_root(root: str) -> None:
    """Store at a non-existing root — write() creates folders implicitly.

    The root path and any intermediate directories are created on first
    write.  This works the same way on every backend: there is no need
    for a separate "create folder" step.
    """
    # root_path="project/data" does not exist yet — that's fine
    store = Store(LocalBackend(root=root), root_path="project/data")
    store.write("report.csv", b"col1,col2\n1,2\n")
    print(store.read_text("report.csv"))  # 'col1,col2\n1,2\n'

    # child() scopes further without extra backends
    archive = store.child("2024")
    archive.write("summary.txt", b"Year-end summary")
    print(archive.read_text("summary.txt"))  # 'Year-end summary'


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        print("-- Direct construction --")
        demo_direct(f"{tmp}/direct")

        print("-- Registry config --")
        demo_registry(f"{tmp}/registry")

        print("-- New root (non-existing path) --")
        demo_new_root(f"{tmp}/new-root")
