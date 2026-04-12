"""Homepage code snippets — tested source for docs-src/index.md.

Each named region (``# --8<-- [start:name]`` / ``# --8<-- [end:name]``)
maps to a ``pymdownx.snippets`` include directive in the docs.

Run this file directly or via ``hatch run examples`` to verify all
snippets execute correctly.
"""

# ruff: noqa: F401, F811

from __future__ import annotations

import shutil
import tempfile

from remote_store import Store
from remote_store.backends import MemoryBackend


def demo(root: str | None = None) -> None:
    """Execute all homepage snippets.

    Parameters
    ----------
    root:
        Filesystem root for the LocalBackend snippet.  When *None* a unique
        temporary directory is created automatically, avoiding collisions
        when tests run in parallel (pytest-xdist / CI matrix).
    """
    if root is None:
        root = tempfile.mkdtemp(prefix="homepage-snippet-")
    _core_idea(root)
    _capabilities()
    _custom_backend()


def _core_idea(root: str) -> None:
    try:
        # --8<-- [start:core-idea]
        from remote_store import Store
        from remote_store.backends import LocalBackend

        store = Store(LocalBackend(root="/tmp/data"))
        store.write_text("hello.txt", "Hello, world!")
        print(store.read_text("hello.txt"))  # 'Hello, world!'
        # --8<-- [end:core-idea]

        # Re-run with the isolated root so parallel workers don't collide
        store = Store(LocalBackend(root=root))
        store.write_text("hello.txt", "Hello, world!")

        # --8<-- [start:child-scoping]
        sub = store.child("reports/2024")
        sub.write_text("summary.txt", "...")
        # --8<-- [end:child-scoping]
    finally:
        shutil.rmtree(root, ignore_errors=True)
        # Also clean up the hardcoded path used in the snippet region
        shutil.rmtree("/tmp/data", ignore_errors=True)


def _capabilities() -> None:
    store = Store(MemoryBackend())

    # --8<-- [start:capabilities]
    from remote_store import Capability

    store.supports(Capability.GLOB)  # True for most backends; see capabilities matrix
    store.supports(Capability.ATOMIC_WRITE)  # True for most backends; see capabilities matrix
    # --8<-- [end:capabilities]


def _custom_backend() -> None:
    # Verify the import and class structure work — we don't instantiate.
    # --8<-- [start:custom-backend]
    from remote_store import Backend, Store

    class MyBackend(Backend):
        """Implement the Backend protocol for your storage."""

        ...

    # --8<-- [end:custom-backend]


if __name__ == "__main__":
    demo()
    print("\nAll homepage snippets OK.")
