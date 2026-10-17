"""Audit probe c1 (4, async): optional protocol subclassed without overriding its method."""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store.drivers import AsyncDriverBackend, AsyncSupportsCopy, AsyncSupportsRemoveFolder  # noqa: E402
from tests._kernel._fake import FakeStore, _AsyncBase, run_async  # noqa: E402


class Forgetful(_AsyncBase, AsyncSupportsCopy, AsyncSupportsRemoveFolder):
    pass


st = FakeStore(parents="implicit").add("src", "d/")
caps = CapabilitySet({Capability.READ, Capability.WRITE, Capability.LIST, Capability.DELETE, Capability.COPY})
drv = Forgetful(
    st,
    name="forgetful",
    namespace="hierarchical",
    parents="implicit",
    caps=caps,
    put_is_atomic=False,
    close_is_terminal=False,
    rename_replaces=False,
)
b = AsyncDriverBackend(drv)
run_async(b.copy("src", "dst"))
print("async copy returned; 'dst' in store:", "dst" in st.files)
run_async(b.delete_folder("d"))
print("async delete_folder returned; 'd' still a folder:", "d" in st.folders, run_async(b.is_folder("d")))
