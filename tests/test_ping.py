"""Tests for Store.ping() — spec 026 (Store-level only).

PING-001 (`Store.ping()` delegates to `Backend.check_health()` and propagates
exceptions) and PING-010 (the observe `on_ping` / `on_error` integration)
are Store-level cross-cutting tests; they belong here.

The ABC-level `Backend.check_health()` healthy-path contract (PING-002 — every
backend returns None when reachable and authorized) lives in
tests/backends/conformance/test_check_health.py. The per-backend
probe-identity assertions (which SDK method is the probe — PING-004/005/006/007)
and SDK error-mapping branches (PING-009) live in each backend's
tests/backends/<x>/test_ping.py (and tests/backends/s3/test_pyarrow.py for the
S3-PyArrow case). The LocalBackend-specific filesystem failure-injection
(missing root, unreadable root) lives in tests/backends/local/test_ping.py.
Split out under BK-217 (BK-191 slice 2/6).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from remote_store._errors import BackendUnavailable
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend


class TestStorePing:
    @pytest.mark.spec("PING-001")
    def test_ping_delegates_to_check_health(self) -> None:
        backend = MemoryBackend()
        backend.check_health = MagicMock(spec=MemoryBackend.check_health)  # type: ignore[method-assign]
        result = Store(backend).ping()
        backend.check_health.assert_called_once()
        assert result is None

    @pytest.mark.spec("PING-001")
    def test_ping_propagates_exception(self) -> None:
        backend = MemoryBackend()
        mock_check = MagicMock(spec=MemoryBackend.check_health)
        mock_check.side_effect = BackendUnavailable("down", backend="memory")
        backend.check_health = mock_check  # type: ignore[method-assign]
        with pytest.raises(BackendUnavailable, match="down"):
            Store(backend).ping()

    @pytest.mark.spec("PING-001")
    def test_child_store_ping(self) -> None:
        result = Store(MemoryBackend()).child("subdir").ping()
        assert result is None

    @pytest.mark.spec("PING-008")
    def test_memory_backend_always_healthy_end_to_end(self) -> None:
        # End-to-end Store.ping() -> real MemoryBackend.check_health() (the
        # default ABC no-op). test_ping_delegates_to_check_health mocks
        # check_health away, and the conformance suite calls check_health()
        # directly; this pins the composition PING-008 actually specifies.
        result = Store(MemoryBackend()).ping()
        assert result is None


class TestPingObserve:
    @pytest.mark.spec("PING-010")
    @pytest.mark.parametrize(
        ("hook_kwarg", "check"),
        [
            pytest.param("on_ping", lambda events: events[0].operation == "ping", id="on_ping"),
            pytest.param("on_any", lambda events: any(e.operation == "ping" for e in events), id="on_any"),
        ],
    )
    def test_observe_hook_fires_for_ping(self, hook_kwarg: str, check: Any) -> None:
        from remote_store.ext.observe import observe

        events: list[Any] = []
        observed = observe(Store(MemoryBackend()), **{hook_kwarg: lambda e: events.append(e)})
        observed.ping()
        assert len(events) >= 1
        assert check(events)

    @pytest.mark.spec("PING-010")
    def test_observe_on_error_fires_for_failed_ping(self) -> None:
        from remote_store.ext.observe import observe

        errors: list[Any] = []
        backend = MemoryBackend()
        mock_check = MagicMock(spec=MemoryBackend.check_health)
        mock_check.side_effect = BackendUnavailable("down", backend="memory")
        backend.check_health = mock_check  # type: ignore[method-assign]
        observed = observe(Store(backend), on_error=lambda e: errors.append(e))
        with pytest.raises(BackendUnavailable):
            observed.ping()
        assert len(errors) == 1
        assert errors[0].error is not None
