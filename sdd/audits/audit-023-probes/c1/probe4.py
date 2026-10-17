"""Audit probes c1 (4): an OPTIONAL protocol subclassed without overriding its method.

The kernel refuses an inherited protocol body for the fourteen required
primitives. Does it for an optional protocol's method (copy, remove_folder,
delete_tree, ensure_parents, rename, ...)?
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store.drivers import (  # noqa: E402
    DriverBackend,
    SupportsCopy,
    SupportsRemoveFolder,
)
from tests._kernel._fake import FakeStore, _SyncBase  # noqa: E402


def show(label, fn):
    try:
        out = fn()
        print(f"[{label}] -> returned {out!r}")
    except BaseException as e:  # noqa: BLE001
        print(f"[{label}] -> raised {type(e).__name__}: {e}")


class Forgetful(_SyncBase, SupportsCopy, SupportsRemoveFolder):
    """Subclasses SupportsCopy and SupportsRemoveFolder but implements neither method."""


def build():
    st = FakeStore(parents="implicit").add("src", "d/")
    st.namespace = "hierarchical"
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
    return st, DriverBackend(drv)


def copy_case():
    st, b = build()
    b.copy("src", "dst")
    return f"copy returned; 'dst' in store: {'dst' in st.files}"


def rmdir_case():
    st, b = build()
    b.delete_folder("d")
    return f"delete_folder returned; folder 'd' still present: {'d' in st.folders}; is_folder('d')={b.is_folder('d')}"


show("construction + copy('src','dst')", copy_case)
show("construction + delete_folder('d')", rmdir_case)
