"""Measure MemoryBackend vs AsyncMemoryBackend parity: same op sequence, compare outcomes."""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import io

from remote_store.aio.backends._memory import AsyncMemoryBackend
from remote_store.backends._memory import MemoryBackend


def norm(v):
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        d = {}
        for f in dataclasses.fields(v):
            x = getattr(v, f.name)
            if f.name in ("modified_at", "modified", "last_modified", "created_at"):
                x = "<time>" if x is not None else None
            d[f.name] = norm(x)
        return (type(v).__name__, d)
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    return v if isinstance(v, (str, bytes, int, float, bool, type(None), tuple)) else repr(v)


def err(e):
    return (
        "EXC",
        type(e).__name__,
        str(e).replace("async-memory", "memory"),
        getattr(e, "path", None),
        (getattr(e, "backend", None) or "").replace("async-memory", "memory"),
    )


async def aiter_of(chunks):
    for c in chunks:
        yield c


def sync_ops():
    return [
        ("write a/b.txt", lambda b: b.write("a/b.txt", b"hello")),
        ("write dup", lambda b: b.write("a/b.txt", b"x")),
        ("write folder", lambda b: b.write("a", b"x")),
        ("write under file", lambda b: b.write("a/b.txt/c", b"x")),
        ("write root", lambda b: b.write("", b"x")),
        ("write dotdot", lambda b: b.write("../x", b"x")),
        ("write meta", lambda b: b.write("m.txt", b"m", metadata={"k": "v"})),
        ("write bad meta", lambda b: b.write("m2.txt", b"m", metadata=[("k", "v")])),
        ("write bytearray", lambda b: b.write("ba.txt", bytearray(b"ba"))),
        ("write memoryview", lambda b: b.write("mv.txt", memoryview(b"mv"))),
        ("write str", lambda b: b.write("s.txt", "str")),
        ("write list", lambda b: b.write("l.txt", [b"a", b"b"])),
        ("write_atomic", lambda b: b.write_atomic("wa.txt", b"atomic")),
        ("write_atomic dup", lambda b: b.write_atomic("wa.txt", b"atomic")),
        ("read_bytes", lambda b: b.read_bytes("a/b.txt")),
        ("read_bytes missing", lambda b: b.read_bytes("nope")),
        ("read_bytes folder", lambda b: b.read_bytes("a")),
        ("read_bytes root", lambda b: b.read_bytes("")),
        ("get_file_info", lambda b: b.get_file_info("m.txt")),
        ("get_file_info folder", lambda b: b.get_file_info("a")),
        ("get_folder_info", lambda b: b.get_folder_info("a")),
        ("get_folder_info file", lambda b: b.get_folder_info("a/b.txt")),
        ("get_folder_info missing", lambda b: b.get_folder_info("zz")),
        ("exists folder", lambda b: b.exists("a")),
        ("is_file", lambda b: b.is_file("a/b.txt")),
        ("is_folder", lambda b: b.is_folder("a/b.txt")),
        ("list_files rec", lambda b: b.list_files("", recursive=True)),
        ("list_files file", lambda b: b.list_files("a/b.txt")),
        ("list_files missing", lambda b: b.list_files("zz")),
        ("list_folders", lambda b: b.list_folders("")),
        ("iter_children", lambda b: b.iter_children("")),
        ("glob", lambda b: b.glob("*.txt")),
        ("move missing->blocked", lambda b: b.move("nope", "a/b.txt/c")),
        ("copy", lambda b: b.copy("a/b.txt", "c.txt")),
        ("copy dup", lambda b: b.copy("a/b.txt", "c.txt")),
        ("move self", lambda b: b.move("c.txt", "c.txt")),
        ("move", lambda b: b.move("c.txt", "d/e.txt")),
        ("delete missing", lambda b: b.delete("nope")),
        ("delete missing ok", lambda b: b.delete("nope", missing_ok=True)),
        ("delete folder", lambda b: b.delete("a")),
        ("delete_folder nonempty", lambda b: b.delete_folder("a")),
        ("delete_folder file", lambda b: b.delete_folder("a/b.txt")),
        ("delete_folder missing", lambda b: b.delete_folder("zz")),
        ("delete_folder rec", lambda b: b.delete_folder("d", recursive=True)),
        ("unwrap", lambda b: b.unwrap(dict)),
        ("native_path", lambda b: b.native_path("/x//y/")),
        ("native_path refused", lambda b: b.native_path("../x")),
        ("to_key", lambda b: b.to_key("x/y")),
        ("resolve", lambda b: b.resolve("x//y")),
        ("check_health", lambda b: b.check_health()),
    ]


async def call_async(fn, b):
    r = fn(b)
    if inspect.isasyncgen(r) or hasattr(r, "__aiter__"):
        return [x async for x in r]
    if inspect.isawaitable(r):
        return await r
    return r


def call_sync(fn, b):
    r = fn(b)
    if hasattr(r, "__next__") or inspect.isgenerator(r):
        return list(r)
    return r


def main():
    sb, ab = MemoryBackend(), AsyncMemoryBackend()
    print("name:", sb.name, "|", ab.name)
    print(
        "caps only sync:",
        sorted(c.value for c in sb.capabilities)
        and sorted(set(c.value for c in sb.capabilities) - set(c.value for c in ab.capabilities)),
    )
    print("caps only async:", sorted(set(c.value for c in ab.capabilities) - set(c.value for c in sb.capabilities)))
    loop = asyncio.new_event_loop()
    diffs = 0
    for label, fn in sync_ops():
        try:
            s = norm(call_sync(fn, sb))
        except Exception as e:  # noqa: BLE001
            s = err(e)
        try:
            a = norm(loop.run_until_complete(call_async(fn, ab)))
        except Exception as e:  # noqa: BLE001
            a = err(e)
        if isinstance(a, tuple) and len(a) == 2 and isinstance(a[1], dict):
            pass
        same = repr(s).replace("async-memory", "memory") == repr(a).replace("async-memory", "memory")
        if not same:
            diffs += 1
        print(
            f"{'SAME' if same else 'DIFF'} {label}\n   sync : {s}\n   async: {a}" if not same else f"SAME {label}: {s}"
        )
    print("DIFF COUNT:", diffs)

    # Cross-runtime content shapes
    try:
        loop.run_until_complete(ab.write("x1", io.BytesIO(b"sync stream on async")))
        print("async accepts BinaryIO: yes")
    except Exception as e:  # noqa: BLE001
        print("async BinaryIO:", err(e))
    try:
        sb.write("x1", aiter_of([b"a"]))
        print("sync accepts async iterator: yes")
    except Exception as e:  # noqa: BLE001
        print("sync async-iter:", err(e))

    # close then reuse
    sb.close()
    loop.run_until_complete(ab.aclose())
    print("sync after close:", norm(sb.read_bytes("a/b.txt")))
    print("async after close:", norm(loop.run_until_complete(ab.read_bytes("a/b.txt"))))
    print("sync has aclose?", hasattr(sb, "aclose"), "async has close?", hasattr(ab, "close"))
    loop.close()


main()
