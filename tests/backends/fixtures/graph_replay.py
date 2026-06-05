"""``graph_replay`` fixture: ``GraphBackend`` replaying from a committed cassette.

Stage 1, kind=replay, async. Exercises the real ``GraphBackend`` code path and
the ``httpx`` transport against recorded cassette files (no network). The
token-provider is a constant stub — the bearer token is scrubbed out of every
cassette at record time, so replay never needs a real one.

vcrpy 8.1.1 records and replays ``httpx.AsyncClient.stream()`` with no transport
shim (proven by ``test_httpx_streaming_replay.py``), so — unlike the Azure async
replay fixture — no ``AsyncioRequestsTransport`` is injected.

Until GR-READ / GR-WRITE / GR-MUTATE record cassettes (and implement the
data-plane ops), the conformance suite's missing-cassette skip keeps every
graph_replay slice inert.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._cassettes import FAKE_DRIVE_ID
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_meta = load_fixture("graph_replay")


def _factory() -> AsyncBackend:
    try:
        from remote_store.aio.backends._graph import GraphBackend  # noqa: PLC0415
    except ImportError:
        pytest.skip("httpx not installed (graph extra)")

    return GraphBackend(FAKE_DRIVE_ID, token_provider=lambda: "graph-replay-token")


async def _aclose(backend: AsyncBackend) -> None:
    await backend.aclose()


def _capabilities() -> frozenset:
    try:
        from remote_store.aio.backends._graph import GraphBackend  # noqa: PLC0415
    except ImportError:
        return frozenset()
    return frozenset(GraphBackend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        aclose=_aclose,
        # record_mode="none" forces replay even when --record is active.
        marks=(pytest.mark.vcr(record_mode="none"),),
        **_meta.to_kwargs(),
    )
)
