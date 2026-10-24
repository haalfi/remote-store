"""Probe: read-side answers for root spellings and unstorable keys (BK-468; run with `hatch run python <this file>`)."""

import tempfile

from remote_store import Store
from remote_store.backends import LocalBackend, MemoryBackend

KEYS = ["", ".", "./", "/", "\\", "\ud800", "x" * 300]

with tempfile.TemporaryDirectory() as d:
    for name, backend in (("memory", MemoryBackend()), ("local", LocalBackend(root=d))):
        store = Store(backend=backend)
        for key in KEYS:
            for op in ("exists", "is_folder", "list_files"):
                try:
                    r = getattr(store, op)(key)
                    if op == "list_files":
                        r = list(r)
                    out = f"ok {r!r}"
                except Exception as e:  # noqa: BLE001
                    out = f"{type(e).__name__}: {str(e)[:50]}"
                print(f"{name:7} {op:10} {key[:6]!r:12} {out}")
