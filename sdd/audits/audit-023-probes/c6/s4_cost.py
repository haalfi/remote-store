"""Measure the guide's write-cost claim (flat vs hierarchical) and limit=1 claims."""

from __future__ import annotations

from pathlib import Path

from remote_store.drivers import DriverBackend

src = Path(__file__).with_name("s2_behaviour.py").read_text().split("# --- A. construction")[0]
ns: dict = {}
exec(compile(src, "s2_head", "exec"), ns)
Dict = ns["Dict"]

d = Dict()
b = DriverBackend(d)
d.calls.clear()
b.write("a/b/c.txt", b"x")
print("flat write a/b/c.txt calls:", d.calls)
d.calls.clear()
b.write("a/b/c.txt", b"y", overwrite=True)
print("flat overwrite calls:", d.calls)
d.calls.clear()


class Hier(Dict):
    namespace = "hierarchical"


h = Hier()
hb = DriverBackend(h)
h.calls.clear()
hb.write("a/b/c.txt", b"x")
print("hier write a/b/c.txt calls:", h.calls)
