"""``AsyncMemoryDriver.open_write``, called on the driver.

The async kernel never reaches it: ``put_is_atomic`` sends ``write_atomic`` to
``put`` first, and ``AsyncBackend`` has no ``open_atomic``. The driver is public,
so its handle is held to SAW-012's terms here directly: refused on open as the
commit would refuse, committed by the atomic ``put``, and dropped on abort.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from remote_store._errors import AlreadyExists, InvalidPath
from remote_store.aio.backends._memory import AsyncMemoryDriver


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _seeded() -> AsyncMemoryDriver:
    driver = AsyncMemoryDriver()
    await driver.put("f", b"old", overwrite=False, metadata=None)
    await driver.put("d/x", b"x", overwrite=False, metadata=None)
    return driver


@pytest.mark.spec("SAW-012", "MEM-013")
@pytest.mark.parametrize(
    ("key", "overwrite", "refused"),
    [
        pytest.param("f", False, AlreadyExists, id="existing-file"),
        pytest.param("d", True, InvalidPath, id="folder-at-key"),
        pytest.param("f/g", True, InvalidPath, id="file-above-key"),
    ],
)
def test_open_refuses_what_the_commit_would(key: str, overwrite: bool, refused: type[Exception]) -> None:
    async def scenario() -> None:
        driver = await _seeded()
        with pytest.raises(refused):
            await driver.open_write(key, overwrite=overwrite, metadata=None)
        assert driver.counts == (2, 1)

    _run(scenario())


@pytest.mark.spec("SAW-012", "MEM-013")
def test_commit_stores_the_buffered_bytes_with_metadata() -> None:
    async def scenario() -> None:
        driver = await _seeded()
        handle = await driver.open_write("n/new", overwrite=False, metadata={"k": "v"})
        await handle.write(b"ab")
        await handle.write(b"cd")
        assert await driver.stat("n/new") is None  # nothing visible before the commit
        result = await handle.commit()
        assert result.size == 4
        entry = await driver.stat("n/new")
        assert entry is not None
        assert entry.size == 4
        assert entry.metadata == {"k": "v"}
        chunks = [c async for c in await driver.get("n/new")]
        assert b"".join(chunks) == b"abcd"

    _run(scenario())


@pytest.mark.spec("SAW-012")
def test_commit_rechecks_a_file_created_after_open() -> None:
    async def scenario() -> None:
        driver = await _seeded()
        handle = await driver.open_write("late", overwrite=False, metadata=None)
        await handle.write(b"mine")
        await driver.put("late", b"theirs", overwrite=False, metadata=None)
        with pytest.raises(AlreadyExists):
            await handle.commit()
        chunks = [c async for c in await driver.get("late")]
        assert b"".join(chunks) == b"theirs"

    _run(scenario())


@pytest.mark.spec("SAW-012")
def test_abort_stores_nothing() -> None:
    async def scenario() -> None:
        driver = await _seeded()
        handle = await driver.open_write("gone", overwrite=False, metadata=None)
        await handle.write(b"partial")
        await handle.abort()
        assert await driver.stat("gone") is None
        assert driver.counts == (2, 1)

    _run(scenario())
