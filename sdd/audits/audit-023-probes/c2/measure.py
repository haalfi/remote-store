"""Measure MEM-* clauses on both Memory runtimes. Read-only: in-process only."""

from __future__ import annotations

import asyncio
import io
import sys
import time

from remote_store._capabilities import Capability
from remote_store.aio.backends._memory import AsyncMemoryBackend, AsyncMemoryDriver
from remote_store.backends._memory import MemoryBackend, MemoryDriver
from remote_store.backends._memory_tree import DirNode, FileEntry


def walk(tree):
    files = folders = 0
    stack = [tree.root]
    while stack:
        for c in stack.pop().children.values():
            if isinstance(c, FileEntry):
                files += 1
            else:
                folders += 1
                stack.append(c)
    return files, folders


class SyncRun:
    def __init__(self):
        self.b = MemoryBackend()

    def __call__(self, name, *a, **k):
        return getattr(self.b, name)(*a, **k)

    def read_all(self, p):
        return self.b.read(p).read()


class AsyncRun:
    def __init__(self):
        self.b = AsyncMemoryBackend()
        self.loop = asyncio.new_event_loop()

    def __call__(self, name, *a, **k):
        r = getattr(self.b, name)(*a, **k)
        if name in ("list_files", "list_folders", "iter_children"):

            async def coll():
                return [x async for x in r]

            return self.loop.run_until_complete(coll())
        return self.loop.run_until_complete(r)

    def read_all(self, p):
        async def coll():
            return b"".join([c async for c in self.b.read(p)])

        return self.loop.run_until_complete(coll())


def outcome(fn):
    try:
        r = fn()
        return ("ok", r if isinstance(r, (bool, bytes, type(None))) else type(r).__name__)
    except Exception as e:  # noqa: BLE001
        return ("err", type(e).__name__, str(e))


print("== A. counters vs tree walk after op sequences ==")
SEQ = [
    ("write", ("a/b/c.txt", b"1"), {}),
    ("write", ("a/b/c.txt", b"22"), {"overwrite": True}),
    ("write", ("a/d/e/f.txt", b"3"), {}),
    ("copy", ("a/b/c.txt", "x/y/c2.txt"), {}),
    ("copy", ("a/b/c.txt", "x/y/c2.txt"), {"overwrite": True}),
    ("move", ("a/d/e/f.txt", "m/n/f.txt"), {}),
    ("write", ("m/n/g.txt", b"g"), {}),
    ("move", ("m/n/g.txt", "m/n/f.txt"), {"overwrite": True}),
    ("delete", ("x/y/c2.txt",), {}),
    ("delete_folder", ("x/y",), {"recursive": False}),
    ("delete_folder", ("a",), {"recursive": True}),
    ("write_atomic", ("w/a.txt", b"w"), {}),
    ("write", ("bad/f", b"z"), {}),
    ("write", ("bad/f/g", b"z"), {}),  # refused: ancestor is a file
    ("write", ("bad", b"z"), {}),  # refused: folder
    ("move", ("missing", "q/r/s"), {}),  # refused: no src -> must not create q/r
]
for label, R in (("sync", SyncRun), ("async", AsyncRun)):
    r = R()
    drv = r.b._driver
    bad = []
    for name, a, k in SEQ:
        res = outcome(lambda: r(name, *a, **k))
        if drv.counts != walk(drv._tree):
            bad.append((name, a, k, drv.counts, walk(drv._tree)))
    print(
        label,
        "repr:",
        repr(r.b),
        "walk:",
        walk(drv._tree),
        "mismatches:",
        bad,
        "q exists:",
        outcome(lambda: r("exists", "q")),
    )

print("\n== A2. driver called directly: move(k, k, overwrite=True) ==")
d = MemoryDriver()
d.put("k", b"x", overwrite=False, metadata=None)
d.move("k", "k", overwrite=True)
print("sync driver counts:", d.counts, "walk:", walk(d._tree), "stat:", d.stat("k"))

