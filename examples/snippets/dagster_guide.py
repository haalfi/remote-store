"""Dagster guide snippets — tested source for the Dagster Integration guide.

Named regions can be included in the guide via pymdownx.snippets:

    ```python
    ;--8<-- "examples/snippets/dagster_guide.py:multi-partition"
    ```

Run directly or via ``hatch run examples`` to verify all snippets.
The multi-partition example exercises load_input with a mocked
multi-partition InputContext to avoid requiring a running Dagster instance.
"""

# ruff: noqa: F811, F841

from __future__ import annotations

from typing import Any
from unittest import mock

from dagster import (
    AssetKey,
    IOManager,
    build_output_context,
)
from dagster import InputContext as _InputContext

from remote_store.backends import MemoryBackend


def demo() -> None:
    """Execute all dagster guide snippets."""
    _multi_partition()


def _multi_partition() -> None:
    # --8<-- [start:multi-partition]

    from dagster import (  # noqa: F811
        AssetIn,
        Definitions,
        MonthlyPartitionsDefinition,
        TimeWindowPartitionMapping,
        asset,
        io_manager,
    )

    from remote_store import Store  # noqa: F811
    from remote_store.backends import LocalBackend
    from remote_store.ext.dagster import dagster_io_manager  # noqa: F811

    monthly = MonthlyPartitionsDefinition(start_date="2026-01-01")

    @io_manager
    def my_io_manager() -> IOManager:
        store = Store(LocalBackend(root="/data/dagster"))
        return dagster_io_manager(store, serializer="json")

    @asset(partitions_def=monthly)
    def sales_monthly() -> dict:
        """Upstream asset — one partition per month."""
        return {"revenue": 100}

    @asset(
        partitions_def=monthly,
        ins={
            "sales_monthly": AssetIn(
                partition_mapping=TimeWindowPartitionMapping(start_offset=-2),
            ),
        },
    )
    def sales_rolling_3m(sales_monthly: dict[str, Any]) -> dict:
        """Downstream — receives last 3 months as dict[str, Any].

        ``sales_monthly`` is ``{"2026-01": {...}, "2026-02": {...}, "2026-03": {...}}``
        when the current partition is ``"2026-03"``.
        """
        total = sum(v["revenue"] for v in sales_monthly.values())
        return {"rolling_revenue": total}

    defs = Definitions(
        assets=[sales_monthly, sales_rolling_3m],
        resources={"io_manager": my_io_manager},
    )
    # --8<-- [end:multi-partition]

    # --- Verify the multi-partition load_input behavior ---
    store = Store(backend=MemoryBackend())
    mgr = dagster_io_manager(store, serializer="json")

    partitions = {"2026-01": {"revenue": 100}, "2026-02": {"revenue": 200}, "2026-03": {"revenue": 300}}
    for pk, obj in partitions.items():
        out_ctx = build_output_context(
            asset_key=AssetKey(["sales", "monthly"]),
            partition_key=pk,
        )
        mgr.handle_output(out_ctx, obj)

    ctx = mock.MagicMock(spec=_InputContext)
    ctx.asset_key = AssetKey(["sales", "monthly"])
    ctx.has_asset_partitions = True
    ctx.asset_partition_keys = ["2026-01", "2026-02", "2026-03"]

    result = mgr.load_input(ctx)
    assert isinstance(result, dict)
    assert len(result) == 3
    assert result == partitions

    # Verify the downstream logic works with the dict
    total = sum(v["revenue"] for v in result.values())
    assert total == 600

    store.close()


if __name__ == "__main__":
    demo()
    print("\nAll dagster guide snippets OK.")
