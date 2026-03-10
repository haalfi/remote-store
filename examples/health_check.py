"""Health check example -- startup gate pattern.

Demonstrates ``Store.ping()`` for verifying backend connectivity
before accepting traffic.
"""

from __future__ import annotations

from remote_store import (
    BackendUnavailable,
    NotFound,
    PermissionDenied,
    Store,
)
from remote_store.backends._memory import MemoryBackend


def demo(store: Store) -> None:
    """Run a health check against the store."""
    # --- Startup gate pattern ---
    try:
        store.ping()
        print("Health check passed -- backend is reachable")
    except PermissionDenied as exc:
        print(f"Health check FAILED -- bad credentials: {exc}")
        raise
    except NotFound as exc:
        print(f"Health check FAILED -- missing resource: {exc}")
        raise
    except BackendUnavailable as exc:
        print(f"Health check FAILED -- backend unreachable: {exc}")
        raise

    # --- Write and verify ---
    store.write("health-probe.txt", b"ok", overwrite=True)
    assert store.read_bytes("health-probe.txt") == b"ok"
    store.delete("health-probe.txt")
    print("Write/read/delete cycle OK")


if __name__ == "__main__":
    store = Store(MemoryBackend())
    demo(store)
