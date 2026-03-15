"""HTTP backend -- read files from HTTP/HTTPS URLs.

Demonstrates:
- Creating a ReadOnlyHttpBackend with base_url
- Reading files and metadata from an HTTP endpoint
- Capability-gated error handling for unsupported operations
- Transport selection (urllib, requests, httpx)
"""

from __future__ import annotations

from remote_store import Capability, CapabilityNotSupported, Store
from remote_store.backends import ReadOnlyHttpBackend


def demo(store: Store) -> dict:
    """HTTP backend demonstration. Returns results dict."""
    results = {}

    # --- Capabilities ---
    print("=== HTTP Backend Capabilities ===\n")
    results["supports_read"] = store.supports(Capability.READ)
    results["supports_write"] = store.supports(Capability.WRITE)
    print(f"READ supported: {results['supports_read']}")
    print(f"WRITE supported: {results['supports_write']}")

    # --- Unsupported operations raise CapabilityNotSupported ---
    print("\n=== Write Attempt (read-only) ===\n")
    try:
        store.write("test.txt", b"hello")
    except CapabilityNotSupported as exc:
        results["write_error"] = str(exc)
        print(f"Expected error: {exc}")

    return results


if __name__ == "__main__":
    # Point at a public HTTP endpoint (httpbin for demonstration)
    backend = ReadOnlyHttpBackend(
        base_url="https://httpbin.org/",
        timeout=10.0,
    )
    store = Store(backend=backend)
    try:
        demo(store)
    finally:
        store.close()
