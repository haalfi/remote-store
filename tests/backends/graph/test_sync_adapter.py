"""ResourceLocked forwarding across the async->sync boundary for the Graph backend.

The Graph backend is async-only; sync callers reach it through
``AsyncBackendSyncAdapter`` (ADR-0025). ``ResourceLocked`` (ERR-013) is Graph's
signature error — no other backend raises it — so the sync-adapter conformance
suite (which wraps Memory / Local / Azure) never exercises it crossing the
boundary. This module pins that path: a Graph ``423 resourceLocked`` raised on the
async backend's private event loop must surface verbatim to a sync caller, proving
the GR-DONE wrapper-forwarding gate for the sync adapter.
"""

from __future__ import annotations

import re

import httpx
import pytest
import respx

from remote_store._async_to_sync_adapter import AsyncBackendSyncAdapter
from remote_store._errors import ResourceLocked
from remote_store.aio.backends._graph.backend import GraphBackend

_DRIVE = "b!driveid123"
# Small-file writes go to PUT /content (matches the route shape in test_write.py).
_CONTENT_RE = re.compile(r"https://graph\.microsoft\.com/v1\.0/drives/.+:/content(\?.*)?$")


@respx.mock
@pytest.mark.spec("GR-045")
def test_resource_locked_surfaces_through_sync_adapter() -> None:
    # A 423 on the small-file PUT /content maps to ResourceLocked (GR-045). The
    # async backend raises it on its background-thread loop; the adapter's
    # future.result() must re-raise it verbatim to the synchronous caller.
    respx.put(_CONTENT_RE).mock(return_value=httpx.Response(423, json={"error": {"code": "resourceLocked"}}))
    backend = GraphBackend(_DRIVE, token_provider=lambda: "tok")
    with AsyncBackendSyncAdapter(backend) as adapter, pytest.raises(ResourceLocked) as exc:
        adapter.write("locked.txt", b"data")
    assert exc.value.backend == "graph"
