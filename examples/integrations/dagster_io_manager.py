"""Dagster IO Manager -- use any Store as a Dagster IOManager.

Demonstrates:
- dagster_io_manager(): wrapping a Store for Dagster
- Pickle roundtrip: write and read back a Python object
- Partitioned assets: path includes partition key
- JSON serializer: alternative serializer choice
"""

from __future__ import annotations

from dagster import AssetKey, build_input_context, build_output_context

from remote_store import Store
from remote_store.backends import MemoryBackend
from remote_store.ext.dagster import dagster_io_manager


def demo() -> dict:
    """Dagster IO manager adapter demo. Returns results for test verification."""
    results: dict = {}
    store = Store(backend=MemoryBackend())

    # --- Pickle roundtrip ---
    print("=== Pickle roundtrip ===")
    mgr = dagster_io_manager(store, serializer="pickle")
    obj = {"users": [{"name": "Alice"}, {"name": "Bob"}]}

    out_ctx = build_output_context(asset_key=AssetKey(["raw", "users"]))
    mgr.handle_output(out_ctx, obj)
    print(f"  Wrote to: raw/users.pkl (exists={store.exists('raw/users.pkl')})")

    in_ctx = build_input_context(
        asset_key=AssetKey(["raw", "users"]),
        upstream_output=out_ctx,
    )
    loaded = mgr.load_input(in_ctx)
    print(f"  Loaded: {loaded}")
    results["pickle_roundtrip"] = loaded == obj
    print()

    # --- Partitioned asset ---
    print("=== Partitioned asset ===")
    partition_data = {"revenue": 42_000}

    part_ctx = build_output_context(
        asset_key=AssetKey(["metrics", "monthly"]),
        partition_key="2026-01",
    )
    mgr.handle_output(part_ctx, partition_data)
    path = "metrics/monthly/2026-01.pkl"
    print(f"  Partitioned path: {path} (exists={store.exists(path)})")
    results["partition_path_exists"] = store.exists(path)
    print()

    # --- JSON serializer ---
    print("=== JSON serializer ===")
    json_mgr = dagster_io_manager(store, serializer="json")
    config = {"version": 3, "debug": False}

    json_out = build_output_context(asset_key=AssetKey(["config"]))
    json_mgr.handle_output(json_out, config)
    print(f"  Wrote config.json (exists={store.exists('config.json')})")

    json_in = build_input_context(
        asset_key=AssetKey(["config"]),
        upstream_output=json_out,
    )
    loaded_config = json_mgr.load_input(json_in)
    print(f"  Loaded: {loaded_config}")
    results["json_roundtrip"] = loaded_config == config

    store.close()
    return results


if __name__ == "__main__":
    demo()
    print("\nDone!")
