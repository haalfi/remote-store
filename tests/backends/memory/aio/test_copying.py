"""``AsyncMemoryBackend`` copies and pickles, as it did before it moved onto the kernel."""

from __future__ import annotations

import asyncio
import copy
import pickle
from typing import Any

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store.aio.backends._memory import AsyncMemoryBackend


class _Narrow(AsyncMemoryBackend):
    CAPABILITIES = CapabilitySet({Capability.READ, Capability.WRITE, Capability.LIST})


@pytest.mark.spec("MEM-001", "MEM-003")
@pytest.mark.parametrize("clone", [copy.deepcopy, lambda b: pickle.loads(pickle.dumps(b))], ids=["deepcopy", "pickle"])
@pytest.mark.parametrize("cls", [AsyncMemoryBackend, _Narrow], ids=["default", "narrowed"])
def test_a_backend_clones_with_its_capabilities_and_contents(clone: Any, cls: type) -> None:
    backend = cls()
    asyncio.run(backend.write("d/f", b"x"))
    copied = clone(backend)
    assert repr(copied) == "AsyncMemoryBackend(files=1, folders=1)"
    assert set(copied.capabilities) == set(cls.CAPABILITIES)
    assert asyncio.run(copied.read_bytes("d/f")) == b"x"
