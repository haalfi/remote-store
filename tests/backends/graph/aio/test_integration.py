"""Integration-only invariants for ``GraphBackend`` (spec 044 § Integration-only).

Some Graph invariants cannot be validated against ``respx`` fixtures because they
depend on service-imposed behaviour the mock does not reproduce (spec 044
§ Integration-only): the device-code handshake (GR-007), real 320 KiB chunk
alignment (GR-020), genuine async copy monitor polling (GR-026), authentic
``Retry-After`` throttling (GR-034), and ``507`` quota exhaustion (GR-054). This
module carries those plus the RFC-0010 10 MiB upload-session + range-read
round-trip. The respx unit suites already cover the request/response *mapping*
for every one of these IDs; here they run against a real tenant.

Gating (mirrors ``tests/backends/azure/aio/test_live_hns.py``)
--------------------------------------------------------------
Two skip-gates, both required to run:

1. ``pytest.mark.live`` at module level. Default ``addopts`` is ``-m 'not live'``,
   so plain ``hatch run test`` deselects this file entirely — it skips cleanly
   without the gate. ``pytest.mark.integration`` is the spec-named marker
   (spec 044) and groups it as external-service.
2. ``RS_TEST_LIVE_GRAPH=1`` env var — the same opt-in the ``graph_live``
   conformance fixture uses.

Fixture-time precondition (fails loudly, does not skip): the three ``GRAPH_*``
credential vars must be present once the opt-in is set —
``require_graph_live_credentials`` calls ``pytest.fail`` (not skip) for a missing
var, because a silent skip here would read as "tested" when it was not.

The live tier is **device-code / consumer** (M365 Family tenant, no app-only
auth): first sign-in is interactive; the MSAL token cache the first run writes
makes subsequent runs non-interactive (see ``graph_live`` fixture docstring).
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("httpx", reason="httpx not installed (graph extra)")
pytest.importorskip("msal", reason="msal not installed (graph extra)")

from remote_store.aio.backends._graph import GraphAuth, GraphBackend  # noqa: E402
from tests.backends.fixtures._live_env import require_graph_live_credentials  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RS_TEST_LIVE_GRAPH") != "1",
        reason="graph integration suite is opt-in via RS_TEST_LIVE_GRAPH=1",
    ),
]

# Consumer/personal accounts consent to the delegated Files.ReadWrite scope, not
# the work/school .All variants (matches the graph_live fixture).
_LIVE_SCOPES = ["Files.ReadWrite", "User.Read"]

# 320 KiB is Graph's documented upload-session alignment unit.
_CHUNK = 320 * 1024


@pytest.fixture
async def graph_backend() -> AsyncIterator[GraphBackend]:
    """A live ``GraphBackend`` against the consumer device-code tenant.

    Builds the backend directly (rather than via the conformance registry) so the
    integration assertions own their backend lifecycle. Credentials are validated
    fail-loud once the opt-in flag is set.
    """
    creds = require_graph_live_credentials()
    auth = GraphAuth(creds["GRAPH_TENANT_ID"], creds["GRAPH_CLIENT_ID"], scopes=_LIVE_SCOPES)
    backend = GraphBackend(creds["GRAPH_DRIVE_ID"], token_provider=auth)
    try:
        yield backend
    finally:
        await backend.aclose()


@pytest.fixture
def scratch_prefix() -> str:
    """A uuid-suffixed scratch directory so concurrent / repeated runs cannot collide."""
    return f"rs-integration/{uuid.uuid4().hex[:8]}"


async def _cleanup(backend: GraphBackend, prefix: str) -> None:
    """Best-effort delete of the scratch prefix; a teardown race must not fail a green test."""
    import contextlib  # noqa: PLC0415

    with contextlib.suppress(Exception):
        await backend.delete_folder(prefix, recursive=True)


@pytest.mark.spec("GR-007")
async def test_device_code_flow_round_trip(graph_backend: GraphBackend, scratch_prefix: str) -> None:
    # GR-007: the device-code handshake cannot be mocked at the protocol layer.
    # A successful authenticated write+read proves a token was acquired via the
    # delegated device-code flow (the MSAL cache makes this non-interactive after
    # the first sign-in).
    path = f"{scratch_prefix}/hello.txt"
    payload = b"device-code round trip"
    try:
        await graph_backend.write(path, payload)
        assert await graph_backend.read_bytes(path) == payload
    finally:
        await _cleanup(graph_backend, scratch_prefix)


@pytest.mark.spec("GR-020")
async def test_real_chunk_alignment_multichunk_upload(graph_backend: GraphBackend, scratch_prefix: str) -> None:
    # GR-020: respx accepts any Content-Range; only Graph enforces the 320 KiB
    # alignment rule. A multi-chunk upload that round-trips byte-for-byte proves
    # the backend's chunk math is service-acceptable.
    graph_backend._upload_chunk_size = _CHUNK  # force a 320 KiB-aligned multi-chunk path
    path = f"{scratch_prefix}/aligned.bin"
    payload = bytes((i % 251) for i in range(_CHUNK * 2 + 7))  # 2 full chunks + a trailing partial
    try:
        await graph_backend.write(path, payload)
        assert await graph_backend.read_bytes(path) == payload
    finally:
        await _cleanup(graph_backend, scratch_prefix)


@pytest.mark.spec("GR-026")
async def test_copy_monitor_poll_to_completion(graph_backend: GraphBackend, scratch_prefix: str) -> None:
    # GR-026: a real POST copy returns 202 + a genuine cross-host monitor URL;
    # the poller must drive it to completion (the unit suite mocks the monitor).
    src = f"{scratch_prefix}/src.txt"
    dst = f"{scratch_prefix}/dst.txt"
    payload = b"copy via monitor"
    try:
        await graph_backend.write(src, payload)
        await graph_backend.copy(src, dst)
        assert await graph_backend.read_bytes(dst) == payload
    finally:
        await _cleanup(graph_backend, scratch_prefix)


@pytest.mark.spec("GR-034")
async def test_sustained_load_throttle_is_transparently_retried(
    graph_backend: GraphBackend, scratch_prefix: str
) -> None:
    # GR-034: real tenant throttling returns 429 with an authentic Retry-After
    # under sustained load. The backend's in-loop Retry-After handling makes
    # throttling transparent — a burst of metadata reads must all succeed even if
    # some are throttled mid-flight. (If the tenant never throttles, the ops still
    # succeed; the value is exercising the real Retry-After path when it does.)
    path = f"{scratch_prefix}/throttle.txt"
    try:
        await graph_backend.write(path, b"x")
        for _ in range(40):
            assert await graph_backend.is_file(path)
    finally:
        await _cleanup(graph_backend, scratch_prefix)


@pytest.mark.spec("GR-054")
async def test_quota_exhaustion_maps_insufficient_storage(graph_backend: GraphBackend) -> None:
    # GR-054: 507 insufficientStorage / quotaLimitReached can only be elicited
    # against a drive that is actually at quota — respx asserts the mapping
    # (test_http_mapping.py / test_write.py) but cannot reproduce the condition.
    # Provoking it would require filling the live drive, so this invariant needs a
    # drive provisioned at quota; gated behind a dedicated opt-in to avoid
    # destructive disk-filling on an ordinary test drive.
    if os.environ.get("RS_TEST_LIVE_GRAPH_QUOTA") != "1":
        pytest.skip("GR-054 needs a drive at quota; opt-in via RS_TEST_LIVE_GRAPH_QUOTA=1")
    from remote_store._errors import BackendUnavailable  # noqa: PLC0415

    # 507 insufficientStorage / quotaLimitReached both map to BackendUnavailable
    # (classify_graph_error, http.py); see test_http_mapping.py GR-054 unit tests.
    with pytest.raises(BackendUnavailable):
        await graph_backend.write("rs-integration/over-quota.bin", b"0" * (1024 * 1024))


@pytest.mark.spec("GR-019")
async def test_large_round_trip_10mib(graph_backend: GraphBackend, scratch_prefix: str) -> None:
    # RFC-0010 test plan: a 10 MiB upload-session write + full read-back validates
    # byte-equality across the large-file path against the real service.
    path = f"{scratch_prefix}/large.bin"
    payload = bytes((i % 251) for i in range(10 * 1024 * 1024))
    try:
        await graph_backend.write(path, payload)
        assert await graph_backend.read_bytes(path) == payload
    finally:
        await _cleanup(graph_backend, scratch_prefix)
