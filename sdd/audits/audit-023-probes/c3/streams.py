"""Measure read-stream, close-error, content-error and cancellation behaviour, sync vs async kernel."""

from __future__ import annotations

import asyncio
import io

from remote_store._kernel.aio_backend import AsyncDriverBackend
from remote_store._kernel.backend import DriverBackend
from remote_store.aio.backends._memory import AsyncMemoryDriver
from remote_store.backends._memory import MemoryDriver

LOG: list[str] = []


def show(label, fn):
    try:
        r = fn()
        print(f"{label}: OK {r!r}")
    except BaseException as e:  # noqa: BLE001
        cause = e.__cause__
        ctx = e.__context__
        print(
            f"{label}: {type(e).__module__}.{type(e).__name__}: {e} | cause={type(cause).__name__ if cause else None}"
            f" | context={type(ctx).__name__ if ctx else None}"
        )


# ---------------------------------------------------------------- stream doubles
class SyncBad(io.RawIOBase):
    def __init__(self, mode):
        self.mode, self.n = mode, 0

    def readable(self):
        return True

    def readinto(self, b):
        self.n += 1
        if self.mode in ("mid", "mid+close") and self.n >= 2:
            raise OSError("wire dropped")
        if self.n > 3:
            return 0
        b[:1] = b"x"
        return 1

    def close(self):
        LOG.append("sync-close")
        if self.mode in ("close", "mid+close") and not self.closed:
            super().close()
            raise RuntimeError("close boom")
        super().close()


class AsyncBad:
    def __init__(self, mode):
        self.mode, self.n = mode, 0

    def __aiter__(self):
        if self.mode == "aiter":
            raise OSError("aiter dropped")
        return self

    async def __anext__(self):
        self.n += 1
        if self.mode in ("mid", "mid+close") and self.n >= 2:
            raise OSError("wire dropped")
        if self.n > 3:
            raise StopAsyncIteration
        return b"x"

    async def aclose(self):
        LOG.append("async-aclose")
        if self.mode in ("close", "mid+close"):
            raise RuntimeError("close boom")


class SD(MemoryDriver):
    mode = "ok"

    def get(self, key):
        super().get(key)
        return SyncBad(self.mode)


class AD(AsyncMemoryDriver):
    mode = "ok"

    async def get(self, key):
        await super().get(key)
        return AsyncBad(self.mode)


async def drain(gen):
    return b"".join([c async for c in gen])


def main():
    loop = asyncio.new_event_loop()
    run = loop.run_until_complete

    for mode in ("ok", "mid", "close", "mid+close", "aiter"):
        sd, ad = SD(), AD()
        sd.mode = ad.mode = mode
        sb, ab = DriverBackend(sd), AsyncDriverBackend(ad)
        sb.write("f", b"abc")
        run(ab.write("f", b"abc"))
        LOG.clear()

        def sync_read():
            s = sb.read("f")
            try:
                return s.read()
            finally:
                s.close()

        if mode != "aiter":
            show(f"[{mode}] sync read()", sync_read)
            print("   log:", list(LOG))
            LOG.clear()
            show(f"[{mode}] sync read_bytes()", lambda: sb.read_bytes("f"))
            print("   log:", list(LOG))
            LOG.clear()
        show(f"[{mode}] async read()", lambda: run(drain(ab.read("f"))))
        print("   log:", list(LOG))
        LOG.clear()
        show(f"[{mode}] async read_bytes()", lambda: run(ab.read_bytes("f")))
        print("   log:", list(LOG))

    # laziness of NotFound
    sb, ab = DriverBackend(MemoryDriver()), AsyncDriverBackend(AsyncMemoryDriver())
    show("sync read('nope') call", lambda: sb.read("nope"))
    show("async read('nope') call (no iteration)", lambda: ab.read("nope"))
    show("async read('nope') first anext", lambda: run(ab.read("nope").__anext__()))

    # caller content raising mid-write: verbatim?
    class SyncContentBad(io.RawIOBase):
        def readable(self):
            return True

        def readinto(self, b):
            raise ValueError("caller content broke")

    async def async_content_bad():
        yield b"a"
        raise ValueError("caller content broke")

    show("sync write content error", lambda: sb.write("w", SyncContentBad()))
    show("async write content error", lambda: run(ab.write("w", async_content_bad())))
    show("sync write_atomic content error", lambda: sb.write_atomic("w", SyncContentBad()))
    show("async write_atomic content error", lambda: run(ab.write_atomic("w", async_content_bad())))
    show("sync w exists", lambda: sb.exists("w"))
    show("async w exists", lambda: run(ab.exists("w")))

    # an OSError from the caller's content: classified or verbatim?
    async def async_content_oserror():
        yield b"a"
        raise OSError("caller disk")

    class SyncContentOSErr(io.RawIOBase):
        def readable(self):
            return True

        def readinto(self, b):
            raise OSError("caller disk")

    show("sync write content OSError", lambda: sb.write("w2", SyncContentOSErr()))
    show("async write content OSError", lambda: run(ab.write("w2", async_content_oserror())))

    # cancellation mid-write
    started = asyncio.Event()

    async def slow_content():
        yield b"part"
        started.set()
        await asyncio.sleep(3600)
        yield b"never"

    async def cancel_write(method):
        started.clear()
        t = asyncio.ensure_future(getattr(ab, method)("cancelled.txt", slow_content()))
        await started.wait()
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            return "cancelled", await ab.exists("cancelled.txt")
        return "not cancelled", None

    show("cancel write", lambda: run(cancel_write("write")))
    show("cancel write_atomic", lambda: run(cancel_write("write_atomic")))

    # cancellation mid-read: does the driver stream get aclosed?
    class AD2(AsyncMemoryDriver):
        async def get(self, key):
            await super().get(key)

            async def gen():
                try:
                    yield b"1"
                    await asyncio.sleep(3600)
                    yield b"2"
                finally:
                    LOG.append("driver-stream-finally")

            return gen()

    ab2 = AsyncDriverBackend(AD2())
    run(ab2.write("r", b"x"))
    LOG.clear()

    async def cancel_read():
        got = asyncio.Event()

        async def consume():
            async for _ in ab2.read("r"):
                got.set()

        t = asyncio.ensure_future(consume())
        await got.wait()
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            return "cancelled"
        return "?"

    show("cancel mid-read", lambda: run(cancel_read()))
    print("   log:", list(LOG))
    LOG.clear()

    async def abandon_read():
        g = ab2.read("r")
        await g.__anext__()
        await g.aclose()

    show("abandon (aclose) mid-read", lambda: run(abandon_read()))
    print("   log:", list(LOG))
    loop.close()


main()
