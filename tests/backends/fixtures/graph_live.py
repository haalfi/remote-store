"""``graph_live`` fixture: ``GraphBackend`` against a real Microsoft 365 drive.

Stage 3, real-live, async. Two-layer gate (``--stage=3`` plus
``RS_TEST_LIVE_GRAPH=1``) plus the device-code credential vars; skips cleanly
when either layer is missing.

The live tier is **device-code / consumer** (a personal Microsoft account), not
app-only — the M365 Family tenant has no application permissions. ``GraphAuth``
therefore runs the delegated device-code flow with consumer-compatible scopes
(``Files.ReadWrite`` + ``User.Read``). First sign-in is interactive; the MSAL
token cache it writes (under ``user_config_dir("remote-store")``) makes
subsequent runs non-interactive — the property a CI / recording run relies on.

``pytest.mark.vcr`` is added dynamically by the root
``conftest.pytest_collection_modifyitems`` when ``--record`` is active, so a
live run records cassettes for ``graph_replay`` to play back.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._cassettes import GRAPH_CONFORMANCE_BASE_PATH
from tests.backends.fixtures._live_env import require_graph_live_credentials
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_meta = load_fixture("graph_live")

# Consumer/personal accounts consent to the delegated Files.ReadWrite scope, not
# the work/school .All variants (see GraphAuth's device-code default).
_LIVE_SCOPES = ["Files.ReadWrite", "User.Read"]


def _factory() -> AsyncBackend:
    if os.environ.get("RS_TEST_LIVE_GRAPH") != "1":
        pytest.skip("graph_live opt-in via RS_TEST_LIVE_GRAPH=1")
    try:
        from remote_store.aio.backends._graph import GraphAuth, GraphBackend  # noqa: PLC0415
    except ImportError:
        pytest.skip("httpx / msal not installed (graph extra)")

    creds = require_graph_live_credentials()
    auth = GraphAuth(creds["GRAPH_TENANT_ID"], creds["GRAPH_CLIENT_ID"], scopes=_LIVE_SCOPES)
    # Per-test isolation via a fresh empty drive subfolder (GR-058 base_path) — the
    # Graph analogue of azure_live's fresh ``conformance-<uuid>`` filesystem. The
    # drive has one root with no container concept, so without scoping the suite's
    # fixed scratch paths would collide on overwrite=False seeds AND the real
    # OneDrive root content (e.g. the default "Getting started" PDF) would break the
    # empty-namespace assertions. A unique base_path gives every test a clean root.
    base_path = f"{GRAPH_CONFORMANCE_BASE_PATH}-{uuid.uuid4().hex[:8]}"
    backend = GraphBackend(creds["GRAPH_DRIVE_ID"], token_provider=auth, base_path=base_path)
    # Stash what _aclose needs to delete the scoped folder: the rooted backend
    # cannot address its own root's parent, so teardown uses an unrooted sibling.
    backend._conformance_teardown = (creds["GRAPH_DRIVE_ID"], auth, base_path)  # type: ignore[attr-defined]
    return backend


async def _aclose(backend: AsyncBackend) -> None:
    teardown = getattr(backend, "_conformance_teardown", None)
    try:
        await backend.aclose()
    finally:
        # Delete the per-test scoped folder via an unrooted sibling (reusing the
        # same auth). Best-effort: a teardown race must never turn a green test red.
        if teardown is not None:
            from remote_store.aio.backends._graph import GraphBackend  # noqa: PLC0415

            drive_id, auth, base_path = teardown
            cleaner = GraphBackend(drive_id, token_provider=auth)
            try:
                with contextlib.suppress(Exception):
                    await cleaner.delete_folder(base_path, recursive=True, missing_ok=True)
            finally:
                await cleaner.aclose()


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
        marks=(pytest.mark.live,),
        **_meta.to_kwargs(),
    )
)
