"""Audit probes c1 (2): read vs read_bytes mapping on the same mid-stream fault; laziness."""

from __future__ import annotations

import sys
import tempfile

sys.path.insert(0, ".")

from tests._kernel._fake import FakeDown, FakeStore, make_kernel  # noqa: E402


def show(label, fn):
    try:
        out = fn()
        print(f"[{label}] -> returned {out!r}")
    except BaseException as e:  # noqa: BLE001
        print(f"[{label}] -> raised {type(e).__module__}.{type(e).__name__}: {e}")


for rt in ("sync", "async"):
    print(f"===== runtime {rt} =====")
    for exc_factory, label in (
        (lambda: FakeDown("dropped"), "FakeDown (a wire error, not in stream_catch)"),
        (lambda: AttributeError("bug in stream"), "AttributeError (programming error)"),
    ):
        for member in ("read", "read_bytes"):

            def go(member=member, exc_factory=exc_factory):
                st = FakeStore()
                st.add("big", data=b"0123456789")
                r = make_kernel(rt, st)
                r.driver.stream_catch = ()
                st.fault("stream.read", exc_factory(), key="big", nth=2 if rt == "async" else 1)
                return getattr(r, member)("big")

            show(f"{member}: mid-stream {label}", go)

# Laziness: does a non-kernel backend raise at call time for a refused key on list_files?
from remote_store.backends import LocalBackend  # noqa: E402


def local_lazy():
    b = LocalBackend(root=tempfile.mkdtemp())
    it = b.list_files("../x")
    return f"call returned {type(it).__name__} without raising"


show("LocalBackend.list_files('../x') at call time", local_lazy)
