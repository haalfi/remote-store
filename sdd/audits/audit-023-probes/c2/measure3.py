"""Store-level metadata aliasing; MEM-015 max(modified_at); list_files metadata aliasing."""

from __future__ import annotations

import asyncio
import time

from remote_store import Store
from remote_store.aio import AsyncStore
from remote_store.aio.backends._memory import AsyncMemoryBackend
from remote_store.backends._memory import MemoryBackend

s = Store(backend=MemoryBackend())
s.write("a.txt", b"x", metadata={"k": "v"})
s.get_file_info("a.txt").metadata["k"] = "VIA_STORE_INFO"
next(iter(s.list_files(""))).metadata["k2"] = "VIA_LIST"
print("sync Store: stored metadata after mutating returned infos:", s.get_file_info("a.txt").metadata)


async def amain():
    st = AsyncStore(backend=AsyncMemoryBackend())
    await st.write("a.txt", b"x", metadata={"k": "v"})
    (await st.get_file_info("a.txt")).metadata["k"] = "VIA_STORE_INFO"
    return (await st.get_file_info("a.txt")).metadata


print("async Store: stored metadata after mutating returned info:", asyncio.run(amain()))

b = MemoryBackend()
b.write("d/one", b"1")
time.sleep(0.01)
b.write("d/sub/two", b"22")
t2 = b.get_file_info("d/sub/two").modified_at
time.sleep(0.01)
b.write("d/one", b"111", overwrite=True)
t1 = b.get_file_info("d/one").modified_at
fi = b.get_folder_info("d")
print(
    "MEM-015: folder modified_at == max:",
    fi.modified_at == max(t1, t2),
    "size:",
    fi.total_size,
    "count:",
    fi.file_count,
)
