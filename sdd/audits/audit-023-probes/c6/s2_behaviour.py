"""Measure the guide's and drivers.md's behavioural claims against a minimal driver."""

from __future__ import annotations

import io
import logging
import traceback
from typing import Literal

from remote_store import (
    AlreadyExists,
    BackendUnavailable,
    Capability,
    CapabilityNotSupported,
    CapabilitySet,
    InvalidPath,
    NotFound,
    RemoteStoreError,
    ResolutionPlan,
    Store,
)
from remote_store.drivers import Driver, DriverBackend, Entry, Page, PutResult

ALL = CapabilitySet({Capability.READ, Capability.WRITE, Capability.DELETE, Capability.LIST, Capability.METADATA})


class Dict(Driver):
    name = "dict"
    namespace: Literal["flat", "hierarchical"] = "flat"
    parents: Literal["none", "implicit", "explicit"] = "none"
    capabilities = ALL
    put_is_atomic = True
    close_is_terminal = False

    def __init__(self):
        self.d: dict[str, bytes] = {}
        self.calls: list[tuple] = []
        self.extra_list: list[str] = []
        self.stream_exc: type | None = None

    def stat(self, key, *, follow_links=True):
        self.calls.append(("stat", key))
        if key in self.d:
            return Entry(key=key, kind="file", size=len(self.d[key]))
        return None

    def get(self, key):
        self.calls.append(("get", key))
        if key not in self.d:
            raise NotFound(key)
        if self.stream_exc:
            exc = self.stream_exc

            class S(io.RawIOBase):
                def readable(self):
                    return True

                def readinto(self, b):
                    raise exc("mid-stream")

            return io.BufferedReader(S())
        return io.BytesIO(self.d[key])

    def put(self, key, content, *, overwrite, metadata):
        self.calls.append(("put", key))
        raw = content if isinstance(content, bytes) else content.read()
        if not overwrite and key in self.d:
            raise AlreadyExists(key)
        self.d[key] = raw
        return PutResult(size=len(raw))

    def delete(self, key):
        self.calls.append(("delete", key))
        if key not in self.d:
            raise NotFound(key)
        del self.d[key]

    def list_page(self, prefix, *, delimiter, cursor=None, limit=None, follow_links=True):
        self.calls.append(("list_page", prefix, limit))
        base = f"{prefix}/" if prefix else ""
        keys = sorted([k for k in self.d if k.startswith(base)] + [k for k in self.extra_list if k.startswith(base)])
        entries, folders = [], set()
        for k in keys:
            rest = k[len(base) :]
            if delimiter and delimiter in rest:
                folders.add(base + rest.split(delimiter, 1)[0])
            else:
                entries.append(Entry(key=k, kind="file", size=len(self.d.get(k, b""))))
        return Page(entries=tuple(entries), prefixes=tuple(sorted(folders)))

    def close(self):
        self.calls.append(("close",))

    def classify(self, exc, *, op, key):
        return RemoteStoreError(f"native {type(exc).__name__}")

    def container_absent(self, exc, *, op):
        return False

    def connection_dead(self, exc):
        return False

    def unwrap(self, type_hint):
        raise CapabilityNotSupported("no", capability="unwrap", backend=self.name)

    def native_path(self, key):
        self.calls.append(("native_path", key))
        return "n:" + key

    def to_key(self, native_path):
        return native_path.removeprefix("n:")

    def resolve(self, key):
        self.calls.append(("resolve", key))
        return ResolutionPlan(kind="dict", backend="dict", key=key, native_path=self.native_path(key), details={})


def show(label, fn):
    try:
        r = fn()
        print(f"[{label}] OK -> {r!r}")
    except BaseException as e:  # noqa: BLE001
        print(f"[{label}] {type(e).__name__}: {e}")


# --- A. construction refusals -------------------------------------------------
print("== A. construction")
show("baseline", lambda: DriverBackend(Dict()))


class FlatImplicit(Dict):
    parents = "implicit"

    def remove_folder(self, key):
        pass


show("flat+implicit", lambda: DriverBackend(FlatImplicit()))


class HierImplicitNoRemove(Dict):
    namespace = "hierarchical"
    parents = "implicit"


show("hier implicit no remove_folder", lambda: DriverBackend(HierImplicitNoRemove()))


