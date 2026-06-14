"""GraphBackend concurrency — create-once-race contract + live race probes (BK-289).

The Graph slice of the BK-289 concurrency lane. It lives in the Graph backend
home (not the cross-backend ``conformance/`` lane) because it constructs a
concrete ``GraphBackend`` with mocked transport — backend-specific, per TEST-003
— whereas the registry-parametrised cross-backend invariants live in
``tests/backends/conformance/test_concurrency.py`` (+ its ``aio/`` sibling).

Two tiers:

* **Tier 1 (CI, deterministic, respx):** the ``overwrite=False`` server-atomic
  create-if-absent contract (GR-018 / GR-059) and the
  version-pinned concurrent-read invariant. Cassette replay is **not** used —
  vcrpy matches sequentially, so it cannot model a concurrent race (research
  §4.2); respx returns canned responses per request instead.
* **Tier 3 (live, gated by ``RS_TEST_LIVE_GRAPH``):** real concurrent
  create/overwrite/move/copy, N-parallel large uploads, and token-call counting
  against a throwaway OneDrive — the only place server-side atomicity is *proven*
  rather than mocked (research §6 #3).

Cross-references (consolidated, not duplicated):

* **BUG-219 ``aclose`` no-raise / no-warning, close-terminal posture** —
  ``test_write.py::TestUseAfterClose`` (idempotent aclose, concurrent ops after
  aclose all surface typed ``BackendUnavailable``). Carries GR-051 and GR-059.
* **Bridge deadlock-freedom** — ``tests/aio/test_async_to_sync_adapter.py::
  TestConcurrency`` (ASYNC-089): N=32 concurrent sync callers funnel onto the
  adapter's single private loop, deadlock-free. That is the GR-059
  "bridged sync path is safe" guarantee, exercised generically.

Mock-fidelity note (research §6 #3): the respx create-once-race guards the
**409 → ``AlreadyExists`` mapping** and the contract *shape* (exactly one
winner). They do not *prove* Graph's server-side atomicity — that is the Tier-3
live probe's job. The mock simulates the server (201 once, then 409).
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid

import httpx
import pytest
import respx

from remote_store._errors import AlreadyExists
from remote_store._models import WriteResult

pytest.importorskip("httpx", reason="httpx not installed (graph extra)")

from remote_store.aio.backends._graph.backend import GraphBackend  # noqa: E402

_DRIVE = "b!driveid123"
_DOWNLOAD = "https://download.example.test/blob"

# Whole-URL regex routes (write composes a conflictBehavior query onto the
# content URL; the metadata GET addresses ``…/root:/<path>:``).
_CONTENT_RE = re.compile(r"https://graph\.microsoft\.com/v1\.0/drives/.+:/content(\?.*)?$")
_META_RE = re.compile(r".*/root:/.+:$")

# One loop, modest coroutine fan-out (research §4.3).
_N = 12


def _make() -> GraphBackend:
    return GraphBackend(_DRIVE, token_provider=lambda: "tok")


def _drive_item(name: str = "race.txt") -> dict[str, object]:
    return {
        "id": "01ABCDEF",
        "name": name,
        "size": 1,
        "eTag": '"{E1},1"',
        "lastModifiedDateTime": "2024-01-15T10:30:00Z",
        "file": {"mimeType": "text/plain"},
    }


def _file_item(name: str = "a.txt", content_len: int = 11) -> dict[str, object]:
    return {
        "name": name,
        "size": content_len,
        "lastModifiedDateTime": "2024-01-15T10:30:00Z",
        "eTag": '"{AB12CD34},2"',
        "file": {"mimeType": "text/plain"},
        "@microsoft.graph.downloadUrl": _DOWNLOAD,
    }


@pytest.mark.concurrency
@pytest.mark.spec("GR-059")
class TestCreateOnceRace:
    """GR-018 / GR-059 — ``overwrite=False`` is a server-side atomic create-if-absent.

    Graph sets ``@microsoft.graph.conflictBehavior=fail`` on the content PUT, so
    two racing creators cannot both succeed: the server returns 201 to one and
    409 ``nameAlreadyExists`` to the rest, which the backend maps to
    ``AlreadyExists``. These guards assert that mapping and the exactly-one-winner
    *shape*; server-side atomicity itself is proven by the Tier-3 live probe.
    """

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_create_once_race_yields_exactly_one_winner(self) -> None:
        # respx simulates the server's atomic create: the first PUT to reach the
        # responder wins (201), every later one loses (409). Single-loop asyncio
        # makes the state mutation race-free, so the outcome is deterministic.
        state = {"created": False}

        def _responder(request: httpx.Request) -> httpx.Response:
            if state["created"]:
                return httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}})
            state["created"] = True
            return httpx.Response(201, json=_drive_item())

        respx.put(_CONTENT_RE).mock(side_effect=_responder)
        async with _make() as backend:
            results = await asyncio.gather(
                *(backend.write("race.txt", b"x", overwrite=False) for _ in range(_N)),
                return_exceptions=True,
            )
        winners = [r for r in results if isinstance(r, WriteResult)]
        losers = [r for r in results if isinstance(r, AlreadyExists)]
        assert len(winners) == 1, results
        assert len(losers) == _N - 1, results
        # No third outcome: every coroutine resolved to one winner or a typed loser.
        assert len(winners) + len(losers) == _N

    @respx.mock
    @pytest.mark.spec("GR-018")
    async def test_concurrent_create_on_existing_all_already_exists(self) -> None:
        # The key already exists: every concurrent overwrite=False create loses
        # typed. Pins the 409 -> AlreadyExists mapping under concurrent load.
        respx.put(_CONTENT_RE).mock(return_value=httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}}))
        async with _make() as backend:
            results = await asyncio.gather(
                *(backend.write("exists.txt", b"x", overwrite=False) for _ in range(_N)),
                return_exceptions=True,
            )
        assert all(isinstance(r, AlreadyExists) for r in results), results


@pytest.mark.concurrency
class TestConcurrentReads:
    """GR-012 — concurrent reads on one instance are version-pinned and consistent.

    The read path resolves a per-request pre-signed ``@microsoft.graph.downloadUrl``;
    concurrent reads of one key each stream the same pinned bytes. This is the
    deterministic, in-process half of the stream-vs-mutate story — the eTag /
    delete error-fidelity branches are exercised by the read/error suites in
    ``test_read.py`` / ``test_transfer.py`` and proven against a live racer by the
    Tier-3 probe.
    """

    @respx.mock
    @pytest.mark.spec("GR-012")
    async def test_concurrent_reads_return_consistent_content(self) -> None:
        respx.get(url__regex=_META_RE.pattern).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DOWNLOAD).mock(return_value=httpx.Response(200, content=b"hello world"))
        async with _make() as backend:
            results = await asyncio.gather(*(backend.read_bytes("a.txt") for _ in range(_N)))
        assert all(r == b"hello world" for r in results)


# ---------------------------------------------------------------------------
# Tier 3 — live race probes (opt-in: RS_TEST_LIVE_GRAPH=1, real OneDrive)
# ---------------------------------------------------------------------------


class _CountingProvider:
    """Wraps a token provider and counts acquisitions (token-call probe)."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self._inner()  # type: ignore[operator]


