"""Replay-backed execution of the published Graph example snippet (BK-283).

``examples/backends/graph_backend.py`` is the one published snippet with no
emulator path: ``tests/scripts/run_examples.py`` sweeps only the
credential-free example dirs (as subprocesses, which in-process vcrpy cannot
intercept), so the replayed variant lives here instead — the cassette
machinery's home. The division of labour stands: ``run_examples.py`` keeps
its credential-free subprocess sweep; this module owns the one example that
needs a cassette.

Placement and routing: this module sits under ``tests/backends/conformance/``
— not because it tests backend conformance, but because the conformance
conftest routes the entire cassette stack by the fixture-alias tokens in a
node's parametrize id. The param ids ``graph_live`` / ``graph_replay`` buy
cassette-dir routing, the shared cassette name
(``test_graph_backend_example[graph].yaml``), the ``GRAPH_PROFILE``
record/replay scrub configs, the missing-cassette skip, and the root
conftest's ``--record``-mode vcr marking — with zero conftest or
``record_cassettes.py`` changes. The recorder's ``-k graph_live`` sweep
records (and a full ``record-graph`` regenerates) the cassette alongside the
conformance corpus.

What this test guards: it is an executable-documentation guard for the
published snippet — imports resolve, the env gate works, the demonstrated
API usage still sequences, the printed output is what the docs show. It is
**not** the integration test for the ``Store → GraphBackend → API`` chain;
every layer is contract-covered elsewhere (Store→backend over the memory
backends, GraphBackend→API in the conformance suite). Assertions therefore
target the script's observable stdout, never backend semantics.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import runpy
from pathlib import Path

import pytest

from tests.backends.fixtures._cassettes_graph import FAKE_DRIVE_ID
from tests.backends.fixtures._live_env import require_graph_live_credentials

# Without the graph extra, ``remote_store.aio`` has no ``GraphAuth`` attribute
# to monkeypatch and the example's import raises — both params would hard-fail
# in an environment the conformance suite deliberately passes in. Mirrors the
# ImportError-to-skip conversion in the graph fixture factories.
pytest.importorskip("httpx", reason="httpx not installed (graph extra)")
pytest.importorskip("msal", reason="msal not installed (graph extra)")

EXAMPLE = Path(__file__).parents[3] / "examples" / "backends" / "graph_backend.py"

# The example's fixed Store root on the drive — a constant (unlike the
# per-test ``rs-conformance-<uuid>`` folders), so the scrub layer needs no
# new rules for it.
_EXAMPLE_ROOT = "remote-store-example"


class _StubGraphAuth:
    """Replay stand-in for ``GraphAuth``: constant token, no MSAL, no network.

    Accepts the example's constructor arguments and returns the same constant
    token the ``graph_replay`` fixture uses (the bearer token is scrubbed out
    of every cassette at record time, so replay never needs a real one).
    ``calls`` counts token fetches so a silent fall-through to real MSAL
    fails the test loudly instead of hanging on an interactive device-code
    prompt.
    """

    calls = 0

    def __init__(self, tenant_id: str, client_id: str, *, client_secret: str | None = None, **_: object) -> None:
        pass

    def __call__(self) -> str:
        type(self).calls += 1
        return "graph-replay-token"

    async def aget_token(self) -> str:
        # The example wires the backend with the async provider (auth.aget_token);
        # mirror the real GraphAuth, whose async path ultimately fetches the token.
        return self()


async def _purge_example_root() -> None:
    """Best-effort delete of the drive's example folder (live-run hygiene).

    The example cleans up its files but leaves empty folders behind;
    pre-cleaning keeps re-records deterministic and post-cleaning leaves the
    drive tidy. Mirrors ``graph_live._aclose``: an unrooted sibling backend
    deletes the folder, and a teardown race must never turn a green run red.
    During ``--record`` these requests land in the cassette too; replay never
    re-issues them (vcrpy does not require every interaction to be played).
    """
    from remote_store.aio import GraphAuth, GraphBackend  # noqa: PLC0415 -- import gated by the graph extra

    creds = require_graph_live_credentials()
    auth = GraphAuth(creds["GRAPH_TENANT_ID"], creds["GRAPH_CLIENT_ID"])
    cleaner = GraphBackend(creds["GRAPH_DRIVE_ID"], token_provider=auth)
    try:
        with contextlib.suppress(Exception):
            await cleaner.delete_folder(_EXAMPLE_ROOT, recursive=True, missing_ok=True)
    finally:
        await cleaner.aclose()


@pytest.mark.spec("TEST-007")
@pytest.mark.parametrize(
    "mode",
    [
        pytest.param("live", id="graph_live", marks=pytest.mark.live),
        pytest.param("replay", id="graph_replay", marks=pytest.mark.vcr(record_mode="none")),
    ],
)
def test_graph_backend_example(mode: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Run the published Graph example end to end and pin its printed output.

    ``runpy.run_path(..., run_name="__main__")`` executes the script exactly
    as a user does — module-level env gate, ``asyncio.run(main())``, and
    ``sys.exit`` paths included — which a plain import + ``await main()``
    would not.
    """
    if mode == "live":
        if os.environ.get("RS_TEST_LIVE_GRAPH") != "1":
            pytest.skip("graph_live opt-in via RS_TEST_LIVE_GRAPH=1")
        require_graph_live_credentials()  # real env vars stay in place
        asyncio.run(_purge_example_root())
    else:
        # The drive id must be FAKE_DRIVE_ID so the example skips the
        # aresolve_drive_id round trip (symmetric with recording, where the
        # real GRAPH_DRIVE_ID is set and the env-redact rewrites it to
        # FAKE_DRIVE_ID in every recorded URI). Tenant/client ids are inert:
        # the stub auth never contacts MSAL.
        monkeypatch.setenv("GRAPH_TENANT_ID", "consumers")
        monkeypatch.setenv("GRAPH_CLIENT_ID", "00000000-0000-0000-0000-000000000000")
        monkeypatch.setenv("GRAPH_DRIVE_ID", FAKE_DRIVE_ID)
        monkeypatch.delenv("GRAPH_CLIENT_SECRET", raising=False)
        monkeypatch.setattr("remote_store.aio.GraphAuth", _StubGraphAuth)
        monkeypatch.setattr(_StubGraphAuth, "calls", 0)

    try:
        runpy.run_path(str(EXAMPLE), run_name="__main__")
    finally:
        if mode == "live":
            asyncio.run(_purge_example_root())

    if mode == "replay":
        assert _StubGraphAuth.calls > 0, "stub token provider never called — the example fell through to real MSAL"

    out = capsys.readouterr().out
    assert "Wrote 2 files." in out
    assert "revenue,profit" in out  # demonstrated content, not just banners
    assert "Cleaned up all example files." in out
    assert "Done!" in out
