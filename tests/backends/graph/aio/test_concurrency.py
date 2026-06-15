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
from typing import Any

import httpx
import pytest
import respx

from remote_store._errors import AlreadyExists, InvalidPath
from remote_store._models import WriteResult

pytest.importorskip("httpx", reason="httpx not installed (graph extra)")

from remote_store.aio.backends._graph import backend as graph_backend  # noqa: E402
from remote_store.aio.backends._graph.auth import GraphAuth  # noqa: E402
from remote_store.aio.backends._graph.backend import (  # noqa: E402
    _REPLACE_RACE_MAX_ATTEMPTS,
    GraphBackend,
)

_DRIVE = "b!driveid123"
_DOWNLOAD = "https://download.example.test/blob"
_UPLOAD_URL = "https://up.example.test/session/abc?tempauth=secret"

# Whole-URL regex routes (write composes a conflictBehavior query onto the
# content URL; the metadata GET addresses ``…/root:/<path>:``).
_CONTENT_RE = re.compile(r"https://graph\.microsoft\.com/v1\.0/drives/.+:/content(\?.*)?$")
_SESSION_RE = re.compile(r"https://graph\.microsoft\.com/v1\.0/drives/.+:/createUploadSession$")
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
@pytest.mark.spec("GR-018")
class TestOverwriteReplaceRetry:
    """GR-018 / GR-032 — ``overwrite=True`` retries a create-race ``409``.

    ``overwrite=True`` (``conflictBehavior=replace``) is meant to overwrite, but a
    concurrent create of the same new key can land a loser's ``replace`` mid-create
    and draw ``409 nameAlreadyExists`` (live-reproduced on consumer OneDrive). The
    winner's create has committed by then, so the backend re-issues the ``replace``
    a bounded number of times and wins. These respx guards pin the mechanism
    deterministically; the Tier-3 live probe proves it against real Graph.

    The retry is deliberately narrow: gated on ``overwrite=True`` (so the
    ``overwrite=False`` single-winner outcome is preserved), and only the plain
    ``AlreadyExists`` discrimination is retried — a folder-target / file-ancestor
    ``409`` (``InvalidPath``) and a terminal SharePoint replace-rejection are not
    papered over.
    """

    @respx.mock
    async def test_overwrite_create_race_retries_then_wins(self) -> None:
        # First replace lands mid-create (409); the winner's create has committed
        # by the re-attempt, so the second replace overwrites it (200).
        calls = {"n": 0}

        def _responder(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}})
            return httpx.Response(200, json=_drive_item())

        respx.put(_CONTENT_RE).mock(side_effect=_responder)
        async with _make() as backend:
            result = await backend.write("race.txt", b"x", overwrite=True)
        assert isinstance(result, WriteResult)
        assert calls["n"] == 2  # one re-attempt was enough

    @respx.mock
    async def test_overwrite_create_race_reissues_full_body(self) -> None:
        # Guards the load-bearing reader.seek(0) rewind: on the small-file path the
        # PUT carries the body *and* draws the 409 in one request, so the reader is
        # consumed before the conflict. Without the rewind the re-issued PUT would
        # read from EOF and upload b"". Capture every PUT body and assert the second
        # (post-retry) request carried the full original content, not a truncated one.
        bodies: list[bytes] = []

        def _responder(request: httpx.Request) -> httpx.Response:
            bodies.append(request.content)
            if len(bodies) == 1:
                return httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}})
            return httpx.Response(200, json=_drive_item())

        respx.put(_CONTENT_RE).mock(side_effect=_responder)
        async with _make() as backend:
            await backend.write("race.txt", b"hello-bytes", overwrite=True)
        assert bodies == [b"hello-bytes", b"hello-bytes"]  # rewound, not truncated to b""

    @respx.mock
    async def test_overwrite_create_race_retries_upload_session_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Branch coverage for the >4 MiB dispatch path. Shrink the small-file
        # boundary so a tiny body takes the upload-session path; createUploadSession
        # 409s once (create race -> AlreadyExists), then the re-attempt opens a fresh
        # session and the chunk PUT carries the full body. This proves the retry loop
        # re-enters and re-opens the session for the large-file branch. (Unlike the
        # small-file path, the create-race 409 here fires at createUploadSession — a
        # POST with no body — before any reader.read(), so the reader is still at 0
        # and the seek(0) rewind is a no-op on this path; the rewind guard lives in
        # test_overwrite_create_race_reissues_full_body, which the small-file PUT
        # exercises because it consumes the reader before drawing the 409.)
        monkeypatch.setattr(graph_backend, "_SMALL_FILE_MAX_SIZE", 4)
        sessions = {"n": 0}

        def _session_responder(request: httpx.Request) -> httpx.Response:
            sessions["n"] += 1
            if sessions["n"] == 1:
                return httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}})
            return httpx.Response(200, json={"uploadUrl": _UPLOAD_URL})

        respx.post(_SESSION_RE).mock(side_effect=_session_responder)
        chunks = respx.put(_UPLOAD_URL).mock(return_value=httpx.Response(201, json=_drive_item()))
        async with _make() as backend:
            backend._upload_chunk_size = 320 * 1024  # single chunk for the 6-byte body
            result = await backend.write("race.bin", b"abcdef", overwrite=True)
        assert isinstance(result, WriteResult)
        assert sessions["n"] == 2  # createUploadSession retried after the create-race 409
        assert b"".join(c.request.content for c in chunks.calls) == b"abcdef"

    @respx.mock
    async def test_overwrite_persistent_409_exhausts_to_already_exists(self) -> None:
        # A terminal conflict (e.g. a SharePoint replace-rejection) keeps 409-ing;
        # the bounded budget is spent and AlreadyExists surfaces unchanged. The
        # retry re-issued the replace each time — it never swallowed the conflict.
        route = respx.put(_CONTENT_RE).mock(
            return_value=httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}})
        )
        async with _make() as backend:
            with pytest.raises(AlreadyExists, match="race.txt"):
                await backend.write("race.txt", b"x", overwrite=True)
        assert route.call_count == _REPLACE_RACE_MAX_ATTEMPTS  # initial + bounded re-attempts

    @respx.mock
    async def test_overwrite_false_does_not_retry(self) -> None:
        # overwrite=False's create-once-race AlreadyExists is the correct
        # single-winner outcome (GR-059); it must surface on the first 409.
        route = respx.put(_CONTENT_RE).mock(
            return_value=httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}})
        )
        async with _make() as backend:
            with pytest.raises(AlreadyExists):
                await backend.write("exists.txt", b"x", overwrite=False)
        assert route.call_count == 1  # no re-attempt

    @respx.mock
    async def test_overwrite_file_ancestor_409_not_retried(self) -> None:
        # A file-ancestor 409 discriminates to InvalidPath (ID-209), which is
        # structural — it propagates on the first attempt, never retried.
        route = respx.put(_CONTENT_RE).mock(
            return_value=httpx.Response(
                409,
                json={"error": {"code": "nameAlreadyExists", "details": [{"name": "parent", "file": {}}]}},
            )
        )
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="ancestor"):
                await backend.write("parent/child.txt", b"x", overwrite=True)
        assert route.call_count == 1  # no re-attempt


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


