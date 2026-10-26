"""Probe: which keys each backend's Store.write accepts (BK-468; run with `hatch run python <this file>`)."""

import tempfile

from remote_store import Store
from remote_store.backends import LocalBackend, MemoryBackend

CASES = {
    "surrogate": "\ud800",
    "300 chars": "x" * 300,
    "control \\x01": "a\x01b",
    "newline": "a\nb",
    "backslash a\\b": "a\\b",
    "lone backslash": "\\",
    "./": "./",
    "/": "/",
    "/a": "/a",
    "a/": "a/",
    "con": "CON",
    "colon": "a:b",
    "trailing dot": "a.",
    "trailing space": "a ",
}

with tempfile.TemporaryDirectory() as d:
    for name, backend in (("memory", MemoryBackend()), ("local", LocalBackend(root=d))):
        store = Store(backend=backend)
        for label, key in CASES.items():
            try:
                r = store.write(key, b"x", overwrite=True)
                out = f"ok path={str(r.path)!r}"
            except Exception as e:  # noqa: BLE001
                out = f"{type(e).__module__}.{type(e).__name__}: {str(e)[:70]}"
            print(f"{name:7} {label:16} {out}")