class HierExplicitNoEnsure(Dict):
    namespace = "hierarchical"
    parents = "explicit"

    def remove_folder(self, key):
        pass


show("hier explicit no ensure_parents", lambda: DriverBackend(HierExplicitNoEnsure()))


class Terminal(Dict):
    close_is_terminal = True


show("close_is_terminal mismatch (class default False)", lambda: DriverBackend(Terminal()))


class NoDelete(Dict):
    delete = Driver.delete


show("inherited delete body", lambda: DriverBackend(NoDelete()))


class Structural:
    """Does not subclass Driver; copies everything but probe."""


for k, v in vars(Dict).items():
    if k not in ("__dict__", "__weakref__"):
        setattr(Structural, k, v)
show("structural without probe", lambda: DriverBackend(Structural()))
Structural.probe = lambda self: None
show("structural with probe", lambda: DriverBackend(Structural()))


class OtherCaps(Dict):
    capabilities = CapabilitySet(set(ALL) | {Capability.USER_METADATA, Capability.SEEKABLE_READ, Capability.LAZY_READ})


show("undeclared-backed USER_METADATA/SEEKABLE/LAZY taken as declared", lambda: DriverBackend(OtherCaps()))


# Rename without rename_replaces: is it "detected"?
class RenameNoFlag(Dict):
    capabilities = CapabilitySet(set(ALL) | {Capability.MOVE})

    def rename(self, src, dst, *, replace):
        self.d[dst] = self.d.pop(src)


show("rename() defined, rename_replaces missing, MOVE declared", lambda: DriverBackend(RenameNoFlag()))


# ensure_parents on implicit driver: used?
class HierImplicitEnsure(Dict):
    namespace = "hierarchical"
    parents = "implicit"

    def remove_folder(self, key):
        pass

    def ensure_parents(self, key):
        self.calls.append(("ensure_parents", key))


b = DriverBackend(HierImplicitEnsure())
b.write("a/b/c.txt", b"x")
print("ensure_parents called on implicit driver:", [c for c in b._driver.calls if c[0] == "ensure_parents"])


# MOVE backed by copy alone
class CopyOnly(Dict):
    capabilities = CapabilitySet(set(ALL) | {Capability.MOVE, Capability.COPY})

    def copy(self, src, dst, *, overwrite):
        self.calls.append(("copy", src, dst))
        if src not in self.d:
            raise NotFound(src)
        if dst in self.d and not overwrite:
            raise AlreadyExists(dst)
        self.d[dst] = self.d[src]


b = DriverBackend(CopyOnly())
b.write("s.txt", b"x")
b.move("s.txt", "t.txt")
print("move via copy-then-delete:", b.exists("s.txt"), b.read_bytes("t.txt"), [c[0] for c in b._driver.calls[-6:]])

# --- C/D. key rule and what reaches the driver -----------------------------------
print("== C/D. key rule")
drv = Dict()
b = DriverBackend(drv)
for p in ["/a", "a/../b", "a\0b", "a\\b"]:
    drv.calls.clear()
    show(f"read {p!r}", lambda p=p: b.read_bytes(p))
    print("   driver calls:", drv.calls)
drv.d["a/b"] = b"1"
for p in ["./a/b", "a//b", "a/./b/"]:
    drv.calls.clear()
    show(f"read {p!r}", lambda p=p: b.read_bytes(p))
    print("   driver calls:", drv.calls)
for p in ["", ".", "./", "//"]:
    drv.calls.clear()
    show(f"read root {p!r}", lambda p=p: b.read_bytes(p))
    print("   driver calls:", drv.calls)
for p in ["../x", "/abs", "a\\b"]:
    drv.calls.clear()
    show(f"native_path {p!r}", lambda p=p: b.native_path(p))
    show(f"resolve {p!r}", lambda p=p: b.resolve(p).native_path)
    print("   driver calls:", drv.calls)

# --- E. get NotFound on folder -> InvalidPath
print("== E/F")
drv.d["dir/x"] = b"1"
show("read folder", lambda: b.read_bytes("dir"))
show("write over folder", lambda: b.write("dir", b"x"))
show("write under file", lambda: b.write("dir/x/y", b"x"))

# --- G. non-canonical listed key omitted and logged
print("== G")
logging.basicConfig(level=logging.WARNING)
drv.extra_list = ["lst/a\\b", "lst/./c", "lst//d"]
drv.d["lst/ok"] = b"1"
show("list_files lst", lambda: sorted(str(f.path) for f in b.list_files("lst")))
drv.extra_list = []

