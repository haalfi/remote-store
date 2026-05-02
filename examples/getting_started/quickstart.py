"""Quickstart — Minimal config, write, and read.

Demonstrates two ways to get started:
1. Direct construction — three lines, no config
2. Registry with declarative config — for multi-backend applications

---
see_also:
  - label: Getting Started
    url: ../../tutorial/getting-started.md
    note: step-by-step guide
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


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        print("-- Direct construction --")
        demo_direct(f"{tmp}/direct")

        print("-- Registry config --")
        demo_registry(f"{tmp}/registry")
