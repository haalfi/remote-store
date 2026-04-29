"""Async write-integrity snippets — sourced by docs-src/how-to/write-integrity.md and docs-src/how-to/async.md.

Named regions are included via pymdownx.snippets ``--8<--`` syntax.
Run directly (``python examples/snippets/write_integrity_async.py``) to verify.
"""

from __future__ import annotations

import asyncio

from remote_store.aio import AsyncMemoryBackend, AsyncStore


def _async_quick_start() -> None:
    # --8<-- [start:async-quick-start]
    import asyncio

    from remote_store.aio import AsyncStore
    from remote_store.backends import MemoryBackend

    async def main() -> None:
        async with AsyncStore(MemoryBackend(), root_path="reports") as store:
            result = await store.write("summary.txt", b"Q1 results", overwrite=True)
            print(f"wrote {result.size} bytes")
            data = await store.read_bytes("summary.txt")
            print(data.decode())

    asyncio.run(main())
    # --8<-- [end:async-quick-start]


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


async def _async_iterator_write() -> None:
    # --8<-- [start:async-iterator-write]
    store = AsyncStore(AsyncMemoryBackend())

    async def generate_report():
        yield b"header\n"
        yield b"row1\n"
        yield b"row2\n"

    result = await store.write("report.csv", generate_report())
    print(f"wrote {result.size} bytes to {result.path}")
    # --8<-- [end:async-iterator-write]
    assert result.size == len(b"header\nrow1\nrow2\n")


async def demo() -> None:
    """Execute all async write-integrity snippets."""
    await _async_write_with_hash()
    await _async_iterator_write()


if __name__ == "__main__":
    _async_quick_start()
    asyncio.run(demo())
