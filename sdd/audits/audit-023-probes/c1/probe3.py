"""Audit probes c1 (3): which spelling an error's ``path`` carries for a non-canonical key."""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from tests._kernel._fake import FakeStore, make_kernel  # noqa: E402


def show(label, fn):
    try:
        out = fn()
        print(f"[{label}] -> returned {out!r}")
    except BaseException as e:  # noqa: BLE001
        print(f"[{label}] -> raised {type(e).__name__} path={getattr(e, 'path', None)!r}")


for rt in ("sync", "async"):
    print(f"===== runtime {rt} =====")

    def mk():
        st = FakeStore(parents="implicit").add("f", "d/a")
        return make_kernel(rt, st)

    show("read_bytes('x//missing')  (kernel probe NotFound)", lambda: mk().read_bytes("x//missing"))
    show("get_file_info('./x/missing')", lambda: mk().get_file_info("./x/missing"))
    show("delete('d//')  (folder -> InvalidPath)", lambda: mk().delete("d//"))
    show("write('f/', b'') no overwrite (AlreadyExists)", lambda: mk().write("f/", b"x"))
    show("get_folder_info('./f')  (file -> InvalidPath)", lambda: mk().get_folder_info("./f"))
    show("delete_folder('nope//')  (NotFound)", lambda: mk().delete_folder("nope//"))
    show("read_bytes('./')  (root refusal)", lambda: mk().read_bytes("./"))
    show("read_bytes('a/../b')  (key refusal)", lambda: mk().read_bytes("a/../b"))
    show("move('./missing', 'z')", lambda: mk().move("./missing", "z"))
