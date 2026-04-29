"""Async Store — Async/await usage with `AsyncStore` -- streaming reads, async writes, child stores.

Demonstrates the async Store API with read, write, listing, and child
store patterns.

---
see_also:
  - label: Async Store
    url: ../how-to/async.md
    note: async usage guide
  - label: Async API
    url: ../api/aio.md
    note: API reference
"""

from __future__ import annotations

import asyncio

from remote_store.aio import AsyncMemoryBackend, AsyncStore


async def demo(store: AsyncStore) -> None:
    """Run all async Store demos against the given store."""
    # --- Write and read back ---
    await store.write("hello.txt", b"Hello, async world!")
    text = await store.read_text("hello.txt")
    print(f"read_text: {text}")

    # --- Streaming read ---
    await store.write("chunks.bin", b"AAAA" * 100)
    total = 0
    async for chunk in store.read("chunks.bin"):
        total += len(chunk)
    print(f"streaming read: {total} bytes")

    # --- Write from async iterator ---
    async def row_generator():
        yield b"id,value\n"
        for i in range(3):
            yield f"{i},{i * 10}\n".encode()

    await store.write("data.csv", row_generator())
    print(f"async iterator write: {await store.read_text('data.csv')}", end="")

    # --- Listing ---
    await store.write("reports/q1.txt", b"q1")
    await store.write("reports/q2.txt", b"q2")
    files = [fi.name async for fi in store.list_files("reports")]
    print(f"list_files: {sorted(files)}")

    # --- Child store ---
    child = store.child("reports")
    child_text = await child.read_text("q1.txt")
    print(f"child read: {child_text}")

    # --- Metadata ---
    info = await store.get_file_info("hello.txt")
    print(f"file info: size={info.size}, name={info.name}")
    assert await store.exists("hello.txt")
    assert await store.is_file("hello.txt")
    assert not await store.is_folder("hello.txt")

    print("All async demos passed.")


async def main() -> None:
    """Entry point: run demo with AsyncMemoryBackend."""
    async with AsyncStore(AsyncMemoryBackend(), root_path="demo") as store:
        await demo(store)


if __name__ == "__main__":
    asyncio.run(main())
