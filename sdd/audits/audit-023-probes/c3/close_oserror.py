"""A driver stream whose close raises an OSError (inside the caught set): sync read vs async read."""

from __future__ import annotations

import asyncio
import io

from remote_store._kernel.aio_backend import AsyncDriverBackend
from remote_store._kernel.backend import DriverBackend
from remote_store.aio.backends._memory import AsyncMemoryDriver
from remote_store.backends._memory import MemoryDriver


class SyncStream(io.BytesIO):
    def close(self):
        if not self.closed:
            super().close()
            raise ConnectionResetError("close reset")


class AsyncStream:
    def __init__(self):
        self.done = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.done:
            raise StopAsyncIteration
        self.done = True
        return b"abc"

    async def aclose(self):
        raise ConnectionResetError("close reset")


class SD(MemoryDriver):
    def get(self, key):
        super().get(key)
        return SyncStream(b"abc")


class AD(AsyncMemoryDriver):
    async def get(self, key):
        await super().get(key)
        return AsyncStream()


def show(label, fn):
    try:
        print(label, "OK", fn())
    except BaseException as e:  # noqa: BLE001
        print(label, f"{type(e).__module__}.{type(e).__name__}: {e}")


sb, ab = DriverBackend(SD()), AsyncDriverBackend(AD())
sb.write("f", b"abc")
asyncio.run(ab.write("f", b"abc"))


def sync_read():
    s = sb.read("f")
    data = s.read()
    s.close()
    return data


async def async_read():
    return b"".join([c async for c in ab.read("f")])


show("sync read() + close():", sync_read)
show("sync read_bytes():", lambda: sb.read_bytes("f"))
show("async read():", lambda: asyncio.run(async_read()))
show("async read_bytes():", lambda: asyncio.run(ab.read_bytes("f")))
