"""Posture-gated close conformance lane — async (BK-298 / M1).

The async axis of the sync ``test_close_posture.py`` lane. Terminal async
backends (async Azure, Graph) raise ``BackendUnavailable`` on a use-after-close;
reusable backends (async Memory, async Local) re-initialise on demand. The
terminal guard short-circuits before any network or cassette access, so the
assertion is tier-safe.

The ``async_backend`` fixture is auto-parametrised over every async fixture by
``conftest.pytest_generate_tests``. Its teardown awaits ``aclose`` best-effort
(idempotent) and runs ``cleanup`` separately, so pre-closing here is safe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import BackendUnavailable
from tests.backends.conformance._helpers import _require

if TYPE_CHECKING:
    from remote_store.aio._async_backend import AsyncBackend

_PROBE = "bk298-close-posture-probe.txt"


@pytest.mark.spec("BE-020")
async def test_close_posture(async_backend: AsyncBackend) -> None:
    """An async backend honours its declared ``close_is_terminal`` posture after aclose()."""
    await async_backend.aclose()
    if async_backend.close_is_terminal:
        with pytest.raises(BackendUnavailable, match="is closed"):
            await async_backend.exists(_PROBE)
    else:
        # Reusable: the op re-initialises rather than terminally refusing; it
        # must not raise the terminal "<name> backend is closed" guard.
        error: BackendUnavailable | None = None
        try:
            assert await async_backend.exists(_PROBE) is False
        except BackendUnavailable as exc:  # pragma: no cover -- defensive parity with sync lane
            error = exc
        assert error is None or "is closed" not in str(error)


@pytest.mark.spec("BE-020")
@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
async def test_close_posture_outranks_root_rejection(async_backend: AsyncBackend, root: str) -> None:
    """A closed async backend refuses before it classifies the path type.

    Async twin of the sync cell of the same name (BE-020 outranks BE-029).
    Both terminal async backends carry that ordering and neither was pinned
    before this cell: ``AsyncAzureBackend`` runs ``_raise_if_closed()`` ahead
    of the root pre-check inside ``_reject_root_as_file``, and ``GraphBackend``
    reaches its closed guard through the lazy ``_client`` property before any
    root verdict exists.

    The plain-path sibling above does not reach this: ``exists()`` carries no
    root pre-check, so the ordering only shows on a file-shaped op.

    Where the terminal branch actually runs: no Stage-1 async fixture
    *executes* it. ``azure_replay_async`` and ``graph_replay`` are both Stage 1
    and terminal, but this cell is a new test name and no cassette has been
    recorded under it, so the missing-cassette hook skips them at collection —
    even though the terminal guard short-circuits before any request and the
    cassette would be empty. The four Stage-1 fixtures that do run
    (``memory_async_native``, ``memory_async_adapted``, ``local_async_adapted``,
    ``dafny_oracle_async``) are all reusable, so Stage 1 exercises the reusable
    branch only. ``azurite_async`` (Stage 2, the CI Docker lane) is the fixture
    that executes the terminal branch.
    """
    _require(async_backend, Capability.READ)
    await async_backend.aclose()
    if async_backend.close_is_terminal:
        with pytest.raises(BackendUnavailable, match="is closed"):
            await async_backend.read_bytes(root)
    else:
        # Reusable: whatever it answers, it must not be the terminal guard.
        error: Exception | None = None
        try:
            await async_backend.read_bytes(root)
        except Exception as exc:  # noqa: BLE001 -- any typed error is acceptable here
            error = exc
        assert "is closed" not in str(error)
