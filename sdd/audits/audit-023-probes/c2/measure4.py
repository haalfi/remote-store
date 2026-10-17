"""MEM-DS-003 / MEM-040: transient allocation of an in-place overwrite (tracemalloc peak)."""

from __future__ import annotations

import tracemalloc

from remote_store.backends._memory import MemoryBackend

N = 10_000_000
b = MemoryBackend()
payload = b"a" * N
b.write("f", payload)
buf_before = b._driver._tree.traverse("f").data
payload2 = b"b" * N
tracemalloc.start()
tracemalloc.reset_peak()
b.write("f", payload2, overwrite=True)
cur, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
same = b._driver._tree.traverse("f").data is buf_before
print(
    f"overwrite of {N} B: same bytearray object: {same}; tracemalloc peak during write: {peak} B ({peak / N:.2f}x content)"
)
