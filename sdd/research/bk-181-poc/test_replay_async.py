"""BK-181 PoC -- async ``AsyncAzureBackend`` over a recorded HTTP cassette.

This is the make-or-break file for the mechanism choice. The async Azure
SDK rides ``AioHttpTransport`` (aiohttp), and vcrpy's aiohttp support is
the weakest of its stubs. If these tests cannot record-and-replay, the
verdict tilts away from ``pytest-recording`` toward a custom
``azure.core`` transport adapter.

Filesystem setup still uses the sync DataLake SDK (see ``conftest.py``);
the test *bodies* exercise the async path. ``asyncio_mode = "auto"`` in
``pyproject.toml`` makes the ``async def`` tests first-class without a
decorator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.vcr


async def test_async_write_read_roundtrip(async_azure_backend: object) -> None:
    """Happy-path baseline over ``AioHttpTransport``: ``write`` then ``read_bytes``."""
    payload = b"hello from the bk-181 async cassette/replay PoC"
    # overwrite=True keeps re-recording idempotent (see the sync sibling).
    await async_azure_backend.write("poc-happy-async.txt", payload, overwrite=True)  # type: ignore[attr-defined]

    assert await async_azure_backend.read_bytes("poc-happy-async.txt") == payload  # type: ignore[attr-defined]


async def test_async_bug197_read_bytes_on_hns_directory_returns_empty(
    async_azure_backend: object,
    hns_directory: Callable[[str], str],
) -> None:
    """The BUG-197 unhappy case on the async backend, replayed from a cassette.

    BUG-197 has an async sibling: ``AsyncAzureBackend.read_bytes(hns_dir)``
    also silently returns ``b""`` instead of raising ``InvalidPath``. The
    assertion freezes the current buggy behaviour; flip it to
    ``pytest.raises(InvalidPath)`` and re-record once the fix lands.
    """
    dirpath = hns_directory("poc-dir197-async")

    assert await async_azure_backend.read_bytes(dirpath) == b""  # type: ignore[attr-defined]
