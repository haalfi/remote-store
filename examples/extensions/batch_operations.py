"""Batch operations — Bulk delete, copy, and existence checks with error aggregation.

Demonstrates:
- batch_exists: check multiple paths at once
- batch_copy: copy multiple files, collecting errors
- batch_delete: delete multiple files with missing_ok and stop_on_error
- BatchResult: inspecting succeeded/failed paths
- Error collection: continuing past individual failures

---
see_also:
  - label: Batch Operations
    url: ../how-to/batch-operations.md
    note: bulk operations guide
"""

from __future__ import annotations

from remote_store import (
    BackendConfig,
    Registry,
    RegistryConfig,
    StoreProfile,
    batch_copy,
    batch_delete,
    batch_exists,
)


def demo(store):
    """Batch operations with error collection. Returns results dict."""
    results = {}

    # --- Set up some files ---
    for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
        store.write(name, f"content of {name}".encode())
    print("Wrote 4 files: a.txt, b.txt, c.txt, d.txt")

    # --- batch_exists ---
    exists = batch_exists(store, ["a.txt", "b.txt", "missing.txt"])
    results["exists"] = exists
    print(f"\nbatch_exists: {exists}")

    # --- batch_copy ---
    result = batch_copy(
        store,
        [("a.txt", "a_copy.txt"), ("b.txt", "b_copy.txt")],
    )
    results["copy_ok"] = result
    print("\nbatch_copy result:")
    print(f"  succeeded: {result.succeeded}")
    print(f"  all_succeeded: {result.all_succeeded}")
    print(f"  total: {result.total}")
    print(f"  a_copy.txt exists: {store.exists('a_copy.txt')}")
    print(f"  b_copy.txt exists: {store.exists('b_copy.txt')}")

    # --- batch_copy with errors (overwrite=False, destination exists) ---
    result = batch_copy(
        store,
        [("c.txt", "a_copy.txt"), ("d.txt", "new.txt")],
    )
    results["copy_partial"] = result
    print("\nbatch_copy (partial failure):")
    print(f"  succeeded: {result.succeeded}")
    print(f"  failed keys: {list(result.failed.keys())}")
    print(f"  error type: {type(result.failed.get('c.txt')).__name__}")

    # --- batch_delete ---
    result = batch_delete(store, ["a.txt", "b.txt"])
    results["delete_ok"] = result
    print("\nbatch_delete:")
    print(f"  succeeded: {result.succeeded}")
    print(f"  all_succeeded: {result.all_succeeded}")

    # --- batch_delete with missing_ok ---
    result = batch_delete(store, ["c.txt", "already_gone.txt"], missing_ok=True)
    results["delete_missing_ok"] = result
    print("\nbatch_delete (missing_ok=True):")
    print(f"  succeeded: {result.succeeded}")
    print(f"  all_succeeded: {result.all_succeeded}")

    # --- batch_delete with stop_on_error ---
    result = batch_delete(store, ["d.txt", "gone.txt", "a_copy.txt"], stop_on_error=True)
    results["delete_stop_on_error"] = result
    print("\nbatch_delete (stop_on_error=True):")
    print(f"  succeeded: {result.succeeded}")
    print(f"  failed keys: {list(result.failed.keys())}")
    print(f"  total processed: {result.total}")

    # --- Final state ---
    remaining = batch_exists(
        store,
        ["a.txt", "b.txt", "c.txt", "d.txt", "a_copy.txt", "b_copy.txt", "new.txt"],
    )
    results["final_state"] = remaining
    still_here = [k for k, v in remaining.items() if v]
    print(f"\nRemaining files: {still_here}")

    return results


if __name__ == "__main__":
    config = RegistryConfig(
        backends={"mem": BackendConfig(type="memory", options={})},
        stores={"data": StoreProfile(backend="mem", root_path="data")},
    )

    with Registry(config) as registry:
        store = registry.get_store("data")
        demo(store)

    print("\nDone!")
