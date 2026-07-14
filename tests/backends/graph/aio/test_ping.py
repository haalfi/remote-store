"""GraphBackend check_health() probe-identity and error-mapping tests -- PING-011.

The healthy-path assertion (``check_health() is None``) is the universal ABC
contract covered by tests/backends/conformance/test_check_health.py, and the
override-or-exemption structural check lives in
tests/backends/conformance/test_health_probe_declared.py. This file pins what is
Graph-specific:

- The probe is one item-metadata ``GET`` on the effective root, reusing
  ``_get_item("")`` — ``GET /drives/{id}/root`` with no ``base_path``, or the
  ``base_path`` folder item when one is pinned.
- It runs at the default item scope, not the type-probe scope: a drive-identity
  ``resourceNotFound`` maps to ``BackendUnavailable`` (an unreachable / missing
  drive), while a ``base_path`` folder ``itemNotFound`` maps to ``NotFound``
  (PING-011, GR-031). A ``401`` / ``403`` maps to ``PermissionDenied`` (PING-009).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from remote_store._errors import BackendUnavailable, NotFound, PermissionDenied
from remote_store.aio.backends._graph.backend import GraphBackend

_DRIVE = "b!driveid123"


def _make(**kwargs: object) -> GraphBackend:
    return GraphBackend(_DRIVE, token_provider=lambda: "tok", **kwargs)  # type: ignore[arg-type]


def _root_url(**kwargs: object) -> str:
    """The item-metadata endpoint the probe GETs, via the real URL builder.

    Routing through ``_item_url("")`` keeps the mock honest about the drive-root
    special-case (bare ``/root``) and the ``base_path`` folder-item form.
    """
    return _make(**kwargs)._item_url("")


class TestGraphHealthProbe:
    """PING-011: one metadata GET on the effective root, mapped through GR-031."""

    @respx.mock
    @pytest.mark.spec("PING-011")
    async def test_healthy_returns_none_and_probes_root_once(self) -> None:
        route = respx.get(_root_url()).mock(return_value=httpx.Response(200, json={"folder": {}, "root": {}}))
        async with _make() as backend:
            assert await backend.check_health() is None
        assert route.call_count == 1
        assert route.calls.last.request.method == "GET"

    @respx.mock
    @pytest.mark.spec("PING-011")
    async def test_drive_unreachable_raises_backend_unavailable(self) -> None:
        # The regression pin: a drive-identity 404 must escalate, not report healthy.
        # A no-op check_health() returns None here and fails this assertion.
        respx.get(_root_url()).mock(return_value=httpx.Response(404, json={"error": {"code": "resourceNotFound"}}))
        async with _make() as backend:
            with pytest.raises(BackendUnavailable):
                await backend.check_health()

    @respx.mock
    @pytest.mark.spec("PING-011")
    async def test_missing_base_path_root_raises_not_found(self) -> None:
        # A configured base_path folder that does not exist is a missing root.
        respx.get(_root_url(base_path="scoped")).mock(
            return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}})
        )
        async with _make(base_path="scoped") as backend:
            with pytest.raises(NotFound):
                await backend.check_health()

    @respx.mock
    @pytest.mark.spec("PING-011")
    @pytest.mark.parametrize("status", [401, 403])
    async def test_bad_credentials_raise_permission_denied(self, status: int) -> None:
        respx.get(_root_url()).mock(return_value=httpx.Response(status, json={"error": {"code": "accessDenied"}}))
        async with _make() as backend:
            with pytest.raises(PermissionDenied):
                await backend.check_health()
