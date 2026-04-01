"""Dagster v2 Resource -- config-driven Store construction with RemoteStoreIOManager.

Demonstrates:
- RemoteStoreIOManager: IO manager factory that constructs and owns a Store
- setup_for_execution / teardown_after_execution: manual lifecycle outside orchestrator
- Pickle roundtrip through the config-driven IO manager
"""

from __future__ import annotations

from dagster import AssetKey, build_init_resource_context, build_input_context, build_output_context

from remote_store.ext.dagster import RemoteStoreIOManager


def demo() -> dict:
    """Dagster v2 resource demo. Returns results for test verification."""
    results: dict = {}

    # --- Create IO manager factory from config ---
    print("=== RemoteStoreIOManager (memory backend) ===")
    factory = RemoteStoreIOManager(
        backend_type="memory",
        backend_options={},
        serializer="pickle",
    )

    # Manually drive the lifecycle (no Dagster orchestrator present)
    factory.setup_for_execution(context=build_init_resource_context())
    io_mgr = factory.create_io_manager(context=build_init_resource_context())
    print("  IO manager created with memory backend")
    print()

    # --- Pickle roundtrip ---
    print("=== Pickle roundtrip ===")
    obj = {"pipeline": "v2-demo", "records": [10, 20, 30]}

    out_ctx = build_output_context(asset_key=AssetKey(["processed", "records"]))
    io_mgr.handle_output(out_ctx, obj)
    print("  Wrote processed/records.pkl")

    in_ctx = build_input_context(
        asset_key=AssetKey(["processed", "records"]),
        upstream_output=out_ctx,
    )
    loaded = io_mgr.load_input(in_ctx)
    print(f"  Loaded: {loaded}")
    results["pickle_roundtrip"] = loaded == obj
    print()

    # --- Teardown ---
    factory.teardown_after_execution(context=build_init_resource_context())
    print("  Store torn down")
    results["teardown_ok"] = True

    return results


if __name__ == "__main__":
    demo()
    print("\nDone!")
