"""Capabilities and errors — Capability querying, gating, and the structured error hierarchy.

Demonstrates:
- Capability enum members and what they gate
- Store.supports() runtime capability checks
- CapabilityNotSupported when calling unsupported operations
- Error hierarchy: RemoteStoreError base, structured attributes
- to_key() and native_path() round-trip

---
see_also:
  - label: Capabilities Matrix
    url: ../../reference/capabilities-matrix.md
    note: per-backend capability reference
"""

from __future__ import annotations

from remote_store import (
    Capability,
    CapabilityNotSupported,
    CapabilitySet,
    InvalidPath,
    NotFound,
    RemoteStoreError,
    Store,
)
from remote_store.backends import MemoryBackend


def demo(store):
    """Capability system and error handling. Returns results dict."""
    results = {}

    # --- Capability enum ---
    print("=== Capability Enum ===\n")
    all_caps = list(Capability)
    results["all_capabilities"] = [c.value for c in all_caps]
    for cap in sorted(all_caps, key=lambda c: c.value):
        supported = store.supports(cap)
        marker = "+" if supported else "-"
        print(f"  [{marker}] {cap.value}")

    # --- CapabilitySet ---
    print("\n=== CapabilitySet ===\n")
    caps = CapabilitySet({Capability.READ, Capability.WRITE, Capability.LIST})
    results["capset_supports_read"] = caps.supports(Capability.READ)
    results["capset_supports_delete"] = caps.supports(Capability.DELETE)
    results["capset_len"] = len(caps)
    print(f"Custom set: {caps}")
    print(f"  supports READ: {caps.supports(Capability.READ)}")
    print(f"  supports DELETE: {caps.supports(Capability.DELETE)}")
    print(f"  len: {len(caps)}")

    # require() succeeds silently for supported capabilities
    caps.require(Capability.READ)
    print("  require(READ): OK")

    # require() raises for missing capabilities
    try:
        caps.require(Capability.GLOB, backend="example")
    except CapabilityNotSupported as exc:
        results["require_error"] = exc
        print(f"  require(GLOB): {type(exc).__name__}")
        print(f"    capability={exc.capability}, backend={exc.backend}")

    # --- Store.supports() ---
    print("\n=== Store.supports() ===\n")
    store.write("test.txt", b"hello")
    results["store_supports_read"] = store.supports(Capability.READ)
    results["store_supports_glob"] = store.supports(Capability.GLOB)
    print(f"READ: {store.supports(Capability.READ)}")
    print(f"GLOB: {store.supports(Capability.GLOB)}")
    print(f"ATOMIC_WRITE: {store.supports(Capability.ATOMIC_WRITE)}")

    # --- Error hierarchy ---
    print("\n=== Error Hierarchy ===\n")
    print("RemoteStoreError")
    for cls in [NotFound, InvalidPath, CapabilityNotSupported]:
        is_sub = issubclass(cls, RemoteStoreError)
        print(f"  {cls.__name__} (is RemoteStoreError: {is_sub})")
    results["hierarchy_check"] = issubclass(NotFound, RemoteStoreError)

    # Structured error attributes
    try:
        store.read_bytes("does-not-exist.txt")
    except NotFound as exc:
        results["error_path"] = exc.path
        results["error_backend"] = exc.backend
        print("\nNotFound attributes:")
        print(f"  path: {exc.path}")
        print(f"  backend: {exc.backend}")

    # InvalidPath with null byte
    try:
        store.read_bytes("bad\x00path.txt")
    except InvalidPath as exc:
        results["null_byte_error"] = exc
        print(f"\nInvalidPath (null byte): path={exc.path}")

    # --- to_key() and native_path() round-trip ---
    print("\n=== to_key() / native_path() ===\n")
    store.write("reports/q1.csv", b"revenue,100")
    native = store.native_path("reports/q1.csv")
    key = store.to_key(native)
    results["native_path"] = native
    results["round_trip_key"] = key
    print("key: 'reports/q1.csv'")
    print(f"native_path: '{native}'")
    print(f"to_key(native): '{key}'")
    print(f"round-trip matches: {key == 'reports/q1.csv'}")

    return results


if __name__ == "__main__":
    store = Store(backend=MemoryBackend())
    demo(store)
    print("\nDone!")
