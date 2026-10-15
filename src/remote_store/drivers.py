"""The contract kernel and the driver protocols a backend is written against.

A backend is a *driver*: a class that maps one-to-one onto its wire and carries
no path, root, type or closed logic. ``DriverBackend`` (sync) and
``AsyncDriverBackend`` (async) are the kernel: each is a complete ``Backend`` /
``AsyncBackend`` built over a driver, and decides once everything the backend
contract states, so a driver implements only the wire primitives. Errors are
split the same way: the driver's ``classify`` names what a native exception
means, and the kernel decides when it is asked and fills the error's ``path``
and ``backend``.

``Driver`` and ``AsyncDriver`` are the required primitives and declared
attributes. Each ``Supports*`` protocol is optional and detected per instance
when the kernel is constructed. Construction refuses a declared ``COPY``,
``MOVE``, ``ATOMIC_MOVE``, ``ATOMIC_WRITE`` or ``GLOB`` that the protocols the
driver presents cannot back; the other capabilities need only the required
primitives, so the driver's declaration is taken as it stands. ``Entry``, ``Page``
and ``PutResult`` are the records a driver hands the kernel, and ``Op`` names
the operation a ``classify`` call is asked about.

Example:
    A driver is wrapped once, by a subclass that builds it::

        class MyBackend(DriverBackend):
            def __init__(self, **options) -> None:
                super().__init__(MyDriver(**options))
"""

from __future__ import annotations

from remote_store._kernel._async.driver import (
    AsyncDriver,
    AsyncSupportsAtomicMove,
    AsyncSupportsCopy,
    AsyncSupportsDeleteTree,
    AsyncSupportsEnsureParents,
    AsyncSupportsFolderStats,
    AsyncSupportsGlob,
    AsyncSupportsOpenWrite,
    AsyncSupportsRangeRead,
    AsyncSupportsRemoveFolder,
    AsyncSupportsRename,
    AsyncWriteHandle,
)
from remote_store._kernel._model import Entry, Op, Page, PutResult
from remote_store._kernel._sync.driver import (
    Driver,
    SupportsAtomicMove,
    SupportsCopy,
    SupportsDeleteTree,
    SupportsEnsureParents,
    SupportsFolderStats,
    SupportsGlob,
    SupportsOpenWrite,
    SupportsRangeRead,
    SupportsRemoveFolder,
    SupportsRename,
    WriteHandle,
)
from remote_store._kernel.aio_backend import AsyncDriverBackend
from remote_store._kernel.backend import DriverBackend

__all__ = [
    "AsyncDriver",
    "AsyncDriverBackend",
    "AsyncSupportsAtomicMove",
    "AsyncSupportsCopy",
    "AsyncSupportsDeleteTree",
    "AsyncSupportsEnsureParents",
    "AsyncSupportsFolderStats",
    "AsyncSupportsGlob",
    "AsyncSupportsOpenWrite",
    "AsyncSupportsRangeRead",
    "AsyncSupportsRemoveFolder",
    "AsyncSupportsRename",
    "AsyncWriteHandle",
    "Driver",
    "DriverBackend",
    "Entry",
    "Op",
    "Page",
    "PutResult",
    "SupportsAtomicMove",
    "SupportsCopy",
    "SupportsDeleteTree",
    "SupportsEnsureParents",
    "SupportsFolderStats",
    "SupportsGlob",
    "SupportsOpenWrite",
    "SupportsRangeRead",
    "SupportsRemoveFolder",
    "SupportsRename",
    "WriteHandle",
]
