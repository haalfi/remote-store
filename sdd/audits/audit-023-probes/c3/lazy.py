"""When does async read() refuse, and how much does its first chunk hold."""

from __future__ import annotations

import asyncio

from remote_store._kernel.aio_backend import AsyncDriverBackend
from remote_store.aio.backends._memory import AsyncMemoryBackend, AsyncMemoryDriver


class Terminal(AsyncMemoryDriver):
    close_is_terminal = True


class TerminalBackend(AsyncDriverBackend):
    close_is_terminal = True


async def main():
    b = AsyncMemoryBackend()
    for p in ("../x", "", "nope"):
        g = b.read(p)
        print(f"read({p!r}) call: returned {type(g).__name__} (no exception)")
        try:
            await g.__anext__()
        except Exception as e:  # noqa: BLE001
            print(f"   first anext: {type(e).__name__}: {e}")
    t = TerminalBackend(Terminal())
    await t.aclose()
    g = t.read("f")
    print("closed terminal read() call: returned", type(g).__name__)
    try:
        await g.__anext__()
    except Exception as e:  # noqa: BLE001
        print("   first anext:", type(e).__name__, e)

    size = 4 * 1024 * 1024
    await b.write("big", b"\0" * size)
    chunks = [len(c) async for c in b.read("big")]
    print(
        f"LAZY_READ declared={b.capabilities.supports(__import__('remote_store').Capability.LAZY_READ)};"
        f" file={size} chunks={len(chunks)} first_chunk={chunks[0]}"
    )


asyncio.run(main())