@pytest.mark.live
@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.skipif(
    os.environ.get("RS_TEST_LIVE_GRAPH") != "1",
    reason="Graph live race probes are opt-in via RS_TEST_LIVE_GRAPH=1",
)
class TestGraphConcurrencyLive:
    """Real concurrent operations against a throwaway OneDrive (GR-059).

    The only place Graph's server-side atomicity is *proven* rather than mocked.
    Every assertion is still an invariant — exactly one create winner, no torn
    large upload, a token was acquired — never a timing or interleaving claim.
    """

    _LIVE_SCOPES = ["Files.ReadWrite", "User.Read"]
    _LARGE = 5 * 1024 * 1024  # > the 4 MiB createUploadSession boundary (GR-018)

    @pytest.fixture
    def live_creds(self) -> dict[str, str]:
        from tests.backends.fixtures._live_env import require_graph_live_credentials

        return require_graph_live_credentials()

    @pytest.fixture
    def scratch(self) -> str:
        return f"rs-bk289/{uuid.uuid4().hex[:8]}"

    async def _backend(self, creds: dict[str, str], provider: object | None = None) -> GraphBackend:
        from remote_store.aio.backends._graph import GraphAuth

        auth = provider or GraphAuth(creds["GRAPH_TENANT_ID"], creds["GRAPH_CLIENT_ID"], scopes=self._LIVE_SCOPES)
        return GraphBackend(creds["GRAPH_DRIVE_ID"], token_provider=auth)

    async def test_live_create_once_race_one_winner(self, live_creds: dict[str, str], scratch: str) -> None:
        backend = await self._backend(live_creds)
        key = f"{scratch}/create-once.txt"
        try:
            results = await asyncio.gather(
                *(backend.write(key, b"payload", overwrite=False) for _ in range(8)),
                return_exceptions=True,
            )
            winners = [r for r in results if isinstance(r, WriteResult)]
            losers = [r for r in results if isinstance(r, AlreadyExists)]
            assert len(winners) == 1, results
            assert len(losers) == len(results) - 1, results
            assert await backend.read_bytes(key) == b"payload"
        finally:
            import contextlib

            with contextlib.suppress(Exception):
                await backend.delete_folder(scratch, recursive=True)
            await backend.aclose()

    async def test_live_n_parallel_large_uploads(self, live_creds: dict[str, str], scratch: str) -> None:
        backend = await self._backend(live_creds)
        payload = bytes((i % 251) for i in range(self._LARGE))
        keys = [f"{scratch}/large-{i}.bin" for i in range(4)]
        try:
            await asyncio.gather(*(backend.write(key, payload) for key in keys))
            for key in keys:
                info = await backend.get_file_info(key)
                assert info.size == self._LARGE
        finally:
            import contextlib

            with contextlib.suppress(Exception):
                await backend.delete_folder(scratch, recursive=True)
            await backend.aclose()

    async def test_live_concurrent_ops_acquire_tokens(self, live_creds: dict[str, str], scratch: str) -> None:
        from remote_store.aio.backends._graph import GraphAuth

        inner = GraphAuth(live_creds["GRAPH_TENANT_ID"], live_creds["GRAPH_CLIENT_ID"], scopes=self._LIVE_SCOPES)
        provider = _CountingProvider(inner)
        backend = await self._backend(live_creds, provider=provider)
        n_ops = 8
        try:
            await asyncio.gather(*(backend.write(f"{scratch}/tok-{i}.txt", b"x") for i in range(n_ops)))
            # BK-292 probe. Today each op acquires a token independently
            # (live-confirmed ~1 call/op), so N concurrent writes make >= N
            # acquisitions. This is deliberately tight: when BK-292's async-auth
            # single-flight / in-flight refresh dedup lands, the count drops below
            # N and this assertion breaks *by design* — the signal that the dedup
            # took effect (at which point this probe is updated alongside it).
            assert provider.calls >= n_ops
        finally:
            import contextlib

            with contextlib.suppress(Exception):
                await backend.delete_folder(scratch, recursive=True)
            await backend.aclose()
