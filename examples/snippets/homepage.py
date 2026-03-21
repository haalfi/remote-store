"""Homepage code snippets — tested source for docs-src/index.md.

Each named region (``# --8<-- [start:name]`` / ``# --8<-- [end:name]``)
maps to a ``pymdownx.snippets`` include directive in the docs.

Run this file directly or via ``hatch run examples`` to verify all
snippets execute correctly.
"""

from __future__ import annotations

import tempfile

from remote_store import Store
from remote_store.backends import MemoryBackend


def demo() -> None:
    """Execute all homepage snippets."""
    with tempfile.TemporaryDirectory() as tmp:
        _core_idea(tmp)
        _capabilities()
        _custom_backend()


def _core_idea(tmp: str) -> None:
    # --8<-- [start:core-idea]
    from remote_store import Store  # noqa: F811
    from remote_store.backends import LocalBackend  # noqa: F811

    store = Store(LocalBackend(root=tmp))
    store.write_text("hello.txt", "Hello, world!")
    print(store.read_text("hello.txt"))  # 'Hello, world!'
    # --8<-- [end:core-idea]

    # --8<-- [start:child-scoping]
    sub = store.child("reports/2024")
    sub.write_text("summary.txt", "...")
    # --8<-- [end:child-scoping]


def _capabilities() -> None:
    store = Store(MemoryBackend())

    # --8<-- [start:capabilities]
    from remote_store import Capability  # noqa: F811

    store.supports(Capability.GLOB)  # True for Local, S3, S3-PyArrow, Azure
    store.supports(Capability.ATOMIC_WRITE)  # True for all except HTTP
    # --8<-- [end:capabilities]


def _custom_backend() -> None:
    # Verify the import and class structure work — we don't instantiate.
    # --8<-- [start:custom-backend]
    from remote_store import Backend  # noqa: F811

    class MyBackend(Backend):  # noqa: F811
        """Implement the Backend protocol for your storage."""

        ...

    # --8<-- [end:custom-backend]


if __name__ == "__main__":
    demo()
    print("\nAll homepage snippets OK.")
