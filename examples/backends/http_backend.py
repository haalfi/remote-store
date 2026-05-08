"""HTTP backend — Read-only access to files over HTTP/HTTPS — no credentials needed for public endpoints.

Demonstrates:
- Creating a ReadOnlyHttpBackend with base_url
- Reading files and metadata from an HTTP endpoint
- Capability-gated error handling for unsupported operations
- Transport selection (urllib, requests, httpx)

---
see_also:
  - label: HTTP Backend
    url: ../../guides/backends/http.md
    note: backend guide
"""

from __future__ import annotations

from typing import Any

from remote_store import Capability, CapabilityNotSupported, Store
from remote_store.backends import ReadOnlyHttpBackend


def demo(store: Store) -> dict[str, Any]:
    """HTTP backend demonstration. Returns results dict."""
    results: dict[str, Any] = {}

    # --- Capabilities ---
    print("=== HTTP Backend Capabilities ===\n")
    results["supports_read"] = store.supports(Capability.READ)
    results["supports_write"] = store.supports(Capability.WRITE)
    print(f"READ supported: {results['supports_read']}")
    print(f"WRITE supported: {results['supports_write']}")

    # --- Read files ---
    print("\n=== Reading Files ===\n")
    content = store.read_bytes("hello.txt")
    results["read_content"] = content
    print(f"Content of hello.txt: {content!r}")

    text = store.read_text("hello.txt")
    results["read_text"] = text
    print(f"Text: {text}")

    # --- Metadata ---
    print("\n=== File Metadata ===\n")
    info = store.get_file_info("hello.txt")
    results["size"] = info.size
    results["content_type"] = info.content_type
    print(f"Size: {info.size} bytes")
    print(f"Content-Type: {info.content_type}")
    print(f"Modified: {info.modified_at}")
    print(f"ETag: {info.etag}")

    # --- Unsupported operations raise CapabilityNotSupported ---
    print("\n=== Write Attempt (read-only) ===\n")
    try:
        store.write("test.txt", b"hello")
    except CapabilityNotSupported as exc:
        results["write_error"] = str(exc)
        print(f"Expected error: {exc}")

    return results


if __name__ == "__main__":
    # --- Transport selection ---
    # The backend auto-detects the best HTTP library (httpx > requests > urllib).
    # Override with http_client= to force a specific transport:
    #
    #   ReadOnlyHttpBackend(base_url=..., http_client="urllib")
    #   ReadOnlyHttpBackend(base_url=..., http_client="requests")
    #   ReadOnlyHttpBackend(base_url=..., http_client="httpx")

    backend = ReadOnlyHttpBackend(
        base_url="https://data.example.com/datasets/",
        timeout=10.0,
    )
    store = Store(backend=backend)
    try:
        demo(store)
    finally:
        store.close()
