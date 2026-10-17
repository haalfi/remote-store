"""Measure glob_files on Memory (fallback) vs Local (native) on the same tree."""

import os
import sys
import tempfile
import warnings

from remote_store import Capability, Store
from remote_store.backends import LocalBackend, MemoryBackend
from remote_store.ext.glob import glob_files

FILES = [
    "a.csv",
    ".hidden.csv",
    "d/a.csv",
    "d/b.CSV",
    "d/.h.csv",
    "d/e/c.csv",
    "d/e/f/g.csv",
    "d/x/b.csv",
    ".dot/z.csv",
    "f.txt",
    "abc",
    "a-b",
    "a]b",
    "x/y",
]

PATTERNS = [
    "*",
    "*.csv",
    "**",
    "**/*.csv",
    "d/**",
    "d/**/*.csv",
    "d**",
    "d/e**",
    "a**",
    "**/",
    "d/*/",
    "d/",
    "/d/*.csv",
    "",
    ".",
    "/",
    "d/a.csv",
    "f.txt/*",
    "f.txt/**",
    "nope/*.csv",
    "nope/**",
    "*.CSV",
    "d/[!a]*",
    "d[!x]e/c.csv",
    "a[!x]b",
    "d/[a-b].csv",
    "[]]*",
    "a[]]b",
    "[!]]*",
    "[\\]",
    "[a&&b]",
    "[[:alpha:]]*",
    "d/*/c.csv",
    "*/*/c.csv",
    "**/e/**",
    "x?y",
    "a?b",
    "d/e/f/**",
    "**/**/*.csv",
    "d/**/**",
    "**/.hidden.csv",
    ".*",
    "d/.*",
    "*/",
    "d/e",
    "d/e/",
]


def build_local():
    tmp = tempfile.mkdtemp()
    b = LocalBackend(root=tmp)
    return Store(backend=b)


def run(store, pat):
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = sorted(str(i.path) for i in glob_files(store, pat))
            raw = [str(i.path) for i in glob_files(store, pat)]
        dup = len(raw) != len(set(raw))
        wn = [str(x.category.__name__) for x in w]
        return r, ("DUP " if dup else "") + (" W:" + ",".join(wn) if wn else "")
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}", ""


def main():
    mem = Store(backend=MemoryBackend())
    try:
        loc = build_local()
    except Exception as e:  # noqa: BLE001
        print("local build failed", e)
        loc = None
    for f in FILES:
        mem.write(f, b"x")
        if loc is not None:
            loc.write(f, b"x")
    print("mem GLOB", mem.supports(Capability.GLOB), "local GLOB", loc.supports(Capability.GLOB) if loc else None)
    for p in PATTERNS:
        m, mn = run(mem, p)
        l, ln = run(loc, p) if loc else ("-", "")
        flag = "" if m == l else "   <<< DIFF"
        print(f"{p!r:22} MEM={m}{mn}")
        print(f"{'':22} LOC={l}{ln}{flag}")


if __name__ == "__main__":
    main()