class _CountingGraphAuth(GraphAuth):
    """A ``GraphAuth`` whose MSAL acquisition is faked and counted (no network).

    Overrides ``get_token`` so the inherited ``aget_token`` / single-flight wraps
    a deterministic stand-in; ``calls`` counts the underlying acquisitions that
    single-flight is meant to collapse.
    """

    def __init__(self) -> None:
        super().__init__("t", "c", client_secret="s")
        self.calls = 0

    def get_token(self) -> str:
        self.calls += 1
        return "tok"


@pytest.mark.concurrency
class TestAsyncTokenProvider:
    """GR-008 — the async ``GraphAuth.aget_token`` provider drives a real request.

    Proves the backend awaits the ``Callable[[], Awaitable[str]]`` shape and that
    N concurrent ops sharing one provider never acquire *more* than once per op
    (single-flight can only collapse, never multiply). The exactly-one-acquisition
    dedup is proven deterministically in ``test_auth.py::TestAsyncAcquisition``.
    """

    @respx.mock
    @pytest.mark.spec("GR-008")
    async def test_async_provider_request_path(self) -> None:
        respx.get(url__regex=_META_RE.pattern).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DOWNLOAD).mock(return_value=httpx.Response(200, content=b"hello world"))
        auth = _CountingGraphAuth()
        async with GraphBackend(_DRIVE, token_provider=auth.aget_token) as backend:
            assert await backend.read_bytes("a.txt") == b"hello world"
        assert auth.calls >= 1  # the async provider was invoked and awaited

    @respx.mock
    @pytest.mark.spec("GR-008")
    async def test_concurrent_ops_do_not_multiply_acquisitions(self) -> None:
        respx.get(url__regex=_META_RE.pattern).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.get(_DOWNLOAD).mock(return_value=httpx.Response(200, content=b"hello world"))
        auth = _CountingGraphAuth()
        async with GraphBackend(_DRIVE, token_provider=auth.aget_token) as backend:
            results = await asyncio.gather(*(backend.read_bytes("a.txt") for _ in range(_N)))
        assert all(r == b"hello world" for r in results)
        # Single-flight: at most one acquisition per op, never the N-multiplied
        # stampede a naive async provider would cause.
        assert 1 <= auth.calls <= _N


