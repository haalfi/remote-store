"""C5 audit probe 1: kernel Memory vs Dafny oracle on clauses where the formal model and kernel may diverge."""

from __future__ import annotations

import sys
import traceback

sys.path.insert(0, ".")

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store.backends._memory import MemoryBackend, MemoryDriver  # noqa: E402
from tests.backends.dafny._helpers import DafnyOracleBackend  # noqa: E402


def run(label, fn):
    try:
        out = fn()
        if hasattr(out, "__iter__") and not isinstance(out, (str, bytes, dict)):
            out = list(out)
        print(f"  {label}: OK {out!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  {label}: {type(e).__name__} path={getattr(e, 'path', None)!r} {e}")


def section(t):
    print(f"\n=== {t}")


# 1. BE-030 omission vs Dafny ListFiles/ListFolders completeness and GetFolderInfo aggregate.
section("1. non-canonical stored key below a folder (planted via driver), kernel Memory")
m = MemoryBackend()
m.write("a/ok.txt", b"12")
drv = m._driver
drv.put("a/./hidden", b"xyz", overwrite=False, metadata=None)  # tree name "." under a
drv.put("a/sl\\ash", b"q", overwrite=False, metadata=None)  # tree name with backslash
run("list_files('a', recursive=True)", lambda: [f.path.__str__() for f in m.list_files("a", recursive=True)])
run("list_folders('a')", lambda: [f.path.__str__() for f in m.list_folders("a")])
run(
    "get_folder_info('a') (folder_stats push-down)",
    lambda: (m.get_folder_info("a").file_count, m.get_folder_info("a").total_size),
)
run("get_folder_info('') ", lambda: (m.get_folder_info("").file_count, m.get_folder_info("").total_size))
run("sum over list_files('', recursive)", lambda: sum(f.size for f in m.list_files("", recursive=True)))

section("1b. same, kernel listing-fallback aggregate (driver without folder_stats)")


class NoStatsDriver(MemoryDriver):
    pass


# remove the protocol member by shadowing via a class lacking it: build a driver class without folder_stats
ns = {k: v for k, v in vars(MemoryDriver).items() if k not in ("folder_stats", "__dict__", "__weakref__")}
NoStats = type("NoStatsMemoryDriver", MemoryDriver.__bases__, ns)
from remote_store._kernel.backend import DriverBackend  # noqa: E402


class NoStatsBackend(DriverBackend):
    close_is_terminal = False

    def __init__(self):
        super().__init__(NoStats())


n = NoStatsBackend()
print("  has folder_stats push-down:", n._stats is not None)
n.write("a/ok.txt", b"12")
n._driver.put("a/./hidden", b"xyz", overwrite=False, metadata=None)
run(
    "get_folder_info('a') (listing fallback)",
    lambda: (n.get_folder_info("a").file_count, n.get_folder_info("a").total_size),
)

# 2. Caller passes non-canonical keys: kernel folds (BE-030 table), oracle receives them outside WellFormedPath.
section("2. non-canonical caller keys: kernel Memory vs Dafny oracle")
for name, factory in (("kernel", MemoryBackend), ("oracle", DafnyOracleBackend)):
    b = factory()
    print(f" [{name}]")
    run("write('d//f')", lambda b=b: b.write("d//f", b"x").path.__str__())
    run("exists('d/f')", lambda b=b: b.exists("d/f"))
    run("exists('d//f')", lambda b=b: b.exists("d//f"))
    run("is_folder('d/')", lambda b=b: b.is_folder("d/"))
    run("list_files('d')", lambda b=b: [f.path.__str__() for f in b.list_files("d")])
    run("write('e/./g')", lambda b=b: b.write("e/./g", b"x").path.__str__())
    run("is_folder('e/.')", lambda b=b: b.is_folder("e/."))
    run("list_folders('')", lambda b=b: [f.path.__str__() for f in b.list_folders("")])
    run("write('h\\\\i') backslash", lambda b=b: b.write("h\\i", b"x").path.__str__())
    run("write('/lead')", lambda b=b: b.write("/lead", b"x").path.__str__())
    run("write('p/../q')", lambda b=b: b.write("p/../q", b"x").path.__str__())
    run("read_bytes('./d/f')", lambda b=b: b.read_bytes("./d/f"))
    run("delete_folder('./')", lambda b=b: b.delete_folder("./"))
    run("move src './d/f' -> 'z'", lambda b=b: b.move("./d/f", "z"))

