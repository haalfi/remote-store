"""C06: an open Local read() stream across a replace or a delete on the same host.

Usage (repo root): hatch run python sdd/research/bk-511-op01-behaviour-classification/local_pin.py
Reads 2 bytes of a 16 KiB file, replaces (os.replace) or removes it, reads the rest.
"""

from __future__ import annotations

import os
import platform
import tempfile
from pathlib import Path

from remote_store import Store
from remote_store.backends import LocalBackend

WORK = Path(__file__).resolve().parents[3] / "tmp" / "bk-511-local-pin"  # repo tmp/, gitignored

if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)
    print(platform.system(), platform.python_version())
    for action in ("replace", "remove"):
        d = Path(tempfile.mkdtemp(dir=WORK))
        (d / "a").write_bytes(b"v1" * 8192)  # beyond one 8 KiB buffer, so later reads reach the file
        s = Store(LocalBackend(str(d))).read("a")
        got = s.read(2)
        if action == "replace":
            (d / "new").write_bytes(b"v2" * 8192)
            os.replace(d / "new", d / "a")
        else:
            os.remove(d / "a")
        got += s.read()
        s.close()
        print(f"{action}: {len(got)} bytes delivered, all of the old content: {got == b'v1' * 8192}")