print("\n== B. MEM-DS-003 shrink claim (100MB->1KB keeps ~100MB) ==")
for label, R in (("sync", SyncRun), ("async", AsyncRun)):
    r = R()
    r("write", "big", b"x" * 10_000_000)
    e = r.b._driver._tree.traverse("big")
    before = sys.getsizeof(e.data)
    r("write", "big", b"y" * 1000, overwrite=True)
    e2 = r.b._driver._tree.traverse("big")
    print(label, "same object:", e is e2, "getsizeof before:", before, "after:", sys.getsizeof(e2.data))

print("\n== C. bytearray overallocation (~12.5% claim) ==")
r = SyncRun()
r("write", "bytes_in", b"x" * 1_000_000)
r("write", "stream_in", io.BytesIO(b"x" * 1_000_000))
for k in ("bytes_in", "stream_in"):
    e = r.b._driver._tree.traverse(k)
    print(k, "len", len(e.data), "getsizeof", sys.getsizeof(e.data), "bytes getsizeof", sys.getsizeof(bytes(e.data)))

print("\n== D. metadata aliasing through FileInfo / copy ==")
for label, R in (("sync", SyncRun), ("async", AsyncRun)):
    r = R()
    r("write", "s.txt", b"x", metadata={"k": "v"})
    info = r("get_file_info", "s.txt")
    t = type(info.metadata).__name__
    try:
        info.metadata["k"] = "MUTATED"
        mut = "mutable"
    except TypeError:
        mut = "immutable"
    after = r("get_file_info", "s.txt").metadata
    r2 = R()
    r2("write", "src", b"x", metadata={"k": "v"})
    r2("copy", "src", "dst")
    di = r2("get_file_info", "dst")
    try:
        di.metadata["k"] = "VIA_DST"
    except TypeError:
        pass
    src_after = r2("get_file_info", "src").metadata
    lst = r2("list_files", "")
    lst = list(lst)
    print(
        label,
        "type:",
        t,
        mut,
        "stored after caller mutation:",
        after,
        "| src after mutating dst's info:",
        src_after,
        "| same dict obj src/dst in tree:",
        r2.b._driver._tree.traverse("src").metadata is r2.b._driver._tree.traverse("dst").metadata,
    )

print("\n== E/F. empty metadata echo vs round-trip; WriteResult aliasing caller dict ==")
for label, R in (("sync", SyncRun), ("async", AsyncRun)):
    r = R()
    wr = r("write", "e.txt", b"x", metadata={})
    print(label, "WriteResult.metadata:", wr.metadata, "get_file_info.metadata:", r("get_file_info", "e.txt").metadata)
    md = {"a": "1"}
    wr2 = r("write", "f.txt", b"x", metadata=md)
    md["a"] = "CHANGED"
    print(
        label,
        "WriteResult.metadata after caller mutates own dict:",
        wr2.metadata,
        "stored:",
        r("get_file_info", "f.txt").metadata,
    )

print("\n== G. modified_at on move/copy; content_type ==")
for label, R in (("sync", SyncRun), ("async", AsyncRun)):
    r = R()
    r("write", "o.txt", b"x")
    t0 = r("get_file_info", "o.txt").modified_at
    time.sleep(0.01)
    r("copy", "o.txt", "c.txt")
    r("move", "o.txt", "m.txt")
    tc = r("get_file_info", "c.txt").modified_at
    tm = r("get_file_info", "m.txt").modified_at
    print(
        label,
        "move preserved:",
        tm == t0,
        "copy new:",
        tc > t0,
        "tz:",
        t0.tzinfo,
        "content_type:",
        r("get_file_info", "m.txt").content_type,
    )

print("\n== H. read snapshot vs later overwrite ==")
r = SyncRun()
r("write", "f", b"old")
s = r.b.read("f")
r("write", "f", b"new", overwrite=True)
print("sync: read() then overwrite then consume ->", s.read(), "seekable:", s.seekable())
ar = AsyncRun()
ar("write", "f", b"old")


async def lazy():
    it = ar.b.read("f")
    await ar.b.write("f", b"new", overwrite=True)
    chunks = [c async for c in it]
    return chunks, it


