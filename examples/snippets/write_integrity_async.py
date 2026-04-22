"""Async write-integrity snippets -- sourced by docs-src/write-integrity.md.

Named regions are included via pymdownx.snippets ``--8<--`` syntax.
Run directly (``python examples/snippets/write_integrity_async.py``) to verify.
"""

from __future__ import annotations

import asyncio

from remote_store.aio import AsyncMemoryBackend, AsyncStore


async def _async_write_with_hash() -> None:
    # --8<-- [start:async-write-with-hash]
    from remote_store.aio.ext.write import write_with_hash

    store = AsyncStore(AsyncMemoryBackend())
    result = await write_with_hash(store, "report.csv", b"col1,col2\n1,2\n")

    print(result.digest.algorithm)  # sha256
    print(result.digest.value)  # hex digest
    # --8<-- [end:async-write-with-hash]
    assert result.digest is not None
    assert result.digest.algorithm == "sha256"
    assert len(result.digest.value) == 64


async def demo() -> None:
    """Execute all async write-integrity snippets."""
    await _async_write_with_hash()


if __name__ == "__main__":
    asyncio.run(demo())
