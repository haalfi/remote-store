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

from remote_store._errors import BackendUnavailable

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
