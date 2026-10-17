"""Audit probe c1 (5): unwrap after a terminal close; namespace-typo flat write below an item measured on the kernel."""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from tests._kernel._fake import FakeStore, make_kernel  # noqa: E402

for rt in ("sync", "async"):
    st = FakeStore()
    r = make_kernel(rt, st, close_is_terminal=True)
    r.close()
    try:
        out = r.unwrap(FakeStore)
        print(f"[{rt}] closed terminal kernel: unwrap(FakeStore) returned the handle: {out is st}")
    except BaseException as e:  # noqa: BLE001
        print(f"[{rt}] closed terminal kernel: unwrap raised {type(e).__name__}: {e}")
    try:
        r.exists("a")
    except BaseException as e:  # noqa: BLE001
        print(f"[{rt}] same kernel: exists('a') raised {type(e).__name__}")
