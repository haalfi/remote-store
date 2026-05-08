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
"""

from __future__ import annotations

from tests.backends.fixtures.registry import (
    AnyBackend,
    BackendFixture,
    all_fixtures,
    fixture_params,
    fixtures,
)


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
    # the async-memory and async-local entries that share a single module.
    _MODULE_FOR: dict[str, str] = {
        "memory_async_native": "memory_async",
        "memory_async_adapted": "memory_async",
        "local_async_adapted": "local_async",
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
