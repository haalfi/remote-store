"""The contract kernel: one ``Backend`` implementation over thin drivers.

The modules are private; ``remote_store.drivers`` is the public surface that
re-exports what a driver author uses.

Layout: ``_model``, ``_keys`` and ``_aggregate`` are runtime-neutral.
``_async`` holds the hand-written async driver protocols and kernel core.
``_sync`` holds the sync twin that ``scripts/gen_sync_kernel.py`` generates
from it, with one hand-written ``_io`` module per runtime. ``backend`` and
``aio_backend`` add the members each runtime has alone.
"""

# Design: RFC-0017 D1, D2 and D6, and RFC-0021. Spec 003 states the kernel's
# contract in BE-030 (key rule), BE-031 (delete_folder) and BE-032 (the store
# tree on the kernel, whose parts A.1 to A.10 the core cites as "A.n"), and in
# the sentences of its other clauses that name "a class on the kernel".
