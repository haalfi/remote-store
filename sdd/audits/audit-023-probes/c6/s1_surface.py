"""Enumerate the driver protocol surface and resolve the mkdocstrings refs in drivers.md."""

import inspect
import re
from pathlib import Path

import remote_store.drivers as d

print("== __all__ count", len(d.__all__))
for name in d.__all__:
    obj = getattr(d, name)
    print("resolves", name, obj.__module__)

doc = Path("docs-src/reference/api/drivers.md").read_text()
refs = re.findall(r"^::: (remote_store\.drivers\.\w+)", doc, re.M)
print("== mkdocstrings refs", len(refs))
documented = {r.rsplit(".", 1)[1] for r in refs}
print("in __all__ but not in drivers.md:", sorted(set(d.__all__) - documented))
print("in drivers.md but not in __all__:", sorted(documented - set(d.__all__)))

for proto in (d.Driver, d.AsyncDriver):
    print("==", proto.__name__)
    meths = [n for n, v in vars(proto).items() if callable(v) and not n.startswith("_")]
    print(" methods", len(meths), meths)
    print(" annotations", list(proto.__annotations__))
    for n in meths:
        print(
            "  ",
            n,
            inspect.signature(getattr(proto, n)),
            "coroutine" if inspect.iscoroutinefunction(getattr(proto, n)) else "",
        )

for name in d.__all__:
    if "Supports" in name or "WriteHandle" in name:
        proto = getattr(d, name)
        meths = [n for n, v in vars(proto).items() if callable(v) and not n.startswith("_")]
        for n in meths:
            print(name, n, inspect.signature(getattr(proto, n)))
        print(name, "annotations", list(getattr(proto, "__annotations__", {})))

# Async backend surface claims
from remote_store import Backend
from remote_store.aio import AsyncBackend

print("AsyncBackend has read_seekable:", hasattr(AsyncBackend, "read_seekable"))
print("AsyncBackend has open_atomic:", hasattr(AsyncBackend, "open_atomic"))
print("Backend abstract methods:", sorted(Backend.__abstractmethods__))
