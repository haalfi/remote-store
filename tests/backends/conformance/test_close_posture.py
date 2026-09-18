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
from remote_store._errors import BackendUnavailable, InvalidPath
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

    The plain-path sibling above does not reach this: it probes an ordinary key,
    so it meets no root pre-check at all. The probes have one of their own, on
    every backend that decides the root from the key, and the cell below covers
    that third path.
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


@pytest.mark.spec("BE-020")
@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
def test_close_posture_outranks_root_write_rejection(backend: Backend, root: str) -> None:
    """The same ordering on the *write* path, which has its own root pre-check.

    The sibling above covers the read-shaped pre-check. A backend that writes to
    the root carries a second, differently-worded root guard, and it is added to
    each backend in the same place — ahead of the work, after the closed guard.
    "Ahead of the work" is the easy half to get right and "after the closed
    guard" is the half that silently depends on which line the implementer typed
    first, which is exactly what BE-020's paragraph says must not decide it.

    Nothing pinned that on this path: the ordering is asserted in five
    write-guard docstrings, covering six classes (``_s3_base`` serves both S3
    lanes), and the read-shaped cell above cannot reach any of them, because
    ``read_bytes`` never touches a write guard.
    """
    _require(backend, Capability.WRITE)
    backend.close()
    if backend.close_is_terminal:
        with pytest.raises(BackendUnavailable, match="is closed"):
            backend.write(root, b"x")
    else:
        # `raises` rather than a caught-and-inspected error: a bare
        # "is closed" not in str(error) passes when nothing is raised at all,
        # because str(None) is "None" -- and a non-terminal backend that
        # silently *succeeds* in writing to the root is the defect this whole
        # change exists for. The root refusal is unconditional, so the
        # non-terminal arm owes it just as the terminal arm owes BackendUnavailable.
        with pytest.raises(InvalidPath) as exc_info:
            backend.write(root, b"x")
        assert "is closed" not in str(exc_info.value)


# **Every root-reaching read operation, enumerated rather than sampled.** This is
# the third root pre-check and the one with no cell until BUG-254: the two above
# reach a file-shaped and a write-shaped guard, and neither routes through a
# probe or an aggregate.
#
# The enumeration is deliberate and was not the first attempt. BUG-254 patched
# the three probes from a reading of where the hazard was, and the next review
# round found the same defect one operation over, in ``get_folder_info`` — a
# state that reading had not considered. A third reading is not more likely to be
# exhaustive than the first two, so the axis is parametrised instead: every
# operation that can answer the root without a round trip belongs here, and a
# future one is added to this dict rather than argued about.
#
# ``get_folder_info`` is the folder-shaped member and is gated separately below,
# since a LIST-capable backend need not aggregate.
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
def test_close_posture_outranks_the_root_probes(backend: Backend, root: str, op_name: str) -> None:
    """The same ordering on the probes, which answer the root from the key.

    BE-029 makes the root's answers definitional, so a backend that decides them
    from the string returns before touching the lazy client accessor that carries
    the closed guard — and then a closed store answers ``True`` instead of
    refusing. That is the ordering BE-020 says must not depend on which line the
    implementer typed first, and the two cells above cannot reach it: one drives
    ``read_bytes`` and the other ``write``, neither of which is a probe.

    The gap was not hypothetical, and it was not found once. Five classes
    answered the root probes after ``close()`` — three of them before BUG-254 and
    two more because that item's first fix pass put its short-circuit ahead of
    the guard. The round that fixed those three operations was followed by one
    that found the same defect in ``get_folder_info``, reached a different way:
    an ``except Exception`` catching the guard's own error and re-classifying it.
    That is why the dict above enumerates the axis instead of listing the
    operations someone thought of.

    Gated on LIST for the same reason ``TestBackendRootPath`` is: "the root is a
    folder" presupposes a backend that has folders.
    """
    _require(backend, Capability.LIST)
    backend.close()
    if backend.close_is_terminal:
        with pytest.raises(BackendUnavailable, match="is closed"):
            _ROOT_PROBES[op_name](backend, root)
    else:
        # Reusable: it re-initialises rather than refusing, and BE-004 / BE-005
        # forbid these three from raising for an inaccessible path, so the answer
        # itself is not asserted here — only that it is not the terminal guard.
        error: Exception | None = None
        try:
            _ROOT_PROBES[op_name](backend, root)
        except Exception as exc:  # noqa: BLE001 -- any typed error is acceptable here
            error = exc
        assert "is closed" not in str(error)
