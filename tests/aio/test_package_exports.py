"""The async packages' exports: the Memory names are loaded lazily, and still listed.

``remote_store.aio`` and ``remote_store.aio.backends`` resolve ``AsyncMemoryBackend``
and ``AsyncMemoryDriver`` through a module ``__getattr__``, since the async kernel
imports the package. Introspection must still see them.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

LAZY = ("AsyncMemoryBackend", "AsyncMemoryDriver")


@pytest.mark.spec("ASYNC-001")
@pytest.mark.parametrize("module", ["remote_store.aio", "remote_store.aio.backends"])
def test_the_lazy_memory_names_are_listed_by_introspection(module: str) -> None:
    package = importlib.import_module(module)
    listed = dir(package)
    members = dict(inspect.getmembers(package))
    for name in LAZY:
        assert name in package.__all__
        assert name in listed
        assert members[name] is getattr(package, name)


@pytest.mark.spec("ASYNC-001")
@pytest.mark.parametrize("module", ["remote_store.aio", "remote_store.aio.backends"])
def test_an_unknown_name_is_still_an_attribute_error(module: str) -> None:
    package = importlib.import_module(module)
    with pytest.raises(AttributeError, match="no attribute 'NoSuchThing'"):
        package.NoSuchThing  # noqa: B018
