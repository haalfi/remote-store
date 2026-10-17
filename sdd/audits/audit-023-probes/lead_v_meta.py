"""Verify c2 F1 (metadata aliasing), F2 (empty metadata echo), F8 (driver self-move)."""

import asyncio

from remote_store import Store
from remote_store.aio import AsyncStore
from remote_store.aio.backends import AsyncMemoryBackend
from remote_store.backends import MemoryBackend, MemoryDriver

s = Store(MemoryBackend())
s.write("a.txt", b"x", metadata={"k": "v"})
s.get_file_info("a.txt").metadata["k"] = "MUTATED"
print("sync stored after mutating info:", s.get_file_info("a.txt").metadata)
s.copy("a.txt", "b.txt")
s.get_file_info("b.txt").metadata["k"] = "VIA_DST"
print("sync src after mutating dst info:", s.get_file_info("a.txt").metadata)
r = s.write("e.txt", b"x", metadata={})
print("sync write metadata={} -> WriteResult.metadata", r.metadata, "| info", s.get_file_info("e.txt").metadata)


async def main() -> None:
    a = AsyncStore(AsyncMemoryBackend())
    await a.write("a.txt", b"x", metadata={"k": "v"})
    (await a.get_file_info("a.txt")).metadata["k"] = "MUTATED"
    print("async stored after mutating info:", (await a.get_file_info("a.txt")).metadata)
    r = await a.write("e.txt", b"x", metadata={})
    print("async write metadata={} ->", r.metadata)


asyncio.run(main())

d = MemoryDriver()
print("driver attrs:", [n for n in dir(d) if not n.startswith("__")][:40])
