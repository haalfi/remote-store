"""Backend fixture registry.

Per spec 048 / TEST-004 the registry is the single source of truth for
which backends conformance and backend-specific tests parametrise over.

Public surface:

    from tests.backends.fixtures import BackendFixture, all_fixtures, fixtures

``all_fixtures()`` returns every registered fixture, regardless of stage
or capability gating. ``fixtures(*caps, is_async=...)`` returns the
subset whose ``stage <= current_stage()``, ``is_async`` matches the
requested mode, and whose capabilities cover ``caps``.

Fixture-side state (the active stage, session-scoped infra URLs) lives
in ``tests.backends.fixtures._state``. Per-backend factory modules
(``memory``, ``local``, ``azurite``, ...) each register one or more
``BackendFixture`` records by appending to ``_FIXTURES`` in
``tests.backends.fixtures.registry``.

The public names are re-exported **lazily** via ``__getattr__``. Eager
re-export from ``registry`` would pull ``import pytest`` and
``from remote_store...`` into every consumer of this package — including
``scripts/mutate_scopes.py``, which imports ``_loader`` at scope
introspection time on a vanilla ``actions/setup-python`` runner that has
neither pytest nor remote_store installed (see BUG-206). With lazy
re-export, ``import tests.backends.fixtures._loader`` only runs this
``__init__``; ``registry`` is loaded the first time a caller dereferences
one of its names, which is always inside a pytest session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tests.backends.fixtures.registry import (
        AnyBackend,
        BackendFixture,
        all_fixtures,
        fixture_params,
        fixtures,
    )

_LAZY_REGISTRY_NAMES = frozenset({"AnyBackend", "BackendFixture", "all_fixtures", "fixture_params", "fixtures"})


def __getattr__(name: str) -> Any:
    if name in _LAZY_REGISTRY_NAMES:
        from tests.backends.fixtures import registry

        return getattr(registry, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _load_all() -> None:
    """Import every per-fixture factory module to trigger registration.

    The loop walks ``fixtures.toml`` (via ``_loader.load_fixtures``) so the
    list of registered fixtures is derived from the TOML registry, not
    duplicated as a hardcoded import list. Adding a fixture is therefore
    a one-step change: declare ``[fixture.<name>]`` in ``fixtures.toml``
    and create ``tests/backends/fixtures/<name>.py``.

    A few TOML names map to a Python module that registers more than one
    fixture at import time (e.g. both ``memory_async_native`` and
    ``memory_async_adapted`` live in ``memory_async.py``). The mapping
    here resolves the TOML key to the module that must be imported; the
    registry's duplicate-name guard catches accidental double-imports.
    """
    import importlib

    from tests.backends.fixtures._loader import load_fixtures

    # Per-fixture TOML key → Python module under tests.backends.fixtures
    # that registers that key. Most fixtures map 1:1; the exceptions are
    # the async-memory and async-local entries that share a single module,
    # and the ID-211 strict variants whose factory module is the non-strict
    # one (they differ only in the opt-in kwarg threaded into the
    # backend constructor).
    _MODULE_FOR: dict[str, str] = {
        "memory_async_native": "memory_async",
        "memory_async_adapted": "memory_async",
        "local_async_adapted": "local_async",
        "s3_moto_strict": "s3_moto",
        "s3_pyarrow_moto_strict": "s3_pyarrow_moto",
        "sqlblob_strict": "sqlblob",
        "azurite_strict": "azurite",
    }

    seen: set[str] = set()
    for name in load_fixtures():
        module = _MODULE_FOR.get(name, name)
        if module in seen:
            continue
        seen.add(module)
        importlib.import_module(f"tests.backends.fixtures.{module}")


__all__ = [
    "AnyBackend",
    "BackendFixture",
    "all_fixtures",
    "fixture_params",
    "fixtures",
]
