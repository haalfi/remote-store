"""C5 audit probe 3: metadata={} echo through Store and async; async folder_stats omission; oracle iter_children/nested list_folders."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from remote_store import Store  # noqa: E402
from remote_store.aio.backends._memory import AsyncMemoryBackend  # noqa: E402
from remote_store.backends._memory import MemoryBackend  # noqa: E402
from tests.backends.dafny._helpers import DafnyOracleBackend  # noqa: E402

print("metadata={} echo")
print("  MemoryBackend.write:", MemoryBackend().write("x", b"1", metadata={}).metadata)
print("  Store(MemoryBackend).write:", Store(backend=MemoryBackend()).write("x", b"1", metadata={}).metadata)
print(
    "  Store(MemoryBackend).write_atomic:", Store(backend=MemoryBackend()).write_atomic("x", b"1", metadata={}).metadata
)
print("  Store(Oracle).write:", Store(backend=DafnyOracleBackend()).write("x", b"1", metadata={}).metadata)


async def amain() -> None:
    b = AsyncMemoryBackend()
    r = await b.write("x", b"1", metadata={})
    print("  AsyncMemoryBackend.write:", r.metadata)
    # BE-030 omission vs folder_stats push-down, async
    await b.write("a/ok", b"12")
    await b._driver.put("a/./hidden", b"xyz", overwrite=False, metadata=None)
    files = [str(f.path) async for f in b.list_files("a", recursive=True)]
    fi = await b.get_folder_info("a")
    print("  async list_files('a', recursive):", files, " get_folder_info('a'):", fi.file_count, fi.total_size)


asyncio.run(amain())

print("oracle nested folders")
o = DafnyOracleBackend()
o.write("ic/a.txt", b"a")
o.write("ic/sub/deep/c.txt", b"c")
m = MemoryBackend()
m.write("ic/a.txt", b"a")
m.write("ic/sub/deep/c.txt", b"c")
for name, b in (("oracle", o), ("kernel", m)):
    print(f"  [{name}] list_folders('ic'):", sorted(str(f.path) for f in b.list_folders("ic")))
    print(f"  [{name}] iter_children('ic'):", sorted(str(c.path) for c in b.iter_children("ic")))
