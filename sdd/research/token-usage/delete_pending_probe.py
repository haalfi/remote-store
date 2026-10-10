"""Probe: what LocalBackend listings answer for a Windows delete-pending subfolder.

Usage: python delete_pending_probe.py <src-dir> <work-dir> <label>

``<src-dir>`` is a source tree to import ``remote_store`` from (for example a
``git archive`` of a branch), so several trees can be compared without touching
the checkout. Windows only.

Part 1 (P1): hold a handle on root/sub (FILE_SHARE_DELETE) and rmdir it.
Part 1b (P1b): set the classic delete disposition on root/sub while a second
handle stays open, so it is delete-pending; then run each listing.
Part 2 (P2): a thread rmtree's root/sub while the recursive listing walks;
``PROBE_N`` runs per form (default 200).
"""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
import threading
import time
from collections import Counter
from ctypes import wintypes

src, work, label = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, src)
import remote_store.backends._local as mod  # noqa: E402
from remote_store.backends._local import LocalBackend  # noqa: E402

print(f"== {label}: module {mod.__file__}")
print(f"   python {sys.version.split()[0]}  work {work}")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateFileW.restype = wintypes.HANDLE
k32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
INVALID = wintypes.HANDLE(-1).value
FILE_LIST_DIRECTORY = 0x1
SHARE_ALL = 0x7
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000


def build(root: str) -> LocalBackend:
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(os.path.join(root, "sub", "deep"))
    for rel in ("a.txt", "sub/b.txt", "sub/deep/c.txt", "other/d.txt"):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"x")
    return LocalBackend(root)


def outcome(fn) -> str:
    try:
        return "ok " + str(sorted(str(e.path) for e in fn()))
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__module__}.{type(exc).__name__}: {exc}"


CALLS = {
    "list_files": lambda b: b.list_files(""),
    "list_files(recursive)": lambda b: b.list_files("", recursive=True),
    "list_files(recursive,max_depth=5)": lambda b: b.list_files("", recursive=True, max_depth=5),
    "list_folders": lambda b: b.list_folders(""),
    "iter_children": lambda b: b.iter_children(""),
    "list_files('sub')": lambda b: b.list_files("sub"),
    "list_files('sub',recursive)": lambda b: b.list_files("sub", recursive=True),
}

# ---- Part 1: deterministic delete-pending ----
root = os.path.join(work, f"dp-{label}")
b = build(root)
sub = os.path.join(root, "sub")
shutil.rmtree(os.path.join(sub, "deep"))
os.remove(os.path.join(sub, "b.txt"))
h = k32.CreateFileW(sub, FILE_LIST_DIRECTORY, SHARE_ALL, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
assert h != INVALID, ctypes.get_last_error()
try:
    try:
        os.rmdir(sub)
        print("   rmdir(sub) with open handle: succeeded")
    except OSError as exc:
        print(f"   rmdir(sub) with open handle: {exc!r}")
    print(f"   os.path.exists(sub)={os.path.exists(sub)}  'sub' in listdir(root)={'sub' in os.listdir(root)}")
    try:
        os.scandir(sub).close()
        print("   scandir(sub): ok")
    except OSError as exc:
        print(f"   scandir(sub): {type(exc).__name__} errno={exc.errno} winerror={getattr(exc, 'winerror', None)}")
    try:
        os.stat(sub)
        print("   stat(sub): ok")
    except OSError as exc:
        print(f"   stat(sub): {type(exc).__name__} errno={exc.errno} winerror={getattr(exc, 'winerror', None)}")
    for name, call in CALLS.items():
        print(f"   [P1] {name:36s} -> {outcome(lambda call=call: call(b))}")
finally:
    k32.CloseHandle(h)
shutil.rmtree(root, ignore_errors=True)


# ---- Part 1b: classic (non-POSIX) delete disposition, the pre-1809 / non-NTFS shape ----
class FILE_DISPOSITION_INFO(ctypes.Structure):
    _fields_ = [("DeleteFile", wintypes.BOOLEAN)]


k32.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
DELETE = 0x00010000
root = os.path.join(work, f"dpc-{label}")
b = build(root)
sub = os.path.join(root, "sub")
shutil.rmtree(os.path.join(sub, "deep"))
os.remove(os.path.join(sub, "b.txt"))
holder = k32.CreateFileW(sub, FILE_LIST_DIRECTORY, SHARE_ALL, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
deleter = k32.CreateFileW(sub, DELETE, SHARE_ALL, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
assert holder != INVALID, ctypes.get_last_error()
assert deleter != INVALID, ctypes.get_last_error()
info = FILE_DISPOSITION_INFO(1)
ok = k32.SetFileInformationByHandle(deleter, 4, ctypes.byref(info), ctypes.sizeof(info))  # FileDispositionInfo
print(f"   [P1b] classic disposition set: {bool(ok)} (err {ctypes.get_last_error()})")
k32.CloseHandle(deleter)
try:
    print(f"   [P1b] exists(sub)={os.path.exists(sub)}  'sub' in listdir(root)={'sub' in os.listdir(root)}")
    for fn_name, fn in (("scandir", lambda: os.scandir(sub).close()), ("stat", lambda: os.stat(sub))):
        try:
            fn()
            print(f"   [P1b] {fn_name}(sub): ok")
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            print(f"   [P1b] {fn_name}(sub): {type(exc).__name__} errno={exc.errno} winerror={winerror}")
    for name, call in CALLS.items():
        print(f"   [P1b] {name:35s} -> {outcome(lambda call=call: call(b))}")
finally:
    k32.CloseHandle(holder)
shutil.rmtree(root, ignore_errors=True)

# ---- Part 2: race, recursive listing vs concurrent rmtree of sub ----
N = int(os.environ.get("PROBE_N", "200"))
for name in ("list_files(recursive)", "list_files(recursive,max_depth=5)"):
    tally: Counter[str] = Counter()
    for _ in range(N):
        rroot = os.path.join(work, f"race-{label}")
        rb = build(rroot)
        # widen sub so rmtree takes a while
        for j in range(200):
            with open(os.path.join(rroot, "sub", f"f{j}.txt"), "wb") as f:
                f.write(b"x")
        go = threading.Event()

        def killer(go: threading.Event = go, rroot: str = rroot) -> None:
            go.wait()
            shutil.rmtree(os.path.join(rroot, "sub"), ignore_errors=True)

        t = threading.Thread(target=killer)
        t.start()
        try:
            it = CALLS[name](rb)
            next(it)  # root's own files come first, before sub is scanned
            go.set()
            time.sleep(0)
            list(it)
            tally["ok"] += 1
        except StopIteration:
            tally["ok"] += 1
        except Exception as exc:  # noqa: BLE001
            tally[f"{type(exc).__name__}: {getattr(exc, 'path', '')}"] += 1
        finally:
            go.set()  # every outcome releases the killer, or join() waits forever
        t.join()
        shutil.rmtree(rroot, ignore_errors=True)
    print(f"   [P2] {name:36s} N={N} -> {dict(tally)}")
