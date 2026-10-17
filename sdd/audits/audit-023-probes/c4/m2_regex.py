"""Measure pattern_to_regex edge cases and the fallback/native split on more keys."""

import os
import re
import tempfile
import warnings

from remote_store import Store
from remote_store._glob import extract_prefix, needs_recursive, normalize_pattern, pattern_to_regex
from remote_store.backends import LocalBackend, MemoryBackend
from remote_store.ext.glob import glob_files

print("PatternError is ValueError subclass:", issubclass(re.error, ValueError), re.error)

CASES = [
    ("a**", ["ab/c.csv", "abc"]),
    ("d**/c.csv", ["d/e/c.csv", "dx/c.csv"]),
    ("d/e**", ["d/e/f/g.csv", "d/ef"]),
    ("**x", []),
    ("x**y", []),
    ("d[!x]e/c.csv", ["d/e/c.csv"]),
    ("d[/]e/c.csv", ["d/e/c.csv"]),
    ("d[^x]e", ["d^e", "dae"]),
    ("[z-a]", []),
    ("[\\]", []),
    ("a[b", ["a[b"]),
    ("[a&&b]", []),
    ("**", ["", "x"]),
]
for pat, keys in CASES:
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rx = pattern_to_regex(pat)
        res = {k: bool(rx.match(k)) for k in keys}
        print(f"{pat!r:16} regex={rx.pattern!r:40} {res} warn={[x.category.__name__ for x in w]}")
    except Exception as e:  # noqa: BLE001
        print(f"{pat!r:16} RAISES {type(e).__module__}.{type(e).__name__}: {e}")

print()
for p in ["d/a.csv", "a[b/x", "d[/x.csv", "d/./a.csv/", "a/b/"]:
    try:
        n = normalize_pattern(p)
        print(f"{p!r:14} norm={n!r} prefix={extract_prefix(n)!r} recursive={needs_recursive(n)}")
    except Exception as e:  # noqa: BLE001
        print(p, type(e).__name__, e)

# cross-tier on keys that show segment crossing
KEYS = ["ab/c.csv", "abc", "d/e/c.csv", "dx/c.csv", "d^e", "dae", "a[b", "[z-a]x"]
mem = Store(backend=MemoryBackend())
tmp = tempfile.mkdtemp()
loc = Store(backend=LocalBackend(root=tmp))
for k in KEYS:
    mem.write(k, b"x")
    loc.write(k, b"x")


def run(s, p):
    try:
        return sorted(str(i.path) for i in glob_files(s, p))
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__module__}.{type(e).__name__}: {e}"


for p in ["a**", "d**/c.csv", "d[!x]e/c.csv", "d[/]e/c.csv", "d[^x]e", "[z-a]", "[z-a]*", "a[b", "**x", "x**y"]:
    m, l = run(mem, p), run(loc, p)
    print(f"{p!r:16} MEM={m}  LOC={l}{'   <<< DIFF' if m != l else ''}")

# list_files(pattern=) tier 1 on same patterns
print()
for p in ["[^x]*", "d[!x]e", "[z-a]", "*"]:
    try:
        print(p, "tier1 mem:", sorted(str(i.path) for i in mem.list_files("", pattern=p)))
    except Exception as e:  # noqa: BLE001
        print(p, "tier1 raises", type(e).__name__, e)