# ---------------------------------------------------------------------------
# Tier 3 — live race probes (opt-in: RS_TEST_LIVE_GRAPH=1, real OneDrive)
# ---------------------------------------------------------------------------


class _LiveCountingGraphAuth(GraphAuth):
    """Real-MSAL ``GraphAuth`` that counts underlying acquisitions (live probe).

    Unlike the Tier-1 ``_CountingGraphAuth``, ``get_token`` calls through to the
    real MSAL acquisition — the single-flight wrapper (``aget_token``) is what is
    under test, and ``calls`` counts the acquisitions it collapses.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.calls = 0

    def get_token(self) -> str:
        self.calls += 1
        return super().get_token()


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

    async def test_live_overwrite_create_race_all_succeed(self, live_creds: dict[str, str], scratch: str) -> None:
        # BK-294: N concurrent overwrite=True writes to the SAME new key. With the
        # create-race retry, every loser re-issues its replace and wins (last-
        # writer-wins) — so none should surface AlreadyExists, and the surviving
        # content must be one of the payloads written intact (no tearing).
        backend = await self._backend(live_creds)
        key = f"{scratch}/overwrite-race.txt"
        payloads = [f"writer-{i}".encode() for i in range(8)]
        try:
            results = await asyncio.gather(
                *(backend.write(key, p, overwrite=True) for p in payloads),
                return_exceptions=True,
            )
            assert all(isinstance(r, WriteResult) for r in results), results
            assert await backend.read_bytes(key) in payloads
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

    async def test_live_concurrent_ops_single_flight_acquire_tokens(
        self, live_creds: dict[str, str], scratch: str
    ) -> None:
        auth = _LiveCountingGraphAuth(
            live_creds["GRAPH_TENANT_ID"], live_creds["GRAPH_CLIENT_ID"], scopes=self._LIVE_SCOPES
        )
        # The async single-flight provider (aget_token), not the sync instance:
        # this is the BK-292 path under probe.
        backend = await self._backend(live_creds, provider=auth.aget_token)
        n_ops = 8
        try:
            await asyncio.gather(*(backend.write(f"{scratch}/tok-{i}.txt", b"x") for i in range(n_ops)))
            # BK-292: the async single-flight collapses concurrent acquisitions.
            # The live invariant is the dedup *direction* — never more than one
            # acquisition per op, and at least one — not a precise count (live
            # token warmth and interleaving vary; fully-overlapping cold callers
            # collapse to one). The deterministic exactly-one dedup is proven in
            # tests/backends/graph/aio/test_auth.py::TestAsyncAcquisition.
            assert 1 <= auth.calls <= n_ops
        finally:
            import contextlib

            with contextlib.suppress(Exception):
                await backend.delete_folder(scratch, recursive=True)
            await backend.aclose()
