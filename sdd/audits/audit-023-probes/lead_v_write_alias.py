"""Audit-023 T1, write side: is WriteResult.metadata the caller's own dict?"""

import asyncio

from remote_store import Store
from remote_store.aio import AsyncStore
from remote_store.aio.backends import AsyncMemoryBackend
from remote_store.backends import MemoryBackend

m = {"k": "v"}
r = Store(MemoryBackend()).write("a.txt", b"x", metadata=m)
m["k"] = "CALLER"
print("sync WriteResult.metadata after caller mutates its dict:", r.metadata, "| is caller's:", r.metadata is m)


async def main() -> None:
    m2 = {"k": "v"}
    r2 = await AsyncStore(AsyncMemoryBackend()).write("a.txt", b"x", metadata=m2)
    m2["k"] = "CALLER"
    print("async WriteResult.metadata after caller mutates its dict:", r2.metadata, "| is caller's:", r2.metadata is m2)


asyncio.run(main())
