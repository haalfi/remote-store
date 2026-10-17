"""WR-012 empty-mapping echo through Store, both runtimes, and a non-USER_METADATA subclass."""

from __future__ import annotations

import asyncio

from remote_store import Store
from remote_store._capabilities import Capability, CapabilitySet
from remote_store.aio import AsyncStore
from remote_store.aio.backends._memory import AsyncMemoryBackend
from remote_store.backends._memory import MemoryBackend

s = Store(backend=MemoryBackend())
print("sync Store write(metadata={}).metadata:", s.write("a", b"x", metadata={}).metadata)


async def amain():
    st = AsyncStore(backend=AsyncMemoryBackend())
    r = await st.write("a", b"x", metadata={})
    return r.metadata


print("async Store write(metadata={}).metadata:", asyncio.run(amain()))


class NoUserMeta(MemoryBackend):
    CAPABILITIES = CapabilitySet(set(MemoryBackend.CAPABILITIES) - {Capability.USER_METADATA})


b = NoUserMeta()
r = b.write("a", b"x", metadata={})
print(
    "no-USER_METADATA subclass: declares",
    b.capabilities.supports(Capability.USER_METADATA),
    "WriteResult.metadata:",
    r.metadata,
    "is not None:",
    r.metadata is not None,
)
