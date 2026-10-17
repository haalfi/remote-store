"""Cancellation on the async kernel's two non-atomic write_atomic routes (handle, temp+rename)."""

from __future__ import annotations

import asyncio

from remote_store._kernel.aio_backend import AsyncDriverBackend
from remote_store.aio.backends._memory import AsyncMemoryDriver

LOG: list[str] = []


class HandleDriver(AsyncMemoryDriver):
    put_is_atomic = False

    async def open_write(self, key, *, overwrite, metadata):
        h = await super().open_write(key, overwrite=overwrite, metadata=metadata)
        orig_abort = h.abort

        async def abort():
            LOG.append("handle-abort")
            await orig_abort()

        class Wrap:
            write = h.write
            commit = h.commit

        w = Wrap()
        w.abort = abort
        return w


class RenameDriver(AsyncMemoryDriver):
    put_is_atomic = False
    open_write = None  # not offered
    rename_replaces = True

    async def put(self, key, content, *, overwrite, metadata):
        # a wire that makes the object visible before the body is complete
        async with self._lock:
            self._tree.put(key, bytearray(b""), overwrite=True, metadata=None)
        LOG.append(f"partial-put {key}")
        return await super().put(key, content, overwrite=True, metadata=metadata)

    async def rename(self, src, dst, *, replace):
        async with self._lock:
            self._tree.move(src, dst, overwrite=replace)

    async def delete(self, key):
        LOG.append(f"delete {key}")
        await super().delete(key)


async def scenario(driver_cls):
    LOG.clear()
    b = AsyncDriverBackend(driver_cls())
    started = asyncio.Event()

    async def slow():
        yield b"part"
        started.set()
        await asyncio.sleep(3600)
        yield b"never"

    t = asyncio.ensure_future(b.write_atomic("d/target.txt", slow()))
    await started.wait()
    await asyncio.sleep(0)
    t.cancel()
    try:
        await t
        outcome = "completed"
    except asyncio.CancelledError:
        outcome = "cancelled"
    files = [f.path.path if hasattr(f.path, "path") else str(f.path) async for f in b.list_files("", recursive=True)]
    return outcome, files, list(LOG)


async def scenario_wait_for(driver_cls):
    """Cancellation via asyncio.wait_for timeout."""
    LOG.clear()
    b = AsyncDriverBackend(driver_cls())

    async def slow():
        yield b"part"
        await asyncio.sleep(3600)

    try:
        await asyncio.wait_for(b.write_atomic("t.txt", slow()), 0.05)
        outcome = "completed"
    except TimeoutError:
        outcome = "timeout"
    files = [str(f.path) async for f in b.list_files("", recursive=True)]
    return outcome, files, list(LOG)


for cls in (HandleDriver, RenameDriver):
    print(cls.__name__, asyncio.run(scenario(cls)))
    print(cls.__name__, "wait_for", asyncio.run(scenario_wait_for(cls)))
