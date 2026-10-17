"""Who refuses an existing file on the open_write route when overwrite=False? Does a second close reach the driver?"""

from __future__ import annotations

from pathlib import Path

from remote_store import Capability, CapabilitySet
from remote_store.drivers import DriverBackend, PutResult

src = Path(__file__).with_name("s2_behaviour.py").read_text().split("# --- A. construction")[0]
ns: dict = {}
exec(compile(src, "s2_head", "exec"), ns)
Dict, ALL = ns["Dict"], ns["ALL"]


def show(label, fn):
    try:
        print(f"[{label}] OK -> {fn()!r}")
    except BaseException as e:  # noqa: BLE001
        print(f"[{label}] {type(e).__name__}: {e}")


class OW(Dict):
    capabilities = CapabilitySet(set(ALL) | {Capability.ATOMIC_WRITE})
    put_is_atomic = False

    def open_write(self, key, *, overwrite, metadata):
        self.calls.append(("open_write", key, overwrite))
        drv = self

        class H:
            buf = b""

            def write(self, data):
                H.buf += data

            def commit(self):
                drv.calls.append(("commit", key))
                drv.d[key] = H.buf  # ignores overwrite entirely
                return PutResult(size=len(H.buf))

            def abort(self):
                drv.calls.append(("abort", key))

        return H()


d = OW()
b = DriverBackend(d)
d.d["x"] = b"old"
d.calls.clear()
show("write_atomic overwrite=False onto existing (driver ignores overwrite)", lambda: b.write_atomic("x", b"new"))
print("   calls:", d.calls, "value:", d.d["x"])
d.calls.clear()


def oa():
    with b.open_atomic("x") as f:
        f.write(b"newer")


show("open_atomic overwrite=False onto existing", oa)
print("   calls:", d.calls, "value:", d.d["x"])


class CloseOnce(Dict):
    closed = False

    def close(self):
        if self.closed:
            raise RuntimeError("already closed")
        self.closed = True


cb = DriverBackend(CloseOnce())
cb.close()
show("second close on a driver whose close is not repeatable", cb.close)