chunks, it = ar.loop.run_until_complete(lazy())
print(
    "async: read() then overwrite then consume ->", chunks, "type:", type(it).__name__, "has seek:", hasattr(it, "seek")
)


async def missing():
    it = ar.b.read("nope")
    try:
        await it.__anext__()
    except Exception as e:  # noqa: BLE001
        return "raised at first iteration: " + type(e).__name__
    return "no raise"


print("async read of missing:", ar.loop.run_until_complete(missing()))

print("\n== L. async chunk count for 10 MB ==")
ar("write", "big", b"z" * 10_000_000)


async def cnt():
    return [len(c) async for c in ar.b.read("big")]


print("chunks:", ar.loop.run_until_complete(cnt()))
print(
    "declares: sync LAZY_READ",
    MemoryBackend().capabilities.supports(Capability.LAZY_READ),
    "async LAZY_READ",
    AsyncMemoryBackend().capabilities.supports(Capability.LAZY_READ),
    "async SEEKABLE_READ",
    AsyncMemoryBackend().capabilities.supports(Capability.SEEKABLE_READ),
)

print("\n== I. get_folder_info edge cases ==")
for label, R in (("sync", SyncRun), ("async", AsyncRun)):
    r = R()
    r("write", "d/f", b"x")
    r("delete", "d/f")
    fi = r("get_folder_info", "d")
    print(
        label,
        "empty folder:",
        fi.file_count,
        fi.total_size,
        fi.modified_at,
        "| absent:",
        outcome(lambda: r("get_folder_info", "zz")),
        "| file:",
        outcome(lambda: r("get_folder_info", "x")) if False else "",
    )

print("\n== K. MEM-DS-004 / MEM-041 sizes ==")
from datetime import UTC, datetime

fe = FileEntry(data=bytearray(), modified_at=datetime.now(UTC))
dn = DirNode()
print(
    "FileEntry",
    sys.getsizeof(fe),
    "DirNode",
    sys.getsizeof(dn),
    "DirNode+dict",
    sys.getsizeof(dn) + sys.getsizeof(dn.children),
    "empty bytearray",
    sys.getsizeof(bytearray()),
    "python",
    sys.version.split()[0],
)

print("\n== N. sync vs async outcome matrix ==")
OPS = [
    ("read_bytes", ("d",)),
    ("read_bytes", ("f/x",)),
    ("read_bytes", ("nope",)),
    ("get_file_info", ("d",)),
    ("delete", ("d",)),
    ("delete", ("nope",)),
    ("delete", ("f/x",)),
    ("delete_folder", ("f",)),
    ("delete_folder", ("nope",)),
    ("delete_folder", ("d",), {"recursive": False}),
    ("move", ("d", "z")),
    ("move", ("f", "d")),
    ("move", ("f", "f/x")),
    ("copy", ("f", "d")),
    ("copy", ("nope", "d")),
    ("write", ("d", b"x")),
    ("write", ("f/x", b"x")),
    ("write", ("f", b"x")),
    ("write_atomic", ("d", b"x")),
    ("get_folder_info", ("f",)),
    ("get_folder_info", ("nope",)),
    ("is_folder", ("f/x",)),
    ("exists", ("f/x/y",)),
    ("list_files", ("f",)),
    ("list_folders", ("f",)),
    ("write", ("a\\b", b"x")),
    ("write", ("a/../b", b"x")),
    ("move", ("f", "d/sub/f2"), {"overwrite": True}),
]
diffs = 0
for op in OPS:
    name, a = op[0], op[1]
    k = op[2] if len(op) > 2 else {}
    outs = []
    for R in (SyncRun, AsyncRun):
        r = R()
        r("write", "d/inner", b"i")
        r("write", "f", b"f")
        o = outcome(lambda: r(name, *a, **k))
        if o[0] == "err":
            o = (o[0], o[1], o[2].replace("async-memory", "memory"))
        outs.append(o)
    if outs[0] != outs[1]:
        diffs += 1
        print("DIFF", name, a, k, outs)
    else:
        print("same", name, a, k, outs[0])
print("diffs:", diffs, "of", len(OPS))
