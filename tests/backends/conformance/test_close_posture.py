"""Posture-gated close conformance lane — sync (BK-298 / M1).

The cross-backend home for the ``close_is_terminal`` contract (BE-020). Like the
concurrency lane it does **not** assert one uniform property: backends declare
their posture and the lane tests each against *its own* declaration.

* **Terminal** (``close_is_terminal=True``: Azure, S3, Graph) — a use-after-close
  raises ``BackendUnavailable``. The guard short-circuits before any network or
  cassette access, so this assertion is tier-safe: the replay fixtures execute it
  with no cassette recorded under its name (ID-241 made the missing-cassette skip
  fire on the unplayable request rather than the test name).
* **Reusable** (the default: Local, Memory, SFTP, HTTP, SQL) — an operation after
  ``close()`` re-initialises the client and must **not** raise the terminal
  ``BackendUnavailable("closed")``.

The ``backend`` fixture is auto-parametrised over every sync fixture by
``conftest.pytest_generate_tests``. Fixture cleanup re-closes idempotently or
uses a side client, so pre-closing the backend here is safe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import BackendUnavailable
from tests.backends.conformance._helpers import _require

if TYPE_CHECKING:
    from remote_store._backend import Backend

_PROBE = "bk298-close-posture-probe.txt"


@pytest.mark.spec("BE-020")
def test_close_posture(backend: Backend) -> None:
    """A backend honours its declared ``close_is_terminal`` posture after close()."""
    backend.close()
    if backend.close_is_terminal:
        with pytest.raises(BackendUnavailable, match="is closed"):
            backend.exists(_PROBE)
    else:
        # Reusable: the op re-initialises the client rather than terminally
        # refusing. It must not raise the terminal "<name> backend is closed"
        # guard. A re-init may still surface an unrelated, backend-specific
        # error (e.g. an in-memory SQLite engine whose state is gone) — that is
        # a re-init attempt, not a terminal refusal — so only the guard message
        # is forbidden here.
        error: BackendUnavailable | None = None
        try:
            assert backend.exists(_PROBE) is False
        except BackendUnavailable as exc:  # pragma: no cover -- only the in-memory SQL fixture
            error = exc
        assert error is None or "is closed" not in str(error)


@pytest.mark.spec("BE-020")
@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
def test_close_posture_outranks_root_rejection(backend: Backend, root: str) -> None:
    """A closed backend refuses before it classifies the path type.

    The root pre-check that BE-029 requires is a cheap string test, so it
    naturally wants to run first — and on a terminal backend that made
    ``read_bytes("")`` after ``close()`` answer ``InvalidPath`` instead of
    ``BackendUnavailable``. BE-020 states its guarantee without exception, so
    the closed check wins; otherwise the answer depends on which guard the
    implementer happened to write first, which is the undeclared-divergence
    shape this whole item exists to remove.

    The plain-path sibling above does not reach this: ``exists()`` carries no
    root pre-check, so the ordering only shows on a file-shaped op.
    """
    _require(backend, Capability.READ)
    backend.close()
    if backend.close_is_terminal:
        with pytest.raises(BackendUnavailable, match="is closed"):
            backend.read_bytes(root)
    else:
        # Reusable: whatever it answers, it must not be the terminal guard.
        error: Exception | None = None
        try:
            backend.read_bytes(root)
        except Exception as exc:  # noqa: BLE001 -- any typed error is acceptable here
            error = exc
        assert "is closed" not in str(error)