# --- J. stream_catch
print("== J")
drv.d["s.bin"] = b"payload"
drv.stream_exc = ValueError
show("mid-stream ValueError without stream_catch", lambda: b.read("s.bin").read())
drv.stream_catch = (ValueError,)
show("mid-stream ValueError with stream_catch", lambda: b.read("s.bin").read())
drv.stream_exc = OSError
del drv.stream_catch
show("mid-stream OSError", lambda: b.read("s.bin").read())
drv.stream_exc = None

# --- I. classify raising / returning junk
print("== I")


class BadClassify(Dict):
    def stat(self, key, *, follow_links=True):
        raise KeyError("boom")

    def classify(self, exc, *, op, key):
        raise RuntimeError("classifier broke")


show("classify raises", lambda: DriverBackend(BadClassify()).exists("k"))


class JunkClassify(BadClassify):
    def classify(self, exc, *, op, key):
        return "not an error"


show("classify returns junk", lambda: DriverBackend(JunkClassify()).exists("k"))

# --- K. close_is_terminal
print("== K")


class TermBackend(DriverBackend):
    close_is_terminal = True


td = Terminal()
tb = TermBackend(td)
tb.close()
td.calls.clear()
for label, fn in [
    ("read ../x after close", lambda: tb.read_bytes("../x")),
    ("exists after close", lambda: tb.exists("a")),
    ("list_files after close", lambda: list(tb.list_files(""))),
    ("check_health after close", lambda: tb.check_health()),
    ("native_path after close", lambda: tb.native_path("a")),
    ("close again", lambda: tb.close()),
]:
    show(label, fn)
print("   driver calls after close:", td.calls)

# --- L. rename without rename_replaces: aside and restore
print("== L")


class RenameNR(Dict):
    capabilities = CapabilitySet(set(ALL) | {Capability.MOVE})
    rename_replaces = False
    fail = False

    def rename(self, src, dst, *, replace):
        self.calls.append(("rename", src, dst, replace))
        if self.fail and not dst.startswith(".") and "/." not in dst:
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
rd.calls.clear()
rb.move("a.txt", "b.txt", overwrite=True)
print("move overwrite, renames:", [c for c in rd.calls if c[0] == "rename"], rd.d)
rb.write("a.txt", b"A2")
rd.fail = True
rd.calls.clear()
show("move overwrite with failing rename", lambda: rb.move("a.txt", "b.txt", overwrite=True))
print("   renames:", [c for c in rd.calls if c[0] == "rename"], "state:", rd.d)

# --- M. fallbacks without optional protocols
print("== M")
m = Dict()
mb = DriverBackend(m)
mb.write("f/a", b"12")
mb.write("f/g/b", b"345")
show("get_folder_info", lambda: (mb.get_folder_info("f").file_count, mb.get_folder_info("f").total_size))
s = mb.read_seekable("f/a")
show("read_seekable seekable", lambda: (s.seekable(), s.read()))
show("delete_folder recursive", lambda: mb.delete_folder("f", recursive=True))
print("   left:", m.d)

# --- O. Store gating before driver
print("== O")


class RO(Dict):
    capabilities = CapabilitySet({Capability.READ, Capability.METADATA})


rod = RO()
st = Store(backend=DriverBackend(rod))
rod.calls.clear()
show("Store.write on read-only", lambda: st.write("x", b"1"))
show("Store.glob without GLOB", lambda: st.glob("*"))
print("   driver calls:", rod.calls)

# --- S. CAPABILITIES vs driver mismatch
print("== S")


class Mismatch(DriverBackend):
    CAPABILITIES = CapabilitySet({Capability.READ})

    def __init__(self):
        super().__init__(Dict())


show("CAPABILITIES disagrees with driver", lambda: sorted(c.name for c in Mismatch().capabilities))

# --- H. limit returning more is safe: is_folder with many keys
print("== H")
hd = Dict()
for i in range(5):
    hd.d[f"h/{i}"] = b"x"
hb = DriverBackend(hd)
hd.calls.clear()
show("is_folder h", lambda: hb.is_folder("h"))
print("   list_page limits seen:", [c for c in hd.calls if c[0] == "list_page"])
