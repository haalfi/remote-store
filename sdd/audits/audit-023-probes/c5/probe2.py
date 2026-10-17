"""C5 audit probe 2: ListFolders depth, folder persistence, metadata aliasing, oracle vs kernel Memory."""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from remote_store.backends._memory import MemoryBackend  # noqa: E402
from tests.backends.dafny._helpers import DafnyOracleBackend  # noqa: E402


def run(label, fn):
    try:
        out = fn()
        print(f"  {label}: OK {out!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  {label}: {type(e).__name__} path={getattr(e, 'path', None)!r} {e}")


for name, factory in (("kernel", MemoryBackend), ("oracle", DafnyOracleBackend)):
    print(f"[{name}]")
    b = factory()
    b.write("a/b/c.txt", b"1")
    b.write("a/top.txt", b"22")
    run("list_folders('')", lambda b=b: sorted(str(f.path) for f in b.list_folders("")))
    run("list_folders('a')", lambda b=b: sorted(str(f.path) for f in b.list_folders("a")))
    run("list_folders('') names", lambda b=b: sorted(f.name for f in b.list_folders("")))
    run("list_files('', recursive=False)", lambda b=b: sorted(str(f.path) for f in b.list_files("")))
    b.delete("a/b/c.txt")
    run("after delete: is_folder('a/b')", lambda b=b: b.is_folder("a/b"))
    run("after delete: get_folder_info('a/b')", lambda b=b: (b.get_folder_info("a/b").file_count,))
    run("delete_folder('a', recursive=False)", lambda b=b: b.delete_folder("a"))
    run("delete_folder('a', recursive=True)", lambda b=b: b.delete_folder("a", recursive=True))
    run("exists('a')", lambda b=b: b.exists("a"))
    # metadata round trip and copy
    b.write("m", b"x", metadata={"k": "v"})
    run("copy('m','m2')", lambda b=b: b.copy("m", "m2"))
    run("get_file_info('m2').metadata", lambda b=b: b.get_file_info("m2").metadata)
    run("move('m2','m3')", lambda b=b: b.move("m2", "m3"))
    run("get_file_info('m3').metadata", lambda b=b: b.get_file_info("m3").metadata)
    run("write metadata={} -> WriteResult.metadata", lambda b=b: b.write("e", b"x", metadata={}).metadata)
    run("get_file_info('e').metadata", lambda b=b: b.get_file_info("e").metadata)
    run("write source", lambda b=b: b.write("s1", b"x").source)
    run("close then exists", lambda b=b: (b.close(), b.exists("m"))[1])