# 3. max_depth negative: Dafny 'max_depth < 0 means unlimited'; kernel uses None.
section("3. negative max_depth")
for name, factory in (("kernel", MemoryBackend), ("oracle", DafnyOracleBackend)):
    b = factory()
    b.write("x/a", b"1")
    b.write("x/y/b", b"1")
    run(
        f"[{name}] list_files('x', recursive=True, max_depth=-1)",
        lambda b=b: [f.path.__str__() for f in b.list_files("x", recursive=True, max_depth=-1)],
    )
    run(
        f"[{name}] list_files('x', recursive=True, max_depth=None)",
        lambda b=b: [f.path.__str__() for f in b.list_files("x", recursive=True)],
    )

# 4. Capability gate before closed guard (BE-030) vs Dafny Move/Copy (no capability clause).
section("4. MOVE/COPY gate vs closed guard on a terminal backend without MOVE/COPY (kernel)")


class TermDriver(MemoryDriver):
    close_is_terminal = True


class TermNoMove(DriverBackend):
    close_is_terminal = True

    def __init__(self):
        caps = CapabilitySet(
            set(Capability)
            - {Capability.GLOB, Capability.LAZY_READ, Capability.MOVE, Capability.COPY, Capability.ATOMIC_MOVE}
        )
        super().__init__(TermDriver(caps))


t = TermNoMove()
t.write("s", b"1")
run("open, no MOVE: move('s','d')", lambda: t.move("s", "d"))
run("open, no COPY: copy('s','d')", lambda: t.copy("s", "d"))
t.close()
run("closed terminal, no MOVE: move('s','d')", lambda: t.move("s", "d"))
run("closed terminal, no COPY: copy('s','d')", lambda: t.copy("s", "d"))
run("closed terminal: exists('s')", lambda: t.exists("s"))

# 5. Self-move / self-copy on non-canonical spelling (BK-301)
section("5. self-move with spellings differing only by normalisation")
for name, factory in (("kernel", MemoryBackend), ("oracle", DafnyOracleBackend)):
    b = factory()
    b.write("k/f", b"1")
    run(f"[{name}] move('k/f','k//f')", lambda b=b: b.move("k/f", "k//f"))
    run(f"[{name}] exists('k/f') after", lambda b=b: b.exists("k/f"))
    run(f"[{name}] list_files('k')", lambda b=b: [f.path.__str__() for f in b.list_files("k")])

# 6. delete_folder root: kernel InvalidPath (BE-031); oracle
section("6. delete_folder root and file-ancestor writes")
for name, factory in (("kernel", MemoryBackend), ("oracle", DafnyOracleBackend)):
    b = factory()
    run(f"[{name}] delete_folder('')", lambda b=b: b.delete_folder(""))
    run(f"[{name}] delete_folder('', recursive=True)", lambda b=b: b.delete_folder("", recursive=True))
    b.write("f", b"1")
    run(f"[{name}] write('f/x')", lambda b=b: b.write("f/x", b"1"))
    run(f"[{name}] exists('f/x')", lambda b=b: b.exists("f/x"))
    run(f"[{name}] get_folder_info('f')", lambda b=b: b.get_folder_info("f"))
    run(f"[{name}] get_folder_info('f/x')", lambda b=b: b.get_folder_info("f/x"))
    run(f"[{name}] list_files('f/x')", lambda b=b: list(b.list_files("f/x")))
    run(f"[{name}] delete_folder('f/x')", lambda b=b: b.delete_folder("f/x"))
    run(f"[{name}] delete('f/x')", lambda b=b: b.delete("f/x"))
    run(f"[{name}] read_bytes('f/x')", lambda b=b: b.read_bytes("f/x"))
    run(f"[{name}] move('f','f/y')", lambda b=b: b.move("f", "f/y"))
    run(f"[{name}] copy('f','f/y')", lambda b=b: b.copy("f", "f/y"))
