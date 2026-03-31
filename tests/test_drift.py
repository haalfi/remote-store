"""Drift protection -- ensures async API mirrors sync API."""

from __future__ import annotations

import inspect

import pytest

from remote_store._backend import Backend
from remote_store._store import Store
from remote_store.aio._async_backend import AsyncBackend
from remote_store.aio._async_store import AsyncStore


class TestStoreAsyncDrift:
    """Verify AsyncStore mirrors Store method signatures."""

    # Methods intentionally different or deferred
    _DEFERRED = {"read_seekable", "open_atomic", "close"}
    _RENAMED = {"close": "aclose"}
    # Methods whose return types differ (sync BinaryIO vs async AsyncIterator)
    _RETURN_DIFFERS = {"read", "list_files", "list_folders", "iter_children", "glob"}

    @pytest.mark.spec("ASYNC-046")
    def test_all_store_methods_have_async_equivalents(self) -> None:
        sync_methods = {m for m in dir(Store) if not m.startswith("_") and callable(getattr(Store, m))}
        async_methods = {m for m in dir(AsyncStore) if not m.startswith("_") and callable(getattr(AsyncStore, m))}
        for method in sorted(sync_methods - self._DEFERRED):
            target = self._RENAMED.get(method, method)
            assert target in async_methods, f"Store.{method} has no AsyncStore.{target}"

    @pytest.mark.spec("ASYNC-046")
    def test_method_parameter_names_match(self) -> None:
        sync_methods = {m for m in dir(Store) if not m.startswith("_") and callable(getattr(Store, m))}
        for method in sorted(sync_methods - self._DEFERRED - self._RETURN_DIFFERS):
            target = self._RENAMED.get(method, method)
            if not hasattr(AsyncStore, target):
                continue
            sync_sig = inspect.signature(getattr(Store, method))
            async_sig = inspect.signature(getattr(AsyncStore, target))
            sync_params = [(name, p.kind) for name, p in sync_sig.parameters.items() if name != "self"]
            async_params = [(name, p.kind) for name, p in async_sig.parameters.items() if name != "self"]
            assert sync_params == async_params, (
                f"Parameter mismatch for {method}: sync={sync_params}, async={async_params}"
            )


class TestBackendAsyncDrift:
    """Verify AsyncBackend mirrors Backend method signatures."""

    _DEFERRED = {"read_seekable", "open_atomic", "close"}
    _RENAMED = {"close": "aclose"}
    # Methods whose content type or return type differs
    _SIGNATURE_DIFFERS = {"read", "write", "write_atomic", "list_files", "list_folders", "glob", "iter_children"}

    @pytest.mark.spec("ASYNC-001")
    def test_all_backend_methods_have_async_equivalents(self) -> None:
        sync_methods = {m for m in dir(Backend) if not m.startswith("_") and callable(getattr(Backend, m))}
        async_methods = {m for m in dir(AsyncBackend) if not m.startswith("_") and callable(getattr(AsyncBackend, m))}
        for method in sorted(sync_methods - self._DEFERRED):
            target = self._RENAMED.get(method, method)
            assert target in async_methods, f"Backend.{method} has no AsyncBackend.{target}"

    @pytest.mark.spec("ASYNC-001")
    def test_backend_method_parameter_names_match(self) -> None:
        sync_methods = {m for m in dir(Backend) if not m.startswith("_") and callable(getattr(Backend, m))}
        for method in sorted(sync_methods - self._DEFERRED - self._SIGNATURE_DIFFERS):
            target = self._RENAMED.get(method, method)
            if not hasattr(AsyncBackend, target):
                continue
            sync_sig = inspect.signature(getattr(Backend, method))
            async_sig = inspect.signature(getattr(AsyncBackend, target))
            sync_params = [(name, p.kind) for name, p in sync_sig.parameters.items() if name != "self"]
            async_params = [(name, p.kind) for name, p in async_sig.parameters.items() if name != "self"]
            assert sync_params == async_params, (
                f"Parameter mismatch for {method}: sync={sync_params}, async={async_params}"
            )
