"""Async/Sync bridge adapter snippets — tested source for the bridge guide.

Named regions can be included in any docs page via pymdownx.snippets:

    ```python
    --8<-- "examples/snippets/async_sync_bridges.py:sync-to-async"
    ```

Run directly or via ``hatch run examples`` to verify all snippets.
"""

from __future__ import annotations

import asyncio


def demo() -> None:
    """Execute all async/sync bridge adapter snippets."""
    asyncio.run(_sync_to_async())
    _async_to_sync()


async def _sync_to_async() -> None:
    # --8<-- [start:sync-to-async]
    from remote_store.aio import AsyncStore, SyncBackendAdapter  # noqa: F811
    from remote_store.backends import MemoryBackend  # noqa: F811

    backend = MemoryBackend()
    async_backend = SyncBackendAdapter(backend)

    async with AsyncStore(async_backend) as store:
        await store.write("report.csv", b"col,val\n1,2")
        content = await store.read_bytes("report.csv")
    # --8<-- [end:sync-to-async]
    assert content == b"col,val\n1,2"


def _async_to_sync() -> None:
    # --8<-- [start:async-to-sync]
    from remote_store import AsyncBackendSyncAdapter, Store  # noqa: F811
    from remote_store.aio import AsyncMemoryBackend  # noqa: F811

    async_backend = AsyncMemoryBackend()

    with AsyncBackendSyncAdapter(async_backend) as adapter:
        store = Store(adapter)
        store.write("report.csv", b"col,val\n1,2")
        content = store.read_bytes("report.csv")
    # --8<-- [end:async-to-sync]
    assert content == b"col,val\n1,2"


if __name__ == "__main__":
    demo()
    print("\nAll async/sync bridges snippets OK.")
