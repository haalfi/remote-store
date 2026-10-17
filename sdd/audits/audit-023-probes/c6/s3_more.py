"""Follow-ups: glob gating at iteration, rename put-back, re-typing of a driver's typed error."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from remote_store import AlreadyExists, Capability, CapabilitySet, InvalidPath, NotFound, PermissionDenied, Store
from remote_store.drivers import DriverBackend

spec = importlib.util.spec_from_file_location("s2", Path(__file__).with_name("s2_behaviour.py"))
# import only the class definitions: exec the file up to the first section marker
src = Path(__file__).with_name("s2_behaviour.py").read_text().split("# --- A. construction")[0]
ns: dict = {}
exec(compile(src, "s2_head", "exec"), ns)
Dict = ns["Dict"]
ALL = ns["ALL"]


def show(label, fn):
    try:
        r = fn()
        print(f"[{label}] OK -> {r!r}")
    except BaseException as e:  # noqa: BLE001
        print(f"[{label}] {type(e).__name__}: {e}")


class RO(Dict):
    capabilities = CapabilitySet({Capability.READ, Capability.LIST})


rod = RO()
st = Store(backend=DriverBackend(rod))
rod.calls.clear()
show("list(Store.glob('*')) without GLOB", lambda: list(st.glob("*")))
print("   driver calls:", rod.calls)


class RenameNR(Dict):
    capabilities = CapabilitySet(set(ALL) | {Capability.MOVE})
    rename_replaces = False
    fail = False

    def rename(self, src, dst, *, replace):
        self.calls.append(("rename", src, dst, replace))
        if self.fail and src == "a.txt":
            raise OSError("rename failed")
        if src not in self.d:
            raise NotFound(src)
        if dst in self.d and not replace:
            raise AlreadyExists(dst)
        self.d[dst] = self.d.pop(src)


rd = RenameNR()
rb = DriverBackend(rd)
rb.write("a.txt", b"A")
rb.write("b.txt", b"B")
rd.fail = True
rd.calls.clear()
show("move overwrite, rename fails", lambda: rb.move("a.txt", "b.txt", overwrite=True))
print("   renames:", [c for c in rd.calls if c[0] == "rename"], "state:", rd.d)


# A typed error the driver raises: "passes through unchanged"?
class Lies(Dict):
    def get(self, key):
        raise PermissionDenied("driver says denied")


ld = Lies()
lb = DriverBackend(ld)
show("driver raises PermissionDenied on absent key", lambda: lb.read_bytes("nothing"))
ld.d["f"] = b"x"
show("driver raises PermissionDenied on existing file", lambda: lb.read_bytes("f"))


class LiesNF(Dict):
    def put(self, key, content, *, overwrite, metadata):
        raise NotFound("driver says not found")


nb = DriverBackend(LiesNF())
nb._driver.d["exists.txt"] = b"x"
show("put raises NotFound, dst exists, overwrite False", lambda: nb.write("exists.txt", b"y"))
