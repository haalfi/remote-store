"""The Memory drivers' lifetime duties (spec 052 BE-038, BE-039), on both runtimes.

The kernel trusts a driver's stream to end where its client's data ends, and a
write handle to take ``abort`` after a failed ``commit``; these call the drivers
directly, so no kernel behaviour can stand in for the driver's.
"""

from __future__ import annotations

import asyncio

import pytest

from remote_store._errors import AlreadyExists
from remote_store.aio.backends._memory import AsyncMemoryDriver
from remote_store.backends._memory import MemoryDriver

_DATA = b"0123456789"


@pytest.mark.spec("BE-038")
def test_a_sync_stream_ends_after_the_last_stored_byte() -> None:
    driver = MemoryDriver()
    driver.put("f", _DATA, overwrite=False, metadata=None)
    stream = driver.get("f")
    read = b"".join(iter(lambda: stream.read(3), b""))
    assert read == _DATA
    assert stream.read() == b""


@pytest.mark.spec("BE-038")
def test_an_async_stream_ends_after_the_last_stored_byte() -> None:
    driver = AsyncMemoryDriver()

    async def run() -> bytes:
        await driver.put("f", _DATA, overwrite=False, metadata=None)
        return b"".join([chunk async for chunk in await driver.get("f")])

    assert asyncio.run(run()) == _DATA


@pytest.mark.spec("BE-039")
def test_a_sync_handle_takes_abort_after_a_failed_commit() -> None:
    driver = MemoryDriver()
    handle = driver.open_write("f", overwrite=False, metadata=None)
    handle.write(b"lost")
    driver.put("f", _DATA, overwrite=False, metadata=None)  # the conflict the commit meets
    with pytest.raises(AlreadyExists):
        handle.commit()
    handle.abort()
    handle.abort()
    assert driver.get("f").read() == _DATA


@pytest.mark.spec("BE-039")
def test_an_async_handle_takes_abort_after_a_failed_commit() -> None:
    driver = AsyncMemoryDriver()

    async def run() -> bytes:
        handle = await driver.open_write("f", overwrite=False, metadata=None)
        await handle.write(b"lost")
        await driver.put("f", _DATA, overwrite=False, metadata=None)
        with pytest.raises(AlreadyExists):
            await handle.commit()
        await handle.abort()
        await handle.abort()
        return b"".join([chunk async for chunk in await driver.get("f")])

    assert asyncio.run(run()) == _DATA
