"""Drive the guide's RedisDriver (fake client from tests/test_snippets.py) on claims the tests do not pin."""

from __future__ import annotations

import sys

sys.path.insert(0, ".")
import examples.snippets.custom_backend_guide as cbg
from tests.test_snippets import _FakeRedisModule

cbg.redis = _FakeRedisModule
from remote_store import Store


def show(label, fn):
    try:
        print(f"[{label}] OK -> {fn()!r}")
    except BaseException as e:  # noqa: BLE001
        print(f"[{label}] {type(e).__name__}: {e}")


b = cbg.RedisBackend(prefix="rs:")
s = Store(backend=b)
s.write("w1/x", b"1")
s.write("w[1]/y", b"2")
s.write("st*r/z", b"3")
s.write("stXr/q", b"4")
show("list w[1]", lambda: sorted(str(f.path) for f in s.list_files("w[1]")))
show("list st*r", lambda: sorted(str(f.path) for f in s.list_files("st*r")))
show("list_folders root", lambda: sorted(f.name for f in s.list_folders("")))
show("to_key(native_path)", lambda: [b.to_key(b.native_path(k)) for k in ["", "a/b", "../x", "w[1]"]])
show("read_seekable", lambda: b.read_seekable("w1/x").read())
show("unwrap(int)", lambda: b.unwrap(int))
show("delete_folder w[1] recursive", lambda: s.delete_folder("w[1]", recursive=True))
show("w1 still there", lambda: s.read_bytes("w1/x"))
# a prefix that itself holds a wildcard
b2 = cbg.RedisBackend(prefix="app[1]:")
s2 = Store(backend=b2)
s2.write("k", b"v")
show("list with wildcard prefix", lambda: [str(f.path) for f in s2.list_files("")])
# flat: key 'a' and keys under 'a/' both stored (another tool)
b3 = cbg.RedisBackend(prefix="z:")
c = b3._driver._client
c.hset("z:file:a", mapping={"data": b"x", "size": 1, "modified_at": "2026-01-01T00:00:00+00:00"})
c.hset("z:file:a/b", mapping={"data": b"y", "size": 1, "modified_at": "2026-01-01T00:00:00+00:00"})
s3 = Store(backend=b3)
show("shadowed: list root recursive", lambda: sorted(str(f.path) for f in s3.list_files("", recursive=True)))
show("shadowed: read a/b", lambda: s3.read_bytes("a/b"))
