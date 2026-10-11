"""The contract kernel: one ``Backend`` implementation over thin drivers.

Private. Nothing here is exported until the first backend runs on it.

Layout: ``_model``, ``_keys`` and ``_aggregate`` are runtime-neutral.
``_async`` holds the hand-written async driver protocols and kernel core.
``_sync`` holds the sync twin that ``scripts/gen_sync_kernel.py`` generates
from it, with one hand-written ``_io`` module per runtime. ``backend`` and
``aio_backend`` add the members each runtime has alone.
"""

# Design: RFC-0017 D1, D2 and D6. The clauses only the kernel states are spec
# 003's BE-030 (key rule) and BE-031 (delete_folder).
