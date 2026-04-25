"""Sync↔async API drift guard.

Public methods on ``Store`` / ``Backend`` must have counterparts on
``AsyncStore`` / ``AsyncBackend`` with matching parameter names, kinds,
and defaults (annotations legitimately differ: e.g. ``Iterator[T]`` vs
``AsyncIterator[T]``, ``WritableContent`` vs ``AsyncWritableContent``).

The allowlists below capture methods that are intentionally sync-only or
async-only; adding a new method to one side must either add the
counterpart on the other side or extend the allowlist with
justification. Without this guard, async silently lags sync.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from remote_store._backend import Backend
from remote_store._store import Store
from remote_store.aio._async_backend import AsyncBackend
from remote_store.aio._async_store import AsyncStore

# Methods that intentionally exist only on the sync side.
_STORE_SYNC_ONLY = frozenset(
    {
        "read_seekable",  # returns sync BinaryIO; async callers use read() iterator
        "open_atomic",  # yields sync BinaryIO; no async file-object protocol
        "close",  # aclose() is the async counterpart
    }
)
_STORE_ASYNC_ONLY = frozenset(
    {
        "aclose",  # close() is the sync counterpart
    }
)
_BACKEND_SYNC_ONLY = frozenset(
    {
        "read_seekable",
        "open_atomic",
        "close",
    }
)
_BACKEND_ASYNC_ONLY = frozenset(
    {
        "aclose",
    }
)


def _public_methods(cls: type) -> dict[str, inspect.Signature]:
    """Return {name: Signature} for public routines declared on *cls* or its bases."""
    out: dict[str, inspect.Signature] = {}
    for name, member in inspect.getmembers(cls, predicate=inspect.isroutine):
        if name.startswith("_"):
            continue
        out[name] = inspect.signature(member)
    return out


def _param_shape(sig: inspect.Signature) -> list[tuple[str, Any, Any]]:
    """Reduce a signature to (name, kind, default) tuples (skip annotations and return).

    ``kind`` is typed as ``Any`` to avoid naming the private ``inspect._ParameterKind``
    enum; equality on the values still works via the public ``inspect.Parameter.kind``
    attribute. Testing rule: never depend on CPython private names.
    """
    return [(p.name, p.kind, p.default) for p in sig.parameters.values()]


_STORE_SYNC = _public_methods(Store)
_STORE_ASYNC = _public_methods(AsyncStore)
_BACKEND_SYNC = _public_methods(Backend)
_BACKEND_ASYNC = _public_methods(AsyncBackend)

_SHARED_STORE = sorted(set(_STORE_SYNC) & set(_STORE_ASYNC))
_SHARED_BACKEND = sorted(set(_BACKEND_SYNC) & set(_BACKEND_ASYNC))


class TestStoreAsyncStoreDrift:
    """AsyncStore keeps method-set parity with Store modulo the allowlist."""

    @pytest.mark.spec("ASYNC-046")
    def test_every_sync_method_has_async_counterpart(self) -> None:
        missing = (set(_STORE_SYNC) - set(_STORE_ASYNC)) - _STORE_SYNC_ONLY
        assert not missing, (
            f"Store methods without AsyncStore counterpart "
            f"(add an async counterpart, or extend _STORE_SYNC_ONLY with "
            f"justification): {sorted(missing)}"
        )

    @pytest.mark.spec("ASYNC-046")
    def test_every_async_method_has_sync_counterpart(self) -> None:
        extra = (set(_STORE_ASYNC) - set(_STORE_SYNC)) - _STORE_ASYNC_ONLY
        assert not extra, (
            f"AsyncStore methods without Store counterpart "
            f"(add a sync counterpart, or extend _STORE_ASYNC_ONLY with "
            f"justification): {sorted(extra)}"
        )

    @pytest.mark.spec("ASYNC-046")
    @pytest.mark.parametrize("method", _SHARED_STORE)
    def test_shared_method_parameters_match(self, method: str) -> None:
        sync_shape = _param_shape(_STORE_SYNC[method])
        async_shape = _param_shape(_STORE_ASYNC[method])
        assert sync_shape == async_shape, (
            f"Store.{method} vs AsyncStore.{method} parameter drift:\n  sync:  {sync_shape}\n  async: {async_shape}"
        )


class TestBackendAsyncBackendDrift:
    """AsyncBackend keeps method-set parity with Backend modulo the allowlist."""

    @pytest.mark.spec("ASYNC-001")
    def test_every_sync_method_has_async_counterpart(self) -> None:
        missing = (set(_BACKEND_SYNC) - set(_BACKEND_ASYNC)) - _BACKEND_SYNC_ONLY
        assert not missing, (
            f"Backend methods without AsyncBackend counterpart "
            f"(add an async counterpart, or extend _BACKEND_SYNC_ONLY with "
            f"justification): {sorted(missing)}"
        )

    @pytest.mark.spec("ASYNC-001")
    def test_every_async_method_has_sync_counterpart(self) -> None:
        extra = (set(_BACKEND_ASYNC) - set(_BACKEND_SYNC)) - _BACKEND_ASYNC_ONLY
        assert not extra, (
            f"AsyncBackend methods without Backend counterpart "
            f"(add a sync counterpart, or extend _BACKEND_ASYNC_ONLY with "
            f"justification): {sorted(extra)}"
        )

    @pytest.mark.spec("ASYNC-001")
    @pytest.mark.parametrize("method", _SHARED_BACKEND)
    def test_shared_method_parameters_match(self, method: str) -> None:
        sync_shape = _param_shape(_BACKEND_SYNC[method])
        async_shape = _param_shape(_BACKEND_ASYNC[method])
        assert sync_shape == async_shape, (
            f"Backend.{method} vs AsyncBackend.{method} parameter drift:\n  sync:  {sync_shape}\n  async: {async_shape}"
        )
