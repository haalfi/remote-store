"""``remote_store.drivers`` exports: the async kernel class is loaded lazily, and still listed.

``AsyncDriverBackend``'s module imports ``remote_store.aio``, and with it the
async store and every installed async backend. A sync driver author importing
``Driver`` and ``DriverBackend`` pays none of that; introspection still sees
the lazy name.
"""

from __future__ import annotations

import inspect
import subprocess
import sys

import pytest

import remote_store.drivers as drivers


def test_importing_drivers_loads_no_async_package() -> None:
    probe = (
        "import sys, remote_store.drivers; "
        "print(sorted(m for m in sys.modules if m == 'remote_store.aio' or m.startswith('remote_store.aio.')))"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"


def test_the_lazy_name_resolves_to_the_async_kernel() -> None:
    from remote_store._kernel.aio_backend import AsyncDriverBackend

    assert drivers.AsyncDriverBackend is AsyncDriverBackend


def test_the_lazy_name_is_listed_by_introspection() -> None:
    assert "AsyncDriverBackend" in drivers.__all__
    assert "AsyncDriverBackend" in dir(drivers)
    members = dict(inspect.getmembers(drivers))
    assert members["AsyncDriverBackend"] is drivers.AsyncDriverBackend
    # Every exported name resolves, the eager ones and the lazy one alike.
    assert all(getattr(drivers, name) is not None for name in drivers.__all__)


def test_an_unknown_name_is_still_an_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no attribute 'NoSuchThing'"):
        drivers.NoSuchThing  # noqa: B018
