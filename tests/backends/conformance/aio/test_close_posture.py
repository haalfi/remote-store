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

    The plain-path sibling above does not reach this: it probes an ordinary key,
    so it meets no root pre-check at all. The probes have one of their own, and
    the cell at the end of this file covers that third path.

    Where the terminal branch actually runs: ``azure_replay_async`` and
    ``graph_replay``, both Stage 1 and terminal, execute it with no cassette at
    all — the terminal guard short-circuits before any request, so there is
    nothing to replay. They did not always: until ID-241 the missing-cassette
    skip fired on the test *name*, and this cell has no recording under its
    name, so both were skipped at collection over a request they never make.
    The four other Stage-1 fixtures (``memory_async_native``,
    ``memory_async_adapted``, ``local_async_adapted``, ``dafny_oracle_async``)
    are all reusable and exercise the other branch.
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


@pytest.mark.spec("BE-020")
@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
async def test_close_posture_outranks_root_write_rejection(async_backend: AsyncBackend, root: str) -> None:
    """Async twin of the sync cell of the same name, on the write path.

    Two terminal async backends carry a second root guard on ``write`` /
    ``write_atomic``, worded for a write rather than a wrong-typed read, and the
    read-shaped sibling above cannot reach either: ``read_bytes`` never touches a
    write guard, so the ordering was asserted in docstrings and pinned by
    nothing.

    Where the terminal branch runs, since the sibling above spends a paragraph
    on the same point for the same reason: ``azure_replay_async`` and
    ``graph_replay``. Both guards short-circuit before any request, so both
    execute with no cassette recorded — and since ID-241 the missing-cassette
    skip fires on the unplayable request rather than the test name, which is
    what lets a cassette-less cell run on a replay lane at all.

    **``graph_replay`` is the one that caught something.** ``GraphBackend``
    reaches its closed guard through the lazy ``_client`` property, and
    ``_require_writable_key`` ran *ahead* of the first touch of it, so a closed
    store answered "cannot write to the drive root" where BE-020 requires
    "backend is closed". This cell is the only conformance pin for the
    ``if self._closed:`` check that fixed it; delete that check and this is where
    it fails.
    """
    _require(async_backend, Capability.WRITE)
    await async_backend.aclose()
    if async_backend.close_is_terminal:
        with pytest.raises(BackendUnavailable, match="is closed"):
            await async_backend.write(root, b"x")
    else:
        error: Exception | None = None
        try:
            await async_backend.write(root, b"x")
        except Exception as exc:  # noqa: BLE001 -- any typed error is acceptable here
            error = exc
        assert "is closed" not in str(error)


# Every root-reaching read operation, enumerated rather than sampled. See the
# sync sibling for why the axis is parametrised: the operations were patched from
# a reading once and the next round found the one that reading missed.
_ROOT_PROBES = {
    "exists": lambda b, root: b.exists(root),
    "is_file": lambda b, root: b.is_file(root),
    "is_folder": lambda b, root: b.is_folder(root),
    "get_folder_info": lambda b, root: b.get_folder_info(root),
}


@pytest.mark.spec("BE-020")
@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
@pytest.mark.parametrize("op_name", sorted(_ROOT_PROBES))
async def test_close_posture_outranks_the_root_probes(
    async_backend: AsyncBackend,
    root: str,
    op_name: str,
) -> None:
    """Async twin of the sync cell of the same name: the probes' own root pre-check.

    See the sync sibling for why this third path needed a cell of its own — the
    two above drive ``read_bytes`` and ``write``, and neither a probe nor an
    aggregate is either. On this lane ``AsyncAzureBackend`` is the class that
    answered the root after ``aclose()``; it carries its own copy of every one of
    these bodies, so the sync fix does not reach it and a sync-only cell would
    not have caught it — which held for ``get_folder_info`` too, where the async
    twin had the same downgraded error class as the sync one.
    """
    _require(async_backend, Capability.LIST)
    await async_backend.aclose()
    if async_backend.close_is_terminal:
        with pytest.raises(BackendUnavailable, match="is closed"):
            await _ROOT_PROBES[op_name](async_backend, root)
    else:
        error: Exception | None = None
        try:
            await _ROOT_PROBES[op_name](async_backend, root)
        except Exception as exc:  # noqa: BLE001 -- any typed error is acceptable here
            error = exc
        assert "is closed" not in str(error)
