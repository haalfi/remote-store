"""Metadata that is not a mapping, on both Memory classes called directly (spec 013 MEM-020, 003 BE-030).

``Store`` refuses it before the backend is reached, so each test calls the
backend itself: the kernel refuses it with ``ValueError`` before the tree sees
it, and no parent folder is made.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from remote_store.aio.backends._memory import AsyncMemoryBackend
from remote_store.backends._memory import MemoryBackend

_NOT_A_MAPPING: dict[str, object] = {"int": 5, "str": "ab", "pairs": [("k", "v")], "empty-list": []}


def _run(result: Any) -> Any:
    return asyncio.run(result) if inspect.iscoroutine(result) else result


@pytest.mark.spec("MEM-020", "BE-030", "WR-011")
@pytest.mark.parametrize("value", sorted(_NOT_A_MAPPING))
@pytest.mark.parametrize("member", ["write", "write_atomic"])
@pytest.mark.parametrize("runtime", ["sync", "async"])
def test_metadata_that_is_not_a_mapping_never_reaches_the_tree(runtime: str, member: str, value: str) -> None:
    backend: Any = MemoryBackend() if runtime == "sync" else AsyncMemoryBackend()
    with pytest.raises(ValueError, match="must be a mapping"):
        _run(getattr(backend, member)("d/f", b"x", metadata=_NOT_A_MAPPING[value]))
    assert not _run(backend.exists("d/f"))
    assert not _run(backend.exists("d"))
